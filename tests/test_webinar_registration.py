from datetime import datetime

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


def _row():
    return {
        "Webinar ID": "wb001",
        "Date": "2026-07-22",
        "Time": "2:00 PM",
        "Title": "TradeWave Live",
        "Description": "A live walkthrough.",
        "Webinar Link": "https://zoom.example/private",
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
    monkeypatch.setattr(module, "_mailerlite_write_allowed", lambda: True)
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


def test_success_uses_server_schedule_fields_and_verified_groups(registration, monkeypatch):
    subscribers = iter([
        (Response(404), None),
        (Response(200), _subscriber()),
    ])
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: next(subscribers))
    monkeypatch.setattr(registration, "_ensure_group", lambda *_args: "dated")
    monkeypatch.setattr(registration, "_reconcile_managed_groups", lambda *_args, **_kwargs: "created")
    writes = []
    monkeypatch.setattr(
        registration, "_mailerlite_request",
        lambda method, url, **kwargs: writes.append((method, url, kwargs.get("json"))) or Response(200),
    )
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row()], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "success"
    payload = writes[0][2]
    assert payload["fields"] == {
        "name": "Alex",
        "webinar_date": "July 22, 2026",
        "webinar_time": "2:00 PM ET",
        "webinar_url": "https://zoom.example/private",
    }
    assert "status" not in payload


def test_disabled_environment_makes_no_mailerlite_calls(registration, monkeypatch):
    monkeypatch.setattr(registration, "_mailerlite_write_allowed", lambda: False)
    called = []
    monkeypatch.setattr(registration, "_get_mailerlite_subscriber", lambda *_args: called.append(True))
    result = registration.register_webinar_subscriber(
        "person@example.com", "Alex", "wb001_2026-07-22_0200PM",
        data=[_row()], now=datetime(2026, 7, 19, tzinfo=EASTERN),
    )
    assert result == "disabled"
    assert called == []
