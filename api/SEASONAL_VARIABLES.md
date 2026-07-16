# TradeWave Seasonal Analysis Variables - Canonical Reference

The single source of truth for what TradeWave's seasonal analysis knobs MEAN and HOW to use them,
for engineers, agents, and future sessions. The API/MCP layer (apiserver + mcpserver) and the
user-facing self-describing guide (`describe_tradewave`) must stay consistent with this file.

No em dashes anywhere in TradeWave copy (use " - ").

---

## 0. The one distinction that governs everything: DETECTION vs ANALYSIS

There are two different engines, with different rules. Conflating them is the most common mistake.

| | Pattern DETECTION | Symbol ANALYSIS |
|---|---|---|
| Question | "Which seasonal patterns exist (across a market / for a symbol)?" | "Score THIS one setup over N years of history." |
| Appserver | OppList4 / OppBySymbol | ChartData4 / consolidated_seasonal_chart2 |
| Gateway | `/v1/scan`, `/v1/opportunities`, `/v1/opportunities/<symbol>` | `/v1/analyze/<symbol>`, `/v1/patterns/...`, `/v1/seasonal-chart` |
| MCP tools | `find_best_opportunities`, `get_seasonal_opportunities`, `get_symbol_patterns` | `analyze_symbol`, `get_seasonal_pattern`, `get_opportunity_chart` |
| `years` meaning | **year1** = lookback; paired with **year2** (min winning years) and CONSTRAINED to a per-market win-rate BAND (only in-band combos are precomputed) | a CONTINUOUS lookback length (1-99), scored on the fly; NO band, any value up to the symbol's available history |

So `years` is band-constrained on the DETECTION tools and free on the ANALYSIS tools.

---

## 1. The detection knobs: `years` (year1) and `min_winning_years` (year2)

A seasonal pattern is "this calendar window, held this long, won in N of the last M years." The
engine exposes the two knobs behind that:

- **`years` (year1)** - the LOOKBACK: how many years of history to scan for patterns. (In PE mode,
  the number of presidential-cycle-position occurrences, not calendar years.)
- **`min_winning_years` (year2)** - of those `years`, the MINIMUM that must have been profitable for
  a pattern to be listed. So `year2 / year1` is the **win-rate floor**. `10-9` = won >= 9 of 10
  years (90%); `20-18` = 90%; `20-16` = 80%.

### The WIN-RATE BAND (the rule that makes "20-9" impossible)

TradeWave's detectors only surface patterns inside a win-rate band: the engine PRECOMPUTES only the
in-band `(year1, year2)` combos and stores them as files on disk. A combo below the floor (e.g.
`20-9` = 45%) is **not a thing** - there is no file, so it can never return results. The floor is
**MARKET-SPECIFIC** (riskier/less-efficient markets get a lower floor). Valid `year2` for a given
`(market, year1)` is `[floor(market, year1) .. year1]`.

Per-market floors (SCAN path / Monthly_Opp grid), measured from the precomputed grid on disk:

| id | market | per-symbol grid? | lookback (year1) range | floor @10y | floor @20y |
|---|---|---|---|---|---|
| 0 | DOW 30 STOCKS | yes | 5-61 | 8 (80%) | 16 (80%) |
| 1 | NASDAQ 100 STOCKS | yes | 5-61 | 8 (80%) | 16 (80%) |
| 2 | S&P 500 STOCKS | yes | 5-61 | 8 (80%) | 17 (85%) |
| 3 | RUSSELL 1000 STOCKS | no | 5-60 | 9 (90%) | 18 (90%) |
| 4 | WILSHIRE 5000 | no | 5-60 | 9 (90%) | 18 (90%) |
| 5 | INDICES COMMON | no | 5-96 | 8 (80%) | 15 (75%) |
| 6 | INDICES ALL | no | 5-57 | 9 (90%) | 18 (90%) |
| 7 | FUTURES & COMMODITIES | yes | 5-50 | 8 (80%) | 16 (80%) |
| 8 | FOREX ALL | no | 5-45 | 9 (90%) | 18 (90%) |
| 9 | FOREX LIQUID | yes | 5-52 | 7 (70%) | 14 (70%) |
| 10 | GOVERNMENT BONDS | no | 5-43 | 8 (80%) | 15 (75%) |
| 11 | ETFs | no | 5-30 | 8 (80%) | 16 (80%) |
| 12 | LONDON EXCHANGE | no | 5-55 | 9 (90%) | 18 (90%) |
| 13 | TORONTO STOCKS | no | 5-43 | 9 (90%) | 18 (90%) |
| 16 | CRYPTO CURRENCIES | no | 5-15 | 7 (70%) | n/a |

The floor is not a clean flat percentage - it is the actual precomputed grid (e.g. S&P at 20y allows
year2 17-20, i.e. 85%+, not 80%). Always trust the grid (the manifest), not a rounded ratio.

### Two grids (scan vs per-symbol)

- **scan path** (Monthly_Opp): exists for ALL 15 markets. Backs `/scan` + `/opportunities`.
- **per-symbol path** (opp_by_symbol): exists for **5 markets only - ids 0, 1, 2, 7, 9** (DOW 30,
  NASDAQ 100, S&P 500, Futures & Commodities, FOREX Liquid). Backs `/opportunities/<symbol>` and
  `get_symbol_patterns`. For any OTHER market the per-symbol tool returns a clear error - use
  `find_best_opportunities` (scan) for those.

### The default

`min_winning_years` DEFAULTS to **~90% of `years`** (clamped into the market band), not a fixed
number - so a bare `years=20` yields a valid `20-18`. (The old fixed default of 9 was the bug: it
was out of band for any year1 > ~11 and silently returned nothing.)

### Behavior on out-of-band

- Single-market endpoints (`/opportunities`, `/opportunities/<symbol>`): **400** with the valid
  range, e.g. "For a 20-year lookback in S&P 500, min_winning_years must be between 17 and 20."
- Multi-market `/scan`: lenient (markets have different bands) and adds a `lookback_note` naming the
  markets the combo is out of band for (so it is never a silent short list).
- PE mode (`pe_cycle` != consecutive): the grid differs (year1 = #occurrences); band check skipped,
  only sanity bounds apply.

Enforced in `apiserver/market_bands.py` (+ the manifest `apiserver/market_bands.json`), called from
`apiserver/routes.py:_lookback_args(market, path, pe_mode)`.

---

## 2. The other selection knobs

- **`min_days` / `max_days`** - the pattern's HOLDING-PERIOD length in calendar days (filters on
  `days_out`). Use both for a range, e.g. `min_days=10&max_days=90`. Available on the detection
  tools (find_best_opportunities, get_seasonal_opportunities, get_symbol_patterns); NOT on
  whats_seasonal_now or analyze_symbol (which pins a single days_out).
- **`pe_cycle`** - presidential-election-cycle mode. `consecutive` (default) scans consecutive
  years; `pe` scans the current cycle position; `pe0`..`pe3` target a specific position (single-
  security/chart endpoints only). In PE mode `years` counts cycle occurrences, not calendar years.
- **`period`** - a wave-viewer date-range PRESET (month jan..dec, quarter q1..q4, season, ytd,
  year_end, buy_hold) that overrides entry_date/days_out. `reverse=true` = the complement window.
- **`direction`** - `long` or `short`. Receipts/returns are direction-aware (a short profits when
  the underlying falls; per-year net and bars are sign-flipped for shorts - see cards.py).
- **`rank_by`** (scan) - edge | win_rate | sharpe (default) | ml | avg_return.

---

## 3. The result variables (what a PatternCard reports)

### The THREE win rates - NEVER conflate them
- **`historical_win_rate`** - share of past YEARS the seasonal window was profitable (in-sample
  seasonal history; the "Percent Profitable").
- **`ml_win_prob`** - the 62-feature ML model's probability THIS instance works. It is
  available on ML-eligible markets when the caller's tier and remaining daily quota allow it
  (Free 5/day, Dev 100/day, Pro/Business unlimited).
- **`track_record.win_rate`** - the LIVE, forward-tested record of past daily picks (out-of-sample,
  the real proof; daily-pick only).

### Other fields
- **`edge_score`** (0-100) - a documented blend (0.40 win_rate + 0.30 Sharpe + 0.20 ML + 0.10
  history). One number to rank by. See cards.compute_edge_score.
- **`bias`** - bullish | bearish | neutral. neutral = a genuine "no statistical edge" finding, not
  weak support.
- **`setup.timing`** - days_to_entry + plain-language status (window opens in N days / in window now
  / passed).
- **stats** - sharpe_ratio, avg/median return %, plus std_dev / annualized / cumulative return and
  sharpe_ratio_mfe. NB: the AGGREGATE stats arrive already TRADE-relative from the appserver (do not
  re-sign-flip for shorts); only the per-year `pct` entries are long-relative.
- **`per_year` / `per_year_bars`** - year-by-year receipts. A bar is `net,mfe,mae` as PERCENTAGES
  (never prices): net = the trade's return; mfe = max favorable excursion (>=0); mae = max adverse
  excursion (<=0); all direction-aware.
- **The Trend Chart** (`seasonal_curve`) - the user-facing name for the year-averaged, normalized
  0-100 seasonal INDEX curve (the typical within-year shape). It is NOT per-year price paths and
  never a price. `curve_summary` describes the trend of the entry->exit hold section.
- **`alignment`** - does the per-instance ML agree with the in-sample seasonal win rate.
- **`extend_research`** - the per-card research hand-off (what TradeWave is blind to + what to check
  with your own tools). Every pattern-bearing response carries the exact educational `disclaimer`.

---

## 4. Market coverage cheat-sheet

- **15 active markets**, ids 0-13 and 16 (14 and 15 do not exist).
- **ML-eligible**: ids 0, 1, 2, 3, 4, 11 (US stock universes + ETFs).
- **Per-symbol pattern detection** (`get_symbol_patterns`): ids 0, 1, 2, 7, 9 only.
- **Scan/opportunity detection** (`find_best_opportunities`): all 15.
- **Free tier**: market 2 (S&P 500 stocks) only.

---

## 5. Progressive disclosure + the educational-only posture (context)

- Every detection/analysis tool defaults to a lean `view=decision` over MCP (full receipts a
  `view=full` away; `view=table` for compact rows). The raw API defaults to `view=full`.
- The integration is EDUCATIONAL-ONLY: impersonal patterns, the same for every caller; it never reads
  or advises on a user's holdings. See MCP_INTEGRATION_ROADMAP.md COMPLIANCE LANDMINES.

---

## 6. Regenerating the band manifest

`apiserver/market_bands.json` is generated from the on-disk precomputed grid by
`ops/generate_market_bands.py`. **Re-run it whenever the appserver's opportunity data is rebuilt**
(the bands move with the data), then commit the manifest. The gateway loads it at startup; if it is
missing the gateway degrades to lenient (no band validation), with the appserver as the backstop.

Related: PATTERNCARD_SPEC.md (the card contract), MCP_TOOLS.md (the tool surface),
MCP_INTEGRATION_ROADMAP.md (the integration plan + compliance).
