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
MAILERLITE_BASE = "https://connect.mailerlite.com/api"

RESEND_API_URL = "https://api.resend.com/emails"


def _is_placeholder(val: str) -> bool:
    """Treat empty string or any value containing 'PLACEHOLDER' as unconfigured."""
    if not val:
        return True
    return 'PLACEHOLDER' in val


def resend_send_email(to: str, subject: str, body_text: str,
                      from_addr: str = None, reply_to: str = None,
                      html: str = None, headers: dict = None) -> bool:
    """Send a transactional email via Resend. Returns True on 2xx, False
    otherwise. Never raises.

    Pass `html` to send a multipart text+HTML email (e.g. to deliver the signed
    agreement snapshot inline); plain `body_text` stays the fallback.

    Skips silently (returns False) when RESEND_API_KEY is empty/placeholder -
    e.g. on dev before Resend is wired. Caller can still rely on the database
    row being written; the email is best-effort.
    """
    api_key = getattr(config, 'RESEND_API_KEY', '')
    if _is_placeholder(api_key):
        log.debug("resend_send_email skipped: RESEND_API_KEY is placeholder/empty")
        return False

    from_addr = from_addr or getattr(config, 'SUPPORT_EMAIL_FROM', '')
    if not from_addr:
        log.warning("resend_send_email: no from_addr; refusing to send")
        return False

    payload = {
        "from":    from_addr,
        "to":      [to] if isinstance(to, str) else list(to),
        "subject": subject,
        "text":    body_text,
    }
    if html:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = reply_to
    if headers:
        # custom MIME headers (e.g. List-Unsubscribe / List-Unsubscribe-Post for
        # one-click unsubscribe required by Gmail/Yahoo bulk-sender rules).
        payload["headers"] = headers

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    try:
        # 5s ceiling: caller is usually an HTTP handler (e.g. /api/contact);
        # blocking a Flask worker longer than that risks the 30s gunicorn
        # worker timeout cascading other requests. The DB row is the canonical
        # record - a missed email can be resent manually.
        resp = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=5)
    except requests.RequestException as e:
        log.warning("resend_send_email network error to=%s subject=%r: %s", to, subject, e)
        return False
    except Exception as e:
        log.warning("resend_send_email unexpected error to=%s subject=%r: %s", to, subject, e)
        return False

    if 200 <= resp.status_code < 300:
        log.info("resend_send_email ok to=%s subject=%r status=%s", to, subject, resp.status_code)
        return True

    log.warning("resend_send_email failed to=%s subject=%r status=%s body=%s",
                to, subject, resp.status_code, (resp.text or "")[:300])
    return False


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

    # status=active mirrors TW1: a SaaS signup is a direct/single opt-in add, NOT a
    # newsletter form signup - so it must NOT trigger MailerLite's double-opt-in
    # confirmation email (that's reserved for the SMN form). Omitting status lets the
    # account-level double-opt-in default kick in and email the user a "confirm" notice.
    body = {"email": email, "status": "active"}
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


def mailerlite_unsubscribe(email: str) -> bool:
    """Set a MailerLite subscriber to 'unsubscribed' (upsert by email). Best-effort,
    never raises; skips when MAILERLITE_API_KEY is empty/placeholder. Called from the
    /unsubscribe endpoint so an opt-out in our system also stops MailerLite sends."""
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    if _is_placeholder(api_key):
        log.debug("mailerlite_unsubscribe skipped: MAILERLITE_API_KEY placeholder/empty")
        return False
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json",
               "Content-Type": "application/json"}
    try:
        resp = requests.post(MAILERLITE_API_URL,
                             json={"email": email, "status": "unsubscribed"},
                             headers=headers, timeout=3)
    except requests.RequestException as e:
        log.warning("mailerlite_unsubscribe network error for %s: %s", email, e)
        return False
    except Exception as e:
        log.warning("mailerlite_unsubscribe unexpected error for %s: %s", email, e)
        return False
    if 200 <= resp.status_code < 300:
        log.info("mailerlite_unsubscribe ok: email=%s status=%s", email, resp.status_code)
        return True
    log.warning("mailerlite_unsubscribe failed: email=%s status=%s body=%s",
                email, resp.status_code, (resp.text or "")[:200])
    return False


def _level_group_id(tier: str, period: str = None):
    """Resolve the Mailerlite level-group id for a (tier, period). Returns the id
    string, or None if it can't be mapped (caller should skip + log)."""
    groups = getattr(config, 'MAILERLITE_LEVEL_GROUPS', {}) or {}
    tier = (tier or '').strip().lower()
    if tier in ('', 'explorer', 'canceled'):
        return groups.get('explorer') or None
    period = (period or '').strip().lower()
    if period not in ('monthly', 'yearly'):
        return None  # paid tier with no derivable period -> caller skips + logs
    return groups.get(f"{tier}_{period}") or None


def sync_mailerlite_level_group(email: str, tier: str, period: str = None,
                                new_user: bool = False, dry_run: bool = False) -> str:
    """Replicate TW1/UMP's level->group sync: ensure `email` sits in EXACTLY the
    Mailerlite level group matching (tier, period) and is removed from the other
    level groups. Source of truth = TW2 (caller passes the current tier/period).

    Returns a short status string describing what happened (or, with dry_run=True,
    what WOULD happen) - used by the reconcile script's preview. Never raises
    (best-effort, like mailerlite_subscribe); the live hooks ignore the return.

    Rules:
      - Only the 5 configured LEVEL groups are ever touched; marketing/SMN groups
        are never added or removed.
      - Respects opt-out: an unsubscribed/bounced subscriber is NEVER added to a
        group (adds can reactivate). We only REMOVE them from wrong level groups
        (DELETE can't reactivate). A user not in Mailerlite who is known to have
        unsubscribed is left alone.
      - new_user=True (signup hot path): single POST to create/add in the target
        group, skipping the read+reconcile round-trips to keep signup fast.
    """
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    if _is_placeholder(api_key):
        return "skip:no-api-key"

    target = _level_group_id(tier, period)
    if not target:
        log.warning("sync_mailerlite_level_group: no level group for tier=%s period=%s email=%s "
                    "(skipping - place manually)", tier, period, email)
        return "skip:no-mappable-group"

    all_level_ids = {v for v in (getattr(config, 'MAILERLITE_LEVEL_GROUPS', {}) or {}).values() if v}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }
    import urllib.parse as _ul

    try:
        if new_user:
            if dry_run:
                return f"would-create+add:{target}"
            # status=active = direct add (TW1 SaaS-signup behavior), NO double-opt-in email.
            resp = requests.post(MAILERLITE_API_URL,
                                 json={"email": email, "status": "active", "groups": [target]},
                                 headers=headers, timeout=3)
            ok = 200 <= resp.status_code < 300
            if not ok:
                log.warning("sync(new) failed email=%s status=%s body=%s",
                            email, resp.status_code, (resp.text or "")[:200])
            return "created" if ok else f"error:{resp.status_code}"

        # Existing user: read current state (one GET gives id, status, groups[])
        r = requests.get(f"{MAILERLITE_BASE}/subscribers/{_ul.quote(email)}",
                         headers=headers, timeout=6)
        if r.status_code == 404:
            if dry_run:
                return f"would-create+add:{target}"
            # status=active = direct add (TW1 SaaS-signup behavior), NO double-opt-in email.
            resp = requests.post(MAILERLITE_API_URL,
                                 json={"email": email, "status": "active", "groups": [target]},
                                 headers=headers, timeout=3)
            return "created" if 200 <= resp.status_code < 300 else f"error:{resp.status_code}"
        if not (200 <= r.status_code < 300):
            log.warning("sync GET failed email=%s status=%s", email, r.status_code)
            return f"error:get-{r.status_code}"

        data = (r.json() or {}).get("data") or {}
        sub_id = data.get("id")
        status = data.get("status")
        cur_level = {g.get("id") for g in (data.get("groups") or [])} & all_level_ids
        removes = cur_level - {target}

        if status != "active":
            # Unsubscribed/bounced/junk/unconfirmed: removals only, never add.
            if dry_run:
                return f"unsub({status}):would-remove{sorted(removes)}" if removes else f"unsub({status}):noop"
            for gid in removes:
                requests.delete(f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{gid}",
                                headers=headers, timeout=3)
            return f"unsub({status}):removed{len(removes)}"

        need_add = target not in cur_level
        if dry_run:
            if not need_add and not removes:
                return "noop"
            return f"would-add:{target if need_add else '-'} would-remove:{sorted(removes)}"

        if need_add:
            requests.post(f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{target}",
                          headers=headers, timeout=3)
        for gid in removes:
            requests.delete(f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{gid}",
                            headers=headers, timeout=3)
        if not need_add and not removes:
            return "noop"
        return f"add:{1 if need_add else 0} remove:{len(removes)}"
    except requests.RequestException as e:
        log.warning("sync_mailerlite_level_group network error email=%s: %s", email, e)
        return "error:network"
    except Exception as e:
        log.warning("sync_mailerlite_level_group unexpected error email=%s: %s", email, e)
        return "error:exception"


def sync_mailerlite_winback_group(email: str, churned: bool, dry_run: bool = False) -> str:
    """Add (churned=True) or remove (churned=False) `email` from the winback
    trust-letter group (config.MAILERLITE_WINBACK_GROUP_ID) - the trigger for
    the "TW Winback - Explorer (trust letter)" automation that sends ONE honest
    email a day after a paying web subscription ends.

    Same contract as sync_mailerlite_level_group: best-effort, never raises,
    returns a short status string. Rules:
      - An unsubscribed/bounced subscriber is NEVER added (adds can reactivate);
        removals are always safe.
      - Someone not in MailerLite at all is NOT created just to be churn-lettered
        (unlike the level sync, which creates - a churner who never joined the
        list should stay off it).
    """
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    gid = str(getattr(config, 'MAILERLITE_WINBACK_GROUP_ID', '') or '')
    if _is_placeholder(api_key) or not gid:
        return "skip:not-configured"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }
    import urllib.parse as _ul
    try:
        r = requests.get(f"{MAILERLITE_BASE}/subscribers/{_ul.quote(email)}",
                         headers=headers, timeout=6)
        if r.status_code == 404:
            return "skip:not-in-mailerlite"
        if not (200 <= r.status_code < 300):
            log.warning("winback GET failed email=%s status=%s", email, r.status_code)
            return f"error:get-{r.status_code}"
        data = (r.json() or {}).get("data") or {}
        sub_id = data.get("id")
        status = data.get("status")
        in_group = any(str(g.get("id")) == gid for g in (data.get("groups") or []))

        if churned:
            if status != "active":
                return f"skip:unsub({status})"
            if in_group:
                return "noop"
            if dry_run:
                return f"would-add:{gid}"
            resp = requests.post(f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{gid}",
                                 headers=headers, timeout=3)
            ok = 200 <= resp.status_code < 300
            if not ok:
                log.warning("winback add failed email=%s status=%s", email, resp.status_code)
            return "added" if ok else f"error:{resp.status_code}"

        if not in_group:
            return "noop"
        if dry_run:
            return f"would-remove:{gid}"
        requests.delete(f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{gid}",
                        headers=headers, timeout=3)
        return "removed"
    except requests.RequestException as e:
        log.warning("sync_mailerlite_winback_group network error email=%s: %s", email, e)
        return "error:network"
    except Exception as e:
        log.warning("sync_mailerlite_winback_group unexpected error email=%s: %s", email, e)
        return "error:exception"
