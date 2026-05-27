# TradeWave MCP server - tool schema (DRAFT, 2026-05-27)

Thin wrapper over the v1 API (`openapi.yaml`). Tools are phrased for agents
("give me tradeable answers"), NOT a 1:1 mirror of the 73 internal appserver routes.

**Auth:** BYOK for v1 - the caller's TradeWave API key gates the server; tier and
entitlements flow from `users.api_key_hash`. (Remote OAuth via WorkOS is a later add.)

**Safety contract (same as the API):** signals only - no raw OHLCV / last price /
price-by-date. Returns are percentages, never price levels. ML tools are Pro-only and
degrade gracefully (return an upgrade stub, never an error) for non-Pro callers.

| Tool | Inputs | Returns | Tier |
|---|---|---|---|
| `list_markets` | - | the 17 markets + which are in the caller's scope | all |
| `list_symbols` | `market` | symbols in a market | all |
| `get_seasonal_opportunities` | `market`, `from?`, `to?`, `direction?`, `min_win_rate?`, `limit?` | ranked seasonal setups (symbol, direction, entry, hold, sharpe, avg/median %, win rate) | all (result count + ML gated by tier) |
| `get_opportunity_for_symbol` | `symbol`, `market` | seasonal setups for one symbol | all |
| `get_seasonal_pattern` | `market`, `symbol` | aggregate seasonal pattern stats (no price series) | all |
| `get_opportunity_chart` | `market`, `symbol`, `entry_date?`, `days_out?`, `direction?`, `years?` | trend-chart DATA for the setup: per-year % paths + average path + stats (no price series, no image) | all |
| `score_opportunities` | list of `{symbol, date, days_out, direction}` | ML `ml_score` / `win_prob` / `pred_return` / `pred_mfe` | **Pro** (graceful upgrade stub otherwise) |
| `get_daily_pick` | - | today's ML-selected featured pick | all |
| `get_pick_track_record` | - | realized win/loss record of past picks (the hook) | all |

**Maps to:** `/v1/markets`, `/v1/markets/{id}/symbols`, `/v1/opportunities`,
`/v1/opportunities/{symbol}`, `/v1/patterns/{id}/{symbol}`, `/v1/seasonal-chart`, `/v1/score`,
`/v1/daily-pick`, `/v1/daily-pick/track-record`.

**Tool descriptions** (what the model reads to decide when to call) should be
opinionated, e.g. `get_seasonal_opportunities`: "Find the best seasonal trade setups
for a market and date window, ranked by historical edge. Use when the user asks what
to trade, when to enter, or which symbols have a strong seasonal tendency."

x-verify: confirm `win_rate` derivation and the publishable `Pattern.stats` subset
against the appserver before freeze.
