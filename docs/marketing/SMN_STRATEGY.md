# SMN (SeasonalMarketNews.com) - Monetization Strategy

_Status: RECOMMENDED strategy, owner decision pending. Written 2026-07-02 from a code-verified
read of the SMN pipeline, the pricing/funnel docs, and a 280-fetch external research pass
(Google AI-content policy, gating economics, publisher-API comps). Once the owner decides,
record the decision here and reconcile `config.py TIER_FEATURES` + the homepage copy._

## 0. The One-Line Strategy

**Give away the story, sell the numbers.** Prose has zero defensible moat in 2026 - anyone
can generate articles. The proprietary seasonal DATA inside each article (30-year windows,
win rates, MFE/MAE) is the moat, and TradeWave already sells it. SMN's job is distribution,
credibility, and email capture for that paid engine - not to be a revenue SKU itself.

## 1. What SMN Is (code-verified facts)

- Pipeline `smn/`: Tavily whitelist research + Grok synthesis -> GPT-5.1 writing grounded in
  appserver ChartData4 seasonal stats -> OpenAI SEO titles w/ dedupe+validation -> Replicate
  hero images -> bleach-sanitized static HTML to `/var/www/smn/articles/`.
- Volume knob `smn/daily_article_queue.py:ARTICLES_PER_DAY` (repo = 2; owner states prod runs
  6/weekday - VERIFY on the prod box). Sunday weekly recap email.
- Full distribution plumbing already exists: sitemap + sitemap-news + RSS + IndexNow +
  `llms.txt` + AI-crawler-welcoming robots.txt + NewsArticle JSON-LD + GA4 (prod).
- Every article embeds the MailerLite signup form (SMN-DAILY / SMN-WEEKLY groups) and the
  required `transition_to_tradewave` bridge paragraph.
- NO gating anywhere (verified). Endorsed by finance-media professionals (Anne-Marie Bayind;
  Michael Sachitello, formerly Investopedia) - Anne-Marie suggested price-gating it.
- Current conflict to resolve: `config.py TIER_FEATURES` lists "Seasonal Market News" as an
  Analyst-tier feature, while the shipped homepage spec (HOMEPAGE_REDESIGN_THE_LEDGER.md §11)
  says SMN is "free to read... before you ever create an account."

## 2. What the External Research Established (mid-2026, sourced in detail below)

**Google does NOT penalize AI content per se.** Live policy: "Rewarding high-quality content,
however it is produced"; the QRG "Lowest" rule (Jan 2025) triggers on low effort/originality/
value, not AI use. What it DOES punish: "scaled content abuse" (many pages without added
value), with the highest bar on YMYL finance. Survivors all pair disclosed automation +
structured-data grounding + human curation (AP, United Robots, Newsquest). Every AI-content
blow-up (CNET, Sports Illustrated, Gannett, Hoodline) involved HIDDEN AI, fake bylines, or
unedited auto-publish - trust failures, not tech failures. YouTube similarly: disclosure
rules for synthetic media + a July 2025 "inauthentic content" monetization policy against
mass-produced repetition; no ban on AI content as such.

**SEO volume is a dead growth channel for small sites; a narrow surface survives.** Small
publishers lost ~60% of search referrals in two years (Chartbeat); AI Overviews cover 91% of
educational finance queries. BUT ticker-specific / time-sensitive / data-driven content sits
in the least-AI-Overview'd zone (7-8% on tickers, ~2-3% on business-news queries), and Top
Stories / Discover still generate clicks. SMN publishes exactly the surviving kind.

**AI-citation (AEO) is SMN's asymmetric channel.** 65.7% of finance AI Overview citations come
from OUTSIDE the organic top-100; statistics-rich unique-data pages get cited ~78% vs ~12% for
generic content; AI-referred visitors convert ~50%+ better. A site whose every article carries
a proprietary stat ("X has closed higher in this window in 17 of 20 years") is structurally
built for this channel. SMN already has llms.txt + open robots.txt.

**Gating economics say do not paywall the articles.** Paywall ceiling for non-must-have content
is ~0.5-1% of uniques; ~68% of news visitors read one article/month so a wall never touches
them; finance paid-newsletter churn is the worst of any vertical (~16.7%/mo). The winning
industry pattern: free content -> email/registration capture (3-12%) -> sell to the list
(registered users convert to paid at ~10-19% vs ~0.2% anonymous). Content bundled INSIDE a
SaaS retains via the tool instead (Robinhood, Benzinga-in-brokerages, United Robots' measured
952 paid conversions from robot content).

**Custom articles for pay is a non-business.** Price capped by human freelancers ($250-1,500/
article); no comp anywhere prices automated content per article.

**Publisher feed/API licensing is real but B2B-heavy and premature.** Market rates: self-serve
news API $99-500/mo; white-label feed $500-3,500/mo; broker/enterprise deals 5-6 figures/yr
(the Benzinga model - its $300M valuation came from licensing engagement content to brokers).
Every durable comp licenses proprietary structured DATA wrapped in narrative, and the
licensor's trust burden transfers to licensees (the MSN/AdVon lesson). Automated Insights -
the canonical article-generator - got absorbed; the value accrued to data owners.
LLM-crawler licensing (TollBit etc.) yields $0-low hundreds/mo at SMN's size: optionality only.

## 3. The Recommended Strategy (three moves)

### Move 1 - Keep SMN free, open, and proudly disclosed (the reach asset)
Not "free because we could not decide" - free WITH a job description and KPIs:
- Job: credibility engine ("the platform shows its thinking daily"), email capture, AI-citation
  distribution, and per-article funnel entry. This matches the homepage Ledger positioning.
- Lean INTO disclosure as brand: an editorial-standards page stating the human-curated,
  engine-grounded, AI-written process (Google explicitly asks "is automation self-evident?").
  The praise quotes (with permission) belong on that page. The anti-CNET posture IS the moat.
- Hardening for the YMYL bar: visible methodology link (exists), real dates (exist), a named
  human "reviewed by" editor line if the owner will stand behind it, moderate velocity (quality
  per article beats count; there is no SEO reason to raise ARTICLES_PER_DAY).
- Distribution: submit to Google News Publisher Center + ensure Bing indexation (ChatGPT
  citations flow through Bing); keep robots.txt open to search/citation bots (that is the
  channel); training-bot access is a separate, low-stakes call.

### Move 2 - Gate the DEPTH, not the news (the honest version of "price-gate it")
The article is the ad; the pattern is the product. This resolves the Analyst-tier conflict
without paywalling the public site:
- Every article gets a per-pattern deep link into the wave viewer (the `?o=BASE64` param
  exists) - "Open this pattern in TradeWave" -> lands in the 7-day reverse trial. The stat is
  free to READ; interrogating it (any date range, AI score, per-year table, your portfolio)
  requires the product. That gate already exists and is enforced server-side.
- Replace the vague "Seasonal Market News" line in TIER_FEATURES with a REAL paid feature:
  a personalized SMN brief at Analyst+ - the daily email filtered to the subscriber's
  watchlist/portfolio tickers plus upcoming seasonal windows on their names. Cheap to build
  (pipeline + MailerLite groups + watchlists all exist), impossible to get free elsewhere, and
  it is personalization - where finance WTP actually lives. Public SMN stays generic-6-a-day.
  (Keep it filtering/reporting, not individualized advice - stays inside the Lowe v. SEC
  impersonal-publication exclusion.)
- Wire the SMN email list into the funnel: the list is the asset that survives Google. The
  built-but-inactive email automations + the free-seasonal-report activation bridge are the
  same motion; SMN subscribers should receive the same trial invitation cadence.

### Move 3 - Defer the publisher API; keep it as designed optionality
Post-cutover roadmap already ends with "paid-SMN" after affiliate -> API -> MCP. When it
comes up: license PatternCards + narrative (data wrapped in story, Benzinga-shaped, via the
existing `apiserver` - a `/v1/news` endpoint is trivial), NOT a bare article feed. Enterprise
sales motion; do not start it pre-cutover. If a broker/publisher approaches inbound, the
asset and the rate-card comps ($500-3,500/mo white-label; 5-6 figure broker deals) are ready.

### Explicitly rejected
- Hard paywall / regwall on SMN articles (kills distribution to protect ~0.5-1% capture).
- Standalone paid custom articles (price-capped by humans, zero comps, distraction).
- Scaling article volume for SEO (the volume channel is dead; scaled-content-abuse risk).

## 4. KPIs (so "free" is accountable)

- SMN email list growth /mo (MailerLite SMN-DAILY + SMN-WEEKLY).
- SMN -> signup attribution (per-article UTM on the bridge + deep links; GA4 exists).
- SMN-subscriber -> trial -> paid conversion vs other channels.
- AI-citation checks (ChatGPT/Perplexity/AIO mentions of seasonalmarketnews.com; a $29/mo
  tool or a monthly manual probe suffices).
- Article-page -> deep-link CTR once Move 2 ships.

## 5. Source Notes (load-bearing, verified 2026-07-02)

- Google AI-content policy: developers.google.com/search/blog/2023/02/google-search-and-ai-content
  (still live); spam policies (scaled content abuse) developers.google.com/search/docs/essentials/spam-policies;
  QRG 4.6.6 AI-Lowest rule (Sept 2025 PDF); helpful-content Who/How/Why self-assessment.
- Small-publisher search decline: Chartbeat via Axios/SEJ (-60% small, -47% mid, -22% large).
- Finance AIO exposure split: BrightEdge (91% educational vs 7% ticker queries); NewzDash
  (2-3.5% on news queries).
- AEO: BrightEdge/SEL June 2026 (65.7% of finance AIO citations outside organic top-100);
  ZipTie (unique-data cited 78% vs 12%); Princeton GEO/KDD 2024 (stats+citations +30-40%).
- Gating: GNI Subscriptions Lab benchmarks; Piano (registered ~10-19% vs 0.2% anonymous);
  Chiou & Tucker 2013; WSJ First-Click-Free exit (traffic -44%, conversions 4x).
- Newsletter economics: beehiiv State of Paid Newsletters 2026 (finance 0.78% free->paid
  median, money-vertical churn 16.67%/mo).
- Comps: Automated Insights/AP (absorbed into Stats Perform); United Robots (952 paid subs
  from robot content, NTM 2021); Benzinga/Beringer $300M (broker feed licensing); CityFALCON
  $240-3,200/mo white-label rate card; TollBit rates $0.005-0.01/crawl.
- Failure modes: CNET/Red Ventures, Sports Illustrated, Gannett/LedeAI, MSN, Hoodline - all
  hidden-AI or unedited auto-publish scandals.
