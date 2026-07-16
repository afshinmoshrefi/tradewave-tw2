> **HISTORICAL AND SUPERSEDED. DO NOT EXECUTE THIS REDESIGN.** This is an archived
> creative-direction artifact, not a current product or pricing specification. Use
> [PRICING_STRATEGY.md](PRICING_STRATEGY.md) and
> [PRICING_QUOTA_SPEC.md](../PRICING_QUOTA_SPEC.md) for current decisions and limits.
> The executable homepage source is [site/generate_home_page.py](../../site/generate_home_page.py).

I'll synthesize the final spec. Let me work through the decision and build it directly.

The judges are unanimous: all three picked Direction 2 (The Ledger). The PM scored it 9, the retail trader 9, the brand strategist 9. The cross-pollination guidance is also consistent across all three judges. I have everything I need to synthesize without tool calls.

WINNER: Direction 2, The Ledger.

Why (3-4 sentences): All three judges independently chose The Ledger by a clear margin, because it wins on the one wound the whole category shares - trust - and does so with the same words for a hedge-fund PM (auditability), a once-burned retail trader (anti-scam reassurance), and a brand strategist (a position no competitor can clone, because a public pre-outcome ledger with losses left in is the one un-fakeable asset). It inverts the genre's reflex: every rival wins by making a bigger claim, while The Ledger wins by refusing to claim and handing over the evidence, which obeys the do-not-claim invariants natively rather than fighting them. It also carries the lowest execution risk, because the ledger, methodology, and loss row exist today, whereas the rival hero (Ask Anything) stakes itself on the still-gated MCP layer. The only thing it gives up is a half-beat of raw-power swagger in the hero and a touch-the-engine moment, both of which the judges told me exactly how to graft in.

Below is the build-ready spec. The grafts I resolved: (1) Direction 3's live hero ask-bar, repositioned as verification not conversion novelty (every judge's top transplant); (2) Direction 1's concrete power-nouns pulled into the hero subhead so depth lands in the first two seconds; (3) Direction 1's three-equal-panel engine router anchored by the same wave-viewer thumbnail, replacing The Ledger's prose self-select, with Direction 3's question-first card pattern and "segment on how you work, not how good you are" principle; (4) Direction 1's distinct "Desk - From $4,800/yr, talk to us" contact-sales strip; (5) Direction 3's "a neutral read is a real finding" line and the fuller market enumeration. One conflict resolved per the brand judge's caution: I keep The Ledger's claim-free verbs and never import the word "edge."

---

# TRADEWAVE HOME PAGE - FINAL BUILD-READY SPEC

## BASE DIRECTION: The Ledger (with grafts from The Open Engine + Ask Anything)

**Decision in brief:** All three judges (skeptical hedge-fund PM, once-burned retail swing trader, brand/conversion strategist) independently ranked The Ledger first at 9/9/9. It wins because trust is the category's deepest and most universal wound, and "we would rather be audited than believed" satisfies a capital allocator's due-diligence filter and a retail trader's anti-scam reflex with the identical words. Its differentiator is an asset competitors cannot fake (a public pre-outcome ledger with losses left in), not a feature they can eventually clone, and it is true today rather than staked on the still-gated MCP layer. The grafts below close its only gaps: a touch-the-engine hero ask-bar, power-nouns in the hero, and a concrete three-panel engine router.

---

## POSITIONING STATEMENT

TradeWave is the seasonal market research platform that shows its work. A deterministic engine computes per-year seasonal statistics from up to a century of end-of-day data across 15 markets, a 62-feature machine-learning model does one honest job - ranking what the engine finds - and the daily pick is written to a public forward ledger before the outcome is known, losses included. Where Seasonax hands you backtested charts and stops, and Financhill hands you a black-box score and a marketing funnel, TradeWave hands you the receipts under every answer and invites you to audit them. The one line: we would rather be audited than believed.

**One engine, three honest entry points - never three diluted messages.** The hero promise ("shows its work") is the rare line a skeptical PM, a working quant, and a self-directed retail trader all nod at, because rigor is the universal want and hype is the universal turn-off. The page resolves the three-audience tension structurally, with a quiet self-select router segmented on HOW YOU WORK, not how good you are (the explicit guard against the Tickeron Beginner/DIY downmarket trap), never with a mushy "for everyone" headline.

---

## HERO

- **Headline (title case, no terminal period):** Seasonal Market Research That Shows Its Work
- **Subhead:** TradeWave computes deterministic seasonal statistics from up to a century of end-of-day data across 15 markets, and a 62-feature model ranks what it finds. Ask for any of it in plain language, on the platform. The daily pick goes on the public record before the outcome is known - losses included.
- **CTA (the one sitewide CTA):** Start Free - 7 Days of Everything
- **Microcopy:** No credit card required. After the week, a free plan that stays useful.
- **Signature object - the ask-bar (grafted from Ask Anything, repositioned as VERIFICATION not conversion novelty):** A single input sits directly under the CTA with a slowly cycling placeholder question: "What's seasonal in US tech in the next two weeks?" then "Show me a July window on a Dow stock" then "Scan futures for windows opening this month." On submit, the page scrolls into the wave-viewer screenshot answering that exact question and surfaces the per-year results table and the deep link - not a chat reply. This is framed so a skeptic can operate the engine pre-signup and reproduce what they see; it is the strongest "verify it yourself" affordance on the page, not a toy. The cycling placeholder is the page's single piece of motion.
- **Visual:** One large wave-viewer screenshot in clean light-on-dark browser chrome (tradewave.ai/app), centered below the ask-bar, no autoplay. A major US index seasonal pattern with the longest available history loaded: the per-year results bar chart spanning 1986 to 2026 across the top, the seasonal projection (a 0-100 normalized index, never a price line) overlaid on the price chart beneath, and the top rows of the per-year results table pulling the eye downward - winning AND losing years both legible, because the losses are the point. A small Tara chat docked at the right edge mid-answer. Fresh capture required: no probability percentages legible in frame, no aggregate win totals, no cherry-picked standout number; model output renders as ordinal rank badges and unitless bars only.
- **Chips under the visual:** `15 Markets` | `Histories Up to a Century` | `One Public Ledger` (a fourth `Inside ChatGPT and Claude` chip is gated behind MCP_LIVE)
- **Caption (small caps):** THE WAVE-VIEWER. END-OF-DAY DATA, DETERMINISTIC STATISTICS.

---

## ORDERED SECTION LIST (FINAL COPY + LAYOUT)

### 1. The Three Rules
**Purpose:** Plant the entire trust thesis in three contract clauses at the hero seam, before any feature is explained - the spine the whole page hangs from.
**Copy:** `01 Deterministic by Design.   02 Receipts on Every Pattern.   03 Logged Before the Outcome.`
**Layout:** Full-width thin typographic band at the hero seam. Three numbered clauses set like the recitals of a contract - monospaced numerals, generous letter-spacing, hairline vertical dividers, minimal height, no icons. Reads as a standard you are holding the company to, not a feature list. Stacks on mobile.

### 2. Whoever's Asking, It Bends to You
**Purpose:** Resolve the three-audience tension with concrete self-select panels (grafted from The Open Engine's three-equal-panel router + Ask Anything's question-first cards), so the broad headline stays broad while each persona finds its own lane one click down - on the HOW-YOU-WORK axis, never a downmarket skill axis. Replaces The Ledger's plainer prose strip.
**Copy:**
- Eyebrow: One Platform, Three Desks.
- Headline: Whoever's Asking, It Bends to You
- Body: The engine does not care whether you are a fund running a thousand backtests or a trader testing one hunch you have carried for years. You ask at your own altitude; it answers at the same depth. No tier is a different product - it is the same engine, the same receipts, and the same century of evidence, priced to the job in front of you.
- **Panel 1 - Independent and Active Traders.** Question (mono): "What's seasonal in tech right now?" Answer: Ask in plain language and get ranked windows with the full per-year history under each. Start free for seven days with every market and every metric, then keep a free plan that stays useful. The daily public-record pick is yours every day at no cost. Link: See the retail view.
- **Panel 2 - Professionals, Quants and RIAs.** Question (mono): "Give me the strongest 30-to-60-day windows across all 15 markets, ranked by Sharpe." Answer: Full lookback, PE-cycle and date-range knobs, CSV into your own model, on-demand research reports, and deep links that hand a colleague the exact pattern, years, and settings you see. Built for a desk, not a demo. Link: See Strategist.
- **Panel 3 - Funds and Enterprise.** Question (mono): "Pull the ranked patterns into our own code." Answer: License the historical pattern file and the trained model for internal backtests over a compiled, multi-decade dataset. A derived-data-only REST API with high rate limits, multi-seat keys, redistribution rights, SSO and audit. One clean source of data and receipts instead of rebuilding the pipeline. Your agent can write a backtest; it cannot make it true. Link: Talk to us. {MCP_LIVE: until the flag flips, soften the API/MCP line to "deep links, CSV exports, and the historical pattern file for internal research."}

**Layout:** Three equal-width panels in one row (stacked on mobile), each headed by the SAME small wave-viewer thumbnail so the shared engine is literal, not implied (graft from The Open Engine). Each panel leads with a monospaced sample QUESTION in quotes, then a plain-language answer, then a quiet text link (two route to "Start Free," the third to "Talk to us"). Restrained borders, no icons, no pricing here. Equal visual weight signals retail is not a second-class citizen.

### 3. Underneath Every AI Answer: Up to a Century of Receipts
**Purpose:** Establish the deterministic engine as the credibility anchor (depth = power, breadth = serious infrastructure) and out-rigor Seasonax's backward-averaged curve by surfacing the complete per-year record under every pattern.
**Copy:**
- Eyebrow: You've noticed it for years.
- Headline: Underneath Every AI Answer: Up to a Century of Receipts
- Body: The same calendar window, the same behavior, year after year - most serious traders carry a private list of these hunches, while the evidence stayed folklore: almanac pages, screenshots, other people's conviction. TradeWave was built to test them with statistics, not stories. A deterministic engine computes seasonal patterns from end-of-day data across 15 markets - US and global equities, indices, ETFs, futures and commodities, currencies, government bonds, and crypto - on histories that reach back as far as a century. Open any pattern and its complete record is on the table: every historical year's individual result, win consistency, average return, Sharpe, the TradeWave Ratio, the MFE/MAE intraperiod-risk band, and PE-cycle overlays that read the pattern against the presidential-election cycle. The same inputs always produce the same answer - no black box, no hand-picked backtest window. Every exact view carries a deep link, so the pattern you found is the pattern a colleague opens.
- Caption: Up to a century of seasonality, measured to the day.

**Layout:** Centered text block above a full-bleed wave-viewer screenshot. A magnified inset of the per-year results table sits bottom-right with a hairline frame (wins and losses both visible; label "sample data, for layout" if recreated). Three thin callout labels point into the image: per-year results / deep link / PE-cycle overlay. Airy margins around a deliberately dense screenshot - the density-as-depth contrast (see Brand System). The fuller market enumeration here is the graft from The Open Engine (concrete breadth nouns reassure the skeptic the 15 markets are real).

### 4. Machine Learning With One Honest Job: Ranking
**Purpose:** Defuse AI hype by scoping the model precisely - it orders the list, it does not promise outcomes - the credibility Tickeron and Financhill forfeit, and tee up the public ledger as the payoff of the scan.
**Copy:**
- Eyebrow: AI layer one - rank it.
- Headline: Machine Learning With One Honest Job: Ranking
- Body: One scan sweeps all 15 markets and surfaces the setups entering their seasonal window now. A separate gradient-boosted model reads 62 features of every qualifying setup and produces a ranking used for exactly one thing: ordering the list. It does not promise outcomes. The statistics stay deterministic - the model only decides what you look at first. A neutral result is a real finding, not weak support. Once a day, that ranking plus rules selects a single pick, and it is logged in public before the outcome is known, losses included.
- Screenshot tag on the top row: Today's pick - logged to the public ledger.

**Layout:** Two-column. Copy left, the opportunities-table screenshot right with model output as ordinal rank badges and unitless bars only - no percentages in frame. The top row carries a small tag chip reading "logged to the public ledger." Symbols span multiple asset classes (a US stock, an ETF, a future, a global equity) to reinforce 15-market breadth visually. The three distinct win rates (historical_win_rate, ml_win_prob, track_record.win_rate) are never named together here; this section speaks only to ranking. The "a neutral read is a real finding" line is the graft from Ask Anything.

### 5. Ask the Chart. Watch It Answer
**Purpose:** Show the modern conversational layer Seasonax and Financhill both lack, framed strictly as an interface to the same statistics, reinforcing auditability instead of diluting it. Live in production, NOT gated.
**Copy:**
- Eyebrow: AI layer two - talk to it.
- Headline: Ask the Chart. Watch It Answer
- Body: Tara is how you question the platform out loud. Ask why a setup ranks where it does, and the answer cites that pattern's own table: the years, the consistency, the risk. Ask to see something else, and the wave-viewer changes in front of you. Tara is an interface to the same statistics, not another opinion - the evidence lands on screen, not in adjectives. A first-week trader and a twenty-year quant ask Tara the same question and get the same receipts back.
- Caption: The chart just changed.

**Layout:** Centered copy above a full-width split screenshot: wave-viewer left (chart visibly AFTER an update), Tara chat docked right showing one real two-message exchange that moved the chart. Before/after chart states distinguishable so chat-drives-the-viewer reads from the still. Mark "sample exchange, for layout" if recreated. Not gated.

### 6. TradeWave Works Inside ChatGPT and Claude {ENTIRE SECTION GATED: MCP_LIVE}
**Purpose:** Claim the category-first differentiator - the same engine and receipts inside the assistant the buyer already uses, plus a derived-data-only API for the enterprise lane.
**Copy:**
- Eyebrow: AI layer three - take it with you. [Badge: New]
- Headline: TradeWave Works Inside ChatGPT and Claude
- Body: Add TradeWave to ChatGPT, Claude, or any MCP-capable assistant and sign in with your TradeWave account. Then just ask: scans, pattern analysis, plain language - the same engine and the same receipts, inside the tools you already use. Building your own stack? A derived-data-only REST API comes with a developer portal, Python and TypeScript SDKs, an interactive playground, and full documentation. Your agent can write a backtest. It cannot make it true. We give it clean data, a trained model, and forward-tested receipts to check against.
- CTA band: Start Free - 7 Days of Everything / No credit card required.

**Layout:** Two-column. Real ChatGPT-window screenshot left (connector enabled, a scan request answered in derived-data-only terms - percentages and a normalized 0-100 curve, never a price). Copy right with a small developer-portal inset card (Try-it console, OpenAPI and Postman download chips, llms.txt). Full-width CTA band beneath. Entire block conditionally rendered on MCP_LIVE; hidden until the connector is publicly reachable. The hero's fourth chip and the Section 2 Panel 3 API line gate with this flag.

### 7. A Tuesday With TradeWave
**Purpose:** Translate capability into a working desk routine - an operational pipeline, not a lookup tool - quietly serving the pro and enterprise lanes (CSV into their model, on-demand reports, deep-link handoff) without segment labels.
**Copy:**
- Eyebrow: Built for a desk, not a demo.
- Headline: A Tuesday With TradeWave
- Timeline: 8:50 - Your calendar pings: a pattern window on your watchlist opens Thursday. 9:15 - You export the stats table to CSV and drop it into your own model. 11:00 - A date-range research report across your portfolio, generated on demand. 2:40 - You send a teammate a deep link that opens the exact pattern, years, and settings you see.
- Closing line: Nothing here required remembering to check a dashboard.

**Layout:** Horizontal day-timeline strip, four timestamps each anchored by a small genuine screenshot (calendar event / CSV in a spreadsheet / generated report / deep-linked chart). Vertical stack on mobile. Mono timestamps in the accent color. Documentary tone, no illustration, no hype.

### 8. We Do Not Ask for Trust. We Publish the Ledger
**Purpose:** The emotional and strategic peak. Published methodology plus a public forward ledger with a loss row plainly visible - the un-fakeable asset no competitor has, and where "verify any number on this page" lives. Referenced by the hero's "One Public Ledger" chip.
**Copy:**
- Eyebrow: Accountability.
- Headline: We Do Not Ask for Trust. We Publish the Ledger
- Body: The methodology is public: what we compute, how, and what it cannot tell you - read it before you trust a single number. The model's daily pick is written to a public forward ledger before the outcome is known, and it stays there: losses included, nothing removed. Anyone can audit the live record, even an AI agent. TradeWave is an educational research platform - no performance promises, just instruments you can check. We would rather be audited than believed.
- Links: Read the methodology -> /methodology | Inspect the ledger -> /scorecard
- Provenance card: "I built the instrument I could not buy." - Afshin Moshrefi, founder, Tara Data Research LLC, author of The 100-Year Pattern (2026).
- CTA band: Start Free - 7 Days of Everything / No credit card required.

**Layout:** Centered copy above two side-by-side screenshot panels: the /scorecard page left with a LOSS row plainly visible and unhidden in normal data color, the methodology page right. Two text links beneath, then a quiet founder-provenance card (small headshot afshin-profile-pic.jpg, single quote, byline - framed as authorship, never styled as a testimonial), then the CTA band. The loss row is intentionally not minimized; it is the proof and the single most persuasive pixel on the page.

### 9. On the Record, Like Everything Else Here {SHIPS HIDDEN until >=2 real named quotes}
**Purpose:** House real third-party credibility (name + role + market focus) under the same auditable-truth ethos. Disciplined emptiness is itself a trust signal.
**Copy:**
- Headline: On the Record, Like Everything Else Here
- Framing line: Early users - independent traders, advisors, and quants - on rigor, depth, and where TradeWave fits in their day.
- Editorial law: performance quotes are rejected; quotes speak only to rigor, depth, and workflow, with full name, role, and market focus. Never founder-as-testimonial.

**Layout:** Three restrained quote cards (serif pull-quote, full name, role, market focus). No star ratings, no logo wall, no anonymous initials, no placeholders. Section omitted from render until the >=2-named-quotes gate is met.

### 10. Start With Everything. Pay Only If It Earns Its Place on Your Desk
**Purpose:** Convert with the reverse-trial ladder - generous trial, then a free plan that stays useful, an entry tier just under the incumbent, the marketed hero tier, and a Desk anchor that makes the middle read as serious and opens the enterprise conversation. Transparency is itself a trust edge over both opaque competitors.
**Copy:**
- Ribbon: Every signup starts with 7 days of the full platform.
- Headline: Start With Everything. Pay Only If It Earns Its Place on Your Desk
- Body: Create a free account and get everything for 7 days: every market, every metric, the model and Tara included. After the week, stay on Explorer free for as long as you like, or go Analyst at $47/mo ($37/mo billed yearly) or Strategist at $149/mo ($99/mo billed yearly). Paid plans carry a 7-day trial. Cancel anytime. Running a fund or a team that wants API, MCP, multi-seat keys, and the pattern file? Talk to us about Desk.
- Per-column feature checklists: **Explorer (free)** - DJ30 market, top patterns, 1 portfolio, daily pick + public ledger, community support. **Analyst** - US stocks + ETFs, more patterns, ML ranking + custom start dates, CSV + calendar alerts, portfolios + watchlists, email support. **Strategist** (marketed tier) - all 15 markets, most patterns, ML ranking + PE-cycle filters, CSV + alerts + on-demand reports, deep links, Tara, [API and MCP access]{MCP_LIVE}, premium support.
- Kicker: Every tier runs the same engine and the same receipts, starting at $0.
- NOTE: Explorer/Analyst/Strategist prices render from live Stripe metadata (product_line=eod) at build time, never hardcoded.

**Layout:** Single ribbon line above a three-column self-serve table (Explorer / Analyst / Strategist, Strategist marked the marketed tier), monthly-yearly toggle defaulting to yearly, same CTA under each column, kicker beneath. A quiet, visually distinct fourth strip sits below the table: `Desk - From $4,800/yr - pattern file + model + API - Talk to us` routing to contact-sales, never a self-serve price (graft from The Open Engine: lets a PM gauge there IS a serious enterprise tier without a demo wall). The [API and MCP access] checklist row on Strategist gates with MCP_LIVE.

### 11. What the Engine Sees This Week / Bring Your Hunches
**Purpose:** Prove the operation is alive and expert-run (dated-content credibility cue), then close on the retail-resonant emotional core - the trader's private list of carried hunches - and carry the mandatory disclaimer footer.
**Copy:**
- Living strip headline: What the Engine Sees This Week
- Living body: Seasonal Market News covers what the engine sees in current markets. The Insights library teaches the method - how the statistics are built, and what up to a century of data can and cannot justify. Real articles, real dates, free to read: what the platform is thinking, before you ever create an account. Link: Browse the library.
- Closing band headline: Bring Your Hunches
- Closing body: Test the calendar windows you've carried for years against up to a century of receipts - in the platform, with Tara beside the chart. Seven days of everything, free. A free plan that keeps working after.
- Button: Start Free - 7 Days of Everything / No credit card required.
- Footer: TradeWave is an educational research platform operated by Tara Data Research LLC. Nothing on this site is investment, financial, or trading advice, or a recommendation to buy or sell any security or instrument. Seasonal statistics describe historical behavior; historical behavior does not guarantee future results. All trading and investing involves risk, including the possible loss of principal.
- Footer links: Methodology | Scorecard | Insights | Seasonal Market News | Pricing | Terms | Privacy | Contact | Disclaimer

**Layout:** Living-research card row (auto-fed: 3 latest Seasonal Market News articles + 1 Insights explainer, real dates visible), MailerLite daily-pick capture folded into this strip (no mid-page capture section). Then a calm full-width closing band with one centered CTA. Then the complete disclaimer footer. {When MCP_LIVE is on, the closing body may append ", or inside ChatGPT and Claude" to the access list.}

---

## VISUAL / BRAND SYSTEM

**Name:** The Ledger. **Aesthetic:** institutional-grade calm meets a courtroom evidence file - it should look like it belongs next to a Bloomberg panel, read as friendly as Koyfin, and carry the moral seriousness of a document you can be held to.

**Palette:** deep charcoal-to-navy ground (#0B1220 base, #0F1A2E panels) with crisp near-white text (#EAF0F8). Exactly one signal accent - TradeWave purple from the existing wordmark (#7C5CFF) - used only for the live wave/brand, the ask-bar focus state, rank bars, links, and the single CTA. Color is otherwise reserved strictly for DATA: the existing red/pink per-year bars, green/teal price series, neutral grey for locked/blurred state. A loss row on the scorecard is shown in the normal data color, never hidden or de-emphasized. No decorative color, no gradients-for-mood, no gamified brights; at most one subtle radial behind the hero shot.

**Typography:** a clean modern sans (Inter or near-equivalent) for headlines and body, title case with no terminal period per the invariant. A precise monospaced, tabular-numeral face for ALL statistics, the three-rules numerals, the timeline timestamps, the deep links, and the sample questions in the audience cards - numbers must feel measured, never marketed. A single restrained serif is permitted only for the testimonial pull-quotes (the editorial "on the record" touch). Triadic, contract-like cadence in headers ("Deterministic by Design. Receipts on Every Pattern. Logged Before the Outcome.").

**Density paradox (the core bridge technique, articulated as a deliberate principle, grafted from The Open Engine):** the product screenshots are deliberately dense and busy - the wave-viewer, the per-year bars, the opportunity table, the scan - so density reads as institutional depth and proves the engine can handle complexity; meanwhile the marketing layout wrapping them is spacious with heavy section breathing room, so whitespace reads as clarity and approachability. That contrast is the entire bridge between the enterprise, pro, and retail audiences. Every section earns its scroll before the next CTA band appears.

**Imagery:** real product UI only, captured fresh per the spec rules (no legible probability percentages, no aggregate win totals, model scores as rank badges/unitless bars, no price levels). The wave-viewer is the hero object exactly as Seasonax makes the seasonal chart its hero - but ours shows the receipts table too, which theirs never does. Browser-chrome frames around every screenshot. Zero stock photography, zero trader-staring-at-six-monitors cliche, zero icon-grid feature blocks. The one human image is the small founder-provenance headshot, framed as authorship not endorsement. Note: the existing product-demo.webp shows legible Win%/AIS/price and must be re-captured before reuse; the Anne-Marie/Erin testimonial videos are removed until re-shot under the new rules.

**Motion:** near-zero by mandate. The ONLY motion is the hero ask-bar's slowly cycling placeholder question and the calm scroll of the living-research dates; post-MCP_LIVE, a single tasteful before/after still of the chat-drives-the-viewer mechanic. No parallax, no autoplay video, no counters, no animated stats, no popups, no exit-intent, no sticky bars, no tab-title scripts, no user-count copy. The page lives in dark by default to read as a professional terminal. Restraint and honesty are the brand's whole visual argument.

---

## TOP-TO-BOTTOM ASCII WIREFRAME

```
+==============================================================================+
|  TradeWave (purple wordmark)        Wave Viewer   News   Pricing   [Sign in] |
+==============================================================================+
|                                                                              |
|              Seasonal Market Research That Shows Its Work                    |
|                                                                              |
|   TradeWave computes deterministic seasonal statistics from up to a century  |
|   of end-of-day data across 15 markets, and a 62-feature model ranks what    |
|   it finds. Ask for any of it in plain language, on the platform. The daily  |
|   pick goes on the public record before the outcome is known - losses incl.  |
|                                                                              |
|                 [  Start Free - 7 Days of Everything  ]                      |
|                 No credit card required. Free plan after.                    |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  | > "What's seasonal in US tech in the next two weeks?"          [ Ask ] |  | <- LIVE ASK-BAR (cycling placeholder) = verify-the-engine object
|  +------------------------------------------------------------------------+  |
|                                                                              |
|  +-- tradewave.ai/app --------------------------------------------------+    |
|  |  per-year bars 1986 ----------------------------------------- 2026    |    |
|  |  [win][LOSS][win][win][LOSS][win] ... losses legible      +--------+  |    |
|  |  ---- seasonal projection (0-100 index) over price chart  | Tara   |  |    |
|  |  opp table edge: DATE TICKER DAYS DIR SR [rank badge]     | answer |  |    |
|  +----------------------------------------------------------------------+    |
|        THE WAVE-VIEWER. END-OF-DAY DATA, DETERMINISTIC STATISTICS.            |
|     [ 15 Markets ]  [ Histories Up to a Century ]  [ One Public Ledger ]     |
|                                       ( [ Inside ChatGPT+Claude ] = MCP_LIVE )|
+------------------------------------------------------------------------------+
|  01 Deterministic by Design.  | 02 Receipts on Every Pattern. | 03 Logged   |
|                               |                               | Before the   |
|                               |                               | Outcome.     |  (thin contract band)
+==============================================================================+
|  One Platform, Three Desks                                                   |
|                  WHOEVER'S ASKING, IT BENDS TO YOU                           |
|  +------------------+   +------------------+   +-----------------------+      |
|  | [wv thumbnail]   |   | [wv thumbnail]   |   | [wv thumbnail]        |      |  <- SAME wave-viewer thumbnail anchors all three
|  | INDEPENDENT &    |   | PROS, QUANTS &   |   | FUNDS & ENTERPRISE     |      |
|  | ACTIVE TRADERS   |   | RIAs             |   |                        |      |
|  | "What's seasonal |   | "Strongest 30-60d|   | "Pull the ranked       |      |  <- question-first (mono)
|  |  in tech now?"   |   |  windows, all 15,|   | patterns into our code"|      |
|  | ranked windows + |   |  by Sharpe."     |   | pattern file + model   |      |
|  | full per-yr hist |   | knobs, CSV, deep |   | lic., API/MCP*, seats, |      |
|  | free plan stays  |   | links, reports.  |   | SSO, redistribution.   |      |
|  | useful.          |   | desk not a demo. |   | agent can't make it    |      |
|  | > See retail view|   | > See Strategist |   | true. > Talk to us     |      |
|  +------------------+   +------------------+   +-----------------------+      |
|  Not different products - same engine, same receipts, priced to the job.     |
+==============================================================================+
|  You've noticed it for years.                                                |
|        UNDERNEATH EVERY AI ANSWER: UP TO A CENTURY OF RECEIPTS               |
|  15 markets - US + global equities, indices, ETFs, futures & commodities,    |
|  currencies, government bonds, crypto - histories back as far as a century.  |
|  Same inputs, same answer. No black box. No hand-picked window. Deep link.   |
|  +======================== full-bleed wave-viewer ====================+      |
|  |  per-year bars + price + projection      +---------------------+    |      |
|  |  <-per-year results  <-deep link          | PER-YEAR TABLE INSET|    |      |
|  |  <-PE-cycle overlay                       | 1986 +x% .. 2002 -x%|    |      |  <- wins AND losses
|  +---------------------------------------------------------------------+      |
|        Up to a century of seasonality, measured to the day.                  |
+==============================================================================+
|  AI layer one - rank it                                                      |
|  MACHINE LEARNING WITH ONE HONEST JOB: RANKING   | +----------------------+  |
|  One scan, all 15 markets. A 62-feature model    | | [logged to ledger]   |  |
|  reads features and orders the list. It does not | | TICK(stk) DIR [#1]    |  |
|  promise outcomes. A neutral result is a real    | | TICK(ETF) DIR [#2]    |  |
|  finding, not weak support. Once a day, ranking  | | TICK(fut) DIR [#3]    |  |
|  + rules pick one, logged in public before the   | | TICK(gbl) DIR [bars] |  |  (mixed asset classes)
|  outcome, losses included.                       | | (NO % in frame)      |  |
|                                                  | +----------------------+  |
+==============================================================================+
|  AI layer two - talk to it                                                   |
|                  ASK THE CHART. WATCH IT ANSWER                              |
|  +----------------------- split screenshot ------------------------+         |
|  |  wave-viewer (chart AFTER, visibly changed)  | Tara chat        |         |
|  |                                              | > why rank here? |         |
|  |                                              | < cites the table|         |
|  |                                              | > show me April  |         |
|  |                                              | [chart updates ^]|         |
|  +-----------------------------------------------------------------+         |
|                        The chart just changed.                               |
+==============================================================================+
|  AI layer three - take it with you        [ New ]    { ENTIRE: MCP_LIVE }    |
|  +------------------------------+   TRADEWAVE WORKS INSIDE CHATGPT AND CLAUDE |
|  | [ ChatGPT window screenshot ]|   Sign in with your account. Scans,         |
|  | connector enabled, scan      |   pattern analysis, plain language, same   |
|  | answered, derived-data %     |   engine, same receipts. Building a stack?  |
|  | (no price)                   |   Derived-data REST API + portal + SDKs.   |
|  +------------------------------+   [ inset: Try it / OpenAPI / Postman ]     |
|  [============  Start Free - 7 Days of Everything | No card  ============]    |
+==============================================================================+
|  Built for a desk, not a demo                                                |
|                     A TUESDAY WITH TRADEWAVE                                 |
|  8:50 --------- 9:15 ----------- 11:00 ------------- 2:40                     |
|  [calendar]     [CSV in sheet]   [report]            [deep-link chart]        |
|  window opens   export to model  report on portfolio teammate opens exact    |
|        Nothing here required remembering to check a dashboard.               |
+==============================================================================+
|  Accountability                                                              |
|        WE DO NOT ASK FOR TRUST. WE PUBLISH THE LEDGER                        |
|  Methodology is public. The daily pick is logged before the outcome,         |
|  losses included, nothing removed. We would rather be audited than believed. |
|  +------------------------+        +------------------------+                |
|  | /scorecard             |        | /methodology           |                |
|  | pick  date  result     |        | what we compute, how,  |                |
|  | XXX   ...   WIN         |        | and what it cannot     |                |
|  | YYY   ...   LOSS  <-----| visible| tell you               |                |  <- loss row NOT minimized
|  +------------------------+        +------------------------+                |
|  Read the methodology ->     Inspect the ledger ->                           |
|  +----------------------------------------------------------+                |
|  | [photo] "I built the instrument I could not buy."        |                |
|  |  Afshin Moshrefi, Tara Data Research LLC, author of      |                |
|  |  The 100-Year Pattern (2026)                             |                |
|  +----------------------------------------------------------+                |
|  [============  Start Free - 7 Days of Everything | No card  ============]    |
+==============================================================================+
|  ON THE RECORD, LIKE EVERYTHING ELSE HERE   { HIDDEN until >=2 named quotes } |
|  [ "...rigor" ]      [ "...depth" ]      [ "...workflow" ]                    |
|   Name, Role, Focus   Name, Role, Focus   Name, Role, Focus                  |
+==============================================================================+
|  Every signup starts with 7 days of the full platform.  [ Monthly | YEARLY ] |
|     START WITH EVERYTHING. PAY ONLY IF IT EARNS ITS PLACE ON YOUR DESK       |
|  +-------------+   +-------------+   +==============+                         |
|  | EXPLORER    |   | ANALYST     |   | STRATEGIST * |   (* = marketed tier)   |
|  | $0          |   | $37/mo yr   |   | $99/mo yr    |   (prices <- live       |
|  | DJ30        |   | $47 mo      |   | $149 mo      |    Stripe metadata)     |
|  | daily pick  |   | US+ETFs,ML  |   | all 15 mkts, |                         |
|  | + ledger    |   | CSV,alerts  |   | PE knobs,    |                         |
|  | 1 portfolio |   | portfolios  |   | reports,Tara,|                         |
|  |             |   |             |   | [API/MCP]*   |                         |
|  | [Start Free]|   | [Start Free]|   | [Start Free] |                         |
|  +-------------+   +-------------+   +==============+                         |
|  [ Desk - From $4,800/yr - pattern file + model + API - Talk to us ]         |  <- contact-sales strip, visually distinct
|   Every tier runs the same engine and the same receipts, starting at $0.     |
+==============================================================================+
|  WHAT THE ENGINE SEES THIS WEEK   (living research, real dates)              |
|  [news 06-15] [news 06-13] [news 06-11] [insights explainer]                 |
|  Browse the library ->            (MailerLite daily-pick capture folded here) |
|  - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - |
|                          BRING YOUR HUNCHES                                  |
|   Test the calendar windows you've carried for years against up to a         |
|   century of receipts. Seven days of everything, free. Free plan after.      |
|                 [  Start Free - 7 Days of Everything  ]                      |
|                 No credit card required.                                     |
+------------------------------------------------------------------------------+
|  TradeWave is an educational research platform operated by Tara Data         |
|  Research LLC. Nothing here is investment, financial, or trading advice...   |
|  historical behavior does not guarantee future results. Risk of loss.        |
|  Methodology | Scorecard | Insights | Seasonal Market News | Pricing |       |
|  Terms | Privacy | Contact | Disclaimer                                      |
+==============================================================================+
  * = gated behind MCP_LIVE build flag until the connector is publicly reachable
```

---

## INVARIANT COMPLIANCE CHECK

- No win-rate / return / accuracy / performance claims anywhere; ML rendered as ordinal rank badges / unitless bars only; no aggregate win totals or standout numbers in screenshots. PASS
- Derived-data only: seasonal curve is a 0-100 normalized index, never a price; no OHLCV / price levels in any shown API or ChatGPT response. Three win rates kept distinct, never conflated. PASS
- No em-dashes; spaced hyphen " - " used throughout. PASS
- 15 markets canonical everywhere (never a different count; ids 0-13 and 16, hole kept). PASS
- Title-case display headlines, no terminal period. PASS
- One CTA sitewide ("Start Free - 7 Days of Everything" + "No credit card required."). PASS
- No popups / exit-intent / sticky bars / counters / user-count copy / tab-title scripts. PASS
- Educational research platform positioning + mandatory disclaimer footer; ML "one honest job: ranking," a neutral read is a real finding. PASS
- Prices render live from Stripe metadata, never hardcoded. PASS
- MCP/API behind MCP_LIVE flag (hero chip, Section 2 Panel 3 API line, Section 6 entirely, Strategist API row, closing-band ChatGPT clause); enterprise SSO/SCIM is contact-sales, not self-serve. PASS
- Testimonials ship hidden until >=2 real named quotes; never founder-as-testimonial; founder card framed as authorship. PASS
