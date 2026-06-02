"""Env-driven public URLs for the TradeWave API/MCP developer portal + docs.

Single source so the marketing and docs generators emit links that point at the RIGHT
host per environment (dev -> *-dev.trxstat.com; prod -> *.tradewave.ai) instead of
hardcoding. Reads TW2_PUBLIC_HOST (main site), TW2_DEVELOPERS_PUBLIC_HOST (the dedicated
public developer portal), TW2_API_PUBLIC_HOST (the JSON API), and TW2_MCP_PUBLIC_HOST (the
MCP endpoint) from the environment, falling back to /etc/tradewave/secrets.env, then dev
defaults. Prod sets the four env vars, e.g.:
  TW2_PUBLIC_HOST=tradewave.ai
  TW2_DEVELOPERS_PUBLIC_HOST=developers.tradewave.ai   # marketing + docs + learning + MCP setup
  TW2_API_PUBLIC_HOST=api.tradewave.ai                 # the JSON API (/v1) only
  TW2_MCP_PUBLIC_HOST=mcp.tradewave.ai                 # the MCP endpoint
The customer console (keys/usage/billing) stays GATED on the main app at MAIN_HOST.
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


MAIN_HOST = _host("TW2_PUBLIC_HOST", "tw2-dev.trxstat.com")              # main app + consumer marketing
DEV_HOST  = _host("TW2_DEVELOPERS_PUBLIC_HOST", "developers-dev.trxstat.com")  # the dedicated developer portal
API_HOST  = _host("TW2_API_PUBLIC_HOST", "api-dev.trxstat.com")          # the JSON API (/v1) only
MCP_HOST  = _host("TW2_MCP_PUBLIC_HOST", "mcp-dev.trxstat.com")          # the MCP endpoint

# The dedicated public developer portal (developers.tradewave.ai) hosts ALL the human-facing
# developer surface - marketing landing, technical docs/reference, learning, and MCP setup -
# at ONE host. api.* serves only the JSON API; mcp.* only the MCP endpoint; the console
# (keys/usage/billing) stays gated on the main app.
MAIN_URL      = f"https://{MAIN_HOST}"          # main app + consumer marketing (login, pricing, scorecard...)
PORTAL_URL    = f"https://{DEV_HOST}"           # developer portal root (marketing landing)
DOCS_URL      = f"https://{DEV_HOST}/docs"      # technical docs / API reference
LEARN_URL     = f"https://{DEV_HOST}/learn"     # learning / tutorials track
MCP_SETUP_URL = f"https://{DEV_HOST}/mcp"       # MCP setup + agent cookbook pages
PLAYGROUND_URL = f"https://{DEV_HOST}/playground"  # interactive "Try it" API console
API_BASE      = f"https://{API_HOST}/v1"        # REST base shown in docs/examples
MCP_URL       = f"https://{MCP_HOST}"           # the MCP server endpoint (what clients connect to)
CONSOLE_URL   = f"{MAIN_URL}/account/api/keys"  # "Get a free API key" -> login -> the keys page
SIGNUP_URL    = f"{MAIN_URL}/signup"
LOGIN_URL     = f"{MAIN_URL}/login"


def nav(path):
    """A main-site nav target (login, pricing, scorecard, insights, legal pages, ...)."""
    return f"{MAIN_URL}/{str(path).lstrip('/')}"


def dev(path=""):
    """A developer-portal nav target (docs, learn, mcp, pricing, ... on DEV_HOST)."""
    return f"{PORTAL_URL}/{str(path).lstrip('/')}"


def as_dict():
    return {k: v for k, v in sorted(globals().items())
            if k.isupper() and isinstance(v, str)}


if __name__ == "__main__":
    for k, v in as_dict().items():
        print(f"{k} = {v}")
