// =====================================================================
// onboarding.js - shared helper module for the new-user trial onboarding.
//
// Pure JS (no JSX). This is the dependency the onboarding UI components
// import: WelcomeTrial, the daily Tara cards, the days-remaining pill,
// and the end-of-trial conversion card all pull state + copy from here.
//
// Design source of truth: docs/ONBOARDING_DESIGN_VALIDATED.md
// House voice: AP Title Case headlines, no terminal period, no em-dashes
// (use " - "), confident evidence framing, short.
//
// State pieces this module owns:
//   localStorage 'tw_onboard_started_at'  - ISO date the 7-day arc actually started (seeds day
//                                           counter). ONLY seeded when the user is enrolled (or
//                                           being enrolled via enrollNow()) - see Gating v2 below.
//   localStorage 'tw_onboard_lastfired'   - YYYY-MM-DD of the last day a card fired
//   localStorage 'tw_lesson_enrolled'     - '1' once the user has opted (or been auto-opted) into
//                                           the 7-day lesson arc. THE gate for all auto-open/arc
//                                           behavior (see Gating v2 below).
//   cookie       'tw_welcomed'            - welcome modal shown (per-user)
//   cookie       'tw_onboard_dismissed'   - whole arc muted (per-user)
//   cookie       'tw_lesson_day'          - last-viewed lesson day (LessonBox reopen, per-user)
//
// Window globals (set by the server, already the EFFECTIVE values):
//   window.tw2_user_tier          'explorer'|'navigator'|'analyst'|'strategist'
//   window.tw2_trial_ends_at      ISO string while a reverse trial is active, else ''
//   window.current_user_created_at  date-only ISO string ('YYYY-MM-DD') of account creation,
//                                    injected by web/app.py from users.created_at. Drives
//                                    getAccountAgeDays()/isAutoArcEligible() below.
//
// ---------------------------------------------------------------------
// Gating v2 (2026-07-04) - eligibility + enrollment model.
//
// THE BUG this replaced: getOnboardingDay() used to unconditionally seed
// tw_onboard_started_at with TODAY the first time it was ever called with no
// existing value - which happens for every logged-in user who lacks the key,
// i.e. literally every pre-existing account (App.js called it on every
// login). That silently enrolled every existing user as a brand-new Day-1
// onboarding target, so the LessonBox auto-popped daily for people who had
// been using the app for months.
//
// THE FIX: enrollment is now its own explicit, persisted flag
// (tw_lesson_enrolled), and getOnboardingDay() no longer seeds anything for
// an unenrolled user. Only two things ever enroll a user:
//   1. App.js, on login, auto-enrolls a GENUINE new user: isAutoArcEligible()
//      (account created <= 7 days ago) AND not already enrolled AND not
//      dismissed. Fails safe: an unknown/unparseable created_at date is
//      NEVER eligible (isAutoArcEligible() returns false), so a missing
//      server value can never accidentally auto-enroll anyone.
//   2. An explicit user action in LessonBox.js (clicking the lightbulb while
//      unenrolled, "Start the tour" on the one-time invite bubble, or the
//      SubscriptionWelcomeModal handoff) calls enrollNow() - user intent
//      overrides the age window.
// isOnboardingArcActive() (and anything else gating the daily arc) now
// requires isEnrolled() first. This is also the retroactive fix for the
// past week's wrongly-enrolled existing users: they have a stale
// tw_onboard_started_at but never got the (newly-introduced) enrolled flag,
// so every auto-open path now correctly treats them as not-enrolled.
// =====================================================================

import { lsGet, lsSet, getCookie, setCookie } from './Common';

// ---------------------------------------------------------------------
// Per-user cookie helpers.
//
// lsGet/lsSet in Common.js are already user-scoped (keys are prefixed
// with window.current_user_id). The cookie helpers are NOT, so we scope
// the cookie NAME by user id ourselves - otherwise a second account on
// the same browser would inherit the first user's "welcomed"/"dismissed"
// state. Default to '0' when no user id is present (logged-out / pre-auth).
// ---------------------------------------------------------------------
const _currentUserId = () => {
  try {
    return (typeof window !== 'undefined' && window.current_user_id)
      ? String(window.current_user_id)
      : '0';
  } catch (e) { return '0'; }
};

const _scopedCookieName = (name) => `${name}_${_currentUserId()}`;

const _todayStr = () => {
  // Local-date YYYY-MM-DD, the same key shape the existing tip scheduler uses.
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
};

// ---------------------------------------------------------------------
// Day counter - 1-based day since the arc started.
//
// Seeds localStorage 'tw_onboard_started_at' (ISO date) the first time it is
// called for an ENROLLED user with no start date yet (see Gating v2 above -
// enrollNow() normally seeds this itself, so that path is mostly a safety
// net). An UNENROLLED user with no start date is not on the arc at all -
// returns 0 (inactive) and seeds nothing. Otherwise returns the calendar-day
// delta + 1, so the first day is Day 1, clamped to the 7-day arc on the high
// end; never returns < 1 once a valid start date exists.
// ---------------------------------------------------------------------
export function getOnboardingDay() {
  let startedAt = lsGet('tw_onboard_started_at', null);
  const now = new Date();

  if (!startedAt) {
    if (!isEnrolled()) return 0; // not on the arc - never silently seed/enroll
    startedAt = _todayStr();
    lsSet('tw_onboard_started_at', startedAt);
  }

  // Parse the stored YYYY-MM-DD as a LOCAL date. new Date('YYYY-MM-DD') parses as
  // UTC midnight, which in a negative-offset timezone reads back as the PREVIOUS
  // local day - the off-by-one that made Day 1 compute as Day 2.
  let start;
  const _m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(startedAt));
  if (_m) {
    start = new Date(parseInt(_m[1], 10), parseInt(_m[2], 10) - 1, parseInt(_m[3], 10));
  } else {
    start = new Date(startedAt);
  }
  if (isNaN(start.getTime())) {
    // Corrupt value - reseed today so the arc still works.
    start = now;
    lsSet('tw_onboard_started_at', _todayStr());
  }

  // Compare on calendar-day boundaries (ignore clock time), so a login at
  // 11pm and one at 1am the next day are Day 1 and Day 2, not 2 hours apart.
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const msPerDay = 24 * 60 * 60 * 1000;
  // Math.round (not floor): across a DST transition a true 1-calendar-day step is
  // 23h or 25h, and floor would drop/inflate a day. Same UTC-vs-local class as the
  // start-date parse above.
  const delta = Math.round((nowDay - startDay) / msPerDay);

  const day = delta + 1;
  if (day < 1) return 1;
  if (day > ONBOARDING_DAYS.length) return ONBOARDING_DAYS.length;
  return day;
}

// ---------------------------------------------------------------------
// Trial state - read straight off the window globals the server set.
//
// onTrial is true ONLY on an affirmative future trial-end (default-to-silent
// on ambiguous / missing / past state, so a payer never sees a clock).
// daysRemaining counts what the user still HAS, inclusive of today, so a
// trial ending later today still reads as "1 day left", never 0.
// ---------------------------------------------------------------------
export function getTrialState() {
  let tier = 'explorer';
  let endsAtRaw = '';
  try {
    if (typeof window !== 'undefined') {
      tier = window.tw2_user_tier || 'explorer';
      endsAtRaw = window.tw2_trial_ends_at || '';
    }
  } catch (e) { /* default values */ }

  if (!endsAtRaw) {
    return { onTrial: false, daysRemaining: null, tier };
  }

  const endsAt = new Date(endsAtRaw);
  if (isNaN(endsAt.getTime())) {
    return { onTrial: false, daysRemaining: null, tier };
  }

  const now = new Date();
  if (endsAt <= now) {
    // Trial already over - silent, no pill.
    return { onTrial: false, daysRemaining: null, tier };
  }

  const msPerDay = 24 * 60 * 60 * 1000;
  const daysRemaining = Math.max(1, Math.ceil((endsAt - now) / msPerDay));
  return { onTrial: true, daysRemaining, tier };
}

// ---------------------------------------------------------------------
// Telemetry - fire-and-forget. Never throws, never blocks a render.
//
// These WEB endpoints authenticate off the session cookie, so a plain
// same-origin fetch with credentials:'same-origin' is correct (no token).
// valid types: market_opened|symbol_scored|wave_viewer_opened|pattern_saved|
//              reverse_date_range|pe_toggle|report_view|persona
// ---------------------------------------------------------------------
export function logEvent(type, detail) {
  try {
    fetch('/api/onboarding/event', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, detail: detail || {} }),
      keepalive: true,
    }).catch(() => { /* fire-and-forget */ });
  } catch (e) { /* never throw from telemetry */ }
}

// ---------------------------------------------------------------------
// Usage summary - the trust-signal source for the end-of-trial card.
//
// Returns the parsed object, or null on any error (caller must hedge:
// when null or measured===false, do NOT claim "measured").
// Shape: {measured, event_count, markets_used[], market_names[], persona,
//         patterns_saved, max_years, recommended_tier}
// ---------------------------------------------------------------------
export async function fetchUsageSummary() {
  try {
    const res = await fetch('/api/onboarding/usage-summary', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

// ---------------------------------------------------------------------
// The 7-day Tara card arc.
//
// One ~15-second card per calendar day, fallback for users who leave and
// return (the same-session fast track compresses D1-D3 inline for users who
// stay). Each entry: {day, headline, body, taraPrefill}.
//   - headline: AP Title Case, no terminal period, no em-dash.
//   - body: max two short lines; every metric term gets a 5-word plain gloss
//     the FIRST time it appears.
//   - taraPrefill: the pre-filled question handed to Tara (chatbotPrefill ->
//     autosend), so she is the single through-line of the curriculum.
//
// Arc (from the design):
//   D1 WHY -> verdict -> PE+2 tease -> the 5-part pattern schema
//   D2 the SCAN -> VALIDATE -> ORGANIZE -> ACT loop + the 3 fixed views
//   D3 read win-rate WITH the smoothness score + small-sample honesty
//   D4 regime / PE+2 toggle + the multiple-comparisons / hold-out card
//   D5 the 100-Year Pattern (stop/target discipline)
//   D6 the long workflow (Buy & Hold -> Reverse Date Range -> long hold)
//   D7 consolidate -> save one pattern + set the reminder
// ---------------------------------------------------------------------
export const ONBOARDING_DAYS = [
  {
    day: 1,
    headline: 'Why a Calendar Window Can Have an Edge',
    body: 'Some date windows have paid off almost every year for a century - here is yours, scored good, bad or noise. This one is PE+2-calibrated (where 2026 sits in the election cycle).',
    taraPrefill: 'Show me the strongest seasonal window on my stock and explain what makes this pattern real - including the one cycle it lost.',
  },
  {
    day: 2,
    headline: 'Scan, Validate, Organize, Act',
    body: 'The loop: scan thousands of windows, validate the one you like, organize it, then act. The three Wave Viewer views run in that order. A high rank is found, not approved - you still validate it.',
    taraPrefill: 'Walk me through the scan to validate to act loop on this setup, and show me why ranked is not the same as approved.',
  },
  {
    day: 3,
    headline: 'Read the Win Rate With Its Smoothness',
    body: 'Win rate alone is half the story - read it with the TWR (how smooth the ride was). And mind the sample: 96% across 24 cycles is signal, 100% across 3 years is noise.',
    taraPrefill: 'Open the stats table and read me the win rate with the TWR, then show me a thin-sample setup so I can see why a small number lies.',
  },
  {
    day: 4,
    headline: 'The Same Date, A Different Regime',
    body: 'Toggle the PE+2 filter (where the year sits in the election cycle) and watch the same setup flip. We scan thousands of windows - here is how we keep that from manufacturing a 96%: it has to hold on cycles the search never touched.',
    taraPrefill: 'Toggle the election-cycle filter on this setup and show me how it holds up out of sample, so I know the number is not just curve-fit.',
  },
  {
    day: 5,
    headline: 'The 100-Year Pattern, Entry to Exit',
    body: 'The 100-Year Pattern is the full-history seasonal shape (one curve over ~98 years). Set your stop and target before you enter, not after - and know the path: how deep it went underwater before it worked.',
    taraPrefill: 'Show me the 100-Year Pattern on this stock with its drawdown, and help me set a stop and target before entry.',
  },
  {
    day: 6,
    headline: 'The Long Hold, Positioned by Cycle',
    body: 'For a months-long hold: Buy & Hold, then Reverse Date Range (work backward from your exit date) to a 150-340 day position. The election cycle tells you whether 2026 favors holding it.',
    taraPrefill: 'Build me a long positioning hold using Reverse Date Range and the 98-year history, and tell me whether this part of the cycle favors holding.',
  },
  {
    day: 7,
    headline: 'Save One Pattern, Set the Reminder',
    body: 'Pick the strongest window you found this week, save it, and set its reminder so it pings when the window opens. Everything you saved stays here - it does not expire with the trial.',
    taraPrefill: 'Help me save my strongest pattern from this week and set a reminder for when its window opens.',
  },
];

// ---------------------------------------------------------------------
// Tier info - copy for the welcome / conversion / what-you-keep surfaces.
// Prices confirmed against the live Stripe-authoritative points.
// (markets phrasing matches the AP-style house voice.)
// ---------------------------------------------------------------------
export const TIER_INFO = {
  explorer: {
    price: 'free',
    markets: 'the Dow 30',
  },
  navigator: {
    price: '$19/mo',
    markets: 'Dow, NASDAQ and S&P 500',
  },
  analyst: {
    price: '$47/mo',
    markets: 'Russell, Wilshire, ETFs and indices',
  },
  strategist: {
    price: '$129/mo',
    markets: 'futures, forex, bonds and crypto',
  },
};

// ---------------------------------------------------------------------
// Account age + auto-enroll eligibility (Gating v2, 2026-07-04).
//
// getAccountAgeDays() reads the server-injected window.current_user_created_at
// (date-only ISO string, e.g. '2026-06-30') and returns the CALENDAR-day
// difference to today - 0 the day the account was created, 1 the next
// calendar day, etc. Returns null whenever the date is missing or fails to
// parse, so a server/window glitch reads as "unknown", never as "0 days old".
// ---------------------------------------------------------------------
export function getAccountAgeDays() {
  let createdRaw = '';
  try {
    if (typeof window !== 'undefined') createdRaw = window.current_user_created_at || '';
  } catch (e) { return null; }
  if (!createdRaw) return null;

  const _m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(createdRaw));
  const created = _m
    ? new Date(parseInt(_m[1], 10), parseInt(_m[2], 10) - 1, parseInt(_m[3], 10))
    : new Date(createdRaw);
  if (isNaN(created.getTime())) return null;

  const now = new Date();
  const createdDay = new Date(created.getFullYear(), created.getMonth(), created.getDate());
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const delta = Math.round((nowDay - createdDay) / (24 * 60 * 60 * 1000));
  return delta < 0 ? 0 : delta; // clock-skew safety - never a negative age
}

// Auto-enroll eligibility window: account age must be KNOWN and <= 7 days.
// FAILS SAFE - an unavailable/unparseable created_at (getAccountAgeDays()
// returns null) is NEVER eligible, so a missing server value can never
// silently auto-enroll an existing user. This is the direct fix for the bug
// where every pre-existing account without a start date read as brand new.
export function isAutoArcEligible() {
  const age = getAccountAgeDays();
  return age !== null && age <= 7;
}

// ---------------------------------------------------------------------
// Enrollment - the master gate for ALL auto-open / daily-arc behavior
// (Gating v2, 2026-07-04). Per-user localStorage flag, set either by
// App.js auto-enrolling a genuinely new user (isAutoArcEligible()) or by an
// explicit user action in LessonBox.js (lightbulb click / invite accept /
// welcome-modal handoff while unenrolled).
// ---------------------------------------------------------------------
export function isEnrolled() {
  return lsGet('tw_lesson_enrolled', null) === '1';
}

export function setEnrolled() {
  lsSet('tw_lesson_enrolled', '1');
}

// Opt a user into the arc RIGHT NOW: mark enrolled, seed a FRESH start date
// (today), and reset the per-day progress markers so the arc always begins
// cleanly at Day 1 - regardless of any earlier (possibly stale/wrong) state.
export function enrollNow() {
  setEnrolled();
  lsSet('tw_onboard_started_at', _todayStr());
  lsSet('tw_lesson_lastopened', 0);
  for (let d = 1; d <= ONBOARDING_DAYS.length; d += 1) {
    lsSet(`tw_lesson_screen_${d}`, 0);
  }
}

// ---------------------------------------------------------------------
// Seen / dismissed state - one-time, cookie-gated, per-user.
//   tw_welcomed         - the welcome modal has been shown (never re-fires).
//   tw_onboard_dismissed- the whole arc is muted ("Skip tips" / "Just browse"
//                         / the daily-card permanent checkbox). Mute leaves
//                         Tara usable and does NOT suppress the days-remaining
//                         pill or the end-of-trial card (those are state facts).
// 365-day cookie lifetime so the one-time gates outlive the 7-day arc.
// ---------------------------------------------------------------------
export function hasWelcomed() {
  return getCookie(_scopedCookieName('tw_welcomed')) === '1';
}

export function setWelcomed() {
  setCookie(_scopedCookieName('tw_welcomed'), '1', 365);
}

export function isTipsDismissed() {
  return getCookie(_scopedCookieName('tw_onboard_dismissed')) === '1';
}

export function setTipsDismissed() {
  setCookie(_scopedCookieName('tw_onboard_dismissed'), '1', 365);
}

// Unmute counterpart - overwrites the cookie rather than deleting it, so a stale
// browser-cached '1' can never resurrect on a partial expiry.
export function clearTipsDismissed() {
  setCookie(_scopedCookieName('tw_onboard_dismissed'), '0', 365);
}

// Conversion card show-once - PER USER (not global). A global name let one account
// permanently suppress the day-7 card for every other account on a shared browser.
export function hasConversionShown() {
  return getCookie(_scopedCookieName('tw_conversion_shown')) === '1';
}

export function setConversionShown() {
  setCookie(_scopedCookieName('tw_conversion_shown'), '1', 365);
}

// ---------------------------------------------------------------------
// Last-viewed lesson day - per-user cookie so the LessonBox reopens on the day
// the user was last reading (not forced back to today), and survives the
// localStorage logout-wipe. Returns null when unset/invalid so the caller can
// fall back to today's day. Clamped to the 7-day arc.
// ---------------------------------------------------------------------
export function getLessonDay() {
  const n = parseInt(getCookie(_scopedCookieName('tw_lesson_day')), 10);
  if (isNaN(n) || n < 1) return null;
  return Math.min(n, ONBOARDING_DAYS.length);
}

export function setLessonDay(day) {
  const n = parseInt(day, 10);
  if (isNaN(n) || n < 1) return;
  setCookie(_scopedCookieName('tw_lesson_day'), String(Math.min(n, ONBOARDING_DAYS.length)), 365);
}

// Is the 7-day arc still running? Uses the RAW (un-clamped) day delta so it can tell
// Day 7 from Day 50 (getOnboardingDay clamps both to 7). Drives whether the daily
// cards fire and whether the legacy Tara tips stay suppressed (vs the old approach of
// permanently pinning tw_tara_tip_index, which killed the generic tips forever).
export function isOnboardingArcActive() {
  if (!isEnrolled()) return false; // Gating v2: enrollment is the master switch
  if (isTipsDismissed()) return false;
  const startedAt = lsGet('tw_onboard_started_at', null);
  if (!startedAt) return true; // enrolled, start date not persisted yet (race) - arc is starting
  const _m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(startedAt));
  const start = _m
    ? new Date(parseInt(_m[1], 10), parseInt(_m[2], 10) - 1, parseInt(_m[3], 10))
    : new Date(startedAt);
  if (isNaN(start.getTime())) return true;
  const now = new Date();
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const nowDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const delta = Math.round((nowDay - startDay) / (24 * 60 * 60 * 1000));
  return delta < ONBOARDING_DAYS.length; // Day 1..7 = delta 0..6; day 7+ = done
}

// ---------------------------------------------------------------------
// Per-day fire guard - at most one daily card per calendar day.
//
// dayFiredToday() is the scheduler guard (tw_onboard_lastfired != today);
// markDayFired() is called when a card fires OR is dismissed (dismissing
// still counts the day as taught, so tomorrow's card is the next one).
// localStorage (user-scoped via lsGet/lsSet), keyed to the local date.
// ---------------------------------------------------------------------
export function dayFiredToday() {
  return lsGet('tw_onboard_lastfired', null) === _todayStr();
}

export function markDayFired() {
  lsSet('tw_onboard_lastfired', _todayStr());
}
