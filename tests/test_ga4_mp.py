"""
Coverage for /home/flask/web/ga4_mp.py - server-side GA4 Measurement Protocol
event tracking.

This module is money-path-adjacent (fires from checkout, the Stripe webhook,
and the WorkOS auth callback) so the two properties that matter most are:

  1. `send_event` NEVER raises, and no-ops (returns False) whenever GA4 isn't
     configured or the caller has no client_id - the normal dev/staging state.
  2. `parse_ga_client_id` never raises on a malformed/missing `_ga` cookie;
     it returns None rather than a wrong client_id.

No real network call is made anywhere in this file - `requests.post` is
always mocked.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

import ga4_mp


class _FakeRequest:
    """Minimal stand-in for a Flask request - only `.cookies.get()` is used."""
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


# ---------------------------------------------------------------------
# parse_ga_client_id
# ---------------------------------------------------------------------

class TestParseGaClientId:
    def test_valid_ga1_1_form(self):
        req = _FakeRequest({"_ga": "GA1.1.111111111.2222222222"})
        assert ga4_mp.parse_ga_client_id(req) == "111111111.2222222222"

    def test_valid_ga1_2_form(self):
        # The middle segment ("version") varies (GA1.2.*, GA1.3.*, ...); only
        # the trailing two numeric segments matter.
        req = _FakeRequest({"_ga": "GA1.2.987654321.1600000000"})
        assert ga4_mp.parse_ga_client_id(req) == "987654321.1600000000"

    def test_missing_cookie(self):
        req = _FakeRequest({})
        assert ga4_mp.parse_ga_client_id(req) is None

    def test_empty_cookie_value(self):
        req = _FakeRequest({"_ga": ""})
        assert ga4_mp.parse_ga_client_id(req) is None

    @pytest.mark.parametrize("raw", [
        "junk",
        "GA1.1.111111111",                 # only one trailing segment
        "GA1.1.abc.def",                   # non-numeric segments
        "GA2.1.111111111.2222222222",      # wrong version prefix (not GA1)
        "GA1.1.111111111.2222222222.extra",  # trailing garbage
        "GA1..111111111.2222222222",       # empty version field
    ])
    def test_malformed_forms_return_none(self, raw):
        req = _FakeRequest({"_ga": raw})
        assert ga4_mp.parse_ga_client_id(req) is None


# ---------------------------------------------------------------------
# send_event - unconfigured no-op
# ---------------------------------------------------------------------

class TestSendEventUnconfiguredNoOp:
    def test_noop_when_measurement_id_missing(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "secret123", raising=False)
        with patch.object(ga4_mp.requests, "post") as mock_post:
            result = ga4_mp.send_event("111.222", "sign_up")
        assert result is False
        mock_post.assert_not_called()

    def test_noop_when_api_secret_missing(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "", raising=False)
        with patch.object(ga4_mp.requests, "post") as mock_post:
            result = ga4_mp.send_event("111.222", "sign_up")
        assert result is False
        mock_post.assert_not_called()

    def test_noop_when_client_id_missing(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "secret123", raising=False)
        with patch.object(ga4_mp.requests, "post") as mock_post:
            result = ga4_mp.send_event(None, "sign_up")
        assert result is False
        mock_post.assert_not_called()

    def test_noop_when_client_id_empty_string(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "secret123", raising=False)
        with patch.object(ga4_mp.requests, "post") as mock_post:
            result = ga4_mp.send_event("", "sign_up")
        assert result is False
        mock_post.assert_not_called()


# ---------------------------------------------------------------------
# send_event - configured, posts the right payload
# ---------------------------------------------------------------------

class TestSendEventPostsCorrectPayload:
    def test_posts_expected_url_and_body(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "shh-secret", raising=False)

        fake_resp = MagicMock(status_code=204, text="")
        with patch.object(ga4_mp.requests, "post", return_value=fake_resp) as mock_post:
            result = ga4_mp.send_event(
                "123.456", "begin_checkout",
                params={"currency": "usd", "value": 47.0, "tier": "analyst"},
                user_id="42",
            )

        assert result is True
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        url = call_args[0]
        assert url.startswith("https://www.google-analytics.com/mp/collect?")
        assert "measurement_id=G-TEST123" in url
        assert "api_secret=shh-secret" in url

        body = call_kwargs["json"]
        assert body == {
            "client_id": "123.456",
            "user_id": "42",
            "events": [{
                "name": "begin_checkout",
                "params": {"currency": "usd", "value": 47.0, "tier": "analyst"},
            }],
        }
        assert call_kwargs["timeout"] == 4

    def test_omits_user_id_when_not_passed(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "shh-secret", raising=False)

        fake_resp = MagicMock(status_code=204, text="")
        with patch.object(ga4_mp.requests, "post", return_value=fake_resp) as mock_post:
            ga4_mp.send_event("123.456", "sign_up")

        body = mock_post.call_args.kwargs["json"]
        assert "user_id" not in body
        assert body["events"] == [{"name": "sign_up", "params": {}}]

    def test_non_2xx_status_returns_false(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "shh-secret", raising=False)

        fake_resp = MagicMock(status_code=400, text="bad request")
        with patch.object(ga4_mp.requests, "post", return_value=fake_resp):
            result = ga4_mp.send_event("123.456", "sign_up")
        assert result is False


# ---------------------------------------------------------------------
# send_event - fail-open on any exception
# ---------------------------------------------------------------------

class TestSendEventFailsOpen:
    def test_swallows_network_exception(self, monkeypatch):
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "shh-secret", raising=False)

        with patch.object(ga4_mp.requests, "post", side_effect=Exception("boom - GA is down")):
            result = ga4_mp.send_event("123.456", "purchase", {"value": 47.0})

        assert result is False  # must not raise

    def test_swallows_timeout(self, monkeypatch):
        import requests as real_requests
        monkeypatch.setattr(ga4_mp.config, "ga_measurement_id", "G-TEST123", raising=False)
        monkeypatch.setattr(ga4_mp.config, "GA4_MP_API_SECRET", "shh-secret", raising=False)

        with patch.object(ga4_mp.requests, "post",
                          side_effect=real_requests.exceptions.Timeout("timed out")):
            result = ga4_mp.send_event("123.456", "purchase")

        assert result is False
