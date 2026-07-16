"""Doc-CI regression net: the PUBLISHED quickstart snippets must actually run.

The 2026-06-12 docs review found the live quickstart crashed on copy-paste:
generate_api_docs.py emitted pick["symbol"] / pick.days_out for a /daily-pick
response whose PatternCard lives under "card" (hold days at card.setup.hold_days).
site/api_docs/check_quickstart_snippets.py now extracts every code-tab snippet
from the generated quickstart.html and EXECUTES it (curl + Python + JavaScript)
against the gateway; generate_api_docs.py fails the build when one errors.

This test runs that same checker under pytest so the suite catches a drifted
snippet even when nobody regenerates the docs. It needs a live gateway and an
API key, so it SKIPS (never fails) when either is absent - the same integration
posture as test_mcpserver's importorskip.

Key resolution (see check_quickstart_snippets.resolve_key): TW_DOCCHECK_KEY or
TRADEWAVE_API_KEY env, else the JSON keys file at TW_DOCCHECK_KEYS_FILE
(default /tmp/mcp_review_keys.json). Only 12-char key prefixes are ever printed.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path("/home/flask")
if not REPO_ROOT.is_dir():
    REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "site/api_docs/check_quickstart_snippets.py"
QUICKSTART = REPO_ROOT / "site/api_docs/quickstart.html"
CHECK_BASE = os.environ.get("TW_DOCCHECK_API_BASE", "http://127.0.0.1:8088/v1")


def _gateway_reachable() -> bool:
    u = urlparse(CHECK_BASE)
    try:
        with socket.create_connection((u.hostname, u.port or (443 if u.scheme == "https" else 80)),
                                      timeout=3):
            return True
    except OSError:
        return False


def test_published_quickstart_snippets_execute():
    if not QUICKSTART.is_file():
        pytest.skip("quickstart.html not generated yet")
    if not _gateway_reachable():
        pytest.skip(f"gateway not reachable at {CHECK_BASE}")
    proc = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, text=True)
    if proc.returncode == 2:
        pytest.skip("no API key configured for doc-CI (TW_DOCCHECK_KEY / keys file)")
    if proc.returncode == 3:
        pytest.skip("doc-CI inconclusive: the test key's day quota is exhausted")
    assert proc.returncode == 0, (
        "published quickstart snippet(s) failed against the gateway:\n"
        f"{proc.stdout}\n{proc.stderr}"
    )


def test_scan_quickstarts_use_the_contract_parameter_name():
    """`market` is silently ignored by /scan; the documented parameter is `markets`."""
    if not QUICKSTART.is_file():
        pytest.skip("quickstart.html not generated yet")
    document = QUICKSTART.read_text(encoding="utf-8")
    assert "/scan?market=" not in document
    assert "/scan?markets=2" in document
