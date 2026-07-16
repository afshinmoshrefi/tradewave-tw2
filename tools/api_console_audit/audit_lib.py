"""API-console UX audit helpers. Dev only. Never prints secret values."""
import os, sys, json, datetime
sys.path.insert(0, "/home/flask")
sys.path.insert(0, "/home/flask/web")

import config
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response
import psycopg2, psycopg2.extras

EMAIL = "tw-apiux-test-20260710@trxstat.com"
PASSWORD = "Apiux!Test-20260710#audit"
FIRST = "ApiuxAudit"
LAST = "Throwaway"
STATE_FILE = "/tmp/claude-0/-home-flask/0a525026-2010-4572-a505-12cf6e7a1966/scratchpad/audit_state.json"

DSN = os.environ["POSTGRES_DSN"]


def _client():
    return WorkOSClient(api_key=config.WORKOS_API_KEY, client_id=config.WORKOS_CLIENT_ID, request_timeout=20)


def db():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=2, default=str)
