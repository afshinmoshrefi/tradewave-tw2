"""Self-serve payout details on the partner dashboard Payouts page.

The partner sets PayPal / Wise, the payout email and the account holder name.
Changing details that were already on file: confirmation email to the ACCOUNT
email (old destination masked), an audit_log row, and a 24-hour payout hold
enforced by the existing mark-paid / export gate.

Hermetic: SQLite copy of the affiliate tables, fake email, the real blueprint
(tests/affiliate_portal_harness.py)."""
import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affiliate_portal_harness as h  # noqa: E402

pytestmark = pytest.mark.unit

UTC = dt.timezone.utc
BASE = "/account/affiliate"
EM_DASH = "—"
ACTION = "affiliate_payout_details_changed"


@pytest.fixture
def env(monkeypatch):
    import config
    import email_utils
    monkeypatch.setattr(h, "TABLES", h.all_tables())
    db, factory, engine = h.make_db()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE UNIQUE INDEX uq_notif ON affiliate_notifications "
                             "(affiliate_id, event_key)")
    outbox = []

    def fake_send(to, subject, body_text, from_addr=None, reply_to=None, html=None, headers=None):
        outbox.append(SimpleNamespace(to=to, subject=subject, text=body_text, html=html))
        return True

    monkeypatch.setattr(email_utils, "resend_send_email", fake_send)
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test_key", raising=False)
    monkeypatch.setattr(config, "WORKOS_COOKIE_PASSWORD", "unit-only-cookie-password", raising=False)
    monkeypatch.setattr(config, "tw2_public_url", "https://tw.test/", raising=False)
    state = SimpleNamespace(user=None, catalog=h.CATALOG)
    h.fake_stripe(monkeypatch.setattr)
    app = h.make_app(monkeypatch.setattr, factory, state)
    notes = []
    from affiliate_portal import routes
    monkeypatch.setattr(routes, "_notify_operator", lambda subject, body: notes.append((subject, body)))
    yield SimpleNamespace(db=db, factory=factory, state=state, app=app, client=app.test_client(),
                          outbox=outbox, notes=notes, patch=monkeypatch.setattr)
    db.close()
    engine.dispose()


def save(env, method="paypal", email="new@pay.example", name=""):
    return env.client.post(BASE + "/payouts/details", data={
        "payout_method": method, "payout_email": email, "payout_account_name": name})


def page(env):
    return env.client.get(BASE + "/payouts").get_data(as_text=True)


def flashes(env):
    with env.client.session_transaction() as sess:
        return [m for _c, m in sess.get("_flashes", [])]


def audits(env):
    import models
    env.db.expire_all()
    return env.db.query(models.AuditLog).filter(models.AuditLog.action == ACTION).all()


def fresh(env, aff):
    import models
    env.db.expire_all()
    return env.db.get(models.Affiliate, aff.id)


def pending_payout(env, aff, amount="80.00"):
    import models
    p = models.AffiliatePayout(affiliate_id=aff.id, period_start=dt.date(2026, 10, 1),
                               period_end=dt.date(2026, 10, 31), currency="usd",
                               gross_revenue=Decimal("400"), commission_amount=Decimal(amount),
                               status="pending", locked=False)
    env.db.add(p)
    env.db.commit()
    return p


# ---------------------------------------------------------------------------
# first-time setup
# ---------------------------------------------------------------------------
class TestFirstTimeSetup:
    def test_page_shows_the_form_and_no_longer_says_to_email(self, env):
        aff, user = h.seed_empty(env.db)
        env.state.user = user
        html = page(env)
        assert 'action="/account/affiliate/payouts/details"' in html
        for field in ('name="payout_method"', 'name="payout_email"', 'name="payout_account_name"'):
            assert field in html
        assert '<option value="paypal">PayPal</option>' in html
        assert '<option value="wise">Wise</option>' in html
        assert "To change payout details, contact" not in html
        assert "Contact help@tradewave.ai to add your PayPal" not in html
        assert "Add your PayPal or Wise details in the Payout details form" in html
        assert "<details" not in html.split('id="payout-details"')[1].split('id="tax-form"')[0]
        assert EM_DASH not in html

    def test_first_save_stores_details_without_a_hold(self, env):
        aff, user = h.seed_empty(env.db)
        env.state.user = user
        r = save(env, "paypal", "  nadia@pay.example ")
        assert r.status_code == 302 and r.headers["Location"].endswith("/payouts#payout-details")
        live = fresh(env, aff)
        assert (live.payout_method, live.payout_email) == ("paypal", "nadia@pay.example")
        assert live.payout_account_name is None
        assert live.payout_details_changed_at is None            # nothing was replaced: no hold
        assert "Saved. We sent a confirmation to newbie@partner.example." in flashes(env)[-1]
        row, = audits(env)
        assert row.actor_user_id == user.id and row.target_user_id == user.id
        assert row.details["first_time"] is True and row.details["old_email"] is None
        assert row.details["new_email"] == "nadia@pay.example" and row.details["hold_until"] is None
        mail, = env.outbox
        assert mail.to == "newbie@partner.example"               # the ACCOUNT email
        assert mail.subject == "Your payout details were added"
        assert "PayPal, n***a@pay.example" in mail.text and "nadia@pay.example" not in mail.text
        assert "If you did not make this change" in mail.text and EM_DASH not in mail.text
        assert env.notes == []                                   # the owner is told about changes only
        html = page(env)
        assert "nadia@pay.example" in html and "Payouts are on hold" not in html
        assert "Change payout details" in html                   # the form folds away once set

    def test_checklist_item_turns_done(self, env):
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_empty(env.db)
        env.state.user = user
        assert dash.payout_checklist(aff, {})["items"][1]["ok"] is False
        save(env, "wise", "nadia@pay.example", "Nadia Okafor")
        live = fresh(env, aff)
        check = dash.payout_checklist(live, {})
        assert check["items"][1]["ok"] is True and check["hold_until"] is None
        assert live.payout_account_name == "Nadia Okafor"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
class TestValidation:
    @pytest.mark.parametrize("method,email,name,message", [
        ("", "a@b.example", "", "Choose PayPal or Wise."),
        ("bank", "a@b.example", "", "Choose PayPal or Wise."),
        ("paypal", "", "", "Enter the email address of your PayPal account."),
        ("paypal", "not-an-email", "", "That email address does not look right"),
        ("paypal", "a@b", "", "That email address does not look right"),
        ("paypal", "a b@c.example", "", "That email address does not look right"),
        ("paypal", "<a@b.example>", "", "That email address does not look right"),
        ("wise", "a@b.example", "", "Enter the account holder name exactly as it is on your Wise"),
        ("wise", "a@b.example", "<b>Nadia</b>", "Enter the account holder name as plain text."),
        ("paypal", "a@b.example", "x" * 121, "The account holder name is too long"),
    ])
    def test_bad_input_saves_nothing(self, env, method, email, name, message):
        aff, user = h.seed_empty(env.db)
        env.state.user = user
        assert save(env, method, email, name).status_code == 302
        assert message in flashes(env)[-1]
        live = fresh(env, aff)
        assert live.payout_method is None and live.payout_email is None
        assert audits(env) == [] and env.outbox == []

    def test_only_the_linked_login_can_save(self, env):
        import models
        aff, user = h.seed_empty(env.db)
        env.state.user = user
        env.client.get(BASE + "/payouts")
        from affiliate_portal import routes
        env.patch(routes, "_is_owner", lambda live: False)
        save(env)
        assert "Only the account owner can change payout details." in flashes(env)[-1]
        assert fresh(env, aff).payout_email is None and audits(env) == []
        assert env.db.query(models.AffiliateNotification).count() == 0

    def test_logged_out_is_sent_to_login(self, env):
        r = save(env)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_csrf_token_is_required(self, env, monkeypatch):
        aff, user = h.seed_empty(env.db)
        state = SimpleNamespace(user=user, catalog=h.CATALOG)
        app = h.make_app(monkeypatch.setattr, env.factory, state, csrf=True)
        r = app.test_client().post(BASE + "/payouts/details", data={
            "payout_method": "paypal", "payout_email": "x@pay.example"})
        assert r.status_code == 400
        assert fresh(env, aff).payout_email is None


# ---------------------------------------------------------------------------
# changing details that are already on file
# ---------------------------------------------------------------------------
class TestChange:
    def test_change_emails_the_account_audits_and_starts_the_hold(self, env):
        import affiliate_service as asvc
        aff, user = h.make_partner(env.db)                       # paypal, pay-anne@partner.example
        env.state.user = user
        before = dt.datetime.now(UTC)
        save(env, "wise", "anne.lee@wise.example", "Anne  Lee")
        live = fresh(env, aff)
        assert (live.payout_method, live.payout_email, live.payout_account_name) == (
            "wise", "anne.lee@wise.example", "Anne Lee")
        hold = asvc.payout_details_hold_until(live)
        assert hold is not None
        assert dt.timedelta(hours=23, minutes=59) < hold - before <= dt.timedelta(hours=24, minutes=1)

        row, = audits(env)
        assert row.details["old_method"] == "paypal"
        assert row.details["old_email"] == "pay-anne@partner.example"
        assert row.details["new_method"] == "wise" and row.details["first_time"] is False
        assert row.details["hold_until"] and row.details["code"] == "ANNE"

        mail, = env.outbox
        assert mail.to == "anne@partner.example"                 # NOT the new payout address
        assert mail.subject == "Your payout details were changed"
        assert "Before: PayPal, p***e@partner.example" in mail.text    # old method, masked
        assert "Now: Wise, a***e@wise.example" in mail.text
        assert "pay-anne@partner.example" not in mail.text
        assert "anne.lee@wise.example" not in mail.text
        assert "on hold for 24 hours" in mail.text and "help@tradewave.ai" in mail.text
        assert "This is a required program notice" in mail.text  # cannot be switched off
        assert EM_DASH not in mail.text and EM_DASH not in mail.html

        (subject, body), = env.notes                             # the owner hears about it too
        assert "ANNE" in subject and "PayPal to Wise" in body
        assert "payouts are on hold for 24 hours" in flashes(env)[-1]

        html = page(env)
        assert "Payouts are on hold until" in html and "On hold for 24 hours" in html
        assert "Ready to be paid" not in html
        assert EM_DASH not in html

    def test_change_lands_in_the_partner_inbox(self, env):
        import models
        aff, user = h.make_partner(env.db)
        env.state.user = user
        save(env, "paypal", "other@pay.example")
        n, = env.db.query(models.AffiliateNotification).all()
        assert n.event_type == "payout_details_changed" and n.email_status == "sent"
        assert n.to_email == "anne@partner.example"
        assert n.link_url.endswith("/account/affiliate/payouts#payout-details")

    def test_same_details_change_nothing(self, env):
        aff, user = h.make_partner(env.db)
        env.state.user = user
        save(env, "paypal", "pay-anne@partner.example")
        assert "No change" in flashes(env)[-1]
        assert fresh(env, aff).payout_details_changed_at is None
        assert audits(env) == [] and env.outbox == []

    def test_name_only_change_is_audited_but_not_held(self, env):
        aff, user = h.make_partner(env.db)
        env.state.user = user
        save(env, "paypal", "pay-anne@partner.example", "Anne Lee")
        live = fresh(env, aff)
        assert live.payout_account_name == "Anne Lee" and live.payout_details_changed_at is None
        assert len(audits(env)) == 1
        assert env.outbox[0].subject == "Your payout details were updated"
        assert env.notes == []

    def test_hold_expires_after_24_hours(self, env):
        import affiliate_service as asvc
        from affiliate_portal import dashboard as dash
        aff, user = h.make_partner(env.db)
        changed = dt.datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
        aff.payout_details_changed_at = changed
        assert asvc.payout_details_hold_until(aff, changed + dt.timedelta(hours=23, minutes=59)) == \
            changed + dt.timedelta(hours=24)
        assert asvc.payout_details_hold_until(aff, changed + dt.timedelta(hours=24)) is None
        during = dash.payout_checklist(aff, {"usd": Decimal("80")}, now=changed + dt.timedelta(hours=1))
        assert during["ready"] is False and during["hold_until"] == "21 Nov 2026, 09:30 UTC"
        after = dash.payout_checklist(aff, {"usd": Decimal("80")}, now=changed + dt.timedelta(hours=25))
        assert after["ready"] is True and after["hold_until"] is None

    def test_a_failed_email_does_not_undo_the_save(self, env):
        import affiliate_comms as comms

        def boom(*a, **k):
            raise RuntimeError("mail down")
        aff, user = h.make_partner(env.db)
        env.state.user = user
        env.patch(comms, "notify_payout_details_changed", boom)
        save(env, "paypal", "other@pay.example")
        live = fresh(env, aff)
        assert live.payout_email == "other@pay.example" and live.payout_details_changed_at is not None
        assert len(audits(env)) == 1


# ---------------------------------------------------------------------------
# the hold blocks mark-paid and the bulk export
# ---------------------------------------------------------------------------
class TestPayoutGate:
    def test_hold_blocks_mark_paid_and_the_export(self, env):
        import affiliate_admin as afa
        import affiliate_ops as ops
        aff, user = h.make_partner(env.db)
        payout = pending_payout(env, aff)
        assert afa.payout_block_reason(payout, aff) is None
        row, = ops.pending_payout_rows(env.db)
        assert row["payable"] is True

        env.state.user = user
        save(env, "paypal", "thief@pay.example")
        live = fresh(env, aff)
        reason = afa.payout_block_reason(payout, live)
        assert "24-hour security hold" in reason and "ANNE" in reason
        row, = ops.pending_payout_rows(env.db)
        assert row["payable"] is False
        assert row["short_reason"] == "Payout details changed, 24h hold"
        with pytest.raises(ops.OpsError):
            ops.select_for_export(env.db, [payout.id], "paypal", "usd")

        # 24 hours later (or once an admin clears the timestamp) it is payable again
        live.payout_details_changed_at = dt.datetime.now(UTC) - dt.timedelta(hours=24, minutes=1)
        env.db.commit()
        assert afa.payout_block_reason(payout, live) is None
        live.payout_details_changed_at = None
        env.db.commit()
        row, = ops.pending_payout_rows(env.db)
        assert row["payable"] is True and row["email"] == "thief@pay.example"

    def test_tax_form_reason_still_comes_first(self, env):
        import affiliate_admin as afa
        aff, user = h.make_partner(env.db, tax_form_type=None, tax_form_received_at=None)
        aff.payout_details_changed_at = dt.datetime.now(UTC)
        assert "no tax form on file" in afa.payout_block_reason(pending_payout(env, aff), aff)

    def test_wise_file_uses_the_account_holder_name(self, env):
        import affiliate_ops as ops
        aff, user = h.make_partner(env.db, payout_method="wise", payout_account_name="Anne Lee Ltd")
        other, _u = h.make_partner(env.db, code="BOB", payout_method="wise")
        pending_payout(env, aff)
        pending_payout(env, other)
        rows = {r["code"]: r for r in ops.pending_payout_rows(env.db)}
        assert rows["ANNE"]["payout_name"] == "Anne Lee Ltd" and rows["ANNE"]["name"] == "Anne Lee"
        assert rows["BOB"]["payout_name"] == "Bob Lee"            # falls back to the partner name
        text = ops.wise_csv([rows["ANNE"], rows["BOB"]])
        assert "Anne Lee Ltd" in text and "Bob Lee" in text


# ---------------------------------------------------------------------------
# helpers + copy
# ---------------------------------------------------------------------------
def test_mask_email():
    import affiliate_service as asvc
    assert asvc.mask_email("jane.doe@example.com") == "j***e@example.com"
    assert asvc.mask_email("jo@example.com") == "j***@example.com"
    assert asvc.mask_email("j@example.com") == "j***@example.com"
    assert asvc.mask_email("") == "" and asvc.mask_email(None) == ""
    assert asvc.mask_email("garbage") == "***"


def test_notice_is_a_required_email_and_is_retried():
    import affiliate_comms as comms
    assert comms.EVENT_PREF["payout_details_changed"] is None
    assert comms.EVENT_LABEL["payout_details_changed"] == "Payout details changed"
    assert "payout_details_changed" in comms._ONE_SHOT_EVENTS
    assert any(label == "Payout details changed" for label, _why in comms.REQUIRED_NOTICES)


def test_copy_no_longer_sends_partners_to_email_for_payout_details():
    root = Path(__file__).resolve().parents[1]
    from affiliate_portal import dashboard as dash
    guide = (root / "docs" / "AFFILIATE_PARTNER_GUIDE.md").read_text()
    template = (root / "web" / "affiliate_portal" / "templates" / "aff_payouts.html").read_text()
    for text in (guide, template, dash.PAYOUT_METHOD_HELP):
        assert "To change payout details, contact" not in text
        assert "Contact help@tradewave.ai to add your PayPal" not in text
        assert EM_DASH not in text
    assert "**Payout details** form" in guide and "hold payouts for 24 hours" in guide
    assert "help@" not in dash.PAYOUT_METHOD_HELP


def test_migration_adds_the_two_columns_on_the_previous_head():
    import models
    root = Path(__file__).resolve().parents[1]
    mig = (root / "migrations" / "versions"
           / "f3a4b5c6d7e8_affiliate_payout_details_self_serve.py").read_text()
    assert "down_revision = 'e2f3a4b5c6d7'" in mig
    cols = models.Affiliate.__table__.columns
    for name in ("payout_account_name", "payout_details_changed_at"):
        assert name in cols and cols[name].nullable and '"%s"' % name in mig
