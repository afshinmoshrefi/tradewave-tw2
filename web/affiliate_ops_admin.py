"""Admin screens for the affiliate operations + growth tools (TW-TASK-0039 C).

Three Flask-Admin BaseViews, built by make_views() and registered in
web/app.py next to the other affiliate views:

  bulk_payouts  /admin/affiliate_bulk_payouts/  export PayPal / Wise CSV for
                payable ledger rows; bulk mark-paid with references. Files
                and records only - this never moves money.
  tax_forms     /admin/affiliate_tax_forms/     review uploaded tax forms;
                every download writes an audit_log entry first.
  creatives     /admin/affiliate_creatives/     the creative library.

All logic is in web/affiliate_ops.py; this module is forms + templates.
"""
from __future__ import annotations

import logging

import affiliate_ops as ops
import affiliate_ops_models as om

log = logging.getLogger("tw2.affiliate_ops_admin")

_CSS = """
 body{font:14px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2a44;background:#f4f5f9;margin:0;}
 .wrap{max-width:1080px;margin:0 auto;padding:24px 20px 60px;}
 nav a{margin-right:14px;display:inline-block;} a{color:#5b4bdb;}
 h1{font-size:22px;margin:14px 0 4px;} h2{font-size:17px;margin:0 0 8px;color:#3a32a8;}
 .doc{background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:20px 24px;margin:16px 0;}
 .flash{border-radius:8px;padding:10px 14px;margin:12px 0;font-size:13px;border:1px solid #e3e6ee;}
 .flash-success{background:#e7f6ec;color:#0a7d28;border-color:#bfe6cb;}
 .flash-warning{background:#fffbe6;color:#8a6d00;border-color:#f0e6b0;}
 .flash-error,.flash-danger{background:#fdeaea;color:#b00020;border-color:#f3c6c6;}
 .flash-info{background:#eef2ff;color:#3a32a8;border-color:#cfd6f5;}
 .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;}
 table{border-collapse:collapse;width:100%;margin-top:8px;}
 th,td{border:1px solid #e1e4ec;padding:7px 10px;text-align:left;font-size:13px;vertical-align:top;}
 th{background:#f5f5f9;white-space:nowrap;} td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
 label{display:block;margin:12px 0 0;font-size:13px;font-weight:600;color:#3a3a55;}
 input[type=text],input[type=number],select,textarea{margin-top:4px;padding:7px 9px;border:1px solid #cfd3e0;border-radius:7px;font-size:14px;font-family:inherit;max-width:100%;box-sizing:border-box;}
 input[type=text]{width:340px;} textarea{width:100%;}
 .note{font-size:13px;color:#555;background:#f7f7fb;border:1px solid #e6e6ef;border-radius:8px;padding:10px 14px;margin:12px 0;}
 .warn{font-size:13px;color:#8a6d00;background:#fffbe6;border:1px solid #f0e6b0;border-radius:8px;padding:10px 14px;margin:12px 0;}
 .muted{color:#666;font-size:13px;} .err{color:#b00020;} .ok{color:#0a7d28;}
 button,.btn{display:inline-block;margin-top:12px;font-size:14px;font-weight:600;border:1px solid #4338ca;background:#4f46e5;color:#fff;border-radius:7px;padding:8px 16px;cursor:pointer;text-decoration:none;}
 button.secondary,.btn.secondary{background:#fff;color:#4338ca;} button.danger{background:#b00020;border-color:#8f001a;}
 button.small,.btn.small{margin-top:0;padding:4px 10px;font-size:12px;}
 .pill{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:20px;background:#eef2ff;color:#3a32a8;white-space:nowrap;}
 .pill.ok{background:#e7f6ec;color:#0a7d28;} .pill.bad{background:#fdeaea;color:#b00020;} .pill.warnp{background:#fffbe6;color:#8a6d00;}
 .grid{display:flex;gap:24px;flex-wrap:wrap;} .grid>div{flex:1;min-width:260px;}
 .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;}
 img.thumb{max-width:160px;max-height:80px;display:block;border:1px solid #e1e4ec;border-radius:6px;background:#0b0f1a;}
 form.inline{display:inline;}
 @media (max-width:640px){.wrap{padding:16px 12px 48px;} .doc{padding:14px 14px;} input[type=text]{width:100%;}}
"""

_HEAD = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>{{ title }}</title><style>""" + _CSS + """</style></head><body><div class="wrap">
<nav><a href="/admin">&larr; Admin</a><a href="/admin/affiliate/">Affiliates</a>
<a href="/admin/affiliatepayout/">Payout ledger</a>
<a href="{{ url_for('affiliate_bulk_payouts.index') }}">Bulk payouts</a>
<a href="{{ url_for('affiliate_tax_forms.index') }}">Tax forms</a>
<a href="{{ url_for('affiliate_creatives.index') }}">Creative library</a></nav>
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}{% for cat, m in msgs %}<div class="flash flash-{{ cat }}">{{ m }}</div>{% endfor %}{% endif %}
{% endwith %}
"""
_FOOT = "</div></body></html>"

_BULK_TMPL = _HEAD + """
<h1>Bulk payouts</h1>
<p class="muted">Step 1: export a file and upload it to PayPal or Wise yourself. Step 2: after the money is sent,
mark the rows paid here with the payment references. <strong>This page never moves money</strong> and never
contacts PayPal or Wise.</p>

{% if preview is not none %}
<div class="doc"><h2>Check before marking paid</h2>
 <div class="scroll"><table>
  <tr><th>Reference</th><th>Partner</th><th>Statement</th><th class="num">Amount</th><th>Payment reference</th><th>Result</th></tr>
  {% for e in preview %}
  <tr><td class="mono">{{ e.ref or '-' }}</td><td>{{ e.code or '-' }}</td><td>{{ e.period or '-' }}</td>
   <td class="num">{% if e.amount is not none %}{{ '%.2f'|format(e.amount) }} {{ e.currency|upper }}{% else %}-{% endif %}</td>
   <td class="mono">{{ e.reference or '-' }}</td>
   <td class="{{ 'ok' if e.ok else 'err' }}">{{ e.message }}</td></tr>
  {% endfor %}
 </table></div>
 {% if preview_ok %}
 <form method="post" action="{{ url_for('affiliate_bulk_payouts.mark_paid') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input type="hidden" name="confirm" value="yes">
  <textarea name="batch" hidden>{{ batch_text }}</textarea>
  <input type="hidden" name="default_reference" value="{{ default_reference }}">
  <button type="submit">Mark {{ preview_ok }} row{{ '' if preview_ok == 1 else 's' }} paid</button>
  <a class="btn secondary" href="{{ url_for('affiliate_bulk_payouts.index') }}">Cancel</a>
 </form>
 <p class="muted">Rows shown in red are skipped. Marking a row paid also marks its ledger lines paid.</p>
 {% else %}<p class="err">Nothing can be marked paid from this list.</p>
 <a class="btn secondary" href="{{ url_for('affiliate_bulk_payouts.index') }}">Back</a>{% endif %}
</div>
{% endif %}

<div class="doc"><h2>1. Export payable rows</h2>
{% if groups %}
 {% for g in groups %}
 <form method="post" action="{{ url_for('affiliate_bulk_payouts.export') }}" style="margin-bottom:22px;">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <input type="hidden" name="method" value="{{ g.method }}"><input type="hidden" name="currency" value="{{ g.currency }}">
  <h3 style="margin:14px 0 2px;font-size:15px;">{{ g.method_label }} - {{ g.currency|upper }}
    <span class="muted" style="font-weight:400;">{{ g.rows|length }} row{{ '' if g.rows|length == 1 else 's' }}, {{ '%.2f'|format(g.total) }} {{ g.currency|upper }}</span></h3>
  <div class="scroll"><table>
   <tr><th><input type="checkbox" checked aria-label="Select all" onclick="var b=this.form.querySelectorAll('input[name=ids]');for(var i=0;i<b.length;i++)b[i].checked=this.checked;"></th>
     <th>Reference</th><th>Partner</th><th>Statement</th><th>Pay to</th><th class="num">Amount</th></tr>
   {% for r in g.rows %}
   <tr><td><input type="checkbox" name="ids" value="{{ r.id }}" checked aria-label="Select {{ r.ref }}"></td>
     <td class="mono">{{ r.ref }}</td><td><strong>{{ r.code }}</strong> {{ r.name }}</td><td>{{ r.period }}</td>
     <td class="mono">{{ r.email }}</td><td class="num"><strong>{{ '%.2f'|format(r.amount) }}</strong></td></tr>
   {% endfor %}
  </table></div>
  <button type="submit">Export {{ g.method_label }} CSV ({{ g.currency|upper }})</button>
 </form>
 {% endfor %}
 <p class="muted">One file per payout method and currency. PayPal: Payouts - Upload a file (no header row: email, amount,
 currency, reference, note, wallet). Wise: Batch transfers - Upload (header row: {{ wise_columns|join(', ') }}).
 The Reference column is how the rows are matched when you mark them paid.</p>
{% else %}
 <p class="muted">No payable rows right now. Commit the month on <a href="/admin/affiliate_compute/">Compute / What I owe</a> first.</p>
{% endif %}
{% if blocked %}
 <h3 style="margin:18px 0 2px;font-size:15px;">Not payable yet ({{ blocked|length }})</h3>
 <div class="scroll"><table>
  <tr><th>Reference</th><th>Partner</th><th>Statement</th><th class="num">Amount</th><th>Why</th></tr>
  {% for r in blocked %}
  <tr><td class="mono">{{ r.ref }}</td><td><strong>{{ r.code }}</strong> {{ r.name }}</td><td>{{ r.period }}</td>
    <td class="num">{{ '%.2f'|format(r.amount) }} {{ r.currency|upper }}</td><td>{{ r.short_reason }}</td></tr>
  {% endfor %}
 </table></div>
{% endif %}
</div>

<div class="doc"><h2>2. Mark rows paid</h2>
 <p class="muted">Paste one row per line: the TradeWave reference, then the payment reference from PayPal or Wise
 (comma or tab between them). Or upload the result file from PayPal or Wise, or the file you exported.
 You see a preview before anything is saved.</p>
 <form method="post" action="{{ url_for('affiliate_bulk_payouts.mark_paid') }}" enctype="multipart/form-data">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <label for="batch">Paid rows</label>
  <textarea id="batch" name="batch" rows="6" class="mono" placeholder="TWP000123, 5AB12345CD678901E&#10;TWP000124, 8XY98765ZW432109K">{{ batch_text if preview is none else '' }}</textarea>
  <div class="grid">
   <div><label for="batch_file">Or a CSV file</label><input type="file" id="batch_file" name="batch_file" accept=".csv,text/csv,text/plain"></div>
   <div><label for="default_reference">Batch reference (used for lines without their own)</label>
     <input type="text" id="default_reference" name="default_reference" maxlength="120" placeholder="e.g. PayPal batch id"></div>
  </div>
  <button type="submit">Preview</button>
 </form>
</div>
""" + _FOOT

_TAX_TMPL = _HEAD + """
<h1>Tax forms</h1>
<p class="muted">Partners upload their W-9 / W-8BEN / W-8BEN-E on the Payouts page. Files are encrypted and kept
outside the web root. <strong>Accept</strong> puts the form on file, which is what lets a payout be marked paid.
Every download is written to the audit log.</p>
{% if not enabled %}<div class="warn"><strong>Upload is switched off:</strong> TW2_TAX_FORM_KEY is not set (or not a valid key)
in secrets.env on this box, so partners see "not available" and stored files cannot be opened.</div>{% endif %}
<div class="doc"><h2>Waiting for review ({{ waiting|length }})</h2>
{% if waiting %}
 {% for f in waiting %}
 <div style="border-top:1px solid #e3e6ee;padding:14px 0;">
  <strong>{{ f.affiliate.code }}</strong> {{ f.affiliate.name }} - <span class="pill">{{ labels[f.form_type] }}</span>
  <span class="muted">uploaded {{ f.uploaded_at.strftime('%d %b %Y %H:%M') }} UTC, {{ '%.0f'|format(f.size_bytes / 1024) }} KB,
   {{ f.original_filename }}</span>
  <div style="margin-top:6px;">
   <a class="btn small secondary" href="{{ url_for('affiliate_tax_forms.download', form_id=f.id) }}">Download PDF</a>
   <form class="inline" method="post" action="{{ url_for('affiliate_tax_forms.accept', form_id=f.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <button class="small" type="submit">Accept</button></form>
  </div>
  <form method="post" action="{{ url_for('affiliate_tax_forms.reject', form_id=f.id) }}" style="margin-top:8px;">
   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
   <input type="text" name="reason" maxlength="500" placeholder="Reason the partner will see, e.g. The form is not signed." aria-label="Rejection reason">
   <button class="small danger" type="submit">Reject</button>
  </form>
 </div>
 {% endfor %}
{% else %}<p class="muted">Nothing to review.</p>{% endif %}
</div>
<div class="doc"><h2>History</h2>
{% if history %}
 <div class="scroll"><table>
  <tr><th>Partner</th><th>Form</th><th>Status</th><th>Uploaded</th><th>Reviewed</th><th>Note</th><th></th></tr>
  {% for f in history %}
  <tr><td><strong>{{ f.affiliate.code }}</strong></td><td>{{ labels[f.form_type] }}</td>
   <td><span class="pill {{ 'ok' if f.status == 'accepted' else ('bad' if f.status == 'rejected' else '') }}">{{ f.status|capitalize }}</span></td>
   <td>{{ f.uploaded_at.strftime('%d %b %Y') }}</td>
   <td>{% if f.reviewed_at %}{{ f.reviewed_at.strftime('%d %b %Y') }} <span class="muted">{{ f.reviewed_by or '' }}</span>{% else %}-{% endif %}</td>
   <td>{{ f.reject_reason or '' }}</td>
   <td>{% if f.storage_name %}<a href="{{ url_for('affiliate_tax_forms.download', form_id=f.id) }}">Download</a>{% else %}<span class="muted">file deleted</span>{% endif %}</td></tr>
  {% endfor %}
 </table></div>
{% else %}<p class="muted">No reviewed forms yet.</p>{% endif %}
</div>
""" + _FOOT

_CREATIVE_TMPL = _HEAD + """
<h1>Creative library</h1>
<p class="muted">Banners, logos and ready-written copy that partners see on their Promote page with their own
tracked link filled in. Tie an item to a campaign and it shows only while that campaign is live.</p>
<div class="doc"><h2>Add an item</h2>
 <form method="post" action="{{ url_for('affiliate_creatives.create') }}" enctype="multipart/form-data">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="grid">
   <div>
    <label for="kind">Kind</label>
    <select id="kind" name="kind">{% for k in kinds %}<option value="{{ k }}"{% if f.kind == k %} selected{% endif %}>{{ kind_labels[k] }}</option>{% endfor %}</select>
    <label for="title">Title</label>
    <input type="text" id="title" name="title" maxlength="120" value="{{ f.title or '' }}" placeholder="e.g. Leaderboard 728 x 90">
    <label for="campaign_id">Show</label>
    <select id="campaign_id" name="campaign_id"><option value="">Always (evergreen)</option>
     {% for c in campaigns %}<option value="{{ c.id }}"{% if f.campaign_id == c.id|string %} selected{% endif %}>Only during {{ c.name }}</option>{% endfor %}</select>
    <label for="image">Image (banner or logo: png, jpg, webp or gif, 5 MB max)</label>
    <input type="file" id="image" name="image" accept="image/png,image/jpeg,image/webp,image/gif">
   </div>
   <div>
    <label for="body">Copy (email or social post; optional usage note for an image)</label>
    <textarea id="body" name="body" rows="9">{{ f.body or '' }}</textarea>
    <p class="muted" style="margin:6px 0 0;">Filled in per partner: {% for p in placeholders %}<span class="mono">{{ p }}</span>{% if not loop.last %}, {% endif %}{% endfor %}.
    Include the disclosure line in copy. Do not promise profits.</p>
   </div>
  </div>
  <button type="submit">Add to library</button>
 </form>
</div>
<div class="doc"><h2>Library ({{ items|length }})</h2>
{% if items %}
 <div class="scroll"><table>
  <tr><th>Item</th><th>Kind</th><th>Shown</th><th>Status</th><th></th></tr>
  {% for c in items %}
  <tr><td>{% if c.file_name %}<img class="thumb" src="{{ url_for('affiliate_creatives.file', creative_id=c.id) }}" alt="">{% endif %}
    <strong>{{ c.title }}</strong>{% if c.width %} <span class="muted">{{ c.width }} x {{ c.height }}</span>{% endif %}
    {% if c.body %}<div class="muted" style="white-space:pre-wrap;max-width:460px;">{{ c.body[:220] }}{% if c.body|length > 220 %}...{% endif %}</div>{% endif %}</td>
   <td>{{ kind_labels[c.kind] }}</td>
   <td>{% if c.campaign %}During {{ c.campaign.name }}{% else %}Always{% endif %}</td>
   <td><span class="pill {{ 'ok' if c.status == 'active' else '' }}">{{ c.status|capitalize }}</span></td>
   <td style="white-space:nowrap;">
    <form class="inline" method="post" action="{{ url_for('affiliate_creatives.status', creative_id=c.id) }}">
     <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
     <input type="hidden" name="status" value="{{ 'archived' if c.status == 'active' else 'active' }}">
     <button class="small secondary" type="submit">{{ 'Archive' if c.status == 'active' else 'Restore' }}</button></form>
    <form class="inline" method="post" action="{{ url_for('affiliate_creatives.delete', creative_id=c.id) }}"
          onsubmit="return confirm('Delete this item for good?');">
     <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
     <button class="small danger" type="submit">Delete</button></form></td></tr>
  {% endfor %}
 </table></div>
{% else %}<p class="muted">The library is empty.</p>{% endif %}
</div>
""" + _FOOT


def _email_partner(affiliate, subject, body):
    try:
        from email_utils import resend_send_email
        if affiliate is not None and affiliate.email:
            resend_send_email(to=affiliate.email, subject=subject, body_text=body)
    except Exception as e:   # noqa: BLE001 - best effort
        log.warning("tax form email to partner failed: %s", e)


def make_views(auth_cls, *, audit_fn, current_user_fn):
    """Build the BaseViews. auth_cls is app._AdminAuth (super_admin gate);
    audit_fn is app.write_audit; current_user_fn is app.get_current_user."""
    from flask import Response, flash, redirect, render_template_string, request, send_file, url_for
    from flask_admin import BaseView, expose

    def _S():
        import models
        return models.Session()

    def actor():
        u = current_user_fn()
        return "admin:%s" % (getattr(u, "email", None) or "unknown")

    def actor_id():
        return getattr(current_user_fn(), "id", None)

    # ---------------------------------------------------------- Bulk payouts
    class BulkPayoutsView(auth_cls, BaseView):

        def _page(self, s, **extra):
            rows = ops.pending_payout_rows(s)
            ctx = dict(title="Bulk payouts", groups=ops.payout_groups(rows),
                       blocked=[r for r in rows if not r["payable"]],
                       wise_columns=ops.WISE_COLUMNS, preview=None, preview_ok=0,
                       batch_text="", default_reference="")
            ctx.update(extra)
            return render_template_string(_BULK_TMPL, **ctx)

        @expose("/")
        def index(self):
            s = _S()
            try:
                return self._page(s)
            finally:
                s.close()

        @expose("/export", methods=["POST"])
        def export(self):
            method = (request.form.get("method") or "").strip()
            currency = (request.form.get("currency") or "").strip().lower()
            s = _S()
            try:
                try:
                    rows, skipped = ops.select_for_export(s, request.form.getlist("ids"), method, currency)
                    text = ops.paypal_csv(rows) if method == "paypal" else ops.wise_csv(rows)
                except ops.OpsError as e:
                    flash(str(e), "error")
                    return redirect(url_for("affiliate_bulk_payouts.index"))
                refs = [r["ref"] for r in rows]
                total = "%.2f" % sum(r["amount"] for r in rows)
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_payout_export",
                     details={"method": method, "currency": currency, "rows": refs, "total": total,
                              "skipped": [r for r, _why in skipped]})
            return Response(text, mimetype="text/csv; charset=utf-8", headers={
                "Content-Disposition": 'attachment; filename="%s"' % ops.export_filename(method, currency),
                "Cache-Control": "private, no-store"})

        @expose("/mark-paid", methods=["POST"])
        def mark_paid(self):
            text = request.form.get("batch") or ""
            f = request.files.get("batch_file")
            if f is not None and f.filename:
                text = f.read(2 * 1024 * 1024).decode("utf-8-sig", errors="replace")
            default_ref = (request.form.get("default_reference") or "").strip()
            entries = ops.parse_paid_batch(text)
            s = _S()
            try:
                if not entries:
                    flash("Paste the paid rows or choose a file first.", "error")
                    return redirect(url_for("affiliate_bulk_payouts.index"))
                if request.form.get("confirm") != "yes":
                    ops.check_paid_batch(s, entries, default_ref)
                    return self._page(s, preview=entries, preview_ok=sum(1 for e in entries if e["ok"]),
                                      batch_text=text, default_reference=default_ref)
                result = ops.apply_paid_batch(s, entries, default_ref)
            except Exception as e:   # noqa: BLE001
                s.rollback()
                log.exception("bulk mark-paid failed")
                flash("Nothing was saved: %s" % e, "error")
                return redirect(url_for("affiliate_bulk_payouts.index"))
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_payout_bulk_paid",
                     details={"paid": result["paid"], "refused": [r for r, _why in result["refused"]],
                              "ledger_lines": result["lines"]})
            if result["paid"]:
                flash("%d row(s) marked paid, %d ledger line(s) updated."
                      % (len(result["paid"]), result["lines"]), "success")
            if result["refused"]:
                flash("Not marked paid: " + "; ".join("%s (%s)" % rw for rw in result["refused"][:20]),
                      "warning")
            return redirect(url_for("affiliate_bulk_payouts.index"))

    # ------------------------------------------------------------- Tax forms
    class TaxFormsView(auth_cls, BaseView):

        def _load(self, s, form_id):
            return s.get(om.AffiliateTaxForm, form_id)

        @expose("/")
        def index(self):
            T = om.AffiliateTaxForm
            s = _S()
            try:
                return render_template_string(
                    _TAX_TMPL, title="Tax forms", enabled=ops.tax_upload_enabled(),
                    labels=ops.TAX_FORM_LABELS,
                    waiting=s.query(T).filter(T.status == "received").order_by(T.uploaded_at).all(),
                    history=(s.query(T).filter(T.status != "received")
                             .order_by(T.uploaded_at.desc()).limit(200).all()))
            finally:
                s.close()

        @expose("/download/<int:form_id>")
        def download(self, form_id):
            s = _S()
            try:
                form = self._load(s, form_id)
                if form is None:
                    return Response("Not found.", status=404, mimetype="text/plain")
                try:
                    blob = ops.read_tax_form(form)
                except ops.OpsError as e:
                    flash(str(e), "error")
                    return redirect(url_for("affiliate_tax_forms.index"))
                code, ftype = form.affiliate.code, form.form_type
                target = form.affiliate.user_id
            finally:
                s.close()
            # The audit entry is written BEFORE the bytes leave; if it cannot
            # be written the download is refused.
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_tax_form_downloaded",
                     target_user_id=target,
                     details={"form_id": form_id, "affiliate": code, "form_type": ftype,
                              "ip": request.headers.get("CF-Connecting-IP") or request.remote_addr})
            import io
            resp = send_file(io.BytesIO(blob), mimetype="application/pdf", as_attachment=True,
                             download_name="%s-%s-%d.pdf" % (code.lower(), ftype, form_id))
            resp.headers["Cache-Control"] = "private, no-store"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            return resp

        @expose("/accept/<int:form_id>", methods=["POST"])
        def accept(self, form_id):
            s = _S()
            try:
                form = self._load(s, form_id)
                if form is None:
                    flash("That form was not found.", "error")
                    return redirect(url_for("affiliate_tax_forms.index"))
                try:
                    ops.accept_tax_form(s, form, actor())
                except ops.OpsError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return redirect(url_for("affiliate_tax_forms.index"))
                aff, label = form.affiliate, ops.TAX_FORM_LABELS[form.form_type]
                code, target = aff.code, aff.user_id
                _email_partner(aff, "Your TradeWave tax form is on file",
                               "Hi %s,\n\nWe have accepted your %s. Your tax form is now on file, so "
                               "nothing more is needed from you for payouts.\n\nTradeWave Partners"
                               % (aff.name, label))
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_tax_form_accepted",
                     target_user_id=target, details={"form_id": form_id, "affiliate": code})
            flash("Accepted. %s now has a %s on file and can be paid." % (code, label), "success")
            return redirect(url_for("affiliate_tax_forms.index"))

        @expose("/reject/<int:form_id>", methods=["POST"])
        def reject(self, form_id):
            s = _S()
            try:
                form = self._load(s, form_id)
                if form is None:
                    flash("That form was not found.", "error")
                    return redirect(url_for("affiliate_tax_forms.index"))
                try:
                    ops.reject_tax_form(s, form, request.form.get("reason"), actor())
                except ops.OpsError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return redirect(url_for("affiliate_tax_forms.index"))
                aff, reason = form.affiliate, form.reject_reason
                code, target = aff.code, aff.user_id
                _email_partner(aff, "Your TradeWave tax form needs a fix",
                               "Hi %s,\n\nWe could not accept the tax form you uploaded.\n\nWhat to fix: %s\n\n"
                               "Please upload a corrected form on the Payouts page of your partner "
                               "dashboard. Do not email the form.\n\nTradeWave Partners" % (aff.name, reason))
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_tax_form_rejected",
                     target_user_id=target, details={"form_id": form_id, "affiliate": code, "reason": reason})
            flash("Rejected. %s sees the reason on their Payouts page. The file was deleted." % code, "success")
            return redirect(url_for("affiliate_tax_forms.index"))

    # ------------------------------------------------------ Creative library
    class CreativeLibraryView(auth_cls, BaseView):

        def _page(self, s, form=None):
            import affiliate_service as afs
            return render_template_string(
                _CREATIVE_TMPL, title="Creative library", items=ops.list_creatives(s),
                kinds=om.CREATIVE_KINDS, kind_labels=ops.CREATIVE_KIND_LABELS,
                placeholders=ops.CREATIVE_PLACEHOLDERS, f=form or {},
                campaigns=[c for c in afs.list_campaigns(s, include_archived=False)])

        @expose("/")
        def index(self):
            s = _S()
            try:
                return self._page(s)
            finally:
                s.close()

        @expose("/create", methods=["POST"])
        def create(self):
            f = request.files.get("image")
            blob = f.read(ops.CREATIVE_MAX_BYTES + 1) if f is not None and f.filename else None
            s = _S()
            try:
                try:
                    row = ops.save_creative(
                        s, kind=(request.form.get("kind") or "").strip(), title=request.form.get("title"),
                        body=request.form.get("body"), filename=f.filename if f is not None else None,
                        blob=blob, campaign_id=(request.form.get("campaign_id") or "").strip() or None,
                        actor=actor())
                except ops.OpsError as e:
                    s.rollback()
                    flash(str(e), "error")
                    return self._page(s, form=request.form)
                details = {"id": row.id, "kind": row.kind, "title": row.title}
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_creative_added",
                     details=details)
            flash("Added. Partners see it on their Promote page.", "success")
            return redirect(url_for("affiliate_creatives.index"))

        @expose("/status/<int:creative_id>", methods=["POST"])
        def status(self, creative_id):
            s = _S()
            try:
                row = s.get(om.AffiliateCreative, creative_id)
                if row is None:
                    flash("That item was not found.", "error")
                else:
                    try:
                        ops.set_creative_status(s, row, (request.form.get("status") or "").strip())
                        flash("Saved.", "success")
                    except ops.OpsError as e:
                        s.rollback()
                        flash(str(e), "error")
            finally:
                s.close()
            return redirect(url_for("affiliate_creatives.index"))

        @expose("/delete/<int:creative_id>", methods=["POST"])
        def delete(self, creative_id):
            s = _S()
            try:
                row = s.get(om.AffiliateCreative, creative_id)
                if row is None:
                    flash("That item was not found.", "error")
                    return redirect(url_for("affiliate_creatives.index"))
                details = {"id": row.id, "kind": row.kind, "title": row.title}
                ops.delete_creative(s, row)
            finally:
                s.close()
            audit_fn(actor_user_id=actor_id(), actor_label=actor(), action="affiliate_creative_deleted",
                     details=details)
            flash("Deleted.", "success")
            return redirect(url_for("affiliate_creatives.index"))

        @expose("/file/<int:creative_id>")
        def file(self, creative_id):
            s = _S()
            try:
                row = s.get(om.AffiliateCreative, creative_id)
                path = ops.creative_path(row) if row is not None else None
                mime = row.mime_type if row is not None else None
            finally:
                s.close()
            if path is None or not path.is_file():
                return Response("Not found.", status=404, mimetype="text/plain")
            return send_file(str(path), mimetype=mime, max_age=300)

    return {"bulk_payouts": BulkPayoutsView, "tax_forms": TaxFormsView, "creatives": CreativeLibraryView}
