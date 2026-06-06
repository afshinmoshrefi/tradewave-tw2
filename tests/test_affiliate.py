"""Unit tests for the affiliate commission engine (web/affiliate_service.py).

Hermetic: Stripe is monkeypatched, and the pure core _compute() takes a list of
duck-typed affiliate objects (no DB / no network).
"""
import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import sys
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

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
         email="buyer@example.com", created=None, iid="in_1"):
    if created is None:
        created = int(dt.datetime(2026, 5, 15, tzinfo=dt.timezone.utc).timestamp())
    return {
        "id": iid, "amount_paid": amount_paid, "currency": "usd",
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

def test_recurring_commission(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=8000, tax=0)])
    rows = afs._compute([_aff()], 2026, 5)
    assert len(rows) == 1
    assert rows[0]["gross_revenue"] == Decimal("80.00")
    assert rows[0]["commission_amount"] == Decimal("24.00")  # 30% of 80
    assert rows[0]["code"] == "ANNE"


def test_tax_is_excluded(monkeypatch):
    # $88 paid, $8 tax -> basis $80 -> 30% = $24
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=8800, tax=800)])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["gross_revenue"] == Decimal("80.00")
    assert rows[0]["commission_amount"] == Decimal("24.00")


def test_total_tax_amounts_fallback(monkeypatch):
    # older API shape: total_tax_amounts (no total_taxes) - still supported
    inv = _inv(amount_paid=8800, tax=0)
    inv["total_taxes"] = []
    inv["total_tax_amounts"] = [{"amount": 800}]
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("24.00")


def test_legacy_top_level_tax_fallback(monkeypatch):
    # oldest API shape: top-level `tax`
    inv = _inv(amount_paid=8800, tax=0)
    inv["total_taxes"] = []
    inv["tax"] = 800
    _patch_month_invoices(monkeypatch, [inv])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("24.00")


def test_other_coupon_is_ignored(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv(coupon="cpn_someone_else")])
    assert afs._compute([_aff()], 2026, 5) == []


def test_self_referral_skipped(monkeypatch):
    _patch_month_invoices(monkeypatch, [_inv(email="anne@example.com")])
    assert afs._compute([_aff(email="anne@example.com")], 2026, 5) == []


def test_multiple_invoices_accumulate(monkeypatch):
    _patch_month_invoices(monkeypatch, [
        _inv(amount_paid=8000, iid="in_1", customer="cus_1"),
        _inv(amount_paid=4000, iid="in_2", customer="cus_2"),
    ])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["gross_revenue"] == Decimal("120.00")
    assert rows[0]["commission_amount"] == Decimal("36.00")
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
    # $33.33 basis * 30% = 9.999 -> 10.00 (ROUND_HALF_UP at the cent)
    _patch_month_invoices(monkeypatch, [_inv(amount_paid=3333, tax=0)])
    rows = afs._compute([_aff()], 2026, 5)
    assert rows[0]["commission_amount"] == Decimal("10.00")


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


def test_first_payment_model(monkeypatch):
    first_ts = int(dt.datetime(2026, 5, 10, tzinfo=dt.timezone.utc).timestamp())
    later_ts = int(dt.datetime(2026, 5, 25, tzinfo=dt.timezone.utc).timestamp())
    month_items = [
        _inv(iid="in_first", created=first_ts, customer="cus_1"),
        _inv(iid="in_later", created=later_ts, customer="cus_1"),
    ]

    def _list(**kw):
        if "customer" in kw:
            # customer's full paid history: earliest is in_first
            return _FakeList([_inv(iid="in_first", created=first_ts, customer="cus_1")])
        return _FakeList(month_items)

    monkeypatch.setattr(stripe.Invoice, "list", _list)
    rows = afs._compute([_aff(commission_model="first_payment")], 2026, 5)
    # only the first invoice counts -> 30% of $80 = $24, single detail line
    assert rows[0]["commission_amount"] == Decimal("24.00")
    assert len(rows[0]["detail"]) == 1
    assert rows[0]["detail"][0]["invoice"] == "in_first"


def test_first_payment_dedupes_near_simultaneous_invoices(monkeypatch):
    """Regression: two paid invoices on the SAME coupon minutes apart
    (proration / true-up) must pay first_payment ONCE - the earliest invoice by
    identity - not twice. The old +/-1h window double-counted them ($48)."""
    t0 = int(dt.datetime(2026, 5, 15, 10, 0, tzinfo=dt.timezone.utc).timestamp())
    t1 = int(dt.datetime(2026, 5, 15, 10, 30, tzinfo=dt.timezone.utc).timestamp())
    early = _inv(iid="in_early", created=t0, customer="cus_1")
    later = _inv(iid="in_later", created=t1, customer="cus_1")

    def _list(**kw):
        # both the month listing and the per-customer history return both
        return _FakeList([early, later])

    monkeypatch.setattr(stripe.Invoice, "list", _list)
    rows = afs._compute([_aff(commission_model="first_payment")], 2026, 5)
    assert len(rows) == 1
    assert rows[0]["commission_amount"] == Decimal("24.00")   # ONE invoice, not $48
    assert len(rows[0]["detail"]) == 1
    assert rows[0]["detail"][0]["invoice"] == "in_early"


def test_first_payment_ignores_unrelated_earlier_invoice(monkeypatch):
    """Regression for the anchor bug: a customer's earlier invoice under a
    DIFFERENT coupon must not anchor first_payment, or the affiliate's real
    first invoice gets wrongly skipped."""
    unrelated_ts = int(dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc).timestamp())
    aff_ts = int(dt.datetime(2026, 5, 10, tzinfo=dt.timezone.utc).timestamp())
    month_items = [_inv(iid="in_aff", created=aff_ts, customer="cus_1", coupon="cpn_anne")]

    def _list(**kw):
        if "customer" in kw:
            # full paid history: an unrelated earlier invoice + the affiliate one
            return _FakeList([
                _inv(iid="in_unrelated", created=unrelated_ts, customer="cus_1", coupon="cpn_other"),
                _inv(iid="in_aff", created=aff_ts, customer="cus_1", coupon="cpn_anne"),
            ])
        return _FakeList(month_items)

    monkeypatch.setattr(stripe.Invoice, "list", _list)
    rows = afs._compute([_aff(commission_model="first_payment")], 2026, 5)
    # the affiliate invoice IS the earliest carrying the affiliate coupon -> it counts
    assert len(rows) == 1
    assert rows[0]["commission_amount"] == Decimal("24.00")
    assert rows[0]["detail"][0]["invoice"] == "in_aff"
