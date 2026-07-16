"""Unit tests for standalone promo coupons (web/promo_service.py). Hermetic:
Stripe is monkeypatched; validation + param-shaping only (no DB / network)."""
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
import promo_service as ps  # noqa: E402


def _p(**kw):
    base = dict(code="LAUNCH20", name=None, discount_type="percent",
                percent_off=Decimal("20.00"), amount_off_cents=None, currency=None,
                duration="once", duration_in_months=None, max_redemptions=None,
                expires_at=None, stripe_coupon_id=None, stripe_promotion_code_id=None)
    base.update(kw)
    return SimpleNamespace(**base)


class _Obj:
    def __init__(self, _id):
        self.id = _id


# --- validation -------------------------------------------------------------

def test_validate_percent_ok():
    ps.validate_promo(_p())
    ps.validate_promo(_p(percent_off=Decimal("100")))  # free / comp


def test_validate_percent_bad():
    for bad in (None, Decimal("0"), Decimal("100.01")):
        with pytest.raises(ps.PromoError):
            ps.validate_promo(_p(percent_off=bad))


def test_validate_amount_ok():
    ps.validate_promo(_p(discount_type="amount", percent_off=None,
                         amount_off_cents=1000, currency="usd"))


def test_validate_amount_needs_currency():
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(discount_type="amount", percent_off=None,
                             amount_off_cents=1000, currency=None))


def test_validate_amount_rejects_percent():
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(discount_type="amount", percent_off=Decimal("20"),
                             amount_off_cents=1000, currency="usd"))


def test_validate_repeating_needs_months():
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(duration="repeating", duration_in_months=None))
    ps.validate_promo(_p(duration="repeating", duration_in_months=3))


def test_validate_bad_code():
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(code="bad code!!"))


def test_validate_bad_max_redemptions():
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(max_redemptions=0))


# --- provisioning param shaping ---------------------------------------------

def test_provision_percent_params(monkeypatch):
    cap = {}
    monkeypatch.setattr(stripe.Coupon, "create",
                        lambda **kw: (cap.__setitem__("coupon", kw) or _Obj("cpn_x")))
    monkeypatch.setattr(stripe.PromotionCode, "create",
                        lambda **kw: (cap.__setitem__("promo", kw) or _Obj("promo_x")))
    expires = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    cid, pid = ps.provision_promo_coupon(
        _p(code="launch20", percent_off=Decimal("20"), max_redemptions=50, expires_at=expires))
    assert (cid, pid) == ("cpn_x", "promo_x")
    assert cap["coupon"]["percent_off"] == 20.0
    assert cap["coupon"]["duration"] == "once"
    assert len(cap["coupon"]["name"]) <= 40
    assert "coupon" not in cap["promo"]
    assert cap["promo"]["promotion"] == {"type": "coupon", "coupon": "cpn_x"}
    assert cap["promo"]["code"] == "LAUNCH20"
    assert cap["promo"]["max_redemptions"] == 50
    assert cap["promo"]["expires_at"] == int(expires.timestamp())


def test_validate_rejects_past_expiry():
    past = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
    with pytest.raises(ps.PromoError):
        ps.validate_promo(_p(expires_at=past))


def test_provision_naive_expiry_treated_as_utc(monkeypatch):
    cap = {}
    monkeypatch.setattr(stripe.Coupon, "create",
                        lambda **kw: (cap.__setitem__("coupon", kw) or _Obj("cpn")))
    monkeypatch.setattr(stripe.PromotionCode, "create",
                        lambda **kw: (cap.__setitem__("promo", kw) or _Obj("promo")))
    naive = dt.datetime(2030, 6, 1, 12, 0, 0)   # no tzinfo, future
    ps.provision_promo_coupon(_p(code="UTCTEST", expires_at=naive))
    assert cap["promo"]["expires_at"] == int(naive.replace(tzinfo=dt.timezone.utc).timestamp())


def test_provision_amount_params(monkeypatch):
    cap = {}
    monkeypatch.setattr(stripe.Coupon, "create",
                        lambda **kw: (cap.__setitem__("coupon", kw) or _Obj("cpn_a")))
    monkeypatch.setattr(stripe.PromotionCode, "create",
                        lambda **kw: (cap.__setitem__("promo", kw) or _Obj("promo_a")))
    ps.provision_promo_coupon(_p(code="TENOFF", discount_type="amount", percent_off=None,
                                 amount_off_cents=1000, currency="USD",
                                 duration="repeating", duration_in_months=3))
    assert cap["coupon"]["amount_off"] == 1000
    assert cap["coupon"]["currency"] == "usd"   # normalized
    assert cap["coupon"]["duration"] == "repeating"
    assert cap["coupon"]["duration_in_months"] == 3
    assert "percent_off" not in cap["coupon"]
