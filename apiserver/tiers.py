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

import logging
import os

log = logging.getLogger("apiserver.tiers")

ML_MARKETS = {"0", "1", "2", "3", "4", "11"}
# 14/15 were removed (Korea); keep the hole, never renumber.
ALL_MARKETS = [str(i) for i in range(0, 17) if i not in (14, 15)]

# Pricing display gate - paid-tier dollar amounts render only when this is set; the
# tiers/quotas themselves are always live. THE single source; the portal marketing
# site, the developer docs, and the console billing page all import it from here.
def _pricing_live_flag():
    """TW2_API_PRICING_LIVE from the environment, FALLING BACK to /etc/tradewave/
    secrets.env (env wins - same precedence as site/lib/portal_urls.py). The fallback
    matters: the portal generators run from operator/deploy shells that do NOT load
    the box env (deploy.sh sshes in as root), so without it a post-flip regen would
    silently revert the published pricing pages to "Coming Soon" on every deploy."""
    v = os.environ.get('TW2_API_PRICING_LIVE')
    if v is None:
        try:
            with open('/etc/tradewave/secrets.env') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('TW2_API_PRICING_LIVE='):
                        v = line.partition('=')[2].strip().strip('"').strip("'")
        except OSError:
            pass
    return (v or '').strip().lower() in ('1', 'true', 'yes')


API_PRICING_LIVE = _pricing_live_flag()

# Annual billing = 10x the monthly price (pay for 10 months, get 12 = "2 months free",
# about 17% off). Stripe holds separate monthly and yearly prices per product;
# create_api_products.py and the console both read price_annual from this module.

# rate = (per_minute, per_day); opp_limit = max results per /opportunities call.
# Quotas are enforced per customer, not per key (auth.check_rate_limit buckets on
# user_id), so max_keys never multiplies the entitlement.
#
# `history` is RESERVED / NOT IMPLEMENTED (verified 2026-06-12): no code path consumes
# it - free keys receive the same live seasonal patterns as paid tiers. It is kept only as a
# placeholder for a possible future delayed-data free tier. Do NOT market it: the
# pricing page deliberately carries no data-freshness bullet until enforcement exists.
API_TIERS = {
    "free": {
        "name": "Free", "price_monthly": 0, "price_annual": 0,
        "markets": ["2"], "ml_access": True, "history": "delayed", "ml_daily_limit": 5,
        "opp_limit": 3, "rate": {"per_minute": 10, "per_day": 100}, "max_keys": 1,  # taste: a watchlist + browsing
        "stripe_price_metadata": None,
    },
    "dev": {
        "name": "Dev", "price_monthly": 39, "price_annual": 390,
        "markets": ["0", "1", "2", "3", "4", "11"], "ml_access": True, "history": "full", "ml_daily_limit": 100,  # markets narrowed to US stocks + ETFs (mirrors web Analyst); all 15 (futures/forex/bonds/crypto) reserved for Pro/Business
        "opp_limit": 100, "rate": {"per_minute": 60, "per_day": 5000}, "max_keys": 3,
        "stripe_price_metadata": {"product_line": "api", "tier": "dev"},
    },
    "pro": {
        "name": "Pro", "price_monthly": 199, "price_annual": 1990,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": None,  # unlimited ML = the Pro upsell
        "opp_limit": 1000, "rate": {"per_minute": 120, "per_day": 50000}, "max_keys": 10,
        "stripe_price_metadata": {"product_line": "api", "tier": "pro"},
    },
    "business": {
        "name": "Business", "price_monthly": 599, "price_annual": 5990,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": None,  # unlimited
        "opp_limit": 5000, "rate": {"per_minute": 300, "per_day": 250000}, "max_keys": 50,
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
    # BUNDLED entitlement for the Navigator ($19/mo) WEB sub - NOT a service principal, NOT sold
    # standalone (kept out of API_TIERS so it never appears in pricing/Stripe; resolved via tier_for()
    # + WEB_TIER_TO_API below). Without it a paying Navigator fell through to DEFAULT_TIER='free'
    # (S&P-only, 5 ML/day) = identical to a $0 Explorer. Scope mirrors config.level_access_hierarchy['2']
    # (Dow + NASDAQ + S&P). Do NOT remap navigator->'dev' (that leaks the wider U.S.
    # stock/ETF scope + 100 ML/day).
    "navigator": {
        "name": "Navigator", "price_monthly": 0, "price_annual": 0,
        "markets": ["0", "1", "2"], "ml_access": True, "history": "full", "ml_daily_limit": 5,
        "opp_limit": 25, "rate": {"per_minute": 30, "per_day": 1000}, "max_keys": 1,
        "stripe_price_metadata": None,
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

# Unified accounts: effective REST tier = MAX(explicit, bundled) on the rank ladder below
# (spec: docs/API_CONSOLE_USER_FLOWS.md §0/§7.1, decided 2026-07-06). This is also the
# "free key bundled into a paid web sub": a web Navigator gets the bundled 'navigator'
# entitlement (Dow/NASDAQ/S&P, 5 ML/day, NOT sold standalone), a web Analyst gets Dev API
# access, and a Strategist gets Pro API access, at no extra charge just by holding the web sub.
# MAX (not "explicit wins") matters because an explicit sub can be LOWER than the bundled
# tier: a Strategist (bundled pro) who also holds an explicit Dev sub must resolve pro, not
# be demoted to dev. MCP's merge_entitlements already MAXes; this makes REST match.
WEB_TIER_TO_API = {"explorer": "free", "navigator": "navigator", "analyst": "dev", "strategist": "pro"}

# Rank ladder for the MAX(explicit, bundled) rule above. Only the SOLD/bundled-sellable
# names belong here (API_TIERS + 'navigator', the one bundled-only INTERNAL_TIERS entry
# sold via a web plan) - service/internal principals (chatbot, mcp, demo) must never win
# or rank in this comparison, so they are deliberately absent (see api_tier_from_user).
API_TIER_RANK = {"free": 0, "navigator": 1, "dev": 2, "pro": 3, "business": 4}

# --- Consumer MCP (TradeWave inside ChatGPT/Claude via WorkOS login) -------------------
# The MCP USER layer MIRRORS the WEB subscription, NOT the API developer ladder: what a
# person bought on the website is exactly what they get inside the assistant. (auth.py's
# workos_principal branch used to route consumer-OAuth through the API ladder, which gave
# a web Analyst the Dev-API scope - subtly wrong.) These are full entitlement dicts in the
# same shape the gateway consumes (markets/ml_daily_limit/opp_limit/rate); rate caps are
# ASSISTANT-scaled (a human chatting makes a handful of tool calls/min), not data-feed
# scaled. Market scope mirrors the web ladder exactly: Explorer=DJ30, Navigator=Dow/NASDAQ/
# S&P, Analyst=US stocks+ETFs [0,1,2,3,4,11], Strategist=all 15.
# AI gating MIRRORS Ladder A (web AI starts at Analyst): explorer/navigator carry
# ml_daily_limit=0 in STEADY STATE - no permanent AI trickle. The in-chat AI taste comes
# ONLY via the two time-boxed teasers in auth._resolve_mcp (Explorer's reverse trial ->
# Strategist; Navigator's first-connect window -> Analyst), so losing it after the window
# is the loss-shaped upgrade trigger. This deliberately makes the SAME free identity behave
# 5/day on the BYO-key API but 0/day on consumer-MCP: API free = developer-eval taste; MCP
# mirrors your WEB plan, where AI starts at Analyst. NOT sold standalone (kept out of
# API_TIERS) and resolved only via auth._resolve_mcp().
WEB_TIER_TO_MCP = {
    "explorer": {
        "name": "Explorer (in-chat)", "price_monthly": 0, "price_annual": 0,
        "markets": ["0"], "ml_access": True, "history": "full", "ml_daily_limit": 0,
        "opp_limit": 10, "rate": {"per_minute": 20, "per_day": 400}, "max_keys": 0,
        "stripe_price_metadata": None,
    },
    "navigator": {
        "name": "Navigator (in-chat)", "price_monthly": 0, "price_annual": 0,
        "markets": ["0", "1", "2"], "ml_access": True, "history": "full", "ml_daily_limit": 0,
        "opp_limit": 25, "rate": {"per_minute": 30, "per_day": 1000}, "max_keys": 0,
        "stripe_price_metadata": None,
    },
    "analyst": {
        "name": "Analyst (in-chat)", "price_monthly": 0, "price_annual": 0,
        "markets": ["0", "1", "2", "3", "4", "11"], "ml_access": True, "history": "full", "ml_daily_limit": 100,
        "opp_limit": 100, "rate": {"per_minute": 60, "per_day": 5000}, "max_keys": 0,
        "stripe_price_metadata": None,
    },
    "strategist": {
        "name": "Strategist (in-chat)", "price_monthly": 0, "price_annual": 0,
        "markets": ALL_MARKETS, "ml_access": True, "history": "full", "ml_daily_limit": None,
        "opp_limit": 500, "rate": {"per_minute": 120, "per_day": 20000}, "max_keys": 0,
        "stripe_price_metadata": None,
    },
}


# Safety rail: the `service` delegation flag (X-TW-On-Behalf-Of in auth.py) must live ONLY on
# internal tiers, never on a sold one - otherwise a paying customer key could impersonate any
# user's metering. Fail loud at import if that invariant is ever violated by a future edit.
assert not any(t.get("service") for t in API_TIERS.values()), \
    "a sold API_TIERS entry has service:True - delegation must be INTERNAL_TIERS only"

# Safety rails for API_TIER_RANK (the MAX(explicit, bundled) ladder - spec §7.1): every
# name reachable via API_TIERS or the bundled WEB_TIER_TO_API mapping must be ranked, in
# ladder order, and rank must never include an unsold/internal principal (mcp/chatbot/demo)
# - those must fall through api_tier_from_user's "unrankable -> absent" branch, never win.
assert set(API_TIER_RANK) == set(API_TIERS) | {"navigator"}, \
    "API_TIER_RANK must cover exactly API_TIERS plus the bundled-only 'navigator' tier"
assert [API_TIER_RANK[n] for n in ("free", "navigator", "dev", "pro", "business")] == [0, 1, 2, 3, 4], \
    "API_TIER_RANK order must match the free < navigator < dev < pro < business ladder"
assert not (set(API_TIER_RANK) & (set(INTERNAL_TIERS) - {"navigator"})), \
    "a service/internal tier (chatbot/mcp/demo) leaked into API_TIER_RANK - it must never rank"

# Safety rails for the MCP mirror: it must cover exactly the web tiers (parity with
# WEB_TIER_TO_API), carry NO delegation flag (mirrors are entitlements, not principals),
# and only ever WIDEN scope up the ladder (a higher web tier never loses a market in chat).
assert set(WEB_TIER_TO_MCP) == set(WEB_TIER_TO_API), \
    "WEB_TIER_TO_MCP must mirror exactly the web tiers (parity with WEB_TIER_TO_API)"
assert not any(t.get("service") or t.get("workos_principal") for t in WEB_TIER_TO_MCP.values()), \
    "an MCP mirror entry has a delegation flag - mirrors are entitlements, never principals"
_MCP_LADDER = ["explorer", "navigator", "analyst", "strategist"]
for _lo, _hi in zip(_MCP_LADDER, _MCP_LADDER[1:]):
    assert set(WEB_TIER_TO_MCP[_lo]["markets"]) <= set(WEB_TIER_TO_MCP[_hi]["markets"]), \
        "MCP market scope regresses from %s to %s" % (_lo, _hi)


def tier_for(name):
    n = (name or "").lower()
    if n in API_TIERS:
        return API_TIERS[n]
    if n in INTERNAL_TIERS:   # internal principals (e.g. chatbot) - not in the sold catalog
        return INTERNAL_TIERS[n]
    return API_TIERS[DEFAULT_TIER]


def api_tier_from_user(user_row):
    """user_row is a dict with at least 'tier' (web tier) and optionally 'api_tier'.

    Effective tier = MAX(explicit, bundled) by API_TIER_RANK (spec §7.1): an explicit API
    subscription never DOWNGRADES a bundled one (e.g. a Strategist - bundled pro - who also
    holds an explicit dev sub resolves pro, not dev). An explicit value unranked by
    API_TIER_RANK (defensive: a service/internal name like 'mcp' or 'chatbot' should never
    reach here, but must never crash or grant anything if it does) is treated as absent."""
    explicit = (user_row.get("api_tier") if hasattr(user_row, "get") else None)
    bundled = WEB_TIER_TO_API.get(user_row.get("tier"), DEFAULT_TIER)
    if not explicit or explicit not in API_TIER_RANK:
        if explicit and explicit not in API_TIER_RANK:
            log.warning("api_tier_from_user: ignoring unrankable explicit api_tier=%r", explicit)
        return bundled
    if API_TIER_RANK[explicit] >= API_TIER_RANK.get(bundled, 0):
        return explicit
    return bundled


def mcp_tier_for(web_tier):
    """The consumer-MCP entitlement that MIRRORS a web subscription tier (NOT the API
    ladder). Falls back to the Explorer mirror (least privilege) for an unknown tier."""
    return WEB_TIER_TO_MCP.get((web_tier or "").lower(), WEB_TIER_TO_MCP["explorer"])


def merge_entitlements(a, b):
    """Field-wise MAX of two entitlement dicts (broader always wins). Used so a consumer
    who holds BOTH a web sub (-> the MCP mirror) AND an explicit standalone API sub is
    never DOWNGRADED inside the assistant - they keep the better of the two. Returns a new
    dict; inputs are not mutated. None ml_daily_limit (= unlimited) beats any finite cap."""
    merged = dict(a)
    merged["markets"] = sorted(set(a.get("markets") or []) | set(b.get("markets") or []), key=int)
    la, lb = a.get("ml_daily_limit"), b.get("ml_daily_limit")
    merged["ml_daily_limit"] = None if (la is None or lb is None) else max(la, lb)
    merged["opp_limit"] = max(a.get("opp_limit", 0), b.get("opp_limit", 0))
    ra, rb = a.get("rate") or {}, b.get("rate") or {}
    merged["rate"] = {
        "per_minute": max(ra.get("per_minute", 0), rb.get("per_minute", 0)),
        "per_day": max(ra.get("per_day", 0), rb.get("per_day", 0)),
    }
    merged["max_keys"] = max(a.get("max_keys", 0), b.get("max_keys", 0))
    merged["ml_access"] = bool(a.get("ml_access") or b.get("ml_access"))
    merged["history"] = "full" if "full" in (a.get("history"), b.get("history")) else a.get("history")
    return merged


def market_in_scope(tier_name, market_id):
    return str(market_id) in tier_for(tier_name)["markets"]


def ml_allowed(tier_name, market_id):
    t = tier_for(tier_name)
    return bool(t["ml_access"]) and str(market_id) in ML_MARKETS

