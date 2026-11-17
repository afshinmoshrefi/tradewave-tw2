#!/usr/bin/env python3
"""Authenticated, controlled live gate proving Tara actually completed on Luna."""

import datetime
import json
import os
import sys
from pathlib import Path

import jwt
import requests


QUESTION_LOG = Path(
    os.environ.get("TARA_QUESTION_LOG", "/var/log/tradewave/tara_questions.log")
)
MESSAGE = "In one sentence, what kind of market research does TradeWave provide?"
USER_ID = "tara-parity-model-smoke"


def main():
    bind = str(os.environ.get("TW2_APPSERVER_BIND") or "")
    try:
        port = int(bind.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        raise SystemExit("FAIL: invalid TW2_APPSERVER_BIND")
    secret = str(os.environ.get("APPSERVER_JWT_SECRET") or "")
    if not secret:
        raise SystemExit("FAIL: APPSERVER_JWT_SECRET is missing")
    now = datetime.datetime.now(datetime.timezone.utc)
    token = jwt.encode(
        {
            "user": USER_ID,
            "user_level": "6",
            "ipv4": "127.0.0.1",
            "country_code": "US",
            "zip": "0",
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "iat": now,
            "exp": now + datetime.timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    body = {
        "message": MESSAGE,
        "history": [{"role": "user", "content": MESSAGE}],
        "token": token,
        "wave_viewer": {},
        "screen_context": {},
        "opportunities": [],
    }
    response = requests.post(
        f"http://127.0.0.1:{port}/chatbot/chat", json=body, timeout=120
    )
    response.raise_for_status()
    payload = response.json()
    if not str(payload.get("reply") or "").strip():
        raise SystemExit("FAIL: Tara model smoke returned no reply")
    if payload.get("actions") not in (None, []):
        raise SystemExit("FAIL: Tara model smoke returned an unexpected UI action")

    provider = None
    if QUESTION_LOG.exists():
        for raw in reversed(QUESTION_LOG.read_text(encoding="utf-8").splitlines()):
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if entry.get("user_id") == USER_ID and entry.get("question") == MESSAGE:
                provider = entry.get("provider")
                break
    # The expected provider is the release policy's primary; a fallback answer
    # ("<provider>_fallback") fails the smoke.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "appserver" / "appserver"))
    import tara_runtime_policy as policy
    policy.validate_policy()
    if provider != policy.PRIMARY_PROVIDER:
        raise SystemExit(
            f"FAIL: expected live provider={policy.PRIMARY_PROVIDER}, got {provider!r}")
    print(f"tara-model-http={response.status_code}")
    print(f"tara-model-provider={policy.PRIMARY_PROVIDER}")
    print(f"tara-model={policy.PRIMARY_MODEL}")
    print("tara-model-actions=none")


if __name__ == "__main__":
    main()
