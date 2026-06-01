"""
TW2 web tier - /api/contact (Tier-1) support form helpers.

Three concerns kept out of app.py so the route is short:
  1. Cloudflare Turnstile server-side verification
  2. Customer-context enrichment (tier / Stripe / last_login snapshot for the
     notification email)
  3. The two email bodies - notification to support, confirmation to visitor

Design rules mirror email_utils.py: never raise; log warnings; fail-soft on
third-party outages (the DB ticket is the canonical record).
"""
from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

import requests

sys.path.insert(0, '/home/flask')
import config

log = logging.getLogger("tw2.web.contact_form")

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Visible labels for each topic storage-ID. Storage IDs are stable; labels are
# free to evolve - see SUPPORT_TICKET_TOPICS in web/models.py for the canonical
# storage values.
TOPIC_LABELS = {
    "bug":           "Bug report",
    "feature":       "Feature request",
    "billing":       "Billing question",
    "account":       "Account access",
    "data":          "Data accuracy",
    "institutional": "Institutional / API",
    "press":         "Press inquiry",
    "other":         "Other",
}


def verify_turnstile(token: str, remote_ip: str = None) -> bool:
    """Server-side Turnstile token verification. Returns True iff CF confirms
    the token is valid. Never raises.

    A missing secret (placeholder/empty) returns False - the /api/contact
    handler must treat that as a hard fail in staging/prod. On dev with
    Turnstile's test keys configured, real verification still runs against the
    CF endpoint and always passes (that's what the test keys do).
    """
    secret = getattr(config, 'TURNSTILE_SECRET_KEY', '')
    if not secret or 'PLACEHOLDER' in secret:
        log.warning("verify_turnstile: TURNSTILE_SECRET_KEY missing - rejecting")
        return False
    if not token:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        resp = requests.post(TURNSTILE_VERIFY_URL, data=payload, timeout=3)
    except requests.RequestException as e:
        log.warning("verify_turnstile network error: %s", e)
        return False

    if resp.status_code != 200:
        log.warning("verify_turnstile HTTP %s: %s", resp.status_code, (resp.text or "")[:200])
        return False
    try:
        data = resp.json() or {}
    except ValueError:
        log.warning("verify_turnstile non-JSON response")
        return False
    ok = bool(data.get("success"))
    if not ok:
        log.info("verify_turnstile rejected: errors=%s", data.get("error-codes"))
    return ok


def hash_ip(ip: str) -> Optional[str]:
    """SHA256(ip + per-env salt). Lets us de-dup / rate-limit by source
    without ever storing the raw IP. Returns None if no IP or no salt
    configured (in which case rate limiting is degraded but the form still
    works)."""
    if not ip:
        return None
    salt = getattr(config, 'SUPPORT_IP_HASH_SALT', '')
    if not salt:
        return None
    return hashlib.sha256(f"{ip}|{salt}".encode("utf-8")).hexdigest()


def enrich_user_context(user) -> dict:
    """Snapshot of the logged-in customer's state at submit time. Empty dict
    for anonymous submissions. The snapshot lives on the ticket row so the
    notification email - and any future audit - reflects what was true when
    the customer wrote in, not what's true at read time.
    """
    if user is None:
        return {}
    last_login = getattr(user, 'last_login_at', None)
    return {
        "user_id":                   str(user.id),
        "tier":                      user.tier,
        "stripe_subscription_status": user.stripe_subscription_status,
        "last_login_at":             last_login.isoformat() if last_login else None,
        "created_at":                user.created_at.isoformat() if user.created_at else None,
    }


def _fmt_context_block(ctx: dict) -> str:
    if not ctx:
        return "  (anonymous - no logged-in account at submit time)\n"
    lines = [
        f"  TW2 account:    yes (id: {ctx.get('user_id', '?')})",
        f"  Tier:           {ctx.get('tier', '?')}",
        f"  Stripe:         {ctx.get('stripe_subscription_status') or '(no subscription)'}",
    ]
    if ctx.get("last_login_at"):
        lines.append(f"  Last login:     {ctx['last_login_at']}")
    if ctx.get("created_at"):
        lines.append(f"  Account since:  {ctx['created_at']}")
    return "\n".join(lines) + "\n"


def format_notification_email(ticket) -> tuple[str, str]:
    """Render the (subject, body_text) we send to SUPPORT_EMAIL_TO. The
    customer's email goes into Reply-To at the send-site so hitting Reply in
    Afshin's inbox responds directly to the customer."""
    topic_label = TOPIC_LABELS.get(ticket.topic, ticket.topic)
    subject = f"[{ticket.public_id}] {topic_label} - {ticket.name}"

    admin_url = f"{config.tw2_public_url.rstrip('/')}/admin/supportticket/?flt_0_public_id={ticket.public_id}"

    body = (
        "-" * 56 + "\n"
        f"Ticket:    {ticket.public_id}\n"
        f"Topic:     {topic_label}\n"
        f"Submitted: {ticket.created_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        "\n"
        f"From:      {ticket.name} <{ticket.email}>\n"
        "\n"
        "Customer context:\n"
        + _fmt_context_block(ticket.enrichment or {}) +
        "-" * 56 + "\n"
        "MESSAGE\n"
        + "-" * 56 + "\n\n"
        + ticket.body.strip() + "\n\n"
        + "-" * 56 + "\n"
        f"Admin view: {admin_url}\n"
    )
    return subject, body


def format_confirmation_email(ticket) -> tuple[str, str]:
    """Render the (subject, body_text) we send to the visitor so they have
    proof their message landed + a reference number to quote later."""
    topic_label = TOPIC_LABELS.get(ticket.topic, ticket.topic)
    subject = f"We got your message - {ticket.public_id}"
    body = (
        f"Hi {ticket.name},\n\n"
        f"Thanks for reaching out. Your message landed and we'll get back to\n"
        f"you within one business day.\n\n"
        f"Reference:  {ticket.public_id}\n"
        f"Topic:      {topic_label}\n\n"
        "If your situation is urgent, reply to this email and add URGENT to\n"
        "the subject - it bumps the priority on our side.\n\n"
        "- The TradeWave team\n"
    )
    return subject, body
