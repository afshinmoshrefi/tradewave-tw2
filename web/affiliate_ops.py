"""Affiliate operations + growth tools (TW-TASK-0039 package C).

Service layer for five features. The screens live in
web/affiliate_portal/ops_routes.py (partner) and web/affiliate_ops_admin.py
(admin); the monthly owner summary is web/affiliate_ops_summary.py.

1. Tax forms   - validated PDF upload, Fernet-encrypted at rest outside the
                 web root, admin review (accept satisfies the payout gate).
2. Sub-links   - partner-created named links (?code=X&sub=name) with clicks /
                 signups / paid / earned per link and per campaign. REPORTING
                 ONLY: nothing here is read by attribution or the engine.
3. Bulk payouts- PayPal Payouts CSV / Wise batch CSV export for payable
                 ledger rows, and bulk mark-paid with references. NEVER moves
                 money and never talks to PayPal or Wise.
4. Creatives   - admin-uploaded banners / logos / copy, filled in with the
                 partner's tracked link on the Promote page.

Errors meant for a person are raised as OpsError; the message is safe to show.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import logging
import os
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import config
import affiliate_service as afs
import affiliate_ops_models as om

log = logging.getLogger("tw2.affiliate_ops")

UTC = dt.timezone.utc
SUB_COOKIE = afs.SUB_COOKIE
HELP_EMAIL = "help@tradewave.ai"


class OpsError(afs.AffiliateError):
    """Bad input or a refused action; str(e) is safe to show the person."""


def _now(now=None):
    return afs._utc(now) or dt.datetime.now(UTC)


def _clean(text):
    """House style: never an em-dash (or en-dash used as one) in stored copy."""
    return re.sub(r"\s*%s\s*|\s+%s\s+" % (chr(0x2014), chr(0x2013)), " - ", text or "")


# ===========================================================================
# 1. Tax forms
# ===========================================================================
TAX_FORM_LABELS = {"w9": "W-9", "w8ben": "W-8BEN", "w8bene": "W-8BEN-E"}
TAX_FORM_CHOICES = (("w9", "W-9 (U.S. person or business)"),
                    ("w8ben", "W-8BEN (individual outside the U.S.)"),
                    ("w8bene", "W-8BEN-E (company outside the U.S.)"))
TAX_STATUS_LABELS = {"received": "Received - being reviewed", "accepted": "Accepted",
                     "rejected": "Not accepted", "replaced": "Replaced"}
TAX_UPLOADS_PER_DAY = 5
_PDF_MIME = ("application/pdf", "application/x-pdf")


def _tax_fernet():
    """MultiFernet over config.TAX_FORM_KEY (comma-separated keys; the first
    encrypts, all decrypt), or None when no valid key is configured."""
    raw = getattr(config, "TAX_FORM_KEY", "") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        return None
    try:
        from cryptography.fernet import Fernet, MultiFernet
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except Exception:   # noqa: BLE001 - a malformed key is "not configured"
        log.error("TW2_TAX_FORM_KEY is set but is not a valid Fernet key; tax-form upload is off")
        return None


def _tax_dir():
    """The storage folder, or None if it is unset or sits inside the web root
    (an encrypted tax form must still never be reachable by URL)."""
    raw = (getattr(config, "TAX_FORM_DIR", "") or "").strip()
    if not raw:
        return None
    path = Path(raw).resolve()
    web_root = Path(getattr(config, "web_root_dir", "/var/www/tradewave/")).resolve()
    if path == web_root or web_root in path.parents:
        log.error("TW2_TAX_FORM_DIR is inside the web root; tax-form upload is off")
        return None
    return path


def tax_upload_enabled() -> bool:
    return _tax_fernet() is not None and _tax_dir() is not None


def validate_tax_pdf(filename, mimetype, blob) -> None:
    """Size, extension, declared type and magic bytes. Raises OpsError."""
    limit = int(getattr(config, "TAX_FORM_MAX_BYTES", 5 * 1024 * 1024))
    if not blob:
        raise OpsError("That file is empty. Choose your completed PDF.")
    if len(blob) > limit:
        raise OpsError("That file is too large (%d MB max)." % (limit // (1024 * 1024)))
    if not (filename or "").lower().endswith(".pdf"):
        raise OpsError("Upload the form as a PDF file (.pdf).")
    if (mimetype or "").split(";")[0].strip().lower() not in _PDF_MIME:
        raise OpsError("Upload the form as a PDF file (.pdf).")
    # A real PDF starts with %PDF-<version> and carries an %%EOF marker near
    # the end. Checked on the bytes, never on the name or the declared type.
    if not re.match(rb"%PDF-\d\.\d", blob[:8]) or b"%%EOF" not in blob[-2048:]:
        raise OpsError("That file is not a valid PDF. Export or print the form to PDF and try again.")


def _delete_tax_file(form) -> None:
    name, form.storage_name = form.storage_name, None
    folder = _tax_dir()
    if not name or folder is None:
        return
    try:
        (folder / name).unlink(missing_ok=True)
    except OSError:
        log.warning("could not delete tax form file for form %s", form.id)


def store_tax_form(session, affiliate, form_type, filename, mimetype, blob, user_id=None, now=None):
    """Validate, encrypt and store a partner's tax form; returns the new
    'received' row. Any earlier form still waiting for review is marked
    'replaced' and its file deleted. Commits."""
    now = _now(now)
    fernet, folder = _tax_fernet(), _tax_dir()
    if fernet is None or folder is None:
        raise OpsError("Secure upload is not available right now. Contact %s and we will "
                       "send you a secure way to get it to us. Do not email the form." % HELP_EMAIL)
    if form_type not in om.TAX_FORM_TYPES:
        raise OpsError("Choose which form you are uploading.")
    validate_tax_pdf(filename, mimetype, blob)
    T = om.AffiliateTaxForm
    recent = (session.query(T).filter(T.affiliate_id == affiliate.id,
                                      T.uploaded_at >= now - dt.timedelta(days=1)).count())
    if recent >= TAX_UPLOADS_PER_DAY:
        raise OpsError("You have uploaded several forms today. Try again tomorrow, or contact %s."
                       % HELP_EMAIL)
    token = fernet.encrypt(blob)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    name = uuid.uuid4().hex + ".bin"
    fd = os.open(str(folder / name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(token)
    except Exception:
        (folder / name).unlink(missing_ok=True)
        raise
    try:
        for old in session.query(T).filter(T.affiliate_id == affiliate.id, T.status == "received").all():
            old.status = "replaced"
            _delete_tax_file(old)
        row = T(affiliate_id=affiliate.id, form_type=form_type, status="received",
                storage_name=name, original_filename=os.path.basename(filename or "")[:200],
                size_bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                uploaded_by_user_id=user_id, uploaded_at=now)
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
        (folder / name).unlink(missing_ok=True)
        raise
    return row


def read_tax_form(form) -> bytes:
    """Decrypted PDF bytes of a stored form. Raises OpsError if it is gone or
    cannot be decrypted (wrong / rotated-out key)."""
    fernet, folder = _tax_fernet(), _tax_dir()
    if fernet is None or folder is None:
        raise OpsError("TW2_TAX_FORM_KEY is not configured on this box, so the file cannot be opened.")
    if not form.storage_name or not re.match(r"^[0-9a-f]{32}\.bin$", form.storage_name):
        raise OpsError("This form's file is no longer stored (rejected and replaced forms are deleted).")
    try:
        token = (folder / form.storage_name).read_bytes()
    except OSError:
        raise OpsError("The stored file is missing on this box.")
    try:
        from cryptography.fernet import InvalidToken
        return fernet.decrypt(token)
    except InvalidToken:
        raise OpsError("The file could not be decrypted with the configured key.")


def accept_tax_form(session, form, actor, now=None):
    """Admin accepts a received form: it becomes the form on file, which is
    exactly what the payout gate reads (affiliates.tax_form_received_at)."""
    now = _now(now)
    if form.status != "received":
        raise OpsError("Only a form that is waiting for review can be accepted.")
    T = om.AffiliateTaxForm
    for old in session.query(T).filter(T.affiliate_id == form.affiliate_id, T.status == "accepted",
                                       T.id != form.id).all():
        old.status = "replaced"
        _delete_tax_file(old)
    form.status, form.reviewed_at, form.reviewed_by, form.reject_reason = "accepted", now, actor, None
    aff = form.affiliate
    aff.tax_form_type = form.form_type
    aff.tax_form_received_at = now
    session.commit()
    return form


def reject_tax_form(session, form, reason, actor, now=None):
    """Admin rejects a received form with a reason the partner will read. The
    stored file is deleted (a rejected tax form is not kept)."""
    reason = _clean(reason or "").strip()
    if form.status != "received":
        raise OpsError("Only a form that is waiting for review can be rejected.")
    if len(reason) < 10:
        raise OpsError("Write a short reason the partner can act on (at least 10 characters).")
    if len(reason) > 500:
        raise OpsError("Keep the reason under 500 characters.")
    form.status, form.reviewed_at, form.reviewed_by = "rejected", _now(now), actor
    form.reject_reason = reason
    _delete_tax_file(form)
    session.commit()
    return form


def tax_form_view(session, affiliate) -> dict:
    """What the partner sees on Payouts: the form on file and the latest
    upload, with a status label and (if rejected) the reason."""
    T = om.AffiliateTaxForm
    latest = (session.query(T).filter(T.affiliate_id == affiliate.id, T.status != "replaced")
              .order_by(T.uploaded_at.desc(), T.id.desc()).first())
    on_file = affiliate.tax_form_received_at is not None

    def day(v):
        return v.strftime("%d %b %Y").lstrip("0") if v else ""
    out = {"enabled": tax_upload_enabled(), "on_file": on_file,
           "on_file_label": TAX_FORM_LABELS.get(affiliate.tax_form_type, "Tax form") if on_file else None,
           "choices": TAX_FORM_CHOICES, "latest": None,
           "max_mb": int(getattr(config, "TAX_FORM_MAX_BYTES", 5 * 1024 * 1024)) // (1024 * 1024)}
    if latest is not None:
        out["latest"] = {"status": latest.status,
                         "status_label": TAX_STATUS_LABELS.get(latest.status, latest.status),
                         "form_label": TAX_FORM_LABELS.get(latest.form_type, latest.form_type),
                         "uploaded": day(latest.uploaded_at), "reviewed": day(latest.reviewed_at),
                         "reason": latest.reject_reason}
    return out


# ===========================================================================
# 2. Sub-links
# ===========================================================================
MAX_SUBLINKS = 50


def slugify_sub(name) -> str | None:
    s = re.sub(r"[^a-z0-9_-]+", "-", (name or "").strip().lower()).strip("-_")[:40].rstrip("-_")
    return afs.normalize_sub(s)


def sublink_urls(affiliate, sub) -> dict:
    import affiliate_agreement as agr
    base = agr._base()
    return {"join": "%s/join/%s?sub=%s" % (base, affiliate.code, sub),
            "referral": "%s/?code=%s&sub=%s" % (base, affiliate.code, sub)}


def create_sublink(session, affiliate, name, campaign_id=None):
    """Create a named sub-link for this partner. `name` is free text; the URL
    slug is derived from it and is permanent. Commits."""
    S = om.AffiliateSublink
    label = _clean(name or "").strip()
    slug = slugify_sub(label)
    if not slug:
        raise OpsError("Give the link a short name using letters or numbers, such as youtube or march-newsletter.")
    if len(label) > 80 or re.search(r"[<>]|https?://", label, re.I):
        raise OpsError("Keep the name short and plain (no links or markup).")
    if session.query(S).filter(S.affiliate_id == affiliate.id, S.sub == slug).first() is not None:
        raise OpsError("You already have a link named %s." % slug)
    if session.query(S).filter(S.affiliate_id == affiliate.id, S.archived_at.is_(None)).count() >= MAX_SUBLINKS:
        raise OpsError("You have %d links already. Archive one you no longer use first." % MAX_SUBLINKS)
    camp = None
    if campaign_id:
        from models import PromoCampaign
        try:
            camp = session.get(PromoCampaign, uuid.UUID(str(campaign_id)))
        except (ValueError, TypeError):
            camp = None
        if camp is None or camp.status != "active":
            raise OpsError("That promotion is not available.")
    row = S(affiliate_id=affiliate.id, sub=slug, label=label if label.lower() != slug else None,
            campaign_id=camp.id if camp is not None else None)
    session.add(row)
    session.commit()
    return row


def archive_sublink(session, affiliate, sublink_id, restore=False):
    """Hide (or bring back) one of the partner's OWN sub-links. Its numbers
    are kept and visits still count. Commits; returns the row or None."""
    S = om.AffiliateSublink
    try:
        sid = int(sublink_id)
    except (TypeError, ValueError):
        return None
    row = session.query(S).filter(S.id == sid, S.affiliate_id == affiliate.id).first()
    if row is None:
        return None
    row.archived_at = None if restore else _now()
    session.commit()
    return row


def record_sub_click(session, affiliate, raw_sub, cookie_value=None, day=None):
    """+1 the visit counter of the partner's REGISTERED sub-link `raw_sub`,
    unless this browser is already tagged with it (a refresh is not a new
    click). Unknown slugs are ignored, so an anonymous visitor cannot create
    rows. Commits. Returns the slug counted, or None."""
    slug = afs.normalize_sub(raw_sub)
    if slug is None or affiliate is None:
        return None
    if afs.sub_from_cookie(cookie_value, affiliate.code) == slug:
        return None
    S, C = om.AffiliateSublink, om.AffiliateSublinkClick
    row = session.query(S.id).filter(S.affiliate_id == affiliate.id, S.sub == slug).first()
    if row is None:
        return None
    day = day or _now().date()
    tbl = C.__table__
    stmt = afs._dialect_insert(session, tbl).values(sublink_id=row[0], day=day, clicks=1)
    stmt = stmt.on_conflict_do_update(index_elements=["sublink_id", "day"],
                                      set_={"clicks": tbl.c.clicks + 1})
    session.execute(stmt)
    session.commit()
    return slug


def checkout_sub(offer, user, url_sub=None, cookie_value=None):
    """The sub-link slug to stamp on a checkout, or None. Called AFTER the
    partner is resolved (offer["affiliate_code"]); it only ever tags a sale
    that partner already earns: the ?sub= on a link, then the tw_ref_sub
    cookie when it belongs to that partner, then the buyer's signup stamp
    when that signup was the same partner's."""
    code, aff_id = (offer or {}).get("affiliate_code"), (offer or {}).get("affiliate_id")
    if not code or not aff_id:
        return None
    slug = afs.normalize_sub(url_sub) or afs.sub_from_cookie(cookie_value, code)
    if slug is None and user is not None \
            and str(getattr(user, "referred_by_affiliate_id", "") or "") == str(aff_id):
        slug = afs.normalize_sub(getattr(user, "referred_sub", None))
    return slug


def _earned_by_referral(session, affiliate):
    """{referral_id: Decimal earned} over pending / paid / held lines (a
    refund line is negative, so it nets out)."""
    from sqlalchemy import func
    from models import AffiliateCommissionLine as L
    rows = (session.query(L.referral_id, func.sum(L.amount))
            .filter(L.affiliate_id == affiliate.id, L.state.in_(("pending", "paid", "held")),
                    L.currency == "usd")
            .group_by(L.referral_id).all())
    return {rid: Decimal(str(amt or 0)) for rid, amt in rows}


def _cents(amount) -> int:
    return int((Decimal(str(amount or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def link_stats(session, affiliate, include_archived=True) -> dict:
    """Numbers for the Links page:

    sublinks  [{id, sub, label, campaign, archived, urls, clicks, signups,
               paid, earned_cents}] newest first, plus an "untagged" row for
               the plain link / typed code so the columns add up to the
               partner's totals.
    campaigns [{name, clicks, signups, paid, earned_cents, live}] - clicks
               and signups come from the sub-links the partner tied to that
               promotion; paid and earned from the customers who actually
               claimed it.
    Counts only - no customer identities (portal rule)."""
    from sqlalchemy import func
    from models import AffiliateClick, AffiliateReferral, PromoCampaign, User
    S, C = om.AffiliateSublink, om.AffiliateSublinkClick
    subs = (session.query(S).filter(S.affiliate_id == affiliate.id)
            .order_by(S.created_at.desc(), S.id.desc()).all())
    clicks = dict(session.query(C.sublink_id, func.coalesce(func.sum(C.clicks), 0))
                  .filter(C.sublink_id.in_([s.id for s in subs] or [-1]))
                  .group_by(C.sublink_id).all())
    signups = dict(session.query(User.referred_sub, func.count(User.id))
                   .filter(User.referred_by_affiliate_id == affiliate.id,
                           User.referred_sub.isnot(None))
                   .group_by(User.referred_sub).all())
    refs = session.query(AffiliateReferral).filter(AffiliateReferral.affiliate_id == affiliate.id).all()
    earned = _earned_by_referral(session, affiliate)
    campaigns = {c.id: c for c in session.query(PromoCampaign).all()}

    def paid_refs(rows):
        return [r for r in rows if r.first_paid_at is not None and r.source != "return"]

    out, known = [], set()
    for s in subs:
        known.add(s.sub)
        mine = [r for r in refs if r.sub_link == s.sub]
        camp = campaigns.get(s.campaign_id)
        row = {"id": s.id, "sub": s.sub, "label": s.label or s.sub, "archived": s.archived_at is not None,
               "campaign": camp.name if camp is not None else None, "campaign_id": s.campaign_id,
               "urls": sublink_urls(affiliate, s.sub),
               "clicks": int(clicks.get(s.id, 0) or 0), "signups": int(signups.get(s.sub, 0)),
               "paid": len(paid_refs(mine)),
               "earned_cents": _cents(sum((earned.get(r.id, Decimal("0")) for r in mine), Decimal("0")))}
        out.append(row)
    total_clicks = int(session.query(func.coalesce(func.sum(AffiliateClick.clicks), 0))
                       .filter(AffiliateClick.affiliate_id == affiliate.id).scalar() or 0)
    total_signups = (session.query(func.count(User.id))
                     .filter(User.referred_by_affiliate_id == affiliate.id).scalar() or 0)
    rest = [r for r in refs if r.sub_link not in known]
    total_earned = _cents(sum(earned.values(), Decimal("0")))
    untagged = {"clicks": max(0, total_clicks - sum(r["clicks"] for r in out)),
                "signups": max(0, int(total_signups) - sum(r["signups"] for r in out)),
                "paid": len(paid_refs(rest)),
                "earned_cents": total_earned - sum(r["earned_cents"] for r in out)}
    totals = {"clicks": total_clicks, "signups": int(total_signups), "paid": len(paid_refs(refs)),
              "earned_cents": total_earned}

    by_camp = {}
    for r in out:
        if r["campaign_id"] is not None:
            row = by_camp.setdefault(r["campaign_id"], {"clicks": 0, "signups": 0, "paid": 0, "earned": Decimal("0")})
            row["clicks"] += r["clicks"]
            row["signups"] += r["signups"]
    for r in refs:
        if r.campaign_id is not None:
            row = by_camp.setdefault(r.campaign_id, {"clicks": 0, "signups": 0, "paid": 0, "earned": Decimal("0")})
            row["paid"] += 1 if (r.first_paid_at is not None and r.source != "return") else 0
            row["earned"] += earned.get(r.id, Decimal("0"))
    camp_rows = []
    for cid, row in by_camp.items():
        camp = campaigns.get(cid)
        if camp is None:
            continue
        camp_rows.append({"name": camp.name, "live": afs.campaign_is_live(camp),
                          "starts_at": camp.starts_at, "clicks": row["clicks"],
                          "signups": row["signups"], "paid": row["paid"],
                          "earned_cents": _cents(row["earned"])})
    camp_rows.sort(key=lambda r: afs._utc(r["starts_at"]) or _now(), reverse=True)
    if not include_archived:
        out = [r for r in out if not r["archived"]]
    return {"sublinks": out, "untagged": untagged, "totals": totals, "campaigns": camp_rows,
            "live_campaigns": [{"id": str(c.id), "name": c.name} for c in campaigns.values()
                               if afs.campaign_is_live(c)]}


# ===========================================================================
# 3. Bulk payouts (files only - no money moves here)
# ===========================================================================
PAYOUT_REF_PREFIX = "TWP"
_REF_RE = re.compile(r"^TWP0*(\d{1,12})$", re.I)
# Wise batch template header. Wise generates the template per account and
# transfer type; if the file the owner downloads from Wise differs, change
# this one tuple (the columns below map by name).
WISE_COLUMNS = ("name", "recipientEmail", "paymentReference", "receiverType",
                "amountCurrency", "amount", "sourceCurrency", "targetCurrency")
_PAID_WORDS = ("success", "succeeded", "completed", "complete", "paid", "sent",
               "outgoing_payment_sent", "funds_converted", "claimed", "unclaimed")
PAYOUT_METHOD_LABELS = {"paypal": "PayPal", "wise": "Wise"}


def payout_ref(payout_or_id) -> str:
    """Reference id written into the export file and matched on import.
    Alphanumeric only (PayPal's reference-id rule), stable per ledger row."""
    pid = getattr(payout_or_id, "id", payout_or_id)
    return "%s%06d" % (PAYOUT_REF_PREFIX, int(pid))


def _period_label(payout) -> str:
    return payout.period_start.strftime("%b %Y")


def _block_reason(payout, affiliate):
    """Why a pending row cannot be exported / paid, or None. Same gate as the
    Payout Ledger's mark-paid (tax form, negative, minimum) plus payout
    details."""
    import affiliate_admin as afa
    reason = afa.payout_block_reason(payout, affiliate)
    if reason:
        return reason
    if (affiliate.payout_method or "") not in PAYOUT_METHOD_LABELS:
        return "No payout method set for %s (PayPal or Wise)." % affiliate.code
    if not (affiliate.payout_email or "").strip():
        return "No payout email set for %s." % affiliate.code
    if getattr(affiliate, "terminated_for_cause", False):
        return "%s was terminated for cause." % affiliate.code
    return None


def _short_reason(reason) -> str:
    r = (reason or "").lower()
    if "tax form" in r:
        return "No tax form on file"
    if "negative" in r:
        return "Negative, carried"
    if "minimum" in r:
        return "Below minimum, carried"
    if "payout method" in r:
        return "No payout method"
    if "payout email" in r:
        return "No payout email"
    return reason or ""


def pending_payout_rows(session) -> list:
    """Every pending ledger row as a dict, newest period first:
    {id, ref, payout, affiliate, code, name, period, currency, amount,
    method, email, payable, reason, short_reason}."""
    from models import Affiliate, AffiliatePayout
    rows = (session.query(AffiliatePayout, Affiliate)
            .join(Affiliate, Affiliate.id == AffiliatePayout.affiliate_id)
            .filter(AffiliatePayout.status == "pending")
            .order_by(AffiliatePayout.period_start.desc(), Affiliate.code).all())
    out = []
    for p, a in rows:
        reason = _block_reason(p, a)
        out.append({"id": p.id, "ref": payout_ref(p), "payout": p, "affiliate": a, "code": a.code,
                    "name": a.name, "period": _period_label(p), "currency": (p.currency or "usd").lower(),
                    "amount": Decimal(str(p.commission_amount or 0)).quantize(Decimal("0.01")),
                    "method": a.payout_method or "", "email": (a.payout_email or "").strip(),
                    "payable": reason is None, "reason": reason, "short_reason": _short_reason(reason)})
    return out


def payout_groups(rows) -> list:
    """Payable rows grouped by (method, currency) - one export file each -
    as [{method, method_label, currency, rows, total}]."""
    groups = {}
    for r in rows:
        if r["payable"]:
            groups.setdefault((r["method"], r["currency"]), []).append(r)
    return [{"method": m, "method_label": PAYOUT_METHOD_LABELS[m], "currency": c, "rows": rs,
             "total": sum((r["amount"] for r in rs), Decimal("0"))}
            for (m, c), rs in sorted(groups.items())]


def select_for_export(session, ids, method, currency):
    """(rows to export, [(ref, why skipped)]) for the ticked ledger ids. Only
    payable rows of exactly this method and currency are exported."""
    wanted = set()
    for i in ids or []:
        try:
            wanted.add(int(i))
        except (TypeError, ValueError):
            continue
    if method not in PAYOUT_METHOD_LABELS:
        raise OpsError("Unknown payout method.")
    currency = (currency or "").lower()
    chosen, skipped = [], []
    for r in pending_payout_rows(session):
        if r["id"] not in wanted:
            continue
        if not r["payable"]:
            skipped.append((r["ref"], r["short_reason"]))
        elif r["method"] != method or r["currency"] != currency:
            skipped.append((r["ref"], "different method or currency"))
        else:
            chosen.append(r)
    if not chosen:
        raise OpsError("Tick at least one payable row to export.")
    return chosen, skipped


def _csv_text(rows, header=None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    if header:
        w.writerow(header)
    for row in rows:
        # never let a cell start a spreadsheet formula
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "@") else c for c in row])
    return buf.getvalue()


def _note(row) -> str:
    return "TradeWave partner commission %s" % row["period"]


def paypal_csv(rows) -> str:
    """PayPal Payouts (Payouts Web) upload file: one payout per row, NO header
    row, one currency per file, columns in this fixed order:
    recipient email, amount, currency code, reference id, note, recipient wallet."""
    currencies = {r["currency"] for r in rows}
    if len(currencies) > 1:
        raise OpsError("A PayPal payout file can hold one currency only.")
    return _csv_text([[r["email"], "%.2f" % r["amount"], r["currency"].upper(), r["ref"],
                       _note(r), "PAYPAL"] for r in rows])


def wise_csv(rows) -> str:
    """Wise batch-transfer file (header row WISE_COLUMNS): the recipient is
    paid by email, the amount is fixed in the TARGET currency so the partner
    receives exactly what the ledger says."""
    source = getattr(config, "AFFILIATE_WISE_SOURCE_CURRENCY", "USD") or "USD"
    out = []
    for r in rows:
        cells = {"name": r["name"], "recipientEmail": r["email"], "paymentReference": r["ref"],
                 "receiverType": "PERSON", "amountCurrency": "target", "amount": "%.2f" % r["amount"],
                 "sourceCurrency": source, "targetCurrency": r["currency"].upper()}
        out.append([cells[c] for c in WISE_COLUMNS])
    return _csv_text(out, header=WISE_COLUMNS)


def export_filename(method, currency, now=None) -> str:
    return "tradewave-%s-payouts-%s-%s.csv" % (method, currency.lower(), _now(now).strftime("%Y%m%d-%H%M"))


def _find_col(header, names):
    for i, h in enumerate(header):
        if re.sub(r"[^a-z]", "", h.lower()) in names:
            return i
    return None


def parse_paid_batch(text) -> list:
    """Parse a pasted list or an imported CSV of paid rows into
    [{"line", "ref", "payout_id", "reference", "status", "error"}].

    Accepted shapes:
      - our export reference alone:            TWP000123
      - reference + the processor's id:        TWP000123, 5AB12345CD678901E
      - a result file WITH a header row; our reference is read from a column
        named Reference ID / paymentReference / Sender Item ID, the processor
        id from Transaction ID / Payout Item ID / Transfer ID / id, and an
        optional Status column (rows that are not paid are refused)."""
    text = (text or "").lstrip("﻿").strip()
    if not text:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    ref_col = ext_col = status_col = None
    first_line = lines[0]
    delim = "\t" if "\t" in first_line else (";" if ";" in first_line and "," not in first_line else ",")
    first = [c.strip() for c in next(csv.reader([first_line], delimiter=delim))]
    if not any(_REF_RE.match(c) for c in re.split(r"[,;\t\s]+", first_line.strip())):
        ref_col = _find_col(first, ("referenceid", "reference", "paymentreference", "senderitemid",
                                    "customerreference", "ourreference"))
    if ref_col is not None:
        ext_col = _find_col(first, ("transactionid", "payoutitemid", "transferid", "id",
                                    "externalreference", "paymentid", "txnid"))
        status_col = _find_col(first, ("status", "transactionstatus", "state"))
        table = list(csv.reader(lines[1:], delimiter=delim))
    else:
        # a pasted list: each line may use its own separator
        table = []
        for ln in lines:
            d = "\t" if "\t" in ln else (";" if ";" in ln and "," not in ln else ",")
            table.append(next(csv.reader([ln], delimiter=d)))
    out = []
    for n, cells in enumerate(table, start=1):
        cells = [c.strip() for c in cells]
        if ref_col is None and len(cells) == 1 and " " in cells[0]:
            cells = cells[0].split()
        entry = {"line": n, "ref": "", "payout_id": None, "reference": "", "status": "", "error": None}
        if ref_col is not None:
            entry["ref"] = cells[ref_col] if ref_col < len(cells) else ""
            entry["reference"] = cells[ext_col] if ext_col is not None and ext_col < len(cells) else ""
            entry["status"] = cells[status_col] if status_col is not None and status_col < len(cells) else ""
        else:
            hits = [c for c in cells if _REF_RE.match(c)]
            entry["ref"] = hits[0] if hits else (cells[0] if cells else "")
            # the processor's id is the cell right after our reference (or the
            # only other cell); anything else falls back to the batch reference
            others = [c for c in cells if c and not _REF_RE.match(c)]
            at = cells.index(entry["ref"]) if hits else -1
            if hits and len(cells) == 2 and others:
                entry["reference"] = others[0]
            elif hits and at == 0 and len(cells) > 1:
                entry["reference"] = cells[1]
        m = _REF_RE.match(entry["ref"])
        if not m:
            entry["error"] = "No TradeWave reference (like %s) on this line" % payout_ref(123)
        else:
            entry["payout_id"] = int(m.group(1))
            entry["ref"] = payout_ref(entry["payout_id"])
            if entry["status"] and entry["status"].strip().lower() not in _PAID_WORDS:
                entry["error"] = "Not paid according to the file (status %s)" % entry["status"]
        entry["reference"] = entry["reference"][:120]
        out.append(entry)
    return out


def check_paid_batch(session, entries, default_reference="") -> list:
    """Add to each parsed entry what would happen: {"ok", "message", "code",
    "amount", "currency", "period"}. Read-only."""
    from models import Affiliate, AffiliatePayout
    default_reference = (default_reference or "").strip()[:120]
    seen = set()
    for e in entries:
        e.update(ok=False, message=e.get("error") or "", code="", amount=None, currency="", period="")
        if e.get("error"):
            continue
        if e["payout_id"] in seen:
            e["message"] = "Listed twice - the first line is used"
            continue
        seen.add(e["payout_id"])
        p = session.get(AffiliatePayout, e["payout_id"])
        if p is None:
            e["message"] = "No ledger row with this reference"
            continue
        a = session.get(Affiliate, p.affiliate_id)
        e.update(code=a.code, amount=Decimal(str(p.commission_amount or 0)), currency=p.currency,
                 period=_period_label(p))
        e["reference"] = e["reference"] or default_reference
        if p.status == "paid":
            e["message"] = "Already marked paid (%s)" % (p.external_ref or "no reference")
        elif p.status != "pending":
            e["message"] = "Row is %s, not pending" % p.status
        elif not e["reference"]:
            e["message"] = "No payment reference - add one on the line or a batch reference"
        else:
            import affiliate_admin as afa
            reason = afa.payout_block_reason(p, a)
            if reason:
                e["message"] = _short_reason(reason)
            else:
                e["ok"], e["message"] = True, "Will be marked paid"
    return entries


def apply_paid_batch(session, entries, default_reference="", paid_at=None) -> dict:
    """Mark the OK rows paid with their references, then flip their ledger
    lines to paid (same as marking a row paid by hand). Every row goes back
    through the payout gate under a row lock. Records only: no money moves.
    Commits. Returns {"paid": [refs], "refused": [(ref, why)], "lines": n}."""
    from models import Affiliate, AffiliatePayout
    import affiliate_admin as afa
    paid_at = _now(paid_at)
    check_paid_batch(session, entries, default_reference)
    done, refused = [], []
    for e in entries:
        if not e["ok"]:
            refused.append((e["ref"] or "line %d" % e["line"], e["message"]))
            continue
        p = (session.query(AffiliatePayout).filter(AffiliatePayout.id == e["payout_id"])
             .with_for_update().first())
        a = session.get(Affiliate, p.affiliate_id) if p is not None else None
        if p is None or p.status != "pending" or afa.payout_block_reason(p, a):
            refused.append((e["ref"], "Changed since the preview - not marked paid"))
            continue
        p.status, p.paid_at, p.external_ref = "paid", paid_at, e["reference"]
        done.append(e["ref"])
    session.commit()
    lines = afa.sync_paid_lines(session) if done else 0
    return {"paid": done, "refused": refused, "lines": lines}


# ===========================================================================
# 4. Creative library
# ===========================================================================
CREATIVE_URLPATH = "/assets/affiliate-creatives"
CREATIVE_KIND_LABELS = {"banner": "Banner", "logo": "Logo", "email": "Email copy", "social": "Social post"}
CREATIVE_IMAGE_KINDS = ("banner", "logo")
CREATIVE_MAX_BYTES = 5 * 1024 * 1024
CREATIVE_PLACEHOLDERS = ("{link}", "{join_link}", "{code}", "{discount}", "{name}")
_IMAGE_FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"),
                  "WEBP": ("webp", "image/webp"), "GIF": ("gif", "image/gif")}
_FILE_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|webp|gif)$")


def creative_dir() -> Path:
    raw = (getattr(config, "AFFILIATE_CREATIVE_DIR", "") or "").strip()
    return Path(raw) if raw else Path(config.web_root_dir.rstrip("/")) / "assets" / "affiliate-creatives"


def creative_path(row):
    """Absolute path of a creative's image, or None (no file / odd name)."""
    if not row.file_name or not _FILE_RE.match(row.file_name):
        return None
    return creative_dir() / row.file_name


def _campaign_or_none(session, campaign_id):
    if not campaign_id:
        return None
    from models import PromoCampaign
    try:
        camp = session.get(PromoCampaign, uuid.UUID(str(campaign_id)))
    except (ValueError, TypeError):
        camp = None
    if camp is None:
        raise OpsError("That campaign does not exist.")
    return camp


def save_creative(session, *, kind, title, body=None, filename=None, blob=None, campaign_id=None,
                  actor=None, sort_order=0):
    """Add one library item. banner / logo need an image (png, jpg, webp or
    gif, checked by decoding it, 5 MB max); email / social need copy. Commits."""
    title = _clean(title or "").strip()
    body = _clean(body or "").strip() or None
    if kind not in om.CREATIVE_KINDS:
        raise OpsError("Choose what kind of creative this is.")
    if not title or len(title) > 120:
        raise OpsError("Give it a title (120 characters max).")
    camp = _campaign_or_none(session, campaign_id)
    values = dict(kind=kind, title=title, body=body, campaign_id=camp.id if camp else None,
                  status="active", created_by=actor, sort_order=int(sort_order or 0))
    path = None
    if kind in CREATIVE_IMAGE_KINDS:
        if not blob:
            raise OpsError("Choose an image file for a banner or logo.")
        if len(blob) > CREATIVE_MAX_BYTES:
            raise OpsError("Image too large (5 MB max).")
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(blob))
            img.verify()
            fmt = img.format
            width, height = Image.open(io.BytesIO(blob)).size
        except Exception:   # noqa: BLE001 - any decode failure = reject
            raise OpsError("That file is not a supported image (png, jpg, webp or gif).")
        if fmt not in _IMAGE_FORMATS:
            raise OpsError("That file is not a supported image (png, jpg, webp or gif).")
        ext, mime = _IMAGE_FORMATS[fmt]
        name = "%s.%s" % (uuid.uuid4().hex, ext)
        folder = creative_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(blob)
        values.update(file_name=name, original_filename=os.path.basename(filename or "")[:200],
                      mime_type=mime, width=width, height=height, size_bytes=len(blob))
    else:
        if not body:
            raise OpsError("Write the copy partners will use.")
        if len(body) > 6000:
            raise OpsError("Keep the copy under 6,000 characters.")
    try:
        row = om.AffiliateCreative(**values)
        session.add(row)
        session.commit()
    except Exception:
        session.rollback()
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return row


def set_creative_status(session, row, status):
    if status not in om.CREATIVE_STATUSES:
        raise OpsError("Unknown status.")
    row.status = status
    session.commit()
    return row


def delete_creative(session, row) -> None:
    path = creative_path(row)
    session.delete(row)
    session.commit()
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("could not delete creative file %s", path)


def list_creatives(session) -> list:
    C = om.AffiliateCreative
    return session.query(C).order_by(C.status, C.sort_order, C.id.desc()).all()


def fill_copy(body, affiliate, links, discount="") -> str:
    """Replace the placeholders with the partner's own values. Plain string
    replacement (never str.format), so stray braces in the copy are safe."""
    name = (affiliate.page_display_name or affiliate.name or "").strip()
    values = {"{link}": links.get("referral", ""), "{join_link}": links.get("join", ""),
              "{code}": affiliate.code, "{discount}": str(discount or "0"), "{name}": name}
    out = body or ""
    for key, value in values.items():
        out = out.replace(key, value)
    return out


def creatives_for_partner(session, affiliate, links, discount="", now=None) -> dict:
    """Active library items a partner may use right now, filled in:
    {"images": [...], "texts": [...]}. An item tied to a campaign shows only
    while that campaign is live: it disappears by itself when the campaign
    ends (or is paused), and says when that will be while it shows.
    `quotes_discount` marks general copy that states the partner's own
    discount, so the page can warn when a live sale is the better price."""
    import affiliate_agreement as agr
    from markupsafe import escape
    C = om.AffiliateCreative
    base = agr._base()
    images, copy = [], []
    for c in (session.query(C).filter(C.status == "active").order_by(C.sort_order, C.id.desc()).all()):
        camp = c.campaign
        if camp is not None and not afs.campaign_is_live(camp, now):
            continue
        ends = afs._utc(camp.ends_at) if camp is not None and camp.ends_at else None
        item = {"id": c.id, "kind": c.kind, "kind_label": CREATIVE_KIND_LABELS[c.kind], "title": c.title,
                "campaign": camp.name if camp is not None else None,
                "ends": ("%d %s" % (ends.day, ends.strftime("%b"))) if ends else None,
                "quotes_discount": camp is None and "{discount}" in (c.body or "")}
        if c.kind in CREATIVE_IMAGE_KINDS:
            if creative_path(c) is None:
                continue
            public = "%s%s/%s" % (base, CREATIVE_URLPATH, c.file_name)
            item.update(width=c.width, height=c.height, public_url=public,
                        # a wide strip (leaderboard) gets the full row so its text is readable
                        wide=bool(c.width and c.height and c.width >= 3 * c.height),
                        embed='<a href="%s"><img src="%s" alt="%s" width="%s" height="%s"></a>' % (
                            escape(links.get("join", "")), escape(public), escape(c.title),
                            c.width or "", c.height or ""),
                        note=fill_copy(c.body, affiliate, links, discount) if c.body else None)
            images.append(item)
        else:
            item["text"] = fill_copy(c.body, affiliate, links, discount)
            copy.append(item)
    return {"images": images, "texts": copy}
