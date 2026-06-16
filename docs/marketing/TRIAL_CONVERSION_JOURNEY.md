# TradeWave Trial Conversion Journey - Build-Ready Spec
> Produced 2026-06-16 by a 16-agent workflow (4 grounding agents against live code, 4 journey concepts
> across psych lenses, 5 judges incl. a dark-pattern skeptic + compliance, synthesis, 2 adversarial
> reviewers). Extends - does not replace - the June-9 welcome modal spec (`/home/afshin/tw-welcome-modal-spec.md`).
> The adversarial fixes are baked in below; one DISQUALIFYING issue gates two emails (see §Dependencies).

## The strategy in one line
The 7-day reverse trial is a **loss-aversion machine**: get them to look up a stock THEY own (attachment),
accumulate saved work (investment), then at trial end frame the upgrade as **keeping what they built**, not
gaining features. Honest loss only - every named loss maps to a verified config delta.

## North-star metric
`paid_conversion_from_trial` = trial signups who start a paid sub within 14 days / trial signups.
Leading metric (movable weekly): `trial_activation_rate` = share who reach the **endowed state** by day 4
= (>=1 personal-ticker lookup on a non-DJ30 market) AND (>=1 saved pattern OR watchlist symbol).
**Blocker:** there is NO event sink in the codebase today - none of this is measurable until P0 builds it.

## The four levers (each moment names one)
1. **Aha before ask** - feel the green/red per-year bars before any wall.
2. **Personalization = attachment** - look up your OWN ticker (gated for free, OPEN in trial). The trial's #1 job.
3. **Loss aversion at trial end** - "keep what you have," itemized + true. ~2x the pull of gain framing. Currently DARK.
4. **Investment accumulation** - drive SAVES / watchlists / alerts; each is a sunk-cost hook for lever 3.

## The verified LOSS LIST (trial Strategist level '6' -> post-trial Explorer level '1')
Every loss-aversion claim must map to one of these (config.py TIER_FEATURES + level dicts):
- Markets: all 15 -> **DJ30 only** (`level_access_hierarchy['1']=['0']`)
- **Watchlists: 50 -> 0** (feature GONE, not capped - the cleanest honest loss object)
- Portfolios: 100 -> 1; tracked opportunities: 500 -> 5; top patterns/market: 500 -> 5
- Window tuning (change_start_date) + the 4-year election-cycle scan: ON -> OFF
- AI columns (AIS/Win%/PredR/PMFE): keep on DJ30 rows, stop on every other market (NOT trial-only - never claim they are)
- SMN articles, weekly Zoom, premium support -> off/community

## The journey (14 moments, day 0 -> day 9+)

| When | Channel | Surface | Lever | Goal + copy direction |
|---|---|---|---|---|
| Day 0, /app/ loads | in-app | June-9 Welcome Modal (BUILD) | 1 | Aha: CTA auto-fires the ungated row-click so bars are live on close. Trial chip "Full Access - 7 Days". |
| Day 0, ~90s | in-app | Tara proactive tip (existing engine) | 2 | "Want me to load a stock you actually trade? Type: show me NVDA." Tara's set_view loader is SHIPPED (Chatbot.js:294). |
| Day 0, on lookup | in-app | securities dropdown + inline coachmark (small build) | 2 | Get them onto THEIR ticker on a non-DJ30 market; honest thin-data fallback. |
| Day 0 | email | MailerLite welcome | 2 | Drive the one in-session action (personal lookup). |
| Day 1 (~24h) | email | NEW `trial_drip.py` via Resend | 2 | First practice rep if day-0 missed; plant the ledger trust anchor (SEE DEPENDENCY). |
| Day 2 | in-app | Tara tip | 4 | First SAVE (first sunk cost). |
| Day 3 | email | trial_drip.py | 1/trust | Teach the tool's LIMITS (anti-signal-seller; highest-trust move). |
| Day 4 | in-app | Tara tip(s) | 4 | Deepest accumulation: WATCHLIST (free=0, cleanest loss) + alert. |
| Day 5 | in-app | NEW trial-status / loss panel | 3 | Make the accumulated stake VISIBLE before it's taken - itemized, true. "2 Days Left." |
| Day 5 | email | trial_drip.py | 3 | The itemized loss to the inbox (lands without a login). |
| Day 6 | in-app | trial-status panel, "1 Day Left" | 3 | Narrow to the sharpest TRUE personal loss. |
| Day 7 | both | panel day-7 state + email | 3 | Decision moment at peak loss-salience. SOFT cutover (8h LTK tail - no instant-lockout claim). |
| Day 8+ | in-app | EXISTING free-register dialog + upgrade banner | 3 | The EXPERIENCED-loss peak: they stare at a DJ30 list where their ticker was yesterday. Both surfaces already fire - the work is copy. |
| Day 9 | email | trial_drip.py "graduate" | 3/close | Calm de-escalation; their saved work is held (true); then STOP. |

## The centerpiece: the honest trial-end loss panel (day 5, in-app)
> Header chip: **Full Access - 2 Days Left**
> Title: **You Have Built Something This Week. Here Is How to Keep It**
> On {trial_end_date} your account returns to the free Explorer plan. Here is exactly what that means:
> - Markets: you go from all 15 back to the Dow 30 only. The other 14 lock.
> - Your watchlist ({watchlist_count} tickers): the free plan does not include watchlists, so it is set aside while you are on Explorer.
> - Your saved patterns ({saved_count}): kept within the free plan's single-portfolio limit, but you can only act on the Dow 30 names in them.
> - The AI columns: you keep them on your Dow 30 rows; they stop on every other market.
> - Window tuning and the four-year election-cycle scan: paid features, so they turn off.
> Nothing is deleted today. You have two full days of everything left, and you can keep all of it.
> CTA: **Continue Full Access** / secondary **Remind Me Tomorrow**
> Footer: Research and education, not advice. Past patterns do not guarantee future results.

**FAIL-SOFT:** if the redis saved-work read is unavailable, DROP the two count-bearing lines entirely (never render `{watchlist_count}` literally, never a zero-count line). Keep markets + AI + window-tuning.
**CTA HONESTY (judge-mandated):** "Continue Full Access" must lead to a path that genuinely continues access. If checkout mints a SECOND 7-day Stripe trial (app.py trial_period_days:7), that is a dark pattern - resolve the second-trial question (§Open decisions) before this ships.

## Adversarial fixes baked in (do NOT regress)
- **KILLED - fabricated social proof:** "Most members have their moment right here..." (unverifiable). Replace with a falsifiable, self-referential line about what they just did.
- **KILLED - false-certainty flattery:** "You now know more about that stock than most people trading it." Replace with "In two minutes you have seen something most charts never show you - the calendar history."
- **Loss panel guardrail:** every "you will lose X" item conditioned on the user's REAL redis state; never overstate; the AI columns are NOT trial-only so are never claimed as a loss.
- **"15 markets" count:** verified (resources 0-13,16 = 15). Keep consistent everywhere.
- **Disclaimer on every signal-bearing moment** (in-app + email) - verbatim educational/no-advice line.
- **No advice/guarantee/competitor leaks** - reviewers spot-checked clean; keep it that way.

## DEPENDENCIES (the journey is BLOCKED on these - resolve before the dependent moments ship)
1. **THE SCORECARD MUST SHOW REAL LOSSES (disqualifying as-is).** The day-1 and day-3 emails' core trust
   move is "go look at our scorecard - we leave the losing calls in, on purpose." But the scorecard
   currently renders losing calls as WINS (the realize-at-peak-target bug from the website audit P1
   "scorecard truth package", still unshipped). A sophisticated trader who follows that CTA sees losses
   labeled wins and distrusts everything. **These two emails CANNOT ship until the scorecard truth fix
   lands.** This links the trial journey directly to the already-identified P1 site fix - do that first.
2. **Event sink (P0)** - no analytics exist; the north-star + 8 of 12 funnel events are unmeasurable
   until a minimal `track(event,props) -> POST /appserver/event -> events table` ships.
3. **Trial-end email rail (P0)** - NO trigger exists when `reverse_trial_ends_at` passes. Build
   `web/trial_drip.py` (clone expire_trials.py's row-locked structure), daily cron, keyed on the
   timestamp window; target ONLY rows with `reverse_trial_ends_at NOT NULL` (never-trialed explorers
   have it NULL - "your trial ended" is false for them).
4. **Trial-aware client wiring (small, do once)** - React reads `window.tw2_trial_ends_at` NOWHERE today
   (it is injected and ready, app.py:1042). Add `isTrial = trialEndsAt !== ''` + days-left at App mount;
   it is the ONLY signal distinguishing a trial user from a paid Strategist client-side.
5. **Resend dark on dev** (SUPPORT_EMAIL_FROM empty) + **gateway must be healthy** (Tara personalization
   needs it) + **Tara is desktop/tablet-landscape only** (phone users get the email rail, not the tips).

## Build phases
- **P0 (ship first, or the push runs blind):** event sink; `trial_drip.py` cron; the banner copy-flip
  (config.py:76, gated on trial-alumni discriminator - NOT one line, needs the discriminator). + the
  scorecard-truth fix as the unblocker for the trust emails.
- **P1:** the welcome modal (June-9 spec + trial chip); the trial-status/loss panel (the lever-3 in-app
  centerpiece, consumes tw2_trial_ends_at); trial-aware Tara tips (days 0/2/4).
- **P2:** contextual day-8+ gate copy ("This Market Was Open During Your Trial"); personalized email
  counts (fail-soft cross-tier redis read); MailerLite evergreen drip + re-auth.

## Open decisions (owner)
1. **Second-trial / card question (highest priority).** Does "Continue Full Access" mint a SECOND
   Stripe 7-day trial? If so the loss-aversion CTA is a dark pattern - decide the checkout path.
2. **Scorecard losses** - confirm the truth fix is scheduled (it gates the trust emails AND the site P1).
3. **Free-Explorer daily-pick email** - verified there is NO TW2 send today (it was TW1 infra). The free
   retention hook the strategy leans on does not exist yet - build or drop the assumption.
4. localStorage vs server seen-flags (per-device re-show); mobile coverage (Tara is desktop-only);
   /pricing frame (personal "what you keep" vs generic); reverse_trial coverage on the back-catalog.
