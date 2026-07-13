"""Affiliate dashboard routes. READ-ONLY against money (no Stripe writes, no
ledger writes - spec A7); the only writes are profile fields, the SMN terms
acceptance, and the take lifecycle, all scoped to the session affiliate."""
import io
import os
import re
import json
import time
import logging
from datetime import datetime, timezone

import requests as _requests
from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import func as safunc

import config
from .blueprint import bp, get_current_affiliate, get_current_user, require_affiliate

log = logging.getLogger("tw2.affiliate_portal")

AFFILIATE_LOGO_DIR = os.path.join(config.web_root_dir.rstrip("/"), "assets", "affiliate-logos")
AFFILIATE_LOGO_URLPATH = "/assets/affiliate-logos"

MODEL_LABELS = {
    "recurring": "Recurring (lifetime)",
    "duration_12mo": "First 12 months",
    "first_payment": "First payment only",
}

SMN_TERMS_PATH = "/home/flask/docs/SMN_CONTRIBUTOR_TERMS.md"
SLUG_RE = re.compile(r"^[a-z0-9-]{2,64}$")
PLAIN_TEXT_BAN = re.compile(r"[<>]|https?://", re.IGNORECASE)

MAX_PHOTO_BYTES = 2 * 1024 * 1024

# In-process caches (single gunicorn worker pool; staleness is acceptable -
# the estimate is labeled, the article list is a picker).
_ESTIMATE_TTL = 3600
_estimate_cache: dict = {}      # {affiliate_id: (monotonic_ts, year, month, rows|None)}
_ARTICLES_TTL = 600
_articles_cache: list = [0.0, None]   # [monotonic_ts, list|None]


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def _db():
    from models import Session as DBSession
    return DBSession()


def _fresh_affiliate(s):
    """Re-fetch the session affiliate inside a live DB session (for writes)."""
    from models import Affiliate
    return s.get(Affiliate, get_current_affiliate().id)


def _smn_profile(s, aff_id):
    from models import AffiliateSmnProfile
    return s.get(AffiliateSmnProfile, aff_id)


def _effective_terms(aff):
    import affiliate_service as asvc
    terms = {
        "split": asvc.is_interval_split(aff),
        "annual_discount": aff.discount_pct,
        "annual_commission": aff.commission_pct,
        "monthly_discount": asvc.effective_discount_pct(aff, "monthly"),
        "monthly_commission": asvc.effective_commission_pct(aff, "monthly"),
        "model_label": MODEL_LABELS.get(aff.commission_model, aff.commission_model),
    }
    return terms


def _links_for(aff):
    import affiliate_agreement as agr
    return {"referral": agr.referral_link(aff), "join": agr.join_link(aff)}


def _month_now():
    now = datetime.now(timezone.utc)
    return now.year, now.month


def _estimate(aff):
    """Cached (~1h) current-month LIVE ESTIMATE via compute_for_affiliate.
    Returns (rows|None, cached_at_iso|None); None rows = unavailable/error."""
    year, month = _month_now()
    hit = _estimate_cache.get(str(aff.id))
    if hit and hit[1] == year and hit[2] == month and (time.monotonic() - hit[0]) < _ESTIMATE_TTL:
        return hit[3], hit[4]
    rows = None
    if aff.status == "active":
        s = _db()
        try:
            import affiliate_service as asvc
            rows = asvc.compute_for_affiliate(s, _fresh_affiliate(s), year, month)
        except Exception as e:   # noqa: BLE001 - estimate is best-effort by design
            log.warning("estimate failed for %s: %s", aff.code, e)
            rows = None
        finally:
            s.close()
    else:
        rows = []   # paused/unsigned affiliates don't accrue (activation gate)
    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    _estimate_cache[str(aff.id)] = (time.monotonic(), year, month, rows, stamp)
    return rows, stamp


def _articles():
    """Recent SMN articles for the take picker. Public posts.json over HTTP
    (topology-independent); local docroot fallback for co-located dev."""
    ts, cached = _articles_cache
    if cached is not None and (time.monotonic() - ts) < _ARTICLES_TTL:
        return cached
    data = None
    base = (config.news_website_url or "").rstrip("/")
    if base:
        try:
            r = _requests.get(base + "/posts.json", timeout=6)
            r.raise_for_status()
            data = r.json()
        except Exception as e:   # noqa: BLE001
            log.warning("posts.json fetch failed from %s: %s", base, e)
    if data is None:
        try:
            with open("/var/www/smn/posts.json") as f:
                data = json.load(f)
        except Exception:
            data = []
    posts = data if isinstance(data, list) else (data.get("posts") or data.get("articles") or [])
    out = []
    for p in posts:
        if not isinstance(p, dict):
            continue
        slug = p.get("slug") or p.get("article_slug")
        if not slug and p.get("url"):
            slug = os.path.basename(str(p["url"]).rstrip("/"))
            slug = slug[:-5] if slug.endswith(".html") else slug
        if not slug or not re.fullmatch(r"[a-zA-Z0-9_-]{1,200}", slug):
            continue
        out.append({
            "slug": slug,
            "title": p.get("title") or slug,
            "symbol": p.get("symbol") or "",
            "published_date": p.get("published_date") or "",
        })
    out = out[:40]
    _articles_cache[0] = time.monotonic()
    _articles_cache[1] = out
    return out


def _article_url(slug):
    base = (config.news_website_url or "").rstrip("/")
    return f"{base}/articles/{slug}.html" if base else f"/articles/{slug}.html"


def _plain_text(value, maxlen, label):
    v = (value or "").strip()
    if not v:
        return None
    if len(v) > maxlen:
        raise ValueError(f"{label} is too long ({maxlen} characters max).")
    if PLAIN_TEXT_BAN.search(v):
        raise ValueError(f"{label} must be plain text (no links or markup).")
    return v


def _notify_operator(subject, body):
    try:
        from email_utils import resend_send_email
        resend_send_email(to=config.SUPPORT_EMAIL_TO, subject=subject, body_text=body)
    except Exception as e:   # noqa: BLE001
        log.warning("affiliate portal notify failed: %s", e)


def _slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:64] if len(s) >= 2 else "expert"


def _ctx(aff, tab, **extra):
    smn_row = None
    s = _db()
    try:
        smn_row = _smn_profile(s, aff.id)
        if smn_row is not None:
            s.expunge(smn_row)
    finally:
        s.close()
    ctx = {"aff": aff, "active_tab": tab, "smn": smn_row}
    ctx.update(extra)
    return ctx


# ------------------------------------------------------------------
# pages
# ------------------------------------------------------------------
@bp.route("/")
@require_affiliate
def overview():
    aff = get_current_affiliate()
    est_rows, est_stamp = _estimate(aff)
    est_total = sum((r["commission_amount"] for r in est_rows), start=0) if est_rows else 0
    s = _db()
    try:
        from models import AffiliatePayout
        paid = (s.query(safunc.coalesce(safunc.sum(AffiliatePayout.commission_amount), 0))
                .filter(AffiliatePayout.affiliate_id == aff.id,
                        AffiliatePayout.status == "paid").scalar())
        pending = (s.query(safunc.coalesce(safunc.sum(AffiliatePayout.commission_amount), 0))
                   .filter(AffiliatePayout.affiliate_id == aff.id,
                           AffiliatePayout.status == "pending").scalar())
    finally:
        s.close()
    return render_template("aff_overview.html", **_ctx(
        aff, "overview", terms=_effective_terms(aff), links=_links_for(aff),
        est_rows=est_rows, est_total=est_total, est_stamp=est_stamp,
        lifetime_paid=paid, pending=pending))


@bp.route("/performance")
@require_affiliate
def performance():
    aff = get_current_affiliate()
    est_rows, est_stamp = _estimate(aff)
    s = _db()
    try:
        from models import AffiliatePayout
        history = (s.query(AffiliatePayout)
                   .filter(AffiliatePayout.affiliate_id == aff.id)
                   .order_by(AffiliatePayout.period_start.desc()).limit(36).all())
        rows = [{
            "period": p.period_start.strftime("%B %Y"),
            "currency": p.currency,
            "gross": p.gross_revenue,
            "commission": p.commission_amount,
            "status": p.status,
            "paid_at": p.paid_at.strftime("%Y-%m-%d") if p.paid_at else None,
            "customers": len((p.detail or {}).get("lines", [])) or None,
        } for p in history]
    finally:
        s.close()
    return render_template("aff_performance.html", **_ctx(
        aff, "performance", history=rows, est_rows=est_rows, est_stamp=est_stamp))


@bp.route("/payouts")
@require_affiliate
def payouts():
    aff = get_current_affiliate()
    s = _db()
    try:
        from models import AffiliatePayout
        rows = (s.query(AffiliatePayout)
                .filter(AffiliatePayout.affiliate_id == aff.id)
                .order_by(AffiliatePayout.period_start.desc()).limit(60).all())
        ledger = [{
            "period": p.period_start.strftime("%B %Y"),
            "currency": p.currency,
            "commission": p.commission_amount,
            "status": p.status,
            "paid_at": p.paid_at.strftime("%Y-%m-%d") if p.paid_at else None,
            "external_ref": p.external_ref,
        } for p in rows]
    finally:
        s.close()
    return render_template("aff_payouts.html", **_ctx(aff, "payouts", ledger=ledger))


@bp.route("/links")
@require_affiliate
def links():
    aff = get_current_affiliate()
    take_links = []
    s = _db()
    try:
        from models import ExpertTake
        prof = _smn_profile(s, aff.id)
        if prof is not None and prof.status == "active":
            takes = (s.query(ExpertTake)
                     .filter(ExpertTake.affiliate_id == aff.id,
                             ExpertTake.status == "published")
                     .order_by(ExpertTake.published_at.desc()).limit(20).all())
            for t in takes:
                take_links.append({
                    "title": t.title or t.article_slug,
                    "url": f"{_article_url(t.article_slug)}?code={aff.code}#expert-{prof.slug}",
                })
    finally:
        s.close()
    return render_template("aff_links.html", **_ctx(
        aff, "links", links=_links_for(aff), take_links=take_links))


# ------------------------------------------------------------------
# profile (join-page fields + photo + SMN expert profile)
# ------------------------------------------------------------------
@bp.route("/profile", methods=["GET", "POST"])
@require_affiliate
def profile():
    aff = get_current_affiliate()
    if request.method == "POST":
        s = _db()
        try:
            live = _fresh_affiliate(s)
            changed = []
            try:
                for field, maxlen, label in (
                        ("page_display_name", 80, "Display name"),
                        ("page_note", 280, "Note"),
                        ("page_signoff", 60, "Sign-off")):
                    new = _plain_text(request.form.get(field), maxlen, label)
                    if new != getattr(live, field):
                        setattr(live, field, new)
                        changed.append(field)
                # --- SMN expert profile fields (participants only) ---
                prof = _smn_profile(s, live.id)
                if prof is not None and prof.status in ("invited", "active"):
                    bio = (request.form.get("bio_md") or "").strip() or None
                    if bio and len(bio) > 4000:
                        raise ValueError("Bio is too long (4000 characters max).")
                    if bio != prof.bio_md:
                        prof.bio_md = bio
                        changed.append("bio")
                    cred = _plain_text(request.form.get("credentials"), 200, "Credentials")
                    if cred != prof.credentials:
                        prof.credentials = cred
                        changed.append("credentials")
                    disc = (request.form.get("disclosure_md") or "").strip() or None
                    if disc and len(disc) > 500:
                        raise ValueError("Disclosure is too long (500 characters max).")
                    if disc != prof.disclosure_md:
                        prof.disclosure_md = disc
                        changed.append("disclosure")
                    links_in = []
                    for i in range(1, 4):
                        lbl = (request.form.get(f"link_label_{i}") or "").strip()
                        url = (request.form.get(f"link_url_{i}") or "").strip()
                        if lbl and url:
                            if not url.startswith("https://") or len(url) > 300 or len(lbl) > 40:
                                raise ValueError("Links must be https:// URLs (labels 40 chars max).")
                            links_in.append({"label": lbl, "url": url})
                    if links_in != (prof.links or []):
                        prof.links = links_in or None
                        changed.append("links")
                    # slug: a STORAGE ID - editable ONLY until the hub is published
                    new_slug = (request.form.get("slug") or "").strip().lower()
                    if new_slug and new_slug != (prof.slug or ""):
                        if prof.published_at is not None:
                            raise ValueError("Your expert URL is locked once published.")
                        if not SLUG_RE.fullmatch(new_slug):
                            raise ValueError("Expert URL may use a-z, 0-9 and dashes (2-64 chars).")
                        from models import AffiliateSmnProfile as ASP
                        taken = (s.query(ASP).filter(ASP.slug == new_slug,
                                                     ASP.affiliate_id != live.id).first())
                        if taken:
                            raise ValueError("That expert URL is already in use.")
                        prof.slug = new_slug
                        changed.append("slug")
            except ValueError as ve:
                s.rollback()
                flash(str(ve), "error")
                return redirect(url_for("affiliate_portal.profile"))
            if changed:
                s.commit()
                g_key = getattr(get_current_affiliate(), "code", "?")
                _notify_operator(
                    "Affiliate profile updated: %s" % g_key,
                    "Affiliate %s updated: %s. Review at /admin (revert there if needed)."
                    % (g_key, ", ".join(changed)))
                flash("Profile updated.", "success")
            else:
                flash("No changes.", "success")
        finally:
            s.close()
        # bust the g-cache so the page re-renders fresh values
        from flask import g as _g
        _g._aff_portal_affiliate = "unset"
        return redirect(url_for("affiliate_portal.profile"))
    return render_template("aff_profile.html", **_ctx(
        aff, "profile", logo_urlpath=AFFILIATE_LOGO_URLPATH))


@bp.route("/profile/photo", methods=["POST"])
@require_affiliate
def profile_photo():
    """Headshot upload (decision 2): jpg/png/webp <=2MB -> validated, resized
    to 512px, EXIF stripped (re-encode), saved as <code>-photo.webp (code is a
    stable id - tw-coding-standards #2). Operator notified. Logo (brand mark)
    stays operator-managed."""
    aff = get_current_affiliate()
    f = request.files.get("photo")
    if f is None or not f.filename:
        flash("Choose an image file first.", "error")
        return redirect(url_for("affiliate_portal.profile"))
    blob = f.read(MAX_PHOTO_BYTES + 1)
    if len(blob) > MAX_PHOTO_BYTES:
        flash("Image too large (2 MB max).", "error")
        return redirect(url_for("affiliate_portal.profile"))
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("format")
        img = img.convert("RGB")
        img.thumbnail((512, 512))
    except Exception:   # noqa: BLE001 - any parse failure = reject
        flash("That file is not a supported image (jpg, png or webp).", "error")
        return redirect(url_for("affiliate_portal.profile"))
    fname = f"{aff.code.lower()}-photo.webp"
    os.makedirs(AFFILIATE_LOGO_DIR, exist_ok=True)
    img.save(os.path.join(AFFILIATE_LOGO_DIR, fname), "WEBP", quality=88)
    s = _db()
    try:
        live = _fresh_affiliate(s)
        live.page_photo = fname
        s.commit()
    finally:
        s.close()
    from flask import g as _g
    _g._aff_portal_affiliate = "unset"
    _notify_operator("Affiliate photo updated: %s" % aff.code,
                     "Affiliate %s uploaded a new headshot (%s)." % (aff.code, fname))
    flash("Photo updated.", "success")
    return redirect(url_for("affiliate_portal.profile"))


# ------------------------------------------------------------------
# SMN expert module (opt-in tab; hidden entirely when no profile row)
# ------------------------------------------------------------------
def _terms_doc():
    """(version, rendered_html) of the contributor terms. OUR OWN authored doc
    (trusted source) - plain markdown render, no bleach needed here."""
    import markdown as _md
    with open(SMN_TERMS_PATH) as fh:
        raw = fh.read()
    m = re.search(r"^Version:\s*(\S+)", raw, re.MULTILINE)
    version = m.group(1) if m else "unversioned"
    return version, _md.markdown(raw, extensions=["tables"])


@bp.route("/smn")
@require_affiliate
def smn():
    aff = get_current_affiliate()
    ctx = _ctx(aff, "smn")
    if ctx["smn"] is None:
        return render_template("aff_not_affiliate.html"), 404   # tab hidden; direct hit = nothing here
    if ctx["smn"].status == "invited":
        version, terms_html = _terms_doc()
        return render_template("aff_smn_invited.html", terms_html=terms_html,
                               terms_version=version, **ctx)
    s = _db()
    try:
        from models import ExpertTake
        takes = (s.query(ExpertTake)
                 .filter(ExpertTake.affiliate_id == aff.id)
                 .order_by(ExpertTake.updated_at.desc()).limit(50).all())
        take_rows = [{
            "id": str(t.id), "article_slug": t.article_slug, "title": t.title,
            "status": t.status, "review_note": t.review_note,
            "published_at": t.published_at.strftime("%Y-%m-%d") if t.published_at else None,
            "url": f"{_article_url(t.article_slug)}?code={aff.code}#expert-{ctx['smn'].slug}"
                   if t.status == "published" else None,
            "declared_call": t.declared_call,
            "execution_result": t.execution_result,
        } for t in takes]
    finally:
        s.close()
    return render_template("aff_smn.html", takes=take_rows, **ctx)


@bp.route("/smn/accept", methods=["POST"])
@require_affiliate
def smn_accept():
    aff = get_current_affiliate()
    if request.form.get("agree") != "yes":
        flash("Tick the agreement box to continue.", "error")
        return redirect(url_for("affiliate_portal.smn"))
    s = _db()
    try:
        prof = _smn_profile(s, aff.id)
        if prof is None or prof.status != "invited":
            flash("Nothing to accept.", "error")
            return redirect(url_for("affiliate_portal.smn"))
        version, terms_html = _terms_doc()
        now = datetime.now(timezone.utc)
        prof.status = "active"
        prof.terms_version = version
        prof.terms_accepted_at = now
        prof.terms_accepted_ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                                  or request.remote_addr or "")[:100]
        prof.terms_accepted_user_agent = (request.headers.get("User-Agent") or "")[:500]
        prof.terms_snapshot = (
            "<h2>Seasonal Market News (SMN) Contributor Terms - accepted copy</h2>"
            f"<p>Accepted by affiliate {aff.code} ({aff.name}) on {now.isoformat()} "
            f"(terms version {version}).</p>" + terms_html)
        if not prof.slug:
            base = _slugify(aff.page_display_name or aff.name)
            slug = base
            from models import AffiliateSmnProfile as ASP
            n = 2
            while s.query(ASP).filter(ASP.slug == slug, ASP.affiliate_id != aff.id).first():
                slug = f"{base}-{n}"
                n += 1
            prof.slug = slug
        from models import AuditLog
        s.add(AuditLog(actor_user_id=get_current_user().id, action="smn_terms_accepted",
                       details={"affiliate_id": str(aff.id), "code": aff.code,
                                "terms_version": version}))
        s.commit()
    finally:
        s.close()
    _notify_operator("SMN contributor terms accepted: %s" % aff.code,
                     "Affiliate %s accepted the SMN contributor terms and can now submit takes."
                     % aff.code)
    flash("Welcome to the Seasonal Market News expert program. You can now write your first take.", "success")
    return redirect(url_for("affiliate_portal.smn"))


@bp.route("/smn/takes/new", methods=["GET", "POST"])
@require_affiliate
def take_new():
    aff = get_current_affiliate()
    ctx = _ctx(aff, "smn")
    if ctx["smn"] is None or ctx["smn"].status != "active":
        return redirect(url_for("affiliate_portal.smn"))
    import expert_takes_service as ets
    edit_id = request.args.get("id") or request.form.get("take_id") or None
    if request.method == "POST":
        s = _db()
        try:
            live = _fresh_affiliate(s)
            call = {
                "symbol": request.form.get("call_symbol"),
                "direction": request.form.get("call_direction"),
                "entry_date": request.form.get("call_entry"),
                "exit_date": request.form.get("call_exit"),
            } if request.form.get("scored_call") == "yes" else None
            try:
                take = ets.upsert_draft(
                    s, live, take_id=edit_id,
                    article_slug=request.form.get("article_slug") or "",
                    title=request.form.get("title"),
                    body_md=request.form.get("body_md") or "",
                    declared_call=call,
                    execution_note=request.form.get("execution_note"))
                s.flush()
                if request.form.get("action") == "submit":
                    ets.submit_take(s, live, take.id)
                    msg = "Take submitted for review."
                else:
                    msg = "Draft saved."
                s.commit()
                flash(msg, "success")
                return redirect(url_for("affiliate_portal.smn"))
            except ets.TakeError as te:
                s.rollback()
                flash(str(te), "error")
        finally:
            s.close()
    take = None
    if edit_id:
        s = _db()
        try:
            from models import ExpertTake
            t = s.get(ExpertTake, edit_id)
            if t is not None and t.affiliate_id == aff.id and t.status in ("draft", "rejected"):
                take = {"id": str(t.id), "article_slug": t.article_slug, "title": t.title,
                        "body_md": t.body_md, "declared_call": t.declared_call or {},
                        "execution_note": t.execution_note, "review_note": t.review_note}
        finally:
            s.close()
    return render_template("aff_take_form.html", articles=_articles(), take=take, **ctx)


@bp.route("/smn/takes/<take_id>/retract", methods=["POST"])
@require_affiliate
def take_retract(take_id):
    aff = get_current_affiliate()
    import expert_takes_service as ets
    s = _db()
    try:
        try:
            ets.retract_take(s, _fresh_affiliate(s), take_id)
            s.commit()
            flash("Take retracted. It will disappear from the article shortly.", "success")
        except ets.TakeError as te:
            s.rollback()
            flash(str(te), "error")
    finally:
        s.close()
    return redirect(url_for("affiliate_portal.smn"))


@bp.route("/smn/takes/<take_id>/result", methods=["POST"])
@require_affiliate
def take_result(take_id):
    aff = get_current_affiliate()
    import expert_takes_service as ets
    s = _db()
    try:
        try:
            ets.set_execution_result(s, _fresh_affiliate(s), take_id,
                                     request.form.get("execution_result") or "")
            s.commit()
            flash("Result recorded (shown as expert-reported).", "success")
        except ets.TakeError as te:
            s.rollback()
            flash(str(te), "error")
    finally:
        s.close()
    return redirect(url_for("affiliate_portal.smn"))
