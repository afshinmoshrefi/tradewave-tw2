"""Regression tests for the independent code review of affiliate v2
(TW-TASK-0038). One class per finding; each test failed before its fix.

Hermetic like tests/test_affiliate_v2.py, whose fakes and SQLite fixture are
reused here.
"""
import datetime as dt
import logging
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe

import affiliate_service as afs
from tests.test_affiliate_v2 import (  # noqa: F401  (fixtures are used by name)
    AFF_ID, D, FakeList, MAY, PAID_MAY, app_module, db, day, invoice, ledger, lines_of,
    make_partner, make_referral, partner, payout_for, referral, refund, resolve,
    stripe_world, terms, total, ts)
from tests.test_affiliate_admin_v2 import admin, text_of  # noqa: F401


@pytest.fixture
def coupons(monkeypatch):
    """Fake Stripe coupons: {coupon_id: percent_off}; records created ones."""
    world = SimpleNamespace(pct={}, created=[], modified=[])
    monkeypatch.setattr(afs, "_coupon_pct_cache", {})

    def retrieve(cid, **kw):
        return {"id": cid, "percent_off": world.pct[cid]}

    def create(**kw):
        cid = "cpn_new%d" % (len(world.created) + 1)
        world.created.append(kw)
        world.pct[cid] = kw.get("percent_off")
        return SimpleNamespace(id=cid)
    monkeypatch.setattr(stripe.Coupon, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Coupon, "create", create)
    monkeypatch.setattr(stripe.Coupon, "delete", lambda cid: None)
    monkeypatch.setattr(stripe.PromotionCode, "create",
                        lambda **kw: SimpleNamespace(id="promo_new"))
    monkeypatch.setattr(stripe.PromotionCode, "modify",
                        lambda pid, **kw: world.modified.append((pid, kw)))
    monkeypatch.setattr(stripe.PromotionCode, "list", lambda **kw: FakeList([]))
    return world


# ============================================================================
# Finding 1 - a monthly coupon above the 25% cap is re-issued / never applied
# ============================================================================

class TestMonthlyCouponAboveTheCap:
    def _legacy(self, db, coupons):
        """After migration b4d7e1f2a3c5: the DB says 25% monthly, the Stripe
        monthly coupon still says 40%."""
        coupons.pct.update({"cpn_anne": 20.0, "cpn_anne_mo": 40.0})
        return make_partner(db, discount_pct_monthly=D(25), stripe_coupon_id_monthly="cpn_anne_mo")

    def test_checkout_never_applies_a_coupon_that_differs_from_the_stamp(self, db, coupons):
        self._legacy(db, coupons)
        o = resolve(db, raw_code="ANNE", period="monthly", list_price_cents=4900)
        assert o["discount_spec"] is None                  # not the 40% coupon
        assert o["metadata"]["tw2_discount_pct"] == "0.00" and o["first_period_cents"] == 4900

    def test_falls_back_to_the_flat_coupon_when_it_carries_the_stamped_discount(self, db, coupons):
        coupons.pct.update({"cpn_anne": 25.0, "cpn_anne_mo": 40.0})
        make_partner(db, discount_pct=D(25), discount_pct_monthly=D(25),
                     stripe_coupon_id_monthly="cpn_anne_mo")
        o = resolve(db, raw_code="ANNE", period="monthly", list_price_cents=4900)
        assert o["discount_spec"] == {"promotion_code": "promo_anne"}
        assert o["metadata"]["tw2_discount_pct"] == "25.00"

    def test_display_offers_matches_checkout(self, db, coupons):
        aff = self._legacy(db, coupons)
        cat = {("analyst", "month"): {"list_price_cents": 4900}}
        row = afs.display_offers(db, aff, cat)["analyst:month"]
        assert row["price_cents"] == 4900 and row["offer"] is None

    def test_reconcile_reissues_the_monthly_coupon(self, db, coupons):
        aff = self._legacy(db, coupons)
        out = afs.reconcile_v2_stripe(db)
        assert [o["action"] for o in out] == ["monthly_coupon_reissued"]
        assert aff.stripe_coupon_id_monthly == "cpn_new1"
        assert coupons.created[0]["percent_off"] == 25.0
        assert coupons.created[0]["metadata"]["tw2_interval"] == "month"
        o = resolve(db, raw_code="ANNE", period="monthly", list_price_cents=4900)
        assert o["discount_spec"] == {"coupon": "cpn_new1"}
        assert o["metadata"]["tw2_discount_pct"] == "25.00" and o["first_period_cents"] == 3675
        assert afs.reconcile_v2_stripe(db) == []           # idempotent

    def test_reconcile_drops_a_monthly_coupon_that_is_no_longer_needed(self, db, coupons):
        coupons.pct.update({"cpn_anne": 25.0, "cpn_anne_mo": 40.0})
        aff = make_partner(db, discount_pct=D(25), discount_pct_monthly=D(25),
                           stripe_coupon_id_monthly="cpn_anne_mo")
        out = afs.reconcile_v2_stripe(db)
        assert [o["action"] for o in out] == ["monthly_coupon_dropped"]
        assert aff.stripe_coupon_id_monthly is None and aff.discount_pct_monthly is None
        assert coupons.created == []

    def test_matching_coupons_are_left_alone(self, db, coupons):
        coupons.pct.update({"cpn_anne": 20.0, "cpn_anne_mo": 10.0})
        make_partner(db, discount_pct_monthly=D(10), stripe_coupon_id_monthly="cpn_anne_mo")
        assert afs.reconcile_v2_stripe(db) == []
        o = resolve(db, raw_code="ANNE", period="monthly", list_price_cents=4900)
        assert o["discount_spec"] == {"coupon": "cpn_anne_mo"}


# ============================================================================
# Finding 2 - termination WITHOUT cause: commission stays payable, the final
# balance is paid below the minimum, held lines can be released
# ============================================================================

class TestTerminationWithoutCause:
    def _sale(self, db, world, **partner_kw):
        aff = make_partner(db, tax_form_received_at=day(2026, 1, 1), **partner_kw)
        make_referral(db, aff)
        world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        return aff

    def test_lines_are_payable_and_the_final_balance_ignores_the_minimum(self, db, stripe_world):
        import affiliate_admin as afa
        aff = self._sale(db, stripe_world, status="terminated")
        afs.upsert_month(db, *MAY)
        line = ledger(db)[0]
        assert (line.state, line.hold_reason, line.payable_month) == ("pending", None, dt.date(2026, 5, 1))
        row = payout_for(db, aff, dt.date(2026, 5, 1))
        assert row.commission_amount == D("30.00")                     # below the $50 minimum
        assert afa.payout_block_reason(row, aff) is None               # ...and still payable
        assert afa.payout_note(row).startswith("Final balance")
        assert "\u2014" not in afa.payout_note(row)

    def test_minimum_still_applies_to_active_and_for_cause_partners(self, db, stripe_world):
        import affiliate_admin as afa
        aff = self._sale(db, stripe_world)
        afs.upsert_month(db, *MAY)
        row = payout_for(db, aff, dt.date(2026, 5, 1))
        assert "payout minimum" in afa.payout_block_reason(row, aff)
        aff.status, aff.terminated_for_cause = "terminated", True
        assert "payout minimum" in afa.payout_block_reason(row, aff)

    def test_lines_held_while_paused_are_released_by_a_plain_termination(self, db, stripe_world):
        aff = self._sale(db, stripe_world, status="paused")
        afs.upsert_month(db, *MAY)
        assert ledger(db)[0].state == "held"
        aff.status = "terminated"
        db.commit()
        afs.upsert_month(db, 2026, 6)
        line = ledger(db)[0]
        assert (line.state, line.hold_reason, line.payable_month) == ("pending", None, dt.date(2026, 6, 1))
        assert payout_for(db, aff, dt.date(2026, 6, 1)).commission_amount == D("30.00")

    def test_release_held_lines_action(self, db, stripe_world):
        import models
        aff = self._sale(db, stripe_world, status="paused")
        afs.upsert_month(db, *MAY)
        line = ledger(db)[0]
        line.hold_reason = "review"                                    # an explicit operator hold
        aff.status = "terminated"
        db.commit()
        afs.upsert_month(db, 2026, 6)
        db.refresh(line)
        assert (line.state, line.hold_reason) == ("held", "review")    # never released on its own
        assert afs.release_held_lines(db, aff, actor="admin:test") == 1
        db.refresh(line)
        assert (line.state, line.hold_reason, line.payable_month) == ("pending", None, None)
        assert afs.release_held_lines(db, aff) == 0                    # idempotent
        afs.upsert_month(db, 2026, 6)
        assert payout_for(db, aff, dt.date(2026, 6, 1)).commission_amount == D("30.00")
        assert db.query(models.AuditLog).filter_by(action="affiliate_held_lines_released").count() == 1

    def test_release_is_refused_after_termination_for_cause(self, db, stripe_world, monkeypatch):
        monkeypatch.setattr(stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = self._sale(db, stripe_world, status="paused")
        afs.upsert_month(db, *MAY)
        afs.terminate_for_cause(db, aff, "fraudulent self-dealing", actor="admin:test")
        with pytest.raises(afs.AffiliateError, match="forfeited"):
            afs.release_held_lines(db, aff)

    def test_engine_terminate_for_cause_voids_lines_on_unpaid_payout_rows(self, db, stripe_world,
                                                                          monkeypatch):
        """The forfeiture lives in the engine, not only in the admin wrapper."""
        monkeypatch.setattr(stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = self._sale(db, stripe_world)
        afs.upsert_month(db, *MAY)
        line, row = ledger(db)[0], payout_for(db, aff, dt.date(2026, 5, 1))
        assert line.state == "pending" and line.payout_id == row.id
        afs.terminate_for_cause(db, aff, "fraudulent self-dealing", actor="admin:test")
        db.refresh(line)
        db.refresh(row)
        assert (line.state, line.hold_reason, line.payable_month) == ("void", "terminated_for_cause", None)
        assert (row.status, row.external_ref) == ("void", afs.FORFEIT_REF)

    def test_admin_release_held_lines_button(self, admin, db, stripe_world):
        aff = self._sale(db, stripe_world, status="paused")
        afs.upsert_month(db, *MAY)
        aid = str(aff.id)
        html = text_of(admin.get("/admin/affiliate_change_terms/?id=%s" % aid))
        assert "Release held lines" in html and "\u2014" not in html
        resp = admin.post("/admin/affiliate_change_terms/release", data={"id": aid})
        assert resp.status_code == 302
        db.expire_all()
        assert ledger(db)[0].state == "pending"
        html = text_of(admin.get("/admin/affiliate_change_terms/?id=%s" % aid))
        assert "Release held lines" not in html.split("</h1>", 1)[1].replace(
            "1 held line(s) of ANNE released", "")


# ============================================================================
# Finding 3 - a transient Stripe error must never become a permanent line
# ============================================================================

def flaky_customer_lookups(monkeypatch, failures=1):
    """Make the per-customer invoice history lookup raise `failures` times."""
    real = stripe.Invoice.list
    state = {"left": failures, "raised": 0}

    def invoice_list(**kw):
        if "customer" in kw and state["left"] > 0:
            state["left"] -= 1
            state["raised"] += 1
            raise stripe.error.APIConnectionError("stripe timed out")
        return real(**kw)
    monkeypatch.setattr(stripe.Invoice, "list", invoice_list)
    return state


class TestTransientStripeError:
    def _monthly_customer(self, db, world):
        """A monthly customer who first paid in Jan 2025 (webhook missed: the
        referral clock is not stamped). May 2026 is month 17: a RENEWAL."""
        aff = make_partner(db)
        ref = make_referral(db, aff, billing_interval="month", list_price_cents=5000)
        make_referral(db, aff, sub="sub_new", customer="cus_new",       # keeps the partner active
                      first_paid_at=day(2026, 3, 1), year_anchor_at=day(2026, 3, 1))
        first = invoice("in_first", paid=4000, list_cents=5000, paid_at=ts(2025, 1, 10), interval="month")
        may = invoice("in_may", paid=5000, paid_at=ts(2026, 5, 10), interval="month")
        world.invoices = [first, may]
        return aff, ref

    def test_failed_clock_lookup_skips_the_invoice_and_persists_nothing(self, db, stripe_world,
                                                                        monkeypatch, caplog):
        aff, ref = self._monthly_customer(db, stripe_world)
        state = flaky_customer_lookups(monkeypatch)
        with caplog.at_level(logging.WARNING, logger=afs.log.name):
            afs.upsert_month(db, *MAY)
        assert state["raised"] == 1
        assert ledger(db) == []                                        # not booked
        db.refresh(ref)
        assert ref.first_paid_at is None and ref.year_anchor_at is None    # no fallback anchor
        assert "in_may" in caplog.text and "SKIPPED" in caplog.text

        afs.upsert_month(db, *MAY)                                     # Stripe is back
        (line,) = ledger(db)
        assert (line.kind, line.year_number, line.amount) == ("renewal", 2, D("12.50"))
        db.refresh(ref)
        assert afs._utc(ref.first_paid_at) == day(2025, 1, 10)
        assert afs._utc(ref.year_anchor_at) == day(2025, 1, 10)

    def test_skipped_sources_are_reported(self, db, stripe_world, monkeypatch):
        self._monthly_customer(db, stripe_world)
        flaky_customer_lookups(monkeypatch)
        skipped = []
        assert afs.compute_month(db, *MAY, skipped=skipped) == []
        assert [(x["source"], x["id"]) for x in skipped] == [("invoice", "in_may")]

    def test_unresolved_activity_never_books_a_lapsed_line(self, db, stripe_world, monkeypatch):
        """The renewal is only payable if the partner's other (unstamped)
        referral paid recently. Stripe fails on that lookup: no lapsed line."""
        aff = make_partner(db)
        make_referral(db, aff, first_paid_at=day(2024, 5, 10), year_anchor_at=day(2024, 5, 10))
        make_referral(db, aff, sub="sub_new", customer="cus_new")       # clock not stamped
        stripe_world.invoices = [
            invoice("in_renew", paid=39900, paid_at=ts(2026, 5, 10)),
            invoice("in_new", paid=8000, list_cents=10000, paid_at=ts(2026, 2, 1),
                    sub="sub_new", customer="cus_new"),
        ]
        flaky_customer_lookups(monkeypatch)
        afs.upsert_month(db, *MAY)
        assert ledger(db) == []                                        # NOT a lapsed line
        afs.upsert_month(db, *MAY)
        (line,) = ledger(db)
        assert (line.kind, line.state, line.amount) == ("renewal", "pending", D("99.75"))

    def test_a_guessed_anchor_is_used_but_never_persisted(self, db, stripe_world, monkeypatch):
        """Stripe answers, but knows no earlier paid invoice: the invoice in
        hand prices the line, and the referral row is left for the webhook."""
        aff = make_partner(db)
        ref = make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        real = stripe.Invoice.list
        monkeypatch.setattr(stripe.Invoice, "list",
                            lambda **kw: FakeList([]) if "customer" in kw else real(**kw))
        afs.upsert_month(db, *MAY)
        assert ledger(db)[0].kind == "first_year"
        db.refresh(ref)
        assert ref.first_paid_at is None and ref.year_anchor_at is None

    def test_failed_reversal_lookup_is_skipped_not_dropped(self, db, stripe_world, monkeypatch):
        aff = make_partner(db)
        make_referral(db, aff, first_paid_at=day(2026, 4, 10), year_anchor_at=day(2026, 4, 10))
        inv = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [inv]
        stripe_world.by_pi = {"pi_1": inv}
        afs.upsert_month(db, 2026, 4)
        stripe_world.refunds = [refund(8000, created=ts(2026, 5, 5))]
        real = stripe.InvoicePayment.list
        calls = {"n": 0}

        def ip_list(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise stripe.error.APIConnectionError("stripe timed out")
            return real(**kw)
        monkeypatch.setattr(stripe.InvoicePayment, "list", ip_list)
        skipped = []
        afs.compute_month(db, *MAY, skipped=skipped)
        assert [(x["source"], x["id"]) for x in skipped] == [("refund", "re_1")]
        afs.upsert_month(db, *MAY)
        assert [(l.kind, l.amount) for l in ledger(db)] == [("first_year", D("30")), ("refund", D("-30"))]


# ============================================================================
# Finding 5 - dispute won / inquiry escalated / refund failed AFTER the month
# ============================================================================

class TestReversalStatusChanges:
    def _april_sale(self, db, world):
        aff = make_partner(db)
        make_referral(db, aff, first_paid_at=day(2026, 4, 10), year_anchor_at=day(2026, 4, 10))
        inv = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        world.invoices = [inv]
        world.by_pi = {"pi_1": inv}
        afs.upsert_month(db, 2026, 4)
        return aff

    def _lines(self, db):
        return [(l.source_id, l.kind, l.amount, l.period_month.month) for l in ledger(db)]

    def test_a_dispute_that_is_later_won_gives_the_commission_back(self, db, stripe_world):
        import affiliate_admin as afa
        self._april_sale(db, stripe_world)
        dispute = {"id": "dp_1", "amount": 8000, "payment_intent": "pi_1",
                   "status": "needs_response", "created": ts(2026, 5, 9)}
        stripe_world.disputes = [dispute]
        afs.upsert_month(db, *MAY)
        assert self._lines(db)[-1] == ("dp_1", "dispute", D("-30"), 5)
        dispute["status"] = "won"
        afs.upsert_month(db, 2026, 6)
        afs.upsert_month(db, 2026, 6)                                  # idempotent
        afs.upsert_month(db, 2026, 7)                                  # ... in later months too
        assert self._lines(db) == [("in_1", "first_year", D("30"), 4),
                                   ("dp_1", "dispute", D("-30"), 5),
                                   ("dp_1:won", "dispute", D("30"), 6)]
        won = ledger(db)[-1]
        assert (won.detail["outcome"], won.stripe_reversal_id, won.stripe_invoice_id) == \
            ("won", "dp_1", "in_1")
        assert (won.basis_cents, won.net_paid_cents) == (10000, 8000)
        assert afa.line_kind_label(won) == "Chargeback won - commission restored"
        assert sum(l.amount for l in ledger(db)) == D("30")

    def test_a_dispute_won_before_it_was_ever_clawed_back_books_nothing(self, db, stripe_world):
        self._april_sale(db, stripe_world)
        stripe_world.disputes = [{"id": "dp_1", "amount": 8000, "payment_intent": "pi_1",
                                  "status": "won", "created": ts(2026, 5, 9)}]
        afs.upsert_month(db, *MAY)
        afs.upsert_month(db, 2026, 6)
        assert self._lines(db) == [("in_1", "first_year", D("30"), 4)]

    def test_an_inquiry_that_escalates_later_is_clawed_back(self, db, stripe_world):
        self._april_sale(db, stripe_world)
        dispute = {"id": "dp_1", "amount": 8000, "payment_intent": "pi_1",
                   "status": "warning_needs_response", "created": ts(2026, 5, 9)}
        stripe_world.disputes = [dispute]
        afs.upsert_month(db, *MAY)
        assert len(ledger(db)) == 1                                    # an inquiry moves no money
        dispute["status"] = "needs_response"
        afs.upsert_month(db, 2026, 6)
        afs.upsert_month(db, 2026, 6)
        assert self._lines(db)[1:] == [("dp_1", "dispute", D("-30"), 6)]
        assert afs._utc(ledger(db)[1].event_at) == day(2026, 6, 1)

    def test_a_pending_refund_that_fails_is_given_back(self, db, stripe_world):
        import affiliate_admin as afa
        self._april_sale(db, stripe_world)
        pending = refund(8000, created=ts(2026, 5, 5), status="pending")
        stripe_world.refunds = [pending]
        afs.upsert_month(db, *MAY)
        assert self._lines(db)[-1] == ("re_1", "refund", D("-30"), 5)
        pending["status"] = "failed"
        afs.upsert_month(db, 2026, 6)
        afs.upsert_month(db, 2026, 6)
        assert self._lines(db)[2:] == [("re_1:failed", "refund", D("30"), 6)]
        assert afa.line_kind_label(ledger(db)[-1]) == "Refund failed - commission restored"
        # the give-back frees the invoice: a later real refund is clawed back in full
        stripe_world.refunds.append(refund(8000, rid="re_2", created=ts(2026, 7, 3)))
        afs.upsert_month(db, 2026, 7)
        assert self._lines(db)[3:] == [("re_2", "refund", D("-30"), 7)]
        assert sum(l.amount for l in ledger(db)) == D("0")

    def test_a_refund_that_failed_before_it_was_booked_books_nothing(self, db, stripe_world):
        self._april_sale(db, stripe_world)
        stripe_world.refunds = [refund(8000, created=ts(2026, 5, 5), status="failed")]
        afs.upsert_month(db, *MAY)
        assert len(ledger(db)) == 1

    def test_an_earlier_months_booked_refund_is_not_booked_again(self, db, stripe_world):
        self._april_sale(db, stripe_world)
        stripe_world.refunds = [refund(4000, created=ts(2026, 5, 5))]
        afs.upsert_month(db, *MAY)
        afs.upsert_month(db, 2026, 6)
        assert self._lines(db)[1:] == [("re_1", "refund", D("-15"), 5)]

    def test_lookback_is_configurable(self, monkeypatch):
        import config
        assert config.AFFILIATE_REVERSAL_LOOKBACK_DAYS == 180
        assert "TW2_AFFILIATE_REVERSAL_LOOKBACK_DAYS" in open(config.__file__).read()
        seen = {}
        monkeypatch.setattr(config, "AFFILIATE_REVERSAL_LOOKBACK_DAYS", 30)
        monkeypatch.setattr(stripe.Refund, "list", lambda **kw: seen.update(kw) or FakeList([]))
        monkeypatch.setattr(stripe.Dispute, "list", lambda **kw: FakeList([]))
        start, end, _, _ = afs._month_window(*MAY)
        afs._month_reversals(start, end)
        assert seen["created"] == {"gte": ts(2026, 4, 1), "lt": ts(2026, 6, 1)}
