# Paid API Self-Service Rollout Readiness

Status as of 2026-07-20: the API, MCP server, OAuth connection, developer portal,
customer console, and subscription lifecycle are already deployed in production.
Paid self-service acquisition is intentionally closed by `TW2_API_PRICING_LIVE`;
the public pricing page therefore says Coming Soon. This is a pricing launch, not
a fresh API/MCP deployment.

## Current State

- Production web and app tiers were read-only verified clean at commit `b9242d1`.
  The API health check returns 200 and the API, MCP, appserver, and web services
  are active. The production pricing flag is unset on both tiers.
- The approved catalog is monthly only: Free $0, Dev $39, Pro $199, and Business
  $599. Daily request quotas are 100, 1,000, 5,000, and 20,000 respectively.
- Checkout idempotency, exact Stripe-catalog validation, dedicated portal
  validation, transactional key lifecycle, subscription entitlement updates,
  private/no-store raw-key responses, and split-topology proof-data behavior are
  already on `main`.
- `codex/complete-api-rollout` closes the last code-level launch risk: anonymous
  demo traffic is metered per client instead of every visitor sharing one global
  `demo` rate-limit and ML-quota bucket. Raw client addresses are never stored in
  Redis or usage records.
- Staging was fully verified on 2026-07-19, but on 2026-07-20 both public staging
  hosts returned Cloudflare 530 and the recorded staging web SSH endpoint refused
  connections. Restore staging before promotion. Do not bypass this gate.

## Guarded Rollout Order

All staging and production commands below are operator-run. Keep the flag off
until the applicable environment passes every gate.

1. Merge `codex/complete-api-rollout` to `main`, then restore staging network and
   host availability. Confirm both staging repositories are clean before deploy.
2. Deploy current `main` to staging with pricing still off:

   ```bash
   bash ops/deploy.sh staging
   ```

3. Re-run the existing staging auth and load gate with BYOK and WorkOS OAuth.
   Confirm API and MCP health, daily pick, concurrent scans, and the storm-breaker
   canary. Run the unit and database-marked commercial tests against the isolated
   staging/test database.
4. On the staging web tier, read-only verify that the Stripe TEST catalog contains
   exactly one active monthly API price for each paid tier, at $39, $199, and
   $599, and that the configured API Billing Portal is active, non-default,
   TEST-mode, and exposes only those prices:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask; ./venv/bin/python ops/verify_api_pricing_catalog.py --expect-mode test --expect-pricing off'
   ```
5. Set `TW2_API_PRICING_LIVE=1` in `/etc/tradewave/secrets.env` on both staging
   tiers. Restart `tradewave-web` on the web tier, restart
   `tradewave-apiserver` on the app tier, and then regenerate the app-tier static
   developer portal:

   ```bash
   sudo bash /home/flask/ops/assemble_developer_portal.sh
   ```

   Re-run the read-only audit with `--expect-pricing on`.

6. Complete one controlled staging purchase and cancellation. Verify checkout,
   webhook entitlement, key create/reveal/rotate/revoke, usage display, Billing
   Portal return, downgrade to Free, and that no raw key appears in logs or cache.
7. Deploy the verified commit to production while production pricing remains off:

   ```bash
   bash ops/deploy.sh prod
   ```

8. On the production web tier, read-only verify the LIVE Stripe catalog and
   dedicated portal. Confirm webhook delivery, API/MCP health, and a Free-tier key
   before changing visibility:

   ```bash
   sudo -u flask bash -lc 'set -a; . /etc/tradewave/secrets.env; set +a; cd /home/flask; ./venv/bin/python ops/verify_api_pricing_catalog.py --expect-mode live --expect-pricing off'
   ```
9. Only after explicit owner approval, set `TW2_API_PRICING_LIVE=1` in
   `/etc/tradewave/secrets.env` on both production tiers. Restart the same services
   and re-run `assemble_developer_portal.sh` on the production app tier.
   Re-run the read-only audit with `--expect-pricing on`.
10. Confirm the public pricing page exposes the paid plans, complete one controlled
    live purchase and cancellation, and verify the full key and entitlement
    lifecycle. Roll back visibility by setting the flag to `0`, restarting the
    affected services, and reassembling the portal if any commercial gate fails.

## Acceptance Criteria

- Staging is reachable, clean, current, and passes the release gate before any
  production promotion.
- Anonymous demo visitors have isolated rate-limit and ML-quota buckets; paid,
  OAuth, and service-account identities remain metered per customer.
- Stripe keys and catalog objects match the environment. The catalog is USD,
  monthly only, complete, and duplicate-free; the portal is dedicated and exact.
- Checkout and webhook processing are idempotent, and API subscription changes do
  not alter the separate web subscription tier.
- A user can buy, create and manage a key, see usage, manage billing, cancel, and
  return to Free without an operator repairing state.
- Raw API keys are shown only once, returned with private/no-store headers, and do
  not appear in logs, Redis metering keys, or analytics records.
- Production remains closed unless the owner approves the LIVE catalog and the
  controlled staging purchase has passed.
