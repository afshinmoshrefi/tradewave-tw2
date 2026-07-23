#!/usr/bin/env python3
"""Publish one combined X close ledger after the appserver EOD sync completes.

No closures means no post. Copy is deterministic and uses only persisted
result fields; it never invents a causal explanation for a loss.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SITE_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(SITE_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_LIB_DIR))
if os.path.isdir("/home/flask") and "/home/flask" not in sys.path:
    sys.path.insert(0, "/home/flask")

import config
from daily_pick_close_card import generate_close_assets
from market_clock import new_york_now
from m_daily_ai_pick_social import (
    DailyPickError,
    estimated_x_length,
    post_to_x,
    validate_x_message,
)
from pick_stats import is_win, reached_target


FEATURED_HISTORY_FILE = os.environ.get(
    "TW2_FEATURED_HISTORY_FILE", "/home/flask/site/data/featured_history.json"
)
LOCK_DIR = "/var/log/tradewave"
REQUEST_TIMEOUT = 30


class CloseLedgerError(RuntimeError):
    pass


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pct(value: Any) -> str:
    return "%+.1f%%" % _number(value)


def _plural(count: int, singular: str, plural: Optional[str] = None) -> str:
    return singular if count == 1 else (plural or singular + "s")


def load_history(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise CloseLedgerError("featured-history file is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseLedgerError("featured-history file is unreadable") from exc
    if not isinstance(value, list):
        raise CloseLedgerError("featured-history data is not a list")
    return [item for item in value if isinstance(item, dict)]


def closing_entries(
    history: Iterable[Dict[str, Any]], market_date: str
) -> List[Dict[str, Any]]:
    return sorted(
        [
            entry
            for entry in history
            if entry.get("status") == "closed"
            and entry.get("actual_return") is not None
            and entry.get("resolved_session_date") == market_date
        ],
        key=lambda entry: (
            str(entry.get("symbol") or ""),
            str(entry.get("featured_date") or ""),
        ),
    )


def pending_due_entries(
    history: Iterable[Dict[str, Any]], market_date: str
) -> List[Dict[str, Any]]:
    due = []
    for entry in history:
        end_date = entry.get("end_date")
        if not end_date and entry.get("date") and entry.get("daysOut") is not None:
            try:
                end_date = (
                    dt.date.fromisoformat(str(entry["date"]))
                    + dt.timedelta(days=int(entry["daysOut"]))
                ).isoformat()
            except (TypeError, ValueError):
                continue
        if (
            end_date
            and str(end_date) <= market_date
            and not (
                entry.get("status") == "closed"
                and entry.get("actual_return") is not None
            )
        ):
            due.append(entry)
    return due


def _result_line(entry: Dict[str, Any], compact: int = 0) -> str:
    symbol = str(entry.get("symbol") or "").strip().upper()
    won = is_win(entry)
    mark = "✓" if won else "✗"
    actual = _pct(entry.get("actual_return"))
    target = _pct(entry.get("pred_return"))
    peak = _pct(entry.get("peak_return"))

    if compact >= 2:
        if reached_target(entry):
            return "%s %s target hit; close %s" % (mark, symbol, actual)
        if won:
            return "%s %s close %s" % (mark, symbol, actual)
        return "%s %s peak %s; close %s" % (mark, symbol, peak, actual)
    if compact == 1:
        if reached_target(entry):
            return "%s %s target %s hit; close %s" % (
                mark,
                symbol,
                target,
                actual,
            )
        if won:
            return "%s %s close %s (target not hit)" % (mark, symbol, actual)
        return "%s %s peak %s; target %s; close %s" % (
            mark,
            symbol,
            peak,
            target,
            actual,
        )
    if reached_target(entry):
        return "%s %s hit its %s target; closed %s." % (
            mark,
            symbol,
            target,
            actual,
        )
    if won:
        return "%s %s missed target but closed %s." % (
            mark,
            symbol,
            actual,
        )
    return "%s %s best move %s; missed %s target; closed %s." % (
        mark,
        symbol,
        peak,
        target,
        actual,
    )


def compose_close_message(
    entries: Iterable[Dict[str, Any]], market_date: str, landing_url: str
) -> str:
    rows = list(entries)
    if not rows:
        raise CloseLedgerError("there are no closed opportunities to post")
    parsed_date = dt.date.fromisoformat(market_date)
    wins = sum(1 for entry in rows if is_win(entry))
    losses = len(rows) - wins
    header = "TradeWave Close Ledger — %s" % parsed_date.strftime("%b %d")
    summary = "%d AI %s closed: %d %s, %d %s." % (
        len(rows),
        _plural(len(rows), "window"),
        wins,
        _plural(wins, "win"),
        losses,
        _plural(losses, "loss", "losses"),
    )

    for compact in (0, 1, 2):
        message = "\n".join(
            [header, summary, ""]
            + [_result_line(entry, compact) for entry in rows]
            + ["", "Full ledger: " + landing_url]
        )
        if estimated_x_length(message) <= 280:
            validate_x_message(message)
            return message
    raise CloseLedgerError(
        "combined close post exceeds X's 280-character limit"
    )


def lock_path(lock_dir: str, market_date: str) -> str:
    return os.path.join(
        lock_dir, "m_daily_pick_close_social.x.%s.json" % market_date
    )


def read_lock(lock_dir: str, market_date: str) -> Optional[Dict[str, Any]]:
    path = lock_path(lock_dir, market_date)
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {"status": "complete"}
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {"status": "complete"}


def write_lock(
    lock_dir: str,
    market_date: str,
    status: str,
    entries: Iterable[Dict[str, Any]],
    result: Optional[Dict[str, Any]] = None,
) -> None:
    os.makedirs(lock_dir, exist_ok=True)
    path = lock_path(lock_dir, market_date)
    temporary = "%s.tmp.%s" % (path, os.getpid())
    payload = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "market_date": market_date,
        "status": status,
        "symbols": [str(entry.get("symbol") or "") for entry in entries],
    }
    if result:
        payload.update(
            {
                "provider": "x-direct",
                "post_id": result.get("post_id"),
                "post_url": result.get("post_url"),
            }
        )
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def fetch_eod_status(
    appserver_url: Optional[str] = None,
    service_key: Optional[str] = None,
) -> Dict[str, Any]:
    base_url = (appserver_url or config.appserver_url).rstrip("/")
    key = service_key if service_key is not None else config.SERVICE_API_KEY
    if not base_url or not key:
        raise CloseLedgerError("appserver URL or service API key is missing")
    try:
        login = requests.post(
            base_url + "/login/api",
            headers={"X-Service-Key": key},
            timeout=REQUEST_TIMEOUT,
        )
        login.raise_for_status()
        token = login.json().get("token")
        if not token:
            raise CloseLedgerError("appserver service login failed")
        response = requests.get(
            base_url + "/internal/eod-status",
            params={"token": token},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        status = response.json()
    except requests.RequestException as exc:
        raise CloseLedgerError("appserver EOD status is unavailable") from exc
    if not isinstance(status, dict):
        raise CloseLedgerError("appserver EOD status is invalid")
    return status


def validate_eod_status(status: Dict[str, Any]) -> str:
    market_date = str(status.get("market_date") or "")
    try:
        dt.date.fromisoformat(market_date)
    except ValueError as exc:
        raise CloseLedgerError("appserver EOD status has no market date") from exc
    if status.get("ok") is not True:
        raise CloseLedgerError("appserver EOD sync is not complete")
    if str(status.get("latest_us_date") or "") < market_date:
        raise CloseLedgerError("appserver US CSVs are not current")
    completed = status.get("completed_at")
    try:
        completed_at = dt.datetime.fromisoformat(str(completed))
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError) as exc:
        raise CloseLedgerError("appserver EOD status has no completion time") from exc
    age = dt.datetime.now(dt.timezone.utc) - completed_at.astimezone(dt.timezone.utc)
    if age < dt.timedelta(minutes=-5) or age > dt.timedelta(hours=30):
        raise CloseLedgerError("appserver EOD completion marker is stale")
    return market_date


def regenerate_scorecard() -> None:
    generator = Path(__file__).resolve().parent / "generate_scorecard.py"
    result = subprocess.run(
        [sys.executable, str(generator)],
        cwd=str(generator.parent),
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        raise CloseLedgerError(
            "scorecard regeneration failed with exit %d" % result.returncode
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Publish to X")
    parser.add_argument("--force", action="store_true", help="Ignore completion lock")
    parser.add_argument("--date", help="Market date YYYY-MM-DD")
    parser.add_argument("--history", default=FEATURED_HISTORY_FILE)
    parser.add_argument("--lock-dir", default=LOCK_DIR)
    args = parser.parse_args()

    if args.date:
        try:
            dt.date.fromisoformat(args.date)
        except ValueError:
            print("ERROR: --date must be YYYY-MM-DD")
            return 2

    environment = str(getattr(config, "tw2_env", "")).strip().lower()
    if args.send and environment != "prod":
        print("SKIP: X writes are production-only (TW2_ENV=%s)." % (
            environment or "unset"
        ))
        return 0
    if args.send and not bool(
        getattr(config, "X_CLOSE_POSTING_ENABLED", False)
    ):
        print("ERROR: close-ledger X posting is disabled.")
        return 4

    try:
        if args.send:
            status = fetch_eod_status()
            status_date = validate_eod_status(status)
            market_date = args.date or status_date
            if market_date != status_date:
                raise CloseLedgerError(
                    "requested date does not match the completed appserver sync"
                )
            existing = read_lock(args.lock_dir, market_date)
            if existing and not args.force:
                print(
                    "Already completed for %s: %s"
                    % (
                        market_date,
                        existing.get("post_url") or existing.get("status"),
                    )
                )
                return 0
            regenerate_scorecard()
        else:
            market_date = args.date or new_york_now().date().isoformat()

        history = load_history(args.history)
        pending = pending_due_entries(history, market_date)
        if pending:
            symbols = ", ".join(
                str(entry.get("symbol") or "?") for entry in pending
            )
            raise CloseLedgerError(
                "due opportunities are still awaiting final appserver bars: "
                + symbols
            )
        entries = closing_entries(history, market_date)
        if not entries:
            print("No AI pick windows closed on %s; no X post." % market_date)
            if args.send:
                write_lock(
                    args.lock_dir, market_date, "no_closures", entries
                )
            return 0

        domain = (
            getattr(config, "domain_root", "") or "https://tradewave.ai/"
        ).rstrip("/") + "/"
        landing_url = (
            domain + "close-ledger/%s.html" % market_date
        )
        message = compose_close_message(entries, market_date, landing_url)
        print("=== TradeWave AI close ledger -> X ===")
        print("Market date: %s" % market_date)
        print("Closed: %d" % len(entries))
        print("Weighted length: %d/280" % estimated_x_length(message))
        print("--- X post ---")
        print(message)

        if not args.send:
            print("\nDRY-RUN: nothing was posted.")
            return 0

        assets = generate_close_assets(
            entries,
            market_date,
            getattr(config, "web_root_dir", "/var/www/tradewave/"),
            domain,
        )
        print("Close-ledger card ready: %s" % assets["image_path"])
        result = post_to_x(message)
        if not result.get("ok"):
            print("ERROR posting to X: %s" % result.get("error", "unknown"))
            return 5
        write_lock(
            args.lock_dir, market_date, "posted", entries, result
        )
        print("Posted successfully: %s" % result["post_url"])
        return 0
    except (CloseLedgerError, DailyPickError) as exc:
        print("WAIT: %s" % exc)
        return 3
    except (OSError, RuntimeError, ValueError) as exc:
        print("ERROR: %s" % exc)
        return 5


if __name__ == "__main__":
    sys.exit(main())
