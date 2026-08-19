# Tara Investor Discovery and Education Contract

Status: implemented; environment activation is recorded in the release manifest
Last reviewed: 2026-08-18

## Outcome

Tara helps a person move from a vague investing question to a transparent,
repeatable research process. She does not convert the top seasonal row into a
personal recommendation.

The default funnel is:

1. Establish the horizon: long-term investing over years, or a seasonal study
   lasting days or weeks.
2. Establish the research universe: curated ETFs or S&P 500 stocks.
3. Show up to five historical research candidates and disclose the screen's
   assumptions and blind spots.
4. Let the user choose a security for a full evidence review.
5. Show both bullish and historically weak windows, including losing years and
   the worst observed close when the data is available.
6. Keep news/fundamentals separate from TradeWave's mathematical evidence.

Tara also presents no more than three contextual next questions. Each control
has an outcome label and the exact question it will send. The questions change
with the research stage: choose a horizon, choose a universe, inspect a named
candidate, study downside, establish a Buy & Hold baseline, or interrogate a
validated comparison report. They are generated deterministically from the
validated intent, action, ticker, and report type rather than from arbitrary
model markup.

The direct questions "What can I ask Tara?" and "What can I research with
Tara?" also use a deterministic capability guide. It describes five outcomes:
find opportunities, research a ticker, study downside, research long-term
timing, and learn TradeWave.

When a question requests a chart change, the next questions remain hidden until
the browser verifies that the pattern data and seasonal graph loaded. A failed
load produces retry guidance and never advances the research path as if the
chart were ready.

This is TradeWave's advantage over a news-only workflow: news supplies a claim
or narrative; TradeWave tests a clearly defined calendar window against the
historical record. It can show whether the record supports, conflicts with, or
is irrelevant to the narrative without pretending that either source predicts
the next outcome.

## Why the product behaves this way

Comparable discovery products use a funnel rather than a single opaque answer:

- TradingView screeners translate filters into a candidate list for further
  analysis, not a suitability decision.
- Fidelity provides reusable screens and expert strategies, then routes the
  user into comparison and deeper research.
- TrendSpider translates natural language into explicit scan parameters before
  ranking results.
- StockCharts seasonality charts lead with frequency and average gain/loss and
  state that historical tendencies do not guarantee a future result.

TradeWave's distinctive contribution is the exact seasonal window, direction,
holding period, completed-year record, losing evidence, and weak/complementary
period analysis. Tara should make that evidence easier to understand, not hide
it behind a ticker recommendation.

## Behavior by question type

### “I have $2,000. What should I buy?”

Tara does not allocate the amount. She asks one material question: is the goal
long-term investing or a seasonal opportunity? The amount is not used as a
ranking input or position-size instruction.

### “How do I figure out what to invest in?”

For a long-term goal, Tara explains that TradeWave is a timing overlay. The
platform does not evaluate diversification, fund fees and holdings, valuation,
fundamentals, taxes, liquidity, breaking news, or the user's financial needs.

For a seasonal goal, Tara asks for stocks versus ETFs and then runs the evidence
screen.

### "How does Buy & Hold help a long-term investor?"

Tara leads with Buy & Hold as the main long-term feature and explains the path
in short, numbered sections:

1. In the Wave Viewer, enter a ticker and wait for its chart to load. Open
   **Analysis -> Buy & Hold** to establish TradeWave's Jan-1-to-Jan-1,
   always-invested historical baseline.
2. Read the green/red yearly bars for each completed year's gain or loss, the
   Trend Chart for the typical path through the calendar, and Cumulative Return
   for the compounded result across the selected history.
3. With Buy & Hold still loaded, open **Analysis -> Compare Symbols...**. Start
   with MSFT, for example, then add WMT and AVGO. The report uses the same
   full-year dates, direction, and common completed years for every symbol.
4. As an advanced study, identify and set a precise recurring weak date range
   from the Trend Chart and yearly evidence, then use
   **Analysis -> Exclude Current Range**.
5. After the outside dates load, select **View Exclusion Report** and compare
   the exclusion model with Buy & Hold over the same completed years.
6. Keep suitability factors outside TradeWave concise: it does not evaluate
   personal goals, diversification, holdings, fees, valuation, liquidity,
   taxes, news, or risk needs.

Tara never claims the timed model will beat Buy & Hold. She treats Buy & Hold as
the primary baseline, symbol comparison as the next research step, and date
exclusion as an advanced test that must earn the right to beat the baseline in
the historical record.

### “Find bullish ETFs this time of year.”

Tara runs a long-direction screen over a curated starter ETF universe. The
unrestricted ETF market is not called safe because it can contain leveraged,
inverse, single-stock, commodity, and other specialized products. Current fund
documents, holdings, fees, liquidity, and structure remain outside TradeWave's
seasonal dataset.

The starter universe is a transparent allowlist of conventional index products:
AGG, BND, DIA, EFA, IEMG, IJH, IWM, SPY, TIP, VTI, VT, and VXUS. This allowlist
is a research-universe control, not an endorsement or portfolio.

### “Find bullish stocks this time of year.”

Tara defaults explicitly to the S&P 500 and returns a shortlist. A market-only
view action may switch the opportunity table so the screen and interface agree;
no winning symbol is auto-loaded.

### “Should I buy TSLA?”

The user selected TSLA, so Tara may load its exact, tool-grounded seasonal
evidence. She must not answer the suitability question yes or no. The response
states that TradeWave cannot determine fit, gives the historical record and
downside evidence, and contains no buy/sell/hold, allocation, or return forecast.

### “When is AAPL historically weak?”

Tara reads AAPL's exact Best Waves rows for the active lookback, selects the
highest-Sharpe qualifying Short row, confirms the same setup through ChartData4,
and translates it into plain language as recurring weakness in the underlying.
It is never framed as a sell, short, or avoid instruction. An empty Best Waves
result is explained as no qualifying weak row at that setting, not as a tool
failure.

### "When is the best time to buy SPY?"

Tara uses the Wave Viewer's Best Waves dataset rather than the currently loaded
window. She searches qualifying Long rows with entry dates from one week before
the current market date through December 31 using the exact Wave Viewer lookback
and cycle mode. She selects the highest-Sharpe qualifying row in that range, matching
the Best Waves dropdown ranking. The answer names the exact date range, effective
lookback and cycle, average, median, and Sharpe Ratio, explains
where to find the Best Waves dropdown above the desktop bar chart, and notes that
the dropdown is empty or hidden when no row passes the criteria. Tara loads the
chart only after ChartData4 echoes the same symbol, market, date, duration, and
cycle.

### "How did MSFT do during the 100-Year Pattern?"

Tara resolves the named security and applies the canonical September 27 through
July 18 window in PE+2 to that security's actual available completed history.
The same workflow applies to other markets, including "DJI index" and "CL crude
oil". Descriptive words disambiguate shared tickers; unresolved ambiguity is
shown to the user rather than guessed. The answer reports the verified wins,
losses, average, median, Sharpe Ratio, and worst completed observation, then
loads the exact confirmed chart. It also states that the named book pattern is
the canonical SPX study; other securities are comparisons over its dates and
cycle position.

### “What if I exclude this date range?”

Tara explains only an active, validated Date Range Exclusion Report. The
excluded dates, remaining dates, and Buy & Hold must share the same completed
historical cohort. Tara refuses to synthesize an exclusion result from unrelated
tool calls.

Tara also accepts validated multi-date-range comparison reports, checks their
shared cohort and canonical Buy & Hold reference, and explains average return,
profitable-year frequency, and worst historical outcome without selecting an
investment.

## Evidence shown

At screening depth:

- ticker and research universe;
- direction;
- approximate entry date and holding period;
- average historical return;
- Sharpe ratio;
- winning/losing-year record and worst observed close when included in the
  source response.

At deep-dive depth:

- exact setup identity (ticker, market, entry date, hold days, lookback);
- completed years, wins, and losses;
- average historical return and Sharpe ratio;
- best and worst historical outcomes;
- year-by-year evidence and adverse/favorable excursions when loaded;
- historically weak or complementary window when requested;
- explicit data boundaries.

No statistic may be inferred from prose, reused from another window, or carried
across a setup change.

## Deterministic safeguards

- Broad investing/trading questions never require or receive a symbol-load
  action.
- Dollar amounts never become allocations or order sizes.
- ETF discovery is filtered before ranking and limiting.
- Candidate screens bypass free-form model selection and are composed from the
  exact TradeWave result.
- Named buy/sell questions trigger a response guard. Personalized directives,
  allocations, and security forecasts are rejected and retried.
- A chart action must match the exact setup returned by a read tool, and only
  the browser may claim the graph loaded successfully.
- Weak-period and exclusion studies are separate contracts.
- Buy & Hold guidance is deterministic and always distinguishes an educational
  workflow from a validated result for a particular ticker and cohort.
- Date-range reports are rejected if roles, dates, common years, sample counts,
  or Buy & Hold references do not reconcile.
- Guided-question payloads are capped at three, client-validated, and restricted
  to static prompts plus validated ticker tokens.

## Audit and completion truth

Every accepted chat turn receives a random `turn_id`. The question audit stores
the bounded question, response, provider, requested actions, and protocol trace.
Every view action receives its own `action_id`, an action-set manifest, an expiry,
and an HMAC receipt bound to the authenticated user and turn.

The browser does not treat an accepted action as a loaded chart. It validates the
signed manifest, applies the allowlisted state, and, for chart-backed actions,
requires both the primary Gain-Loss payload and the exact seasonal Trend payload
to return current, non-empty, structurally valid data. Only then does the browser
display completion text and send a joined `action_result` audit. A timeout,
superseded view, mismatched response, empty graph, or invalid action produces a
failed result and retry guidance without a success claim.

## Research basis

Primary and official sources reviewed:

- TradingView screener walkthrough:
  https://www.tradingview.com/support/solutions/43000718885-tradingview-screeners-walkthrough/
- Fidelity stock screener:
  https://www.fidelity.com/research/equity/popups/stock-research-screener.shtml
- TrendSpider natural-language scanning:
  https://trendspider.com/blog/scanning-the-markets-with-sidekick-ai/
- StockCharts seasonality charts:
  https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/seasonality-charts
- Investor.gov asset allocation and time horizon:
  https://www.investor.gov/introduction-investing/getting-started/asset-allocation
- Investor.gov risk tolerance:
  https://www.investor.gov/introduction-investing/investing-basics/save-and-invest/gauge-your-risk-tolerance
- SEC robo-adviser guidance:
  https://www.sec.gov/investment/im-guidance-2017-02.pdf
- FINRA communications guidance and Rule 2210:
  https://www.finra.org/rules-guidance/guidance/faqs/advertising-regulation
  https://www.finra.org/rules-guidance/rulebooks/finra-rules/2210
- Deflated Sharpe Ratio research on selection bias and backtest overfitting:
  https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2460551_code87814.pdf?abstractid=2460551
- Issuer verification for the starter ETF universe:
  https://investor.vanguard.com/investment-products/list/etfs?strategy=total_market_etfs
  https://www.ishares.com/us/products/etf-investments
  https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy
  https://www.ssga.com/us/en/individual/etfs/state-street-spdr-dow-jones-industrial-average-etf-trust-dia
