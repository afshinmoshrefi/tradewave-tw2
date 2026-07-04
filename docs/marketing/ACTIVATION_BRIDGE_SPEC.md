# Activation Bridge - spec (free seasonal report -> signup -> "their stocks, scored")

**Why:** the report email promises "see the calibrated AI score on YOUR stocks." If signup dumps
the user in the generic app, that promise is unfulfilled in the first 60 seconds and they churn -
the funnel's worst leak, right after the most expensive conversion (we pay affiliates 35% to get
them here). The activation bridge's one job: **close the exact loop the email opened** - land the
new user on their own stocks with the calibration score revealed, in under a minute.

## The flow (signup -> aha -> 7-day arc -> catch-net)

1. **Resolve "their stocks"** (two sources, union preferred):
   - PRIMARY: **email-match union** - `leads_tickers_for_email(user.email)` (BUILT, web/app.py):
     union of every ticker that email asked about across all non-spam report requests, newest-first,
     deduped, capped at 15. Robust (survives the OAuth round-trip; works even if they ran the report
     3x). This is why "ran it more than once" is a feature - they get ALL their stocks.
   - FALLBACK: the `?tickers=AAPL,MSFT,NVDA` param the report CTA now carries (BUILT in
     seasonal_report.py). Best-effort only - it can be lost across the WorkOS OAuth redirect unless
     threaded through `state`/session; the email-match makes it non-load-bearing. Use it only when
     the signup email differs from the report email (no lead rows to match).

2. **Create their starter watchlist at signup** [TO BUILD]:
   in `lazy_create_user` (web/app.py, ~where mailerlite_subscribe fires on CREATE), resolve the
   tickers (union || param) and create a "My Stocks" watchlist for the new user. Watchlists are
   appserver-side (Redis saved-data) - mint the user token and POST the watchlist, OR let the
   first-run React view create it client-side on first load. DECISION: prefer server-side at create
   so the app simply finds it already there. Skip silently if no tickers resolve (cold signup).

3. **First-run "Your Stocks, Scored" view** [TO BUILD - React, the biggest piece]:
   the FIRST screen post-signup is NOT the blank app - it's their 3+ stocks with the AI calibration
   score REVEALED (the locked thing from the email), each beside its historical record. One-time
   banner: "Your 7-day full access is on - here are the calibrated scores on the stocks you asked
   about." Reuse the existing score/pattern rendering; what's new is the guided landing + the banner.

4. **Drive the aha (retention predictor)** [TO BUILD]:
   a pre-filled Tara prompt - "Which of my stocks has the strongest seasonal setup right now?" -
   Tara names the winner + drives the chart. Then nudge: add more of your stocks; surface one thing
   they'll lose on free Explorer (a market beyond DJ30, the PE-cycle filter) to plant the loss.

5. **The 7-day arc** [TO BUILD - MailerLite automation + Stripe coupon]:
   D1-4 pull-backs ("a window historically opened on one of your stocks" - past-tense, compliant) ->
   **D5 loss-framed downgrade** ("in 2 days you drop to Explorer, DJ30 only - here's the exact window
   on $TICKER you'll lose") -> D6-7 close to **Navigator $19, annual-first** (Stripe coupon onto the
   $19 rung; lead with $159/yr to recover CAC + the 35% affiliate haircut day one).

6. **Catch-net for non-converters** [FUTURE - the recurring loop]:
   if they don't pay, they fall to free Explorer but are now a known warm user -> the recurring
   trigger loop (warm-base emails, compliant template). A non-converter is nurtured, not lost.

## Built already (this work)
- `leads_tickers_for_email(email)` - the email-match union (web/app.py). TESTED on dev.
- `?tickers=` carried into the signup link from the report CTA (seasonal_report.py).
- Report CTA reframed around the calibration gap ("See My Calibrated Scores - Free for 7 Days").
- **localStorage pre-fill** - a return visitor to the report modal gets their last tickers + email
  pre-filled (v4.html; key `tw_lead`). TESTED.

## MVP (feasible in the 60-day window)
(1) signup reads union/param -> auto-create the "My Stocks" watchlist; (2) drop them into the app
with it active + the one-time "scores unlocked" banner; (3) the D5 loss-frame email + the $19 annual
coupon. Defer the full first-run React redesign + the recurring loop.

## Open / operator + decisions
- WHERE the watchlist is created (server-side at lazy_create_user vs client-side first-run) - pick one.
- Threading `?tickers` through the WorkOS `state` if you want the param as a true fallback (else rely
  on email-match only).
- The Stripe coupon for the Navigator-$19 / annual-first close (operator: create in Stripe).
- The D5/close + pull-back emails as a MailerLite automation (operator: build in MailerLite UI).
- Confirm the appserver watchlist-create endpoint + the service/user-token path for step 2.

## The pairing rule
Ship the stronger report CTA (already live) WITH at least the MVP bridge. A bigger promise + a blank
app makes the leak worse - the promise and the payoff must land together.
