"""Admin screens for partner applications and partner messaging
(TW-TASK-0039 package B). Built like affiliate_admin.make_views: web/app.py
calls make_views() and registers the two BaseViews under "Affiliates".

  Applications  /admin/affiliate_applications/   review, approve, reject
  Messages      /admin/affiliate_messages/       compose, preview, send log

All logic is in web/affiliate_comms.py. No em-dashes in any UI string.
"""
from __future__ import annotations

import logging
import uuid

import affiliate_admin as afa
import affiliate_comms as comms
import affiliate_service as afs

log = logging.getLogger(__name__)

# The shared admin head has no viewport tag; these screens are also used on a phone.
_HEAD = afa._HEAD.replace(
    '<meta charset="utf-8">',
    '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">', 1)

_SUBNAV = """
<p style="margin:10px 0 0;"><a href="{{ url_for('affiliate_applications.index') }}">Applications</a> &middot;
<a href="{{ url_for('affiliate_messages.index') }}">Send a message</a> &middot;
<a href="{{ url_for('affiliate_messages.log') }}">Send log</a></p>
<style>
 .badge{display:inline-block;font-size:12px;font-weight:700;padding:1px 8px;border-radius:20px;}
 .b-new{background:#eef2ff;color:#3a32a8;} .b-approved,.b-sent{background:#e7f6ec;color:#0a7d28;}
 .b-rejected,.b-failed{background:#fdeaea;color:#b00020;} .b-spam,.b-skipped,.b-pending{background:#f1f1f5;color:#555;}
 .b-dup{background:#fffbe6;color:#8a6d00;}
 .tabs a{display:inline-block;margin:0 6px 6px 0;padding:5px 12px;border:1px solid #cfd3e0;border-radius:20px;text-decoration:none;font-size:13px;}
 .tabs a.on{background:#4f46e5;border-color:#4338ca;color:#fff;}
 .kv td:first-child{width:190px;color:#555;background:#fafafc;} pre.msg{white-space:pre-wrap;font:inherit;margin:0;}
 .scroll{overflow-x:auto;} textarea{min-height:90px;}
 .count{font-size:26px;font-weight:800;color:#3a32a8;}
 @media (max-width:640px){
   nav a{display:inline-block;margin:0 12px 6px 0;} .grid{display:block;} textarea,select{max-width:100%;}
   .wrap{padding:16px 12px 48px;} .doc{padding:16px 14px;}
   input[type=text],input[type=number],select{width:100%;box-sizing:border-box;}
   .kv td:first-child{width:110px;} button{width:100%;}
   table.cards thead{display:none;} table.cards tr{display:block;border:1px solid #e1e4ec;border-radius:10px;margin:0 0 10px;padding:6px 0;background:#fff;}
   table.cards td{display:flex;justify-content:space-between;gap:12px;border:0;padding:5px 12px;text-align:right;}
   table.cards td::before{content:attr(data-label);color:#666;font-weight:600;text-align:left;flex:none;}
 }
</style>
"""

_APPS_LIST_TMPL = _HEAD + _SUBNAV + """
<h1>Partner applications</h1>
<p class="muted">People who applied on <a href="/partners/apply" target="_blank" rel="noopener">/partners/apply</a>.
Approving one creates the partner on the default terms and emails the agreement signing link.</p>
<div class="tabs" style="margin-top:12px;">
{% for key, label in tabs %}
<a class="{{ 'on' if status == key else '' }}" href="{{ url_for('affiliate_applications.index', status=key) }}">{{ label }} ({{ counts.get(key, 0) }})</a>
{% endfor %}
</div>
<div class="doc">
{% if rows %}
<div class="scroll"><table class="cards">
<thead><tr><th>Applied</th><th>Name</th><th>Email</th><th>Audience</th><th>Country</th><th>Status</th><th></th></tr></thead>
<tbody>
{% for r in rows %}
<tr>
 <td data-label="Applied">{{ r.app.created_at.strftime('%Y-%m-%d') if r.app.created_at else '' }}</td>
 <td data-label="Name">{{ r.app.name }}</td>
 <td data-label="Email">{{ r.app.email }}</td>
 <td data-label="Audience">{{ sizes.get(r.app.audience_size, r.app.audience_size or '-') }}</td>
 <td data-label="Country">{{ r.app.country or '-' }}</td>
 <td data-label="Status"><span><span class="badge b-{{ r.app.status }}">{{ r.app.status }}</span>
   {% if r.flags.affiliate %} <span class="badge b-dup">Already a partner: {{ r.flags.affiliate.code }}</span>{% endif %}
   {% if r.flags.earlier %} <span class="badge b-dup">Applied before ({{ r.flags.earlier|length }})</span>{% endif %}</span></td>
 <td data-label=""><a href="{{ url_for('affiliate_applications.view', id=r.app.id) }}">{{ 'Review' if r.app.status == 'new' else 'Open' }}</a></td>
</tr>
{% endfor %}
</tbody></table></div>
{% else %}
<p class="muted" style="margin:0;">Nothing here.</p>
{% endif %}
</div>
""" + afa._FOOT

_APP_VIEW_TMPL = _HEAD + _SUBNAV + """
<h1>Application: {{ app.name }}</h1>
<p class="muted">Applied {{ app.created_at.strftime('%Y-%m-%d %H:%M UTC') if app.created_at else '' }} &middot;
<span class="badge b-{{ app.status }}">{{ app.status }}</span>
{% if app.decided_at %} &middot; decided {{ app.decided_at.strftime('%Y-%m-%d') }} by {{ app.decided_by or '-' }}{% endif %}</p>

{% if flags.affiliate %}
<div class="warn"><strong>Duplicate: this email is already a partner.</strong>
 {{ flags.affiliate.code }} ({{ flags.affiliate.name }}), status {{ flags.affiliate.status }}.
 {% if flags.affiliate.status != 'terminated' %}You cannot approve a second account for the same email.{% endif %}</div>
{% endif %}
{% if flags.earlier %}
<div class="warn"><strong>This email applied before:</strong>
 {% for e in flags.earlier %}<a href="{{ url_for('affiliate_applications.view', id=e.id) }}">{{ e.created_at.strftime('%Y-%m-%d') if e.created_at else 'earlier' }} ({{ e.status }})</a>{{ ', ' if not loop.last else '' }}{% endfor %}</div>
{% endif %}

<div class="doc">
<table class="kv">
<tr><td>Name</td><td>{{ app.name }}</td></tr>
<tr><td>Email</td><td><a href="mailto:{{ app.email }}">{{ app.email }}</a></td></tr>
<tr><td>Country</td><td>{{ app.country or '-' }}</td></tr>
<tr><td>Audience size</td><td>{{ sizes.get(app.audience_size, app.audience_size or '-') }}</td></tr>
<tr><td>Website</td><td>{{ app.website or '-' }}</td></tr>
<tr><td>Channels</td><td><pre class="msg">{{ app.channels or '-' }}</pre></td></tr>
<tr><td>How they will promote</td><td><pre class="msg">{{ app.promo_plan or '-' }}</pre></td></tr>
<tr><td>Agreed to policies</td><td>{{ app.agreed_policies_at.strftime('%Y-%m-%d %H:%M UTC') if app.agreed_policies_at else 'No' }}</td></tr>
{% if app.decision_note %}<tr><td>Decision note</td><td><pre class="msg">{{ app.decision_note }}</pre></td></tr>{% endif %}
{% if partner %}<tr><td>Partner created</td><td><a href="/admin/affiliate/?search={{ partner.code }}">{{ partner.code }}</a>
 ({{ partner.status }}{{ ', signed' if partner.agreement_signed_at else ', not signed yet' }})
 &middot; <a href="{{ url_for('affiliate_signed.index', id=partner.id) }}">signing link</a></td></tr>{% endif %}
</table>
</div>

{% if app.status != 'approved' %}
<div class="grid">
<div class="doc" style="margin:0 0 16px;">
<h2>Approve</h2>
<p class="muted">Creates the partner on terms <strong>{{ terms_version }}</strong> ({{ terms_summary }}), paused until they sign.
The partner can change the discount later.</p>
<form method="post" action="{{ url_for('affiliate_applications.approve') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="id" value="{{ app.id }}">
<label for="ap-code">Partner code</label>
<input type="text" id="ap-code" name="code" value="{{ f.code }}" maxlength="64" style="text-transform:uppercase;" required>
<div class="muted">Letters, digits, - and _. It is permanent and becomes their link and checkout code.</div>
<label for="ap-disc">Customer discount (%)</label>
<input type="number" id="ap-disc" name="discount_pct" value="{{ f.discount_pct }}" min="0" max="{{ max_discount }}" step="1" required>
<div class="muted">0 to {{ max_discount }}. The partner earns the rest of the {{ pool }}% pool.</div>
<label for="ap-note">Personal note at the top of the email (optional)</label>
<textarea id="ap-note" name="note" maxlength="2000" rows="3">{{ f.note }}</textarea>
<label class="inline"><input type="checkbox" name="send_email" value="yes" checked> Email the signing link to {{ app.email }}</label><br>
<button type="submit"{{ ' disabled' if blocked else '' }}>Approve and send signing link</button>
</form>
</div>
<div class="doc" style="margin:0 0 16px;">
<h2>Reject</h2>
<form method="post" action="{{ url_for('affiliate_applications.reject') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="id" value="{{ app.id }}">
<label for="rj-reason">Reason (optional, included in the email)</label>
<textarea id="rj-reason" name="reason" maxlength="2000" rows="3">{{ f.reason }}</textarea>
<label class="inline"><input type="checkbox" name="send_email" value="yes" checked> Email {{ app.email }} a polite decline</label><br>
<button type="submit" class="danger">Reject</button>
</form>
<form method="post" action="{{ url_for('affiliate_applications.spam') }}" style="margin-top:6px;">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="hidden" name="id" value="{{ app.id }}">
<button type="submit" class="secondary">Mark as spam (no email)</button>
</form>
</div>
</div>
{% endif %}
""" + afa._FOOT

_COMPOSE_TMPL = _HEAD + _SUBNAV + """
<h1>Send a message to partners</h1>
<p class="muted">The message appears in each partner's dashboard <strong>Messages</strong> inbox and is emailed to them.
Partners who turned off "News from the TradeWave team" still get it in the inbox, just not by email.</p>

{% if preview %}
<div class="doc">
<h2>Check before you send</h2>
<p><span class="count">{{ preview.count }}</span> partner{{ '' if preview.count == 1 else 's' }} will get this
 &middot; <strong>{{ preview.audience }}</strong></p>
{% if preview.count %}
<p class="muted">{{ preview.email_count }} by email{% if preview.opted_out %}, {{ preview.opted_out }} in the inbox only (they turned these emails off){% endif %}.
First recipients: {{ preview.names|join(', ') }}{{ ' and more' if preview.count > preview.names|length else '' }}.</p>
<h3>How {{ preview.sample_name }} will see it</h3>
<table class="kv"><tr><td>Subject</td><td>{{ preview.subject }}</td></tr>
<tr><td>Message</td><td><pre class="msg">{{ preview.body }}</pre></td></tr></table>
<form method="post" action="{{ url_for('affiliate_messages.send') }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
{% for k in ('subject', 'body', 'audience', 'partner', 'terms', 'days', 'required') %}<input type="hidden" name="{{ k }}" value="{{ f.get(k, '') }}">{% endfor %}
<button type="submit">Send to {{ preview.count }} partner{{ '' if preview.count == 1 else 's' }}</button>
<span class="muted" style="margin-left:10px;">Or change it below and preview again.</span>
</form>
{% else %}
<div class="warn">Nobody matches that group, so there is nothing to send.</div>
{% endif %}
</div>
{% endif %}

<div class="doc">
<form method="post" action="{{ url_for('affiliate_messages.preview') }}" id="compose">
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<label for="m-aud">Send to</label>
<select id="m-aud" name="audience">
{% for key, label in audiences %}<option value="{{ key }}" {{ 'selected' if f.get('audience', 'active') == key else '' }}>{{ label }}</option>{% endfor %}
</select>
<span id="aud-one" class="aud-extra"><select name="partner" aria-label="Partner">
<option value="">Choose a partner</option>
{% for a in partners %}<option value="{{ a.id }}" {{ 'selected' if f.get('partner') == a.id|string else '' }}>{{ a.code }} - {{ a.name }} ({{ a.status }})</option>{% endfor %}
</select></span>
<span id="aud-terms" class="aud-extra"><select name="terms" aria-label="Terms version">
{% for t in terms %}<option value="{{ t.id }}" {{ 'selected' if f.get('terms') == t.id|string else '' }}>{{ t.version }}</option>{% endfor %}
</select></span>
<span id="aud-inactive" class="aud-extra"><input type="number" name="days" min="1" max="3650" value="{{ f.get('days') or 90 }}" aria-label="Days" style="width:90px;"> days</span>
<div class="muted" id="aud-count" aria-live="polite" style="margin-top:6px;">&nbsp;</div>

<label for="m-subject">Subject</label>
<input type="text" id="m-subject" name="subject" value="{{ f.get('subject', '') }}" maxlength="150" style="width:100%;box-sizing:border-box;" required>
<label for="m-body">Message (plain text)</label>
<textarea id="m-body" name="body" rows="10" maxlength="10000" required>{{ f.get('body', '') }}</textarea>
<div class="muted">You can use {{ placeholders|join(', ') }}. They are filled in for each partner. Links are made clickable.
The email adds "The TradeWave team" and the unsubscribe footer for you.</div>
<label class="inline" style="margin-top:12px;"><input type="checkbox" name="required" value="yes" {{ 'checked' if f.get('required') == 'yes' else '' }}>
 Program notice: email every recipient, even those who turned team news off (use for agreement or payment changes only)</label><br>
<button type="submit">Preview recipients</button>
</form>
</div>

<div class="doc">
<h2>Recent messages</h2>
{% if recent %}
<div class="scroll"><table class="cards">
<thead><tr><th>Sent</th><th>Subject</th><th>To</th><th class="num">Recipients</th><th class="num">Emailed</th><th class="num">Read</th><th></th></tr></thead>
<tbody>
{% for r in recent %}
<tr><td data-label="Sent">{{ r.message.created_at.strftime('%Y-%m-%d %H:%M UTC') if r.message.created_at else '' }}</td>
<td data-label="Subject"><span>{{ r.message.subject }}{% if r.message.required %} <span class="badge b-new">notice</span>{% endif %}</span></td>
<td data-label="To">{{ r.audience }}</td>
<td data-label="Recipients" class="num">{{ r.message.recipient_count }}</td>
<td data-label="Emailed" class="num">{{ r.counts.get('sent', 0) }}{% if r.counts.get('failed') %} <span class="err">({{ r.counts.get('failed') }} failed)</span>{% endif %}</td>
<td data-label="Read" class="num">{{ r.read }}</td>
<td data-label=""><a href="{{ url_for('affiliate_messages.log', id=r.message.id) }}">Details</a></td></tr>
{% endfor %}
</tbody></table></div>
{% else %}<p class="muted" style="margin:0;">No messages sent yet.</p>{% endif %}
</div>
<style>.aud-extra{display:none;margin-left:8px;}</style>
<script>
(function () {
  var sel = document.getElementById("m-aud"), out = document.getElementById("aud-count");
  var form = document.getElementById("compose");
  function refresh() {
    ["one", "terms", "inactive"].forEach(function (k) {
      document.getElementById("aud-" + k).style.display = sel.value === k ? "inline-block" : "none";
    });
    var q = new URLSearchParams({audience: sel.value, partner: form.partner.value,
                                 terms: form.terms.value, days: form.days.value});
    fetch("{{ url_for('affiliate_messages.count') }}?" + q.toString(), {credentials: "same-origin"})
      .then(function (r) { return r.json(); })
      .then(function (d) { out.textContent = d.error ? d.error : (d.count + (d.count === 1 ? " partner" : " partners") + " match right now."); })
      .catch(function () { out.textContent = ""; });
  }
  ["change", "input"].forEach(function (ev) {
    sel.addEventListener(ev, refresh); form.partner.addEventListener(ev, refresh);
    form.terms.addEventListener(ev, refresh); form.days.addEventListener(ev, refresh);
  });
  refresh();
})();
</script>
""" + afa._FOOT

_LOG_TMPL = _HEAD + _SUBNAV + """
<h1>{{ 'Message recipients' if message else 'Partner email log' }}</h1>
{% if message %}
<div class="doc"><table class="kv">
<tr><td>Subject</td><td>{{ message.subject }}</td></tr>
<tr><td>Sent</td><td>{{ message.created_at.strftime('%Y-%m-%d %H:%M UTC') if message.created_at else '' }} by {{ message.sent_by or '-' }}</td></tr>
<tr><td>To</td><td>{{ audience }} ({{ message.recipient_count }})</td></tr>
<tr><td>Message</td><td><pre class="msg">{{ message.body }}</pre></td></tr>
</table></div>
{% else %}
<p class="muted">Every message and automatic email, one row per partner per event (newest {{ rows|length }}).
"skipped" means it is in the partner's inbox but was not emailed: the reason is in the last column.</p>
{% endif %}
<div class="doc">
{% if rows %}
<div class="scroll"><table class="cards">
<thead><tr><th>When</th><th>Partner</th><th>Type</th><th>Subject</th><th>Email</th><th>Read</th><th>Note</th></tr></thead>
<tbody>
{% for n, code in rows %}
<tr><td data-label="When">{{ n.created_at.strftime('%Y-%m-%d %H:%M UTC') if n.created_at else '' }}</td>
<td data-label="Partner">{{ code }}</td>
<td data-label="Type">{{ labels.get(n.event_type, n.event_type) }}</td>
<td data-label="Subject">{{ n.subject }}</td>
<td data-label="Email"><span class="badge b-{{ n.email_status }}">{{ n.email_status }}</span></td>
<td data-label="Read">{{ 'Yes' if n.read_at else 'No' }}</td>
<td data-label="Note">{{ reasons.get(n.email_reason, n.email_reason or '') }}</td></tr>
{% endfor %}
</tbody></table></div>
{% else %}<p class="muted" style="margin:0;">Nothing sent yet.</p>{% endif %}
</div>
""" + afa._FOOT

REASON_LABELS = {
    "preference": "Partner turned this email off",
    "inbox_only": "Shown in the partner's Messages only (no email by design)",
    "no_email": "No email address on file",
    "email_not_configured": "Email sending is not set up on this server",
    "send_failed": "The email provider refused it (retried up to 3 times)",
}
STATUS_TABS = (("new", "New"), ("approved", "Approved"), ("rejected", "Rejected"),
               ("spam", "Spam"), ("all", "All"))


def make_views(auth_cls, *, audit_fn, current_user_fn):
    """Build the BaseViews. auth_cls is app._AdminAuth (super_admin gate)."""
    from flask import flash, jsonify, redirect, render_template_string, request, url_for
    from flask_admin import BaseView, expose
    from models import Affiliate, AffiliateApplication, AffiliateMessage

    def _S():
        import models
        return models.Session()

    def actor():
        u = current_user_fn()
        return "admin:%s" % (getattr(u, "email", None) or "unknown")

    def load_app(s, raw):
        try:
            return s.get(AffiliateApplication, uuid.UUID(str(raw)))
        except (ValueError, TypeError, AttributeError):
            return None

    # ----------------------------------------------------------- Applications
    class AffiliateApplicationsView(auth_cls, BaseView):
        @expose("/")
        def index(self):
            from sqlalchemy import func
            status = request.args.get("status") or "new"
            if status not in dict(STATUS_TABS):
                status = "new"
            s = _S()
            try:
                counts = dict(s.query(AffiliateApplication.status, func.count())
                              .group_by(AffiliateApplication.status).all())
                counts["all"] = sum(counts.values())
                q = s.query(AffiliateApplication)
                if status != "all":
                    q = q.filter(AffiliateApplication.status == status)
                apps = q.order_by(AffiliateApplication.created_at.desc()).limit(300).all()
                rows = [{"app": a, "flags": comms.application_flags(s, a)} for a in apps]
                return render_template_string(
                    _APPS_LIST_TMPL, title="Partner applications", errors=None, rows=rows,
                    status=status, tabs=STATUS_TABS, counts=counts,
                    sizes=comms.AUDIENCE_SIZE_LABEL)
            finally:
                s.close()

        def _view(self, s, app_row, form=None, errors=None, code=200):
            terms = afs.get_terms(s) or afs.DEFAULT_TERMS
            flags = comms.application_flags(s, app_row)
            partner = s.get(Affiliate, app_row.affiliate_id) if app_row.affiliate_id else None
            form = form or {}
            f = {"code": form.get("code") or comms.suggest_code(s, app_row.name),
                 "discount_pct": form.get("discount_pct") or afa.pct(comms.default_discount(terms)),
                 "note": form.get("note") or "", "reason": form.get("reason") or ""}
            blocked = flags["affiliate"] is not None and flags["affiliate"].status != "terminated"
            return render_template_string(
                _APP_VIEW_TMPL, title="Application - %s" % app_row.name, errors=errors,
                app=app_row, flags=flags, partner=partner, f=f, blocked=blocked,
                sizes=comms.AUDIENCE_SIZE_LABEL, terms_version=terms.version,
                terms_summary=afa.terms_summary(terms), pool=afa.pct(terms.pool_pct),
                max_discount=afa.pct(terms.max_discount_pct)), code

        @expose("/view")
        def view(self):
            s = _S()
            try:
                app_row = load_app(s, request.args.get("id"))
                if app_row is None:
                    flash("Application not found.", "error")
                    return redirect(url_for("affiliate_applications.index"))
                return self._view(s, app_row)
            finally:
                s.close()

        @expose("/approve", methods=["POST"])
        def approve(self):
            s = _S()
            try:
                app_row = load_app(s, request.form.get("id"))
                if app_row is None:
                    flash("Application not found.", "error")
                    return redirect(url_for("affiliate_applications.index"))
                try:
                    aff, emailed = comms.approve_application(
                        s, app_row, code=request.form.get("code"),
                        discount_pct=request.form.get("discount_pct"), actor=actor(),
                        note=request.form.get("note"),
                        send_email=request.form.get("send_email") == "yes")
                except comms.CommsError as e:
                    s.rollback()
                    return self._view(s, app_row, form=request.form, errors=e.errors, code=400)
                audit_fn(actor_label=actor(), action="affiliate_application_approved",
                         details={"application": str(app_row.id), "code": aff.code,
                                  "discount_pct": str(aff.discount_pct), "emailed": emailed})
                if emailed:
                    flash("Approved. %s is created (paused until signed) and the signing link "
                          "was emailed to %s." % (aff.code, aff.email), "success")
                else:
                    import affiliate_agreement as agr
                    flash("Approved. %s is created (paused until signed). The email was NOT "
                          "sent - copy this signing link and send it yourself: %s"
                          % (aff.code, agr.signing_url(aff)), "warning")
                return redirect(url_for("affiliate_applications.view", id=app_row.id))
            finally:
                s.close()

        @expose("/reject", methods=["POST"])
        def reject(self):
            s = _S()
            try:
                app_row = load_app(s, request.form.get("id"))
                if app_row is None:
                    flash("Application not found.", "error")
                    return redirect(url_for("affiliate_applications.index"))
                want_email = request.form.get("send_email") == "yes"
                try:
                    emailed = comms.reject_application(
                        s, app_row, actor=actor(), reason=request.form.get("reason"),
                        send_email=want_email)
                except comms.CommsError as e:
                    s.rollback()
                    return self._view(s, app_row, form=request.form, errors=e.errors, code=400)
                audit_fn(actor_label=actor(), action="affiliate_application_rejected",
                         details={"application": str(app_row.id), "emailed": emailed})
                if want_email and not emailed:
                    flash("Rejected, but the email to %s could NOT be sent." % app_row.email,
                          "warning")
                else:
                    flash("Rejected%s." % (" and %s was emailed" % app_row.email
                                           if emailed else " (no email sent)"), "success")
                return redirect(url_for("affiliate_applications.index"))
            finally:
                s.close()

        @expose("/spam", methods=["POST"])
        def spam(self):
            s = _S()
            try:
                app_row = load_app(s, request.form.get("id"))
                if app_row is not None:
                    try:
                        comms.mark_application_spam(s, app_row, actor())
                        flash("Marked as spam. No email was sent.", "success")
                    except comms.CommsError as e:
                        s.rollback()
                        flash(str(e), "error")
                return redirect(url_for("affiliate_applications.index"))
            finally:
                s.close()

    # --------------------------------------------------------------- Messages
    def audience_param(values):
        audience = values.get("audience") or ""
        param = {"one": values.get("partner"), "terms": values.get("terms"),
                 "inactive": values.get("days")}.get(audience)
        return audience, param

    class AffiliateMessagesView(auth_cls, BaseView):
        def _compose(self, s, form=None, errors=None, preview=None, code=200):
            return render_template_string(
                _COMPOSE_TMPL, title="Message partners", errors=errors, f=form or {},
                preview=preview, audiences=comms.AUDIENCES, terms=afs.list_terms(s),
                partners=s.query(Affiliate).order_by(Affiliate.code).all(),
                placeholders=comms.PLACEHOLDERS, recent=comms.message_log(s, limit=20)), code

        @expose("/")
        def index(self):
            s = _S()
            try:
                form = {}
                if request.args.get("partner"):
                    form = {"audience": "one", "partner": request.args.get("partner")}
                return self._compose(s, form=form)
            finally:
                s.close()

        @expose("/count")
        def count(self):
            s = _S()
            try:
                audience, param = audience_param(request.args)
                try:
                    n = len(comms.resolve_audience(s, audience, param))
                except comms.CommsError as e:
                    return jsonify({"count": 0, "error": str(e)})
                return jsonify({"count": n})
            finally:
                s.close()

        @expose("/preview", methods=["POST"])
        def preview(self):
            s = _S()
            try:
                form = request.form
                audience, param = audience_param(form)
                try:
                    subject, body = comms.validate_message(form.get("subject"), form.get("body"))
                    recipients = comms.resolve_audience(s, audience, param)
                except comms.CommsError as e:
                    return self._compose(s, form=form, errors=e.errors, code=400)
                required = form.get("required") == "yes"
                opted_out = 0
                if not required:
                    opted_out = sum(1 for a in recipients
                                    if "announcement" in comms.disabled_prefs(s, a.id))
                sample = recipients[0] if recipients else None
                preview = {
                    "count": len(recipients), "audience": comms.audience_text(s, audience, param),
                    "names": ["%s (%s)" % (a.code, a.name) for a in recipients[:10]],
                    "opted_out": opted_out, "email_count": len(recipients) - opted_out,
                    "sample_name": sample.name if sample else "",
                    "subject": comms.personalize(subject, sample) if sample else subject,
                    "body": comms.personalize(body, sample) if sample else body}
                return self._compose(s, form=form, preview=preview)
            finally:
                s.close()

        @expose("/send", methods=["POST"])
        def send(self):
            s = _S()
            try:
                form = request.form
                audience, param = audience_param(form)
                try:
                    msg, stats = comms.send_message(
                        s, subject=form.get("subject"), body=form.get("body"),
                        audience=audience, param=param,
                        required=form.get("required") == "yes", sent_by=actor())
                except comms.CommsError as e:
                    s.rollback()
                    return self._compose(s, form=form, errors=e.errors, code=400)
                audit_fn(actor_label=actor(), action="affiliate_message_sent",
                         details={"message": msg.id, "audience": audience, "param": param,
                                  "stats": stats})
                flash("Sent to %d partner%s: %d emailed, %d inbox only, %d failed."
                      % (stats["recipients"], "" if stats["recipients"] == 1 else "s",
                         stats["sent"], stats["skipped"], stats["failed"]),
                      "warning" if stats["failed"] else "success")
                return redirect(url_for("affiliate_messages.log", id=msg.id))
            finally:
                s.close()

        @expose("/log")
        def log(self):
            s = _S()
            try:
                message = None
                raw = request.args.get("id")
                if raw:
                    try:
                        message = s.get(AffiliateMessage, int(raw))
                    except (ValueError, TypeError):
                        message = None
                rows = comms.notification_log(
                    s, limit=500 if message else 200,
                    message_id=message.id if message else None)
                return render_template_string(
                    _LOG_TMPL, title="Partner email log", errors=None, message=message,
                    audience=(comms.audience_text(s, message.audience, message.audience_param)
                              if message else None),
                    rows=rows, labels=comms.EVENT_LABEL, reasons=REASON_LABELS)
            finally:
                s.close()

    return {"applications": AffiliateApplicationsView, "messages": AffiliateMessagesView}
