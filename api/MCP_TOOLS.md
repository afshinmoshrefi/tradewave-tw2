# TradeWave MCP server - tool schema (2026-06-08)

Wrapper over the v1 API (`openapi.yaml`). Tools are phrased for agents ("give me
tradeable answers"), NOT a 1:1 mirror of the internal appserver routes. The design
goal is that the in-chat experience feels like "your seasonal-edge analyst", not a
REST mirror: the model reaches for a small set of FLAGSHIP tools that each return a
ready, evidence-backed answer, and falls back to the low-level primitives only when
it needs one exact slice.

**Inventory: 17 tools - 6 flagship + 11 primitives.** Flagship:
`find_best_opportunities`, `analyze_symbol`, `explain_pick`, `morning_briefing`,
`whats_seasonal_now`, `compare_opportunities`. Primitives: `list_markets`, `whoami`, `describe_tradewave`,
`list_symbols`, `get_seasonal_opportunities`, `get_symbol_patterns`,
`get_seasonal_pattern`, `get_opportunity_chart`, `score_opportunities`,
`get_daily_pick`, `get_pick_track_record`. (There is NO `get_opportunity_for_symbol`;
the symbol pattern list is served only by `get_symbol_patterns`.)

**Educational-only contract:** every pattern is impersonal and identical for everyone -
TradeWave never reads or advises on a caller's holdings. The exact educational
disclaimer rides on EVERY pattern-bearing response: the gateway stamps an identical
`disclaimer` on each card and the MCP layer hoists it to a single envelope line
(`_extract_disclaimer`) so it always reaches the model once. Every card-bearing
FLAGSHIP response ALSO appends a research hand-off (see below).

**One source of truth:** the gateway composes every PatternCard server-side (headline,
verdict, edge_score, receipts, order ticket). The MCP tools forward those structured
cards verbatim (`json.dumps`) plus a one-line conversational lead - they NEVER recompute
or re-rank cards client-side. See `api/PATTERNCARD_SPEC.md` for the card shape.

**Authentication:** the hosted MCP server supports two authentication paths.

1. **TradeWave account authorization (recommended for ChatGPT and Claude):** the user
   adds the hosted MCP URL, selects Connect/Authorize, and signs in to TradeWave through
   WorkOS. The user does **not** create, copy, or paste an API key. The MCP server validates
   the audience-bound WorkOS OAuth token, maps its `sub` claim to the existing TradeWave
   user, and applies that user's web subscription, market access, metering, and quotas.
   The server's `MCP_GATEWAY_KEY` is an internal service credential and is never given to
   the user or MCP client.
2. **Bring your own API key (developer alternative):** developer tools and local clients
   may send a TradeWave key in `Authorization: Bearer <tw_...>`. A stdio deployment may
   instead read the same user-owned key from `TRADEWAVE_API_KEY`. Tier and entitlements
   for this path flow from `users.api_key_hash`.

Both paths are resolved independently on every call. Every tool invokes
`_bind_request_key(ctx)` at entry; `ctx` is a FastMCP `Context` and is stripped from the
published input schema by FastMCP. Missing or invalid credentials fail authentication.

**Safety contract (same as the API):** patterns only - no raw OHLCV / last price /
price-by-date. Returns are percentages, never price levels; the seasonal curve is a
normalized 0-100 index, never a price. Entitlements depend on the authentication path:
with TradeWave account authorization, the consumer web plans are mirrored exactly
(Explorer and Navigator receive deterministic seasonal tools, Analyst receives 100 ML
scores/day, and Strategist receives unlimited ML); temporary trials may widen that access.
With a developer API key, the API plans apply (Free 5 ML scores/day, Dev 100/day, and
Pro or Business unlimited). ML scoring is limited to eligible markets (ids 0,1,2,3,4,11).
When the daily ML allowance is spent the
gateway returns a graceful 200 nudge - `{requires:"upgrade", reason:"ml_daily_limit",
message, upgrade_url, ml_remaining_today}` on /v1/score; on cards the field
`tier_notes` becomes "Daily ML limit reached on your plan - upgrade for unlimited ML
scoring." The MCP layer surfaces both as a clear "daily ML limit reached - upgrade for
unlimited" message with `ml_remaining_today` if present, never as an error. The daily
pick's ML is free/unmetered (it is the teaser). Responses include `ml_remaining_today`
(None = unlimited). Weak setups come back as a `neutral` bias rather than a manufactured trade.

---

## Flagship tools (reach for these first)

| Tool | Inputs | Returns | Maps to | Tier |
|---|---|---|---|---|
| `find_best_opportunities` | `markets?`, `window?`, `direction?`, `min_win_rate?`, `min_years?`, `min_days?`, `max_days?`, `min_avg_return?`, `min_median_return?`, `min_sharpe?`, `pe_cycle?`, `years?`, `min_winning_years?`, `rank_by?` (default: `sharpe`), `limit?`, `view?` (full\|evidence\|decision\|table; default `evidence`), `include_chart?` (default true) | ranked PatternCards across the in-scope markets, pre-sorted by Sharpe ratio. The default evidence view returns the winner in full, lean runners, two native TradeWave chart images for the winner, chart data/specifications, and its exact Wave Viewer link. `min_days`/`max_days` filter pattern length; return filters are percentages/ratios. | `GET /v1/scan` | all (ML metered daily; count gated by tier) |
| `analyze_symbol` | `symbol`, `market?`, `direction?`, `days_out?`, `entry_date?`, `pe_cycle?`, `years?`, `period?`, `reverse?`, `view?` (full\|evidence\|decision\|table; default `evidence`), `include_chart?` (default true) | one full PatternCard plus other setups. `days_out` is inclusive CALENDAR days: entry is day 1 and end = entry + (`days_out` - 1). PIN a specific setup with `entry_date` (+`days_out`) or a `period`/`reverse` preset. By default the MCP response includes year-by-year MFE/MAE evidence and normalized seasonal trend data/specifications, two native PNG image blocks, and a server-generated link that opens the exact setup in Wave Viewer. | `GET /v1/analyze/{symbol}` | all (ML metered daily) |
| `explain_pick` | - | today's daily pick as a PatternCard WITH its live forward-tested track record (the strongest receipt) | `GET /v1/daily-pick` | all |
| `morning_briefing` | - | the one-call MORNING BRIEFING: today's pick (decision view), the live track-record summary with the last 5 outcomes, and the top setups entering their window now; sections fail-soft (a degraded briefing beats no briefing) | `GET /v1/daily-pick` + `GET /v1/daily-pick/track-record` + `GET /v1/scan` (composed, parallel) | all |
| `whats_seasonal_now` | `markets?`, `min_win_rate?`, `view?` (full\|decision\|table; default `decision`) | setups entering their window in the next ~10 trading days, as ranked PatternCards (weekly digest) | `GET /v1/scan` with `window="now"` | all |
| `compare_opportunities` | `symbols[]`, `market?`, `view?` (full\|decision\|table; default `decision`) | N symbols deep-dived and returned side-by-side for head-to-head ranking | N x `GET /v1/analyze/{symbol}` | all (ML metered daily) |

- `find_best_opportunities` is THE "what should I trade right now" entry point; the
  description is opinionated so the model reaches for it on "find me / what's good /
  anything seasonal in X". `whats_seasonal_now` is kept a SEPARATE named tool (a thin
  `window="now"` alias over scan) because the NAME is the routing signal for
  "what is entering its window this week / weekly digest" prompts.
- `compare_opportunities` fans out per symbol and fails SOFT per row: a per-symbol
  HTTP error degrades only that row (`{symbol, error, card:null}`); an upgrade stub
  (requires:'pro' or requires:'upgrade') becomes `{symbol, requires, message, upgrade_url}` -
  the comparison never breaks.
- Empty scans return the structured payload (`count:0`) plus a lead that suggests
  widening markets/window/min_win_rate, so "nothing now" is never a dead end.
- **Progressive disclosure (`view`):** the flagship discovery/deep-dive tools take
  `view=full|evidence|decision|table`. MCP defaults to `evidence`: rank 1 is complete,
  runners are lean, and the winner receives the two-chart evidence pack. `table` is a
  compact ranked row; `decision` is lean; `full` expands every card. The raw API remains
  backward-compatible with `full` as its default.
- **Native TradeWave charts + Wave Viewer:** `find_best_opportunities` and `analyze_symbol`
  request `include=chart` by default. Their MCP result contains the canonical chart data,
  explicit chart specifications, and native PNG image content blocks. Every PatternCard
  also carries a server-generated `wave_viewer.url` for the exact market, symbol, date,
  hold, lookback, and PE-cycle selection.
- **TradeWave-first presentation, research hand-off + disclaimer.** Card-bearing flagships
  (`find_best_opportunities`, `analyze_symbol`, `explain_pick`, `whats_seasonal_now`, `morning_briefing`,
  `compare_opportunities`) append an `extend_research` hand-off after the payload
  (`handoff=True`): it states TradeWave is BLIND to fundamentals/news/macro/valuation/
  earnings, but first requires the model to present TradeWave's verdict, statistics,
  charts, path risk, failed years, and Wave Viewer link. Outside research is an optional
  current-context check, never a substitute. The model must never invent a catalyst and
  must report a `neutral` bias as a genuine "no edge" finding. The
  educational disclaimer is hoisted to a single envelope line on every pattern-bearing
  response. Primitives like `whoami`/`list_markets` do NOT carry the hand-off.

## Low-level primitives (prefer the flagships unless you need this exact slice)

Most primitive descriptions open with: "Low-level primitive. Prefer
find_best_opportunities / analyze_symbol unless you need this exact slice ..." so the
model defers to the flagships by default. (`whoami` and `describe_tradewave` are the
exceptions - they are meta/onboarding tools the model SHOULD reach for first on
"what can you do" / "how do I read these" prompts.)

| Tool | Inputs | Returns | Maps to | Tier |
|---|---|---|---|---|
| `list_markets` | - | the 15 active markets (ids span 0-16) + which are in the caller's scope, each market's ML eligibility, and its `pattern_detection` coverage (scan vs per-symbol) with an example win-rate band - so "which markets support per-symbol patterns?" and "what lookback/min_winning_years is valid here?" are answerable from data | `GET /v1/markets` | all |
| `whoami` | - | the caller's plan tier, `ml_remaining_today` (null = unlimited), the markets in scope, and a few example prompts. The "what can you do / what plan am I on / how many ML calls left" tool | `GET /v1/me` | all |
| `describe_tradewave` | - | the static how-it-works + how-to-research guide: the method (edge -> extend with your own tools -> synthesize), the three distinct win rates + edge_score glossary, and the SEASONAL ANALYSIS KNOBS glossary (lookback `years` + `min_winning_years` and the per-market band, day-range, market coverage). No API call | (local) | all |
| `list_symbols` | `market` | symbols in a market | `GET /v1/markets/{id}/symbols` | all |
| `get_seasonal_opportunities` | `market`, `from?`, `to?`, `direction?`, `min_win_rate?`, `min_days?`, `max_days?`, `min_avg_return?`, `min_median_return?`, `min_sharpe?`, `pe_cycle?`, `years?`, `min_winning_years?`, `limit?` | raw single-market ranked setups (symbol, direction, entry, hold, sharpe, avg/median %, win rate). Same column filters as scan (`min_days`/`max_days` pattern length; `min_avg_return`/`min_median_return` PERCENT; `min_sharpe`) | `GET /v1/opportunities` | all (count gated by tier; ML metered daily) |
| `get_symbol_patterns` | `symbol`, `market`, `pe_cycle?`, `years?`, `min_winning_years?`, `min_days?`, `max_days?`, `min_avg_return?`, `min_sharpe?` | a security's TOP seasonal patterns across the year, ranked by Sharpe (the wave-viewer pattern dropdown). COVERAGE: per-symbol patterns exist for market ids **0,1,2,7,9** only (DOW 30, NASDAQ 100, S&P 500, Futures & Commodities, FOREX Liquid); any other market returns a clear error - use `find_best_opportunities` to scan those instead. `years`/`min_winning_years` obey the same per-market band as scan | `GET /v1/securities/{symbol}/patterns` | all |
| `get_seasonal_pattern` | `market`, `symbol`, `pe_cycle?`, `years?`, `period?`, `reverse?` | bare aggregate seasonal pattern stats (no price series) | `GET /v1/patterns/{id}/{symbol}` | all |
| `get_opportunity_chart` | `market`, `symbol`, `entry_date?`, `days_out?`, `direction?`, `years?`, `pe_cycle?`, `period?`, `reverse?` | a SINGLE year-averaged, normalized 0-100 seasonal index curve (`seasonal_curve`) - the typical within-year shape, NOT per-year cumulative paths, NOT an image, never a price - PLUS `per_year_bars` (each completed year's trade return with its favorable (mfe)/adverse (mae) excursion band, direction-aware, all percentages); `days_out` is inclusive CALENDAR days with entry as day 1; `receipts.curve_summary` describes the TREND OF THE HOLD SECTION (entry to exit), NOT the full year - `peak_day`/`trough_day` are days into the hold (0=entry) | `GET /v1/seasonal-chart` | all |
| `score_opportunities` | list of `{symbol, date, days_out, direction}` where `days_out` is inclusive CALENDAR days and `date` is day 1 | ML `ml_score` / `win_prob` / `pred_return` / `pred_mfe`; includes `ml_remaining_today` | `POST /v1/score` | quota depends on authentication path; see Authentication and Safety contract above |
| `get_daily_pick` | - | bare daily-pick payload (no receipts) | `GET /v1/daily-pick` | all |
| `get_pick_track_record` | - | standalone realized win/loss record of past picks | `GET /v1/daily-pick/track-record` | all |

### Lookback BAND on `years` / `min_winning_years`
Pattern DETECTION (`find_best_opportunities`, `get_seasonal_opportunities`,
`get_symbol_patterns`) is constrained by a per-market detection band; ANALYSIS
(`analyze_symbol`, `get_opportunity_chart`) scores a setup on the fly and leaves `years`
free (1-99).
- `years` (lookback) + `min_winning_years` together set the WIN-RATE FLOOR: of those
  `years`, the minimum that must have been WINNERS (year2 over year1).
- `min_winning_years` DEFAULTS to ~90% of `years` - so a bare `years=20` yields a valid
  20-18 and you rarely need to set it.
- It must lie inside the market's per-market band (market-specific win-rate floors, e.g.
  S&P 500 ~85%, Wilshire ~90%, FOREX Liquid ~70% at a 20-year lookback). An OUT-OF-BAND
  combo like `20-9` (45%) is REJECTED with the valid range returned in the error - never
  lower it below the market's floor. On a multi-market scan, a value out of band for only
  some scanned markets degrades gracefully with a `lookback_note` naming them.
The full glossary of these knobs is returned live by `describe_tradewave` (the "SEASONAL
ANALYSIS KNOBS" section), and each market's band + an example is returned by
`list_markets` (`pattern_detection`).

### `get_opportunity_chart` description fix
The previous description wrongly claimed "per-year cumulative % paths and the average
seasonal line". The endpoint returns ONE year-averaged, normalized 0-100 seasonal index
curve (`seasonal_curve`) - a single relative shape, not per-year paths. The tool
description now states this accurately (and that the index is never a price).

x-verify: confirm `historical_win_rate` derivation and the publishable `Pattern.stats`
subset against the appserver before freeze; confirm the live `/v1/scan` and
`/v1/analyze/{symbol}` response envelopes match `api/PATTERNCARD_SPEC.md` sections 1 + 5.
