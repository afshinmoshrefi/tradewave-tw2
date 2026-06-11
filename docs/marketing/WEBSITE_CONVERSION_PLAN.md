# tradewave.ai Website Conversion Plan
> Produced 2026-06-10 by a 13-agent audit (4 site mappers, 3 competitor teardowns + category research,
> 4 CRO reviewers, 1 adversarial critic; 43 raw findings consolidated). Owner positioning: "statistical
> research, not a promise." Context: affiliate traffic starts ~June 16; solo founder; ~2 weeks of site
> budget max. THIS DOC = the prioritized execution plan. Check items off as they ship.

## The verdict

The funnel physically cannot complete a conversion today, and the copy contradicts the brand. The theme
of the fix is **wiring and honesty, not redesign**: ~8-10 days making every existing click land somewhere
real and every published number survive a skeptic's re-check. Fix plumbing first (P0), then the truth
package (P1), then conversion architecture (P2). SEO/growth (P3) comes after June 16.

---

## P0 - BROKEN PLUMBING (revenue-losing bugs; ALL before June 16)

> **STATUS 2026-06-10: P0 SHIPPED on dev + pushed (commits 07fa31d, aef1437) - every item below
> except analytics *activation* and the prod attribution test. ALSO SHIPPED: the reverse-trial
> freemium gate (7d full Strategist for new signups, Explorer=DJ30 after; effective_tier at token
> mint; ops/grant_reverse_trial.py for the existing free base; migration d4e5f6a7b8c9).
> Verified by independent agent + 2 adversarial reviewers; suite 235 passed.
> OPERATOR REMAINING: (1) decide/confirm LIVE Stripe eod prices ($47/$149 launch vs $58/$199 post -
> the page now always shows live truth; align dev TEST products too); (2) reactivate + rename
> MailerLite form 146340885183858176 (marked inactive, accepts posts today); (3) confirm the Stripe
> Billing Portal allows plan switches (subscription_update); (4) create GA4 property + set
> TW2_GA_MEASUREMENT_ID in staging/prod secrets.env (snippet bakes on next regen); (5) deploy
> staging->prod, regen static pages on prod, check /var/log/tradewave/home_opportunities.log
> freshness; (6) the end-to-end affiliate attribution test on prod.

- [ ] **Email capture posts to a nonexistent MailerLite form.** Home strip + exit popup POST to account
  `871495` / form `131498498498077...` (placeholder-looking); the connected account is `489451`, real
  home form `146340885183858176`. Files: `site/templates/index-dark-blue.html:1311,2170`,
  `site/templates/scorecard.html:548` (points at the SMN list). Standardize ALL capture on one
  daily-pick group; drop `target=_blank` for fetch + inline confirm. VERIFY with one real subscribe.
- [ ] **All 103 /patterns/ pages have dead money-CTAs**: baked TW1 WordPress URLs on a LAN IP
  (`http://192.168.1.176/register/?lid=1`, `/my-account/?ihc_ap_menu=subscription`) from
  `site/ticker_pages/generate_ticker_pages.py:64-65` (+ `ticker_data.py:44` hardcodes
  `tradewave.ai/wave-viewer` which has no TW2 route). Fix: primary CTA `/app/?o=<pattern>` deep link,
  secondary `/signup`. Regenerate all pages.
- [ ] **Trial checkout success flow bounces paying users**: `/stripe/success` (`web/app.py:~1402`)
  requires `payment_status=='paid'` but 7-day-trial sessions complete as `no_payment_required` ->
  trialist lands on `/pricing?payment_pending=1` with no confirmation. Fix: verify subscription is
  `trialing` server-side, write tier, redirect `/app/?welcome=trial`.
- [ ] **Second-subscription double-billing**: create-checkout has no existing-subscription check; an
  Analyst clicking Strategist on the home page mints a NEW subscription + second trial. Fix: existing
  trialing/active sub -> Stripe Billing Portal `subscription_update` flow.
- [ ] **Home page shows wrong prices**: generator fallback $58/$41 + $199/$131
  (`site/generate_home_page.py:34-45`) vs real Stripe $47/$37 + $149/$99 - and `_stripe_prices()`
  matches by product NAME, not the `product_line=eod` metadata convention `web/app.py` uses. Fix both;
  make the build FAIL LOUDLY when the fallback fires.
- [ ] **"Today's AI Pick" card (the page's best proof) silently failed to render** - exception swallowed
  at `generate_home_page.py:~1187` degraded it to 3 bare stats. Fix the render + alert on degradation.
- [ ] **"This Week's Top Patterns" is 3+ months stale** (`site/data/home_opportunities.csv` last
  updated Mar 1; Feb-Apr windows shown in June under "Active windows close every day you wait").
  Refresh pipeline or render from live data; never show dated windows older than the current week.
- [ ] **Patterns hub + sitemaps clobbered by a 2-ticker test run** (May 8): `/patterns/index.html`
  lists 2 of 103 tickers; `patterns/sitemap.xml` has 3 URLs; main `sitemap.xml` is on the retired
  tw2.trxstat.com domain, omits patterns/scorecard, includes a 404 + auth-gated /app/. Regenerate full;
  rebuild sitemap on tradewave.ai.
- [ ] **Zero analytics anywhere** (`config.ga_measurement_id` has no consumers; React shell has a TODO).
  Add GA4 or Plausible sitewide + events: CTA clicks, signup, trial start, capture submit, /join visits.
  UTM-through-to-Stripe. Without this the 60-day window is unmeasurable.
- [ ] **/pricing redirect drops query params** (`web/app.py:990`): `/pricing?code=X` loses the affiliate
  code unless the cookie was already set. Fix: set tw_ref from `?code/?via` + carry params through.
- [ ] **Affiliate readiness**: commit + deploy the uncommitted /join personalization work; run ONE
  end-to-end attribution test on prod (click -> cookie -> checkout -> webhook row -> 30/35 math).

## P1 - THE HONESTY PACKAGE (the positioning fix; before June 16)

The site's top layer talks like the promise-sellers while the FAQ/scorecard copy is excellently hedged.
A skeptical trader (or a regulator, or an affiliate's audience) sees the top first.

- [ ] **De-hype the headline layer**: drop "Zero losing years" from title/meta/hero; drop the undefined
  "+291% AI Lift" column; drop the "One winning trade on a $10k position pays for a year" ROI anchor;
  change "8 years of live testing" to "walk-forward out-of-sample testing". Hero direction (style
  rules apply): concrete-stat lead, e.g. "AAPL closed higher in this window in 14 of the last 15
  years. We log a pick like this every market day - publicly, before the outcome."
- [ ] **Kill the self-contradiction**: hero claims "78-86% AI win rate" while the strip below shows 70%
  on 10 picks. Define exactly TWO labeled rates computed by ONE shared function: "backtest 78-86%
  (walk-forward, method linked)" and "live record: X of N picks since Mar 2026."
- [ ] **Scorecard truth package** (`site/generate_scorecard.py`): raw 6W/4L is rendered as wins via an
  undisclosed realize-at-target rule (NVDA -1.3%, COP -2.1% shown as +6.8%/+4.9%); streak uses a
  different basis than the table; Win Prob shows identical 84.5% on 9/10 rows. Fix: rename column
  "Realized Return", disclose the exit rule in one line, show both bases ("80% realized / 60% held to
  close"), same basis everywhere, fix the Win Prob bug, show losses with one line of commentary
  (two-sided messaging measurably RAISES trust with skeptics).
- [ ] **Scorecard cadence honesty**: 10 picks Mar 17 - May 8, nothing since (multi-week gaps) under a
  "every trading day" promise. Restart the daily pipeline (appserver service-auth blocker) + cron
  `generate_daily_ai_pick.py`/`send_daily_ai_pick.py`, or state "logged since March 2026; daily
  publishing resumes <date>".
- [ ] **One source for marketing numbers** (`brand_stats.py`): 15 ACTIVE markets (ids 0-13,16; the audit had it backwards - the page was right), 98 years (page
  says 100/98/"nearly a century"), real user count (page says 250+, truth ~222 - say "200+"), picks
  logged N. Every generator imports it.
- [ ] **Remove the engagement-hack stack**: the 1.5s tab-title flasher ("Free daily AI pick waiting...")
  above all - it is the screenshot an affiliate's skeptical reader posts. Keep ONE exit-intent at most.
- [ ] **Fix mislabeled CTAs**: hero secondary "Watch How It Works" anchors to #testimonials -> retarget
  "See the Live Track Record" -> /scorecard.html; footer "Methodology" points at a nonexistent anchor
  -> point at /research.html.

## P2 - CONVERSION ARCHITECTURE (week of June 16, after P0/P1)

- [ ] **Make the scorecard a conversion surface**: remove hardcoded `noindex` (scorecard.html:7 - also
  research/about/daily-pick generators); add meta description + OG/Twitter card; add "Create Free
  Account" CTAs under the stat boxes; 3-sentence forward-tested wedge ("Every pick logged before the
  outcome - wins and losses"). This is the asset NO competitor has; lead with it everywhere.
- [ ] **Land signups in the product, not /account**: signup state default + hero CTA ->
  `/app/?o=<today's pick>` deep link (WorkOS round-trip preserves it). First-value moment = a live
  in-season pattern, ideally the ticker they arrived from.
- [ ] **Turn on lifecycle email**: the drafted "TW Welcome v2 (Explorer)" + "TW Trial (7-day)"
  MailerLite automations exist but are OFF. Enable + add a day-5 pre-charge notice. Add "Card
  required. No charge for 7 days. Cancel in one click." at every trial button.
- [ ] **Fix the freemium gate** (free->paid pressure is structurally weak): open paywall gives Explorer
  all 15 markets AND ML (config.py:237/515) while the pricing page sells exactly those; the in-app
  upgrade banner is disabled (`config.upgrade_message=''`). Decide the gate consciously. STRONG
  pattern from category research: **reverse trial** (new signups get 7 days of full Strategist, then
  auto-downgrade to Explorer; benchmarks 15-30% free->paid) + make locked features VISIBLE (blurred ML
  column with inline unlock; greyed locked markets), + upgrade prompts at value moments (limit-hit
  events), not timers. NOTE: changing the open-paywall decision = an Afshin call, not a default.
- [ ] **Pricing section mechanics**: default the toggle to ANNUAL; show savings in dollars ("Save $120
  a year"); highlight Analyst as default with Strategist as upgrade; "cancel anytime in one click"
  next to the price; honest TIER_FEATURES comparison table collapsed below; consider a 30-day
  money-back line (Afshin call).
- [ ] **One shared conversion partial on every content page**: proof strip (scorecard stats + link) +
  working email capture + one CTA, included by the patterns/insights/learn/markets/research
  generators. Today: insights (10 strong articles), 6 learn guides, 103 pattern pages, 7 market pages
  capture ZERO emails and mostly dead-end ("Continue reading" only; one article prints "(/app/)" as
  unlinked text).
- [ ] **Kill the learn stub**: nav/footers point at /learn.html ("coming soon") while 6 finished guides
  live at /learn/. Retarget everywhere.
- [ ] **One CTA verb sitewide** (category pattern): pick one ("See today's pick free" / "Start free")
  and repeat on home, scorecard, patterns, affiliate pages.
- [ ] **Named testimonials**: ask the 22 payers for 3-6 named quotes with role context. NO
  return-percentage quotes (testimonial laundering - the competitor mistake).
- [ ] **WorkOS trust line**: "You will see workos.com - that is our secure login provider" under the
  auth buttons (the consent screen says workos.com until the custom domain).
- [ ] **Mobile + speed pass**: 1 hour real-device test of home -> signup -> scorecard; one Lighthouse
  run; fix the top 2 items. Affiliate X/newsletter traffic is majority mobile.

## P3 - GROWTH LAYER (after June 16)

- [ ] Fix hardcoded retired-domain canonicals/og/sitemaps in `generate_insights.py:135-186`,
  `generate_learn.py:140-194`; og:image is relative AND the file does not exist - shares render bare.
- [ ] Pattern pages SEO: evergreen titles (currently bake dated AI signals), plain-English stat sentence
  per page (snippet bait: "AAPL has averaged +X% in this window, higher in 14 of 15 years"),
  month-of-year discovery pages ("What is seasonally strong in June") as the internal-linking layer,
  de-dupe the /markets/ vs /_static/markets/ trees.
- [ ] Re-run text/ticker generators on a schedule (pages claim "Updated daily" while 33 days stale).
- [ ] **MCP/ChatGPT teaser block** on home: "Ask TradeWave from inside ChatGPT and Claude" + waitlist
  capture - a category-first differentiator no competitor has; honest teaser, ships with the ~week-5
  MCP beta moment.
- [ ] Annual-plan bonus artifact: CSV/Excel export of pattern stats for yearly subscribers (cheap,
  sticky).
- [ ] Founder + methodology page: who builds this, how stats are computed (suits an evidence-first solo
  founder; their version of competitor award-bios).

## The 200 existing free users (DO FIRST - before the affiliate noise)

One-time founder email to the warm base BEFORE June 16: today's pick + the scorecard + what Analyst
adds + the 7-day trial. The single fastest revenue action available. (Requires P0 email capture +
pipeline fixes so the pick/scorecard are fresh.)

## Affiliate enablement (protects the whole push)

One-page APPROVED-CLAIMS sheet per affiliate: real prices ($47/$37, $149/$99 + their discount),
evidence-first framing, scorecard + pattern deep links, the no-promises style rules. Without it,
affiliates will copy the hype hero and quote the wrong prices. (Michael's kit exists at
`docs/marketing/affiliate_kits/` - add the approved-claims page + correct anything quoting page prices.)

## Competitor cheat sheet

**Seasonax** (premium, institutional): steal - card policy stated at the CTA, trial unlocks TOP tier,
one CTA verb, named testimonials, concrete scale numbers, methodology/founder page, annual-savings
framing. Avoid - testimonial return-laundering, unquantified "high-probability" hype, $100/mo anchor.
**Financhill** (retail, score-driven): steal - hyper-specific stat copy, live product data on the
homepage (rows blurred behind signup), ML win-prob as THE hero number, programmatic SEO scale, daily
pick as an email funnel, fast time-to-first-value onboarding. Avoid - absurd backtest returns
("1,841,637%"), "100% accuracy", scarcity theater, trap trials, confirm-shaming.
**EquityClock** (free, ad-supported): steal - plain-English stat sentence per chart (snippet bait),
prominent methodology statement, month-of-year discovery nav, quantified catalog, fresh dated content
daily, "cancel anytime" next to price. Avoid - hard paywall with zero preview, persona-not-product
credibility, conflict-of-interest upsells.
**TradeWave's wedge vs all three**: the public forward-tested ledger (none of them logs picks before
the outcome and shows losses) + ML scoring + soon "works inside ChatGPT/Claude". Be the one that says:
"Verify any number on this page."

## Execution order (the 8-10 days)

Day 1-2: P0 plumbing (email IDs, ticker CTAs, stripe success/double-sub, prices, /pricing params,
analytics). Day 3: regenerate everything stale (home, patterns full run, sitemaps, daily pick) + the
pick-card render fix. Day 4: P1 honesty package (headline layer, scorecard truth, brand_stats).
Day 5: 200-user founder email + affiliate kit corrections + /join deploy + end-to-end attribution
test. Day 6-8: P2 (scorecard conversion surface, signup deep link, lifecycle email, pricing mechanics,
shared content partial). Then Michael posts. P3 after.
