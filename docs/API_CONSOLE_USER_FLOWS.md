# API / MCP - the Definitive User Workflow (spec, decided 2026-07-06)

Status: TO-BE spec with decisions made. Section 7 is the exact implementation delta.
The as-built gaps that motivated each rule are inline (in "why" notes) so nothing is
re-derived. Code-verified sources: `site/lib/portal_urls.py`, `site/api_marketing/
generate.py`, `web/api_portal/*`, `web/app.py` (login/signup/callback/webhook),
`apiserver/{auth,tiers}.py`, `web/templates/account.html`.

## 0. The Model (hold these three facts)

- **Two surfaces.** The PUBLIC developer portal (`developers.*`, static, no login:
  marketing, docs, learn, playground, demo token) and the LOGIN-GATED console
  (`tradewave.ai/account/api/*`: Keys, Usage, Billing, MCP Connect). Every acquisition
  CTA on the portal lands on the console.
- **One entitlement rule.** Effective API tier = MAX(explicit `users.api_tier`, bundled
  `WEB_TIER_TO_API[web tier]`) on the rank ladder free(0) < navigator(1) < dev(2) <
  pro(3) < business(4). Bundled: explorer->free, navigator->navigator, analyst->dev,
  strategist->pro. Keys are identity, not tier: the tier is resolved per request, so a
  plan change re-tiers every existing key instantly, nothing is re-issued.
  (DECISION - this MAX is a change: today `api_tier_from_user` lets an explicit LOWER
  api_tier beat a higher bundled one, so a paid Dev-API holder who later buys web
  Strategist would be DOWNGRADED from bundled-pro to dev on REST. MCP already does MAX;
  REST must match. See 7.1.)
- **The REST ladder is a developer product; the web reverse trial is a consumer feature.**
  A new signup's 7-day Strategist trial applies to the website and to in-chat MCP, NOT to
  REST keys (deliberate: trial-elevated keys would hand every throwaway signup 7 days of
  Pro-scope scanning = abuse surface, and API-free-as-eval-taste is the priced design).
  The console must SAY this during an active trial (see copy C4) instead of silently
  showing "Free" next to a site that says "Strategist trial".

## 1. Global Routing Rules

- R1 **Acquisition CTAs route to SIGNUP, management routes to LOGIN.** All portal CTAs
  (logged-out audience) link `MAIN/signup?next=<url-encoded target>`; AuthKit's signup
  screen carries a "sign in instead" toggle, so existing users pass through too. Console
  internal bounces (`require_login`) keep `/login?next=...` (account pages imply an
  account exists). `next` must round-trip the FULL path incl. query (percent-encoded);
  `/auth/callback` already redirects to `state`.
- R2 **Free intent lands on Keys; paid intent lands on Billing.** Portal free-card
  "Get Started" and every "Get a free API key" -> `/account/api/keys`. Paid cards
  "Start Dev/Pro/Business" -> `/account/api/billing?subscribe=<tier>`. Founder strip ->
  `/account/api/billing?subscribe=pro&promo=FOUNDER`.
  (why: today ALL cards, paid included, land on the keys page = buy intent dead-ends on
  a curl example.)
- R3 **`?subscribe=<tier>` semantics: highlight, never auto-charge.** Billing scrolls to
  + highlights the target card. If actionable, one click completes checkout. If the flag
  `API_PRICING_LIVE` is off, or the tier is already covered (rank <= effective), show the
  explanatory state instead (R5/C2) - a stale or wrong link never errors and never
  silently charges.
- R4 **`promo=FOUNDER`**: checkout session is created with the FOUNDER promotion code
  pre-applied (Stripe enforces the 100-seat cap); if Stripe rejects it (exhausted or
  expired), fall back to plain checkout with `allow_promotion_codes=True` plus a flash
  note. No dead end when seat 101 clicks the strip.
- R5 **Billing card states are a pure function of (card rank T, effective rank C, source
  of C, has API Stripe sub).** Exactly one of:
  - T == C, explicit sub: "Current plan" + Manage in billing portal.
  - T == C, bundled: disabled "Included with your {WebTier} plan" (no purchase possible).
  - T < C: bundled C -> disabled "Included at a higher tier via your plan"; explicit C ->
    "Downgrade in billing portal" (proration handled by Stripe).
  - T > C: "Subscribe" -> Stripe Checkout (mode=subscription, product_line=api metadata).
    If the user ALSO holds an explicit API sub at a lower tier, the button is "Upgrade in
    billing portal" instead (switch the existing sub; never create a second API sub).
  (why: today a bundled-pro Strategist is shown Subscribe/"Switch in portal" on Dev - a
  paid downgrade below what he already has free, and "Switch in portal" opens the WEB
  subscription's portal = wrong sub.)
- R6 **The bundling banner is always present on Keys + Billing** (copy C1): "your key
  inherits your TradeWave plan" with the current web tier -> API tier mapping. When the
  effective tier is `navigator` (bundled-only, not a card), the banner IS its
  representation; cards then read from rank normally.
  (why: today a Navigator subscriber matches no card - no "current plan" indicator at
  all - and nobody is told bundling exists, which is why "Start Pro" never asking for
  money read as a bug.)
- R7 **Redundant-sub advice.** If explicit api_tier <= bundled tier (the MAX rule makes
  the explicit sub pointless), Billing shows: "Your {WebTier} plan already includes
  {BundledTier} API access - you can cancel the {ExplicitTier} API subscription in the
  billing portal." Never auto-cancel.
- R8 **Console discoverability.** The logged-in `/account` hub gets an "API & MCP" action
  ("API keys, usage, billing, and connecting ChatGPT/Claude" -> `/account/api/keys`).
  The portal header's Get API Key nav CTA reuses the existing tw-auth-link swap: logged
  out -> `signup?next=keys`, logged in -> "API Console" -> keys.
  (why: today a logged-in subscriber has NO path to the console except the marketing
  footer or typing the URL.)

## 2. Persona B - No TradeWave Login (Prospect), Every Intent

Entry: home-page footer "API / Developer Portal", direct portal URL, docs links, or an
AI-referred visit. All paths below start on `developers.*`.

- B1 **"Just show me" (no commitment):** Playground "Try it" or any docs curl with the
  public demo token `tw_demo_explore`. Works with zero signup; capped to 5 symbols
  (AAPL/MSFT/NVDA/AMZN/TSLA), enumeration + bulk endpoints blocked, one shared global
  rate bucket. First successful call in under a minute; every demo response and doc
  points to the free-key step next.
- B2 **"Get a free key":** CTA -> `signup?next=/account/api/keys` -> AuthKit sign-UP
  (toggle to sign-in exists) -> account created (`tier=explorer`, 7-day web/MCP trial
  starts) -> lands on Keys -> "Create a new key" -> key shown ONCE, already baked into
  the tabbed cURL/PowerShell/Python quickstart -> first authenticated call. Tier: FREE
  (S&P 500, 5 ML/day, 100/day, 1 key). Trial note C4 visible so "site says Strategist
  trial, key says Free" is explained, not discovered.
- B3 **"Start Dev/Pro/Business" (buy intent):** paid card -> `signup?next=/account/api/
  billing%3Fsubscribe%3D<tier>` -> AuthKit signup -> Billing with that card highlighted
  -> Subscribe -> Stripe Checkout (their new Stripe customer is created here) -> success
  URL -> Billing flash "activating" -> webhook writes `users.api_tier` -> tier live;
  any key they create (or already created) carries it immediately. The Pro card carries
  note C3 ("Also included with the Strategist web plan") so the $199-API vs $129-web
  inversion is disclosed, not hidden.
- B4 **Founder seat:** strip -> same as B3 with `promo=FOUNDER` pre-applied (R4).
- B5 **Enterprise:** Business card note + enterprise strip -> `contact.html`. No change.
- B6 **Consumer MCP (ChatGPT/Claude.ai):** no key and no console needed - the user adds
  the MCP URL in the assistant, the OAuth connect walks them through WorkOS login/signup
  in-flow, and their in-chat scope mirrors their web plan (incl. the trial teasers).
  Portal MCP page already documents this; the console's MCP Connect tab is only for the
  BYOK dev-tool path.
- B7 **Pricing flag OFF (pre-launch state):** paid cards show "Coming Soon"/Talk to
  Sales (never a checkout path), free card + demo token fully functional; a stale
  `?subscribe=` deep link degrades to the launch-soon note (R3).

End states for B: demo-only (no account), free key holder (account, trial running on
web/MCP), standalone API subscriber (explicit api_tier, no web sub), or contact-sales
lead. No path dead-ends; every screen states the next step.

## 3. Persona A - With a TradeWave Login, by Web Tier

Discovery for all: `/account` hub "API & MCP" (R8), portal CTAs (signup screen toggles
straight through since they hold a session - AuthKit sees the live session and returns),
or direct URL. Landing = Keys.

What each sees (no explicit API sub, pricing live):

| Web tier | Effective API | Keys page | Billing cards |
|---|---|---|---|
| Explorer (trial or not) | free | banner C1 + trial note C4 during trial; create 1 key at FREE | Free = "Included with your Explorer plan" (bundled T==C per R5; "current" here is shorthand); Dev/Pro/Business = Subscribe (upgrade) |
| Navigator | navigator (bundled) | banner C1 shows "Navigator -> Navigator API (Dow/NASDAQ/S&P, 5 ML/day) included" | no card matches: banner carries current state (R6); Free = "included at a higher tier"; Dev/Pro/Business = Subscribe |
| Analyst | dev (bundled) | banner C1 "Analyst -> Dev API included"; 3 keys, 100 ML/day | Free = included-below; Dev = "Included with your Analyst plan" (disabled); Pro/Business = Subscribe |
| Strategist | pro (bundled) | banner C1 "Strategist -> Pro API included"; 10 keys, unlimited ML | Free/Dev = included-below (disabled, no purchase); Pro = "Included with your Strategist plan"; Business = Subscribe |
| + explicit API sub | MAX(rank) (7.1) | banner shows both sources | current explicit = "Current plan"+portal; lower = downgrade-in-portal; higher = upgrade-in-portal; redundant sub -> advice C5 (R7) |

Purchase truth for Persona A: a bundled user is NEVER asked to pay for what the plan
already grants (that is the answer to "when is it going to ask me to purchase?" - for a
Strategist buying Pro: never, by design, and now the UI says so). The only purchases
offered are strictly-above-current tiers.

## 4. Lifecycle and Edge Cases (all decided)

- **Post-checkout race:** success redirect can beat the webhook by seconds; Billing
  already flashes "being activated - appears once Stripe confirms". Keys need no action
  (tier is per-request).
- **Cancel the API sub:** webhook maps deletion to `api_tier=NULL` -> entitlement falls
  back to the bundled web tier. Keys keep working at the lower tier.
- **Cancel the web sub while holding an explicit API sub:** web tier drops to explorer;
  explicit api_tier is untouched -> REST keeps the paid API tier. Correct: the two
  product lines bill independently and the webhook router never cross-writes.
- **Downgrade leaves excess keys:** `max_keys` is enforced at CREATE only; existing keys
  keep authenticating after a downgrade (grandfathered), new creation is blocked until
  under the limit. Documented behavior, not a bug.
- **At key limit:** Keys page disables creation and links Billing to upgrade (exists).
- **Admin role:** the role bypass elevates the WEB app only; REST/console use the raw
  ladder (an admin without a sub is `free` on REST). Internal-facing; acceptable.
- **Unverified email:** keys are issued on account creation regardless; exposure is
  bounded by the free tier itself (S&P only, 100/day) and the demo token already grants
  a taste anonymously. Accepted.
- **Trial window on REST:** never elevated (Section 0). Console explains via C4.
- **Stale/foreign deep links** (`?subscribe=business` while flag off, unknown tier
  value, already-covered tier): degrade to highlight-with-explanation or the
  launch-soon note; never 500, never checkout (R3).

## 5. Copy Blocks (exact strings; house style: no em-dashes, sentence-case body)

- C1 (Keys + Billing banner): "Your API access is included with your TradeWave plan:
  {WebTier} includes {ApiTierLabel} ({scope summary}). Keys automatically carry your
  current plan - upgrade the plan and every key upgrades with it."
- C2 (included-below card state): "Included at a higher tier with your {WebTier} plan."
- C3 (Pro card, users with no web sub): "Also included with the Strategist web plan."
- C4 (active reverse trial, Keys + Billing): "Your 7-day Strategist trial applies to the
  website and to TradeWave inside ChatGPT/Claude. REST API keys are separate and start
  on the Free tier - upgrade any time on the Billing tab."
- C5 (redundant sub): "Your {WebTier} plan already includes {BundledTier} API access.
  Your {ExplicitTier} API subscription is no longer needed - you can cancel it in the
  billing portal."

## 6. Invariants This Spec Locks

- One entitlement formula everywhere: MAX(explicit, bundled) on the rank ladder, REST
  and MCP alike. No surface may hand out LESS than bundled.
- Acquisition -> signup screen; management -> login screen; `next` always carries the
  full target.
- Paid intent always reaches a checkout or an explicit "included/coming soon" state in
  <= 2 clicks from any CTA; free intent always reaches a working key in one click after
  auth.
- A user is never shown a purchase action whose result is not strictly more entitlement.
- Every "surprising" state (trial vs free key, bundled tier, redundant sub) is stated on
  screen, never left for the user to infer.

## 7. Implementation Delta (ordered; small, independent steps)

1. **`apiserver/tiers.py`** - add `API_TIER_RANK = {free:0, navigator:1, dev:2, pro:3,
   business:4}`; change `api_tier_from_user` to `max(explicit, bundled)` by rank
   (fixes the explicit-downgrades-bundled defect; MCP merge already MAXes).
   Gateway restart.
2. **`site/api_marketing/generate.py`** - paid card `btn_href` ->
   `{MAIN_URL}/signup?next=%2Faccount%2Fapi%2Fbilling%3Fsubscribe%3D{key}`; free card ->
   `{MAIN_URL}/signup?next=%2Faccount%2Fapi%2Fkeys`; founder strip adds
   `%26promo%3DFOUNDER`; header CTA default href -> signup-wrapped keys (auth-swap flips
   it when logged in). Re-assemble portal. Same treatment for the other CONSOLE_URL CTAs
   (hero "Get a free key", MCP page, use-cases).
3. **`web/api_portal/routes_billing.py`** - compute `explicit`, `bundled`, `effective`
   (rank MAX), per-card state per R5; honor `?subscribe=` + `promo=FOUNDER` (R3/R4:
   highlight; checkout create passes `discounts=[{promotion_code}]` when promo valid,
   else `allow_promotion_codes`); block checkout when rank <= effective (server-side,
   not just UI); pass banner/trial/redundant-sub context (C1/C4/C5).
4. **`templates/api_billing.html`** - render R5 states + C1..C5 + highlight/scroll for
   `?subscribe=`.
5. **`templates/api_keys.html` + `routes_keys.py`** - banner C1 + trial note C4.
6. **`web/templates/account.html`** - add the "API & MCP" hub action (R8).
7. **Verify** - headless matrix: for each web tier x {no sub, dev sub} assert card
   states + banners; deep-link highlight; founder promo checkout session (TEST); no
   em-dashes in emitted copy.

Out of scope here (already tracked elsewhere): final $ decision + Fix A inversion,
TW2_API_PRICING_LIVE flips, portal docs tabbed snippets parity.
