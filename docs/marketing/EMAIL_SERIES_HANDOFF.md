# Conversion Email Series - Handoff (built 2026-06-29, autonomous overnight run)

4 emails for each of the 4 plans (16 total), written to CONVERT THROUGH TRUST, not by selling -
the "tell them what they do not need / stay free if it fits / smallest plan that covers your use"
inverse-incentive (per the owner's "power of telling them not to buy" transcript). Produced by a
multi-agent loop (4 expert writers x 4 adversarial scorers, looped) then a finalize+verify pass.

## What is DONE (autonomous)
- **16 emails** written, scored, and finalized. Files (HTML to paste + plain-text + subjects):
  `docs/marketing/emails/{explorer-free,navigator,analyst,strategist}/email-{1..4}.html` and `.txt`,
  plus `subjects.md` per plan.
- **4 MailerLite automations created, INACTIVE** (one per plan, trigger = subscriber_joins_group):
  - "TradeWave - Explorer Nurture (4 email)"  -> group `explorer`
  - "TradeWave - Navigator Nurture (4 email)" -> groups `navigator_monthly` + `navigator_yearly` (newly created)
  - "TradeWave - Analyst Nurture (4 email)"   -> groups `analyst_monthly` + `analyst_yearly`
  - "TradeWave - Strategist Nurture (4 email)"-> groups `strategist_monthly` + `strategist_yearly`
  Each has 4 email steps + 3 delays (Explorer/Navigator 2/2/3 days, Analyst 2/2/2, Strategist 1/2/2),
  with subjects + plain-text set via API. Verified inactive via list_automations. IDs:
  - Explorer:   `191588255322343409`  https://dashboard.mailerlite.com/automations/191588255322343409
  - Navigator:  `191588340700546941`  https://dashboard.mailerlite.com/automations/191588340700546941
  - Analyst:    `191588402343183617`  https://dashboard.mailerlite.com/automations/191588402343183617
  - Strategist: `191588731493287625`  https://dashboard.mailerlite.com/automations/191588731493287625

### Plain-text cap caveat
`update_automation_email` HARD-REJECTS plain_text over 1000 chars; the full bodies are 1,252-3,635 chars.
So each step holds a faithful CONDENSED plain-text (subject + header + opening + CTA link + the honest
"stay on the cheaper plan" framing + price + sign-off). The FULL body lives in the HTML files - it gets
into MailerLite when you paste the HTML in the visual editor (step 1 below). Nothing was left empty.

### Reconcile overlapping automations
The account already has several Explorer/Trial-ish automations (e.g. "TW Welcome v2 (Explorer)",
"Free Explorer signup", "existing Explorer automation", "TW Trial (7-day)", plus the enabled
"Top 10 Welcome Sequence" / "New Pro Subscribers" / "New Instituional Subscribers"). Before activating
these new ones, decide which series owns each group so a subscriber does not get two welcomes.

## API LIMITATION (why HTML is not on MailerLite yet)
MailerLite's API CANNOT author email HTML - `create_automation`/`update_automation_email` only set the
subject + PLAIN TEXT. So the automations currently carry the complete copy as plain-text. To get the
designed look, a human must paste each email's HTML in the MailerLite visual editor (one paste per email).

## FLAGGED DECISION - Navigator + AI scoring (important)
The home page (and the dead `config.py` TIER_FEATURES doc) advertise Navigator with "AI scoring on Dow,
NASDAQ 100 and S&P 500." But the LIVE runtime gate is `config.py:253 ml_score_access_levels = ['4','5','6','7']`
(Analyst + Strategist + reverse-trial). **Navigator is level '2' - NOT in that list - so a paying Navigator
user does NOT get AI scoring today.** The adversarial reviewers caught this (code-verified). I did NOT
touch live config (pricing/policy call). I wrote the Navigator emails to its REAL unlocks (3 markets,
browse-any-start-date, the election-cycle table filter, more capacity) with NO AI claim. Decide one of:
  (a) Navigator SHOULD include AI scoring -> add '2' to `ml_score_access_levels`, restart appserver, and
      I can re-add the AI angle to the Navigator emails; OR
  (b) Navigator does NOT include AI scoring -> the emails are correct as-is, and the HOME PAGE Navigator
      card should drop/clarify the "AI scoring" claim (currently overstates Navigator).

## OPERATOR STEPS TO GO LIVE (none done by me; nothing is active)
1. **Paste HTML**: open each automation in MailerLite, and for each email paste the matching HTML from
   `docs/marketing/emails/<plan>/email-N.html` into the visual/custom-HTML block.
2. **Sender + reply-to**: set a verified sender (from-name, e.g. "Afshin at TradeWave") and a MONITORED
   reply-to (Analyst/Strategist emails promise email/premium support, so replies must reach a human).
3. **Subscription -> group wiring**: confirm/build the app step that adds a new subscriber to the right
   tier group on subscription (explorer / navigator_monthly|yearly / analyst_monthly|yearly /
   strategist_monthly|yearly). Without this, the join-group trigger never fires.
4. **Suppress the legacy welcome** for users entering a tier automation (group-membership exclusion) so a
   payer does not also get "Top 10 Welcome" / "New Pro" / "New Institutional".
5. **Resolve the Navigator AI decision** (above) before activating the Navigator series.
6. **Verify the CTA URLs** in the emails: `https://tradewave.ai/app/`, `.../scorecard/`, `.../pricing/`
   (placeholders - confirm the real paths). Unsubscribe is `href="#"` (MailerLite injects the real link).
7. **Activate** each automation when satisfied.

## Quality bar
Looped until each plan scored high on trust-signal/anti-sell, conversion, informativeness, value-clarity,
voice/compliance, and craft. Voice rules enforced: no em-dash, AP Title Case subjects + headlines (no
terminal period), confident historical evidence (never a forward promise), no "buy this", no competitor
names, live prices only (Navigator $19/$14yr, Analyst $47/$33yr, Strategist $129/$99yr, Explorer free).
A trial series (the `trial` group exists) was NOT built this run - add it next if wanted.
