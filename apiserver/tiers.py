"""API/MCP tier entitlements - the single source of truth for what each tier unlocks
(market scope + ML access + rate limits + key count). The gateway, MCP, and console all
read this. Merged into the billing/Stripe metadata at integration.

Invariants: market scope uses the permanent resource keys '0'..'16'; ML-eligible markets
are 0,1,2,3,4,11; returns are always percentages (raw prices never exposed).
"""

ML_MARKETS = {"0", "1", "2", "3", "4", "11"}
# 14/15 were removed (Korea); keep the hole, never renumber.
ALL_MARKETS = [str(i) for i in range(0, 17) if i not in (14, 15)]

# rate = (per_minute, per_day); opp_limit = max results per /opportunities call.
API_TIERS = {
    "free": {
        "name": "Free", "price_monthly": 0,
        "markets": ["2"], "ml_access": False, "history": "delayed",
        "opp_limit": 3, "rate": {"per_minute": 10, "per_day": 100}, "max_keys": 1,
        "stripe_price_metadata": None,
    },
    "dev": {
        "name": "Dev", "price_monthly": 39,
        "markets": ALL_MARKETS, "ml_access": False, "history": "full",
        "opp_limit": 100, "rate": {"per_minute": 60, "per_day": 5000}, "max_keys": 3,
        "stripe_price_metadata": {"product_line": "api", "tier": "dev"},
    },
    "pro": {
        "name": "Pro", "price_monthly": 199,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full",   # ML is the Pro paywall
        "opp_limit": 1000, "rate": {"per_minute": 300, "per_day": 50000}, "max_keys": 10,
        "stripe_price_metadata": {"product_line": "api", "tier": "pro"},
    },
    "business": {
        "name": "Business", "price_monthly": 599,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full",
        "opp_limit": 5000, "rate": {"per_minute": 1200, "per_day": 250000}, "max_keys": 50,
        "stripe_price_metadata": {"product_line": "api", "tier": "business"},
    },
}

DEFAULT_TIER = "free"

# Unified accounts: an explicit API subscription wins; else inherit from the web tier.
WEB_TIER_TO_API = {"explorer": "free", "analyst": "dev", "strategist": "pro"}


def tier_for(name):
    return API_TIERS.get((name or "").lower(), API_TIERS[DEFAULT_TIER])


def api_tier_from_user(user_row):
    """user_row is a dict with at least 'tier' (web tier) and optionally 'api_tier'."""
    explicit = (user_row.get("api_tier") if hasattr(user_row, "get") else None)
    if explicit:
        return explicit
    return WEB_TIER_TO_API.get(user_row.get("tier"), DEFAULT_TIER)


def market_in_scope(tier_name, market_id):
    return str(market_id) in tier_for(tier_name)["markets"]


def ml_allowed(tier_name, market_id):
    t = tier_for(tier_name)
    return bool(t["ml_access"]) and str(market_id) in ML_MARKETS
