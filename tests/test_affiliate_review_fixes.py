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
