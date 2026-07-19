# TradeWave Per-Tier Product and Quota Specification

> Status: CURRENT and implemented, code-verified 2026-07-14.
> Business decisions are summarized in `docs/marketing/PRICING_STRATEGY.md`.

This specification records the shipped relationship between the web app, consumer
MCP, and standalone developer API. It replaces the 2026-06-17 proposal that treated
MCP and the standalone API as one entitlement ladder.

## 1. Cross-surface rules

1. The web app is the consumer product. Its permanent tier is Explorer, Navigator,
   Analyst, or Strategist.
2. Consumer MCP mirrors the web subscription. It has assistant-scaled result and rate
   limits, but the same market and AI fence as the permanent web tier.
3. The standalone API is a separate developer product with Free, Dev, Pro, and
   Business tiers.
4. A web subscription can include bundled API-key access through `WEB_TIER_TO_API`.
   This mapping does not redefine the consumer MCP entitlement.
5. An active Explorer reverse trial temporarily resolves to Strategist on web and MCP.
   It never mutates the stored billing tier.
6. AI scoring is available only for resource ids `0,1,2,3,4,11`. Strategist adds other
   asset classes, but those additional markets do not receive ML scores.
7. Resource ids `0` through `16` are permanent. The absent ids `14` and `15` are never
   reused.

## 2. Web consumer tiers

Runtime sources: the enforced level dictionaries and `ml_score_access_levels` in
`config.py`, with tier mapping in `web/tier_compat.py`. `TIER_FEATURES` is a reference
mirror; it is not the general enforcement path.

| Entitlement | Explorer | Navigator | Analyst | Strategist |
|---|---:|---:|---:|---:|
| Monthly price | $0 | $19 | $47 | $129 |
| Annual charge | $0 | $168 | $399 | $1,188 |
| Annual equivalent | $0 | $14/mo | $33.25/mo | $99/mo |
| Markets | `0` | `0,1,2` | `0,1,2,3,4,11` | All 15 |
| Market description | Dow 30 | Dow 30, NASDAQ 100, S&P 500 | U.S. stocks and ETFs | All supported asset classes |
| AI scoring | No | No | Yes | Yes, on `0,1,2,3,4,11` only |
| Start-date control | Locked to today | Unlocked | Unlocked | Unlocked |
| Historical lookback cap | 10 years | 15 years | No tier cap | No tier cap |
| Portfolios | 1 | 3 | 25 | 100 |
| Published date-range reports, lifetime / day | 5 / 10 | 25 / 25 | 100 / 100 | 500 / 500 |
| Watchlists | 0 | 1 | 10 | 50 |
| Symbols per watchlist | 0 | 25 | 50 | 100 |

The opportunity table returns at most five results for steady-state Explorer or a
date-locked request. Paid, date-unlocked tiers receive the full ranked result set up to
the service-wide cap. The vestigial `top_patterns_per_market` values in `TIER_FEATURES`
must not be marketed as paid-tier result limits.

### Trial behavior

- New free signup: seven days of effective Strategist access, no card required, then
  the stored Explorer tier resumes.
- Paid-plan checkout: seven-day trial with a card collected at checkout.
- Reverse-trial expiry is implicit in `effective_tier()` and requires no tier mutation
  or expiry cron.

## 3. Consumer MCP entitlements

Runtime source: `apiserver/tiers.py:WEB_TIER_TO_MCP`, resolved by
`apiserver/auth.py:_resolve_mcp`.

| Entitlement | Explorer | Navigator | Analyst | Strategist |
|---|---:|---:|---:|---:|
| Markets | `0` | `0,1,2` | `0,1,2,3,4,11` | All 15 |
| ML scores per day | 0 | 0 | 100 | Unlimited |
| Results per call | 10 | 25 | 100 | 500 |
| Rate per minute / day | 20 / 400 | 30 / 1,000 | 60 / 1,000 | 120 / 2,000 |

Temporary MCP exposure is explicit and machine-readable through `teaser_state`:

- Active Explorer reverse trial: Strategist MCP scope until the same web-trial cutoff,
  then Explorer scope.
- Navigator first MCP connection: one-time seven-day Analyst scope, then Navigator
  scope.
- A separately purchased API subscription may widen MCP markets and rate limits through
  a field-wise merge. It does not bypass the steady-state Explorer or Navigator MCP AI
  fence.

## 4. Standalone developer API

Runtime source: `apiserver/tiers.py:API_TIERS`. Paid prices are configured, but public
price display and self-serve acquisition are hidden while `TW2_API_PRICING_LIVE` is off.

Billing is monthly only (owner decision 2026-07-05, reaffirmed 2026-07-17, pre-launch
so no grandfathering). There is no annual API price; `price_annual` does not exist
anywhere in `apiserver/tiers.py`, the seeder, the console, or the pricing page.

| Entitlement | Free | Dev | Pro | Business |
|---|---:|---:|---:|---:|
| Monthly price | $0 | $39 | $199 | $599 |
| Markets | `2` | `0,1,2,3,4,11` | All 15 | All 15 |
| ML scores per day | 5 | 100 | Unlimited | Unlimited |
| Results per call | 3 | 100 | 1,000 | 5,000 |
| Rate per minute / day | 10 / 100 | 60 / 1,000 | 120 / 5,000 | 300 / 20,000 |
| API keys | 1 | 3 | 10 | 50 |

The `history` field is reserved and not enforced. Do not market a delayed-versus-full
data distinction until a runtime path implements it.

## 5. Bundled API-key access for web subscribers

Runtime source: `apiserver/tiers.py:WEB_TIER_TO_API`.

| Web subscription | Bundled API entitlement | Markets | ML/day |
|---|---|---|---:|
| Explorer | Free | S&P 500 (`2`) | 5 |
| Navigator | Internal Navigator | `0,1,2` | 5 |
| Analyst | Dev | `0,1,2,3,4,11` | 100 |
| Strategist | Pro | All 15 | Unlimited |

This table explains why the same account can have different steady-state AI behavior
on consumer MCP and a developer API key. MCP mirrors the web product; the API key is a
metered developer evaluation or bundled developer entitlement.

## 6. Source-of-truth and update checklist

- Web enforcement: `config.py` plus server-side clamps and `web/tier_compat.py`.
- Web price display: active Stripe metadata read by `site/generate_home_page.py`.
- API and MCP enforcement: `apiserver/tiers.py`, `apiserver/auth.py`, and
  `apiserver/ml_quota.py`.
- Reverse-trial and Navigator-teaser cutoff math: `reverse_trial.py`.

Any tier or price change must update the enforcing source, this specification,
`docs/marketing/PRICING_STRATEGY.md`, `docs/TRADEWAVE_ECOSYSTEM.md`, tests, and affected
customer-facing copy in one change.
