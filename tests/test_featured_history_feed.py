"""Private web-to-gateway daily-pick feed contract."""

import json

import pytest


pytestmark = pytest.mark.unit


def test_featured_history_requires_service_key(tmp_path, monkeypatch):
    import app as web_app

    source = tmp_path / "featured_history.json"
    source.write_text(json.dumps([{"date": "2026-07-15", "symbol": "AAPL"}]), encoding="utf-8")
    monkeypatch.setenv("TW2_FEATURED_HISTORY_FILE", str(source))
    monkeypatch.setattr(web_app.config, "SERVICE_API_KEY", "test-service-key")
    client = web_app.app.test_client()

    assert client.get("/internal/featured-history").status_code == 401
    response = client.get(
        "/internal/featured-history", headers={"X-Service-Key": "test-service-key"}
    )
    assert response.status_code == 200
    assert response.get_json()[0]["symbol"] == "AAPL"
    assert response.headers["Cache-Control"] == "no-store"


def test_featured_history_fails_honestly_when_missing(tmp_path, monkeypatch):
    import app as web_app

    monkeypatch.setenv("TW2_FEATURED_HISTORY_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(web_app.config, "SERVICE_API_KEY", "test-service-key")
    response = web_app.app.test_client().get(
        "/internal/featured-history", headers={"X-Service-Key": "test-service-key"}
    )
    assert response.status_code == 503
