"""Server-side webinar registration backed by the verified Google schedule.

The browser supplies only the dated group name. All date, time, and meeting URL
fields are reloaded from the schedule so a visitor cannot register arbitrary
MailerLite groups or replace the private meeting link.
"""
from __future__ import annotations

import logging

import config
from webinar_schedule import fetch_webinar_data, get_upcoming_webinars
from email_utils import (
    MAILERLITE_API_URL,
    MAILERLITE_BASE,
    _get_mailerlite_subscriber,
    _group_ids,
    _is_placeholder,
    _locally_suppressed,
    _mailerlite_headers,
    _mailerlite_request,
    _mailerlite_write_allowed,
    _reconcile_managed_groups,
)


log = logging.getLogger("tw2.web.webinar_registration")


def _json_data(response):
    try:
        payload = response.json() or {}
    except (TypeError, ValueError, AttributeError):
        return None
    data = payload.get("data")
    return data


def _find_group_id(group_name: str, headers: dict) -> str | None:
    """Find an exact MailerLite group name without relying on fuzzy search."""
    url = f"{MAILERLITE_BASE}/groups?limit=100"
    for _page in range(10):
        response = _mailerlite_request("GET", url, headers=headers)
        if response is None or not (200 <= response.status_code < 300):
            return None
        try:
            payload = response.json() or {}
        except (TypeError, ValueError, AttributeError):
            return None
        for group in payload.get("data") or []:
            if str(group.get("name") or "").strip() == group_name and group.get("id"):
                return str(group["id"])
        next_url = (payload.get("links") or {}).get("next")
        if not next_url:
            break
        url = next_url
    return None


def _ensure_group(group_name: str, headers: dict) -> str | None:
    group_id = _find_group_id(group_name, headers)
    if group_id:
        return group_id

    response = _mailerlite_request(
        "POST", f"{MAILERLITE_BASE}/groups", headers=headers,
        json={"name": group_name}, timeout=3,
    )
    if response is not None and 200 <= response.status_code < 300:
        data = _json_data(response)
        if isinstance(data, dict) and data.get("id"):
            return str(data["id"])

    # A concurrent registration may have created the same group first.
    return _find_group_id(group_name, headers)


def _scheduled_session(group_name: str, *, data=None, now=None):
    schedule = fetch_webinar_data() if data is None else data
    for session in get_upcoming_webinars(schedule, now=now):
        if session["group_name"] == group_name:
            return session
    return None


def register_webinar_subscriber(
    email: str,
    first_name: str,
    group_name: str,
    *,
    data=None,
    now=None,
) -> str:
    """Register for one currently scheduled future session.

    Stable results: ``success``, ``invalid_session``, ``inactive``,
    ``suppressed``, ``disabled``, or ``error``.
    """
    session = _scheduled_session(group_name, data=data, now=now)
    if session is None or not session.get("webinar_url"):
        return "invalid_session"

    api_key = getattr(config, "MAILERLITE_API_KEY", "")
    general_group_id = str(
        getattr(config, "MAILERLITE_WEBINAR_GROUP_ID", "") or ""
    )
    if (
        _is_placeholder(api_key)
        or _is_placeholder(general_group_id)
        or not _mailerlite_write_allowed()
    ):
        return "disabled"

    suppression = _locally_suppressed(email)
    if suppression is None:
        return "error"
    if suppression:
        return "suppressed"

    headers = _mailerlite_headers(api_key)
    existing_response, existing = _get_mailerlite_subscriber(email, headers)
    if existing_response is None:
        return "error"
    if existing_response.status_code != 404:
        if not (200 <= existing_response.status_code < 300) or existing is None:
            return "error"
        if existing.get("status") != "active":
            return "inactive"

    dated_group_id = _ensure_group(group_name, headers)
    if not dated_group_id:
        log.warning("webinar registration could not ensure group=%s", group_name)
        return "error"

    desired_groups = {general_group_id, dated_group_id}
    reconciliation = _reconcile_managed_groups(
        email,
        desired_groups,
        desired_groups,
        create_if_missing=True,
        name=first_name,
        label="webinar-groups",
    )
    if reconciliation.startswith("unsub("):
        return "inactive"
    if reconciliation == "skip:local-optout":
        return "suppressed"
    if not (
        reconciliation in ("created", "noop")
        or reconciliation.startswith("reconciled:")
    ):
        log.warning(
            "webinar registration group reconciliation failed group=%s result=%s",
            group_name, reconciliation,
        )
        return "error"

    # Omit status deliberately: an upsert must never reactivate an unsubscribed
    # or bounced address. The exact meeting URL stays server-side throughout.
    fields = {
        "name": first_name,
        "webinar_date": session["formatted_date"],
        "webinar_time": session["formatted_time"] + " ET",
        "webinar_url": session["webinar_url"],
    }
    updated = _mailerlite_request(
        "POST", MAILERLITE_API_URL, headers=headers,
        json={"email": email, "fields": fields}, timeout=3,
    )
    if updated is None or not (200 <= updated.status_code < 300):
        return "error"

    verified_response, verified = _get_mailerlite_subscriber(email, headers)
    if (
        verified_response is None
        or not (200 <= verified_response.status_code < 300)
        or verified is None
    ):
        return "error"
    if verified.get("status") != "active":
        return "inactive"
    if not desired_groups.issubset(_group_ids(verified)):
        return "error"

    # Close the practical opt-out race between the first check and the upsert.
    suppression = _locally_suppressed(email)
    if suppression is None:
        return "error"
    if suppression:
        _reconcile_managed_groups(
            email, desired_groups, set(), create_if_missing=False,
            label="webinar-groups-race-cleanup",
        )
        return "suppressed"
    return "success"
