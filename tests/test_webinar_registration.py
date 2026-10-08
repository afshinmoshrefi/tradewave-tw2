from datetime import datetime
from unittest.mock import Mock

import pytest

from webinar_schedule import EASTERN


pytestmark = pytest.mark.unit


class Response:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}
        self.text = ""
        self.headers = {}

    def json(self):
        return self._data


def _row(link_field="Webinar Link"):
    return {
        "Webinar ID": "wb001",
        "Date": "2026-07-22",
        "Time": "2:00 PM",
        "Title": "TradeWave Live",
        "Description": "A live walkthrough.",
        link_field: "https://zoom.example/private",
    }


def _subscriber(groups=("general", "dated"), status="active"):
    return {
        "id": "subscriber-1",
        "status": status,
        "groups": [{"id": group_id} for group_id in groups],
    }


@pytest.fixture
def registration(monkeypatch):
    import webinar_registration as module
    monkeypatch.setattr(module.config, "MAILERLITE_API_KEY", "test-key")
    monkeypatch.setattr(module.config, "MAILERLITE_WEBINAR_GROUP_ID", "general")
    monkeypatch.setattr(module, "_mailerlite_write_allowed", lambda **_kwargs: True)
    monkeypatch.setattr(module, "_locally_suppressed", lambda _email: False)
    return module


def test_invalid_or_past_session_never_touches_mailerlite(registration, monkeypatch):
    called = []
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: called.append(True))
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row()], now=datetime(2026, 7, 23, tzinfo=EASTERN),
    )
    assert result == "invalid_session"
    assert called == []


def test_session_without_meeting_link_never_touches_mailerlite(registration, monkeypatch):
    row = _row()
    row.pop("Webinar Link")
    called = []
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: called.append(True))
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[row], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "invalid_session"
    assert called == []


def test_inactive_subscriber_is_not_reactivated(registration, monkeypatch):
    monkeypatch.setattr(
        registration, "_get_mailerlite_subscriber",
        lambda *_args: (Response(200), _subscriber(groups=(), status="unsubscribed")),
    )
    ensured = []
    monkeypatch.setattr(registration, "_ensure_group", lambda *_args: ensured.append(True))
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row()], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "inactive"
    assert ensured == []


@pytest.mark.parametrize("link_field", ["Webinar Link", "zoom url"])
def test_success_uses_server_schedule_fields_and_verified_groups(registration, monkeypatch, link_field):
    subscribers = iter([
        (Response(404), None),
        (Response(200), _subscriber()),
    ])
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: next(subscribers))
    monkeypatch.setattr(registration, "_ensure_group", lambda *_args: "dated")
    reconciliations = []
    monkeypatch.setattr(
        registration, "_reconcile_managed_groups",
        lambda *args, **kwargs: reconciliations.append((args, kwargs)) or "created",
    )
    writes = []
    monkeypatch.setattr(
        registration, "_mailerlite_request",
        lambda method, url, **kwargs: writes.append((method, url, kwargs.get("json"))) or Response(200),
    )
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row(link_field)], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "success"
    assert reconciliations == [(
        ("person@example.com", {"general", "dated"}, {"general", "dated"}),
        {"create_if_missing": True, "name": "Alex", "label": "webinar-groups", "write_scope": "webinar_registration"},
    )]
    payload = writes[0][2]
    assert payload["fields"] == {
        "name": "Alex",
        "webinar_date": "July 22, 2026",
        "webinar_time": "2:00 PM ET",
        "webinar_url": "https://zoom.example/private",
    }
    assert "status" not in payload


def test_disabled_environment_makes_no_mailerlite_calls(registration, monkeypatch):
    monkeypatch.setattr(registration, "_mailerlite_write_allowed", lambda **_kwargs: False)
    called = []
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: called.append(True))
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row()], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "disabled"
    assert called == []


@pytest.mark.parametrize("has_link,enabled,status", [
    (True, True, 200), (True, False, 503), (False, True, 400),
])
def test_public_route_with_webinar_only_permission_and_mocked_mailerlite(
    monkeypatch, has_link, enabled, status,
):
    import importlib
    import email_utils
    import webinar_registration as registration
    from webinar_schedule import get_upcoming_webinars

    group = "wb001_2026-10-09_0100PM"
    row = _row("zoom url")
    row.update({"Date": "2026-10-09T04:00:00.000Z", "Time": "1:00 PM EST"})
    if not has_link:
        row.pop("zoom url")
    monkeypatch.setattr(registration, "fetch_webinar_data", lambda: [row])
    monkeypatch.setattr(registration, "get_upcoming_webinars", lambda data, **_kwargs: get_upcoming_webinars(
        data, now=datetime(2026, 10, 8, 9, 0, tzinfo=EASTERN),
    ))
    monkeypatch.setattr(registration.config, "tw2_env", "prod")
    monkeypatch.setattr(registration.config, "MAILERLITE_OUTBOUND_ENABLED", False)
    monkeypatch.setattr(registration.config, "MAILERLITE_WEBINAR_REGISTRATION_ENABLED", enabled)
    monkeypatch.setattr(registration.config, "MAILERLITE_API_KEY", "test-key")
    monkeypatch.setattr(registration.config, "MAILERLITE_WEBINAR_GROUP_ID", "general")
    monkeypatch.setattr(registration.config, "MAILERLITE_LIFECYCLE_GROUPS", {
        "trial_started": "g-trial",
    })
    monkeypatch.setattr(registration, "_locally_suppressed", lambda _email: False)
    monkeypatch.setattr(email_utils, "_locally_suppressed", lambda _email: False)
    memberships, fields = set(), {}

    def mocked_request(method, url, **kwargs):
        if method == "GET" and "/groups?" in url:
            return Response(200, {"data": [{"id": "dated", "name": group}]})
        if method == "GET" and "/subscribers/" in url:
            return Response(200, {"data": _subscriber(groups=memberships)})
        if method == "POST" and "/groups/" in url:
            memberships.add(url.rsplit("/", 1)[-1])
            return Response(204)
        if method == "POST" and url == email_utils.MAILERLITE_API_URL:
            fields.update(kwargs["json"]["fields"])
            return Response(200)
        raise AssertionError((method, url))

    request = Mock(side_effect=mocked_request)
    monkeypatch.setattr(email_utils.requests, "request", request)
    app_module = importlib.import_module("app")
    response = app_module.app.test_client().post("/api/webinar/register", json={
        "first_name": "Alex", "email": "person@example.com", "group_name": group,
    })
    assert response.status_code == status
    if status == 200:
        assert response.json == {"status": "success"}
        assert memberships == {"general", "dated"}
        assert fields == {
            "name": "Alex", "webinar_date": "October 9, 2026",
            "webinar_time": "1:00 PM ET", "webinar_url": "https://zoom.example/private",
        }
        calls = request.call_count
        assert email_utils.sync_mailerlite_lifecycle_groups(
            "person@example.com", "trial_started", create_if_missing=True,
        ) == "skip:writes-disabled"
        assert request.call_count == calls
    else:
        assert response.json["message"] == (
            "Registration is temporarily unavailable. Please try again shortly."
            if status == 503 else "This webinar is no longer available."
        )
        request.assert_not_called()
