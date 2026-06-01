#!/usr/bin/env python3
"""
Daily AI Pick Email Sender (TW2 port from TW1 prod).

Reads /var/www/tradewave/daily-ai-pick.html (generated earlier the same
morning by site/generate_daily_ai_pick.py), extracts the title + top picks
table, composes a Mailerlite campaign, and schedules it for delivery.

TW1 lineage: /home/flask/blog/send_daily_ai_pick.py, scheduled TWICE in
TW1 prod /etc/crontab — both at `* * 1-5` weekdays, at 07:30 and 07:41,
writing to different log files. We use a daily lock to make double-fire
a no-op (so re-running is safe).

    30 7 * * 1-5  → /home/flask/blog/logs/daily_ai_pick.log
    41 7 * * 1-5  → /home/flask/blog/logs/daily_ai_pick_email_cron.log

Usage:
    python send_daily_ai_pick.py [--dry-run] [--group-id ID] [--force]
"""

import argparse
import datetime
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/smn')
import config
import email_tools_web as email_tools

INPUT_HTML = "/var/www/tradewave/daily-ai-pick.html"
LOCK_DIR = "/var/log/tradewave"
SEND_OFFSET_MINUTES = 1
MAX_AGE_HOURS = 24  # daily-ai-pick.html older than this is stale — refuse to send


# ---------------------------------------------------------------------------
# PARSE daily-ai-pick.html
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)
_HERO_RE = re.compile(r'<div class="pick-hero"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
_TABLE_RE = re.compile(r'(<table class="pick-table".*?</table>)', re.IGNORECASE | re.DOTALL)
_TAG_STRIP = re.compile(r'<[^>]+>')


def parse_html(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    title_m = _TITLE_RE.search(src)
    h1_m = _H1_RE.search(src)
    hero_m = _HERO_RE.search(src)
    table_m = _TABLE_RE.search(src)

    return {
        "html_src": src,
        "title": title_m.group(1).strip() if title_m else "Daily AI Pick",
        "hero_text": (_TAG_STRIP.sub(" ", hero_m.group(1)).strip()
                      if hero_m else (h1_m.group(1).strip() if h1_m else "")),
        "table_html": table_m.group(1) if table_m else "",
    }


# ---------------------------------------------------------------------------
# COMPOSE email body
# ---------------------------------------------------------------------------

_EMAIL_CSS = """
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         color: #1a1a1a; max-width: 720px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 22px; margin: 0 0 8px 0; }
  .lede { color: #555; margin: 0 0 18px 0; font-size: 14px; }
  table.pick-table { width: 100%; border-collapse: collapse; margin: 0 0 18px 0;
                     font-size: 13px; border: 1px solid #e5e5e5; }
  table.pick-table th, table.pick-table td { padding: 8px 10px; text-align: left;
                                             border-bottom: 1px solid #ececec; }
  table.pick-table th { background: #f5f5f7; font-weight: 700;
                        text-transform: uppercase; font-size: 11px; letter-spacing: 0.6px; }
  .cta { display: inline-block; padding: 10px 18px; background: #0a4a8a; color: #fff;
         border-radius: 6px; text-decoration: none; margin: 14px 0; }
  .cta:hover { background: #073a6f; }
  .footer { font-size: 12px; color: #999; margin-top: 18px; text-align: center; }
  .r-dir.long  { color: #0a8a3c; font-weight: 600; }
  .r-dir.short { color: #b13a1f; font-weight: 600; }
  .r-sym a { color: #0a4a8a; text-decoration: none; font-weight: 700; }
"""


def build_email_html(parsed: Dict[str, Any], landing_url: str) -> str:
    title = parsed["title"]
    hero = parsed["hero_text"]
    table = parsed["table_html"] or "<p>Picks unavailable — see the link below.</p>"

    # Rewrite relative URLs in the embedded table to absolute (so links work in mail clients).
    domain = (config.domain_root.rstrip("/") + "/") if config.domain_root else "https://tw2.trxstat.com/"
    table = re.sub(r'href="/', 'href="%s' % domain, table)

    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
        '<h1>%s</h1>'
        '<p class="lede">%s</p>'
        '%s'
        '<a class="cta" href="%s">View on TradeWave →</a>'
        '<div class="footer">Sent by TradeWave AI. You can manage your subscription in your account settings.</div>'
        '</body></html>'
        % (_EMAIL_CSS, _esc(title), _esc(hero), table, landing_url)
    )


def _esc(s: str) -> str:
    import html
    return html.escape(s or "", quote=True)


# ---------------------------------------------------------------------------
# LOCK FILE
# ---------------------------------------------------------------------------

def lock_path(day: datetime.date) -> str:
    return os.path.join(LOCK_DIR, "send_daily_ai_pick.%s.lock" % day.isoformat())


def already_sent(day: datetime.date) -> bool:
    return os.path.exists(lock_path(day))


def mark_sent(day: datetime.date, info: Dict[str, Any]) -> None:
    p = lock_path(day)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                       "day": day.isoformat(), **info}, f)
    except Exception as e:
        print("WARN: lock write failed: %s" % e)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--group-id",
                        help="Mailerlite group ID (else env DAILY_AI_PICK_GROUP_ID, "
                             "else config.MAILERLITE_GROUP_ID)")
    parser.add_argument("--force", action="store_true",
                        help="Send even if today's lock file exists")
    parser.add_argument("--input", default=INPUT_HTML)
    args = parser.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    print("=== send_daily_ai_pick.py — TW2 port ===")
    print("Started at %s" % now.isoformat())

    if not args.force and already_sent(today):
        print("Already sent today (%s); use --force to re-send. Exiting cleanly."
              % lock_path(today))
        return 0

    if not os.path.exists(args.input):
        print("ERROR: %s does not exist — was generate_daily_ai_pick.py run first?"
              % args.input)
        return 2

    age_h = (now.timestamp() - os.path.getmtime(args.input)) / 3600.0
    if age_h > MAX_AGE_HOURS:
        print("ERROR: %s is %.1fh old (> %dh) — refusing to send stale picks"
              % (args.input, age_h, MAX_AGE_HOURS))
        return 3

    group_id = (args.group_id
                or os.environ.get("DAILY_AI_PICK_GROUP_ID")
                or getattr(config, "MAILERLITE_GROUP_ID", "")
                or "")
    if not group_id:
        print("ERROR: no Mailerlite group id (set DAILY_AI_PICK_GROUP_ID in "
              "secrets.env, or pass --group-id, or set MAILERLITE_GROUP_ID).")
        return 4

    parsed = parse_html(args.input)
    domain = (config.domain_root.rstrip("/") + "/") if config.domain_root else "https://tw2.trxstat.com/"
    landing_url = domain + "daily-ai-pick.html"
    html = build_email_html(parsed, landing_url)

    subject = "TradeWave Daily AI Pick — %s" % today.strftime("%a %b %d")
    campaign_name = "daily_ai_pick_%s" % today.isoformat()

    print("Subject: %s" % subject)
    print("Campaign: %s" % campaign_name)
    print("HTML size: %d bytes" % len(html))
    print("Source age: %.1fh" % age_h)

    if args.dry_run:
        print("\n=== DRY-RUN — first 800 bytes of email HTML ===")
        print(html[:800])
        return 0

    try:
        campaign_id, created_at = email_tools.create_campaign(
            campaign_name=campaign_name,
            subject=subject,
            from_name=config.smn_from_name,
            from_email=config.smn_from_email,
            group_id=str(group_id),
            content=html,
        )
        print("Created campaign id=%s at %s" % (campaign_id, created_at))
    except Exception as e:
        print("ERROR creating Mailerlite campaign: %s" % e)
        return 5

    send_at = now + datetime.timedelta(minutes=SEND_OFFSET_MINUTES)
    try:
        email_tools.schedule_campaign(
            campaign_id=campaign_id,
            send_date=send_at.strftime("%Y-%m-%d"),
            send_hour=int(send_at.strftime("%H")),
            send_minute=int(send_at.strftime("%M")),
        )
        print("Scheduled for %s" % send_at.isoformat())
    except Exception as e:
        print("ERROR scheduling campaign id=%s: %s" % (campaign_id, e))
        return 6

    mark_sent(today, {
        "campaign_id": campaign_id,
        "subject": subject,
        "send_at": send_at.isoformat(),
        "group_id": group_id,
        "source_mtime": datetime.datetime.utcfromtimestamp(os.path.getmtime(args.input)).isoformat() + "Z",
    })
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
