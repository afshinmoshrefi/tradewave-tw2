# Engine 1: Programmatic SEO Ticker Pages

## Goal
Auto-generate a unique, SEO-optimized page for every ticker in the TradeWave database.
Each page targets long-tail searches like "AAPL seasonal pattern" and "best month to buy AAPL."

## Architecture

```
generate_ticker_pages.py    # Main generator script (cron)
templates/ticker.html       # Jinja2 template
```

Output: static HTML files deployed to production web root, one per ticker.

## Data Sources (all already exist)

- **Appserver API** (`/api/chartdata4`): seasonal pattern data, stats, historical returns per month
- **ML Scorer** (`config.ml_scorer_url`): AI score, win probability, predicted return, predicted peak
- **EDGAR service** (`config.edgar_service_url`): next earnings date estimate
- **Realtime service** (`config.realtime_service_url`): current price
- **Opportunity lists** (`/api/opplist4`): active patterns for this ticker
- **Config**: `/home/flask/config.py` for URLs, paths, API keys

## What Each Page Shows

1. **Header**: Ticker, company name, current price, today's date
2. **AI Seasonal Score**: Current AI score, win probability, predicted return (if active pattern exists)
3. **Seasonal Pattern Chart**: Monthly return bar chart (best/worst months) from historical data
4. **Election-Cycle Overlay**: Performance in election year 1/2/3/4 (data from PE mode)
5. **Active Patterns**: Any currently active seasonal windows with stats
6. **Historical Stats**: Win rate by month, average return, Sharpe ratio
7. **Next Earnings**: Estimated date from EDGAR
8. **CTA**: "See full analysis in Wave Viewer" (free signup gate)

## URL Structure

`/patterns/AAPL` or `/_static/patterns/AAPL.html`

Decision needed: WordPress rewrite rule vs static files in _static. Static is simpler and matches existing homepage approach.

## SEO Requirements

- Unique `<title>`: "AAPL Seasonal Pattern & AI Score | TradeWave"
- Unique `<meta description>` built from live data
- Schema markup: FAQPage (auto-generated Q&A from data), FinancialProduct
- Canonical URL per page
- Internal links to related tickers (same sector, similar patterns)
- `robots.txt` and sitemap.xml inclusion
- Open Graph tags with dynamic chart image

## Template Tech

Same stack as homepage: Jinja2 + Python, generates static HTML.
Use `/home/flask/blog/templates/` for the template.
Use `/home/flask/config.py` for all config (domain, paths, API URLs).
Match the dark-blue theme from `index-dark-blue.html`.

## Cron

Run daily after market close (after the homepage generator).
Start with 30 blue-chip tickers (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, JPM, etc.).
Scale to full 475+ once indexing is confirmed.

## Ticker List

Pull from the same source as opportunity lists. The appserver knows all supported tickers.
Alternatively, hardcode a starter list of 30 and expand.

## Build Steps

1. Create the Jinja2 template (ticker.html) matching the dark-blue theme
2. Write generate_ticker_pages.py that loops through tickers, fetches data, renders pages
3. Deploy to web root, add to sitemap
4. Test with 5 tickers, verify Google indexing
5. Scale to 30, then 475+

## Key Constraints

- No environment variables, use `/home/flask/config.py`
- Use explicit hardcoded paths, not Path(__file__).parent
- Use "AI" not "ML" in all user-facing text
- No em dashes in generated text
- SEO enabled only on production (check config.seo_enabled)
- This is the dev server (192.168.1.151), production URLs come from config
