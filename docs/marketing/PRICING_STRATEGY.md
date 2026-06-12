# TradeWave Pricing Strategy
> Decided with the owner 2026-06-12. The core insight: the price is a STRUCTURE, not a number -
> willingness to pay spans $20/mo (hobbyist) to $10k+/yr (RIA/fund) for the same software, so
> maximum return = tiered capture with an anchor, not a single optimal point.

## The four principles

1. **Price the segments, not the product.** The value metric ladder is already built: market
   coverage, depth (patterns/portfolios), ML, API/export rights.
2. **The "too cheap = no value" problem is solved by an ANCHOR above, not by raising the core
   price.** A visible expensive tier makes $99/mo read as serious.
3. **The "too expensive = won't try" problem is solved by the reverse trial, not the price.**
   Everyone tries at $0 (7 days of everything, no card); price resistance only matters at the
   upgrade moment, after value is felt.
4. **Discover, don't guess.** Iterate with grandfathering as the safety net. Instruments:
   the launch->post price split already in config ($47/$149 -> $58/$199), a 5-question survey
   to the 22 payers (also the testimonial ask), and the ONE metric: trial-to-paid conversion
   (<5% = price/value story off; 8-15% = healthy; >20% with no grumbling = underpriced, raise).

## The structure

| Tier | Price | Role |
|---|---|---|
| Explorer | Free (DJ30 after the 7-day full trial) | Funnel + ledger audience |
| Analyst | $47/mo, $37/mo annual | Entry paid; just under the incumbent's $49.95 with more machine. Never go lower. |
| Strategist | $149/mo, $99/mo annual | THE hero tier we market. Fold API/MCP dev access in ("your scans inside ChatGPT and your own code") - the justification for pricing above the incumbent's $100 Pro. |
| Desk (NEW) | "From $4,800/yr - talk to us" | Mostly an ANCHOR + the manual RIA/fund conversation: seats, API volume, historical signal file for internal backtests, priority support, invoicing. No self-serve. One deal = ~40 Analyst subs. |

- **Founding framing with a real deadline:** current prices locked FOR LIFE through the launch
  window (tie to the affiliate push), then list rises to $58/$199 (already wired as
  monthly_price_post). Announce the rise - the deadline is honest and converts fence-sitters.
- Existing 22 payers: FROZEN where they are, never touched (standing rule).
- Future increases always grandfather - every raise becomes a loyalty gift, not a churn event.

## Anti-patterns (decided against)
- A $20 tier: churn-heavy cohort, support drain, and the exact "no value" signal feared.
- Usage-metered pricing for the core product (retail traders hate variable bills; metering
  stays where it is - the API/ML daily allowances).
- Annual-only: monthly is the trust bridge for a young brand; the annual discount migrates.

## Context notes
- At ~300 accounts the binding constraint is FUNNEL VOLUME, not price elasticity - affiliates,
  the MCP launch, and the home page rebuild matter more than $47-vs-$39.
- TradeWave Realtime (Anne-Marie) prices separately (~$99/mo founding planned); the EOD+RT
  "TradeWave Complete" bundle uses the contract's standalone-price formula.
- API product line keeps its own tiers (Free/$39/$199/$599 + Founder $99) for API-only buyers;
  Strategist subsumes the dev tier for platform subscribers.

## Next actions
- [ ] Draft the 5-question pricing survey + testimonial ask to the 22 payers (Claude task).
- [ ] Add the Desk tier card to the pricing page spec (anchor presentation, contact CTA).
- [ ] Set the founding-window deadline date when the affiliate/MCP launch dates are fixed.
