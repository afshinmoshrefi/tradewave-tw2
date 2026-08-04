#!/usr/bin/env python3
"""Fail-closed Tara release preflight and nonsecret fingerprint printer."""

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "appserver" / "appserver"
sys.path.insert(0, str(APP_DIR))

from tara_release_fingerprint import runtime_fingerprint  # noqa: E402
from tara_runtime_policy import validate_policy  # noqa: E402


def credential_preflight(require_no_legacy_canary=False):
    missing = [
        name
        for name in ("OPENAI_KEY", "ANTHROPIC_TOKEN", "TARA_GATEWAY_KEY")
        if not str(os.environ.get(name) or "").strip()
    ]
    if missing:
        raise RuntimeError("missing required Tara credentials: " + ", ".join(missing))
    if require_no_legacy_canary and "TARA_OPENAI_CANARY_PERCENT" in os.environ:
        raise RuntimeError("legacy TARA_OPENAI_CANARY_PERCENT is still present")
    validate_policy()


def assert_approved_fingerprint(result, expected):
    if expected and result.get("fingerprint") != expected:
        raise RuntimeError("Tara runtime fingerprint does not match the approved release")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-credentials", action="store_true")
    parser.add_argument("--require-no-legacy-canary", action="store_true")
    parser.add_argument("--frontend-dir")
    parser.add_argument("--expected-fingerprint")
    args = parser.parse_args()

    if args.check_credentials:
        credential_preflight(args.require_no_legacy_canary)
    result = runtime_fingerprint(args.frontend_dir)
    assert_approved_fingerprint(result, args.expected_fingerprint)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
