"""API/MCP tier entitlements - the single source of truth for what each tier unlocks
(market scope + ML access + rate limits + key count). The gateway, MCP, and console all
read this. Merged into the billing/Stripe metadata at integration.

Invariants: market scope uses the permanent resource keys '0'..'16'; ML-eligible markets
are 0,1,2,3,4,11; returns are always percentages (raw prices never exposed).

ML access model (2026-05-31): ML scores are available to EVERY tier, METERED PER DAY via
`ml_daily_limit` (None = unlimited). Free Explorer gets a real taste (5/day) - the upsell
is unlimited ML, not ML-vs-no-ML. The daily count is enforced in ml_quota.py (Redis db4).
`ml_access` stays True on every tier and now just means "ML is offered at all" (it is).
"""

ML_MARKETS = {"0", "1", "2", "3", "4", "11"}
# 14/15 were removed (Korea); keep the hole, never renumber.
ALL_MARKETS = [str(i) for i in range(0, 17) if i not in (14, 15)]

# Annual billing = 10x the monthly price (pay for 10 months, get 12 = "2 months free",
# ~17% off). Stripe holds a separate yearly price per product; checkout picks the interval.
# price_annual is the single source of truth (create_api_products.py + the pricing page read it).

# rate = (per_minute, per_day); opp_limit = max results per /opportunities call.
#
# `history` is RESERVED / NOT IMPLEMENTED (verified 2026-06-12): no code path consumes
# it - free keys receive the same live seasonal patterns as paid tiers. It is kept only as a
# placeholder for a possible future delayed-data free tier. Do NOT market it: the
# pricing page deliberately carries no data-freshness bullet until enforcement exists.
API_TIERS = {
    "free": {
        "name": "Free", "price_monthly": 0, "price_annual": 0,
        "markets": ["2"], "ml_access": True, "history": "delayed", "ml_daily_limit": 5,
        "opp_limit": 3, "rate": {"per_minute": 10, "per_day": 100}, "max_keys": 1,
        "stripe_price_metadata": None,
    },
    "dev": {
        "name": "Dev", "price_monthly": 39, "price_annual": 390,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": 100,
        "opp_limit": 100, "rate": {"per_minute": 60, "per_day": 5000}, "max_keys": 3,
        "stripe_price_metadata": {"product_line": "api", "tier": "dev"},
    },
    "pro": {
        "name": "Pro", "price_monthly": 199, "price_annual": 1990,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": None,  # unlimited ML = the Pro upsell
        "opp_limit": 1000, "rate": {"per_minute": 300, "per_day": 50000}, "max_keys": 10,
        "stripe_price_metadata": {"product_line": "api", "tier": "pro"},
    },
    "business": {
        "name": "Business", "price_monthly": 599, "price_annual": 5990,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": None,  # unlimited
        "opp_limit": 5000, "rate": {"per_minute": 1200, "per_day": 250000}, "max_keys": 50,
        "stripe_price_metadata": {"product_line": "api", "tier": "business"},
    },
}

DEFAULT_TIER = "free"

# Internal, NOT-sold tiers - deliberately kept OUT of API_TIERS so they never appear in
# pricing pages / Stripe products / anything that iterates the sellable catalog.
# `chatbot`: the principal the in-product assistant ("Tara") uses to call this gateway
# (see docs/TARA_GATEWAY_INTEGRATION.md). `service: True` is the ONLY flag that lets a key
# delegate the metering principal via X-TW-On-Behalf-Of (auth.py) - normal customer keys
# cannot. ml_daily_limit here is the chatbot's OWN per-web-user allowance, namespaced
# separately from the API ML quota (the delegated principal is 'cb:' prefixed), so a human
# who uses BOTH the API and the chatbot never shares one ML bucket across the two products.
INTERNAL_TIERS = {
    "chatbot": {
        "name": "Chatbot", "price_monthly": 0, "price_annual": 0,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": 30,
        "opp_limit": 25, "rate": {"per_minute": 30, "per_day": 600}, "max_keys": 1,
        "stripe_price_metadata": None, "service": True,
    },
    # The MCP server's principal for the consumer OAuth flow (ChatGPT/Claude -> WorkOS login).
    # `workos_principal: True` lets it pass X-TW-Principal-WorkOS:<workos_sub>; the gateway then
    # resolves that to the user's REAL api tier (not this tier) - see auth._apply_on_behalf and
    # docs/MCP_OAUTH_INTEGRATION.md. These own entitlements are only a fallback for a direct
    # mcp-key call with no principal header (should not happen in normal use).
    "mcp": {
        "name": "MCP", "price_monthly": 0, "price_annual": 0,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": 5,
        "opp_limit": 25, "rate": {"per_minute": 60, "per_day": 2000}, "max_keys": 1,
        "stripe_price_metadata": None, "service": True, "workos_principal": True,
    },
    # The PUBLIC demo principal (token printed in the docs, NOT a secret). Safe only because of
    # the `demo_symbols` allowlist + blocked symbol-enumeration/bulk endpoints in routes.py - so a
    # zero-signup tryer can explore a handful of tickers but can never scrape the dataset. Has NO
    # `service` flag, so it can never delegate the metering principal to another user.
    "demo": {
        "name": "Demo", "price_monthly": 0, "price_annual": 0,
        "markets": ["2"], "ml_access": True, "history": "delayed", "ml_daily_limit": 25,
        "opp_limit": 5, "rate": {"per_minute": 30, "per_day": 1000}, "max_keys": 0,
        "stripe_price_metadata": None,
        "demo": True,
        "demo_symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA"],
    },
}

# The Founder's plan: first 100 customers get Pro at $99/mo (50% off) for 12 months, in
# exchange for a logo + a tracked-record testimonial. Implemented as a Stripe coupon (50% off,
# repeating 12 months, max_redemptions=100) + the promo code below, applied at checkout
# (allow_promotion_codes=True). NOT a separate tier - it is Pro at a discount, so entitlements
# and api_tier stay "pro".
FOUNDER = {
    "code": "FOUNDER", "applies_to_tier": "pro", "percent_off": 50,
    "duration_months": 12, "max_redemptions": 100, "effective_monthly": 99,
}

# Unified accounts: an explicit API subscription wins; else inherit from the web tier.
# This is also the "free Dev key bundled into a paid web sub": a web Analyst gets Dev API
# access and a Strategist gets Pro API access at no extra charge just by holding the web sub.
WEB_TIER_TO_API = {"explorer": "free", "analyst": "dev", "strategist": "pro"}


# Safety rail: the `service` delegation flag (X-TW-On-Behalf-Of in auth.py) must live ONLY on
# internal tiers, never on a sold one - otherwise a paying customer key could impersonate any
# user's metering. Fail loud at import if that invariant is ever violated by a future edit.
assert not any(t.get("service") for t in API_TIERS.values()), \
    "a sold API_TIERS entry has service:True - delegation must be INTERNAL_TIERS only"


def tier_for(name):
    n = (name or "").lower()
    if n in API_TIERS:
        return API_TIERS[n]
    if n in INTERNAL_TIERS:   # internal principals (e.g. chatbot) - not in the sold catalog
        return INTERNAL_TIERS[n]
    return API_TIERS[DEFAULT_TIER]


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
