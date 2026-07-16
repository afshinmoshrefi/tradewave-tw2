# PatternCard Contract Deviation

> Status: OPEN for the integrator, reported 2026-07-14.

`api/PATTERNCARD_SPEC.md` is explicitly integrator-owned and read-only for agents.
Its ML entitlement language still says `ml_win_prob` and ML fields are Pro-only.
That statement no longer matches the implemented and published contract.

## Implemented behavior

- ML is available only on eligible market ids `0,1,2,3,4,11`.
- Free receives 5 ML scores per day.
- Dev receives 100 ML scores per day.
- Pro and Business receive unlimited ML scores.
- When quota is exhausted or the market is ineligible, the card remains valid with
  `ml: null` and an explanatory tier or quota note.

Runtime authority: `apiserver/tiers.py`, `apiserver/ml_quota.py`, and
`apiserver/routes.py`. `api/openapi.yaml` already describes the tier-metered behavior.

## Integrator action

Update the Pro-only statements in `api/PATTERNCARD_SPEC.md` at the next contract
revision. No response-schema or runtime change is required. Keep the distinction
between `historical_win_rate` and `ml_win_prob` unchanged.
