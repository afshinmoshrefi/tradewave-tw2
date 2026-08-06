# TradeWave - Methodology & Functionality Knowledge Base
_Derived from a 20-agent deep read of "The 100-Year Pattern" (260pp), 2026-06-25. Durable expert reference for product + onboarding work._

## === FINAL SYNTHESIS (distilled expert layer) ===

### Executive Overview

TradeWave (a registered trademark of Tara Data Research LLC; founder Afshin Moshrefi) is a seasonal-pattern MEASUREMENT ENGINE plus an AI interpretation layer, built to answer one question: "Is what the market is doing right now normal for this point in the calendar and the presidential/political cycle, or is it an outlier I should be cautious about?" It replaces folklore ("Sell in May"), headlines, and gut feel with measured probability stated in exact dates and percentages, drawing on ~98 years of S&P 500 history and on the order of a trillion data points. Its identity is explicit: "not a prediction book, a probability book"; "built for measurement, not mythology"; "no forecasting, no predictions, just context."

METHODOLOGY. A seasonal pattern is a recurring, testable tendency driven by real-world behavior (holiday/retail spending, agricultural cycles, fiscal-year budgeting, earnings windows, inventory/supply chains, tax flows, energy/weather demand, election-cycle policy timing) — "the market's chord progression," not a crystal ball. A pattern is uniquely defined by FIVE things together: symbol + start date + days held + year set + direction; change any one and it is a different pattern. It becomes a decision tool only when you measure how OFTEN it happened (win rate), how LARGE the move was (avg/median gain), and how MESSY it gets when it fails (volatility, drawdown, outlier-dependence). The differentiating 2026 idea is REGIME CONDITIONING via the Presidential Election Cycle (PE / PE+1 / PE+2 midterm / PE+3): "a regime is not what the market is, it is the lens you measure it with." Blending dissimilar years dilutes real edges or manufactures fake ones; isolating like-years reveals structure. The flagship discovery — the "100-Year Pattern" — is a PE+2 (midterm) S&P 500 window ~Sep 27 → ~Jul 18 (~295 days), profitable in 23 of 24 cycles (96%, failing only in 1930), 19% avg gain vs 4% buy-and-hold, anchored to the next cycle starting September 27, 2026. The credibility rests on showing its work: proprietary metrics MFE (best favorable excursion), MAE (worst adverse excursion), TWA (TradeWave Average, MFE-based), and the signature TWR (TradeWave Ratio — Sharpe-like but incorporating MFE, so it rewards strong-along-the-path windows Sharpe discards), used alongside Sharpe, win rate, median, std dev, cumulative return, and the Buy & Hold benchmark.

CAPABILITY BREADTH. The product runs one disciplined loop — SCAN → VALIDATE → ORGANIZE → ACT ("Scan then Lab") — across two operating modes. SHORT-TERM/active trading lives in the Opportunity Table (the scanner: rank thousands of securities × windows × samples × regimes, filter with a precise no-spaces string syntax, detect "regime flips") → the Wave Viewer Lab (Profit Bar Chart → Trend Chart → Stats Table, in that fixed order) → window alignment to the pivot zone → predefined exits (MFE target, MAE stop, time horizon) → trigger confirmation (50-day MA, Trend Long) → options expression (calls/puts, OTM/ATM credit spreads) over 10-120 day horizons. LONG-TERM/investing lives in Buy & Hold Analysis → Reverse Date Range → Best Seasonal Hold Window (150-340 day holds, 25-63+ year samples), benchmarked on Cumulative Ret vs B&H, with PE-cycle macro positioning (the 100-Year Pattern, per-cycle optimal windows, the "Lost Summer" Sep 4-Oct 25 weak window), covered-call income overlays, do-not-trade filters, tax-aware (Roth-preferred) execution, and three-axis diversification (timeframe/sector/asset class). Both modes share the Portfolio Manager (saves the full reproducible CONFIGURATION, virtual-position tracking, calendar reminders, ~2000-pattern quota), Custom TradeWave Reports (static, shareable, PNG/CSV, advisor workflow), appendix QR/deep-link loadable patterns, and a strictly read-only AI layer (TradeWave Research chatbot "Tara" + Green/Yellow/Red Confidence Overlay) governed by the hard rule: "TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics."

### What Tradewave Can Do

An organized, exhaustive capability map. TradeWave is a two-layer system: Layer 1 = the deterministic Engine (the math, auditable, "shows its work," ~trillion data points); Layer 2 = the AI Research Agent that only interprets. Every screen operates on a "pattern" = symbol + start date + days held + year set + direction.

1. THE OPPORTUNITY TABLE (the Scanner / triage). Ranked output of the engine across thousands of securities × windows × samples × regimes × quality metrics for a chosen start date. Controls: Universe selector (S&P 500, Nasdaq 100, Dow 30, Wilshire 5000, sectors, ETFs, futures, forex); Start Date Month + Day dropdowns; Years dropdown (consecutive max ~61, cycle mode far fewer e.g. 15); the PE+2 checkbox/regime toggle (the master dial — changes the DATASET, not the display); consistency/hit-rate selector ("9 of 10 years"); a Filter field; column-header sorting; tooltips on/off. Columns: Date · Ticker · Days · DIR (Long/Short) · AvgP · A%/SR · TWA · TWR. Filter-string syntax (no spaces, ";"-joined, day-range first then metric thresholds): e.g. `2-24;sr>1.0;twr>1.50`, `10-90;twa>10;twr>1.40`, `2-24;sr>1.30;twr>1.50`. Footer summarizes (e.g. "236 opportunities, 226 Longs, 18 Shorts, 95%"). SECOND USE — regime detector: hold date/depth/horizon constant, toggle only the lens, read whether longs/shorts/% stay or flip (Jan 5 2026 S&P 500 5-60d: Consecutive 10yr = 85 opps/93% bullish vs PE+2 10yr = 30 opps/83% bearish). "Ranked highly ≠ approved trade."

2. THE WAVE VIEWER (the Lab / validation). Loads ONE pattern; label like "20-Year NVDA 01-22 to 02-18." Toolbar: symbol field, as-of/anchor date, date-range window (MM-DD to MM-DD), days/window-length, years, regime dropdown (consecutive / PE / PE+1 / PE+2 / PE+3), MFE + MAE overlay checkboxes, "Months & Qtrs" grouping, "Jan-Dec" full-year toggle, Help (?), Reverse Date Range (top-right, desktop), Save (+). THREE validation views in fixed order, all regime-aware: (A) Profit Bar Chart — one raw underlying-price-return bar/year, green/up=price rose and red/down=price fell; green is profitable for Longs while red is profitable for Shorts; height=magnitude, MFE/MAE shading; shows distribution and whether a "hero year" carries the average. (B) Trend Chart — many years compressed into the most-typical PATH, window shaded, < > year nav; marks recurring weak zones and the pivot zone; used to prevent panic-exits and overstaying, and for window alignment (BA Jan-23→Jan-27 lifted Sharpe 0.8→1.14). (C) Stats Table — five blue panels: Wave Detail (symbol, direction, date range, days hold), Wave Profit Loss (winners, losers, cumulative return, S&P 500 B&H), Wave Stats (avg loss, avg gain, median gain, std dev), Wave Info (% profitable, Sharpe, Trend Long, Trend Short), General (years filter, group, last price, ACTIVE flag for in-progress year) + cumulative-return mini-chart vs S&P. Per-window stats strip on cards: Sharpe (two values), Avg Gain, % Profitable, Cumulative Ret, B&H [ticker].

3. THE TWO MASTER DIALS + TECHNIQUES. Dial 1 Years/sample depth (calendar years in consecutive mode vs cycle samples in PE mode — "8 years ≠ 8 PE2 years"). Dial 2 Regime/PE-cycle lens. Reverse Date Range (flip a window to its complementary worst/best period). Date Range Presets (Q1-Q4, Spring, Summer, Buy & Hold, individual months). Buy & Hold Analysis (Jan-1→Jan-1 baseline benchmark). Optimal Dates / Best Seasonal Hold Window output with Cumulative Return Multiplier (DIS 35x, AAPL 40x, ADI 38x, AMD 6,220x). Metrics: MFE (targets/strikes), MAE (stops/sizing/invalidation), TWA, TWR (≥1.5 consecutive / ≥1.0 PE-cycle filter thresholds), Sharpe (the "not-luck" check).

4. THE PORTFOLIO MANAGER (operational library). Save Pattern stores the full CONFIGURATION (entry/exit dates, direction, days, Years/lookback definition, group, tags, notes) — reproducible, not a chart image. Columns: checkbox · Entry · Exit · Days · Ticker · DIR · SR · Years · Group · action icons · # shares · $ invested · % live. Dual Years format: plain number = consecutive; PE2-N = N midterm-cycle years. Header quota ("Saved Patterns 1382 / Remaining 618", ~2000 cap). Per-row 7-step toolbar: recall/refresh, report, calendar reminder, delete, # shares, $ invested, % live. Virtual positions (track current year vs history, for CONTEXT not prediction). Multiple named portfolios by theme; Notes = trading journal; Securities Group (watchlist); portfolio summary footer.

5. REPORTS & SHARING (Appendix E advisor workflow). Custom TradeWave Report — static, self-contained, link-shareable, interactive public page: header + descriptive paragraph, Opportunity Key Information stats block, Gain/Loss bar chart, Trend Chart, "Load on Wave Viewer" link, share icons (email/Facebook/X/Reddit/LinkedIn/StockTwits/Gmail/copy-URL), optional PNG + CSV downloads. Advisor flow: Wave Viewer + → Portfolio Manager → report icon → share. Print-to-app QR codes / deep-links on every appendix pattern (Appendix C carries two: Best Window + Buy & Hold).

6. THE AI LAYER. TradeWave Research (Tara-class chatbot) — reads outputs, answers plain-English questions (worst drawdowns by year, PE+2 vs all years, reverse-window comparison, early-vs-late return distribution, "why ranked high if Sharpe moderate"), cuts analysis 30 min → 3. Confidence Overlay — Green/Yellow/Red reliability rating + 2-4 bullet reasons (sample size/year-set relevance, dispersion/outlier dependence, drawdown severity, modern-vs-older consistency, gain concentration); answers "how stable is this edge and how easy to misuse," distinct from the historical edge. Announced/not-yet-built: one-page auto-brief per pattern; autonomous daily watchlist scanning. Hard rule: AI never invents statistics.

7. OPTIONS / EXECUTION TOOLING. Option Risk Graph (P/L at expiration, P/L with time value, break-even line, strike markers). MFE → strike/target; MAE → invalidation/sizing. Structure matching: directional → calls/puts; range → credit spreads/iron condors; volatility/events → straddles/strangles; asymmetric → ratio spreads. OTM credit spread = time-decay income in stable windows; ATM = directional, exit 20-50% via buy-to-close. Covered-call income overlay (strike just above typical MFE + cushion). Buy options ~2 months past the window, exit ~1 month early. External confirmation layered on: 50-day MA, Trend Long.

8. APPENDIX DATA SURFACES. Repeatability-proof grids: win% (sample count) across day-length buckets (All/10-30/30-60/60-90/60-120) and Year-Pair settings (10_9, 10_10, 15_14, 15_15, 20_18, 20_19, 20_20). Split Consecutive (Baseline vs Filtered TWR≥1.5) and PE-cycle (Baseline vs Filtered TWR≥1.0). Green cell = Win% ≥ 80% (only when sample count is meaningful); 30-60 day bucket = the practical sweet spot. Appendix D = multi-month commodity/futures holds (RBOB long Jan25-Mar3 4,805% cumulative, Gold, Lean Hogs, etc.).

CROSS-CUTTING FLOWS. Short-term tactical: Table → Wave Viewer validation → MAE stop/MFE target → trigger confirm → options → Save → execute with reminder. Long-term hold: Buy & Hold baseline → find weak window on Trend Chart → Reverse Date Range to exclude it → optimize → confirm Cumulative Ret > B&H → save/track monthly. Regime-first discipline overlays both (set lens + depth before reading any chart). Governance: deterministic engine produces numbers, AI only reads them.

### Seven Day Learning Path

Raw knowledge/practice material (NOT screen designs) — the ordered set of concepts + features a new user must absorb and try to become genuinely productive in 7 days. Each day pairs a CONCEPT (the methodology behind it) with FEATURES to exercise.

DAY 1 — The thesis, the mental model, and what a pattern IS. Learn: TradeWave answers "is this move normal for this calendar point and cycle, or an outlier?"; it is a probability tool not a prediction oracle ("no forecasting, just context"); seasonality = testable recurring real-world behavior (holidays, fiscal years, earnings, harvests, tax flows, energy/weather, election timing), "the market's chord progression," not magic. The unit of analysis: a pattern = symbol + start date + days held + year set + direction (change one → different pattern). The three measures that make a pattern a decision tool: how OFTEN (win rate), how LARGE (avg/median gain), how MESSY (volatility/drawdown). The two-layer architecture (deterministic Engine vs read-only AI) and the hard rule "AI never invents statistics." Do: read the Opportunity Table footer summary; load one familiar ticker into the Wave Viewer; identify the five fields that define the loaded pattern.

DAY 2 — The core loop and the three validation views. Learn: SCAN → VALIDATE → ORGANIZE → ACT ("Scan then Lab"); the Opportunity Table is TRIAGE ("ranked highly ≠ approved trade"); the Wave Viewer is the Lab. The fixed validation order and what each answers: Profit Bar Chart = distribution/consistency (is it broad-based or a "hero year"? are losers contained?); Trend Chart = the typical PATH/timing (coherent direction? where is the pivot zone and the recurring weak zone? — NOT a prediction); Stats Table = quantified reliability (% profitable, Sharpe, median vs avg, std dev, cumulative vs B&H, Trend Long/Short). Do: pick 3-5 candidates from the table, validate each through all three views in order, accept a trade only when all three align.

DAY 3 — The metrics that separate real edges from noise. Learn every metric: Win Rate/% Profitable (a historical frequency "X of Y years," not a forecast); AvgP (skewable by outliers); Median Gain (the sanity check); Std Dev; Sharpe (risk-adjusted, smoothness, "not-luck" check, but ignores the PATH); MFE (best favorable excursion → targets/strikes); MAE (worst adverse excursion → stops/sizing/invalidation); TWA (MFE-based average); the signature TWR (Sharpe-like + MFE, surfaces strong-along-the-path windows Sharpe discards; filter ≥1.5 consecutive / ≥1.0 PE-cycle); Cumulative Ret and the multiplier; B&H (Jan-1→Jan-1 benchmark). THE core decision skill: read Win Rate WITH Sharpe — hit rate gives direction, low Sharpe = lumpy/choppy (use staged/hedged tactics), high Sharpe = clean repeatable drift. Sample-size gating: high % on tiny Opp counts (91% on 11) is NOT meaningful. Do: contrast two patterns (e.g. a high-hit/low-Sharpe vs high-Sharpe one); toggle MFE/MAE on the bar chart.

DAY 4 — Regime conditioning: the most important 2026 idea. Learn: the Presidential Election Cycle (PE / PE+1 / PE+2 midterm / PE+3); 2026 = PE+2; "a regime is a LENS, not what the market is"; blending year types dilutes or fakes edges; the two controls every user sets deliberately BEFORE reading any chart — Control 1 (which lens) and Control 2 (sample depth), and that "8 years ≠ 8 PE2 years" (cycle samples span ~4× the calendar). The "10 of 10" misread (qualifying cycle years, not consecutive). The regime-flip technique: hold date/depth/horizon constant, toggle only the PE+2 checkbox, read whether the opportunity set stays or flips; when lenses disagree, THAT disagreement is the signal and the clearer lens is the dominant regime to refine inside. "Sell in May" is regime-specific (weakness concentrates in PE+2). Do: run the same scan in Consecutive vs PE+2 mode and observe a flip; use the Wave Viewer regime dropdown to re-run one ticker across all four cycle types.

DAY 5 — The flagship discovery + the short-term execution discipline. Learn the 100-Year Pattern: PE+2 S&P 500 window ~Sep 27 → ~Jul 18 (~295d), 23 of 24 cycles (96%), failing only 1930, next cycle Sep 27 2026; "the filter revealed it, did not create it." Then the active-trader execution rules: "seasonality sets the BIAS not the TRIGGER"; horizon is 10-120 days (intraday is noise); window ALIGNMENT to the pivot zone with small honest shifts vs CURVE-FITTING (searching the whole calendar — illegitimate); set the exit BEFORE entering (MFE target, MAE stop, time horizon — "lazy traders execute exits, they do not improvise them"); avoid panic-exits (check Trend Chart context, AVGO case) and overstaying past the peak (BX 17d Sharpe 2.18/+102% collapses to -0.01/-2% at 86d); confirm the trigger (50-day MA, Trend Long) and pass/reduce size on strong conflict; "seasonality is probability not protection" (NVDA -23.16% MAE, finished -5.22%). Do: align a window to its pivot and watch Sharpe/Avg Gain update; deliberately widen a window and watch the stats degrade; write down MFE target + MAE stop for one setup. Briefly meet options expression (calls/puts 2 months past window, OTM=income/ATM=directional).

DAY 6 — The long-term investing workflow. Learn the investor's distinct loop: Buy & Hold Analysis (full-year Jan-1→Jan-1 baseline, read cumulative + green/red bars vs S&P) → find the recurring weak window on the Trend Chart → Reverse Date Range to EXCLUDE it and recompute (AAPL ex-September 216,221% → 3,765,269%) → hand-tune/optimize → the governing decision rule: a window earns its keep only when Cumulative Ret > B&H. The Best Seasonal Hold Window output and Cumulative Return Multiplier (DIS 35x/AAPL 40x/AMD 6,220x); the near-universal "late-Sep/Oct → following-summer" shape and the Lost Summer Effect (Sep 4-Oct 25, ~-1%). Long-term overlays: covered calls over weak windows (strike above typical MFE + cushion), the do-not-trade filter, tax-awareness (Roth preferred). Macro PE-cycle positioning: classify the year first, then apply the regime-correct window (per-cycle optimal windows table). Portfolio construction: short-term satellite around a long-term diversified core; three-axis diversification (timeframe/sector/asset class). Do: run Buy & Hold + Reverse Date Range on 10 familiar tickers; confirm Cumulative Ret > B&H on each.

DAY 7 — Operationalize, automate, and communicate. Learn: Save Pattern stores the full reproducible CONFIGURATION (not a chart) including the Years/lookback definition (plain number = consecutive, PE2-N = cycle); Portfolio Manager as the pattern library with multiple themed portfolios, virtual-position tracking (context not prediction), per-row recall/report/calendar/delete, the ~2000 quota, Notes-as-journal, Securities Group watchlist. Calendar Notifications (edges fail in execution, not research). Custom TradeWave Reports (static, shareable, PNG/CSV, Load-on-Wave-Viewer, advisor email template) and appendix QR/deep-link loadable patterns. The AI layer as accelerant: TradeWave Research for plain-English questions, Confidence Overlay Green/Yellow/Red + bullet reasons before committing. The cadence (15-min daily scan / 60-min weekly plan for traders; track MONTHLY not daily for investors; repeat windows annually). The closing minimum workflow: pick ONE style, commit 90 days, define risk rules before entering, prioritize consistency over the best-looking average. Do: save a validated pattern with notes, set a calendar reminder, generate and share a report, ask the AI two questions about a loaded pattern.

GUARDRAILS woven throughout all 7 days: TradeWave is a thinking tool not a black box/auto-trader; alignment ≠ curve-fitting; backtesting answers "consistent enough and stable across regimes?" not "what always works"; the only unacceptable outcome is the big loss; standing down is a position; "the goal is to eliminate unforced errors, not uncertainty."

### Tara Role

Tara is the in-app AI research assistant — the user-facing surface of TradeWave Research, the "Tara-class research agent" that is Layer 2 of the two-layer architecture. Her role for a new user is ACCELERANT and INTERPRETER, never source-of-truth or trader. The governing boundary is absolute and should shape every way she is presented: "TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics." She is "a very fast intern" reading the deterministic engine's auditable output — "AI is not the edge. The edge is the edge. AI just helps you find it faster, understand it better, and apply it with fewer mistakes."

What she does for a new user: (1) She collapses the learning curve — turning ~30 minutes of manual stats-reading into ~3 minutes by answering plain-English questions ABOUT the measured numbers: "Why is this pattern ranked high if the Sharpe is only moderate?", "Show me the worst drawdowns inside this window and which years they happened," "Compare this window to its reverse date-range window and tell me which is cleaner," "Does this pattern work better in PE+2 than in all years?", "Summarize how much of the return happens early vs late in the window." For a beginner, this is the bridge from the dense Stats Table to actual understanding — she teaches the metrics by answering questions about the user's own loaded pattern. (2) She is paired conceptually with the Confidence Overlay, the reliability second-opinion that rates an edge's STABILITY and misuse-risk (Green = solid/consistent/drawdown matches reward; Yellow = mixed reliability or cautionary drawdowns; Red = fragile/outlier-driven/too noisy) and ALWAYS gives 2-4 short bullet reasons — "not vibes, not a black box." Together they let a novice get a sanity check before committing capital, answering a different question than the historical edge itself: "how stable is this edge and how easy is it to misuse?"

What she must NOT do (critical onboarding framing): she does not predict, does not invent or override the engine's numbers, and does not give personalized financial advice. Announced-but-not-yet-built capabilities (one-page auto-brief per pattern; autonomous daily watchlist scanning that flags whether a current move is historically normal vs extreme) should be treated as roadmap, not present reality, and verified against the live product before onboarding leans on them. Net: position Tara to a new user as the fast, plain-English guide who explains what the engine already measured and flags reliability — reinforcing, never undermining, the "measurement not mythology" thesis.

### Onboarding Implications

Principles (not screens) for designing new-user onboarding, derived from the methodology and capability surface:

1. TEACH THE MENTAL MODEL BEFORE THE BUTTONS. The product's entire value is a way of thinking ("is this move normal for this calendar point and cycle?"). A user who learns clicks without the model will misread every number. Onboarding must front-load: probability not prediction, the SCAN→VALIDATE loop, and the rule "ranked highly ≠ approved trade." The biggest failure mode to design against is treating the Opportunity Table as a buy list.

2. MAKE THE FIVE-PART PATTERN DEFINITION CONCRETE EARLY. Because a pattern = symbol + start date + days held + year set + direction, and because "8 years ≠ 8 PE2 years," the single most dangerous misconception is ambiguity about what dataset a number describes. Onboarding should make the user feel that changing the Years dropdown or the PE+2 toggle changes the underlying data, not the display.

3. ENFORCE THE FIXED VALIDATION SEQUENCE. The book is emphatic and repeats it: Profit Bar Chart → Trend Chart → Stats Table, act only when all three align. Onboarding should bake this order in as a habit, not present the three views as interchangeable tabs.

4. SPLIT THE TWO PERSONAS EXPLICITLY. Short-term traders and long-term investors use fundamentally different workflows, tools, horizons, and benchmarks (Opportunity Table vs Buy & Hold Analysis; Sharpe/TWR vs Cumulative Ret > B&H; 10-120 days vs 150-340 days). The closing-chapter guidance is "pick ONE style and commit for 90 days." Onboarding should ask the user which they are and route them, rather than dumping the whole surface.

5. INTRODUCE REGIME CONDITIONING AS THE DIFFERENTIATOR, CAREFULLY. The PE+2 lens is the most powerful and the most confusing concept (it changes the dataset, the meaning of "Years," and "10 of 10"). It is also the 2026 hook. Onboarding should demonstrate a regime FLIP live (same scan, two lenses, opposite tone) because seeing it is more convincing than explaining it.

6. SET THE METRICS FLOOR: WIN RATE WITH SHARPE, AND SAMPLE-SIZE HONESTY. The core judgment skill is pairing hit rate (direction) with Sharpe (smoothness/tactics), and never trusting a high % on a tiny sample. Onboarding must inoculate against the "100% on 2 opps" trap and against outlier-driven averages (teach Median and the hero-year check).

7. RISK DISCIPLINE IS NON-NEGOTIABLE AND SHOULD BE PART OF FIRST SUCCESS. "Seasonality is probability, not protection"; define the exit (MFE target, MAE stop, time horizon) BEFORE entering; the only unacceptable outcome is the big loss; standing down is a position. The first guided trade/analysis should require the user to state a stop and target.

8. LEAD WITH FAST WINS VIA PRELOADED PATTERNS. The appendix QR/deep-link loadable patterns and the "pick 10 familiar tickers" exercise let a user reach a real, validated result in minutes. Use concrete, high-quality example patterns (clean ones like AXP 100%/Sharpe 2.52, plus a deliberately messy one) to teach reading-the-evidence quickly.

9. POSITION THE AI AS GUIDE, NOT ORACLE. Surface Tara and the Confidence Overlay as ways to UNDERSTAND the engine's numbers faster, always reinforcing "AI never invents statistics." This both accelerates the beginner and protects the brand's "measurement not mythology" credibility.

10. CLOSE THE LOOP TO RETENTION: SAVE → TRACK → REMIND → REPEAT. The product's durable value is repeatability over time (reproducible saved configs, virtual positions, calendar reminders, annual window repeats). Onboarding should end by getting the user to save at least one pattern and set one reminder, because "seasonal edges fail in execution, not research."

11. RESPECT THE HOUSE VOICE AND CONSTRAINTS. Confident historical-evidence framing (never hedged), AP Title Case headlines with no terminal period, no em-dashes, no third-party name-drops — the onboarding copy must match the established TradeWave voice.

### Open Questions (verify vs live product)

- Exact live control labels and placement: the four sections describe controls from the book (e.g. the 'PE+2 checkbox', 'Months & Qtrs' dropdown, Reverse Date Range 'top-right select box, desktop only', the Save '+' icon). Verify the live React wave-viewer and Opportunity Table use these exact labels/positions before designing flows around them.
- Filter-string syntax fidelity: confirm the live Opportunity Table actually accepts the no-spaces, semicolon-joined, day-range-first syntax (e.g. `2-24;sr>1.0;twr>1.50`) and which metric tokens are valid (sr, twr, twa, price/days filters) — book examples may differ from the deployed parser.
- Metric naming collisions: the book uses TWA for both 'TradeWave Average' and occasionally as a column header, and TWR is called TradeWave Ratio / Rating / Win Ratio in different places, plus the column header shows 'A%' vs 'SR'. Verify the live UI's exact column headers and tooltip definitions so onboarding teaches the real labels.
- AI layer reality vs roadmap: confirm which AI features are actually live in the product today — TradeWave Research/Tara chat and the Confidence Overlay are described as built, but the one-page auto-brief and autonomous daily watchlist scanning are explicitly 'announced, not yet built.' Onboarding must not promise unbuilt features. Also reconcile with the memory note that Tara is a gateway client tuned to ~80% and may screen from OppList4.
- Portfolio Manager specifics: verify the ~2000 saved-pattern quota, the dual Years column format (plain number vs PE2-N), Calendar Notifications behavior, and the report-sharing channels (which social/share icons and PNG/CSV downloads truly exist in the live build vs the book).
- Reverse-trial / tier gating interaction: per project rules new signups get a 7-day full Strategist trial then drop to Explorer (DJ30 / level '1'). Confirm which markets, universes (S&P 500 / Nasdaq 100 / Wilshire 5000 / futures / forex), regime lenses, and PE-cycle features are actually available to a brand-new trial user vs gated — the book assumes full access, but onboarding must match what a real new user can click.
- Confidence Overlay live behavior: verify the Green/Yellow/Red rating with 2-4 bullet reasons is actually rendered in the product and on which surfaces (Wave Viewer, reports), since the book presents it as a defined feature but it may be partially built.
- Universe coverage and resource keys: the book lists S&P 500, Nasdaq 100, Dow 30, Wilshire 5000, sectors, ETFs, futures, forex; confirm which of these are live (resource keys 0..16, crypto = 16) and which appendix commodity/futures instruments are actually loadable via the live deep-links.
- Current-year handling: the book notes the analysis drops/includes the in-progress year (the 'ACTIVE' flag) and that B&H may show one extra year due to Jan-1→Jan-1 completion. Verify how the live engine treats the current in-progress year in default scans (the free-report funnel note flags this as a known behavior to confirm).
- Pricing/tier context for onboarding CTAs: confirm current live price points and tier names (Analyst, Strategist, and the in-flight Navigator tier) against Stripe before any onboarding upgrade prompts, since config.py fallbacks are known-stale.


## === THEMATIC SECTIONS (full depth) ===

### The 100-Year Pattern — Methodology & Core Concepts: The Complete Conceptual Foundation of TradeWave

## 1. The One-Sentence Thesis

TradeWave exists to answer a single question: **"Is what the market is doing right now normal for this point in the calendar and the political/presidential cycle, or is it an outlier I should be cautious about?"** It answers that question by giving the user a near-century historical baseline (≈98 years of S&P 500 data) instead of a guess, a headline, or a narrative. Everything in the product — the Opportunity Table, the Wave Viewer, the Trend Chart, the Stats Table, the regime filters, the AI layer — serves that one job: convert market folklore into **measured probability with exact dates and percentages**.

The product's identity is captured in three repeated framings:
- "This is not a prediction book. It is a probability book. Markets do not owe us certainty."
- "The goal of this book and TradeWave is simple. It is to help you stop guessing in the dark."
- "TradeWave was built for measurement, not mythology... I wanted something that could look at decades of history, run the math, and show its work."

TradeWave is a **registered trademark of Tara Data Research LLC**; the author/founder is Afshin Moshrefi (medical-imaging, video-patent, and medical-AI background; built TradeWave to "test seasonality the way an engineer tests reality"). The foreword is by David M. Aferiat, co-founder of Trade Ideas LLC.

---

## 2. What a "Seasonal Pattern" Actually Is

A **seasonal pattern** is a recurring tendency in a market that aligns with specific times of the year, driven by consistent real-world behaviors. The book's hard insistence: these are **not magic and not a story — they are recurring human and institutional behaviors expressed through prices.** The concrete drivers cited repeatedly:

- Consumer/holiday spending (retail, year-end)
- Agricultural planting/harvest cycles
- Corporate fiscal-year budgeting, earnings/guidance windows
- Inventory cycles and supply chains
- Tax-driven flows and institutional rebalancing
- Energy demand tied to weather/travel (summer/cooling/driving season)
- Election-cycle policy timing and political incentives

**Key conceptual distinction — seasonality is historical behavior organized to be tradable, NOT prediction.** It answers: *"When has this tended to go up or down, how consistently, and across how many years?"* A pattern becomes a **decision tool** (not just "interesting") only when you can measure three things about a window:
1. **How OFTEN** it happened (hit rate / % profitable)
2. **How LARGE** the move tended to be (average/median gain)
3. **How MESSY** it gets when it fails (volatility, drawdown, outlier-dependence)

**Why seasonality is hidden:** "Seasonality is not hidden because nobody knows it exists. It is hidden because most traders cannot test it properly." Retail loses not to a conspiracy but to **structure / information asymmetry** — institutions run statistical studies across decades while retail decides on fragments (headlines, opinions, reactive tools). "Wall Street does not need a conspiracy to keep traders behind. The structure does it automatically."

### The "market as music" metaphor
Markets are not chaos; they have a repeating **"chord progression."** Day-to-day moves look like noise, but underneath are repeating patterns tied to real-world behavior, business timing, and policy cycles. "Seasonality is not a crystal ball. It is the market's chord progression. It gives you a framework you can test and verify." Once you recognize the rhythm, "you stop reacting and start anticipating. You stop trading emotion and start trading with context."

---

## 3. The "100-Year Pattern" Thesis (The Flagship Discovery)

The book's centerpiece and namesake is **The 100-Year Pattern**: a regime-conditioned S&P 500 seasonal window that has held for roughly 95 years across nearly a century of data. It is **anchored to September 27, 2026** as the start of the next cycle's window.

**Definition:** Filtering the S&P 500 specifically for **midterm-election (PE+2) years** reveals a long, cross-year bullish window:
- **Start: ~September 27 of a midterm year → End: ~July 18 of the following year** (≈295 days)
- Measured across **24 complete cycles (1930–2022)**: **19% average gain per cycle vs 4% buy-and-hold**
- **Profitable in 23 of 24 cycles = 96% win rate**
- The **single failure was 1930**, at the depth of the Great Depression
- Cumulative return figure cited: **5,045% cumulative vs 49% buy-and-hold cumulative**

**The critical methodological point:** this edge ONLY appears once you isolate the midterm regime — it disappears when you blend all years together. "In Chapter 7, the midterm-year filter did not create the 100-year pattern. It revealed it." Midterm years are "the messiest, most volatile, correction-prone year of the cycle, which is exactly why isolating them reveals patterns that disappear in blended data... this is the window where the market historically stops being messy."

**Modern-era validation (1985–2025):** the edge persists — seasonal timing ~12% avg annual return vs ~11% buy-and-hold, profitable in 83% of years; $10,000 grew to ~$650,000 seasonally vs ~$414,000 buy-and-hold. Modern market structure (ETFs, index flows, algorithms) did NOT erase the edge; institutional rebalancing/positioning cycles can even amplify seasonal flows.

**The honest caveat baked into the thesis:** "If this pattern fails in a meaningful way, it is not just a bad trade. It would be a major signal." A pattern breaking — especially one this durable — would itself signal recession or something worse (the Great Depression is the canonical example of stable rhythms breaking and staying broken).

---

## 4. The Long-Term "Every-Year" Seasonal Regime

Separate from the regime-conditioned 100-Year Pattern, the book documents a **consecutive-years (all-years) long-term seasonal structure** on the S&P 500 across 1928–2025:

- **Strong/in-season window: October 26 → September 3** (where most long-term compounding happens)
- **Weak window ("The Lost Summer Effect"): September 4 → October 25** (a 52-day stretch)
- **Compounding demonstration:** $10,000 (1928–2025) → **$3.9M full-year buy-and-hold vs $17.7M with seasonal timing** that sits out only those 52 weak days each year
- **Measured cost:** the Lost Summer window averages **about −1%** vs **about +9%** for optimized seasonal windows

This reframes "Sell in May" folklore: sitting out a repeatedly weak window reshapes the entire distribution of outcomes (how often/deep drawdowns are, how fast you recover), which compounds dramatically over decades. **"Seasonality is not 'September bad, November good.' That is meme-level thinking. The power is precision."**

---

## 5. The Presidential / Election Cycle (PE) — The Most Important Regime Filter

The single most differentiating concept in the 2026 edition is **regime-conditioned (cycle-aware) seasonality.** The U.S. four-year presidential cycle is the primary regime overlay because the U.S. is ~4% of world population but ~25% of global GDP, so its cycles propagate worldwide. It matters "not via political theory but as classification."

### The four cycle phases (TradeWave naming)
- **PE (PE+0):** Presidential Election year
- **PE+1:** Post-election year (year after the election)
- **PE+2:** **Midterm year** — the second year after a presidential election; the messiest, most volatile, correction-prone year. **2026 is a PE+2 year.** This is the focus of the book.
- **PE+3:** Pre-election year (year before the next election)

The PE+2 label **changes as the calendar year changes** — it is dynamic.

### Why regime filtering is the whole game
"Seasonality folklore is half-right: people measure the right phenomenon but mix the wrong years, so blended averages look random." The distinction TradeWave enforces is between **"a seasonal pattern exists"** and **"a seasonal pattern exists in the right regime."** Averaging all years together can **dilute a real edge OR manufacture a fake one.**

**"Sell in May" decomposed by year type** (24 cycles, 1930–2022) — the headline finding that "is the story in one sentence":
- Only **PE+2 is negative May–Oct (−34% cumulative)**; its Nov–Apr is +958%
- PE: +177% / +154% · PE+1: +40% / +32% · PE+3: +56% / +53%
- "Sell in May" is not a universal law — the weakness concentrates almost entirely in **midterm years.**

**Best single window per year type** (Optimal Dates, cumulative, avg gain vs buy-and-hold):
- PE: May 23–Jan 6, 683% / 9% (vs 417% / 8%)
- PE+1: Apr 7–Aug 2, 552% / 9% (vs 217% / 7%)
- PE+2: Sep 27–Jan 6, 354% / 7% (vs 49% / 4%)
- PE+3: Jan 2–Jul 20, 1,295% / 12% (vs 1,220% / 12%)

PE+1 also carries its own strong-window edge: April–August strength (window 04-05 to 08-02), higher 77% of the time over 98 years, 100% over the last 50 years, avg 7.46% — directly contradicting "Sell in May" in PE+1 years.

### A regime is a LENS, not a fact
"A regime is not what the market 'is.' A regime is the lens you use to measure it. When you change the lens, you do not change the market. You change what becomes visible." This is the core mental move the user must internalize.

### The two controls a user must set deliberately
1. **Control 1 — Regime lens:** consecutive years vs a specific PE-cycle year type (PE/PE+1/PE+2/PE+3).
2. **Control 2 — Sample depth:** how many samples inside that lens.

**The ambiguity trap:** "last 10 years" is ambiguous — 10 consecutive calendar years vs 10 PE+2 years (which span ~40 years, because midterms occur once every four years). **"We are trading breadth for relevance."** "'8 years' and '8 PE2 years' are not the same dataset." This is why the **Years dropdown maxes at ~61 in consecutive mode but far fewer (e.g. 15) in cycle mode** — different datasets, different meaning of "Years."

### Regime flip = the signal
When the consecutive lens and the cycle (PE+2) lens **disagree** for the same window, **that disagreement is itself the signal.** Worked example: S&P 500 stocks, Jan 5 2026, 5–60 day horizon — Consecutive 10-year lens = 85 opportunities, 79 Longs, 6 Shorts, 93% bullish; PE+2 10-year lens = 30 opportunities, 5 Longs, 25 Shorts, 83% bearish. The **dominant regime** is "the personality explaining most of the behavior — more consistent, less internally conflicted, less like a coin flip." Used as a **regime detector, not a trading signal.**

---

## 6. The Statistical / Edge Basis — Every Metric Defined

TradeWave's credibility rests on showing its work — "it avoids black boxes." The metrics:

| Metric | Definition |
|---|---|
| **Win Rate / % Profitable / Success Rate** | Share of sampled years the window finished positive (for a long) or negative (for a short). Expressed as a frequency "X of Y years" (e.g. 33 of 41) to make it a historical fact, not a forecast. |
| **AvgP / Avg Gain / Average Return** | Mean return of the window across the sample. Useful but **distortable by outliers**. |
| **Median Gain / Median Return** | The middle return after sorting all years — "typical" behavior without one crazy year dominating. A key sanity-check against a single hero year. |
| **Std Dev** | Volatility / noisiness of the window. |
| **SR / Sharpe Ratio** | Risk-adjusted return — return relative to variability. Rewards cleaner, smoother, more stable patterns. **But it only looks at the final result and ignores the path** — a trade that finished +3% but reached +10% looks identical to one that finished +3% and never went higher. The UI typically shows **two Sharpe values** (pattern vs annualized/second figure). Small samples can flatter it. |
| **MFE (Maximum Favorable Excursion)** | How far a trade moved in your favor at its BEST point inside the window (e.g. MFE 12% even if you only captured 5%). Answers "How good can it get?" Used to set targets and option strikes. |
| **MAE (Maximum Adverse Excursion)** | How far a trade moved against you at its WORST point — the drawdown / "heat" you had to sit through. Answers "How bad can it get?" Used to set stops, position size, and option-strike invalidation. |
| **TWA (TradeWave Average)** | TradeWave's average-outcome metric **computed using MFE** — reflects favorable movement that occurred DURING the window, not only where it ended. |
| **TWR / TWA (TradeWave Ratio)** | **TradeWave's signature pattern-quality score.** Sharpe-like (return relative to variability) but **also incorporates MFE**. Designed to surface windows that move strongly in the right direction along the PATH, even if they did not finish at the peak — these get filtered out too early by Sharpe. Higher TWR = more consistent, efficient pattern. **Complements, does not replace, Sharpe.** Common filter thresholds: **TWR ≥ 1.5 for Consecutive studies, TWR ≥ 1.0 for PE-cycle studies** (lower because the 4-year cycle yields fewer data points). |
| **Cumulative Ret** | Compounded result of repeatedly trading the window across history. Shown as % or as a **Cumulative Return Multiplier** (e.g. DIS 35x, AAPL 40x, ADI 38x, AMD 6,220x). |
| **B&H (Buy & Hold)** | The benchmark: continuously invested **Jan 1 → Jan 1 of the next year, repeated across years** — the "always in the market" comparison. Every seasonal window is judged against it; a window "earns its keep" only when Cumulative Ret > B&H. (Note: B&H may show one extra year because Jan-1-to-Jan-1 can complete earlier than a seasonal window.) |
| **Trend Long / Trend Short** | Quick directional-tendency readouts (e.g. Trend Long 80 / Trend Short 20) summarizing how the broader trend behaved around the window. |

### Why MFE/MAE and TWR exist (the path matters)
The deepest statistical insight in the book: **a window's average return can lie.** A strong average can be driven by a few outlier years, a volatile/punishing path, or noise the average hides. Sharpe captures smoothness but throws away path information. **MFE/MAE describe the experience inside the window**, and **TWR rewards strong-but-not-smooth opportunities** that traditional end-of-trade metrics discard. "It tells you whether a pattern tends to pay you and whether it tends to punish you along the way." For options especially, the **path** (not just final return) decides whether a trade survives.

### Sample-size gating
**Win% ≥ 80% is flagged green as "exceptional"** — BUT very small occurrence (Opp) counts are NOT statistically meaningful even at a high rate (e.g. a short side showing 91% on only 11 opps, or 100% on 2 opps, is shown but understood as fragile). Sample size gates significance. Sharpe is the "not luck" check — it confirms a result isn't carried by one or two lucky years.

---

## 7. Why It Works (The Causal/Structural Basis)

1. **Real recurring drivers:** earnings calendars, fiscal quarters, seasonal demand, supply chains, holidays, tax flows, energy/weather cycles, and election-cycle policy timing are genuinely periodic, so the price effects repeat rather than being random.
2. **Edges compound over long timeframes;** durable edges come from what is measured and repeatable, not what is loud, recent, or emotionally triggering.
3. **Structure beats most traders automatically** (information asymmetry), so a measured baseline is a real edge.
4. **Regime conditioning removes the dilution** that makes seasonality look like noise — isolating like-years reveals structure that blending destroys.
5. **Modern market structure reinforces rather than erases** seasonal flows (rebalancing, risk budgets, positioning cycles).

---

## 8. The Three Analytical Lenses (Where Seasonality Fits)

Seasonality is **one of three complementary lenses**, not a replacement:

| Lens | Question | Focus | Best use |
|---|---|---|---|
| **Technical analysis (the Price Lens)** | How do I execute? | Price & volume, trends, momentum | Timing entries/exits over days–weeks; managing risk. Premise: price contains info; shared signals self-fulfill. Works best with healthy liquidity, worst in macro-shock/single-narrative regimes. Failure mode: "signal hunting" — by the time indicators cluster into a "dashboard," the obvious move already happened. |
| **Fundamental analysis (the Business Lens)** | What is it worth? | Earnings, revenue, margins, balance sheet | Selecting strong long-term holdings. Slow-moving while price is fast; markets can ignore fundamentals for long stretches. |
| **Seasonal analysis (the Calendar Advantage)** | WHEN are the odds historically favorable? | Recurring calendar/cycle behavior | The most underused lens because most traders lack the tooling to test it. Answers the timing question the other two miss. |

**The integrated workflow:** "Fundamentals decide WHAT deserves attention, seasonality decides WHEN the odds are historically favorable, technicals EXECUTE and manage risk." And the guardrail: "Technical analysis without context can become random signal hunting. Fundamentals without timing can become dead money. Seasonality without discipline can become overconfidence."

**Seasonality sets the BIAS, not the TRIGGER:** a seasonal pattern is a high-probability tendency, not a timing signal — you still confirm the entry with current price action (trend strength, 50-day moving average). If technicals and seasonality strongly conflict, pass or reduce size.

---

## 9. Risk Philosophy

- **The four trade outcomes:** a big win, a small win, or a controlled loss are all acceptable; **the one unacceptable outcome is the big loss.** Sync strategy with structure to avoid it.
- **Seasonality is probability, not protection.** The NVDA case is the canonical lesson: a historically bullish 20-year window (18 winners / 2 losers) took a 2025 news shock that pushed price **−23.16% against the position at its worst point (MAE)** yet finished only **−5.22%**. Position sizing and risk tolerance still matter because the edge is the distribution, not a guarantee on any single trade.
- **Define the exit BEFORE entering, every time.** Every position needs a profit target (from MFE), an invalidation point (from MAE — "the line that says this trade is wrong"), and a planned time horizon. "Lazy traders execute exits; they do not improvise them."
- **Diversification = "the quiet superpower"** across three independent axes: **timeframes** (short tactical windows vs long compounding/dividend windows), **sectors** (cyclical / defensive / commodity-sensitive), and **asset classes** (so you can avoid forcing trades in the wrong environment). "A portfolio that only works when one sector leads is a bet, not a plan."
- **The goal is not to eliminate uncertainty; it is to eliminate unforced errors.**
- **A perfect success rate can hide interim drawdowns.** Long windows are best treated as a **bias filter**, then managed with normal risk rules — not held blindly.
- **Standing down is a position.** "Doing nothing is a position. Keep this boring, boring works."

---

## 10. The Philosophy & The Caveats (The Honest Core)

The book is deliberately built on **measurement over interpretation**, born from the author's cautionary Elliott Wave story: a lucky ~$700K 2008 win that bled away chasing perpetual-bear "doomcast" forecasts. The lessons:

- **"Any framework that cannot be tested and verified will eventually turn into belief instead of analysis."** This is the thesis of the whole book.
- Elliott Wave's idea (crowd psychology repeating) is valid, but real-time labeling is subjective — two skilled analysts produce two confident, contradictory counts, and "extensions" become a universal escape hatch so nothing is ever wrong. "It was not built to predict. It was built to measure."
- **"A broken clock is right twice a day."** Being right about a correction is not a usable framework. "The key problem is not that they are always wrong. The key problem is what they do to you when they are right. They make you believe the story again."
- **Confidence ≠ intelligence.** "The market does not reward confidence. It rewards accuracy."
- **Curve-fitting vs alignment** (the credibility line): **Alignment** = shifting a window's start/end by SMALL amounts to begin measuring at the visible "pivot zone" where behavior actually changes (legitimate). **Curve-fitting** = "torturing the data until it confesses" by searching the whole calendar for the best Sharpe (illegitimate). "That is not curve fitting. That is alignment."
- **Backtesting is not about finding what 'always works' (it doesn't exist).** It answers two questions: does the edge show up consistently enough to be useful, and is it stable across lookbacks/regimes or fragile? A pattern strong over 10 years can be mediocre over 20 and strong again in the modern era — "that flexibility is the whole point. It is also the trap."
- **Math first, then AI.** The product is two layers: a **deterministic Engine** (the math; produces auditable, reproducible numbers) and a separate **AI Research Agent** layer (interprets/summarizes/contextualizes). The governing rule: **"TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics."** And: **"AI is not the edge. The edge is the edge. AI just helps you find it faster, understand it better, and apply it with fewer mistakes."**
- **"No forecasting. No predictions. Just context."** Historical context lets you avoid panicking on a scary move by checking whether it is historically normal (the August 2024 S&P case study: a sharp drop that history showed was normal for that cycle condition, and the market rebounded).
- **TradeWave is a decision-framework / thinking tool, not a black box or signal robot.** "A tool should not replace thinking. It should improve thinking." "This book was not about selling you a dream. It was about handing you a flashlight in a dark room."

---

## 11. The Layered Workflow Model (How the Concepts Combine)

The conceptual payload reduces to a **layered process**, not a single signal:
1. **Seasonality picks the WHEN** (the calendar window).
2. **TWR filters pattern QUALITY** (≥1.5 consecutive / ≥1.0 PE-cycle).
3. **Regime alignment picks the DIRECTION** (long in bullish regimes, short in bearish; toggle Consecutive vs PE+2 to detect the dominant regime).
4. **Technical confirmation improves the ENTRY** (trend + 50-day MA inside the window).

This exists to kill two specific failure modes: **"right pattern, wrong environment"** and **"right window, wrong entry."** The headline win rates in the appendices are deliberately a conservative **"baseline floor"** (they include mismatches a disciplined trader would avoid); the filters lift outcomes above that floor.

The validation sub-loop ("Scan then Lab"): the **Opportunity Table is triage (finds candidates) — NOT an approved trade.** Every candidate is validated in the Wave Viewer in a fixed sequence: **(1) Profit Bar Chart** — consistent or a few outliers? **(2) Trend Chart** — is the path tradable or does it whip you out? **(3) Stats Table** — do the metrics confirm a reliable, low-torture tendency? Act only when all three align. "Do not confuse 'ranked highly' with 'approved trade.'"

---

## 12. Canonical Glossary (Methodology Terms)

- **The 100-Year Pattern** — the flagship PE+2 (midterm) S&P 500 seasonal window, ~Sep 27 → ~Jul 18 (≈295 days), profitable in 23 of 24 cycles (96%), failing only in 1930; next cycle begins Sep 27, 2026.
- **Seasonal pattern / Pattern** — a recurring calendar tendency; in TradeWave, uniquely defined by **symbol + start date + days held + year set + direction**. Change any one and it is a different pattern.
- **Seasonal window** — plain English: "buy here, hold this many days, then exit" (a start date + a holding length).
- **Regime** — the LENS/sample you measure with (consecutive vs a PE-cycle year type), not what the market "is."
- **Consecutive mode** — the last N calendar years in a row; the baseline "normal."
- **Presidential Election Cycle / PE cycle** — 4-year market segmentation: PE (election), PE+1 (post), PE+2 (midterm), PE+3 (pre-election).
- **PE+2 / midterm year** — second year after a presidential election; most volatile/correction-prone; 2026's regime; the book's focus.
- **Year Set / Lookback (Years)** — the exact set of historical years included. "PE+2:5" or "PE2-8" = N midterm sample years, NOT N consecutive calendar years.
- **"10 of 10" wins** — 10 QUALIFYING years within the chosen year set (often midterm slices), **never** 10 consecutive years. (Classic misread the book explicitly warns against.)
- **Regime flip** — when toggling the lens changes the opportunity set from broadly bullish to broadly bearish (or vice versa) for the same horizon.
- **Dominant regime** — the lens where behavior is clearer, more consistent, "more like a personality, less like a coin flip."
- **Pivot zone** — where a seasonal average bends then turns; where a real move begins.
- **Peak zone** — the natural high point of a seasonal move; holding past it gives back gains (demonstrated: BX 17-day peak window Sharpe 2.18 / 100% / +102% CumRet collapses to Sharpe −0.01 / 60% / −2% when widened to 86 days).
- **Alignment vs Curve-fitting** — small honest shifts to the pivot zone vs searching the whole calendar for the best Sharpe.
- **Win Rate / % Profitable / Success Rate; AvgP / Avg Gain; Median Gain; Std Dev; Sharpe (SR); MFE; MAE; TWA (TradeWave Average); TWR/TWA (TradeWave Ratio); Cumulative Ret; Cumulative Return Multiplier; B&H** — all defined in §6.
- **Reverse Date Range** — flips a window to its complementary (out-of-season / worst) period; on desktop, top-right select box in the Wave Viewer.
- **Lost Summer Effect** — the weak ~52-day all-years window (Sep 4 → Oct 25), avg ≈ −1%.
- **Best Six Months** — Yale-Hirsch-popularized framing of "Sell in May"; the market's stronger stretch historically falls outside summer.
- **Baseline (floor) repeatability** — pattern performance with NO regime/timing conditioning (deliberately includes mismatches a real trader would avoid); the filters are designed to beat it.
- **Confidence Overlay** — the AI reliability "second opinion" rating an edge's **stability and misuse-risk** (Green = solid edge / consistent / drawdown matches reward; Yellow = mixed reliability or cautionary drawdowns; Red = fragile/outlier-driven/too noisy), always with 2–4 bullet reasons, "Not vibes. Not a black box." Distinct from the historical edge itself.
- **TradeWave Research** — the AI analyst/chatbot layer that reads outputs and answers plain-English questions (drawdowns by year, PE+2 vs all years, reverse-window comparison, early-vs-late return distribution), cutting analysis "from thirty minutes to three." Never invents statistics.

---

## 13. Worked Examples That Anchor the Concepts

- **NVDA (probability ≠ protection):** Jan window, 20-yr, 18W/2L; 2025 shock MAE −23.16%, finished −5.22%. Also a documented PE+2 short weakness (Mar 21–Aug 2, ~30% avg, 100% over 6 midterm years, Sharpe 0.95) — "the most valuable company on the planet has a recurring weak spot... history suggests the odds are higher it happens during this window, in this cycle type, than at a random time."
- **AVGO (panic-exit lesson):** 2024 live year deep red while history was strongly green; Trend Chart context was right, position recovered (10-29→11-27 Sharpe 1.06, 91% profitable, CumRet 116%).
- **CAH (clean tactical example):** 10-yr PE+2, Feb 5–Mar 17 (41 days), 100% profitable, 142% cumulative, Sharpe 2.64, Trend Long 100/Short 0.
- **AAPL long-term seasonal timing:** buy-and-hold 216,221%; excluding September → 3,765,269%; optimized exclusion (Sep 5–Oct 3) → 8,591,518% (~17x baseline); Best-Window Oct 3–Sep 4 multiplier 40x.
- **AMD (multiplier extreme):** Best Window Oct-27→May-29, 80% (33/41), 6,220x cumulative vs 30% full-year buy-and-hold avg gain.
- **Sharpe-vs-hit-rate contrast:** AMAT 20% avg / 0.77 Sharpe = rough ride; BIIB 16% avg / 1.58 Sharpe = repeatable drift. High hit rate gives direction; Sharpe tells you the smoothness and which tactics to use (tight stops vs staged/hedged entries).
- **AXP (highest-quality short window):** 100% (10/10), Sharpe 2.52, 19 days — "perfect wins with an exceptional Sharpe in a short window."

These are illustrative — every ticker has its own optimal window: "the value is in testing the rule systematically, not memorizing a date range." All figures are historical, simplified, excluding taxes/frictions; seasonal in/out timing has real tax consequences, so the overlays are most attractive in tax-advantaged accounts (e.g. Roth IRA) or expressed via covered calls.

### The Complete TradeWave Capability Surface: Every Feature, Control, and How They Fit Together

## 0. The Mental Model That Organizes Everything

TradeWave is a **seasonal-pattern measurement engine** plus an interpretation layer on top of it. The whole product is built around one disciplined loop the book repeats verbatim:

> **SCAN → VALIDATE → ORGANIZE → ACT** — "Scan then Lab."

- The **Opportunity Table** is the **Scanner** (triage: find and rank candidates fast across a universe).
- The **Wave Viewer** is the **Lab** (validate the evidence, the path, and the risk of a single candidate).
- The **Portfolio Manager** is the **operational library** (save the full configuration, track, report, share, set reminders).
- The **AI layer** (TradeWave Research + Confidence Overlay) only *reads and explains* the numbers — it never invents them.

Two architectural facts gate the entire product:
1. **Two-layer architecture.** Layer 1 = the deterministic **Engine** (the math; processes "on the order of a trillion data points"; auditable, "shows its work," avoids black boxes). Layer 2 = the **Research Agent (AI)** that interprets. The hard rule: *"TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics."*
2. **A "pattern" is a unit defined by FIVE things together:** **symbol + start date + days held + year set + direction.** Change any one and it is a *different pattern entirely*. Every screen in TradeWave is operating on this unit.

---

## 1. THE OPPORTUNITY TABLE (the Scanner / "institutional-grade research scanner")

**What it is:** The ranked output of the analytics engine. Not a human-made list — it scans thousands of securities × many seasonal windows × many year samples × multiple regimes × multiple quality metrics, then surfaces and ranks the windows that historically mattered for the chosen start date. It inverts the retail habit ("pick a stock, then find a reason") by starting with data.

**Its role is TRIAGE, not a decision.** "Ranked highly" ≠ "approved trade." It finds candidates; you must still validate each in the Wave Viewer.

### Core controls (the table's top control bar)
| Control | What it does / is FOR |
|---|---|
| **Universe selector** (top-right dropdown) | Picks the scan universe: `S&P 500 STOCKS`, `Nasdaq 100`, `DOW 30 STOCKS`, `Wilshire 5000`, a sector, ETFs, futures, forex. Defines *what* you scan. |
| **Start Date: Month dropdown + Day dropdown** (e.g. `January` + `13`) | The table scans only for patterns that START on this month/day. |
| **Years dropdown** (sample size) | How many historical years/cycles feed the measurement. Consecutive mode max observed ≈ **61 years**; in cycle mode the max shrinks dramatically (e.g. 15) because you're limited by how many cycle samples exist. Guidance: 5y = recent regimes/new companies, 10y = balanced, 20y = stable, 40–60y+ = structural seasonality. |
| **PE+2 checkbox / Regime toggle** | THE master dial. Unchecked = **Consecutive mode** (last N calendar years). Checked = **Presidential-cycle mode** (scan ONLY years matching the current election-cycle regime; 2026 = midterm = PE+2). "Not a cosmetic checkbox — a switch that changes the dataset." The label changes with the calendar year. |
| **Consistency / hit-rate selector** (e.g. `9 of 10 years`) | Requires the tendency to have held in at least N of M sampled years. |
| **Filter field** (text box) | A semicolon-separated, NO-SPACES filter string combining a day-range and metric thresholds. |
| **Column-header sorting** | Click `SR` or `TWR` to sort by the quality you care about. Direction is read off `DIR` (sorting handles it since patterns are usually all-Long or all-Short). |
| **tooltips ON/OFF toggle** (top-left) | Turns interface tooltips on/off. |

### Columns
`Date · Ticker · Days (window length) · DIR (Long/Short) · AvgP (average profit) · A% (likely accuracy / hit-rate) · SR (Sharpe Ratio) · TWA (TradeWave Average) · TWR (TradeWave Ratio)`

### Filter-string syntax (exact)
- No spaces; conditions joined by `;`. First token is a **day-range**, then **metric thresholds**.
- `2-24;sr>1.0;twr>1.50` → short-duration, higher-quality candidates.
- `10-90;twa>10;twr>1.40` → medium-duration patterns with strong TradeWave movement.
- `2-24;sr>1.30;twr>1.50` → high-quality short patterns, then sort by SR.

### Footer
Summarizes the result set, e.g. `236 opportunities, 226 Longs, 18 Shorts, 95%, no filter` or `13 opportunities, 13 Longs, 0 Shorts, 100%`.

### A second, advanced use: the Opportunity Table as a REGIME DETECTOR
Hold time-of-year, sample depth, and horizon (e.g. `filter by 5-60`) constant; toggle **only** the regime lens; read whether the longs/shorts/percent stays bullish or **flips**. A "regime flip" (e.g. Jan 5 2026 S&P 500, 5–60 day: Consecutive 10-Year = 85 opps / 79 Longs / 6 Shorts / **93% bullish** vs PE+2 10-Year = 30 opps / 5 Longs / 25 Shorts / **83% bearish**) tells you what *kind* of market you're measuring — "not a trading signal." When two lenses disagree, that disagreement is the signal, and the clearer/more-consistent lens is the **dominant regime** you should refine inside.

---

## 2. THE WAVE VIEWER (the Lab / validation surface)

**What it is:** The per-instrument analysis screen that loads ONE pattern setup and shows how that exact window performed across history, plus the stats that tell you whether it's real or a lucky coincidence. You click into it from an Opportunity Table row. It brings a pattern "to life."

### 2.1 Wave Viewer toolbar (the configuration bar)
Reads back the loaded pattern as a label like `20-Year NVDA 01-22 to 02-18` or `10-Year CAH 02-05 to 03-17`, with editable controls:
- **Symbol field** (ticker, e.g. NVDA / CAH / BX).
- **As-of / anchor date field** (e.g. `2026-02-05`) — the current-year reference the window projects from.
- **Date-range window control** (`MM-DD to MM-DD`, e.g. `02-05 to 03-17`) — sets the seasonal start/end.
- **Days / window-length field** (e.g. `41 days`, `53 days`, `17 days`, `86 days`, `210 days`) — the holding period. Widening it past the seasonal peak *visibly degrades the stats* (the core overstaying lesson).
- **Years field** (e.g. `20 years`, `10 years`).
- **Regime dropdown** — selects the historical sample: `consecutive`, `PE Years`, `PE+1 Years`, `PE+2 Years`, `PE+3 Years`. Lets you re-run the exact same ticker/window under a different sample.
- **MFE checkbox** and **MAE checkbox** — overlay favorable (green) / adverse (pink-red) excursion shading on the year bars.
- **"Months & Qtrs"** grouping/aggregation selector for the time axis.
- **"Jan-Dec"** full-year toggle on the Trend Chart header (seasonal-window view ↔ full-year view).
- **Help (?) icon.**
- **Reverse Date Range** control (top-right select box, desktop only) — see §3.4.
- **Save (+) icon** — saves the current pattern config into the Portfolio Manager.

### 2.2 The THREE validation views (used in a fixed sequence)
The prescribed order: **Profit Bar Chart → Trend Chart → Stats Table.** All three are **regime-aware** (they recompute for Consecutive vs PE+2, so the same row legitimately looks different per regime — by design).

**(A) Profit Bar Chart / Year Bars** — distribution & consistency.
One vertical bar per analyzed year showing the underlying price return inside the window. **Green/up = price rose; red/down = price fell; bar height = raw price-return magnitude. A green/up year wins for a Long, while a red/down year wins for a Short.** With MFE/MAE on, each bar splits into a solid segment (realized/MFE) plus a lighter cap (MFE upside above the close) and salmon/pink bars below zero (MAE drawdown). Purpose: "Seasonality is not one number — it is a distribution." It's the fastest way to see whether the edge is broad-based or carried by one **"hero year"** outlier, and whether losing years are small/contained.

**(B) Trend Chart** — the typical PATH (tradability & timing), NOT the ending and NOT a prediction.
Compresses many overlapping yearly price paths into a single **most-typical path** through the year, with the seasonal window **shaded/highlighted** as a band and **left/right (< >) navigation arrows** to step through years. Labeled by sample, e.g. `20-Year Trend Chart for Northrop Grumman`, `8 PE+2 Year Trend Chart for Biogen Inc`, `25 Year Trend Chart for Tyler Technologies`. It marks **recurring weak zones** (red-shaded danger stretches, e.g. ADI's late-July-to-mid-October weak window) and the **pivot zone** where a move actually begins. Two concrete behavioral uses: (1) **prevent panic-exits** — check the path before bailing on a normal red pullback (the AVGO case: it was historically green and recovered); (2) **prevent overstaying** — exit as seasonal strength fades near/after the peak. Used for **window alignment** (shifting the start to the pivot zone, e.g. BA Jan-23→Jan-27 raised Sharpe 0.8→1.14 and Avg Gain 4.54%→5.85%) — which is honest "alignment," NOT "curve-fitting" (searching the whole calendar for the best Sharpe).

**(C) Stats Table** — quantified reliability & risk. "Charts help you see; the Stats Table helps you measure."
Organized into labeled blue-headed panels:
- **Wave Detail:** Symbol, Trade Direction (long/short), Date Range, Calendar Days Hold.
- **Wave Profit Loss:** Num Winners, Num Losers, Cumulative Return, **S&P 500 Buy & Hold** (benchmark).
- **Wave Stats:** Avg Loss, Avg Gain, Median Gain, Std Dev.
- **Wave Info:** Percent Profitable, Sharpe Ratio, **Trend Long**, **Trend Short**, and **Trend Alignment**. Trend Long asks whether roughly the last one to two weeks of movement has been upward; Trend Short asks whether it has been downward. Alignment selects the score matching the loaded seasonal direction: Aligned = recent movement confirms it, Against = recent movement has not been moving strongly in it, Neutral = no clear confirmation. This is current-momentum context, not part of the historical win rate or a forecast; a missing provider reading displays as Unavailable, never as a real zero.
- **General:** Years Filter, Securities Group, Last Price, `TradeWave.AI`, plus an **ACTIVE flag** when the analysis includes the current in-progress year.
- A small **Cumulative Return mini-chart** plotting the ticker vs the S&P 500 (red line).

### 2.3 The per-window stats strip (under the Trend Chart on pattern cards)
A condensed horizontal readout used throughout the appendices: **Sharpe Ratio (shown as two values — pattern vs a second/annualized figure), Avg Gain %, % Profitable, Cumulative Ret %, and B&H [TICKER] %** (buy-and-hold of the same symbol for direct comparison). This is the "judge it at a glance" surface (e.g. TER short: Cumulative Ret 247% vs B&H TER −74%).

---

## 3. THE TWO MASTER DIALS + KEY TECHNIQUES

### 3.1 Dial 1 — Years / Sample Size (Control 2: "how deep is the sample")
Small N catches recent/changing regimes but adds randomness; large N finds what's structurally true. **Crucially, "Years" means different things per regime:** in Consecutive mode it's calendar years (max ~61); in cycle mode it's **cycle samples** (e.g. "last 10 PE+2 years" spans ~40 calendar years because midterms occur once every four years). You trade breadth for relevance. **"'8 years' and '8 PE2 years' are not the same dataset."**

### 3.2 Dial 2 — Regime / Election-Cycle Filter (Control 1: "which lens")
The **Presidential-cycle classifier** splits all history into four year types — **PE** (election year), **PE+1** (post-election), **PE+2** (midterm — the messiest/most volatile, the book's focus, =2026), **PE+3** (pre-election). Available as the Opportunity Table PE+2 checkbox and the Wave Viewer regime dropdown. The filter *changes the backtest universe*, not the narrative. "A regime is not what the market is — it is the lens you use to measure it. Change the lens, you change what becomes visible." The midterm filter "did not create the 100-year pattern; it revealed it." **Misread warning:** "10 of 10" in a PE+2 study means 10 qualifying *cycle* years, NOT 10 consecutive calendar years.

### 3.3 The TradeWave proprietary metrics (built from MFE)
- **MFE — Maximum Favorable Excursion:** how far a trade moved in your favor at its best point inside the window ("How good can it get?"). Used to set profit targets and option strikes.
- **MAE — Maximum Adverse Excursion:** how far it moved against you at its worst point — the drawdown / "heat" you had to sit through ("How bad can it get?"). Used to set stops, position size, and invalidation.
- **TWA — TradeWave Average:** average-outcome metric computed using MFE, reflecting favorable movement *during* the window, not just where it ended.
- **TWR — TradeWave Ratio (a.k.a. TradeWave Rating / Win Ratio / TW Ratio):** a Sharpe-like pattern-quality score built on the Sharpe Ratio but **incorporating MFE**, so it surfaces windows with strong favorable movement along the path that smoothness-only metrics (Sharpe) would filter out too early. Higher TWR = more consistent, efficient pattern. Used as a quality **filter threshold** (Consecutive studies use **TWR ≥ 1.5**; PE-cycle studies use a lower **TWR ≥ 1.0** because the 4-year cycle yields fewer data points).
- **Sharpe Ratio (SR):** the traditional risk-adjusted lens — rewards smooth/clean patterns but only looks at the final result; a "not-luck" check. The book pairs it with Win Rate: high hit rate + low Sharpe = real but lumpy/choppy edge (manage with staged/hedged entries); high Sharpe = repeatable smooth drift.

### 3.4 Reverse Date Range
A Wave Viewer feature (top-right select box, desktop only) that **flips the currently loaded window to its complementary/inverse period** — turning a strong "best window" into the weak "worst window" you should avoid, or vice versa. Core to the long-term workflow: find a visibly weak stretch on the Trend Chart, highlight it, then **Reverse Date Range** to reveal the complementary strong window; validate via Cumulative Ret vs B&H. Appendix C ships only the Best Window + Buy & Hold links and instructs "to see the worst window, load this in TradeWave and click Reverse Date Range."

### 3.5 Date Range Presets
Shortcut selector for common windows — **Q1, 2nd/3rd/4th Qtr, Spring, Summer, Buy & Hold**, and individual months (January–December). Surfaced via the "Months & Qtrs" dropdown to speed exploration and to choose which window to exclude/include.

### 3.6 Buy & Hold Analysis (the baseline)
A dedicated long-term view computing a security's unfiltered cumulative return over a chosen timeframe, used as the honest benchmark. **TradeWave's definition: continuously invested Jan-1 to Jan-1 of the next year, repeated across years** ("always in the market"). Surfaces Cumulative Return, Year-by-Year Trends (green/red bars), and S&P 500 overlay. Caveat: Jan-1→Jan-1 can complete a year earlier than a seasonal window, so B&H may show one extra year. (AAPL examples: 216,221% full-year baseline → 3,765,269% excluding September → 8,591,518% optimized hold Oct-3→Sep-4.)

### 3.7 Optimal Dates / Best Seasonal Hold Window output
TradeWave returns the precise start/end of the strongest window for a given setup (e.g. `Sep 27 – Jul 18`, `May 23 – Jan 6`), with a headline **Cumulative Return Multiplier** for long-term holds (DIS 35x, AAPL 40x, ADI 38x, AMD 6,220x, RTX 4x). The "best window earns its keep when its Cumulative Ret > Buy & Hold."

---

## 4. THE PORTFOLIO MANAGER (the operational library)

**What it is:** Where seasonal research stops being disposable charts and becomes a reproducible, trackable, shareable process. Accessed via its own tab. The 2026 upgrade made it central.

**Save Pattern saves the CONFIGURATION, not a chart image:** entry date, exit date, direction, days-in-window, **Years/lookback setting**, group, tags, notes. This is what makes research reproducible — you can recall the exact study later and get the same result ("no guessing 'did I use 10 or 14 lookback years, consecutive or election-cycle?'").

### Table columns
checkbox · **Entry Date · Exit Date · Days · Ticker · DIR · SR · Years · Group** · then per-row action icons · **# (shares) · $ (invested amount) · % (live change)**.

### The 2026 dual-format Years column
- A plain number = **consecutive** lookback (e.g. `20` = last 20 consecutive years).
- `PE2-N` = **election-cycle** lookback (e.g. `PE2-8` = last 8 PE+2 / midterm-year occurrences; also `PE2-10`, `PE2-11`). These are genuinely different datasets, so the lookback choice is part of the edge and must be recorded.

### Header quota
`Saved Patterns 1382 / Remaining 618` (implies a ~2000 saved-pattern cap).

### Per-row action toolbar (the 7-step workflow)
1. **Recall/refresh icon** — reload the exact saved config back into the Wave Viewer instantly.
2. **Report icon** — generate a Custom TradeWave Report.
3. **Calendar icon** — push the pattern's entry/exit window + an ahead-of-start reminder to your calendar (Calendar Notifications).
4. **Delete (trash) icon** — remove patterns that no longer meet criteria.
5. **# column** — enter number of shares (virtual position sizing).
6. **$ column** — enter invested amount.
7. **% column** — live % change of the pattern as the year unfolds vs history.

### Virtual positions
A saved pattern tracked live (shares, invested $, live %) so you observe whether the current year is **normal-or-deviating** vs the historical sample — "for CONTEXT, not prediction."

### Multiple portfolios & supporting structures
- **Multiple named portfolios** by theme (dropdown shows e.g. `100-Year Patte...`): short-term trades, swing windows, index/sector ideas, election-cycle setups, paper-tracked (not-yet-risked) strategies.
- **Notes field** per pattern = a trading journal (why saved, what would invalidate it, desired confirmation, live-vs-paper flag).
- **Securities Group (Watchlist)** — a saved list of symbols you follow, to focus analysis on names you care about.
- **Portfolio summary footer** — Security Purchase Price, # Shares, Total Current Value, Security Last Price, Total % Gain or Loss across the portfolio.

---

## 5. REPORTS & SHARING (incl. the financial-advisor workflow — Appendix E)

### Custom TradeWave Report
Generated from a saved pattern (report icon). A **static, self-contained, link-shareable, interactive** public page containing:
- A header summary + descriptive paragraph (e.g. `20-Year Custom TradeWave Report Apple (AAPL) 2025-03-07 to 2025-08-17`, Report Date).
- A **"[Ticker] TradeWave Opportunity Key Information"** stats block (Symbol, Trade Direction, Date Range, Days Hold, History Years, Securities Group, Num Winners/Losers, Percent Profitable, Biggest Winner, Avg Loss/Gain, Median Gain, Std Dev, Cumulative Return, Sharpe Ratio, Trend Long/Short).
- A **Gain/Loss Bar Chart** (green per-year bars).
- A **Trend Chart** (average path during the window).
- A **"Load on Wave Viewer"** link so recipients can *interact with*, not just view, the exact pattern.
- **Share icons** at the top: email, Facebook, X/Twitter, Reddit, LinkedIn, StockTwits, Gmail, more, plus **copy-URL**.
- Optional **downloads**: chart images as **PNG**, raw data as **CSV** (for an advisor's own analysis).
- Static = "always shows exactly what you saw, even months or years later."

### Advisor share flow (Appendix E, step-by-step)
Wave Viewer **+** to save → open **Portfolio Manager** tab → click the **report icon** → share via email icon / social / copy-URL → optionally attach PNG + CSV → use the email template subject `Seasonal Pattern Review – [Ticker] [Date Range]`.

### Print-to-app deep links / QR codes
Every printed pattern in Appendices B/C/D carries a clickable **"Load/Analyze [TICKER] [Date Range] on TradeWave"** deep-link and a scannable **QR code** that opens the exact instrument + window + direction + years-mode preconfigured in the live tool. Appendix C stocks carry **two** per entry (Best Window + Buy & Hold).

---

## 6. THE AI LAYER

### TradeWave Research (the AI analyst / chatbot — "Tara"-class research agent)
Reads your TradeWave outputs instantly and turns them into plain-English research, cutting analysis "from thirty minutes to three." It answers questions *about* the measured stats but **never invents statistics** (it's "a very fast intern" reading the deterministic engine's output). Example queries it handles:
- "Why is this pattern ranked high if the Sharpe is only moderate?"
- "Show me the worst drawdowns inside this window and which years they happened."
- "Compare this window to the reverse date-range window and tell me which is cleaner."
- "Does this pattern work better in PE+2 than in all years?"
- "Summarize how much of the return happens early vs late in the window."

For eligible US-stock/ETF setups, a loaded-pattern brief separates the observed seasonal record
from the current-condition V3 model read. V3 uses 62 inputs across pattern robustness, technical and
security context, market regime, calendar context, and interactions. Three regression estimates are
averaged for direction-adjusted close-to-close PredR, and a separate three-model ensemble estimates
direction-adjusted PMFE inside the horizon. Win% is the empirical profitable share in the matching
walk-forward PredR calibration group. AIS is PredR's 0-100 percentile position within that horizon
tier's walk-forward calibration distribution, not a probability or universal confidence grade.

Plain-language reading: the historical record says what happened in the selected completed years;
AI Scores ask how the setup looks under current stock and market conditions. Calibration is the
reality check that turns model output into AI Win%: older readings are kept in time order, similar
PredR readings are grouped, and Win% is the share of that group that later finished profitable. A
historical 9 of 10 therefore stays 9 of 10 (n=10), while AI Win% may differ because it answers a
current-condition question. Win% is the quickest probability summary, PredR estimates the ending
return, PMFE estimates the best favorable move inside the window, and AIS is only a 0-100 relative
PredR rank, not a probability. Use them as a second opinion beside history, not as a replacement.

For a pattern from 10 through 30 calendar days, Tara states only the current-duration AI Win
Probability, PredR, and PMFE. Above 30 days, TradeWave also shows shorter-duration comparisons that
fit inside the source window: 31-60 days adds 30; 61-90 days adds 30 and 60; and a source above 90
days uses 30, 60, and 90. The exact current-duration V3 reading remains the primary table value
through 90 days, so an 85-day source shows 30, 60, and the current 85 days and never invents a
90-day extension. Above 90 days the table displays 90 as the bounded model reading while the
complete source duration remains visible as historical context. Tara deliberately omits AIS from
the headline because an unexplained relative rank is less useful than probability and estimated
return; AIS remains available in the opportunity table and guide.

Every shorter comparison preserves the same symbol, nominal entry date, direction, string
historical-years selection, and recurrence rule; only duration changes. The entry day is day 1, so
30, 60, and 90 calendar days end at entry plus 29, 59, and 89 days. The scorer independently
recalculates the selected historical cohort at that shorter duration and reports the actual screen
evidence, such as `6 of 10 positive; requires 9`. That screen result does not gate inference. Every
duration with a validated qualifying profile or a raw/prebuilt-validated empty-profile state keeps
its numeric model reading, and the
UI separately says **Meets screen**, **Does not meet screen**, or **Screen check incomplete**. A true
input-data, volatility, profile-validation, or provider failure is **Temporarily unavailable** and
remains a dash, never a fake zero. A validated empty set preserves the same missing pattern inputs
used by the manual duration scorer; it does not substitute the selected recurrence as learned
features. Selected recurrence is explanation, not an inference gate. Model estimates never become
extra historical observations.

AI sorting and filtering always use the value visibly shown: the current-duration value through 90
calendar days and the 90-day comparison above 90 days. Unavailable states use an internal null and
sort below numeric readings; they never become numeric zero. Common default and frequently viewed
table contexts are recorded without user identity and warmed only after the authoritative EOD
completion marker. The warmer discards old dates and row snapshots, re-fetches the six standard
default-year tables plus bounded popular logical views for the marker's target calendar date, and
gives every eligible default row first use of a 2,500-row global safety budget. Active rows are a
separate later phase. Manifests disclose eligible, warmed, and truncated coverage. Eligible table
windows are 10-367 inclusive calendar days, and scorer data must be from the exact EOD session
proven by the marker. Candidate scores stay
in generation-scoped staging records until every selected row has a terminal durable result; one
transaction then publishes all score values and pointers with the complete generation. A failed or
partial run exposes or replaces no live warmed score. Model release, feature/context schema, data-as-of date,
resource namespace, horizon, direction, entry, string `years`, and statistical recurrence selection
are part of the cache identity. Caller origin is telemetry only, so scanner warming, the table, and
Tara share one score for identical statistical inputs. On-demand scoring remains a bounded fallback for genuine misses. Loading, profile
unavailable, unsupported market/date, volatility block, and provider failure are distinct states.

Tara can also demonstrate why this differs from a conventional technical-indicator workflow.
Traditional indicators summarize recent price state; TradeWave aligns the same inclusive calendar
window across completed years and exposes the observed base rate, payoff, path, and failure years.
The user can recalculate that exact hypothesis over supported 10-, 12-, 15-, 20-, 25-year or maximum
history depths to reveal whether it is recent, durable, or lookback-sensitive. Strategy-building
questions are framed positively as a measurable research process: define fixed rules, test history
and nearby-window robustness, add current-condition context, and preserve the definition for future
tracking. Historical hit rate and AI Win Probability remain distinct evidence layers.

### Confidence Overlay (reliability second-opinion)
A **second opinion before committing**, answering a *different* question than the historical edge: "How stable is this edge, and how easy is it to misuse?" It weighs measurable attributes — **sample size & year-set relevance, return dispersion & outlier dependence, drawdown severity & typical adverse excursion, consistency across modern vs older regimes, and concentration of gains in a small subset of years.** Output: a simple **Green / Yellow / Red** rating **plus 2–4 short bullet reasons** (never a black-box prediction score):
- **Green** = solid edge, consistent behavior, drawdown matches reward.
- **Yellow** = edge exists but reliability mixed or drawdowns demand caution.
- **Red** = fragile, outlier-driven, or too noisy to treat as a real tendency.

### Planned AI capabilities (announced, not yet built)
- **One-page auto-brief per pattern** (the edge, what failure years look like, typical drawdowns, major catalysts inside the window) — summarizes/cross-checks what TradeWave already measured; "will not invent statistics."
- **Autonomous watchlist scanning** — AI scans your watchlist daily, surfaces only the most statistically meaningful shifts, generates a clean brief per opportunity with evidence, tracks patterns and notifies when conditions change, and flags whether a current move is historically normal or unusually extreme.

---

## 7. THE OPTIONS / EXECUTION TOOLING

Seasonality "sets the BIAS, not the TRIGGER" — the engine gives WHAT and WHICH DIRECTION; the options structure is just the risk wrapper. Supporting tools and reads:
- **Option Risk Graph** — payoff diagram of P/L vs stock price for a call/put or spread, showing **Profit/Loss at Expiration**, **Profit/Loss with Time Value** (curved line / a dashed "N months before expiration" line), **Break-even Line**, and **Strike Price** markers (used in worked CAH, OTM bear-call, ATM bull-put, and the real GOOGL Jan-2025 examples).
- **MFE → strike/target selection; MAE → invalidation/exit & sizing.** Covered-call rule of thumb: strike just above typical MFE plus cushion (MFE 5% → 7–8% strike, MFE 10% → 13–15%).
- **Trend Chart directional read** drives covered-call timing (downtrend favors selling the call/low assignment risk; sharp uptrend argues to hold shares).
- **Structure-matching:** directional conviction → long calls/puts; range/containment → credit spreads / iron condors; volatility/events → straddles/strangles; asymmetric → ratio spreads. OTM credit spread = high-probability time-decay income (expire worthless); ATM credit spread = directional, exit early at 20–50%.
- External confirmation the book layers on (not TradeWave features per se): **50-day moving average / Trend Long elevation** for the trigger, and a **buy-to-close** order to automate the spread exit.

---

## 8. APPENDIX DATA SURFACES (the repeatability proof tables)

Reference grids that are *evidence*, not signals: **win% (sample count)** cells across **day-length buckets** (`All / 10-30 / 30-60 / 60-90 / 60-120`) and **Year-Pair history settings** (`10_9, 10_10, 15_14, 15_15, 20_18, 20_19, 20_20`, where the pair = #historical-years _ #required-successful-years). Split into **Consecutive** (Baseline-Unfiltered vs Filtered TWR≥1.5, Long/Short, per year 2022–2025) and **Presidential-Election-Cycle** (Baseline vs Filtered TWR≥1.0). Conventions: **green cell = Win% ≥ 80% = exceptional**, but tiny Opp counts (e.g. 11) are not statistically meaningful. The **30-60 day bucket** is flagged the practical "sweet spot." These quantify the "baseline floor" of repeatability that the quality/regime filters are designed to lift.

---

## 9. HOW THE PIECES FIT — THE END-TO-END FLOWS

**Short-term / tactical:** Opportunity Table (pick universe, start date, regime, Years; filter `30-60;sr>1...`; sort SR/TWR) → click a row → Wave Viewer (set window/days/regime; toggle MFE/MAE; read Profit Bar Chart for consistency, Trend Chart for directional coherence, Stats Table for Sharpe/win-rate) → use MAE for stop, MFE for target → confirm trigger (50-day MA / Trend Long) → (optional) Option Risk Graph → **Save (+)** to Portfolio Manager → execute with pre-defined exit + Calendar Notification.

**Long-term / hold:** Buy & Hold Analysis (full-year baseline + S&P 500 benchmark) → read Trend Chart / Year Bars for the recurring weak window → exclude it via Reverse Date Range / Date Range Presets and recompute Cumulative Return → hand-tune the Date Range to optimize → confirm Cumulative Ret > B&H → save, set Calendar Notifications, track as virtual position, review monthly.

**Regime-first discipline (overlay on both):** set **Control 1 (which lens)** and **Control 2 (sample depth)** *before* reading any chart; use the Opportunity Table as a regime detector; when Consecutive and PE+2 disagree, refine inside the dominant regime; never compare a midterm window against a blended all-years average.

**Communicate:** Save Pattern → Portfolio Manager → Report icon → Custom TradeWave Report (stats block + Gain/Loss chart + Trend Chart + Load-on-Wave-Viewer link) → share by email/social/copy-URL/PNG/CSV.

**Governance throughout:** the deterministic Engine produces auditable numbers; the AI layer (TradeWave Research + Confidence Overlay Green/Yellow/Red + bullet reasons) only reads and explains them. "AI is not the edge. The edge is the edge."


### The Short-Term / Active-Trading Playbook: Finding, Validating, Timing, and Managing Trades in TradeWave

## 0. The mental model a short-term trader must hold first

TradeWave is a **measurement engine, not a prediction oracle**. For active trading this resolves into a single governing rule that appears again and again across the book:

> **"Seasonality sets the bias, not the trigger."**

A seasonal pattern tells you *what* to trade and *which direction* and *roughly when the window opens* — it is a high-probability historical tendency. It does **not** tell you the exact entry tick. You still confirm the trigger with current price action (trend strength + a moving average) before committing capital. Two corollaries:

- **"Seasonality is probability, not protection."** A historically bullish window can still take heavy intra-trade heat from a news shock and recover (the canonical case: NVDA entered a 20-year bullish January window, a news shock drove price as much as **−23.16% (MAE)** at its worst point, yet the window finished only **−5.22%**). Size and risk-manage accordingly.
- **The horizon where the edge lives is 10–120 days** (options stretch to roughly 10–90 days; swing = multi-week to multi-month). Seasonality "needs weeks, not minutes." On intraday timeframes the seasonal signal is dominated by spreads, microstructure, and randomness, so it is not statistically actionable there. Day trading is explicitly out of scope.

The four-outcome risk frame the active trader operates under: **a big win, a small win, or a controlled loss are all acceptable; the one unacceptable outcome is the big loss.** Every rule below exists to avoid the big loss.

The over-arching short-term workflow is a two-part rhythm:

1. **SCAN** — the Opportunity Table is the "Scanner": find and rank candidates fast across a universe.
2. **VALIDATE (the "Lab")** — the Wave Viewer: inspect the distribution, the path, and the risk before trading.

> "If you skip the scan, you waste time. If you skip validation, you fool yourself."
> "Do not confuse 'ranked highly' with 'approved trade.' The Opportunity Table is triage. It finds candidates. Your job is to validate."

---

## 1. STEP ONE — Scan: find candidates in the Opportunity Table

The Opportunity Table is the output of an institutional-grade analytics engine ("on the order of a trillion data points") that scans thousands of securities × many seasonal windows and ranks them by quality. It flips the retail habit of "pick a stock, then find a reason" into "start with the data, then decide if the trade deserves your risk."

### 1.1 The controls (top toolbar)

- **`tooltips ON/OFF`** toggle — interface help.
- **`PE+2` checkbox** — the regime switch (see §2). Unchecked = Consecutive years; checked = Presidential-cycle (midterm) years.
- **Month dropdown** + **Day dropdown** (e.g. `January` + `13`, or `February` + `10`) — the table scans for patterns that **start on this calendar month/day**.
- **Universe selector** (e.g. `S&P 500 STOCKS`) — what you scan: S&P 500, Nasdaq 100, a sector, futures, forex, ETFs, Wilshire 5000.
- **Years dropdown** — sample size. In Consecutive mode this is calendar years (observed max ~61). In PE+2/cycle mode it is *cycle samples* and the max shrinks dramatically (e.g. 15) because midterms occur only once every four years.
- **`9 of 10 years`-style consistency dropdown** — hit-rate selector: how many of the sampled years the tendency must have held.
- **Filter field** — semicolon-separated filter string (see §1.3).

### 1.2 The columns

`Date | Ticker | Days | DIR | AvgP | A% (or SR) | TWA | TWR`

- **Days** — window length in CALENDAR days, counting the ENTRY DAY as day 1. The last date is therefore `start + (days - 1)`: Jul 21 with Days=30 ends Aug 19; Jul 1 with Days=31 ends Jul 31. Never call these trading days. The analytics engine receives `daysOut = days - 1`; the +1 is only the inclusive display convention. See ecosystem doc §11 (0A).
- **DIR** — direction, **Long or Short** (the table surfaces both; you take the side the seasonal direction dictates).
- **AvgP** — average profit/return across the sample (simplest signal, but skewable by outliers).
- **SR (Sharpe Ratio)** — rewards cleaner, more stable patterns; largely focused on the final result.
- **TWA (TradeWave Average)** — average metric computed using **MFE**, so it reflects favorable movement *during* the window, not just where it ended.
- **TWR (TradeWave Ratio)** — Sharpe-like ratio computed from **MFE**; designed to surface windows that move strongly in the right direction along the path even if they did not finish at the peak. Complements (does not replace) Sharpe.
- **Footer** — opportunity summary, e.g. `13 opportunities, 13 Longs, 0 Shorts, 100%`, plus a "no filter" indicator.

### 1.3 Filter-string syntax (load-bearing — exact)

**No spaces. Conditions joined by `;`. Day-range first, then metric thresholds.** Worked examples from the book:

- `2-24;sr>1.0;twr>1.50` — short-duration (2–24 day) higher-quality candidates.
- `2-24;sr>1.30;twr>1.50` — high average-profit short patterns, then sort by quality.
- `10-90;twa>10;twr>1.40` — medium-duration patterns with strong TradeWave (MFE) movement.

After filtering, **click a column header (SR or TWR) to sort** by the quality you care about (cleaner/lower-risk vs higher reward). Direction is just read off the DIR column.

### 1.4 Short-term scan recipe (active trader)

1. Pick the universe (e.g. `S&P 500 STOCKS`, or Wilshire 5000 for breadth).
2. Set the start Month + Day to the calendar date you intend to trade.
3. Choose the regime: leave `PE+2` unchecked for normal calendar history, or check it to scan only current-cycle (midterm) years — 2026 is a PE+2 year.
4. Set Years (sample size); smaller (5–10) catches recent regimes, larger (20+) finds structural seasonality — but small samples carry more randomness so validate harder.
5. Apply a price filter to exclude thin/low-priced names (e.g. exclude under **$10**).
6. Apply a days-in-window filter to match your holding horizon (e.g. **30–60 day patterns**).
7. Apply a quality threshold (e.g. **Sharpe > 1**) and sort by **SR** or **AvgF/TWR**.
8. Read the footer, then **click only the candidates worth Lab time** into the Wave Viewer.

> "Filter for 30-to-60 day patterns … sort by SR or AvgF to bring the strongest setups to the top."

---

## 2. STEP TWO — Choose the regime (the most important 2026 dial)

The single most important 2026 concept for an active trader: the **`PE+2` checkbox changes the dataset itself, not just the display.** It also changes what "Years" means (calendar years vs cycle samples).

- **Consecutive mode** (unchecked): the last N calendar years — the "normal" definition of seasonality.
- **Presidential-cycle mode** (`PE+2` checked): scans only historical years matching the current election-cycle regime. The label changes with the calendar year (2026 = midterm = PE+2). In the Wave Viewer the full dropdown is: **consecutive, PE Years, PE+1 Years, PE+2 Years, PE+3 Years.**

**Decision rule — regime detection / "regime flip":** Hold time-of-year, sample depth, and horizon constant; toggle ONLY the lens. Read the longs/shorts/percent.

> Worked example (S&P 500 stocks, Jan 5 2026, 5–60 day horizon): Consecutive 10-Year lens = **85 opportunities, 79 Longs, 6 Shorts, 93% bullish**. PE+2 10-Year lens = **30 opportunities, 5 Longs, 25 Shorts, 83% bearish**. That is a regime flip.

- If both lenses stay broadly bullish → the cycle isn't changing much; trade the general read.
- If toggling flips the tone (bullish → bearish) → treat the **cycle lens as dominant** ("more like a personality, less like a coin flip"). Do all subsequent window refinement *inside the dominant regime* — you do not want a great plan for the wrong market personality.

> "These numbers aren't telling you what will happen. They are telling you what kind of market you are measuring."
> "When the two views disagree, that disagreement is the signal."

A short-term-relevant warning: **short-side seasonality is more regime-dependent than long-side.** Long win rates commonly cluster above 60% at baseline; shorts are "conditional, not always on." So shorts especially demand regime confirmation (favor longs in bullish regimes, shorts in bearish).

---

## 3. STEP THREE — Validate in the Wave Viewer (the Lab)

Never trade off the table. Validate each candidate with the **three-tool stack in a fixed order**:

1. **Profit Bar Chart** — is it consistent or a few outlier years?
2. **Trend Chart** — is the path tradable or does it whip you to death?
3. **Stats Table** — do the metrics confirm a reliable, low-torture tendency?

A pattern strong in one view but weak in others is the system working, not a conflict. **Act only when all three align.**

### 3.1 Wave Viewer toolbar (exact controls)

Editable date-range field (e.g. `02-05 to 03-17`), reference/as-of date (e.g. `2026-02-05`), symbol field (e.g. `CAH`), window-length field (e.g. `41 days`), lookback-years field (e.g. `10 years`), sample-type/regime selector (`PE+2 Years` / consecutive), and a `Months & Qtrs` time-grouping dropdown. The Trend Chart has a `Jan-Dec` span control and left/right (`< >`) navigation arrows.

### 3.2 Profit Bar Chart — distribution & consistency

One bar per historical year inside the window. **Green/up = price rose; red/down = price fell; green wins for a Long and red wins for a Short; bar height = raw price-return magnitude.** Toggle the **`MFE`** and **`MAE`** checkboxes to overlay the path:

- **MFE (Maximum Favorable Excursion)** — how far the trade moved in your favor at its best point. Light/dark split shows captured move vs additional upside. "How good can it get?"
- **MAE (Maximum Adverse Excursion)** — how far it moved against you at its worst. Shown as salmon/pink bars below zero. "How bad can it get?"

What to read:
- Consistency: bars mostly agree with the loaded direction (green/up for Longs, red/down for Shorts) rather than a coin flip.
- Outlier check: is the average carried by one or two "miracle years"? "Seasonality is not one number. It is a distribution."
- Are losing years small/contained?
- Did losers run up via MFE first (relevant for partial exits)?

### 3.3 Trend Chart — the most-typical-path map

Compresses many years of price paths into one average path. Its value is not the math; it is the timing map: where strength builds, where it peaks, where weakness recurs (shaded weak zones). It is a directional-coherence and behavioral tool, **not a prediction**.

- Confirm the move develops in **one coherent direction across most years**, not dominated by a couple of extreme years (trend coherence test).
- Read the shaded recurring weak zones (e.g. ADI's 20-year chart climbs through the first half then has a recurring red weak window roughly late July → mid-October).
- Click a year to inspect that specific year's path.

### 3.4 Stats Table — quantify reliability

Five blue-headed panels: **Wave Detail** (Symbol, Trade Direction, Date Range, Calendar Days Hold), **Wave Profit Loss** (Num Winners, Num Losers, Cumulative Return, S&P 500 Buy & Hold), **Wave Stats** (Avg Loss, Avg Gain, Median Gain, Std Dev), **Wave Info** (Percent Profitable, Sharpe Ratio, Trend Long, Trend Short), **General** (Years Filter, Securities Group, Last Price), plus a Cumulative Return mini-chart (ticker vs S&P 500).

Key reads for an active trader:
- **% Profitable / Win Rate** — share of years the window finished in the trade's direction.
- **Sharpe** — "not luck" check; confirms the result isn't carried by one or two lucky years and the variance isn't chaotic.
- **Avg Gain vs Avg Loss**, **Median Gain** (less outlier-distorted than the average), **Std Dev** (volatility/torture level).
- **Cumulative Ret vs B&H** — does timing the window beat simply holding?
- **Trend Long / Trend Short / Alignment** — current-momentum readout over roughly the last one to two weeks. For a long setup, Alignment uses Trend Long and tests for upward movement; for a short setup, it uses Trend Short and tests for downward movement. Against means the recent move is not confirming the seasonal direction, not that the historical pattern scored zero or is certain to lose. Unavailable means no usable current score was returned.

> "Charts help you see. The Stats Table helps you measure." / "Metrics help you find candidates. Charts help you decide what is real."

---

## 4. STEP FOUR — Read Success Rate WITH Sharpe (the core decision rule)

The most important single judgment skill: **pair the hit rate with the Sharpe Ratio.**

- High/perfect **Success Rate** → gives you the **direction**.
- **Low Sharpe** next to a high hit rate → the path is **choppy/lumpy** (countertrend rallies, news spikes); the edge is real but uneven → use **noise-tolerant tactics** (staged entries, hedges, defined-risk structures, don't over-trust the average, don't miss the window).
- **High Sharpe** → the move looks like **repeatable seasonal drift**, not random volatility → cleaner, more tradeable.

Worked contrasts:
- **BIIB** short: 16% avg / Sharpe **1.58** over 50 days → repeatable drift; when the down-move shows up it's sharp, so size for it.
- **AMAT** short: 20% avg but Sharpe only **0.77** over 210 days → a rough ride; manage with staged/hedged entries.
- **AXP** long (Appendix): 100% / Sharpe **2.52** over 19 days → the cleanest tactical setup in the book (high hit rate *and* high Sharpe).

Sample-depth caveat: an **8–10 year PE+2 sample is statistically shallower** than a 25–33 year consecutive sample. A perfect record on a tiny sample is notable but not equal to a deep record. (And "10 of 10 years" in a PE+2 study means 10 *midterm-cycle sample years*, not 10 consecutive calendar years.)

---

## 5. STEP FIVE — Window alignment (timing the window), NOT curve-fitting

A real seasonal move begins in a **pivot zone** (the average bends, then turns). Align the window's start/end to where behavior actually changes by testing **small shifts** and watching Sharpe and Avg Gain update.

> Worked example — Boeing (BA Trend Chart): window `Jan-23 to Feb-7` → Sharpe 0.8/1.74, Avg Gain 4.54%. Shift start to `Jan-27 to Feb-7` (onto the pivot) → Sharpe 1.14/1.72, Avg Gain 5.85%. Better stats because measurement now starts where the move starts.

**The hard line:** only test small shifts around an *obvious* pivot zone. Searching the whole calendar for the best Sharpe is **curve-fitting** ("torturing the data until it confesses"). Alignment ≠ curve-fitting, and the difference is the credibility of the whole method.

---

## 6. STEP SIX — Set the exit BEFORE entering (non-negotiable)

> "Plan your exit before entering." / "Lazy traders execute exits, they do not improvise them."

Every position must have three predefined things:
1. **Profit target** — derived from **MFE** (how far it typically runs).
2. **Invalidation point / stop** — derived from **MAE** (the normal amount of pain; the line that says this trade is wrong).
3. **Planned time horizon** — when you're out regardless (for options, exit before time decay accelerates — see §8).

Behavioral guardrails the Trend Chart enforces:
- **Prevent panic exits.** When a live position goes red, check the Trend Chart context before bailing. If the historical path supports strength ahead, hold with risk controls. (AVGO example: 2024 was deep red −10% inside a 91%-profitable window; the trend was right and the position recovered.)
- **Prevent overstaying past the peak.** A seasonal move has a natural peak zone; holding past it gives back gains. Demonstrated brutally by widening the holding window:

> **BX (Blackstone)** `01-13 to 01-29`, 17 days (disciplined peak window): Sharpe 2.18, %Profitable **100%**, CumRet **+102%**. Same ticker widened to `01-13 to 04-08`, 86 days (overstaying): Sharpe **−0.01**, %Profitable 60%, CumRet **−2%**. The edge collapses.

Verification habit: **watch the stats degrade as you extend the days control** — if widening the window kills Sharpe/CumRet, your edge is concentrated near the peak; keep the window tight.

---

## 7. STEP SEVEN — Confirm the trigger with price action

Seasonality is a *timing overlay*; technicals time the entry **inside** the window. Before pulling the trigger, confirm:

- Price is **reclaiming/holding above its 50-day moving average** (for a long; inverse for a short).
- **Trend Long is elevated** / trend strength aligns with the seasonal direction.
- Optional confirmation: trend alignment, basic moving-average confirmation, clear support/resistance.

**Conflict rule:** if technicals and seasonality **strongly conflict, pass or reduce size.** Also glance at the bigger market — don't fight an obvious broad-stress environment; confirm your trade isn't swimming against the dominant tape.

Quick pre-entry reality check (the "30-min → 3-min" discipline):
- Confirm the **next earnings date** — will you be holding through it?
- Scan for obvious red flags: guidance shocks, major regulatory events, existential headlines.
- If something can blow up the trade: size down, plan around it, or skip.

---

## 8. STEP EIGHT — Express the setup as an options structure

Seasonality supplies the directional bias and timing window; **the option structure is just the defined-risk wrapper.** Match the structure to the setup:

| Setup | Structure |
|---|---|
| Strong directional conviction | Buy **calls** (bullish window) / **puts** (weakness window) |
| Containment within a range | OTM / ATM **credit spreads**, **iron condors** |
| Expected volatility / event | **Straddles / strangles** |
| Asymmetric payoff | **Ratio spreads** |

### 8.1 Buying calls/puts (Ch. 12)

- Long options are a **three-dimensional bet**: you must be right on price **direction**, **time** (before expiration), and **volatility**. That is why even a good seasonal bias is risky as a long option.
- **Expiration rule:** buy options ~**2 months beyond** the pattern window and **exit ~1 month before** expiry, because time decay accelerates late. (A 44-day pattern wants 45–60+ day options.)
- Use the **Option Risk Graph** before sizing: P/L at expiration, P/L with time value (curved line), Break-even Line, Strike Price markers.
- **Worked seasonal-options example — Cardinal Health (CAH):** 10-year PE+2 window `Feb-5 to Mar-17` (41 days), 100% profitable, 142% cumulative return, Sharpe **2.64**, Trend Long 100 / Trend Short 0, vs S&P 500 buy-and-hold ~flat. A textbook clean directional long-call setup.

### 8.2 Credit spreads (Ch. 14) — the active-income workhorses

A credit spread = sell one option, buy another farther out to cap risk; collect premium up front for limited profit and defined max loss. **Bull put** = bullish/neutral; **bear call** = bearish/neutral.

**The OTM-vs-ATM fork (active-trader decision):**
- **OTM credit spread** — high-probability, profits from **time decay**, aims to **expire worthless**, small premium, low capital. Use in stable/sideways windows with a strong seasonal pattern. (Example math: stock $90, sell $100 call / buy $110 call; $10-wide, $2 credit → $800 margin/contract.)
- **ATM credit spread** — **directional**, relies on the move happening, higher reward/risk, credit ~**50% of spread width**, fast outcome. Use when TradeWave shows a short-term pattern with **strong momentum** and you expect a quick directional move.
- **ATM exit rule:** exit early for a **20–50% gain** rather than holding to expiration (holding adds limited gain but raises reversal risk). Automate with a **buy-to-close** order.

**Real January 2025 GOOGL bull-put case study:** TradeWave seasonal pattern bullish through Feb 2 2025; GOOGL $190 on Jan 2; sold Mar $195 put / bought Mar $185 put for **$5.00 credit** ($500/contract; max risk $5). By Jan 7 (5 days) GOOGL $201 → spread $3.95 = **21% gain**; by Jan 21 (19 days) GOOGL $202.29 → spread $3.30 = **34% gain**. A buy-to-close at $3.50 targets ~30%.

**Strike selection inputs (for any options structure):** **MFE** sets the upside target / where to place the short strike (keep the strike *outside* the stock's normal upside); **MAE** sets invalidation and gauges drawdown risk. A consistent up Trend Chart favors holding shares / bullish structures; a downward-sloping Trend Chart favors selling the call side. "Most spread disasters happen at the end, not at the start." "You are not paid by how many calls you sell. You are paid by outcomes."

---

## 9. STEP NINE — Save, automate, and execute

Execution, not research, is where seasonal edges fail ("Traders miss the start date. They hesitate. They forget to review an exit window. Or they remember the idea two weeks too late.").

- **Save the validated candidate** with the **`+` save icon** in the Wave Viewer → it stores the full **configuration** (symbol, entry/exit dates, direction, days, the Years/lookback definition, group, tags, notes) so it reloads exactly — not a chart image.
- **Portfolio Manager** is the pattern library / virtual-position tracker. Create a **dedicated portfolio for short-term trades** (separate from swing/long-term/paper-track). Columns: Entry/Exit Date, Days, Ticker, **DIR**, **SR**, **Years** (dual format: plain number = consecutive, **`PE2-N`** = N midterm-cycle years), Group, action icons, **# shares**, **$ invested**, **% live change**.
- **Calendar Notifications** (calendar icon) — push the entry and exit window + an ahead-of-start reminder to your calendar so you don't rely on memory.
- **Notes field** = trading journal: why saved, what invalidates it, what confirmation you want, live vs paper.
- **Track as a virtual position** (#, $, %) to see whether the current year is behaving normally vs history.

---

## 10. The AI layer for faster validation

Two AI features speed the short-term loop (the boundary: **"TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics."**):

- **TradeWave Research** (chatbot/analyst) — reads your outputs and answers plain-language questions, cutting analysis from ~30 min to ~3. Useful active-trader queries: "Show me the worst drawdowns inside this window and which years"; "Compare this window to the reverse date-range window and tell me which is cleaner"; "Does this pattern work better in PE+2 than all years?"; "Summarize how much of the return happens early vs late in the window"; "Why is this ranked high if the Sharpe is only moderate?"
- **Confidence Overlay** — a reliability **Green / Yellow / Red** second opinion that ALWAYS gives **2–4 bullet reasons** (never a black-box prediction). It answers a different question than the historical edge: *"How stable is this edge, and how easy is it to misuse?"* — weighing sample size & year-set relevance, return dispersion & outlier dependence, drawdown severity/typical adverse excursion, modern-vs-older-regime consistency, and gain concentration. **Green** = solid edge, drawdown matches reward; **Yellow** = mixed reliability / drawdowns demand caution; **Red** = fragile, outlier-driven, too noisy. Read it before committing.

---

## 11. Daily / weekly cadence (the routine)

- **15-minute daily:** scan the Opportunity Table for high-probability windows, save **3–5 candidates**, check earnings dates and obvious red flags, set alerts for key levels/dates.
- **60-minute weekly:** review the next 2–4 weeks of seasonal windows, pick your best **1–3 trades**, **predefine exits** for each, schedule reminders so you execute without stress.

Trader-persona checklists:
- **Short-term options traders:** patterns ~**10–90 days**; define exit before entry; use alerts/calendar reminders so you're not watching every tick.
- **Swing traders:** multi-week to multi-month patterns; **enter early in the window, not late**; **scale out near historical peak periods shown by the Trend Chart.**
- **Beginners:** paper-trade first using the same checklist; focus on one or two setups until execution is consistent; track outcomes to learn process, not superstition.

> "Standards turn a firehose into a shortlist." / "The goal is not to eliminate uncertainty. The goal is to eliminate unforced errors." / "Trade smarter, not more. The best traders are not working harder. They are filtering better."

---

## 12. Ready-made short-term setups from the appendices (loadable patterns)

Each book pattern carries a **QR code / deep-link** ("Load [TICKER] pattern on TradeWave") that opens the exact symbol + window + direction + years-mode preloaded. High-quality short-side and tight-window examples an active trader can pull straight in:

- **NVDA** short, Mar 21 – Aug 2 (PE+2, 6 of 6, ~30% avg, Sharpe 0.95) — "hard-to-believe but repeatable midterm-cycle weakness… trade it with tight risk definition and the expectation of violent volatility, not a clean downtrend."
- **ADSK** short, Mar 18 – Jul 3 (PE+2, 88%, Sharpe 0.9, CumRet 209% vs B&H 14%).
- **TER** short, Mar 19 – Jun 11 (PE+2, 100%, Sharpe 1.08, CumRet 247% vs B&H −74%).
- **AXP** long, Oct 24 – Nov 12 (PE+2, 100% / 10 of 10, Sharpe **2.52**, 19 days) — cleanest tactical card.
- **INTC** long, Oct 16 – Nov 16 (PE+2, 100% / 10 of 10, 14% avg, Sharpe 1.27) — perfect but timing-sensitive given the tight window.
- **COP** long, Feb 26 – Apr 8 (PE+2, 100% / 10 of 10, 6% avg, Sharpe **2.31**, 41 days) — "short, punchy"; edge is consistency/efficiency, easier to manage tactically with defined risk.
- **CMCSA** long, Oct 1 – Dec 9 (PE+2, 100% / 10 of 10, 10% avg, Sharpe 1.59) — clean post-summer strength.
- **DIS** long, Oct 11 – Nov 8 (PE+2, 93% / 14 of 15, 9% avg, Sharpe 0.83, 28 days) — high hit rate but modest Sharpe → discipline matters, don't miss the 28-day window.
- **Commodity shorts/longs:** Lean Hogs short Aug-10 to Aug-28 (43 of 44, Sharpe 1.79); Sugar short Mar-28 to May-04 (11 of 11); Corn short Jul-12 to Jul-26 (18 of 20); Natural Gas short Nov-25 to Dec-16 (9 of 10); Live Cattle short Apr-20 to May-01 (39 of 45); RBOB Gasoline long Jan-25 to Mar-03 (26 of 26, CumRet 4,805%).

For any loaded card: read the **per-year bar chart** as raw price movement (green/up = price rose; red/down = price fell). Green wins for a Long; red wins for a Short. Then use the **bottom stats strip** (Sharpe, Avg Gain, % Profitable, Cumulative Ret, **B&H** comparison) for direction-adjusted performance. Use **Reverse Date Range** to flip a window and find the complementary side to fade or avoid.

---

## 13. The complete short-term loop (one screen)

1. **Scan** the Opportunity Table — universe, start date, regime (`PE+2`?), Years, price filter, days filter (30–60d), quality filter, sort by SR/TWR.
2. **Choose regime** — toggle the lens; if it flips, trade inside the dominant regime; confirm shorts especially.
3. **Validate** in the Wave Viewer — Profit Bar Chart (consistency/outliers, MFE/MAE), Trend Chart (coherent direction, peak/weak zones), Stats Table (Win Rate, Sharpe, Median, CumRet vs B&H).
4. **Read Success Rate WITH Sharpe** — direction from hit rate, path-smoothness/tactics from Sharpe; weight sample depth.
5. **Align the window** to the pivot zone with small shifts (alignment, not curve-fitting); keep it near the peak.
6. **Predefine the exit** — MFE target, MAE stop, time horizon; plan against panic-exit and overstay.
7. **Confirm the trigger** — price reclaiming the 50-day MA, Trend Long elevated, earnings/headline check, conflict → pass/reduce size.
8. **Express it** — calls/puts (2 months past the window, exit 1 month early) or OTM/ATM credit spreads (OTM = time-decay income in stable windows; ATM = directional momentum, exit at 20–50% via buy-to-close); MFE/MAE set strikes; Risk Graph before sizing.
9. **Save & automate** — `+` save to a short-term Portfolio, calendar notifications, virtual-position tracking, journal note.
10. **Run the cadence** — 15-min daily scan, 60-min weekly planning; let the AI Research + Confidence Overlay accelerate validation.

> "Markets will still surprise you… But once you start thinking this way, they stop feeling like pure chaos. They start feeling like behavior. Repeatable, measurable behavior."

### The Long-Term / Investing Playbook: How a Buy-and-Hold Investor Uses TradeWave

## 0. The core distinction: investor vs. trader

TradeWave is one engine with two operating modes, and the long-term investor uses a *fundamentally different workflow, time horizon, and toolset* than the short-term trader. The short-term trader lives in the **Opportunity Table → Wave Viewer ("Scan then Lab")** loop hunting 10-to-120-day windows; the long-term investor lives in the **Buy & Hold Analysis → Reverse Date Range → Best Seasonal Hold Window** loop, working with windows measured in *months* (150-340 days), deep samples (25-63+ consecutive years), and a single benchmark question that governs everything: **does timing this window beat just holding the stock all year (Buy & Hold, Jan-1 to Jan-1)?**

| Axis | Short-term trader | Long-term investor |
|---|---|---|
| Time horizon | 10-120 days (options ~10-90d; swing multi-week to multi-month) | 150-340 day hold windows; multi-month / multi-year positioning |
| Entry tool | Opportunity Table (scan, rank, filter) | Buy & Hold Analysis (baseline) → Reverse Date Range |
| Sample depth | 5-10-20 years, often PE+2 (small cycle samples) | 20 / 25 / 30 / 33 / 41 / 45 / 63 years (deep consecutive history) |
| The benchmark | Sharpe / TWR / win rate vs. each other | **Cumulative Ret vs. B&H** (Cumulative Return Multiplier) |
| Goal | Capture a discrete move with defined risk | Be invested only in the strong window, sit out the weak one; reallocation |
| Execution | Calls/puts, credit spreads, covered calls | Position holds, covered-call income overlay, do-not-trade filter, rebalancing |
| Cadence | 15-min daily scan / 60-min weekly plan | Track **monthly, not daily**; annual repeat of the same windows |
| Account | Any | **Tax-advantaged (Roth IRA) preferred** to avoid realized-gain drag |

The investor's mantra from the closing chapters: **"Trade smarter, not more"**, **"track results monthly, not daily"**, and **"over time you typically want more of your wealth in long-term diversified holdings, with active trading becoming the smaller satellite around the core."**

---

## 1. The core long-term loop (Chapter 10 "The Long-Term Toolbox")

This is the canonical investor workflow. Memorize it; the whole long-term product is built around it.

**Step 1 — Establish the baseline with Buy & Hold Analysis.** Enter a ticker, set the date range to the **full year (Jan 1 - Jan 1, 366 Calendar Days Hold)**, and read the **Cumulative Return** plus the **year-by-year green/red bar chart**. Compare it to the **S&P 500 Buy & Hold** figure shown right beside it in the Wave Profit Loss panel. This is the honest, unfiltered "always invested" floor everything else is measured against.
- AAPL since 1981 IPO = **216,221%** cumulative return by Jan 16, 2026 (29 winners / 17 losers, 63% profitable, ACTIVE flag = current in-progress year included); S&P 500 B&H = 4,990%.
- ADI since 1981 = **34,521%** (31 winners / 15 losers).

**Step 2 — Find the recurring weak window.** Read the **Trend Chart** and the red year-bars to identify the recurring weak month or stretch. AAPL underperforms in **September**; ADI declines roughly **June 9 to October 25**.

**Step 3 — Apply Reverse Date Range to EXCLUDE the weak window and recompute.** Reverse Date Range is *the central long-term tool of the chapter*. It excludes a chosen historically weak window from the analysis and recomputes cumulative return, showing how avoiding that window would have changed long-term results.
- AAPL excluding September → **3,765,269%** (~17× the buy-and-hold baseline).
- ADI excluding June 9-Oct 25 (refined hold = Oct 26 to June 8) → **1,320,644%** (vs 34,521% baseline).

**Step 4 — Hand-tune / optimize the excluded range.** Each stock has its own optimal window — *test, don't memorize*. Hand-type the Date Range field to optimize.
- AAPL optimized exclusion (exclude **Sep 5 to Oct 3**, i.e. hold **Oct 3 - Sep 4**, 537 Calendar Days Hold) → **8,591,518%** (33 winners / 12 losers, 73% profitable, Sharpe ~0.64).

**Decision rule (Appendix C):** A seasonal hold window earns its keep only when its **Cumulative Ret is HIGHER than B&H** for the same stock. That single comparison proves timing beat holding all year. **Self-consistency check:** open the Buy & Hold view and confirm its two cumulative numbers match the full year — if they do, the analysis is internally sound.

---

## 2. The "Best Seasonal Hold Window" — the investor's flagship output (Appendix C)

Appendix C reframes the engine for buy-and-hold investors. For each major stock it contrasts a **Buy & Hold baseline** (Jan-1 to Jan-1, full history) against the **Best Seasonal Hold Window** — the contiguous multi-month stretch that historically captured the strongest, most consistent portion of the stock's long-term move — and reports Success Rate, Avg Gain, Sharpe Ratio, and a headline **Cumulative Return Multiplier**.

### The desktop discovery workflow (find a window yourself)
1. **Load the stock and set Years to the MAXIMUM available** ("max years").
2. **Read the Trend Chart** to find a visibly, consistently WEAK stretch (a high-probability down move that stands out across years).
3. **Use the Trend Chart's interactive date-range selector** (the shaded/draggable band) to highlight that weak stretch.
4. **Use the top-right Reverse Date Range selector in the Wave Viewer** (desktop only) to flip it and reveal the complementary, usually stronger "best window."
5. **Check the bottom stats bar's Cumulative Ret vs. B&H.** If Cumulative Ret > B&H, timing that window historically outperformed holding all year.

The weak (worst) window is simply the **complement** of the best — you reveal it by reversing the date range. The book's recurring instruction across every Appendix C card: *"To see the worst window, load this in TradeWave and click Reverse Date Range."*

### Appendix C reference table (exact stats)

| Stock | Yrs | Best Window | Best: Success | Best: Avg | Best: Sharpe | Multiplier | B&H baseline (Jan1-Jan1) |
|---|---|---|---|---|---|---|---|
| JPM | 41 | Sep 27 - Jul 31 (307d) | 68% (28/41) | 21% | 0.55 | — | 69% (29/42), 18%, 0.40 |
| DIS | 63 | Sep 30 - Jun 7 (250d) | 78% (49/63) | 24% | 0.61 | **35×** | 73% (47/64), 18%, 0.41 |
| AAPL | 45 | Oct 3 - Sep 5 (337d) | 76% (34/45) | 38% | 0.64 | **40×** | 65% (30/46), 32%, 0.45 |
| RTX | 41 | Oct 10 - Jul 31 (294d) | 93% (38/41) | 20% | 0.79 | **4×** | 76% (32/42), 16%, 0.52 |
| ADI | 45 | Oct 26 - Jun 9 (226d) | 78% (35/45) | 30% | 0.55 | **38×** | 67% (31/46), 20%, 0.37 |
| AXP | 41 | Oct 26 - Aug 28 (306d) | 80% (33/41) | 17-20% | 0.43-0.6 | **4.6×** | 74% (31/42), 17%, 0.43 |
| BA | 63 | Oct 27 - Jun 17 (233d) | 76% (48/63) | 21% | 0.58 | **12.5×** | 70% (45/64), 19%, 0.37 |
| AMD | 41 | Oct 27 - May 29 (214d) | 80% (33/41) | 45% | 0.58 | **6,220×** | 48% (20/42), 30%, 0.28 |

**Read the lift across all four stats simultaneously** — timing the window doesn't just compound returns, it *raises* Success Rate, Avg Gain, AND Sharpe versus B&H (e.g. DIS lifts Avg Gain 18→24% and Sharpe 0.41→0.61; AAPL 32→38% and 0.45→0.64; ADI 20→30% and 0.37→0.55). **Caveat:** B&H (Jan-1 to Jan-1) can complete earlier than seasonal windows, so it may show one extra year in the sample.

### A near-universal calendar truth for long-term holds
Notice how many "best windows" start in **late September / October** and run through the following **summer** — DIS, AAPL, RTX, ADI, AXP, BA, AMD, JPM all share this shape. This echoes Chapter 7's flagship every-year finding on the S&P 500 itself: the strong in-season window is **October 26 to September 3**, and the weak 52-day window is **September 4 to October 25** (the **"Lost Summer Effect"**, averaging ~-1% vs ~+9% for optimized windows). The investor lesson: the back half of summer into mid-October is structurally where you sit out, and you re-enter in the fall.

---

## 3. Long-horizon PE-cycle positioning (Chapters 7-8): the "100-Year Pattern"

The single most important *macro* tool for a long-term investor is **regime conditioning by the Presidential Election Cycle** — because the strongest multi-year broad-market edges only appear once you stop blending dissimilar years.

### The two controls every investor must set deliberately (Chapter 8)
- **Control 1 — Regime lens:** Consecutive years (baseline) vs. a specific cycle-year type: **PE** (election), **PE+1** (post-election), **PE+2** (midterm), **PE+3** (pre-election).
- **Control 2 — Sample depth:** how many samples inside that lens. *"Last 10 years" is ambiguous* — 10 consecutive calendar years vs. 10 PE+2 years (which span ~40 years, since midterms occur once every four years). You **trade breadth for relevance.**

### The 100-Year Pattern (the book's centerpiece, regime-aware)
Filtering the S&P 500 for **midterm (PE+2) years** reveals a ~295-day bullish cross-year window, **Sep 27 (of a midterm year) to Jul 18 (of the next year)**:
- **5,045% cumulative return, 19% avg gain per cycle** vs. 49% cumulative / 4% avg gain buy-and-hold.
- **Profitable in 23 of 24 cycles = 96% win rate** (1930-2022); the single failure was **1930**, the depth of the Great Depression.
- The next cycle begins **September 27, 2026** — which is *why 2026 is the book's anchor year*.
- Modern-era re-run (1985-2025): ~12% seasonal vs ~11% B&H annual, profitable 83% of years; $10,000 → ~$650K seasonal vs ~$414K B&H.

### Best window per cycle-year type (24 cycles, 1930-2022) — long-term allocation map
| Year type | Optimal window | Cumulative | Avg gain | vs B&H cumulative |
|---|---|---|---|---|
| PE (election) | May 23 - Jan 6 | 683% | 9% | 417% / 8% |
| PE+1 (post-elec) | Apr 7 - Aug 2 | 552% | 9% | 217% / 7% |
| PE+2 (midterm) | Sep 27 - Jan 6 | 354% | 7% | 49% / 4% |
| PE+3 (pre-elec) | Jan 2 - Jul 20 | 1,295% | 12% | 1,220% / 12% |

### "Sell in May" is regime-specific (critical for investors)
The May-Oct weakness concentrates **almost entirely in PE+2 (midterm) years**: -34% May-Oct cumulative vs +958% Nov-Apr cumulative. *Only PE+2 is negative May-Oct.* An investor positioning a long-term core should NOT defensively "sell in May" every year — only the midterm year historically warrants it, and even then the strong cross-year window begins again at Sep 27. **PE+2 turning zone:** weakness runs into late June (~June 24), tone changes in late September (Sep 27).

### PE+1 directly challenges "Sell in May" (Chapter 10 example)
The S&P 500 (SPX) in PE+1 years has a strong **April-August window (04-05 to 08-02, 120 days)**: higher 77% of the time over the last 98 years, **100% over the last 50 years**, avg window return **7.46%**. The 2025 PE+1 year delivered strength *beyond* this window — reinforcing that a tendency is a historical frequency, not a guaranteed calendar script.

**Investor takeaway:** classify the current year (PE/PE+1/PE+2/PE+3) FIRST, then apply the regime-correct window. Use the **Years Filter cohort controls** ("Presidential Election+1 Years", "PE+2 Years", etc.) — these are literal dataset switches, not narrative. *"If you trade 2026 like a normal year, you will miss what the data is signaling."*

---

## 4. Portfolio construction (Chapter 18 "The Road to Financial Freedom")

### The two-phase capital arc
- **Phase 1:** Start with short-term seasonal trading — it compounds faster (more trades, build momentum) but must be systematic.
- **Phase 2:** As the account grows, **gradually shift weight toward long-term seasonal investing** for stability; longer-term seasonal moves of bigger names are slower and more reliable. Active trading becomes the **smaller satellite around a long-term diversified core**, so one bad short trade can't durably damage durable wealth.

### Diversification — "the quiet superpower" — across THREE independent axes
1. **Timeframes:** short windows = tactical opportunities; **longer windows = compounding and dividends**.
2. **Sectors:** cyclical (benefit in expansions), defensive (hold up when conditions tighten), commodity-sensitive (behave differently from broad equities).
3. **Asset classes:** when equities are messy and other markets behave better, cross-asset pattern analysis lets you **avoid forcing trades in the wrong environment**.

*"The goal is not to trade everything — it's to have OPTIONS when conditions change. A portfolio that only works when one sector leads is a bet, not a plan."* TradeWave's **cross-asset / multi-market pattern analysis** (stocks, ETFs, indices, futures/commodities — Appendix D) and **sector filtering** support this.

### Reallocation as a long-term use case (Chapter 10, Example 1)
Use **buy-and-hold comparisons across holdings** to inform reallocation: e.g. Verizon (VZ) underperformed the S&P 500 over 15 years while Microsoft (MSFT) materially outperformed VZ. Whether to reallocate is a question of objectives and risk tolerance, but the long-run relative-performance comparison is the data input.

---

## 5. Long-term income & risk overlays (Chapters 10, 13)

The investor doesn't have to *exit* to act on a weak window. Two overlays:

### Covered calls over the weak window (monetize without selling)
Study the historically weaker window for a stock and **write calls (often near-the-money)** to collect premium during it. In taxable accounts this reduces the need for frequent exits and realized gains. Strike selection is quantified with three inputs:
- **MFE** (Maximum Favorable Excursion = the historical high / normal upside) — set the strike *just above typical MFE plus a cushion* (MFE 5% → strike 7-8%; MFE 10% → 13-15%); avoid placing the strike *inside* the stock's normal upside.
- **MAE** (Maximum Adverse Excursion = historical low / drawdown) — gauges downside risk.
- **Trend Chart shape:** a consistent DOWNTREND during the window favors selling the call (low assignment risk); a sharp UPTREND argues to hold the shares and capture the gain instead of capping it.
- Window/expiration matching: a 44-day window wants 45-60 day expiration. Treat **assignment as a planned outcome, not a failure.** *"Keep this boring. Boring works."*

### The do-not-trade filter (the simplest risk control)
Use seasonality purely as a filter to **NOT be invested** in historically weak windows — an alternative to options requiring no derivatives. *"Doing nothing is a position."*

### Tax-awareness (essential for the long-term overlay)
Frequent in/out seasonal-timing trades in a **taxable account** trigger realized gains. The exclusion/overlay strategy is most attractive in **tax-advantaged accounts (Roth IRAs)** where gains remain tax-free. Covered calls let you monetize a weak window *without* the exits, mitigating tax drag where exits would otherwise be needed.

---

## 6. Validating a long-term pattern before trusting it (Chapters 6, 17; Appendices A-B)

Long windows demand more scrutiny than short ones because a perfect-looking multi-month record can hide interim drawdowns.

### The three-tool validation stack, applied long-term
1. **Profit Bar Chart** — is the long edge stable across decades or carried by a couple of "hero years"? (e.g. TYL's only losing years in 25 were 2002 and 2009; AMD's one red year ~2018.) Toggle **MFE/MAE** to read upside potential vs. drawdown pain per year.
2. **Trend Chart** — the most-typical-path map; read where strength builds, peaks, and the recurring weak zone (ADI's 20-yr chart: strong climb first half, weak late-July-to-mid-October zone). Use it as a **bias filter**, then manage entries/exits with normal risk rules — a perfect Success Rate still contains pullbacks.
3. **Stats Table** — the five-block readout: **Wave Detail, Wave Profit Loss, Wave Stats, Wave Info, General**. Read Percent Profitable, Sharpe, Avg Gain vs Avg Loss, Median Gain (less outlier-distorted than the mean), Std Dev, and Cumulative Return vs S&P 500 B&H.

### Robustness checks specific to long horizons
- **Verify across 10-year AND 20-to-30-year views.** A strong pattern should not collapse when you zoom out; if it only works in one narrow slice, treat it as **fragile**.
- **Inspect failure years.** If they cluster in a regime/cycle slice, that's useful information; if they appear randomly, the pattern is fragile.
- **Toggle election-cycle filtering** to confirm whether the edge holds (and whether disagreement between Consecutive and PE+2 views is itself a signal).
- **Raise the history requirement (Year Pair settings)** for cleaner patterns: 10_9, 10_10, 15_14, 15_15, 20_18, 20_19, 20_20 — but accept fewer opportunities and interpret the smaller sample carefully (the second number = minimum successful years required).
- **Sample-depth honesty:** an 8-year PE+2 sample is statistically shallower than a 33-year consecutive sample. A perfect record on a tiny Opp count (e.g. 91% on 11 occurrences) is NOT statistically meaningful — sample size gates significance (green = Win% ≥ 80% is only highlighted when the count is large enough).

### TWR / TWA as the long-term quality filter (Appendix A)
**TWR (TradeWave Ratio)** is the pattern-quality score — Sharpe-like (return relative to variability) but also incorporating **MFE**, so it rewards windows that move strongly in the right direction along the path, not just where they finish. Filter long candidates to **TWR ≥ 1.5** (Consecutive studies) or **TWR ≥ 1.0** (PE-cycle studies, looser because the 4-year cycle yields fewer data points). Higher thresholds raise win rate while cutting opportunity count — the intentional quality-for-frequency tradeoff. **TWA (TradeWave Average)** is the companion average-outcome metric that incorporates intra-window opportunity (MFE behavior), not just end-of-window closes.

Appendix A baseline (long side, "All" row): 2022=64%, 2023=78%, 2024=71%, 2025=77% — long-side seasonality is meaningfully above random even unfiltered (commonly clusters above 60% before any regime/timing filters), whereas short-side is more context-dependent. The **30-60 day bucket** is a practical sweet spot in the filtered tables; for *long-term* investors, prefer the deeper-history, longer-window cards.

### The layered workflow (Appendix B framing) — applies at every horizon
**(1) Seasonality selects WHEN** (the window) → **(2) TWR filters QUALITY** → **(3) Regime alignment selects DIRECTION** (long in bullish regimes, short in bearish) → **(4) Technical confirmation improves ENTRY.** Headline win rates are a deliberately conservative "baseline floor" (they include mismatches a real trader would avoid); the filters exist to lift outcomes above that floor by reducing "right pattern, wrong environment" and "right window, wrong entry."

---

## 7. Longer-duration commodity/futures holds (Appendix D)

Long-horizon investors also use **multi-month commodity holds**, each defined by instrument + Analyzed Date Range + direction + Years Analyzed, with Key Stats (Winning Years, Sharpe, Average Gain Overall, Cumulative Return), loadable via "Analyze [SYMBOL] Date Range on TradeWave" links/QR codes:
- **RBOB Gasoline (RB):** Jan 25 - Mar 3, long, 25 yrs, 26/26 (100%), Sharpe 1.48, avg 17%, cumulative **4,805%**.
- **Gold (GC):** Dec 15 - Apr 28, long, 20 yrs, 18/20 (90%), Sharpe 0.8, avg 8%, **377%**; PE+2 variant Sep 26 - Feb 1, 6/6 (100%), Sharpe 1.57, **83%**.
- **Lean Hogs (HE):** Apr 9 - Apr 24 long, 44 yrs, 43/44, Sharpe 1.47, **14,920%**.
- **Feeder Cattle (GF):** PE+2, May 21 - Aug 17, 10/11, **156%**.
- **Crude Oil (CL):** Dec 1 - Mar 1 long, 11/13 winners (recurring multi-month long).
Treat cumulative-return figures as the long-run compounding case for **repeating the same calendar window every year**, and use deep Years Analyzed (40-60+ for equities) to judge robustness.

---

## 8. Operationalizing it: Portfolio Manager, reports, automation (Chapters 15-16, Appendix E)

The long-term investor's edge is *repeatability over years*, so the Portfolio Manager is central.

### Save the full configuration, not a chart
**Save Pattern (+ icon)** persists the entire generating CONFIGURATION: entry date, exit date, **direction**, days-in-window, **Years/lookback definition, group, tags, notes** — making every study reproducible. *"'8 years' and '8 PE2 years' are not the same dataset"* — the lookback choice is part of the edge and must be recorded.

### The 2026 dual Years column (critical for long-term records)
The **Years column** now expresses lookback two ways: a plain number = **Consecutive** (e.g. `20` = last 20 consecutive years), and **`PE2-N`** = election-cycle (e.g. `PE2-8` = last 8 midterm-year occurrences, spanning ~32 years). These are genuinely different datasets.

### Portfolio Manager as the long-running pattern library
- Maintain **separate portfolios by theme**: index/sector ideas, election-cycle setups, swing windows, paper-tracked strategies.
- Track each idea as a **virtual position** (# shares, invested $, live %) — for *context* (is the current year behaving normally vs. history?), not prediction — without manual spreadsheet upkeep.
- **Recall** any saved pattern instantly back into the Wave Viewer; **Calendar Notifications** push entry/exit windows (with ahead-of-start reminders) so you never miss the annual re-entry — *"seasonal edges often fail in execution, not research."*
- Portfolio summary footer: Security Purchase Price, # Shares, Total Current Value, Security Last Price, Total % Gain or Loss. Header shows the saved-pattern quota (e.g. "Saved Patterns 1382 / Remaining 618", ~2000 cap).

### Sharing with a financial advisor (Appendix E)
Save the opportunity (+), open Portfolio Manager, click the **report icon** to generate a **static, self-contained Custom TradeWave Report** (profit bar chart + Trend Chart + Stats Table + metric definitions). Share via email/social icons or **copy-URL**; optionally attach **PNG charts and CSV raw data**, plus a **"Load on Wave Viewer"** link so the advisor can interact, not just look. Reports are **static** — "they always show exactly what you saw, even years later." Email template subject: *"Seasonal Pattern Review - [Ticker] [Date Range]."*

### AI layer (read-only second opinion)
**TradeWave Research** (chatbot) reads your outputs to answer investor questions in plain English ("how much return happens early vs late in the window?", "does this work better in PE+2 than all years?", "compare this window to its reverse date-range window"), cutting analysis from 30 to 3 minutes. The **Confidence Overlay** gives a Green/Yellow/Red reliability rating *plus 2-4 bullet reasons* (sample size, return dispersion/outlier dependence, drawdown severity, modern-vs-older-regime consistency). Hard boundary: **"TradeWave generates the statistics. AI reads the statistics and produces research. AI never invents the statistics."**

---

## 9. The minimum long-term workflow (Chapter 19 / "Final Thoughts")

The exact onboarding loop for a new long-term investor:
1. **Log in; look at what's setting up now.**
2. **Pick ~10 familiar tickers.**
3. For each, run **Buy & Hold Analysis** and read: the favorable seasonal window, the **win rate**, the **drawdowns**, and how often the move has repeated.
4. Use **Reverse Date Range** to find the Best Seasonal Hold Window and confirm **Cumulative Ret > B&H**.
5. Optionally tighten with the **presidential-cycle filter** and the **TWR ≥ 1.5** quality filter.
6. **Prioritize consistency over the best-looking average** (use Median, year-bars, Sharpe — not just Avg Gain).
7. **Pick ONE style and commit for 90 days.** Build a **watchlist (Securities Group)** with notes.
8. **Define risk rules BEFORE entering:** max exposure, max loss, planned exit. Express via position holds, defined-risk options/covered calls, or the do-not-trade filter.
9. **Track results MONTHLY, not daily.** Repeat the same windows annually.

---

## 10. Mental-model guardrails for the long-term investor

- **TradeWave is a decision-framework / thinking tool, not a black box or auto-trader.** It gives context (favorable vs weak windows), not predictions. *"A tool should not replace thinking. It should improve thinking."*
- **Seasonality is probability, not protection.** A historically bullish window can still take heavy intra-trade heat (NVDA 2025: -23.16% MAE, finished only -5.22%) and recover. Position sizing and risk tolerance still matter.
- **A tendency is a historical frequency across comparable years, not a guaranteed script** for any single year (e.g. "19 of 20 years" is a fact; the year can also deliver strength beyond the window).
- **Every ticker has its own optimal window — test systematically, don't memorize a date range.**
- **Choose the right LENS before reading any chart** — mixing year types is exactly why most people conclude seasonality is "random." The headline long-term edges (100-Year Pattern; 35×/40×/6,220× multipliers) only appear once you isolate the regime and benchmark against B&H.
- **Diversify, sit out weak windows, compound the strong ones, and let the long-term core carry the wealth** while active trading stays the satellite. *"Financial freedom is not a single trade. It is what happens when your decisions stop being random, your risk stops being careless, and your process becomes repeatable."*
