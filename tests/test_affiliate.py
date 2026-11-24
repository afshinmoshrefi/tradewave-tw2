"""Unit tests for the affiliate commission engine (web/affiliate_service.py).

Hermetic: Stripe is monkeypatched, and the pure core _compute() takes a list of
duck-typed affiliate objects (no DB / no network).

Program v2 (TW-TASK-0038): a first-year regular sale pays the POOL rule -
(50 - discount)% of the LIST price (pre-discount subtotal, tax excluded) - not
a flat percent of what was paid. The $100 plan at 20% off pays $30 (it paid
$24 under the old 30%-of-paid engine). The full rule matrix lives in
tests/test_affiliate_v2.py; this module keeps the engine-plumbing checks.
"""
import datetime as dt
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


# --- helpers ----------------------------------------------------------------

def _aff(**kw):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        code="ANNE", name="Anne", email="anne@example.com",
        payout_email="anne@pay.com",
        commission_pct=Decimal("30.00"), commission_model="recurring",
        stripe_coupon_id="cpn_anne", status="active",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _inv(coupon="cpn_anne", amount_paid=8000, tax=0, customer="cus_1",
         email="buyer@example.com", created=None, iid="in_1", subtotal=10000):
    """A paid invoice: $100 list (subtotal) at 20% off = $80 paid by default."""
    if created is None:
        created = int(dt.datetime(2026, 5, 15, tzinfo=dt.timezone.utc).timestamp())
    return {
        "id": iid, "amount_paid": amount_paid, "currency": "usd",
        "status": "paid", "subtotal": subtotal,
        # SDK 15.x shape: tax lives in `total_taxes` (list of {amount}),
        # NOT the old top-level `tax` / `total_tax_amounts`.
        "total_taxes": ([{"amount": tax}] if tax else []),
        "customer": customer, "customer_email": email, "created": created,
        # Real SDK-15 shape: the coupon id is under discount.source.coupon.
        "discounts": ([{"id": "di_x", "promotion_code": "promo_x",
                        "source": {"type": "coupon", "coupon": coupon}}] if coupon else []),
    }


class _FakeList:
    def __init__(self, items):
        self._items = items

    def auto_paging_iter(self):
        return iter(self._items)


def _patch_month_invoices(monkeypatch, items):
    """Patch the month listing; per-customer history lookups return empty."""
    def _list(**kw):
        if "customer" in kw:
            return _FakeList([])
        return _FakeList(items)
    monkeypatch.setattr(stripe.Invoice, "list", _list)
    _patch_reversals(monkeypatch)


def _patch_reversals(monkeypatch, refunds=(), disputes=(), invoices=None):
    """Patch the clawback pass: refunds/disputes created in the month, and the
    payment -> invoice lookup (InvoicePayment.list + Invoice.retrieve)."""
    invoices = invoices or {}
    monkeypatch.setattr(stripe.Refund, "list", lambda **kw: _FakeList(list(refunds)))
    monkeypatch.setattr(stripe.Dispute, "list", lambda **kw: _FakeList(list(disputes)))

    def _ip_list(**kw):
        pi = kw["payment"]["payment_intent"]
        inv = invoices.get(pi)
        return _FakeList([{"invoice": inv["id"]}] if inv else [])
    monkeypatch.setattr(stripe.InvoicePayment, "list", _ip_list)
    by_id = {v["id"]: v for v in invoices.values()}
    monkeypatch.setattr(stripe.Invoice, "retrieve", lambda iid, **kw: by_id[iid])


# --- code validation --------------------------------------------------------

def test_normalize_and_validate_code():
    assert afs.normalize_code(" anne ") == "ANNE"
    afs.validate_code("ANNE")
    afs.validate_code("COACH-BOB")
    afs.validate_code(afs.normalize_code("coach_bob"))
    for bad in ("A", "ANNE!!", "x" * 65, "", "an ne"):
        with pytest.raises(afs.AffiliateError):
            afs.validate_code(afs.normalize_code(bad))


def test_month_window():
    start, end, ps, pe = afs._month_window(2026, 5)
    assert ps == dt.date(2026, 5, 1)
    assert pe == dt.date(2026, 5, 31)
    assert end == dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    # December rolls the year
    _, end_dec, _, pe_dec = afs._month_window(2026, 12)
    assert end_dec == dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)
    assert pe_dec == dt.date(2026, 12, 31)


def test_invoice_coupon_ids_shapes():
    # current SDK-15 shape: discount.source.coupon
    assert afs._invoice_coupon_ids(
        {"discounts": [{"source": {"type": "coupon", "coupon": "c1"}}]}) == ["c1"]
    # legacy shapes still supported
    assert afs._invoice_coupon_ids({"discounts": [{"coupon": {"id": "c2"}}]}) == ["c2"]
    assert afs._invoice_coupon_ids({"discount": {"coupon": {"id": "c3"}}}) == ["c3"]
    # unexpanded id string / empty -> nothing
    assert afs._invoice_coupon_ids({"discounts": ["di_x"]}) == []
    assert afs._invoice_coupon_ids({}) == []


# --- commission math --------------------------------------------------------

def test_first_year_pool_rule(monkeypatch):
    # $100 list, 20% off -> customer pays $80, partner earns (50 - 20)% of
    # LIST = $30 (was $24 = 30% of paid before program v2).
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=8000, tax=0)])
    rows = afs._compute([_aff()], 2026, 5)
    assert len(rows) == 1
    assert rows[0]["gross_revenue"] == Decimal("80.00")
    assert rows[0]["commission_amount"] == Decimal("30.00")
    assert rows[0]["code"] == "ANNE"
    line = rows[0]["detail"][0]
    assert line["kind"] == "first_year" and line["state"] == "estimated"
    assert line["basis"] == "100.00" and Decimal(line["rate_pct"]) == Decimal("30")


def test_legacy_commission_fields_are_ignored(monkeypatch):
    # commission_pct / commission_model are pre-v2 columns: the engine reads
    # the rules from the terms version, never from them.
    _patch_month_invoices(monkeypatch, [_inv()])
    for model in ("recurring", "first_payment", "duration_12mo"):
        rows = afs._compute([_aff(commission_pct=Decimal("5"), commission_model=model)], 2026, 5)
        assert rows[0]["commission_amount"] == Decimal("30.00")


def test_tax_is_excluded(monkeypatch):
    # $88 paid, $8 tax -> $80 net on a $100 list -> pool rule = $30
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=8800, tax=800)])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["gross_revenue"] == Decimal("80.00")
    assert rows[0]["commission_amount"] == Decimal("30.00")


def test_total_tax_amounts_fallback(monkeypatch):
    # older API shape: total_tax_amounts (no total_taxes) - still supported
    inv = _inv(amount_paid=8800, tax=0)
    inv["total_taxes"] = []
    inv["total_tax_amounts"] = [{"amount": 800}]
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("30.00")


def test_legacy_top_level_tax_fallback(monkeypatch):
    # oldest API shape: top-level `tax`
    inv = _inv(amount_paid=8800, tax=0)
    inv["total_taxes"] = []
    inv["tax"] = 800
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("30.00")


def test_other_coupon_is_ignored(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv(coupon="cpn_someone_else")])
    assert afs._compute([_aff()], 2026, 5) == []


def test_self_referral_skipped(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv(email="anne@example.com")])
    assert afs._compute([_aff(email="anne@example.com")], 2026, 5) == []


def test_multiple_invoices_accumulate(monkeypatch):
    _patch_month_invoices(monkeypatch, [
        _inv(amount_paid=8000, iid="in_1", customer="cus_1"),
        _inv(amount_paid=4000, iid="in_2", customer="cus_2", subtotal=5000),
    ])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["gross_revenue"] == Decimal("120.00")
    assert rows[0]["commission_amount"] == Decimal("45.00")   # $30 + $15
    assert len(rows[0]["detail"]) == 2


def test_zero_basis_skipped(monkeypatch):
    # fully tax / $0 paid -> no commission row
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=0, tax=0)])
    assert afs._compute([_aff()], 2026, 5) == []


def test_no_affiliates_returns_empty(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv()])
    assert afs._compute([], 2026, 5) == []
    # affiliate without a coupon id is not attributable
    assert afs._compute([_aff(stripe_coupon_id=None)], 2026, 5) == []


def test_rounding_half_up(monkeypatch):
    # $33.33 list at 0% off * 50% = 16.665 -> 16.67 (ROUND_HALF_UP at the cent)
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=3333, tax=0, subtotal=3333)])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("16.67")


def test_provision_passes_new_promotion_param(monkeypatch):
    """Lock the Stripe param shape: coupon (percent_off / repeating 12mo /
    name<=40) and promotion code nested under `promotion` (SDK 15.x), not the
    old top-level `coupon`."""
    captured = {}

    class _Obj:
        def __init__(self, _id):
            self.id = _id

    def fake_coupon_create(**kw):
        captured["coupon"] = kw
        return _Obj("cpn_x")

    def fake_promo_create(**kw):
        captured["promo"] = kw
        return _Obj("promo_x")

    monkeypatch.setattr(stripe.Coupon, "create", fake_coupon_create)
    monkeypatch.setattr(stripe.PromotionCode, "create", fake_promo_create)

    aff = _aff(code="newcode", stripe_coupon_id=None,
               stripe_promotion_code_id=None, discount_pct=Decimal("20.00"))
    cid, pid = afs.provision_stripe_objects(aff)
    assert (cid, pid) == ("cpn_x", "promo_x")
    assert captured["coupon"]["percent_off"] == 20.0
    assert captured["coupon"]["duration"] == "repeating"
    assert captured["coupon"]["duration_in_months"] == 12
    assert len(captured["coupon"]["name"]) <= 40
    # NEW nested promotion param; the old top-level `coupon` must NOT be sent
    assert "coupon" not in captured["promo"]
    assert captured["promo"]["promotion"] == {"type": "coupon", "coupon": "cpn_x"}
    assert captured["promo"]["code"] == "NEWCODE"


def test_commission_rounds_on_aggregate_not_per_line(monkeypatch):
    """Commission is summed unrounded and quantized ONCE per (affiliate, currency).
    Two $0.01 list-price invoices at 50%: per-line rounding would lift both to
    $0.01 ($0.02 total); aggregate rounding gives 0.005+0.005=0.010 -> $0.01."""
    aff = _aff(commission_model="recurring")
    i1 = _inv(iid="a", amount_paid=1, customer="cus_1", subtotal=1)     # $0.01 basis
    i2 = _inv(iid="b", amount_paid=1, customer="cus_2", subtotal=1)     # distinct customer; both count
    _patch_month_invoices(monkeypatch, [i1, i2])
    rows = afs._compute([aff], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("0.01")


def _refund(amount, pi="pi_1", rid="re_1", status="succeeded"):
    return {"id": rid, "amount": amount, "payment_intent": pi, "charge": "ch_1",
            "status": status, "created": 0}


def test_full_refund_same_month_nets_to_zero(monkeypatch):
    """Paid and fully refunded in the same month -> zero commission."""
    inv = _inv(amount_paid=8000)
    _patch_month_invoices(monkeypatch, [inv])
    _patch_reversals(monkeypatch, refunds=[_refund(8000)], invoices={"pi_1": inv})
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("0.00")
    kinds = [ln["kind"] for ln in rows[0]["detail"]]
    assert kinds == ["first_year", "refund"]


def test_partial_refund_netted(monkeypatch):
    """Half refunded -> half of the ORIGINAL $30 line is reversed."""
    inv = _inv(amount_paid=8000)
    _patch_month_invoices(monkeypatch, [inv])
    _patch_reversals(monkeypatch, refunds=[_refund(4000)], invoices={"pi_1": inv})
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("15.00")   # $30 - $15


def test_refund_of_earlier_month_is_clawed_back(monkeypatch):
    """Invoice paid in April, refunded in May -> May gets a NEGATIVE row."""
    april = _inv(amount_paid=8800, tax=800,
                 created=int(dt.datetime(2026, 4, 10, tzinfo=dt.timezone.utc).timestamp()))
    _patch_month_invoices(monkeypatch, [])                     # nothing paid in May
    _patch_reversals(monkeypatch, refunds=[_refund(8800)], invoices={"pi_1": april})
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["gross_revenue"] == Decimal("-80.00")       # tax share stripped
    assert rows[0]["commission_amount"] == Decimal("-30.00")   # the original line, reversed


def test_lost_dispute_clawed_back_won_ignored(monkeypatch):
    inv = _inv(amount_paid=8000)
    _patch_month_invoices(monkeypatch, [inv])
    disputes = [{"id": "dp_1", "amount": 8000, "payment_intent": "pi_1", "status": "lost"},
                {"id": "dp_2", "amount": 8000, "payment_intent": "pi_1", "status": "won"}]
    _patch_reversals(monkeypatch, disputes=disputes, invoices={"pi_1": inv})
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("0.00")
    assert [ln["kind"] for ln in rows[0]["detail"]] == ["first_year", "dispute"]


def test_failed_refund_ignored(monkeypatch):
    inv = _inv(amount_paid=8000)
    _patch_month_invoices(monkeypatch, [inv])
    _patch_reversals(monkeypatch, refunds=[_refund(8000, status="failed")],
                     invoices={"pi_1": inv})
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("30.00")


def test_refund_of_unattributed_invoice_ignored(monkeypatch):
    inv = _inv(coupon=None, amount_paid=8000)
    _patch_month_invoices(monkeypatch, [])
    _patch_reversals(monkeypatch, refunds=[_refund(8000)], invoices={"pi_1": inv})
    assert afs._compute([_aff()], 2026, 5) == []


def test_renewal_attributed_via_referral_after_coupon_expires(monkeypatch):
    """The persisted-referral fix: a month-13 invoice no longer carries the
    12-month discount coupon, but the referral maps its subscription -> partner,
    so the renewal still pays (25% of what was paid). Without the referral the
    same invoice is un-attributable and pays nothing."""
    aff = _aff()
    paid = dt.datetime(2026, 5, 15, tzinfo=dt.timezone.utc)
    inv = _inv(coupon=None, iid="in_m13", amount_paid=10000)   # coupon has fallen off
    inv["subscription"] = "sub_anne"
    inv["lines"] = {"data": [{"period": {"start": int(paid.timestamp())}}]}
    _patch_month_invoices(monkeypatch, [inv])
    # no referral, no coupon -> nothing to attribute to
    assert afs._compute([aff], 2026, 5) == []
    first = dt.datetime(2025, 5, 15, tzinfo=dt.timezone.utc)
    refs = {
        "sub_anne": SimpleNamespace(affiliate_id=aff.id, first_paid_at=first, year_anchor_at=first),
        # a newer customer keeps the partner ACTIVE under the 12-month rule
        "sub_new": SimpleNamespace(affiliate_id=aff.id,
                                   first_paid_at=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc),
                                   year_anchor_at=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc)),
    }
    rows = afs._compute([aff], 2026, 5, refs)
    assert len(rows) == 1
    assert rows[0]["commission_amount"] == Decimal("25.00")
    assert rows[0]["detail"][0]["kind"] == "renewal"
    assert rows[0]["detail"][0]["year_number"] == 2


def test_bare_affiliate_id_referral_still_attributes(monkeypatch):
    """Legacy callers pass {subscription_id: affiliate_id}: still attributed."""
    aff = _aff()
    inv = _inv(coupon=None, iid="in_x", amount_paid=10000)
    inv["subscription"] = "sub_anne"
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([aff], 2026, 5, {"sub_anne": aff.id})
    assert rows[0]["commission_amount"] == Decimal("50.00")    # 0% off -> full pool


def test_unattributed_discounted_invoice_is_skipped(monkeypatch):
    """A discounted invoice whose coupon belongs to no active affiliate (and has
    no referral) is skipped - never paid to the wrong party - and surfaced via a
    warning log rather than silently dropped."""
    inv = _inv(coupon="cpn_stranger", iid="in_x")
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([_aff()], 2026, 5)         # _aff coupon is cpn_anne
    assert rows == []
