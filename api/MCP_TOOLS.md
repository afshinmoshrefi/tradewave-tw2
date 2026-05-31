# TradeWave MCP server - tool schema (2026-05-31)

Wrapper over the v1 API (`openapi.yaml`). Tools are phrased for agents ("give me
tradeable answers"), NOT a 1:1 mirror of the internal appserver routes. The design
goal is that the in-chat experience feels like "your seasonal-edge analyst", not a
REST mirror: the model reaches for a small set of FLAGSHIP tools that each return a
ready, evidence-backed answer, and falls back to the low-level primitives only when
it needs one exact slice.

**One source of truth:** the gateway composes every SignalCard server-side (headline,
verdict, edge_score, receipts, order ticket). The MCP tools forward those structured
cards verbatim (`json.dumps`) plus a one-line conversational lead - they NEVER recompute
or re-rank cards client-side. See `api/SIGNALCARD_SPEC.md` for the card shape.

**Auth:** BYOK for v1 - the caller's TradeWave API key gates the server; tier and
entitlements flow from `users.api_key_hash`. Resolved per call: the incoming MCP
request's `Authorization: Bearer <key>` (remote sse/streamable-http) else env
`TRADEWAVE_API_KEY` (stdio). Every tool calls `_bind_request_key(ctx)` at entry; `ctx`
is a FastMCP `Context` and is stripped from the published input schema by FastMCP.

**Safety contract (same as the API):** signals only - no raw OHLCV / last price /
price-by-date. Returns are percentages, never price levels; the seasonal curve is a
normalized 0-100 index, never a price. ML fields are Pro-only + ML-eligible-market
(ids 0,1,2,3,4,11) and degrade gracefully (UpgradeRequired stub surfaced as a clear
"Pro subscription required" message + `upgrade_url`, never an error). Weak setups come
back as `NO_SIGNAL` rather than a manufactured trade.

---

## Flagship tools (reach for these first)

| Tool | Inputs | Returns | Maps to | Tier |
|---|---|---|---|---|
| `find_best_opportunities` | `markets?`, `window?`, `direction?`, `min_win_rate?`, `min_years?`, `rank_by?`, `limit?` | ranked SignalCards across the in-scope markets, pre-sorted by edge score | `GET /v1/scan` | all (ML + count gated by tier) |
| `analyze_symbol` | `symbol`, `market?`, `direction?`, `days_out?` | one rich SignalCard (best setup + receipts + order ticket) + other setups for the symbol | `GET /v1/analyze/{symbol}` | all (ML Pro-only) |
| `explain_pick` | - | today's daily pick as a SignalCard WITH its live forward-tested track record (the strongest receipt) | `GET /v1/daily-pick` | all |
| `whats_seasonal_now` | `markets?`, `min_win_rate?` | setups entering their window in the next ~10 trading days, as ranked SignalCards (weekly digest) | `GET /v1/scan` with `window="now"` | all |
| `compare_opportunities` | `symbols[]`, `market?` | N symbols deep-dived and returned side-by-side for head-to-head ranking | N x `GET /v1/analyze/{symbol}` | all (ML Pro-only) |

- `find_best_opportunities` is THE "what should I trade right now" entry point; the
  description is opinionated so the model reaches for it on "find me / what's good /
  anything seasonal in X". `whats_seasonal_now` is kept a SEPARATE named tool (a thin
  `window="now"` alias over scan) because the NAME is the routing signal for
  "what is entering its window this week / weekly digest" prompts.
- `compare_opportunities` fans out per symbol and fails SOFT per row: a per-symbol
  HTTP error degrades only that row (`{symbol, error, card:null}`); a Pro-gated stub
  becomes `{symbol, requires:'pro', message, upgrade_url}` - the comparison never breaks.
- Empty scans return the structured payload (`count:0`) plus a lead that suggests
  widening markets/window/min_win_rate, so "nothing now" is never a dead end.

## Low-level primitives (prefer the flagships unless you need this exact slice)

Each primitive's description opens with: "Low-level primitive. Prefer
find_best_opportunities / analyze_symbol unless you need this exact slice ..." so the
model defers to the flagships by default.

| Tool | Inputs | Returns | Maps to | Tier |
|---|---|---|---|---|
| `list_markets` | - | the 17 markets + which are in the caller's scope | `GET /v1/markets` | all |
| `list_symbols` | `market` | symbols in a market | `GET /v1/markets/{id}/symbols` | all |
| `get_seasonal_opportunities` | `market`, `from?`, `to?`, `direction?`, `min_win_rate?`, `limit?` | raw single-market ranked setups (symbol, direction, entry, hold, sharpe, avg/median %, win rate) | `GET /v1/opportunities` | all (count + ML gated by tier) |
| `get_opportunity_for_symbol` | `symbol`, `market` | raw list of every setup for one symbol (no enrichment) | `GET /v1/opportunities/{symbol}` | all |
| `get_seasonal_pattern` | `market`, `symbol` | bare aggregate seasonal pattern stats (no price series) | `GET /v1/patterns/{id}/{symbol}` | all |
| `get_opportunity_chart` | `market`, `symbol`, `entry_date?`, `days_out?`, `direction?`, `years?` | a SINGLE year-averaged, normalized 0-100 seasonal index curve (`seasonal_curve`) - the typical within-year shape, NOT per-year cumulative paths, NOT an image, never a price | `GET /v1/seasonal-chart` | all |
| `score_opportunities` | list of `{symbol, date, days_out, direction}` | ML `ml_score` / `win_prob` / `pred_return` / `pred_mfe` | `POST /v1/score` | **Pro** (graceful upgrade stub otherwise) |
| `get_daily_pick` | - | bare daily-pick payload (no receipts) | `GET /v1/daily-pick` | all |
| `get_pick_track_record` | - | standalone realized win/loss record of past picks | `GET /v1/daily-pick/track-record` | all |

### `get_opportunity_chart` description fix
The previous description wrongly claimed "per-year cumulative % paths and the average
seasonal line". The endpoint returns ONE year-averaged, normalized 0-100 seasonal index
curve (`seasonal_curve`) - a single relative shape, not per-year paths. The tool
description now states this accurately (and that the index is never a price).

x-verify: confirm `historical_win_rate` derivation and the publishable `Pattern.stats`
subset against the appserver before freeze; confirm the live `/v1/scan` and
`/v1/analyze/{symbol}` response envelopes match `api/SIGNALCARD_SPEC.md` sections 1 + 5.
