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
import time
import urllib.parse
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
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


def _mailerlite_write_allowed() -> bool:
    """Return True only when this environment explicitly permits ML writes."""
    return bool(getattr(config, 'MAILERLITE_OUTBOUND_ENABLED', False))


def _retry_delay(response, attempt: int) -> float:
    """Small bounded retry delay; honor an integer Retry-After when present."""
    raw = (
        (getattr(response, 'headers', {}) or {}).get('Retry-After')
        if response is not None else None
    )
    try:
        return min(max(float(raw), 0.0), 2.0)
    except (TypeError, ValueError):
        return min(0.25 * (2 ** attempt), 2.0)


def _mailerlite_request(method: str, url: str, *, headers: dict,
                        json: dict = None, timeout: int = 6,
                        max_attempts: int = 3):
    """Issue a bounded MailerLite request and retry only transient failures.

    Returns the final response, or None after network failures. Ordinary 4xx
    responses are returned immediately so callers can classify them correctly.
    """
    for attempt in range(max_attempts):
        try:
            response = requests.request(
                method, url, json=json, headers=headers, timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt + 1 >= max_attempts:
                log.warning("Mailerlite %s network failure url=%s: %s", method, url, exc)
                return None
            time.sleep(_retry_delay(None, attempt))
            continue
        except Exception as exc:
            log.warning("Mailerlite %s unexpected failure url=%s: %s", method, url, exc)
            return None

        retryable = response.status_code in (408, 425, 429) or response.status_code >= 500
        if not retryable or attempt + 1 >= max_attempts:
            return response
        time.sleep(_retry_delay(response, attempt))
    return None


def _mailerlite_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _subscriber_data(response):
    """Return the MailerLite subscriber object, or None for malformed JSON."""
    try:
        data = (response.json() or {}).get("data") or {}
    except (TypeError, ValueError, AttributeError):
        return None
    return data if data.get("id") else None


def _group_ids(subscriber: dict) -> set:
    return {
        str(group.get("id"))
        for group in (subscriber.get("groups") or [])
        if group and group.get("id") is not None
    }


def _locally_suppressed(email: str) -> bool | None:
    """Fail closed against the durable TradeWave marketing opt-out table.

    The import stays lazy so this utility module remains usable by scripts that
    do not otherwise need the ORM. A private, unscoped session is essential:
    callers such as the Stripe webhook may already own ``models.Session`` in
    this thread, and closing that scoped session would detach their objects.
    ``None`` means the check itself failed, which callers treat as retryable.
    """
    session = None
    try:
        from sqlalchemy.orm import sessionmaker
        from models import EmailOptout, engine
        session = sessionmaker(bind=engine, expire_on_commit=False)()
        return (
            session.get(EmailOptout, (email or '').strip().lower())
            is not None
        )
    except Exception as exc:
        log.warning(
            "Mailerlite local suppression check failed; refusing add email=%s: %s",
            email, exc,
        )
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


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


def _get_mailerlite_subscriber(email: str, headers: dict):
    encoded = urllib.parse.quote(email, safe='')
    response = _mailerlite_request(
        "GET", f"{MAILERLITE_BASE}/subscribers/{encoded}", headers=headers,
    )
    return response, _subscriber_data(response) if response is not None and 200 <= response.status_code < 300 else None


def _reconcile_managed_groups(email: str, managed_ids: set, desired_ids: set,
                              *, create_if_missing: bool, name: str = None,
                              dry_run: bool = False, label: str = "groups") -> str:
    """Reconcile one mutually-exclusive family and verify the final membership."""
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    if _is_placeholder(api_key):
        return "skip:no-api-key"
    if not dry_run and not _mailerlite_write_allowed():
        return "skip:writes-disabled"

    managed_ids = {str(group_id) for group_id in managed_ids if group_id}
    desired_ids = {str(group_id) for group_id in desired_ids if group_id}
    if not managed_ids:
        return "skip:not-configured"
    if not desired_ids.issubset(managed_ids):
        return "error:desired-group-not-managed"
    if desired_ids:
        suppression = _locally_suppressed(email)
        if suppression is None:
            return "error:local-optout-check"
        if suppression:
            return "skip:local-optout"

    headers = _mailerlite_headers(api_key)
    response, subscriber = _get_mailerlite_subscriber(email, headers)
    if response is None:
        return "error:network"
    if response.status_code == 404:
        if not desired_ids or not create_if_missing:
            return "noop:not-in-mailerlite"
        if dry_run:
            return f"would-create+add:{sorted(desired_ids)}"
        body = {"email": email, "status": "active", "groups": sorted(desired_ids)}
        if name:
            body["fields"] = {"name": name}
        created = _mailerlite_request(
            "POST", MAILERLITE_API_URL, headers=headers, json=body, timeout=3,
        )
        if created is None:
            return "error:network"
        if not (200 <= created.status_code < 300):
            log.warning("%s create failed email=%s status=%s", label, email, created.status_code)
            return f"error:create-{created.status_code}"
        verify, verify_data = _get_mailerlite_subscriber(email, headers)
        if verify is None:
            return "error:verify-network"
        if not (200 <= verify.status_code < 300) or verify_data is None:
            return f"error:verify-{verify.status_code}"
        if (_group_ids(verify_data) & managed_ids) != desired_ids:
            return "error:verify-membership"
        suppression = _locally_suppressed(email)
        if suppression is None:
            return "error:local-optout-check"
        if suppression:
            verify_sub_id = str(verify_data["id"])
            for group_id in sorted(_group_ids(verify_data) & managed_ids):
                deleted = _mailerlite_request(
                    "DELETE",
                    f"{MAILERLITE_BASE}/subscribers/{verify_sub_id}/groups/{group_id}",
                    headers=headers, timeout=3,
                )
                if deleted is None or not (200 <= deleted.status_code < 300):
                    return "error:create-race-cleanup"
            stopped = _mailerlite_request(
                "POST", MAILERLITE_API_URL, headers=headers,
                json={"email": email, "status": "unsubscribed"}, timeout=3,
            )
            if stopped is None or not (200 <= stopped.status_code < 300):
                return "error:create-race-unsubscribe"
            final_verify, final_data = _get_mailerlite_subscriber(
                email, headers,
            )
            if final_verify is None:
                return "error:create-race-verify-network"
            if not (200 <= final_verify.status_code < 300) or final_data is None:
                return f"error:create-race-verify-{final_verify.status_code}"
            if _group_ids(final_data) & managed_ids:
                return "error:create-race-verify-membership"
            if final_data.get("status") == "active":
                return "error:create-race-verify-active"
            return "unsub(local-optout):reconciled"
        return "created"
    if not (200 <= response.status_code < 300):
        log.warning("%s GET failed email=%s status=%s", label, email, response.status_code)
        return f"error:get-{response.status_code}"
    if subscriber is None:
        return "error:malformed-subscriber"

    status = subscriber.get("status")
    current = _group_ids(subscriber) & managed_ids
    # Never add an inactive subscriber. Removals remain safe and prevent a
    # stale automation trigger from surviving a bounce/unsubscribe.
    effective_desired = desired_ids if status == "active" else set()
    removes = current - effective_desired
    adds = effective_desired - current
    if dry_run:
        if not adds and not removes:
            return f"unsub({status}):noop" if status != "active" else "noop"
        return f"would-add:{sorted(adds)} would-remove:{sorted(removes)}"
    if not adds and not removes:
        return f"unsub({status}):noop" if status != "active" else "noop"

    sub_id = str(subscriber["id"])
    # Remove first so lifecycle automations configured to exit when the
    # trigger no longer matches cannot overlap with the next journey.
    for group_id in sorted(removes):
        deleted = _mailerlite_request(
            "DELETE",
            f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{group_id}",
            headers=headers, timeout=3,
        )
        if deleted is None:
            return "error:delete-network"
        if not (200 <= deleted.status_code < 300):
            log.warning("%s delete failed email=%s group=%s status=%s",
                        label, email, group_id, deleted.status_code)
            return f"error:delete-{deleted.status_code}"
    for group_id in sorted(adds):
        added = _mailerlite_request(
            "POST",
            f"{MAILERLITE_BASE}/subscribers/{sub_id}/groups/{group_id}",
            headers=headers, timeout=3,
        )
        if added is None:
            return "error:add-network"
        if not (200 <= added.status_code < 300):
            log.warning("%s add failed email=%s group=%s status=%s",
                        label, email, group_id, added.status_code)
            return f"error:add-{added.status_code}"

    verify, verify_data = _get_mailerlite_subscriber(email, headers)
    if verify is None:
        return "error:verify-network"
    if not (200 <= verify.status_code < 300) or verify_data is None:
        return f"error:verify-{verify.status_code}"

    # Re-evaluate both MailerLite status and the local suppression row after
    # the mutations. This closes the practical unsubscribe race: if an opt-out
    # committed while a group add was in flight, remove the just-added trigger
    # and force the MailerLite subscriber inactive before returning.
    suppression = _locally_suppressed(email) if desired_ids else False
    if suppression is None:
        return "error:local-optout-check"
    suppressed_now = bool(suppression)
    verify_status = verify_data.get("status")
    verify_desired = (
        desired_ids
        if verify_status == "active" and not suppressed_now else set()
    )
    verify_current = _group_ids(verify_data) & managed_ids

    postcheck_changed = False
    if not verify_desired and verify_current:
        verify_sub_id = str(verify_data["id"])
        for group_id in sorted(verify_current):
            deleted = _mailerlite_request(
                "DELETE",
                f"{MAILERLITE_BASE}/subscribers/{verify_sub_id}/groups/{group_id}",
                headers=headers, timeout=3,
            )
            if deleted is None:
                return "error:postcheck-delete-network"
            if not (200 <= deleted.status_code < 300):
                return f"error:postcheck-delete-{deleted.status_code}"
        verify_current = set()
        postcheck_changed = True

    if suppressed_now and verify_status == "active":
        stopped = _mailerlite_request(
            "POST", MAILERLITE_API_URL, headers=headers,
            json={"email": email, "status": "unsubscribed"}, timeout=3,
        )
        if stopped is None:
            return "error:postcheck-unsubscribe-network"
        if not (200 <= stopped.status_code < 300):
            return f"error:postcheck-unsubscribe-{stopped.status_code}"
        verify_status = "unsubscribed"
        postcheck_changed = True

    if postcheck_changed:
        final_verify, final_data = _get_mailerlite_subscriber(email, headers)
        if final_verify is None:
            return "error:postcheck-verify-network"
        if not (200 <= final_verify.status_code < 300) or final_data is None:
            return f"error:postcheck-verify-{final_verify.status_code}"
        verify_current = _group_ids(final_data) & managed_ids
        verify_status = final_data.get("status")

    if verify_current != verify_desired:
        return "error:verify-membership"
    if suppressed_now and verify_status == "active":
        return "error:verify-local-optout-active"
    if suppressed_now:
        return "unsub(local-optout):reconciled"
    prefix = f"unsub({status}):" if status != "active" else ""
    return f"{prefix}reconciled:add={len(adds)} remove={len(removes)}"


def mailerlite_subscribe(email: str, name: str = None) -> bool:
    """Ensure an active subscriber is in the configured lead group.

    Use the same verified reconciliation path as lifecycle and access groups so
    an existing active subscriber is actually added to the requested group and
    an opt-out that races the write is removed again immediately.
    """
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    group_id = getattr(config, 'MAILERLITE_GROUP_ID', '')
    if (
        _is_placeholder(api_key)
        or _is_placeholder(group_id)
        or not _mailerlite_write_allowed()
    ):
        log.debug("mailerlite_subscribe skipped: not configured/enabled")
        return False
    result = _reconcile_managed_groups(
        email,
        {str(group_id)},
        {str(group_id)},
        create_if_missing=True,
        name=name,
        label="lead-group",
    )
    ok = (
        result == "created"
        or result == "noop"
        or result.startswith("reconciled:")
    )
    if not ok:
        log.info("mailerlite_subscribe skipped/failed email=%s result=%s",
                 email, result)
    return ok


def mailerlite_unsubscribe(email: str) -> bool:
    """Set and verify unsubscribed status; never writes off-production."""
    api_key = getattr(config, 'MAILERLITE_API_KEY', '')
    if _is_placeholder(api_key) or not _mailerlite_write_allowed():
        log.debug("mailerlite_unsubscribe skipped: not configured/enabled")
        return False
    response = _mailerlite_request(
        "POST", MAILERLITE_API_URL, headers=_mailerlite_headers(api_key),
        json={"email": email, "status": "unsubscribed"}, timeout=3,
    )
    if response is None or not (200 <= response.status_code < 300):
        log.warning("mailerlite_unsubscribe failed email=%s status=%s",
                    email, getattr(response, 'status_code', 'network'))
        return False
    verify, subscriber = _get_mailerlite_subscriber(
        email, _mailerlite_headers(api_key),
    )
    ok = bool(
        verify is not None
        and 200 <= verify.status_code < 300
        and subscriber is not None
        and subscriber.get("status") != "active"
    )
    if not ok:
        log.warning("mailerlite_unsubscribe readback failed email=%s status=%s",
                    email, getattr(verify, 'status_code', 'network'))
    return ok


def _level_group_id(tier: str, period: str = None):
    """Resolve the MailerLite level group for a current access tier."""
    groups = getattr(config, 'MAILERLITE_LEVEL_GROUPS', {}) or {}
    tier = (tier or '').strip().lower()
    if tier in ('', 'explorer', 'canceled'):
        return groups.get('explorer') or None
    period = (period or '').strip().lower()
    if period not in ('monthly', 'yearly'):
        return None
    return groups.get(f"{tier}_{period}") or None


def sync_mailerlite_level_group(email: str, tier: str, period: str = None,
                                new_user: bool = False, dry_run: bool = False) -> str:
    """Reconcile exactly one access-level group and verify every mutation.

    ``new_user`` remains for call-site compatibility; the safe implementation
    always reads subscriber status first so an old opt-out cannot be reactivated.
    """
    target = _level_group_id(tier, period)
    if not target:
        log.warning("No MailerLite level group tier=%s period=%s email=%s",
                    tier, period, email)
        return "skip:no-mappable-group"
    managed = {
        str(value) for value in
        (getattr(config, 'MAILERLITE_LEVEL_GROUPS', {}) or {}).values() if value
    }
    return _reconcile_managed_groups(
        email, managed, {str(target)}, create_if_missing=True,
        dry_run=dry_run, label="level-group",
    )


def clear_mailerlite_level_groups(email: str, dry_run: bool = False) -> str:
    """Remove every managed access-level group without creating a subscriber."""
    managed = {
        str(value) for value in
        (getattr(config, 'MAILERLITE_LEVEL_GROUPS', {}) or {}).values() if value
    }
    return _reconcile_managed_groups(
        email, managed, set(), create_if_missing=False,
        dry_run=dry_run, label="level-group",
    )


def sync_mailerlite_lifecycle_groups(email: str, desired_state: str = None,
                                     *, name: str = None,
                                     create_if_missing: bool = False,
                                     dry_run: bool = False) -> str:
    """Reconcile the mutually-exclusive lifecycle automation trigger groups.

    ``desired_state`` is one of trial_started, trial_ended_explorer,
    winback_explorer, or None (paid/no lifecycle journey). Level groups are not
    touched here.
    """
    groups = getattr(config, 'MAILERLITE_LIFECYCLE_GROUPS', {}) or {}
    allowed = {'trial_started', 'trial_ended_explorer', 'winback_explorer'}
    if desired_state not in allowed | {None}:
        return "error:invalid-lifecycle-state"
    managed = {str(value) for value in groups.values() if value}
    target = str(groups.get(desired_state) or '') if desired_state else ''
    if desired_state and not target:
        return "skip:not-configured"
    return _reconcile_managed_groups(
        email, managed, {target} if target else set(),
        create_if_missing=create_if_missing, name=name,
        dry_run=dry_run, label="lifecycle-group",
    )


def sync_mailerlite_winback_group(email: str, churned: bool,
                                  dry_run: bool = False) -> str:
    """Backward-compatible winback wrapper over lifecycle reconciliation."""
    return sync_mailerlite_lifecycle_groups(
        email,
        'winback_explorer' if churned else None,
        create_if_missing=False,
        dry_run=dry_run,
    )
