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
7. **Activity rule.** Renewal commissions (not first-year) are paid only while the partner has brought in at least 1 new PAYING customer (first successful payment > 0; trials don't count) in the trailing 12 months plus a 30-day grace (13 months in effect; owner decision 2026-11-24) measured at the renewal payment's date. A partner whose only customer of the year renews 12 months later is still paid on that renewal. If not active, that renewal line earns $0 and is recorded as "lapsed" (forfeited, never paid later). Renewals resume with the next new paying customer.
8. **Cancel and return.** Same customer (Stripe customer) starts a new subscription within 12 months of the previous one ending: same partner keeps credit and the year count continues (no new first year). After 12 months: brand-new customer, credited to whoever refers them now, or nobody.
9. **Paused partner.** Commissions accrue during an admin pause and are HELD (state held, reason paused); they become payable when unpaused, or when the partner is terminated without cause. Forfeited only on termination for cause (admin action records cause). A termination without cause forfeits nothing, and that partner's final balance is paid even below the payout minimum (agreement 5.3 / 11.3).
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

Phase 1 (backend), run 2026-11-24 in the cloud session (no Postgres, Stripe mocked):

- `tests/test_affiliate_v2.py` - 133 passed. Every row of the acceptance table is asserted twice:
  through the pure rule helpers (`TestAcceptanceTable`) and through the engine on fake Stripe
  invoices (`TestEngineAcceptance`). Also covered: monthly month 12/13 and 60/61 boundaries, annual
  5th renewal $0 on 5-year terms, 10-year and lifetime terms, activity lapse and resume, a trial $0
  invoice not starting the clock, failed payment, late-paid invoice counted once, rerun idempotency,
  a booked line never re-priced, paused -> held -> paid on unpause, termination for cause, refund at
  the original rate after the partner changed discount, frozen paid month rolling new lines forward,
  negative-month carry, cancel and return within / after 12 months, campaign vs partner price both
  ways plus the tie, typed promo code attribution, founder guard (checkout + portal), checkout
  metadata stamping, single migration head.
- `tests/test_affiliate.py` - 25 passed (the old $24 assertions rewritten to the pool rule, $30).
- `tests/test_affiliate_gaps.py`, `test_affiliate_signing.py`, `test_affiliate_mcp.py`,
  `test_promo.py` - passed (1 skipped: `mcp` package not installed in the cloud venv).
- Checkout / webhook suites (`test_commercial_integrity.py`, `test_dunning.py`,
  `test_stripe_lifecycle.py`, `test_web_funnel_fixes.py`, `test_webhook_idempotency.py`,
  `test_appserver_concurrency.py`): every test that does not need Postgres passed. 51 tests in
  those files ERROR at fixture setup with `connection refused 127.0.0.1:5432` - the same 51 before
  this change (baseline at 1bae19e: 142 passed, 51 errors; after: 288 passed, 51 errors). They must
  be re-run on the dev box (`tradewave_test` database) before dev activation.
- Migration `b4d7e1f2a3c5`: single Alembic head; `alembic upgrade a7f3c2e9b1d4:b4d7e1f2a3c5 --sql`
  and the downgrade render cleanly. NOT yet applied to any Postgres database.

Not verified here (needs the dev box): the migration against real Postgres, the ledger SQL on
Postgres (tests run it on SQLite), a Stripe test-mode checkout end to end, campaign coupon creation
against the live Stripe API (`applies_to` + `redeem_by`), the Billing Portal cancel flow.

## Implementation and Handoff

Repository afshinmoshrefi/tradewave-tw2; branch `claude/affiliate-v2-20261124` from main ff59560.
Phase 1 commits are listed in the History section. Not pushed, not deployed.

### What Phase 1 built

- **Data model** (`web/models.py`, migration `b4d7e1f2a3c5_affiliate_program_v2.py`):
  `affiliate_terms`, `affiliate_discount_changes`, `promo_campaigns`,
  `affiliate_commission_lines`; new columns on `affiliates` and `affiliate_referrals`.
- **Engine** (`web/affiliate_service.py`): `classify_invoice`, `_compute`, `compute_month`,
  `compute_for_affiliate`, `upsert_month`. Architecture: `docs/TRADEWAVE_ECOSYSTEM.md`,
  "Affiliate program v2".
- **Checkout + webhook + founder guard** (`web/app.py`): `_resolve_checkout_offer`,
  `_is_new_customer`, `_campaign_catalog`, `_founder_subscription`, `_founder_portal_session`,
  `_affiliate_lifecycle_hook`, `GET /api/offers`, `offers` in the `/join/<code>` context.
- **Config** (`config.py`, env-agnostic): `FOUNDER_PRICE_IDS` (`TW2_FOUNDER_PRICE_IDS`),
  `FOUNDER_BILLING_PORTAL_CONFIGURATION_ID` (`TW2_FOUNDER_BILLING_PORTAL_CONFIGURATION_ID`),
  `AFFILIATE_PAID_LOOKBACK_DAYS` (`TW2_AFFILIATE_PAID_LOOKBACK_DAYS`, default 120).

### Service functions for the Phase 2 UI (`import affiliate_service as afs`)

Pure previews (cents in, cents out; `terms=None` uses the v2 default):
`preview_offer(list_price_cents, discount_pct, terms=None)`,
`preview_promo(promo_price_cents, list_price_cents=None, terms=None)`,
`preview_renewal(paid_cents, terms=None)`, `renewal_schedule(terms=None)`,
`activity_status(affiliate, now=None, *, first_paid_dates=None, session=None, terms=None)`,
`is_payment_line(line)`.

Partner: `set_partner_discount(session, affiliate, new_pct, *, interval="year", actor=None,
now=None, enforce_cooldown=True)`, `next_discount_change_at(affiliate, now=None)`,
`discount_history(session, affiliate, limit=50)`, `terms_for(session, affiliate)`,
`compute_for_affiliate(session, affiliate, year, month)` (rows carry `lines`, `held_amount`,
`lapsed_count`).

Admin: `list_terms(session)`, `get_terms(session, terms_id=None)`, `create_terms(session, version,
*, pool_pct=50, max_discount_pct=25, promo_commission_pct=50, renewal_pct=25, renewal_years=5,
activity_rule_months=12, notes=None)`, `assign_terms(session, affiliate, terms_id, actor=None)`,
`terminate_for_cause(session, affiliate, cause, actor=None, now=None)`,
`create_campaign(session, *, name, tiers, intervals, starts_at, ends_at, offer_type, catalog,
intro_prices=None, percent_off=None, intro_months=12, new_customers_only=True, status="active",
notes=None, code=None)`, `update_campaign(session, campaign, *, catalog=None, **changes)`,
`list_campaigns(session, include_archived=True)`, `active_campaign_for(session, tier, interval,
list_price_cents, now=None)`, `display_offers(session, affiliate, catalog, now=None,
is_new_customer=True)`, `sync_line_states(session)` (call after marking a payout paid),
`compute_month` / `upsert_month` (unchanged signatures). `catalog` = `app._campaign_catalog()`.

### Design decisions that are expensive to change (storage names)

- Column `billing_interval` (values `month` | `year`, Stripe's `recurring.interval`), not
  `interval`: INTERVAL is an SQL type name. Offer keys inside campaign JSON are `<tier>:<interval>`.
- Table `promo_campaigns`, not `affiliate_campaigns`: a campaign is company-wide and a direct sale
  can claim it. `tiers`, `billing_intervals`, `intro_prices`, `stripe_coupon_ids` are JSONB (not
  `text[]`) so the per-plan maps and the lists share one type.
- Ledger UNIQUE is `(affiliate_id, source_id)` WITHOUT `kind`: with `kind` in the key a rerun
  that classified the same invoice differently (renewal vs lapsed) could add a second line.
- `affiliate_terms.renewal_years` is the LAST commission year (5 = years 2-5), NULL = lifetime.
- `estimated` is a compute-output state only; it is never stored.

### Owner decisions still open (the build picked the conservative reading)

Decided since the first draft of this list, and no longer open:

- **Activity window** (was item 2): decided 2026-11-24 - trailing 12 months PLUS a 30-day grace
  (13 months in effect), see rule 7. A returning customer still does not count as a new one.
- **Plain termination** (was item 3): the signed agreement decides it (5.3 / 11.3) - a termination
  without cause forfeits nothing. Commission on payments already made stays payable and the final
  balance is paid regardless of the $50 minimum. Only `terminate_for_cause` forfeits.

These remain open:

1. **Return within 12 months** carries the ORIGINAL year-1 anchor by calendar time (the gap
   counts toward the year count). The alternative - counting only months of paid service - pays
   the partner more first-year commission.
2. **Tie** between campaign and partner price goes to the partner offer (pool rule).
3. **Legacy partners are paused by the migration** until they re-sign agreement v2. The agreement
   v2 text (`AGREEMENT_VERSION`) and its signing copy must ship in the same deploy.

### Deploy steps (not done)

1. `alembic upgrade head` (b4d7e1f2a3c5).
2. Once, after the migration: `affiliate_service.reconcile_v2_stripe(session)`. It deactivates the
   codes of paused partners and re-issues every coupon that no longer matches the (clamped to 25%)
   discount: the annual coupon and the monthly override coupon. Until it has run, a coupon that
   disagrees with the stored discount is simply not applied at checkout (the customer pays the list
   price and 0% is stamped).
3. Set `TW2_FOUNDER_PRICE_IDS` in `/etc/tradewave/secrets.env` (or tag the founder price/product
   with metadata `tw2_founder=true`).
4. **DEPLOY BLOCKER - founder Billing Portal configuration.** Whenever `TW2_FOUNDER_PRICE_IDS` is
   set, `TW2_FOUNDER_BILLING_PORTAL_CONFIGURATION_ID` MUST be set too. Do not deploy without it.
   The web/EOD portal configuration is not managed in code, so this is done by hand, once per
   Stripe account (test mode for dev/staging, live mode for production):
   1. Stripe dashboard: Settings > Billing > Customer portal.
   2. Add a configuration (a second one, next to the default).
   3. Subscription update ("Customers can switch plans"): OFF.
   4. Cancel subscriptions: ON. Leave payment method update and invoice history ON so a founder
      can still fix a failed card.
   5. Save, then copy the configuration id (it starts with `bpc_`).
   6. Put it in `/etc/tradewave/secrets.env` as `TW2_FOUNDER_BILLING_PORTAL_CONFIGURATION_ID=bpc_...`
      and restart gunicorn.

   What happens without it: the app logs a `DEPLOY BLOCKER` error at every startup
   (`app.warn_founder_portal_config`); `/account/manage-subscription` sends a founder into the
   portal's cancel flow, which is a deep link and not a hard restriction; and the dunning
   final-notice email gives a founder the plain `/account` link instead of a card-update portal
   link (a founder is never given a default portal session, because that one allows a plan switch).
5. Restart gunicorn. Check the log for `DEPLOY BLOCKER` (there must be none).
6. Dev box only, before activation: run the Postgres suites that the cloud session cannot run,
   including `tests/test_dunning.py` (its portal stub was changed for the founder guard).

### Not built in Phase 1

- Admin and partner UI, agreement v2, partner guide (Phase 2 - built since, see History).

### Code review fixes (2026-11-24, branch `fix-review` from ae9a1e4)

An independent review found seven defects; all are fixed, each with a regression test in
`tests/test_affiliate_review_fixes.py` that failed before the fix.

1. **Monthly coupon above the cap.** `reconcile_v2_stripe` re-issues (or drops) the monthly
   override coupon too. `_partner_spec` never applies a coupon whose Stripe `percent_off` differs
   from the discount being stamped: it falls back to the flat coupon when that one matches, else
   no coupon and a 0% stamp. One limit: if Stripe cannot be asked for the coupon's percent at that
   moment, the coupon is still applied (the engine's `extra_discount` guard then protects the
   payout); a known mismatch is never applied.
2. **Termination without cause.** Lines are payable, not held; lines held while paused are
   released by a plain termination; the payout minimum does not block the final balance. New admin
   action "Release held lines" on the Change terms page. `terminate_for_cause` itself now voids
   pending payout rows and lines already on an unpaid payout row (was only in `affiliate_admin`).
3. **Transient Stripe error.** A failed lookup raises `StripeLookupError`; the invoice or reversal
   is skipped for the run (no line, nothing persisted, logged, listed on the compute page). A
   guessed clock is never persisted; an unresolved activity check never books `lapsed`.
4. **Founder guard.** The dunning email no longer creates a default portal session for a founder;
   startup check + deploy blocker above.
5. **Refunds / disputes.** Won disputes and failed / canceled refunds get an offsetting positive
   line (`<id>:won`, `<id>:failed`); an inquiry that escalates later is clawed back when first seen
   as a dispute. Lookback `TW2_AFFILIATE_REVERSAL_LOOKBACK_DAYS` (180). Known limit: an event older
   than the lookback at the time its status changes is not followed. The give-back keeps the kind
   `refund` / `dispute` with a positive amount (no schema change); the admin ledger labels it
   "Chargeback won - commission restored" / "Refund failed - commission restored". The partner
   dashboard shows it under the plain kind label until its templates are updated.
6. **New customer.** Only web/EOD-line subscriptions that are live or ever had a payment above $0
   count; abandoned checkouts, unpaid trials and Developer API subscriptions do not.
7. **Documents.** Agreement 4.2 and Exhibit A say one Customer Discount applies to monthly and
   annual plans (a separate monthly value only where Company set one); the ecosystem doc has the
   30-day grace and the attribution precedence (a partner code in the URL at checkout beats the
   first-touch cookie).

Tests after the fixes (cloud session, no Postgres): `tests/test_affiliate*.py tests/test_promo*.py`
401 passed, 1 skipped (359 before). Not run here: the Postgres suites.

## Environment Verification

Dev: pending. Staging and production: not changed.

## History

- 2026-11-24: Gap analysis, owner decisions recorded, build started.
- 2026-11-24: Phase 1 backend committed on `claude/affiliate-v2-20261124`. Not pushed, not deployed.
  - a31944f data model and migration b4d7e1f2a3c5
  - 747ca08 commission engine and partner services
  - c48e6e7 checkout offer, typed-code attribution, founder guard, ecosystem doc, v2 tests
  - this commit: task record
- 2026-11-24: Independent code review, seven findings fixed on branch `fix-review` (from ae9a1e4);
  see "Code review fixes". Not pushed, not deployed.
