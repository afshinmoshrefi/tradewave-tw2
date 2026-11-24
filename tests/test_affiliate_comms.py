"""Partner lifecycle + communication (TW-TASK-0039 package B).

Covered: the public application (validation, honeypot, rate limit, duplicate,
emails), approve / reject, admin messaging (groups, preview, send log, inbox,
opt-outs), every automatic email of the daily job and its idempotency, email
preferences + the unsubscribe links, the portal Messages inbox, the admin
screens, the migration and the docs.

Hermetic: SQLite copy of the affiliate tables (tests/affiliate_portal_harness),
Resend is mocked (nothing leaves the process), Stripe provisioning is mocked.
"""
import datetime as dt
import importlib
import re
import sys
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affiliate_portal_harness as h  # noqa: E402

pytestmark = pytest.mark.unit

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[1]
EM_DASH = "—"
NOW = dt.datetime(2026, 11, 24, 15, 0, tzinfo=UTC)
COMMS_TABLES = ["affiliate_applications", "affiliate_messages", "affiliate_notifications",
                "affiliate_email_prefs"]
D = h.D

GOOD_FORM = {
    "name": "Maya Stone", "email": "Maya@Example.com", "website": "mayatrades.com",
    "channels": "YouTube: Maya Trades (42k)\nNewsletter: The Open", "audience_size": "10k_50k",
    "promo_plan": "A review video and a section in my weekly newsletter.",
    "country": "Canada", "agree": "yes",
}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch):
    """DB + mocked Resend. world.outbox collects every email 'sent'."""
    import config
    import email_utils
    monkeypatch.setattr(h, "TABLES", h.TABLES + COMMS_TABLES)
    db, factory, engine = h.make_db()
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE UNIQUE INDEX uq_notif ON affiliate_notifications "
                             "(affiliate_id, event_key)")
    outbox = []
    state = SimpleNamespace(ok=True)

    def fake_send(to, subject, body_text, from_addr=None, reply_to=None, html=None, headers=None):
        outbox.append(SimpleNamespace(to=to, subject=subject, text=body_text, html=html,
                                      headers=headers or {}))
        return state.ok

    monkeypatch.setattr(email_utils, "resend_send_email", fake_send)
    monkeypatch.setattr(config, "RESEND_API_KEY", "re_test_key", raising=False)
    monkeypatch.setattr(config, "WORKOS_COOKIE_PASSWORD", "unit-only-cookie-password", raising=False)
    monkeypatch.setattr(config, "SUPPORT_EMAIL_TO", "owner@tradewave.test", raising=False)
    monkeypatch.setattr(config, "AFFILIATE_SUPPORT_EMAIL", "", raising=False)  # set by config since package A; empty -> SUPPORT_EMAIL_TO
    monkeypatch.setattr(config, "tw2_public_url", "https://tw.test/", raising=False)
    monkeypatch.delenv("TW2_AFFILIATE_COMMS_MAX_EVENT_AGE_DAYS", raising=False)
    yield SimpleNamespace(db=db, factory=factory, engine=engine, outbox=outbox, send=state,
                          patch=monkeypatch.setattr)
    db.close()
    engine.dispose()


@pytest.fixture
def stripe_ok(monkeypatch):
    """Stripe provisioning for a new partner, mocked."""
    import affiliate_service as afs
    import promo_service as ps
    calls = SimpleNamespace(provision=[], promo_active=[], fail=False)

    def provision(aff):
        if calls.fail:
            raise afs.AffiliateError("Stripe is down")
        calls.provision.append(aff.code)
        return "cpn_" + aff.code.lower(), "promo_" + aff.code.lower()

    monkeypatch.setattr(afs, "provision_stripe_objects", provision)
    monkeypatch.setattr(ps, "set_promo_active", lambda aff, active: calls.promo_active.append((aff.code, active)))
    return calls


def comms():
    import affiliate_comms
    return affiliate_comms


def models():
    import models as m
    return m


def notes(db, aff=None, etype=None):
    m = models()
    q = db.query(m.AffiliateNotification)
    if aff is not None:
        q = q.filter(m.AffiliateNotification.affiliate_id == aff.id)
    if etype is not None:
        q = q.filter(m.AffiliateNotification.event_type == etype)
    return q.order_by(m.AffiliateNotification.id).all()


def referral(db, aff, n, *, first_paid=None, ended=None, **kw):
    m = models()
    base = dict(id=uuid.uuid4(), affiliate_id=aff.id, stripe_subscription_id="sub_%s_%s" % (aff.code, n),
                stripe_customer_id="cus_%s_%s" % (aff.code, n), source="checkout", terms_id=1,
                offer_type="regular", discount_pct=D(20), referral_code=aff.code, tier="analyst",
                billing_interval="year", list_price_cents=39900, attributed_at=first_paid or NOW,
                first_paid_at=first_paid, year_anchor_at=first_paid, ended_at=ended)
    base.update(kw)
    r = m.AffiliateReferral(**base)
    db.add(r)
    db.commit()
    return r


def partner(db, code="ANNE", signed_days_ago=400, **kw):
    kw.setdefault("agreement_signed_at", NOW - dt.timedelta(days=signed_days_ago))
    aff, user = h.make_partner(db, code, **kw)
    return aff, user


# ---------------------------------------------------------------------------
# 1. applications (service)
# ---------------------------------------------------------------------------
class TestApplicationSubmit:
    def test_valid_application_is_stored_and_two_emails_go_out(self, world):
        c = comms()
        outcome, row = c.submit_application(world.db, GOOD_FORM, ip="203.0.113.9",
                                            user_agent="pytest", now=NOW)
        assert outcome == "ok" and row.status == "new"
        assert row.email == "maya@example.com" and row.audience_size == "10k_50k"
        assert row.ip_hash and "203.0.113.9" not in row.ip_hash       # never the raw IP
        assert row.agreed_policies_at is not None
        applicant, owner = world.outbox
        assert applicant.to == "maya@example.com"
        assert applicant.subject == "We received your TradeWave partner application"
        assert "Hi Maya" in applicant.text and "5 business days" in applicant.text
        assert owner.to == "owner@tradewave.test"
        assert owner.subject == "New partner application: Maya Stone"
        assert "https://tw.test/admin/affiliate_applications/view?id=%s" % row.id in owner.text
        assert "maya@example.com" in owner.text and "10,000 to 50,000" in owner.text
        for mail in world.outbox:
            assert EM_DASH not in mail.text + mail.subject

    def test_every_problem_is_listed_at_once(self, world):
        c = comms()
        with pytest.raises(c.CommsError) as e:
            c.submit_application(world.db, {"name": "M", "email": "nope", "audience_size": "huge",
                                            "promo_plan": "short", "website": "not a site"})
        errors = " | ".join(e.value.errors)
        for needle in ("your name", "valid email", "Website should look like", "audience size",
                       "how you will promote", "your country", "tick the box"):
            assert needle in errors
        assert world.outbox == [] and world.db.query(models().AffiliateApplication).count() == 0

    def test_needs_a_website_or_a_channel_and_plain_text(self, world):
        c = comms()
        form = dict(GOOD_FORM, website="", channels="")
        with pytest.raises(c.CommsError) as e:
            c.clean_application(form)
        assert "a website or your channels" in e.value.errors[0]
        with pytest.raises(c.CommsError) as e:
            c.clean_application(dict(GOOD_FORM, name="<b>Maya</b>"))
        assert "plain text" in e.value.errors[0]
        assert c.clean_application(dict(GOOD_FORM, website=""))["website"] is None

    def test_honeypot_stores_nothing_and_sends_nothing(self, world):
        c = comms()
        outcome, row = c.submit_application(world.db, dict(GOOD_FORM, company_url="http://spam.biz"))
        assert outcome == "honeypot" and row is None
        assert world.outbox == [] and world.db.query(models().AffiliateApplication).count() == 0

    def test_same_email_waiting_is_a_duplicate_not_a_second_row(self, world):
        c = comms()
        c.submit_application(world.db, GOOD_FORM, ip="203.0.113.9", now=NOW)
        sent = len(world.outbox)
        outcome, row = c.submit_application(world.db, dict(GOOD_FORM, email="MAYA@example.com"),
                                            ip="203.0.113.10", now=NOW)
        assert outcome == "duplicate" and row is not None
        assert world.db.query(models().AffiliateApplication).count() == 1
        assert len(world.outbox) == sent                              # no second pair of emails

    def test_rate_limit_per_network_per_day(self, world):
        c = comms()
        for i in range(c.APPLY_LIMIT_PER_IP_DAY):
            outcome, _ = c.submit_application(
                world.db, dict(GOOD_FORM, email="p%d@example.com" % i), ip="198.51.100.7", now=NOW)
            assert outcome == "ok"
        outcome, row = c.submit_application(world.db, dict(GOOD_FORM, email="p9@example.com"),
                                            ip="198.51.100.7", now=NOW)
        assert outcome == "rate_limited" and row is None
        # another network, and the same network a day later, are fine
        assert c.submit_application(world.db, dict(GOOD_FORM, email="q@example.com"),
                                    ip="198.51.100.8", now=NOW)[0] == "ok"
        assert c.submit_application(world.db, dict(GOOD_FORM, email="r@example.com"),
                                    ip="198.51.100.7", now=NOW + dt.timedelta(days=1, minutes=1))[0] == "ok"


class TestApplicationDecision:
    def _app(self, world, **form):
        _o, row = comms().submit_application(world.db, dict(GOOD_FORM, **form), now=NOW)
        world.outbox.clear()
        return row

    def test_approve_creates_a_paused_partner_on_default_terms_and_emails_the_link(self, world, stripe_ok):
        c, m = comms(), models()
        row = self._app(world)
        assert c.suggest_code(world.db, row.name) == "MAYA"
        aff, emailed = c.approve_application(world.db, row, code="maya", discount_pct="15",
                                             actor="admin:afshin@example.com",
                                             note="Welcome aboard, Maya.", now=NOW)
        assert emailed is True
        assert aff.code == "MAYA" and aff.status == "paused" and aff.agreement_signed_at is None
        assert aff.terms_id == 1 and aff.discount_pct == D(15) and aff.commission_pct == D(35)
        assert aff.email == "maya@example.com" and aff.stripe_coupon_id == "cpn_maya"
        assert stripe_ok.provision == ["MAYA"] and stripe_ok.promo_active == [("MAYA", False)]
        fresh = world.db.get(m.AffiliateApplication, row.id)
        assert fresh.status == "approved" and fresh.affiliate_id == aff.id
        assert fresh.decided_by == "admin:afshin@example.com"
        (mail,) = world.outbox
        assert mail.to == "maya@example.com" and mail.subject == "Sign your TradeWave Affiliate Agreement"
        assert "/affiliate/sign/" in mail.text and "Welcome aboard, Maya." in mail.text

    def test_zero_discount_needs_no_stripe_coupon(self, world, stripe_ok):
        aff, _ = comms().approve_application(world.db, self._app(world), code="MAYA",
                                             discount_pct="0", actor="admin:x", now=NOW)
        assert stripe_ok.provision == [] and aff.stripe_coupon_id is None
        assert aff.commission_pct == D(50)

    def test_approve_refuses_bad_input_and_duplicates(self, world, stripe_ok):
        c, m = comms(), models()
        row = self._app(world)
        for kwargs, needle in (
                (dict(code="x", discount_pct="10"), "code"),
                (dict(code="MAYA", discount_pct="26"), "between 0% and 25%"),
                (dict(code="MAYA", discount_pct="lots"), "must be a number")):
            with pytest.raises(c.CommsError) as e:
                c.approve_application(world.db, row, actor="admin:x", **kwargs)
            assert needle in str(e.value)
        h.make_partner(world.db, "TAKEN")
        with pytest.raises(c.CommsError) as e:
            c.approve_application(world.db, row, code="taken", discount_pct="10", actor="admin:x")
        assert "The code TAKEN is taken" in str(e.value)
        h.make_partner(world.db, "OLDMAYA", email="Maya@Example.com")
        with pytest.raises(c.CommsError) as e:
            c.approve_application(world.db, row, code="MAYA", discount_pct="10", actor="admin:x")
        assert "already a partner (code OLDMAYA)" in str(e.value)
        assert world.db.query(m.Affiliate).filter_by(code="MAYA").count() == 0
        assert world.outbox == []

    def test_stripe_failure_saves_nothing(self, world, stripe_ok):
        c, m = comms(), models()
        row = self._app(world)
        stripe_ok.fail = True
        with pytest.raises(c.CommsError) as e:
            c.approve_application(world.db, row, code="MAYA", discount_pct="10", actor="admin:x")
        assert "Stripe could not create the discount code" in str(e.value)
        assert world.db.query(m.Affiliate).filter_by(code="MAYA").count() == 0
        assert world.db.get(m.AffiliateApplication, row.id).status == "new"
        assert world.outbox == []

    def test_reject_with_and_without_reason(self, world):
        c, m = comms(), models()
        row = self._app(world)
        assert c.reject_application(world.db, row, actor="admin:x",
                                    reason="We are focused on stock educators this year.") is True
        (mail,) = world.outbox
        assert mail.to == "maya@example.com" and mail.subject == "Your TradeWave partner application"
        assert "focused on stock educators" in mail.text and "apply again later" in mail.text
        assert EM_DASH not in mail.text
        assert world.db.get(m.AffiliateApplication, row.id).status == "rejected"
        world.outbox.clear()
        other = self._app(world, email="other@example.com")
        assert c.reject_application(world.db, other, actor="admin:x", send_email=False) is False
        assert world.outbox == []

    def test_flags_find_the_existing_partner_and_earlier_applications(self, world, stripe_ok):
        c = comms()
        first = self._app(world)
        c.reject_application(world.db, first, actor="admin:x", send_email=False)
        second = self._app(world)                     # re-applies after the rejection
        h.make_partner(world.db, "MAYA1", email="maya@example.com")
        flags = c.application_flags(world.db, second)
        assert flags["affiliate"].code == "MAYA1"
        assert [a.id for a in flags["earlier"]] == [first.id]
        assert c.suggest_code(world.db, "Maya Stone") == "MAYA"
        h.make_partner(world.db, "MAYA")
        assert c.suggest_code(world.db, "Maya Stone") == "MAYA2"
        assert c.suggest_code(world.db, "?") == "PARTNER"


# ---------------------------------------------------------------------------
# 2. delivery: idempotent, preference-aware, logged
# ---------------------------------------------------------------------------
class TestDelivery:
    def _event(self, etype="new_customer", key="new_customer:1"):
        return comms().make_event(etype, key, "Subject line", "Hello.\n\nSecond paragraph https://tw.test/x.",
                                  occurred_at=NOW, link=("Open", "https://tw.test/account/affiliate"))

    def test_one_send_per_event_per_partner(self, world):
        c = comms()
        aff, _ = partner(world.db)
        row = c.deliver(world.db, aff, self._event(), NOW)
        assert row.email_status == "sent" and row.attempts == 1 and row.to_email == aff.email
        assert c.deliver(world.db, aff, self._event(), NOW) is None
        assert c.deliver(world.db, aff, self._event(), NOW + dt.timedelta(days=3)) is None
        assert len(world.outbox) == 1 and len(notes(world.db, aff)) == 1
        other, _ = partner(world.db, "BOB")
        assert c.deliver(world.db, other, self._event(), NOW).email_status == "sent"
        assert len(world.outbox) == 2

    def test_optional_email_has_unsubscribe_link_and_one_click_headers(self, world):
        c = comms()
        aff, _ = partner(world.db)
        c.deliver(world.db, aff, self._event(), NOW)
        (mail,) = world.outbox
        token = c.make_pref_token(aff.id)
        prefs = "https://tw.test/partners/email-preferences/%s" % token
        assert prefs in mail.text and prefs + "?off=new_customer" in mail.text
        assert "Stop this kind of email" in mail.text and "stop this kind of email" in mail.html
        assert mail.headers["List-Unsubscribe"] == "<https://tw.test/partners/unsubscribe/%s/new_customer>" % token
        assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert '<a href="https://tw.test/x">' in mail.html              # links are clickable
        assert "Open:\nhttps://tw.test/account/affiliate" in mail.text
        assert c.verify_pref_token(token) == str(aff.id)
        assert c.verify_pref_token(token + "x") is None and c.verify_pref_token("") is None

    def test_required_notice_has_no_unsubscribe_and_ignores_opt_outs(self, world):
        c = comms()
        aff, _ = partner(world.db)
        c.set_disabled_prefs(world.db, aff.id, c.PREF_IDS)
        row = c.deliver(world.db, aff, self._event("payout_sent", "payout:1"), NOW)
        assert row.email_status == "sent"
        (mail,) = world.outbox
        assert "required program notice" in mail.text
        assert "Stop this kind of email" not in mail.text and "unsubscribe" not in mail.text.lower()
        assert "List-Unsubscribe" not in mail.headers
        assert "/partners/email-preferences/" in mail.text      # can still manage the others

    def test_opted_out_partner_gets_the_inbox_row_but_no_email(self, world):
        c = comms()
        aff, _ = partner(world.db)
        c.turn_off_pref(world.db, aff.id, "new_customer")
        row = c.deliver(world.db, aff, self._event(), NOW)
        assert (row.email_status, row.email_reason) == ("skipped", "preference")
        assert world.outbox == [] and c.unread_count(world.db, aff.id) == 1
        assert c.deliver(world.db, aff, self._event(), NOW) is None     # and it stays skipped

    def test_failed_send_is_retried_three_times_then_stops(self, world):
        c = comms()
        aff, _ = partner(world.db)
        world.send.ok = False
        for attempt in (1, 2, 3):
            row = c.deliver(world.db, aff, self._event(), NOW + dt.timedelta(days=attempt))
            assert (row.email_status, row.attempts) == ("failed", attempt)
        assert c.deliver(world.db, aff, self._event(), NOW + dt.timedelta(days=4)) is None
        assert len(world.outbox) == 3 and len(notes(world.db, aff)) == 1
        other, _ = partner(world.db, "BOB")
        c.deliver(world.db, other, self._event(), NOW)
        world.send.ok = True
        row = c.deliver(world.db, other, self._event(), NOW + dt.timedelta(days=1))
        assert (row.email_status, row.attempts) == ("sent", 2)

    def test_a_send_in_progress_is_not_sent_twice(self, world):
        c, m = comms(), models()
        aff, _ = partner(world.db)
        world.db.add(m.AffiliateNotification(
            affiliate_id=aff.id, event_type="new_customer", event_key="new_customer:1",
            subject="s", body="b", email_status="pending", attempts=0, created_at=NOW))
        world.db.commit()
        assert c.deliver(world.db, aff, self._event(), NOW + dt.timedelta(minutes=5)) is None
        assert world.outbox == []
        # a claim left behind by a crashed run is picked up later
        assert c.deliver(world.db, aff, self._event(), NOW + dt.timedelta(hours=2)).email_status == "sent"

    def test_without_resend_the_inbox_still_gets_it(self, world):
        import config
        c = comms()
        world.patch(config, "RESEND_API_KEY", "")
        aff, _ = partner(world.db)
        row = c.deliver(world.db, aff, self._event(), NOW)
        assert (row.email_status, row.email_reason) == ("skipped", "email_not_configured")
        assert world.outbox == []

    def test_preferences_round_trip(self, world):
        c = comms()
        aff, _ = partner(world.db)
        assert all(r["on"] for r in c.pref_rows(world.db, aff.id))
        c.set_disabled_prefs(world.db, aff.id, ["announcement", "bogus", "welcome"])
        assert c.disabled_prefs(world.db, aff.id) == {"announcement", "welcome"}
        assert c.turn_off_pref(world.db, aff.id, "bogus") is False
        c.set_disabled_prefs(world.db, aff.id, [])
        assert c.disabled_prefs(world.db, aff.id) == set()
        # every event type maps to a known preference or is required
        assert set(v for v in c.EVENT_PREF.values() if v) <= set(c.PREF_IDS)
        for label, help_ in list(c.REQUIRED_NOTICES) + [(p[1], p[2]) for p in c.PREFS]:
            assert EM_DASH not in label + help_


# ---------------------------------------------------------------------------
# 3. admin messaging
# ---------------------------------------------------------------------------
class TestMessaging:
    def _cast(self, world):
        """ANNE active with a recent customer; BOB active, old customer, 10y
        terms; CARL active, no customer; PAUL paused (signed); UNA unsigned;
        TERRY terminated."""
        db = world.db
        anne, _ = partner(db, "ANNE")
        bob, _ = partner(db, "BOB", terms_id=2)
        carl, _ = partner(db, "CARL")
        paul, _ = partner(db, "PAUL", status="paused")
        una, _ = partner(db, "UNA", status="paused", agreement_signed_at=None)
        terry, _ = partner(db, "TERRY", status="terminated")
        referral(db, anne, 1, first_paid=NOW - dt.timedelta(days=10))
        referral(db, bob, 1, first_paid=NOW - dt.timedelta(days=200))
        referral(db, terry, 1, first_paid=NOW - dt.timedelta(days=5))
        referral(db, carl, 1, first_paid=None)                  # signed up, never paid
        referral(db, carl, 2, first_paid=NOW - dt.timedelta(days=3), source="return")
        return SimpleNamespace(anne=anne, bob=bob, carl=carl, paul=paul, una=una, terry=terry)

    def _codes(self, world, audience, param=None):
        return [a.code for a in comms().resolve_audience(world.db, audience, param, NOW)]

    def test_groups(self, world):
        p = self._cast(world)
        assert self._codes(world, "all") == ["ANNE", "BOB", "CARL", "PAUL", "UNA"]
        assert self._codes(world, "active") == ["ANNE", "BOB", "CARL"]
        assert self._codes(world, "paused") == ["PAUL"]
        assert self._codes(world, "unsigned") == ["UNA"]
        assert self._codes(world, "terms", "2") == ["BOB"]
        assert self._codes(world, "terms", "1") == ["ANNE", "CARL", "PAUL", "UNA"]
        assert self._codes(world, "has_customers") == ["ANNE", "BOB"]
        assert self._codes(world, "no_customers") == ["CARL", "PAUL", "UNA"]
        assert self._codes(world, "inactive", "90") == ["BOB", "CARL", "PAUL"]
        assert self._codes(world, "inactive", "5") == ["ANNE", "BOB", "CARL", "PAUL"]
        assert self._codes(world, "one", str(p.terry.id)) == ["TERRY"]

    def test_bad_group_input(self, world):
        c = comms()
        self._cast(world)
        for audience, param in (("everyone", None), ("one", "nope"), ("one", str(uuid.uuid4())),
                                ("terms", "x"), ("inactive", "0"), ("inactive", "abc")):
            with pytest.raises(c.CommsError):
                c.resolve_audience(world.db, audience, param, NOW)

    def test_send_logs_every_recipient_and_fills_the_inbox(self, world):
        c = comms()
        p = self._cast(world)
        c.turn_off_pref(world.db, p.carl.id, "announcement")
        msg, stats = c.send_message(
            world.db, subject="New charts for {first_name}",
            body="Hi {first_name},\n\nYour code {code} has new banners. Link: {link}",
            audience="active", sent_by="admin:afshin@example.com", now=NOW)
        assert stats == {"sent": 2, "skipped": 1, "failed": 0, "recipients": 3}
        assert msg.recipient_count == 3 and msg.audience == "active"
        assert sorted(m.to for m in world.outbox) == ["anne@partner.example", "bob@partner.example"]
        anne_mail = [m for m in world.outbox if m.to == "anne@partner.example"][0]
        assert anne_mail.subject == "New charts for Anne"
        assert "Your code ANNE has new banners. Link: https://tw.test/join/ANNE" in anne_mail.text
        assert "?off=announcement" in anne_mail.text and "List-Unsubscribe" in anne_mail.headers
        # Carl opted out of the email, and still has it in his inbox
        (carl_note,) = notes(world.db, p.carl)
        assert (carl_note.email_status, carl_note.email_reason) == ("skipped", "preference")
        assert carl_note.subject == "New charts for Carl" and carl_note.message_id == msg.id
        assert c.unread_count(world.db, p.carl.id) == 1 and c.unread_count(world.db, p.paul.id) == 0
        (entry,) = c.message_log(world.db)
        assert entry["counts"] == {"sent": 2, "skipped": 1} and entry["read"] == 0
        assert entry["audience"] == "Active partners"
        assert len(c.notification_log(world.db, message_id=msg.id)) == 3

    def test_program_notice_reaches_partners_who_opted_out(self, world):
        c = comms()
        p = self._cast(world)
        c.set_disabled_prefs(world.db, p.carl.id, c.PREF_IDS)
        _msg, stats = c.send_message(world.db, subject="Change to payout dates",
                                     body="From January payouts go out on the 10th.",
                                     audience="one", param=str(p.carl.id), required=True,
                                     sent_by="admin:x", now=NOW)
        assert stats["sent"] == 1
        (mail,) = world.outbox
        assert "required program notice" in mail.text and "List-Unsubscribe" not in mail.headers
        assert notes(world.db, p.carl)[0].event_type == "program_notice"

    def test_validation_and_empty_group(self, world):
        c = comms()
        self._cast(world)
        with pytest.raises(c.CommsError) as e:
            c.send_message(world.db, subject="x", body="short", audience="active")
        assert len(e.value.errors) == 2
        with pytest.raises(c.CommsError) as e:
            c.send_message(world.db, subject="Hello there", body="A long dash — is not house style.",
                           audience="active")
        assert "long dash" in str(e.value)
        with pytest.raises(c.CommsError) as e:
            c.send_message(world.db, subject="Hello there", body="Nobody is on this version.",
                           audience="terms", param="3")
        assert "Nobody matches" in str(e.value)
        assert world.outbox == [] and world.db.query(models().AffiliateMessage).count() == 0


# ---------------------------------------------------------------------------
# 4. the daily job: each automatic email, once
# ---------------------------------------------------------------------------
def run(world, now=NOW, **kw):
    return comms().run_daily(world.db, now=now, **kw)


def mails(world, subject_part):
    return [m for m in world.outbox if subject_part in m.subject]


class TestDailyJob:
    def test_welcome_first_click_and_new_customer(self, world):
        m = models()
        aff, _ = partner(world.db, signed_days_ago=1)
        world.db.add(m.AffiliateClick(affiliate_id=aff.id, day=(NOW - dt.timedelta(days=1)).date(), clicks=4))
        world.db.add(m.AffiliateClick(affiliate_id=aff.id, day=NOW.date(), clicks=9))
        referral(world.db, aff, 1, first_paid=NOW - dt.timedelta(hours=5))
        referral(world.db, aff, 2, first_paid=NOW - dt.timedelta(hours=2), offer_type="promo",
                 discount_pct=None, tier="navigator", billing_interval="month")
        referral(world.db, aff, 3, first_paid=None)                              # trial, not paid
        referral(world.db, aff, 4, first_paid=NOW - dt.timedelta(hours=1), source="return")
        stats = run(world)
        assert stats["sent"] == 4 and stats["errors"] == 0
        (welcome,) = mails(world, "Welcome to the TradeWave partner program")
        assert "Your link: https://tw.test/join/ANNE" in welcome.text
        assert "20% off and you earn 30% of the list price" in welcome.text
        assert "$80.00 for the customer and $30.00 for you" in welcome.text
        assert "25% of what the customer pays on renewals" in welcome.text
        (click,) = mails(world, "Your link got its first click")
        assert "7-day trial" in click.text
        new = mails(world, "You have a new paying customer")
        assert len(new) == 2                                    # trial + returning customer excluded
        regular = [x for x in new if "Analyst annual" in x.text][0]
        assert "You earn $119.70 on this payment (30% of the list price)" in regular.text
        assert "You now have 2 paying customers in total" in regular.text
        promo = [x for x in new if "Navigator monthly" in x.text][0]
        assert "TradeWave sale, so you earn 50% of what they paid" in promo.text
        # never who the customer is
        for mail in world.outbox:
            blob = mail.text + (mail.html or "") + mail.subject
            assert "cus_" not in blob and "sub_" not in blob and "secret.example" not in blob
            assert EM_DASH not in blob
            assert "/partners/email-preferences/" in mail.text and "List-Unsubscribe" in mail.headers
        # idempotent: a second and third run send nothing
        world.outbox.clear()
        again = run(world)
        assert again["sent"] == 0 and again["already"] == 4 and world.outbox == []
        assert run(world, now=NOW + dt.timedelta(days=1))["sent"] == 0 and world.outbox == []

    def test_statement_ready_and_payout_sent(self, world):
        m = models()
        aff, _ = partner(world.db)
        oct1, sep1 = dt.date(2026, 10, 1), dt.date(2026, 9, 1)
        world.db.add_all([
            m.AffiliatePayout(affiliate_id=aff.id, period_start=oct1, period_end=oct1, currency="usd",
                              commission_amount=D("108.45"), status="pending",
                              computed_at=NOW - dt.timedelta(days=1)),
            m.AffiliatePayout(affiliate_id=aff.id, period_start=sep1, period_end=sep1, currency="usd",
                              commission_amount=D("1219.70"), status="paid", external_ref="PP-7H2K91",
                              computed_at=NOW - dt.timedelta(days=50), paid_at=NOW - dt.timedelta(hours=3)),
            m.AffiliatePayout(affiliate_id=aff.id, period_start=dt.date(2026, 8, 1),
                              period_end=dt.date(2026, 8, 1), currency="usd",
                              commission_amount=D("-12.00"), status="void", external_ref="carried:2026-09",
                              computed_at=NOW - dt.timedelta(days=1), paid_at=None)])
        world.db.commit()
        assert run(world)["sent"] == 2
        (statement,) = mails(world, "statement is ready")
        assert statement.subject == "Your October 2026 statement is ready"
        assert "Commission for the month: $108.45." in statement.text
        assert "by the 15th" in statement.text and "at least $50.00" in statement.text
        assert "?off=statement_ready" in statement.text
        (payout,) = mails(world, "Payout sent")
        assert payout.subject == "Payout sent: $1,219.70"
        assert "for September 2026 by PayPal. Reference: PP-7H2K91." in payout.text
        assert "required program notice" in payout.text and "List-Unsubscribe" not in payout.headers
        # September's statement is 50 days old: too old to announce now
        assert [n.event_key for n in notes(world.db, aff)] == ["statement:2026-10", "payout:2"]
        world.outbox.clear()
        assert run(world)["sent"] == 0

    def test_activity_warnings_60_30_7_then_stopped_then_resumed(self, world):
        c = comms()
        aff, _ = partner(world.db)
        paid = dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        referral(world.db, aff, 1, first_paid=paid)
        # 12 months + 30 days of grace after the last new paying customer
        until = dt.date(2027, 2, 9)
        import affiliate_service as afs
        assert afs.activity_status(aff, NOW, session=world.db)["active_until"] == until

        def at(days_before):
            return dt.datetime(until.year, until.month, until.day, 9, 0, tzinfo=UTC) - dt.timedelta(days=days_before)

        assert run(world, now=at(61))["sent"] == 0                     # too early
        assert run(world, now=at(60))["sent"] == 1
        assert run(world, now=at(45))["sent"] == 0                     # the 60-day one is done
        assert run(world, now=at(30))["sent"] == 1
        assert run(world, now=at(8))["sent"] == 0
        assert run(world, now=at(7))["sent"] == 1
        assert run(world, now=at(1))["sent"] == 0
        w60, w30, w7 = world.outbox
        assert w60.subject == "60 days left to keep your renewal commissions"
        assert w30.subject == "30 days left to keep your renewal commissions"
        assert w7.subject == "7 days left to keep your renewal commissions"
        assert "on 9 February 2027" in w60.text
        assert "at least 1 new paying customer every 12 months, with a 30-day grace" in w60.text
        assert "first-year commissions are not affected" in w60.text
        assert "?off=activity_warning" in w60.text and "?off=activity_warning" in w30.text
        assert "required program notice" in w7.text and "List-Unsubscribe" not in w7.headers
        assert [n.event_type for n in notes(world.db, aff)] == [
            "activity_warning_60", "activity_warning_30", "activity_warning_7"]

        world.outbox.clear()
        after = dt.datetime(2027, 2, 10, 9, 0, tzinfo=UTC)
        assert run(world, now=after)["sent"] == 1
        (stopped,) = world.outbox
        assert stopped.subject == "Your renewal commissions have stopped for now"
        assert "ended on 9 February 2027" in stopped.text and "earn $0" in stopped.text
        assert "refer 1 new paying customer" in stopped.text
        assert "required program notice" in stopped.text
        assert run(world, now=after + dt.timedelta(days=2))["sent"] == 0

        world.outbox.clear()
        back = dt.datetime(2027, 3, 1, 9, 0, tzinfo=UTC)
        referral(world.db, aff, 2, first_paid=back - dt.timedelta(hours=4))
        run(world, now=back)
        (resumed,) = mails(world, "Your renewal commissions are active again")
        assert "until at least 31 March 2028" in resumed.text
        assert "?off=renewals_resumed" in resumed.text
        assert len(mails(world, "You have a new paying customer")) == 1
        world.outbox.clear()
        assert run(world, now=back + dt.timedelta(days=1))["sent"] == 0
        assert c.EVENT_PREF["renewals_lapsed"] is None

    def test_only_the_most_urgent_warning_on_a_first_run(self, world):
        aff, _ = partner(world.db)
        referral(world.db, aff, 1, first_paid=dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC))
        assert run(world, now=dt.datetime(2027, 2, 4, 9, 0, tzinfo=UTC))["sent"] == 1
        assert [n.event_type for n in notes(world.db, aff)] == ["activity_warning_7"]
        assert world.outbox[0].subject == "5 days left to keep your renewal commissions"

    def test_no_activity_emails_without_a_customer_who_can_renew(self, world):
        aff, _ = partner(world.db)
        paid = dt.datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
        referral(world.db, aff, 1, first_paid=paid, ended=paid + dt.timedelta(days=40))
        nobody, _ = partner(world.db, "CARL")
        assert run(world, now=dt.datetime(2027, 2, 4, 9, 0, tzinfo=UTC))["sent"] == 0
        assert run(world, now=dt.datetime(2027, 2, 10, 9, 0, tzinfo=UTC))["sent"] == 0

    def test_new_company_sale_goes_to_active_partners_with_their_link(self, world):
        m = models()
        anne, _ = partner(world.db)
        paul, _ = partner(world.db, "PAUL", status="paused")
        live = m.PromoCampaign(
            id=uuid.uuid4(), code="BLACK-FRIDAY", name="Black Friday", tiers=["analyst"],
            billing_intervals=["year"], new_customers_only=True,
            starts_at=NOW - dt.timedelta(hours=6), ends_at=NOW + dt.timedelta(days=6),
            offer_type="price", intro_prices={"analyst:year": 9900}, intro_months=12, status="active")
        draft = m.PromoCampaign(
            id=uuid.uuid4(), code="XMAS", name="Holiday", tiers=["analyst"], billing_intervals=["year"],
            new_customers_only=True, starts_at=NOW - dt.timedelta(hours=6),
            ends_at=NOW + dt.timedelta(days=6), offer_type="percent", percent_off=D(30),
            intro_months=12, status="draft")
        future = m.PromoCampaign(
            id=uuid.uuid4(), code="NY", name="New Year", tiers=["analyst"], billing_intervals=["year"],
            new_customers_only=True, starts_at=NOW + dt.timedelta(days=30),
            ends_at=NOW + dt.timedelta(days=40), offer_type="percent", percent_off=D(30),
            intro_months=12, status="active")
        world.db.add_all([live, draft, future])
        world.db.commit()
        assert run(world)["sent"] == 1
        (mail,) = world.outbox
        assert mail.to == "anne@partner.example"
        assert mail.subject == "New TradeWave sale: Black Friday - your link already works"
        assert "The offer is Analyst annual for $99 for new customers." in mail.text
        assert "It runs until 30 November 2026, 15:00 UTC." in mail.text
        assert "you earn 50% of what they pay" in mail.text
        assert "Your tracked link: https://tw.test/join/ANNE" in mail.text
        assert "Short link: https://tw.test/?code=ANNE" in mail.text
        assert "whichever price is lower" in mail.text and "?off=campaign_started" in mail.text
        world.outbox.clear()
        assert run(world, now=NOW + dt.timedelta(days=2))["sent"] == 0
        assert comms().campaign_offer_text(draft) == "30% off for new customers"

    def test_discount_change_is_confirmed_once_per_save(self, world):
        m = models()
        aff, user = partner(world.db, discount_pct=D(10))
        when = NOW - dt.timedelta(minutes=30)
        for iv in ("year", "month"):              # one save writes a row per interval
            world.db.add(m.AffiliateDiscountChange(
                affiliate_id=aff.id, billing_interval=iv, old_pct=D(20), new_pct=D(10),
                actor="partner:%s" % user.id, changed_at=when))
        world.db.add(m.AffiliateDiscountChange(
            affiliate_id=aff.id, billing_interval="year", old_pct=D(15), new_pct=D(20),
            actor="partner:%s" % user.id, changed_at=NOW - dt.timedelta(days=40)))
        world.db.commit()
        assert run(world)["sent"] == 1
        (mail,) = world.outbox
        assert mail.subject == "Your customer discount is now 10%"
        assert "changed from 20% to 10% on 24 November 2026, 14:30 UTC" in mail.text
        assert "You now earn 40% of the list price on first-year payments." in mail.text
        assert "If you did not make this change" in mail.text
        assert "required program notice" in mail.text and "List-Unsubscribe" not in mail.headers
        world.outbox.clear()
        assert run(world)["sent"] == 0

    def test_old_events_are_not_mailed_when_the_job_is_first_switched_on(self, world):
        m = models()
        aff, _ = partner(world.db, signed_days_ago=300)
        world.db.add(m.AffiliateClick(affiliate_id=aff.id, day=(NOW - dt.timedelta(days=200)).date(), clicks=3))
        referral(world.db, aff, 1, first_paid=NOW - dt.timedelta(days=90))
        world.db.add(m.AffiliatePayout(
            affiliate_id=aff.id, period_start=dt.date(2026, 6, 1), period_end=dt.date(2026, 6, 1),
            currency="usd", commission_amount=D("80"), status="paid", external_ref="PP-1",
            computed_at=NOW - dt.timedelta(days=120), paid_at=NOW - dt.timedelta(days=100)))
        world.db.commit()
        stats = run(world)
        assert stats["sent"] == 0 and world.outbox == [] and notes(world.db) == []

    def test_preferences_are_respected_and_required_still_sent(self, world):
        c, m = comms(), models()
        aff, user = partner(world.db, signed_days_ago=1)
        c.set_disabled_prefs(world.db, aff.id, c.PREF_IDS)
        referral(world.db, aff, 1, first_paid=NOW - dt.timedelta(hours=5))
        world.db.add(m.AffiliateDiscountChange(
            affiliate_id=aff.id, billing_interval="year", old_pct=D(20), new_pct=D(5),
            actor="partner:%s" % user.id, changed_at=NOW - dt.timedelta(hours=1)))
        world.db.commit()
        stats = run(world)
        assert stats["sent"] == 1 and stats["skipped"] == 2
        assert [x.subject for x in world.outbox] == ["Your customer discount is now 5%"]
        by_type = {n.event_type: n for n in notes(world.db, aff)}
        assert by_type["welcome"].email_reason == "preference"
        assert by_type["new_customer"].email_reason == "preference"
        assert c.unread_count(world.db, aff.id) == 3              # all three are in the inbox

    def test_unsigned_gets_nothing_and_terminated_only_the_payout(self, world):
        m = models()
        una, _ = partner(world.db, "UNA", status="paused", agreement_signed_at=None)
        terry, _ = partner(world.db, "TERRY", status="terminated", signed_days_ago=1)
        for aff in (una, terry):
            referral(world.db, aff, 1, first_paid=NOW - dt.timedelta(hours=5))
            world.db.add(m.AffiliatePayout(
                affiliate_id=aff.id, period_start=dt.date(2026, 10, 1), period_end=dt.date(2026, 10, 1),
                currency="usd", commission_amount=D("60"), status="paid", external_ref="W-9",
                computed_at=NOW - dt.timedelta(days=2), paid_at=NOW - dt.timedelta(hours=1)))
        world.db.commit()
        run(world)
        assert [(x.to, x.subject) for x in world.outbox] == [("terry@partner.example", "Payout sent: $60.00")]

    def test_dry_run_writes_and_sends_nothing(self, world):
        aff, _ = partner(world.db, signed_days_ago=1)
        stats = run(world, dry_run=True)
        assert stats["sent"] == 1 and world.outbox == [] and notes(world.db) == []

    def test_one_broken_partner_does_not_stop_the_job(self, world):
        c = comms()
        partner(world.db, "ANNE", signed_days_ago=1)
        partner(world.db, "BOB", signed_days_ago=1)
        real = c.collect_events

        def flaky(session, aff, now=None, campaigns=None):
            if aff.code == "ANNE":
                raise RuntimeError("boom")
            return real(session, aff, now, campaigns)

        world.patch(c, "collect_events", flaky)
        stats = run(world)
        assert stats["errors"] == 1 and stats["sent"] == 1
        assert [x.to for x in world.outbox] == ["bob@partner.example"]

    def test_welcome_right_after_signing(self, world):
        import models as m
        c = comms()
        aff, _ = partner(world.db, signed_days_ago=0)
        world.patch(m, "Session", world.factory)
        world.patch(c, "_now", lambda now=None: now or NOW + dt.timedelta(minutes=1))
        c.notify_signed(aff.id)
        assert [x.subject for x in world.outbox] == ["Welcome to the TradeWave partner program"]
        c.notify_signed(aff.id)                                    # and the daily job later: no repeat
        assert len(world.outbox) == 1
        c.notify_signed(uuid.uuid4())                              # unknown id: no error


# ---------------------------------------------------------------------------
# 5. partner portal: Messages inbox, unread badge, email preferences
# ---------------------------------------------------------------------------
BASE = "/account/affiliate"


@pytest.fixture
def portal(world, monkeypatch):
    state = SimpleNamespace(user=None, catalog=h.CATALOG)
    h.fake_stripe(monkeypatch.setattr)
    app = h.make_app(monkeypatch.setattr, world.factory, state)
    world.state, world.client = state, app.test_client()
    return world


def page(portal, path):
    r = portal.client.get(BASE + path)
    return r, r.get_data(as_text=True)


class TestPortalInbox:
    def _seed(self, portal):
        c = comms()
        aff, user = partner(portal.db)
        other, _ = partner(portal.db, "BOB")
        c.send_message(portal.db, subject="New banners for {first_name}",
                       body="Hi {first_name},\n\nFresh banners are on your Promote page.\nSee {dashboard}",
                       audience="active", sent_by="admin:x", now=NOW)
        c.deliver(portal.db, aff, c.make_event(
            "payout_sent", "payout:9", "Payout sent: $60.00", "We sent your payout.",
            occurred_at=NOW, link=("See your payouts", "https://tw.test/account/affiliate/payouts")), NOW)
        portal.state.user = user
        return aff, other

    def test_tab_badge_list_and_read_flow(self, portal):
        aff, other = self._seed(portal)
        r, home = page(portal, "/settings")
        assert r.status_code == 200
        assert re.search(r'/account/affiliate/messages"[^>]*>Messages <span class="navbadge"[^>]*>2</span>', home)
        r, html = page(portal, "/messages")
        assert r.status_code == 200 and EM_DASH not in html
        assert "New banners for Anne" in html and "Payout sent: $60.00" in html
        assert "Mark all as read" in html and html.count('class="msgrow unread"') == 2
        assert "New banners for Bob" not in html                    # only my own messages
        mine = notes(portal.db, aff, "message")[0]
        r, html = page(portal, "/messages/%d" % mine.id)
        assert r.status_code == 200
        assert "Fresh banners are on your Promote page.<br>See https://tw.test/account/affiliate" in html
        assert "Also emailed to anne@partner.example" in html
        assert comms().unread_count(portal.db, aff.id) == 1         # opening it marked it read
        _r, html = page(portal, "/messages")
        assert html.count('class="msgrow unread"') == 1
        assert '<span class="navbadge" aria-label="1 unread">1</span>' in html
        r = portal.client.post(BASE + "/messages/read-all")
        assert r.status_code == 302 and comms().unread_count(portal.db, aff.id) == 0
        _r, html = page(portal, "/messages")
        assert "navbadge\"" not in html and "Mark all as read" not in html

    def test_cannot_open_another_partners_message(self, portal):
        aff, other = self._seed(portal)
        theirs = notes(portal.db, other)[0]
        r, _ = page(portal, "/messages/%d" % theirs.id)
        assert r.status_code == 404
        assert comms().unread_count(portal.db, other.id) == 1       # and it was not marked read
        r, _ = page(portal, "/messages/999999")
        assert r.status_code == 404

    def test_empty_inbox_and_login_gate(self, portal):
        aff, user = partner(portal.db)
        r, _ = page(portal, "/messages")
        assert r.status_code == 302 and "/login" in r.headers["Location"]
        portal.state.user = user
        r, html = page(portal, "/messages")
        assert r.status_code == 200 and "No messages yet" in html and "navbadge\"" not in html

    def test_email_preferences_in_settings(self, portal):
        c = comms()
        aff, user = partner(portal.db)
        portal.state.user = user
        r, html = page(portal, "/settings")
        assert r.status_code == 200 and EM_DASH not in html
        assert 'id="email"' in html and "Email preferences" in html
        for _pid, label, _help in c.PREFS:
            assert label in html
        assert html.count('name="on"') == len(c.PREFS) and html.count("checked") >= len(c.PREFS)
        assert "Emails every partner gets" in html and "Payout sent." in html
        r = portal.client.post(BASE + "/settings/email",
                               data={"on": ["new_customer", "statement_ready", "bogus"]})
        assert r.status_code == 302 and r.headers["Location"].endswith("/settings#email")
        assert c.disabled_prefs(portal.db, aff.id) == set(c.PREF_IDS) - {"new_customer", "statement_ready"}
        _r, html = page(portal, "/settings")
        assert 'value="new_customer" checked' in html and 'value="announcement" >' in html
        # another partner is untouched
        bob, _ = partner(portal.db, "BOB")
        assert c.disabled_prefs(portal.db, bob.id) == set()


# ---------------------------------------------------------------------------
# 6. public pages + admin screens on the real app
# ---------------------------------------------------------------------------
@pytest.fixture
def site(world, monkeypatch):
    import models as m
    mod = importlib.import_module("app")
    monkeypatch.setattr(m, "Session", world.factory)
    monkeypatch.setattr(mod, "write_audit", lambda **kw: world.audit.append(kw))
    monkeypatch.setitem(mod.app.config, "WTF_CSRF_ENABLED", False)
    world.audit = []
    world.mod, world.client = mod, mod.app.test_client()
    return world


@pytest.fixture
def admin(site, monkeypatch):
    monkeypatch.setattr(site.mod, "get_current_user",
                        lambda: SimpleNamespace(id="u-admin", email="afshin@example.com",
                                                roles=["super_admin"]))
    return site


def body(resp, status=200):
    assert resp.status_code == status, resp.status_code
    return resp.get_data(as_text=True)


class TestApplyPage:
    def test_form_renders_with_the_program_numbers(self, site):
        html = body(site.client.get("/partners/apply"))
        assert EM_DASH not in html
        for needle in ("Become a", "Up to 50%", "On a $100 plan that is up to $50", "in years 2 to 5",
                       "Up to 25% off", "Program policies", "Say you earn a commission",
                       'name="company_url"', 'name="audience_size"', "Send my application",
                       '<meta name="viewport"'):
            assert needle in html
        assert "noindex" not in html                               # the page is meant to be found

    def test_submit_shows_thanks_and_stores_the_application(self, site):
        html = body(site.client.post("/partners/apply", data=GOOD_FORM,
                                     environ_base={"REMOTE_ADDR": "203.0.113.50"}))
        assert "We have your application" in html and "Send my application" not in html
        (row,) = site.db.query(models().AffiliateApplication).all()
        assert row.email == "maya@example.com" and row.status == "new"
        assert [m.subject for m in site.outbox] == [
            "We received your TradeWave partner application", "New partner application: Maya Stone"]

    def test_errors_keep_what_was_typed(self, site):
        html = body(site.client.post("/partners/apply", data=dict(GOOD_FORM, email="nope", agree="")), 400)
        assert "Please enter a valid email address." in html and "tick the box" in html
        assert 'value="Maya Stone"' in html and "A review video" in html
        assert site.outbox == []

    def test_honeypot_looks_like_success(self, site):
        html = body(site.client.post("/partners/apply", data=dict(GOOD_FORM, company_url="x")))
        assert "We have your application" in html
        assert site.db.query(models().AffiliateApplication).count() == 0 and site.outbox == []

    def test_rate_limit_page(self, site):
        for i in range(comms().APPLY_LIMIT_PER_IP_DAY):
            body(site.client.post("/partners/apply", data=dict(GOOD_FORM, email="a%d@example.com" % i),
                                  environ_base={"REMOTE_ADDR": "203.0.113.77"}))
        html = body(site.client.post("/partners/apply", data=dict(GOOD_FORM, email="z@example.com"),
                                     environ_base={"REMOTE_ADDR": "203.0.113.77"}), 429)
        assert "Please try again tomorrow" in html

    def test_form_post_needs_the_csrf_token(self, site):
        site.mod.app.config["WTF_CSRF_ENABLED"] = True
        assert site.client.post("/partners/apply", data=GOOD_FORM).status_code == 400
        assert site.db.query(models().AffiliateApplication).count() == 0

    def test_linked_from_join_page_footer_and_site_footer(self):
        assert 'href="/partners/apply"' in (REPO / "web/templates/affiliate_landing.html").read_text()
        gen = (REPO / "site/generate_text_pages.py").read_text()
        assert '<a href="/partners/apply">Become a partner</a>' in gen
        assert 'href="{PARTNER_APPLY_URL}">Apply now' in gen
        assert "location /partners/" in (REPO / "ops/nginx/sites-available/tradewave").read_text()


class TestPreferenceLinks:
    def test_public_page_saves_without_login(self, site):
        c = comms()
        aff, _ = partner(site.db)
        url = c.prefs_url(aff).replace("https://tw.test", "")
        html = body(site.client.get(url))
        assert "For partner code ANNE" in html and "Always sent" in html and EM_DASH not in html
        assert html.count('name="on"') == len(c.PREFS) and "noindex" in html
        html = body(site.client.post(url, data={"on": ["new_customer"]}))
        assert "Saved. Your email preferences are updated." in html
        assert c.disabled_prefs(site.db, aff.id) == set(c.PREF_IDS) - {"new_customer"}
        html = body(site.client.post(url, data={"all_off": "yes", "on": ["new_customer"]}))
        assert "All optional partner emails are off" in html
        assert c.disabled_prefs(site.db, aff.id) == set(c.PREF_IDS)

    def test_stop_link_preselects_but_a_get_changes_nothing(self, site):
        c = comms()
        aff, _ = partner(site.db)
        url = c.prefs_url(aff, "statement_ready").replace("https://tw.test", "")
        html = body(site.client.get(url))
        assert "We unticked the email you asked to stop" in html
        assert 'value="statement_ready" >' in html and 'value="new_customer" checked' in html
        assert c.disabled_prefs(site.db, aff.id) == set()           # mail scanners prefetch links

    def test_one_click_unsubscribe_post_works_without_csrf(self, site):
        c = comms()
        aff, _ = partner(site.db)
        site.mod.app.config["WTF_CSRF_ENABLED"] = True
        url = c.one_click_url(aff, "announcement").replace("https://tw.test", "")
        assert site.client.post(url, data={"List-Unsubscribe": "One-Click"}).status_code == 200
        assert c.disabled_prefs(site.db, aff.id) == {"announcement"}
        assert site.client.get(url).status_code == 405
        assert site.client.post(url.replace("/announcement", "/payout_sent")).status_code == 404

    def test_bad_token(self, site):
        partner(site.db)
        html = body(site.client.get("/partners/email-preferences/not-a-token"), 404)
        assert "This link is not valid" in html
        assert site.client.post("/partners/unsubscribe/not-a-token/announcement").status_code == 404
        forged = comms().make_pref_token(uuid.uuid4())
        body(site.client.get("/partners/email-preferences/" + forged), 404)


class TestAdminApplications:
    def test_menu(self, admin):
        names = [v.name for v in admin.mod.admin._views]
        assert "Applications" in names and "Messages" in names

    def test_needs_super_admin(self, site, monkeypatch):
        monkeypatch.setattr(site.mod, "get_current_user", lambda: None)
        assert site.client.get("/admin/affiliate_applications/").status_code in (302, 403)
        assert site.client.get("/admin/affiliate_messages/").status_code in (302, 403)

    def test_list_review_approve(self, admin, stripe_ok):
        c, m = comms(), models()
        c.submit_application(admin.db, GOOD_FORM, now=NOW)
        h.make_partner(admin.db, "ZED", email="zed@example.com")
        c.submit_application(admin.db, dict(GOOD_FORM, name="Zed Two", email="zed@example.com"), now=NOW)
        admin.outbox.clear()
        html = body(admin.client.get("/admin/affiliate_applications/"))
        assert EM_DASH not in html
        for needle in ("Partner applications", "New (2)", "Approved (0)", "Maya Stone",
                       "10,000 to 50,000", "Already a partner: ZED", "Review"):
            assert needle in html
        row = admin.db.query(m.AffiliateApplication).filter_by(email="maya@example.com").one()
        html = body(admin.client.get("/admin/affiliate_applications/view?id=%s" % row.id))
        for needle in ('name="code" value="MAYA"', 'name="discount_pct" value="20"',
                       "Approve and send signing link", "terms <strong>v2-5y</strong>",
                       "YouTube: Maya Trades (42k)", "Mark as spam"):
            assert needle in html
        assert EM_DASH not in html
        # a bad code re-renders the form with the problem, nothing is created
        html = body(admin.client.post("/admin/affiliate_applications/approve",
                                      data={"id": str(row.id), "code": "ZED", "discount_pct": "10",
                                            "send_email": "yes"}), 400)
        assert "The code ZED is taken" in html and 'name="code" value="ZED"' in html
        r = admin.client.post("/admin/affiliate_applications/approve",
                              data={"id": str(row.id), "code": "maya", "discount_pct": "10",
                                    "note": "Glad to have you.", "send_email": "yes"})
        assert r.status_code == 302
        aff = admin.db.query(m.Affiliate).filter_by(code="MAYA").one()
        assert aff.status == "paused" and aff.discount_pct == D(10) and aff.terms_id == 1
        assert [x.subject for x in admin.outbox] == ["Sign your TradeWave Affiliate Agreement"]
        assert admin.audit[-1]["action"] == "affiliate_application_approved"
        html = body(admin.client.get("/admin/affiliate_applications/view?id=%s" % row.id))
        assert "Partner created" in html and "Approve and send signing link" not in html
        assert "was emailed to maya@example.com" in html
        # the duplicate cannot be approved
        dup = admin.db.query(m.AffiliateApplication).filter_by(email="zed@example.com").one()
        html = body(admin.client.get("/admin/affiliate_applications/view?id=%s" % dup.id))
        assert "Duplicate: this email is already a partner." in html and "disabled" in html
        body(admin.client.post("/admin/affiliate_applications/approve",
                               data={"id": str(dup.id), "code": "ZED2", "discount_pct": "10"}), 400)

    def test_approve_without_working_email_shows_the_link(self, admin, stripe_ok):
        c, m = comms(), models()
        _o, row = c.submit_application(admin.db, GOOD_FORM, now=NOW)
        admin.send.ok = False
        admin.client.post("/admin/affiliate_applications/approve",
                          data={"id": str(row.id), "code": "MAYA", "discount_pct": "0", "send_email": "yes"})
        html = body(admin.client.get("/admin/affiliate_applications/view?id=%s" % row.id))
        assert "The email was NOT sent" in html and "/affiliate/sign/" in html

    def test_reject_and_spam(self, admin):
        c, m = comms(), models()
        _o, row = c.submit_application(admin.db, GOOD_FORM, now=NOW)
        _o, junk = c.submit_application(admin.db, dict(GOOD_FORM, email="junk@example.com"), now=NOW)
        admin.outbox.clear()
        r = admin.client.post("/admin/affiliate_applications/reject",
                              data={"id": str(row.id), "reason": "Not a fit this year.", "send_email": "yes"})
        assert r.status_code == 302
        admin.db.expire_all()
        assert admin.db.get(m.AffiliateApplication, row.id).status == "rejected"
        assert "Not a fit this year." in admin.outbox[0].text
        admin.client.post("/admin/affiliate_applications/spam", data={"id": str(junk.id)})
        admin.db.expire_all()
        assert admin.db.get(m.AffiliateApplication, junk.id).status == "spam"
        assert len(admin.outbox) == 1
        html = body(admin.client.get("/admin/affiliate_applications/?status=rejected"))
        assert "Maya Stone" in html and "Rejected (1)" in html and "Spam (1)" in html
        assert admin.client.get("/admin/affiliate_applications/view?id=nope").status_code == 302


class TestAdminMessages:
    def _cast(self, admin):
        anne, _ = partner(admin.db, "ANNE")
        bob, _ = partner(admin.db, "BOB")
        paul, _ = partner(admin.db, "PAUL", status="paused")
        referral(admin.db, anne, 1, first_paid=NOW - dt.timedelta(days=3))
        comms().turn_off_pref(admin.db, bob.id, "announcement")
        return anne, bob, paul

    def test_compose_preview_send_log(self, admin):
        anne, bob, paul = self._cast(admin)
        html = body(admin.client.get("/admin/affiliate_messages/"))
        assert EM_DASH not in html
        for needle in ("Send a message to partners", "No new paying customer in the last N days",
                       "Partners on one terms version", "ANNE - Anne Lee (active)", "{first_name}",
                       "Preview recipients", "No messages sent yet"):
            assert needle in html
        assert admin.client.get("/admin/affiliate_messages/count?audience=active").get_json() == {"count": 2}
        assert admin.client.get("/admin/affiliate_messages/count?audience=has_customers").get_json() == {"count": 1}
        assert admin.client.get("/admin/affiliate_messages/count?audience=inactive&days=2").get_json() == {"count": 3}
        assert "error" in admin.client.get("/admin/affiliate_messages/count?audience=one").get_json()
        form = {"audience": "active", "subject": "Hello {first_name}",
                "body": "Hi {first_name},\n\nNew banners are live for code {code}."}
        html = body(admin.client.post("/admin/affiliate_messages/preview", data=form))
        assert '<span class="count">2</span> partners will get this' in html
        assert "1 by email, 1 in the inbox only" in html
        assert "ANNE (Anne Lee), BOB (Bob Lee)" in html and "Subject</td><td>Hello Anne" in html
        assert "New banners are live for code ANNE." in html and "Send to 2 partners" in html
        assert admin.outbox == []                                  # a preview sends nothing
        r = admin.client.post("/admin/affiliate_messages/send", data=form)
        assert r.status_code == 302 and "/admin/affiliate_messages/log?id=1" in r.headers["Location"]
        assert [x.to for x in admin.outbox] == ["anne@partner.example"]
        assert admin.audit[-1]["action"] == "affiliate_message_sent"
        html = body(admin.client.get("/admin/affiliate_messages/log?id=1"))
        for needle in ("Message recipients", "Sent to 2 partners: 1 emailed, 1 inbox only, 0 failed.",
                       "Partner turned this email off", "Active partners (2)", "Hello Bob"):
            assert needle in html
        html = body(admin.client.get("/admin/affiliate_messages/log"))
        assert "Partner email log" in html and "Hello Anne" in html
        html = body(admin.client.get("/admin/affiliate_messages/"))
        assert "Hello {first_name}" in html and "Details" in html

    def test_one_partner_and_bad_input(self, admin):
        anne, bob, paul = self._cast(admin)
        html = body(admin.client.post("/admin/affiliate_messages/preview",
                                      data={"audience": "one", "partner": str(paul.id),
                                            "subject": "About your pause", "body": "Hi {first_name}, a quick note."}))
        assert '<span class="count">1</span> partner will get this' in html
        assert "One partner: PAUL (Paul Lee)" in html
        html = body(admin.client.post("/admin/affiliate_messages/preview",
                                      data={"audience": "one", "subject": "x", "body": "y"}), 400)
        assert "Subject must be 3 to 150 characters." in html
        html = body(admin.client.post("/admin/affiliate_messages/send",
                                      data={"audience": "terms", "terms": "3", "subject": "Hello all",
                                            "body": "Nobody is on these terms."}), 400)
        assert "Nobody matches that group" in html and admin.outbox == []
        html = body(admin.client.get("/admin/affiliate_messages/?partner=%s" % paul.id))
        assert 'value="%s" selected' % paul.id in html


# ---------------------------------------------------------------------------
# 7. migration, cron, docs
# ---------------------------------------------------------------------------
def test_migration_adds_the_four_tables_from_the_v2_head():
    import models as m
    mig = (REPO / "migrations/versions/c5e8f1a2b3d6_affiliate_lifecycle_comms.py").read_text()
    assert "revision = 'c5e8f1a2b3d6'" in mig and "down_revision = 'b4d7e1f2a3c5'" in mig
    assert "affiliate_lifecycle_comms" in mig
    for table in COMMS_TABLES:
        assert 'create_table(\n        "%s"' % table in mig
        assert 'drop_table("%s")' % table in mig
        block = mig.split('create_table(\n        "%s"' % table)[1].split("\n    )\n")[0]
        migrated = set(re.findall(r'sa\.Column\("(\w+)"', block))
        assert migrated == set(c.name for c in m.Base.metadata.tables[table].columns), table
    assert "uq_affiliate_notification_event" in mig


def test_cron_installer_runs_the_daily_job():
    script = (REPO / "ops/install_affiliate_comms_cron.sh").read_text()
    assert "10 14 * * *" in script and "/home/flask/web/affiliate_comms.py" in script
    assert "flock -n" in script and "grep -v 'affiliate_comms.py'" in script     # idempotent install
    assert "install_affiliate_comms_cron.sh" in (REPO / "ops/install_affiliate_crons.sh").read_text()


def test_docs_and_admin_guide_cover_the_new_features():
    guide = (REPO / "docs/AFFILIATE_PARTNER_GUIDE.md").read_text()
    for needle in ("Messages", "Email preferences", "/partners/apply", "60, 30 and 7 days"):
        assert needle in guide, needle
    assert EM_DASH not in guide
    app_src = (REPO / "web/app.py").read_text()
    tmpl = app_src.split("_AFFILIATE_GUIDE_TMPL = ")[1].split("class AffiliateGuideView")[0]
    for needle in ("Applications", "Send a message", "Automatic emails", "affiliate_comms.py"):
        assert needle in tmpl, needle
    for src in ("web/affiliate_comms.py", "web/affiliate_comms_admin.py", "web/affiliate_comms_views.py",
                "web/affiliate_portal/messages.py", "web/templates/partner_apply.html",
                "web/templates/partner_email_prefs.html",
                "web/affiliate_portal/templates/aff_messages.html",
                "web/affiliate_portal/templates/aff_email_prefs.html"):
        text = (REPO / src).read_text()
        # the only long dash allowed is the one the validators look for
        assert text.count(EM_DASH) == text.count('"%s"' % EM_DASH), src
