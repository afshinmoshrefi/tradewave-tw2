"""Credential-safe internal service-login contract."""

from pathlib import Path
import re
import importlib.util
import ast
import datetime
import hashlib
import hmac
import logging
import sys
import types

import pytest
from flask import Flask, jsonify, request


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]

CALLERS = (
    "apiserver/appserver_client.py",
    "site/generate_home_page.py",
    "site/generate_daily_ai_pick.py",
    "site/generate_scorecard.py",
    "site/home_opportunities.py",
    "site/ticker_pages/ticker_data.py",
    "site/lib/svg_wave_chart.py",
    "web/seasonal_report.py",
)


def test_appserver_accepts_service_key_only_on_pathless_post_route():
    source = (ROOT / "appserver/appserver/appserver.py").read_text(encoding="utf-8")
    assert "@app.route('/login/api', methods=['POST'])" in source
    assert "request.headers.get('X-Service-Key'" in source
    assert "@app.route('/login/api/<" not in source
    assert "SERVICE_JWT_TTL_HOURS" in source
    assert "datetime.timedelta(days=7)" not in source


def test_service_token_ttl_default_is_bounded_above_client_cache():
    source = (ROOT / "config.py").read_text(encoding="utf-8")
    assert "SERVICE_JWT_TTL_HOURS = int(os.environ.get('SERVICE_JWT_TTL_HOURS', '24'))" in source
    assert "21 <= SERVICE_JWT_TTL_HOURS <= 24" in source


def test_ordinary_user_with_matching_key_cannot_be_promoted_to_service_account():
    helper_path = ROOT / "appserver/appserver/service_auth.py"
    spec = importlib.util.spec_from_file_location("service_auth_contract", helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.has_service_account_role(["service_account"]) is True
    assert helper.has_service_account_role(["user"]) is False
    assert helper.has_service_account_role(["chatbot"]) is False
    assert helper.has_service_account_role("service_account") is False

    source = (ROOT / "appserver/appserver/appserver.py").read_text(encoding="utf-8")
    assert source.index("has_service_account_role(row.get('roles'))") < source.index(
        "token = jwt.encode", source.index("def login_api")
    )


@pytest.mark.parametrize(
    ("roles", "expected_status", "expects_token"),
    [(["user"], 403, False), (["service_account"], 200, True)],
)
def test_service_login_route_rejects_ordinary_row_and_accepts_service_row(
        monkeypatch, roles, expected_status, expects_token):
    """Execute the real login_api handler body without importing the legacy monolith."""
    source_path = ROOT / "appserver/appserver/appserver.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    node = next(item for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "login_api")
    node.decorator_list = []

    row = {
        "id": "u1", "email": "person@example.test", "roles": roles,
        "tier": "strategist", "legacy_wp_level": "6",
    }

    class Cursor:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return row

        def close(self):
            return None

    class Connection:
        def cursor(self, **_kwargs):
            return Cursor()

        def close(self):
            return None

    extras = types.ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.extras = extras
    psycopg2.connect = lambda _dsn: Connection()
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)

    class Config:
        API_KEY_HMAC_SECRET = "test-hmac-secret"
        POSTGRES_DSN = "not-used"
        num_portfolios_allowed_by_level = {"6": 100}
        num_watchlists_allowed_by_level = {"6": 100}
        num_watchlist_items_allowed_by_level = {"6": 500}
        num_opp_reports_allowed_by_level = {"6": 2000}
        SERVICE_JWT_TTL_HOURS = 24

    encoded = []
    jwt_stub = types.SimpleNamespace(
        encode=lambda payload, *_args, **_kwargs: encoded.append(payload) or "service-jwt"
    )
    flask_app = Flask(__name__)
    flask_app.config["SECRET_KEY"] = "test-secret"

    helper_spec = importlib.util.spec_from_file_location(
        "service_auth_route_contract", ROOT / "appserver/appserver/service_auth.py"
    )
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    namespace = {
        "app": flask_app,
        "available_resources": {"2": "S&P 500"},
        "config": Config,
        "datetime": datetime,
        "get_all_levels": lambda: (["2"], None, None),
        "get_remote_address": lambda: "127.0.0.1",
        "hashlib": hashlib,
        "hmac": hmac,
        "has_service_account_role": helper.has_service_account_role,
        "jsonify": jsonify,
        "jwt": jwt_stub,
        "logging": logging,
        "request": request,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source_path), "exec"), namespace)

    with flask_app.test_request_context(
            "/login/api", method="POST", headers={"X-Service-Key": "x" * 32}):
        result = namespace["login_api"]()
        if isinstance(result, tuple):
            response, status = result
        else:
            response, status = result, result.status_code
        assert status == expected_status
        assert bool(encoded) is expects_token
        if expects_token:
            assert response.get_json()["token"] == "service-jwt"
            assert encoded[0]["is_service_account"] is True
            assert response.headers["Cache-Control"] == "no-store"
        else:
            assert response.get_json()["message"] == "invalid api_key"


@pytest.mark.parametrize("relative", CALLERS)
def test_tracked_service_login_callers_do_not_put_key_in_path(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    credential_path = re.compile(
        r"login/api/(?:\{[^}]*SERVICE|%s|['\"]?\s*\+\s*[^\n]*SERVICE)"
    )
    assert credential_path.search(source) is None
    assert "X-Service-Key" in source
