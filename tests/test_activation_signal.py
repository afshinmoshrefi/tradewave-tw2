"""
Coverage for CARD W1.4 (docs/marketing/GTM_EXECUTION_PLAYBOOK.md) -
POST /api/activation/ai-score-viewed in /home/flask/web/app.py.

The contract (strategy §2 machine-part-1 persistence rule, BINDING):
  * Both the day-2 and day-7 trial-activation emails read
    users.first_ai_score_viewed_at - NEVER GA4. GA4 is analytics only.
  * The handler writes Postgres in this order: (1) append an
    onboarding_events row (event_type='ai_score_viewed'), (2) idempotent
    first-touch UPDATE of users.first_ai_score_viewed_at (a second view
    must NOT overwrite the timestamp), (3) fire the GA4 Measurement
    Protocol event - fail-open, and the Postgres write must succeed even
    when GA4 is completely unconfigured (the normal dev/staging state).
  * Unauthenticated callers get 401 and touch neither table.

GA4 is monkeypatched throughout - no network. Flask test client against
the tradewave_test DB (db-marked), following the test_web_funnel_fixes.py
/ test_lazy_create_user.py conventions.
"""
from __future__ import annotations

import importlib

import pytest


pytestmark = pytest.mark.db


@pytest.fixture
def app_module(_models_module):
    """Import web.app with DBSession re-pointed at the test engine, and
    GA4 stubbed so no test ever attempts real network I/O."""
    mod = importlib.import_module("app")
    mod.DBSession = _models_module.Session
    return mod


@pytest.fixture
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.fixture
def stub_ga4(app_module, monkeypatch):
    """Capture ga4_mp.send_event calls without hitting the network. Returns
    the mock so tests can assert call args or force a raise (fail-open check)."""
    from unittest.mock import MagicMock
    m = MagicMock(return_value=True)
    monkeypatch.setattr(app_module, "send_event", m)
    return m


@pytest.fixture
def logged_in(app_module, monkeypatch):
    """Monkeypatch get_current_user() to return the given User row for the
    duration of one request (get_current_user caches on flask.g, which is
    per-request, so this is safe across multiple client calls)."""
    def _apply(user):
        monkeypatch.setattr(app_module, "get_current_user", lambda: user)
    return _apply


class TestAiScoreViewedAuth:
    def test_anonymous_is_redirected_not_written(self, client, db_session, _models_module):
        """@require_login (web/app.py) redirects (302) an unauthenticated caller to
        WorkOS hosted signup before the view body ever runs - it never returns 401
        itself. This mirrors the existing /api/onboarding/event route (app.py:827-833),
        whose own `if u is None: return 401` body-level check is unreachable for the
        same reason; that is pre-existing behavior, not something this card changes.
        What actually matters here: an anonymous POST must touch neither table."""
        r = client.post("/api/activation/ai-score-viewed", json={})
        assert r.status_code == 302
        assert db_session.query(_models_module.OnboardingEvent).count() == 0


class TestAiScoreViewedFirstTouch:
    def test_first_view_stamps_column_and_logs_event(
        self, app_module, client, make_user, logged_in, stub_ga4, db_session, _models_module
    ):
        u = make_user(tier="analyst")
        assert u.first_ai_score_viewed_at is None
        logged_in(u)

        r = client.post(
            "/api/activation/ai-score-viewed",
            json={"detail": {"market": 4, "symbol": "AAPL", "horizon": 30}},
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["first_touch"] is True

        db_session.expire_all()
        refreshed = db_session.get(_models_module.User, u.id)
        assert refreshed.first_ai_score_viewed_at is not None

        rows = (
            db_session.query(_models_module.OnboardingEvent)
            .filter_by(user_id=u.id, event_type="ai_score_viewed")
            .all()
        )
        assert len(rows) == 1
        # Storage-key discipline: market coerced to the stable string key, not an int.
        assert rows[0].detail["market"] == "4"
        assert rows[0].detail["symbol"] == "AAPL"

        stub_ga4.assert_called_once()
        args, kwargs = stub_ga4.call_args
        assert args[1] == "ai_score_viewed"
        assert kwargs.get("user_id") == str(u.id)

    def test_second_view_does_not_overwrite_timestamp(
        self, app_module, client, make_user, logged_in, stub_ga4, db_session, _models_module
    ):
        u = make_user(tier="strategist")
        logged_in(u)

        r1 = client.post("/api/activation/ai-score-viewed", json={"detail": {"symbol": "MSFT"}})
        assert r1.status_code == 200
        assert r1.get_json()["first_touch"] is True

        db_session.expire_all()
        first_ts = db_session.get(_models_module.User, u.id).first_ai_score_viewed_at
        assert first_ts is not None

        r2 = client.post("/api/activation/ai-score-viewed", json={"detail": {"symbol": "NVDA"}})
        assert r2.status_code == 200
        assert r2.get_json()["first_touch"] is False

        db_session.expire_all()
        second_ts = db_session.get(_models_module.User, u.id).first_ai_score_viewed_at
        assert second_ts == first_ts, "a second view must never overwrite the first-touch stamp"

        # Both views are still logged as separate append-only telemetry rows.
        rows = (
            db_session.query(_models_module.OnboardingEvent)
            .filter_by(user_id=u.id, event_type="ai_score_viewed")
            .all()
        )
        assert len(rows) == 2

    def test_postgres_write_succeeds_even_when_ga4_unconfigured(
        self, app_module, client, make_user, logged_in, db_session, _models_module, monkeypatch
    ):
        """The normal dev/staging state: TW2_GA_MEASUREMENT_ID / GA4_MP_API_SECRET
        are unset, so ga4_mp.send_event no-ops (returns False) rather than firing.
        The Postgres write must happen regardless - GA4 is analytics only."""
        monkeypatch.setattr(app_module.config, "ga_measurement_id", "", raising=False)
        monkeypatch.setattr(app_module.config, "GA4_MP_API_SECRET", "", raising=False)

        u = make_user(tier="analyst")
        logged_in(u)

        r = client.post("/api/activation/ai-score-viewed", json={"detail": {"symbol": "TSLA"}})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

        db_session.expire_all()
        refreshed = db_session.get(_models_module.User, u.id)
        assert refreshed.first_ai_score_viewed_at is not None

    def test_ga4_exception_never_fails_the_request(
        self, app_module, client, make_user, logged_in, db_session, _models_module, monkeypatch
    ):
        """A GA4 outage/misconfiguration must never be the reason this request
        fails - send_event itself is fail-open, but this guards the call site too."""
        def _boom(*a, **kw):
            raise RuntimeError("GA is down")
        monkeypatch.setattr(app_module, "send_event", _boom)

        u = make_user(tier="strategist")
        logged_in(u)

        r = client.post("/api/activation/ai-score-viewed", json={"detail": {"symbol": "GOOG"}})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

        db_session.expire_all()
        refreshed = db_session.get(_models_module.User, u.id)
        assert refreshed.first_ai_score_viewed_at is not None

    def test_oversized_detail_is_truncated_not_rejected(
        self, app_module, client, make_user, logged_in, stub_ga4, db_session, _models_module
    ):
        u = make_user(tier="analyst")
        logged_in(u)

        huge = {"symbol": "AAPL", "junk": "x" * 5000}
        r = client.post("/api/activation/ai-score-viewed", json={"detail": huge})
        assert r.status_code == 200

        row = (
            db_session.query(_models_module.OnboardingEvent)
            .filter_by(user_id=u.id, event_type="ai_score_viewed")
            .one()
        )
        assert row.detail == {"_truncated": True}
