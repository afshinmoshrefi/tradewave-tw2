"""
TradeWave 2.0 - Web Tier - Email / Newsletter Utilities
=======================================================

Thin wrappers around third-party email/list-management APIs. Currently:
  - mailerlite_subscribe() - POST a new subscriber to Mailerlite

Design rules:
  - Fail fast and silently when API keys are placeholders/empty. Caller does
    not need to gate on config; we do.
  - NEVER raise. Caller code paths (e.g. lazy_create_user) must not be
    affected by an outage in a third-party newsletter service.
  - Log warnings on failure so /var/log/syslog (journalctl -u tradewave-web)
    captures the why.
"""
import logging
import sys

import requests

sys.path.insert(0, '/home/flask')
import config

log = logging.getLogger("tw2.web.email_utils")

MAILERLITE_API_URL = "https://connect.mailerlite.com/api/subscribers"


def _is_placeholder(val: str) -> bool:
    """Treat empty string or any value containing 'PLACEHOLDER' as unconfigured."""
    if not val:
        return True
    return 'PLACEHOLDER' in val


def mailerlite_subscribe(email: str, name: str = None) -> bool:
    """Add `email` to the configured Mailerlite group. Returns True on 2xx,
    False otherwise. Never raises.

    Skips silently (returns False) when MAILERLITE_API_KEY or
    MAILERLITE_GROUP_ID is empty/placeholder - this is the normal dev/staging
    path before Mailerlite is wired live.
    """
    api_key  = getattr(config, 'MAILERLITE_API_KEY', '')
    group_id = getattr(config, 'MAILERLITE_GROUP_ID', '')

    if _is_placeholder(api_key):
        log.debug("mailerlite_subscribe skipped: MAILERLITE_API_KEY is placeholder/empty")
        return False

    body = {"email": email}
    if name:
        body["fields"] = {"name": name}
    if not _is_placeholder(group_id):
        body["groups"] = [group_id]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }

    try:
        # F2.15 - lower from 5s to 2s. lazy_create_user() calls this on the
        # signup hot path; we'd rather lose a Mailerlite subscribe than have
        # the user-facing /auth/callback wait up to 5s on a Mailerlite blip.
        # The Mailerlite list-add is best-effort and safe to retry later via
        # cron / batch. (Long-term: move to a background queue.)
        resp = requests.post(MAILERLITE_API_URL, json=body, headers=headers, timeout=2)
    except requests.RequestException as e:
        log.warning("mailerlite_subscribe network error for %s: %s", email, e)
        return False
    except Exception as e:
        log.warning("mailerlite_subscribe unexpected error for %s: %s", email, e)
        return False

    if 200 <= resp.status_code < 300:
        log.info("mailerlite_subscribe ok: email=%s status=%s", email, resp.status_code)
        return True

    # Capture body for debugging - but cap length so we don't flood logs
    body_preview = (resp.text or "")[:300]
    log.warning(
        "mailerlite_subscribe failed: email=%s status=%s body=%s",
        email, resp.status_code, body_preview,
    )
    return False
