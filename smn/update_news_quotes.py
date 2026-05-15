#!/usr/bin/env python3
"""
Live Quote Refresher (TW2 port from TW1 prod).

Refreshes the JSON files that the SMN and TW marketing pages poll for live
market data. Pages render with a hardcoded market-bar template + a small
JS that fetches /assets/quotes.json on load to populate live prices —
this script keeps that JSON current.

Outputs:
  /var/www/smn/assets/quotes.json       (SMN market bar; existing schema)
  /var/www/tradewave/assets/quotes.json (TW marketing equivalent; created if missing)

TW1 lineage: /home/flask/blog/update_news_quotes.py, scheduled at
`* * * * 0-5` in TW1 prod /etc/crontab (every minute, Sun-Fri).

Each run is fast: it queries the local realtime price service first (no
EODHD token cost) and falls back to EODHD direct only if the service is
unavailable.

Schema (existing /var/www/smn/assets/quotes.json):
    {"GSPC": {"close": 7365.12, "change_p": 1.4588}, ...}

Usage:
    python update_news_quotes.py [--dry-run] [--include-tw-marketing]
"""

import argparse
import datetime
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/smn')
import config
from get_price_eod import get_quote_details

# (symbol, exchange) for each market-bar instrument. Mirrors the keys in
# the existing /var/www/smn/assets/quotes.json. TW1_SPEC: confirm full set
# against TW1's update_news_quotes.py.
MARKET_BAR_SYMBOLS: List[Tuple[str, str]] = [
    ("GSPC", "INDX"),  # S&P 500
    ("DJI",  "INDX"),  # Dow Jones
    ("IXIC", "INDX"),  # NASDAQ Composite
    ("VIX",  "INDX"),
    ("CL",   "COMM"),  # WTI crude futures
    ("NG",   "COMM"),  # natural gas futures
    ("GC",   "COMM"),  # gold futures
]

SMN_QUOTES_JSON = "/var/www/smn/assets/quotes.json"
TW_QUOTES_JSON = "/var/www/tradewave/assets/quotes.json"


def fetch_one(symbol: str, exchange: str) -> Optional[Dict[str, float]]:
    q = get_quote_details(symbol, exchange)
    if not q:
        return None
    close = q.get("close")
    change_p = q.get("change_p")
    if close is None:
        return None
    out: Dict[str, float] = {"close": round(float(close), 4)}
    if change_p is not None:
        out["change_p"] = round(float(change_p), 4)
    return out


def write_atomic(path: str, payload: Dict[str, Any]) -> None:
    out_dir = os.path.dirname(path)
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".quotes.", dir=out_dir)
    os.close(fd)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    os.replace(tmp, path)
    os.chmod(path, 0o644)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-tw-marketing", action="store_true",
                   default=True,
                   help="Also write /var/www/tradewave/assets/quotes.json (default on)")
    p.add_argument("--smn-only", action="store_true",
                   help="Write only the SMN quotes.json")
    args = p.parse_args()

    started = datetime.datetime.now(datetime.timezone.utc)

    payload: Dict[str, Dict[str, float]] = {}
    failed: List[str] = []
    for sym, exch in MARKET_BAR_SYMBOLS:
        q = fetch_one(sym, exch)
        if q is None:
            failed.append("%s.%s" % (sym, exch))
            continue
        payload[sym] = q

    elapsed = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
    print("%s — fetched %d/%d quotes in %.2fs (failed: %s)" % (
        started.isoformat(), len(payload), len(MARKET_BAR_SYMBOLS),
        elapsed, ",".join(failed) if failed else "none"))

    if not payload:
        # Don't blow away existing files with an empty JSON. Fail soft.
        print("All quote lookups failed — leaving JSON files unchanged.")
        return 1

    if args.dry_run:
        print("DRY-RUN payload:", json.dumps(payload))
        return 0

    write_atomic(SMN_QUOTES_JSON, payload)
    print("Wrote %s (%d symbols)" % (SMN_QUOTES_JSON, len(payload)))

    if not args.smn_only and args.include_tw_marketing:
        write_atomic(TW_QUOTES_JSON, payload)
        print("Wrote %s (%d symbols)" % (TW_QUOTES_JSON, len(payload)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
