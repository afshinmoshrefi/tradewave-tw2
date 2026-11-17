"""Shared helpers for the Tara eval harness (TW-TASK-0032).

No customer data lives here. Secrets are read from the process environment only
(source /etc/tradewave/secrets.env and /etc/tradewave/appserver.env before running).
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BANK_PATH = REPO_ROOT / "tests" / "fixtures" / "tara_eval_questions.json"
CONTEXTS_PATH = REPO_ROOT / "tests" / "fixtures" / "tara_eval_contexts.json"
KB_PATH = REPO_ROOT / "appserver" / "appserver" / "chatbot_knowledge.txt"

PLAN_NAMES = {1: "Explorer (free)", 2: "Navigator", 4: "Analyst", 6: "Strategist"}

CATEGORIES = (
    "product", "getting_started", "ui_howto", "definitions", "chart_reading",
    "pattern_analysis", "screening", "symbol_research", "comparisons", "dates_cycles",
    "ai_scores", "risk_boundary", "strategy", "portfolio_tools", "account_billing",
    "data_methodology", "troubleshooting", "mcp_api", "offtopic_markets", "multi_turn",
    "messy_input", "non_english",
)


def load_env_files(paths=("/etc/tradewave/secrets.env", "/etc/tradewave/appserver.env")):
    """Best-effort KEY=VALUE loader so the tools work without `set -a; . file`."""

    for path in paths:
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.replace("export ", "").strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def mint_token(user_id, user_level, minutes=30):
    """HS256 appserver JWT, same claims as ops/smoke_tara_model_bound.py."""

    import jwt

    secret = os.environ.get("APPSERVER_JWT_SECRET") or ""
    if not secret:
        raise SystemExit("APPSERVER_JWT_SECRET is not set (source /etc/tradewave/secrets.env)")
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {
            "user": user_id,
            "user_level": str(user_level),
            "ipv4": "127.0.0.1",
            "country_code": "US",
            "zip": "0",
            "aud": "tw2-appserver",
            "iss": "tw2-web",
            "iat": now,
            "exp": now + datetime.timedelta(minutes=minutes),
        },
        secret,
        algorithm="HS256",
    )


def strip_html(text):
    text = re.sub(r"<\s*br\s*/?>|</\s*(?:p|div|li|h\d)\s*>", "\n", str(text or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def sha(*parts):
    digest = hashlib.sha256()
    for part in parts:
        digest.update(json.dumps(part, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()[:24]


def load_bank(path=None):
    data = json.loads(Path(path or BANK_PATH).read_text(encoding="utf-8"))
    return data["questions"] if isinstance(data, dict) else data


def load_contexts(path=None):
    return json.loads(Path(path or CONTEXTS_PATH).read_text(encoding="utf-8"))["contexts"]


def read_jsonl(path):
    rows = []
    path = Path(path)
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def kb_sections():
    """Return ({heading: text}, {heading: first_line_number}) for the tracked KB."""

    sections, lines_at, heading, buf = {}, {}, "", []
    for number, raw in enumerate(KB_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if raw.startswith("## "):
            if heading:
                sections[heading] = "\n".join(buf).strip()
            heading, buf = raw[3:].strip(), [raw]
            lines_at[heading] = number
        elif heading:
            buf.append(raw)
    if heading:
        sections[heading] = "\n".join(buf).strip()
    return sections, lines_at


def routed_kb_headings(question):
    """Which KB sections Tara's router would attach for this question (pure function)."""

    import sys

    app_dir = str(REPO_ROOT / "appserver" / "appserver")
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from tara_prompt_context import select_topic_knowledge

    sections, _ = kb_sections()
    return list(select_topic_knowledge(question, sections).headings)
