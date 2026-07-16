"""Gateway API-key cache and entitlement-boundary tests."""

import pytest

from apiserver import auth, settings, tiers


def _row(user_id="u1"):
    return {
        "user_id": user_id,
        "email": "u@example.com",
        "tier": "analyst",
        "api_tier": "dev",
        "roles": ["user"],
        "reverse_trial_ends_at": None,
        "key_id": "k1",
    }


def test_successful_lookup_is_cached_but_negative_lookup_is_not(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_HMAC_SECRET", "test-secret")
    monkeypatch.setattr(settings, "API_KEY_CACHE_TTL_SECONDS", 30)
    monkeypatch.setattr(settings, "API_KEY_CACHE_MAX_ENTRIES", 8)
    monkeypatch.setattr(tiers, "api_tier_from_user", lambda row: "dev")
    auth._key_cache.clear()
    calls = []

    def lookup(key_hash):
        calls.append(key_hash)
        return _row() if len(calls) <= 1 else None

    monkeypatch.setattr(auth.db, "get_user_by_key_hash", lookup)
    assert auth.resolve_customer("tw_live_one")["user_id"] == "u1"
    assert auth.resolve_customer("tw_live_one")["user_id"] == "u1"
    assert len(calls) == 1
    assert auth.resolve_customer("tw_live_missing") is None
    assert auth.resolve_customer("tw_live_missing") is None
    assert len(calls) == 3


def test_cache_is_size_bounded(monkeypatch):
    monkeypatch.setattr(settings, "API_KEY_HMAC_SECRET", "test-secret")
    monkeypatch.setattr(settings, "API_KEY_CACHE_TTL_SECONDS", 30)
    monkeypatch.setattr(settings, "API_KEY_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(tiers, "api_tier_from_user", lambda row: "dev")
    auth._key_cache.clear()
    monkeypatch.setattr(auth.db, "get_user_by_key_hash", lambda key_hash: _row(key_hash[-8:]))
    for raw in ("tw_live_a", "tw_live_b", "tw_live_c"):
        assert auth.resolve_customer(raw)
    assert len(auth._key_cache) == 2


def test_internal_service_tier_requires_durable_service_role(
    monkeypatch, caplog,
):
    monkeypatch.setattr(settings, "API_KEY_HMAC_SECRET", "test-secret")
    monkeypatch.setattr(settings, "API_KEY_CACHE_TTL_SECONDS", 0)
    auth._key_cache.clear()

    service = _row("svc")
    service.update({
        "tier": "explorer",
        "api_tier": "mcp",
        "roles": ["service_account"],
    })
    ordinary = dict(service, user_id="ordinary", roles=["user"])
    rows = iter([service, ordinary])
    monkeypatch.setattr(auth.db, "get_user_by_key_hash", lambda _: next(rows))

    resolved_service = auth.resolve_customer("tw_svc_service")
    assert resolved_service["tier"] == "mcp"
    assert resolved_service["entitlements"]["service"] is True
    assert resolved_service["entitlements"]["workos_principal"] is True

    resolved_ordinary = auth.resolve_customer("tw_svc_untrusted")
    assert resolved_ordinary["tier"] == "free"
    assert resolved_ordinary["entitlements"].get("service") is not True
    assert "without service_account role" in caplog.text


def _ordinary_explorer(api_tier):
    return {
        "user_id": "ordinary-workos-user",
        "email": "ordinary@example.com",
        "tier": "explorer",
        "api_tier": api_tier,
        "roles": ["user"],
        "reverse_trial_ends_at": None,
    }


@pytest.mark.parametrize("api_tier", ["mcp", "chatbot", "demo", "unknown-tier"])
def test_workos_ordinary_user_cannot_merge_internal_or_unknown_api_tier(
    api_tier, caplog,
):
    label, entitlements, teaser = auth._resolve_mcp(_ordinary_explorer(api_tier))

    assert label == "explorer"
    assert entitlements == tiers.mcp_tier_for("explorer")
    assert teaser == auth._NO_TEASER
    assert entitlements.get("service") is not True
    assert entitlements.get("demo") is not True
    assert "ignoring non-sold explicit api_tier" in caplog.text


@pytest.mark.parametrize("api_tier", list(tiers.API_TIERS))
def test_workos_ordinary_user_merges_valid_sold_api_tier(api_tier):
    label, entitlements, teaser = auth._resolve_mcp(_ordinary_explorer(api_tier))

    expected = tiers.merge_entitlements(
        tiers.mcp_tier_for("explorer"), tiers.tier_for(api_tier)
    )
    # A standalone API subscription may widen markets and request limits, but it does
    # not bypass the steady Explorer in-chat ML gate.
    expected["ml_daily_limit"] = tiers.mcp_tier_for("explorer")["ml_daily_limit"]

    assert label == "explorer"
    assert entitlements == expected
    assert teaser == auth._NO_TEASER
    assert entitlements.get("service") is not True
