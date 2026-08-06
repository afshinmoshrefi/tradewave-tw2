# Tara on the Gateway - integration spec

Status: PHASE 1 (read-client) + PHASE 2 (UI-actuation) BOTH BUILT + verified on dev 2026-06-02.
Owner decision on the auth/metering principal (section 7): RESOLVED = option A (internal chatbot
service key + per-web-user 'cb:'-namespaced quota).

Provider note (2026-08-04): the tracked release policy is the same in dev, staging, and
production. Deterministic planner answers run first. Every model-bound turn starts on OpenAI
`gpt-5.6-luna`; Haiku 4.5 is used only after a classified OpenAI request, API, connection, or
adapter failure. `run_chat_with_tools` (Anthropic fallback) and
`run_chat_with_openai_tools` (OpenAI Responses primary) both execute calls through the same
validated `_execute_tara_tool` path. Missing primary credentials fail release preflight and do
not select Haiku. Percentage canaries, user buckets, and environment-specific provider defaults
are not part of normal operation.

Loaded ChartData4 context includes an explicit `Trend Score Available` flag alongside Trend Long /
Trend Short. Tara treats unavailable readings as missing, not as a real `0`; for a rolling old bundle
or cached response, an all-zero current/prior score set with no flag is also treated as missing.
Trend Alignment wording must name the loaded direction and explain that it compares roughly the last
one to two weeks of price movement with that seasonal direction. It is not a historical score or a
forecast.

Loaded-pattern analysis also has a direct appserver ML enrichment path; this is separate from Tara's
gateway tool loop. For an eligible US-stock/ETF user, `chatbot.py` discards any browser-supplied
`ai_analysis` object and asks the callback registered by `appserver.py` for the current daily-cached
reading. A setup from 10 through 30 calendar days gets its current-duration AI Win Probability /
PredR / PMFE read. Above 30 days, Tara keeps that exact current reading through 90 days and adds only
shorter standard comparisons that fit: 31-60 adds 30, while 61-90 adds 30 and 60. An 85-day setup
therefore shows 30, 60, and the current 85 days, never 90. Above 90 days Tara uses bounded 30/60/90
comparisons and clearly keeps the complete source window as historical context. Tara intentionally
omits AIS from analysis prose; AIS remains in the opportunity table and its dedicated explainer.
The callback converts inclusive 30/60/90 labels to legacy scorer offsets 29/59/89.

At every shorter horizon the scorer recalculates both the trained all-qualifying-combo V3 profile
and the selected consecutive- or PE-year cohort. Every valid V3 profile receives a model reading;
Tara separately reports the actual `x of n; requires y` screen evidence when the selected recurrence
misses its requirement. A true model-profile, input-data, volatility, or provider failure remains a
structured unavailable state and never becomes zero. Scores are not shown more
than five days before entry or newly calculated
after entry, and scorer failure degrades to the verified historical analysis rather than blocking
Tara.

Questions such as "why does AI only do the first 90 days?" are deterministic product explanations,
not provider turns. Tara explains that the models are trained and calibrated for 10-90-calendar-day
seasonal horizons, that shorter comparisons never extend beyond the source duration, and how those
readings complement the complete-window historical record. This prevents a provider from denying
the real horizon boundary or diverting to an unrelated daily pick.

Product-value questions do not need a provider or live scorer. `tara_answer_planner.py`
deterministically handles seasonality-value prompts with a compact loaded-pattern demonstration and
strategy-building prompts with a measurable-odds research framework. These replies use the same
semantic `tara-analysis` HTML cards as pattern analysis, preserve sample-size and calendar-day
semantics, link to the existing Years/Seasonality/Filtering guides, and avoid negative refusal-led
marketing language.

Phase 2 as built: an `update_view` tool lets the model DRIVE the wave-viewer. Both tool loops
in `tara_gateway.py` return (text, actions); an update_view call is
validated server-side (`_validate_view_spec`: allowlist + range-check symbol/market/entry_date/
days_out/years/pe_cycle/show_mfe/show_mae/show_tooltips/bottom_slide, dropping invalid fields) and queued as `{type:'set_view', spec}` -
it never hits the gateway. `chat()` returns `{reply, actions}` (additive; old bundles ignore it).
`Chatbot.js applyViewSpec` re-validates each field then calls the React setters (mirrors
`loadOppWV`; a fresh load only on a symbol CHANGE), and `SetPEselected` was added to
`App.js chartSetProps`. The TOOL_INSTRUCTION is appended (recency) and forcefully tells the model
to drive the view rather than tell the user where to click. Verified live: "load NVDA, 20 years"
-> action `{market:'1',symbol:'NVDA',years:20}`; "change lookback to 15" -> `years:15`; "switch
to PE+2" -> `pe_cycle:'pe2'`. React bundle rebuilt (served from web-react/build on dev). Blast
radius of the actuation = which chart/knobs the user sees (no code exec, no data beyond the
derived-data-only gateway, no auth/billing).

Direct lower-panel requests bypass both model providers. `tara_answer_planner.py` maps Trend Chart,
Wave Stats (including “the stats”), and Price Chart to a validated `bottom_slide`; React calls the
desktop Swiper's stable `slideTo(0|1|2)` contract. Explanatory questions remain explanations.

An explicitly named ticker also outranks the loaded chart and conversation pronouns. When a user
changes symbols without naming a new lookback, Tara carries the current consecutive lookback to the
target, checks the target's `StockMetaData` limit, and steps down only when less history exists. The
gateway read and final viewer action use that same effective lookback and anchor the recurring setup
to the current occurrence year. `/v1/analyze/<symbol>` supplies the matching market-specific
`year1`/`year2` detection pair so a 16-year request cannot silently fall back to the legacy 10-year
grid. Tara's brief card retains `sharpe_ratio_mfe`; TWR is described as the Sharpe-style calculation
on MFE, and losing-year MFE/giveback is surfaced when it changes the endpoint-only interpretation.

Screening fix (2026-06-21): a "which <group> stocks" answer must match the on-screen opp table, but
the table (`OppList4`) and the gateway `/scan` are DIFFERENT data paths that pick different setups per
symbol (verified live: scan = FAST/TXN/CDNS...; the real NASDAQ table = AAPL/AMZN/CHTR... - AAPL is #1
in the table but ABSENT from /scan at any years/window; /scan is structurally near-term-only). So Tara
now SCREENS FROM OppList4, not /scan: `Chatbot.js` sends `opp_table_market` (+`_market_name`) and
`opp_table_years`; `tara_gateway.run_chat_with_tools` intercepts `find_best_opportunities` -> same
market as the table: answer from the passed rows (`_rows_to_scan_cards`+`_filter_table_rows`);
different market: fetch that market's OppList4 LOOPBACK (`_opplist4_rows`, via `config.appserver_url`
using the user's LTK) + auto-append `set_view{market}` so the table follows. Win-rate/winning-years/
years/pe_cycle filters or a loopback failure fall back to the gateway scan.

Phase 1 as built (dev .176): a `chatbot` INTERNAL_TIER (tiers.py, service:True, not in the sold
catalog) + an X-TW-On-Behalf-Of delegation in the gateway (auth.py, service-tier-only, principal
'cb:'-namespaced + regex-validated) + a gateway client/tool-loop (appserver/appserver/tara_gateway.py)
+ chat() wired to it (chatbot.py, falls back to old behavior when unconfigured) + tools= on
send_claude_messages (AI_tools_appserver.py). Service key minted by apiserver/provision_chatbot_key.py
(secrets: TARA_GATEWAY_KEY + TW2_GATEWAY_URL). Verified: explain_pick narrated the real NVDA card +
disclaimer; find_best_opportunities narrated real UNH/WMT/AXP cards and metered ML under
mlq:cb:<user>; a normal customer key + on-behalf header did NOT delegate (no cb: key created).

Passed a 13-agent adversarial review (auth-delegation / tool-loop-injection / derived-data-secrets /
robustness lenses). Security core CLEAN: delegation cannot escalate scope, a normal key cannot
spoof, the service key never leaks, derived-data-only is inherited (Tara goes THROUGH the gateway),
the loop terminates. Fixes landed: HIGH - tool results were raw-sliced to 6000 chars (malformed
JSON on big scans); now `_bounded_json` caps lists + drops heavy card fields to valid JSON (tested
80k->1.4k valid). MEDIUM - gateway read timeout 60s->20s (fail-fast). Hardening - a `tiers.py`
assert forbids any sold tier carrying `service:True`.

## 1. What and why

"Tara" is the in-product chatbot already shipped in the desktop wave-viewer
(`web-react/src/components/Chatbot.js` <-> `appserver/appserver/chatbot.py`, JWT-gated).
The shipped implementation uses a deterministic verified-answer planner first, then a
provider-routed model/tool loop for questions that need it. Historical proposal language below
describes the gateway capabilities that were subsequently built.

This spec makes Tara a **client of the same gateway** the public API + MCP server use
(`apiserver/`), in two phases:

- **Phase 1 - read-client (narrate).** Tara gains tool-use: it calls the gateway's
  flagship tools (`/v1/scan`, `/v1/analyze`, `/v1/daily-pick`, ...) mid-conversation,
  gets back the SAME server-composed PatternCards, and narrates them. Backend-only.
- **Phase 2 - UI-actuation (drive the view).** Tara returns structured actions that the
  React app applies to its own wave-viewer state - load a pattern, set the years slider,
  flip consecutive<->PE, apply a filter, change the date range - so the user never has to
  find the control. Frontend + backend.

This is a **wiring** relationship, not a product merge. Tara stays the on-site, login-
gated UI helper; the public API/MCP stays derived-data-only for developers. Tara never becomes
a sellable API SKU (the MCP server already IS the developer chatbot). See
`api/BUILD_STATE.md` and `docs/TRADEWAVE_ECOSYSTEM.md` for the product line.

## 2. The unifying idea: one ViewSpec

The wave-viewer's knobs map **1:1** to the v1 API params we already shipped, because the
React state and the API contract use the same vocabulary. So there is one object - the
**ViewSpec** - that:

- the model **emits** (as a tool call),
- the backend **sends to the gateway** to fetch + narrate a card (Phase 1), and
- the frontend **applies to the wave-viewer** to drive the on-screen view (Phase 2).

Because narration and the on-screen chart are driven by the *same* ViewSpec, they are in
sync by construction - Tara can never describe numbers that differ from what is plotted.

```
ViewSpec = {
  market?:     string,   // market name or permanent id '0'..'16'
  symbol?:     string,
  entry_date?: string,   // 'YYYY-MM-DD'
  days_out?:   integer,  // 1..367 inclusive calendar days
  years?:      integer,  // 1..99 (lookback)
  pe_cycle?:   'consecutive'|'pe'|'pe0'|'pe1'|'pe2'|'pe3',
  show_mfe?:   boolean,  // best-move overlay on the year-by-year chart
  show_mae?:   boolean,  // worst-move overlay on the year-by-year chart
  show_tooltips?: boolean, // global guidance tooltips across TradeWave
  bottom_slide?: 'trend_chart'|'wave_stats'|'price_chart', // lower carousel destination
  period?:     'jan'..'dec'|'q1'..'q4'|'spring'|'summer'|'fall'|'winter'|'ytd'|'year_end'|'buy_hold',
  reverse?:    boolean,
  direction?:  'long'|'short',
  filter?:     string    // the opp-table filter expression
}
```

## 3. ViewSpec <-> React setter <-> API param (verified mapping)

The React setters live in `App.js` and are passed to children via `chartSetProps`
(App.js ~lines 1270-1360). Row clicks already route through `OppTable.handlerRowClicked`
and `SeasonalBarChart.selectboxChanged`; the chatbot already reaches parent state via
`Chatbot.loadOppWV` (calls `props.SetSymbol/SetStartDate/SetDaysOut/SetSeasonalYears`).
Phase 2 generalizes that existing write-channel.

| ViewSpec field | React setter (App.js) | API param | Notes |
|---|---|---|---|
| `symbol` | `SetSymbol(str)` | `symbol` | direct |
| `entry_date` | `SetStartDate('YYYY-MM-DD')` | `entry_date` | direct |
| `days_out` | `SetDaysOut(n)` | `days_out` | direct (UI shows +1 internally) |
| `years` | `SetSeasonalYears('10')` | `years` | wave-viewer lookback |
| `period` | `SetMonthsAndQtrs(label)` | `period` | SeasonalBarChart derives date0/date1 -> SetStartDate/SetDaysOut |
| `reverse` | `SetMonthsAndQtrs('Reverse Date Range')` | `reverse` | re-derives the complement window |
| `pe_cycle` | `SetShowPEOpps(bool)` + `SetPEselected('cons'|'pe0..3')` | `pe_cycle` | table mode is boolean; per-security is the pe0..3 selector |
| `filter` | `SetAppliedFilter(str)` | `filter` | direct |
| `market` | `SetSelectedSecurity(name)` | `market` | name resolved to id via `getSelectedIDFromSecuritiesList2` |
| `direction` | `SetBarChartLongOrShort('long'\|'short')` | `direction` | usually inferred from ChartData4; settable but normally let the setup decide |
| `show_mfe` | `setShowMFE(bool)` | local view only | shows/hides the direction-aware MFE overlay; persisted in the existing `MFE` cookie |
| `show_mae` | `setShowMAE(bool)` | local view only | shows/hides the direction-aware MAE overlay; persisted in the existing `MAE` cookie |
| `show_tooltips` | `SetTooltipSW(bool)` | local view only | shows/hides global guidance tooltips through the same state as the upper-left toolbar switch |
| `bottom_slide` | `swiper.slideTo(0\|1\|2)` | local view only | shows Trend Chart, Wave Stats, or Price Chart immediately; Tara is desktop-only |

A single `applyViewSpec(spec)` helper in `Chatbot.js` walks these keys and calls the
matching `props.Set*` from `chartSetProps`. No new state is introduced - it drives the
exact setters the dropdowns/sliders/row-clicks already use.

Direct lower-panel commands are resolved deterministically before provider selection. Thus
"show me the stats" produces `bottom_slide:'wave_stats'` and actually moves the carousel; Tara
does not merely tell the user to swipe. Concept questions (for example, "what is the Trend
Chart?") remain explanation/guide requests and do not move the panel.

Tooltip preference language is also deterministic. Dislike, distraction, or removal wording emits
`show_tooltips:false`; confusion about controls/buttons/icons emits `show_tooltips:true`. Tara names
the switch in the upper-left toolbar beside the settings gear in both replies. A location or
definition question explains the switch without changing it.

Trend-arrow questions are deterministic as well. The direction-specific score level determines
`Aligned`, `Neutral`, or `Against`; the adjacent arrow only compares the current score with its
previous available reading. Green up is higher, red down is lower, and white/gray horizontal is
unchanged. When both readings are available, Tara names the exact change and keeps it separate from
the current alignment label.

## 4. Action allowlist + guardrails

Today actions are smuggled as HTML: the reply is `{reply: "<...data-action='open-sharpe-popup'...>"}`
and `Chatbot.js` string-matches `reply.includes('data-action=')` to call `setShowSharpePopup(true)`
(17 popup setters). This is replaced by a **structured `actions[]`** field. Two action
types only:

```
actions: [
  { "type": "open_guide", "guide": "sharpe" },                       // existing 17 popups, now structured
  { "type": "set_view",   "spec": { ...ViewSpec... } }              // the new wave-viewer drive
]
```

Guardrails (defense in depth):
- **Allowlist, both ends.** Backend validates every action: `type` in {open_guide,set_view},
  `guide` in the known 17, ViewSpec keys in the table above, values range-checked (reuse the
  gateway's existing validators: days_out 1-367, years 1-99, period enum, pe_cycle enum).
  Frontend re-validates against the same allowlist before applying. Never `eval`, never a
  dynamic setter name.
- **View/navigation only.** Every setter in the allowlist is reversible view state. Tara
  drives the *view*; it never places trades, never touches account/billing/auth. This is the
  same line the current "no trade advice / no execution" disclaimer already draws.
- **Visible echo.** When a `set_view` is applied, Tara also says what it did in chat
  ("Loaded GLD over 20 years, Q4 window") so the user sees the change and can undo by asking.

## 5. Phase 1 - backend read-client (narrate)

Goal: Tara can fetch + narrate via the gateway. No frontend change; response stays `{reply}`.

Changes:
1. **`AI_tools_appserver.py` `send_claude_messages(...)`** - add an optional `tools=` kwarg
   and include it in the Anthropic payload (currently the payload has no `tools`). Return the
   full response (not just `content[0].text`) when tools are present, so the caller can run the
   tool loop.
2. **`chatbot.py`** - define the gateway tool schemas (a small set: `find_best_opportunities`,
   `analyze_symbol`, `explain_pick`, `get_symbol_patterns`, `compare_opportunities` - the
   flagships are enough to start). Run the tool-use loop: on a tool call, execute an HTTP
   request to the gateway and feed the result back until the model returns text.
3. **Gateway client** - a thin internal client (mirror `mcpserver`'s `_get`) that calls
   `API_BASE_URL` (`http://127.0.0.1:8088/v1` on dev; per-env) with the service principal
   from section 7. Reuses the gateway's card composition + derived-data-only rails verbatim (one
   source of truth).
4. **System prompt** (`build_system_prompt`) - add a short "you can call these tools to fetch
   live TradeWave data; never invent numbers, always ground answers in a tool result" block.

Result: "find me a safe energy setup and explain it simply" -> model calls
`find_best_opportunities(markets='energy', min_win_rate=0.7)` -> gateway card -> narrated.

## 6. Phase 2 - frontend actuation (drive the view)

Goal: Tara operates the wave-viewer. Builds on Phase 1's tool loop.

Changes:
1. **`chatbot.py` response** - add `actions: [...]` to the JSON alongside `reply`. Populate it
   when the model calls a new `update_view(spec)` tool (model-facing name) or `open_guide(guide)`.
   Validate against the allowlist (section 4) before returning.
2. **`Chatbot.js`** - replace the HTML `data-action` string-match with: read `data.actions`,
   validate, then for each: `open_guide` -> the existing 17 popup setters; `set_view` ->
   new `applyViewSpec(spec)` calling `chartSetProps` setters (section 3). Keep the HTML
   fallback only during transition, then delete it.
3. **System prompt** - instruct: "to show the user a chart/pattern/filter, call `update_view`
   with the ViewSpec instead of describing where to click." Reuse the same ViewSpec the model
   already built for the Phase-1 fetch, so the fetched card and the on-screen view match.

Result: "show me this over 20 years on the PE cycle" -> `update_view({years:20, pe_cycle:'pe'})`
-> wave-viewer slider + mode actually change, and Tara narrates the same numbers.

## 7. OPEN DECISION - auth / metering principal for Tara -> gateway

The gateway authenticates per the BYOK model (API key -> tier -> ML quota in redis db4,
keyed by `api_key_hash`). Tara's users are **web/app subscribers with a JWT**, not API-key
customers. Two clean options:

- **(A) Internal service key + separate chatbot quota (recommended).** Tara calls the gateway
  with one internal service token (trusted, loopback). ML usage is metered by the web `user_id`
  using the chatbot's OWN planned per-user quota (already on the `chatbot_readme.txt` roadmap),
  NOT the API ML quota. Keeps the two products' metering separate (API quota = API customers;
  chatbot quota = app users), which matches the "two separate products" stance.
- **(B) Per-user API principal.** Extend the gateway's ML quota to accept a `user_id` principal
  so app users are metered in the same system. More unification, but couples the app chatbot to
  the API billing model and risks blurring the product line.

Recommendation: **(A)**. Decide before Phase 1 lands (it sets where the service token + quota
checks live).

## 8. Marketing

- **Consumer / product (home page, Getting Started tour):** YES, headline Phase 2 - "ask in
  plain English and TradeWave drives the charts for you." This is the answer to the
  "too many things for a new user" problem and the demo-able differentiator.
- **Developer portal (developers.tradewave.ai):** NOT as a product (the dev chatbot is their
  own agent via MCP; docs deliberately never mention a chatbot). One honest **proof line** is
  allowed: "TradeWave's own in-app analyst runs on this same API" - dogfooding credibility,
  subordinate to "your agent + our MCP."
- Market it **after** it ships, not as a promise.

## 9. Non-goals / risks

- Not a trade-execution or portfolio feature. View/analysis control only.
- Not a developer SKU. No public "chat" endpoint.
- Desktop-only (Tara is already desktop-only).
- Reliability: a mis-parsed `set_view` only changes a reversible view; the visible echo +
  user correction is the safety net. Keep the allowlist tight.

## 10. File-by-file (concrete)

Phase 1 (backend):
- `appserver/appserver/AI_tools_appserver.py` - `send_claude_messages`: add `tools=` passthrough.
- `appserver/appserver/chatbot.py` - tool schemas, tool-use loop, gateway client, system-prompt block.
- (config) service token + `API_BASE_URL` per-env in `secrets.env` (never hardcode).

Phase 2 (frontend + backend):
- `appserver/appserver/chatbot.py` - add validated `actions[]` to the response; `update_view`/`open_guide` tools.
- `web-react/src/components/Chatbot.js` - `applyViewSpec`, structured action handling, retire the `data-action` HTML hack.
- (build) rebuild React; gunicorn restart for the Python edits (no auto-reload).

When built, update `docs/TRADEWAVE_ECOSYSTEM.md` (new data flow: Tara -> gateway) in the
same commit, per the repo rule.

## 11. Approved direction - smarter Tara on GPT-5.6 Luna (2026-08-03)

Owner decision: GPT-5.6 Luna is Tara's primary model for every model-bound turn in every
environment. Haiku is fallback-only. Deterministic answers and validated UI actions remain
provider-independent.

### Finding

The segmented prompt and explicit cache are working. The remaining intelligence limit is
orchestration, not token price:

- Every Luna turn currently uses low reasoning and low text verbosity, including deep
  analysis questions.
- The stable behavior prefix is approximately 30,000 characters, around 8,000 tokens in
  observed usage. Caching makes it inexpensive but does not make the instruction set simpler.
- All five tools are exposed to every model-bound turn. Their serialized definitions are
  approximately 4,378 characters, roughly 1,100 tokens, before tool results. The loop allows
  four rounds.
- A local sample of 30 logged Luna API calls cost approximately $0.0308 at the published
  2026-08-03 standard prices, about $0.001 per API call. Quality can therefore receive more
  reasoning budget selectively without undoing the efficiency work.
- Existing tests strongly cover numeric truth and UI-action correctness. They do not yet
  measure relevance, depth, readability, or usefulness across beginner, intermediate, and
  professional trader/investor lenses.

### Target architecture

Keep the boundary explicit: TradeWave computes and verifies facts; Luna prioritizes,
connects, and explains them; the server validates the answer and actions.

1. Add a deterministic complexity router. Direct view commands bypass the model. Simple
   definitions use low reasoning. Loaded-pattern analysis and comparisons use medium
   reasoning and medium verbosity. Deep skeptical, strategy, and "what do you really think"
   questions use high reasoning with a concise output contract.
2. Build one compact, verified analysis brief for the loaded pattern. It should contain the
   exact pattern identity, completed `n`, record, mean/median, Sharpe, TWR, winner/loser
   payoff, MFE/MAE, losing-year path, recent-versus-earlier comparison, outlier concentration,
   occurrence timing, PE context, Trend alignment, and applicable current/shorter AI durations.
3. Add deterministic insight flags such as high-hit/weak-payoff, favorable-path/exit-giveback,
   outlier-dependent average, recent weakness, modest sample, history/AI agreement, and
   history/AI divergence. Luna selects only the facts that change the interpretation.
4. Render broad analysis as five compact sections: bottom line, strongest evidence, path/risk,
   current context, and one best next check with a validated action link. Do not dump every
   available metric.
5. Split the large stable prompt into a small invariant core plus intent-specific modules.
   Move arithmetic, day counting, current-row exclusion, direction semantics, and state
   identity into deterministic enforcement rather than repeated prose.
6. Expose only the tools required by the routed intent and convert schemas to strict mode.
   A loaded analysis with a complete brief should normally require no read tool. This should
   also reduce latency by avoiding unnecessary tool rounds.
7. Preserve compact verified session state: loaded pattern fingerprint, market, lookback,
   PE mode, active lower panel, opportunity-table identity/order, last compared patterns,
   and current analysis brief. Do not use unrestricted opaque model memory when the chart
   state has changed.
8. Keep Luna as the default candidate. Test Luna low, medium, and high blindly before adding
   another model. Route to a different model only if a repeatable eval gap remains.

### Evaluation gate

Create a representative trace set from real Tara failures and successful interactions. Cover
short and long patterns, active/upcoming/completed occurrences, long/short bar semantics, PE
cohorts, above-30-day AI duration comparisons, terse "analyze" prompts, MFE/MAE aliases, loaded
symbol/lookback continuity, table ordinals, and beginner/intermediate/professional explanations.
Grade numeric truth and UI actions deterministically. Grade relevance, completeness, clarity,
and concision blindly. Record quality, tool rounds, latency, input/cache-write/cache-read/output/
reasoning tokens, fallback rate, and estimated cost. Establish the current Luna-low baseline
before changing behavior and evaluate one material change at a time.

### Question-log reality and analytics gap

The current per-environment file is
`/home/flask/appserver/appserver/chatbot_questions.log`. It is JSONL with `ts`, `user_id`,
`provider`, loaded `symbol`, full `question`, and only the first 500 characters of `response`.
It has no conversation/session id, turn id, actions, tools, intent, model settings, prompt
version, latency, token/cache usage, error/fallback detail, user feedback, rotation, or retention
policy. It is useful for spot review but is not a complete future quality-analysis dataset.

Before relying on logs for product analysis, add a versioned, access-controlled event schema
with a conversation id and turn id; provider/model/reasoning/verbosity; routed intent; a
non-price pattern fingerprint; question and complete bounded response; validated actions and
tool names/status; latency; cache/token/cost fields; fallback/error class; prompt/analysis-brief
version; and explicit user feedback. Never log auth tokens, API keys, raw price payloads, or the
full hidden prompt. Add rotation, a declared retention period, and a pseudonymous user key before
opening this analysis beyond the owner.

## 12. Tara awareness of consumer MCP (2026-08-04)

Tara must explain the connected-AI product boundary in plain language. TradeWave computes the
pattern evidence; Tara, ChatGPT, or Claude can help the user work with that evidence.

- An unconnected AI assistant does not automatically have TradeWave scans, exact historical
  results, path evidence, charts, or ML scores.
- Tara is screen-aware inside the Wave Viewer. She can use the loaded pattern, visible table, and
  active chart state, and can drive validated TradeWave view controls.
- ChatGPT or Claude connected through TradeWave MCP can call TradeWave's derived research tools in
  its own chat. It can return charts and an exact Wave Viewer link, but it does not control the
  already-open Wave Viewer.
- Tara and MCP receive server-composed derived evidence from the same TradeWave gateway. For the
  same inputs, the underlying numbers should match even when the assistants phrase the answer
  differently.
- Consumer MCP account authorization follows the web plan. The normal ChatGPT or Claude connection
  uses TradeWave sign-in and does not require a user-created API key.
- MCP never exposes raw market-price history, live prices, or user holdings. It remains impersonal,
  derived-data-only research.

Common product questions are answered deterministically before a model call: what MCP is, how to
connect, API-key requirements, Tara versus an outside assistant, Wave Viewer control, same-data
questions, plan access, data boundaries, and useful starter prompts. Broader connected-AI wording
loads only the dedicated MCP knowledge section through `tara_prompt_context.py`, preserving the
segmented-prompt efficiency contract.
