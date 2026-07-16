import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site" / "lib"))
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
