# TradeWave Product and Pricing Decisions

> Status: CURRENT decision record, reconciled to the implemented product on 2026-07-14.
> This document replaces the pricing recommendations in
> `FREE_PAID_STRATEGY_RESEARCH.md`, `PRICING_TIERING_RECOMMENDATION.md`, and the
> pre-launch portions of `API_MCP_STRATEGY.md`. Those files remain historical research.

## Source priority

When a document and the product disagree, use this order:

1. Web access enforcement: `config.py`, `web/tier_compat.py`, and the server-side clamps.
2. Web consumer prices: active Stripe metadata read by `site/generate_home_page.py`.
3. API and MCP entitlements: `apiserver/tiers.py` plus teaser resolution in
   `apiserver/auth.py`.
4. Cross-surface reference: `docs/PRICING_QUOTA_SPEC.md`.
5. This document for the business decision and marketing interpretation.

Never use an older research brief to override a shipped gate or active Stripe price.

## Decided consumer ladder

| Tier | Monthly | Annual charge | Annual equivalent | Permanent market access | AI scoring | Role |
|---|---:|---:|---:|---|---|---|
| Explorer | $0 | $0 | $0 | Dow 30 | No | Useful free floor and acquisition |
| Navigator | $19 | $168 | $14/mo | Dow 30, NASDAQ 100, S&P 500 | No | Entry paid breadth and date control |
| Analyst | $47 | $399 | $33.25/mo | All U.S. stocks and ETFs | Yes | Core paid plan |
| Strategist | $129 | $1,188 | $99/mo | All 15 markets | Yes, on U.S. stocks and ETFs | Highlighted multi-asset premium anchor |

The live structure is Ladder A. AI scoring starts at Analyst. Explorer and Navigator
can see an AI upgrade affordance, but they do not receive permanent AI scores.
Strategist expands market breadth; it does not expand AI coverage beyond the U.S.
stock and ETF markets scored for Analyst.

## Trial decisions

- A new free signup receives seven days of full Strategist access without a card.
  The billing tier remains Explorer; access elevation ends automatically and falls
  back to the permanent Explorer entitlement.
- A customer who selects a paid plan at checkout also receives a seven-day trial,
  with a card collected by Stripe.
- The Explorer reverse trial applies on the web and consumer MCP surfaces.
- Navigator receives a separate one-time, seven-day Analyst-scope MCP teaser on its
  first MCP connection. That teaser is temporary exposure, not a Navigator feature.

## Decisions closed by this reconciliation

- Keep Analyst at $47 monthly and $399 annually. The proposed $39 reprice is not adopted.
- Keep Strategist at $129 monthly and $1,188 annually. The older $149, $199, and
  post-launch-hike figures are retired.
- Keep Navigator as the implemented $19 tier. It is the shipped version of the proposed
  catch rung, but it has three markets and no permanent AI scoring.
- Keep Explorer AI off after the reverse trial. The ML-on-free proposal is not adopted.
- Keep annual pricing selected by default on the public pricing presentation.
- Keep Strategist highlighted on the current four-card pricing presentation; this is an
  anchor/premium-path decision, not a claim that it is the smallest suitable plan.
- Do not advertise a standing 72-hour coupon, Desk tier, automatic PE-cycle advantage,
  or a different price until the capability or offer is separately approved and live.

## Programmatic products

The developer API is a separate product ladder configured at Free / Dev $39 / Pro
$199 / Business $599, with annual prices equal to ten monthly payments. Paid API
price display and self-serve acquisition remain gated by `TW2_API_PRICING_LIVE`; until
that flag is enabled, these are configured prices rather than a public acquisition offer.

Consumer MCP is included with the web subscription and mirrors the web tier. It is not
sold as another SKU and it does not use the standalone API ladder for normal OAuth users.
A web subscription can separately bundle API-key access through `WEB_TIER_TO_API`.

## Marketing interpretation

The product promise is not "MCP access" or generic "AI-powered trading." Those are
delivery mechanisms and features. The durable position is:

> Auditable seasonal research: ranked setups, ML-calibrated probabilities, and a
> public record that leaves every win and loss visible.

Use the tier ladder to sell progressively broader research access:

- Explorer proves the historical method on a narrow universe.
- Navigator sells more U.S. index breadth and date control.
- Analyst adds the ML calibration layer and the full U.S. stock and ETF universe.
- Strategist adds all supported asset classes and premium workflow capacity.

## Change control

Any future pricing or entitlement decision must update, in the same change:

1. the enforcing code or Stripe metadata;
2. `docs/PRICING_QUOTA_SPEC.md`;
3. `docs/TRADEWAVE_ECOSYSTEM.md` when implementation truth changes; and
4. this decision record plus affected customer-facing copy.

Historical research should be labeled as such, never silently edited into a new decision.
