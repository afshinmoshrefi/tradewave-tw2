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
    are stripped); Exhibit A is rendered per-affiliate from their own fields
    and their program terms (affiliate_service.terms_for -> AffiliateTerms):
    exhibit() builds one ordered row list that BOTH the signing page and the
    frozen snapshot print, so what is shown is what is stored.
  - Signing records name + timestamp + IP + user-agent + version + an immutable
    snapshot of the exact terms (the E-SIGN/UETA audit trail), and flips a
    'paused' affiliate to 'active' so the referral code goes live.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import html
import re

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config  # noqa: E402

import markdown  # noqa: E402
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired  # noqa: E402

# Bump when the terms change materially so signatures record which version was
# shown. Keep in step with docs/AFFILIATE_AGREEMENT.md.
#   2026-06-11  version 1: commission = rate x net revenue, three commission models
#   2026-11-24  version 2 (TW-TASK-0038): 50% pool, partner-chosen 0-25% discount,
#               promotions, renewals for a Renewal Term, activity requirement
# Snapshots signed under an earlier version are immutable stored text
# (affiliates.agreement_snapshot / the migration's archive) and are never
# re-rendered from this module.
AGREEMENT_VERSION = "2026-11-24"

# Payout minimum stated in Section 5.3 and Exhibit A (whole US dollars).
PAYOUT_MINIMUM_USD = 50

# Grace period added to the activity window (Section 4.5) when
# affiliate_service does not define ACTIVITY_GRACE_DAYS itself.
ACTIVITY_GRACE_DAYS_DEFAULT = 30

# List price used for the worked dollar example in Exhibit A (cents).
EXAMPLE_LIST_PRICE_CENTS = 10000

# itsdangerous salt namespaces this use of the app secret away from Flask's own
# session cookie signing (which uses the same WORKOS_COOKIE_PASSWORD).
_SIGN_SALT = "affiliate-agreement-sign"

# Link lifetime (seconds). 30 days is plenty for a hand-picked partner to sign.
SIGN_TOKEN_MAX_AGE = 60 * 60 * 24 * 30

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


def join_link(affiliate) -> str:
    """The co-branded landing page the affiliate can send their audience to."""
    return f"{_base()}/join/{affiliate.code}"


def _partner_reply_to() -> str:
    """Reply-To on every partner email: the support inbox, so a partner who
    answers the email reaches a person (the From address does not)."""
    return (getattr(config, "AFFILIATE_SUPPORT_EMAIL", "") or "help@tradewave.ai").strip()


def dashboard_link() -> str:
    """The affiliate's logged-in partner dashboard (web/affiliate_portal/)."""
    return f"{_base()}/account/affiliate"


def signing_url(affiliate) -> str:
    token = make_sign_token(affiliate.id, getattr(affiliate, "agreement_token_version", 0))
    return f"{_base()}/affiliate/sign/{token}"


# --- presentation ------------------------------------------------------------

_EM_DASH_RE = re.compile(r"[ \t]*—[ \t]*")


def _no_em_dash(s: str) -> str:
    """Project rule: no em dashes in customer content. Defensive backstop so an
    em dash (e.g. from the source agreement .md) can never reach the signed doc."""
    return _EM_DASH_RE.sub(" - ", s)


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
    _BODY_HTML_CACHE = _no_em_dash(markdown.markdown(
        body, extensions=["tables", "sane_lists", "fenced_code"]))
    return _BODY_HTML_CACHE


def addendum_html(affiliate) -> str:
    """The per-affiliate rider ('Exhibit B - Additional Terms') as HTML, rendered
    from affiliate.agreement_addendum (operator-authored markdown). Returns "" when
    there is none. The standard body (Sections 1-15) is identical for every
    affiliate; ONLY this rider varies, so a special term for one affiliate never
    touches anyone else's contract."""
    raw = (getattr(affiliate, "agreement_addendum", None) or "").strip()
    if not raw:
        return ""
    return _no_em_dash(markdown.markdown(
        raw, extensions=["tables", "sane_lists", "fenced_code"]))


def _fmt_money(cents) -> str:
    """8000 -> '$80.00', 9975 -> '$99.75'."""
    return "$%s" % format(Decimal(int(cents)) / Decimal(100), ",.2f")


def _terms(affiliate, session=None):
    """The program terms behind this affiliate's Exhibit A (an AffiliateTerms
    row, or the service default). Uses the given session, else the session the
    ORM object is attached to, else the already-loaded `terms` attribute."""
    import affiliate_service as afs
    if session is None:
        try:
            from sqlalchemy.orm import object_session
            session = object_session(affiliate)
        except Exception:
            session = None
    if session is not None:
        return afs.terms_for(session, affiliate)
    return getattr(affiliate, "terms", None) or afs.DEFAULT_TERMS


def renewal_term_label(terms) -> str:
    """'Commission Years 2-5' / '... 2-10' / 'Lifetime' for a terms version.
    renewal_years is the LAST commission year; None = lifetime."""
    last = getattr(terms, "renewal_years", None)
    if last is None:
        return "Lifetime"
    last = int(last)
    if last < 2:
        return "None (first year only)"
    return "Commission Years 2-%d" % last


def exhibit(affiliate, session=None) -> dict:
    """Per-affiliate Exhibit A (agreement version 2) for the signing page and
    the snapshot.

    Terms come from the backend (affiliate_service.terms_for): Commission Pool,
    maximum Customer Discount, Promotion Rate, Renewal Rate, Renewal Term and
    the Activity Requirement. The partner's CURRENT Customer Discount is shown
    per billing interval (annual / monthly), each with the first-year rate it
    leaves (pool - discount). `example` is a worked dollar example on a $100
    plan at the annual discount. `rows` is the ordered (label, value) list
    that both renderers print."""
    import affiliate_service as afs

    t = _terms(affiliate, session)
    pool = Decimal(str(t.pool_pct))
    sched = afs.renewal_schedule(t)
    months = int(sched["activity_rule_months"])

    def _interval(iv):
        d = afs.clamp_discount(afs.effective_discount_pct(affiliate, iv), t)
        return {"discount": d, "discount_pct": _fmt_pct(d),
                "commission_pct": _fmt_pct(max(Decimal("0"), pool - d))}

    annual, monthly = _interval("year"), _interval("month")
    offer = afs.preview_offer(EXAMPLE_LIST_PRICE_CENTS, annual["discount"], t)
    renewal = afs.preview_renewal(EXAMPLE_LIST_PRICE_CENTS, t)
    promo = afs.preview_promo(EXAMPLE_LIST_PRICE_CENTS, None, t)
    term_label = renewal_term_label(t)
    has_renewals = sched["lifetime"] or int(sched["last_year"]) >= 2
    example = {
        "list_price": _fmt_money(EXAMPLE_LIST_PRICE_CENTS),
        "discount_pct": annual["discount_pct"],
        "customer_pays": _fmt_money(offer["customer_pays_cents"]),
        "partner_earns": _fmt_money(offer["partner_earns_cents"]),
        "retained": _fmt_money(offer["retained_cents"]),
        "renewal_paid": _fmt_money(renewal["customer_pays_cents"]),
        "renewal_earns": _fmt_money(renewal["partner_earns_cents"]),
    }
    example["first_year_text"] = (
        "On a %(list_price)s plan at your current %(discount_pct)s%% Customer "
        "Discount, the customer pays %(customer_pays)s, you earn %(partner_earns)s "
        "and TradeWave keeps %(retained)s." % example)
    if has_renewals:
        example["renewal_text"] = (
            "When that customer renews at %s (%s) and you meet the Activity "
            "Requirement, you earn %s."
            % (example["renewal_paid"],
               "any later year" if sched["lifetime"]
               else "years 2-%d" % int(sched["last_year"]),
               example["renewal_earns"]))
    else:
        example["renewal_text"] = "Renewal payments earn no Commission."
    example["text"] = example["first_year_text"] + " " + example["renewal_text"]

    # Owner decision 2026-11-24: the trailing window carries a grace period
    # (affiliate_service.ACTIVITY_GRACE_DAYS; 30 if this build predates it).
    grace = int(getattr(afs, "ACTIVITY_GRACE_DAYS", ACTIVITY_GRACE_DAYS_DEFAULT) or 0)
    if months > 0:
        window = "%d months" % months
        if grace > 0:
            window += " plus a %d-day grace period" % grace
        activity = ("At least 1 New Paying Customer in the trailing %s, "
                    "measured at each renewal payment. Free trials do not count. "
                    "Renewal Commission on a payment made while this is not met "
                    "is forfeited." % window)
    else:
        activity = "None"
    payout = (affiliate.payout_method or "").upper()
    payout_email = affiliate.payout_email or ""
    ex = {
        "version": AGREEMENT_VERSION,
        "name": affiliate.name or "",
        "email": affiliate.email or "",
        "code": affiliate.code,
        "referral_link": referral_link(affiliate),
        "terms_version": getattr(t, "version", "") or "",
        "pool_pct": _fmt_pct(pool),
        "max_discount_pct": _fmt_pct(t.max_discount_pct),
        # annual / default discount and the first-year rate it leaves
        "discount_pct": annual["discount_pct"],
        "commission_pct": annual["commission_pct"],
        "annual": {k: annual[k] for k in ("discount_pct", "commission_pct")},
        "monthly": {k: monthly[k] for k in ("discount_pct", "commission_pct")},
        "is_split": annual["discount"] != monthly["discount"],
        "promo_pct": _fmt_pct(t.promo_commission_pct),
        "renewal_pct": _fmt_pct(t.renewal_pct),
        "renewal_term": term_label,
        "renewal_lifetime": bool(sched["lifetime"]),
        "renewal_last_year": sched["last_year"],
        "activity_rule_months": months,
        "activity_grace_days": grace if months > 0 else 0,
        "activity_rule": activity,
        "payout_minimum": "$%d" % PAYOUT_MINIMUM_USD,
        "payout_method": payout,
        "payout_email": payout_email,
        "example": example,
    }
    # Compatibility for web/templates/affiliate_sign.html, which still prints a
    # "Commission Model" row from this key until it is switched to `rows`.
    ex["model_label"] = (
        "Program v2: %s%% Commission Pool in the first year, then %s%% of the "
        "Amount Paid on renewals (Renewal Term: %s). %s"
        % (ex["pool_pct"], ex["renewal_pct"], term_label, example["text"]))
    ex["rows"] = [
        ("Affiliate", ex["name"]),
        ("Contact email", ex["email"]),
        ("Referral Code", ex["code"]),
        ("Referral Link", ex["referral_link"]),
        ("Commission Pool", "%s%% of the List Price (first year)" % ex["pool_pct"]),
        ("Maximum Customer Discount", "%s%%" % ex["max_discount_pct"]),
        ("Your Customer Discount - annual plans",
         "%s%% off the List Price (first year). You earn %s%% of the List Price."
         % (annual["discount_pct"], annual["commission_pct"])),
        ("Your Customer Discount - monthly plans",
         "%s%% off the List Price (first 12 months). You earn %s%% of the List Price."
         % (monthly["discount_pct"], monthly["commission_pct"])),
        ("Changing your discount",
         "Any time from your partner dashboard, 0%% to %s%%. One Customer Discount "
         "applies to monthly and annual plans. Applies to new checkouts only "
         "(Section 4.2)." % ex["max_discount_pct"]),
        ("Promotion Rate",
         "%s%% of the Amount Paid when a Promotion price applies (for example %s "
         "on a %s sale)" % (ex["promo_pct"], _fmt_money(promo["partner_earns_cents"]),
                            _fmt_money(promo["customer_pays_cents"]))),
        ("Renewal Rate", "%s%% of the Amount Paid" % ex["renewal_pct"]),
        ("Renewal Term", term_label),
        ("Activity Requirement", activity),
        ("Payout minimum", "%s (smaller balances are carried forward)" % ex["payout_minimum"]),
        ("Payout method", "%s - %s" % (payout, payout_email) if payout_email else payout),
        ("Worked example", example["text"]),
    ]
    return ex


def build_snapshot(affiliate, session=None) -> str:
    """An immutable, self-contained HTML record of the EXACT terms signed -
    body + this affiliate's Exhibit A + the signature line. Stored verbatim so a
    later edit to the source .md (or to the partner's discount, or to the terms
    row) can't change what a partner is shown to have agreed to."""
    ex = exhibit(affiliate, session)
    signed_at = affiliate.agreement_signed_at
    e = lambda x: html.escape(str(x if x is not None else ""))  # escape all interpolated values
    rows = "".join(
        f"<tr><th style='text-align:left;padding:4px 12px 4px 0;vertical-align:top'>{e(k)}</th>"
        f"<td style='padding:4px 0'>{e(v)}</td></tr>"
        for k, v in ex["rows"])
    # Per-affiliate rider, frozen alongside the rest of the terms. Empty for the
    # vast majority of affiliates (no addendum), in which case Exhibit B is omitted.
    add_html = addendum_html(affiliate)
    exhibit_b = (f"<h2>Exhibit B - Additional Terms</h2>\n{add_html}\n" if add_html else "")
    snap = (
        f"<!-- TradeWave Affiliate Program Agreement v{e(affiliate.agreement_version)} -->\n"
        f"{agreement_body_html()}\n"
        f"<h2>Exhibit A - Affiliate-Specific Terms</h2>\n<table>{rows}</table>\n"
        f"{exhibit_b}"
        f"<h2>Acceptance</h2>\n<p>Electronically signed by "
        f"<strong>{e(affiliate.agreement_signed_name)}</strong> on "
        f"{e(signed_at.isoformat() if signed_at else '')} "
        f"(IP {e(affiliate.agreement_signed_ip)}). Agreement version "
        f"{e(affiliate.agreement_version)}.</p>"
    )
    return _no_em_dash(snap)


# --- the testable core -------------------------------------------------------

def record_signature(affiliate, signed_name, ip, user_agent):
    """Apply a signature to `affiliate` (does NOT commit - the caller owns the
    session/transaction). Idempotent guard: raises AlreadySigned if already
    signed. Flips a 'paused' affiliate to 'active'."""
    if affiliate.agreement_signed_at is not None:
        raise AlreadySigned("This agreement has already been signed.")
    if getattr(affiliate, "status", None) == "terminated":
        raise AgreementError("This affiliate has been terminated; the agreement "
                             "can no longer be signed.")
    name = (signed_name or "").strip()
    if len(name) < 2:
        raise AgreementError("Please type your full legal name to sign.")
    affiliate.agreement_signed_name = name[:200]
    affiliate.agreement_signed_at = datetime.now(timezone.utc)
    affiliate.agreement_signed_ip = (ip or "")[:100]
    affiliate.agreement_signed_user_agent = (user_agent or "")[:500]
    # Always stamp the version of the text that was actually shown and is
    # frozen below (the body is always rendered from the current .md). A row
    # that still carries an older label - e.g. a partner paused by the v2
    # migration for re-signature - must not record v2 text under a v1 label.
    affiliate.agreement_version = AGREEMENT_VERSION
    affiliate.agreement_snapshot = build_snapshot(affiliate)
    if affiliate.status == "paused":
        affiliate.status = "active"


def email_signed_copy(affiliate) -> bool:
    """Best-effort: email the executed agreement to the affiliate (with the FROZEN
    snapshot inline, so they hold the actual signed document) and a notification to
    the support inbox - as TWO separate sends, so neither recipient sees the
    other's address. Returns True if the affiliate copy was accepted. Never raises."""
    try:
        from email_utils import resend_send_email
    except Exception:
        return False
    signed_at = affiliate.agreement_signed_at
    summary = (
        f"The TradeWave Affiliate Program Agreement has been signed.\n\n"
        f"Affiliate : {affiliate.name}\n"
        f"Code      : {affiliate.code}\n"
        f"Signed by : {affiliate.agreement_signed_name}\n"
        f"Date      : {signed_at.isoformat() if signed_at else ''}\n"
        f"Version   : {affiliate.agreement_version}\n"
    )
    sent = False
    # 1) the affiliate: their executed copy (snapshot inline) + their links.
    if affiliate.email:
        body = (summary +
                f"\nView your signed agreement any time:\n{signing_url(affiliate)}\n"
                f"\nShare either of these with your audience (both apply your discount "
                f"and credit you):\n"
                f"  - Your referral link: {referral_link(affiliate)}\n"
                f"  - Your landing page:  {join_link(affiliate)}\n"
                f"\nTrack your referrals, earnings and payouts in your partner dashboard "
                f"(sign in or create a free TradeWave account with this email "
                f"address, {affiliate.email}):\n{dashboard_link()}\n")
        html = None
        if affiliate.agreement_snapshot:
            html = (f"<p>Your TradeWave Affiliate Program Agreement, electronically "
                    f"signed {signed_at.isoformat() if signed_at else ''}. A copy is "
                    f"below for your records.</p><hr>{affiliate.agreement_snapshot}")
        try:
            sent = bool(resend_send_email(
                to=affiliate.email,
                subject="Your signed TradeWave Affiliate Agreement",
                body_text=body, html=html,
                reply_to=_partner_reply_to()))
        except Exception:
            pass
    # 2) support inbox: a notification (the full doc lives in Flask-Admin).
    support_to = getattr(config, "SUPPORT_EMAIL_TO", "")
    if support_to:
        try:
            resend_send_email(
                to=support_to,
                subject=f"Affiliate agreement signed: {affiliate.code}",
                body_text=summary + f"\nView the signed snapshot in Flask-Admin "
                                     f"(Affiliates -> {affiliate.code}).\n")
        except Exception:
            pass
    return sent


def email_signing_link(affiliate, note=None) -> bool:
    """Best-effort: email the affiliate the private link to review and e-sign the
    agreement. Returns True if Resend accepted it. Never raises. Does NOT modify
    or commit the affiliate.

    note: optional operator-written personal message ("Hi Michael, here is the
    updated agreement for your review") shown at the top of the email, above the
    standard copy. Plain text; HTML-escaped, newlines preserved."""
    if not getattr(affiliate, "email", None):
        return False
    try:
        from email_utils import resend_send_email
    except Exception:
        return False
    from html import escape as _esc
    url = signing_url(affiliate)
    ref = referral_link(affiliate)
    join = join_link(affiliate)
    dash = dashboard_link()
    first = (affiliate.name or "").strip().split(" ")[0] or "there"
    note = (note or "").strip()[:2000]
    note_text = f"{note}\n\n----\n\n" if note else ""
    note_html = (
        '<p style="white-space:pre-line;border-left:3px solid #6366f1;'
        'padding:8px 14px;background:#f5f6ff;border-radius:6px;color:#1f2a44;">'
        f"{_esc(note)}</p>" if note else "")
    body_text = note_text + (
        f"Hi {first},\n\n"
        f"Welcome to the TradeWave affiliate program. Please review and sign your "
        f"affiliate agreement here (no login needed):\n\n{url}\n\n"
        f"The link is private to you and expires in 30 days. Once you sign, your "
        f"referral code activates and we email you a copy for your records.\n\n"
        f"Then you can share either of these with your audience (both apply your "
        f"discount and credit you automatically):\n"
        f"  - Your referral link:  {ref}\n"
        f"  - Your landing page:   {join}  (a ready-made page describing TradeWave "
        f"and your discount)\n\n"
        f"You can follow your referrals, earnings and payouts any time in your "
        f"partner dashboard. Sign in (or create a free account) with this email "
        f"address:\n{dash}\n\n"
        f"Thanks,\nThe TradeWave team\n"
    )
    html_body = note_html + (
        f"<p>Hi {_esc(first)},</p>"
        f"<p>Welcome to the TradeWave affiliate program. Please review and sign your "
        f"affiliate agreement (no login needed):</p>"
        f'<p><a href="{_esc(url)}">Review &amp; sign your agreement &rarr;</a></p>'
        f"<p>The link is private to you and expires in 30 days. Once you sign, your "
        f"referral code activates and we email you a copy for your records.</p>"
        f"<p>Then share either of these with your audience - both apply your "
        f"discount and credit you automatically:</p>"
        f"<ul>"
        f'<li>Your referral link: <a href="{_esc(ref)}">{_esc(ref)}</a></li>'
        f'<li>Your landing page: <a href="{_esc(join)}">{_esc(join)}</a> '
        f"(a ready-made page describing TradeWave and your discount)</li>"
        f"</ul>"
        f"<p>You can follow your referrals, earnings and payouts any time in your "
        f'<a href="{_esc(dash)}">partner dashboard</a>. Sign in (or create a free '
        f"account) with this email address.</p>"
        f"<p>Thanks,<br>The TradeWave team</p>"
    )
    try:
        return bool(resend_send_email(
            to=affiliate.email,
            subject="Sign your TradeWave Affiliate Agreement",
            body_text=body_text, html=html_body,
            reply_to=_partner_reply_to()))
    except Exception:
        return False
