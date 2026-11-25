"""Partner-portal routes for the operations + growth tools (TW-TASK-0039 C):
tax-form upload (Payouts), named sub-links with stats (Links) and the
creative library (Promote).

Everything is scoped to the SESSION affiliate (never a request parameter).
The page data reaches the existing templates through the `aff_ops` template
global below, so the page routes in routes.py are untouched. Logic lives in
web/affiliate_ops.py.
"""
import logging

from flask import Response, flash, redirect, request, send_file, url_for

from .blueprint import bp, get_current_affiliate, get_current_user, require_affiliate
from . import routes as _routes
from . import dashboard as dash

log = logging.getLogger("tw2.affiliate_portal")


def _ops():
    import affiliate_ops
    return affiliate_ops


def _asvc_admin_url(path):
    import affiliate_service as asvc
    return asvc.admin_url(path)


class _PageData:
    """Lazy, per-request page data for the templates: aff_ops.tax(),
    aff_ops.links(), aff_ops.creatives(). Each opens its own short DB
    session and returns plain dicts; a failure degrades to "feature not
    shown" instead of breaking the page."""

    def _run(self, fn, fallback):
        aff = get_current_affiliate()
        if aff is None:
            return fallback
        s = _routes._db()
        try:
            return fn(s, _routes._fresh_affiliate(s))
        except Exception:   # noqa: BLE001
            log.exception("affiliate ops page data failed")
            try:
                s.rollback()
            except Exception:   # noqa: BLE001
                pass
            return fallback
        finally:
            s.close()

    def tax(self):
        return self._run(lambda s, live: _ops().tax_form_view(s, live), None)

    def links(self):
        return self._run(lambda s, live: _ops().link_stats(s, live), None)

    def creatives(self):
        def build(s, live):
            import affiliate_service as asvc
            offer = dash.offer_summary(live, asvc.terms_for(s, live))
            return _ops().creatives_for_partner(s, live, _routes._links_for(live),
                                                offer["discount_year"])
        return self._run(build, {"images": [], "texts": []})


@bp.context_processor
def _inject_ops():
    import affiliate_service as asvc
    # aff_attribution_days: the referral-cookie window (60), for page copy.
    return {"aff_ops": _PageData(), "aff_attribution_days": asvc.attribution_window_days()}


# ------------------------------------------------------------------
# tax form
# ------------------------------------------------------------------
@bp.route("/tax-form", methods=["POST"])
@require_affiliate
def tax_form_upload():
    """Secure tax-form upload. The PDF is validated, encrypted and stored
    outside the web root; the operator is told a form is waiting (no file,
    no tax details in the email)."""
    ops = _ops()
    aff = get_current_affiliate()
    back = redirect(url_for("affiliate_portal.payouts") + "#tax-form")
    f = request.files.get("tax_form")
    if f is None or not f.filename:
        flash("Choose your completed PDF first.", "error")
        return back
    limit = ops.config.TAX_FORM_MAX_BYTES
    blob = f.read(limit + 1)
    user = get_current_user()
    s = _routes._db()
    try:
        live = _routes._fresh_affiliate(s)
        row = ops.store_tax_form(s, live, (request.form.get("form_type") or "").strip(),
                                 f.filename, f.mimetype, blob, user_id=getattr(user, "id", None))
        label = ops.TAX_FORM_LABELS.get(row.form_type, row.form_type)
    except ops.OpsError as e:
        s.rollback()
        flash(str(e), "error")
        return back
    except Exception:   # noqa: BLE001
        s.rollback()
        log.exception("tax form upload failed for %s", aff.code)
        flash("We could not save your form. Nothing was stored - try again in a few minutes.", "error")
        return back
    finally:
        s.close()
    _routes._notify_operator(
        "Affiliate tax form to review: %s" % aff.code,
        "Affiliate %s uploaded a %s. Review it here:\n%s"
        % (aff.code, label, _asvc_admin_url("affiliate_tax_forms/")))
    flash("Thanks - we have your %s. We will review it and show the result here." % label, "success")
    return back


# ------------------------------------------------------------------
# sub-links
# ------------------------------------------------------------------
@bp.route("/links/sub", methods=["POST"])
@require_affiliate
def sublink_create():
    ops = _ops()
    back = redirect(url_for("affiliate_portal.links") + "#sublinks")
    s = _routes._db()
    try:
        live = _routes._fresh_affiliate(s)
        row = ops.create_sublink(s, live, request.form.get("name"),
                                 campaign_id=(request.form.get("campaign_id") or "").strip() or None)
        flash("Link %s created. Share it and its numbers appear below." % row.sub, "success")
    except ops.OpsError as e:
        s.rollback()
        flash(str(e), "error")
    except Exception:   # noqa: BLE001
        s.rollback()
        log.exception("sub-link create failed")
        flash("We could not create that link. Try again in a few minutes.", "error")
    finally:
        s.close()
    return back


@bp.route("/links/sub/<int:sublink_id>/archive", methods=["POST"])
@require_affiliate
def sublink_archive(sublink_id):
    ops = _ops()
    restore = request.form.get("restore") == "1"
    s = _routes._db()
    try:
        row = ops.archive_sublink(s, _routes._fresh_affiliate(s), sublink_id, restore=restore)
        if row is None:
            flash("That link was not found.", "error")
        else:
            flash("Link %s %s. Its numbers are kept." % (row.sub, "restored" if restore else "archived"),
                  "success")
    finally:
        s.close()
    return redirect(url_for("affiliate_portal.links") + "#sublinks")


# ------------------------------------------------------------------
# creative library
# ------------------------------------------------------------------
@bp.route("/creative/<int:creative_id>/file")
@require_affiliate
def creative_file(creative_id):
    """Preview or download (?download=1) a library image. Only active items
    the partner can currently see are served."""
    ops = _ops()
    s = _routes._db()
    try:
        from affiliate_ops_models import AffiliateCreative
        import affiliate_service as asvc
        row = s.get(AffiliateCreative, creative_id)
        if row is None or row.status != "active" or row.kind not in ops.CREATIVE_IMAGE_KINDS \
                or (row.campaign is not None and not asvc.campaign_is_live(row.campaign)):
            return Response("Not found.", status=404, mimetype="text/plain")
        path = ops.creative_path(row)
        mime, title, ext = row.mime_type, row.title, (row.file_name or "").rsplit(".", 1)[-1]
    finally:
        s.close()
    if path is None or not path.is_file():
        return Response("Not found.", status=404, mimetype="text/plain")
    slug = _routes._slugify(title)
    resp = send_file(str(path), mimetype=mime, as_attachment=bool(request.args.get("download")),
                     download_name="tradewave-%s.%s" % (slug, ext), max_age=3600)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
