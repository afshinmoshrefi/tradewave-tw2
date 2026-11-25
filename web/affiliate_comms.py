"""Partner lifecycle + communication (TW-TASK-0039 package B).

One service module, no Flask:

  1. Applications - validate / store a public application, approve it (creates
     the affiliates row on the default v2 terms and emails the signing link)
     or reject it.
  2. Notifications - ONE row per (partner, event) in affiliate_notifications.
     That row is the portal inbox entry, the email send log and the
     idempotency claim, so an event is delivered once per partner no matter
     how often the job runs.
  3. Email preferences - optional emails a partner can turn off (Settings, or
     the signed link in every optional email). Required notices ignore them.
  4. Admin messaging - one partner or a group, with a recipient preview.
  5. The daily job (run_daily) that finds lifecycle events and delivers them.

Views: web/affiliate_comms_views.py (public pages), web/affiliate_comms_admin.py
(Flask-Admin), web/affiliate_portal/messages.py (portal inbox + preferences).

Cron (web box, daily 14:10 UTC; ops/install_affiliate_comms_cron.sh):
  python web/affiliate_comms.py [--dry-run]

House style: no em-dashes in any copy (use " - ").
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import re
import sys
import uuid
from decimal import Decimal
from html import escape as _esc
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WEB_ROOT = Path(__file__).resolve().parent
for _candidate in (str(_REPO_ROOT), str(_WEB_ROOT)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

import config  # noqa: E402
import affiliate_service as afs  # noqa: E402
import affiliate_agreement as agr  # noqa: E402

log = logging.getLogger("tw2.affiliate_comms")

UTC = dt.timezone.utc
HELP_EMAIL = "help@tradewave.ai"


class CommsError(afs.AffiliateError):
    """A problem to show the admin / applicant. `errors` lists every one.
    `fields` (application form only) is [(field name, message)] in the order
    the fields appear on the form, so the page can mark each field."""

    def __init__(self, errors, fields=None):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        self.fields = list(fields or [])
        super().__init__("; ".join(self.errors))


# ---------------------------------------------------------------------------
# 1) Event catalog + preferences
# ---------------------------------------------------------------------------
# ONE name per kind of email. The same words are used for the Settings
# toggle, the tag on a Messages entry, the admin send log and the "always
# sent" list, so a partner (and the owner) never has to match two names.
KIND_LABEL = {
    "welcome": "Welcome",
    "first_click": "First click",
    "new_customer": "New paying customer",
    "statement_ready": "Monthly statement",
    "payout_sent": "Payout sent",
    "activity_warning": "Activity reminder",
    "activity_final": "Final activity warning",
    "renewals_lapsed": "Renewal commissions stopped",
    "renewals_resumed": "Renewal commissions resumed",
    "campaign_started": "New TradeWave sale",
    "discount_changed": "Discount change",
    "payout_details_changed": "Payout details changed",
    "announcement": "News from the TradeWave team",
    "program_notice": "Program notice",
    "help_answer": "Answer from the team",
}

# Preference ids (STORAGE IDs in affiliate_email_prefs.disabled - never rename).
# "welcome" used to be a toggle; it is sent once, at signing, before a partner
# can reach Settings, so it is now a required notice. A stored "welcome"
# opt-out is simply ignored (disabled_prefs() drops unknown ids).
PREFS = (
    ("first_click", KIND_LABEL["first_click"], "Sent once, when your link gets its first visit."),
    ("new_customer", KIND_LABEL["new_customer"], "Sent each time a customer you referred makes a first payment. Never says who."),
    ("statement_ready", KIND_LABEL["statement_ready"], "Sent when a month's commission statement is on your Payouts page."),
    ("activity_warning", KIND_LABEL["activity_warning"], "Sent 60 and 30 days before your renewal commissions would stop."),
    ("renewals_resumed", KIND_LABEL["renewals_resumed"], "Sent when your renewal commissions start again."),
    ("campaign_started", KIND_LABEL["campaign_started"], "Sent when a company-wide sale starts that your link already applies."),
    ("announcement", KIND_LABEL["announcement"], "Program news and tips written by the TradeWave team."),
)
PREF_IDS = tuple(p[0] for p in PREFS)
PREF_LABEL = {p[0]: p[1] for p in PREFS}

# Notices every partner gets (money, account changes, loss of commission).
REQUIRED_NOTICES = (
    (KIND_LABEL["welcome"], "Sent once, when you sign your agreement, with your links and first steps."),
    (KIND_LABEL["payout_sent"], "A record of every payment we send you."),
    (KIND_LABEL["discount_changed"], "So you know right away if your customer discount changes."),
    (KIND_LABEL["payout_details_changed"], "Every time the payout method or payout email on your "
                                           "account is set or changed."),
    (KIND_LABEL["activity_final"], "7 days before your renewal commissions would stop."),
    (KIND_LABEL["renewals_lapsed"], "When the activity window ends."),
    (KIND_LABEL["help_answer"], "When the TradeWave team answers a question you asked in Help."),
    ("Tax form result", "Whether the tax form you uploaded was accepted, and what to fix if not."),
    ("Signing reminder", "Until you sign your agreement: 3 and 10 days after you are approved."),
    (KIND_LABEL["program_notice"], "Rare notices about the program or your agreement."),
)

# event_type (STORAGE ID in affiliate_notifications.event_type) -> preference
# id, or None for a required notice.
EVENT_PREF = {
    "welcome": None,
    "first_click": "first_click",
    "new_customer": "new_customer",
    "statement_ready": "statement_ready",
    "payout_sent": None,
    "activity_warning_60": "activity_warning",
    "activity_warning_30": "activity_warning",
    "activity_warning_7": None,
    "renewals_lapsed": None,
    "renewals_resumed": "renewals_resumed",
    "campaign_started": "campaign_started",
    "discount_changed": None,
    "payout_details_changed": None,
    "message": "announcement",
    "program_notice": None,
    "help_answer": None,
    "tax_form_accepted": None,
    "tax_form_rejected": None,
    "signing_reminder": None,
}
EVENT_LABEL = {
    "welcome": KIND_LABEL["welcome"], "first_click": KIND_LABEL["first_click"],
    "new_customer": KIND_LABEL["new_customer"],
    "statement_ready": KIND_LABEL["statement_ready"], "payout_sent": KIND_LABEL["payout_sent"],
    "activity_warning_60": KIND_LABEL["activity_warning"],
    "activity_warning_30": KIND_LABEL["activity_warning"],
    "activity_warning_7": KIND_LABEL["activity_final"],
    "renewals_lapsed": KIND_LABEL["renewals_lapsed"],
    "renewals_resumed": KIND_LABEL["renewals_resumed"],
    "campaign_started": KIND_LABEL["campaign_started"],
    "discount_changed": KIND_LABEL["discount_changed"],
    "payout_details_changed": KIND_LABEL["payout_details_changed"],
    "message": KIND_LABEL["announcement"], "program_notice": KIND_LABEL["program_notice"],
    "help_answer": KIND_LABEL["help_answer"],
    "tax_form_accepted": "Tax form result", "tax_form_rejected": "Tax form result",
    "signing_reminder": "Signing reminder",
}
ACTIVITY_WARNING_DAYS = (60, 30, 7)
SIGNING_REMINDER_DAYS = (3, 10)        # days after a partner was created, still unsigned
OWNER_WAIT_HOURS = 48                  # the owner digest lists what waited longer than this
DIGEST_ACTION = "affiliate_owner_digest_sent"
MAX_SEND_ATTEMPTS = 3
PENDING_RETRY_AFTER = dt.timedelta(minutes=30)


def max_event_age() -> dt.timedelta:
    """Events older than this are never emailed (so switching the job on does
    not mail a backlog of old news). Env: TW2_AFFILIATE_COMMS_MAX_EVENT_AGE_DAYS."""
    try:
        days = int(getattr(config, "AFFILIATE_COMMS_MAX_EVENT_AGE_DAYS", 0) or 0)
    except (TypeError, ValueError):
        days = 0
    if days <= 0:
        import os
        try:
            days = int(os.environ.get("TW2_AFFILIATE_COMMS_MAX_EVENT_AGE_DAYS", "7"))
        except ValueError:
            days = 7
    return dt.timedelta(days=max(1, days))


def _utc(v):
    return afs._utc(v)


def _now(now=None):
    return _utc(now) or dt.datetime.now(UTC)


def first_name(aff) -> str:
    return ((getattr(aff, "name", "") or "").strip().split(" ")[0]) or "there"


def money(amount, currency="usd") -> str:
    q = Decimal(str(amount or 0)).quantize(Decimal("0.01"))
    text = "{:,.2f}".format(abs(q))
    sign = "-" if q < 0 else ""
    if (currency or "usd").lower() == "usd":
        return "%s$%s" % (sign, text)
    return "%s%s %s" % (sign, text, (currency or "").upper())


def _pct(v) -> str:
    return agr._fmt_pct(v)


def _day(d) -> str:
    """'5 Mar 2027' (no leading zero) - the same date style as the portal."""
    return "%d %s" % (d.day, d.strftime("%b %Y"))


def _day_time(d) -> str:
    """'5 Mar 2027, 14:05'."""
    return "%s, %s" % (_day(d), d.strftime("%H:%M"))


def support_inbox() -> str:
    """Where a partner's reply to any partner email lands."""
    return (getattr(config, "AFFILIATE_SUPPORT_EMAIL", "") or HELP_EMAIL).strip()


# "Hi Anne," / "Hello there!" - a greeting word, at most three more words, then punctuation
_GREETING_RE = re.compile(r"^\s*(?:hi|hello|hey|dear)\b(?:[ \t]+[^\s,!.:]+){0,3}[ \t]*[,!.:]\s+",
                          re.IGNORECASE)


def preview_text(body, limit=140) -> str:
    """One line for the Messages list: the body without its greeting
    ("Hi Anne,") so the list shows what each message is about."""
    text = _GREETING_RE.sub("", (body or "").strip(), count=1)
    return " ".join(text.split())[:limit]


def attribution_days() -> int:
    """Days a click stays credited to the partner. affiliate_service owns the
    number when it exposes attribution_window_days(); otherwise config, with
    the agreement's 60 days as the default."""
    fn = getattr(afs, "attribution_window_days", None)
    try:
        if callable(fn):
            return int(fn())
        return int(getattr(config, "AFFILIATE_ATTRIBUTION_DAYS", None)
                   or getattr(config, "AFFILIATE_COOKIE_DAYS", None) or 60)
    except (TypeError, ValueError):
        return 60


def offer_example(terms=None, discount=None) -> dict:
    """The discount trade-off as one line: '20% off for them = 30% for you'."""
    t = terms or afs.DEFAULT_TERMS
    d = default_discount(t) if discount is None else afs.clamp_discount(discount, t)
    rate = afs.preview_offer(10000, d, t)["commission_rate_pct"]
    return {"discount": _pct(d), "rate": _pct(rate),
            "line": "%s%% off for them = %s%% for you" % (_pct(d), _pct(rate))}


def dashboard_url(path="") -> str:
    return agr.dashboard_link() + path


# --- signed preference tokens (the link in every optional email) -----------
_PREF_SALT = "affiliate-email-prefs"


def _pref_serializer():
    from itsdangerous import URLSafeSerializer
    secret = getattr(config, "WORKOS_COOKIE_PASSWORD", "") or ""
    if not secret:
        raise CommsError("signing secret (WORKOS_COOKIE_PASSWORD) is not configured")
    return URLSafeSerializer(secret, salt=_PREF_SALT)


def make_pref_token(affiliate_id) -> str:
    return _pref_serializer().dumps({"aid": str(affiliate_id)})


def verify_pref_token(token):
    """Affiliate id (str) or None. No expiry: an unsubscribe link in an old
    email must keep working."""
    try:
        data = _pref_serializer().loads(token or "")
    except Exception:   # noqa: BLE001  (bad signature, no secret, garbage)
        return None
    if not isinstance(data, dict) or not data.get("aid"):
        return None
    return str(data["aid"])


def prefs_url(aff, pref=None):
    """Public, login-free preferences page for this partner. With `pref`, the
    page opens ready to turn that one email off. Falls back to the logged-in
    Settings page if no signing secret is configured."""
    try:
        token = make_pref_token(aff.id)
    except CommsError:
        return dashboard_url("/settings#email")
    url = "%s/partners/email-preferences/%s" % (agr._base(), token)
    return url + ("?off=%s" % pref if pref else "")


def one_click_url(aff, pref):
    """List-Unsubscribe-Post target (RFC 8058). None without a signing secret."""
    try:
        token = make_pref_token(aff.id)
    except CommsError:
        return None
    return "%s/partners/unsubscribe/%s/%s" % (agr._base(), token, pref)


# --- preferences ------------------------------------------------------------
def disabled_prefs(session, affiliate_id) -> set:
    from models import AffiliateEmailPref
    row = session.get(AffiliateEmailPref, affiliate_id)
    return set(x for x in ((row.disabled if row is not None else None) or []) if x in PREF_IDS)


def set_disabled_prefs(session, affiliate_id, disabled) -> set:
    """Replace the partner's opt-outs. Unknown ids are dropped. Commits."""
    from models import AffiliateEmailPref
    clean = sorted(x for x in set(disabled or []) if x in PREF_IDS)
    row = session.get(AffiliateEmailPref, affiliate_id)
    if row is None:
        row = AffiliateEmailPref(affiliate_id=affiliate_id, disabled=clean)
        session.add(row)
    else:
        row.disabled = clean
    row.updated_at = _now()
    session.commit()
    return set(clean)


def turn_off_pref(session, affiliate_id, pref) -> bool:
    if pref not in PREF_IDS:
        return False
    set_disabled_prefs(session, affiliate_id, disabled_prefs(session, affiliate_id) | {pref})
    return True


def pref_rows(session, affiliate_id) -> list:
    """[{id, label, help, on}] for the Settings card / public page."""
    off = disabled_prefs(session, affiliate_id)
    return [{"id": pid, "label": label, "help": help_, "on": pid not in off}
            for pid, label, help_ in PREFS]


# ---------------------------------------------------------------------------
# 2) Email rendering + delivery (idempotent)
# ---------------------------------------------------------------------------
_URL_RE = re.compile(r"(https?://[^\s<]+[^\s<.,;:!?)\]])")


def _html_paragraphs(text) -> str:
    out = []
    for block in re.split(r"\n\s*\n", (text or "").strip()):
        safe = _esc(block)
        safe = _URL_RE.sub(lambda m: '<a href="%s">%s</a>' % (m.group(1), m.group(1)), safe)
        out.append('<p style="margin:0 0 14px;">%s</p>' % safe.replace("\n", "<br>"))
    return "".join(out)


def render_email(aff, subject, body, *, link=None, pref=None):
    """(text, html, headers). `pref` None = required notice: no unsubscribe
    link. Every optional email carries the preferences link, a stop link for
    its own kind, and the one-click List-Unsubscribe headers."""
    manage = prefs_url(aff)
    text = body.strip()
    if link and link[1]:
        text += "\n\n%s:\n%s" % (link[0], link[1])
    text += "\n\nThe TradeWave team\n\n--\n"
    headers = None
    if pref:
        stop = prefs_url(aff, pref)
        text += ("You get this email because you are a TradeWave partner (code %s).\n"
                 "Choose which partner emails you get: %s\n"
                 "Stop this kind of email: %s\n" % (aff.code, manage, stop))
        foot = ('You get this email because you are a TradeWave partner (code %s). '
                '<a href="%s">Choose which partner emails you get</a> or '
                '<a href="%s">stop this kind of email</a>.'
                % (_esc(aff.code), _esc(manage), _esc(stop)))
        one_click = one_click_url(aff, pref)
        if one_click:
            headers = {"List-Unsubscribe": "<%s>" % one_click,
                       "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    else:
        text += ("This is a required program notice. It is sent to every TradeWave partner "
                 "(code %s).\nChoose your other partner emails: %s\n" % (aff.code, manage))
        foot = ('This is a required program notice. It is sent to every TradeWave partner '
                '(code %s). <a href="%s">Choose your other partner emails</a>.'
                % (_esc(aff.code), _esc(manage)))
    button = ""
    if link and link[1]:
        button = ('<p style="margin:6px 0 20px;"><a href="%s" style="display:inline-block;'
                  'background:#4f46e5;color:#ffffff;text-decoration:none;font-weight:600;'
                  'padding:10px 18px;border-radius:8px;">%s</a></p>' % (_esc(link[1]), _esc(link[0])))
    html = ('<div style="font:15px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;'
            'color:#1f2a44;max-width:560px;">%s%s<p style="margin:0 0 14px;">The TradeWave team</p>'
            '<p style="margin:22px 0 0;padding-top:12px;border-top:1px solid #e3e6ee;'
            'font-size:12px;color:#6b7280;">%s</p></div>'
            % (_html_paragraphs(body), button, foot))
    return text, html, headers


def email_configured() -> bool:
    import email_utils
    return not email_utils._is_placeholder(getattr(config, "RESEND_API_KEY", ""))


def _send(to, subject, text, html=None, headers=None, reply_to=None) -> bool:
    """Every partner email is answerable: Reply-To is the support inbox (the
    From address is a no-reply sender), so "reply to this email" works."""
    import email_utils
    try:
        return bool(email_utils.resend_send_email(
            to=to, subject=subject, body_text=text, html=html, headers=headers,
            reply_to=reply_to or support_inbox()))
    except Exception as e:   # noqa: BLE001
        log.warning("partner email send raised to=%s: %s", to, e)
        return False


def make_event(event_type, key, subject, body, *, occurred_at=None, link=None, message_id=None):
    if event_type not in EVENT_PREF:
        raise ValueError("unknown event type %r" % event_type)
    return SimpleNamespace(type=event_type, key=key, subject=subject, body=body,
                           occurred_at=occurred_at, link=link, message_id=message_id)


def _claim(session, aff, ev, now):
    """The notification row to deliver, or None when this event is already
    done (sent / skipped), being sent right now, or out of retries."""
    from models import AffiliateNotification
    from sqlalchemy.exc import IntegrityError
    row = (session.query(AffiliateNotification)
           .filter(AffiliateNotification.affiliate_id == aff.id,
                   AffiliateNotification.event_key == ev.key).first())
    if row is not None:
        if row.email_status in ("sent", "skipped"):
            return None
        if row.email_status == "failed" and int(row.attempts or 0) >= MAX_SEND_ATTEMPTS:
            return None
        if row.email_status == "pending":
            created = _utc(row.created_at)
            if created is not None and now - created < PENDING_RETRY_AFTER:
                return None            # another run is sending it
        return row
    row = AffiliateNotification(
        affiliate_id=aff.id, message_id=ev.message_id, event_type=ev.type, event_key=ev.key,
        subject=ev.subject, body=ev.body,
        link_label=ev.link[0] if ev.link else None, link_url=ev.link[1] if ev.link else None,
        email_status="pending", attempts=0, to_email=(aff.email or None), created_at=now)
    try:
        with session.begin_nested():
            session.add(row)
    except IntegrityError:
        return None                    # raced: the other run owns it
    session.commit()                   # the claim is durable BEFORE the send
    return row


def deliver(session, aff, ev, now=None, disabled=None, email=True):
    """Deliver one event to one partner, once. Returns the notification row
    when this call created or retried it, else None. Commits.
    email=False puts it in the partner's Messages only."""
    now = _now(now)
    row = _claim(session, aff, ev, now)
    if row is None:
        return None
    pref = EVENT_PREF[ev.type]
    if disabled is None:
        disabled = disabled_prefs(session, aff.id)
    if not email:
        row.email_status, row.email_reason = "skipped", "inbox_only"
    elif pref and pref in disabled:
        row.email_status, row.email_reason = "skipped", "preference"
    elif not (aff.email or "").strip():
        row.email_status, row.email_reason = "skipped", "no_email"
    elif not email_configured():
        # Not permanent: the row stays 'failed' WITHOUT using up an attempt, so
        # the next run sends it once the Resend key is configured.
        row.email_status, row.email_reason = "failed", "email_not_configured"
    else:
        text, html, headers = render_email(aff, ev.subject, ev.body, link=ev.link, pref=pref)
        row.attempts = int(row.attempts or 0) + 1
        row.to_email = aff.email
        if _send(aff.email, ev.subject, text, html, headers):
            row.email_status, row.email_reason, row.emailed_at = "sent", None, now
        else:
            row.email_status, row.email_reason = "failed", "send_failed"
    session.commit()
    return row


def deliver_help_reply(session, aff, esc, closed=False, now=None):
    """Help <-> Messages bridge: the team's answer to a Help question (or the
    note sent when a question is closed) also lands in Messages, linking back
    to the Help chat where the partner can reply. An answer is emailed as a
    required notice; a closing note is Messages-only."""
    question = " ".join((esc.question or "").split())
    short = question if len(question) <= 70 else question[:67].rstrip() + "..."
    if closed:
        subject = "We closed your question: %s" % short
        body = ("Hi %s,\n\nYou asked:\n%s\n\nFrom the TradeWave team:\n%s"
                % (first_name(aff), esc.question, esc.answer))
    else:
        subject = "Answer from the TradeWave team: %s" % short
        body = ("Hi %s,\n\nYou asked:\n%s\n\nOur answer:\n%s\n\n"
                "Need more? Open Help in your dashboard and ask again. You can also reply "
                "to this email."
                % (first_name(aff), esc.question, esc.answer))
    ev = make_event("help_answer", "help:%s" % esc.id, subject, body, occurred_at=_now(now),
                    link=("Open Help in your dashboard", dashboard_url("#help")))
    return deliver(session, aff, ev, now, email=not closed)


# --- inbox -------------------------------------------------------------------
def unread_count(session, affiliate_id) -> int:
    from models import AffiliateNotification
    return int(session.query(AffiliateNotification)
               .filter(AffiliateNotification.affiliate_id == affiliate_id,
                       AffiliateNotification.read_at.is_(None)).count())


def inbox(session, affiliate_id, limit=100) -> list:
    from models import AffiliateNotification
    return (session.query(AffiliateNotification)
            .filter(AffiliateNotification.affiliate_id == affiliate_id)
            .order_by(AffiliateNotification.created_at.desc(), AffiliateNotification.id.desc())
            .limit(limit).all())


def mark_read(session, affiliate_id, notification_id=None, now=None) -> int:
    """Mark one (or every) inbox row of THIS partner read. Commits."""
    from models import AffiliateNotification
    q = (session.query(AffiliateNotification)
         .filter(AffiliateNotification.affiliate_id == affiliate_id,
                 AffiliateNotification.read_at.is_(None)))
    if notification_id is not None:
        q = q.filter(AffiliateNotification.id == notification_id)
    n = q.update({"read_at": _now(now)}, synchronize_session=False)
    session.commit()
    return int(n or 0)


# ---------------------------------------------------------------------------
# 3) Admin messaging
# ---------------------------------------------------------------------------
# Audience ids are STORAGE IDs (affiliate_messages.audience).
AUDIENCES = (
    ("one", "One partner"),
    ("all", "All partners"),
    ("active", "Active partners"),
    ("paused", "Paused partners (signed)"),
    ("unsigned", "Partners who have not signed yet"),
    ("terms", "Partners on one terms version"),
    ("inactive", "No new paying customer in the last N days"),
    ("has_customers", "Partners with paying customers"),
    ("no_customers", "Partners with no paying customer yet"),
)
AUDIENCE_LABEL = dict(AUDIENCES)
PLACEHOLDERS = ("{first_name}", "{name}", "{code}", "{link}", "{dashboard}")


def _last_paid_by_affiliate(session) -> dict:
    """{affiliate_id: latest first payment of a NEW referred customer}."""
    from models import AffiliateReferral
    from sqlalchemy import func
    rows = (session.query(AffiliateReferral.affiliate_id, func.max(AffiliateReferral.first_paid_at))
            .filter(AffiliateReferral.first_paid_at.isnot(None),
                    AffiliateReferral.source != "return")
            .group_by(AffiliateReferral.affiliate_id).all())
    return {aid: _utc(last) for aid, last in rows}


def resolve_audience(session, audience, param=None, now=None) -> list:
    """The partners a message goes to. Groups never include terminated
    partners; 'one' reaches exactly the named partner. Raises CommsError on a
    bad audience / parameter."""
    from models import Affiliate
    now = _now(now)
    if audience not in AUDIENCE_LABEL:
        raise CommsError("Choose who the message goes to.")
    if audience == "one":
        try:
            aid = uuid.UUID(str(param))
        except (ValueError, TypeError, AttributeError):
            raise CommsError("Choose the partner.")
        aff = session.get(Affiliate, aid)
        if aff is None:
            raise CommsError("That partner no longer exists.")
        return [aff]
    live = (session.query(Affiliate).filter(Affiliate.status != "terminated")
            .order_by(Affiliate.code).all())
    if audience == "all":
        return live
    if audience == "active":
        return [a for a in live if a.status == "active"]
    if audience == "paused":
        return [a for a in live if a.status == "paused" and a.agreement_signed_at is not None]
    if audience == "unsigned":
        return [a for a in live if a.agreement_signed_at is None]
    if audience == "terms":
        try:
            tid = int(param)
        except (ValueError, TypeError):
            raise CommsError("Choose the terms version.")
        default = afs.get_terms(session)
        default_id = getattr(default, "id", None)
        return [a for a in live if (a.terms_id or default_id) == tid]
    last = _last_paid_by_affiliate(session)
    if audience == "has_customers":
        return [a for a in live if a.id in last]
    if audience == "no_customers":
        return [a for a in live if a.id not in last]
    # inactive
    try:
        days = int(param)
    except (ValueError, TypeError):
        raise CommsError("Enter the number of days.")
    if days < 1 or days > 3650:
        raise CommsError("Days must be between 1 and 3650.")
    floor = now - dt.timedelta(days=days)
    return [a for a in live if a.agreement_signed_at is not None
            and (last.get(a.id) is None or last[a.id] < floor)]


def audience_text(session, audience, param=None) -> str:
    label = AUDIENCE_LABEL.get(audience, audience)
    if audience == "one":
        from models import Affiliate
        try:
            aff = session.get(Affiliate, uuid.UUID(str(param)))
        except (ValueError, TypeError, AttributeError):
            aff = None
        return "One partner: %s" % (("%s (%s)" % (aff.code, aff.name)) if aff else "unknown")
    if audience == "terms":
        try:
            terms = afs.get_terms(session, int(param))
        except (ValueError, TypeError):
            terms = None
        return "Partners on terms %s" % (getattr(terms, "version", None) or param)
    if audience == "inactive":
        return "No new paying customer in the last %s days" % param
    return label


def personalize(text, aff) -> str:
    out = text or ""
    for token, value in (("{first_name}", first_name(aff)), ("{name}", aff.name or ""),
                         ("{code}", aff.code or ""), ("{link}", agr.join_link(aff)),
                         ("{dashboard}", dashboard_url())):
        out = out.replace(token, value)
    return out


def validate_message(subject, body) -> tuple:
    subject = " ".join((subject or "").split())
    body = (body or "").replace("\r\n", "\n").strip()
    errors = []
    if not 3 <= len(subject) <= 150:
        errors.append("Subject must be 3 to 150 characters.")
    if not 10 <= len(body) <= 10000:
        errors.append("Message must be 10 to 10,000 characters.")
    if "—" in subject or "—" in body:
        errors.append("Please replace the long dash with ' - ' (house style).")
    if errors:
        raise CommsError(errors)
    return subject, body


def deliver_message(session, msg, recipient_ids=None, now=None) -> dict:
    """Deliver a stored admin message to its recipients (inbox + email), once
    per partner (event key msg:<id>), so it is safe to run again after a
    crash. Returns {sent, skipped, failed, recipients}."""
    from models import Affiliate
    now = _now(now)
    ids = []
    for raw in recipient_ids or []:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            continue
    recipients = [a for a in (session.get(Affiliate, i) for i in ids) if a is not None]
    stats = {"sent": 0, "skipped": 0, "failed": 0, "recipients": len(recipients)}
    etype = "program_notice" if msg.required else "message"
    for aff in recipients:
        ev = make_event(etype, "msg:%s" % msg.id, personalize(msg.subject, aff),
                        personalize(msg.body, aff), occurred_at=now, message_id=msg.id)
        try:
            row = deliver(session, aff, ev, now)
        except Exception as e:   # noqa: BLE001  (one partner must not stop the rest)
            session.rollback()
            log.warning("message %s to %s failed: %s", msg.id, aff.code, e)
            stats["failed"] += 1
            continue
        if row is not None:
            stats[row.email_status if row.email_status in stats else "failed"] += 1
    return stats


def send_message(session, *, subject, body, audience, param=None, required=False,
                 sent_by=None, now=None, background=False):
    """Store the message, then deliver it to every recipient (inbox + email).
    Returns (message, {sent, skipped, failed, recipients}).

    background=True (the admin screen, for a group): the recipients are fixed
    now, a 'send_message' job is queued (web/affiliate_jobs.py) and the call
    returns at once with stats {"queued": True, "job": id, "recipients": n}.
    A single recipient is always sent inline."""
    from models import AffiliateMessage
    now = _now(now)
    subject, body = validate_message(subject, body)
    recipients = resolve_audience(session, audience, param, now)
    if not recipients:
        raise CommsError("Nobody matches that group, so nothing was sent.")
    msg = AffiliateMessage(subject=subject, body=body, audience=audience,
                           audience_param=(str(param) if param not in (None, "") else None),
                           required=bool(required), sent_by=sent_by,
                           recipient_count=len(recipients), created_at=now)
    session.add(msg)
    session.commit()
    ids = [str(a.id) for a in recipients]
    if background and len(recipients) > 1:
        import affiliate_jobs as jobs
        job = jobs.enqueue(session, "send_message", {"message_id": msg.id, "recipient_ids": ids},
                           created_by=sent_by, now=now)
        return msg, {"queued": True, "job": job.id, "sent": 0, "skipped": 0, "failed": 0,
                     "recipients": len(recipients)}
    return msg, deliver_message(session, msg, ids, now)


def message_log(session, limit=100) -> list:
    """Newest admin messages with per-status recipient counts."""
    from models import AffiliateMessage, AffiliateNotification
    from sqlalchemy import func
    msgs = (session.query(AffiliateMessage).order_by(AffiliateMessage.id.desc())
            .limit(limit).all())
    ids = [m.id for m in msgs]
    counts, reads = {}, {}
    if ids:
        for mid, status, n in (session.query(AffiliateNotification.message_id,
                                             AffiliateNotification.email_status, func.count())
                               .filter(AffiliateNotification.message_id.in_(ids))
                               .group_by(AffiliateNotification.message_id,
                                         AffiliateNotification.email_status).all()):
            counts.setdefault(mid, {})[status] = int(n)
        for mid, n in (session.query(AffiliateNotification.message_id, func.count())
                       .filter(AffiliateNotification.message_id.in_(ids),
                               AffiliateNotification.read_at.isnot(None))
                       .group_by(AffiliateNotification.message_id).all()):
            reads[mid] = int(n)
    return [{"message": m, "audience": audience_text(session, m.audience, m.audience_param),
             "counts": counts.get(m.id, {}), "read": reads.get(m.id, 0)} for m in msgs]


def notification_log(session, limit=200, message_id=None) -> list:
    """Newest per-partner sends (automatic emails and messages), with the code."""
    from models import Affiliate, AffiliateNotification
    q = (session.query(AffiliateNotification, Affiliate.code)
         .join(Affiliate, Affiliate.id == AffiliateNotification.affiliate_id))
    if message_id is not None:
        q = q.filter(AffiliateNotification.message_id == message_id)
    return (q.order_by(AffiliateNotification.created_at.desc(), AffiliateNotification.id.desc())
            .limit(limit).all())


# ---------------------------------------------------------------------------
# 4) Applications
# ---------------------------------------------------------------------------
# Storage ids (affiliate_applications.audience_size).
AUDIENCE_SIZES = (
    ("lt1k", "Under 1,000"),
    ("1k_10k", "1,000 to 10,000"),
    ("10k_50k", "10,000 to 50,000"),
    ("50k_250k", "50,000 to 250,000"),
    ("gt250k", "More than 250,000"),
)
AUDIENCE_SIZE_LABEL = dict(AUDIENCE_SIZES)
HONEYPOT_FIELD = "company_url"          # hidden; humans leave it empty
# the application form's fields, in the order they appear on the page
APPLICATION_FIELDS = ("name", "email", "country", "audience_size", "website", "channels",
                      "promo_plan", "agree")
APPLY_LIMIT_PER_IP_DAY = 3
_EMAIL_RE = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[A-Za-z]{2,}$")
_SITE_RE = re.compile(r"^(https?://)?[A-Za-z0-9][A-Za-z0-9.\-]*\.[A-Za-z]{2,}(/\S*)?$")
_MARKUP_RE = re.compile(r"[<>]")
# A "name" that carries a link is how a form gets abused to make us email
# someone a URL: never greet with it.
_LINK_RE = re.compile(r"(?i)(https?:|www\.|://|\b[a-z0-9-]+\.(?:com|net|org|io|co|ru|cn|info|biz|xyz|top|ly|me|app|dev|site|online|link|click|shop)\b)")


def has_link(text) -> bool:
    return bool(_LINK_RE.search(text or ""))


def greeting_name(name) -> str:
    """First name for an email greeting, or 'there' when the name is empty or
    looks like it carries a link."""
    name = (name or "").strip()
    if not name or has_link(name):
        return "there"
    return name.split(" ")[0] or "there"


def hash_ip(ip):
    """Salted hash for the per-network rate limit (the raw IP is not stored)."""
    return afs.hash_ip(ip)


def clean_application(form) -> dict:
    """Validated field dict, or CommsError listing every problem."""
    def get(key, cap):
        return " ".join(str(form.get(key) or "").split())[:cap + 1]

    def long(key):
        return str(form.get(key) or "").replace("\r\n", "\n").strip()

    found = {}

    def bad(field, message):
        found.setdefault(field, message)        # one message per field: the first

    name = get("name", 120)
    if not 2 <= len(name) <= 120:
        bad("name", "Please enter your name (2 to 120 characters).")
    elif has_link(name):
        bad("name", "Please enter your name only (no web address). Use the website field for links.")
    email = get("email", 320).lower()
    if not email:
        bad("email", "Please enter your email address.")
    elif not _EMAIL_RE.match(email) or len(email) > 320:
        bad("email", "That email address does not look right. Example: you@example.com")
    website = get("website", 300)
    if website and (len(website) > 300 or not _SITE_RE.match(website)):
        bad("website", "Website should look like example.com or https://example.com.")
    channels = long("channels")
    if len(channels) > 1000:
        bad("channels", "Channels: 1,000 characters at most.")
    if not website and not channels:
        bad("channels", "Tell us where you reach your audience: a website or your channels.")
    size = get("audience_size", 20)
    if size not in AUDIENCE_SIZE_LABEL:
        bad("audience_size", "Please choose your audience size.")
    plan = long("promo_plan")
    if not 20 <= len(plan) <= 2000:
        bad("promo_plan", "Tell us how you will promote TradeWave (20 to 2,000 characters).")
    country = get("country", 80)
    if not 2 <= len(country) <= 80:
        bad("country", "Please enter your country.")
    if str(form.get("agree") or "") != "yes":
        bad("agree", "Please tick the box to agree to the program policies.")
    for field, label, value in (("name", "Name", name), ("channels", "Channels", channels),
                                ("promo_plan", "How you will promote", plan),
                                ("country", "Country", country)):
        if _MARKUP_RE.search(value):
            bad(field, "%s must be plain text (no < or >)." % label)
    if found:
        ordered = [(f, found[f]) for f in APPLICATION_FIELDS if f in found]
        raise CommsError([m for _f, m in ordered], fields=ordered)
    return {"name": name, "email": email, "website": website or None,
            "channels": channels or None, "audience_size": size, "promo_plan": plan,
            "country": country}


def submit_application(session, form, *, ip=None, user_agent=None, now=None):
    """Handle one public submission. Returns (outcome, application | None):

      'honeypot'      a bot filled the hidden field - nothing stored, no email
      'rate_limited'  too many from this network today, or too many from
                      everyone in the last hour - nothing stored
      'duplicate'     this email already has an application waiting - nothing new
      'ok'            stored; confirmation + owner notification sent. If the
                      owner's auto-approve rules match, the partner is created
                      and the signing link is emailed (they still must sign).

    Raises CommsError (all problems) when the form is invalid."""
    from models import AffiliateApplication
    now = _now(now)
    if str(form.get(HONEYPOT_FIELD) or "").strip():
        log.info("partner application honeypot tripped")
        return "honeypot", None
    data = clean_application(form)
    ip_hash = hash_ip(ip)
    if ip_hash:
        recent = (session.query(AffiliateApplication)
                  .filter(AffiliateApplication.ip_hash == ip_hash,
                          AffiliateApplication.created_at > now - dt.timedelta(days=1)).count())
        if recent >= APPLY_LIMIT_PER_IP_DAY:
            log.info("partner application rate limited")
            return "rate_limited", None
    hourly = (session.query(AffiliateApplication)
              .filter(AffiliateApplication.created_at > now - dt.timedelta(hours=1)).count())
    if hourly >= apply_limit_per_hour():
        log.warning("partner application global hourly cap reached (%d)", hourly)
        return "rate_limited", None
    waiting = (session.query(AffiliateApplication)
               .filter(AffiliateApplication.email == data["email"],
                       AffiliateApplication.status == "new").first())
    if waiting is not None:
        return "duplicate", waiting
    app_row = AffiliateApplication(id=uuid.uuid4(), status="new", agreed_policies_at=now,
                                   ip_hash=ip_hash, user_agent=(user_agent or "")[:500] or None,
                                   created_at=now, **data)
    session.add(app_row)
    session.commit()
    _email_application_received(app_row)
    auto = None
    try:
        import affiliate_owner as owner
        auto = owner.try_auto_approve(session, app_row, now=now)
    except Exception:   # noqa: BLE001  (the application is stored; the owner reviews it)
        session.rollback()
        log.exception("auto-approve failed for application %s", app_row.id)
    _email_owner_new_application(session, app_row, auto=auto)
    return "ok", app_row


def apply_limit_per_hour() -> int:
    try:
        return max(1, int(getattr(config, "AFFILIATE_APPLY_MAX_PER_HOUR", 30) or 30))
    except (TypeError, ValueError):
        return 30


def owner_email() -> str:
    """The one owner address (affiliate_service.owner_email)."""
    return afs.owner_email()


def admin_applications_url(app_id=None) -> str:
    base = agr._base() + "/admin/affiliate_applications/"
    return base + ("view?id=%s" % app_id if app_id else "")


def _email_application_received(app_row) -> bool:
    first = greeting_name(app_row.name)
    body = ("Hi %s,\n\n"
            "Thanks for applying to the TradeWave partner program. We have your application "
            "and we read every one personally. You will hear from us by email, usually within "
            "5 business days.\n\n"
            "If we approve it, we will email you a private link to review and sign the partner "
            "agreement. Your link and discount code go live once you sign.\n\n"
            "Nothing to do for now. If you have a question, reply to this email or write to "
            "%s.\n\nThe TradeWave team\n" % (first, HELP_EMAIL))
    return _send(app_row.email, "We received your TradeWave partner application", body)


def _email_owner_new_application(session, app_row, auto=None) -> bool:
    flags = application_flags(session, app_row)
    notes = []
    if auto is not None:
        notes.append("AUTO-APPROVED by your rules: partner %s was created (paused until they "
                     "sign) and the signing link was %s."
                     % (auto["code"], "emailed" if auto["emailed"] else "NOT emailed - send it yourself"))
    if flags["affiliate"] is not None and auto is None:
        notes.append("ALREADY A PARTNER: %s (%s)" % (flags["affiliate"].code, flags["affiliate"].status))
    if flags["earlier"]:
        notes.append("Earlier applications from this email: %d" % len(flags["earlier"]))
    body = ("New partner application.\n\n"
            "Name      : %s\nEmail     : %s\nWebsite   : %s\nAudience  : %s\nCountry   : %s\n\n"
            "Channels:\n%s\n\nHow they will promote:\n%s\n\n%s"
            "%s:\n%s\n"
            % (app_row.name, app_row.email, app_row.website or "-",
               AUDIENCE_SIZE_LABEL.get(app_row.audience_size, app_row.audience_size or "-"),
               app_row.country or "-", app_row.channels or "-", app_row.promo_plan or "-",
               ("\n".join(notes) + "\n\n") if notes else "",
               "Open the application" if auto is not None else "Approve or reject",
               admin_applications_url(app_row.id)))
    subject = "%s partner application: %s" % ("Auto-approved" if auto is not None else "New",
                                              "(name hidden: contains a link)" if has_link(app_row.name)
                                              else app_row.name)
    return _send(owner_email(), subject, body, reply_to=app_row.email or None)


def application_flags(session, app_row) -> dict:
    """Duplicate detection by email: {'affiliate': existing partner | None,
    'earlier': [other applications from the same email, newest first]}."""
    from models import Affiliate, AffiliateApplication
    from sqlalchemy import func
    email = (app_row.email or "").strip().lower()
    aff = None
    earlier = []
    if email:
        aff = (session.query(Affiliate).filter(func.lower(Affiliate.email) == email)
               .order_by(Affiliate.created_at.desc()).first())
        earlier = (session.query(AffiliateApplication)
                   .filter(AffiliateApplication.email == email,
                           AffiliateApplication.id != app_row.id)
                   .order_by(AffiliateApplication.created_at.desc()).all())
    return {"affiliate": aff, "earlier": earlier}


def suggest_code(session, name) -> str:
    """A free partner code from the applicant's first name (ANNE, ANNE2, ...)."""
    from models import Affiliate
    base = re.sub(r"[^A-Z0-9]", "", ((name or "").strip().split(" ")[0]).upper())[:20]
    if len(base) < 2:
        base = "PARTNER"
    taken = {c for (c,) in session.query(Affiliate.code).filter(Affiliate.code.like(base + "%")).all()}
    code, n = base, 1
    while code in taken:
        n += 1
        code = "%s%d" % (base, n)
    return code


def default_discount(terms=None) -> Decimal:
    t = terms or afs.DEFAULT_TERMS
    try:
        d = Decimal(str(getattr(config, "AFFILIATE_DEFAULT_DISCOUNT_PCT", 20)))
    except Exception:   # noqa: BLE001
        d = Decimal("20")
    return afs.clamp_discount(d, t)


def approve_application(session, app_row, *, code, discount_pct, actor, note=None,
                        send_email=True, now=None):
    """Create the partner on the default v2 terms (PAUSED until they sign),
    mark the application approved and email the signing link. Returns
    (affiliate, emailed). Raises CommsError; nothing is saved on an error."""
    from models import Affiliate
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    now = _now(now)
    if app_row.status == "approved":
        raise CommsError("This application was already approved.")
    code = afs.normalize_code(code)
    try:
        afs.validate_code(code)
    except afs.AffiliateError as e:
        raise CommsError(str(e))
    terms = afs.get_terms(session)
    try:
        discount = Decimal(str(discount_pct).strip())
    except Exception:   # noqa: BLE001
        raise CommsError("Customer discount must be a number.")
    max_d = Decimal(str((terms or afs.DEFAULT_TERMS).max_discount_pct))
    if discount < 0 or discount > max_d:
        raise CommsError("Customer discount must be between 0%% and %s%%." % _pct(max_d))
    email = (app_row.email or "").strip().lower()
    existing = (session.query(Affiliate)
                .filter(func.lower(Affiliate.email) == email,
                        Affiliate.status != "terminated").first())
    if existing is not None:
        raise CommsError("%s is already a partner (code %s). Reject this application as a "
                         "duplicate instead." % (email, existing.code))
    if session.query(Affiliate).filter(Affiliate.code == code).first() is not None:
        raise CommsError("The code %s is taken. Choose another." % code)

    aff = Affiliate(
        id=uuid.uuid4(), code=code, name=app_row.name, email=email, discount_pct=discount,
        commission_pct=afs.preview_offer(10000, discount, terms)["commission_rate_pct"],
        commission_model="recurring", status="paused",
        terms_id=getattr(terms, "id", None), agreement_version=agr.AGREEMENT_VERSION,
        agreement_token_version=0, terminated_for_cause=False,
        notes="Created from partner application %s (%s)." % (app_row.id, now.date().isoformat()))
    try:
        session.add(aff)
        session.flush()                         # claims the code (UNIQUE) before Stripe
        if discount > 0:
            coupon_id, promo_id = afs.provision_stripe_objects(aff)
            aff.stripe_coupon_id, aff.stripe_promotion_code_id = coupon_id, promo_id
        app_row.status = "approved"
        app_row.affiliate_id = aff.id
        app_row.decided_by = actor
        app_row.decided_at = now
        app_row.decision_note = (note or "").strip()[:2000] or None
        session.commit()
    except IntegrityError:
        session.rollback()
        raise CommsError("The code %s is taken. Choose another." % code)
    except afs.AffiliateError as e:
        session.rollback()
        raise CommsError("Stripe could not create the discount code: %s" % e)
    # The code must not be redeemable before the agreement is signed (same as
    # the Add affiliate form). Signing reactivates it.
    try:
        import promo_service as ps
        ps.set_promo_active(aff, False)
    except Exception as e:   # noqa: BLE001
        log.warning("could not deactivate promo for new partner %s: %s", code, e)
    emailed = False
    if send_email:
        emailed = bool(agr.email_signing_link(aff, note=note))
    return aff, emailed


def reject_application(session, app_row, *, actor, reason=None, send_email=True, now=None) -> bool:
    """Mark rejected; optionally email the applicant (with the reason when one
    is given). Returns True if the email was accepted."""
    if app_row.status == "approved":
        raise CommsError("This application was already approved. Pause or terminate the "
                         "partner instead.")
    reason = (reason or "").replace("\r\n", "\n").strip()[:2000]
    if "—" in reason:
        raise CommsError("Please replace the long dash with ' - ' (house style).")
    app_row.status = "rejected"
    app_row.decided_by = actor
    app_row.decided_at = _now(now)
    app_row.decision_note = reason or None
    session.commit()
    if not send_email:
        return False
    first = greeting_name(app_row.name)
    body = ("Hi %s,\n\n"
            "Thank you for applying to the TradeWave partner program and for the time you "
            "put into it. We are not able to offer you a place right now.\n\n%s"
            "This is not a judgment of your work. We keep the program small, and you are "
            "welcome to apply again later.\n\nThe TradeWave team\n"
            % (first, (reason + "\n\n") if reason else ""))
    return _send(app_row.email, "Your TradeWave partner application", body)


def mark_application_spam(session, app_row, actor, now=None) -> None:
    if app_row.status == "approved":
        raise CommsError("This application was already approved.")
    app_row.status = "spam"
    app_row.decided_by = actor
    app_row.decided_at = _now(now)
    session.commit()


# ---------------------------------------------------------------------------
# 5) Lifecycle events (what the daily job looks for)
# ---------------------------------------------------------------------------
_PLAN_LABEL = {"navigator": "Navigator", "analyst": "Analyst", "strategist": "Strategist"}
_INTERVAL_LABEL = {"year": "annual", "month": "monthly"}


def _rule_text(terms) -> str:
    months = int(getattr(terms, "activity_rule_months", 12) or 12)
    return ("at least 1 new paying customer every %d months, with a %d-day grace"
            % (months, afs.ACTIVITY_GRACE_DAYS))


WELCOME_KEY = "welcome"


def _welcome_event(session, aff, terms):
    signed = _utc(aff.agreement_signed_at)
    if signed is None:
        return None
    discount = afs.clamp_discount(aff.discount_pct, terms)
    offer = afs.preview_offer(10000, discount, terms)
    code_line = ("Your code: %s (customers can type it at checkout)\n" % aff.code
                 if discount > 0 else "")
    body = (
        "Hi %s,\n\n"
        "Your agreement is signed and your partner account is live. Welcome.\n\n"
        "Your link: %s\n"
        "Your landing page: %s\n%s\n"
        "Right now your audience gets %s%% off and you earn %s%% of the list price in the "
        "first year (%s). On a $100 plan that is %s for the customer and %s for you. The "
        "discount and your commission come out of the same %s%%, so a bigger discount means a "
        "smaller commission. You can change the discount in Settings. After the first year "
        "you earn %s%% of what the customer pays on renewals.\n\n"
        "One rule to know about renewals: they keep paying while you bring in %s. If a "
        "window ends without one, renewal payments from your existing customers earn $0 "
        "until your next new paying customer, and renewals missed in that time are not paid "
        "later. First-year commissions are never affected. We email you 60, 30 and 7 days "
        "before a window ends, and your dashboard always shows the date.\n\n"
        "Three things to do first:\n"
        "1. Open your dashboard and copy your link.\n"
        "2. Add your PayPal or Wise details and upload your tax form (Payouts page). We need both "
        "before we can pay you.\n"
        "3. Share your link. Always say that you earn a commission.\n\n"
        "Watch the 2-minute tour: %s\n\n"
        "Questions: use Help in your dashboard, reply to this email or write to %s."
        % (first_name(aff), agr.join_link(aff), agr.referral_link(aff), code_line,
           _pct(discount), _pct(offer["commission_rate_pct"]),
           "%s%% off for them = %s%% for you" % (_pct(discount), _pct(offer["commission_rate_pct"])),
           money(Decimal(offer["customer_pays_cents"]) / 100),
           money(Decimal(offer["partner_earns_cents"]) / 100),
           _pct(getattr(terms, "pool_pct", 50)),
           _pct(getattr(terms, "renewal_pct", 25)), _rule_text(terms),
           dashboard_url("#tour"), HELP_EMAIL))
    # ONE welcome per partner, ever: a constant key, so re-signing (new terms,
    # a regenerated link) never sends a second one. An older dated key
    # ('welcome:<date>') counts as already welcomed.
    from models import AffiliateNotification
    if (session.query(AffiliateNotification.id)
            .filter(AffiliateNotification.affiliate_id == aff.id,
                    AffiliateNotification.event_type == "welcome",
                    AffiliateNotification.event_key != WELCOME_KEY).first()) is not None:
        return None
    return make_event("welcome", WELCOME_KEY,
                      "Welcome to the TradeWave partner program", body, occurred_at=signed,
                      link=("Open your partner dashboard", dashboard_url()))


def _first_click_event(session, aff):
    from models import AffiliateClick
    from sqlalchemy import func
    first = (session.query(func.min(AffiliateClick.day))
             .filter(AffiliateClick.affiliate_id == aff.id, AffiliateClick.clicks > 0).scalar())
    if first is None:
        return None
    if isinstance(first, str):
        first = dt.date.fromisoformat(first[:10])
    body = ("Hi %s,\n\n"
            "Someone just visited TradeWave through your link. It is working.\n\n"
            "Your dashboard counts every click, signup and paying customer. Each new visitor "
            "gets a free 7-day trial, so a first payment usually follows a week or more after "
            "the click.\n\n"
            "Keep sharing: %s" % (first_name(aff), agr.join_link(aff)))
    return make_event("first_click", "first_click", "Your link got its first click", body,
                      occurred_at=dt.datetime(first.year, first.month, first.day, tzinfo=UTC),
                      link=("See your clicks", dashboard_url()))


def _new_customer_events(session, aff, terms, status):
    from models import AffiliateReferral
    refs = (session.query(AffiliateReferral)
            .filter(AffiliateReferral.affiliate_id == aff.id,
                    AffiliateReferral.first_paid_at.isnot(None),
                    AffiliateReferral.source != "return").all())
    total = len(refs)
    out = []
    for ref in refs:
        plan = _PLAN_LABEL.get(ref.tier or "", "")
        interval = _INTERVAL_LABEL.get(ref.billing_interval or "", "")
        plan_text = (" on the %s plan" % " ".join(x for x in (plan, interval) if x)
                     if (plan or interval) else "")
        ref_terms = getattr(ref, "terms", None) or terms
        earn = ""
        if ref.offer_type == "promo":
            earn = ("They bought during a TradeWave sale, so you earn %s%% of what they paid. "
                    % _pct(getattr(ref_terms, "promo_commission_pct", 50)))
        elif ref.list_price_cents and ref.discount_pct is not None:
            try:
                offer = afs.preview_offer(int(ref.list_price_cents), ref.discount_pct, ref_terms)
                earn = ("You earn %s on this payment (%s%% of the list price). "
                        % (money(Decimal(offer["partner_earns_cents"]) / 100),
                           _pct(offer["commission_rate_pct"])))
            except afs.AffiliateError:
                earn = ""
        until = status.get("active_until")
        keep = (" This also keeps your renewal commissions active until %s." % _day(until)
                if until else "")
        body = ("Hi %s,\n\n"
                "A customer you referred just made their first payment%s. %sThe exact amount "
                "is on your Earnings page.\n\n"
                "You now have %d paying customer%s in total. To protect their privacy we "
                "never share who they are.%s"
                % (first_name(aff), plan_text, earn, total, "" if total == 1 else "s", keep))
        out.append(make_event("new_customer", "new_customer:%s" % ref.id,
                              "You have a new paying customer", body,
                              occurred_at=_utc(ref.first_paid_at),
                              link=("See your earnings", dashboard_url("/earnings"))))
    return out


NEGATIVE_MONTH_TEXT = ("No payout this month - refunds were larger than sales; "
                       "the balance carries forward")


def _statement_events(session, aff, now):
    from models import AffiliatePayout
    # Only a recent month is news: re-computing an old month must not
    # announce its statement again as if it were new.
    oldest = (now - dt.timedelta(days=100)).date()
    rows = (session.query(AffiliatePayout)
            .filter(AffiliatePayout.affiliate_id == aff.id,
                    AffiliatePayout.period_start >= oldest,
                    AffiliatePayout.status.in_(("pending", "paid"))).all())
    months = {}
    for r in rows:
        # FINALIZED months only: a row for the month still running (a mid-month
        # preview that was committed) is not a statement yet.
        if r.period_end is None or r.period_end >= now.date():
            continue
        months.setdefault(r.period_start, []).append(r)
    out = []
    for period, items in months.items():
        label = period.strftime("%B %Y")
        items = sorted(items, key=lambda i: i.currency or "")
        amounts = [Decimal(str(i.commission_amount or 0)) for i in items]
        totals = ", ".join(money(i.commission_amount, i.currency) for i in items)
        if any(a < 0 for a in amounts) and not any(a > 0 for a in amounts):
            subject = "Your %s statement: no payout this month" % label
            body = ("Hi %s,\n\n"
                    "Your %s statement is ready. %s.\n\n"
                    "Month total: %s. Nothing is owed by you and nothing is taken from your "
                    "bank or PayPal. The amount is set against your next month with "
                    "commission.\n\n"
                    "The line-by-line breakdown is on your Earnings page."
                    % (first_name(aff), label, NEGATIVE_MONTH_TEXT, totals))
        else:
            subject = "Your %s statement is ready" % label
            body = ("Hi %s,\n\n"
                    "Your %s statement is ready. Commission for the month: %s.\n\n"
                    "Payouts are sent by the 15th of the month after the statement month, once "
                    "your balance is at least %s and your tax form is on file. A smaller balance "
                    "is not lost: it carries forward.\n\n"
                    "The line-by-line breakdown is on your Earnings page."
                    % (first_name(aff), label, totals, money(afs.payout_minimum())))
        occurred = max((_utc(i.computed_at) for i in items if i.computed_at is not None),
                       default=None)
        out.append(make_event("statement_ready", "statement:%s" % period.strftime("%Y-%m"),
                              subject, body, occurred_at=occurred,
                              link=("Open your Payouts page", dashboard_url("/payouts"))))
    return out


def _payout_events(session, aff):
    from models import AffiliatePayout
    rows = (session.query(AffiliatePayout)
            .filter(AffiliatePayout.affiliate_id == aff.id, AffiliatePayout.status == "paid",
                    AffiliatePayout.paid_at.isnot(None)).all())
    out = []
    for r in rows:
        # The amount actually SENT: a row marked paid at its exported amount
        # carries it in paid_amount; otherwise it is the ledger amount.
        sent = r.paid_amount if getattr(r, "paid_amount", None) is not None else r.commission_amount
        if Decimal(str(sent or 0)) <= 0:
            continue
        ref = (r.external_ref or "").strip()
        if ref.startswith(("carried:", "forfeited:")):
            continue                              # bookkeeping rows, not a payment
        method = {"paypal": "PayPal", "wise": "Wise"}.get((aff.payout_method or "").lower(), "")
        amount = money(sent, r.currency)
        body = ("Hi %s,\n\n"
                "We sent your payout of %s for %s%s.%s\n\n"
                "Depending on the provider it can take a few days to arrive. If it has not "
                "arrived after 5 business days, write to %s."
                % (first_name(aff), amount, r.period_start.strftime("%B %Y"),
                   (" by %s" % method) if method else "",
                   (" Reference: %s." % ref) if ref else "", HELP_EMAIL))
        out.append(make_event("payout_sent", "payout:%s" % r.id, "Payout sent: %s" % amount,
                              body, occurred_at=_utc(r.paid_at),
                              link=("See your payouts", dashboard_url("/payouts"))))
    return out


def _has_open_customer(session, aff) -> bool:
    from models import AffiliateReferral
    return (session.query(AffiliateReferral.id)
            .filter(AffiliateReferral.affiliate_id == aff.id,
                    AffiliateReferral.first_paid_at.isnot(None),
                    AffiliateReferral.ended_at.is_(None)).first()) is not None


def _activity_events(session, aff, terms, status, now):
    """60 / 30 / 7-day warnings, 'renewals stopped' and 'renewals resumed'.
    Only for a partner who has a customer that can still renew."""
    from models import AffiliateNotification
    out = []
    rule = _rule_text(terms)
    until, lapsed = status.get("active_until"), status.get("lapsed_since")
    last = status.get("last_new_customer_at")
    if status.get("active") and until is not None:
        if _has_open_customer(session, aff):
            days_left = (until - now.date()).days
            due = [t for t in ACTIVITY_WARNING_DAYS if days_left <= t]
            if due and days_left >= 0:
                t = min(due)                     # only the most urgent one that applies
                when = "today" if days_left == 0 else ("in %d day%s" % (days_left, "" if days_left == 1 else "s"))
                body = ("Hi %s,\n\n"
                        "Your renewal commissions stay active while you bring in %s. Your "
                        "current window ends %s, on %s.\n\n"
                        "Refer 1 new paying customer before then and the window starts again. "
                        "If it ends first, renewal payments from your existing customers earn "
                        "$0 until your next new paying customer, and renewals missed in that "
                        "time are not paid later.\n\n"
                        "Your first-year commissions are not affected.\n\n"
                        "Your link: %s"
                        % (first_name(aff), rule, when, _day(until), agr.join_link(aff)))
                subject = ("%d day%s left to keep your renewal commissions"
                           % (days_left, "" if days_left == 1 else "s")) if days_left else \
                    "Last day to keep your renewal commissions"
                out.append(make_event("activity_warning_%d" % t,
                                      "activity_warn:%d:%s" % (t, until.isoformat()),
                                      subject, body, occurred_at=now,
                                      link=("Open your dashboard", dashboard_url())))
        # resumed: a 'stopped' notice went out before the latest new customer
        if last is not None:
            lapsed_note = (session.query(AffiliateNotification)
                           .filter(AffiliateNotification.affiliate_id == aff.id,
                                   AffiliateNotification.event_type == "renewals_lapsed")
                           .order_by(AffiliateNotification.created_at.desc()).first())
            if lapsed_note is not None and _utc(lapsed_note.created_at) < last:
                body = ("Hi %s,\n\n"
                        "Good news. Your new paying customer restarted your renewal "
                        "commissions. Renewal payments from your customers earn commission "
                        "again from now on, until at least %s.\n\n"
                        "Renewals that were paid while you were inactive are not paid later. "
                        "To stay active, bring in %s."
                        % (first_name(aff), _day(until), rule))
                out.append(make_event("renewals_resumed", "resumed:%s" % last.date().isoformat(),
                                      "Your renewal commissions are active again", body,
                                      occurred_at=last,
                                      link=("Open your dashboard", dashboard_url())))
    elif not status.get("active") and lapsed is not None and _has_open_customer(session, aff):
        body = ("Hi %s,\n\n"
                "Your activity window ended on %s, so your renewal commissions have stopped "
                "for now. The rule is %s.\n\n"
                "What this means: renewal payments from your existing customers earn $0 while "
                "you are inactive, and those renewals are not paid later. Your first-year "
                "commissions are not affected.\n\n"
                "How to fix it: refer 1 new paying customer. Your renewal commissions start "
                "again with that customer's first payment.\n\n"
                "Your link: %s"
                % (first_name(aff), _day(lapsed), rule, agr.join_link(aff)))
        out.append(make_event("renewals_lapsed", "lapsed:%s" % lapsed.isoformat(),
                              "Your renewal commissions have stopped for now", body,
                              occurred_at=dt.datetime(lapsed.year, lapsed.month, lapsed.day, tzinfo=UTC),
                              link=("Open your dashboard", dashboard_url())))
    return out


def campaign_offer_text(campaign) -> str:
    if campaign.offer_type == "percent":
        return "%s%% off for new customers" % _pct(campaign.percent_off)
    parts = []
    for tier, tier_label in _PLAN_LABEL.items():
        for iv, iv_label in (("month", "monthly"), ("year", "annual")):
            v = (campaign.intro_prices or {}).get(afs.offer_key(tier, iv))
            if (v is not None and tier in (campaign.tiers or [])
                    and iv in (campaign.billing_intervals or [])):
                price = money(Decimal(int(v)) / 100)
                if price.endswith(".00"):
                    price = price[:-3]
                parts.append("%s %s for %s" % (tier_label, iv_label, price))
    return (", ".join(parts) + " for new customers") if parts else "a special price for new customers"


def _campaign_events(aff, terms, campaigns, now):
    if aff.status != "active":
        return []
    out = []
    for c in campaigns:
        ends = _utc(c.ends_at)
        body = ("Hi %s,\n\n"
                "A TradeWave sale just started: %s. The offer is %s. It runs until %s UTC.\n\n"
                "Your link already works with it. Customers who use your link get whichever "
                "price is lower, the sale price or your discount, and the sale stays credited "
                "to you. When a customer you refer buys at the sale price, you earn %s%% of "
                "what they pay.\n\n"
                "Your tracked link: %s\n"
                "Short link: %s"
                % (first_name(aff), c.name, campaign_offer_text(c),
                   _day_time(ends),
                   _pct(getattr(terms, "promo_commission_pct", 50)),
                   agr.join_link(aff), agr.referral_link(aff)))
        out.append(make_event("campaign_started", "campaign:%s" % c.id,
                              "New TradeWave sale: %s - your link already works" % c.name, body,
                              occurred_at=_utc(c.starts_at),
                              link=("Get copy and links to share", dashboard_url("/promote"))))
    return out


def _discount_events(session, aff, terms):
    from models import AffiliateDiscountChange
    rows = (session.query(AffiliateDiscountChange)
            .filter(AffiliateDiscountChange.affiliate_id == aff.id)
            .order_by(AffiliateDiscountChange.changed_at, AffiliateDiscountChange.id).all())
    groups = {}
    for r in rows:
        when = _utc(r.changed_at)
        if when is None:
            continue
        key = "discount:%s:%s" % (when.strftime("%Y%m%d%H%M"), _pct(r.new_pct))
        groups.setdefault(key, []).append(r)
    out = []
    for key, items in groups.items():
        r = items[0]
        when = _utc(r.changed_at)
        try:
            rate = afs.preview_offer(10000, r.new_pct, terms)["commission_rate_pct"]
            earn = " You now earn %s%% of the list price on first-year payments." % _pct(rate)
        except afs.AffiliateError:
            earn = ""
        was = ("from %s%% to %s%%" % (_pct(r.old_pct), _pct(r.new_pct))
               if r.old_pct is not None else "to %s%%" % _pct(r.new_pct))
        body = ("Hi %s,\n\n"
                "Your customer discount changed %s on %s UTC.%s\n\n"
                "The new discount applies to customers who check out from now on. Customers "
                "you already have keep their price, and what you earn on them does not "
                "change. You can change the discount again after 24 hours.\n\n"
                "If you did not make this change, reply to this email or write to %s right "
                "away."
                % (first_name(aff), was, _day_time(when), earn,
                   HELP_EMAIL))
        out.append(make_event("discount_changed", key,
                              "Your customer discount is now %s%%" % _pct(r.new_pct), body,
                              occurred_at=when,
                              link=("Review your offer", dashboard_url("/settings#offer"))))
    return out


def _signing_reminder_events(aff, now):
    """A reminder 3 and 10 days after an approved partner was created and has
    still not signed. Only the latest one that is due is returned; the age
    cut-off in run_for_affiliate keeps an old unsigned row from being mailed."""
    if aff.agreement_signed_at is not None or aff.status != "paused":
        return []
    created = _utc(aff.created_at)
    if created is None or not (aff.email or "").strip():
        return []
    due = [d for d in SIGNING_REMINDER_DAYS if now - created >= dt.timedelta(days=d)]
    if not due:
        return []
    d = max(due)
    try:
        url = agr.signing_url(aff)
    except Exception:   # noqa: BLE001  (no signing secret configured)
        return []
    last = d == max(SIGNING_REMINDER_DAYS)
    body = ("Hi %s,\n\n"
            "Your TradeWave partner application was approved, and one step is left: review "
            "and sign the partner agreement. It takes a few minutes. Your link and your "
            "code %s start working the moment you sign.\n\n"
            "%s"
            "If the link has expired or you have a question first, reply to this email or "
            "write to %s."
            % (first_name(aff), aff.code,
               "This is our last reminder. Your place stays open, and you can ask us for a "
               "fresh link at any time.\n\n" if last else "", HELP_EMAIL))
    return [make_event("signing_reminder", "signing_reminder:%d" % d,
                       "Reminder: sign your TradeWave partner agreement", body,
                       occurred_at=created + dt.timedelta(days=d),
                       link=("Review and sign the agreement", url))]


def collect_events(session, aff, now=None, campaigns=None) -> list:
    """Every lifecycle event that currently applies to this partner (old and
    new alike - deliver() and the age cut-off decide what is actually sent)."""
    now = _now(now)
    if aff.status == "terminated":
        return _payout_events(session, aff)       # a final balance is still confirmed
    if aff.agreement_signed_at is None:
        return _signing_reminder_events(aff, now)  # not a partner yet: reminders + admin messages
    terms = afs.terms_for(session, aff) or afs.DEFAULT_TERMS
    status = afs.activity_status(aff, now, session=session, terms=terms)
    if campaigns is None:
        campaigns = live_campaigns(session, now)
    events = []
    welcome = _welcome_event(session, aff, terms)
    if welcome is not None:
        events.append(welcome)
    click = _first_click_event(session, aff)
    if click is not None:
        events.append(click)
    events += _new_customer_events(session, aff, terms, status)
    events += _statement_events(session, aff, now)
    events += _payout_events(session, aff)
    events += _activity_events(session, aff, terms, status, now)
    events += _campaign_events(aff, terms, campaigns, now)
    events += _discount_events(session, aff, terms)
    return events


def live_campaigns(session, now=None) -> list:
    now = _now(now)
    return [c for c in afs.list_campaigns(session, include_archived=False)
            if afs.campaign_is_live(c, now)]


def run_for_affiliate(session, aff, now=None, campaigns=None, dry_run=False) -> list:
    """Deliver this partner's due events. Returns [(event, row | None)] for
    the events that were inside the age cut-off."""
    now = _now(now)
    cutoff = now - max_event_age()
    disabled = disabled_prefs(session, aff.id)
    out = []
    for ev in collect_events(session, aff, now, campaigns):
        occurred = _utc(ev.occurred_at)
        if occurred is None or occurred < cutoff or occurred > now + dt.timedelta(minutes=5):
            continue
        if dry_run:
            out.append((ev, None))
            continue
        out.append((ev, deliver(session, aff, ev, now, disabled)))
    return out


def notify_tax_form(session, form, now=None):
    """Tell the partner the result of a tax-form review: a Messages inbox row
    plus a REQUIRED email (the partner cannot be paid until a form is on
    file, so this is not optional). Once per form and result. Returns the
    notification row or None."""
    aff = form.affiliate
    if aff is None or form.status not in ("accepted", "rejected"):
        return None
    import affiliate_ops as ops
    label = ops.TAX_FORM_LABELS.get(form.form_type, "tax form")
    if form.status == "accepted":
        ev = make_event(
            "tax_form_accepted", "tax_form:%s:accepted" % form.id,
            "Your %s is on file" % label,
            "Hi %s,\n\n"
            "We have accepted your %s. Your tax form is now on file, so nothing more is "
            "needed from you for payouts.\n\n"
            "Payouts are sent by the 15th of the month after the statement month, once your "
            "balance is at least %s." % (first_name(aff), label, money(afs.payout_minimum())),
            occurred_at=_now(now), link=("Open your Payouts page", dashboard_url("/payouts")))
    else:
        ev = make_event(
            "tax_form_rejected", "tax_form:%s:rejected" % form.id,
            "Your %s needs a fix" % label,
            "Hi %s,\n\n"
            "We could not accept the %s you uploaded.\n\n"
            "What to fix: %s\n\n"
            "Please upload a corrected form on the Payouts page of your partner dashboard. "
            "Do not email the form. We cannot send a payout until a form is on file."
            % (first_name(aff), label, form.reject_reason or "see the note on your Payouts page"),
            occurred_at=_now(now),
            link=("Upload a corrected form", dashboard_url("/payouts#tax-form")))
    return deliver(session, aff, ev, now)


def notify_payout_details_changed(session, aff, change, now=None):
    """Confirm a self-serve payout-details change to the partner: a Messages
    inbox row plus a REQUIRED email to the ACCOUNT email (aff.email), never to
    the new payout address, so the real owner hears about a change they did
    not make. `change` is the dict from affiliate_service.set_payout_details.
    Addresses are masked. Returns the notification row or None."""
    if not change or not change.get("changed"):
        return None
    label = afs.PAYOUT_METHOD_LABELS
    new = "%s, %s" % (label.get(change["new_method"], change["new_method"]),
                      afs.mask_email(change["new_email"]))
    when = _utc(change.get("changed_at")) or _now(now)
    hold = _utc(change.get("hold_until"))
    not_you = ("If you did not make this change, write to %s right away and we will stop "
               "any payout and secure your account." % HELP_EMAIL)
    if change.get("replaced"):
        old = "%s, %s" % (label.get(change["old_method"], change["old_method"] or "not set"),
                          afs.mask_email(change["old_email"]))
        subject = "Your payout details were changed"
        body = ("Hi %s,\n\n"
                "The payout details on your TradeWave partner account were changed on %s UTC.\n\n"
                "Before: %s\n"
                "Now: %s\n\n"
                "As a security step, payouts to you are on hold for 24 hours%s. You do not need "
                "to do anything: after that, payouts go to the new details as usual.\n\n%s"
                % (first_name(aff), _day_time(when), old, new,
                   (", until %s UTC" % _day_time(hold)) if hold else "", not_you))
    elif not change.get("had_details"):
        subject = "Your payout details were added"
        body = ("Hi %s,\n\n"
                "Payout details were added to your TradeWave partner account on %s UTC.\n\n"
                "Payouts go to: %s\n\n%s"
                % (first_name(aff), _day_time(when), new, not_you))
    else:
        subject = "Your payout details were updated"
        body = ("Hi %s,\n\n"
                "The account holder name on your TradeWave payout details was updated on %s UTC. "
                "The payout method and payout email did not change.\n\n"
                "Payouts go to: %s\n\n%s"
                % (first_name(aff), _day_time(when), new, not_you))
    ev = make_event("payout_details_changed", "payout_details:%s" % when.strftime("%Y%m%dT%H%M%S%f"),
                    subject, body, occurred_at=when,
                    link=("Review your payout details", dashboard_url("/payouts#payout-details")))
    return deliver(session, aff, ev, now)


# Events that are delivered at the moment they happen (not found again by
# collect_events): the daily job retries their failed sends.
_ONE_SHOT_EVENTS = ("message", "program_notice", "tax_form_accepted", "tax_form_rejected",
                    "help_answer", "payout_details_changed")


def retry_failed(session, now=None) -> int:
    """Send again the one-shot notices whose email failed (provider refused,
    or email was not configured at the time) and that still have retries
    left. Returns how many were sent."""
    from models import Affiliate, AffiliateNotification as N
    now = _now(now)
    rows = (session.query(N)
            .filter(N.email_status == "failed", N.event_type.in_(_ONE_SHOT_EVENTS),
                    N.attempts < MAX_SEND_ATTEMPTS, N.created_at >= now - max_event_age()).all())
    sent = 0
    for row in rows:
        aff = session.get(Affiliate, row.affiliate_id)
        if aff is None:
            continue
        ev = make_event(row.event_type, row.event_key, row.subject, row.body, occurred_at=now,
                        link=((row.link_label, row.link_url) if row.link_url else None),
                        message_id=row.message_id)
        try:
            out = deliver(session, aff, ev, now)
        except Exception:   # noqa: BLE001
            session.rollback()
            log.exception("retry of notification %s failed", row.id)
            continue
        if out is not None and out.email_status == "sent":
            sent += 1
    return sent


def _daily_housekeeping(session, now, stats) -> None:
    """Everything the daily job does besides the per-partner events. Each step
    is isolated: one failing step never stops the others."""
    steps = []

    def jobs_step():
        import affiliate_jobs as jobs
        stats["jobs"] = jobs.run_pending(session, now=now)
    steps.append(("background jobs", jobs_step))

    def retry_step():
        stats["retried"] = retry_failed(session, now)
    steps.append(("retry failed notices", retry_step))

    def digest_step():
        import affiliate_owner as owner
        stats["owner_digest"] = owner.send_digest(session, now=now)
    steps.append(("owner digest", digest_step))

    def purge_step():
        import affiliate_help as ah
        stats["help_purged"] = ah.purge_old(session, force=True)
    steps.append(("help retention purge", purge_step))

    for label, fn in steps:
        try:
            fn()
        except Exception:   # noqa: BLE001
            session.rollback()
            stats["errors"] += 1
            log.exception("daily step failed: %s", label)


def run_daily(session, now=None, dry_run=False) -> dict:
    """The daily job. Idempotent: safe to run any number of times a day."""
    from models import Affiliate
    now = _now(now)
    campaigns = live_campaigns(session, now)
    stats = {"partners": 0, "sent": 0, "skipped": 0, "failed": 0, "already": 0, "errors": 0}
    ids = [a.id for a in session.query(Affiliate).order_by(Affiliate.code).all()]
    for aid in ids:
        try:
            aff = session.get(Affiliate, aid)
            if aff is None:
                continue
            stats["partners"] += 1
            for ev, row in run_for_affiliate(session, aff, now, campaigns, dry_run):
                if dry_run:
                    log.info("dry-run: would deliver %s (%s) to %s", ev.type, ev.key, aff.code)
                    stats["sent"] += 1
                elif row is None:
                    stats["already"] += 1
                else:
                    stats[row.email_status if row.email_status in stats else "failed"] += 1
                    log.info("%s %s -> %s (%s%s)", ev.type, ev.key, aff.code, row.email_status,
                             (": " + row.email_reason) if row.email_reason else "")
        except Exception:   # noqa: BLE001  (one partner must not stop the job)
            session.rollback()
            stats["errors"] += 1
            log.exception("partner comms failed for affiliate %s", aid)
    if not dry_run:
        _daily_housekeeping(session, now, stats)
    return stats


def notify_signed(affiliate_id) -> None:
    """Best-effort hook for the signing route: send the welcome right away
    instead of waiting for the daily job. Own session; never raises."""
    try:
        import models
        s = models.Session()
        try:
            aff = s.get(models.Affiliate, affiliate_id)
            if aff is not None:
                run_for_affiliate(s, aff)
        finally:
            s.close()
    except Exception:   # noqa: BLE001
        log.exception("welcome email after signing failed (the daily job retries)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Partner lifecycle emails (idempotent daily job).")
    ap.add_argument("--dry-run", action="store_true", help="log what would be sent; write nothing")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s affiliate_comms: %(message)s")
    import models
    s = models.Session()
    try:
        stats = run_daily(s, dry_run=args.dry_run)
    finally:
        s.close()
    log.info("done%s: %s", " (dry run)" if args.dry_run else "", stats)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
