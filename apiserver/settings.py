"""Isolated settings for the API gateway + MCP server.

Reads from the environment (systemd EnvironmentFile=/etc/tradewave/secrets.env in
staging/prod); for dev/manual runs it also loads /etc/tradewave/secrets.env if present.
Deliberately does NOT import the big /home/flask/config.py - this service stays decoupled
so it can never break the cutover-critical tiers.
"""
import os


def _load_secrets_env(path="/etc/tradewave/secrets.env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_secrets_env()


def _get(name, default=None):
    return os.environ.get(name, default)


# Postgres: the TW2 users table + our api_keys / api_usage tables (same DB as appserver/web).
POSTGRES_DSN = _get("POSTGRES_DSN")
DB_POOL_MIN = max(1, int(_get("TW2_API_DB_POOL_MIN", "1")))
DB_POOL_MAX = max(DB_POOL_MIN, int(_get("TW2_API_DB_POOL_MAX", "12")))

# HMAC secret for hashing API keys. MUST match the appserver (API_KEY_HMAC_SECRET,
# falling back to APPSERVER_JWT_SECRET) so keys verify consistently.
API_KEY_HMAC_SECRET = _get("API_KEY_HMAC_SECRET") or _get("APPSERVER_JWT_SECRET")

# The existing appserver (data engine). Port is PER-ENV: dev :5000, staging/prod :80.
# Read it off the env; never hardcode 5000 off dev.
APPSERVER_URL = _get("TW2_APPSERVER_URL") or _get("APPSERVER_URL") or "http://127.0.0.1:5000"

# Service-account key for the appserver /login/api handshake (same one home_opportunities.py uses).
SERVICE_API_KEY = _get("SERVICE_API_KEY")

# The daily-pick record is generated on the web box. Dev is co-located and reads the
# file directly; split staging/prod topology supplies the service-authenticated URL.
FEATURED_HISTORY_FILE = _get(
    "TW2_FEATURED_HISTORY_FILE", "/home/flask/site/data/featured_history.json"
)
FEATURED_HISTORY_URL = (_get("TW2_FEATURED_HISTORY_URL", "") or "").strip()

# Only successful API-key lookups are cached. Revocation can lag by this bounded TTL.
API_KEY_CACHE_TTL_SECONDS = max(
    0, min(60, int(_get("TW2_API_KEY_CACHE_TTL_SECONDS", "30")))
)
API_KEY_CACHE_MAX_ENTRIES = max(
    1, min(10000, int(_get("TW2_API_KEY_CACHE_MAX_ENTRIES", "4096")))
)

# PUBLIC demo token (printed in the docs - NOT a secret). Safe via the 'demo' tier symbol
# allowlist + blocked enumeration in routes.py. Override per-box with TW2_DEMO_API_KEY.
DEMO_API_KEY = _get("TW2_DEMO_API_KEY") or "tw_demo_explore"

# Redis for rate-limit counters + usage. db4 keeps us off the appserver's db0(cache)/db2(state)/db3(news).
REDIS_HOST = _get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(_get("REDIS_PORT", "6379"))
REDIS_DB = int(_get("API_REDIS_DB", "4"))

# Stripe (TEST mode on dev).
STRIPE_SECRET_KEY = _get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = _get("STRIPE_WEBHOOK_SECRET")

PUBLIC_HOST = _get("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")
ENV = _get("TW2_ENV", "dev")


# CORS: the public developer portal ("Try it" playground at developers.tradewave.ai) calls this
# API from the browser. Auth is a bearer API key (never cookies), so echoing an allowlist of our
# own portal origins is safe. Set API_CORS_ORIGINS to a comma-separated list, or "*" for any origin.
def _default_cors_origins():
    if ENV == "prod":
        return ["https://developers.tradewave.ai", "https://tradewave.ai", "https://www.tradewave.ai"]
    if ENV == "staging":
        return ["https://developers-stage.trxstat.com", "https://tw2-stage.trxstat.com"]
    return ["https://developers-dev.trxstat.com", "https://tw2-dev.trxstat.com",
            "http://127.0.0.1:8090", "http://localhost:8090"]


_cors_raw = (_get("API_CORS_ORIGINS", "") or "").strip()
if _cors_raw == "*":
    CORS_ORIGINS = ["*"]
elif _cors_raw:
    CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
else:
    CORS_ORIGINS = _default_cors_origins()
