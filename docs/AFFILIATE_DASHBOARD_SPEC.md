# Affiliate Dashboard + SMN Expert Module - Design Spec

_Status: BUILT + TESTED on dev 2026-07-07 (all phases incl. the SMN module; 32/32 integration checks in tests/test_affiliate_portal_dev.py). Remaining: expert_sync cron install (make_bulletproof.sh), staging/prod deploy, scorecard evaluation job (Phase C2). Written 2026-07-07 from a code-verified
map of the affiliate system. Companion strategy doc: `docs/marketing/SMN_STRATEGY.md` (Option E =
the SMN expert layer this dashboard hosts). Build order per owner: dashboard first, SMN module
second, as a tab of the same portal._

## 1. Purpose

Give each affiliate a login dashboard on tradewave.ai to see their status (the ONLY missing
piece of the affiliate system today), and extend it with an OPTIONAL SMN expert module: a
profile that powers the affiliate's public page on BOTH properties (tradewave.ai join page +
SMN expert hub) and an editor for expert commentary published onto SMN articles. SMN
participation is opt-in per affiliate; a TradeWave-only affiliate never sees or needs it.

## 2. What Already Exists (code-verified 2026-07-07; do not rebuild)

| Piece | Where | State |
|---|---|---|
| Affiliate model (code, rates incl. monthly split, payout, status, page_* branding, full e-sign audit fields) | `web/models.py:259-333` | BUILT |
| Payout ledger (idempotent monthly upsert, locked rows, paid refs) | `web/models.py:336-363`, `affiliate_service.upsert_month` | BUILT |
| Durable attribution (AffiliateReferral per subscription, webhook metadata `tw2_affiliate_id`) | `web/models.py:366-390`, `web/app.py:1998-2024` | BUILT |
| Commission compute (referral-first attribution, coupon fallback, self-referral guard, 3 models, basis = paid - tax - refunds) | `affiliate_service.compute_month/_compute` | BUILT |
| Co-branded public partner page | `/join/<code>` route + `page_display_name/logo/photo/note/signoff` | BUILT (this IS the tradewave-side affiliate page) |
| Referral capture (tw_ref 60d first-touch, `?code=`/`?via=`, checkout pre-apply) | `web/app.py:1960-2225` | BUILT |
| Agreement e-sign (magic link, 30d token, immutable snapshot, paused->active on sign, Exhibit B addendum rider) | `web/affiliate_agreement.py`, `/affiliate/sign/<token>` | BUILT |
| Monthly statements email (anonymized: totals + customer count only) | `web/affiliate_report.py` (cron 2nd 03:30) | BUILT |
| Operator admin (create/provision, compute/commit, mark paid, change terms + re-sign) | Flask-Admin views `web/app.py:3276-4210` | BUILT |
| Blueprint pattern to copy (session gating via injected `get_current_user`) | `web/api_portal/` | BUILT |
| Affiliate login / any users-table linkage | - | MISSING (affiliates are non-users today; only magic links) |

## 3. Requirements

### R-A. General dashboard (must ship first)
- A1. Affiliate signs in with a normal TradeWave (WorkOS) account and reaches
  `/account/affiliate`; non-affiliates get a clean "invite-only program" page (no probing).
- A2. Overview: program status (paused/active), agreement status with a link to the signed
  snapshot, their code, referral link (`/?code=X`), join-page link (`/join/X`), effective
  discount/commission terms incl. monthly split when present, commission model label.
- A3. Performance: current-month LIVE estimate + settled monthly history (from
  `affiliate_payouts`), each row: period, currency, basis, commission, status
  (pending/paid/void), paid date + external ref. Customer identities NEVER shown (mirror the
  statement-email privacy posture: totals + customer count; per-line detail limited to date,
  plan/interval, basis, commission).
- A4. Payouts: ledger view + payout method/email on file, with a "contact us to change" note
  (payout details stay operator-edited in v1; they gate real money).
- A5. Links and assets: copyable referral URL, join URL, and (Phase C) per-take SMN article
  URLs with their code + anchor.
- A6. Profile: view join-page branding (display name, photo, note, signoff); edit subject to
  the SAME validators the admin enforces (plain text, no links/markup, 280/60 caps), with
  operator notification email on change (partners are hand-picked + under signed agreement;
  post-hoc revert in admin is the control. Flippable to pre-approval later - see Open Q3).
- A7. Nothing in the portal writes to Stripe or the payout ledger. Read-only against money.
  (Keeps the whole portal in the "pure downstream of Stripe" safety class - buildable during
  stabilization, same as the rest of the affiliate system.)

### R-B. SMN expert module (optional per affiliate, second)
- B1. Participation is OPT-IN and operator-INVITED: affiliates have SMN state
  none -> invited -> active (-> paused). TradeWave-only affiliates (state none) see no SMN
  tab at all. Invited affiliates see the pitch + accept flow. Owner controls who is invited
  (quality bar for publishing on SMN).
- B2. Accepting requires click-accepting the SMN CONTRIBUTOR TERMS in-portal (they are
  already logged in; no magic link needed), recorded with the same audit discipline as the
  main agreement: version, timestamp, IP, UA, immutable snapshot. Terms source:
  `docs/SMN_CONTRIBUTOR_TERMS.md` (to be authored; covers position disclosure, no issuer
  compensation, no personalized advice, affiliate-compensation disclosure, retraction rights,
  license to publish, scorecard consent).
- B3. Expert profile (only for SMN participants): slug (IMMUTABLE once published), bio,
  credentials line, social links, disclosure line; reuses `page_photo` for the headshot.
  Powers the public SMN expert hub page (bio + take archive + scorecard when live).
- B4. Take editor: pick a recent article (from SMN `posts.json` via the web tier), write a
  take in MARKDOWN ONLY, optionally declare a scored call (symbol, direction, window dates),
  submit. States: draft -> submitted -> approved -> published, plus rejected and retracted.
  Operator review is MANDATORY before publish (market commentary on a public property).
- B5. Published takes render as the public Expert Desk block on the SMN article (display
  model per SMN_STRATEGY.md: public, stacked, static-baked, CTA carries `?code=`), and the
  expert hub page regenerates. Retraction removes the block on the next sync.
- B6. The affiliate sees status, published URLs (with their anchor + code), and later their
  scorecard, in the SMN tab.

### R-C. Non-functional
- C1. Topology-independent publishing: works whether SMN shares the web box (TW2 dev/staging
  today) or runs on a separate server over WAN (owner-stated prod). SMN NEVER gets auth;
  content crosses via the publish pipeline, identity stays on tradewave.ai.
- C2. Every portal query is scoped by the linked affiliate id derived from the SESSION user,
  never from a request parameter.
- C3. All affiliate-authored content is sanitized server-side on the web tier before it can
  reach a public page (bleach; markdown in, sanitized HTML out) AND the SMN injector bleaches
  again on its side (defense in depth; `publish_article.py` already has the chain).
- C4. Additive migrations only; no changes to webhook/billing paths; `years`-style storage
  IDs (slug, statuses) are permanent once written (tw-coding-standards).

## 4. Design

### 4.1 Auth + linkage (the one new foundation piece)
- Migration: `affiliates.user_id` (PG_UUID, FK users.id, NULLABLE, UNIQUE).
- Linking flow (no new roles; access = "session user has a linked, non-terminated affiliate
  row" - avoids duplicating truth into `ROLES`):
  1. Operator adds/has the affiliate with their real email (already NOT NULL).
  2. Affiliate logs in / signs up via WorkOS as a normal user.
  3. First visit to `/account/affiliate`: if no linked row, attempt AUTO-LINK by exact
     case-insensitive email match against `affiliates.email` where `user_id IS NULL` and
     status != 'terminated'; on match, set user_id + audit-log `affiliate_linked`.
  4. Fallback: operator sets the user manually in AffiliateAdmin (new column).
  - Email is trustworthy enough here because WorkOS verifies it and affiliate emails are
    operator-entered for hand-picked partners; the manual override covers mismatches (e.g.
    affiliate signs up with a different address).
- Account page (`/account`) shows an "Affiliate" card/link only when a linked row exists.

### 4.2 Blueprint + information architecture
`web/affiliate_portal/` blueprint, mounted at `/account/affiliate`, copying the
`web/api_portal/` pattern exactly (`set_user_loader(get_current_user)`, `require_login`,
shared `_base.html` styling).

| Route | Content |
|---|---|
| GET `/` | Overview (A2) + this-month estimate headline |
| GET `/performance` | Live current-month estimate + settled history (A3) |
| GET `/payouts` | Ledger + payout method on file (A4) |
| GET `/links` | Copyable URLs + assets (A5) |
| GET/POST `/profile` | Join-page branding edit (A6) + SMN expert profile when active |
| GET `/smn` | SMN tab: pitch/accept (invited), editor + take list (active); hidden when none |
| POST `/smn/accept` | Click-accept contributor terms (B2) |
| GET/POST `/smn/takes/new`, POST `/smn/takes/<id>/(submit|retract)` | Take lifecycle (B4) |

### 4.3 Schema (three additive migrations)
1. `affiliates.user_id` (4.1).
2. `affiliate_smn_profiles` (1:1, row exists only once invited - keeps `affiliates` lean):
   `affiliate_id` (PK+FK), `status` CHECK ('invited','active','paused'), `slug` (Text UNIQUE,
   immutable once `published_at` set), `bio_md`, `credentials` (Text, <=200), `links` (JSONB,
   validated {label,url} list, https only), `disclosure_md`, `terms_version`,
   `terms_accepted_at/ip/user_agent`, `terms_snapshot`, `scorecard_enabled` (bool default
   true), `published_at`, `created_at`, `updated_at`.
3. `expert_takes`: `id` (uuid), `affiliate_id` (FK, NOT NULL), `article_slug` (Text, NOT
   NULL), `title` (Text <=120, optional), `body_md` (Text <=8k), `declared_call` (JSONB
   nullable: {symbol, direction, entry_date, exit_date}), `status` CHECK
   ('draft','submitted','approved','published','rejected','retracted'), `review_note`,
   `reviewed_by` (FK users), `rendered_html` (sanitized, set at approve),
   `execution_note` (Text <=500, optional expert-described options/trade structure, shown as
   expert-reported), `execution_result` (Text <=300, optional post-window self-reported
   outcome, editable only by the owning affiliate on their published takes, audit-logged),
   `execution_result_at`, `published_at`, `retracted_at`, `created_at`, `updated_at`.
   Statuses and `article_slug` are storage IDs - never rename.

### 4.4 Service additions (`web/affiliate_service.py`)
- `compute_for_affiliate(session, affiliate, year, month)`: scoped variant of the existing
  compute (reuse `_compute` with a single-affiliate list + that affiliate's referrals) for
  the live current-month estimate. Clearly labeled ESTIMATE in the UI (settles on the 2nd).
- `web/expert_takes_service.py`: take CRUD + state machine + markdown render + bleach
  (single sanitation authority), operator notification emails (Resend, best-effort, same as
  agreement mails).

### 4.5 One profile -> two public pages
- tradewave.ai side: `/join/<code>` ALREADY IS the affiliate page; the dashboard just makes
  its `page_*` fields self-serve (A6). No new page needed.
- SMN side: static expert hub `https://<smn>/experts/<slug>.html` (bio, headshot, disclosure,
  take archive linking to articles, scorecard section when live), regenerated by the SMN box
  from pulled profile data (4.6). Published ONLY when smn status = active AND operator has
  approved at least one take (no empty hubs).

### 4.6 SMN publishing across the WAN (pull model, topology-independent)
- Web tier exposes TWO internal endpoints, auth by the existing `X-Service-Key` pattern
  (`/internal/render_report` precedent):
  - `GET /internal/expert_takes?since=<cursor>` -> published + retracted takes
    (rendered_html, article_slug, affiliate display fields, declared_call, timestamps).
  - `GET /internal/expert_profiles?since=<cursor>` -> active profiles for hub pages.
- SMN box: a per-minute cron (or a loop in `article_processor.py`) pulls both, keeps a
  cursor file, bleaches AGAIN, injects/removes the Expert Desk section for affected article
  slugs via the existing `article_post_process.py` section-injection pattern, and
  regenerates hub pages. Outbound-only from SMN; no inbound port, no auth on SMN, ever.
- Co-located deployments work identically (the pull hits localhost); optionally short-cut
  with a redis nudge later - not required.
- Phase 2 gating (future): full takes move behind auth ON tradewave.ai; the SMN block
  becomes the teaser + link. No SMN-side change beyond the block template.

### 4.7 Operator surface additions (Flask-Admin)
- AffiliateAdmin: show/edit `user_id` link; SMN invite action (creates `affiliate_smn_profiles`
  row status=invited + sends invite email); page-field change notifications land in inbox.
- New `ExpertTakeAdmin`: review queue (submitted first), approve (renders + sanitizes +
  stamps `rendered_html`)/reject with note; view published; retract.
- Audit log events: affiliate_linked, smn_invited, smn_terms_accepted, take_submitted/
  approved/rejected/published/retracted, profile_updated.

### 4.8 Privacy + security rules (portal-wide)
- No customer PII to affiliates, anywhere (match `affiliate_report.py` posture).
- All queries scoped via session-derived affiliate id (C2). CSRF on all POSTs (web tier
  default). Modest rate limits on take submission (e.g. 10/day).
- Payout method/email: display-only in v1 (changes via operator).
- Markdown-only inputs; two-sided bleach (C3); links JSONB https-only + label length caps.
- Slug + statuses immutable/permanent (C4). Terminated affiliate: portal access closes
  (linkage check excludes terminated), published takes retracted on next sync per contract.

## 5. Phasing

- PHASE A (dashboard core): migration 1, blueprint, Overview/Performance/Payouts/Links,
  auto-link flow, admin user_id column. Ships value to current partners immediately.
- PHASE B (self-serve profile): `/profile` editing of page_* with validators + notification,
  plus photo/logo upload per decision 2 (validated, auto-resized, notified).
- PHASE C (SMN module): migrations 2+3, contributor terms doc + click-accept, take editor,
  ExpertTakeAdmin review, internal endpoints, SMN-side pull/inject/hub-regen, links tab gains
  per-take URLs. Scorecard = Phase C2 (declared_call evaluation job + hub/dashboard render),
  reusing the daily-pick price-tracking approach.

## 6. Decisions (owner, 2026-07-07)

1. Live estimate: SHOW it - labeled "estimate - final on the 2nd", cached ~1h per affiliate
   (each recompute hits Stripe live; the monthly statement email stays the number of record).
2. Photos/logos: the owner is OUT of the manual file loop ("operator managed not me").
   v1 = upload through the PORTAL profile page: jpg/png/webp only, <=2 MB, server-side
   auto-resize to the standard avatar/chip dimensions, EXIF stripped, saved as
   `/assets/affiliate-logos/<code>-photo.webp` etc., operator notification email on change
   (same posture as decision 3). If the owner instead meant upload via the ADMIN form, the
   pipeline is identical - only the form moves; confirm at Phase B.
3. Join-page text edits: DIRECT with operator notification email; revert-in-admin is the
   control. Flip to a pre-approval queue only if the program opens beyond hand-picked partners.
4. SMN contributor terms: SEPARATE terms document with in-portal click-accept, because SMN
   participation is optional; the main affiliate agreement stays untouched for TradeWave-only
   affiliates.
5. Scorecard: TWO-LAYER (owner flagged that experts will often express calls as compound
   OPTIONS structures, not stock trades):
   - Layer 1, house-scored (canonical, in the verified win rate): every scored call MUST
     declare the directional thesis on the UNDERLYING (symbol, direction, window). Scored
     automatically at close-of-window from underlying prices - same rule as the engine's
     per-year pattern win/loss. Objective, ungameable, needs no options data.
   - Layer 2, expert-reported (optional, labeled, EXCLUDED from the verified record): the
     expert may describe their actual structure at publish time (`execution_note`, e.g. the
     specific spread and credit) and self-report the outcome after the window
     (`execution_result`). Rendered as "expert-reported execution", visually distinct from
     house-verified stats. Pure self-reporting was rejected as the canonical score: a
     self-graded public scorecard is just social media again; the verified directional layer
     is what differentiates the platform.
   - Future extension if needed: a "range" call type for non-directional structures
     (scored on whether the underlying stayed inside the declared range - still computable
     from underlying prices).
