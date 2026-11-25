"""Owner screens of the partner program (TW-TASK-0039, fix-0039).

Two Flask-Admin BaseViews, built by make_views() and registered in web/app.py:

  home        /admin/affiliate_home/        "Partner program": live counts of
              everything waiting for the owner, each linking to its page.
              First item of the Affiliates menu.
  tax_report  /admin/affiliate_tax_report/  what was paid per partner in a
              calendar year, with a CSV for the accountant.

Plus payout_flags_html(), the "Fraud signals" cell of the Payout Ledger list.
All logic is in web/affiliate_owner.py. No em-dashes in any UI string.
"""
from __future__ import annotations

import logging

import affiliate_ops_admin as oa
import affiliate_owner as owner
import affiliate_service as afs

log = logging.getLogger("tw2.affiliate_owner_admin")

_STYLE = """<style>
 .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px;margin:16px 0;}
 a.card{display:block;background:#fff;border:1px solid #e3e6ee;border-radius:12px;padding:16px 18px;text-decoration:none;color:#1f2a44;}
 a.card:hover{border-color:#4f46e5;box-shadow:0 2px 8px rgba(79,70,229,.12);}
 a.card .n{font-size:34px;font-weight:800;line-height:1.1;color:#3a32a8;font-variant-numeric:tabular-nums;}
 a.card .t{font-weight:700;margin-top:2px;} a.card .d{font-size:13px;color:#666;margin-top:4px;}
 a.card.zero .n{color:#9aa0b4;} a.card.urgent{border-color:#f0b4b4;background:#fff8f8;} a.card.urgent .n{color:#b00020;}
 a.card .go{font-size:12px;font-weight:700;color:#4f46e5;margin-top:8px;display:block;}
 .facts td:first-child{width:220px;color:#555;background:#fafafc;}
 @media (max-width:640px){.cards{grid-template-columns:1fr 1fr;gap:10px;} a.card{padding:12px;} a.card .n{font-size:26px;}
  .facts td:first-child{width:120px;}}
 @media (max-width:380px){.cards{grid-template-columns:1fr;}}
</style>"""

_HOME_TMPL = oa._HEAD + _STYLE + """
<h1>Partner program</h1>
<p class="muted">What needs you today. Every number is live and opens the page where you act on it.</p>
<div class="cards">
{% for c in cards %}
<a class="card{{ ' urgent' if c.urgent else '' }}{{ ' zero' if not c.count else '' }}" href="{{ c.url }}" id="card-{{ c.key }}">
 <div class="n">{{ c.count }}</div><div class="t">{{ c.title }}</div><div class="d">{{ c.detail }}</div>
 <span class="go">Open &rarr;</span></a>
{% endfor %}
</div>

<div class="doc" id="activity"><h2>Activity deadline</h2>
{% if activity %}
 <div class="scroll"><table>
  <tr><th>Partner</th><th>State</th><th>Date</th><th class="num">Days left</th></tr>
  {% for a in activity %}
  <tr><td><strong>{{ a.code }}</strong> {{ a.name }}</td>
   <td>{% if a.state == 'closing' %}<span class="pill warnp">Renewal commissions stop soon</span>{% else %}<span class="pill bad">Lapsed</span>{% endif %}</td>
   <td>{{ a.date.strftime('%d %b %Y') }}</td><td class="num">{{ a.days if a.state == 'closing' else '-' }}</td></tr>
  {% endfor %}
 </table></div>
 <p class="muted">A partner keeps renewal commissions while they bring at least one new paying customer in the activity
 window. They are warned by email 60, 30 and 7 days before it ends.</p>
{% else %}<p class="muted" style="margin:0;">Nobody is close to the deadline.</p>{% endif %}
</div>

<div class="doc"><h2>Settings at a glance</h2>
 <div class="scroll"><table class="facts">
  <tr><td>Owner notices go to</td><td><strong>{{ owner_email or 'nobody - set AFFILIATE_OWNER_EMAIL' }}</strong>
   <span class="muted">(AFFILIATE_OWNER_EMAIL in secrets.env: applications, partner questions, tax forms, the monthly summary and the 48-hour digest)</span></td></tr>
  <tr><td>Auto-approve applications</td><td><strong>{{ auto_approve }}</strong> - <a href="/admin/affiliate_applications/#auto-approve">change</a></td></tr>
  <tr><td>Referral link is remembered for</td><td><strong>{{ window_days }} days</strong> <span class="muted">(first-touch cookie)</span></td></tr>
  <tr><td>Payout minimum</td><td><strong>{{ minimum }}</strong></td></tr>
  <tr><td>Background jobs</td><td>{{ jobs.queued + jobs.running }} waiting{% if jobs.failed %}, <span class="err">{{ jobs.failed }} failed</span> (see <span class="mono">python web/affiliate_jobs.py --list</span>){% endif %}
   <span class="muted">(group messages and suggested general answers are sent by a job every 2 minutes)</span></td></tr>
 </table></div>
</div>
""" + oa._FOOT

_TAX_REPORT_TMPL = oa._HEAD + """
<h1>Year-end tax report</h1>
<p class="muted">What was <strong>paid</strong> to each partner in a calendar year (by the date the payout was marked paid, UTC),
per currency. For your accountant: it does not file anything.</p>
<form method="get" action="{{ url_for('affiliate_tax_report.index') }}" style="margin:8px 0 0;">
 <label for="year" style="display:inline;">Year</label>
 <select id="year" name="year" onchange="this.form.submit()">
  {% for y in years %}<option value="{{ y }}"{% if y == report.year %} selected{% endif %}>{{ y }}</option>{% endfor %}
 </select>
 <noscript><button type="submit" class="small">Show</button></noscript>
 <a class="btn secondary" style="margin-left:10px;" href="{{ url_for('affiliate_tax_report.csv', year=report.year) }}">Download CSV ({{ report.year }})</a>
</form>
<div class="doc"><h2>{{ report.year }}: {{ report.partners }} partner{{ '' if report.partners == 1 else 's' }} paid
 {% for c, a in report.totals %}<span class="pill">{{ '{:,.2f}'.format(a) }} {{ c|upper }}</span> {% endfor %}
 {% if report.nec_count %}<span class="pill warnp">{{ report.nec_count }} likely 1099-NEC</span>{% endif %}</h2>
{% if report.rows %}
 <div class="scroll"><table>
  <tr><th>Partner</th><th>Country</th><th>Tax form</th><th>Currency</th><th class="num">Total paid</th><th class="num">Payouts</th><th>1099-NEC</th><th>Note</th></tr>
  {% for r in report.rows %}
  <tr><td><strong>{{ r.code }}</strong> {{ r.name }}<div class="muted">{{ r.email }}</div></td>
   <td>{{ r.country or '-' }}</td>
   <td>{% if r.form %}{{ r.form_label }}{% else %}<span class="err">None on file</span>{% endif %}</td>
   <td>{{ r.currency|upper }}</td><td class="num"><strong>{{ '{:,.2f}'.format(r.total) }}</strong></td>
   <td class="num">{{ r.payouts }}</td>
   <td>{% if r.nec %}<span class="pill warnp">Likely</span>{% else %}<span class="muted">No</span>{% endif %}</td>
   <td>{{ r.note }}</td></tr>
  {% endfor %}
 </table></div>
{% else %}<p class="muted" style="margin:0;">No payouts were marked paid in {{ report.year }}.</p>{% endif %}
 <p class="muted">"1099-NEC likely" marks a partner with a <strong>W-9</strong> on file who was paid <strong>${{ nec_threshold }} or more
 in USD</strong> in the year. It is a prompt for your accountant, not tax advice: corporations and payments made through a
 third-party network such as PayPal can be exempt. Country is what the partner entered on their application (blank for a
 partner you added by hand). Rows that were carried forward or forfeited are not payments and are left out.</p>
</div>
""" + oa._FOOT


def payout_flags_html(session, payout) -> str:
    """The "Fraud signals" cell of one Payout Ledger row: a short label per
    signal with the reason as its tooltip, or '' when there is none. Cached
    per request on flask.g (one query set for the whole list)."""
    from flask import g
    from markupsafe import Markup, escape
    cache = getattr(g, "_tw_fraud_signals", None)
    if cache is None:
        try:
            cache = owner.fraud_signals(session)
        except Exception:   # noqa: BLE001  (a flag column must never break the ledger)
            log.exception("fraud signals failed")
            cache = {}
        g._tw_fraud_signals = cache
    flags = cache.get(payout.affiliate_id) or []
    if not flags:
        return ""
    return Markup(" ".join(
        '<span title="%s" style="display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;'
        'border-radius:12px;background:#fff1e6;color:#9a4a00;border:1px solid #f3cfa8;white-space:nowrap;">%s</span>'
        % (escape(f["reason"]), escape(f["label"])) for f in flags))


def make_views(auth_cls, *, audit_fn, current_user_fn):
    """Build the BaseViews. auth_cls is app._AdminAuth (super_admin gate)."""
    from flask import Response, render_template_string, request
    from flask_admin import BaseView, expose

    def _S():
        import models
        return models.Session()

    def actor():
        u = current_user_fn()
        return "admin:%s" % (getattr(u, "email", None) or "unknown")

    class ProgramHomeView(auth_cls, BaseView):
        @expose("/")
        def index(self):
            import affiliate_admin as afa
            s = _S()
            try:
                data = owner.program_counts(s)
                return render_template_string(
                    _HOME_TMPL, title="Partner program", window_days=afs.attribution_window_days(),
                    minimum=afa.money(afa.payout_minimum_cents()), **data)
            finally:
                s.close()

    class TaxReportView(auth_cls, BaseView):
        def _year(self, s):
            years = owner.tax_years(s)
            try:
                year = int(request.args.get("year") or years[0])
            except (TypeError, ValueError):
                year = years[0]
            if not 2000 <= year <= 2100:
                year = years[0]
            if year not in years:
                years = sorted(set(years) | {year}, reverse=True)
            return year, years

        @expose("/")
        def index(self):
            s = _S()
            try:
                year, years = self._year(s)
                return render_template_string(
                    _TAX_REPORT_TMPL, title="Year-end tax report", years=years,
                    report=owner.tax_year_report(s, year),
                    nec_threshold="{:,.0f}".format(owner.NEC_THRESHOLD))
            finally:
                s.close()

        @expose("/csv")
        def csv(self):
            s = _S()
            try:
                year, _years = self._year(s)
                report = owner.tax_year_report(s, year)
                text = owner.tax_year_csv(report)
            finally:
                s.close()
            audit_fn(actor_user_id=getattr(current_user_fn(), "id", None), actor_label=actor(),
                     action="affiliate_tax_report_exported",
                     details={"year": year, "rows": len(report["rows"])})
            return Response(text, mimetype="text/csv; charset=utf-8", headers={
                "Content-Disposition": 'attachment; filename="%s"' % owner.tax_report_filename(year),
                "Cache-Control": "private, no-store"})

    return {"home": ProgramHomeView, "tax_report": TaxReportView}
