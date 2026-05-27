"""Env-driven public URLs for the TradeWave API/MCP developer portal + docs.

Single source so the marketing and docs generators emit links that point at the RIGHT
host per environment (dev -> *-dev.trxstat.com; prod -> tradewave.ai) instead of
hardcoding. Reads TW2_PUBLIC_HOST (main site), TW2_API_PUBLIC_HOST, TW2_MCP_PUBLIC_HOST
from the environment, falling back to /etc/tradewave/secrets.env, then dev defaults.
Prod sets the three env vars (e.g. tradewave.ai / api.tradewave.ai / mcp.tradewave.ai).
"""
import os


def _load_secrets_env(path="/etc/tradewave/secrets.env"):
    if not os.path.exists(path):
        return
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_secrets_env()


def _host(name, default):
    h = (os.environ.get(name) or default).strip()
    return h.replace("https://", "").replace("http://", "").rstrip("/")


MAIN_HOST = _host("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")
API_HOST = _host("TW2_API_PUBLIC_HOST", "api-dev.trxstat.com")
MCP_HOST = _host("TW2_MCP_PUBLIC_HOST", "mcp-dev.trxstat.com")

MAIN_URL = f"https://{MAIN_HOST}"            # main app + marketing (login, pricing, scorecard...)
PORTAL_URL = f"https://{API_HOST}/api"       # developer portal (marketing) base
DOCS_URL = f"https://{API_HOST}/docs"        # developer docs base
API_BASE = f"https://{API_HOST}/v1"          # REST base shown in docs/examples
MCP_URL = f"https://{MCP_HOST}"              # MCP server
CONSOLE_URL = f"{MAIN_URL}/account/api/keys"  # "Get a free API key" -> login -> the keys page
SIGNUP_URL = f"{MAIN_URL}/signup"
LOGIN_URL = f"{MAIN_URL}/login"


def nav(path):
    """A main-site nav target (login, pricing, scorecard, insights, legal pages, ...)."""
    return f"{MAIN_URL}/{str(path).lstrip('/')}"


def as_dict():
    return {k: v for k, v in sorted(globals().items())
            if k.isupper() and isinstance(v, str)}


if __name__ == "__main__":
    for k, v in as_dict().items():
        print(f"{k} = {v}")
