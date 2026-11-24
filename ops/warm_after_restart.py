#!/usr/bin/env python3
"""Warm the appserver right after a restart, before traffic (TW-BUG-0024).

A freshly restarted appserver loads market data inside each gunicorn worker on
first use. The first burst of scans after a deploy then queues behind that load
(Nov 24 2026: ~29 s for the first scan vs ~4 s once warm). This script sends the
ordinary opportunity-list and chart requests for every market through the normal
service-account path (apiserver.appserver_client, X-Service-Key login), several
copies at once so every worker loads its data.

It deliberately does NOT touch the API's Redis scan cache or call /v1/scan, so a
release gate that runs afterwards still measures an uncached scan on a warm
server. It never changes data, prints no secrets, is bounded in time, and always
exits 0: a failed warm-up is logged and the deploy/gate continue unchanged.

Run as flask on the APP box with secrets.env sourced, from the release checkout:
    /home/flask/venv-api/bin/python ops/warm_after_restart.py [--deadline 150] [--copies 4]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _warm_market(client, market_id: str, today) -> str:
    start = time.perf_counter()
    rows = client.opportunities(market_id, today.isoformat())
    detail = f"{len(rows)} rows"
    if rows:
        top = rows[0]
        symbol = top.get("symbol")
        entry = top.get("entry_date") or today.isoformat()
        days = top.get("days_out") or 30
        if symbol:
            client.chart_stats_and_years(market_id, symbol, entry, days, "10")
            detail += ", 1 chart"
    return f"{detail} in {time.perf_counter() - start:.1f}s"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--deadline", type=float, default=150.0,
                        help="stop waiting after this many seconds (default 150)")
    parser.add_argument("--copies", type=int, default=4,
                        help="parallel copies per market, to reach every worker (default 4)")
    args = parser.parse_args()
    t0 = time.perf_counter()
    try:
        from apiserver import appserver_client as client
        from apiserver.seasonal_evidence import market_today
        markets = [m["id"] for m in client.list_markets()]
    except Exception as exc:  # noqa: BLE001 - warm-up is fail-soft by design
        print(f"WARMUP SKIPPED: could not list markets ({type(exc).__name__})", flush=True)
        return 0
    today = market_today()
    copies = max(1, min(int(args.copies), 8))
    ok = failed = 0
    pool = cf.ThreadPoolExecutor(max_workers=min(16, len(markets) * copies or 1))
    futures = {pool.submit(_warm_market, client, m, today): m
               for m in markets for _ in range(copies)}
    done, pending = cf.wait(futures, timeout=max(1.0, args.deadline))
    seen = set()
    for fut in done:
        market = futures[fut]
        try:
            detail = fut.result()
            ok += 1
            if market not in seen:
                print(f"  market {market}: {detail}", flush=True)
                seen.add(market)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  market {market}: {type(exc).__name__}", flush=True)
    for fut in pending:
        fut.cancel()
    pool.shutdown(wait=False, cancel_futures=True)
    print(f"WARMUP DONE: {ok} ok, {failed} failed, {len(pending)} still running at deadline, "
          f"{len(markets)} markets x {copies}, {time.perf_counter() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"WARMUP FAILED SOFT: {type(exc).__name__}", flush=True)
        raise SystemExit(0)
