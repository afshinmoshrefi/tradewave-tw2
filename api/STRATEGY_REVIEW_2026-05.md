# TradeWave API + MCP - Strategy & Implementation Review (2026-05-31)

Synthesis of a 4-agent review (competitive/concept, implementation, in-chat UX, strategy/GTM),
triggered by reviewing Liquid Co-Invest (liquid.trade/coinvest). All four converged
independently on the same core, which is why this is high-confidence.

---

## 1. The strategic verdict

**Positioning: the provider-neutral EDGE LAYER above every in-chat broker (incl. Liquid).**
Not data (commodity, price war, race to zero - and our EODHD constraint forbids it).
Not execution (capital + regulated + Liquid already pushed it to free on order flow).
The scarce, paid, defensible layer is *the reason to place a trade* = alpha. That band is
nearly empty in equities (only Chart Library is MCP-native; crypto signal players don't
overlap our seasonal-equities/futures/forex turf).

**Posture: hybrid, ~80% stand-alone patterns / 20% "feeds execution" as DISTRIBUTION only.**
Feeding brokers is a discovery channel, never a dependency (their per-trade incentive
opposes ours; platform/clone risk). Be the Switzerland of trading alpha.

**Brand line:** "The edge layer for AI traders. Works with any broker. We don't take your
trades - we show you our receipts."

**The moat = the verifiable track record.** Liquid has $3B volume and ZERO published
out-of-sample performance. Our time-stamped, forward-tested daily-pick ledger is receipts
no execution/data player can fake, and we have no conflict of interest (we don't earn per
trade, so "nothing worth trading today" is credible from us). Make it the hero + free
front door.

**Why patterns-only is focused, not thin:** rich in-chat experience (bundled analysis +
receipts + a clean broker-agnostic handoff) + the conflict-free, provider-neutral story.
Thin products don't publish their win/loss ledger.

---

## 2. Make it POWERFUL - the product gap (unanimous)

Today the API/MCP is a correct but thin "fetch one market, get a list" wrapper. The #1
question - "scan everything I can trade and rank the best setups" - is unanswerable. Fix
with a tiered tool surface: 2 opinionated flagships over the 9 primitives.

### Flagship MCP tools (P0) - compose existing /v1 endpoints, NO new appserver work
- **`find_best_opportunities`** - cross-market scan over a liquid-equities core within the
  caller's scope by default (with explicit markets for broader scans),
  ranked by a documented blended `edge_score` (sharpe x win_rate x ML-if-Pro x history
  length), filters (markets, window="now"|range, direction, min_win_rate, min_years,
  rank_by, limit). The "do what I want" front door. Needs a new gateway endpoint that
  fans out over /v1/opportunities per market + merges/re-ranks + resolves window="now"
  (entry dates in the next ~10 trading days).
- **`analyze_symbol`** - one symbol in, one rich answer out: bundles /opportunities/{symbol}
  + /patterns + /seasonal-chart + (Pro) /score server-side. Kills the current 4-tool
  stitch and the win_rate-appears-in-3-places inconsistency.

### The PatternCard (P0) - the output unit
Structured object with a pre-composed `headline` + `verdict` + inline `receipts`, returned
by the flagships. Fields: rank, symbol, market, direction, setup{entry_window, hold_days,
exit_date}, edge_score + edge_basis, stats{historical_win_rate, sharpe, avg/median_return},
ml{...} (null-not-absent for free, with tier nudge), receipts{years_tested, wins, losses,
win_rate, per_year[], best/worst_year, curve_summary, source, as_of}, next_step{...},
disclaimer.
- RELABEL: `historical_win_rate` (share of profitable years, Percent Profitable) vs
  `ml_win_prob` - never both called "win rate" (current footgun; flagged by 2 reviewers).
- `per_year[]` is the killer receipt ("won 8/10 years; red only in 2022 -4.1%, 2021").
- entry_WINDOW not a single magic day (seasonal entries have tolerance).
- neutral bias / low-conviction state (conflict-free; more credible from us than a broker).

### The no-broker last mile (P1)
`next_step` on every card: a copyable, broker-agnostic order TICKET (side/symbol/type/TIF/
dates/note - NO price level, stays inside the no-raw-prices invariant), "place it at your
broker" framing, and a `set_reminder` (seasonal window opens / hold ends) - the timing
layer is the retention hook we CAN own without becoming a broker.

### Demote the 9 primitives
Keep as the floor; reword descriptions to defer to the flagships ("low-level primitive;
prefer find_best_opportunities / analyze_symbol unless you need this exact slice").

### Later (P2)
explain_pick (daily pick joined to its track record + similar past picks), whats_seasonal_now
(calendar/digest), compare_opportunities, build_seasonal_watchlist, pattern backtest series,
alerts/webhooks (Business hook), saved screens.

---

## 3. Make it CORRECT - P0 bugs (from the implementation review)

1. **`api_tier` split** - console computes api_tier; gateway's db.get_user_by_key_hash never
   selects it (db.py:30-34), so an API-only Pro is enforced as FREE while the dashboard says
   Pro. Wire it end-to-end (enable schema.sql:30 column + select it) OR explicitly scope v1
   to inherited tiers. Revenue bug.
2. **`min_win_rate` silent cap** - MAX_WIN_RATE_ENRICH=50; on S&P 500 (~500 symbols) only the
   first 50 are evaluated and the rest silently dropped. Return `evaluated_count`/
   `enrichment_capped` meta, and/or precompute win_rate server-side.
3. **`to` ignored** - advertised in OpenAPI + MCP, silently uses only `from` (one day).
   Honor the window (the find_best_opportunities work does this) or remove it from the contract.
4. **MCP `get_opportunity_chart` description lies** - says per-year paths; returns one averaged
   0-100 curve. Fix the description (the agent will hallucinate the shape).
5. **Fail-open HMAC** - gateway doesn't refuse an empty API_KEY_HMAC_SECRET; the appserver does
   (appserver.py:565-568). Add the same fail-closed guard.

Also: enrich AFTER the tier slice (free user shouldn't trigger 50 ChartData4 calls);
parallelize/precompute the win_rate fan-out; per-key (not just per-user) rate limiting; don't
meter failed/403 calls; fix prod MCP host drift (routes_mcp.py says mcp.trxstat.com, doc says
mcp.tradewave.ai).

---

## 4. Pricing (validated; structural gaps to close)

$199 Pro with ML as the paywall is CORRECT - priced against Seasonax ($480, Bloomberg-gated)
and SentimenTrader, NOT the raw-data APIs (Polygon/FMP/Alpha Vantage $19-249). Do not frame
as data.

| Tier | Monthly | Annual (~17% off) | ML? | Gate |
|---|---|---|---|---|
| Free / Explorer | $0 | - | No | 3-4 rotating markets + the PUBLIC track record; ~500 calls/day; instant/keyless |
| Dev | $39 | $390 | No | All 17 markets + full record; ~5k/day |
| Pro | $199 | $1,990 | **Yes** | ML win-probability = the paywall |
| Business | $599 + metered overage | $5,990 + overage | Yes | + commercial pattern-redistribution rights (patterns/%s only), multi-key, SLA |
| Founder's (first 100, 12mo) | $99 (Pro 50% off) | - | Yes | Logos + tracked-record testimonials |

Changes vs current: ADD annual, founder deal, metered Business overage. Free tier must EXPOSE
the track record (it is marketing, not product) and be instant/keyless to first value (MCP
discovery dies behind friction).

---

## 5. Distribution / GTM (90 days)

Highest leverage = the official directories (the exact channel Liquid used) + the owned
SMN/tradewave.ai audience.

- **Days 0-30:** lock tier sheet + annual + founder deal in Stripe; make gateway/MCP durable
  systemd units (DONE on dev); publish `.well-known/mcp.json`; disclaimer + ToS (publisher
  exclusion, sec 6); bundle a Dev key into the tradewave.ai consumer sub; private free-tier beta
  to a small SMN segment for the first testimonials.
- **Days 30-60:** submit to the MCP Registry + ChatGPT app directory; list on mcp.so / Glama /
  Smithery / PulseMCP / MCPfinder; ship the "TradeWave + Liquid" complementary recipe + a
  2-min demo; SMN + tradewave.ai launch email; open the founder deal.
- **Days 60-90:** weekly tracked-record content engine (SEO + SMN - the ledger IS a content
  engine); 3-5 affiliate invites; instrument free -> ML-403 -> upgrade funnel; ship the true
  daily seasonal-path endpoint; decide metered overage from real traffic.

Sharp tactical move: publish a "TradeWave + Liquid" recipe (ask TradeWave for the edge + ML
win-prob, then execute on Co-Invest) - ride Liquid's momentum, prove the provider-neutral story.

---

## 6. Business model + risks

**Expansion priority:** (d) tie a Dev key to the tradewave.ai sub NOW (nearly free) -> (a) B2B
pattern LICENSING within 6mo (highest ceiling; the scale path past single-operator seat-selling;
keep it patterns/%s-only to stay inside the EODHD no-raw invariant) -> (b) execution-platform
integration/co-marketing opportunistically (a flat licensed feed, not a trade rev-share) ->
(c) white-label for advisors DEFERRED (multi-tenant load + the advice-personalization line).

**Risks:** (1) patterns-only thinness - countered by receipts + provider-neutral framing + the
Liquid recipe; (2) EODHD derived-only - every B2B/white-label feed must also be %s-only, no
reconstructable series; (3) single-operator scale - favor flat tiers + annual prepay, automate
the funnel, SLA only for Business; (4) the ADVICE line - stay inside the publisher exclusion
(Lowe v. SEC): keep patterns IMPERSONAL (never "given MY portfolio..."), bona fide, regular;
disclaim everywhere; describe MCP tools as "seasonal + ML pattern lookup," NOT "what should I
buy" / "advice" (the model's phrasing to the user is downstream of the tool description). Get a
securities lawyer to bless the ToS before any B2B license.

---

## 7. Recommended build order (on dev, branch feature/api-mcp)

P0a - the 5 correctness bugs (sec 3). Small, ship first.
P0b - the cross-market scan endpoint + `find_best_opportunities` + `analyze_symbol` + the
       PatternCard output shape + win_rate/ml relabel. This is what makes it a flagship.
P0c - neutral bias state + the `next_step` ticket/reminder + reword primitives to defer.
P1  - explain_pick, whats_seasonal_now, annual + founder pricing, Dev-key-in-consumer-sub,
       .well-known/mcp.json, disclaimer/ToS.
Then GTM phases 2-3 (directories, content engine).

NOTE: all P0 product work composes existing /v1 endpoints - no new appserver routes. Update
api/openapi.yaml + api/MCP_TOOLS.md in lockstep. Rebase feature/api-mcp onto main before deploy.
