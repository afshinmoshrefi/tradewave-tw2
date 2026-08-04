#!/usr/bin/env python3
"""Authenticated live gate proving loaded analysis remains deterministic."""

import datetime
import json
import os
from pathlib import Path

import jwt
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTION_LOG = REPO_ROOT / "appserver" / "appserver" / "chatbot_questions.log"
MESSAGE = "explain this chart"
USER_ID = "tara-parity-deterministic-smoke"


def _token():
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
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
        os.environ["APPSERVER_JWT_SECRET"],
        algorithm="HS256",
    )


def main():
    bind = str(os.environ.get("TW2_APPSERVER_BIND") or "")
    try:
        port = int(bind.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        raise SystemExit("FAIL: invalid TW2_APPSERVER_BIND")
    yearly = [
        {
            "year": year,
            "underlying_return_pct": (-2.51 if year < 2023 else 1.44),
            "upside_excursion_pct": 3.25,
            "downside_excursion_pct": -4.5,
        }
        for year in range(2009, 2026)
    ]
    body = {
        "message": MESSAGE,
        "history": [{"role": "user", "content": MESSAGE}],
        "token": _token(),
        "wave_viewer": {
            "symbol": "PEG",
            "start_date": "2026-07-31",
            "days_out": "6",
            "years": "17",
            "direction": "short",
            "selection_origin": "scanner",
            "stats": {"Sharpe Ratio": "0.82", "Sharpe Ratio2": "1.24"},
            "yearly_results": yearly,
        },
        "screen_context": {
            "active_bottom_slide": "price_chart",
            "price_chart_mode": "current",
            "selected_lookback": "17",
            "full_history_years": "40",
            "opportunity_table_visible": True,
            "opportunity_rows": 23,
        },
        "opportunities": [],
    }
    response = requests.post(
        f"http://127.0.0.1:{port}/chatbot/chat", json=body, timeout=90
    )
    response.raise_for_status()
    payload = response.json()
    reply = str(payload.get("reply") or "")
    markers = [
        '<div class="tara-analysis">',
        "<b>Read:</b>",
        "<b>Payoff and path:</b>",
        "<b>Timing:</b>",
        "<b>Next check:</b>",
        "<b>Scope:</b>",
    ]
    missing = [marker for marker in markers if marker not in reply]
    if missing:
        raise SystemExit("FAIL: missing deterministic analysis markers")
    if payload.get("actions") != []:
        raise SystemExit("FAIL: deterministic analysis returned UI actions")

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
    if provider != "deterministic":
        raise SystemExit(f"FAIL: expected deterministic provider, got {provider!r}")
    print(f"tara-deterministic-http={response.status_code}")
    print("tara-deterministic-provider=deterministic")
    print(f"tara-deterministic-markers={len(markers)}/{len(markers)}")
    print("tara-deterministic-actions=none")


if __name__ == "__main__":
    main()
