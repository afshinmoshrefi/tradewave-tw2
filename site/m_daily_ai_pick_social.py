#!/usr/bin/env python3
"""Publish TradeWave's canonical daily AI pick to X.

The homepage generator is the sole writer of the daily-pick record in
``featured_history.json``. This job reads that structured record directly; it
does not scrape the separate Top-10 HTML page.

Safety rules:
  * Dry-run is the default. ``--send`` is required for a network write.
  * Network writes require both ``TW2_ENV=prod`` and
    ``TW2_X_POSTING_ENABLED=1``.
  * A successful post is locked by featured date. Failed attempts remain
    retryable, and a lock is written atomically only after X returns a post id.
  * The newest record must match today's featured date unless ``--date`` is
    supplied explicitly for an operator-controlled backfill.

Usage:
    python m_daily_ai_pick_social.py
    python m_daily_ai_pick_social.py --send
    python m_daily_ai_pick_social.py --date 2026-07-21 --send
    python m_daily_ai_pick_social.py --send --force
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import requests

try:
    from requests_oauthlib import OAuth1
except ImportError:  # pragma: no cover - exercised on a misconfigured box
    OAuth1 = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SITE_LIB_DIR = Path(__file__).resolve().parent / "lib"
if str(SITE_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(SITE_LIB_DIR))
if os.path.isdir("/home/flask") and "/home/flask" not in sys.path:
    sys.path.insert(0, "/home/flask")

import config
from daily_pick_social_card import refresh_scorecard_social_meta


FEATURED_HISTORY_FILE = os.environ.get(
    "TW2_FEATURED_HISTORY_FILE", "/home/flask/site/data/featured_history.json"
)
LOCK_DIR = "/var/log/tradewave"
X_CREATE_POST_URL = "https://api.x.com/2/tweets"
REQUEST_TIMEOUT = 30
MAX_X_CHARS = 280
X_SHORTENED_URL_LENGTH = 23

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CASHTAG_RE = re.compile(r"(?<!\w)\$[A-Za-z][A-Za-z0-9._-]*")


class DailyPickError(RuntimeError):
    """The canonical daily-pick record cannot be safely published."""


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"l", "long", "buy"}:
        return "Long"
    if raw in {"s", "short", "sell"}:
        return "Short"
    raise DailyPickError("daily pick has an invalid direction")


def _friendly_date(value: Any) -> str:
    try:
        parsed = dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise DailyPickError("daily pick has an invalid date") from exc
    return "%s %d" % (parsed.strftime("%b"), parsed.day)


def _lookback_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw.isdigit():
        return "%s-year history" % raw
    match = re.fullmatch(r"pe([0-3])-(\d+)", raw)
    if match:
        phase, samples = match.groups()
        phase_label = "PE" if phase == "0" else "PE+%s" % phase
        return "%s %s samples" % (samples, phase_label)
    return "Historical sample"


def load_featured_pick(history_path: str, featured_date: str) -> Dict[str, Any]:
    """Load the one canonical pick for ``featured_date`` from the ledger."""
    try:
        with open(history_path, "r", encoding="utf-8") as handle:
            history = json.load(handle)
    except FileNotFoundError as exc:
        raise DailyPickError("featured-history file is missing: %s" % history_path) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyPickError("featured-history file is unreadable") from exc

    if not isinstance(history, list):
        raise DailyPickError("featured-history data is not a list")

    matches = [
        item for item in history
        if isinstance(item, dict) and item.get("featured_date") == featured_date
    ]
    if not matches:
        newest = history[-1].get("featured_date") if history and isinstance(history[-1], dict) else None
        if newest:
            raise DailyPickError(
                "no pick for %s; newest ledger record is %s" % (featured_date, newest)
            )
        raise DailyPickError("no pick for %s" % featured_date)

    pick = matches[-1]
    required = ("symbol", "date", "daysOut", "direction", "featured_date")
    missing = [name for name in required if pick.get(name) in (None, "")]
    if missing:
        raise DailyPickError("daily pick is missing fields: %s" % ", ".join(missing))

    try:
        days_out = int(pick["daysOut"])
    except (TypeError, ValueError) as exc:
        raise DailyPickError("daily pick has an invalid holding period") from exc
    if days_out <= 0:
        raise DailyPickError("daily pick holding period must be positive")

    _direction(pick["direction"])
    _friendly_date(pick["date"])
    return pick


def estimated_x_length(message: str) -> int:
    """Estimate X's weighted length for ordinary ASCII copy and t.co URLs."""
    urls = _URL_RE.findall(message)
    return len(_URL_RE.sub("", message)) + len(urls) * X_SHORTENED_URL_LENGTH


def validate_x_message(message: str) -> None:
    length = estimated_x_length(message)
    if length > MAX_X_CHARS:
        raise DailyPickError(
            "composed X post is %d weighted characters (max %d)" % (length, MAX_X_CHARS)
        )
    cashtags = _CASHTAG_RE.findall(message)
    if len(cashtags) > 1:
        raise DailyPickError("X self-serve posts may contain only one cashtag")


def compose_x_message(pick: Dict[str, Any], landing_url: str) -> str:
    """Compose factual copy only from the persisted daily-pick record."""
    symbol = str(pick["symbol"]).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", symbol):
        raise DailyPickError("daily pick has an invalid symbol")

    direction = _direction(pick["direction"])
    start = _friendly_date(pick["date"])
    days_out = int(pick["daysOut"])
    end_value = pick.get("end_date")
    if not end_value:
        end_value = (
            dt.date.fromisoformat(str(pick["date"])) + dt.timedelta(days=days_out)
        ).isoformat()
    end = _friendly_date(end_value)

    lines = [
        "Today's TradeWave AI Pick: $%s" % symbol,
        "%s seasonal window | %s-%s (%dd)" % (
            direction, start, end, days_out,
        ),
    ]

    stats = []
    avg_profit = _number(pick.get("avg_profit"))
    sharpe = _number(pick.get("sharpe_ratio"))
    if avg_profit is not None:
        stats.append("Hist avg %.1f%%" % avg_profit)
    if sharpe is not None:
        stats.append("Sharpe %.2f" % sharpe)
    stats.append(_lookback_label(pick.get("years")))
    if stats:
        lines.append(" | ".join(stats))

    win_prob = _number(pick.get("win_prob"))
    if win_prob is not None:
        probability_pct = win_prob * 100.0 if 0 <= win_prob <= 1 else win_prob
        lines.append("Est. win probability: %.0f%%" % probability_pct)

    lines.extend([
        "",
        "Full history + public scorecard:",
        landing_url,
        "",
        "Research only. Not financial advice.",
    ])
    message = "\n".join(lines)
    validate_x_message(message)
    return message


def _x_credentials() -> Dict[str, str]:
    return {
        "api_key": getattr(config, "X_API_KEY", ""),
        "api_secret": getattr(config, "X_API_KEY_SECRET", ""),
        "access_token": getattr(config, "X_ACCESS_TOKEN", ""),
        "access_token_secret": getattr(config, "X_ACCESS_TOKEN_SECRET", ""),
    }


def post_to_x(message: str, http_post=None) -> Dict[str, Any]:
    """Create one X post with OAuth 1.0a user context."""
    if OAuth1 is None:
        return {"ok": False, "error": "requests-oauthlib is not installed"}

    credentials = _x_credentials()
    missing = [name for name, value in credentials.items() if not value]
    if missing:
        return {
            "ok": False,
            "error": "missing X credentials: %s" % ", ".join(missing),
        }

    auth = OAuth1(
        credentials["api_key"],
        credentials["api_secret"],
        credentials["access_token"],
        credentials["access_token_secret"],
    )
    sender = http_post or requests.post
    try:
        response = sender(
            X_CREATE_POST_URL,
            auth=auth,
            json={"text": message},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {"ok": False, "error": "X request failed: %s" % type(exc).__name__}

    try:
        body = response.json()
    except (TypeError, ValueError):
        body = None

    post_id = None
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        post_id = body["data"].get("id")
    if response.status_code == 201 and post_id:
        return {
            "ok": True,
            "status": response.status_code,
            "post_id": str(post_id),
            "post_url": "https://x.com/i/web/status/%s" % post_id,
        }

    error_detail = "HTTP %s" % response.status_code
    if isinstance(body, dict):
        error_detail = str(body.get("detail") or body.get("title") or error_detail)
    return {"ok": False, "status": response.status_code, "error": error_detail[:300]}


def lock_path(lock_dir: str, featured_date: str) -> str:
    return os.path.join(lock_dir, "m_daily_ai_pick_social.x.%s.json" % featured_date)


def read_post_lock(lock_dir: str, featured_date: str) -> Optional[Dict[str, Any]]:
    path = lock_path(lock_dir, featured_date)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {"lock": path}
    except (OSError, json.JSONDecodeError):
        return {"lock": path}


def write_post_lock(
    lock_dir: str,
    featured_date: str,
    pick: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    os.makedirs(lock_dir, exist_ok=True)
    path = lock_path(lock_dir, featured_date)
    temporary = "%s.tmp.%s" % (path, os.getpid())
    payload = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "featured_date": featured_date,
        "symbol": pick.get("symbol"),
        "provider": "x-direct",
        "post_id": result.get("post_id"),
        "post_url": result.get("post_url"),
    }
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _posting_enabled() -> bool:
    return bool(getattr(config, "X_POSTING_ENABLED", False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Publish to X")
    parser.add_argument("--force", action="store_true", help="Ignore an existing success lock")
    parser.add_argument("--date", help="Featured date YYYY-MM-DD (default: today)")
    parser.add_argument("--history", default=FEATURED_HISTORY_FILE)
    parser.add_argument("--lock-dir", default=LOCK_DIR)
    args = parser.parse_args()

    featured_date = args.date or dt.date.today().isoformat()
    try:
        dt.date.fromisoformat(featured_date)
    except ValueError:
        print("ERROR: --date must be YYYY-MM-DD")
        return 2

    print("=== TradeWave canonical daily pick -> X ===")
    print("Featured date: %s" % featured_date)
    print("Source: %s" % args.history)

    try:
        pick = load_featured_pick(args.history, featured_date)
        domain = (getattr(config, "domain_root", "") or "https://tradewave.ai/").rstrip("/") + "/"
        landing_url = domain + "scorecard.html?pick=" + featured_date
        message = compose_x_message(pick, landing_url)
    except DailyPickError as exc:
        print("ERROR: %s" % exc)
        return 3

    print("Symbol: %s" % pick.get("symbol"))
    print("Weighted length: %d/%d" % (estimated_x_length(message), MAX_X_CHARS))
    print("--- X post ---")
    print(message)

    if not args.send:
        print("\nDRY-RUN: nothing was posted. Re-run with --send to publish.")
        return 0

    environment = str(getattr(config, "tw2_env", "")).strip().lower()
    if environment != "prod":
        print("\nSKIP: X writes are production-only (TW2_ENV=%s)." % (environment or "unset"))
        return 0
    if not _posting_enabled():
        print("\nERROR: X posting is disabled. Set TW2_X_POSTING_ENABLED=1 after verification.")
        return 4

    existing = read_post_lock(args.lock_dir, featured_date)
    if existing and not args.force:
        print("\nAlready posted for %s: %s" % (
            featured_date, existing.get("post_url") or lock_path(args.lock_dir, featured_date),
        ))
        return 0

    try:
        metadata = refresh_scorecard_social_meta(
            pick,
            getattr(config, "web_root_dir", "/var/www/tradewave/"),
            domain,
        )
        print("Social card ready: %s" % metadata["image_url"])
    except (OSError, RuntimeError, ValueError) as exc:
        print("\nERROR: social card preparation failed: %s" % exc)
        return 5

    result = post_to_x(message)
    if not result.get("ok"):
        print("\nERROR posting to X: %s" % result.get("error", "unknown error"))
        return 5

    try:
        write_post_lock(args.lock_dir, featured_date, pick, result)
    except OSError as exc:
        print("\nERROR: X post succeeded but success lock could not be written: %s" % exc)
        print("Post URL: %s" % result["post_url"])
        return 6

    print("\nPosted successfully: %s" % result["post_url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
