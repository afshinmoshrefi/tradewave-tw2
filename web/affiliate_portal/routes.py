"""Affiliate dashboard routes (program v2 layout: Home, Earnings, Customers,
Links, Promote, Payouts, Settings, plus the invite-only Expert Desk).

READ-ONLY against the ledger (no ledger writes - spec A7). The writes are:
profile fields, the SMN terms acceptance, the take lifecycle and - new in v2 -
the partner's own customer discount (affiliate_service.set_partner_discount,
which re-points the partner's Stripe coupon). All are scoped to the session
affiliate. Page data is built in dashboard.py; commission math stays in
affiliate_service."""
import io
import os
import re
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests as _requests
from flask import Response, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func as safunc

import config
from .blueprint import bp, get_current_affiliate, get_current_user, require_affiliate
from . import blueprint as _bpmod
from . import dashboard as dash
from . import qr as _qr

log = logging.getLogger("tw2.affiliate_portal")

AFFILIATE_LOGO_DIR = os.path.join(config.web_root_dir.rstrip("/"), "assets", "affiliate-logos")
AFFILIATE_LOGO_URLPATH = "/assets/affiliate-logos"

GUIDE_PATH = str(Path(__file__).resolve().parents[2] / "docs" / "AFFILIATE_PARTNER_GUIDE.md")
SMN_TERMS_PATH = str(Path(__file__).resolve().parents[2] / "docs" / "SMN_CONTRIBUTOR_TERMS.md")
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


def _links_for(aff):
    import affiliate_agreement as agr
    return {"referral": agr.referral_link(aff), "join": agr.join_link(aff)}


def _month_now():
    now = datetime.now(timezone.utc)
    return now.year, now.month


def _est_redis():
    """Shared cache across gunicorn workers (same local Redis db the session
    memo uses). None if Redis is unavailable -> in-process fallback."""
    try:
        import redis as _redis
        r = _redis.Redis(host="127.0.0.1", port=6379, db=5, socket_timeout=0.25,
                         socket_connect_timeout=0.25, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


def _rows_to_json(rows):
    out = []
    for r in rows:
        out.append({"currency": r["currency"],
                    "gross_revenue": str(r["gross_revenue"]),
                    "commission_amount": str(r["commission_amount"]),
                    "held_amount": str(r.get("held_amount") or "0"),
                    "lapsed": int(r.get("lapsed_count") or 0),
                    "payments": _count_kind(r.get("detail"), "payment"),
                    "reversals": sum(1 for ln in (r.get("detail") or [])
                                     if (ln.get("kind") or "") in ("refund", "dispute")),
                    "customers": _customer_count(r.get("detail"))})
    return out


def _rows_from_json(items):
    from decimal import Decimal
    return [dict(it, gross_revenue=Decimal(it["gross_revenue"]),
                 commission_amount=Decimal(it["commission_amount"]),
                 held_amount=Decimal(it.get("held_amount") or "0")) for it in items]


def _count_kind(detail, kind):
    """Lines of a kind. 'payment' counts every SALE line: the legacy 'payment'
    plus the program-v2 kinds first_year / promo / renewal."""
    if kind == "payment":
        import affiliate_service as asvc
        return sum(1 for ln in (detail or []) if asvc.is_payment_line(ln))
    return sum(1 for ln in (detail or []) if (ln.get("kind") or "payment") == kind)


def _customer_count(detail):
    """DISTINCT paying customers among payment lines (never identities)."""
    import affiliate_service as asvc
    custs = {ln.get("customer") for ln in (detail or [])
             if asvc.is_payment_line(ln) and ln.get("customer")}
    return len(custs)


# Engine line fields the Earnings ledger needs. Whitelisted before caching so
# nothing else from a Stripe invoice (never an email) rides along.
_LINE_KEYS = ("kind", "state", "hold_reason", "source_id", "customer", "subscription",
              "referral_id", "currency", "interval", "event_at", "year_number",
              "net_paid_cents", "basis_cents", "reverses_kind", "rate_pct", "amount",
              "period_month", "persisted")


def _lines_to_json(rows):
    out = []
    for r in rows:
        for ln in (r.get("detail") or []):
            out.append({k: ln.get(k) for k in _LINE_KEYS if ln.get(k) is not None})
    return out


def _estimate_full(aff):
    """Cached (~1h) current-month LIVE ESTIMATE via compute_for_affiliate.
    Shared across gunicorn workers via Redis (falls back to in-process), so
    each affiliate costs at most one Stripe walk per hour.

    Returns {"rows": summary rows | None, "lines": engine lines, "stamp"}.
    rows None = unavailable/error. A PAUSED partner is computed too: their
    lines come back HELD (rows carry held_amount) because commissions keep
    adding up during a pause and are paid when the account is unpaused."""
    year, month = _month_now()
    key = "tw2:aff_est2:%s:%04d-%02d" % (aff.id, year, month)
    rc = _est_redis()
    if rc is not None:
        try:
            hit = rc.get(key)
            if hit:
                payload = json.loads(hit)
                return {"rows": _rows_from_json(payload["rows"]),
                        "lines": payload.get("lines") or [], "stamp": payload["stamp"]}
        except Exception:
            pass
    else:
        hit = _estimate_cache.get(str(aff.id))
        if hit and hit[1] == year and hit[2] == month and (time.monotonic() - hit[0]) < _ESTIMATE_TTL:
            return {"rows": hit[3], "stamp": hit[4], "lines": hit[5]}
    rows = lines = None
    s = _db()
    try:
        import affiliate_service as asvc
        computed = asvc.compute_for_affiliate(s, _fresh_affiliate(s), year, month)
        rows, lines = _rows_to_json(computed), _lines_to_json(computed)
    except Exception as e:   # noqa: BLE001 - estimate is best-effort by design
        log.warning("estimate failed for %s: %s", aff.code, e)
        rows = None
    finally:
        s.close()
    stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
    if rows is None:
        return {"rows": None, "lines": [], "stamp": stamp}      # don't cache failures
    if rc is not None:
        try:
            rc.setex(key, _ESTIMATE_TTL, json.dumps({"rows": rows, "lines": lines, "stamp": stamp}))
        except Exception:
            pass
    rows = _rows_from_json(rows)
    _estimate_cache[str(aff.id)] = (time.monotonic(), year, month, rows, stamp, lines)
    return {"rows": rows, "lines": lines, "stamp": stamp}


def _estimate(aff):
    """(rows|None, stamp) - the summary half of _estimate_full."""
    est = _estimate_full(aff)
    return est["rows"], est["stamp"]


_CATALOG_TTL = 600
_catalog_cache: list = [0.0, None]


def _catalog():
    """{(tier, 'month'|'year'): {"list_price_cents", ...}} - the parent app's
    Stripe price catalog (app._campaign_catalog), injected via
    blueprint.set_catalog_loader or found on the module that created the
    Flask app. {} when prices are unavailable: pages then hide dollar tables
    instead of failing."""
    ts, cached = _catalog_cache
    if cached and (time.monotonic() - ts) < _CATALOG_TTL:
        return cached
    loader = _bpmod.get_catalog_loader()
    if loader is None:
        import sys
        mod = sys.modules.get(current_app.import_name)
        loader = getattr(mod, "_campaign_catalog", None)
    if loader is None:
        return {}
    try:
        cat = loader() or {}
    except Exception as e:   # noqa: BLE001 - prices are best-effort on a dashboard
        log.warning("price catalog unavailable: %s", e)
        return {}
    if cat:
        _catalog_cache[0] = time.monotonic()
        _catalog_cache[1] = cat
    return cat


def _ledger_totals(s, aff_id, status):
    """{currency: Decimal} sum of ledger rows with `status` - never summed
    across currencies."""
    from models import AffiliatePayout
    q = (s.query(AffiliatePayout.currency,
                 safunc.coalesce(safunc.sum(AffiliatePayout.commission_amount), 0))
         .filter(AffiliatePayout.affiliate_id == aff_id, AffiliatePayout.status == status)
         .group_by(AffiliatePayout.currency))
    return {c: amt for c, amt in q.all()}


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
    # A 0% discount has no Stripe coupon, so there is no typed checkout code
    # (links still track).
    try:
        has_code = float(aff.discount_pct or 0) > 0
    except (TypeError, ValueError):
        has_code = False
    ctx = {"aff": aff, "active_tab": tab, "smn": smn_row, "links": _links_for(aff),
           "has_code": has_code,
           # why Copy buttons are disabled (unsigned / paused), or None
           "link_block": dash.link_block(aff)}
    ctx.update(extra)
    return ctx


@bp.app_template_filter("aff_money")
def _f_money(amount, currency="usd"):
    return dash.fmt_money(amount, currency)


@bp.app_template_filter("aff_cents")
def _f_cents(cents, currency="usd"):
    return dash.fmt_cents(cents, currency)


@bp.app_template_filter("aff_price")
def _f_price(cents, currency="usd"):
    return dash.fmt_price(cents, currency)


@bp.app_template_filter("aff_sale_end")
def _f_sale_end(value):
    """Campaign ends_at (UTC ISO string or datetime) -> '30 Nov, 11:59 pm ET'.
    Used by the public /join page, so a sale deadline always carries a time
    and a zone. '' when the value cannot be read."""
    return dash.fmt_sale_end(value)


def _csv_response(text, filename):
    return Response(text, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="%s"' % filename,
                             "Cache-Control": "private, no-store"})


def _est_money(est_rows):
    """[(currency, payable Decimal, held Decimal)] from estimate rows."""
    return sorted((r["currency"], r["commission_amount"], r.get("held_amount") or 0)
                  for r in (est_rows or []))


# ------------------------------------------------------------------
# pages
# ------------------------------------------------------------------
def _page_data(aff, s, *, want_catalog=True):
    """What most pages need, built once inside a live DB session: the fresh
    affiliate row, its terms, the price catalog, the cached estimate, the
    full line ledger and the activity card."""
    import affiliate_service as asvc
    live = _fresh_affiliate(s)
    terms = asvc.terms_for(s, live)
    est = _estimate_full(aff)
    lines = dash.ledger(s, live, est["lines"])
    return {
        "live": live, "terms": terms, "est": est, "lines": lines,
        "catalog": _catalog() if want_catalog else {},
        "activity": dash.activity_card(live, s, terms),
        "offer": dash.offer_summary(live, terms),
    }


@bp.route("/")
@require_affiliate
def overview():
    aff = get_current_affiliate()
    s = _db()
    try:
        d = _page_data(aff, s)
        live, terms, catalog = d["live"], d["terms"], d["catalog"]
        pending, paid = dash.payout_totals(s, live)
        funnel = dash.funnel(s, live, d["lines"], request.args.get("range") or "30d")
        custs = dash.customers(s, live, catalog, terms, d["lines"], d["activity"]["status"])
        promos = dash.promotions(s, live, catalog, terms)
        plans = dash.plan_table(catalog, live, terms, promos) if catalog else []
        usd = dash.ledger_totals(d["lines"]).get("usd") or {}
        has_paying = any(c["status"] != "trial" for c in custs)
        has_activity = bool(custs or d["lines"] or pending or paid
                            or dash.funnel(s, live, [], "all")["clicks"])
        ctx = _ctx(
            aff, "home",
            held_usd=usd.get("held") or 0,
            welcome_back=dash.welcome_back(live, get_current_user(), has_activity),
            steps=dash.getting_started(plans, d["offer"], has_paying),
            est_rows=d["est"]["rows"], est_stamp=d["est"]["stamp"], est_money=_est_money(d["est"]["rows"]),
            pending=sorted(pending.items()), lifetime_paid=sorted(paid.items()),
            active_customers=sum(1 for c in custs if c["status"] == "paying"),
            total_customers=len(custs),
            funnel=funnel, activity=d["activity"], offer=d["offer"],
            plans=plans, promos=promos,
            forecast=dash.forecast(s, live, catalog, terms),
            actions=dash.action_items(live, d["activity"], {
                "payouts": url_for("affiliate_portal.payouts"),
                "links": url_for("affiliate_portal.links"),
                "resend": url_for("affiliate_portal.agreement_resend")}))
    finally:
        s.close()
    return render_template("aff_overview.html", **ctx)


@bp.route("/performance")
@require_affiliate
def performance():
    """Old URL: Performance is folded into Home (funnel) and Earnings."""
    return redirect(url_for("affiliate_portal.earnings"))


_EARNINGS_RANGES = {"30d": 30, "90d": 90, "12m": 365}
_EARNINGS_PAGE = 200


def _earnings_lines(aff, s):
    d = _page_data(aff, s, want_catalog=False)
    state = request.args.get("state") or ""
    kind = request.args.get("type") or ""
    rng = request.args.get("range") or ""
    lines = dash.filter_ledger(d["lines"], state=state, kind=kind,
                               days=_EARNINGS_RANGES.get(rng))
    return d, lines, {"state": state, "type": kind, "range": rng}


@bp.route("/earnings")
@require_affiliate
def earnings():
    aff = get_current_affiliate()
    s = _db()
    try:
        d, lines, filters = _earnings_lines(aff, s)
        ctx = _ctx(
            aff, "earnings", lines=lines[:_EARNINGS_PAGE], line_count=len(lines),
            months=dash.ledger_by_month(lines[:_EARNINGS_PAGE]),
            truncated=len(lines) > _EARNINGS_PAGE,
            totals=sorted(dash.ledger_totals(lines).items()),
            all_totals=sorted(dash.ledger_totals(d["lines"]).items()),
            has_any=bool(d["lines"]), filters=filters,
            est_rows=d["est"]["rows"], est_stamp=d["est"]["stamp"],
            est_money=_est_money(d["est"]["rows"]), activity=d["activity"],
            state_options=[("estimated", "Estimated"), ("pending", "Pending"), ("paid", "Paid"),
                           ("held", "Held"), ("lapsed", "Lapsed")],
            type_options=[("first_year", "First year"), ("promo", "Promotion"),
                          ("renewal", "Renewal"), ("refund", "Refund adjustment"),
                          ("lapsed", "Lapsed")],
            range_options=[("", "All time"), ("30d", "Last 30 days"), ("90d", "Last 90 days"),
                           ("12m", "Last 12 months")])
    finally:
        s.close()
    return render_template("aff_earnings.html", **ctx)


@bp.route("/earnings.csv")
@require_affiliate
def earnings_csv():
    aff = get_current_affiliate()
    s = _db()
    try:
        _d, lines, _f = _earnings_lines(aff, s)
        body = dash.ledger_csv(lines)
    finally:
        s.close()
    return _csv_response(body, "tradewave-earnings-%s.csv" % aff.code)


def _customer_rows(aff, s):
    d = _page_data(aff, s)
    rows = dash.customers(s, d["live"], d["catalog"], d["terms"], d["lines"],
                          d["activity"]["status"])
    filters = {"status": request.args.get("status") or "",
               "plan": request.args.get("plan") or "",
               "source": request.args.get("source") or ""}
    shown = dash.filter_customers(rows, status=filters["status"], interval=filters["plan"],
                                  source=filters["source"])
    return d, rows, shown, filters


@bp.route("/customers")
@require_affiliate
def customers():
    aff = get_current_affiliate()
    s = _db()
    try:
        d, rows, shown, filters = _customer_rows(aff, s)
        ctx = _ctx(
            aff, "customers", rows=shown[:500], row_count=len(shown), has_any=bool(rows),
            filters=filters, activity=d["activity"],
            counts={k: sum(1 for r in rows if r["status"] == k) for k in dash.STATUS_LABELS},
            status_options=list(dash.STATUS_LABELS.items()),
            plan_options=list(dash.INTERVAL_LABELS.items()),
            source_options=list(dash.SOURCE_LABELS.items()))
    finally:
        s.close()
    return render_template("aff_customers.html", **ctx)


@bp.route("/customers.csv")
@require_affiliate
def customers_csv():
    aff = get_current_affiliate()
    s = _db()
    try:
        _d, _rows, shown, _f = _customer_rows(aff, s)
        body = dash.customers_csv(shown)
    finally:
        s.close()
    return _csv_response(body, "tradewave-customers-%s.csv" % aff.code)


@bp.route("/payouts")
@require_affiliate
def payouts():
    aff = get_current_affiliate()
    s = _db()
    try:
        live = _fresh_affiliate(s)
        ledger = dash.payout_history(s, live)
        pending, paid = dash.payout_totals(s, live)
        est = _estimate_full(aff)
        held = sum(int(r.get("held_amount", 0) * 100) for r in (est["rows"] or [])
                   if r["currency"] == "usd")
        ctx = _ctx(aff, "payouts", ledger=ledger,
                   checklist=dash.payout_checklist(live, pending, held_cents=held),
                   pending=sorted(pending.items()), lifetime_paid=sorted(paid.items()))
    finally:
        s.close()
    return render_template("aff_payouts.html", **ctx)


# ------------------------------------------------------------------
# links: referral link, join link, code, link builder, QR
# ------------------------------------------------------------------
def _site_base():
    import affiliate_agreement as agr
    return agr._base()


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
        aff, "links", take_links=take_links, site_base=_site_base(),
        destinations=[("join", "Your join page", "/join/%s" % aff.code),
                      ("home", "Home page", "/"),
                      ("pricing", "Pricing", "/pricing"),
                      ("custom", "Another page on tradewave.ai", "")]))


@bp.route("/qr.svg")
@require_affiliate
def qr_svg():
    """QR code (SVG) for one of the partner's OWN tracked links: the URL must
    be on this site and carry the partner's code, so this is not an open QR
    generator. ?download=1 sends it as a file."""
    aff = get_current_affiliate()
    url = (request.args.get("u") or "").strip()
    base = _site_base()
    code = aff.code
    on_site = url.startswith(base + "/") and not PLAIN_TEXT_BAN.search(url[len(base):])
    tracked = ("/join/%s" % code) in url or ("code=%s" % code) in url
    if not on_site or not tracked or len(url) > 320:
        return Response("Not a tracked link for this account.", status=400, mimetype="text/plain")
    try:
        body = _qr.svg(url, scale=8, border=4)
    except ValueError:
        return Response("That link is too long for a QR code.", status=400, mimetype="text/plain")
    headers = {"Cache-Control": "private, max-age=3600"}
    if request.args.get("download"):
        headers["Content-Disposition"] = 'attachment; filename="tradewave-%s-qr.svg"' % code
    return Response(body, mimetype="image/svg+xml", headers=headers)


# ------------------------------------------------------------------
# promote: swipe copy, AI guide, join-page editor
# ------------------------------------------------------------------
@bp.route("/promote")
@require_affiliate
def promote():
    aff = get_current_affiliate()
    s = _db()
    try:
        import affiliate_service as asvc
        live = _fresh_affiliate(s)
        terms = asvc.terms_for(s, live)
        offer = dash.offer_summary(live, terms)
        catalog = _catalog()
        promos = dash.promotions(s, live, catalog, terms)
        ai_md = _guide_for(live, terms)
    finally:
        s.close()
    links = _links_for(aff)
    html = _render_guide(_guide_md().replace("`ANNE`", "`%s`" % aff.code)
                         .replace("/join/ANNE", "/join/%s" % aff.code)
                         .replace("?code=ANNE", "?code=%s" % aff.code))
    return render_template("aff_promote.html", **_ctx(
        aff, "promote", offer=offer, promos=promos, swipes=dash.swipe_copy(aff, links, offer),
        disclosure=dash.DISCLOSURE, guide_html=html, ai_md=ai_md,
        logo_urlpath=AFFILIATE_LOGO_URLPATH))


# ------------------------------------------------------------------
# settings: your offer (discount chooser), profile, account
# ------------------------------------------------------------------
@bp.route("/settings")
@require_affiliate
def settings():
    aff = get_current_affiliate()
    s = _db()
    try:
        import affiliate_service as asvc
        live = _fresh_affiliate(s)
        terms = asvc.terms_for(s, live)
        catalog = _catalog()
        next_change = asvc.next_discount_change_at(live)
        offer = dash.offer_summary(live, terms)
        promos = dash.promotions(s, live, catalog, terms)
        ctx = _ctx(
            aff, "settings", offer=offer,
            confirm=_pending_confirm(request.args.get("confirm"), offer, next_change,
                                     _is_owner(live)),
            plans=dash.plan_table(catalog, live, terms, promos) if catalog else [],
            grid=dash.discount_grid(catalog, terms),
            history=dash.discount_history_rows(s, live),
            next_change=(next_change.strftime("%d %b %Y, %H:%M UTC").lstrip("0")
                         if next_change else None),
            is_owner=_is_owner(live), logo_urlpath=AFFILIATE_LOGO_URLPATH)
    finally:
        s.close()
    return render_template("aff_settings.html", **ctx)


def _pending_confirm(raw, offer, next_change, is_owner):
    """The confirm step of a discount change (?confirm=<pct> after the first
    POST): {"new", "old", "text"} or None when there is nothing to confirm."""
    if not raw or next_change or not is_owner:
        return None
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(str(raw).strip())
        if not value.is_finite():
            return None
    except (InvalidOperation, ValueError):
        return None
    old = offer["discount_year"]
    new = dash.fmt_pct(value)
    if value < 0 or value > offer["max_discount_int"] or (new == old and not offer["split"]):
        return None
    if old not in ("", "0"):
        text = ("Posts and videos that say %s%% off will now be wrong. New customers get %s%%."
                % (old, new))
    else:
        text = ("New customers get %s%% off from now on. Posts and videos you already made "
                "don't mention a discount." % new)
    if value == 0:
        text += " Your checkout code stops working, but your links still track."
    return {"new": new, "old": old, "text": text}


def _offer_flash(message, category):
    """Discount results are shown NEXT TO the Save button (aff_settings.html
    reads the offer-* categories), not at the top of the page."""
    flash(message, "offer-" + category)


def _discount_error_text(exc):
    """Partner-facing text for a failed discount save. Only the cooldown and
    'no change' messages of affiliate_service are written for partners; every
    other AffiliateError (Stripe, internal wording) maps to one plain sentence
    so raw exception text is never shown."""
    msg = str(exc)
    if msg.startswith("You can change your discount once every 24 hours"):
        return msg
    if msg.startswith("No change"):
        return msg
    return dash.DISCOUNT_SAVE_FAILED


def _is_owner(live):
    """Only the partner's own linked login may change the offer."""
    user = get_current_user()
    return (user is not None and live is not None and live.user_id is not None
            and str(live.user_id) == str(getattr(user, "id", None)))


@bp.route("/settings/discount", methods=["POST"])
@require_affiliate
def settings_discount():
    """Self-serve customer discount (0 to the terms' cap, one change per 24h).
    Validation, the cooldown, the Stripe coupon and the history row all live
    in affiliate_service.set_partner_discount."""
    import affiliate_service as asvc
    from decimal import Decimal, InvalidOperation
    aff = get_current_affiliate()
    flash = _offer_flash                      # results render beside the Save button
    back = redirect(url_for("affiliate_portal.settings") + "#offer-status")
    raw = (request.form.get("discount_pct") or "").strip().rstrip("%").strip()
    try:
        new = Decimal(raw)
        if not new.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        flash("Enter a discount as a number, for example 20.", "error")
        return back
    s = _db()
    try:
        live = _fresh_affiliate(s)
        if not _is_owner(live):
            flash("Only the account owner can change the discount.", "error")
            return back
        terms = asvc.terms_for(s, live)
        cap = asvc._dec(terms.max_discount_pct)
        if new < 0 or new > cap:
            flash("Choose a discount between 0%% and %s%%." % dash.fmt_pct(cap), "error")
            return back
        actor = "partner:%s" % live.user_id
        try:
            annual_same = asvc._dec(live.discount_pct) == new
            monthly_differs = (live.discount_pct_monthly is not None
                               and asvc._dec(live.discount_pct_monthly) != new)
            if annual_same and not monthly_differs:
                flash("No change - your discount is already %s%%." % dash.fmt_pct(new), "success")
                return back
            wait = asvc.next_discount_change_at(live)
            if wait is not None:
                flash("You can change your discount once every 24 hours. Next change "
                      "available %s UTC." % wait.strftime("%Y-%m-%d %H:%M"), "error")
                return back
            if (request.form.get("confirm") != "yes"
                    or request.form.get("confirm_for", dash.fmt_pct(new)) != dash.fmt_pct(new)):
                # Step 1 of 2: show what the change means before anything is saved.
                return redirect(url_for("affiliate_portal.settings",
                                        confirm=dash.fmt_pct(new)) + "#offer-status")
            if not annual_same:
                asvc.set_partner_discount(s, live, new, interval="year", actor=actor)
            if live.discount_pct_monthly is not None:
                # One discount for every plan: fold a legacy monthly override
                # into the same value (same partner action, same cooldown).
                asvc.set_partner_discount(s, live, new, interval="month", actor=actor,
                                          enforce_cooldown=annual_same)
        except asvc.AffiliateError as e:
            s.rollback()
            log.warning("discount change refused for %s: %s", aff.code, e)
            flash(_discount_error_text(e), "error")
            return back
        except Exception:   # noqa: BLE001 - Stripe / DB failure: nothing was saved
            s.rollback()
            log.exception("discount change failed for %s", aff.code)
            flash(dash.DISCOUNT_SAVE_FAILED, "error")
            return back
    finally:
        s.close()
    from flask import g as _g
    _g._aff_portal_affiliate = "unset"
    flash("Saved. New customers now get %s%% off. Nothing changes for customers you already have."
          % dash.fmt_pct(new), "success")
    return back


_resend_at: dict = {}


@bp.route("/agreement/resend", methods=["POST"])
@require_affiliate
def agreement_resend():
    """Email the partner their private agreement-signing link again."""
    aff = get_current_affiliate()
    back = redirect(url_for("affiliate_portal.overview"))
    if aff.agreement_signed_at is not None:
        flash("Your agreement is already signed.", "success")
        return back
    last = _resend_at.get(str(aff.id))
    if last is not None and time.monotonic() - last < 600:
        flash("We just sent it. Check your inbox (and spam) for the signing link.", "success")
        return back
    import affiliate_agreement as agr
    if agr.email_signing_link(aff):
        _resend_at[str(aff.id)] = time.monotonic()
        flash("Sent. The signing link is on its way to %s." % aff.email, "success")
    else:
        flash("We could not send the email. Write to help@tradewave.ai and we will sort it out.", "error")
    return back


# ------------------------------------------------------------------
# partner guide (human page + AI-ready markdown)
# ------------------------------------------------------------------
def _guide_md():
    try:
        with open(GUIDE_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError:
        log.warning("partner guide missing at %s", GUIDE_PATH)
        return "# TradeWave Partner Guide\n\nThe guide is temporarily unavailable. Write to help@tradewave.ai.\n"


def _partner_details_md(aff, terms=None):
    """The partner's own facts, prepended to the guide for their AI. Only the
    affiliate's own terms - never customer data."""
    import affiliate_service as asvc
    if terms is None:
        try:
            terms = getattr(aff, "terms", None)
        except Exception:   # noqa: BLE001 - detached row: fall back to the program default
            terms = None
    o = dash.offer_summary(aff, terms or asvc.DEFAULT_TERMS)
    links = _links_for(aff)
    lines = [
        "## Your details (filled in from your dashboard on %s)" % datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "",
        "- Partner name: %s" % (aff.page_display_name or aff.name),
        "- Referral code: `%s`" % aff.code,
        "- Landing page (share this by default): %s" % links["join"],
        "- Referral link: %s" % links["referral"],
        "- Program status: %s" % aff.status,
        "- Your pool: %s%% of the list price to split between your audience's discount "
        "(up to %s%%) and your commission" % (o["pool_pct"], o["max_discount_pct"]),
    ]
    if o["split"]:
        lines += [
            "- Annual plans: your audience gets %s%% off the first year, you earn %s%% of the list price"
            % (o["discount_year"], o["rate_year"]),
            "- Monthly plans: your audience gets %s%% off the first 12 months, you earn %s%% of the list price"
            % (o["discount_month"], o["rate_month"]),
        ]
    else:
        lines.append("- All plans: your audience gets %s%% off the first year, you earn %s%% of the list price"
                     % (o["discount_year"], o["rate_year"]))
    lines += [
        "- TradeWave sales (promotions): the customer gets the lower price (the sale or your "
        "discount); if the sale wins you earn %s%% of what they paid" % o["promo_pct"],
        "- Renewals: %s%% of what the customer pays, %s"
        % (o["renewal_pct"], "for as long as they stay subscribed" if o["lifetime"]
           else "in years 2-%s" % o["last_year"]),
    ]
    if o["activity_rule_months"]:
        lines.append("- Activity rule: renewal commissions are paid while you bring in at least 1 "
                     "new paying customer every %s months, with a 30-day grace"
                     % o["activity_rule_months"])
    lines.append("- Change your discount any time (once per 24 hours) on the Settings page of "
                 "your dashboard")
    lines += [
        "- Payout method: %s" % ((aff.payout_method or "not set").capitalize()),
        "- Tax form on file: %s" % ("yes" if aff.tax_form_received_at else
                                   "NO - payouts are held until TradeWave has your W-9 / W-8BEN / W-8BEN-E. "
                                   "Do not email the form: contact help@tradewave.ai for a secure upload link"),
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _guide_for(aff, terms=None):
    md = _guide_md()
    head, sep, rest = md.partition("\n---\n")
    if not sep:
        return _partner_details_md(aff, terms) + md
    # Keep the title + intro first, then the partner's own details.
    return head.rstrip() + "\n\n" + _partner_details_md(aff, terms) + rest.lstrip("\n")


def _render_guide(md):
    """Repo-authored markdown -> HTML (tables, headings), still bleached."""
    import bleach
    import markdown as _markdown
    raw = _markdown.markdown(md, extensions=["tables", "sane_lists", "fenced_code"])
    tags = ["h1", "h2", "h3", "h4", "p", "br", "hr", "strong", "em", "ul", "ol", "li",
            "blockquote", "a", "code", "pre", "table", "thead", "tbody", "tr", "th", "td"]
    clean = bleach.clean(raw, tags=tags, attributes={"a": ["href", "title"]},
                         protocols=["https", "mailto"], strip=True)
    return bleach.linkify(clean, skip_tags=["code", "pre"], parse_email=True)


@bp.route("/guide")
@require_affiliate
def guide():
    """Old URL: the guide now lives under Promote."""
    return redirect(url_for("affiliate_portal.promote") + "#guide")


@bp.route("/guide.md")
@require_affiliate
def guide_md():
    aff = get_current_affiliate()
    s = _db()
    try:
        import affiliate_service as asvc
        live = _fresh_affiliate(s)
        body = _guide_for(live, asvc.terms_for(s, live))
    finally:
        s.close()
    return Response(body, mimetype="text/markdown; charset=utf-8",
                    headers={"Content-Disposition":
                             'inline; filename="tradewave-partner-guide-%s.md"' % aff.code,
                             "Cache-Control": "private, no-store"})


# ------------------------------------------------------------------
# profile (join-page fields + photo + SMN expert profile)
# ------------------------------------------------------------------
def _profile_next():
    if request.form.get("next") == "promote":
        return url_for("affiliate_portal.promote") + "#join-page"
    return url_for("affiliate_portal.settings") + "#profile"


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
                # Only when the form carries them (the Promote join-page
                # editor posts the three page fields alone).
                prof = _smn_profile(s, live.id) if "bio_md" in request.form else None
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
                return redirect(_profile_next())
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
        return redirect(_profile_next())
    return redirect(url_for("affiliate_portal.settings") + "#profile")


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
        return redirect(url_for("affiliate_portal.settings") + "#profile")
    blob = f.read(MAX_PHOTO_BYTES + 1)
    if len(blob) > MAX_PHOTO_BYTES:
        flash("Image too large (2 MB max).", "error")
        return redirect(url_for("affiliate_portal.settings") + "#profile")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(blob))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("format")
        img = img.convert("RGB")
        img.thumbnail((512, 512))
    except Exception:   # noqa: BLE001 - any parse failure = reject
        flash("That file is not a supported image (jpg, png or webp).", "error")
        return redirect(url_for("affiliate_portal.settings") + "#profile")
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
    return redirect(url_for("affiliate_portal.settings") + "#profile")


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
            "score_result": t.score_result,
            "score_return_pct": (float(t.score_return_pct)
                                 if t.score_return_pct is not None else None),
        } for t in takes]
        import expert_scorecard
        scorecard = expert_scorecard.scorecard_for(s, aff.id)
    finally:
        s.close()
    return render_template("aff_smn.html", takes=take_rows, scorecard=scorecard, **ctx)


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
