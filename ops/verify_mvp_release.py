#!/usr/bin/env python3
"""Pre-deployment API/MCP auth and bounded-load gate.

This script is read-only against the target. It creates no users, keys, products,
or subscriptions. Supply an existing test API key and an existing WorkOS OAuth
access token through environment variables; neither value is printed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass

import requests


@dataclass
class Sample:
    seconds: float
    status: int
    ok: bool


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("inf")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
    return ordered[index]


def api_get(url: str, token: str, timeout: float) -> requests.Response:
    return requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=timeout,
    )


def require_api_auth(api_base: str, key: str, timeout: float) -> None:
    response = api_get(f"{api_base}/me", key, timeout)
    if response.status_code != 200:
        raise RuntimeError(f"API BYOK verification failed with HTTP {response.status_code}")


def _mcp_json(response: requests.Response) -> dict:
    content_type = response.headers.get("Content-Type", "")
    if "text/event-stream" not in content_type:
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError("MCP response contained no JSON event")


def require_mcp_auth(mcp_url: str, token: str, label: str, timeout: float) -> None:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "tradewave-release-gate", "version": "1"},
        },
    }
    response = requests.post(mcp_url, headers=headers, json=initialize, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"MCP {label} initialize failed with HTTP {response.status_code}")
    body = _mcp_json(response)
    if body.get("error") or not body.get("result"):
        raise RuntimeError(f"MCP {label} initialize returned a protocol error")

    session_id = response.headers.get("Mcp-Session-Id")
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    headers["MCP-Protocol-Version"] = "2025-03-26"
    tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    response = requests.post(mcp_url, headers=headers, json=tools, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"MCP {label} tools/list failed with HTTP {response.status_code}")
    body = _mcp_json(response)
    listed = ((body.get("result") or {}).get("tools") or [])
    if not listed:
        raise RuntimeError(f"MCP {label} tools/list returned no tools")


def one_sample(url: str, key: str, timeout: float) -> Sample:
    started = time.perf_counter()
    try:
        response = api_get(url, key, timeout)
        ok = 200 <= response.status_code < 400
        return Sample(time.perf_counter() - started, response.status_code, ok)
    except requests.RequestException:
        return Sample(time.perf_counter() - started, 0, False)


def load_gate(url: str, key: str, concurrency: int, requests_count: int,
              timeout: float, max_p95: float, max_error_rate: float) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        samples = list(executor.map(
            lambda _: one_sample(url, key, timeout), range(requests_count)
        ))
    durations = [sample.seconds for sample in samples]
    failures = [sample for sample in samples if not sample.ok]
    p95 = percentile(durations, 0.95)
    error_rate = len(failures) / len(samples)
    print(
        f"load concurrency={concurrency} requests={len(samples)} "
        f"median={statistics.median(durations):.3f}s p95={p95:.3f}s "
        f"errors={error_rate:.1%}"
    )
    if p95 > max_p95:
        raise RuntimeError(f"load p95 {p95:.3f}s exceeded {max_p95:.3f}s")
    if error_rate > max_error_rate:
        statuses = sorted({sample.status for sample in failures})
        raise RuntimeError(f"load error rate {error_rate:.1%} exceeded limit; statuses={statuses}")


def require_daily_pick(api_base: str, key: str, timeout: float) -> None:
    response = api_get(f"{api_base}/daily-pick", key, timeout)
    if response.status_code != 200:
        raise RuntimeError(f"daily-pick verification failed with HTTP {response.status_code}")
    body = response.json()
    if body.get("card") is None:
        raise RuntimeError("daily-pick returned card:null")


def require_healthy(api_base: str, timeout: float) -> None:
    root = api_base.rsplit("/v1", 1)[0]
    response = requests.get(f"{root}/healthz", timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"gateway health failed with HTTP {response.status_code}")
    if response.json().get("storm_breaker_active") is not False:
        raise RuntimeError("gateway storm breaker fired during the load test")


def success_message(oauth_verified: bool) -> str:
    checks = ["API", "daily-pick", "MCP BYOK"]
    if oauth_verified:
        checks.append("OAuth")
    checks.extend(["load", "storm-breaker"])
    return "PASS: " + ", ".join(checks) + " gates"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get(
        "TW2_VERIFY_API_BASE", "http://127.0.0.1:8088/v1"
    ))
    parser.add_argument("--mcp-url", default=os.environ.get(
        "TW2_VERIFY_MCP_URL", "http://127.0.0.1:9090/mcp"
    ))
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-p95", type=float, default=15.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--skip-oauth", action="store_true",
                        help="local debugging only; never use for a release gate")
    args = parser.parse_args()

    key = os.environ.get("TW2_TEST_API_KEY", "")
    oauth = os.environ.get("TW2_TEST_OAUTH_TOKEN", "")
    if not key:
        raise RuntimeError("TW2_TEST_API_KEY is required")
    if not args.skip_oauth and not oauth:
        raise RuntimeError("TW2_TEST_OAUTH_TOKEN is required")

    api_base = args.api_base.rstrip("/")
    mcp_url = args.mcp_url.rstrip("/")
    print(f"target api={api_base} mcp={mcp_url}")
    require_api_auth(api_base, key, args.timeout)
    require_daily_pick(api_base, key, args.timeout)
    require_mcp_auth(mcp_url, key, "BYOK", args.timeout)
    if not args.skip_oauth:
        require_mcp_auth(mcp_url, oauth, "WorkOS OAuth", args.timeout)

    scan_url = f"{api_base}/scan?window=now&markets=2&limit=5&view=decision"
    load_gate(scan_url, key, args.concurrency, args.requests, args.timeout,
              args.max_p95, args.max_error_rate)
    require_healthy(api_base, args.timeout)
    print(success_message(oauth_verified=not args.skip_oauth))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, requests.RequestException, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
