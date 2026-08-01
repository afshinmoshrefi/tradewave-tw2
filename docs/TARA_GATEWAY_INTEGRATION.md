# Tara on the Gateway - integration spec

Status: PHASE 1 (read-client) + PHASE 2 (UI-actuation) BOTH BUILT + verified on dev 2026-06-02.
Owner decision on the auth/metering principal (section 7): RESOLVED = option A (internal chatbot
service key + per-web-user 'cb:'-namespaced quota).

Provider note (2026-08-01): model-bound dev turns now have a sticky 10% GPT-5.6 Luna canary;
staging/production default to 0%. `run_chat_with_tools` (Anthropic) and
`run_chat_with_openai_tools` (OpenAI Responses) both execute calls through the same validated
`_execute_tara_tool` path. Luna uses low reasoning/verbosity, explicit stable-prefix caching, and
automatic Haiku fallback. Deterministic planner answers run before provider selection.

Phase 2 as built: an `update_view` tool lets the model DRIVE the wave-viewer. Both tool loops
in `tara_gateway.py` return (text, actions); an update_view call is
validated server-side (`_validate_view_spec`: allowlist + range-check symbol/market/entry_date/
days_out/years/pe_cycle/show_mfe/show_mae, dropping invalid fields) and queued as `{type:'set_view', spec}` -
it never hits the gateway. `chat()` returns `{reply, actions}` (additive; old bundles ignore it).
`Chatbot.js applyViewSpec` re-validates each field then calls the React setters (mirrors
`loadOppWV`; a fresh load only on a symbol CHANGE), and `SetPEselected` was added to
`App.js chartSetProps`. The TOOL_INSTRUCTION is appended (recency) and forcefully tells the model
to drive the view rather than tell the user where to click. Verified live: "load NVDA, 20 years"
-> action `{market:'1',symbol:'NVDA',years:20}`; "change lookback to 15" -> `years:15`; "switch
to PE+2" -> `pe_cycle:'pe2'`. React bundle rebuilt (served from web-react/build on dev). Blast
radius of the actuation = which chart/knobs the user sees (no code exec, no data beyond the
derived-data-only gateway, no auth/billing).

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
  days_out?:   integer,  // 1..366
  years?:      integer,  // 1..99 (lookback)
  pe_cycle?:   'consecutive'|'pe'|'pe0'|'pe1'|'pe2'|'pe3',
  show_mfe?:   boolean,  // best-move overlay on the year-by-year chart
  show_mae?:   boolean,  // worst-move overlay on the year-by-year chart
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

A single `applyViewSpec(spec)` helper in `Chatbot.js` walks these keys and calls the
matching `props.Set*` from `chartSetProps`. No new state is introduced - it drives the
exact setters the dropdowns/sliders/row-clicks already use.

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
  gateway's existing validators: days_out 1-366, years 1-99, period enum, pe_cycle enum).
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
