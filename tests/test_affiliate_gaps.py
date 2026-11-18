"""Hermetic tests for the 2026-11 affiliate-gap fixes (no DB / no network)."""
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(_REPO_ROOT), str(_REPO_ROOT / "web")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import affiliate_service as afs  # noqa: E402
import affiliate_agreement as agr  # noqa: E402
import affiliate_report as rpt  # noqa: E402


DETAIL = [
    {"kind": "payment", "customer": "cus_1"},
    {"kind": "payment", "customer": "cus_1"},      # same customer, 2nd invoice
    {"kind": "payment", "customer": "cus_2"},
    {"kind": "refund", "customer": "cus_2"},
]


def test_statement_customer_count_is_distinct_payers():
    assert rpt._customer_count(DETAIL) == 2


def test_portal_rows_summary():
    from affiliate_portal import routes
    rows = routes._rows_to_json([{"currency": "usd", "gross_revenue": Decimal("10.00"),
                                  "commission_amount": Decimal("3.00"), "detail": DETAIL}])
    assert rows[0]["payments"] == 3
    assert rows[0]["reversals"] == 1
    assert rows[0]["customers"] == 2
    back = routes._rows_from_json(rows)
    assert back[0]["commission_amount"] == Decimal("3.00")


def test_dashboard_link():
    assert agr.dashboard_link().endswith("/account/affiliate")


def test_signing_email_mentions_dashboard(monkeypatch):
    sent = {}

    def fake_send(**kw):
        sent.update(kw)
        return True
    import email_utils
    monkeypatch.setattr(email_utils, "resend_send_email", fake_send)
    monkeypatch.setattr(agr, "signing_url", lambda a: "https://x/affiliate/sign/t")
    aff = SimpleNamespace(id="1", code="ANNE", name="Anne Lee", email="anne@example.com",
                          agreement_token_version=0)
    assert agr.email_signing_link(aff)
    assert "/account/affiliate" in sent["body_text"]
    assert "/account/affiliate" in sent["html"]


def test_statement_negative_month(monkeypatch):
    sent = []
    import email_utils
    monkeypatch.setattr(email_utils, "resend_send_email",
                        lambda **kw: sent.append(kw) or True)
    rows = [{"affiliate_id": "a", "code": "ANNE", "name": "Anne", "email": "anne@example.com",
             "payout_method": "paypal", "payout_email": "p@example.com", "currency": "usd",
             "commission_amount": Decimal("-12.00"), "detail": [{"kind": "refund"}]}]
    assert rpt.send_monthly_statements(rows, 2026, 5) == 1
    body = sent[0]["body_text"]
    assert "Net adjustment" in body
    assert "send your payout" not in body
    assert "/account/affiliate" in body


def test_signup_referral_stamps_first_touch(monkeypatch):
    aff = SimpleNamespace(id="aff-1", email="anne@example.com", code="ANNE")
    monkeypatch.setattr(afs, "active_affiliate_by_code", lambda s, raw: aff)
    sess = SimpleNamespace(commit=lambda: None)
    u = SimpleNamespace(email="buyer@example.com", referred_by_affiliate_id=None, referred_at=None)
    assert afs.record_signup_referral(sess, u, "anne") is True
    assert u.referred_by_affiliate_id == "aff-1" and u.referred_at is not None
    # never overwritten
    other = SimpleNamespace(id="aff-2", email="b@example.com", code="BOB")
    monkeypatch.setattr(afs, "active_affiliate_by_code", lambda s, raw: other)
    assert afs.record_signup_referral(sess, u, "bob") is False
    assert u.referred_by_affiliate_id == "aff-1"


def test_signup_referral_skips_self_and_unknown(monkeypatch):
    sess = SimpleNamespace(commit=lambda: None)
    me = SimpleNamespace(email="Anne@Example.com", referred_by_affiliate_id=None, referred_at=None)
    aff = SimpleNamespace(id="aff-1", email="anne@example.com", code="ANNE")
    monkeypatch.setattr(afs, "active_affiliate_by_code", lambda s, raw: aff)
    assert afs.record_signup_referral(sess, me, "ANNE") is False
    monkeypatch.setattr(afs, "active_affiliate_by_code", lambda s, raw: None)
    assert afs.record_signup_referral(sess, me, "NOPE") is False


# --- expert scorecard (Layer 1) --------------------------------------------
import datetime as _dt  # noqa: E402
import expert_scorecard as esc  # noqa: E402


def test_score_call_long_short():
    assert esc.score_call({"direction": "long"}, 100, 110) == ("win", Decimal("10.0000"))
    assert esc.score_call({"direction": "long"}, 100, 95)[0] == "loss"
    assert esc.score_call({"direction": "short"}, 100, 95) == ("win", Decimal("-5.0000"))
    assert esc.score_call({"direction": "short"}, 100, 100)[0] == "loss"   # flat is not a win
    assert esc.score_call({"direction": "long"}, 0, 110) == ("void", None)


def test_retracted_after_entry_still_counts():
    call = {"entry_date": "2026-10-01", "exit_date": "2026-10-20"}
    late = SimpleNamespace(status="retracted", declared_call=call,
                           retracted_at=_dt.datetime(2026, 10, 5, tzinfo=_dt.timezone.utc))
    early = SimpleNamespace(status="retracted", declared_call=call,
                            retracted_at=_dt.datetime(2026, 9, 28, tzinfo=_dt.timezone.utc))
    today = _dt.date(2026, 11, 1)
    assert esc._counts_in_record(late, today) is True
    assert esc._counts_in_record(early, today) is False


# --- partner guide ----------------------------------------------------------
def test_partner_guide_personalized_and_safe():
    from affiliate_portal import routes
    aff = SimpleNamespace(code="ZED", name="Zed", page_display_name=None, status="active",
                          payout_method="wise", tax_form_received_at=None,
                          discount_pct=Decimal("20"), commission_pct=Decimal("30"),
                          discount_pct_monthly=None, commission_pct_monthly=None,
                          stripe_coupon_id_monthly=None, commission_model="recurring")
    md = routes._guide_for(aff)
    assert md.startswith("# TradeWave Partner Guide")
    assert "Referral code: `ZED`" in md and "/join/ZED" in md
    assert "Tax form on file: NO" in md
    assert "Instructions for AI assistants" in md
    assert "—" not in md                        # house style: no em-dashes
    html = routes._render_guide(routes._guide_md())
    assert "<table>" in html and "<script" not in html
