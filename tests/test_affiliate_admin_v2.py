"""Affiliate program v2 - ADMIN screens (TW-TASK-0038, Phase 2).

Hermetic like tests/test_affiliate_v2.py: Stripe is monkeypatched and the
ledger runs on the in-memory SQLite copy of the affiliate tables (the `db`
fixture is shared with that module).

Covered: discount validation (26% refused, 25% accepted), the dollar preview
(acceptance rows of docs/tasks/TW-TASK-0038.md), campaign form validation and
preview, the $50 payout minimum carry, mark-paid ledger sync, held lines,
terminate for cause, and a render pass over every new admin page.
"""
import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import MultiDict

import affiliate_admin as afa
import affiliate_service as afs
from tests.test_affiliate_v2 import (  # noqa: F401  (fixtures are used by name)
    D, app_module, campaign_stripe, day, db, invoice, ledger, make_partner,
    make_referral, payout_for, stripe_world, terms, ts,
)

CATALOG = {
    ("navigator", "month"): {"price_id": "p_nm", "product_id": "prod_nm", "list_price_cents": 2900},
    ("navigator", "year"): {"price_id": "p_ny", "product_id": "prod_ny", "list_price_cents": 19900},
    ("analyst", "month"): {"price_id": "p_am", "product_id": "prod_am", "list_price_cents": 4900},
    ("analyst", "year"): {"price_id": "p_ay", "product_id": "prod_ay", "list_price_cents": 39900},
    ("strategist", "month"): {"price_id": "p_sm", "product_id": "prod_sm", "list_price_cents": 9900},
    ("strategist", "year"): {"price_id": "p_sy", "product_id": "prod_sy", "list_price_cents": 79900},
}
HUNDRED = {("analyst", "year"): {"price_id": "p", "product_id": "prod", "list_price_cents": 10000}}


def row_for(rows, plan, interval):
    return next(r for r in rows if r["plan"] == plan and r["interval"] == interval)


def campaign_form(**kw):
    base = [("name", "Black Friday 2026"), ("tiers", "analyst"), ("intervals", "year"),
            ("tz", "America/New_York"), ("starts_local", "2026-11-27T00:00"),
            ("ends_local", "2026-12-01T00:00"), ("offer_type", "price"),
            ("price_analyst_year", "99"), ("intro_months", "12")]
    form = MultiDict(base)
    for k, v in kw.items():
        if v is None:
            form.pop(k, None)
        elif isinstance(v, (list, tuple)):
            form.setlist(k, list(v))
        else:
            form[k] = v
    return form


# ============================================================================
# 1. Discount validation
# ============================================================================

class TestDiscountValidation:
    def test_25_is_accepted_and_26_is_refused(self):
        assert afa.parse_discount("25") == D("25.00")
        assert afa.parse_discount("0") == D("0.00")
        with pytest.raises(afs.AffiliateError) as e:
            afa.parse_discount("26")
        assert "0% to 25%" in str(e.value) and "26%" in str(e.value)

    @pytest.mark.parametrize("bad", ["-1", "25.01", "abc", "", None, "NaN"])
    def test_out_of_range_or_not_a_number_is_refused(self, bad):
        with pytest.raises(afs.AffiliateError):
            afa.parse_discount(bad)

    def test_the_cap_comes_from_the_terms_version(self):
        tight = terms(max_discount_pct=D(10))
        assert afa.parse_discount("10", tight) == D("10.00")
        with pytest.raises(afs.AffiliateError) as e:
            afa.parse_discount("11", tight)
        assert "0% to 10%" in str(e.value)

    def test_admin_change_refuses_26_and_touches_nothing(self, db, monkeypatch):
        aff = make_partner(db, agreement_signed_at=day(2026, 1, 1))
        monkeypatch.setattr(afs, "reissue_coupon",
                            lambda *a, **k: pytest.fail("Stripe must not be called"))
        with pytest.raises(afs.AffiliateError):
            afa.apply_partner_discounts(db, aff, "26", "", "admin:test")
        with pytest.raises(afs.AffiliateError):
            afa.apply_partner_discounts(db, aff, "20", "26", "admin:test")
        db.refresh(aff)
        assert aff.discount_pct == D(20) and aff.status == "active"
        assert afs.discount_history(db, aff) == []

    def test_admin_change_to_25_uses_set_partner_discount_no_pause_no_resign(self, db, monkeypatch):
        signed = day(2026, 1, 1)
        aff = make_partner(db, agreement_signed_at=signed, agreement_signed_name="Anne")
        monkeypatch.setattr(afs, "reissue_coupon", lambda a, pct: ("cpn_new", "promo_new"))
        changes = afa.apply_partner_discounts(db, aff, "25", "", "admin:afshin@example.com")
        db.refresh(aff)
        assert [(c.billing_interval, c.old_pct, c.new_pct) for c in changes] == [("year", D(20), D(25))]
        assert aff.discount_pct == D(25) and aff.stripe_coupon_id == "cpn_new"
        assert aff.status == "active"                                   # no pause
        assert aff.agreement_signed_name == "Anne" and aff.agreement_signed_at is not None   # no re-sign
        assert changes[0].actor == "admin:afshin@example.com"
        # the 24h self-serve limit does not apply to the admin
        monkeypatch.setattr(afs, "reissue_coupon", lambda a, pct: ("cpn_new2", "promo_new2"))
        again = afa.apply_partner_discounts(db, aff, "10", "", "admin:afshin@example.com")
        assert again[0].new_pct == D(10)
        assert afa.apply_partner_discounts(db, aff, "10", "", "admin:x") == []     # no change

    def test_monthly_override_is_set_and_cleared(self, db, monkeypatch):
        aff = make_partner(db)
        monkeypatch.setattr(afs.stripe.Coupon, "create",
                            lambda **kw: SimpleNamespace(id="cpn_monthly"))
        changes = afa.apply_partner_discounts(db, aff, "20", "15", "admin:x")
        db.refresh(aff)
        assert [c.billing_interval for c in changes] == ["month"]
        assert aff.discount_pct_monthly == D(15) and aff.stripe_coupon_id_monthly == "cpn_monthly"
        afa.apply_partner_discounts(db, aff, "20", "", "admin:x")       # blank = same as annual
        db.refresh(aff)
        assert aff.discount_pct_monthly is None and aff.stripe_coupon_id_monthly is None


class TestAffiliateCreateForm:
    def _new(self, db, **kw):
        import models
        base = dict(id=uuid.uuid4(), code="newp", name="New Partner", email="new@example.com",
                    discount_pct=D(20), agreement_token_version=0)
        base.update(kw)
        model = models.Affiliate(**base)
        db.add(model)
        return model

    def _save(self, mod, db, model, monkeypatch, provisioned=None):
        calls = provisioned if provisioned is not None else []

        def provision(aff):
            calls.append(str(aff.discount_pct))
            return "cpn_x", "promo_x"
        monkeypatch.setattr(afs, "provision_stripe_objects", provision)
        monkeypatch.setattr(afs, "provision_interval_overrides",
                            lambda aff: calls.append("monthly"))
        monkeypatch.setattr(mod, "write_audit", lambda **kw: None)
        view = SimpleNamespace(session=db)
        mod.AffiliateAdmin.on_model_change(view, None, model, True)
        return calls

    def test_26_percent_is_refused_before_any_stripe_call(self, app_module, db, monkeypatch):
        from wtforms.validators import ValidationError
        model = self._new(db, discount_pct=D(26))
        calls = []
        with pytest.raises(ValidationError) as e:
            self._save(app_module, db, model, monkeypatch, calls)
        assert "0% to 25%" in str(e.value) and calls == []
        db.rollback()

    def test_monthly_26_is_refused(self, app_module, db, monkeypatch):
        from wtforms.validators import ValidationError
        model = self._new(db, discount_pct=D(20), discount_pct_monthly=D(26))
        with pytest.raises(ValidationError):
            self._save(app_module, db, model, monkeypatch)
        db.rollback()

    def test_25_percent_is_saved_paused_on_default_terms_with_pool_share(self, app_module, db, monkeypatch):
        model = self._new(db, discount_pct=D(25))
        calls = self._save(app_module, db, model, monkeypatch)
        db.commit()
        assert calls == ["25.00"]
        assert (model.code, model.status, model.stripe_coupon_id) == ("NEWP", "paused", "cpn_x")
        assert model.terms.version == "v2-5y"
        assert model.commission_pct == D(25)            # pool 50 - discount 25 (legacy column)

    def test_zero_discount_needs_no_coupon(self, app_module, db, monkeypatch):
        model = self._new(db, discount_pct=D(0))
        calls = self._save(app_module, db, model, monkeypatch)
        db.commit()
        assert calls == [] and model.stripe_coupon_id is None
        assert model.commission_pct == D(50)

    def test_edit_form_has_no_commission_or_discount_inputs(self, app_module):
        view = app_module.AffiliateAdmin
        for gone in ("commission_pct", "commission_pct_monthly", "commission_model"):
            assert gone not in view.form_columns
        assert "discount_pct" in view.form_columns and "terms" in view.form_columns
        edit = [r for r in view.form_edit_rules if isinstance(r, str)]
        assert "discount_pct" not in edit and "code" not in edit and "terms" not in edit


# ============================================================================
# 2. Dollar preview (acceptance table)
# ============================================================================

class TestOfferPreview:
    @pytest.mark.parametrize("discount,pays,earns,retains", [
        ("0", 10000, 5000, 5000),
        ("5", 9500, 4500, 5000),
        ("20", 8000, 3000, 5000),
        ("25", 7500, 2500, 5000),
    ])
    def test_100_dollar_plan(self, discount, pays, earns, retains):
        rows = afa.offer_preview(HUNDRED, discount)
        for r in (rows[0], row_for(rows, "Analyst", "Annual")):       # example row + the plan
            assert (r["customer_pays_cents"], r["partner_first_year_cents"],
                    r["retained_cents"]) == (pays, earns, retains)

    def test_100_at_20_reads_80_30_50(self):
        r = afa.offer_preview(HUNDRED, "20")[0]
        assert (r["list_price"], r["customer_pays"], r["partner_first_year"], r["retained"]) == (
            "$100.00", "$80.00", "$30.00", "$50.00")
        assert r["partner_renewal"] == "$25.00"                        # 25% of the $100 renewal

    def test_every_plan_and_interval_is_listed(self):
        rows = afa.offer_preview(CATALOG, "20", example=False)
        assert [(r["plan"], r["interval"]) for r in rows] == [
            ("Navigator", "Monthly"), ("Navigator", "Annual"), ("Analyst", "Monthly"),
            ("Analyst", "Annual"), ("Strategist", "Monthly"), ("Strategist", "Annual")]
        analyst = row_for(rows, "Analyst", "Annual")
        assert analyst["customer_pays"] == "$319.20"                   # $399 less 20%
        assert analyst["partner_first_year"] == "$119.70"              # 30% of $399
        assert analyst["partner_renewal"] == "$99.75"                  # 25% of the $399 renewal
        assert analyst["retained"] == "$199.50"                        # always 50% of list

    def test_monthly_override_changes_only_monthly_rows(self):
        rows = afa.offer_preview(CATALOG, "20", "10", example=False)
        assert row_for(rows, "Analyst", "Annual")["discount_pct"] == "20"
        monthly = row_for(rows, "Analyst", "Monthly")
        assert monthly["discount_pct"] == "10"
        assert (monthly["customer_pays"], monthly["partner_first_year"]) == ("$44.10", "$19.60")

    def test_26_percent_has_no_preview(self):
        with pytest.raises(afs.AffiliateError):
            afa.offer_preview(CATALOG, "26")
        with pytest.raises(afs.AffiliateError):
            afa.offer_preview(CATALOG, "20", "26")

    def test_lifetime_terms_keep_the_same_per_renewal_amount(self):
        lifetime = terms(id=3, version="v2-lifetime", renewal_years=None)
        r = row_for(afa.offer_preview(CATALOG, "0", terms=lifetime), "Analyst", "Annual")
        assert r["partner_renewal"] == "$99.75" and r["partner_first_year"] == "$199.50"
        assert afa.renewal_length_label(lifetime) == "Lifetime"
        assert afa.renewal_length_label(terms()) == "5 years (renewals in years 2-5)"


# ============================================================================
# 3. Terms form
# ============================================================================

class TestTermsForm:
    FORM = dict(version="v2-10y-custom", pool_pct="50", max_discount_pct="25",
                promo_commission_pct="50", renewal_pct="25", renewal_length="10",
                activity_rule_months="12", notes="")

    def test_valid_form_maps_renewal_length(self):
        out = afa.parse_terms_form(self.FORM)
        assert out["renewal_years"] == 10 and out["max_discount_pct"] == D(25)
        assert afa.parse_terms_form(dict(self.FORM, renewal_length="lifetime"))["renewal_years"] is None
        assert afa.parse_terms_form(dict(self.FORM, renewal_length="5"))["renewal_years"] == 5

    @pytest.mark.parametrize("change", [
        {"version": "x"}, {"pool_pct": "101"}, {"max_discount_pct": "60"},
        {"renewal_length": "7"}, {"activity_rule_months": "-1"}, {"renewal_pct": "abc"},
    ])
    def test_bad_values_are_refused(self, change):
        with pytest.raises(afa.FormError):
            afa.parse_terms_form(dict(self.FORM, **change))

    def test_created_version_can_be_assigned_prospectively(self, db):
        kwargs = afa.parse_terms_form(self.FORM)
        row = afs.create_terms(db, kwargs.pop("version"), **kwargs)
        aff = make_partner(db)
        ref = make_referral(db, aff)
        afs.assign_terms(db, aff, row.id, actor="admin:x")
        db.refresh(aff)
        db.refresh(ref)
        assert aff.terms_id == row.id
        assert ref.terms_id == 1                         # the existing customer keeps v2-5y


# ============================================================================
# 4. Campaign form validation + preview
# ============================================================================

class TestCampaignForm:
    def test_valid_form(self):
        spec = afa.parse_campaign_form(campaign_form(), CATALOG)
        assert spec["tiers"] == ["analyst"] and spec["intervals"] == ["year"]
        assert spec["intro_prices"] == {"analyst:year": 9900}
        assert spec["new_customers_only"] is True and spec["code"] is None
        # entered in New York time, stored in UTC (EST = UTC-5 in late November)
        assert spec["starts_at"] == day(2026, 11, 27, 5) and spec["ends_at"] == day(2026, 12, 1, 5)

    def test_claim_window_in_utc(self):
        spec = afa.parse_campaign_form(campaign_form(tz="UTC"), CATALOG)
        assert spec["starts_at"] == day(2026, 11, 27, 0)
        assert afa.window_text(spec["starts_at"], "America/New_York") == (
            "2026-11-26 19:00 America/New_York (2026-11-27 00:00 UTC)")

    def test_end_must_be_after_start(self):
        for ends in ("2026-11-27T00:00", "2026-11-26T23:59"):
            with pytest.raises(afa.FormError) as e:
                afa.parse_campaign_form(campaign_form(ends_local=ends), CATALOG)
            assert "The claim window must end after it starts." in e.value.errors

    def test_at_least_one_plan_and_interval(self):
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(campaign_form(tiers=None), CATALOG)
        assert "Pick at least one plan." in e.value.errors
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(campaign_form(intervals=None), CATALOG)
        assert any("billing interval" in x for x in e.value.errors)

    @pytest.mark.parametrize("price", ["0", "-5", "", "abc", "99.999"])
    def test_prices_must_be_positive_dollar_amounts(self, price):
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(campaign_form(price_analyst_year=price), CATALOG)
        assert any("Analyst annual" in x for x in e.value.errors)

    def test_price_must_be_below_the_regular_price(self):
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(campaign_form(price_analyst_year="399"), CATALOG)
        assert any("below the regular price of $399.00" in x for x in e.value.errors)

    def test_every_eligible_plan_needs_a_price(self):
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(
                campaign_form(tiers=["analyst", "strategist"], intervals=["year", "month"]), CATALOG)
        missing = [x for x in e.value.errors if x.startswith("Enter an intro price")]
        assert len(missing) == 3                          # analyst monthly + both strategist plans

    @pytest.mark.parametrize("percent", ["0", "100", "-10", "", "abc"])
    def test_percent_off_range(self, percent):
        with pytest.raises(afa.FormError):
            afa.parse_campaign_form(campaign_form(offer_type="percent", percent_off=percent), CATALOG)
        ok = afa.parse_campaign_form(campaign_form(offer_type="percent", percent_off="30"), CATALOG)
        assert ok["percent_off"] == D(30) and ok["intro_prices"] is None

    def test_missing_name_dates_and_offer_type_are_all_reported(self):
        with pytest.raises(afa.FormError) as e:
            afa.parse_campaign_form(campaign_form(name=" ", starts_local="", offer_type="bogus"), CATALOG)
        assert len(e.value.errors) == 3

    def test_intro_months_only_matter_for_monthly_plans(self):
        assert afa.parse_campaign_form(campaign_form(intro_months="0"), CATALOG)["intro_months"] == 12
        with pytest.raises(afa.FormError):
            afa.parse_campaign_form(campaign_form(intervals=["month"], price_analyst_month="19",
                                                  intro_months="0"), CATALOG)
        assert afa.intro_length_label("year", 6) == "First year (1 annual payment)"
        assert afa.intro_length_label("month", 6) == "First 6 monthly payments"

    def test_parsed_form_creates_and_round_trips(self, db, campaign_stripe):
        spec = afa.parse_campaign_form(campaign_form(ends_local="2099-12-01T00:00"), CATALOG)
        fields = {k: spec[k] for k in ("name", "tiers", "intervals", "starts_at", "ends_at",
                                       "offer_type", "intro_prices", "percent_off", "intro_months")}
        c = afs.create_campaign(db, catalog=CATALOG, status="active", **fields)
        assert c.stripe_coupon_ids == {"analyst:year": "cpn_camp1"}
        assert campaign_stripe[0]["amount_off"] == 30000            # $399 - $99
        values = afa.campaign_form_values(c, tzname="America/New_York")
        assert values["starts_local"] == "2026-11-27T00:00" and values["prices"] == {"analyst:year": "99.00"}
        assert afa.campaign_offer_text(c) == "Analyst annual $99.00"
        assert afa.campaign_phase(c, day(2026, 11, 28)) == "Live - customers can claim"
        assert afa.campaign_phase(c, day(2026, 11, 1)) == "Scheduled"
        afs.update_campaign(db, c, status="archived")
        assert afa.campaign_phase(c) == "Archived"
        assert afs.active_campaign_for(db, "analyst", "year", 39900, day(2026, 11, 28)) == (None, None)


class TestCampaignPreview:
    def _row(self, **kw):
        spec = afa.parse_campaign_form(campaign_form(**kw), CATALOG)
        rows = afa.campaign_preview(spec, CATALOG)
        assert len(rows) == 1
        return rows[0]

    def test_99_analyst_annual_direct_and_referred(self):
        r = self._row()
        assert (r["plan"], r["interval_label"], r["list_price"], r["renewal_price"]) == (
            "Analyst", "Annual", "$399.00", "$399.00")
        assert (r["direct"]["customer_pays"], r["direct"]["partner_earns"],
                r["direct"]["retained"]) == ("$99.00", "$0.00", "$99.00")
        assert (r["referred"]["customer_pays"], r["referred"]["partner_earns"],
                r["referred"]["retained"]) == ("$99.00", "$49.50", "$49.50")
        assert r["intro_length"] == "First year (1 annual payment)"

    def test_50_dollar_promo_pays_25(self):
        r = self._row(price_analyst_year="50")
        assert (r["referred"]["partner_earns_cents"], r["referred"]["retained_cents"]) == (2500, 2500)

    def test_campaign_wins_against_a_0_and_a_25_percent_partner(self):
        r = self._row()
        zero, top = r["winners"]
        assert (zero["partner_discount_pct"], zero["partner_price"], zero["winner"]) == ("0", "$399.00", "campaign")
        assert (top["partner_discount_pct"], top["partner_price"], top["winner"]) == ("25", "$299.25", "campaign")
        for w in (zero, top):                                # campaign wins -> promo rule
            assert (w["customer_pays"], w["partner_earns"], w["retained"]) == ("$99.00", "$49.50", "$49.50")

    def test_partner_discount_wins_when_it_is_the_lower_price(self):
        r = self._row(offer_type="percent", percent_off="10")
        zero, top = r["winners"]
        assert zero["winner"] == "campaign"                  # $359.10 beats the $399 list price
        assert (zero["customer_pays"], zero["partner_earns"]) == ("$359.10", "$179.55")
        assert top["winner"] == "partner"                    # $299.25 beats $359.10 -> pool rule
        assert (top["customer_pays"], top["partner_earns"], top["retained"]) == (
            "$299.25", "$99.75", "$199.50")

    def test_a_tie_goes_to_the_partner_discount(self):
        r = self._row(offer_type="percent", percent_off="25")
        top = r["winners"][1]
        assert top["partner_price"] == top["campaign_price"] == "$299.25"
        assert top["winner"] == "partner"

    def test_preview_agrees_with_the_checkout_rule(self, db, campaign_stripe):
        """The preview's winner is what resolve_checkout_offer picks."""
        afs.create_campaign(db, name="Ten", tiers=["analyst"], intervals=["year"],
                            starts_at=day(2026, 11, 1), ends_at=day(2099, 1, 1),
                            offer_type="percent", percent_off=10, catalog=CATALOG)
        aff = make_partner(db, discount_pct=D(25))
        got = afs.resolve_checkout_offer(
            db, user=SimpleNamespace(email="b@example.com", referred_by_affiliate_id=None),
            raw_code="ANNE", tier="analyst", period="yearly", list_price_cents=39900,
            now=day(2026, 11, 24))
        top = self._row(offer_type="percent", percent_off="10")["winners"][1]
        assert got["offer_type"] == "regular" and top["winner"] == "partner"
        assert got["first_period_cents"] == top["customer_pays_cents"] == 29925
        assert aff.status == "active"

    def test_monthly_plan_shows_intro_length_and_renewal_price(self):
        r = self._row(intervals=["month"], price_analyst_month="19", intro_months="6")
        assert (r["intro_price"], r["renewal_price"], r["intro_length"]) == (
            "$19.00", "$49.00", "First 6 monthly payments")
        assert r["referred"]["partner_earns"] == "$9.50"


# ============================================================================
# 5. Payouts: minimum carry, mark paid, tax form, held lines
# ============================================================================

APRIL, MAY, JUNE = dt.date(2026, 4, 1), dt.date(2026, 5, 1), dt.date(2026, 6, 1)


def sale(iid, sub, customer, paid_at, paid=8000, list_cents=10000):
    return invoice(iid, paid=paid, list_cents=list_cents, paid_at=paid_at, sub=sub, customer=customer)


class TestPayoutMinimum:
    def test_config_default_is_50_dollars(self):
        import config
        assert config.AFFILIATE_PAYOUT_MINIMUM_CENTS == 5000
        assert afs.payout_minimum() == D("50.00") and afa.payout_minimum_cents() == 5000
        src = open(config.__file__).read()
        assert "TW2_AFFILIATE_PAYOUT_MINIMUM_CENTS" in src

    def test_month_below_minimum_stays_pending_and_is_carried(self, db, stripe_world):
        aff = make_partner(db, tax_form_received_at=day(2026, 1, 1))
        make_referral(db, aff)
        make_referral(db, aff, sub="sub_2", customer="cus_2")
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10))]
        afs.upsert_month(db, 2026, 4)
        april = payout_for(db, aff, APRIL)
        assert (april.status, april.commission_amount) == ("pending", D("30.00"))
        assert afa.payout_below_minimum(april)
        assert afa.payout_note(april) == "Below minimum, carried"
        assert "below the $50.00 payout minimum" in afa.payout_block_reason(april)

        stripe_world.invoices.append(sale("in_2", "sub_2", "cus_2", ts(2026, 5, 10)))
        afs.upsert_month(db, 2026, 5)
        afs.upsert_month(db, 2026, 5)                                 # re-run: carried once
        db.refresh(april)
        may = payout_for(db, aff, MAY)
        assert (april.status, april.external_ref) == ("void", "carried:2026-05")
        assert afa.payout_note(april) == "Carried into 2026-05"
        assert (may.status, may.commission_amount) == ("pending", D("60.00"))
        assert may.detail["carry_in"] == [{"period": "2026-04-01", "amount": "30.00"}]
        assert afa.payout_note(may) == "Includes $30.00 carried from 2026-04"
        assert afa.payout_block_reason(may) is None                   # $60 can be paid

    def test_marking_the_carried_into_month_paid_pays_both_months_lines(self, db, stripe_world):
        aff = make_partner(db, tax_form_received_at=day(2026, 1, 1))
        make_referral(db, aff)
        make_referral(db, aff, sub="sub_2", customer="cus_2")
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10))]
        afs.upsert_month(db, 2026, 4)
        stripe_world.invoices.append(sale("in_2", "sub_2", "cus_2", ts(2026, 5, 10)))
        afs.upsert_month(db, 2026, 5)
        may = payout_for(db, aff, MAY)
        assert [l.state for l in ledger(db)] == ["pending", "pending"]
        totals = afa.payout_line_totals(db, [may.id, payout_for(db, aff, APRIL).id])
        assert afa.payout_lines_text(totals[may.id]) == "1 line, $30.00"
        may.status = "paid"
        db.commit()
        assert afa.sync_paid_lines(db) == 2
        assert [l.state for l in ledger(db)] == ["paid", "paid"]
        assert afa.sync_paid_lines(db) == 0                           # idempotent
        assert afa.payout_lines_text(afa.payout_line_totals(db, [may.id])[may.id]) == (
            "1 line, $30.00 (1 paid)")

    def test_month_at_or_above_the_minimum_is_not_carried(self, db, stripe_world):
        aff = make_partner(db, discount_pct=D(0), tax_form_received_at=day(2026, 1, 1))
        make_referral(db, aff, discount_pct=D(0))
        make_referral(db, aff, sub="sub_2", customer="cus_2", discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=10000)]
        afs.upsert_month(db, 2026, 4)
        april = payout_for(db, aff, APRIL)
        assert april.commission_amount == D("50.00") and afa.payout_block_reason(april) is None
        assert afa.payout_note(april) == ""
        stripe_world.invoices.append(sale("in_2", "sub_2", "cus_2", ts(2026, 5, 10), paid=10000))
        afs.upsert_month(db, 2026, 5)
        db.refresh(april)
        assert april.status == "pending" and payout_for(db, aff, MAY).commission_amount == D("50.00")

    def test_minimum_is_read_from_config(self, db, stripe_world, monkeypatch):
        import config
        monkeypatch.setattr(config, "AFFILIATE_PAYOUT_MINIMUM_CENTS", 2000)
        aff = make_partner(db, tax_form_received_at=day(2026, 1, 1))
        make_referral(db, aff)
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10))]
        afs.upsert_month(db, 2026, 4)
        assert afa.payout_block_reason(payout_for(db, aff, APRIL)) is None

    def test_tax_form_gate_comes_first(self, db, stripe_world):
        aff = make_partner(db, discount_pct=D(0))                     # no tax form
        make_referral(db, aff, discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=10000)]
        afs.upsert_month(db, 2026, 4)
        reason = afa.payout_block_reason(payout_for(db, aff, APRIL))
        assert "no tax form on file" in reason

    def test_negative_month_cannot_be_paid(self):
        aff = SimpleNamespace(code="ANNE", tax_form_received_at=day(2026, 1, 1))
        row = SimpleNamespace(commission_amount=D("-15.00"), affiliate=aff, status="pending",
                              external_ref=None, detail=None)
        assert "negative" in afa.payout_block_reason(row)
        assert afa.payout_note(row) == "Negative, carried into the next payable month"


class TestPayoutAdminView:
    def _month(self, db, stripe_world, paid=10000, **partner_kw):
        aff = make_partner(db, discount_pct=D(0), **partner_kw)
        make_referral(db, aff, discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=paid,
                                      list_cents=paid)]
        afs.upsert_month(db, 2026, 4)
        return aff, payout_for(db, aff, APRIL)

    def test_mark_paid_stamps_the_date_and_flips_the_lines(self, app_module, db, stripe_world):
        aff, row = self._month(db, stripe_world, tax_form_received_at=day(2026, 1, 1))
        view = SimpleNamespace(session=db)
        row.status = "paid"
        with app_module.app.test_request_context("/admin/affiliatepayout/"):
            app_module.AffiliatePayoutAdmin.on_model_change(view, None, row, False)
            db.commit()
            assert row.paid_at is not None
            assert ledger(db)[0].state == "pending"
            app_module.AffiliatePayoutAdmin.after_model_change(view, None, row, False)
        assert ledger(db)[0].state == "paid"

    def test_mark_paid_refused_below_the_minimum(self, app_module, db, stripe_world):
        from wtforms.validators import ValidationError
        aff, row = self._month(db, stripe_world, paid=6000, tax_form_received_at=day(2026, 1, 1))
        assert row.commission_amount == D("30.00")
        row.status = "paid"
        with pytest.raises(ValidationError) as e:
            app_module.AffiliatePayoutAdmin.on_model_change(SimpleNamespace(session=db), None, row, False)
        assert "payout minimum" in str(e.value)
        db.rollback()
        assert payout_for(db, aff, APRIL).status == "pending" and ledger(db)[0].state == "pending"

    def test_mark_paid_refused_without_a_tax_form(self, app_module, db, stripe_world):
        from wtforms.validators import ValidationError
        aff, row = self._month(db, stripe_world)
        row.status = "paid"
        with pytest.raises(ValidationError) as e:
            app_module.AffiliatePayoutAdmin.on_model_change(SimpleNamespace(session=db), None, row, False)
        assert "tax form" in str(e.value)
        db.rollback()

    def test_ledger_view_is_read_only_with_the_required_filters(self, app_module):
        view = app_module.AffiliateCommissionLineAdmin
        assert (view.can_create, view.can_edit, view.can_delete) == (False, False, False)
        for col in ("affiliate", "period_month", "kind", "state", "hold_reason", "rate_pct",
                    "basis_cents", "amount", "payable_month"):
            assert col in view.column_list
        names = [f if isinstance(f, str) else f.name for f in view.column_filters]
        assert names[:5] == ["affiliate.code", "period_month", "payable_month", "Type", "State"]
        assert "ledger_lines" in app_module.AffiliatePayoutAdmin.column_list
        assert "payout_note" in app_module.AffiliatePayoutAdmin.column_list


class TestHeldLines:
    def test_paused_partner_lines_are_held_visible_and_released_on_unpause(self, db, stripe_world):
        aff = make_partner(db, discount_pct=D(0), status="paused")
        make_referral(db, aff, discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=10000)]
        afs.upsert_month(db, 2026, 4)
        line = ledger(db)[0]
        assert (line.state, line.hold_reason) == ("held", "paused")
        assert payout_for(db, aff, APRIL) is None                     # nothing payable yet
        held = afa.held_summary(db)
        assert [(h["code"], h["count"], h["amount"], h["status"]) for h in held] == [
            ("ANNE", 1, D("50.00"), "paused")]
        assert held[0]["reason"].startswith("Partner paused")
        assert afa.LINE_STATE_LABELS[line.state] == "Held"

        aff.status = "active"
        db.commit()
        afs.upsert_month(db, 2026, 5)
        db.refresh(line)
        assert (line.state, line.hold_reason, line.payable_month) == ("pending", None, MAY)
        assert payout_for(db, aff, MAY).commission_amount == D("50.00")
        assert afa.held_summary(db) == []


# ============================================================================
# 6. Terminate for cause
# ============================================================================

class TestTerminateForCause:
    @pytest.mark.parametrize("reason", [None, "", "   ", "too short"])
    def test_a_written_reason_is_required(self, db, reason):
        aff = make_partner(db)
        with pytest.raises(afs.AffiliateError) as e:
            afa.terminate_partner_for_cause(db, aff, reason, "admin:x")
        assert "reason" in str(e.value).lower()
        db.refresh(aff)
        assert aff.status == "active" and not aff.terminated_for_cause

    def test_reason_is_recorded_and_unpaid_commission_is_forfeited(self, db, stripe_world, monkeypatch):
        import models
        off = []
        monkeypatch.setattr(afs.stripe.PromotionCode, "modify", lambda pid, **kw: off.append((pid, kw)))
        aff = make_partner(db, discount_pct=D(0))
        make_referral(db, aff, discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=10000)]
        afs.upsert_month(db, 2026, 4)
        afa.terminate_partner_for_cause(db, aff, "Paid search on the TradeWave brand name",
                                        "admin:afshin@example.com")
        db.refresh(aff)
        assert (aff.status, aff.terminated_for_cause) == ("terminated", True)
        assert aff.termination_cause == "Paid search on the TradeWave brand name"
        assert aff.terminated_at is not None and aff.agreement_token_version == 1
        assert off == [("promo_anne", {"active": False})]
        audit = db.query(models.AuditLog).filter_by(action="affiliate_terminated_for_cause").one()
        assert audit.actor_label == "admin:afshin@example.com"
        with pytest.raises(afs.AffiliateError):                       # not twice
            afa.terminate_partner_for_cause(db, aff, "A second reason, long enough", "admin:x")
        # forfeited at once, including the line already on an unpaid payout row
        row = payout_for(db, aff, APRIL)
        assert (row.status, row.external_ref) == ("void", afa.FORFEIT_REF)
        assert afa.payout_note(row) == "Forfeited - terminated for cause"
        line = ledger(db)[0]
        assert (line.state, line.hold_reason, line.payable_month) == (
            "void", "terminated_for_cause", None)
        assert line.amount == D(50)                                   # never re-priced
        afs.upsert_month(db, 2026, 5)                                 # and it stays that way
        assert payout_for(db, aff, MAY) is None and ledger(db)[0].state == "void"

    def test_paid_commission_is_not_touched(self, db, stripe_world, monkeypatch):
        monkeypatch.setattr(afs.stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = make_partner(db, discount_pct=D(0))
        make_referral(db, aff, discount_pct=D(0))
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10), paid=10000)]
        afs.upsert_month(db, 2026, 4)
        payout_for(db, aff, APRIL).status = "paid"
        db.commit()
        afa.sync_paid_lines(db)
        afa.terminate_partner_for_cause(db, aff, "Breach found after the April payout", "admin:x")
        assert payout_for(db, aff, APRIL).status == "paid" and ledger(db)[0].state == "paid"


# ============================================================================
# 7. The pages render and the forms post (Flask test client, SQLite session)
# ============================================================================

@pytest.fixture
def admin(app_module, db, monkeypatch):
    """Logged-in super admin; the admin views read/write the SQLite `db`."""
    import models
    mod = app_module
    monkeypatch.setattr(mod, "get_current_user",
                        lambda: SimpleNamespace(id="u-admin", email="afshin@example.com",
                                                roles=["super_admin"]))
    monkeypatch.setattr(mod, "write_audit", lambda **kw: None)
    monkeypatch.setattr(mod, "_campaign_catalog", lambda: CATALOG)
    monkeypatch.setattr(models, "Session", db.factory)
    monkeypatch.setitem(mod.app.config, "WTF_CSRF_ENABLED", False)
    return mod.app.test_client()


def text_of(resp):
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


def assert_plain_ui(html):
    assert "—" not in html                        # no em-dashes in UI strings


class TestAdminPages:
    def test_menu_has_terms_ledger_and_campaigns_next_to_coupons(self, app_module):
        names = [v.name for v in app_module.admin._views]
        for name in ("Terms", "Commission lines", "Campaigns", "Change terms"):
            assert name in names
        assert names.index("Campaigns") == names.index("Coupons") + 1

    def test_terms_page_lists_versions_and_partners(self, admin, db):
        make_partner(db)
        make_partner(db, code="BOB", terms_id=3)
        html = text_of(admin.get("/admin/affiliate_terms/"))
        assert_plain_ui(html)
        for needle in ("v2-5y", "v2-10y", "v2-lifetime", "Lifetime", "ANNE", "BOB",
                       "Terms apply to future customers only", "New terms version"):
            assert needle in html

    def test_terms_create_posts_and_rejects_bad_input(self, admin, db):
        import models
        resp = admin.post("/admin/affiliate_terms/create", data=dict(TestTermsForm.FORM))
        assert resp.status_code == 302
        row = db.query(models.AffiliateTerms).filter_by(version="v2-10y-custom").one()
        assert row.renewal_years == 10
        html = text_of(admin.post("/admin/affiliate_terms/create",
                                  data=dict(TestTermsForm.FORM, version="v2-bad", max_discount_pct="60")))
        assert "Maximum customer discount cannot be more than the pool." in html
        assert db.query(models.AffiliateTerms).filter_by(version="v2-bad").first() is None

    def test_change_terms_page_shows_pool_math_and_preview(self, admin, db):
        aff = make_partner(db, agreement_signed_at=day(2026, 1, 1))
        html = text_of(admin.get("/admin/affiliate_change_terms/?id=%s" % aff.id))
        assert_plain_ui(html)
        assert "Partner earns = 50% minus the customer discount" in html
        assert "not paused" in html and "Terminate for cause" in html
        assert 'name="commission_pct"' not in html
        for cell in ("$80.00", "$30.00", "$50.00", "$319.20", "$119.70", "$99.75"):
            assert cell in html
        for header in ("List price", "Customer pays", "Partner earns (first year)",
                       "Partner earns per renewal", "TradeWave retains"):
            assert header in html

    def test_live_preview_endpoint(self, admin, db):
        ok = admin.get("/admin/affiliate_change_terms/preview?discount_year=20&discount_month=").get_json()
        assert ok["ok"] and ok["terms"] == "v2-5y"
        first = ok["rows"][0]
        assert (first["customer_pays"], first["partner_first_year"], first["retained"]) == (
            "$80.00", "$30.00", "$50.00")
        assert len(ok["rows"]) == 7                       # example + 3 plans x 2 intervals
        bad = admin.get("/admin/affiliate_change_terms/preview?discount_year=26").get_json()
        assert bad["ok"] is False and "0% to 25%" in bad["error"]

    def test_apply_refuses_26_and_accepts_25_without_pause(self, admin, db, monkeypatch):
        import models
        aff = make_partner(db, agreement_signed_at=day(2026, 1, 1))
        aid = str(aff.id)
        monkeypatch.setattr(afs, "reissue_coupon", lambda a, pct: ("cpn_new", "promo_new"))
        resp = admin.post("/admin/affiliate_change_terms/apply",
                          data={"id": aid, "discount_pct": "26", "discount_pct_monthly": ""})
        assert resp.status_code == 302
        db.expire_all()
        assert db.query(models.Affiliate).one().discount_pct == D(20)
        resp = admin.post("/admin/affiliate_change_terms/apply",
                          data={"id": aid, "discount_pct": "25", "discount_pct_monthly": ""})
        assert resp.status_code == 302
        db.expire_all()
        got = db.query(models.Affiliate).one()
        assert (got.discount_pct, got.status) == (D(25), "active")
        assert got.agreement_signed_at is not None
        change = db.query(models.AffiliateDiscountChange).one()
        assert change.actor == "admin:afshin@example.com"

    def test_assign_terms_with_and_without_a_new_signature(self, admin, db, monkeypatch):
        import models
        monkeypatch.setattr(afs.stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = make_partner(db, agreement_signed_at=day(2026, 1, 1), agreement_signed_name="Anne")
        aid = str(aff.id)
        admin.post("/admin/affiliate_change_terms/assign", data={"id": aid, "terms_id": "2"})
        db.expire_all()
        got = db.query(models.Affiliate).one()
        assert (got.terms_id, got.status) == (2, "active") and got.agreement_signed_at is not None
        admin.post("/admin/affiliate_change_terms/assign",
                   data={"id": aid, "terms_id": "3", "resign": "1"})
        db.expire_all()
        got = db.query(models.Affiliate).one()
        assert (got.terms_id, got.status) == (3, "paused")
        assert got.agreement_signed_at is None and got.agreement_token_version == 1

    def test_terminate_needs_a_reason(self, admin, db, monkeypatch):
        import models
        monkeypatch.setattr(afs.stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = make_partner(db)
        aid = str(aff.id)
        admin.post("/admin/affiliate_change_terms/terminate", data={"id": aid, "reason": "  "})
        db.expire_all()
        assert db.query(models.Affiliate).one().status == "active"
        admin.post("/admin/affiliate_change_terms/terminate",
                   data={"id": aid, "reason": "Misleading performance claims in ads"})
        db.expire_all()
        got = db.query(models.Affiliate).one()
        assert got.terminated_for_cause and got.termination_cause.startswith("Misleading")
        html = text_of(admin.get("/admin/affiliate_change_terms/?id=%s" % aid))
        assert "Terminated for cause" in html and "Misleading performance claims in ads" in html

    def test_campaign_pages(self, admin, db, campaign_stripe):
        import models
        html = text_of(admin.get("/admin/promo_campaigns/"))
        assert "No campaigns yet." in html and "New campaign" in html
        html = text_of(admin.get("/admin/promo_campaigns/edit"))
        assert_plain_ui(html)
        for needle in ("Customers can claim from", "Customers can claim until", "Intro price lasts",
                       "Timezone of these times", "stored in UTC", "$399.00 per year",
                       "New customers only", "Fixed intro price per plan", "Percent off"):
            assert needle in html
        assert 'value="save_draft"' not in html           # no saving before the preview

        form = campaign_form(ends_local="2099-12-01T00:00", action="preview")
        html = text_of(admin.post("/admin/promo_campaigns/edit", data=form))
        assert_plain_ui(html)
        for needle in ("Direct sale (no partner)", "Referred sale", "$49.50",
                       "Which offer wins with a partner code", "0% partner", "25% partner",
                       "Campaign price", "$299.25", 'value="save_draft"', 'value="activate"',
                       "2026-11-27 00:00 America/New_York (2026-11-27 05:00 UTC)"):
            assert needle in html
        assert db.query(models.PromoCampaign).count() == 0     # a preview saves nothing

        bad = campaign_form(ends_local="2026-11-01T00:00", action="activate")
        html = text_of(admin.post("/admin/promo_campaigns/edit", data=bad))
        assert "The claim window must end after it starts." in html
        assert db.query(models.PromoCampaign).count() == 0

        form["action"] = "save_draft"
        assert admin.post("/admin/promo_campaigns/edit", data=form).status_code == 302
        c = db.query(models.PromoCampaign).one()
        assert (c.status, c.stripe_coupon_ids, campaign_stripe) == ("draft", None, [])
        cid = str(c.id)

        html = text_of(admin.get("/admin/promo_campaigns/edit?id=%s" % cid))
        assert "Draft - not live" in html and "$49.50" in html
        form["action"] = "activate"
        assert admin.post("/admin/promo_campaigns/edit?id=%s" % cid, data=form).status_code == 302
        db.expire_all()
        c = db.query(models.PromoCampaign).one()
        assert c.status == "active" and c.stripe_coupon_ids == {"analyst:year": "cpn_camp1"}
        assert c.starts_at.replace(tzinfo=dt.timezone.utc) == day(2026, 11, 27, 5)

        html = text_of(admin.get("/admin/promo_campaigns/"))
        assert "Black Friday 2026" in html and "Analyst annual $99.00" in html and "Archive" in html
        assert admin.post("/admin/promo_campaigns/archive", data={"id": cid}).status_code == 302
        db.expire_all()
        assert db.query(models.PromoCampaign).one().status == "archived"

    def test_pages_need_a_super_admin(self, app_module, monkeypatch):
        monkeypatch.setattr(app_module, "get_current_user",
                            lambda: SimpleNamespace(id="u", email="x@example.com", roles=["user"]))
        client = app_module.app.test_client()
        for url in ("/admin/affiliate_terms/", "/admin/promo_campaigns/",
                    "/admin/affiliate_change_terms/preview?discount_year=20"):
            assert client.get(url).status_code == 403

    def test_no_em_dashes_in_admin_strings(self):
        import inspect
        src = inspect.getsource(afa)
        assert "—" not in src and "&mdash;" not in src


# ============================================================================
# 8. The Flask-Admin model views render on the SQLite copy
# ============================================================================

@pytest.fixture
def model_admin(admin, app_module, db, monkeypatch):
    """`admin` client with the ModelViews pointed at the SQLite session.

    Harness-only shims for what SQLite lacks next to Postgres: a bare `users`
    table (the Affiliates list joins the portal login), the terms dropdown's
    query (bound to the real session when the form class was built) and
    primary-key lookup by string UUID."""
    import models
    import sqlalchemy as sa
    md = sa.MetaData()
    sa.Table("users", md, *[sa.Column(c.name, sa.Text, primary_key=c.primary_key)
                            for c in models.User.__table__.columns])
    md.create_all(db.get_bind())
    for view in app_module.admin._views:
        name = type(view).__name__
        if name not in ("AffiliateAdmin", "AffiliatePayoutAdmin", "AffiliateCommissionLineAdmin"):
            continue
        monkeypatch.setattr(view, "session", db)
        if name == "AffiliateAdmin":
            monkeypatch.setitem(view._create_form_class.terms.kwargs, "query_factory",
                                lambda: db.query(models.AffiliateTerms))
            monkeypatch.setattr(view, "get_one", lambda pk: db.get(models.Affiliate, uuid.UUID(pk)))
    return admin


class TestModelViews:
    def _seed(self, db, stripe_world):
        aff = make_partner(db, tax_form_received_at=day(2026, 1, 1))
        make_referral(db, aff)
        stripe_world.invoices = [sale("in_1", "sub_1", "cus_1", ts(2026, 4, 10))]
        afs.upsert_month(db, 2026, 4)
        held = make_partner(db, code="HELD", status="paused", discount_pct=D(0))
        make_referral(db, held, sub="sub_h", customer="cus_h", discount_pct=D(0))
        stripe_world.invoices.append(sale("in_h", "sub_h", "cus_h", ts(2026, 4, 12), paid=10000))
        afs.upsert_month(db, 2026, 4)
        return aff

    def test_affiliate_list_shows_pool_share_and_terms(self, model_admin, db):
        make_partner(db)
        html = text_of(model_admin.get("/admin/affiliate/"))
        assert "20% off - partner earns 30% of list" in html
        assert "Terms version" in html and "v2-5y" in html
        assert "Annual commission %" not in html

    def test_affiliate_create_form_has_preview_and_no_commission_inputs(self, model_admin):
        html = text_of(model_admin.get("/admin/affiliate/new/"))
        assert 'name="discount_pct"' in html and 'name="terms"' in html
        assert 'name="commission_pct"' not in html and 'name="commission_model"' not in html
        assert 'id="tw-offer-preview"' in html and "/admin/affiliate_change_terms/preview" in html
        assert "Partner earns (first year)" in html and "TradeWave retains" in html

    def test_affiliate_edit_form_points_to_change_terms(self, model_admin, db):
        aff = make_partner(db)
        html = text_of(model_admin.get("/admin/affiliate/edit/?id=%s" % aff.id))
        assert 'name="discount_pct"' not in html and 'name="commission_pct"' not in html
        assert "Change terms" in html and 'name="status"' in html

    def test_payout_list_shows_line_totals_and_the_carry_note(self, model_admin, db, stripe_world):
        self._seed(db, stripe_world)
        html = text_of(model_admin.get("/admin/affiliatepayout/"))
        assert "Ledger lines" in html and "1 line, $30.00" in html
        assert "Below minimum, carried" in html

    def test_commission_lines_list_and_filters(self, model_admin, app_module, db, stripe_world):
        self._seed(db, stripe_world)
        html = text_of(model_admin.get("/admin/affiliatecommissionline/"))
        for needle in ("Month earned", "Rate %", "Commission basis", "Hold reason", "First year",
                       "Payable", "Held",
                       "Partner paused - becomes payable when the partner is active again",
                       "$100.00", "$30.00", "2026-04"):
            assert needle in html
        view = next(v for v in app_module.admin._views
                    if type(v).__name__ == "AffiliateCommissionLineAdmin")
        names = [str(f.name) for f in view._filters]
        for wanted in ("Affiliate code", "Month earned", "Payout month", "Type", "State"):
            assert any(n.endswith(wanted) for n in names), (wanted, names)
        state_idx = next(i for i, n in enumerate(names) if n.endswith("State"))
        held = text_of(model_admin.get("/admin/affiliatecommissionline/?flt0_%d=held" % state_idx))
        assert "Partner paused" in held and "$30.00" not in held
        paid = text_of(model_admin.get("/admin/affiliatecommissionline/?flt0_%d=paid" % state_idx))
        assert "Partner paused" not in paid

    def test_compute_page_shows_minimum_and_held(self, model_admin, db, stripe_world):
        self._seed(db, stripe_world)
        html = text_of(model_admin.get("/admin/affiliate_compute/?year=2026&month=4"))
        assert "Payout minimum $50.00" in html and "Below minimum, carried" in html
        assert "Held commission (all months)" in html and "HELD" in html

    def test_guide_page_describes_v2(self, model_admin):
        html = text_of(model_admin.get("/admin/affiliate_guide/"))
        assert "—" not in html
        assert "50% of the list price" in html and "$50 payout minimum" in html
        assert "Annual commission %" not in html
