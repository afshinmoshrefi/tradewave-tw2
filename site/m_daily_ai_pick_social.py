#!/usr/bin/env python3
"""
Daily AI Pick — Social Media Poster (TW2 port from TW1 prod).

Reads /var/www/tradewave/daily-ai-pick.html, extracts the day's top pick,
and posts to:
  - Facebook Page (Graph API) — via config.FACEBOOK_PAGE_ID + FACEBOOK_ACCESS_TOKEN
  - X / Twitter via Publer — via config.PUBLER_API_KEY + PUBLER_WORKSPACE_ID + PUBLER_X_ACCOUNT_ID

TW1 lineage: /home/flask/blog/m_daily_ai_pick_social.py, scheduled at
`10 6 * * 0-5` in TW1 prod /etc/crontab.

TW2 has zero existing social-posting code (only credentials in config.py).
This file is the FIRST implementation in TW2; the Publer/FB API call
shapes are taken from public API docs, not from TW1 source. Treat as
draft until validated against a TW1 reference post.

Safety: dry-run by default. Add --send to actually publish.

Usage:
    python m_daily_ai_pick_social.py             # dry-run (default)
    python m_daily_ai_pick_social.py --send      # actually post
    python m_daily_ai_pick_social.py --send --skip-fb     # X only
    python m_daily_ai_pick_social.py --send --skip-x      # FB only
"""

import argparse
import datetime
import json
import os
import re
import sys
from typing import Any, Dict, Optional

import requests

sys.path.insert(0, '/home/flask')
import config

INPUT_HTML = "/var/www/tradewave/daily-ai-pick.html"
LOCK_DIR = "/var/log/tradewave"
MAX_AGE_HOURS = 24

# Graph API version. v18 was current at time of writing; bump as Meta
# deprecates. TW1_SPEC: confirm against TW1 m_daily_ai_pick_social.py.
FB_GRAPH_VERSION = "v18.0"

# Publer API base. TW1_SPEC: confirm endpoint shape.
PUBLER_BASE = "https://app.publer.io/api/v1"

REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Pick extraction
# ---------------------------------------------------------------------------

_FIRST_ROW_RE = re.compile(
    r'<tr[^>]*>\s*<td[^>]*class="r-num"[^>]*>(?P<rank>\d+)</td>.*?'
    r'<td[^>]*class="r-sym"[^>]*>.*?>(?P<symbol>[A-Z\.\-]+)</a>.*?'
    r'<td[^>]*class="r-comp"[^>]*>(?P<company>[^<]+)</td>.*?'
    r'<td[^>]*class="r-mkt"[^>]*>(?P<market>[^<]+)</td>.*?'
    r'<td[^>]*class="r-dir\s+(?P<direction>long|short)[^"]*"[^>]*>[^<]+</td>.*?'
    r'<td[^>]*class="r-sr"[^>]*>(?P<sr>[\d\.]+)</td>.*?'
    r'<td[^>]*class="r-ap"[^>]*>(?P<ap>[\d\.\-%]+)</td>',
    re.IGNORECASE | re.DOTALL,
)

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def extract_top_pick(html_path: str) -> Optional[Dict[str, Any]]:
    with open(html_path, "r", encoding="utf-8") as f:
        src = f.read()

    t = _TITLE_RE.search(src)
    title = t.group(1).strip() if t else "TradeWave Daily AI Pick"

    m = _FIRST_ROW_RE.search(src)
    if not m:
        return {"title": title, "first_row": None}

    return {
        "title": title,
        "first_row": {
            "rank": int(m.group("rank")),
            "symbol": m.group("symbol"),
            "company": m.group("company").strip(),
            "market": m.group("market").strip(),
            "direction": m.group("direction").capitalize(),
            "sharpe": float(m.group("sr")),
            "avg_profit": m.group("ap").strip(),
        },
    }


# ---------------------------------------------------------------------------
# Message composition
# ---------------------------------------------------------------------------

def compose_message(pick: Dict[str, Any], landing_url: str) -> Dict[str, str]:
    """Return {"long": fb_text, "short": x_text}."""
    row = pick.get("first_row")
    today = datetime.date.today().strftime("%a %b %d")

    if not row:
        long_text = (
            "TradeWave Daily AI Pick — %s\n\n"
            "Today's top 10 AI-scored seasonal patterns are live.\n\n"
            "%s"
        ) % (today, landing_url)
        short_text = "TradeWave Daily AI Pick — %s — see today's top 10 → %s" % (today, landing_url)
        return {"long": long_text, "short": short_text}

    long_text = (
        "TradeWave Daily AI Pick — %s\n\n"
        "#1 today: %s (%s) — %s seasonal pattern\n"
        "Sharpe Ratio: %.2f | Avg Profit: %s\n\n"
        "See the full top 10 → %s"
    ) % (today, row["symbol"], row["company"], row["direction"],
         row["sharpe"], row["avg_profit"], landing_url)

    short_text = (
        "TradeWave AI Pick — %s: $%s %s seasonal (SR %.2f, AvgP %s). Top 10 → %s"
    ) % (today, row["symbol"], row["direction"], row["sharpe"],
         row["avg_profit"], landing_url)
    # X has a 280-char limit; truncate if needed.
    if len(short_text) > 280:
        short_text = short_text[:277] + "..."
    return {"long": long_text, "short": short_text}


# ---------------------------------------------------------------------------
# Facebook Graph API
# ---------------------------------------------------------------------------

def post_to_facebook(message: str, link: str) -> Dict[str, Any]:
    page_id = config.FACEBOOK_PAGE_ID
    token = config.FACEBOOK_ACCESS_TOKEN
    if not page_id or not token:
        return {"ok": False, "error": "FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not set"}
    url = "https://graph.facebook.com/%s/%s/feed" % (FB_GRAPH_VERSION, page_id)
    params = {
        "message": message,
        "link": link,
        "access_token": token,
    }
    try:
        resp = requests.post(url, data=params, timeout=REQUEST_TIMEOUT)
        ok = resp.status_code in (200, 201)
        return {"ok": ok, "status": resp.status_code, "body": resp.text[:400]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Publer (X / Twitter)
# ---------------------------------------------------------------------------

def post_to_x_via_publer(message: str) -> Dict[str, Any]:
    """Schedule an immediate X post via Publer.

    TW1_SPEC: confirm the exact Publer endpoint + payload schema against
    a TW1 reference. Below is the documented v1 shape.
    """
    api_key = config.PUBLER_API_KEY
    workspace = config.PUBLER_WORKSPACE_ID
    x_account = config.PUBLER_X_ACCOUNT_ID
    if not api_key or not workspace or not x_account:
        return {"ok": False, "error":
                "PUBLER_API_KEY, PUBLER_WORKSPACE_ID or PUBLER_X_ACCOUNT_ID not set"}

    url = "%s/posts/schedule" % PUBLER_BASE
    headers = {
        "Authorization": "Bearer-API %s" % api_key,
        "Publer-Workspace-Id": workspace,
        "Content-Type": "application/json",
    }
    payload = {
        "bulk": {
            "state": "scheduled",
            "type": "post",
            "accounts": [x_account],
            "posts": [{
                "networks": {
                    "default": {
                        "details": {"text": message},
                    },
                },
                "scheduled_at": None,  # null = post immediately
            }],
        }
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        ok = resp.status_code in (200, 201, 202)
        return {"ok": ok, "status": resp.status_code, "body": resp.text[:400]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------

def lock_path(day: datetime.date) -> str:
    return os.path.join(LOCK_DIR, "m_daily_ai_pick_social.%s.lock" % day.isoformat())


def already_posted(day: datetime.date) -> bool:
    return os.path.exists(lock_path(day))


def mark_posted(day: datetime.date, info: Dict[str, Any]) -> None:
    p = lock_path(day)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                       "day": day.isoformat(), **info}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--send", action="store_true",
                   help="Actually post (default: dry-run)")
    p.add_argument("--skip-fb", action="store_true")
    p.add_argument("--skip-x", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="Post even if today's lock file exists")
    p.add_argument("--input", default=INPUT_HTML)
    args = p.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    print("=== m_daily_ai_pick_social.py — TW2 port ===")
    print("Started at %s   (dry-run=%s)" % (now.isoformat(), not args.send))

    if not os.path.exists(args.input):
        print("ERROR: %s does not exist." % args.input)
        return 2

    age_h = (now.timestamp() - os.path.getmtime(args.input)) / 3600.0
    if age_h > MAX_AGE_HOURS:
        print("ERROR: %s is %.1fh old (> %dh). Refusing to post stale picks."
              % (args.input, age_h, MAX_AGE_HOURS))
        return 3

    if args.send and not args.force and already_posted(today):
        print("Already posted today (%s); use --force to re-send. Exiting cleanly."
              % lock_path(today))
        return 0

    pick = extract_top_pick(args.input)
    if pick is None:
        print("ERROR: could not parse %s" % args.input)
        return 4

    domain = (config.domain_root.rstrip("/") + "/") if config.domain_root else "https://tw2.trxstat.com/"
    landing_url = domain + "daily-ai-pick.html"
    msgs = compose_message(pick, landing_url)

    print("--- FB message ---")
    print(msgs["long"])
    print("--- X message ---")
    print(msgs["short"])

    if not args.send:
        print("\nDRY-RUN: not posting. Re-run with --send to publish.")
        return 0

    results = {}
    if not args.skip_fb:
        print("\nPosting to Facebook...")
        results["facebook"] = post_to_facebook(msgs["long"], landing_url)
        print("  FB result: %s" % results["facebook"])
    else:
        print("\nSkipping Facebook (--skip-fb)")

    if not args.skip_x:
        print("\nPosting to X via Publer...")
        results["x_publer"] = post_to_x_via_publer(msgs["short"])
        print("  X result: %s" % results["x_publer"])
    else:
        print("\nSkipping X (--skip-x)")

    # Lock only if at least one succeeded.
    any_ok = any(r.get("ok") for r in results.values())
    if any_ok:
        mark_posted(today, {"results": results, "pick": pick.get("first_row")})
        print("\nDone — at least one network posted successfully.")
        return 0
    else:
        print("\nAll posts failed — not locking; will retry on next cron fire.")
        return 5


if __name__ == "__main__":
    sys.exit(main())
