# TradeWave MCP/API Integration — Research Blueprint

How to make the TradeWave MCP integration (ChatGPT/Claude) and its API analogue *stunningly useful*
for securities researchers. Synthesized from a 15-agent persona panel + a 5-agent charting study +
an adversarial completeness/compliance pass (corrections folded in). Authored 2026-06-08.

Source workflows: `tradewave-mcp-research` (personas + UX + novelty), `tradewave-mcp-charting`.
Key files: `mcpserver/server.py` (15 `@mcp.tool` decorators — recount before any keep/cut math),
`apiserver/cards.py` (`build_pattern_card`), `apiserver/appserver_client.py` (`_PUBLIC_STAT_FIELDS`
~83-102; single service `_token`), `apiserver/auth.py` (`_apply_on_behalf` → WorkOS sub → `users.id`),
`apiserver/routes.py`, `api/MCP_TOOLS.md` (doc/code drift), `site/data/featured_history.json`.

---

## THE THESIS

Quants want more, novices want less — so **default to a decision, make the data one expand away.**
Progressive disclosure is the spine of the whole blueprint: every tool leads with a verdict + timing +
*one* confidence number; the statistical guts (`per_year`, the 365-pt curve, dispersion, methodology)
exist but are gated behind an explicit `detail=`/`fields=` request or a single-symbol deep-dive. That
one rule satisfies the swing trader, the RIA, the quant, and the PM at once — and it directly fixes the
operator's complaint: *"tons of information, more than a researcher needs, then misses useful info."*

## TWO DECISIVE CALLS

- **DO FIRST (today, standalone):** fix the bare-ticker hard-error. `analyze/AAPL` (and `NVDA`)
  currently 400s with "exists in multiple markets 0,1,13,2,3,4" — the single most common retail/agent
  entry path is broken. Resolve to the primary US listing (S&P→DOW→NASDAQ) + `card.note`; never
  hard-error a bare ticker (keep strict mode opt-in). S-effort, zero compliance/token dependency,
  every other feature is moot if the front door breaks on the most-typed ticker on earth.
- **ELIMINATED (product decision 2026-06-08 — educational-only policy):** `scan_my_portfolio` /
  `analyze_my_book`. NOT a "later, after legal review" item — it is removed from the plan. Reading a
  user's actual holdings (share counts, cost basis, computed P&L) and emitting a verdict on a name they
  hold IS personalized investment advice by its substance — the "educational, not advice" disclaimer can
  only describe impersonal output, it cannot relabel conduct that is personalized. The integration stays
  EDUCATIONAL-ONLY (impersonal; the same pattern goes to everyone). `scan_my_watchlist` remains a candidate
  wedge because a watchlist is bare symbols (impersonal — legally fine); its blocker is the act-as token
  SECURITY work, not legal. Any future feature that reads holdings or attaches a directive to a held
  position is OUT unless an attorney signs off first.

---

## 0.5 THE RESEARCH HANDOFF — the central bet (extend INTO and back FROM the LLM)

The product *is*: **human intent → TradeWave's seasonal/ML prior → the LLM extends with its OWN
news/fundamentals/macro → synthesis, in one turn.** TradeWave is a savant statistician blind to news/
fundamentals/macro/earnings/price; the LLM is the inverse (web/news/fundamentals/reasoning, no seasonal
engine). They're now in the same conversation — the only place both halves exist at once. That's the moat.

**It works today only by LUCK** (good user framing + a research-postured model). The default LLM behavior
after a tool returns a big polished blob is **"summarize and stop"** — and TradeWave's pre-composed
`verdict` reads like a *finished answer*, the strongest possible stop signal. The card nails the thesis
but **never states what TradeWave is BLIND to**, so extending is left to chance. Two default failure modes
under thin framing (both real, both worst-case for a trading tool):
- **Fabrication (ChatGPT):** invents a catalyst ("OPEC+ cuts, Mideast tensions") to complete a confident
  card — no web search made.
- **Confirmation laundering (reverse flow):** recasts a TradeWave **neutral-bias coin-flip** as "mild support"
  when the user's framing wants a yes.

**The fix is FRAMING, not data (~100 tokens, mostly static strings, Phase-1):**

1. **`extend_research` block on the card** (cards.py, after `verdict`): `thesis`, `based_only_on`,
   **`blind_to`** [fundamentals/news/macro/valuation/price], `verify_before_acting` [does news/macro/price
   action SUPPORT or THREATEN this seasonal thesis — SEARCH, don't assume], **`in_window_events`** (the one
   gap a seasonal model can *compute* — dates like FOMC/earnings in the hold — but never *weigh*), and
   **`handoff`**: "statistical seasonal edge ONLY — don't invent a catalyst; use your own tools to test the
   above, then synthesize; if you can't verify, say so."
2. **A shared `patterns_only` epistemic line** hoisted to the envelope once (reuse the `_extract_disclaimer`
   de-dup plumbing) — distinct from the *regulatory* disclaimer.
3. **Instruction layer at 3 altitudes:** server `instructions` doctrine (the method:
   **EDGE → EXTEND → CONFIRM-or-CHALLENGE → SYNTHESIZE-with-PROVENANCE**); a one-line suffix on each flagship
   tool description (re-read every time the tool is picked — highest hit rate); and a point-of-decision
   `_HANDOFF` line appended *after* the verdict in `_lead`/`_present_cards`/`explain_pick` **and the
   neutral-bias lead** — this converts the verdict from a stop-signal into a "now go confirm this" prompt.
4. **`how_to_research()` / `describe_tradewave()`** deep-dive tool carrying the full method + provenance
   template + the three-win-rate glossary (pull, not push).

**Loop back INTO TradeWave too (not just out):** prime the model to re-query TradeWave to deepen —
drill-down (`detail=true` for receipts + Trend Chart when the call is marginal), peers/theme
(`compare_opportunities`), triangulate (live track record + ML agreement), and reverse-trigger (a peer/
catalyst surfaced during news research → "seasonal edge on that?"). Make it CONDITIONAL (reach for more
only when it changes the answer — respect latency + ML quota), via `tradewave_next` pointers in the handoff
block + cross-referencing tool descriptions + the `whoami`/`describe_tradewave` menu (a model can't ask for
data it doesn't know exists).

**Guardrails (the synthesis step is where the NEW risk lives):** never let unsourced content masquerade as
fact (explicit negative: "if you didn't search, say so — never fabricate a catalyst"); two labeled evidence
buckets ("From TradeWave (data):" vs "From my own research (verify):") — never one voice; a base rate is a
tailwind not a forecast; news is context that raises/lowers confidence, doesn't silently veto a multi-year
edge; never collapse the three win rates; re-assert the disclaimer on the *synthesized* output + gate
sizing/"place the trade".

**MINIMUM VIABLE SHIP (one PR, hours):** the `_HANDOFF` constant appended after the verdict on the four
leads (`_lead`, `_present_cards`, `explain_pick`, **neutral bias** at server.py ~331/346/574/543). That alone
turns Transcript-2 fabrication into a real web search and Transcript-4 laundering into an honest "no edge."
The `extend_research` block + per-tool suffixes + `how_to_research()` are the fast-follow that make it robust.
This is simultaneously the wedge AND the single largest correctness/compliance liability — highest
cost-of-failure, lowest-cost fix.

## 1. THE IDEAL MCP TOOL SURFACE

**RC status (2026-07-15): exactly 17 tools (6 flagship + 11 primitives).** The frozen,
release-gated contract is `api/MCP_TOOLS.md`; the discussion below is the historical design
baseline that led to that surface.

At the time this roadmap was written there were **15 tools** (5 flagship + 10 primitives). The
problem wasn't count — it was that every tool returned the same HUGE card (`per_year` +
`next_step` + duplicated stat blocks inline) and there was no compact list mode. The fix was
mostly **response shaping + a `view` parameter**, plus targeted adds/merges.

**KEEP (flagship — right units), reshaped:**
| Tool | Lead with | Default (NEW `view=compact`) | Expand |
|---|---|---|---|
| `find_best_opportunities` | ranked list, one compact line/setup: `[TAKE] DBA short · window LIVE · won 10/10 (+3.7%) · ML 77%` | symbol, direction, `call.rating`, `timing`, win_rate, edge, ml — suppress `per_year`/`next_step`/dupe stats | `view=full` or single-symbol call |
| `analyze_symbol` | go/no-go verdict + timing + in-sample-vs-live | one rich card; `per_year`/365-curve behind `detail=true`; `other_setups` as compact rows | `detail=true` |
| `explain_pick` | pick verdict + **live track record front & center** | card + track summary (in-sample 0.82 vs live 0.60 side by side) | per-pick history |
| `whats_seasonal_now` | compact list, entering window in ~10 trading days | same compact list + `timing.status` | full card on request |
| `compare_opportunities` | a decision **TABLE**, one row/symbol | `view=table`: symbol, dir, in_window, days_to, win_rate, sharpe, ml, worst_year, trend_alignment, earnings_in_window | expand one name |

**MERGE/CUT (primitives 10 → ~6):** cut bare `get_daily_pick` (fold into `explain_pick`); merge
`get_seasonal_opportunities` → `find_best_opportunities` (add `market=`); merge `get_opportunity_chart`
+ `get_seasonal_pattern` → `analyze_symbol detail=true`. Keep `list_markets`, `whoami`, `list_symbols`,
`get_symbol_patterns`, `score_opportunities`, `get_pick_track_record`. Fix `MCP_TOOLS.md` doc/code drift.

**Resolve "too much vs too little":**
- *Trim from default card:* `per_year[]` (biggest token whale → behind `detail`); the duplicate
  `stats`/`receipts` win-rate/avg block (keep one); `next_step`/`order_ticket` (deep-dive + order-intent
  only); `edge_basis`; raw `curve_summary` internals (keep the one-line `shape`); debug envelope fields
  (`evaluated_count`, `enrichment_capped`, `markets_scanned`, `generated_at`) → a `meta` sub-object.
- *Add to card (exists server-side, currently dropped — high value):* `card.call`
  {rating, one_liner, top_reason, top_risk}; `setup.timing` {status, days_to_entry/exit, days_left};
  `setup.event_risk` {next_earnings_est, days_to_earnings, earnings_in_window}; `card.trend`
  {trend_long/short(+prev), alignment}; quant stats `std_dev_pct`/`annualized_return`/`cumulative_return`.

---

## 2. MISSING CAPABILITIES (ranked, corrected)

1. **`scan_my_watchlist` — THE wedge. BUILD (unbundled from portfolio).** Scan only the user's own
   TradeWave watchlist symbols → compact card list. Four personas' #1 ask; the "anything seasonal in MY
   names this week?" Monday ritual that drives retention. Watchlist items are **bare symbol strings
   (clean, low-risk)**. Identity resolves today (`auth._apply_on_behalf` → `users.id`). *Real build item
   (sensitive):* the gateway must mint a web-tier-equivalent token for the resolved user id (the
   appserver derives `userid` from the JWT `'user'` claim) — a **privilege-bearing act-as capability**
   needing audience scoping, short TTL, read-only claim, a `can_act_as` check, audit logging, and
   cross-user isolation tests. NOT "pure plumbing." `scan_my_portfolio` is ELIMINATED (see above) — a
   watchlist is bare symbols (impersonal/educational); reading actual holdings is not, so it is out.
2. **Earnings / event-risk flag in window.** `earnings_in_window` + `next_earnings_est`. #1 invalidator
   of a seasonal stat; RIA/PM unblocker. *Caveat (corrected):* `get_earnings_dates` is EDGAR filing
   dates + a **projected estimate**, with coverage gaps (futures/crypto/many ETFs) — ship as *estimated*
   with explicit null-handling, not an authoritative calendar. Not "pure plumbing"; the trust/null work
   is the effort.
3. **Bare-ticker resolve-and-note** (the DO-FIRST above).
4. **`card.call` go/no-go layer.** Collapses six competing confidence numbers into one categorical
   verdict (derive from edge_score + ml_win_prob + live-track agreement). **Educational-only constraint:**
   the label must DESCRIBE the data ("STRONG PATTERN" - the pattern is strong), never DIRECT the user
   ("STRONG TAKE/BUY" — you should act). A directive label is the personalized-advice line; a descriptive
   one stays educational. Attorney sign-off before it leads every card. (Today there is NO `call` field;
   the existing `verdict` is already descriptive, e.g. "Strong, consistent seasonal long" — compliant.)
5. **Window radar (`setup.timing`).** Human-terms timing ("opens in 2 days, closes in 5"). Pure date math.
6. **Calibration receipts** on the live track record: per-row `original_ml_win_prob`,
   `edge_score_at_call`, `realized_mfe_pct` + `calibration_buckets` ("picks called >80% won 8/10"). The
   trust differentiator (data in `featured_history.json` — but only 10 rows today).
7. **`card.trend.alignment`** (with/against seasonal) — turns a stat into a sizing decision for the PM.
8. **`whats_changed(symbols[], since_date)` delta.** *Corrected: heavier than it looks* — there is **no
   stored historical snapshot** to diff against (`featured_history.json` is only the 10 picks). Either
   build a daily snapshot store (then it's L, and a prerequisite for alerts) or descope to a client-side
   "diff vs your last call."
9. **Correlation / `cluster_id` flag on scans.** Catches "one bet dressed as three" (live ETF scan
   returned IEZ/PXJ/OIH — all oil-services, identical ml 0.8452). *Keep this; DROP the broader
   `seasonal_breadth` sector roll-up* — no confirmed sector taxonomy in the code; speculative.
10. **Quant projection mode** (`format=table`+`fields=`, `t_stat`/CI, `next_cursor` pagination,
    methodology/model-version stamp, per-row distribution on `score_opportunities`). Phase 3 — smallest,
    least-retention persona; don't let it creep forward.

**Missing personas the panel under-weighted (from the adversarial pass):**
- **The unauthenticated / free / trial ChatGPT user** — the *dominant* discovery path (curious user, no
  TradeWave account, hits the tool cold). No first-touch "try it on SPY without an account" story,
  no entitlement-aware graceful degradation in the tool *descriptions*. This is the top of the funnel
  and was absent. **Design it explicitly.**
- **Not-linked / empty-watchlist / auth-failure UX.** `scan_my_watchlist` hard-fails with a raw 401 for
  any WorkOS user who hasn't linked a TradeWave account — the *most common early path*. Specify the
  unhappy path (friendly "link your account" + free-tier fallback), don't 401.

---

## 3. SELF-DESCRIBING / EDUCATIONAL LAYER

This research style is novel (no one has seen a seasonal PatternCard in chat), so the real adoption
blocker is "what am I looking at?" — pull, not push:
1. **`describe_tradewave()` / glossary tool (BUILD).** One call: what seasonal patterns are; the **three
   distinct win rates disambiguated** (`historical_win_rate` = % of profitable *years*, in-sample;
   `ml_win_prob` = the 62-feature model; live `track_record.win_rate` = forward-tested out-of-sample);
   the `edge_score` formula; the 0-100 seasonal index (shown as **The Trend Chart**); the patterns-only constraint (why no prices); how to act on
   a card. Conflating the three win rates is THE key misread for every persona.
2. **Inline `methodology` block on deep-dive cards only** (not every card): entry selection, lookback,
   trading-day calendar, ml model version, feature_count, small-sample caution keyed to `years_tested`.
3. **Tighten tool descriptions:** each flagship states in one line who it's for, what it leads with, and
   when to reach for it vs a primitive.

---

## 4. RESPONSE-SHAPING PRINCIPLES (the fix for "too much / misses useful")

1. Lead with the verdict, not the data. 2. One confidence number front + center; demote the rest.
3. Timing in human terms (never make the user subtract ISO dates). 4. Never conflate the three win
rates — print in-sample vs live side by side, labeled. 5. List views = one compact line per setup;
deep-dive = one rich card (>~3 results → compact/table, never N full cards). 6. Order ticket only on
order intent; suppress for RIA/PM by default. 7. Proactively flag risk in one line (earnings mid-hold,
trend rolled over, correlated cluster). 8. Disclaimer once, verbatim, at the end. 9. Show the
denominator on scans ("top of 127 evaluated") + a multiple-testing caveat.

---

## 5. CHARTING (addendum)

> **Terminology:** TradeWave's user-facing name for the 0-100 seasonal index curve is **"The Trend Chart"**
> (internally `seasonal_curve` / `consolidated_seasonal_chart2`). Use "Trend Chart" in user-facing tool
> descriptions, the glossary, and chart labels; the field name stays `seasonal_curve`.

**MCP — how a chat user draws a TradeWave chart → return clean SERIES DATA as JSON, one call, the
client draws it.** Only modality both clients render today (Claude → inline artifact; ChatGPT →
code-interpreter PNG) AND unconditionally patterns-only. A signed **`chart_url` deep-link** rides in the
same payload as universal fallback. Server-rendered images = **later, guarded, Claude-first** (ChatGPT's
MCP image rendering is inconsistent; and TradeWave's existing `svg_wave_chart` builds a price/candle
panel = patterns-only violation — a new curve/bars-only renderer is required).

**The one load-bearing task:** the **Trend Chart** (the seasonal index curve) is already fully drawable
(`/v1/seasonal-chart` ships all 365 `{date,index}` + window + stats), but per-year **bars are crippled** — `cards.py` (`_net_pct`)
discards the MFE/MAE of the `"net,mfe,mae"` triple, and curve+bars take two calls. Fix: un-drop MFE/MAE +
return curve+bars+window+stats+link in one call via `get_opportunity_chart(include=[...], render=data|spec|image)`.

**API chart contract:** render-agnostic envelope — `series[]` + `axes` + `annotations[]`
(band_x hold window, vline entry/exit/earnings, hline midline, point peak/trough, projection index-only)
+ `meta` + `stats`; explicit `units` enum; `chart.patterns_only:true`. A small `/v1/charts/{seasonal,bars,
monthly}/{symbol}?include=...&format=data|png|svg` family; keep `/v1/seasonal-chart` as alias. Optional
guarded `format=png|svg` reusing `report_renderer` (already price-free PNG) + candle-stripped svg panels.

**Charts to ship, in order:** ① the **Trend Chart** (seasonal index curve) + hold window (zero backend — turn on now) ② per-year
bars +MFE/MAE (the linchpin) ③ live-track-record strip ④ cumulative line (client-side recipe) ⑤
comparison overlay. **Skip forever:** price line + projected-price panel (raw OHLC). **Open risk:**
"does ChatGPT render MCP images?" — exactly why data-first stays primary and image stays a Claude nicety.

---

## 6. API / AGENT AUDIENCE (vs the chat user)

Chat user wants a *decision*; dev/agent wants *determinism, density, pagination*. Differentiate by params,
not separate products: `view=`/`format=table`/`fields=` projection (columnar, prose/ticket/disclaimer
stripped, dataframe-ready); `next_cursor` on `/scan`; methodology/model-version stamp + `per_year[].window_dates`
for replicable backtests; `/me` declares Pro-gated features so an agent pre-empts upgrade stubs; structured
enum risk flags (`earnings_in_window`, `cluster_id`, `call.rating`) so an agent can branch; the order
ticket is *for* the autonomous trading agent (gate it out of chat list views).

---

## 7. PHASED PLAN

**Phase 0 — DO FIRST (today):** bare-ticker resolve-and-note. *[S / unblocks the front door]*

**Phase 1 — Quick wins (days; response shaping + dropped-but-existing fields; no new data plumbing).**
Verified truly-quick: `view=compact`/`table` *[S/XL]*; move `per_year`/365-curve behind `detail`, drop
dupe stat block, hoist `next_step`, debug→`meta` *[S/L]*; `setup.timing` date math *[S/L]*; un-strip
`std_dev`/`annualized`/`cumulative`/`trend_long/short` from `_PUBLIC_STAT_FIELDS` *[S/M]*; `card.trend.alignment`
*[S/M]*; `describe_tradewave()` glossary + tighten descriptions + fix MCP_TOOLS.md drift *[S/L]*; charting
Phase-0 (turn on curve drawing — already drawable) *[S/L]*. (Earnings + `card.call` are NOT quick — see below.)

**Phase 2 — The wedge + linchpins.**
`scan_my_watchlist` (the act-as token capability + isolation tests + not-linked/empty/free unhappy paths)
*[M-L / XL — THE retention feature]*; charting linchpin: un-drop MFE/MAE + one-call curve+bars+window+stats+link
*[M / XL]*; `earnings_in_window` as *estimated* w/ coverage nulls *[M / L — RIA/PM unblocker, trust work]*;
`card.call` go/no-go layer **gated on legal sign-off**, softened label *[M / XL, blocked on compliance]*;
calibration receipts on track record *[S / L]*; merge primitives 10→~6 *[M / M]*.

**Phase 3 — Bigger bets.** Daily snapshot store → `whats_changed` + `watch_setup` server-side alerts
(env has Cron/PushNotification primitives) *[L / L]*; `cluster_id` correlation flag *[M / M]* (drop the
sector roll-up); quant projection mode + per-row distribution on `score_opportunities` *[L / M]*;
charting envelope + `/v1/charts` family + guarded render endpoint *[L / M]*.

**Unauthenticated/free first-touch story + not-linked UX** thread through Phases 1-2 — design the cold-start
path (entitlement-aware tool descriptions, "try it on SPY", friendly link-your-account on 401) explicitly.

---

## COMPLIANCE LANDMINES (do not skip)

**STANDING POLICY (2026-06-08): EDUCATIONAL-ONLY.** The MCP/API surface publishes IMPERSONAL market
information — the same seasonal/ML pattern goes to every caller, never tailored to an individual's
holdings or situation (this is what keeps it inside the publisher's exclusion / Lowe v. SEC, not
investment advice). The label follows the conduct: the "educational, not advice" disclaimer is only
true while the output is impersonal. Two rules follow:
  1. **Never read or advise on a user's actual holdings.** No `num_shares` / cost basis / `gain_loss` /
     P&L, ever. `scan_my_portfolio` / `analyze_my_book` are ELIMINATED. Any feature that ingests holdings
     or attaches a directive to a position the user holds requires attorney sign-off before design.
  2. **Describe the data, don't direct the person.** Labels/verdicts state the strength of the pattern
     ("STRONG PATTERN", "Strong, consistent seasonal long"), never "you should buy/sell". The order_ticket
     stays an impersonal template (no price level; "size to your own risk", "place at your own broker").

- **`card.call` verdict framing** — keep descriptive ("STRONG PATTERN"), never directive ("STRONG TAKE/BUY");
  attorney sign-off before it leads. A directive verb + order ticket + held position = the advice line.
- **Forged per-user token (only ever for impersonal data like a watchlist)** — audit log every act-as,
  scope audience + TTL + read-only, isolation-test WorkOS-sub→user-id (a resolution bug = serving user A's
  data to user B). Never use it to reach holdings.
- **Disclaimer** — exact regulatory string, once, verbatim, never paraphrased; on every PATTERN-bearing
  response (not just PatternCards): `/scan`, `/analyze`, `/daily-pick`, AND the primitives that return a
  win rate / ML probability / return / track record (`/opportunities`(+`/<symbol>`), `/patterns`,
  `/seasonal-chart`, `/score`, `/daily-pick/track-record`). Pure catalog/account (`/markets`, `/me`,
  `/symbols`) are exempt. Verified by an adversarial educational-only audit 2026-06-08.
