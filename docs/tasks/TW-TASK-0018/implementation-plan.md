# Seasonal Market News: membership, public previews, and article promotion

Status: FULL DISCUSSED DEVELOPMENT AND DEV DEPLOYMENT AUTHORIZED October 2, 2026. Afshin directed completion of the discussed development and deployment to Dev, continuing overnight. The earlier foundation checkpoint was a staged execution choice and no longer limits current scope. Free-launch SMN membership is agreed; monthly/annual prices remain dashboard draft/test fixtures. Routine Dev configuration, sandbox checkout and private video prototypes are authorized as needed. No production writes, real customer charges or external social/newsletter sending. Existing provider/math/admin-auth choices remain intact. Planning observations retain their original dates; see ../TW-TASK-0018.md for current claims/contracts.
Prepared: October 2, 2026, America/New_York.
Intended executor: a coding model such as Sol 6.1, working from this document and the current shared project records.
Owner: Afshin. This document contains the conversation's product decisions and proposed engineering choices; it does not establish a running service, payment offer, publishing authorization, or provider connection.

## Current implementation phase matrix - October 3, 2026 UTC

Dev is delivered/main `fd15013dc7a117f2882bc4820d9b016e4d30067b`, active `/opt/smn-worktrees/smn-membership-delivery-20261003`; daily pointer matches and final receipt is `active_verified`. Central application is `3cc399a0e451fcb45fedf1ee46ab9a3f3170c921`. The [canonical task](../TW-TASK-0018.md) and [sanitized evidence](../evidence/TW-TASK-0018-smn-dev-20261003.json) own current verification and exact paths. The original design and dated planning observations below remain useful requirements, not substitutes for runtime proof.

| Phase | Current state | Concrete next acceptance work |
|---|---|---|
| P0 Baseline/fixtures | Verified source/runtime inventory, isolated ownership, retained capsules and current canonical bindings. | Keep future article/source revisions exact; initial missing bearish fixture remains a historical finding. |
| P1 Public versions | Retained pilots plus genuine current ADP generation/import/real admin approval; 80 words, 107 retained hashes, source caps passed, full source unchanged. Exact source-bound social/Substack exports approved and live-proven. | Three archival pilots remain private/unqualified for current publication; final bullish/bearish/news media qualification is distinct from current ADP success. |
| P2 Private content | All 705 articles migrated; 46 selected corpus/1, 036 checks and 44-check XLK recovery passed. Exact delivered/main parity; protected bodies/assets/datasets private/fail-closed. | Future genuine scheduled edition evidence, not another unresolved Dev integration step. |
| P3 Reader identity | Genuine reader/admin WorkOS flows and separate session authority verified on Dev; free signup required. | Dedicated production reader application and later production release gates. |
| P4 Offers/billing | Active free offer; immutable $10/$60/30-day paid draft. TEST API and signed endpoint ledger delivery proof; central migration/lifecycle/race checks passed. | Hosted card-entry Checkout; final paid launch terms, refund/dispute policy, live Stripe/tax readiness. No real charges. |
| P5 Dashboard/editor | Settings, preview/copy review, dated jobs, pause/readiness/import/download and private editor/journal recovery live. Canonical/version export defects fixed; final Playwright export-review/media regression passed. | Preserve independent source/media/export gates; no external dispatch authority implied. |
| P6 Video | Four real narrated assets, 1, 093 existing credits. Four timed jobs imported; 48 artifact getters/decode/exact speech checks. Daily 44.120816s video+same-job VTT DevUI-approved/public, decoded 1080x1920, no-store, AI disclosure. | Three private archival article pilots pending qualification/media approval. QA was ASR exact text+timing+sampled frames; no human full listen/lip-sync/likeness QA. Unattended API key remains blocked. |
| P7 Promotion | Durable jobs/source-media separation; ADP social/Substack exports generated, reviewed in real UI, correct HTTPSlinks/no private body/repeat idempotency proven; dispatch disabled. | Live account/destination and separate external-post authorization before dispatch. |
| P8 Dev operations | Final source/main/daily parity active_verified; four stable services/zero restarts, controller settings bytes unchanged, legacy drop-in precedence corrected. 52 focused Windows/Linux+65 actual product checks at explicit core 4c3; final launch/UI-only delivery smoke. | Observe next scheduled edition; later staging/production gates. Dev independent integration work complete. |
| P9 Substack | Draft export adapter implemented; live pilot intentionally deferred. | Export proved/approved; later destination/access/posting authorization. Not a regular SMN blocker. |
| P10 Daily narrative | Reviewed public Oct. 3 headline roundup: 16 CNBC/NYT RSS headlines, stories not read, four preferred sources unavailable. Separate Oct. 2 complete-text wrap. | Keep source/cutoff/coverage limits explicit; broaden supported access before claiming a full preferred-source narrative. |
| P11 Avatar | API route implemented; no actual avatar generated and no account avatar/library model available. | New ElevenLabs key and explicit browser permissions, personal reference and account/model verification, bounded real generation and QA. |

The full discussed scope remains in progress. Generating/importing copy, approving source claims, reviewing media and publishing externally are distinct actions. No scope is marked complete solely because a route or adapter exists.

## 1. Outcome and decisions

Build on the existing Seasonal Market News (SMN) publication. Every article should have a useful public version that encourages reading the complete article. The site should support free registered membership initially, configurable trials and monthly/annual paid membership later, and article-derived social content plus an automatically produced 10-15 second video using Afshin's existing ElevenLabs voice. Add a separate daily briefing covering the main market news narratives, with a written version and an avatar video prototype made initially through ElevenLabs.

### Confirmed requirements

| Area | Required behavior |
|---|---|
| Public access | Anyone can read the public version without signup or login. |
| Complete articles | Reading a protected complete article requires a signed-in account with access. A zero price does not remove this requirement. |
| Launch | Afshin expects to start with free registered access. No card or payment is needed for a zero-priced membership. |
| Paid access | Support configurable trial length followed by paid membership. Discussed amounts and durations are examples, not approved commercial terms. |
| Plans | Monthly and annual subscriptions; annual amount or discount adjustable in the dashboard. |
| Exclusions | No lifetime or one-time membership. Price-increase scheduling, phased increases, migration campaigns and price-change notices are deferred. |
| Public writing | The planner owns how to make the public version informative and compelling. Examine real articles; do not invent a generic solution without examples. |
| Social | Include the capability to prepare and, when activated, distribute article-related social posts. Channels, account connections and posting cadence remain to be selected. |
| Substack follow-up | After regular SMN publication is established, add a free Substack digest/shorter version linking to complete articles on SMN. This channel must not delay the regular SMN launch. |
| Video | Automatically create a 10-15 second clip for each eligible article using Afshin's ElevenLabs voice. Show the relevant TradeWave chart for a few seconds while the narration explains the article's pattern. |
| Daily briefing | Select and connect the day's major market headlines across companies, the economy, interest rates and world events. Tesla, NVIDIA, rates and war were examples of possible subjects, not a fixed daily checklist. |
| Headline sources | Begin the daily editorial scan with CNBC, Bloomberg, Reuters, The New York Times business coverage and The Wall Street Journal, as Afshin requested. Financial Times is the recommended additional source for international markets/economics. Supplement with primary releases and other credible sources where needed; this is not an exclusive list or a claim of verified feed connections. |
| Daily avatar prototype | Use an avatar model available through ElevenLabs initially, with Afshin's likeness and existing ElevenLabs voice. This is the selected development direction; the exact avatar asset, model and account access still need verification. |
| Planning | Write an explicit plan before implementation. A coding executor must not have to reconstruct business intent from the voice conversation. |

Interpretation of the video discussion: "in the middle of the article" is taken to mean the middle of the short promotional video, because the surrounding discussion concerned narration and showing charts "just for a few seconds." The written complete article already has charts. Show this interpretation in the first storyboard; do not remove or reposition the existing article charts as part of this feature.

### Proposed choices made in this plan

These choices make the plan executable without pretending Afshin already selected them:

- Use a separately written public preview, normally 90-150 words, rather than a blind character cutoff. The preview delivers one substantive finding and explains what deeper understanding the complete article provides.
- Start with one full-article membership entitlement, offered in free, monthly or annual forms. Do not invent several content tiers.
- Use the existing WorkOS identity ecosystem and existing Stripe infrastructure, with SMN-specific access and billing records.
- Recommended membership home: SMN owns the reader signup, access rules and paid offers; Stripe processes payments. Keep Substack free as a discovery/newsletter channel. Afshin has accepted the later Substack distribution scope but is still considering the paywall platform; this recommendation is not a separately approved billing decision.
- In paid mode, use a card-free, application-managed trial. At its end, an unpaid reader retains public access and chooses a subscription to regain full access. No automatic charge without a completed, consented subscription.
- Configure an exact number of trial days. Default draft configuration is 28 days; it is a proposal for review, not published copy. Use "28 days," not "one month," if that is the setting.
- Produce portrait MP4 article clips initially, using the article's real charts, captions and Afshin's narration. The separate daily briefing now requires an ElevenLabs avatar prototype; this does not make avatars mandatory in the 10-15 second article clips. No invented financial-chart animation or background music is required.
- Generate promotion assets automatically; external posting remains disabled until the relevant account/channel and operating rules are activated. After activation, routine posts should not require Afshin's daily involvement; exception review should handle failures.
- New plan versions apply to new enrollments. An existing member's terms cannot be silently migrated by editing a price field.

### Choices deliberately left for launch, not for the coding model

Membership/paywall home before implementing reader billing; currency and actual prices; final trial duration; chosen social accounts and publishing cadence; treatment of launch members when paid enrollment opens; initial archive migration scope; and the tested ElevenLabs model/settings.

Build the stated configuration surfaces and explicit launch gates. Do not make up live prices, promise permanent free access, migrate current members, or turn unresolved options into hardcoded behavior. While these choices remain open, free-mode development and sandbox paid-flow tests can proceed under the October 2 development authorization when their dependencies and milestone scope are ready.

## 2. Evidence and current baseline

### Source inspected

The SMN and shared TradeWave repository refs were fetched during planning. Source facts below are source observations, not a claim that the same revision is running in production.

| Repository | Inspected current ref |
|---|---|
| afshinmoshrefi/SMN | 1663cecd62e0accf9dc9ff52f7c4a2f16e7f2e4f |
| afshinmoshrefi/tradewave-tw2 | 8d64eb364da3590c147497d99e1f72cb352c3d54 |

The local SMN inspection checkout was C:/Users/afshin/Documents/TradeWave Main Orchestrator/smn-recovery-20261002. It was older than fetched main; changed authentication/editor files were read from origin/main. Executors must start from newly fetched current main and preserve newer work.

| Existing surface | Verified observation | Consequence |
|---|---|---|
| SMN blog/subscription_publication.py | Packages complete HTML and assets under public edition paths; copies selected evidence JSON/CSV assets. | Membership requires a real public/private publication split, including assets. A CSS fade cannot protect these files. |
| SMN blog/subscription_edition.py | Receives structured articles, binds writer/evidence hashes, counts source-derived words and renders private drafts. | Derive previews from reviewed artifacts and preserve existing receipts; do not rerun good full articles unnecessarily. |
| SMN blog/schemas/subscription_article.schema.json | Contains sections, source references, takeaways and native chart references. The inspected example has study-specific enums. | Generate per-article schemas from its bundle; do not reuse the example's hardcoded source/chart IDs. |
| SMN blog/article_index.py | posts.json is the catalog authority; modifications use a catalog lock and atomic writes. | Extend the existing catalog and publication transaction; do not create a competing public index. |
| SMN blog/pub_dashboard.py and templates/pub_dashboard.html | Separate Flask dashboard with article, schedule, generation, settings, API and audit surfaces. | Extend this dashboard; keep reader traffic and public authentication separate from administrator authorization. |
| SMN blog/dashboard_auth.py and dashboard_workos.py | Admin-only login, direct WorkOS PKCE flow and existing signed TradeWave admin tickets/API/service authentication. | Reuse provider patterns, but never loosen the administrator check to admit readers. |
| SMN blog/article_editor.py and article_editor_routes.py | Newly added private, versioned model-assisted editing, with owner checks and publication recovery. | Editor reads/writes must follow the new content store. An edit invalidates derivatives bound to the prior full-article hash. |
| TradeWave web/models.py | Users, WorkOS identity, Stripe customer, separate web/API subscriptions, event history and durable checkout claims. | SMN is a separate product line. Do not overwrite web/API tiers, trials or subscription identities. |
| TradeWave web/checkout_claims.py | Durable checkout idempotency; current product-line constraint permits eod/api only. | Add smn to the existing contract and migration when reusing it. Test cross-product independence. |
| TradeWave web/app.py | Existing checkout, subscription resolution, Stripe webhook, account and WorkOS flows. | Add a narrowly scoped SMN billing module/dispatch branch, preserving existing behavior. |
| SMN blog/m_daily_ai_pick_social.py | Legacy social helper includes Publer and Facebook functions. | A discovery lead only; not evidence of working, authorized SMN distribution. Do not run it or inherit its credentials/settings blindly. |

Current shared task records were also reviewed, including TW-TASK-0017 for direct dashboard WorkOS login. Its evidence distinguishes verified Dev login from an incomplete/failed later production qualification. Do not infer reader login or production readiness from the administrator login task.

### Real article examples examined

1. [Microsoft October midterm article](https://seasonalmarketnews.com/articles/US/2026/10/11/microsoft-msft-has-rallied-in-9-of-9-midterm-oct-11-20-windows-averaging-4-5-gains.html)
2. [AMD midterm autumn article](https://seasonalmarketnews.com/articles/US/2026/09/30/ai-tailwind-meets-10-for-10-midterm-fall-losing-streak-for-advanced-micro-devices-amd.html)

Article text and chart descriptions were inspected. Chart pixels and retained engine responses were not independently inspected in this planning pass. These are editorial examples, not certification of their financial claims.

The Microsoft page contains different current-price values in its prose and a chart description; AMD has a similar discrepancy. These may reflect different snapshots and require source/timestamp inspection. Do not silently reconcile them, calculate a replacement, or reuse a current-price claim in a teaser until resolved. This plan does not authorize repairing the published originals.

## 3. First deliverable: prove the public version on real articles

Before developing a generic generation stage, use three retained, reviewable articles: a bullish study, a bearish study, and an article whose main angle is current news. Reuse immutable evidence; do not launch a fresh edition to create test inputs.

For each, retain:
- Canonical article identity, approved full-article hash and approval receipt.
- Engine study/export identity, source bundle hash, source locators and native chart identities.
- Draft public headline/preview, membership invitation, social copy and video script/storyboard.
- A claim-to-evidence map and the reason each selected element earns space.
- Review result and exact unresolved claims, if any.

### Editorial contract

The preview must:
1. Identify the subject and why this article is worth reading now.
2. Deliver one concrete, supported insight, with its relevant limitation.
3. Establish a specific unanswered reader question that the full article actually answers.
4. Describe that additional value plainly, such as the year-by-year evidence, adverse moves or interaction with current news.
5. Offer one truthful next step reflecting the reader's current membership mode.

Avoid mechanical extraction, empty suspense, "secret" claims, unsupported urgency and hiding a material limitation behind signup. Do not turn a historic hit rate into a probability of the next outcome. Avoid revealing every table and conclusion in the preview, but never make the public portion misleading by omission.

The 90-150 word target is editorial guidance. Permit a justified exception when needed for clarity. Do not fail useful copy solely on a word count, or pad it to reach a target.

### Draft example A: Microsoft

Proposed public headline: **Microsoft's clean October record hides a bumpier ride**

Draft preview:

> Microsoft's October 11-20 window finished higher in all nine midterm-election years in the article's TradeWave study. That is a striking historical record, but the closing result leaves out the path investors experienced along the way. Even winning windows included meaningful pullbacks. The full article examines the year-by-year results, the swings inside the window, and the business context. Use that history to understand the setup and its limits; it does not guarantee this year's outcome.

Draft video narration:

> Microsoft's October pattern looks consistent. Its TradeWave chart also shows the pullbacks hidden inside winning periods. Read the full article for the evidence and the risks.

Show the same study's net-and-excursion chart during the middle of the clip. This draft still needs exact engine binding, a readable chart treatment, voice generation and measured timing.

### Draft example B: AMD

Proposed public headline: **AMD's AI story meets a very different seasonal record**

Draft preview:

> The AMD article contrasts AI enthusiasm with a historically weak September 30-October 17 midterm window. Its short-direction study also shows why a favorable closing move would not make the path comfortable. The full article puts the seasonal evidence beside the business context and the risk of sharp adverse rebounds. Historical patterns can break.

The video should explain stock-price weakness and adverse rebounds for a short study correctly. Do not narrate a positive short-trade result as a rise in the stock. Use this fixture specifically to catch direction/sign errors.

These are planning drafts derived from the linked articles. They are not published offers, investment recommendations, validated voice samples or production-approved copy.

## 4. Access rules and reader experience

Authentication answers who the reader is. Entitlement answers whether that reader may read the full article. Price is a separate commercial setting.

| Reader state | Public version | Protected full article | User-facing next step |
|---|---|---|---|
| Anonymous | Available | Denied | Free-mode signup, or clearly stated paid-mode trial invitation |
| Authenticated but email unverified | Available | Denied under proposed default | Complete verification |
| Verified member with free-launch grant | Available | Available while grant is valid | Read article |
| Verified member in unexpired SMN trial | Available | Available | Show trial end in account view |
| Active paid member with current access | Available | Available | Read article/manage membership |
| Canceled at period end, paid-through time not reached | Available | Available | Show actual access end |
| Expired trial or access period | Available | Denied | Choose monthly/annual plan |
| Initial payment incomplete or awaiting confirmation | Available | Denied unless another valid grant exists | Complete payment or wait for confirmation |
| Suspended/revoked member | Available | Denied | Appropriate account/help message |
| Entitlement service unavailable | Available | Do not reveal protected content without valid bounded cached authority | Retry message, operational failure recorded |

Access validity is evaluated using server UTC instants with an exclusive end boundary: access ends when now is greater than or equal to ends_at. Display user-facing dates in the configured local timezone. Tests must use a fake clock around the exact boundary and a daylight-saving transition.

One account receives at most one initial SMN trial. Logging out, changing plan, reopening Checkout, changing email or retrying signup must not reset it. Free launch does not run an invisible trial countdown. Trial-duration settings affect newly granted trials; already issued grants retain their recorded end time.

Entitlement evaluation order is fixed: reject invalid identity/session; apply an explicit membership suspension; otherwise allow if at least one unrevoked SMN grant has started and has not ended. An expired trial does not override a valid paid grant. Record the chosen grant and reason in the server decision. Enrollment and first-trial issuance occur in one transaction with uniqueness constraints, so simultaneous callbacks cannot issue multiple trials. Configuration permits 0-365 trial days; zero means no trial, never unlimited access. Reject negative, fractional or out-of-range values.

### Page behavior

- Keep one canonical URL per article. Anonymous and authenticated visitors receive the appropriate server-rendered representation at that URL.
- The public page contains title, public preview, approved public visual where useful, and an accessible membership invitation.
- Full members see the complete article without a repeated signup block.
- Return to the originating article after signup/login/Checkout using an allowlisted same-site path.
- If a fade is used, apply it only to public presentation content. The withheld text must not exist in the anonymous DOM, page source, script payloads, structured data or network responses.
- Keep an obvious sign-in path for existing members and preserve keyboard/mobile accessibility.
- Account registration and newsletter subscription are separate choices. Existing email subscriptions are not proof of reader identity and do not silently create paid access.

### Free-to-paid transition boundary

The initial implementation supports paid enrollment for new members and preserves recorded grants/subscriptions. Opening paid enrollment must show Afshin the existing free-member count and explain that those grants are unchanged.

Do not implement a global toggle that silently expires free-launch members or bills them. A launch-member migration needs a later explicit policy; automatic price-increase workflows remain deferred. Do not market a free-launch grant as lifetime access.

## 5. Architecture and authoritative data

### Separate responsibilities

1. **Existing article pipeline:** research, engine evidence, full article, full-article review.
2. **Derivative stage:** creates public preview and promotion package from the approved article and its evidence.
3. **Publication/content store:** atomically makes the preview public and the full article private, retaining catalog identity and version history.
4. **Reader service:** handles reader sessions and returns preview or full content after entitlement checks.
5. **Membership/billing service:** uses the existing TradeWave database/provider infrastructure for SMN identities, grants and Stripe events.
6. **Promotion worker:** creates audio/video and posts through configured adapters only after the article is verified live.

Implement the reader service as a separate Flask application/process in SMN. Do not turn off the existing dashboard guard or expose administrator APIs to the public. Keep billing authority in TradeWave's existing web/database tier, with a small SMN-specific module rather than another independent payment backend.

### Identity design

Reuse the existing WorkOS account identity with a dedicated reader application/callback configuration and reader cookie/session namespace. The existing dashboard application's admin ticket is not a reader entitlement.

Bind memberships to a stable, verified WorkOS subject and its central user ID. Reuse an existing User when the verified subject matches. For a new SMN registration, create the shared identity through an explicitly SMN-scoped path that does not start TradeWave reverse trials, grant TradeWave roles, fire unrelated marketing enrollment or modify a current user's tiers. Preserve normal TradeWave signup behavior in its existing flow.

Use PKCE/state, exact allowed callback origins, issuer/application/environment validation and secure server-managed session handling based on the existing patterns. Reader logout must not expose provider tokens. Do not store a long-lived entitlement in the browser as authority.

Recommended entitlement cache ceiling: 60 seconds, bounded further by grant expiry. Revoke/invalidate it on membership changes. On an expired cache plus authority outage, public content remains available and protected content stays protected.

### Proposed data additions

These were the initial proposed contracts. Central additive migration `fa8c2d601b93` and the implemented SMN-only records are now active on Dev; use the canonical task and current source for final names. Preserve the requirements below and existing TradeWave product isolation.

| Record | Required fields/invariants |
|---|---|
| SMN membership | Stable user FK; created/verified times; first trial start/end; suspension state; unique membership per identity; separate SMN Stripe subscription ID/status; no writes to existing web/API subscription fields |
| Access grant | User, source (free_launch/trial/paid/admin), start, exclusive end or explicit open-ended grant, policy version, revocation and audit reference; derivation must be deterministic |
| Offer version | ID, currency, monthly minor-unit amount, annual pricing mode, annual amount or discount basis points, trial days, enabled intervals, status, effective enrollment time, exact Stripe product/price IDs, creator/audit |
| Billing/event binding | Reuse event ledger and checkout claims with product_line=smn; exact customer, subscription, price and user binding; processed/error state |
| Public derivative | Article ID/revision, full/source/engine hashes, public title/preview, claim references, full-article value promise, allowed public asset IDs, reviewer receipt |
| Promotion job | Article revision + kind + channel/template/voice version as unique key; state, attempts, next retry, lease, outputs/hashes, provider request ID, final post receipt |
| Settings/audit | Versioned global enrollment, video and distribution settings; actor, before/after, timestamp; never secrets or customer payment data |

Article identity must be the stable catalog identifier/canonical URL plus revision, not just a ticker or publication date. Two studies for the same instrument must not share derivative or promotion jobs. Use database uniqueness for initial grants, Stripe events, checkout claims and job keys; a check followed by an unprotected insert is insufficient.

Store article/media artifacts and job state in SMN's private state/storage, not in the public catalog. The central database owns membership/billing. Use the existing SMN atomic-write, locking and SQLite job patterns where appropriate; do not put payment authority in an ad hoc JSON file.

### Content-store boundary

Introduce a single content-store adapter used by the publisher, reader, administrator preview and article editor. It must return a specified article revision and representation; callers must not guess filesystem paths.

- Private full bodies and protected assets live outside every public Nginx/Cloudflare document root.
- Public previews and deliberately approved teaser assets use an explicit allowlist.
- Never copy an entire evidence directory into the public package by extension alone.
- Register every old and new canonical article URL to the correct access policy. Inventory both /articles/... and /editions/... paths and alternate raw/static routes.
- Public home/search/posts metadata contains approved summaries only.
- Keep internal provenance, raw source bundles, paid-content data exports and job records private.
- Preview/full versions activate together under the catalog/publication transaction, or neither activates.
- Editor updates invalidate previous preview/video/social approvals; already-live derivatives remain attached to their historical revision until a reviewed replacement or withdrawal is deliberately published.
- Unpublishing an article cancels pending promotion and removes public access to its preview/full assets according to existing unpublish behavior.

Authenticated HTML and private assets use private, no-store responses. Configure edge caching to bypass authenticated requests and ensure a member response can never populate the anonymous cache. Test actual reverse-proxy/cache behavior, not only Flask headers.

Public cache identity includes preview revision and active offer version, or activation explicitly invalidates all affected public responses. A paid-mode change must not leave a cached promise of free access. These controls protect future server responses; they cannot retract copies of articles readers already downloaded while those articles were public.

## 6. Planned API contracts

Routes below preserve the original design sketch. Final Dev contracts are separate `/member/*` reader browser routes, `/smn-reader/*` central session-bound service APIs and `/smn-admin/*` administrator service APIs; the task/current source owns the exact frozen payloads. Never treat a proposed sketch route as a verified runtime endpoint.

| Surface | Contract |
|---|---|
| Reader GET canonical article URL | Select public/full representation from server-verified identity and access; never return protected body to a denied reader |
| Reader GET /member/login and callback | Initiate/complete reader WorkOS flow; validate return path; enroll or retrieve SMN membership once |
| Reader POST /member/logout | End local reader session; use current provider logout flow correctly |
| Reader GET /member/account | Identity, SMN grant/status, trial/access end and available offers; no payment secrets |
| Central POST /smn-reader/authorize | Validate reader-app provider token; bind identity; return audience/environment-scoped reader authority, not administrator credentials |
| Central server-to-server entitlement check | Authenticated service call with verified subject/session binding; return can_read, reason, end time and policy version; prevent cross-user requests |
| Central POST SMN checkout endpoint | Authenticated user, CSRF protection, offer-version/interval only; amount/customer IDs chosen on server; durable single-flight checkout |
| Stripe webhook | Existing verified ingress; exact smn product/price dispatch into isolated membership handler; idempotent event ledger |
| Admin membership/settings routes | Administrator-only, version-checked updates, audit and validation; no service/agent privilege escalation |
| Admin derivative routes | Inspect/regenerate/approve precise article revision; stale-source conflict is explicit |
| Admin promotion routes | Inspect job, retry eligible failure, cancel queued post or pause channel; unknown remote publish outcome requires reconciliation first |

Use explicit machine errors plus concise user copy for unauthenticated, access-required, pending-payment, stale-revision, not-configured and provider-unavailable states. Never treat a provider timeout as "not subscribed" and rewrite a valid paid record.

## 7. Prices, trials and payments

The zero-priced membership path is a local access grant and does not require Stripe Checkout, a payment method or a zero-dollar recurring invoice. Paid monthly and annual offers use hosted Stripe Checkout and the existing payment-event authority.

### Dashboard pricing contract

- Currency is explicit; store monetary amounts in integer minor units, never binary floating point.
- Monthly price can be zero for free mode.
- Annual pricing has one authoritative mode: discount from twelve monthly payments, or explicit annual amount.
- In discount mode, use integer basis points and a documented half-up minor-unit rounding rule. Calculate server-side and show the annual total and effective saving.
- In explicit-amount mode, the annual amount is authoritative; any displayed discount is derived. Never allow conflicting independently editable totals and percentages.
- $10 monthly with 50% annual discount produces $60 annually in a two-decimal currency. $80 is a separate explicit annual example, not a 50% discount.
- Annual price is the amount charged each year; a monthly equivalent must not look like monthly billing.
- Zero monthly price clears/disables percentage-discount comparisons and cannot accidentally produce a paid annual offer in free mode.
- Saving a setting creates a draft version. Activation validates provider price mappings and makes it available to new enrollments.
- Store immutable offer/price references on enrollment/subscription. Updating a future offer does not change existing subscribers.

Reject negative/fractional minor-unit amounts, currency mismatches, unsupported currencies, an empty set of paid intervals and contradictory free/paid settings. Paid annual discount must be between 0 and 9,999 basis points and produce a positive annual amount; a completely free offer uses free mode. Unit-test these boundaries and the displayed savings calculation against the server's authoritative billing values.

Price and trial examples are test fixtures. No live offer is approved in this plan.

### Billing correctness

Use Stripe Billing/Checkout, verified webhook processing and current provider state. A success URL alone never proves paid access. Handle initial payment pending/failure, action required, successful renewal, renewal failure, cancellation, cancellation reversal, refund/dispute notifications and out-of-order/duplicate delivery.

Recommended entitlement behavior: grant through the paid service period after confirmed payment; honor cancellation until its paid-through end; do not extend an unpaid renewal. A failed payment must not erase an unrelated valid grant. Refund/dispute events must be recorded and surfaced, with a documented SMN-specific access rule before live billing; do not silently inherit a rule that changes all of the customer's TradeWave products.

Preserve existing customer/subscription identity checks. Reuse a customer's existing Stripe identity only after the stable internal user binding is verified; never merge billing identities by unverified email. Product/price allowlists and metadata must agree with product_line=smn. An old SMN cancellation must not clear a newer SMN subscription, and no SMN event may change EOD/API access.

Extend the checkout-claim product-line database constraint and related resolver tests explicitly. Use a new instance-based Stripe client in the new module, with an explicitly tested API version; do not casually refactor the existing billing monolith or change all existing API versions.

A member may choose a plan during a trial. Preserve the recorded trial end and show the first charge date; do not restart the trial. Create a provider trial with that exact remaining boundary only when it meets the selected provider API's supported limits. Otherwise defer Checkout until expiry rather than inventing time or charging early.

Use an SMN-scoped account-management/portal flow so actions cannot cancel another product accidentally. Monthly/annual switching after subscription creation is deferred unless deliberately added to this scope; account cancellation remains required.

Use isolated sandbox data and test clocks/fixtures for lifecycle verification. Live Stripe products, tax configuration and payment-account readiness must be checked before activation. Do not assume setting automatic tax means registration is complete.

Official references: [Subscription webhook lifecycle](https://docs.stripe.com/billing/subscriptions/webhooks), [Products and prices](https://docs.stripe.com/products-prices/manage-prices). Public documentation was checked; the Stripe connector requested reauthentication, so live account settings and entitlement to use them were not verified.

## 8. Preview generation and quality contract

Add a derivative schema/stage rather than silently changing the complete-article schema and invalidating all current jobs.

Suggested structured output:
- article/source/evidence revision identifiers supplied by the application, never invented by the writer;
- public headline and preview paragraphs, each with source/claim references;
- one sentence describing additional value actually present in the full article;
- required historical/study qualification;
- social text and its claim references;
- video narration, selected native chart ID, on-screen wording and claim references.

Generate the schema from the selected bundle's valid source and chart IDs. The application chooses membership CTA text using current settings; the language model must not invent a price, discount, trial or guarantee.

Review checks:
- Every factual/numeric statement is supported by the same approved article and evidence.
- Instrument, trade direction, date window, sample/election cohort and data timestamp agree.
- No new TradeWave arithmetic, smoothing, normalization or projected path.
- Public claims preserve the limitation needed to interpret them.
- The value promise matches material in the full article.
- Source word allowances include derivatives where applicable.
- No raw HTML/script, source prompt or private data can enter rendered public copy.
- The preview is useful as a standalone reading experience, not a list of withheld answers.

Keep article generation on its existing verified provider/model policy. The meaning of existing "subscription" writer modules is ChatGPT/Claude subscription execution, not a reader's paid membership. Do not conflate them.

For new derivative jobs, qualify a lower-cost writer on the three fixed fixtures, then choose the cheapest model that passes the editorial and fidelity review. Do not change the main writer/reviewer configuration or run broad parallel comparisons. Record actual usage/retries where available and stop after the bounded comparison. No paid OpenAI API fallback.

## 9. Ten-to-fifteen-second video specification

Use Afshin's existing authorized ElevenLabs voice. Prior audiobook notes identify "afshin-pro"; that is a discovery pointer, not current account/API verification. Locate the existing voice, verify accessible ID/model/settings, and generate one sample before automating a batch. Do not create a replacement clone or substitute a stock voice.

ElevenLabs supplies narration; the SMN video worker combines narration, article assets, captions and branding. [ElevenLabs speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert?explorer=true) supports selecting a voice. Current access, credits, model availability and price were not verified.

### Proposed default storyboard

| Portion | Content |
|---|---|
| Opening, about 2-3 seconds | Subject plus one accurate reason the article matters |
| Middle, about 4-6 seconds | The article's matching TradeWave chart; narration explains one visible pattern or risk |
| Ending, remaining time | Clear reason to read the article and compact SMN call to action |

All ranges must fit the measured 10-15 second final duration. They are layout targets, not three independent fixed timers. Prefer one readable chart. Do not compress several charts into flashes simply to satisfy a plural phrase.

Production rules:
- Draft approximately 24-32 spoken words, then measure the actual audio. Rewrite if necessary; do not truncate a word or accelerate the voice unnaturally to meet the limit.
- Native chart must trace to the exact article/engine study. Never synthesize a financial chart as an AI image.
- A presentation crop/re-export may improve mobile readability, but must preserve relevant values, axis meaning, instrument, date window and study context. Never crop away a qualification needed to interpret the claim.
- Keep the selected chart visible long enough to understand the narrated point. Capture/inspect the middle frame, not just the opening thumbnail.
- Captions match generated speech, respect safe areas and remain readable on a phone. Short on-screen study labels can carry detail that would overcrowd the narration.
- Show historical context without implying a forecast or personal recommendation.
- Output proposed default: 1080x1920 portrait MP4, H.264/AAC, 30 fps, plus caption/transcript and poster artifacts. Validate actual platform requirements before enabling its adapter.
- Retain voice audio, script, source chart, final video and generation/QA receipts privately; publish only approved promotion artifacts.
- No music, sound effects or generated presenter is required for these article clips. The later request for an avatar applies to the separate daily briefing described below.

QA must decode the entire file, measure final duration, verify audio is present and not clipped, compare transcript/captions, inspect phone-size start/middle/end frames and listen to the pilot end to end. Automated transcript checks are useful but do not certify pronunciation or naturalness.

Cache by script + voice/model/settings + source asset hashes. At most two charged narration attempts per article under the proposed initial worker cap; further attempts require a reported failure or changed authorized budget. For an unknown request outcome, inspect provider history/receipt before repeating a charged operation.

### Daily market narrative and ElevenLabs avatar prototype

This is a separate editorial product from the 10-15 second per-article teasers. Afshin clarified that it should explain what the market conversation is about across the day's major headlines. The earlier single-development format is superseded for this briefing. The latest direction selects ElevenLabs for the initial avatar prototype; it does not select a different provider or authorize a production rollout through this document.

**Editorial selection comes first.** Start with a broad, current news scan, reuse relevant verified SMN research, and group repeated reports into distinct stories. Candidate areas include large companies and sectors, earnings, jobs/inflation/central banks, bonds/currencies/commodities, and geopolitics with an evidenced market connection. Include what matters that day; do not force every category, a named ticker, a TradeWave chart or an SMN article promotion into every edition. Social discussion can surface leads but is not factual corroboration. Without measured social data, describe themes found in news coverage rather than claiming a topic is the most discussed online.

**Preferred headline scan:** Start with [CNBC Markets](https://www.cnbc.com/markets/), [Bloomberg Markets](https://www.bloomberg.com/markets), [Reuters Markets](https://www.reuters.com/markets/), [The New York Times Business](https://www.nytimes.com/section/business), including its DealBook/economy coverage, and [The Wall Street Journal Markets & Finance](https://www.wsj.com/finance). The planner also recommends [Financial Times Markets](https://www.ft.com/markets) for international markets and economics. Afshin's phrase "New York Times Finance" refers to relevant NYT business/financial reporting; do not invent a separate publication with that name. Compare leading stories within the same information window and cluster coverage of the same underlying event. Repeated independent coverage helps identify a dominant theme, but selection also weighs significance and freshness; an important exclusive need not appear across every source. Distinguish independent reporting from republished Reuters copy. Use company announcements, economic releases and central-bank statements to substantiate the details when available. Write an original SMN narrative with source links; headline prominence alone does not verify a claim, and a search snippet is not evidence that the complete article was read.

Before automating this scan, verify the supported access method for each selected source in the actual environment. Public homepage, search discovery, authorized article access and a licensed feed are different capabilities. Initial direct retrieval attempts for the CNBC, Bloomberg and Reuters market landing pages were unsuccessful in this planning pass; the expanded source list likewise establishes no continuous feed or full-article access. Record access failures and coverage gaps, and use accessible corroboration without bypassing access controls. Hold unsupported claims; do not invent article details or silently claim a complete scan of the preferred sources when one is unavailable.

For each candidate retain the event time, publication/update time, retrieval time, source link, supported facts, reported market reaction, and selection/exclusion reason. Prefer primary releases for numerical facts and credible current reporting for context. Multiple syndications of one report are one source. Check that the event belongs to this edition and distinguish an upcoming release from its result. Unresolved material conflicts are held or stated explicitly; do not invent a causal explanation from two coincident price moves.

Proposed pilot workflow:
1. Set the edition date in America/New_York and an explicit information cutoff. Label the edition Before the Open, Intraday or Market Wrap as appropriate. Do not mix morning prices with closing prices without labeling the times.
2. Group and rank the main stories by market significance, breadth of credible coverage and freshness. Aim for roughly four to six distinct headlines when the day supports them; this is guidance, not a requirement to fabricate stories or omit a major development.
3. Write original short headlines and a connected narrative explaining what changed and how the stories relate. Preserve a distinction between reported facts, attributed interpretations and SMN's synthesis. A market overview must remain useful on its own without registration.
4. Produce the public written brief, the narration script, a claim/source map, and a storyboard from the same reviewed evidence snapshot. A proposed 45-60 second video is a pilot target, not the earlier 10-15 second article limit. Adapt the spoken script to measured delivery; review duration if the day's story cannot be told coherently at that length.
5. Choose visuals after the narrative. Use clear headline cards, appropriate permitted imagery and exact source-bound charts. Use TradeWave exports only when the study actually helps explain the selected story; never fabricate a market chart or illustrative war footage presented as reporting.

**ElevenLabs prototype sequence:** Locate Afshin's existing avatar/presenter asset and voice in the authorized account. Do not assume an avatar already exists because a voice exists. If a personal avatar asset is missing, prepare the rest of the package and identify the minimum reference material/setup needed; do not substitute a stock presenter. Record the chosen avatar identity, underlying model, voice, settings, available aspect ratio/resolution, cost and supported generation route. Use an avatar model within ElevenLabs initially; do not silently move the prototype to a separate HeyGen, Creatify, vidIQ or other account.

Generate one private review sample from the reviewed script once implementation and the provider generation are authorized. Proposed presentation: Afshin's avatar introduces the lead in a few seconds, the main sequence shows the selected headlines and visuals with his voice continuing, and a brief avatar closing is optional. Exact screen time is an editorial proposal, not a fixed requirement. Keep the AI-presenter disclosure visible and ensure it does not imply a live recording or personal review that did not occur.

Inspect the complete sample for likeness consistency, lip sync, pronunciation, factual/visual alignment, captions, mobile readability and unnatural transitions. Preserve the generated audio, avatar segments, final MP4, source snapshot, model/settings and generation receipt. Cache by edition revision, script, avatar/reference and voice/model/settings hashes. Reconcile an unknown charged job outcome before retrying; use the existing bounded generation-cost controls. If generation fails, retain the written briefing and report the specific media failure.

**Automation qualification:** Official ElevenLabs documentation checked October 2, 2026 describes reusable avatars with library voices and a Flows Avatar node. That page retains an API-at-launch limitation; newer Image & Video documentation and the video-generation endpoint expose some models through APIs, including Creatify Aurora. Treat these as different capability surfaces. Verify the exact chosen avatar/model path in the actual account; do not infer that every model or reusable avatar identity is API-accessible. An app-generated pilot is acceptable evidence of presentation quality, but not proof of unattended daily generation. Record any manual step before committing to automation. No live account, avatar, credit balance or model connection was inspected in this planning update.

References: [ElevenLabs Avatars](https://elevenlabs.io/docs/overview/capabilities/image-video/avatars), [Image & Video models](https://elevenlabs.io/docs/overview/capabilities/image-video), [video-generation API](https://elevenlabs.io/docs/api-reference/flows/video/create), and [Image, Video and Template API announcement](https://elevenlabs.io/blog/introducing-the-image-video-and-templates-apis).

Daily briefing delivery and social/Substack dispatch use the existing approval, destination verification and receipt boundaries. Do not send, schedule, publish or subscribe anyone during prototype work. Keep the daily briefing independently pausable; it must not hold up the regular article edition.

## 10. Social distribution and job operation

The same approved promotion package supplies platform-specific short copy, a permitted image/video and a tracked link to the public article URL. Start with a small selected set of connected accounts; do not assume LinkedIn, X, Facebook, Instagram or YouTube are already enabled.

Keep generation, scheduling and external posting as distinct job states:
draft -> generated -> reviewed/eligible -> queued -> publishing -> published
with held, failed, canceled and unknown-outcome states.

Use one durable job key per article revision/channel/asset variant. Acquire a short lease before dispatch. Persist provider request/post identifiers. On timeouts, reconcile the remote result before retrying; a missing local receipt is not proof the platform did not publish. Updating an article does not automatically repost it.

Automatic publishing requires:
1. Exact article revision and preview verified live.
2. Approved source, copy, chart and video receipts.
3. Enabled, authenticated target account with required permissions.
4. Configured frequency and retry/usage limits.
5. No article withdrawal, stale revision or unresolved remote outcome.

After these are configured and activation is authorized, the ordinary path runs without daily owner approval. A channel kill switch pauses queued dispatch while preserving jobs. A bad derivative is held without dropping a valid article from the edition.

The dashboard must distinguish article failure, preview failure, video failure and social-post failure, with concrete remediation and no false success. Preserve existing immediate alerts for missing/incomplete articles. Route derivative failures through verified operational alert settings; never claim alerts work merely because a recipient field is populated.

Measure preview visits, signup starts/completions, full-article opens, returning readership, trial-to-paid conversions and promotion referrals. Deduplicate events and exclude test accounts. These are measurement goals, not promises of marketing performance. Do not put reader emails or billing identifiers in social URLs or public analytics payloads.

### Substack follow-up after regular SMN launch

**Accepted scope and timing:** Keep complete articles on Seasonal Market News. Once the regular publication is operating and verified, test a free Substack digest or shorter article version containing a useful finding, an approved public chart when it adds value, and a link to the complete SMN article. Substack setup is a later work package, not a requirement for the regular publication launch. Cadence and whether to group several articles into one digest remain to be selected from actual publishing volume.

**Paywall recommendation, still under discussion:** Keep one reader membership and paywall on SMN, using the identity and Stripe integration described in this draft. This matches the requested SMN dashboard controls and keeps full content, trials and access decisions together. It also requires maintaining reader authentication, billing and access enforcement. Substack supplies a managed publishing/subscription alternative and could reduce that development work; its published paid-subscription fee is 10% plus payment processing. If Afshin chooses Substack as the membership home, revise the reader/billing architecture before implementing it; do not build two paid systems or assume Substack payments automatically unlock SMN articles.

**Reader journey:** A public Substack summary links directly to the relevant canonical SMN article with a non-identifying referral tag. In free membership mode, its invitation says signup is free; in paid mode it reflects the actual trial/offer. Subscribing to the Substack newsletter does not by itself create an SMN account or entitlement. Make that distinction clear at the link and destination; do not require newsletter signup as an extra step before the SMN link. Do not import subscribers or assume shared login/consent. Do not promise synchronized accounts.

**Implementation boundary:** Reuse the approved public derivative and its exact source revision. Never export the protected full body or private assets to this channel under the accepted scope. Prepare a reviewable draft/export first. Verify the publication account, permitted publishing mechanism, formatting and external-send authorization before connecting automated dispatch; automatic ingestion from our pipeline has not been established. If no supported automation path is available, retain a manual draft/export workflow and report that limit. A Substack failure cannot block SMN publication. Apply the existing promotion job idempotency and receipt rules if dispatch is later automated.

**Pilot acceptance:** Inspect one draft on desktop/mobile and logged out; verify chart readability, public asset scope, correct article link and membership wording. After an authorized publication, record its remote URL/receipt and verify the destination. Compare referral visits and completed SMN signups to choose a useful cadence; newsletter subscriber counts alone do not prove SMN membership growth. Pause this channel independently if it is ineffective or unreliable.

Official sources checked October 2, 2026: [Substack features](https://substack.com/features) and [paid subscription pricing](https://faq.substack.com/p/how-do-paid-subscriptions-on-substack). These establish advertised platform capabilities and fees, not a verified account connection or integration fit.

## 11. Dashboard and existing editor

Extend the current dashboard with three coherent areas:

**Membership settings:** free/paid enrollment mode, monthly and annual offer configuration, trial days, live/draft offer state, counts by access reason, and clear existing-member impact. Show provider readiness separately from saved settings.

**Article public version:** side-by-side complete/public views, source revision, edit/regenerate controls, factual-review result and a preview of the correct reader CTA. Reuse the existing private editor/version-conflict pattern. Access policy and content edits are explicit; modifying the teaser cannot overwrite the complete article.

**Promotion:** script, chart, audio/video preview, generation status, per-channel queue/receipt, retry/cancel and pause controls. A regeneration creates a new revision and review status. Controls must state whether an action creates an asset, schedules a post or posts externally.

The daily briefing has its own entry within Promotion: edition date/cutoff, selected and excluded headline groups, sources, narrative/script, avatar storyboard, exact ElevenLabs settings, pilot/automation readiness and receipts. Do not identify it by an individual article ticker or apply the article teaser duration limit. Regeneration after a source/script change invalidates the corresponding media approval.

All privileged changes require existing administrator authorization and CSRF/version checks. API/service keys do not automatically gain permission to change prices, grant memberships or publish social posts. Grant only explicitly defined capabilities and record the actor.

Preserve dashboard article order, pins, schedules, search and model-assisted editing. Existing editor code currently reads public article paths; routing it through the new private content-store adapter is a required dependency, not optional follow-up.

## 12. Implementation work packages

Afshin authorized development under this plan on October 2. The first checkpoint is retained as history; current execution covers the discussed plan through working Dev deployment, following dependencies and existing operational gates. Each package ends with a small reviewable diff, focused tests, evidence and a shared task checkpoint. The named new files are proposed boundaries; reconcile names with current main once, then keep the approved contracts stable.

| Package | Dependencies | Work and likely files | Done when |
|---|---|---|---|
| P0 - Current baseline and fixtures | Implementation authorization | Fetch both repos, read current policies/claims, create non-overlapping worktrees and shared task; locate three approved bundles and exact charts; record runtime/source/config boundaries | Reproducible fixtures and claim/evidence map exist; no live article regenerated |
| P1 - Public-version pilot | P0 | New blog/article_derivatives.py and derivative schema/tests; integrate existing writer receipt and source checks; save three example previews/scripts/storyboards | All three are useful, truthful and traceable; bearish direction and material caveats pass review |
| P2 - Content-store split | P1 contract | New blog/article_content_store.py; update subscription_publication.py, article_index.py, publisher/rollback code and article_editor_routes.py consumers | Atomic public/private storage, legacy-route inventory and restart recovery pass; admin editor still opens the full article |
| P3 - Reader identity and access | P0, P2 | New blog/reader_app.py and reader authentication adapter; TradeWave web/smn_membership.py, SQLAlchemy records/migrations and reader authorization endpoint | Free verified signup returns to article; anonymous/expired/admin-separation tests pass through actual proxy |
| P4 - Offers, trials and paid access | P3 | TradeWave web/smn_billing.py, explicit webhook dispatch, offer/grant records, checkout-claim constraint migration and focused lifecycle tests | Sandbox monthly/annual/trial flows pass; no EOD/API entitlement regression; zero mode requires no Stripe call |
| P5 - Dashboard/editor completion | P1-P4 | pub_dashboard.py, templates/pub_dashboard.html, settings routes and editor derivative invalidation | Owner can inspect/update the specified settings/content; stale edits conflict safely; audit and unauthorized-denial tests pass |
| P6 - Video worker | P1, authorized provider sample | New video job/renderer module with existing job-state conventions; ElevenLabs adapter and ffmpeg-style deterministic composition | Three source-bound sample clips are actually 10-15 seconds, readable, audible and reviewed; retry/cost limits work |
| P7 - Promotion dispatch | P2, P5, P6 | New channel adapters and durable promotion job runner; use existing helper only where verified suitable | Draft-only flow first; mocked duplicate/timeout/cancel tests pass; one authorized test per selected channel before unattended activation |
| P8 - Release and operations | P2-P7 required launch subset | Additive migration, private storage/proxy config, cache rules, archive migration manifest, operational alerts and release receipts | Dev end-to-end evidence passes; launch scopes/terms selected; exact production package and rollback are reviewable |
| P9 - Later Substack pilot | Regular SMN publication established; approved public derivative and live destination; later milestone scope | Free digest/shorter-version draft/export using section 10; verify account, supported publishing method, public assets, CTA, referrals and receipts before any adapter | One reviewable pilot passes the section 10 checks; authorized publication has a verified receipt; automation limits and cadence recorded; no duplicate paid membership created |
| P10 - Daily news narrative pilot | Development authorization; current source access | Reuse current research adapters; add edition/cutoff and grouped-headline records, selection reasons, claim map, written brief and narration/storyboard | One actual dated edition covers the main supported narratives, deduplicates syndication, preserves time context and passes editorial review; no forced ticker/chart slots |
| P11 - ElevenLabs avatar prototype | P10 reviewed script; verified account, avatar/reference and voice access; authorized provider generation | Use an avatar model within ElevenLabs; generate presenter segments, compose headline/visual sequence, retain settings, media and receipt; verify supported automation route separately | One private playable sample passes full listening and visual review; model/cost/manual steps recorded; no unverified claim of daily automation or external publication |

The current controller/publisher entry points to reconcile for P1/P2 are blog/smn_subscription_daily.py, blog/smn_subscription_publish.py, blog/subscription_publication.py and blog/subscription_primary_publish.py. Do not attach the new behavior only to an older development controller and then assume the active production workflow uses it.

Free membership can be released before paid enrollment and distribution, but its protected storage, authentication and preview gates are mandatory. Later packages must not be represented as delivered just because their dashboard controls exist.

P9 live publication is explicitly deferred until regular SMN is off the ground. Its draft export adapter does not require paid enrollment, video generation or other social channels, and P9 is not a dependency of P8. Membership authority is now central TradeWave with a separate SMN reader session/app; a later change requires deliberate contract migration rather than adding a second billing authority.

P10/P11 can be developed independently of paid membership and Substack. Neither blocks the regular article publication. P11 is the initial development prototype requested for the daily briefing; automated distribution remains a separate later activation.

### Executor workflow

- Read this entire plan and the current authoritative task records before changing files.
- Distinguish confirmed requirements, proposed defaults and unresolved launch choices.
- Record final API/schema names and dependency ownership in the shared task before parallel coding.
- Keep one owner per concern. Independent packages may use separate worktrees only after contracts are fixed; do not parallelize conflicting billing/auth migrations.
- Use the lowest-cost suitable coding model; escalate architectural ambiguity or repeated failure rather than silently inventing product behavior.
- Preserve unrelated changes, the current main writer/reviewer policy, old receipts, active publication locks and existing operational schedules.
- Report changed files, exact commits, meaningful tests, environment status and next step for each handoff.
- Treat this plan as a specification, not permission to deploy, charge, send or create recurring automation.

## 13. Required acceptance tests

Use focused tests tied to these behaviors. Do not add broad tests that merely restate implementation internals.

### Reader/content tests
- Anonymous preview works with JavaScript disabled and without a cookie/account.
- Full text and protected assets cannot be obtained via page source, direct origin/static URLs, alternate edition URLs, path traversal, encoded paths, query variants, search/catalog JSON or caches.
- Authenticated content never enters a shared anonymous cache; anonymous and member requests exercised in both orders.
- Zero price still denies anonymous full access and grants eligible signed-in members.
- Existing dashboard admin, named API key and service-key boundaries remain correct; reader login never grants admin.
- Signup/login/logout, expired session and return-to-article behavior pass on mobile and desktop.
- Trial starts once, ends exactly on time, survives retries and is not changed by a later duration setting.
- Identity or billing service outage preserves public reading and produces explicit protected-access behavior.
- Editing, unpublishing, republishing, pins, older article search and archive navigation still work.

### Billing tests
- Monthly/annual prices, discount rounding, zero mode, disabled interval and stale offer version.
- Duplicate/concurrent Checkout requests and an unknown provider response.
- Initial payment success, pending, failure and authentication required.
- Paid renewal, payment failure, cancellation at period end and reactivation.
- Duplicate/out-of-order events, old-subscription cancellation and wrong-user/customer/product bindings.
- SMN events leave TradeWave web/API tiers, reverse trials and subscription IDs unchanged.
- No-card trial expiry makes no charge; a later successful subscription restores access.
- Offer changes do not migrate existing members; expired/canceled subscriptions do not regain access through stale cache.
- Portal links cannot operate on another user's or unintended product's subscription.

### Editorial/video/social tests

For the daily briefing, additionally verify deduplicated headline groups, date/cutoff correctness, fact-versus-interpretation labeling, source-bound visuals, and independence from per-article topic/duration constraints. For the ElevenLabs avatar sample, verify exact presenter/voice selection, full-video lip sync and pronunciation, no stale-script media reuse, job reconciliation and an honest manual-versus-automated capability result.
- Bullish, bearish and news-led fixed fixtures pass evidence/direction/caveat review.
- Unsupported numeric claims or missing native charts are held explicitly.
- Source article changes invalidate derivative approval and block queued stale posts.
- Video timing measured from decoded media; middle chart and captions readable on a phone; pilot pronunciation/listening reviewed.
- Voice/provider failure does not publish a silent/stock-voice substitute or hold a ready article.
- Paid-generation retries and platform retries respect budget/idempotency boundaries.
- Social publish timeout reconciles before retry; channel pause/unpublish prevents pending sends.
- End-to-end link lands on the correct public version and a completed signup returns to the same full article.

## 14. Migration, release and rollback

Before implementation, re-read current SMN AGENTS.md, CLAUDE.md, docs/AGENT_COORDINATION.md and daily runbook; and TradeWave AGENTS.md, CLAUDE.md, docs/WORK_MANAGEMENT.md, task/bug indexes, docs/RELEASE_PROCESS.md, docs/TRADEWAVE_ECOSYSTEM.md, ops/OPERATIONS.md and its Git/release skills. Some retained runbooks describe older operational limits; resolve differences against current shared records and explicit authorization.

SMN has Dev and production. Do not invent an SMN staging server. Any coupled TradeWave change follows its actual staging/production gates. A previously approved deployment is not approval for this membership release.

1. Back up current catalog, complete article files, protected-state configuration and relevant database schema/data according to current policy.
2. Add nullable/new records first. Deploy compatible services with reader gating and external posting disabled.
3. Stage the protected article corpus outside public roots and generate/review its previews without altering live URLs.
4. Validate a migration manifest listing every protected URL, full/preview hash, asset classification and prior representation. Preserve URLs/pins/history.
5. Run the full access/cache leak checks on Dev, plus focused billing/provider sandbox tests and all selected-subject/landing/archive checks required by current publication rules.
6. Activate a specifically reviewed scope of gating. Remove or deny corresponding old full-file routes and invalidate relevant caches; verify at public edge and direct origin.
7. Keep promotion dispatch off until the article destination and approved assets are live and the chosen channel operation is authorized.
8. Record release artifact/config hashes, actual runtime pointers, migrations, receipts and rollback.

Rollback must restore a working reader path without exposing protected bodies. If membership serving fails after gating starts, keep public previews available and fail protected content closed while restoring the prior compatible service. Do not automatically restore old publicly accessible full HTML as an "availability" rollback.

Keep member/payment records durable through application rollback. An app rollback does not cancel real subscriptions or undo payments. Reconcile payment events before resuming the new service; never replay charges as a recovery mechanism.

## 15. Final handoff and completion criteria

This plan is committed under the canonical shared task and is the detailed acceptance/design record. Current implemented behavior, environment status and sanitized evidence belong in `../TW-TASK-0018.md`; dated planning observations below remain historical.

Independent Dev integration/parity, current ADP generated-copy/export approvals and public daily media delivery are complete. Remaining actions are credential/browser readiness for a real avatar and unattended media, archival pilot qualification/review, hosted sandbox Checkout and future scheduled-run observation. Existing daily operation choices remain owned by TW-TASK-0009. Complete articles were migrated to private storage without broad regeneration; real test API/private narration calls are recorded in the task. External social/Substack posts and production changes remain unauthorized.

An implementation handoff must contain:
- User-visible result and exact completed/uncompleted packages.
- Current shared task/claim, repository branches, source/artifact hashes and paths.
- Database/config changes, provider prerequisites, account/channel readiness and launch settings.
- Test evidence, actual inspected media/screens and all verification limits.
- Separate Dev/production status, rollback state and remaining operational dependencies.
- Example public preview, member page and real generated clip that Afshin can open.
- A concise next action; another executor must not need the original conversation.

### Verification limits of this plan

- Real public article text/chart descriptions and current source refs were inspected; no financial recalculation or independent engine audit was performed.
- WorkOS and Stripe integration points were located in current source; no reader sign-in, checkout, live account configuration or payment event was exercised.
- The Stripe connector requires reauthentication. Public documentation supported the plan; no account changes were attempted.
- Prior audiobook memory supplied the possible voice name only. Current ElevenLabs voice/model availability, credits, commercial terms and clip quality still need verification.
- Public ElevenLabs avatar and video-API documentation was checked for the daily briefing extension; no personal avatar asset, account entitlement, generation or automatic workflow was exercised. No daily briefing or avatar video has been published or generated by this planning task.
- No source code, runtime configuration, article, payment, social account or scheduled process was changed.
