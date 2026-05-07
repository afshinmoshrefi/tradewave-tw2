# PRD: Programmatic SEO Ticker Pages

## 1. Objective

Auto-generate a unique, data-rich, SEO-optimized page for every supported US stock ticker. Each page targets long-tail searches like "AAPL seasonal pattern," "best month to buy MSFT," and "is GOOGL a buy right now." Pages update daily via cron with fresh data.

This is the highest-leverage automated growth channel. No competitor combines AI scoring + seasonality + election-cycle analysis on a single ticker page.

## 2. Success Metrics

- Pages indexed by Google (check via `site:tradewave.ai/patterns/`)
- Organic search impressions and clicks (Google Search Console)
- Click-through to Wave Viewer or signup from ticker pages
- Target: 30 pages indexed within 60 days, 475+ within 6 months

## 3. Scope

### Phase 1: MVP (30 Blue-Chip Tickers)
Build and deploy pages for the most-searched tickers. Validate Google indexes them and they start ranking.

### Phase 2: Scale (475+ Tickers)
Expand to all tickers that have sufficient data (10+ years of history). Add sitemap, internal linking, and sector hubs.

### Phase 3: Optimize
Add structured data, FAQ sections, A/B test CTAs, add email capture.

---

## 4. Data Architecture

### 4.1 Available Data Sources

All data is already computed and accessible. No new infrastructure needed.

| Data | Source | Config Variable |
|------|--------|----------------|
| Symbol list + company names | `/home/flask/data/csv/US/` (3,543 CSVs) | `config.csv_folder` |
| Historical price data | CSV files per ticker | `config.csv_folder` |
| Active seasonal patterns | Appserver `/OppBySymbol/` | `config.central_server_url` |
| Pattern statistics (ChartData4) | Appserver `/ChartData4/` | `config.central_server_url` |
| Consolidated seasonal chart | Appserver `/consolidated_seasonal_chart2/` | `config.central_server_url` |
| AI score, win probability | ML Scorer `/score` | `config.ml_scorer_url` |
| Next earnings date | EDGAR service | `config.edgar_service_url` |
| Current price + change | Realtime service `/prices/all` | `config.realtime_service_url` |
| Trend score (StockScore) | StockScore service | `config.stockscore_url` |

### 4.2 Data Per Ticker Page

For each ticker, the generator collects:

```python
page_data = {
    "symbol": "AAPL",
    "company_name": "Apple Inc.",
    "current_price": 198.45,
    "price_change_pct": 1.2,

    # Monthly seasonality (computed from CSV)
    "monthly_returns": {
        "Jan": {"avg_return": 2.1, "win_rate": 65.0, "sample_years": 44},
        "Feb": {"avg_return": -0.3, "win_rate": 48.0, "sample_years": 44},
        # ... all 12 months
    },
    "best_month": "Jan",
    "worst_month": "Sep",

    # Active patterns (from OppBySymbol or OppList4)
    "active_patterns": [
        {
            "start_date": "2026-04-10",
            "end_date": "2026-05-08",
            "days": 28,
            "direction": "Long",
            "avg_return": 5.2,
            "sharpe": 1.45,
            "mode": "cons",  # or "pe"
            "wave_viewer_url": "/wave-viewer?o=...",
        }
    ],

    # AI scoring (if active pattern exists)
    "ai_score": 94.2,        # from ML scorer, None if no active pattern
    "win_prob": 84.5,         # percentage
    "pred_return": 5.7,       # predicted return
    "pred_mfe": 10.2,         # predicted peak

    # Election cycle
    "election_year_type": "Midterm (Year 2)",
    "election_cycle_avg": 3.8,  # avg return in this cycle phase

    # Earnings
    "next_earnings_est": "2026-04-25",
    "days_to_earnings": 12,

    # Trend
    "trend_score": {"long": 72.5, "short": 31.2},

    # Data depth
    "years_of_data": 44,
    "first_year": 1982,
}
```

### 4.3 Monthly Seasonality Computation

This is the core unique content. Computed directly from the ticker's CSV file (no API call needed):

```python
# For each month, calculate:
# 1. Average return from day 1 to day ~21 (one month holding period)
# 2. Win rate (% of years with positive return)
# 3. Number of sample years
# 4. Best/worst year returns
```

This gives each page genuinely unique data. Even if two tickers are in the same sector, their monthly patterns are different.

---

## 5. Page Design

### 5.1 URL Structure

```
/patterns/AAPL
```

Deployed as static HTML: `/_static/patterns/AAPL.html`

Nginx rewrite: `location /patterns/ { alias /var/www/tradewave/patterns/; }`

### 5.2 Page Layout (Top to Bottom)

```
+--------------------------------------------------+
| NAV BAR (same as homepage)                        |
+--------------------------------------------------+
| HERO: AAPL - Apple Inc.                          |
| Current Price: $198.45 (+1.2%)                   |
| "44 years of seasonal data. AI-scored daily."    |
+--------------------------------------------------+
| AI SCORE CARD (if active pattern exists)         |
| AI Score: 94.2 | Win Prob: 84.5% | Pred: +5.7%  |
| Direction: Long | Window: Apr 10 - May 8 (28d)  |
| [View Full Analysis in Wave Viewer ->]           |
|                                                  |
| (if no active pattern)                           |
| "No active seasonal pattern for AAPL right now.  |
|  Sign up free to get notified when one opens."   |
| [Get Free Alerts ->]                             |
+--------------------------------------------------+
| MONTHLY SEASONALITY CHART                        |
| Bar chart: 12 months, avg return per month       |
| Color: green for positive, red for negative      |
| Best month highlighted                           |
|                                                  |
| Below chart: "Based on 44 years of data          |
| (1982-2026)"                                     |
+--------------------------------------------------+
| MONTHLY STATS TABLE                              |
| Month | Avg Return | Win Rate | Best | Worst     |
| Jan   | +2.1%      | 65%      | +12% | -8%       |
| Feb   | -0.3%      | 48%      | +9%  | -11%      |
| ...                                              |
+--------------------------------------------------+
| ELECTION CYCLE SECTION                           |
| "AAPL in Midterm Years (Year 2 of 4)"           |
| Avg return in midterm years: +3.8%               |
| Comparison bar: Year 1 / 2 / 3 / 4              |
| [Unlock election-cycle filtering ->]             |
+--------------------------------------------------+
| KEY DATES                                        |
| Next Earnings: Apr 25, 2026 (12 days)           |
| Best Month to Buy: January (avg +2.1%)          |
| Worst Month: September (avg -1.8%)              |
+--------------------------------------------------+
| FAQ (auto-generated, 3-4 questions)              |
| "Is AAPL a good buy right now?"                  |
| "What is AAPL's best month historically?"        |
| "Does AAPL follow election cycle patterns?"      |
+--------------------------------------------------+
| CTA SECTION                                      |
| "See the full seasonal analysis for AAPL"        |
| [Start Free ->] [View All Patterns ->]           |
+--------------------------------------------------+
| RELATED TICKERS                                  |
| Other tech stocks: MSFT, GOOGL, META, NVDA       |
| (internal links to their /patterns/ pages)       |
+--------------------------------------------------+
| FOOTER (same as homepage)                        |
+--------------------------------------------------+
```

### 5.3 Above the Fold Priority

The most important content must be visible without scrolling:
1. Ticker + company name + current price
2. AI score card (if active pattern) OR "no active pattern" with email CTA
3. Start of monthly seasonality chart

### 5.4 Content Gating Strategy

**Free (visible to everyone, indexable by Google):**
- Monthly seasonality chart (all 12 months)
- Monthly stats table
- Election cycle summary (which year type, avg return)
- Key dates (earnings, best/worst month)
- FAQ section

**Gated (requires free signup):**
- Full Wave Viewer analysis (click-through CTA)
- AI score details and predictions
- Historical year-by-year breakdown
- Active pattern entry/exit dates

**Premium (paid tier):**
- Election cycle filtering and comparison
- All 15 markets
- Portfolio tracking

The free content must be genuinely useful and comprehensive enough for Google to rank it. The gated content is the conversion hook.

---

## 6. SEO Specifications

### 6.1 Title Tag
```
AAPL Seasonal Pattern & AI Score | TradeWave
```
Format: `{SYMBOL} Seasonal Pattern & AI Score | TradeWave`

If active pattern exists:
```
AAPL Seasonal Pattern: AI Says Long (+5.7% predicted) | TradeWave
```

### 6.2 Meta Description
Auto-generated from live data:
```
AAPL (Apple Inc.) seasonal pattern analysis based on 44 years of data.
Best month: January (+2.1% avg). AI Score: 94.2. Win probability: 84.5%.
Updated daily.
```

If no active pattern:
```
AAPL (Apple Inc.) seasonal pattern analysis based on 44 years of data.
Best month: January (+2.1% avg). Worst month: September (-1.8% avg).
Next earnings: Apr 25. Updated daily.
```

### 6.3 Schema Markup

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Is AAPL a good buy right now?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Based on 44 years of seasonal data, AAPL's current AI Score is 94.2 with an 84.5% win probability for a Long position over the next 28 days. The predicted return is +5.7%. This is a seasonal pattern analysis, not a buy recommendation."
      }
    },
    {
      "@type": "Question",
      "name": "What is AAPL's best month to buy?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Historically, January has been AAPL's strongest month with an average return of +2.1% and a 65% win rate over 44 years of data."
      }
    },
    {
      "@type": "Question",
      "name": "Does AAPL follow election cycle patterns?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes. In midterm years (year 2 of the 4-year presidential cycle), AAPL has averaged +3.8% returns. 2026 is a midterm year."
      }
    }
  ]
}
```

### 6.4 Open Graph

```html
<meta property="og:title" content="AAPL Seasonal Pattern & AI Score">
<meta property="og:description" content="44 years of data. AI Score: 94.2. Best month: January.">
<meta property="og:image" content="/patterns/og/AAPL.png">
```

The OG image should be a dynamically generated chart card (same as social proof engine cards). Can be a PNG render of the monthly seasonality chart with ticker overlay.

### 6.5 Sitemap

Generate `/patterns/sitemap.xml` listing all ticker pages with `lastmod` set to today (pages regenerate daily).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://tradewave.ai/patterns/AAPL</loc>
    <lastmod>2026-04-13</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.7</priority>
  </url>
  <!-- ... -->
</urlset>
```

Submit sitemap to Google Search Console.

### 6.6 Canonical URLs

Each page has a self-referencing canonical:
```html
<link rel="canonical" href="https://tradewave.ai/patterns/AAPL">
```

### 6.7 Internal Linking

Each page links to:
- 4-6 related tickers (same sector or similar seasonal profile)
- Homepage
- Scorecard
- Wave Viewer (gated)

Sector groupings can be hardcoded for Phase 1 (30 tickers) and computed later.

---

## 7. Technical Implementation

### 7.1 File Structure

```
/home/flask/tradewave-marketing/ticker-pages/
    PRD.md                          # This file
    BUILD.md                        # Technical spec (already exists)
    generate_ticker_pages.py        # Main generator script
    compute_monthly_seasonality.py  # Monthly return calculator
    templates/
        ticker.html                 # Jinja2 page template
    data/
        sector_map.json             # Ticker to sector mapping (for related links)
        ticker_list_phase1.json     # 30 blue-chip tickers for Phase 1
```

Output: `{web_root}/_static/patterns/{SYMBOL}.html`

### 7.2 Generator Script Flow

```
1. Login to appserver (get token)
2. Load ticker list (Phase 1: 30, Phase 2: 475+)
3. Fetch bulk realtime prices (one call)
4. For each ticker:
   a. Read CSV file, compute monthly seasonality
   b. Fetch active patterns (OppBySymbol)
   c. If active pattern: fetch ML score
   d. Fetch earnings date (EDGAR)
   e. Fetch trend score (StockScore)
   f. Compute election cycle stats from CSV
   g. Build page_data dict
   h. Render Jinja2 template
   i. Write HTML to output dir
5. Generate sitemap.xml
6. Print summary
```

### 7.3 Performance Considerations

- **30 tickers (Phase 1):** ~30 API calls to OppBySymbol + ML scorer. Under 2 minutes.
- **475+ tickers (Phase 2):** Monthly seasonality is computed from local CSV files (fast). OppBySymbol and ML scorer calls can be batched or parallelized. Budget 10-15 minutes.
- **CSV reads are fast:** Each ticker CSV is small (< 1MB). Reading 475 files takes seconds.
- **Caching:** Appserver caches most responses in Redis. Repeated runs are faster.

### 7.4 Cron Schedule

```
# Generate ticker pages daily at 6 AM ET (after overnight data updates)
0 6 * * * flask python /home/flask/tradewave-marketing/ticker-pages/generate_ticker_pages.py >> /home/flask/tradewave-marketing/ticker-pages/generate.log 2>&1
```

Run after the ML scorer nightly cache and EDGAR crawler, but before the homepage generator.

### 7.5 Template Theme

Match the existing dark-blue theme from `index-dark-blue.html`. Share CSS variables and base styles. The template should feel like a natural extension of the TradeWave site, not a separate microsite.

Include the same nav bar and footer as the homepage for brand consistency.

---

## 8. Phase 1 Ticker List (30 Blue-Chips)

Most-searched tickers with strong seasonal data:

```
AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA,
JPM, BAC, GS, V, MA,
JNJ, PFE, UNH,
XOM, CVX, COP,
HD, WMT, COST,
DIS, NFLX, SBUX,
BA, CAT, DE,
SPY, QQQ, IWM
```

These cover mega-cap tech, financials, healthcare, energy, consumer, industrials, and major ETFs. High search volume, deep data history.

---

## 9. Monthly Seasonality Computation

### Algorithm

For each ticker, for each month (Jan-Dec):

```
1. From the CSV, identify all years with data
2. For each year, find the close on the 1st trading day of the month
   and the close on the last trading day of the month
3. Compute monthly return: (close_end - close_start) / close_start * 100
4. Aggregate across all years:
   - avg_return = mean of all monthly returns
   - win_rate = % of years with positive return
   - best_year_return = max
   - worst_year_return = min
   - sample_years = count
```

### Election Cycle Overlay

Same computation but filtered by election cycle year:
- Year 1 (post-election): years where year % 4 == 1
- Year 2 (midterm): years where year % 4 == 2
- Year 3 (pre-election): years where year % 4 == 3
- Year 4 (election): years where year % 4 == 0

---

## 10. Conversion Funnel

```
Google Search: "AAPL seasonal pattern"
    -> Ticker page (free, indexed content)
        -> CTA: "View full analysis in Wave Viewer" (requires free signup)
            -> Free signup (Explorer tier)
                -> Wave Viewer experience
                    -> Upgrade CTA (Analyst/Strategist)
```

Secondary funnel:
```
Ticker page
    -> "Get notified when AAPL patterns open" (email capture)
        -> Daily AI pick email
            -> Upgrade CTA
```

---

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Google penalizes thin/duplicate content | Each page has unique computed data, charts, and auto-generated FAQ. Not boilerplate. |
| Pages take months to rank | Expected. Start Phase 1 immediately so the clock starts ticking. |
| API rate limits during generation | Batch requests, add delays. 30 tickers is well within limits. |
| Stale data (page shows yesterday's price) | Acceptable. Pages regenerate daily. Add "Last updated" timestamp. |
| Compliance risk (implied buy/sell recommendation) | Every page includes disclaimer. FAQ answers say "seasonal analysis, not a recommendation." |

---

## 12. Not in Scope (Deferred)

- User comments or discussion on ticker pages
- Real-time price updates via JS (static pages are fine)
- Comparison pages ("AAPL vs MSFT seasonal patterns")
- Sector hub pages ("/patterns/sector/technology")
- API endpoint for programmatic access to page data
- Multi-language support

These are all Phase 3+ enhancements, only worth building after pages are ranking.

---

## 13. Definition of Done

### Phase 1 Complete When:
- [ ] 30 ticker pages generated and deployed
- [ ] Pages accessible at /patterns/{SYMBOL}
- [ ] Sitemap generated and submitted to Google Search Console
- [ ] Each page has unique title, description, schema markup
- [ ] Monthly seasonality chart renders correctly
- [ ] Active pattern AI score shows when available
- [ ] CTA links to signup/Wave Viewer work
- [ ] Pages match dark-blue theme
- [ ] Cron runs daily without errors
- [ ] Mobile-responsive layout
- [ ] Disclaimer present on every page
