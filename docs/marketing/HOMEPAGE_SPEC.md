# tradewave.ai Home Page - Final Spec (v1)

> Produced 2026-06-11 by an 11-agent tournament: 5 creative directors (5 strategic angles:
> AI-era desk / instrument / auditable platform / workflow / discovery), a 4-judge panel
> (skeptical institutional PM, CRO expert, brand strategist, retail trader), executive
> synthesis, and a red team (hype + truth + weakness attack; all 15 tagged fixes applied
> below, including the 15-active-markets correction verified against config.py and commit
> fd114fc). This file IS the page: copy is final-quality; layout notes are per section.

**POSITIONING (internal north star):** TradeWave is the seasonal research platform that
shows its work: up to a century of deterministic per-year receipts under every answer, AI
welded to named mechanisms as the payoff rather than the premise, and a public pre-outcome
ledger in place of every performance claim.

**THE LAUNCH FLAG:** one build flag (`MCP_LIVE`) gates every MCP/API mention: the hero's
third chip + ChatGPT clause, section 5 entirely, and the pricing checklist row "API and MCP
access". Flip it the day the connector is publicly reachable. (Tara section is NOT gated:
chat-drives-the-viewer is live in the production UI per the owner.)

**PAGE-WIDE RULES:** one CTA everywhere: "Start free - 7 days of everything" + "No credit
card required." beside it. No win rates, return figures, or performance promises anywhere.
No popups, no exit-intent, no tab-title scripts, no sticky bars, no counters, no user-count
copy. Product screenshots argue; copy stays short. No em dashes (" - "). Display headlines (hero, section H2s) are TITLE CASE (AP style: capitalize words of 4+ letters and all major words; a/an/the/of/to/in/on stay lowercase) and carry NO terminal period. Screenshots must
contain no aggregate win totals or cherry-picked standout numbers; model scores render as
ordinal rank badges or unitless bars, never as probability percentages legible in frame.

---

## HERO
Layout: calm full-width; headline + subhead left-weighted or centered, one CTA, large
screenshot below; three quiet text chips under the CTA. No motion.

- **Headline:** Seasonal Market Research That Shows Its Work
- **Subhead:** TradeWave computes deterministic seasonal statistics from up to a century of
  end-of-day data, and a machine-learning model ranks what it finds. Ask for any of it in
  plain language - on the platform[, or inside ChatGPT and Claude]{MCP_LIVE}. The daily pick
  goes on the public record before the outcome is known - losses included.
- **CTA:** Start free - 7 days of everything
- **Microcopy:** No credit card required. After the week, a free plan that stays useful.
- **Chips:** 15 Markets | Histories Up to a Century | [Works Inside ChatGPT and Claude]{MCP_LIVE}
- **Visual:** one large wave-viewer screenshot in clean browser chrome: a major US index
  seasonal pattern with the longest available history loaded, seasonal wave overlaid on
  price, top of the per-year results table visible beneath - winning AND losing years
  legible, pulling the eye down. Caption: "The wave-viewer. End-of-day data, deterministic
  statistics."

## 1. THE THREE RULES (pillar strip)
Layout: full-width thin typographic band at the seam under the hero - three numbered
clauses set like contract lines; minimal height.

> 01 Deterministic by Design.  02 Receipts on Every Pattern.  03 Logged Before the Outcome.

## 2. THE RECEIPTS (the deterministic engine)
Layout: centered text block above a full-bleed wave-viewer screenshot; magnified inset of
the per-year table bottom-right; three thin callout labels (per-year results / deep link /
PE overlay).

- **Eyebrow:** You've noticed it for years.
- **Headline:** Underneath Every AI Answer: Up to a Century of Receipts
- **Body:** The same calendar window, the same behavior, year after year - most serious
  traders carry a private list of these hunches, while the evidence stayed folklore:
  almanac pages, screenshots, other people's conviction. TradeWave was built to test them:
  statistics, not stories. A deterministic engine computes seasonal patterns from end-of-day
  data across 15 markets - US and global equities, indices, ETFs, futures, currencies,
  crypto - on histories that reach back as far as a century. Open any pattern and its
  complete record is on the table: every historical year's individual result, win
  consistency, average return, Sharpe, the TradeWave Ratio, MFE/MAE intraperiod risk, and
  PE-cycle overlays. The same inputs always produce the same answer - no black box, no
  hand-picked backtest window. Every exact view carries a deep link, so the pattern you
  found is the pattern a colleague opens.
- **Caption:** Up to a century of seasonality, measured to the day.

## 3. RANKED BY THE MODEL (the scan)
Layout: two-column; copy left, opportunities-table screenshot right (scores as rank badges
or unitless bars - no percentages in frame).

- **Eyebrow:** AI layer one - rank it
- **Headline:** Machine Learning With One Honest Job: Ranking
- **Body:** One scan sweeps all 15 markets. A separate gradient-boosted model reads 62
  features of every qualifying setup and produces a ranking used for exactly one thing:
  ordering the list. It does not promise outcomes. The statistics stay deterministic - the
  model only decides what you look at first. Once a day, that ranking plus rules selects a
  single pick, and it is logged in public before the outcome is known, losses included.
- **Screenshot tag (top row):** Today's pick - logged to the public ledger

## 4. ASK THE CHART (Tara)
Layout: centered copy above a full-width split screenshot: wave-viewer left, Tara chat
docked right showing one real two-message exchange that visibly moved the chart.

- **Eyebrow:** AI layer two - talk to it
- **Headline:** Ask the Chart. Watch It Answer
- **Body:** Tara is how you question the platform. Ask why a setup ranks where it does, and
  the answer cites that pattern's own table: the years, the consistency, the risk. Ask to
  see something else, and the wave-viewer changes in front of you. Tara is an interface to
  the same statistics, not another opinion - the evidence lands on screen, not in adjectives.
- **Caption:** The chart just changed.

## 5. INSIDE CHATGPT AND CLAUDE (MCP + API) {ENTIRE SECTION BEHIND MCP_LIVE}
Layout: two-column; real ChatGPT-window screenshot left (connector enabled, a scan request
answered), copy right with a developer-portal inset card; full-width CTA band beneath.

- **Eyebrow:** AI layer three - take it with you  [Badge: New]
- **Headline:** TradeWave Works Inside ChatGPT and Claude
- **Body:** Add TradeWave to ChatGPT, Claude, or any MCP-capable assistant and sign in with
  your TradeWave account. Then just ask: scans, pattern analysis, plain language - the same
  engine and the same receipts, inside the tools you already use. Building your own stack?
  A signals-only REST API comes with a developer portal, SDKs, and full documentation.
- **CTA band:** Start free - 7 days of everything / No credit card required.

## 6. A TUESDAY WITH TRADEWAVE (workflow)
Layout: horizontal day-timeline strip, four timestamps each anchored by a small genuine
screenshot (calendar event / CSV in a spreadsheet / report / deep-linked chart); vertical
on mobile.

- **Eyebrow:** Built for a desk, not a demo
- **Headline:** A Tuesday With TradeWave
- **Timeline:**
  - 8:50 - Your calendar pings: a pattern window on your watchlist opens Thursday.
  - 9:15 - You export the stats table to CSV and drop it into your own model.
  - 11:00 - A date-range research report across your portfolio, generated on demand.
  - 2:40 - You send a teammate a deep link that opens the exact pattern, years, and
    settings you see.
- **Closing line:** Nothing here required remembering to check a dashboard.

## 7. THE LEDGER (methodology + accountability)
Layout: centered copy above two side-by-side screenshot panels (scorecard left with a loss
row plainly visible, methodology page right); text links + founder provenance card + CTA
band below.

- **Eyebrow:** Accountability
- **Headline:** We Do Not Ask for Trust. We Publish the Ledger
- **Body:** The methodology is public: what we compute, how, and what it cannot tell you -
  read it before you trust a single number. The model's daily pick is written to a public
  forward ledger before the outcome is known, and it stays there: losses included, nothing
  removed. TradeWave is a research platform - no performance promises, just instruments you
  can check. We would rather be audited than believed.
- **Links:** Read the methodology -> /methodology | Inspect the ledger -> /scorecard
- **Provenance card:** "I built the instrument I could not buy." - Afshin Moshrefi,
  founder, Tara Data Research LLC, author of The 100-Year Pattern (2026)
- **CTA band:** Start free - 7 days of everything / No credit card required.

## 8. ON THE RECORD (testimonials - SHIPS HIDDEN until >=2 real named quotes)
Layout: three restrained quote cards (serif quote, full name, role, market focus). Never
placeholders, never founder-as-testimonial, no star ratings, no logo wall.

- **Headline:** On the Record, Like Everything Else Here
- **Framing line:** Early users - independent traders, advisors, and quants - on rigor,
  depth, and where TradeWave fits in their day.
- **Editorial law:** performance quotes are rejected; quotes speak to rigor, depth, workflow.

## 9. PRICING
Layout: single ribbon line above a three-column table (Explorer / Analyst / Strategist),
monthly-yearly toggle (default yearly), same CTA under each column, kicker beneath. Plain
feature checklists per tier: markets, CSV export, calendar alerts, portfolios, reports,
Tara, [API and MCP access]{MCP_LIVE}.

- **Ribbon:** Every signup starts with 7 days of the full platform.
- **Headline:** Start With Everything. Pay Only If It Earns Its Place on Your Desk
- **Body:** Create a free account and get everything for 7 days: every market, every
  metric, the model and Tara included{MCP_LIVE: -> "every market, every metric, every AI
  layer"}. After the week, stay on Explorer free for as long as you like, or go Analyst at
  $47/mo ($37/mo billed yearly) or Strategist at $149/mo ($99/mo billed yearly). Paid plans
  carry a 7-day trial. Cancel anytime.
- **Button per column:** Start free - 7 days of everything / No credit card required.
- **Kicker:** Every tier runs the same engine and the same receipts, starting at $0.
- **NOTE:** prices render from live Stripe (the generator's metadata lookup) - never
  hardcode in the template.

## 10. THE CLOSE (living research + final CTA + footer)
Layout: living-research card row (auto-fed: 3 latest Seasonal Market News articles + 1
Insights explainer, real dates visible), then a calm full-width closing band with one
centered CTA, then the complete disclaimer footer.

- **Living strip headline:** What the Engine Sees This Week
- **Body:** Seasonal Market News covers what the engine sees in current markets. The
  Insights library teaches the method - how the statistics are built, and what up to a
  century of data can and cannot justify. Real articles, real dates, free to read: what the
  platform is thinking, before you ever create an account.
- **Link:** Browse the library
- **Closing band headline:** Bring Your Hunches
- **Closing body:** Test the calendar windows you've carried for years against up to a
  century of receipts - in the platform, with Tara beside the chart[, or inside ChatGPT and
  Claude]{MCP_LIVE}. Seven days of everything, free. A free plan that keeps working after.
- **Button:** Start free - 7 days of everything / No credit card required.
- **Footer:** TradeWave is an educational research platform operated by Tara Data Research
  LLC. Nothing on this site is investment, financial, or trading advice, or a
  recommendation to buy or sell any security or instrument. Seasonal statistics describe
  historical behavior; historical behavior does not guarantee future results. All trading
  and investing involves risk, including the possible loss of principal.
- **Footer links:** Methodology | Scorecard | Insights | Seasonal Market News | Pricing |
  Terms | Privacy | Contact | Disclaimer

---

## BUILD NOTES

- Implement in `site/templates/index-dark-blue.html` + `generate_home_page.py` (or a new
  template file swapped in by the generator - cleaner diff, instant rollback).
- Keep: GA snippet + events, MailerLite capture (move the capture INTO the living-research
  strip or footer - the page no longer has a mid-page capture section; daily-pick email
  capture can live on /scorecard and the close), tw_ref affiliate JS, JSON-LD (rewrite to
  match new copy), market-bar (optional - judges split; keep, it is live data).
- Remove: exit-intent popup, tab-title flasher, sticky bottom bar, returning-visitor hero
  swap, testimonial video section (until re-shot per section 8 rules), "+291% AI Lift"
  column, all win-rate/zero-losing-years copy, the hours-hardcoded market-status badge.
- Screenshots needed (production dependency): hero wave-viewer (century index pattern),
  per-year table inset, scan table (rank badges visible, no percentages), Tara split-view,
  ChatGPT connector window {MCP_LIVE}, calendar event, CSV-in-spreadsheet, report, scorecard
  panel with a visible loss row, methodology page.
- Section order is final per CRO judge; every section after the hero earns the scroll
  before the next CTA band appears (hero -> after section 5 -> after section 7 -> pricing
  -> close).
