# TW-TASK-0038: Affiliate program v2 - pool pricing, promotions, renewals, partner dashboard

- Status: in-progress
- Confidence: reproduced (gap analysis at main ff59560)
- Priority: P2 - new commercial program; current engine underpays the new rules ($24 vs $30) and loses renewals on typed codes
- First observed / last updated: 2026-11-24
- Executor/session/claim time: Claude Code (cloud session), 2026-11-24
- Authorization: Afshin approved building the full feature (2026-11-24, project thread "Add affiliate promotions and renewal commissions"). Staging and production excluded.

## Goal, Scope and Acceptance

Owner-approved rules (2026-11-24). All money examples assume fully paid, no tax, no refund.

1. **Regular first year (pool rule).** Each partner has a 50% pool of the regular pre-tax LIST price for the plan + billing interval. The partner picks a customer discount from 0% to 25% (hard cap on every plan). Partner earns (50 - discount)% of LIST price. $100 plan: 0% off -> pays $100, partner $50; 5% -> $95 / $45; 20% -> $80 / $30. TradeWave always retains 50% of list.
2. **Self-serve discount.** Partner changes the discount on the dashboard (0-25%), no re-signing, no pause. A change applies only to customers whose checkout starts after the save; existing subscribers keep their coupon and their terms. Limit one change per 24 h. Keep change history.
3. **Company-wide promotions (campaigns).** Admin creates a campaign: name, eligible plans (tier) and intervals, new-customers-only flag (always true for now), claim window start + end (UTC), and the intro offer: either a fixed first-period price or a percent off, plus how long the intro lasts (annual: 1 billing period; monthly: 12 months). Renewal is at the regular price.
4. **Referred promo sale.** Partner keeps referral credit and earns 50% of what the customer actually paid (pre-tax). $99 sale -> $49.50; $50 -> $25. Direct promo sale (no partner) -> $0 commission.
5. **One customer offer per purchase.** If the visitor has a partner AND an eligible campaign, the customer gets whichever FIRST-PERIOD price is lower. Campaign wins -> promo rule (50% of paid). Partner discount wins -> pool rule. Never stack.
6. **Renewals.** From year 2 the partner earns the renewal rate (25%) of what the customer actually pays at renewal, pre-tax (a founder renewing at $189 -> $47.25). $399 annual renewal -> $99.75. Renewal length is a per-agreement setting: 5 years (default: commission years 2-5), 10 years (years 2-10), or lifetime. Year 1 = the first 12 months of paid service starting at the subscription's first successful payment with amount_paid > 0 (trial $0 invoices and failed payments never start the clock). Use the invoice line SERVICE PERIOD (line.period.start), not invoice.created, to place a payment in a year. Annual: 4 eligible renewals under the 5-year setting. Monthly: months 1-12 first-year rule, 13-60 renewal rate, 61+ $0.
7. **Activity rule.** Renewal commissions (not first-year) are paid only while the partner has brought in at least 1 new PAYING customer (first successful payment > 0; trials don't count) in the trailing 12 months measured at the renewal payment's date. If not active, that renewal line earns $0 and is recorded as "lapsed" (forfeited, never paid later). Renewals resume with the next new paying customer.
8. **Cancel and return.** Same customer (Stripe customer) starts a new subscription within 12 months of the previous one ending: same partner keeps credit and the year count continues (no new first year). After 12 months: brand-new customer, credited to whoever refers them now, or nobody.
9. **Paused partner.** Commissions accrue during an admin pause and are HELD (state held, reason paused); they become payable when unpaused. Forfeited only on termination for cause (admin action records cause).
10. **Founders ($189 legacy price).** Founders may only cancel in self-serve billing: no plan, interval or price changes via checkout or the Billing Portal update flow. Founders cannot claim campaigns (campaigns are new-customer only). Detection: a subscription whose price is a legacy/founder price; add config `FOUNDER_PRICE_IDS` (env, comma-separated) plus product/price metadata `tw2_founder=true` as the two signals.
11. **Terms are prospective and reproducible.** Every referral is stamped with the terms version, offer type (regular / promo), campaign id, interval, list price and discount at checkout. Payouts read terms from the referral, never from the partner's current row. Changing terms never re-prices a past line. Ledger lines (per invoice) are immutable once the month is finalized; refunds/chargebacks reverse at the ORIGINAL line's rate and formula.
12. **Legacy.** No partner-referred customers exist yet, so no grandfathering of customers. Existing affiliate rows get migrated to terms v2 defaults (pool 50, their discount clamped to 25, renewal 25, 5 years) but MUST re-sign agreement v2 before their link works on v2 terms (existing re-sign flow). Keep the old engine path only as long as needed for tests of historic statements.

Payout minimum $50 (small-balance hold, existing). Tax form still required before "mark paid".

## Acceptance checks (dollar results)

| Case | Customer pays | Partner earns | TW retains |
|---|---|---|---|
| Direct $100 | $100 | $0 | $100 |
| Referral 0% off, $100 | $100 | $50 | $50 |
| Referral 5% off | $95 | $45 | $50 |
| Referral 20% off | $80 | $30 | $50 |
| Direct $99 promo | $99 | $0 | $99 |
| Referred $99 promo | $99 | $49.50 | $49.50 |
| Referred $50 promo | $50 | $25 | $25 |
| $399 renewal years 2-5 | $399 | $99.75 | $299.25 |
| $399 renewal year 6+ (5-yr setting) | $399 | $0 | $399 |
| Same, lifetime setting, partner active | $399 | $99.75 | $299.25 |
| Same, partner inactive 12+ months | $399 | $0 (lapsed) | $399 |
| Full refund of the $80 sale | -$80 | -$30 | |
| $40 partial refund of the $80 sale | -$40 | -$15 | |
| Tax $8 on the $100 0%-off sale | $108 | $50 | |

## Implementation plan (phases)

- Phase 1 backend (models, migration, engine, checkout, webhook, campaigns in Stripe, founder guard, tests).
- Phase 2 in parallel: admin UI; partner dashboard redesign; documents (agreement v2, partner guide, ecosystem doc, MCP view).
- Phase 3 integrate, full affiliate test run, push, PR; dev activation via Remote Control on Afshin's PC (dev box is LAN-only).

Partner dashboard design: see the FABLE review recorded in the gap-analysis doc (seven tabs Home, Earnings, Customers, Links, Promote, Payouts, Settings).

## Evidence and Investigation

Gap analysis (Claude Doc, 2026-11-24) at main ff59560: engine basis = amount_paid - tax times current commission_pct (web/affiliate_service.py:697-704), asserted $24 in tests/test_affiliate.py:127-128; typed affiliate codes write no affiliate_referrals row (web/app.py:2695-2720, 3889); checkout ignores users.referred_by_affiliate_id; rate changes re-price pending months; no campaign object; no founder guard.

## Acceptance and Regression Checks

Pending.

## Implementation and Handoff

Repository afshinmoshrefi/tradewave-tw2; branch claude/affiliate-v2-20261124 from main ff59560. Source SHA pending.

## Environment Verification

Dev: pending. Staging and production: not changed.

## History

- 2026-11-24: Gap analysis, owner decisions recorded, build started.
