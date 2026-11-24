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
        discount_pct_monthly=None, commission_pct_monthly=None,
        terms=None, terms_id=None,
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


def test_agreement_version_is_v2():
    assert agr.AGREEMENT_VERSION == "2026-11-24"


def test_record_signature_restamps_an_older_version_label():
    """A partner paused by the v2 migration still carries the v1 label; the
    signature must record the version of the text actually shown."""
    aff = _aff(agreement_version="2026-06-11")
    agr.record_signature(aff, "Anne Smith", "1.2.3.4", "ua")
    assert aff.agreement_version == agr.AGREEMENT_VERSION
    assert "Agreement version 2026-11-24" in aff.agreement_snapshot
    assert "v2026-11-24" in aff.agreement_snapshot


def test_old_version_snapshot_is_left_alone():
    """Signed snapshots are immutable stored text: nothing here re-renders one."""
    old = "<!-- TradeWave Affiliate Program Agreement v2026-06-11 --><p>30% of Net Revenue</p>"
    aff = _aff(agreement_version="2026-06-11", agreement_signed_name="Anne",
               agreement_signed_at=object(), agreement_snapshot=old, status="active")
    with pytest.raises(agr.AlreadySigned):
        agr.record_signature(aff, "Anne", "1.1.1.1", "ua")
    assert aff.agreement_snapshot == old
    assert aff.agreement_version == "2026-06-11"


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


def test_body_html_is_version_2():
    html = agr.agreement_body_html()
    for phrase in ("Commission Pool", "Customer Discount", "Promotion Rate",
                   "Renewal Rate", "Renewal Term", "Activity Requirement",
                   "12 months plus 30 days", "grace period",
                   "Paused accounts", "Payout minimum", "Legacy pricing plans",
                   "FTC", "Confidentiality", "Indemnification"):
        assert phrase in html, phrase
    # version 1 vocabulary is gone
    for phrase in ("Net Revenue", "Audience Discount", "Commission Model"):
        assert phrase not in html, phrase
    # the acceptance-table dollar examples are in the text
    for amount in ("$45", "$30", "$49.50", "$99.75", "$15"):
        assert amount in html, amount
    assert "\u2014" not in html            # no em dashes in partner content


def test_agreement_md_has_no_em_dash_and_sections_are_consecutive():
    import re
    raw = (_REPO_ROOT / "docs" / "AFFILIATE_AGREEMENT.md").read_text(encoding="utf-8")
    assert "\u2014" not in raw
    nums = [int(n) for n in re.findall(r"^## (\d+)\. ", raw, flags=re.M)]
    assert nums == list(range(1, 16))
    # every sub-clause number runs 1..n inside its section
    for sec in nums:
        subs = [int(n) for n in re.findall(r"^%d\.(\d+) " % sec, raw, flags=re.M)]
        assert subs == list(range(1, len(subs) + 1)), (sec, subs)


# --- Exhibit A (agreement version 2) ----------------------------------------

def _terms(**kw):
    base = dict(id=1, version="v2-5y", pool_pct=Decimal("50"),
                max_discount_pct=Decimal("25"), promo_commission_pct=Decimal("50"),
                renewal_pct=Decimal("25"), renewal_years=5, activity_rule_months=12)
    base.update(kw)
    return SimpleNamespace(**base)


def _rows(ex):
    return dict(ex["rows"])


def test_exhibit_default_terms_formatting():
    """No terms row on the partner -> the service default (v2-5y)."""
    ex = agr.exhibit(_aff(discount_pct=Decimal("20.00")))
    assert ex["code"] == "ANNE"
    assert ex["payout_method"] == "PAYPAL"
    assert ex["pool_pct"] == "50"
    assert ex["max_discount_pct"] == "25"
    assert ex["discount_pct"] == "20"
    assert ex["commission_pct"] == "30"          # pool - discount
    assert ex["promo_pct"] == "50"
    assert ex["renewal_pct"] == "25"
    assert ex["renewal_term"] == "Commission Years 2-5"
    assert ex["activity_rule_months"] == 12
    assert ex["payout_minimum"] == "$50"
    assert ex["is_split"] is False
    rows = _rows(ex)
    assert list(rows)[:4] == ["Affiliate", "Contact email", "Referral Code", "Referral Link"]
    assert rows["Commission Pool"] == "50% of the List Price (first year)"
    assert rows["Maximum Customer Discount"] == "25%"
    assert rows["Promotion Rate"].startswith("50% of the Amount Paid")
    assert "$50.00 on a $100.00 sale" in rows["Promotion Rate"]
    assert rows["Renewal Rate"] == "25% of the Amount Paid"
    assert rows["Renewal Term"] == "Commission Years 2-5"
    assert ("1 New Paying Customer in the trailing 12 months plus a 30-day grace period"
            in rows["Activity Requirement"])
    assert ex["activity_grace_days"] == 30
    assert "trials do not count" in rows["Activity Requirement"]
    assert rows["Payout minimum"].startswith("$50")
    assert rows["Payout method"] == "PAYPAL - anne@pay.com"


@pytest.mark.parametrize("renewal_years,label,phrase", [
    (5, "Commission Years 2-5", "(years 2-5)"),
    (10, "Commission Years 2-10", "(years 2-10)"),
    (None, "Lifetime", "(any later year)"),
])
def test_exhibit_renewal_term(renewal_years, label, phrase):
    aff = _aff(terms=_terms(renewal_years=renewal_years))
    ex = agr.exhibit(aff)
    assert ex["renewal_term"] == label
    assert _rows(ex)["Renewal Term"] == label
    assert ex["renewal_lifetime"] is (renewal_years is None)
    assert phrase in ex["example"]["renewal_text"]
    assert "you earn $25.00" in ex["example"]["renewal_text"]
    agr.record_signature(aff, "Anne Smith", "1.2.3.4", "ua")
    assert ">%s<" % label in aff.agreement_snapshot


@pytest.mark.parametrize("discount,pays,earns,rate", [
    ("0", "$100.00", "$50.00", "50"),
    ("5", "$95.00", "$45.00", "45"),
    ("20", "$80.00", "$30.00", "30"),
    ("25", "$75.00", "$25.00", "25"),
])
def test_exhibit_worked_example(discount, pays, earns, rate):
    """$100 plan at the partner's discount: the acceptance-table dollars."""
    ex = agr.exhibit(_aff(discount_pct=Decimal(discount)))
    eg = ex["example"]
    assert (eg["list_price"], eg["customer_pays"], eg["partner_earns"], eg["retained"]) == (
        "$100.00", pays, earns, "$50.00")
    assert ex["commission_pct"] == rate
    text = _rows(ex)["Worked example"]
    assert ("at your current %s%% Customer Discount, the customer pays %s, you earn %s "
            "and TradeWave keeps $50.00." % (discount, pays, earns)) in text
    assert _rows(ex)["Your Customer Discount - annual plans"] == (
        "%s%% off the List Price (first year). You earn %s%% of the List Price."
        % (discount, rate))


def test_exhibit_discount_per_interval():
    aff = _aff(discount_pct=Decimal("20.00"), discount_pct_monthly=Decimal("10.00"))
    ex = agr.exhibit(aff)
    assert ex["is_split"] is True
    assert ex["annual"] == {"discount_pct": "20", "commission_pct": "30"}
    assert ex["monthly"] == {"discount_pct": "10", "commission_pct": "40"}
    rows = _rows(ex)
    assert rows["Your Customer Discount - monthly plans"] == (
        "10% off the List Price (first 12 months). You earn 40% of the List Price.")
    # the worked example uses the annual discount
    assert ex["example"]["customer_pays"] == "$80.00"


def test_exhibit_reads_the_partner_terms_row():
    """Non-default terms flow through from the backend terms object."""
    aff = _aff(discount_pct=Decimal("10"),
               terms=_terms(version="custom", pool_pct=Decimal("40"),
                            max_discount_pct=Decimal("15"), promo_commission_pct=Decimal("30"),
                            renewal_pct=Decimal("10"), renewal_years=10,
                            activity_rule_months=6))
    ex = agr.exhibit(aff)
    assert (ex["pool_pct"], ex["max_discount_pct"], ex["promo_pct"], ex["renewal_pct"]) == (
        "40", "15", "30", "10")
    assert ex["terms_version"] == "custom"
    assert ex["commission_pct"] == "30"
    assert ex["example"]["partner_earns"] == "$30.00"
    assert ex["example"]["retained"] == "$60.00"
    assert ex["example"]["renewal_earns"] == "$10.00"
    assert "trailing 6 months plus a 30-day grace period" in ex["activity_rule"]


def test_exhibit_grace_days_follow_the_backend_constant(monkeypatch):
    import affiliate_service as afs
    monkeypatch.setattr(afs, "ACTIVITY_GRACE_DAYS", 45, raising=False)
    ex = agr.exhibit(_aff())
    assert ex["activity_grace_days"] == 45
    assert "trailing 12 months plus a 45-day grace period" in ex["activity_rule"]
    monkeypatch.setattr(afs, "ACTIVITY_GRACE_DAYS", 0, raising=False)
    assert "trailing 12 months, measured" in agr.exhibit(_aff())["activity_rule"]


def test_exhibit_uses_terms_for_when_given_a_session(monkeypatch):
    import affiliate_service as afs
    seen = {}

    def fake_terms_for(session, affiliate):
        seen["args"] = (session, affiliate)
        return _terms(version="v2-lifetime", renewal_years=None)

    monkeypatch.setattr(afs, "terms_for", fake_terms_for)
    aff, session = _aff(), object()
    ex = agr.exhibit(aff, session)
    assert seen["args"] == (session, aff)
    assert ex["renewal_term"] == "Lifetime"


def test_exhibit_clamps_a_legacy_discount_above_the_cap():
    """A pre-v2 row above the 25% cap must not break the signing page."""
    ex = agr.exhibit(_aff(discount_pct=Decimal("40.00")))
    assert ex["discount_pct"] == "25"
    assert ex["example"]["customer_pays"] == "$75.00"


def test_snapshot_contains_every_exhibit_row_and_no_em_dash():
    aff = _aff(discount_pct=Decimal("0"))
    agr.record_signature(aff, "Anne Smith", "1.2.3.4", "ua")
    snap = aff.agreement_snapshot
    import html as _html
    for label, value in agr.exhibit(aff)["rows"]:
        assert _html.escape(label) in snap
        assert _html.escape(value) in snap
    assert "the customer pays $100.00, you earn $50.00" in snap
    assert "Net Revenue" not in snap
    assert "\u2014" not in snap


def test_fmt_money():
    assert agr._fmt_money(9975) == "$99.75"
    assert agr._fmt_money(10000) == "$100.00"
    assert agr._fmt_money(0) == "$0.00"


def test_fmt_pct_trims_trailing_zeros():
    assert agr._fmt_pct(Decimal("15.50")) == "15.5"
    assert agr._fmt_pct(Decimal("30.00")) == "30"
    assert agr._fmt_pct(None) == ""
