"""Affiliate program v2 (TW-TASK-0038) - the owner-approved rules, in dollars.

Hermetic: Stripe is monkeypatched. The pure engine (_compute) runs on
duck-typed partners / referrals; the ledger, checkout-offer and webhook
writers run against an in-memory SQLite copy of the affiliate tables (the
real schema is Postgres - the copy keeps names, uniques and types, and drops
only the Postgres-specific defaults / CHECKs).

Every row of the acceptance table in docs/tasks/TW-TASK-0038.md is asserted
in TestAcceptanceTable (pure rules) and again through the engine.
"""
import datetime as dt
import importlib
import re
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "web")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import pytest  # noqa: E402
import stripe  # noqa: E402
import affiliate_service as afs  # noqa: E402

UTC = dt.timezone.utc
AFF_ID = "11111111-1111-1111-1111-111111111111"


def D(v):
    return Decimal(str(v))


def ts(*args):
    return int(dt.datetime(*args, tzinfo=UTC).timestamp())


def day(*args):
    return dt.datetime(*args, tzinfo=UTC)


# --- fakes ------------------------------------------------------------------

def terms(**kw):
    base = dict(id=1, version="v2-5y", pool_pct=D(50), max_discount_pct=D(25),
                promo_commission_pct=D(50), renewal_pct=D(25), renewal_years=5,
                activity_rule_months=12)
    base.update(kw)
    return SimpleNamespace(**base)


LIFETIME = terms(id=3, version="v2-lifetime", renewal_years=None)
TEN_YEAR = terms(id=2, version="v2-10y", renewal_years=10)


def partner(**kw):
    base = dict(id=AFF_ID, code="ANNE", name="Anne", email="anne@example.com",
                payout_email="anne@pay.com", status="active", stripe_coupon_id="cpn_anne",
                stripe_coupon_id_monthly=None, discount_pct=D(20), terminated_for_cause=False)
    base.update(kw)
    return SimpleNamespace(**base)


def referral(sub="sub_1", *, first_paid=None, anchor=None, offer="regular", discount=D(20),
             t=None, source="checkout", customer="cus_1", aff=AFF_ID, **kw):
    return SimpleNamespace(
        id=None, affiliate_id=aff, stripe_subscription_id=sub, stripe_customer_id=customer,
        first_paid_at=first_paid, year_anchor_at=anchor if anchor is not None else first_paid,
        offer_type=offer, discount_pct=discount, terms=t, terms_id=getattr(t, "id", None),
        source=source, billing_interval=kw.get("interval"))


def invoice(iid="in_1", *, paid, list_cents=None, tax=0, sub="sub_1", customer="cus_1",
            coupon=None, paid_at, period_start=None, created=None, interval="year",
            status="paid", email="buyer@example.com"):
    """A Stripe invoice dict. `paid` is the pre-tax amount the customer paid,
    `list_cents` the pre-discount subtotal (defaults to `paid`)."""
    return {
        "id": iid, "status": status, "currency": "usd",
        "amount_paid": (paid + tax) if status == "paid" else 0,
        "subtotal": list_cents if list_cents is not None else paid,
        "total_taxes": ([{"amount": tax}] if tax else []),
        "customer": customer, "customer_email": email, "subscription": sub,
        "created": created if created is not None else paid_at,
        "status_transitions": {"paid_at": paid_at if status == "paid" else None},
        "lines": {"data": [{"period": {"start": period_start if period_start is not None else paid_at},
                            "price": {"recurring": {"interval": interval}}}]},
        "discounts": ([{"id": "di_x", "source": {"type": "coupon", "coupon": coupon}}]
                      if coupon else []),
    }


class FakeList:
    def __init__(self, items):
        self._items = list(items)

    def auto_paging_iter(self):
        return iter(self._items)


@pytest.fixture
def stripe_world(monkeypatch):
    """One mutable fake Stripe account. world.invoices = everything Stripe
    would list; world.refunds / world.disputes; payment_intent -> invoice."""
    world = SimpleNamespace(invoices=[], refunds=[], disputes=[], by_pi={}, calls=[])

    def invoice_list(**kw):
        items = world.invoices
        if "customer" in kw:
            items = [i for i in items if i["customer"] == kw["customer"]]
        if kw.get("status"):
            items = [i for i in items if i["status"] == kw["status"]]
        return FakeList(items)

    def in_window(items, kw):
        w = kw.get("created") or {}
        return [i for i in items if w.get("gte", 0) <= i["created"] < w.get("lt", 10 ** 12)]

    monkeypatch.setattr(stripe.Invoice, "list", invoice_list)
    monkeypatch.setattr(stripe.Refund, "list", lambda **kw: FakeList(in_window(world.refunds, kw)))
    monkeypatch.setattr(stripe.Dispute, "list", lambda **kw: FakeList(in_window(world.disputes, kw)))

    def ip_list(**kw):
        inv = world.by_pi.get(kw["payment"]["payment_intent"])
        return FakeList([{"invoice": inv["id"]}] if inv else [])
    monkeypatch.setattr(stripe.InvoicePayment, "list", ip_list)
    monkeypatch.setattr(stripe.Invoice, "retrieve",
                        lambda iid, **kw: {i["id"]: i for i in world.invoices}[iid])
    return world


def refund(amount, inv_pi="pi_1", rid="re_1", created=None, status="succeeded"):
    return {"id": rid, "amount": amount, "payment_intent": inv_pi, "charge": "ch_1",
            "status": status, "created": created}


def total(rows):
    return sum((r["commission_amount"] for r in rows), Decimal("0.00"))


def lines_of(rows):
    return [ln for r in rows for ln in r["detail"]]


# ============================================================================
# 1. The acceptance table - pure rules (what the UI previews)
# ============================================================================

class TestAcceptanceTable:
    @pytest.mark.parametrize("discount,pays,earns,retains", [
        (0, 10000, 5000, 5000),      # Referral 0% off, $100
        (5, 9500, 4500, 5000),       # Referral 5% off
        (20, 8000, 3000, 5000),      # Referral 20% off
        (25, 7500, 2500, 5000),      # the cap
    ])
    def test_pool_rule(self, discount, pays, earns, retains):
        p = afs.preview_offer(10000, discount)
        assert (p["customer_pays_cents"], p["partner_earns_cents"], p["retained_cents"]) == \
            (pays, earns, retains)

    def test_discount_cap_is_25(self):
        with pytest.raises(afs.AffiliateError):
            afs.preview_offer(10000, 26)
        with pytest.raises(afs.AffiliateError):
            afs.preview_offer(10000, -1)
        assert afs.clamp_discount(40) == D(25)

    @pytest.mark.parametrize("price,earns,retains", [
        (9900, 4950, 4950),          # Referred $99 promo
        (5000, 2500, 2500),          # Referred $50 promo
    ])
    def test_promo_rule(self, price, earns, retains):
        p = afs.preview_promo(price, 39900)
        assert (p["customer_pays_cents"], p["partner_earns_cents"], p["retained_cents"]) == \
            (price, earns, retains)

    def test_renewal_rule(self):
        p = afs.preview_renewal(39900)                 # $399 renewal years 2-5
        assert (p["partner_earns_cents"], p["retained_cents"]) == (9975, 29925)
        assert afs.preview_renewal(18900)["partner_earns_cents"] == 4725   # founder at $189

    def test_renewal_schedule(self):
        five = afs.renewal_schedule(terms())
        assert (five["first_year"], five["last_year"], five["annual_renewals_paid"]) == (2, 5, 4)
        assert (five["monthly_first_month"], five["monthly_last_month"]) == (13, 60)
        assert afs.renewal_schedule(TEN_YEAR)["annual_renewals_paid"] == 9
        life = afs.renewal_schedule(LIFETIME)
        assert life["lifetime"] and life["last_year"] is None and life["monthly_last_month"] is None
        assert "—" not in five["label"] + life["label"]


# ============================================================================
# 2. The acceptance table - through the engine
# ============================================================================

MAY = (2026, 5)
PAID_MAY = ts(2026, 5, 15)


class TestEngineAcceptance:
    def test_direct_sale_pays_nothing(self, stripe_world):
        stripe_world.invoices = [invoice(paid=10000, paid_at=PAID_MAY, sub="sub_direct")]
        assert afs._compute([partner()], *MAY) == []

    @pytest.mark.parametrize("discount,paid,earns", [(0, 10000, "50.00"), (5, 9500, "45.00"),
                                                     (20, 8000, "30.00")])
    def test_referral_pool_rule(self, stripe_world, discount, paid, earns):
        stripe_world.invoices = [invoice(paid=paid, list_cents=10000, paid_at=PAID_MAY)]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(discount=D(discount))})
        assert total(rows) == D(earns)
        assert rows[0]["gross_revenue"] == D(paid) / 100
        ln = rows[0]["detail"][0]
        assert (ln["kind"], ln["year_number"], ln["basis"]) == ("first_year", 1, "100.00")
        # TradeWave always retains 50% of list
        assert D(paid) / 100 - total(rows) == D("50.00")

    def test_tax_is_not_commissionable(self, stripe_world):
        # $100 at 0% off + $8 tax: customer pays $108, partner earns $50
        stripe_world.invoices = [invoice(paid=10000, tax=800, paid_at=PAID_MAY)]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(discount=D(0))})
        assert total(rows) == D("50.00")
        assert rows[0]["detail"][0]["amount_paid_cents"] == 10800

    def test_direct_promo_sale_pays_nothing(self, stripe_world):
        stripe_world.invoices = [invoice(paid=9900, list_cents=39900, paid_at=PAID_MAY,
                                         coupon="cpn_campaign", sub="sub_direct")]
        assert afs._compute([partner()], *MAY) == []

    @pytest.mark.parametrize("paid,earns", [(9900, "49.50"), (5000, "25.00")])
    def test_referred_promo_sale(self, stripe_world, paid, earns):
        stripe_world.invoices = [invoice(paid=paid, list_cents=39900, paid_at=PAID_MAY,
                                         coupon="cpn_campaign")]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(offer="promo", discount=D(0))})
        assert total(rows) == D(earns)
        assert rows[0]["detail"][0]["kind"] == "promo"

    def _renewal(self, world, year, t=None, active=True, paid=39900):
        """An annual renewal invoice paid at the start of commission `year`."""
        anchor = day(2020, 5, 15)
        at = day(2020 + year - 1, 5, 15)
        world.invoices = [invoice(paid=paid, paid_at=int(at.timestamp()))]
        refs = {"sub_1": referral(first_paid=anchor, t=t)}
        if active:      # a NEW paying customer 3 months before the renewal
            recent = afs._add_months(at, -3)
            refs["sub_new"] = referral("sub_new", first_paid=recent, t=t, customer="cus_new")
        return afs._compute([partner()], at.year, at.month, refs)

    @pytest.mark.parametrize("year", [2, 3, 4, 5])
    def test_renewal_years_2_to_5(self, stripe_world, year):
        rows = self._renewal(stripe_world, year)
        assert total(rows) == D("99.75")
        ln = rows[0]["detail"][0]
        assert (ln["kind"], ln["year_number"], D(ln["rate_pct"])) == ("renewal", year, D(25))

    @pytest.mark.parametrize("year", [6, 7, 12])
    def test_renewal_year_6_plus_pays_nothing_on_5_year_terms(self, stripe_world, year):
        assert self._renewal(stripe_world, year) == []

    def test_annual_plan_has_exactly_4_paid_renewals_on_5_year_terms(self, stripe_world):
        earned = [total(self._renewal(stripe_world, y)) for y in range(2, 9)]
        assert earned == [D("99.75")] * 4 + [D("0.00")] * 3

    @pytest.mark.parametrize("year", [6, 11, 25])
    def test_lifetime_terms_keep_paying(self, stripe_world, year):
        assert total(self._renewal(stripe_world, year, t=LIFETIME)) == D("99.75")

    def test_ten_year_terms(self, stripe_world):
        assert total(self._renewal(stripe_world, 10, t=TEN_YEAR)) == D("99.75")
        assert self._renewal(stripe_world, 11, t=TEN_YEAR) == []

    @pytest.mark.parametrize("t", [None, LIFETIME])
    def test_inactive_partner_renewal_is_lapsed(self, stripe_world, t):
        rows = self._renewal(stripe_world, 3, t=t, active=False)
        assert total(rows) == D("0.00")
        ln = rows[0]["detail"][0]
        assert (ln["kind"], ln["state"], ln["commission"]) == ("lapsed", "lapsed", "0.00")
        assert ln["forfeited"] == "99.75" and rows[0]["lapsed_count"] == 1

    def test_founder_renewal_pays_on_what_was_paid(self, stripe_world):
        assert total(self._renewal(stripe_world, 2, paid=18900)) == D("47.25")

    def _sale_and_refund(self, world, refund_cents):
        inv = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        world.invoices = [inv]
        world.by_pi = {"pi_1": inv}
        world.refunds = [refund(refund_cents, created=ts(2026, 5, 20))]
        return afs._compute([partner()], *MAY, {"sub_1": referral()})

    def test_full_refund_of_the_80_sale(self, stripe_world):
        rows = self._sale_and_refund(stripe_world, 8000)
        assert total(rows) == D("-30.00")
        assert rows[0]["gross_revenue"] == D("-80.00")
        ln = rows[0]["detail"][0]
        assert (ln["kind"], ln["reverses_kind"], D(ln["rate_pct"])) == ("refund", "first_year", D(30))

    def test_partial_refund_of_the_80_sale(self, stripe_world):
        rows = self._sale_and_refund(stripe_world, 4000)
        assert total(rows) == D("-15.00")
        assert rows[0]["gross_revenue"] == D("-40.00")

    def test_refunds_never_take_back_more_than_was_earned(self, stripe_world):
        inv = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [inv]
        stripe_world.by_pi = {"pi_1": inv}
        stripe_world.refunds = [refund(6000, rid="re_1", created=ts(2026, 5, 2)),
                                refund(6000, rid="re_2", created=ts(2026, 5, 3))]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral()})
        assert total(rows) == D("-30.00")              # 22.50 + the remaining 7.50

    def test_refund_of_a_promo_sale_uses_the_promo_formula(self, stripe_world):
        inv = invoice(paid=9900, list_cents=39900, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [inv]
        stripe_world.by_pi = {"pi_1": inv}
        stripe_world.refunds = [refund(9900, created=ts(2026, 5, 20))]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(offer="promo")})
        assert total(rows) == D("-49.50")

    def test_dispute_reverses_like_a_refund(self, stripe_world):
        inv = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [inv]
        stripe_world.by_pi = {"pi_1": inv}
        stripe_world.disputes = [{"id": "dp_1", "amount": 8000, "payment_intent": "pi_1",
                                  "status": "lost", "created": ts(2026, 5, 9)}]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral()})
        assert total(rows) == D("-30.00") and rows[0]["detail"][0]["kind"] == "dispute"


# ============================================================================
# 3. Year placement, activity rule, clocks
# ============================================================================

class TestYearPlacement:
    ANCHOR = day(2021, 1, 31)       # month-end anchor: Feb is the 28th, Mar the 31st

    @pytest.mark.parametrize("months,expected", [
        (0, 1), (11, 1), (12, 2), (13, 2), (59, 5), (60, 6), (61, 6),
    ])
    def test_year_number(self, months, expected):
        assert afs.year_number(self.ANCHOR, afs._add_months(self.ANCHOR, months)) == expected

    def test_month_end_anchor_walks_like_stripe(self):
        assert afs._add_months(self.ANCHOR, 1) == day(2021, 2, 28)
        assert afs._add_months(self.ANCHOR, 2) == day(2021, 3, 31)
        assert afs.months_since_anchor(self.ANCHOR, day(2021, 2, 28)) == 1

    def _monthly(self, world, month_no, t=None):
        """Monthly plan, $50 list. Invoice for service month `month_no`."""
        anchor = day(2021, 1, 15)
        at = afs._add_months(anchor, month_no - 1)
        world.invoices = [invoice(paid=5000, paid_at=int(at.timestamp()), interval="month")]
        refs = {"sub_1": referral(first_paid=anchor, discount=D(0), t=t),
                "sub_new": referral("sub_new", first_paid=afs._add_months(at, -1), t=t,
                                    customer="cus_new")}
        return afs._compute([partner()], at.year, at.month, refs)

    def test_monthly_month_12_is_still_first_year(self, stripe_world):
        rows = self._monthly(stripe_world, 12)
        assert total(rows) == D("25.00") and rows[0]["detail"][0]["kind"] == "first_year"

    def test_monthly_month_13_is_the_first_renewal(self, stripe_world):
        rows = self._monthly(stripe_world, 13)
        assert total(rows) == D("12.50") and rows[0]["detail"][0]["kind"] == "renewal"

    def test_monthly_month_60_is_the_last_paid_renewal(self, stripe_world):
        rows = self._monthly(stripe_world, 60)
        assert total(rows) == D("12.50") and rows[0]["detail"][0]["year_number"] == 5

    def test_monthly_month_61_pays_nothing(self, stripe_world):
        assert self._monthly(stripe_world, 61) == []
        assert total(self._monthly(stripe_world, 61, t=LIFETIME)) == D("12.50")

    def test_service_period_not_invoice_date_places_the_payment(self, stripe_world):
        # Month-12 service billed and paid LATE, after the anniversary: still year 1.
        anchor = day(2025, 5, 1)
        stripe_world.invoices = [invoice(paid=5000, interval="month",
                                         period_start=ts(2026, 4, 1), created=ts(2026, 4, 1),
                                         paid_at=ts(2026, 5, 20))]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(first_paid=anchor, discount=D(0))})
        assert rows[0]["detail"][0]["kind"] == "first_year" and total(rows) == D("25.00")


class TestActivityRule:
    def test_lapse_then_resume(self, stripe_world):
        """No new paying customer for 12+ months -> renewals lapse ($0, never
        paid later); the next new paying customer resumes them."""
        old = day(2023, 1, 10)
        refs = {"sub_1": referral(first_paid=old, interval="month")}
        aff = partner()

        def renewal_in(year, month):
            at = ts(year, month, 10)
            stripe_world.invoices = [invoice(f"in_{year}_{month}", paid=5000, paid_at=at,
                                             interval="month")]
            return afs._compute([aff], year, month, refs)

        lapsed = renewal_in(2025, 3)
        assert total(lapsed) == D("0.00") and lines_of(lapsed)[0]["kind"] == "lapsed"
        refs["sub_new"] = referral("sub_new", first_paid=day(2025, 4, 2), customer="cus_new")
        resumed = renewal_in(2025, 5)
        assert total(resumed) == D("12.50") and lines_of(resumed)[0]["kind"] == "renewal"
        # ... and 12 months after that customer, it lapses again
        assert lines_of(renewal_in(2026, 5))[0]["kind"] == "lapsed"

    def test_first_year_commission_ignores_the_activity_rule(self, stripe_world):
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(first_paid=day(2026, 5, 15))})
        assert total(rows) == D("30.00")

    def test_new_customer_earlier_in_the_same_month_counts(self, stripe_world):
        stripe_world.invoices = [
            invoice("in_renew", paid=39900, paid_at=ts(2026, 5, 20)),
            invoice("in_new", paid=10000, paid_at=ts(2026, 5, 3), sub="sub_new", customer="cus_new"),
        ]
        refs = {"sub_1": referral(first_paid=day(2024, 5, 20)),
                "sub_new": referral("sub_new", discount=D(0), customer="cus_new")}  # clock not stamped yet
        rows = afs._compute([partner()], *MAY, refs)
        kinds = {ln["invoice"]: ln["kind"] for ln in lines_of(rows)}
        assert kinds == {"in_new": "first_year", "in_renew": "renewal"}
        assert total(rows) == D("50.00") + D("99.75")

    def test_a_trial_does_not_make_the_partner_active(self, stripe_world):
        # the "new customer" only has a $0 trial invoice -> no first payment
        stripe_world.invoices = [
            invoice("in_renew", paid=39900, paid_at=ts(2026, 5, 20)),
            invoice("in_trial", paid=0, paid_at=ts(2026, 5, 3), sub="sub_new", customer="cus_new"),
        ]
        refs = {"sub_1": referral(first_paid=day(2024, 5, 20)),
                "sub_new": referral("sub_new", customer="cus_new")}
        rows = afs._compute([partner()], *MAY, refs)
        assert [ln["kind"] for ln in lines_of(rows)] == ["lapsed"]

    def test_activity_status_helper(self):
        aff = partner()
        now = day(2026, 5, 1)
        st = afs.activity_status(aff, now, first_paid_dates=[day(2025, 9, 10), day(2025, 1, 1)])
        assert st["active"] and st["active_until"] == dt.date(2026, 9, 10)
        st = afs.activity_status(aff, now, first_paid_dates=[day(2025, 1, 1)])
        assert not st["active"] and st["lapsed_since"] == dt.date(2026, 1, 1)
        st = afs.activity_status(aff, now, first_paid_dates=[])
        assert not st["active"] and st["last_new_customer_at"] is None


class TestCommissionClock:
    def test_trial_invoice_does_not_start_the_clock(self, stripe_world):
        """Trial ($0) invoice in Dec 2025, first REAL payment 15 Jan 2026. The
        Dec 2026 service month is month 12 (first year); it would be month 13
        (a renewal) if the trial had started the clock."""
        trial = invoice("in_trial", paid=0, paid_at=ts(2025, 12, 15), interval="month")
        first = invoice("in_first", paid=5000, paid_at=ts(2026, 1, 15), interval="month")
        dec = invoice("in_dec", paid=5000, paid_at=ts(2026, 12, 15), interval="month")
        stripe_world.invoices = [trial, first, dec]
        found = afs._first_paid_invoice("cus_1", subscription_id="sub_1")
        assert found["invoice"] == "in_first" and found["service_start"] == day(2026, 1, 15)
        discovered = {}
        rows = afs._compute([partner()], 2026, 12, {"sub_1": referral(discount=D(0))},
                            discovered=discovered)
        assert [ln["kind"] for ln in lines_of(rows)] == ["first_year"]
        assert discovered["sub_1"]["year_anchor_at"] == day(2026, 1, 15)

    def test_trial_invoice_earns_nothing(self, stripe_world):
        stripe_world.invoices = [invoice(paid=0, paid_at=PAID_MAY)]
        assert afs._compute([partner()], *MAY, {"sub_1": referral()}) == []

    def test_failed_payment_earns_nothing_and_does_not_start_the_clock(self, stripe_world):
        failed = invoice("in_failed", paid=5000, paid_at=ts(2026, 4, 15), status="open")
        stripe_world.invoices = [failed]
        assert afs._compute([partner()], 2026, 4, {"sub_1": referral()}) == []
        assert afs._first_paid_invoice("cus_1", subscription_id="sub_1") is None

    def test_late_paid_invoice_is_counted_in_the_month_it_was_paid(self, stripe_world):
        late = invoice("in_late", paid=8000, list_cents=10000,
                       created=ts(2026, 3, 28), period_start=ts(2026, 3, 28), paid_at=ts(2026, 5, 4))
        stripe_world.invoices = [late]
        refs = {"sub_1": referral()}
        assert afs._compute([partner()], 2026, 3, refs) == []
        assert afs._compute([partner()], 2026, 4, refs) == []
        assert total(afs._compute([partner()], 2026, 5, refs)) == D("30.00")

    def test_extra_discount_never_stacks(self, stripe_world):
        """Stamped 0% off, but a 50% coupon got onto the invoice: the partner
        is paid the promo rule on what was paid ($25), not $50 of pool."""
        stripe_world.invoices = [invoice(paid=5000, list_cents=10000, paid_at=PAID_MAY)]
        rows = afs._compute([partner()], *MAY, {"sub_1": referral(discount=D(0))})
        assert total(rows) == D("25.00") and rows[0]["detail"][0]["guard"] == "extra_discount"

    def test_terms_come_from_the_referral_not_the_partner(self, stripe_world):
        """Changing the partner's terms or discount never re-prices a customer
        who checked out before the change."""
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        ref = referral(discount=D(20), t=terms())
        changed = partner(discount_pct=D(0), terms=terms(id=9, pool_pct=D(40)))
        assert total(afs._compute([changed], *MAY, {"sub_1": ref})) == D("30.00")

    def test_self_referral_is_never_paid(self, stripe_world):
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY,
                                         email="anne@example.com")]
        assert afs._compute([partner()], *MAY, {"sub_1": referral()}) == []


class TestPartnerStatus:
    def _rows(self, world, **kw):
        world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        return afs._compute([partner(**kw)], *MAY, {"sub_1": referral()})

    def test_paused_partner_commission_is_held(self, stripe_world):
        rows = self._rows(stripe_world, status="paused")
        assert rows[0]["commission_amount"] == D("0.00") and rows[0]["held_amount"] == D("30.00")
        ln = rows[0]["detail"][0]
        assert (ln["state"], ln["hold_reason"], ln["commission"]) == ("held", "paused", "30.00")

    def test_terminated_for_cause_forfeits(self, stripe_world):
        rows = self._rows(stripe_world, status="terminated", terminated_for_cause=True)
        assert rows[0]["commission_amount"] == D("0.00") and rows[0]["held_amount"] == D("0.00")
        assert rows[0]["detail"][0]["state"] == "void"

    def test_plain_termination_holds_for_review(self, stripe_world):
        rows = self._rows(stripe_world, status="terminated")
        assert rows[0]["detail"][0]["hold_reason"] == "terminated"
        assert rows[0]["held_amount"] == D("30.00")


# ============================================================================
# 4. Ledger, checkout offer, webhook writers - SQLite copy of the schema
# ============================================================================

@pytest.fixture
def db():
    import models
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker

    names = ["affiliate_terms", "affiliates", "affiliate_referrals", "affiliate_payouts",
             "affiliate_commission_lines", "affiliate_discount_changes", "promo_campaigns",
             "audit_log"]
    md = sa.MetaData()
    for name in names:
        src = models.Base.metadata.tables[name]
        cols = []
        for c in src.columns:
            ctype = c.type
            tname = type(ctype).__name__
            if tname == "JSONB":
                ctype = sa.JSON()
            elif tname == "UUID":
                ctype = sa.Uuid()
            elif c.primary_key and isinstance(ctype, sa.BigInteger):
                ctype = sa.Integer()
            default = None
            if c.server_default is not None:
                arg = str(getattr(c.server_default.arg, "text", c.server_default.arg))
                if "now" in arg:
                    default = sa.text("CURRENT_TIMESTAMP")
                elif "(" not in arg:
                    default = sa.text(arg)
            cols.append(sa.Column(c.name, ctype, primary_key=c.primary_key, nullable=c.nullable,
                                  unique=bool(c.unique), server_default=default))
        uniques = [sa.UniqueConstraint(*[col.name for col in con.columns], name=con.name)
                   for con in src.constraints
                   if isinstance(con, sa.UniqueConstraint) and len(con.columns) > 1]
        sa.Table(name, md, *cols, *uniques)
    engine = sa.create_engine("sqlite://")
    md.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    session.factory = sessionmaker(bind=engine, future=True)
    t5 = models.AffiliateTerms(id=1, version="v2-5y", renewal_years=5)
    t10 = models.AffiliateTerms(id=2, version="v2-10y", renewal_years=10)
    tl = models.AffiliateTerms(id=3, version="v2-lifetime", renewal_years=None)
    session.add_all([t5, t10, tl])
    session.commit()
    yield session
    session.close()
    engine.dispose()


def make_partner(db, code="ANNE", **kw):
    import models
    base = dict(id=uuid.uuid4(), code=code, name=code.title(), email=code.lower() + "@example.com",
                discount_pct=D(20), commission_pct=D(30), status="active", terms_id=1,
                stripe_coupon_id="cpn_" + code.lower(), stripe_promotion_code_id="promo_" + code.lower(),
                commission_model="recurring", agreement_token_version=0, terminated_for_cause=False)
    base.update(kw)
    aff = models.Affiliate(**base)
    db.add(aff)
    db.commit()
    return aff


def make_referral(db, aff, sub="sub_1", customer="cus_1", **kw):
    import models
    base = dict(id=uuid.uuid4(), affiliate_id=aff.id, stripe_subscription_id=sub,
                stripe_customer_id=customer, source="checkout", terms_id=1, offer_type="regular",
                discount_pct=D(20), billing_interval="year", list_price_cents=10000,
                attributed_at=day(2026, 1, 1))
    base.update(kw)
    ref = models.AffiliateReferral(**base)
    db.add(ref)
    db.commit()
    return ref


def payout_for(db, aff, period):
    import models
    return (db.query(models.AffiliatePayout)
            .filter(models.AffiliatePayout.affiliate_id == aff.id,
                    models.AffiliatePayout.period_start == period).first())


def ledger(db):
    import models
    return db.query(models.AffiliateCommissionLine).order_by(models.AffiliateCommissionLine.id).all()


def cents(v):
    return Decimal(str(v)).quantize(Decimal("0.01"))


class TestLedger:
    def test_rerun_is_idempotent(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        for _ in range(3):
            afs.upsert_month(db, *MAY)
        assert len(ledger(db)) == 1
        p = payout_for(db, aff, dt.date(2026, 5, 1))
        assert cents(p.commission_amount) == D("30.00") and cents(p.gross_revenue) == D("80.00")
        line = ledger(db)[0]
        assert (line.kind, line.state, line.source_id, line.year_number) == \
            ("first_year", "pending", "in_1", 1)
        assert line.payout_id == p.id and line.payable_month == dt.date(2026, 5, 1)

    def test_clock_is_persisted_on_the_referral(self, db, stripe_world):
        aff = make_partner(db)
        ref = make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        db.refresh(ref)
        assert afs._utc(ref.first_paid_at) == day(2026, 5, 15)
        assert afs._utc(ref.year_anchor_at) == day(2026, 5, 15)

    def test_a_line_is_never_repriced(self, db, stripe_world):
        """After the line is booked, the partner's discount, terms and even the
        referral snapshot change - the booked line and payout do not."""
        aff = make_partner(db)
        ref = make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        aff.discount_pct = D(0)
        aff.terms_id = 3
        ref.discount_pct = D(0)
        db.commit()
        afs.upsert_month(db, *MAY)
        assert cents(ledger(db)[0].amount) == D("30.00")
        assert cents(payout_for(db, aff, dt.date(2026, 5, 1)).commission_amount) == D("30.00")
        preview = afs.compute_month(db, *MAY)
        assert total(preview) == D("30.00") and lines_of(preview)[0]["persisted"]

    def test_late_paid_invoice_is_booked_once(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        stripe_world.invoices = [invoice("in_late", paid=8000, list_cents=10000,
                                         created=ts(2026, 3, 28), paid_at=ts(2026, 5, 4))]
        for month in (3, 4, 5, 6):
            afs.upsert_month(db, 2026, month)
        assert [(l.source_id, l.period_month) for l in ledger(db)] == [("in_late", dt.date(2026, 5, 1))]
        assert payout_for(db, aff, dt.date(2026, 4, 1)) is None
        assert payout_for(db, aff, dt.date(2026, 6, 1)) is None
        assert cents(payout_for(db, aff, dt.date(2026, 5, 1)).commission_amount) == D("30.00")

    def test_new_invoice_is_added_on_rerun_without_touching_the_first(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        make_referral(db, aff, sub="sub_2", customer="cus_2", discount_pct=D(0))
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        stripe_world.invoices.append(invoice("in_2", paid=10000, paid_at=ts(2026, 5, 28),
                                             sub="sub_2", customer="cus_2"))
        afs.upsert_month(db, *MAY)
        assert [l.source_id for l in ledger(db)] == ["in_1", "in_2"]
        assert cents(payout_for(db, aff, dt.date(2026, 5, 1)).commission_amount) == D("80.00")

    def test_paused_is_held_then_paid_when_unpaused(self, db, stripe_world):
        aff = make_partner(db, status="paused")
        make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        line = ledger(db)[0]
        assert (line.state, line.hold_reason, line.payable_month) == ("held", "paused", None)
        assert cents(line.amount) == D("30.00")
        assert payout_for(db, aff, dt.date(2026, 5, 1)) is None       # nothing payable yet
        aff.status = "active"
        db.commit()
        afs.upsert_month(db, 2026, 6)
        db.refresh(line)
        assert (line.state, line.hold_reason, line.payable_month) == ("pending", None, dt.date(2026, 6, 1))
        assert line.period_month == dt.date(2026, 5, 1)                # still EARNED in May
        assert cents(payout_for(db, aff, dt.date(2026, 6, 1)).commission_amount) == D("30.00")
        afs.upsert_month(db, 2026, 7)                                  # not paid twice
        assert payout_for(db, aff, dt.date(2026, 7, 1)) is None

    def test_termination_for_cause_forfeits_held_lines(self, db, stripe_world):
        aff = make_partner(db, status="paused")
        make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        afs.terminate_for_cause(db, aff, "fraudulent self-dealing", actor="admin:test")
        afs.upsert_month(db, 2026, 6)
        line = ledger(db)[0]
        assert (line.state, line.hold_reason) == ("void", "terminated_for_cause")
        assert payout_for(db, aff, dt.date(2026, 6, 1)) is None
        with pytest.raises(afs.AffiliateError):
            afs.terminate_for_cause(db, aff, "  ")

    def test_refund_reverses_the_booked_line_at_its_original_rate(self, db, stripe_world):
        """Sale booked in April at 20% off. In May the partner moves to 0% off
        and a $40 partial refund arrives: -$15 (the ORIGINAL 30% of list)."""
        aff = make_partner(db)
        make_referral(db, aff)
        sale = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [sale]
        stripe_world.by_pi = {"pi_1": sale}
        afs.upsert_month(db, 2026, 4)
        # April is paid out, so May stands alone (an unpaid April below the
        # $50 payout minimum would be carried into May instead).
        payout_for(db, aff, dt.date(2026, 4, 1)).status = "paid"
        aff.discount_pct = D(0)
        db.commit()
        stripe_world.refunds = [refund(4000, created=ts(2026, 5, 20))]
        afs.upsert_month(db, *MAY)
        afs.upsert_month(db, *MAY)
        rows = ledger(db)
        assert [(l.kind, l.source_id) for l in rows] == [("first_year", "in_1"), ("refund", "re_1")]
        assert cents(rows[1].amount) == D("-15.00") and rows[1].stripe_invoice_id == "in_1"
        assert cents(payout_for(db, aff, dt.date(2026, 5, 1)).commission_amount) == D("-15.00")

    def test_paid_payout_freezes_and_new_lines_roll_forward(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        make_referral(db, aff, sub="sub_2", customer="cus_2", discount_pct=D(0))
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        afs.upsert_month(db, *MAY)
        p = payout_for(db, aff, dt.date(2026, 5, 1))
        p.status = "paid"
        db.commit()
        # an invoice paid in May surfaces after May was already paid out
        stripe_world.invoices.append(invoice("in_2", paid=10000, paid_at=ts(2026, 5, 30),
                                             sub="sub_2", customer="cus_2"))
        afs.upsert_month(db, *MAY)
        db.refresh(p)
        assert cents(p.commission_amount) == D("30.00")                # frozen
        first, late = ledger(db)
        assert first.state == "paid" and late.payable_month is None
        afs.upsert_month(db, 2026, 6)
        db.refresh(late)
        assert late.payable_month == dt.date(2026, 6, 1)
        assert cents(payout_for(db, aff, dt.date(2026, 6, 1)).commission_amount) == D("50.00")

    def test_negative_month_is_carried_forward(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        make_referral(db, aff, sub="sub_2", customer="cus_2", discount_pct=D(0))
        sale = invoice(paid=8000, list_cents=10000, paid_at=ts(2026, 4, 10))
        stripe_world.invoices = [sale]
        stripe_world.by_pi = {"pi_1": sale}
        afs.upsert_month(db, 2026, 4)
        april = payout_for(db, aff, dt.date(2026, 4, 1))
        april.status = "paid"
        db.commit()
        stripe_world.refunds = [refund(8000, created=ts(2026, 5, 20))]
        afs.upsert_month(db, *MAY)
        assert cents(payout_for(db, aff, dt.date(2026, 5, 1)).commission_amount) == D("-30.00")
        stripe_world.invoices.append(invoice("in_2", paid=10000, paid_at=ts(2026, 6, 5),
                                             sub="sub_2", customer="cus_2"))
        afs.upsert_month(db, 2026, 6)
        june = payout_for(db, aff, dt.date(2026, 6, 1))
        assert cents(june.commission_amount) == D("20.00")             # $50 - the $30 owed
        assert payout_for(db, aff, dt.date(2026, 5, 1)).status == "void"

    def test_portal_estimate_uses_the_same_engine(self, db, stripe_world):
        aff = make_partner(db)
        make_referral(db, aff)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        est = afs.compute_for_affiliate(db, aff, *MAY)
        assert total(est) == D("30.00") and est[0]["lines"][0]["kind"] == "first_year"
        assert ledger(db) == []                                        # an estimate writes nothing
        assert total(afs.compute_month(db, *MAY)) == total(est)


class TestTermsAndDiscount:
    def test_terms_are_versioned_and_assigned_prospectively(self, db):
        aff = make_partner(db)
        ref = make_referral(db, aff)
        new = afs.create_terms(db, "v3-test", renewal_years=None, renewal_pct=20)
        assert [t.version for t in afs.list_terms(db)] == ["v2-5y", "v2-10y", "v2-lifetime", "v3-test"]
        with pytest.raises(afs.AffiliateError):
            afs.create_terms(db, "v3-test")
        with pytest.raises(afs.AffiliateError):
            afs.create_terms(db, "bad", max_discount_pct=60)
        afs.assign_terms(db, aff, new.id, actor="admin:test")
        assert aff.terms_id == new.id and ref.terms_id == 1            # the old referral keeps v2-5y
        assert afs.get_terms(db).version == "v2-5y"
        assert not hasattr(afs, "update_terms")

    def _stripe(self, monkeypatch):
        calls = []
        n = iter(range(1, 100))

        def coupon_create(**kw):
            calls.append(("coupon.create", kw))
            return SimpleNamespace(id="cpn_new%d" % next(n))

        def promo_create(**kw):
            calls.append(("promo.create", kw))
            return SimpleNamespace(id="promo_new%d" % next(n))
        monkeypatch.setattr(stripe.Coupon, "create", coupon_create)
        monkeypatch.setattr(stripe.Coupon, "delete", lambda cid: calls.append(("coupon.delete", cid)))
        monkeypatch.setattr(stripe.PromotionCode, "create", promo_create)
        monkeypatch.setattr(stripe.PromotionCode, "modify",
                            lambda pid, **kw: calls.append(("promo.modify", pid, kw)))
        return calls

    def test_self_serve_discount_change(self, db, monkeypatch):
        import models
        calls = self._stripe(monkeypatch)
        aff = make_partner(db)
        signed = day(2026, 1, 1)
        aff.agreement_signed_at = signed
        db.commit()
        now = day(2026, 5, 1, 12)
        change = afs.set_partner_discount(db, aff, 10, actor="partner:u1", now=now)
        assert (cents(change.old_pct), cents(change.new_pct), change.billing_interval) == \
            (D("20.00"), D("10.00"), "year")
        assert cents(aff.discount_pct) == D("10.00") and aff.stripe_coupon_id.startswith("cpn_new")
        # no pause, no re-sign
        assert aff.status == "active" and afs._utc(aff.agreement_signed_at) == signed
        # the same code string is re-pointed at a 10% coupon
        assert [c for c in calls if c[0] == "coupon.create"][0][1]["percent_off"] == 10.0
        assert ("promo.modify", "promo_anne", {"active": False}) in calls
        assert db.query(models.AffiliateDiscountChange).count() == 1
        # one change per 24 hours
        with pytest.raises(afs.AffiliateError, match="once every 24 hours"):
            afs.set_partner_discount(db, aff, 15, now=now + dt.timedelta(hours=23))
        assert afs.next_discount_change_at(aff, now + dt.timedelta(hours=1)) == now + dt.timedelta(hours=24)
        afs.set_partner_discount(db, aff, 15, now=now + dt.timedelta(hours=24, minutes=1))
        assert [cents(c.new_pct) for c in afs.discount_history(db, aff)] == [D("15.00"), D("10.00")]

    def test_discount_range_is_0_to_25(self, db, monkeypatch):
        calls = self._stripe(monkeypatch)
        aff = make_partner(db)
        for bad in (26, -1, "abc"):
            with pytest.raises(afs.AffiliateError):
                afs.set_partner_discount(db, aff, bad)
        with pytest.raises(afs.AffiliateError, match="No change"):
            afs.set_partner_discount(db, aff, 20)
        assert calls == []
        afs.set_partner_discount(db, aff, 25)
        assert cents(aff.discount_pct) == D("25.00")

    def test_zero_discount_removes_the_coupon(self, db, monkeypatch):
        calls = self._stripe(monkeypatch)
        aff = make_partner(db)
        afs.set_partner_discount(db, aff, 0)
        assert aff.stripe_coupon_id is None and aff.stripe_promotion_code_id is None
        assert calls == [("promo.modify", "promo_anne", {"active": False})]

    def test_existing_customers_keep_their_terms_after_a_change(self, db, monkeypatch, stripe_world):
        self._stripe(monkeypatch)
        aff = make_partner(db)
        make_referral(db, aff)                                         # checked out at 20% off
        afs.set_partner_discount(db, aff, 5)
        stripe_world.invoices = [invoice(paid=8000, list_cents=10000, paid_at=PAID_MAY)]
        assert total(afs.compute_month(db, *MAY)) == D("30.00")        # not 45


CATALOG = {
    ("analyst", "year"): {"price_id": "price_ay", "product_id": "prod_ay", "list_price_cents": 39900},
    ("analyst", "month"): {"price_id": "price_am", "product_id": "prod_am", "list_price_cents": 4900},
    ("navigator", "year"): {"price_id": "price_ny", "product_id": "prod_ny", "list_price_cents": 19900},
}
NOW = day(2026, 11, 24, 12)


@pytest.fixture
def campaign_stripe(monkeypatch):
    created = []

    def coupon_create(**kw):
        created.append(kw)
        return SimpleNamespace(id="cpn_camp%d" % len(created))
    monkeypatch.setattr(stripe.Coupon, "create", coupon_create)
    monkeypatch.setattr(stripe.Coupon, "delete", lambda cid: None)
    return created


def make_campaign(db, **kw):
    base = dict(name="Black Friday 2026", tiers=["analyst"], intervals=["yearly", "monthly"],
                starts_at=day(2026, 11, 20), ends_at=day(2099, 12, 1), offer_type="price",
                intro_prices={"analyst:year": 9900, "analyst:month": 1900}, catalog=CATALOG)
    base.update(kw)
    return afs.create_campaign(db, **base)


class TestCampaigns:
    def test_create_provisions_one_coupon_per_plan(self, db, campaign_stripe):
        c = make_campaign(db)
        assert c.code == "BLACK-FRIDAY-2026" and c.status == "active" and c.new_customers_only
        assert c.stripe_coupon_ids == {"analyst:year": "cpn_camp1", "analyst:month": "cpn_camp2"}
        annual, monthly = campaign_stripe
        assert annual["amount_off"] == 30000 and annual["duration"] == "once"
        assert annual["applies_to"] == {"products": ["prod_ay"]}
        assert annual["redeem_by"] == int(day(2099, 12, 1).timestamp())
        assert (monthly["amount_off"], monthly["duration"], monthly["duration_in_months"]) == \
            (3000, "repeating", 12)
        assert monthly["applies_to"] == {"products": ["prod_am"]}
        assert make_campaign(db).code == "BLACK-FRIDAY-2026-2"          # generated, never free text

    def test_percent_campaign(self, db, campaign_stripe):
        c = make_campaign(db, offer_type="percent", percent_off=40, intro_prices=None,
                          intervals=["year"])
        assert campaign_stripe[0]["percent_off"] == 40.0
        assert afs.campaign_first_period_cents(c, "analyst", "yearly", 39900) == 23940
        assert afs.campaign_first_period_cents(c, "navigator", "year", 19900) is None

    @pytest.mark.parametrize("bad", [
        dict(tiers=["platinum"]), dict(intervals=["weekly"]), dict(new_customers_only=False),
        dict(ends_at=day(2026, 11, 1)), dict(intro_prices={"analyst:year": 9900}),
        dict(intro_prices={"analyst:year": 39900, "analyst:month": 1900}),
        dict(offer_type="percent", percent_off=0), dict(tiers=["strategist"]), dict(name=" "),
    ])
    def test_validation(self, db, campaign_stripe, bad):
        with pytest.raises(afs.AffiliateError):
            make_campaign(db, **bad)
        assert campaign_stripe == []

    def test_window_and_status_gate_the_offer(self, db, campaign_stripe):
        c = make_campaign(db)
        assert afs.active_campaign_for(db, "analyst", "year", 39900, NOW) == (c, 9900)
        assert afs.active_campaign_for(db, "analyst", "year", 39900, day(2026, 11, 19)) == (None, None)
        assert afs.active_campaign_for(db, "navigator", "year", 19900, NOW) == (None, None)
        afs.update_campaign(db, c, status="archived")
        assert afs.active_campaign_for(db, "analyst", "year", 39900, NOW) == (None, None)

    def test_update_offer_reprovisions(self, db, campaign_stripe):
        c = make_campaign(db, intervals=["year"], intro_prices={"analyst:year": 9900})
        afs.update_campaign(db, c, name="BF", catalog=CATALOG)
        assert len(campaign_stripe) == 1                                # a rename mints nothing
        afs.update_campaign(db, c, intro_prices={"analyst:year": 14900}, catalog=CATALOG)
        assert campaign_stripe[1]["amount_off"] == 25000
        assert c.stripe_coupon_ids == {"analyst:year": "cpn_camp2"}
        with pytest.raises(afs.AffiliateError):
            afs.update_campaign(db, c, bogus=1)


def buyer(**kw):
    base = dict(id=uuid.uuid4(), email="buyer@example.com", referred_by_affiliate_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


def resolve(db, **kw):
    base = dict(user=buyer(), raw_code=None, tier="analyst", period="yearly",
                list_price_cents=39900, customer_id=None, is_new_customer=True, now=NOW)
    base.update(kw)
    return afs.resolve_checkout_offer(db, **base)


class TestCheckoutOffer:
    def test_direct_sale(self, db):
        o = resolve(db)
        assert o["affiliate_id"] is None and o["discount_spec"] is None and o["metadata"] == {}
        assert o["first_period_cents"] == 39900

    def test_partner_code_applies_the_partner_discount(self, db):
        aff = make_partner(db)
        o = resolve(db, raw_code="anne")
        assert o["discount_spec"] == {"promotion_code": "promo_anne"}
        assert (o["offer_type"], o["source"], o["first_period_cents"]) == ("regular", "checkout", 31920)
        assert o["metadata"] == {
            "tw2_affiliate_id": str(aff.id), "tw2_affiliate_code": "ANNE",
            "tw2_affiliate_source": "checkout", "tw2_terms_id": "1", "tw2_offer_type": "regular",
            "tw2_list_price_cents": "39900", "tw2_discount_pct": "20.00"}

    def test_signup_stamp_is_used_when_there_is_no_code_or_cookie(self, db):
        aff = make_partner(db)
        o = resolve(db, user=buyer(referred_by_affiliate_id=aff.id))
        assert (o["affiliate_code"], o["source"]) == ("ANNE", "signup")
        assert o["discount_spec"] == {"promotion_code": "promo_anne"}

    def test_code_beats_the_signup_stamp(self, db):
        anne = make_partner(db)
        make_partner(db, "BOB")
        o = resolve(db, raw_code="BOB", user=buyer(referred_by_affiliate_id=anne.id))
        assert o["affiliate_code"] == "BOB"

    def test_paused_partner_and_self_referral_get_nothing(self, db):
        paused = make_partner(db, status="paused")
        assert resolve(db, raw_code="ANNE")["affiliate_id"] is None
        assert resolve(db, user=buyer(referred_by_affiliate_id=paused.id))["affiliate_id"] is None
        make_partner(db, "BOB")
        assert resolve(db, raw_code="BOB", user=buyer(email="BOB@example.com"))["affiliate_id"] is None

    def test_monthly_uses_the_monthly_override(self, db):
        make_partner(db, discount_pct_monthly=D(10), stripe_coupon_id_monthly="cpn_anne_mo")
        o = resolve(db, raw_code="ANNE", period="monthly", list_price_cents=4900)
        assert o["discount_spec"] == {"coupon": "cpn_anne_mo"}
        assert (o["first_period_cents"], o["metadata"]["tw2_discount_pct"]) == (4410, "10.00")

    def test_zero_discount_partner_still_gets_credit(self, db):
        make_partner(db, discount_pct=D(0), stripe_coupon_id=None, stripe_promotion_code_id=None)
        o = resolve(db, raw_code="ANNE")
        assert o["discount_spec"] is None and o["offer_type"] == "regular"
        assert o["metadata"]["tw2_discount_pct"] == "0.00" and o["first_period_cents"] == 39900

    def test_legacy_discount_above_the_cap_is_clamped(self, db):
        make_partner(db, discount_pct=D(40))
        assert resolve(db, raw_code="ANNE")["metadata"]["tw2_discount_pct"] == "25.00"

    # --- campaign vs partner: the lower FIRST-PERIOD price wins, never both ---
    def test_campaign_wins_when_cheaper(self, db, campaign_stripe):
        aff = make_partner(db)
        c = make_campaign(db)                                           # $99 vs 20% off = $319.20
        o = resolve(db, raw_code="ANNE")
        assert o["discount_spec"] == {"coupon": "cpn_camp1"}            # exactly one discount
        assert (o["offer_type"], o["first_period_cents"]) == ("promo", 9900)
        assert (o["partner_price_cents"], o["campaign_price_cents"]) == (31920, 9900)
        md = o["metadata"]
        assert md["tw2_affiliate_id"] == str(aff.id) and md["tw2_offer_type"] == "promo"
        assert md["tw2_campaign_id"] == str(c.id) and md["tw2_discount_pct"] == "0.00"

    def test_partner_wins_when_cheaper(self, db, campaign_stripe):
        make_partner(db)
        make_campaign(db, offer_type="percent", percent_off=10, intro_prices=None)   # $359.10
        o = resolve(db, raw_code="ANNE")
        assert o["discount_spec"] == {"promotion_code": "promo_anne"}
        assert (o["offer_type"], o["first_period_cents"]) == ("regular", 31920)
        assert "tw2_campaign_id" not in o["metadata"] and o["campaign_id"] is None

    def test_tie_goes_to_the_partner_offer(self, db, campaign_stripe):
        make_partner(db)
        make_campaign(db, offer_type="percent", percent_off=20, intro_prices=None)
        assert resolve(db, raw_code="ANNE")["offer_type"] == "regular"

    def test_direct_customer_gets_the_campaign_with_no_partner(self, db, campaign_stripe):
        c = make_campaign(db)
        o = resolve(db)
        assert o["discount_spec"] == {"coupon": "cpn_camp1"} and o["affiliate_id"] is None
        assert o["metadata"] == {"tw2_campaign_id": str(c.id), "tw2_campaign_code": c.code,
                                 "tw2_offer_type": "promo", "tw2_list_price_cents": "39900"}

    def test_campaigns_are_for_new_customers_only(self, db, campaign_stripe):
        make_partner(db)
        make_campaign(db)
        o = resolve(db, raw_code="ANNE", is_new_customer=False)
        assert o["offer_type"] == "regular" and o["discount_spec"] == {"promotion_code": "promo_anne"}
        assert resolve(db, is_new_customer=False)["discount_spec"] is None

    def test_display_offers_match_checkout(self, db, campaign_stripe):
        aff = make_partner(db)
        make_campaign(db, intervals=["year"], intro_prices={"analyst:year": 9900})
        offers = afs.display_offers(db, aff, CATALOG, now=NOW)
        assert (offers["analyst:year"]["offer"], offers["analyst:year"]["price_cents"]) == ("campaign", 9900)
        assert offers["analyst:year"]["campaign"]["code"] == "BLACK-FRIDAY-2026"
        assert (offers["analyst:month"]["offer"], offers["analyst:month"]["price_cents"]) == ("partner", 3920)
        assert offers["navigator:year"]["savings_cents"] == 3980
        plain = afs.display_offers(db, None, CATALOG, now=day(2026, 1, 1))
        assert plain["analyst:year"]["offer"] is None and plain["analyst:year"]["price_cents"] == 39900

    # --- cancel and return ---
    def _returning(self, db, ended, anchor=day(2026, 1, 10)):
        anne = make_partner(db)
        make_partner(db, "BOB")
        prior = make_referral(db, anne, sub="sub_old", customer="cus_back", first_paid_at=anchor,
                              year_anchor_at=anchor, ended_at=ended)
        return anne, prior

    def test_return_within_12_months_keeps_the_partner_and_the_year_count(self, db, campaign_stripe):
        anne, prior = self._returning(db, ended=day(2026, 6, 1))
        make_campaign(db)
        o = resolve(db, raw_code="BOB", customer_id="cus_back", is_new_customer=False)
        assert (o["affiliate_code"], o["source"]) == ("ANNE", "return")  # not BOB
        assert o["offer_type"] == "regular"                              # no campaign for a returner
        assert o["metadata"]["tw2_prior_referral_id"] == str(prior.id)
        assert o["metadata"]["tw2_year_anchor_at"] == str(ts(2026, 1, 10))

    def test_return_after_year_one_gets_no_new_first_year(self, db, stripe_world):
        anne, prior = self._returning(db, ended=day(2026, 3, 1), anchor=day(2025, 2, 1))
        o = resolve(db, customer_id="cus_back", is_new_customer=False)
        assert o["affiliate_code"] == "ANNE" and o["discount_spec"] is None
        # the webhook writes the new referral with the carried anchor ...
        sub = {"id": "sub_new", "customer": "cus_back", "metadata": o["metadata"],
               "items": {"data": [{"price": {"unit_amount": 39900, "recurring": {"interval": "year"}}}]}}
        assert afs.record_referral_from_subscription(db, sub) is True
        import models
        new = db.query(models.AffiliateReferral).filter_by(stripe_subscription_id="sub_new").one()
        assert (new.source, new.prior_referral_id) == ("return", prior.id)
        assert afs._utc(new.year_anchor_at) == day(2025, 2, 1)
        # ... so the first payment of the new subscription is a RENEWAL (25%
        # of paid), not a second first year. A brand-new customer keeps Anne active.
        make_referral(db, anne, sub="sub_other", customer="cus_other", first_paid_at=day(2026, 10, 1),
                      year_anchor_at=day(2026, 10, 1))
        stripe_world.invoices = [invoice(paid=39900, paid_at=ts(2026, 12, 1), sub="sub_new",
                                         customer="cus_back")]
        rows = afs.compute_month(db, 2026, 12)
        assert total(rows) == D("99.75") and lines_of(rows)[0]["kind"] == "renewal"

    def test_return_after_12_months_is_a_brand_new_customer(self, db, campaign_stripe):
        self._returning(db, ended=day(2025, 11, 1))
        assert resolve(db, customer_id="cus_back")["affiliate_id"] is None
        o = resolve(db, raw_code="BOB", customer_id="cus_back")
        assert (o["affiliate_code"], o["source"]) == ("BOB", "checkout")
        assert "tw2_year_anchor_at" not in o["metadata"]

    def test_returning_customer_is_not_a_new_customer_for_activity(self, db, stripe_world):
        anne, prior = self._returning(db, ended=day(2026, 3, 1), anchor=day(2024, 2, 1))
        make_referral(db, anne, sub="sub_new", customer="cus_back", source="return",
                      first_paid_at=day(2026, 6, 1), year_anchor_at=day(2024, 2, 1),
                      prior_referral_id=prior.id)
        st = afs.activity_status(anne, day(2026, 7, 1), session=db)
        assert not st["active"]


class TestWebhookWriters:
    def _sub(self, sub_id="sub_t", coupon=None, metadata=None, interval="year", amount=39900):
        sub = {"id": sub_id, "customer": "cus_t", "metadata": metadata or {"tier": "analyst"},
               "items": {"data": [{"price": {"unit_amount": amount,
                                             "recurring": {"interval": interval}}}]}}
        if coupon:
            sub["discounts"] = [{"id": "di_1", "source": {"type": "coupon", "coupon": coupon}}]
        return sub

    def _ref(self, db, sub_id="sub_t"):
        import models
        return (db.query(models.AffiliateReferral)
                .filter_by(stripe_subscription_id=sub_id).first())

    def test_typed_promo_code_is_attributed(self, db):
        """The customer typed ANNE into Stripe's promo box: no metadata, but the
        coupon on the subscription maps to the partner -> a referral row is
        written, so renewals keep paying after the coupon falls off."""
        aff = make_partner(db)
        assert afs.record_referral_from_subscription(db, self._sub(coupon="cpn_anne")) is True
        ref = self._ref(db)
        assert (ref.affiliate_id, ref.source, ref.offer_type) == (aff.id, "promo_code", "regular")
        assert (cents(ref.discount_pct), ref.terms_id, ref.billing_interval) == (D("20.00"), 1, "year")
        assert (ref.list_price_cents, ref.tier, ref.stripe_customer_id) == (39900, "analyst", "cus_t")
        # webhook retry: still one row
        assert afs.record_referral_from_subscription(db, self._sub(coupon="cpn_anne")) is False

    def test_typed_code_renewal_is_paid_after_the_coupon_falls_off(self, db, stripe_world):
        aff = make_partner(db)
        afs.record_referral_from_subscription(db, self._sub(coupon="cpn_anne"))
        first = invoice("in_first", paid=31920, list_cents=39900, paid_at=ts(2025, 5, 15),
                        sub="sub_t", customer="cus_t", coupon="cpn_anne")
        assert afs.record_first_payment(db, first) is True
        make_referral(db, aff, sub="sub_other", first_paid_at=day(2026, 2, 1), year_anchor_at=day(2026, 2, 1))
        stripe_world.invoices = [first, invoice("in_renew", paid=39900, paid_at=ts(2026, 5, 15),
                                                sub="sub_t", customer="cus_t")]   # no coupon
        rows = afs.compute_month(db, *MAY)
        assert total(rows) == D("99.75") and lines_of(rows)[0]["kind"] == "renewal"
        assert total(afs.compute_month(db, 2025, 5)) == D("119.70")     # 30% of the $399 list

    def test_unexpanded_discount_ids_are_expanded(self, db, monkeypatch):
        aff = make_partner(db)
        sub = self._sub()
        sub["discounts"] = ["di_unexpanded"]
        monkeypatch.setattr(stripe.Subscription, "retrieve",
                            lambda sid, **kw: self._sub(coupon="cpn_anne"))
        assert afs.record_referral_from_subscription(db, sub) is True
        assert self._ref(db).affiliate_id == aff.id

    def test_a_coupon_replaced_by_a_discount_change_still_maps(self, db, monkeypatch):
        monkeypatch.setattr(stripe.Coupon, "create", lambda **kw: SimpleNamespace(id="cpn_v2"))
        monkeypatch.setattr(stripe.PromotionCode, "create", lambda **kw: SimpleNamespace(id="promo_v2"))
        monkeypatch.setattr(stripe.PromotionCode, "modify", lambda pid, **kw: None)
        aff = make_partner(db)
        afs.set_partner_discount(db, aff, 10)
        afs.record_referral_from_subscription(db, self._sub(coupon="cpn_anne"))   # the OLD coupon
        assert cents(self._ref(db).discount_pct) == D("20.00")

    def test_other_coupons_and_plain_subscriptions_write_nothing(self, db):
        make_partner(db)
        assert afs.record_referral_from_subscription(db, self._sub(coupon="cpn_stranger")) is False
        assert afs.record_referral_from_subscription(db, self._sub()) is False
        assert afs.record_referral_from_subscription(db, {}) is False
        assert self._ref(db) is None

    def test_checkout_metadata_snapshot_is_stored(self, db, campaign_stripe):
        aff = make_partner(db)
        c = make_campaign(db)
        o = resolve(db, raw_code="ANNE")
        afs.record_referral_from_subscription(
            db, self._sub(metadata=dict(o["metadata"], tier="analyst", period="yearly")))
        ref = self._ref(db)
        assert (ref.affiliate_id, ref.source, ref.offer_type, ref.campaign_id) == \
            (aff.id, "checkout", "promo", c.id)
        assert (ref.terms_id, ref.list_price_cents, ref.tier) == (1, 39900, "analyst")

    def test_metadata_wins_over_a_typed_coupon(self, db):
        anne = make_partner(db)
        make_partner(db, "BOB")
        md = {"tw2_affiliate_id": str(anne.id), "tw2_affiliate_code": "ANNE", "tw2_offer_type": "regular",
              "tw2_discount_pct": "0", "tw2_terms_id": "1"}
        afs.record_referral_from_subscription(db, self._sub(coupon="cpn_bob", metadata=md))
        assert self._ref(db).affiliate_id == anne.id

    def test_first_payment_and_end_are_stamped_once(self, db):
        aff = make_partner(db)
        ref = make_referral(db, aff, sub="sub_t")
        trial = invoice("in_trial", paid=0, paid_at=ts(2026, 5, 1), sub="sub_t")
        assert afs.record_first_payment(db, trial) is False             # $0 never starts the clock
        assert ref.first_paid_at is None
        paid = invoice("in_paid", paid=8000, paid_at=ts(2026, 5, 8, 9), period_start=ts(2026, 5, 8),
                       sub="sub_t")
        assert afs.record_first_payment(db, paid) is True
        assert afs._utc(ref.first_paid_at) == day(2026, 5, 8, 9)
        assert afs._utc(ref.year_anchor_at) == day(2026, 5, 8)
        later = invoice("in_later", paid=8000, paid_at=ts(2026, 6, 8), sub="sub_t")
        assert afs.record_first_payment(db, later) is False
        assert afs._utc(ref.first_paid_at) == day(2026, 5, 8, 9)
        assert afs.record_subscription_ended(db, {"id": "sub_t", "ended_at": ts(2026, 9, 1)}) is True
        assert afs._utc(ref.ended_at) == day(2026, 9, 1)
        assert afs.record_subscription_ended(db, {"id": "sub_unknown"}) is False


# ============================================================================
# 5. Founder guard + the checkout route (web/app.py)
# ============================================================================

class TestFounderRule:
    def test_detection_signals(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "FOUNDER_PRICE_IDS", ("price_founder",))
        assert afs.is_founder_price({"id": "price_founder"})
        assert afs.is_founder_price({"id": "price_x", "metadata": {"tw2_founder": "true"}})
        assert afs.is_founder_price({"id": "price_x", "product": {"metadata": {"tw2_founder": "TRUE"}}})
        assert afs.is_founder_price({"id": "price_x"}, product_metadata={"tw2_founder": "true"})
        assert not afs.is_founder_price({"id": "price_x", "product": "prod_1"})
        assert not afs.is_founder_price({"id": "price_x", "metadata": {"tw2_founder": "false"}})
        assert not afs.is_founder_price(None)

    def test_config_default_is_empty(self):
        import config
        src = (_REPO_ROOT / "config.py").read_text()
        assert "TW2_FOUNDER_PRICE_IDS" in src and isinstance(config.FOUNDER_PRICE_IDS, tuple)


@pytest.fixture
def app_module(monkeypatch):
    mod = importlib.import_module("app")
    monkeypatch.setenv("TW2_PUBLIC_HOST", "tw2.trxstat.com")
    monkeypatch.setattr(mod, "_stripe_configured", lambda: True)
    monkeypatch.setattr(mod, "parse_ga_client_id", lambda _request: None)
    return mod


def _founder_user():
    return SimpleNamespace(id="u-founder", email="founder@example.com", tier="analyst",
                           stripe_customer_id="cus_f", stripe_subscription_id="sub_f")


def _founder_stripe(monkeypatch, mod, price_id="price_founder"):
    import config
    monkeypatch.setattr(config, "FOUNDER_PRICE_IDS", ("price_founder",))
    monkeypatch.setattr(mod.stripe.Customer, "retrieve",
                        staticmethod(lambda _cid: SimpleNamespace(deleted=False)))
    monkeypatch.setattr(mod.stripe.Subscription, "retrieve", staticmethod(
        lambda sid, **kw: {"id": sid, "items": {"data": [{"id": "si_1", "price": {"id": price_id}}]}}))
    portal = []

    def create_portal(**kw):
        portal.append(kw)
        return SimpleNamespace(url="https://billing.stripe.test/p")
    monkeypatch.setattr(mod.stripe.billing_portal.Session, "create", staticmethod(create_portal))
    return portal


class TestFounderGuardRoutes:
    def _checkout(self, mod, monkeypatch, user):
        monkeypatch.setattr(mod, "get_current_user", lambda: user)
        monkeypatch.setattr(mod, "_price_id_for", lambda *_a: "price_ay")
        monkeypatch.setattr(mod, "_existing_eod_subscription",
                            lambda *_a, **_k: ("sub_f", "si_1", "active"))
        with mod.app.test_request_context("/api/stripe/create-checkout?tier=strategist&period=yearly"):
            return mod.stripe_create_checkout.__wrapped__()

    def test_founder_checkout_is_refused_with_a_clear_message(self, app_module, monkeypatch):
        portal = _founder_stripe(monkeypatch, app_module)
        response, status = self._checkout(app_module, monkeypatch, _founder_user())
        body = response.get_json()
        assert status == 409 and body["error"] == "founder_plan_locked"
        assert "cancel" in body["message"] and body["cancel_url"] == "/account/manage-subscription"
        assert "—" not in body["message"]
        assert portal == []                     # the plan-switch (update-confirm) flow never opened

    def test_non_founder_still_gets_the_plan_switch_flow(self, app_module, monkeypatch):
        portal = _founder_stripe(monkeypatch, app_module, price_id="price_regular")
        response = self._checkout(app_module, monkeypatch, _founder_user())
        assert response.status_code == 303
        assert portal[0]["flow_data"]["type"] == "subscription_update_confirm"

    def test_founder_check_fails_closed(self, app_module, monkeypatch):
        portal = _founder_stripe(monkeypatch, app_module)

        def boom(sid, **kw):
            raise RuntimeError("stripe down")
        monkeypatch.setattr(app_module.stripe.Subscription, "retrieve", staticmethod(boom))
        response, status = self._checkout(app_module, monkeypatch, _founder_user())
        assert status == 503 and portal == []

    def test_founder_billing_portal_is_cancel_only(self, app_module, monkeypatch):
        portal = _founder_stripe(monkeypatch, app_module)
        monkeypatch.setattr(app_module, "get_current_user", _founder_user)
        monkeypatch.setattr(app_module.config, "FOUNDER_BILLING_PORTAL_CONFIGURATION_ID", "")
        with app_module.app.test_request_context("/account/manage-subscription"):
            response = app_module.manage_subscription.__wrapped__()
        assert response.status_code == 303
        assert portal[0]["flow_data"]["type"] == "subscription_cancel"
        assert portal[0]["flow_data"]["subscription_cancel"] == {"subscription": "sub_f"}
        # with a dedicated no-plan-switch portal configuration, that is used instead
        portal.clear()
        monkeypatch.setattr(app_module.config, "FOUNDER_BILLING_PORTAL_CONFIGURATION_ID", "bpc_founder")
        with app_module.app.test_request_context("/account/manage-subscription"):
            app_module.manage_subscription.__wrapped__()
        assert portal[0]["configuration"] == "bpc_founder" and "flow_data" not in portal[0]


class TestCheckoutRoute:
    def _run(self, mod, monkeypatch, db, user, url, customer_new=True, create=None):
        created = []
        monkeypatch.setattr(mod, "get_current_user", lambda: user)
        monkeypatch.setattr(mod, "DBSession", db.factory)
        price = SimpleNamespace(id="price_ay", unit_amount=39900, currency="usd")
        monkeypatch.setattr(mod, "_price_id_for", lambda *_a: price.id)
        monkeypatch.setattr(mod, "_price_for", lambda *_a: price)
        monkeypatch.setattr(mod, "_is_new_customer", lambda _cid: customer_new)
        monkeypatch.setattr(mod, "reserve_checkout", lambda uid, line, kwargs, **kw: SimpleNamespace(
            reused=False, idempotency_key="idem", payload=kwargs))
        monkeypatch.setattr(mod, "complete_checkout", lambda *a, **k: None)
        monkeypatch.setattr(mod, "send_event", lambda *a, **k: None)

        def default_create(**kw):
            created.append(kw)
            return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}
        monkeypatch.setattr(mod.stripe.checkout.Session, "create",
                            staticmethod(create or default_create))
        with mod.app.test_request_context(url):
            response = mod.stripe_create_checkout.__wrapped__()
        assert response.status_code == 303
        return created[0] if created else None

    def _user(self, **kw):
        base = dict(id=uuid.uuid4(), email="buyer@example.com", tier="explorer",
                    stripe_customer_id=None, stripe_subscription_id=None,
                    referred_by_affiliate_id=None)
        base.update(kw)
        return SimpleNamespace(**base)

    URL = "/api/stripe/create-checkout?tier=analyst&period=yearly"

    def test_signup_referred_user_is_attributed_without_a_code(self, app_module, monkeypatch, db):
        aff = make_partner(db)
        kw = self._run(app_module, monkeypatch, db,
                       self._user(referred_by_affiliate_id=aff.id), self.URL)
        assert kw["discounts"] == [{"promotion_code": "promo_anne"}]
        assert "allow_promotion_codes" not in kw
        md = kw["subscription_data"]["metadata"]
        assert md["tw2_affiliate_id"] == str(aff.id) and md["tw2_affiliate_code"] == "ANNE"
        assert (md["tw2_terms_id"], md["tw2_offer_type"], md["tw2_list_price_cents"],
                md["tw2_discount_pct"], md["period"]) == ("1", "regular", "39900", "20.00", "yearly")
        assert "tw2_campaign_id" not in md

    def test_referred_visitor_gets_the_sale_price_when_it_is_lower(self, app_module, monkeypatch,
                                                                    db, campaign_stripe):
        aff = make_partner(db)
        c = make_campaign(db)
        kw = self._run(app_module, monkeypatch, db, self._user(), self.URL + "&code=anne")
        assert kw["discounts"] == [{"coupon": "cpn_camp1"}]             # one discount, the campaign
        md = kw["subscription_data"]["metadata"]
        assert (md["tw2_affiliate_id"], md["tw2_offer_type"], md["tw2_campaign_id"]) == \
            (str(aff.id), "promo", str(c.id))

    def test_direct_checkout_is_unchanged(self, app_module, monkeypatch, db):
        kw = self._run(app_module, monkeypatch, db, self._user(), self.URL)
        assert kw["allow_promotion_codes"] is True and "discounts" not in kw
        assert not [k for k in kw["subscription_data"]["metadata"] if k.startswith("tw2_affiliate")]

    def test_rejected_discount_falls_back_without_a_stale_snapshot(self, app_module, monkeypatch,
                                                                   db, campaign_stripe):
        """Stripe rejects the pre-applied campaign coupon: checkout retries with
        manual promo entry, keeps the partner, and drops the campaign + stamped
        discount so the sale is priced from what the invoice really carries."""
        aff = make_partner(db)
        make_campaign(db)
        calls = []
        monkeypatch.setattr(app_module, "replace_checkout_payload",
                            lambda res, kwargs, **kw: SimpleNamespace(
                                reused=False, idempotency_key="idem2", payload=kwargs))

        def create(**kw):
            calls.append(kw)
            if len(calls) == 1:
                raise app_module.stripe.error.InvalidRequestError("coupon expired", "discounts")
            return {"id": "cs_2", "url": "https://checkout.stripe.test/cs_2"}
        self._run(app_module, monkeypatch, db, self._user(), self.URL + "&code=ANNE", create=create)
        first, second = calls
        assert first["discounts"] == [{"coupon": "cpn_camp1"}]
        assert second["allow_promotion_codes"] is True and "discounts" not in second
        md = second["subscription_data"]["metadata"]
        assert md["tw2_affiliate_id"] == str(aff.id) and md["tw2_offer_type"] == "regular"
        assert not {"tw2_campaign_id", "tw2_campaign_code", "tw2_discount_pct"} & set(md)

    def test_offer_failure_never_breaks_checkout(self, app_module, monkeypatch, db):
        import affiliate_service

        def boom(*a, **k):
            raise RuntimeError("db down")
        monkeypatch.setattr(affiliate_service, "resolve_checkout_offer", boom)
        kw = self._run(app_module, monkeypatch, db, self._user(), self.URL + "&code=ANNE")
        assert kw["allow_promotion_codes"] is True


# ============================================================================
# 6. Migration
# ============================================================================

def test_migration_chain_has_a_single_head():
    versions = _REPO_ROOT / "migrations" / "versions"
    revs, downs = {}, set()
    for path in versions.glob("*.py"):
        text = path.read_text()
        rev = re.search(r"^revision\s*(?::\s*\w+\s*)?=\s*['\"](\w+)['\"]", text, re.M).group(1)
        down = re.search(r"^down_revision\s*(?::[^=]+)?=\s*(.+)$", text, re.M).group(1)
        revs[rev] = path.name
        downs.update(re.findall(r"['\"](\w+)['\"]", down))
    heads = sorted(set(revs) - downs)
    assert heads == ["b4d7e1f2a3c5"], heads
    assert downs <= set(revs)
    mig = (versions / revs["b4d7e1f2a3c5"]).read_text()
    assert "down_revision = 'a7f3c2e9b1d4'" in mig
    for table in ("affiliate_terms", "affiliate_discount_changes", "promo_campaigns",
                  "affiliate_commission_lines"):
        assert 'create_table(\n        "%s"' % table in mig


def test_models_match_the_migration_tables():
    import models
    tables = models.Base.metadata.tables
    line = tables["affiliate_commission_lines"]
    uniq = [sorted(c.name for c in con.columns) for con in line.constraints
            if type(con).__name__ == "UniqueConstraint"]
    assert ["affiliate_id", "source_id"] in uniq
    mig = (_REPO_ROOT / "migrations" / "versions" / "b4d7e1f2a3c5_affiliate_program_v2.py").read_text()
    for name in ("affiliate_terms", "affiliate_discount_changes", "promo_campaigns",
                 "affiliate_commission_lines"):
        for col in tables[name].columns:
            assert '"%s"' % col.name in mig, (name, col.name)
    for col in ("terms_id", "offer_type", "campaign_id", "tier", "billing_interval",
                "list_price_cents", "discount_pct", "first_paid_at", "year_anchor_at",
                "ended_at", "prior_referral_id"):
        assert col in tables["affiliate_referrals"].columns and '"%s"' % col in mig
    for col in ("terms_id", "discount_changed_at", "terminated_for_cause", "terminated_at",
                "termination_cause"):
        assert col in tables["affiliates"].columns and '"%s"' % col in mig
