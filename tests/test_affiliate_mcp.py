"""Affiliate self-service over the gateway + MCP (GET /v1/affiliate/me ->
my_affiliate_program). DB, auth and metering are mocked; the scoping rules are the point:
only the caller's own row, never service/demo/chatbot principals, no customer identities."""
import asyncio
import datetime as dt
import json
import os
import sys
import uuid
from decimal import Decimal

import pytest

from apiserver import affiliate_view, tiers

pytestmark = pytest.mark.unit

UID = str(uuid.uuid4())
AFF_ID = uuid.uuid4()


def _aff(**kw):
    row = {"id": AFF_ID, "code": "ANNE", "name": "Anne Lee", "status": "active",
           "commission_model": "recurring", "discount_pct": Decimal("20.00"),
           "commission_pct": Decimal("30.00"), "discount_pct_monthly": None,
           "commission_pct_monthly": Decimal("25.00"), "payout_method": "paypal",
           "payout_email": "pay@example.com", "tax_form_type": None, "tax_form_received_at": None}
    row.update(kw)
    return row


@pytest.fixture
def fake_db(monkeypatch):
    calls = {}
    from apiserver import db

    def get_aff(user_id, email=None):
        calls["user"] = (user_id, email)
        return calls.get("row", _aff())
    monkeypatch.setattr(db, "get_affiliate_for_user", get_aff)
    monkeypatch.setattr(db, "affiliate_funnel", lambda a, days=30: {
        "days": days, "clicks_recent": 12, "clicks_total": 40, "signups_recent": 3,
        "signups_total": 9, "in_trial": 2, "paying_total": 4})
    monkeypatch.setattr(db, "affiliate_payout_rows", lambda a: [
        {"period_start": dt.date(2026, 10, 1), "currency": "usd", "commission_amount": Decimal("-12.00"),
         "status": "void", "external_ref": "carried:2026-11", "paid_at": None},
        {"period_start": dt.date(2026, 9, 1), "currency": "usd", "commission_amount": Decimal("45.50"),
         "status": "pending", "external_ref": None, "paid_at": None},
        {"period_start": dt.date(2026, 8, 1), "currency": "usd", "commission_amount": Decimal("60.00"),
         "status": "paid", "external_ref": "PP-1", "paid_at": dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)},
    ])
    return calls


def _cust(user_id=UID, tier="analyst", **ent):
    e = dict(tiers.tier_for("dev"))
    e.update(ent)
    return {"user_id": user_id, "email": "anne@example.com", "tier": tier, "entitlements": e}


def test_build_scopes_to_caller_and_has_no_customer_identities(fake_db):
    payload, status = affiliate_view.build(_cust(), "tw2-dev.trxstat.com", today=dt.date(2026, 11, 16))
    assert status == 200
    assert fake_db["user"] == (UID, "anne@example.com")
    assert payload["links"]["join_page"] == "https://tw2-dev.trxstat.com/join/ANNE"
    assert payload["links"]["home_with_code"] == "https://tw2-dev.trxstat.com/?code=ANNE"
    assert payload["terms"]["annual_plans"] == {"discount_pct": 20, "commission_pct": 30}
    assert payload["terms"]["monthly_plans"] == {"discount_pct": 20, "commission_pct": 25}
    assert payload["funnel"]["paying_total"] == 4
    usd = payload["earnings"]["totals_by_currency"]["usd"]
    assert usd["pending"] == 45.5 and usd["paid"] == 60.0
    assert payload["earnings"]["recent_statements"][0]["carried_forward_to"] == "2026-11"
    assert payload["payout"]["next_statement_date"] == "2026-12-02"
    assert payload["payout"]["tax_form"]["on_file"] is False
    assert "W-9" in payload["payout"]["tax_form"]["action"]
    assert "pay@example.com" not in json.dumps(payload)      # only a boolean for the payout email
    promo = payload["promo"]
    assert all(promo["disclosure"] in t["text"] for t in promo["templates"])
    assert all("ANNE" in t["text"] for t in promo["templates"])
    assert "—" not in json.dumps(payload)                # no em-dashes in content


def test_tax_form_on_file_and_inactive_status(fake_db):
    fake_db["row"] = _aff(status="paused", tax_form_type="w9",
                          tax_form_received_at=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    payload, status = affiliate_view.build(_cust(), "h", today=dt.date(2026, 11, 1))
    assert status == 200
    assert payload["payout"]["tax_form"] == {"on_file": True, "type": "w9",
                                             "received_at": "2026-10-01T00:00:00+00:00", "action": None}
    assert payload["payout"]["next_statement_date"] == "2026-11-02"
    assert "status_note" in payload


def test_non_affiliate_gets_404(fake_db):
    fake_db["row"] = None
    payload, status = affiliate_view.build(_cust(), "h")
    assert status == 404 and payload["error"]["code"] == "not_affiliate"


@pytest.mark.parametrize("cust", [
    _cust(user_id="demo", tier="demo"),
    _cust(user_id="cb:" + UID),
    _cust(service=True),                    # a service principal that never resolved to a user
])
def test_non_person_principals_refused_without_db(fake_db, cust):
    payload, status = affiliate_view.build(cust, "h")
    assert status == 403
    assert "user" not in fake_db


def test_gateway_route(monkeypatch, fake_db):
    from apiserver import app as appmod, auth, ml_quota
    a = appmod.app if hasattr(appmod, "app") else appmod.create_app()
    a.config.update(TESTING=True)
    monkeypatch.setattr(auth, "resolve_customer", lambda key: _cust())
    monkeypatch.setattr(auth, "check_rate_limit", lambda cust: (True, {}))
    monkeypatch.setattr(auth, "record_usage", lambda *x, **k: None)
    monkeypatch.setattr(ml_quota, "remaining", lambda cust: None)
    r = a.test_client().get("/v1/affiliate/me", headers={"Authorization": "Bearer tw_live_x"})
    assert r.status_code == 200
    assert r.json["code"] == "ANNE"


def test_mcp_tool_lead_and_payload(monkeypatch, fake_db):
    pytest.importorskip("mcp")  # MCP SDK lives in venv-api; skip cleanly in the main venv
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcpserver"))
    import server
    payload, _ = affiliate_view.build(_cust(), "h", today=dt.date(2026, 11, 16))

    async def fake_get(path, params=None):
        assert path == "/affiliate/me"
        return json.loads(json.dumps(payload))
    monkeypatch.setattr(server, "_get", fake_get)
    out = asyncio.run(server.my_affiliate_program(ctx=None))
    assert out.startswith("Affiliate code ANNE (active). Last 30 days: 12 link visits, 3 signups")
    assert "Tax form not on file" in out
    assert '"disclosure"' in out
