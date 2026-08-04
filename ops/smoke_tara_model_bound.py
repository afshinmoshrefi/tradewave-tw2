#!/usr/bin/env python3
"""Authenticated, controlled live gate proving Tara actually completed on Luna."""

import datetime
import json
import os
from pathlib import Path

import jwt
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTION_LOG = REPO_ROOT / "appserver" / "appserver" / "chatbot_questions.log"
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
    if provider != "openai":
        raise SystemExit(f"FAIL: expected live provider=openai, got {provider!r}")
    print(f"tara-model-http={response.status_code}")
    print("tara-model-provider=openai")
    print("tara-model=gpt-5.6-luna")
    print("tara-model-actions=none")


if __name__ == "__main__":
    main()
