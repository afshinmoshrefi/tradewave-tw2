"""
Affiliate agreement e-signature (in-house clickwrap).
=====================================================

The single place that knows how the affiliate agreement is presented, signed,
and recorded. The Flask route (/affiliate/sign/<token> in web/app.py) is a thin
wrapper around the functions here; the heavy lifting + the testable core
(token signing, body rendering, record_signature) lives in this module.

Design (matches the locked decisions in docs/AFFILIATE_AGREEMENT.md):
  - Magic link, no login/role: a tokenized URL identifies the affiliate. The
    token is an itsdangerous URLSafeTimedSerializer payload signed with the
    app secret + a dedicated salt, carrying (affiliate_id, token_version) and a
    30-day expiry. Bumping agreement_token_version invalidates an issued link.
  - The agreement BODY is single-sourced from docs/AFFILIATE_AGREEMENT.md (the
    internal DRAFT banner blockquote and the static Acceptance/Exhibit A tables
    are stripped); Exhibit A is rendered per-affiliate from their own fields.
  - Signing records name + timestamp + IP + user-agent + version + an immutable
    snapshot of the exact terms (the E-SIGN/UETA audit trail), and flips a
    'paused' affiliate to 'active' so the referral code goes live.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import html

sys.path.insert(0, "/home/flask")
import config  # noqa: E402

import markdown  # noqa: E402
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired  # noqa: E402

# Bump when the terms change materially so signatures record which version was
# shown. Keep in step with docs/AFFILIATE_AGREEMENT.md.
AGREEMENT_VERSION = "2026-06-06"

# itsdangerous salt namespaces this use of the app secret away from Flask's own
# session cookie signing (which uses the same WORKOS_COOKIE_PASSWORD).
_SIGN_SALT = "affiliate-agreement-sign"

# Link lifetime (seconds). 30 days is plenty for a hand-picked partner to sign.
SIGN_TOKEN_MAX_AGE = 60 * 60 * 24 * 30

# Human labels for the stored commission_model ids (mirror AffiliateAdmin.form_choices).
COMMISSION_MODEL_LABELS = {
    "recurring": "Recurring (lifetime)",
    "duration_12mo": "First 12 months",
    "first_payment": "First payment only",
}

_MD_PATH = Path(__file__).resolve().parent.parent / "docs" / "AFFILIATE_AGREEMENT.md"
_BODY_HTML_CACHE = None


class AgreementError(Exception):
    """Bad signing input (e.g. blank name)."""


class AlreadySigned(AgreementError):
    """The agreement was already signed - signing is idempotent / one-shot."""


# --- token signing ----------------------------------------------------------

def _serializer():
    secret = config.WORKOS_COOKIE_PASSWORD
    if not secret:
        # Fail closed: never sign with a guessable fallback key (token forgery).
        raise AgreementError("signing secret (WORKOS_COOKIE_PASSWORD) is not configured")
    return URLSafeTimedSerializer(secret, salt=_SIGN_SALT)


def make_sign_token(affiliate_id, token_version) -> str:
    """Sign (affiliate_id, token_version) into a URL-safe token."""
    return _serializer().dumps({"aid": str(affiliate_id), "tv": int(token_version or 0)})


def verify_sign_token(token, max_age=SIGN_TOKEN_MAX_AGE):
    """Return {'aid': str, 'tv': int} if valid + unexpired, else None."""
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, Exception):
        return None
    if not isinstance(data, dict) or "aid" not in data:
        return None
    return {"aid": str(data["aid"]), "tv": int(data.get("tv", 0))}


# --- URLs --------------------------------------------------------------------

def _base():
    return (config.tw2_public_url or "https://tradewave.ai/").rstrip("/")


def referral_link(affiliate) -> str:
    return f"{_base()}/?code={affiliate.code}"


def signing_url(affiliate) -> str:
    token = make_sign_token(affiliate.id, getattr(affiliate, "agreement_token_version", 0))
    return f"{_base()}/affiliate/sign/{token}"


# --- presentation ------------------------------------------------------------

def _fmt_pct(value) -> str:
    """20.00 -> '20', 15.50 -> '15.5'."""
    if value is None:
        return ""
    d = Decimal(str(value)).normalize()
    # normalize() can yield exponent form (e.g. 2E+1); render as plain.
    return format(d, "f").rstrip("0").rstrip(".") if "." in format(d, "f") else format(d, "f")


def agreement_body_html() -> str:
    """The agreement body (Sections 1-15) as HTML, single-sourced from the .md.

    Strips the internal DRAFT banner (the leading blockquote) and everything
    from '## Acceptance' onward (the static signature + Exhibit A tables) - those
    are replaced by the live signing UI + a per-affiliate Exhibit A.
    """
    global _BODY_HTML_CACHE
    if _BODY_HTML_CACHE is not None:
        return _BODY_HTML_CACHE
    raw = _MD_PATH.read_text(encoding="utf-8")
    # drop the blockquote note (the only '>' block in the doc)
    body = "\n".join(ln for ln in raw.splitlines() if not ln.lstrip().startswith(">"))
    cut = body.find("## Acceptance")
    if cut != -1:
        body = body[:cut].rstrip().rstrip("-").rstrip()  # also trims the trailing --- rule
    _BODY_HTML_CACHE = markdown.markdown(
        body, extensions=["tables", "sane_lists", "fenced_code"])
    return _BODY_HTML_CACHE


def exhibit(affiliate) -> dict:
    """Per-affiliate Exhibit A values for the signing template / snapshot."""
    return {
        "name": affiliate.name or "",
        "email": affiliate.email or "",
        "code": affiliate.code,
        "referral_link": referral_link(affiliate),
        "discount_pct": _fmt_pct(affiliate.discount_pct),
        "commission_pct": _fmt_pct(affiliate.commission_pct),
        "model_label": COMMISSION_MODEL_LABELS.get(
            affiliate.commission_model, affiliate.commission_model or ""),
        "payout_method": (affiliate.payout_method or "").upper(),
        "payout_email": affiliate.payout_email or "",
    }


def build_snapshot(affiliate) -> str:
    """An immutable, self-contained HTML record of the EXACT terms signed -
    body + this affiliate's Exhibit A + the signature line. Stored verbatim so a
    later edit to the source .md can't change what a partner is shown to have
    agreed to."""
    ex = exhibit(affiliate)
    signed_at = affiliate.agreement_signed_at
    e = lambda x: html.escape(str(x if x is not None else ""))  # escape all interpolated values
    rows = "".join(
        f"<tr><th style='text-align:left;padding:4px 12px 4px 0'>{e(k)}</th>"
        f"<td style='padding:4px 0'>{e(v)}</td></tr>"
        for k, v in [
            ("Affiliate", ex["name"]), ("Contact email", ex["email"]),
            ("Referral Code", ex["code"]), ("Referral Link", ex["referral_link"]),
            ("Audience Discount", f"{ex['discount_pct']}% off for the first 12 months"),
            ("Commission Rate", f"{ex['commission_pct']}% of Net Revenue"),
            ("Commission Model", ex["model_label"]),
            ("Payout", f"{ex['payout_method']} — {ex['payout_email']}"),
        ])
    return (
        f"<!-- TradeWave Affiliate Program Agreement v{e(affiliate.agreement_version)} -->\n"
        f"{agreement_body_html()}\n"
        f"<h2>Exhibit A — Affiliate-Specific Terms</h2>\n<table>{rows}</table>\n"
        f"<h2>Acceptance</h2>\n<p>Electronically signed by "
        f"<strong>{e(affiliate.agreement_signed_name)}</strong> on "
        f"{e(signed_at.isoformat() if signed_at else '')} "
        f"(IP {e(affiliate.agreement_signed_ip)}). Agreement version "
        f"{e(affiliate.agreement_version)}.</p>"
    )


# --- the testable core -------------------------------------------------------

def record_signature(affiliate, signed_name, ip, user_agent):
    """Apply a signature to `affiliate` (does NOT commit - the caller owns the
    session/transaction). Idempotent guard: raises AlreadySigned if already
    signed. Flips a 'paused' affiliate to 'active'."""
    if affiliate.agreement_signed_at is not None:
        raise AlreadySigned("This agreement has already been signed.")
    name = (signed_name or "").strip()
    if len(name) < 2:
        raise AgreementError("Please type your full legal name to sign.")
    affiliate.agreement_signed_name = name[:200]
    affiliate.agreement_signed_at = datetime.now(timezone.utc)
    affiliate.agreement_signed_ip = (ip or "")[:100]
    affiliate.agreement_signed_user_agent = (user_agent or "")[:500]
    if not affiliate.agreement_version:
        affiliate.agreement_version = AGREEMENT_VERSION
    affiliate.agreement_snapshot = build_snapshot(affiliate)
    if affiliate.status == "paused":
        affiliate.status = "active"


def email_signed_copy(affiliate) -> bool:
    """Best-effort: email the executed-agreement confirmation to the affiliate
    + the support inbox. Returns True if Resend accepted it. Never raises."""
    try:
        from email_utils import resend_send_email
    except Exception:
        return False
    recipients = [a for a in [affiliate.email, getattr(config, "SUPPORT_EMAIL_TO", "")] if a]
    if not recipients:
        return False
    signed_at = affiliate.agreement_signed_at
    body = (
        f"The TradeWave Affiliate Program Agreement has been signed.\n\n"
        f"Affiliate : {affiliate.name}\n"
        f"Code      : {affiliate.code}\n"
        f"Signed by : {affiliate.agreement_signed_name}\n"
        f"Date      : {signed_at.isoformat() if signed_at else ''}\n"
        f"Version   : {affiliate.agreement_version}\n\n"
        f"View your signed agreement any time:\n{signing_url(affiliate)}\n\n"
        f"Your referral link:\n{referral_link(affiliate)}\n"
    )
    try:
        return bool(resend_send_email(
            to=recipients,
            subject=f"TradeWave Affiliate Agreement — signed by {affiliate.agreement_signed_name}",
            body_text=body,
        ))
    except Exception:
        return False
