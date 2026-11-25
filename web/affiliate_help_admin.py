"""Partner help assistant - owner side (TW-TASK-0039 package A).

Two Flask-Admin screens (super_admin only, built like affiliate_admin's):
  - "Partner questions" (endpoint affiliate_help): the escalations and the
    answer page the notification email links to.
  - "Knowledge base" (endpoint affiliate_help_kb): edit / generalise /
    retire entries, and approve a model-proposed general version in one click.
Plus webhook_bp: the optional Resend inbound webhook for reply-by-email.

web/app.py registers all three. Logic lives in web/affiliate_help.py.
"""
import logging

from flask import Blueprint, request

import config
import affiliate_help as ah
from affiliate_admin import _FOOT, _HEAD

log = logging.getLogger("tw2.affiliate_help")

_NAV = """<style>
 .qa{white-space:pre-wrap;overflow-wrap:anywhere;}
 .chat{background:#f7f7fb;border:1px solid #e6e6ef;border-radius:8px;padding:10px 14px;font-size:13px;}
 .chat div{margin:4px 0;white-space:pre-wrap;overflow-wrap:anywhere;}
 .chat b{color:#3a32a8;}
 .proposal{background:#f0fbf4;border:1px solid #bfe6cb;border-radius:8px;padding:10px 14px;margin-top:8px;}
 .pill{white-space:nowrap;} .pill.partner{background:#fff4e5;color:#8a5a00;} .pill.retired{background:#eee;color:#666;}
 .pill.open{background:#fdeaea;color:#b00020;}
 form.inline{display:inline;} .actions button{margin:4px 6px 0 0;}
 textarea{min-height:140px;}
 @media (max-width:700px){ .wrap{padding:14px 12px 40px;} .doc{padding:16px 14px;}
   table.stack, table.stack tbody, table.stack tr, table.stack td{display:block;width:100%;box-sizing:border-box;}
   table.stack tr.h{display:none;} table.stack tr{border:1px solid #e1e4ec;border-radius:8px;margin:10px 0;}
   table.stack td{border:none;padding:6px 10px;}
   button,.btn{min-height:40px;} }
</style>
"""

_LIST_TMPL = _HEAD + _NAV + """
<h1>Partner questions</h1>
<p class="muted">Questions the partner help assistant could not answer from the guide, the agreement or the
knowledge base. Your answer goes to the partner's chat and email, and is saved to the knowledge base.</p>
{% if not model_ready %}<div class="warn">The assistant has no API key on this server (ANTHROPIC_TOKEN is not set),
so it cannot answer anything itself. Partners can still send questions to you from the chat.</div>{% endif %}
<div class="note">Reply by email is <strong>{{ 'on' if inbound else 'off' }}</strong>.
{% if not inbound %}The answer link in each notification email always works.{% endif %}
Notifications go to <strong>{{ support_email }}</strong>.</div>

<div class="doc"><h2>Waiting for an answer ({{ open|length }})</h2>
<table class="stack"><tr class="h"><th>#</th><th>Partner</th><th>Question</th><th>Asked</th><th></th></tr>
{% for e, a in open %}
<tr><td>{{ e.id }}</td><td><strong>{{ a.code if a else '?' }}</strong><br><span class="muted">{{ a.name if a else '' }}</span></td>
  <td class="qa">{{ e.question }}</td><td>{{ e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else '' }}</td>
  <td><a class="btn" style="margin-top:0" href="{{ url_for('affiliate_help.answer', id=e.id) }}">Answer</a></td></tr>
{% else %}<tr><td colspan="5">Nothing is waiting.</td></tr>{% endfor %}
</table></div>

<div class="doc"><h2>Recently closed</h2>
<table class="stack"><tr class="h"><th>#</th><th>Partner</th><th>Question</th><th>Answer</th><th>Closed</th></tr>
{% for e, a in closed %}
<tr><td>{{ e.id }}</td><td><strong>{{ a.code if a else '?' }}</strong></td><td class="qa">{{ e.question }}</td>
  <td class="qa">{% if e.status == 'dismissed' %}<span class="pill retired">closed without an answer</span>{% else %}{{ e.answer }}{% endif %}</td>
  <td>{{ e.answered_at.strftime('%Y-%m-%d') if e.answered_at else '' }}<br><span class="muted">{{ e.answered_via or '' }}</span></td></tr>
{% else %}<tr><td colspan="5">None yet.</td></tr>{% endfor %}
</table></div>
""" + _FOOT

_ANSWER_TMPL = _HEAD + _NAV + """
{% if not esc %}
  <div class="doc"><h2>This link is not valid</h2><p>The question was not found, or the link is damaged or has expired.
  <a href="{{ url_for('affiliate_help.index') }}">See all partner questions</a>.</p></div>
{% else %}
<h1>Partner question #{{ esc.id }}</h1>
<p class="muted">From <strong>{{ aff.code if aff else '?' }}</strong>{% if aff %} ({{ aff.name }}) &middot; status <strong>{{ aff.status }}</strong>
  &middot; {{ 'agreement signed' if aff.agreement_signed_at else 'agreement not signed' }}{% endif %}
  &middot; asked {{ esc.created_at.strftime('%Y-%m-%d %H:%M UTC') if esc.created_at else '' }}</p>

<div class="doc"><h2>The question</h2>
  <p class="qa" style="font-size:16px">{{ esc.question }}</p>
  {% if esc.reason %}<p class="muted">Why the assistant passed it on: {{ esc.reason }}</p>{% endif %}
  {% if esc.context %}<h3>Recent chat with this partner</h3>
  <div class="chat">{% for t in esc.context %}<div><b>{{ {'partner': 'Partner', 'assistant': 'Assistant', 'team': 'TradeWave team'}.get(t.role, 'Partner') }}:</b> {{ t.body }}</div>{% endfor %}</div>{% endif %}
</div>

{% if esc.status == 'open' %}
<div class="doc"><h2>Your answer</h2>
  <form method="post" action="{{ url_for('affiliate_help.answer') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ esc.id }}">
    <textarea name="answer" required maxlength="6000" placeholder="Write the answer exactly as the partner should read it.">{{ draft }}</textarea>
    <div class="note">When you send: the partner sees this answer in their Help chat and gets it by email, word for word.
      It is saved to the knowledge base as an answer for <strong>this partner only</strong>. You can make it general
      (for every partner) on the Knowledge base page.</div>
    <button type="submit">Send answer to {{ aff.code if aff else 'partner' }}</button>
  </form>
  <form method="post" action="{{ url_for('affiliate_help.dismiss') }}" style="margin-top:6px"
        onsubmit="return confirm('Close this question without answering? The partner is not told.');">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ esc.id }}">
    <button type="submit" class="secondary">Close without answering</button>
  </form>
</div>
{% else %}
<div class="doc"><h2>{{ 'Answered' if esc.status == 'answered' else 'Closed without an answer' }}</h2>
  {% if esc.answer %}<p class="qa">{{ esc.answer }}</p>{% endif %}
  <p class="muted">{{ esc.answered_by or '' }}{% if esc.answered_at %} &middot; {{ esc.answered_at.strftime('%Y-%m-%d %H:%M UTC') }}{% endif %}</p>
  {% if kb %}<p><a class="btn" href="{{ url_for('affiliate_help_kb.edit', id=kb.id) }}">Open the knowledge-base entry</a></p>{% endif %}
</div>
{% endif %}
{% endif %}
""" + _FOOT

_KB_TMPL = _HEAD + _NAV + """
<h1>Help knowledge base</h1>
<p class="muted">What the partner help assistant may answer from, next to the partner guide and the agreement.
A <strong>general</strong> entry is used for every partner. A <strong>partner only</strong> entry is used for that one partner.
A retired entry is not used at all.</p>

<div class="doc"><h2>Entries ({{ rows|length }})</h2>
<table class="stack"><tr class="h"><th>Question and answer</th><th>Used for</th><th>Actions</th></tr>
{% for k, a in rows %}
<tr><td><strong class="qa">{{ k.question }}</strong><div class="qa" style="margin-top:4px">{{ k.answer }}</div>
    <div class="muted" style="margin-top:4px">{{ 'From a partner question' if k.source == 'escalation' else 'Written by you' }}
      &middot; updated {{ k.updated_at.strftime('%Y-%m-%d') if k.updated_at else '' }}</div>
    {% if k.proposed_answer and k.status == 'active' %}
    <div class="proposal"><strong>Suggested general version</strong> (partner details removed by the assistant)
      <div class="qa" style="margin-top:6px"><b>Q:</b> {{ k.proposed_question }}</div>
      <div class="qa"><b>A:</b> {{ k.proposed_answer }}</div>
      <div class="actions">
      <form class="inline" method="post" action="{{ url_for('affiliate_help_kb.approve') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ k.id }}">
        <button class="small" type="submit">Approve for all partners</button></form>
      <form class="inline" method="post" action="{{ url_for('affiliate_help_kb.discard') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ k.id }}">
        <button class="small secondary" type="submit">Discard suggestion</button></form></div>
    </div>{% endif %}</td>
  <td>{% if k.status == 'retired' %}<span class="pill retired">retired</span>
      {% elif k.scope == 'general' %}<span class="pill">all partners</span>
      {% else %}<span class="pill partner">{{ a.code if a else 'one partner' }} only</span>{% endif %}</td>
  <td class="actions"><a class="btn" style="margin-top:0;padding:4px 10px;font-size:12px" href="{{ url_for('affiliate_help_kb.edit', id=k.id) }}">Edit</a>
    {% if k.status == 'active' and k.scope == 'partner' %}
    <form class="inline" method="post" action="{{ url_for('affiliate_help_kb.generalise') }}"
          onsubmit="return confirm('Use this entry, exactly as written, for every partner?');">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ k.id }}">
      <button class="small secondary" type="submit">Make general as written</button></form>
    {% if not k.proposed_answer %}
    <form class="inline" method="post" action="{{ url_for('affiliate_help_kb.propose') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ k.id }}">
      <button class="small secondary" type="submit">Suggest a general version</button></form>{% endif %}
    {% endif %}
    <form class="inline" method="post" action="{{ url_for('affiliate_help_kb.status') }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ k.id }}">
      <input type="hidden" name="status" value="{{ 'active' if k.status == 'retired' else 'retired' }}">
      <button class="small secondary" type="submit">{{ 'Restore' if k.status == 'retired' else 'Retire' }}</button></form></td></tr>
{% else %}<tr><td colspan="3">No entries yet. Add one below, or answer a partner question.</td></tr>{% endfor %}
</table></div>

<div class="doc"><h2>Add an entry for all partners</h2>
<form method="post" action="{{ url_for('affiliate_help_kb.create') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <label>Question <input type="text" name="question" style="width:100%;box-sizing:border-box" maxlength="1500" value="{{ f.get('question', '') }}" required></label>
  <label>Answer <textarea name="answer" maxlength="6000" required>{{ f.get('answer', '') }}</textarea></label>
  <button type="submit">Add entry</button>
</form></div>
""" + _FOOT

_KB_EDIT_TMPL = _HEAD + _NAV + """
{% if not kb %}<div class="doc">Entry not found. <a href="{{ url_for('affiliate_help_kb.index') }}">Back to the knowledge base</a></div>
{% else %}
<h1>Edit knowledge-base entry #{{ kb.id }}</h1>
<p class="muted">{{ 'From a partner question' if kb.source == 'escalation' else 'Written by you' }}
  {% if aff %}&middot; partner <strong>{{ aff.code }}</strong>{% endif %}
  &middot; {{ 'retired' if kb.status == 'retired' else 'in use' }}</p>
<div class="doc">
<form method="post" action="{{ url_for('affiliate_help_kb.edit') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="id" value="{{ kb.id }}">
  <label>Question <input type="text" name="question" style="width:100%;box-sizing:border-box" maxlength="1500" value="{{ f.get('question', kb.question) }}" required></label>
  <label>Answer <textarea name="answer" maxlength="6000" required>{{ f.get('answer', kb.answer) }}</textarea></label>
  <label>Used for
    <select name="scope">
      <option value="general"{% if kb.scope == 'general' %} selected{% endif %}>All partners (general)</option>
      {% if kb.affiliate_id %}<option value="partner"{% if kb.scope == 'partner' %} selected{% endif %}>Only {{ aff.code if aff else 'this partner' }}</option>{% endif %}
    </select></label>
  {% if kb.scope == 'partner' %}<div class="note">Before choosing "All partners", remove anything that is only true for
    {{ aff.code if aff else 'this partner' }}: names, codes, amounts, dates.</div>{% endif %}
  <button type="submit">Save</button>
  <a href="{{ url_for('affiliate_help_kb.index') }}" style="margin-left:12px">Cancel</a>
</form></div>
{% endif %}
""" + _FOOT


def make_views(auth_cls, *, audit_fn, current_user_fn):
    """Build the two BaseViews (same contract as affiliate_admin.make_views)."""
    from flask import flash, redirect, render_template_string, url_for
    from flask_admin import BaseView, expose
    from affiliate_help_models import AffiliateHelpEscalation as E, AffiliateHelpKb as K
    from models import Affiliate

    def _S():
        import models
        return models.Session()

    def actor():
        u = current_user_fn()
        return "admin:%s" % (getattr(u, "email", None) or "unknown")

    def _int(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _affs(s, rows):
        ids = {r.affiliate_id for r in rows if r.affiliate_id}
        by = {a.id: a for a in s.query(Affiliate).filter(Affiliate.id.in_(ids)).all()} if ids else {}
        return [(r, by.get(r.affiliate_id)) for r in rows]

    class HelpQuestionsView(auth_cls, BaseView):
        @expose("/")
        def index(self):
            s = _S()
            try:
                open_rows = s.query(E).filter(E.status == "open").order_by(E.created_at).all()
                closed = (s.query(E).filter(E.status != "open")
                          .order_by(E.answered_at.desc()).limit(50).all())
                return render_template_string(
                    _LIST_TMPL, title="Partner questions", errors=None,
                    open=_affs(s, open_rows), closed=_affs(s, closed),
                    inbound=ah.inbound_enabled(), support_email=ah.owner_email(),
                    model_ready=bool((getattr(config, "anthropic_token", "") or "").strip()))
            finally:
                s.close()

        def _page(self, s, esc, draft="", errors=None):
            aff = s.get(Affiliate, esc.affiliate_id) if esc is not None else None
            kb = (s.query(K).filter(K.escalation_id == esc.id).first() if esc is not None else None)
            return render_template_string(_ANSWER_TMPL, title="Answer a partner question",
                                          esc=esc, aff=aff, kb=kb, draft=draft, errors=errors)

        @expose("/answer", methods=["GET", "POST"])
        def answer(self):
            """GET ?t=<signed token> (the email link) or ?id=<n> (the list).
            Either way the super_admin gate applies: the token only says
            WHICH question, it is never a login."""
            s = _S()
            try:
                if request.method == "GET":
                    eid = (ah.verify_answer_token(request.args.get("t"))
                           if request.args.get("t") else _int(request.args.get("id")))
                    return self._page(s, s.get(E, eid) if eid is not None else None)
                esc = s.get(E, _int(request.form.get("id")) or 0)
                if esc is None:
                    return self._page(s, None)
                try:
                    ah.answer_escalation(s, esc, request.form.get("answer"), actor())
                except ah.HelpError as e:
                    s.rollback()
                    return self._page(s, esc, draft=request.form.get("answer") or "", errors=[str(e)])
                audit_fn(actor_label=actor(), action="affiliate_help_answered",
                         details={"escalation_id": esc.id})
                flash("Answer sent. It is in the partner's chat, emailed to them, and saved to "
                      "the knowledge base for this partner.", "success")
                return redirect(url_for("affiliate_help.answer", id=esc.id))
            finally:
                s.close()

        @expose("/dismiss", methods=["POST"])
        def dismiss(self):
            s = _S()
            try:
                esc = s.get(E, _int(request.form.get("id")) or 0)
                if esc is not None:
                    try:
                        ah.dismiss_escalation(s, esc, actor())
                        audit_fn(actor_label=actor(), action="affiliate_help_dismissed",
                                 details={"escalation_id": esc.id})
                        flash("Question closed without an answer.", "success")
                    except ah.HelpError as e:
                        s.rollback()
                        flash(str(e), "error")
                return redirect(url_for("affiliate_help.index"))
            finally:
                s.close()

    class HelpKbView(auth_cls, BaseView):
        def _list(self, s, form=None, errors=None):
            rows = s.query(K).order_by(K.status, K.updated_at.desc(), K.id.desc()).limit(500).all()
            return render_template_string(_KB_TMPL, title="Help knowledge base", rows=_affs(s, rows),
                                          f=form or {}, errors=errors)

        @expose("/")
        def index(self):
            s = _S()
            try:
                return self._list(s)
            finally:
                s.close()

        @expose("/create", methods=["POST"])
        def create(self):
            s = _S()
            try:
                try:
                    kb = ah.create_kb(s, request.form.get("question"), request.form.get("answer"), actor())
                except ah.HelpError as e:
                    s.rollback()
                    return self._list(s, form=request.form, errors=[str(e)])
                audit_fn(actor_label=actor(), action="affiliate_help_kb_created", details={"kb_id": kb.id})
                flash("Entry added. The assistant uses it from now on.", "success")
                return redirect(url_for("affiliate_help_kb.index"))
            finally:
                s.close()

        @expose("/edit", methods=["GET", "POST"])
        def edit(self):
            s = _S()
            try:
                kb = s.get(K, _int(request.values.get("id")) or 0)
                aff = s.get(Affiliate, kb.affiliate_id) if kb is not None and kb.affiliate_id else None
                errors, form = None, {}
                if request.method == "POST" and kb is not None:
                    try:
                        ah.update_kb(s, kb, request.form.get("question"), request.form.get("answer"),
                                     request.form.get("scope"), actor())
                        audit_fn(actor_label=actor(), action="affiliate_help_kb_edited",
                                 details={"kb_id": kb.id, "scope": kb.scope})
                        flash("Saved.", "success")
                        return redirect(url_for("affiliate_help_kb.index"))
                    except ah.HelpError as e:
                        s.rollback()
                        errors, form = [str(e)], request.form
                return render_template_string(_KB_EDIT_TMPL, title="Edit knowledge-base entry",
                                              kb=kb, aff=aff, f=form, errors=errors)
            finally:
                s.close()

        def _act(self, fn, done, action):
            s = _S()
            try:
                kb = s.get(K, _int(request.form.get("id")) or 0)
                if kb is None:
                    flash("Entry not found.", "error")
                else:
                    try:
                        msg = fn(s, kb)
                        audit_fn(actor_label=actor(), action=action, details={"kb_id": kb.id})
                        flash(msg or done, "success")
                    except ah.HelpError as e:
                        s.rollback()
                        flash(str(e), "error")
                    except ah.AssistantUnavailable:
                        s.rollback()
                        flash("The assistant is not available right now. Edit the entry by hand instead.",
                              "error")
                return redirect(url_for("affiliate_help_kb.index"))
            finally:
                s.close()

        @expose("/approve", methods=["POST"])
        def approve(self):
            return self._act(lambda s, kb: ah.approve_proposal(s, kb, actor()),
                             "Approved. The general version is now used for every partner.",
                             "affiliate_help_kb_approved")

        @expose("/discard", methods=["POST"])
        def discard(self):
            return self._act(lambda s, kb: ah.discard_proposal(s, kb, actor()),
                             "Suggestion discarded. The entry stays for this partner only.",
                             "affiliate_help_kb_proposal_discarded")

        @expose("/generalise", methods=["POST"])
        def generalise(self):
            return self._act(lambda s, kb: ah.update_kb(s, kb, kb.question, kb.answer, "general", actor()),
                             "This entry is now used for every partner.", "affiliate_help_kb_generalised")

        @expose("/propose", methods=["POST"])
        def propose(self):
            def run(s, kb):
                # The model call runs in the background job runner, not here.
                if ah.queue_proposal(s, kb, actor()) is None:
                    raise ah.AssistantUnavailable("no_key")
                return ("Asked the assistant for a general version. It appears below the entry "
                        "within a few minutes if the answer can be made general.")
            return self._act(run, None, "affiliate_help_kb_proposed")

        @expose("/status", methods=["POST"])
        def status(self):
            target = request.form.get("status")
            return self._act(lambda s, kb: ah.set_kb_status(s, kb, target, actor()),
                             "Entry retired. The assistant no longer uses it." if target == "retired"
                             else "Entry restored.", "affiliate_help_kb_status")

    return {"questions": HelpQuestionsView, "kb": HelpKbView}


# ---------------------------------------------------------------------------
# reply-by-email webhook (optional)
# ---------------------------------------------------------------------------
webhook_bp = Blueprint("affiliate_help_webhook", __name__)


@webhook_bp.route("/webhooks/resend/affiliate-help", methods=["POST"])
def resend_inbound():
    """Resend 'email.received' -> the owner's reply answers the escalation.

    Feature OFF (404) unless the inbound secret and address are configured.
    Auth is the Svix signature over the raw body; the escalation is found
    from the signed token in the reply-to address; the sender must be an
    allowed owner address. Always 200 after a valid signature so Resend does
    not retry a reply we deliberately ignored."""
    if not ah.inbound_enabled():
        return ("", 404)
    if (request.content_length or 0) > 512 * 1024:
        return ("", 413)
    body = request.get_data(cache=False)
    if not ah.verify_webhook(config.AFFILIATE_HELP_INBOUND_SECRET, request.headers, body):
        return ("", 403)
    import json
    import models
    try:
        event = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ("", 400)
    s = models.Session()
    try:
        result = ah.handle_inbound(s, event if isinstance(event, dict) else {})
    except Exception as e:   # noqa: BLE001
        s.rollback()
        log.exception("help: inbound webhook failed: %s", type(e).__name__)
        return ("", 500)
    finally:
        s.close()
    log.info("help: inbound reply result=%s", result)
    return ({"ok": True, "result": result}, 200)
