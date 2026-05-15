#!/usr/bin/env python3
"""
SMN Daily / Weekly Email Sender (TW2 port from TW1 prod).

Builds a Mailerlite campaign from recent SMN articles and schedules it for
delivery. Detects mode from the day-of-week (per TW1 prod /etc/crontab):

    Mon-Fri at 07:00 — DAILY blast (articles published in the last ~24h)
    Sunday  at 09:00 — WEEKLY recap (articles published in the last 7 days)

Reads articles from /var/www/smn/posts.json (written by smn/publish_article.py).
Uses smn/email_tools.py primitives (create_campaign, schedule_campaign).

Idempotency: a date+mode lock file is written under /var/log/tradewave/
to prevent double-sends if cron fires the script more than once on the
same day.

TW1 lineage: /home/flask/blog/send_smn_emails.py, scheduled at:
    0  7 * * 1-5  daily
    0  9 * * 0    weekly recap

Usage:
    python send_smn_emails.py [--dry-run] [--mode daily|weekly] [--group-id ID]
"""

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/smn')
import config
import email_tools  # smn/email_tools.py

POSTS_JSON = "/var/www/smn/posts.json"
LOCK_DIR = "/var/log/tradewave"
DEFAULT_DAILY_WINDOW_HOURS = 28   # daily blast: last 28h (covers cron drift)
DEFAULT_WEEKLY_WINDOW_DAYS = 7

# Mailerlite send time — 1 minute in the future so "scheduled" mode delivers
# essentially immediately but Mailerlite accepts the call.
SEND_OFFSET_MINUTES = 1


# ---------------------------------------------------------------------------
# POST INDEX
# ---------------------------------------------------------------------------

def load_posts(path: str = POSTS_JSON) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("ERROR: %s not found — no articles to send" % path)
        return []
    except Exception as e:
        print("ERROR loading %s: %s" % (path, e))
        return []


def _parse_iso(dt: str) -> Optional[datetime.datetime]:
    if not dt:
        return None
    try:
        if dt.endswith("Z"):
            dt = dt[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(dt)
    except Exception:
        return None


def recent_posts(posts: List[Dict[str, Any]], window_start: datetime.datetime
                  ) -> List[Dict[str, Any]]:
    """Filter posts whose published_date >= window_start."""
    kept = []
    for p in posts:
        ts = _parse_iso(p.get("published_date", "")) or _parse_iso(p.get("updated_date", ""))
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        if ts >= window_start:
            kept.append(p)
    # Newest first
    kept.sort(key=lambda p: p.get("published_date", ""), reverse=True)
    return kept


# ---------------------------------------------------------------------------
# EMAIL BODY
# ---------------------------------------------------------------------------

# Inline-styled HTML so Mailerlite renders predictably across clients.
# TW1_SPEC: TW1 likely had a richer template (hero image, brand header,
# CTA buttons). Replace with TW1's template when source is available.

_EMAIL_CSS = """
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a1a; max-width: 640px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 22px; margin: 0 0 8px 0; }
  .lede { color: #555; margin: 0 0 20px 0; }
  .article { margin: 0 0 18px 0; padding-bottom: 14px; border-bottom: 1px solid #e5e5e5; }
  .article a.title { font-size: 17px; font-weight: 600; color: #0a4a8a; text-decoration: none; }
  .article a.title:hover { text-decoration: underline; }
  .meta { font-size: 13px; color: #888; margin: 4px 0 6px 0; }
  .dek { font-size: 14px; color: #333; line-height: 1.45; margin: 0; }
  .footer { font-size: 12px; color: #999; margin-top: 24px; text-align: center; }
"""


def build_html(posts: List[Dict[str, Any]], mode: str, today: datetime.date) -> str:
    if mode == "weekly":
        header = "Seasonal Market News — Weekly Recap"
        lede = "The week's analyst-grade seasonal-pattern picks."
    else:
        header = "Seasonal Market News — %s" % today.strftime("%A, %b %d")
        lede = "Today's newly-published seasonal-pattern articles."

    articles_html_parts = []
    for p in posts:
        title = p.get("title", "(untitled)")
        url = p.get("url", "")
        sym = p.get("symbol", "")
        dek = p.get("dek", "") or p.get("meta_description", "") or ""
        pub = _parse_iso(p.get("published_date", ""))
        pub_str = pub.strftime("%b %d") if pub else ""
        articles_html_parts.append(
            '<div class="article">'
            '<a class="title" href="%s">%s</a>'
            '<div class="meta">%s &middot; %s</div>'
            '<p class="dek">%s</p>'
            '</div>'
            % (url, _esc(title), _esc(sym), _esc(pub_str), _esc(dek))
        )
    body = "".join(articles_html_parts) or '<p>No new articles in this window.</p>'

    home = config.news_website_url or "https://smn-dev.trxstat.com"
    footer = (
        '<div class="footer">'
        'You are receiving this because you subscribed to Seasonal Market News. '
        '<a href="%s">Browse all articles</a>.'
        '</div>' % home
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head>'
        '<body><h1>%s</h1><p class="lede">%s</p>%s%s</body></html>'
        % (_EMAIL_CSS, _esc(header), _esc(lede), body, footer)
    )


def _esc(s: str) -> str:
    import html
    return html.escape(s or "", quote=True)


# ---------------------------------------------------------------------------
# LOCK FILE (idempotency)
# ---------------------------------------------------------------------------

def lock_path_for(mode: str, day: datetime.date) -> str:
    return os.path.join(LOCK_DIR, "send_smn_emails.%s.%s.lock" % (mode, day.isoformat()))


def already_sent_today(mode: str, day: datetime.date) -> bool:
    return os.path.exists(lock_path_for(mode, day))


def mark_sent(mode: str, day: datetime.date, info: Dict[str, Any]) -> None:
    p = lock_path_for(mode, day)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            json.dump({"timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                       "mode": mode, "day": day.isoformat(), **info}, f)
    except Exception as e:
        print("WARN: could not write lock file %s: %s" % (p, e))


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the email and print summary; do not call Mailerlite")
    parser.add_argument("--mode", choices=["daily", "weekly"],
                        help="Override day-of-week detection")
    parser.add_argument("--group-id",
                        help="Mailerlite group ID (else env SMN_EMAIL_GROUP_ID, "
                             "else config.MAILERLITE_GROUP_ID)")
    parser.add_argument("--force", action="store_true",
                        help="Send even if today's lock file exists")
    args = parser.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()

    # Auto-detect mode from day of week (TW1 prod schedule).
    if args.mode:
        mode = args.mode
    elif today.weekday() == 6:  # Sunday
        mode = "weekly"
    else:
        mode = "daily"

    print("=== send_smn_emails.py — TW2 port ===")
    print("Started at %s" % now.isoformat())
    print("Mode: %s   (today: %s, weekday: %d)" % (mode, today, today.weekday()))

    if not args.force and already_sent_today(mode, today):
        print("Already sent today (%s); use --force to re-send. Exiting cleanly."
              % lock_path_for(mode, today))
        return 0

    # Resolve Mailerlite group.
    group_id = (args.group_id
                or os.environ.get("SMN_EMAIL_GROUP_ID")
                or getattr(config, "MAILERLITE_GROUP_ID", "")
                or "")
    if not group_id:
        print("ERROR: no Mailerlite group id (set SMN_EMAIL_GROUP_ID in "
              "secrets.env, or pass --group-id, or set MAILERLITE_GROUP_ID).")
        return 2

    # Build the window + filter posts.
    if mode == "weekly":
        window_start = now - datetime.timedelta(days=DEFAULT_WEEKLY_WINDOW_DAYS)
    else:
        window_start = now - datetime.timedelta(hours=DEFAULT_DAILY_WINDOW_HOURS)

    posts = load_posts()
    print("Loaded %d posts total" % len(posts))
    recent = recent_posts(posts, window_start)
    print("In window since %s: %d article(s)" % (window_start.isoformat(), len(recent)))

    if not recent:
        print("No articles in window — skipping send (not a failure).")
        mark_sent(mode, today, {"skipped": True, "reason": "no articles"})
        return 0

    # Compose.
    html = build_html(recent, mode, today)
    if mode == "weekly":
        subject = "SMN Weekly Recap — %s" % today.strftime("%b %d, %Y")
        campaign_name = "smn_weekly_%s" % today.isoformat()
    else:
        subject = "SMN Daily — %s" % today.strftime("%a %b %d")
        campaign_name = "smn_daily_%s" % today.isoformat()

    print("Subject: %s" % subject)
    print("Campaign: %s" % campaign_name)
    print("HTML size: %d bytes" % len(html))

    if args.dry_run:
        print("\n=== DRY-RUN — first 800 bytes of HTML ===")
        print(html[:800])
        return 0

    # Submit to Mailerlite.
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
        return 3

    # Schedule send (1 min in the future).
    send_at = now + datetime.timedelta(minutes=SEND_OFFSET_MINUTES)
    try:
        resp = email_tools.schedule_campaign(
            campaign_id=campaign_id,
            send_date=send_at.strftime("%Y-%m-%d"),
            send_hour=int(send_at.strftime("%H")),
            send_minute=int(send_at.strftime("%M")),
        )
        print("Scheduled for %s" % send_at.isoformat())
    except Exception as e:
        print("ERROR scheduling Mailerlite campaign id=%s: %s" % (campaign_id, e))
        return 4

    mark_sent(mode, today, {
        "campaign_id": campaign_id,
        "subject": subject,
        "send_at": send_at.isoformat(),
        "article_count": len(recent),
        "group_id": group_id,
    })
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
