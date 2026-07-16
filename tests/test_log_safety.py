import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "site" / "lib"))
from log_safety import scrub_secret_text  # noqa: E402


def test_generator_scrubber_removes_url_keys_jwts_and_legacy_paths():
    original = (
        "GET https://internal/login/api/long-lived-secret?"
        "token=eyJheader.payload.signature&api_key=another-secret failed"
    )
    scrubbed = scrub_secret_text(original)
    assert scrubbed == (
        "GET https://internal/login/api/***?token=***&api_key=*** failed"
    )
    assert "long-lived-secret" not in scrubbed
    assert "payload.signature" not in scrubbed


def test_generator_scrubber_removes_explicit_header_key_from_exception_text():
    assert scrub_secret_text("bad header service-secret", "service-secret") == "bad header ***"


def test_nginx_safe_log_installer_covers_inherited_global_access_log():
    installer = (ROOT / "ops" / "install_safe_nginx_logging.sh").read_text(
        encoding="utf-8"
    )

    assert "NGINX_MAIN=/etc/nginx/nginx.conf" in installer
    assert 'render_safe_access_logs "$rendered"' in installer
    assert 'render_safe_access_logs "$main_rendered"' in installer
    assert 'require_safe_access_logs "$rendered"' in installer
    assert 'require_safe_access_logs "$main_rendered"' in installer
    assert 'install -m 0644 "$main_rendered" "$NGINX_MAIN"' in installer
    assert 'install -m 0644 "$main_backup" "$NGINX_MAIN"' in installer
