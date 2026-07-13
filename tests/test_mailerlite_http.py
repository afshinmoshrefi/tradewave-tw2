"""Unit coverage for fail-closed, verified MailerLite mutations."""
from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests


pytestmark = pytest.mark.unit


class Response:
    def __init__(self, status_code, data=None, headers=None):
        self.status_code = status_code
        self._data = data or {}
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._data


class FalsyResponse(Response):
    def __bool__(self):
        return False


def subscriber(status="active", groups=()):
    return Response(200, {
        "data": {
            "id": "sub-1",
            "status": status,
            "groups": [{"id": group_id} for group_id in groups],
        },
    })


@pytest.fixture
def email_utils(monkeypatch):
    import email_utils as module
    monkeypatch.setattr(module.config, "MAILERLITE_API_KEY", "test-key")
    monkeypatch.setattr(module.config, "MAILERLITE_OUTBOUND_ENABLED", True)
    monkeypatch.setattr(module.config, "MAILERLITE_GROUP_ID", "g-lead")
    monkeypatch.setattr(module.config, "MAILERLITE_LIFECYCLE_GROUPS", {
        "trial_started": "g-trial",
        "trial_ended_explorer": "g-ended",
        "winback_explorer": "g-winback",
    })
    monkeypatch.setattr(module, "_locally_suppressed", lambda _email: False)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return module


def test_writes_disabled_makes_no_http_call(email_utils, monkeypatch):
    request = Mock()
    monkeypatch.setattr(email_utils.config, "MAILERLITE_OUTBOUND_ENABLED", False)
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_started", create_if_missing=True,
    )
    assert result == "skip:writes-disabled"
    request.assert_not_called()


def test_transient_429_retries_then_succeeds(email_utils, monkeypatch):
    request = Mock(side_effect=[
        Response(429, headers={"Retry-After": "0"}),
        Response(200),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    response = email_utils._mailerlite_request(
        "GET", "https://example.invalid", headers={}, max_attempts=3,
    )
    assert response.status_code == 200
    assert request.call_count == 2


def test_retry_after_is_read_from_falsy_requests_response(
    email_utils, monkeypatch,
):
    sleeps = []
    request = Mock(side_effect=[
        FalsyResponse(429, headers={"Retry-After": "1.5"}),
        Response(200),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    monkeypatch.setattr(email_utils.time, "sleep", sleeps.append)
    response = email_utils._mailerlite_request(
        "GET", "https://example.invalid", headers={}, max_attempts=3,
    )
    assert response.status_code == 200
    assert sleeps == [1.5]


def test_network_error_retries(email_utils, monkeypatch):
    request = Mock(side_effect=[
        requests.ConnectionError("temporary"),
        Response(200),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    response = email_utils._mailerlite_request(
        "GET", "https://example.invalid", headers={}, max_attempts=3,
    )
    assert response.status_code == 200
    assert request.call_count == 2


def test_ordinary_400_does_not_retry(email_utils, monkeypatch):
    request = Mock(return_value=Response(400))
    monkeypatch.setattr(email_utils.requests, "request", request)
    response = email_utils._mailerlite_request(
        "GET", "https://example.invalid", headers={}, max_attempts=3,
    )
    assert response.status_code == 400
    request.assert_called_once()


def test_failed_delete_is_reported_as_error(email_utils, monkeypatch):
    request = Mock(side_effect=[
        subscriber(groups=("g-winback",)),
        Response(500), Response(500), Response(500),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", None,
    )
    assert result == "error:delete-500"


def test_inactive_subscriber_is_never_reactivated(email_utils, monkeypatch):
    request = Mock(side_effect=[
        subscriber(status="unsubscribed", groups=("g-trial",)),
        Response(204),
        subscriber(status="unsubscribed", groups=()),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_ended_explorer",
        create_if_missing=True,
    )
    assert result.startswith("unsub(unsubscribed):reconciled")
    methods = [call.args[0] for call in request.call_args_list]
    assert methods == ["GET", "DELETE", "GET"]


def test_readback_membership_mismatch_fails(email_utils, monkeypatch):
    request = Mock(side_effect=[
        subscriber(groups=()),
        Response(204),
        subscriber(groups=()),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_started",
    )
    assert result == "error:verify-membership"


def test_local_optout_prevents_any_group_http(email_utils, monkeypatch):
    request = Mock()
    monkeypatch.setattr(email_utils, "_locally_suppressed", lambda _email: True)
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_started", create_if_missing=True,
    )
    assert result == "skip:local-optout"
    request.assert_not_called()


def test_failed_local_optout_check_is_retryable_and_makes_no_http(
    email_utils, monkeypatch,
):
    request = Mock()
    monkeypatch.setattr(email_utils, "_locally_suppressed", lambda _email: None)
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_started", create_if_missing=True,
    )
    assert result == "error:local-optout-check"
    request.assert_not_called()


def test_optout_racing_group_add_is_removed_and_unsubscribed(
    email_utils, monkeypatch,
):
    suppression_checks = iter((False, True))
    monkeypatch.setattr(
        email_utils,
        "_locally_suppressed",
        lambda _email: next(suppression_checks),
    )
    request = Mock(side_effect=[
        subscriber(groups=()),
        Response(204),
        subscriber(groups=("g-trial",)),
        Response(204),
        Response(200),
        subscriber(status="unsubscribed", groups=()),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "person@example.com", "trial_started",
    )
    assert result == "unsub(local-optout):reconciled"
    assert [call.args[0] for call in request.call_args_list] == [
        "GET", "POST", "GET", "DELETE", "POST", "GET",
    ]


def test_generic_subscribe_adds_configured_group_to_existing_subscriber(
    email_utils, monkeypatch,
):
    request = Mock(side_effect=[
        subscriber(groups=()),
        Response(204),
        subscriber(groups=("g-lead",)),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    assert email_utils.mailerlite_subscribe("lead@example.com") is True
    assert [call.args[0] for call in request.call_args_list] == [
        "GET", "POST", "GET",
    ]


def test_generic_subscribe_refuses_local_optout_without_http(
    email_utils, monkeypatch,
):
    request = Mock()
    monkeypatch.setattr(email_utils, "_locally_suppressed", lambda _email: True)
    monkeypatch.setattr(email_utils.requests, "request", request)
    assert email_utils.mailerlite_subscribe("lead@example.com") is False
    request.assert_not_called()


def test_optout_racing_new_subscriber_create_is_verified_inactive(
    email_utils, monkeypatch,
):
    suppression_checks = iter((False, True))
    monkeypatch.setattr(
        email_utils,
        "_locally_suppressed",
        lambda _email: next(suppression_checks),
    )
    request = Mock(side_effect=[
        Response(404),
        Response(201),
        subscriber(groups=("g-trial",)),
        Response(204),
        Response(200),
        subscriber(status="unsubscribed", groups=()),
    ])
    monkeypatch.setattr(email_utils.requests, "request", request)
    result = email_utils.sync_mailerlite_lifecycle_groups(
        "new@example.com", "trial_started", create_if_missing=True,
    )
    assert result == "unsub(local-optout):reconciled"
    assert [call.args[0] for call in request.call_args_list] == [
        "GET", "POST", "GET", "DELETE", "POST", "GET",
    ]
