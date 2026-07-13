"""Expert-take lifecycle for the SMN expert module (docs/AFFILIATE_DASHBOARD_SPEC.md).

The SINGLE sanitation authority for affiliate-authored content: everything that
can reach a public page goes markdown -> bleach here (the SMN box bleaches
again on inject - defense in depth, see smn/expert_sync.py). Affiliates are
semi-trusted: hand-picked, under signed terms - but their input never reaches
HTML unbleached.

State machine (statuses are STORAGE IDs, models.EXPERT_TAKE_STATUSES):
    draft -> submitted -> published (approve stamps rendered_html)
                     \\-> rejected (with review_note, back to the affiliate)
    published -> retracted (affiliate or operator; SMN removes on next pull)
'approved' stays in the CHECK for a future scheduled-publish step; today
approve == publish (one operator action, no second hop).
"""
import re
import logging
from datetime import datetime, timezone

import bleach
import markdown as _markdown

import config
from models import ExpertTake, Affiliate, AffiliateSmnProfile, AuditLog

log = logging.getLogger("tw2.expert_takes")

# Tight allowlist: commentary formatting only. No images, no headings above h4,
# no tables (takes are 150-300 word reactions, not documents).
ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "blockquote", "a", "code", "h4", "h5"]
ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}
ALLOWED_PROTOCOLS = ["https"]

ARTICLE_SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,200}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,12}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SUBMISSIONS_PER_DAY = 10  # modest abuse bound (spec 4.8)


class TakeError(Exception):
    """Raised for any invalid transition/input; message is user-safe."""


def _now():
    return datetime.now(timezone.utc)


def render_markdown(md_text: str) -> str:
    """Markdown -> sanitized HTML. https links only; rel added by linkify pass."""
    raw = _markdown.markdown(md_text or "", extensions=["nl2br"], output_format="html")
    cleaned = bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS,
                           protocols=ALLOWED_PROTOCOLS, strip=True)
    # rel=nofollow+noopener on every link (bleach.linkify handles existing <a>).
    return bleach.linkify(cleaned, callbacks=[
        lambda attrs, new=False: {**attrs, (None, "rel"): "nofollow noopener"},
    ], skip_tags=["code"], parse_email=False)


def validate_declared_call(call: dict | None) -> dict | None:
    """Normalize/validate the optional scored directional thesis (Layer 1)."""
    if not call:
        return None
    symbol = (call.get("symbol") or "").strip().upper()
    direction = (call.get("direction") or "").strip().lower()
    entry = (call.get("entry_date") or "").strip()
    exit_ = (call.get("exit_date") or "").strip()
    if not symbol and not direction and not entry and not exit_:
        return None
    if not SYMBOL_RE.fullmatch(symbol):
        raise TakeError("Scored call: symbol must be 1-12 chars A-Z 0-9 . -")
    if direction not in ("long", "short"):
        raise TakeError("Scored call: direction must be long or short")
    if not (DATE_RE.fullmatch(entry) and DATE_RE.fullmatch(exit_)):
        raise TakeError("Scored call: entry/exit dates must be YYYY-MM-DD")
    if exit_ <= entry:
        raise TakeError("Scored call: exit date must be after entry date")
    return {"symbol": symbol, "direction": direction, "entry_date": entry, "exit_date": exit_}


def _require_active_smn(session, affiliate: Affiliate) -> AffiliateSmnProfile:
    prof = session.get(AffiliateSmnProfile, affiliate.id)
    if prof is None or prof.status != "active":
        raise TakeError("SMN participation is not active on this account.")
    return prof


def _own_take(session, affiliate: Affiliate, take_id) -> ExpertTake:
    take = session.get(ExpertTake, take_id)
    if take is None or take.affiliate_id != affiliate.id:
        raise TakeError("Take not found.")   # no existence oracle across affiliates
    return take


def upsert_draft(session, affiliate: Affiliate, *, take_id=None, article_slug: str,
                 title: str | None, body_md: str, declared_call: dict | None,
                 execution_note: str | None) -> ExpertTake:
    _require_active_smn(session, affiliate)
    if not ARTICLE_SLUG_RE.fullmatch(article_slug or ""):
        raise TakeError("Invalid article.")
    body_md = (body_md or "").strip()
    if not body_md:
        raise TakeError("The take body is empty.")
    if len(body_md) > 8000:
        raise TakeError("The take is too long (8000 chars max).")
    title = (title or "").strip() or None
    if title and len(title) > 120:
        raise TakeError("Title too long (120 chars max).")
    execution_note = (execution_note or "").strip() or None
    if execution_note and len(execution_note) > 500:
        raise TakeError("Trade structure note too long (500 chars max).")
    call = validate_declared_call(declared_call)

    if take_id:
        take = _own_take(session, affiliate, take_id)
        if take.status not in ("draft", "rejected"):
            raise TakeError("Only drafts and rejected takes can be edited.")
        take.status = "draft"
    else:
        take = ExpertTake(affiliate_id=affiliate.id)
        session.add(take)
    take.article_slug = article_slug
    take.title = title
    take.body_md = body_md
    take.declared_call = call
    take.execution_note = execution_note
    take.updated_at = _now()
    return take


def submit_take(session, affiliate: Affiliate, take_id) -> ExpertTake:
    _require_active_smn(session, affiliate)
    take = _own_take(session, affiliate, take_id)
    if take.status not in ("draft", "rejected"):
        raise TakeError("Only drafts can be submitted.")
    # Abuse bound: SUBMISSIONS_PER_DAY per affiliate (spec 4.8).
    midnight = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    n_today = (session.query(ExpertTake)
               .filter(ExpertTake.affiliate_id == affiliate.id,
                       ExpertTake.updated_at >= midnight,
                       ExpertTake.status.in_(("submitted", "published"))).count())
    if n_today >= SUBMISSIONS_PER_DAY:
        raise TakeError("Daily submission limit reached - try again tomorrow.")
    take.status = "submitted"
    take.review_note = None
    take.updated_at = _now()
    _audit(session, None, "take_submitted", take)
    _notify_operator(
        "SMN take submitted for review",
        f"Affiliate {affiliate.code} submitted a take on article "
        f"'{take.article_slug}'. Review it in Admin -> Affiliates -> Expert Takes.")
    return take


def retract_take(session, affiliate: Affiliate, take_id) -> ExpertTake:
    _require_active_smn(session, affiliate)
    take = _own_take(session, affiliate, take_id)
    if take.status == "published":
        take.status = "retracted"
        take.retracted_at = _now()
        _audit(session, None, "take_retracted", take)
    elif take.status in ("draft", "submitted", "rejected"):
        session.delete(take)   # never published: no public trace to keep
    else:
        raise TakeError("This take cannot be retracted.")
    return take


def set_execution_result(session, affiliate: Affiliate, take_id, result_text: str) -> ExpertTake:
    """Expert-reported Layer 2 outcome, allowed only on the affiliate's own
    PUBLISHED takes; audit-logged; rendered clearly labeled + separate from the
    house-verified record."""
    _require_active_smn(session, affiliate)
    take = _own_take(session, affiliate, take_id)
    if take.status != "published":
        raise TakeError("Results can only be reported on published takes.")
    result_text = (result_text or "").strip()
    if not result_text or len(result_text) > 300:
        raise TakeError("Result must be 1-300 characters.")
    take.execution_result = result_text
    take.execution_result_at = _now()
    take.updated_at = _now()
    _audit(session, None, "take_execution_result", take)
    return take


# ---- operator side (called from Flask-Admin actions) ----

def approve_and_publish(session, take: ExpertTake, reviewer_user) -> ExpertTake:
    if take.status != "submitted":
        raise TakeError("Only submitted takes can be approved.")
    take.rendered_html = render_markdown(take.body_md)
    take.status = "published"
    take.published_at = _now()
    take.reviewed_by = getattr(reviewer_user, "id", None)
    take.updated_at = _now()
    _audit(session, reviewer_user, "take_published", take)
    return take


def reject_take(session, take: ExpertTake, reviewer_user, note: str | None) -> ExpertTake:
    if take.status != "submitted":
        raise TakeError("Only submitted takes can be rejected.")
    take.status = "rejected"
    take.review_note = (note or "").strip() or None
    take.reviewed_by = getattr(reviewer_user, "id", None)
    take.updated_at = _now()
    _audit(session, reviewer_user, "take_rejected", take)
    return take


def operator_retract(session, take: ExpertTake, reviewer_user) -> ExpertTake:
    if take.status != "published":
        raise TakeError("Only published takes can be retracted.")
    take.status = "retracted"
    take.retracted_at = _now()
    take.reviewed_by = getattr(reviewer_user, "id", None)
    take.updated_at = _now()
    _audit(session, reviewer_user, "take_retracted_by_operator", take)
    return take


# ---- internal-endpoint payloads (pulled by the SMN box, X-Service-Key) ----

def _take_payload(take: ExpertTake, prof: AffiliateSmnProfile | None, aff: Affiliate) -> dict:
    return {
        "id": str(take.id),
        "article_slug": take.article_slug,
        "status": take.status,          # 'published' | 'retracted'
        "title": take.title,
        "rendered_html": take.rendered_html,
        "declared_call": take.declared_call,
        "execution_note": take.execution_note,
        "execution_result": take.execution_result,
        "published_at": take.published_at.isoformat() if take.published_at else None,
        "retracted_at": take.retracted_at.isoformat() if take.retracted_at else None,
        "updated_at": take.updated_at.isoformat() if take.updated_at else None,
        "expert": {
            "slug": prof.slug if prof else None,
            "display_name": aff.page_display_name or aff.name,
            "code": aff.code,
            "credentials": prof.credentials if prof else None,
            "photo": aff.page_photo,     # filename under /assets/affiliate-logos/ on tradewave.ai
            "disclosure_html": render_markdown(prof.disclosure_md) if prof and prof.disclosure_md else None,
        },
    }


def takes_since(session, since: datetime | None, limit: int = 200) -> list[dict]:
    """Published + retracted takes changed since the cursor, oldest first.
    Retracted rows ride the same feed so the SMN box removes their blocks."""
    q = (session.query(ExpertTake)
         .filter(ExpertTake.status.in_(("published", "retracted"))))
    if since is not None:
        q = q.filter(ExpertTake.updated_at > since)
    rows = q.order_by(ExpertTake.updated_at.asc()).limit(limit).all()
    out = []
    for t in rows:
        aff = session.get(Affiliate, t.affiliate_id)
        prof = session.get(AffiliateSmnProfile, t.affiliate_id)
        out.append(_take_payload(t, prof, aff))
    return out


def profiles_since(session, since: datetime | None, limit: int = 100) -> list[dict]:
    """Active expert profiles changed since the cursor (for hub pages)."""
    q = session.query(AffiliateSmnProfile).filter(AffiliateSmnProfile.status == "active")
    if since is not None:
        q = q.filter(AffiliateSmnProfile.updated_at > since)
    rows = q.order_by(AffiliateSmnProfile.updated_at.asc()).limit(limit).all()
    out = []
    for p in rows:
        aff = session.get(Affiliate, p.affiliate_id)
        out.append({
            "slug": p.slug,
            "display_name": aff.page_display_name or aff.name,
            "code": aff.code,
            "credentials": p.credentials,
            "photo": aff.page_photo,
            "bio_html": render_markdown(p.bio_md) if p.bio_md else None,
            "disclosure_html": render_markdown(p.disclosure_md) if p.disclosure_md else None,
            "links": [l for l in (p.links or [])
                      if isinstance(l, dict) and str(l.get("url", "")).startswith("https://")],
            "scorecard_enabled": bool(p.scorecard_enabled),
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })
    return out


# ---- plumbing ----

def _audit(session, actor_user, action: str, take: ExpertTake):
    session.add(AuditLog(
        actor_user_id=getattr(actor_user, "id", None),
        actor_label="affiliate_portal" if actor_user is None else None,
        action=action,
        details={"take_id": str(take.id) if take.id else None,
                 "article_slug": take.article_slug,
                 "affiliate_id": str(take.affiliate_id)},
    ))


def _notify_operator(subject: str, body: str):
    """Best-effort operator email (same posture as agreement mails)."""
    try:
        from email_utils import resend_send_email
        resend_send_email(to=config.SUPPORT_EMAIL_TO, subject=subject, body_text=body)
    except Exception as e:   # noqa: BLE001 - notification must never block the flow
        log.warning("expert_takes notify failed: %s", e)
