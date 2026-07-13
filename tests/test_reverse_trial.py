"""
Coverage for the REVERSE-TRIAL freemium gate (web/app.py).

The contract (owner decision 2026-06-10, supersedes the launch open-paywall):

  * `effective_tier(user)` returns 'strategist' ONLY for an 'explorer' whose
    reverse_trial_ends_at is in the future; every other (tier, deadline)
    combination returns the raw tier. users.tier is NEVER mutated - the
    elevation exists only at token-mint time, so expiry is implicit (no cron).
  * `generate_ltk()` mints the EFFECTIVE tier/legacy_level claims, so an
    in-trial explorer reaches the appserver as a Strategist (level '6').
  * `reverse_trial_ends_at_iso()` is non-empty IFF the elevation is in effect
    (what app_index injects as window.tw2_trial_ends_at / /api/me returns as
    trial_ends_at).
  * `lazy_create_user()` stamps reverse_trial_ends_at = now+7d on the CREATE
    path only; the match/update paths never touch it.
  * Billing reads stay RAW: effective_tier must never elevate a paid tier.
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

@pytest.fixture
def app_module():
    """Import web.app once. Subsequent tests reuse the same module."""
    return importlib.import_module("app")


def _user(tier, ends_at, **kw):
    """Duck-typed stand-in for a models.User row - effective_tier only reads
    .tier and .reverse_trial_ends_at; generate_ltk additionally reads
    id/workos_user_id/email/roles."""
    return SimpleNamespace(
        id=kw.get("id", uuid4()),
        workos_user_id=kw.get("workos_user_id", "user_test123"),
        email=kw.get("email", "rt@example.com"),
        roles=kw.get("roles", ["user"]),
        tier=tier,
        reverse_trial_ends_at=ends_at,
    )


FUTURE = datetime.now(timezone.utc) + timedelta(days=3)
PAST = datetime.now(timezone.utc) - timedelta(hours=1)


# ---------------------------------------------------------------------
# 1. effective_tier truth table
# ---------------------------------------------------------------------

@pytest.mark.unit
class TestEffectiveTier:
    def test_explorer_in_trial_elevates_to_strategist(self, app_module):
        assert app_module.effective_tier(_user("explorer", FUTURE)) == "strategist"

    def test_explorer_with_lapsed_trial_stays_explorer(self, app_module):
        assert app_module.effective_tier(_user("explorer", PAST)) == "explorer"

    def test_explorer_without_trial_stays_explorer(self, app_module):
        assert app_module.effective_tier(_user("explorer", None)) == "explorer"

    def test_none_tier_coerces_to_explorer_and_elevates(self, app_module):
        # lazy rows / defensive: tier=None reads as explorer everywhere else.
        assert app_module.effective_tier(_user(None, FUTURE)) == "strategist"

    def test_paid_tiers_never_elevated(self, app_module):
        # Billing safety: a stray reverse_trial_ends_at on a paid row must be
        # inert - the elevation is explorer-only by definition.
        assert app_module.effective_tier(_user("analyst", FUTURE)) == "analyst"
        assert app_module.effective_tier(_user("strategist", FUTURE)) == "strategist"
        assert app_module.effective_tier(_user("canceled", FUTURE)) == "canceled"


# ---------------------------------------------------------------------
# 2. reverse_trial_ends_at_iso (the window.tw2_trial_ends_at / /api/me value)
# ---------------------------------------------------------------------

@pytest.mark.unit
class TestTrialEndsAtIso:
    def test_active_trial_returns_iso(self, app_module):
        u = _user("explorer", FUTURE)
        assert app_module.reverse_trial_ends_at_iso(u) == FUTURE.isoformat()

    def test_lapsed_trial_returns_empty(self, app_module):
        assert app_module.reverse_trial_ends_at_iso(_user("explorer", PAST)) == ""

    def test_no_trial_returns_empty(self, app_module):
        assert app_module.reverse_trial_ends_at_iso(_user("explorer", None)) == ""

    def test_paid_tier_returns_empty(self, app_module):
        assert app_module.reverse_trial_ends_at_iso(_user("analyst", FUTURE)) == ""


# ---------------------------------------------------------------------
# 3. generate_ltk mints the EFFECTIVE claims
# ---------------------------------------------------------------------

@pytest.mark.unit
class TestLtkClaims:
    def _decode(self, app_module, token):
        import jwt
        import config
        return jwt.decode(
            token, config.APPSERVER_JWT_SECRET, algorithms=["HS256"],
            audience="tw2-appserver",
        )

    def test_in_trial_explorer_mints_strategist_level_6(self, app_module):
        claims = self._decode(app_module, app_module.generate_ltk(_user("explorer", FUTURE)))
        assert claims["tier"] == "strategist"
        assert claims["legacy_level"] == "6"

    def test_post_trial_explorer_mints_explorer_level_1(self, app_module):
        claims = self._decode(app_module, app_module.generate_ltk(_user("explorer", PAST)))
        assert claims["tier"] == "explorer"
        assert claims["legacy_level"] == "1"


# ---------------------------------------------------------------------
# 4. lazy_create_user stamps the trial on the CREATE path only
# ---------------------------------------------------------------------

pytest_db = pytest.mark.db


@pytest_db
class TestLazyCreateStampsTrial:
    @pytest.fixture
    def db_app_module(self, _models_module):
        mod = importlib.import_module("app")
        mod.DBSession = _models_module.Session
        return mod

    def test_new_user_gets_7_day_reverse_trial(self, db_app_module, db_session, mock_workos_user):
        before = datetime.now(timezone.utc)
        u = db_app_module.lazy_create_user(mock_workos_user(email="rt-new@example.com"))
        after = datetime.now(timezone.utc)
        assert u.tier == "explorer"  # NO tier mutation - elevation is mint-time only
        assert u.reverse_trial_ends_at is not None
        assert before + timedelta(days=7) <= u.reverse_trial_ends_at <= after + timedelta(days=7)

    def test_repeat_signin_does_not_reset_trial(self, db_app_module, db_session, mock_workos_user):
        wu = mock_workos_user(email="rt-repeat@example.com")
        first = db_app_module.lazy_create_user(wu).reverse_trial_ends_at
        again = db_app_module.lazy_create_user(wu).reverse_trial_ends_at
        assert again == first
