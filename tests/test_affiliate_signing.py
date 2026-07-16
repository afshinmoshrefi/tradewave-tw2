"""Unit tests for the affiliate agreement e-signature core (web/affiliate_agreement.py).

Hermetic: no DB, no network. record_signature() operates on a duck-typed
affiliate object (same approach as test_affiliate.py), token signing is pure,
and body rendering reads the committed docs/AFFILIATE_AGREEMENT.md.
"""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "web")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import pytest  # noqa: E402
import affiliate_agreement as agr  # noqa: E402


def _aff(**kw):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        code="ANNE", name="Anne", email="anne@example.com",
        payout_method="paypal", payout_email="anne@pay.com",
        discount_pct=Decimal("20.00"), commission_pct=Decimal("30.00"),
        commission_model="recurring", status="paused",
        agreement_version=None, agreement_signed_name=None,
        agreement_signed_at=None, agreement_signed_ip=None,
        agreement_signed_user_agent=None, agreement_snapshot=None,
        agreement_token_version=0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --- token signing ----------------------------------------------------------

def test_token_roundtrip():
    tok = agr.make_sign_token("abc-123", 5)
    assert agr.verify_sign_token(tok) == {"aid": "abc-123", "tv": 5}


def test_token_garbage_returns_none():
    assert agr.verify_sign_token("not-a-real-token") is None


def test_token_tampered_returns_none():
    tok = agr.make_sign_token("11111111-1111-1111-1111-111111111111", 0)
    assert agr.verify_sign_token(tok[:-4] + "AAAA") is None


def test_token_expired_returns_none():
    tok = agr.make_sign_token("abc", 0)
    # max_age=-1 => any token is already older than the allowed age.
    assert agr.verify_sign_token(tok, max_age=-1) is None


def test_signing_url_shape_and_decodes():
    aff = _aff(agreement_token_version=2)
    url = agr.signing_url(aff)
    assert "/affiliate/sign/" in url
    tok = url.rsplit("/", 1)[-1]
    assert agr.verify_sign_token(tok) == {"aid": aff.id, "tv": 2}


def test_referral_link_shape():
    assert agr.referral_link(_aff()).endswith("/?code=ANNE")


# --- record_signature (the testable core) -----------------------------------

def test_record_signature_sets_fields_and_activates():
    aff = _aff()
    agr.record_signature(aff, "  Anne Smith  ", "1.2.3.4", "Mozilla/5.0")
    assert aff.agreement_signed_name == "Anne Smith"   # trimmed
    assert aff.agreement_signed_at is not None
    assert aff.agreement_signed_ip == "1.2.3.4"
    assert aff.agreement_signed_user_agent == "Mozilla/5.0"
    assert aff.agreement_version == agr.AGREEMENT_VERSION
    assert aff.agreement_snapshot and "Exhibit A" in aff.agreement_snapshot
    assert aff.status == "active"                       # paused -> active gate


def test_record_signature_is_idempotent():
    aff = _aff()
    agr.record_signature(aff, "Anne", "1.1.1.1", "ua")
    with pytest.raises(agr.AlreadySigned):
        agr.record_signature(aff, "Anne", "1.1.1.1", "ua")


def test_record_signature_rejects_blank_name():
    aff = _aff()
    with pytest.raises(agr.AgreementError):
        agr.record_signature(aff, "  ", "1.1.1.1", "ua")
    assert aff.agreement_signed_at is None              # nothing written on failure
    assert aff.status == "paused"


def test_record_signature_rejects_terminated():
    aff = _aff(status="terminated")
    with pytest.raises(agr.AgreementError):
        agr.record_signature(aff, "Anne", "1.1.1.1", "ua")
    assert aff.agreement_signed_at is None              # terminated -> can't sign


# --- presentation -----------------------------------------------------------

def test_snapshot_escapes_malicious_signed_name():
    """Stored-XSS guard: an affiliate-typed name with markup is html-escaped in the
    snapshot (which is rendered with |safe to the admin / inline in email)."""
    aff = _aff()
    agr.record_signature(aff, "<script>alert(1)</script>", "1.1.1.1", "ua")
    assert "<script>alert(1)</script>" not in aff.agreement_snapshot
    assert "&lt;script&gt;" in aff.agreement_snapshot


def test_body_html_single_sourced_and_trimmed():
    html = agr.agreement_body_html()
    assert "<h" in html                       # rendered markdown headings
    assert "Indemnification" in html          # a late section is included
    assert "NOT LEGAL ADVICE" not in html     # internal DRAFT banner stripped
    assert "By signing or clicking" not in html   # static Acceptance section dropped


def test_exhibit_formatting():
    aff = _aff(discount_pct=Decimal("20.00"), commission_pct=Decimal("30.00"),
               commission_model="duration_12mo")
    ex = agr.exhibit(aff)
    assert ex["discount_pct"] == "20"
    assert ex["commission_pct"] == "30"
    assert ex["model_label"] == "First 12 months"
    assert ex["code"] == "ANNE"
    assert ex["payout_method"] == "PAYPAL"


def test_fmt_pct_trims_trailing_zeros():
    assert agr._fmt_pct(Decimal("15.50")) == "15.5"
    assert agr._fmt_pct(Decimal("30.00")) == "30"
    assert agr._fmt_pct(None) == ""
