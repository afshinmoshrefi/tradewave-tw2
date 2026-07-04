# Homepage Review-Panel Backlog (2026-07-02)

Adversarial 5-reviewer panel on the redesigned dev homepage (post hero-tournament,
post implementation). Round-1 score 78/100; the 6 CRITICAL findings were fixed the
same night (footer MCP gate, Most-chosen badge, og:image/logo 404s, exact yearly
per-month prices, lead-modal deliverable wording, zombie generator copy) - verified
in the rendered page. Below are the MAJOR (non-critical) findings, deduplicated,
as the improvement backlog for after launch measurements arrive.

Panel scores (D1 beginner / D2 pro / D3 believability / D4 energy / D5 proof /
D6 funnel / D7 honesty):
- a beginner retail trader seeing this cold: total 81 (d1=11 d2=13 d3=13 d4=7 d5=13 d6=13 d7=11)
- a skeptical professional quant/RIA: total 74 (d1=12 d2=10 d3=11 d4=8 d5=11 d6=12 d7=10)
- a CRO auditor (NN/g evidence, CTA hierarchy, offer: total 73 (d1=12 d2=13 d3=11 d4=7 d5=10 d6=11 d7=9)
- a front-end mechanics + mobile auditor: total 84 (d1=13 d2=13 d3=13 d4=8 d5=13 d6=12 d7=12)
- a trust-and-compliance auditor: total 78 (d1=13 d2=13 d3=11 d4=8 d5=12 d6=13 d7=8)

## Major findings

1. [01 Hero trust strip (rendered lines 521-528)] Mixed denominators with no bridge: '20 picks on the public ledger' then '6 of 10 held a profit to the close'. A cold visitor immediately asks 'what happened to the other 10?' - the answer (pending/unresolved) is invisible, so the FIRST proof element on the page reads like selective counting, the exact scam-prior it exists to defuse.
   Fix: Change the generator's trust_strip.held_label to carry the denominator's meaning, e.g. '6 of the 10 resolved held a profit to the close' (labels live in generate_home_page.py ~line 1050; this is outside the locked hero winner copy).

2. [<head> OG/JSON-LD metadata (lines 27, 35, 49)] og:image and twitter:image point to /static/images/og-image.jpg and the Organization logo to /static/images/logo.png - /static/ does not exist on the box (verified 404). Every social/chat share of this page renders imageless, and the URLs are relative (scrapers need absolute). Borders on a broken mechanism.
   Fix: Point both to a real absolute asset (e.g. https://<host>/_static/evidence_hero.png or a purpose-made 1200x630 OG card dropped in /_static/), driven from the generator's host config.

3. [04 Your Stocks / 10 Before You Go micro-copy (lines 611, 930)] 'your report lands in your inbox in about a minute' overpromises versus the actual double-opt-in flow the modal reveals: confirmation email first, click it, THEN the report 'usually within a couple of minutes'. The first thing a captured lead experiences is the promise being wrong - bad moment to lose trust.
   Fix: Align the band copy to the real flow: 'confirm your email and the report follows within minutes' (bind via the content dict); keep 'about a minute' only for the confirmation-email step.

4. [Nav (line 502) + footer (line 961)] 'Wave Viewer' links send a cold logged-out visitor straight to the WorkOS signup wall with no warning - the audit killed 'Launch the live demo' for exactly this dead-end, but the nav still routes first-click product-curious visitors into an unbranded auth screen.
   Fix: Use the existing /api/me auth-swap JS to retarget the nav/footer Wave Viewer links for logged-out visitors (e.g. href /signup?next=/app/ with text unchanged, or point them at #tara/#evidence); leave the logged-in href as /app/.

5. [05 The Ledger scorecard table (lines 633-637)] The two summary-rate rows are jammed under the PICK / LOGGED / RESULT column headers ('Held to close | 6 of 10 | 60%' scans as a pick named 'Held to close' logged at '6 of 10'), muddying the page's core proof artifact at the moment of inspection.
   Fix: Split the two rate lines out of the pick table - render them as a small stat strip above the table (or give them their own header-less styled block) in the template's ledger section.

6. [09 Who It's For (line 891) + duplicated report bands (605 vs 924)] 'Whoever's Asking, It Bends to You' is vague and slightly awkward at the self-selection moment, and sections 04/10 repeat 'Name up to three stocks you hold - we'll email each one's full per-year record' verbatim - the repetition reads templated and drains late-page energy (main D4 tax).
   Fix: Sharpen the segmentation headline (e.g. 'Same Evidence, Priced to Your Job') and vary the section-10 re-offer line (e.g. 'Leaving anyway? Take each stock's full per-year record with you') - both bound through the content dict.

7. [Hero trust strip] '20 picks on the public ledger . 6 of 10 held a profit to the close' - the unexplained denominator jump (20 vs 10) is the first thing a skeptic sees and it pattern-matches to cherry-picking; the real reason (10 picks still open) is never stated above the fold.
   Fix: Make the denominator logic explicit in the strip labels (content.hero.trust_strip): '20 picks logged . 10 resolved: 6 held a profit to the close . 10 still open'.

8. [05 The Ledger preview] The 'receipts' panel shows five rows that all read 'pending' - zero visible outcomes. 'Losses included, nothing removed' is asserted but never demonstrated on-page; the proof moment the whole page is built around is hollow, and 5x 'pending' looks like nothing ever resolves.
   Fix: Change build_ledger_rows() to interleave the most recent RESOLVED picks (green wins and at least one red loss - the loss is the trust engine) with 1-2 pending rows.

9. [05 The Ledger scoreboard] Both metrics render identically ('Held to close 6 of 10 60%' / 'Reached target 6 of 10 60%') - to a careful reader it looks like a copy-paste bug, and it wastes the panel on redundant-looking numbers.
   Fix: Surface the already-computed but unused stats (median realized close return, current streak from compute_homepage_scorecard_stats) alongside the two rates, so the panel reads as a real scoreboard even when the rates coincide.

10. [06 What Traders Say] Erin West's quote is an earnings claim ('five-figure trades') carried by an affiliate; the material-connection disclosure is present but there is no results-not-typical qualifier - a compliance gap and a scam-prior trigger for exactly the skeptical pro/RIA persona.
   Fix: Extend the existing disclosure line: 'Their results are their own, are not typical, and are no guarantee of future results.'

11. [01 Hero] The fold still stacks nine elements (eyebrow, H1, subhead, trust strip, CTA, no-card micro, report lead-in, report card, disclaimer). The quiet-card hierarchy fix helped, but on mobile the secondary offer plus its lead-in line pushes the disclaimer and Tara hook well below the fold.
   Fix: Collapse the hero's report lead-in + card into a single text link ('Or get the free seasonal report on stocks you own - no account', keeping data-lm-open/data-lm-source=hero); the capture stays full-strength in sections 04 and 10.

12. [09 Who It's For] Vaguest copy on the page for the pro persona: 'Whoever's Asking, It Bends to You' and 'priced to the job in front of you' say nothing falsifiable, and the pro card promises 'CSV' - a capability not evidenced anywhere else on the page or in the tier cards.
   Fix: Concrete h2 (e.g. 'One Engine - 15 Markets, a Century of Data, Three Ways In') and either verify the CSV export path exists and name where it lives, or drop 'CSV' from the card.

13. [Head / meta description] Meta description asserts 'REST API included.' but no tier card lists API access and the page itself pitches the API only through the funds/enterprise 'Talk to us' kicker - a SERP/social promise the page does not keep (D7 consistency).
   Fix: Reword to 'Documented REST API available' or name the tier that actually includes API access, in the generator's description string.

14. [07 Pricing / Strategist bullets] 'publish up to 500 date-range reports' uses jargon defined nowhere on the page; a prospect cannot map 'date-range report' to value, so the enforced 500-cap entitlement reads as filler.
   Fix: Reword in plain language tied to the same enforced quota (e.g. 'track and publish up to 500 opportunity reports across 100 portfolios') or add a one-line parenthetical defining a date-range report.

15. [Scripts / GA cta_click] The GA cta_click listener only handles anchors (closest('a')); all three paid-tier CTAs are <button type=submit> in checkout forms, so the funnel's most important click is never measured - crippling for the A/B program this loop is meant to feed.
   Fix: Extend the listener to also catch submits/clicks on .pricing-signup-btn buttons (fire cta_click with the form's tier + period before submit).

16. [05 The Ledger - scoretbl rows (home.html:639-647, generate_home_page.py build_ledger_rows)] All 5 visible ledger rows are 'pending' - the proof centerpiece shows ZERO resolved outcomes. The page repeatedly claims 'losses included, nothing removed' but a visitor never sees a single win or loss on the page; the loss-inclusive trust engine is asserted, not felt.
   Fix: Change build_ledger_rows() to guarantee resolved rows in the preview (e.g. newest 3 open + newest 2-3 resolved, rendered with the existing res-w/res-l colors) so at least one visible loss is literally on the board next to the wins.

17. [Hero trust strip (home.html:519-529)] Unexplained denominator shift: '20 picks on the public ledger' followed by '6 of 10 held a profit to the close'. A skeptical reader immediately asks where the other 10 went - at the single most scrutinized element above the fold, this invites the exact suspicion the strip exists to kill.
   Fix: Label the denominator via content.hero.trust_strip.held_label: '6 of 10 resolved held a profit to the close' (or append '10 still open' from scorecard_stats.open_count - the field already exists).

18. [05 The Ledger - scoreboard header (home.html:633-637)] The summary rows 'Held to close | 6 of 10 | 60%' and 'Reached target | 6 of 10 | 60%' render under the column header 'PICK | LOGGED | RESULT', so the stats read as picks named 'Held to close'. Confusing information design at the exact trust moment.
   Fix: Render the two rate stats as their own labeled summary strip above the pick table (or give them a separate header row), keeping the PICK/LOGGED/RESULT header only over actual pick rows.

19. [07 Pricing - yearly price display (home.html:745, 778, 813; generate_home_page.py _stripe_prices)] The yearly view shows only a rounded per-month figure ('$33/mo, billed yearly' from round(yr/12)) and the actual annual charge appears NOWHERE on the page - Analyst's rounding understates the real price ($33 x 12 = $396 vs the true annual total), and the buyer discovers the real charge only inside Stripe checkout. That is a checkout-surprise moment on the highest-intent click.
   Fix: Add the true billed total to the .bill line from the Stripe data the generator already has (e.g. '$399 billed yearly'), and keep the per-month figure as the anchor.

20. [02 Tara ask-bar (home.html:558-561)] The button promises 'See the Evidence' but a logged-out visitor who types a question lands on the WorkOS signup wall with no warning. The question does survive auth, but the visitor does not know that - the immediate-payoff expectation breaks at the wall, the same failure class as the old 'live demo' link.
   Fix: Add a micro-line under the askbar set via content.tara (e.g. 'Free account required - your question will be waiting for Tara right after signup'), or have the JS route show that expectation before redirecting.

21. [Nav + footer 'Wave Viewer' links (home.html:502, 961)] The first nav item sends a cold visitor straight to /app/, which is a WorkOS signup wall with zero context (and workos.com branding on the consent screen). Not a false promise, but a context-free dead end on the most prominent nav slot.
   Fix: For logged-out visitors keep the auth-swap pattern: point the homepage nav item at the Evidence section or label it so the signup step is expected ('Open the App - Free'); restore /app/ for authenticated users via the existing /api/me swap.

22. [04/10 free-report bands + lead modal (home.html:611, 930, 1221)] Band copy promises 'your report lands in your inbox in about a minute' but the actual flow is double opt-in: a confirmation email arrives first, and the report only follows after the visitor clicks the link ('usually within a couple of minutes'). The overstatement is only corrected after submit.
   Fix: Adjust the band/modal micro-copy in the generator content dict to match the mechanism: 'Confirm your email and each report follows within minutes' - keeps urgency, kills the post-submit surprise.

23. [Repeated CTAs and re-offer (home.html:531, 599, 940; sections 04 vs 10)] The identical label 'Start Free - Full Access for 7 Days' appears three times and section 10 is a near-verbatim clone of section 04 (same card, same micro-copy) - by the second exposure this reads as wallpaper and the late-page re-offer loses its second-chance value (banner blindness).
   Fix: Vary the late-funnel framing through the content dict: give the close CTA and section 10 distinct angles (e.g. close = 'Bring a Hunch' action verb CTA; 10 = loss-aversion 'leave with the record on YOUR tickers' framing with different button copy).

24. [04/10 Your Stocks + lead modal] Delivery overpromise vs the real double-opt-in flow: sections 04/10 and the modal reassure line say the report 'lands in your inbox in about a minute', but /api/lead-report actually sends a CONFIRMATION link first and the report arrives 'usually within a couple of minutes' AFTER clicking it (the modal done-state says so). The visitor's first post-capture experience contradicts the promise - exactly where trust was just extended.
   Fix: Align the band/modal micro-copy with reality: 'Confirm your email and each report lands within minutes' (bind through the content dict; keep the done-state copy as is).

25. [Scripts - GA cta_click listener] The cta_click tracker (rendered home.html:1153-1161) only matches anchors (closest('a')), but all three paid-tier CTAs are <button type=submit> inside GET forms - the highest-intent clicks on the page fire NO GA event, so the funnel launches blind on checkout starts.
   Fix: Add a submit listener: document.addEventListener('submit', ...) matching form[action*="create-checkout"], firing gtag('event','cta_click',{link_url: form.action + tier/period, link_text: button text}).

26. [Scripts - UTM passthrough vs billing toggle] UTM passthrough rewrites only live href attributes, but applyBilling resets a.cta hrefs from data-monthly/yearly-href on every toggle click - so toggling billing strips UTM params from the Explorer /signup CTA (attribution leak on a common interaction). Same clobber also reverts the auth-swap 'Your Plan' href from /account back to /signup for logged-in explorers. The tw_ref script already solves this by rewriting the data-* attributes (home.html:1020-1024); the UTM script doesn't.
   Fix: In the UTM IIFE (home.html:1327-1339), also rewrite data-monthly-href/data-yearly-href/data-monthly-url/data-yearly-url with the query string (copy the tw_ref pattern), and have applyBilling skip anchors carrying .is-current.

27. [05 The Ledger - scoretbl preview] All five visible ledger rows are 'pending' (NUE/EXPE/INTC/LEN/BLDR) - the loss-inclusive receipt the whole trust architecture rests on is never actually SEEN as a resolved win/loss row; a skeptic reads five 'pending' and only an aggregate 60%.
   Fix: Change build_ledger_rows() to interleave newest resolved picks (including at least one loss, res-l styled) with 1-2 pending ones so a real loss is visibly on the record above the fold of the section.

28. [Hero trust strip] '20 picks on the public ledger' next to '6 of 10 held a profit to the close' makes a skeptic do missing-denominator math (where did the other 10 go?) - it reads like cherry-picking even though the truth is 10 are still open.
   Fix: Make the denominator self-explaining: '6 of 10 resolved held a profit to the close' or add '10 still open' as a third segment (all fields already exist in scorecard_stats).

29. [Free-report capture (04/10 + modal)] Timing promise vs the double-opt-in reality: pre-submit copy says the report 'lands in your inbox in about a minute', but submission actually sends a confirmation link first (report only after the click) - the success screen reveals the extra step after the promise was made.
   Fix: Set the expectation up front: 'Confirm your email with one click and the report lands in about a minute.' in the band micro and the modal reassure line.

30. [05 The Ledger - founder provenance card] Founder quote overclaims: 'Every number on this page traces back to a per-year table you can open and an audit log you can read' - the Stripe prices and several counts trace to neither, handing a nitpicking skeptic an easy contradiction on the very card meant to close trust.
   Fix: Scope it: 'Every statistic on this page traces back to a per-year table you can open and a public ledger you can read.'

31. [Pricing - price provenance] The rendered $19/$14, $47/$33, $129/$99 exactly equal the generator's hardcoded fallback, so it is indistinguishable whether this render used live Stripe or --allow-price-fallback; the brief requires noting a fallback render, and a fallback render must never ship beyond dev.
   Fix: Regenerate once without --allow-price-fallback and confirm exit 0 (the generator fail-fasts on Stripe problems); record in the loop output which path produced the shipped HTML.

## Addendum (2026-07-02, free-report funnel review session)

The section-04 heading was owner-locked the same day: "Now Get That Same Track Record
for the Stocks You Own" (rationale + history in the project memory). Two new deferred
findings from that review (BOTH APPLIED to the template the same day, owner-approved;
uncommitted on feat/free-seasonal-report-funnel - kept here for the record):

15. APPLIED. [04 Your Stocks / 10 Before You Go frcard buttons (template lines ~567, ~725)] Both main capture buttons carry data-lm-open but NO data-lm-source, so their opens log as the generic 'card' source and - because window.__twLeadSource is only overwritten when a source attribute exists - a submit from these buttons is mis-attributed to whichever sourced trigger (hero/pricing/sticky) was clicked earlier in the session. The "should the capture section move higher?" placement question cannot be answered from analytics until this lands.
   Fix: add data-lm-source="inline-primary" (section 04) and data-lm-source="inline-late" (section 10).

16. APPLIED. [04/10 micro-copy "Free forever" (template lines ~572, ~730)] "Free forever" is plan language on a one-time emailed report, and the backend enforces a tiered day+week quota (LEAD_REPORT_QUOTAS in web/app.py) - a slight overpromise on the page's most honesty-sensitive surface. Related to finding 3 (same micro-line).
   Fix: "Free. No account, no card, no obligation."
