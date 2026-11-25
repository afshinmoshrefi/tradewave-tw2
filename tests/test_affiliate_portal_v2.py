"""Partner dashboard v2 (TW-TASK-0038 Phase 2): the seven-tab portal, the
self-serve discount, anonymized customers, the earnings ledger, CSV exports,
the QR encoder, the /join price cards and the MCP affiliate view.

Hermetic: SQLite copy of the affiliate tables, fake Stripe, a tiny Flask app
with the REAL blueprint (see tests/affiliate_portal_harness.py)."""
import csv
import datetime as dt
import io
import json
import re
import uuid
from decimal import Decimal
from types import SimpleNamespace

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affiliate_portal_harness as h  # noqa: E402

pytestmark = pytest.mark.unit

UTC = dt.timezone.utc
BASE = "/account/affiliate"
PAGES = ["/", "/earnings", "/customers", "/links", "/promote", "/payouts", "/settings"]
EM_DASH = "—"


@pytest.fixture
def portal(monkeypatch):
    db, factory, engine = h.make_db()
    state = SimpleNamespace(user=None, catalog=h.CATALOG)
    world = h.fake_stripe(monkeypatch.setattr)
    app = h.make_app(monkeypatch.setattr, factory, state)
    yield SimpleNamespace(db=db, factory=factory, state=state, world=world, app=app,
                          client=app.test_client(), patch=monkeypatch.setattr)
    db.close()
    engine.dispose()


def login(portal, user):
    portal.state.user = user


def get(portal, path, **kw):
    r = portal.client.get(BASE + path, **kw)
    return r, r.get_data(as_text=True)


def save_discount(portal, pct, **extra):
    """The second (confirmed) step of a discount change."""
    data = {"discount_pct": str(pct), "confirm": "yes"}
    data.update(extra)
    return portal.client.post(BASE + "/settings/discount", data=data)


def flashes(portal):
    with portal.client.session_transaction() as sess:
        return [m for _c, m in sess.get("_flashes", [])]


# ---------------------------------------------------------------------------
# pages render: active, paused, no-data, unsigned
# ---------------------------------------------------------------------------
class TestPagesRender:
    def test_active_partner_every_tab(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        for path in PAGES:
            r, html = get(portal, path)
            assert r.status_code == 200, path
            assert EM_DASH not in html, path            # house style: " - " only
            for tab in ("Home", "Earnings", "Customers", "Links", "Promote", "Payouts", "Settings"):
                assert ">%s</a>" % tab in html
        _r, home = get(portal, "/")
        assert "Estimated this month" in home and "Pending payout" in home
        assert "Paid to date" in home and "Active customers" in home
        assert "$108.45" in home and "$119.70" in home          # pending / paid payouts
        assert "You&#39;re active until" in home
        assert "Refer 1 new paying customer before then to keep your renewal commissions." in home
        assert "with a 30-day grace" in home
        for step in ("Clicks", "Signups", "Paid"):
            assert "<b>%s</b>" % step in home
        # every signup starts a trial, so there is no separate trial step
        assert "Trials started" not in home and "(each starts a 7-day trial)" in home
        assert "Welcome back, Anne" in home and "How you get paid" not in home
        assert "Click to paid" in home and "Earnings per click" in home
        assert "If every customer renews at today's price" in home
        # live promotion card, in the owner's words and dollars
        assert "Black Friday - Analyst annual $99 first year (list $399)." in home
        assert "You earn $49.50" in home and "Customer renews at $399" in home
        assert "whichever price is lower - the sale or your discount" in home
        assert "qr.svg" in home
        # no action strip for a partner in good standing
        assert "Send your tax form" not in home and "Add a payout method" not in home

    def test_funnel_ranges(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        for key in ("7d", "30d", "90d", "12m", "all", "bogus"):
            r, html = get(portal, "/?range=" + key)
            assert r.status_code == 200
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash
        s = portal.factory()
        live = s.get(type(aff), aff.id)
        lines = dash.ledger(s, live)
        f7 = dash.funnel(s, live, lines, "7d")
        fall = dash.funnel(s, live, lines, "all")
        assert f7["clicks"] == 9 + 14 + 6 + 22 and fall["clicks"] == 278
        assert f7["signups"] == 3 and fall["signups"] == 9 and fall["trials"] == 9
        assert f7["paid"] == 1 and fall["paid"] == 4      # every first payment, returns excluded
        assert fall["click_to_paid"] == "1.4%" and fall["epc"].startswith("$")
        assert dash.funnel(s, live, lines, "bogus")["range"] == "30d"
        assert afs is not None
        s.close()

    def test_old_urls_redirect(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        for old, new in (("/performance", "/earnings"), ("/guide", "/promote#guide"),
                         ("/profile", "/settings#profile")):
            r, _ = get(portal, old)
            assert r.status_code == 302 and r.headers["Location"].endswith(BASE + new)
        r, md = get(portal, "/guide.md")
        assert r.status_code == 200 and "Referral code: `ANNE`" in md

    def test_paused_partner_estimate_is_not_zero(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world, code="PAUL", status="paused")
        login(portal, user)
        from affiliate_portal import routes
        with portal.app.test_request_context(BASE + "/"):
            est = routes._estimate_full(aff)
        # the old code returned [] ($0) for anyone not 'active'
        assert est["rows"] and est["rows"][0]["commission_amount"] == Decimal("0.00")
        assert est["rows"][0]["held_amount"] == Decimal("8.70")
        assert [ln["state"] for ln in est["lines"] if not ln.get("persisted")] == ["held"]
        for path in PAGES:
            r, html = get(portal, path)
            assert r.status_code == 200, path
        _r, home = get(portal, "/")
        assert "Your account is paused" in home
        # buckets add up: this month's $8.70 sits in the Held tile, not in Estimated
        assert '<div class="k">Held</div>' in home and "$58.20" in home
        assert "are in Held while you are paused" in home
        _r, earn = get(portal, "/earnings")
        assert ("Your account is paused.</b><span>Commissions keep adding up and are paid when it "
                "is reactivated.") in earn
        # the hold reason on the lines, in plain words
        assert "Held while your account is paused - paid when it&#39;s reactivated." in earn
        assert "Account paused" not in earn and "waiting on something" not in earn
        assert "$58.20" in earn                               # held tile: 49.50 + 8.70
        _r, pay = get(portal, "/payouts")
        assert "Commissions keep adding up and are paid when it is reactivated." in pay

    def test_new_partner_empty_states_and_actions(self, portal):
        aff, user = h.seed_empty(portal.db)
        login(portal, user)
        for path in PAGES:
            r, html = get(portal, path)
            assert r.status_code == 200, path
            assert EM_DASH not in html
        _r, home = get(portal, "/")
        assert "Send your tax form" in home and "Add a payout method" in home
        assert "No visits yet in this period" in home
        assert "Your first paying customer starts the clock." in home
        assert "Your forecast starts with your first paying customer" in home
        assert "Your audience gets 10% off. You earn 40% of the list price." in home
        assert "No earnings yet" in get(portal, "/earnings")[1]
        assert "No customers yet" in get(portal, "/customers")[1]
        pay = get(portal, "/payouts")[1]
        assert "No payouts yet" in pay and "$50 minimum reached" in pay and "$50.00 to go" in pay

    def test_unsigned_partner_can_request_the_signing_link(self, portal):
        aff, user = h.seed_empty(portal.db, code="UNSIGNED", status="paused", agreement_signed_at=None)
        from affiliate_portal import routes as portal_routes
        portal_routes._resend_at.clear()  # module-level throttle; ids repeat across tests
        login(portal, user)
        _r, home = get(portal, "/")
        assert "Sign your partner agreement" in home and "Your account is paused" not in home
        import affiliate_agreement as agr
        sent = []
        portal.patch(agr, "email_signing_link", lambda a, note=None: sent.append(a.code) or True)
        r = portal.client.post(BASE + "/agreement/resend")
        assert r.status_code == 302 and sent == ["UNSIGNED"]
        portal.client.post(BASE + "/agreement/resend")          # throttled: no second email
        assert sent == ["UNSIGNED"]

    def test_logged_out_and_non_affiliate(self, portal):
        r, _ = get(portal, "/")
        assert r.status_code == 302 and "/login" in r.headers["Location"]
        import models
        stranger = models.User(id=uuid.uuid4(), email="nobody@example.com", tier="explorer")
        portal.db.add(stranger)
        portal.db.commit()
        login(portal, stranger)
        r, html = get(portal, "/settings")
        assert r.status_code == 200 and "Your offer" not in html

    def test_activity_deadline_within_60_days_is_amber_and_lapsed_is_red(self, portal):
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_empty(portal.db, code="AMBER")
        now = dt.datetime(2026, 11, 24, tzinfo=UTC)
        terms = afs.DEFAULT_TERMS

        real_status = afs.activity_status

        def card(first_paid):
            status = real_status(aff, now, first_paid_dates=first_paid, terms=terms)
            portal.patch(afs, "activity_status", lambda *a, **k: status)
            return dash.activity_card(aff, None, terms, now)

        soon = card([afs._add_months(now, -11)])
        assert soon["tone"] == "amber" and "left" in soon["badge"]
        # the date is activity_status()["active_until"], never recomputed here
        assert soon["title"] == "You're active until %s." % dash.fmt_date(soon["status"]["active_until"])
        strip = dash.action_items(aff, soon, {"links": "/x"})
        assert any(i["key"] == "activity" for i in strip)
        fresh = card([now - dt.timedelta(days=10)])
        assert fresh["tone"] == "green"
        gone = card([afs._add_months(now, -30)])
        assert gone["tone"] == "red"
        assert gone["title"] == "Renewal commissions are stopped."
        assert gone["text"] == ("They start again with your next new paying customer. "
                                "Renewals during the gap are not paid back.")


# ---------------------------------------------------------------------------
# settings: discount chooser
# ---------------------------------------------------------------------------
class TestDiscount:
    @pytest.fixture
    def partner(self, portal):
        import affiliate_service as afs
        aff, user = h.seed_empty(portal.db, code="DISC", discount_pct=h.D(20))
        login(portal, user)
        calls = []
        portal.patch(afs, "reissue_coupon",
                     lambda a, pct: calls.append(pct) or ("cpn_new_%s" % pct, "promo_new_%s" % pct))
        import stripe
        portal.patch(stripe.PromotionCode, "modify", lambda *a, **k: calls.append(("modify", a, k)))
        return SimpleNamespace(aff=aff, user=user, calls=calls)

    def _pct(self, portal, aff):
        s = portal.factory()
        try:
            return s.get(type(aff), aff.id).discount_pct
        finally:
            s.close()

    def test_page_shows_the_pool_copy_and_live_table(self, portal, partner):
        _r, html = get(portal, "/settings")
        assert "You have 50% of the list price to split." in html
        assert "Give your audience up to 25% off. You earn the rest." in html
        assert "keep the rest" not in html and "You keep" not in html
        assert re.search(r"Example: \$100 plan at <span id=\"ex-pct\">20</span>% off - they pay "
                         r"<span id=\"ex-pay\">\$80</span>, you earn <span id=\"ex-earn\">\$30</span>", html)
        for head in ("List price", "Customer pays", "You earn (year 1)", "Per renewal"):
            assert '<th class="num">%s</th>' % head in html
            assert 'data-label="%s"' % head in html                # short stacked labels (phone)
        assert "You earn on this payment (first year)" not in html
        assert ("New discount applies to customers who sign up after you save. "
                "Nothing changes for customers you already have.") in html
        assert "$319.20" in html and "$119.70" in html and "$99.75" in html     # Analyst annual @20%
        assert "Choosing 0% removes your checkout code" in html
        grid = json.loads(re.search(r"var GRID = (\{.*?\}), CURRENT", html, re.S).group(1))
        assert sorted(map(int, grid["plans"])) == list(range(0, 26))
        assert grid["example"]["0"] == [10000, 5000]
        assert grid["example"]["5"] == [9500, 4500]
        assert grid["example"]["20"] == [8000, 3000]
        assert grid["plans"]["25"]["analyst:year"] == [29925, 9975]

    def test_save_valid_discount(self, portal, partner):
        # step 1: nothing is saved, the page asks first
        r = portal.client.post(BASE + "/settings/discount", data={"discount_pct": "15"})
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/settings?confirm=15#offer-status")
        assert self._pct(portal, partner.aff) == Decimal("20.00") and partner.calls == []
        _r, html = get(portal, "/settings?confirm=15")
        assert "Change your discount from 20% to 15%?" in html
        assert "Posts and videos that say 20% off will now be wrong. New customers get 15%." in html
        assert 'name="confirm" value="yes"' in html and "Keep 20%" in html
        # a confirmation for another number does not save
        save_discount(portal, 10, confirm_for="15")
        assert self._pct(portal, partner.aff) == Decimal("20.00")
        # step 2
        r = save_discount(portal, 15, confirm_for="15")
        assert r.status_code == 302 and r.headers["Location"].endswith("/settings#offer-status")
        assert self._pct(portal, partner.aff) == Decimal("15.00")
        assert partner.calls == [Decimal("15.00")]
        msg = flashes(portal)[-1]
        assert "New customers now get 15% off" in msg and "already have" in msg
        _r, html = get(portal, "/settings")
        # the result is shown beside the Save button, not at the top of the page
        status = html.split('id="offer-status"')[1].split("</form>")[0]
        assert 'class="inline-msg success"' in status and "New customers now get 15% off" in status
        assert 'class="flash' not in html
        assert "20% to <b>15%</b>" in html and ">You<" in html              # history row
        assert "You can change your discount once every 24 hours. Next change available" in html

    @pytest.mark.parametrize("bad", ["26", "25.01", "-1", "abc", "", "nan", "1e9"])
    def test_rejects_out_of_range_and_garbage(self, portal, partner, bad):
        r = portal.client.post(BASE + "/settings/discount", data={"discount_pct": bad})
        assert r.status_code == 302
        assert self._pct(portal, partner.aff) == Decimal("20.00")
        assert partner.calls == []
        msg = flashes(portal)[-1]
        assert "between 0% and 25%" in msg or "as a number" in msg

    @pytest.mark.parametrize("edge", ["0", "25"])
    def test_accepts_the_edges(self, portal, partner, edge):
        save_discount(portal, edge)
        assert self._pct(portal, partner.aff) == Decimal(edge)

    def test_cooldown_one_change_per_24h(self, portal, partner):
        save_discount(portal, 15)
        flashes(portal)
        for data in ({"discount_pct": "10"}, {"discount_pct": "10", "confirm": "yes"}):
            portal.client.post(BASE + "/settings/discount", data=data)
            assert self._pct(portal, partner.aff) == Decimal("15.00")
            assert "once every 24 hours" in flashes(portal)[-1]      # the specific text stays
        assert "Change your discount from" not in get(portal, "/settings?confirm=10")[1]
        # ... and it opens again after 24h
        s = portal.factory()
        live = s.get(type(partner.aff), partner.aff.id)
        live.discount_changed_at = dt.datetime.now(UTC) - dt.timedelta(hours=25)
        s.commit()
        s.close()
        save_discount(portal, 10)
        assert self._pct(portal, partner.aff) == Decimal("10.00")

    @pytest.mark.parametrize("boom", [
        "Stripe coupon create failed: Request req_8sK2: No such coupon: 'cpn_disc'",
        "Could not deactivate the promo code: (psycopg2.OperationalError) server closed",
        "RuntimeError",
    ])
    def test_errors_never_show_raw_exception_text(self, portal, partner, boom):
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash

        def fail(*a, **k):
            raise RuntimeError("Traceback: db host 10.0.0.5") if boom == "RuntimeError" \
                else afs.AffiliateError(boom)
        portal.patch(afs, "set_partner_discount", fail)
        save_discount(portal, 15)
        assert self._pct(portal, partner.aff) == Decimal("20.00")
        assert flashes(portal)[-1] == dash.DISCOUNT_SAVE_FAILED
        html = get(portal, "/settings")[1]
        assert "We couldn&#39;t update your discount. Nothing changed - try again in a few minutes." in html
        assert 'class="inline-msg error"' in html
        for leak in ("Stripe", "req_8sK2", "psycopg2", "Traceback", "10.0.0.5", "coupon create"):
            assert leak not in html

    def test_error_text_mapping(self):
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash, routes
        cooldown = ("You can change your discount once every 24 hours. Next change available "
                    "2026-11-25 14:03 UTC.")
        assert routes._discount_error_text(afs.AffiliateError(cooldown)) == cooldown
        assert routes._discount_error_text(afs.AffiliateError(
            "No change - the discount is already 20%.")).startswith("No change")
        for raw in ("interval must be 'year' or 'month'", "Stripe monthly coupon create failed: x",
                    "a terminated partner cannot change the discount", ""):
            assert routes._discount_error_text(afs.AffiliateError(raw)) == dash.DISCOUNT_SAVE_FAILED

    def test_zero_to_some_discount_confirm_copy(self, portal):
        aff, user = h.seed_empty(portal.db, code="ZED", discount_pct=h.D(0))
        login(portal, user)
        html = get(portal, "/settings?confirm=10")[1]
        assert "Change your discount from 0% to 10%?" in html
        assert "New customers get 10% off from now on." in html and "say 0% off" not in html

    def test_same_value_is_a_no_op(self, portal, partner):
        portal.client.post(BASE + "/settings/discount", data={"discount_pct": "20"})
        assert partner.calls == [] and "No change" in flashes(portal)[-1]

    def test_owner_only(self, portal, partner):
        from affiliate_portal import routes
        portal.patch(routes, "get_current_user", lambda: SimpleNamespace(id=uuid.uuid4()))
        portal.client.post(BASE + "/settings/discount", data={"discount_pct": "15"})
        assert self._pct(portal, partner.aff) == Decimal("20.00")
        assert "Only the account owner" in flashes(portal)[-1]

    def test_get_is_not_allowed_and_csrf_is_enforced(self, portal, monkeypatch):
        aff, user = h.seed_empty(portal.db, code="CSRF", discount_pct=h.D(20))
        r = portal.client.get(BASE + "/settings/discount")
        assert r.status_code == 405
        app = h.make_app(monkeypatch.setattr, portal.factory, portal.state, csrf=True)
        login(portal, user)
        r = app.test_client().post(BASE + "/settings/discount", data={"discount_pct": "15"})
        assert r.status_code == 400
        assert self._pct(portal, aff) == Decimal("20.00")

    def test_zero_discount_hides_the_checkout_code(self, portal):
        aff, user = h.seed_empty(portal.db, code="ZERO", discount_pct=h.D(0))
        login(portal, user)
        links = get(portal, "/links")[1]
        assert "Share your link - at 0% off there is no checkout code." in links
        assert "Customers can also type" not in links
        home = get(portal, "/")[1]
        assert "Customers can also type" not in home
        promote = get(portal, "/promote")[1]
        assert "my code ZERO" not in promote
        aff2, user2 = h.seed_empty(portal.db, code="TEN")
        login(portal, user2)
        assert "Customers can also type TEN at checkout" in get(portal, "/links")[1]


# ---------------------------------------------------------------------------
# customers (anonymized) + CSV
# ---------------------------------------------------------------------------
PRIVATE = re.compile(r"@secret\.example|cus_ANNE|sub_ANNE|in_ANNE|in_r\d|re_r\d|pay-anne", re.I)


class TestCustomers:
    def test_customers_page_never_contains_identities(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        r, html = get(portal, "/customers")
        assert r.status_code == 200
        assert not PRIVATE.search(html)
        for email in h.SECRET_EMAILS:
            assert email not in html
        for n in range(1, 6):
            assert "Customer #%d" % n in html
        for head in ("Signed up", "Plan", "Status", "Commission year", "Next renewal",
                     "Next commission (est.)", "Earned to date", "Source"):
            assert head in html
        assert "Year 2 of 5" in html and "Analyst annual" in html and "Navigator monthly" in html
        assert "Typed code" in html and "Your link" in html and "Signup link" in html
        # and nowhere else in the portal either
        for path in PAGES:
            assert not PRIVATE.search(get(portal, path)[1].replace("pay-anne@partner.example", "")), path

    def test_rows_and_numbers(self, portal):
        import models
        from affiliate_portal import dashboard as dash, routes
        import affiliate_service as afs
        aff, user = h.seed_rich(portal.db, portal.world)
        s = portal.factory()
        live = s.get(models.Affiliate, aff.id)
        terms = afs.terms_for(s, live)
        lines = dash.ledger(s, live)
        act = dash.activity_card(live, s, terms)
        rows = {r["number"]: r for r in dash.customers(s, live, h.CATALOG, terms, lines, act["status"])}
        assert len(rows) == 5
        one = rows[1]                                  # annual, year 2, renewal at today's price
        assert (one["status"], one["year"], one["plan"]) == ("paying", "Year 2 of 5", "Analyst annual")
        assert one["next_commission"] == 9975 and one["earned"] == Decimal("219.45")
        assert one["next_note"] is None
        monthly = next(r for r in rows.values() if r["source_key"] == "promo_code")
        assert monthly["next_commission"] == 870 and monthly["year"] == "Year 1 of 5"
        promo = next(r for r in rows.values() if r["promo"])
        assert promo["next_commission"] == 9975 and promo["earned"] == Decimal("49.50")
        trial = next(r for r in rows.values() if r["status"] == "trial")
        assert trial["next_commission"] is None and trial["year"] == "-"
        ended = next(r for r in rows.values() if r["status"] == "ended")
        assert ended["next_renewal"] == "-" and ended["earned"] == Decimal("0.00")
        assert len(dash.filter_customers(list(rows.values()), status="paying")) == 3
        assert len(dash.filter_customers(list(rows.values()), interval="month")) == 2
        fc = dash.forecast(s, live, h.CATALOG, terms)
        # monthly customer: 8 more first-year months at $8.70, then 4 at the renewal rate
        # ($7.25); plus the two annual customers' renewals at $99.75
        assert fc["total_cents"] == 8 * 870 + 4 * 725 + 2 * 9975
        assert fc["renewal_cents"] == 4 * 725 + 2 * 9975
        assert routes is not None
        s.close()

    def test_renewal_needs_activity_note(self, portal):
        """A renewal that falls after active_until is flagged, not promised."""
        import models
        from affiliate_portal import dashboard as dash
        import affiliate_service as afs
        aff, user = h.make_partner(portal.db, "SOLO")
        now = dt.datetime.now(UTC)
        first = now - dt.timedelta(days=30)
        portal.db.add(models.AffiliateReferral(
            id=uuid.uuid4(), affiliate_id=aff.id, stripe_subscription_id="sub_solo",
            stripe_customer_id="cus_solo", source="checkout", terms_id=1, offer_type="regular",
            discount_pct=h.D(20), tier="analyst", billing_interval="year", list_price_cents=39900,
            attributed_at=first, first_paid_at=first, year_anchor_at=first))
        portal.db.commit()
        s = portal.factory()
        live = s.get(models.Affiliate, aff.id)
        terms = afs.terms_for(s, live)
        status = dict(afs.activity_status(live, session=s, terms=terms))
        status["active_until"] = (now + dt.timedelta(days=200)).date()     # before the renewal
        row = dash.customers(s, live, h.CATALOG, terms, [], status)[0]
        assert row["next_commission"] == 9975
        assert row["next_note"] == "Needs a new paying customer first"
        s.close()

    def test_csv_export(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        r = portal.client.get(BASE + "/customers.csv")
        assert r.status_code == 200 and r.mimetype == "text/csv"
        assert "attachment" in r.headers["Content-Disposition"]
        body = r.get_data(as_text=True)
        assert not PRIVATE.search(body)
        rows = list(csv.reader(io.StringIO(body)))
        assert rows[0] == ["Customer", "Signed up", "Plan", "Status", "Commission year",
                           "Next renewal", "Next commission (est.)", "Next commission note",
                           "Earned to date", "Source"]
        assert len(rows) == 6 and {r[0] for r in rows[1:]} == {"Customer #%d" % n for n in range(1, 6)}
        paying = list(csv.reader(io.StringIO(
            portal.client.get(BASE + "/customers.csv?status=paying").get_data(as_text=True))))
        assert len(paying) == 4 and all(r[3] == "Paying" for r in paying[1:])


# ---------------------------------------------------------------------------
# earnings ledger + CSV
# ---------------------------------------------------------------------------
class TestEarnings:
    def test_ledger_page(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        r, html = get(portal, "/earnings")
        assert r.status_code == 200 and not PRIVATE.search(html)
        for legend in ("<b>Estimated</b> - this month so far, can still change.",
                       "<b>Pending</b> - final, waiting for payout.",
                       "<b>Paid</b> - sent to you.",
                       "<b>Held</b> - earned, not payable yet. Each line says why."):
            assert legend in html
        for kind in ("First year", "Promotion", "Renewal", "Refund adjustment", "Lapsed"):
            assert kind in html
        for state in ("Estimated", "Pending", "Paid"):
            assert ">%s</span>" % state in html
        assert "-$8.70" in html and "$99.75" in html and "$49.50" in html
        assert "Your account is paused" not in html
        # "How it's worked out" replaces the bare rate (first year is a share of LIST)
        assert "<th>How it's worked out</th>" in html and ">Rate<" not in html
        for how in ("30% of $29.00 list", "50% of $99.00 paid", "25% of $399.00 paid",
                    "30% of $399.00 list", "Reverses 30% of $29.00 list"):
            assert how in html
        assert "waiting on something" not in html
        # phone: lines grouped per month, collapsible, with a month total
        assert html.count('<details class="month"') >= 5
        assert re.search(r'<span class="mname">\w+ \d{4}</span>\s*<span class="mmeta">\d+ lines?</span>', html)

    def test_lines_states_and_totals(self, portal):
        import models
        from affiliate_portal import dashboard as dash, routes
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        with portal.app.test_request_context(BASE + "/"):
            est = routes._estimate_full(aff)
        s = portal.factory()
        live = s.get(models.Affiliate, aff.id)
        lines = dash.ledger(s, live, est["lines"])
        assert len(lines) == 9
        newest = lines[0]
        assert (newest["state_key"], newest["type"], newest["amount"]) == \
            ("estimated", "First year", Decimal("8.70"))
        assert newest["customer"].startswith("Customer #") and newest["rate"] == "30"
        assert newest["how"] == "30% of $29.00 list"          # engine line: basis is the list price
        t = dash.ledger_totals(lines)["usd"]
        assert t["estimated"] == Decimal("8.70")
        assert t["pending"] == Decimal("99.75") + Decimal("8.70") + Decimal("49.50")
        assert t["paid"] == Decimal("119.70") + Decimal("8.70")       # 8.70 - 8.70 refunded
        assert t["total"] == t["estimated"] + t["pending"] + t["paid"]
        assert len(dash.filter_ledger(lines, kind="refund")) == 1
        assert len(dash.filter_ledger(lines, state="paid")) == 4
        assert len(dash.filter_ledger(lines, days=30)) == 2
        lapsed = dash.filter_ledger(lines, state="lapsed")[0]
        assert lapsed["amount"] == 0
        assert lapsed["reason"].startswith("Renewals were off: no new paying customer")
        months = dash.ledger_by_month(lines)
        assert sum(g["count"] for g in months) == len(lines)
        assert months[0]["label"] == lines[0]["when"].strftime("%B %Y")
        assert sum(amt for g in months for _c, amt in g["totals"]) == t["total"]
        # no tax form on file: pending money shows as Held with the reason
        live.tax_form_received_at = None
        held = dash.ledger(s, live, est["lines"])
        assert {ln["reason"] for ln in held if ln["state_key"] == "held"} == \
            {"Held until we have your tax form."}
        s.rollback()
        s.close()

    def test_csv_export_and_filters(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        r = portal.client.get(BASE + "/earnings.csv")
        assert r.status_code == 200 and r.mimetype == "text/csv"
        body = r.get_data(as_text=True)
        assert not PRIVATE.search(body)
        rows = list(csv.reader(io.StringIO(body)))
        assert rows[0] == ["Date", "Customer", "Plan", "Type", "Commission year", "Customer paid",
                           "How it's worked out", "Amount", "Currency", "State", "Reason"]
        hows = {r[6] for r in rows[1:]}
        assert {"30% of $29.00 list", "50% of $99.00 paid", "25% of $399.00 paid",
                "Reverses 30% of $29.00 list"} <= hows
        assert len(rows) == 10
        assert sum(Decimal(r[7]) for r in rows[1:]) == Decimal("295.05")
        paid = list(csv.reader(io.StringIO(
            portal.client.get(BASE + "/earnings.csv?state=paid").get_data(as_text=True))))
        assert len(paid) == 5 and all(r[9] == "Paid" for r in paid[1:])
        _r, html = get(portal, "/earnings?type=renewal")
        assert "1 line" in html and "Clear filters" not in html
        _r, html = get(portal, "/earnings?state=held")
        assert "No lines match these filters" in html


# ---------------------------------------------------------------------------
# links, QR, promote, payouts
# ---------------------------------------------------------------------------
class TestLinksAndPromote:
    def test_links_page_and_builder(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        _r, html = get(portal, "/links")
        assert "/join/ANNE" in html and "/?code=ANNE" in html
        assert "Customers can also type ANNE at checkout" in html
        assert "Link builder" in html and "utm_source" in html and "Campaign label" in html
        assert "coming soon" not in html.lower()

    def test_qr_only_for_own_tracked_links(self, portal):
        import affiliate_agreement as agr
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        ok = agr.join_link(aff) + "?utm_source=youtube&label=march"
        r = portal.client.get(BASE + "/qr.svg", query_string={"u": ok})
        assert r.status_code == 200 and r.mimetype == "image/svg+xml"
        assert r.get_data(as_text=True).startswith("<svg")
        r = portal.client.get(BASE + "/qr.svg", query_string={"u": ok, "download": "1"})
        assert "attachment" in r.headers["Content-Disposition"]
        for bad in ("https://evil.example/join/ANNE", agr._base() + "/join/OTHER",
                    agr._base() + "/pricing", "", agr._base() + "/join/ANNE?" + "x" * 400):
            assert portal.client.get(BASE + "/qr.svg", query_string={"u": bad}).status_code == 400

    def test_qr_encoder(self):
        from affiliate_portal import qr
        m = qr.matrix("https://tradewave.ai/join/ANNE")
        n = len(m)
        assert n == 29 and all(len(row) == n for row in m)            # version 3
        # finder patterns in three corners, never the fourth
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
            assert all(m[r0][c0 + i] and m[r0 + 6][c0 + i] and m[r0 + i][c0] and m[r0 + i][c0 + 6]
                       for i in range(7))
            assert m[r0 + 3][c0 + 3] and not m[r0 + 1][c0 + 1]
        assert m[n - 8][8]                                             # the fixed dark module
        assert [m[6][i] for i in range(8, n - 8)] == [i % 2 == 0 for i in range(8, n - 8)]
        # known-good vector: "hello" at version 1-M (data + Reed-Solomon codewords)
        assert qr._codewords(b"hello", 1) == [64, 86, 134, 86, 198, 198, 240, 236, 17, 236, 17, 236,
                                              17, 236, 17, 236, 22, 79, 223, 212, 140, 17, 209, 92,
                                              47, 183]
        assert len(qr.matrix("x" * 331)) == 17 + 4 * 13
        with pytest.raises(ValueError):
            qr.matrix("x" * 332)
        assert qr.svg("abc").count("<path") == 1

    def test_swipe_copy_follows_the_better_offer(self):
        from affiliate_portal import dashboard as dash
        aff = SimpleNamespace(code="ANNE")
        links, offer = {"join": "https://t.example/join/ANNE"}, {"discount_year": "20"}
        plan = {"plan": "Analyst annual", "interval": "year", "sale_cents": 9900, "list_cents": 39900,
                "term": "first year", "sale_wins": True}
        card = {"name": "Black Friday", "ends": "30 Nov", "plans": [plan]}
        # no sale, or a sale the partner's own discount beats: the partner's discount copy
        for promos in (None, [], [dict(card, plans=[dict(plan, sale_wins=False)])]):
            assert dash.sale_for_copy(promos) is None
            copy = dash.swipe_copy(aff, links, offer, promos)
            assert all("sale" not in c for c in copy)
            assert "20% off your first year with my code ANNE" in copy[0]["text"]
        # the sale wins: every channel quotes the sale price and its end date
        copy = dash.swipe_copy(aff, links, offer, [card])
        assert [c["key"] for c in copy] == ["social", "email", "video", "bio"]
        for c in copy:
            assert c["sale"] == "Black Friday version - ends 30 Nov"
            assert "$99" in c["text"] and "30 Nov" in c["text"] and c["text"].endswith(dash.DISCLOSURE)
            assert "\u2014" not in c["text"]
        assert "Black Friday Analyst annual for $99 first year (normally $399)" in copy[0]["text"]
        assert "On the other plans my code ANNE gets you 20% off your first year." in copy[1]["text"]
        # a partner at 0% has no code to mention
        zero = dash.swipe_copy(aff, links, {"discount_year": "0"}, [card])
        assert "my code" not in zero[0]["text"] and "$99" in zero[0]["text"]

    def test_promote_page(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        _r, html = get(portal, "/promote")
        from affiliate_portal import dashboard as dash
        assert html.count(dash.DISCLOSURE) >= 4               # every swipe ends with it
        # seed_rich has a live Black Friday sale that beats ANNE's 20%: the copy is the sale version
        assert "Black Friday Analyst annual for $99 first year (normally $399)" in html
        assert "Black Friday version - ends" in html and "quotes the" in html
        assert "my code ANNE gets you 20% off" in html           # other plans still use the code
        assert "Copy for my AI" in html and "Your join page" in html and 'id="guide"' in html
        assert 'name="page_note"' in html and "Preview" in html
        # the AI text carries v2 terms, not the v1 commission model
        assert "Your pool: 50% of the list price" in html
        assert "you earn 30% of the list price" in html
        assert "Renewals: 25% of what the customer pays, in years 2-5" in html
        assert "with a 30-day grace" in html
        assert "Commission model" not in html

    def test_join_page_editor_does_not_touch_the_expert_profile(self, portal):
        import models
        aff, user = h.seed_empty(portal.db, code="SMNX")
        portal.db.add(models.AffiliateSmnProfile(affiliate_id=aff.id, status="active", slug="smnx",
                                                 bio_md="Keep me"))
        portal.db.commit()
        login(portal, user)
        r = portal.client.post(BASE + "/profile", data={
            "next": "promote", "page_display_name": "Sam", "page_note": "Hello there", "page_signoff": ""})
        assert r.status_code == 302 and r.headers["Location"].endswith("/promote#join-page")
        s = portal.factory()
        assert s.get(models.Affiliate, aff.id).page_note == "Hello there"
        assert s.get(models.AffiliateSmnProfile, aff.id).bio_md == "Keep me"
        s.close()

    def test_payout_checklist(self, portal):
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        _r, html = get(portal, "/payouts")
        assert "Payout checklist" in html and "Ready to be paid" in html
        assert "$108.45" in html and "Next statement on" in html and "PP-7H2K91" in html
        chk = dash.payout_checklist(aff, {"usd": Decimal("20.00")})
        assert [i["ok"] for i in chk["items"]] == [True, True, False]
        assert chk["progress_pct"] == 40 and not chk["ready"]
        assert "$30.00 to go" in chk["items"][2]["help"]
        assert dash.next_payout_date(dt.datetime(2026, 11, 24, tzinfo=UTC)) == dt.date(2026, 12, 2)
        assert dash.next_payout_date(dt.datetime(2026, 12, 1, tzinfo=UTC)) == dt.date(2026, 12, 2)


# ---------------------------------------------------------------------------
# UX review fixes: sale vs offer table, held copy, disabled links, buckets,
# statements, first five minutes
# ---------------------------------------------------------------------------
class TestUxReview:
    def test_offer_table_and_promo_card_agree_during_a_sale(self, portal):
        import models
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        s = portal.factory()
        live = s.get(models.Affiliate, aff.id)
        terms = afs.terms_for(s, live)
        promos = dash.promotions(s, live, h.CATALOG, terms)
        assert promos[0]["compare"] == [
            "During Black Friday, Analyst annual through your link pays you $49.50 instead of "
            "$119.70 - your customer saves $220.20 more."]
        assert promos[0]["other_plans"] is True
        rows = {r["key"]: r for r in dash.plan_table(h.CATALOG, live, terms, promos)}
        sale = rows["analyst:year"]
        assert sale["sale"] and sale["sale_customer_cents"] == 9900 and sale["sale_first_cents"] == 4950
        assert (sale["customer_cents"], sale["first_cents"]) == (31920, 11970)    # after the sale
        assert not rows["navigator:year"]["sale"] and not rows["analyst:month"]["sale"]
        assert not any(r["sale"] for r in dash.plan_table(h.CATALOG, live, terms))
        s.close()
        for path in ("/", "/settings"):
            html = get(portal, path)[1]
            assert '<span class="pill warn">Sale</span>' in html, path
            assert "$49.50" in html
        home = get(portal, "/")[1]
        assert ("During Black Friday, Analyst annual through your link pays you $49.50 instead of "
                "$119.70 - your customer saves $220.20 more. Other plans are unchanged.") in home
        assert "After that Analyst annual goes back to $319.20 and you earn $119.70." in home
        settings = get(portal, "/settings")[1]
        assert 'data-sale-pay="9900" data-sale-earn="4950"' in settings

    def test_held_reasons_are_plain_and_never_blank(self):
        from affiliate_portal import dashboard as dash
        r = dash.HOLD_REASONS
        assert r["paused"] == "Held while your account is paused - paid when it's reactivated."
        assert r["unsigned"] == "Held until you sign your agreement."
        review = "Held for review - we'll email you. Questions: help@tradewave.ai"
        assert r["review"] == review and r["terminated"] == review

        def view(hold, signed=True, state="held"):
            d = {"kind": "first_year", "state": state, "hold_reason": hold, "amount": "8.70",
                 "rate_pct": "30", "basis_cents": 2900, "net_paid_cents": 2320,
                 "event_at": "2026-11-02T00:00:00+00:00"}
            return dash._line_view(d, {}, {}, {}, True, (), signed)
        assert view("paused")["reason"] == r["paused"]
        assert view("terminated")["reason"] == review
        assert view(None)["reason"] == review                    # unknown hold: still explained
        assert view("something_new")["reason"] == review
        assert view(None, signed=False)["reason"] == r["unsigned"]
        assert view(None, state="pending")["reason"] is None

    def test_lapsed_line_says_since_when(self):
        from affiliate_portal import dashboard as dash
        when = dt.datetime(2026, 10, 24, tzinfo=UTC)
        old = dt.datetime(2025, 3, 1, tzinfo=UTC)
        assert dash._lapsed_reason(when, [old, dt.datetime(2024, 1, 1, tzinfo=UTC)]) == \
            "Renewals were off: no new paying customer since 1 Mar 2025"
        # a customer inside the window cannot explain a lapse: no misleading date
        recent = dt.datetime(2026, 10, 5, tzinfo=UTC)
        assert "since" not in dash._lapsed_reason(when, [old, recent])
        assert dash._lapsed_reason(when, []).startswith("Renewals were off: no new paying customer")

    def test_how_its_worked_out(self):
        from affiliate_portal import dashboard as dash
        assert dash._how("first_year", "30", 2900, 2320, "usd") == "30% of $29.00 list"
        assert dash._how("first_year", "30", 0, 2320, "usd", list_cents=2900) == "30% of $29.00 list"
        assert dash._how("promo", "50", 9900, 9900, "usd") == "50% of $99.00 paid"
        assert dash._how("renewal", "25.00", 39900, 39900, "usd") == "25% of $399.00 paid"
        assert dash._how("refund", "30", -2900, -2320, "usd", reverses="first_year") == \
            "Reverses 30% of $29.00 list"
        assert dash._how("refund", "30", -2900, -2320, "usd") == "Reverses 30% of $29.00 list"
        assert dash._how("dispute", "25", -39900, -39900, "usd", reverses="renewal") == \
            "Reverses 25% of $399.00 paid"
        assert dash._how("refund", "30", -1450, -1160, "usd", reverses="first_year") == \
            "Reverses 30% of $14.50 list"                       # partial refund

    def test_copy_is_disabled_for_unsigned_and_paused_partners(self, portal):
        unsigned = "Works after you sign your agreement"
        paused = "Paused - links don&#39;t credit you right now"
        aff, user = h.seed_empty(portal.db, code="UNSIGNED", agreement_signed_at=None)
        login(portal, user)
        for path in ("/", "/links", "/promote"):
            html = get(portal, path)[1]
            assert unsigned in html, path
            assert "twCopy(this, 'http" not in html, path           # no live Copy on a link
            assert "twCopy(this, 'UNSIGNED')" not in html, path
            assert 'class="stickycopy"' not in html, path
        links = get(portal, "/links")[1]
        assert links.count('disabled aria-disabled="true" title="%s"' % unsigned) >= 4
        assert "Awaiting signature" in get(portal, "/")[1]
        aff2, user2 = h.seed_rich(portal.db, portal.world, code="PAUL", status="paused")
        login(portal, user2)
        for path in ("/", "/links", "/promote"):
            html = get(portal, path)[1]
            assert paused in html, path
            assert "twCopy(this, 'http" not in html and "twCopy(this, 'PAUL')" not in html, path
        # swipe copy carries the link too
        assert "getElementById('sw-social')" not in get(portal, "/promote")[1]
        aff3, user3 = h.seed_rich(portal.db, portal.world, code="ANNE")
        login(portal, user3)
        html = get(portal, "/links")[1]
        assert "disabled" not in html.split("<body>")[1].split("<script>")[0]
        assert "twCopy(this, 'ANNE')" in html and "don&#39;t credit you" not in html
        assert "getElementById('sw-social')" in get(portal, "/promote")[1]

    def test_link_block_reasons(self):
        from affiliate_portal import dashboard as dash
        signed = dt.datetime(2026, 1, 5, tzinfo=UTC)
        mk = lambda **k: SimpleNamespace(**k)        # noqa: E731
        assert dash.link_block(mk(agreement_signed_at=signed, status="active")) is None
        assert dash.link_block(mk(agreement_signed_at=None, status="active")) == \
            "Works after you sign your agreement"
        assert dash.link_block(mk(agreement_signed_at=None, status="paused")) == \
            "Works after you sign your agreement"
        assert dash.link_block(mk(agreement_signed_at=signed, status="paused")) == \
            "Paused - links don't credit you right now"

    def test_held_tile_only_when_money_is_held(self, portal):
        aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        home = get(portal, "/")[1]
        assert '<div class="k">Held</div>' not in home and 'class="grid4"' in home
        s = portal.factory()
        live = s.get(type(aff), aff.id)
        live.tax_form_received_at = None            # pending lines are now held for the tax form
        s.commit()
        s.close()
        home = get(portal, "/")[1]
        assert '<div class="k">Held</div>' in home and 'class="grid5"' in home
        assert "$157.95" in home                    # 99.75 + 8.70 + 49.50
        assert "Earned, not payable yet." in home and "waiting on something" not in home
        assert "state=held" in home

    def test_payout_rows_are_statements_with_the_months_they_include(self, portal):
        import models
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_rich(portal.db, portal.world, now=dt.datetime(2026, 11, 24, 12, tzinfo=UTC))
        login(portal, user)
        s = portal.factory()
        pend = s.query(models.AffiliatePayout).filter_by(affiliate_id=aff.id, status="pending").one()
        sep = dt.date(2026, 9, 1)
        pend.detail = {"carry_in": [{"period": sep.isoformat(), "amount": "23.40"}]}
        s.add(models.AffiliatePayout(affiliate_id=aff.id, period_start=sep, period_end=sep,
                                     currency="usd", gross_revenue=h.D("62.40"),
                                     commission_amount=h.D("23.40"), status="void",
                                     external_ref=afs.carry_ref(pend.period_start)))
        s.commit()
        rows = dash.payout_history(s, s.get(models.Affiliate, aff.id),
                                   now=dt.datetime(2026, 11, 3, tzinfo=UTC))
        s.close()
        by = {r["statement"]: r for r in rows}
        octo = by["Statement for Oct 2026"]
        assert octo["includes"] == "includes Sep and Oct 2026 lines"
        assert octo["expected"] == "15 Nov 2026"            # 15th of the month after the statement
        assert by["Statement for Sep 2026"]["carried_to"] == "Oct 2026"
        assert by["Statement for Sep 2026"]["expected"] is None
        html = get(portal, "/payouts")[1]
        assert "Statement for Oct 2026" in html and "includes Sep and Oct 2026 lines" in html
        assert "Moved into the Oct 2026 statement" in html
        assert "Sent by the 15th of the month after the statement" in html
        assert dash._month_span([dt.date(2026, 9, 1), dt.date(2026, 10, 1), dt.date(2026, 11, 1)]) == \
            "Sep to Nov 2026"
        assert dash._month_span([dt.date(2026, 7, 1), dt.date(2026, 9, 1), dt.date(2026, 10, 1)]) == \
            "Jul, Sep and Oct 2026"
        assert dash._month_span([dt.date(2025, 12, 1), dt.date(2026, 1, 1)]) == "Dec 2025 and Jan 2026"

    def test_tax_form_copy_never_invites_emailing_it(self, portal):
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_empty(portal.db)
        login(portal, user)
        pay = get(portal, "/payouts")[1]
        assert ("Don&#39;t email your tax form. Reply to your welcome email or contact "
                "help@tradewave.ai and we&#39;ll send you a secure upload link.") in pay
        assert "Don&#39;t email bank or card details" in pay
        pages = pay + get(portal, "/")[1] + portal.client.get(BASE + "/guide.md").get_data(as_text=True)
        for bad in ("Email a W-9", "Email it to help@", "send a W-9", "Tell us your PayPal"):
            assert bad not in pages
        assert "Email a W-9" not in dash.payout_checklist(aff, {})["items"][0]["help"]

    def test_first_five_minutes(self, portal):
        from affiliate_portal import dashboard as dash
        aff, user = h.seed_empty(portal.db, name="Nadia Okafor")
        login(portal, user)
        home = get(portal, "/")[1]
        assert "Welcome, Nadia" in home and "Welcome back" not in home
        assert "How you get paid" in home
        for step in ("Share your link.",
                     "When someone pays, you earn $99.60 to $319.60 (first year, depending on plan).",
                     "We pay you monthly by PayPal or Wise once you&#39;re over $50."):
            assert step in home
        # logged in on a later day than they joined: a returning partner
        user.last_login_at = aff.agreement_signed_at + dt.timedelta(days=3)
        assert "Welcome back, Nadia" in get(portal, "/")[1]
        assert dash.welcome_back(aff, SimpleNamespace(last_login_at=None), False) is False
        assert dash.welcome_back(aff, SimpleNamespace(last_login_at=None), True) is True
        assert dash.getting_started([], {"rate_year": "40"}, False)[1] == \
            "When someone pays, you earn 40% of the list price (first year)."
        assert dash.getting_started([], {"rate_year": "40"}, True) is None

    def test_guide_points_to_promote(self):
        guide = (h._REPO_ROOT / "docs" / "AFFILIATE_PARTNER_GUIDE.md").read_text(encoding="utf-8")
        assert 'The **Promote** page there has a "Copy for my AI"' in guide
        assert "**Guide** page" not in guide and "Email it to help@" not in guide
        assert EM_DASH not in guide


# ---------------------------------------------------------------------------
# the narrated partner tour (video on Home, static files on the blueprint)
# ---------------------------------------------------------------------------
class TestPartnerTour:
    def test_new_partner_sees_the_tour_card_in_get_started(self, portal):
        _aff, user = h.seed_empty(portal.db)
        login(portal, user)
        _r, home = get(portal, "/")
        assert home.count('id="tour"') == 1
        assert '<div class="card tone-brand" id="tour">' in home
        assert "Watch the 2-minute tour" in home
        # right under "How you get paid", above the money tiles
        assert home.index("How you get paid") < home.index('id="tour"') < home.index("Estimated this month")
        assert '<video class="tourvid" controls preload="none"' in home
        assert 'poster="/account/affiliate/static/partner-tour.jpg"' in home
        assert '<source src="/account/affiliate/static/partner-tour.mp4" type="video/mp4">' in home
        assert 'kind="captions"' in home and 'src="/account/affiliate/static/partner-tour.vtt"' in home
        assert EM_DASH not in home

    def test_everyone_else_gets_a_folded_card_and_a_help_link(self, portal):
        _aff, user = h.seed_rich(portal.db, portal.world)
        login(portal, user)
        _r, home = get(portal, "/")
        assert home.count('id="tour"') == 1
        assert '<details class="card more tourfold" id="tour">' in home
        assert "Watch the 2-minute tour" not in home and "partner-tour.mp4" in home
        for path in ("/", "/earnings", "/payouts"):       # the Help panel is on every page
            assert 'href="/account/affiliate/#tour">Partner tour (2-minute video)</a>' in get(portal, path)[1]

    def test_static_files_are_served(self, portal):
        static = h._REPO_ROOT / "web" / "affiliate_portal" / "static"
        for name, ctype in (("partner-tour.mp4", "video/mp4"), ("partner-tour.jpg", "image/jpeg"),
                            ("partner-tour.vtt", "text/vtt")):
            r = portal.client.get(BASE + "/static/" + name)       # logged out: a plain static asset
            assert r.status_code == 200, name
            assert r.headers["Content-Type"].startswith(ctype), (name, r.headers["Content-Type"])
            assert len(r.data) == (static / name).stat().st_size > 1000
            r.close()
        # seeking needs byte ranges
        r = portal.client.get(BASE + "/static/partner-tour.mp4", headers={"Range": "bytes=0-99"})
        assert r.status_code == 206 and len(r.data) == 100
        r.close()
        assert (static / "partner-tour.mp4").stat().st_size < 8 * 1024 * 1024
        vtt = (static / "partner-tour.vtt").read_text(encoding="utf-8")
        assert vtt.startswith("WEBVTT") and "Welcome to the TradeWave partner program." in vtt
        assert EM_DASH not in vtt


# ---------------------------------------------------------------------------
# /join/<code>: real dollar prices
# ---------------------------------------------------------------------------
class TestJoinPage:
    def _render(self, portal, offers, **kw):
        from flask import render_template
        portal.app.template_folder = str(h._REPO_ROOT / "web" / "templates")
        ctx = dict(code="ANNE", display_name="Anne Lee", logo_url=None, photo_url=None,
                   page_note=None, page_signoff=None, two_tier=False, monthly_discount="20",
                   annual_discount="20", discount="20", cta_url="/pricing?code=ANNE", offers=offers)
        ctx.update(kw)
        with portal.app.test_request_context("/join/ANNE"):
            return render_template("affiliate_landing.html", **ctx)

    def test_shows_dollar_prices_and_the_campaign_price(self, portal):
        import affiliate_service as afs
        aff, user = h.seed_rich(portal.db, portal.world)
        s = portal.factory()
        live = s.get(type(aff), aff.id)
        html = self._render(portal, afs.display_offers(s, live, h.CATALOG))
        assert "$99<small>first year</small>" in html              # Black Friday beats 20% off
        assert "<b>Black Friday price, through Anne.</b> Sale ends" in html
        assert "got you an exclusive discount" not in html          # the sale won, not Anne's discount
        assert "Start with a 7-day free trial - your sale price is locked in." in html
        assert "$639.20<small>first year</small>" in html          # partner discount elsewhere
        assert "<s>$799</s>" in html and "You save $159.80" in html
        assert "$23.20/mo</b> for 12 months, then $29" in html
        assert EM_DASH not in html
        plain = self._render(portal, afs.display_offers(s, live, h.CATALOG, is_new_customer=False))
        assert "$319.20<small>first year</small>" in plain and "Sale ends" not in plain
        assert "got you an exclusive discount" in plain
        assert "Start with a 7-day free trial - your price is locked in." in plain
        s.close()

    def test_each_plan_has_its_own_subscribe_button(self, portal):
        import affiliate_service as afs
        aff, user = h.seed_rich(portal.db, portal.world)
        s = portal.factory()
        html = self._render(portal, afs.display_offers(s, s.get(type(aff), aff.id), h.CATALOG))
        s.close()
        hrefs = re.findall(r'<a class="buy[^"]*" href="([^"]+)" data-plan="([^"]+)"', html)
        assert len(hrefs) == 6
        # same route and params as the pricing page CTAs (web/app.py stripe_create_checkout)
        want = {("%s:%s" % (t, iv)): "/api/stripe/create-checkout?code=ANNE&amp;tier=%s&amp;period=%s"
                % (t, per) for t in ("navigator", "analyst", "strategist")
                for iv, per in (("year", "yearly"), ("month", "monthly"))}
        assert {plan: href for href, plan in hrefs} == want
        assert "Subscribe - $99 first year" in html and "Subscribe monthly - $23.20/mo" in html
        assert "Black Friday price, through Anne</div>" in html     # on the sale card
        assert "Anne's discount</div>" in html                       # on the other cards

    def test_sale_end_has_a_time_and_a_zone(self, portal):
        import affiliate_service as afs
        from affiliate_portal import dashboard as dash
        # stored in UTC, shown in US Eastern (EST in November, EDT in July)
        assert dash.fmt_sale_end("2026-12-01T04:59:00+00:00") == "30 Nov, 11:59 pm ET"
        assert dash.fmt_sale_end(dt.datetime(2026, 7, 5, 3, 59, tzinfo=UTC)) == "4 Jul, 11:59 pm ET"
        assert dash.fmt_sale_end("2026-11-30T17:00:00Z") == "30 Nov, 12:00 pm ET"
        assert dash.fmt_sale_end(None) == "" and dash.fmt_sale_end("junk") == ""
        aff, user = h.seed_rich(portal.db, portal.world)
        s = portal.factory()
        camp = s.query(__import__("models").PromoCampaign).one()
        camp.ends_at = dt.datetime(2026, 12, 1, 4, 59, tzinfo=UTC)
        s.commit()
        html = self._render(portal, afs.display_offers(s, s.get(type(aff), aff.id), h.CATALOG))
        assert "Sale ends 30 Nov, 11:59 pm ET." in html
        # the dashboard card names the same day and time
        login(portal, user)
        home = get(portal, "/")[1]
        assert "Ends 30 Nov, 11:59 pm ET." in home and "Ends 1 Dec" not in home
        s.close()

    def test_falls_back_to_percent_when_prices_are_unavailable(self, portal):
        html = self._render(portal, {})
        assert "20% OFF" in html and "Claim your discount" in html
        assert 'class="buy' not in html
        two = self._render(portal, {}, two_tier=True, monthly_discount="10")
        assert "10% <span" in two


# ---------------------------------------------------------------------------
# MCP / gateway view (apiserver/affiliate_view.py)
# ---------------------------------------------------------------------------
UID = str(uuid.uuid4())
AFF_ID = uuid.uuid4()


class TestMcpView:
    @pytest.fixture
    def view(self, monkeypatch):
        from apiserver import affiliate_view, db, tiers
        calls = {"ids": [], "orig": (db.affiliate_program_v2, db.active_promotions)}
        row = {"id": AFF_ID, "code": "ANNE", "name": "Anne Lee", "status": "active",
               "commission_model": "recurring", "discount_pct": Decimal("20.00"),
               "commission_pct": Decimal("30.00"), "discount_pct_monthly": None,
               "commission_pct_monthly": None, "payout_method": "paypal",
               "payout_email": "pay@example.com", "tax_form_type": "w9",
               "tax_form_received_at": dt.datetime(2026, 1, 1, tzinfo=UTC)}
        calls["row"] = row
        calls["v2"] = {"terms_version": "v2-5y", "pool_pct": Decimal("50"),
                       "max_discount_pct": Decimal("25"), "promo_commission_pct": Decimal("50"),
                       "renewal_pct": Decimal("25"), "renewal_years": 5, "activity_rule_months": 12,
                       "discount_changed_at": dt.datetime(2026, 11, 16, 6, tzinfo=UTC),
                       "last_new_customer_at": dt.datetime(2026, 3, 10, tzinfo=UTC)}
        calls["promotions"] = [{
            "code": "BLACK-FRIDAY", "name": "Black Friday", "tiers": ["analyst"],
            "billing_intervals": ["year", "month"], "offer_type": "price",
            "intro_prices": {"analyst:year": 9900}, "percent_off": None, "intro_months": 12,
            "stripe_coupon_ids": {"analyst:year": "cpn_bf"},
            "starts_at": dt.datetime(2026, 11, 20, tzinfo=UTC),
            "ends_at": dt.datetime(2026, 11, 30, tzinfo=UTC)}]
        calls["offers"] = {"code": "ANNE", "offers": {
            "analyst:year": {"tier": "analyst", "interval": "year", "list_price_cents": 39900,
                             "price_cents": 9900, "offer": "campaign",
                             "campaign": {"code": "BLACK-FRIDAY", "name": "Black Friday"}},
            "analyst:month": {"tier": "analyst", "interval": "month", "list_price_cents": 4900,
                              "price_cents": 3920, "offer": "partner", "campaign": None},
            "navigator:year": {"tier": "navigator", "interval": "year", "list_price_cents": 10000,
                               "price_cents": 8000, "offer": "partner", "campaign": None}}}

        def get_aff(user_id, email=None):
            calls["user"] = (user_id, email)
            return calls["row"]
        monkeypatch.setattr(db, "get_affiliate_for_user", get_aff)
        monkeypatch.setattr(db, "affiliate_funnel", lambda a, days=30: calls["ids"].append(a) or {
            "days": days, "clicks_recent": 1, "clicks_total": 2, "signups_recent": 0,
            "signups_total": 1, "in_trial": 0, "paying_total": 1})
        monkeypatch.setattr(db, "affiliate_payout_rows", lambda a: calls["ids"].append(a) or [])
        monkeypatch.setattr(db, "affiliate_program_v2", lambda a: calls["ids"].append(a) or calls["v2"])
        monkeypatch.setattr(db, "active_promotions", lambda: calls["promotions"])
        monkeypatch.setattr(affiliate_view, "_fetch_offers",
                            lambda base, code: calls.__setitem__("fetched", (base, code)) or calls["offers"])
        e = dict(tiers.tier_for("dev"))
        cust = {"user_id": UID, "email": "anne@example.com", "tier": "analyst", "entitlements": e}
        return SimpleNamespace(mod=affiliate_view, calls=calls, cust=cust,
                               build=lambda **kw: affiliate_view.build(
                                   cust, "tw.example", today=kw.get("today", dt.date(2026, 11, 16))))

    def test_v2_sections(self, view):
        payload, status = view.build()
        assert status == 200
        prog = payload["program"]
        assert (prog["terms_version"], prog["pool_pct"], prog["max_discount_pct"],
                prog["promo_commission_pct"], prog["renewal_pct"]) == ("v2-5y", 50, 25, 50, 25)
        assert any("$100 plan at 20% off - they pay $80, you earn $30" in r for r in prog["rules"])
        assert any("with a 30-day grace" in r for r in prog["rules"])
        offer = payload["offer"]
        assert offer["discount_pct"] == {"annual_plans": 20, "monthly_plans": 20}
        assert offer["first_year_commission_pct"] == {"annual_plans": 30, "monthly_plans": 30}
        assert offer["checkout_code_active"] is True and offer["discount_range_pct"] == [0, 25]
        assert offer["next_discount_change_at"] == "2026-11-17T06:00:00+00:00"   # 24h cooldown
        plans = {p["plan"]: p for p in offer["per_plan"]}
        # acceptance table: $100 list at 20% off -> pays $80, partner $30, renewal 25% of list
        assert plans["Navigator annual"] == {
            "plan": "Navigator annual", "tier": "navigator", "interval": "year", "list_price": 100.0,
            "customer_pays": 80.0, "you_earn_first_year_payment": 30.0, "you_earn_per_renewal": 25.0,
            "price_from": "your discount", "promotion": None}
        bf = plans["Analyst annual"]                                  # referred $99 promo -> $49.50
        assert (bf["customer_pays"], bf["you_earn_first_year_payment"], bf["you_earn_per_renewal"],
                bf["price_from"], bf["promotion"]) == (99.0, 49.5, 99.75, "promotion", "Black Friday")
        assert plans["Analyst monthly"]["you_earn_first_year_payment"] == 14.7
        ren = payload["renewals"]
        assert (ren["first_year"], ren["last_year"], ren["annual_renewals_paid"],
                ren["monthly_first_month"], ren["monthly_last_month"], ren["lifetime"]) == \
            (2, 5, 4, 13, 60, False)
        act = payload["activity"]
        assert act["active"] is True and act["grace_days"] == 30
        assert act["active_until"] == "2027-04-09"            # 10 Mar 2026 + 12 months + 30 days
        assert act["days_left"] == (dt.date(2027, 4, 9) - dt.date(2026, 11, 16)).days
        promo = payload["active_promotions"]
        assert len(promo) == 1 and promo[0]["name"] == "Black Friday"
        assert promo[0]["plans"] == [{"plan": "Analyst annual", "tier": "analyst", "interval": "year",
                                      "intro_price": 99.0, "you_earn_if_sale_wins": 49.5,
                                      "intro_lasts": "first year"}]     # month has no coupon: left out
        assert "whichever price is lower" in promo[0]["rule"]
        assert EM_DASH not in json.dumps(payload)

    def test_read_only_caller_scoped_and_no_identities(self, view):
        payload, _ = view.build()
        assert view.calls["user"] == (UID, "anne@example.com")
        assert set(view.calls["ids"]) == {AFF_ID}              # every query is for the caller's row
        assert view.calls["fetched"] == ("https://tw.example", "ANNE")
        blob = json.dumps(payload)
        assert "pay@example.com" not in blob and "cus_" not in blob and "cpn_bf" not in blob
        import inspect
        from apiserver import db
        assert db is not None
        for fn in view.calls["orig"]:
            src = inspect.getsource(fn).upper()
            assert "SELECT" in src
            assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", src) and "COMMIT=TRUE" not in src

    def test_lapsed_lifetime_zero_discount_and_missing_pieces(self, view):
        view.calls["v2"] = dict(view.calls["v2"], renewal_years=None, terms_version="v2-lifetime",
                                last_new_customer_at=dt.datetime(2025, 1, 1, tzinfo=UTC),
                                discount_changed_at=None)
        view.calls["row"] = dict(view.calls["row"], discount_pct=Decimal("0"))
        view.calls["offers"] = None
        payload, status = view.build()
        assert status == 200
        assert payload["renewals"]["lifetime"] is True and payload["renewals"]["last_year"] is None
        act = payload["activity"]
        assert act["active"] is False and act["lapsed_since"] == "2026-01-31"
        assert act["text"].startswith("Renewal commissions are stopped.")
        offer = payload["offer"]
        assert offer["per_plan"] is None and offer["checkout_code_active"] is False
        assert offer["first_year_commission_pct"]["annual_plans"] == 50
        assert "no checkout code" in offer["checkout_code_note"]
        assert offer["next_discount_change_at"] is None
        assert all("code ANNE" not in t["text"] for t in payload["promo"]["templates"])

    def test_v2_sections_survive_a_missing_table_or_slow_web_tier(self, view, monkeypatch):
        from apiserver import db

        def boom(*a, **k):
            raise RuntimeError("relation does not exist")
        monkeypatch.setattr(db, "affiliate_program_v2", boom)
        monkeypatch.setattr(db, "active_promotions", boom)
        monkeypatch.setattr(view.mod, "_fetch_offers", boom)
        payload, status = view.build()
        assert status == 200 and payload["code"] == "ANNE"
        assert payload["program"]["terms_version"] == "v2-5y"          # program defaults
        assert payload["active_promotions"] == [] and payload["offer"]["per_plan"] is None
        assert payload["activity"]["active"] is False                  # unknown -> nothing promised
