import React, { useState, useEffect, useRef, useCallback } from 'react';
import { themeColors, lsGet, lsSet } from './Common';
import { getOnboardingDay, getTrialState, isTipsDismissed, setTipsDismissed, clearTipsDismissed, isEnrolled, enrollNow, isAutoArcEligible, logEvent, getLessonDay, setLessonDay } from './onboarding';
import { LESSONS, TRIAL_CLOSE_SCREEN } from './onboardingLessons';
import { FaAngleLeft, FaAngleRight, FaCheck } from 'react-icons/fa';

// =====================================================================
// LessonBox - the single teaching surface for the 7-day new-user arc.
//
// Premium dark, draggable floating panel. It REPLACES the OnboardingWelcome
// modal AND the daily Tara-launcher tips (one calm teaching surface, never a
// modal that blocks the chart/table). The render GATE lives in App.js; this
// component is safe to ALWAYS mount and self-manages open/closed via its own
// per-user localStorage state.
//
// Specs implemented verbatim from docs/ONBOARDING_LESSONS_LOCKED.md, PLUS
// Gating v2 (2026-07-04, see onboarding.js and the "Gating v2" doc section):
//   - ALL auto-open behavior is gated on isEnrolled() first (tw_lesson_enrolled).
//     A user who is not enrolled NEVER gets auto-opened - see the "existing-user
//     invite" bullet below.
//   - Day-keyed via getOnboardingDay() (1..7, clamped). While enrolled, auto-opens
//     ONCE per new calendar day to screen 1 (furthest day tracked in
//     tw_lesson_lastopened). Same-day reopen restores the last screen viewed
//     (tw_lesson_screen_<day>). A "where am I" line: "Day N of 7 - new lesson
//     today" vs "picking up where you left off" vs "all caught up".
//   - Usually 3 screens/day (Day 1 has 4); the progress rail + Back/Next adapt
//     to the count. Back HIDDEN on screen 1. The last screen's button is "Done":
//     on any day but the last it shows an "End of Day N / Beginning of Day N+1"
//     card and continues into the next day; on the FINAL day it confirms and
//     collapses to the lightbulb.
//   - All days are browsable from day 1. Back/Next page within a day; days are
//     advanced via the between-days card or jumped to from the "Lessons" list.
//     Only the auto-pop cadence is day-gated. Days ahead of today open in
//     preview/review and do not overwrite progress.
//   - "Lessons" header link lists EVERY day (tap to read) + "Back to Today" /
//     "Start day over".
//   - Draggable by the header; position persisted (tw_lesson_pos) with a
//     snap-back-to-center safety; never covers the whole screen; clear (x).
//   - (x) collapses to a small premium lightbulb pinned where the old Tara
//     launcher sat. First several closes pulse once + a "Your lessons live
//     here" bubble (tw_lesson_close_count). Lightbulb RESUMES exactly where left
//     off, never restarts. Respects tw_onboard_dismissed (stays closed, but the
//     lightbulb still reopens on demand).
//   - EXISTING-USER INVITE (Gating v2): a logged-in user who is NOT enrolled and
//     NOT dismissed gets, ONCE ever (tw_lesson_inviteseen), a lightbulb pulse +
//     small opt-in bubble instead of any auto-open - "Start the tour" enrolls
//     and opens Day 1; "No thanks" just marks the invite seen (lightbulb stays
//     quiet and available). Clicking the lightbulb itself while unenrolled has
//     the same effect as "Start the tour" (see reopenBox).
//   - MUTE / UNMUTE (Gating v2): a footer link in the open panel - "Stop daily
//     pop-ups" calls setTipsDismissed() and closes with a one-time "Muted..."
//     confirmation bubble; "Turn daily pop-ups back on" (shown instead, while
//     dismissed) calls clearTipsDismissed() (and enrollNow() if not already
//     enrolled). Muting never hides the lightbulb or wipes progress.
//   - TRIAL CLOSE SCREEN (Onboarding Lessons v2, 2026-07-04): rides the TRIAL
//     clock, not the lesson counter. screensAt() appends TRIAL_CLOSE_SCREEN
//     (onboardingLessons.js) to whichever day the user's LIVE progress is on
//     whenever getTrialState().onTrial && daysRemaining <= 1 - so a late
//     starter whose trial ends on lesson Day 5 gets it there, not only on Day
//     7. Built via .concat() each render (never mutates LESSONS), so it never
//     doubles up and never shows for a payer or a lapsed-to-Explorer user
//     (onTrial is false in both cases). Its `cta` field renders a button;
//     clicking it dispatches window CustomEvent 'tw-open-conversion-card'
//     (App.js shows the existing TrialConversionCard) and closes the box with
//     standard bookkeeping (no reopen-hint bubble - see handleCtaClick).
//
// Props:
//   UITheme  'dark' | 'light' (we render premium-dark either way)
//   rdd      { isMobile, isTablet } responsive descriptor
//
// No app-action props: the "Try It Now" pointer is text telling the user what
// to click. The box drives nothing in the app.
//
// All persisted keys are PER-USER: lsGet/lsSet (Common.js) prefix the key with
// window.current_user_id, the same scoping onboarding.js uses for its cookies.
// Keys: tw_lesson_lastopened (int day), tw_lesson_screen_<day> (0..N),
//        tw_lesson_pos ({x,y}), tw_lesson_close_count (int), tw_lesson_inviteseen
//        (bool, one-time existing-user invite). Plus the per-user cookie
//        tw_lesson_day (last-viewed day, owned by onboarding.js) so a reopen
//        lands on the day the user was last reading, and tw_lesson_enrolled /
//        tw_onboard_dismissed (both owned by onboarding.js - see Gating v2).
// =====================================================================

// ---- live PE label (matches OppTable.js:72-86 exactly) ---------------
// 2026 % 4 = 2 -> "PE+2". Computed live so the Day-5 lesson never drifts
// from the actual button the user is told to click.
const livePELabel = () => {
  try {
    switch (new Date().getFullYear() % 4) {
      case 0: return 'PE';
      case 1: return 'PE+1';
      case 2: return 'PE+2';
      case 3: return 'PE+3';
      default: return 'PE+2';
    }
  } catch (e) { return 'PE+2'; }
};

// ---- live {year} / {cyclePhrase} ("Onboarding Lessons v2") -----------
// Computed beside the {peLabel} switch above, off the same (year % 4), so
// Day 5 is fully year-agnostic - it reads correctly in 2027, 2028, forever.
// Article is included in the phrase so "a/an" is always right.
const liveYear = () => {
  try { return String(new Date().getFullYear()); } catch (e) { return String(new Date().getFullYear()); }
};
const liveCyclePhrase = () => {
  try {
    switch (new Date().getFullYear() % 4) {
      case 0: return 'an election year';
      case 1: return 'a post-election year';
      case 2: return 'a midterm year';
      case 3: return 'a pre-election year';
      default: return 'a midterm year';
    }
  } catch (e) { return 'a midterm year'; }
};

// Fill the {peLabel}/{year}/{cyclePhrase} tokens in any lesson string with their live values.
const fillTokens = (s) => (typeof s === 'string'
  ? s.split('{peLabel}').join(livePELabel())
      .split('{year}').join(liveYear())
      .split('{cyclePhrase}').join(liveCyclePhrase())
  : s);

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const LessonBox = (props) => {
  const { UITheme, rdd, hidden, onHighlightChatbot, onOpenChatbot, dateRangeLabel } = props;
  const tc = themeColors(UITheme) || {};
  const isMobile = !!(rdd && rdd.isMobile && !rdd.isTablet);

  // {dateRange} renders the LIVE date-range label of the loaded pattern (passed from
  // App.js), so the Day-3 lesson never shows a stale hardcoded example. fill() does
  // every token; use it for any lesson copy carrying {dateRange}/{statsIntro}/{statsOpen}/{statsAt}.
  const dateRangeText = dateRangeLabel || 'the line above the chart';

  // The Wave Stats table is one view of a swipeable chart carousel - and the WAY you
  // reach it differs by device, so these tokens render the right instruction per layout:
  //  - Desktop: bar chart on top, a 3-dot carousel below it (Trend Chart / Wave Stats /
  //    Price Chart); the MIDDLE dot is Wave Stats (it goes red when active).
  //  - Mobile portrait: bar chart and Wave Stats are both SLIDES of one carousel, so you
  //    SWIPE LEFT to the Wave Stats view (there is no "below the chart").
  const statsIntro = isMobile
    ? 'The chart panel swipes between views - swipe left until the stats table comes up (Wave Stats).'
    : 'Now look just above the bottom chart, on its right side - three small dots, two white and one red. The red one is the view you\'re on now. Click the middle dot - that opens the Wave Stats table.';
  const statsOpen = isMobile
    ? 'Swipe left to the stats table - the Wave Stats view'
    : "Click the middle of the three dots above the bottom chart, on its right side - that's the Wave Stats table";
  const statsAt = isMobile
    ? 'in the stats panel (swipe left to it)'
    : 'behind the middle dot above the bottom chart';

  const fill = (s) => (typeof s === 'string'
    ? fillTokens(s)
        .split('{dateRange}').join(dateRangeText)
        .split('{statsIntro}').join(statsIntro)
        .split('{statsOpen}').join(statsOpen)
        .split('{statsAt}').join(statsAt)
    : s);

  // ---- the DEVICE deck: mobile drops desktop-only days (the Tara/chatbot
  // lesson, since the chatbot icon is desktop-only). Days index by POSITION. ---
  const deck = isMobile ? LESSONS.filter((d) => !d.desktopOnly) : LESSONS;
  const lessonAt = (n) => deck[clamp(parseInt(n, 10) || 1, 1, deck.length) - 1] || {};

  // ---- live day (1..N), clamped + bounds-safe -------------------------
  const totalDays = deck.length || 7;
  const liveDay = clamp(getOnboardingDay() || 1, 1, totalDays);

  // ---- TRIAL CLOSE SCREEN gate ("Onboarding Lessons v2", 2026-07-04) ---
  // True only for an ACTIVE trial with <= 1 day left - false for a payer (no
  // trial-end at all) and false for a lapsed-to-Explorer user (trial already
  // over), because getTrialState().onTrial is false in both those cases. This
  // is what keeps a paying subscriber from ever seeing the sale screen.
  const trialClosing = (() => {
    try {
      const ts = getTrialState();
      return !!(ts && ts.onTrial && typeof ts.daysRemaining === 'number' && ts.daysRemaining <= 1);
    } catch (e) { return false; }
  })();

  // screensAt() appends TRIAL_CLOSE_SCREEN to whichever day the user's LIVE
  // progress (liveDay) is on - a late starter whose trial ends on lesson Day 5
  // gets it appended there, not hardcoded to Day 7. Built fresh via .concat()
  // (never mutates the shared LESSONS/day.screens array), so it is never
  // appended twice and never lingers once trialClosing goes false (converted,
  // lapsed, or not a trial user at all).
  const screensAt = (n) => {
    const L = lessonAt(n);
    const base = Array.isArray(L.screens) ? L.screens : [];
    if (trialClosing && (parseInt(n, 10) || 0) === liveDay) return base.concat([TRIAL_CLOSE_SCREEN]);
    return base;
  };

  // ---- core view state ------------------------------------------------
  // open      box visible vs collapsed-to-lightbulb.
  // viewDay   the day currently being read (== liveDay unless in review mode).
  // screen    0..2 within viewDay.
  // mode      'today' | 'review' - review shows the "Reviewing Day N" chrome.
  // whereTone 'new' | 'resume' | 'caught' - drives the "where am I" line on open.
  const [open, setOpen] = useState(false);
  const [viewDay, setViewDay] = useState(liveDay);
  const [screen, setScreen] = useState(0);
  const [mode, setMode] = useState('today');
  const [whereTone, setWhereTone] = useState('resume');
  const [showLessons, setShowLessons] = useState(false); // the "Lessons" list overlay
  const [confirmDone, setConfirmDone] = useState(false); // the one-line "still here" confirm
  const [transition, setTransition] = useState(null); // between-days card {from,to}
  const [pulse, setPulse] = useState(false); // first-close lightbulb pulse
  const [showHint, setShowHint] = useState(false); // one-time "Your lessons live here" bubble
  const [showInvite, setShowInvite] = useState(false); // one-time existing-user opt-in invite
  const [showMuteMsg, setShowMuteMsg] = useState(false); // one-time "Muted" confirmation bubble
  const [dismissed, setDismissed] = useState(() => isTipsDismissed()); // mirrors tw_onboard_dismissed for reactive mute/unmute UI

  // ---- drag position --------------------------------------------------
  // null => centered (default). {x,y} => persisted top-left, viewport-clamped.
  const [pos, setPos] = useState(null);
  const boxRef = useRef(null);
  const dragRef = useRef({ active: false, dx: 0, dy: 0, moved: false });

  // ---- setTimeout bookkeeping (cleared on unmount) --------------------
  // The done-for-today collapse + the first-close pulse/hint use timers; if the
  // box unmounts mid-delay we must not setState on an unmounted component.
  const timersRef = useRef([]);
  const after = useCallback((fn, ms) => { const t = setTimeout(fn, ms); timersRef.current.push(t); return t; }, []);
  useEffect(() => () => { timersRef.current.forEach((t) => clearTimeout(t)); }, []);

  // Box footprint - never covers the whole screen.
  const BOX_W = isMobile ? Math.min(340, Math.round((typeof window !== 'undefined' ? window.innerWidth : 360) * 0.92)) : 360;

  // ---- per-day saved-screen helpers (bounds-safe) ---------------------
  // Screen counts vary per day (most are 3; Day 1 has 4), so clamp to the day's
  // ACTUAL last-screen index, never a hardcoded 2.
  const screenKey = (d) => `tw_lesson_screen_${d}`;
  const maxScreen = (d) => Math.max(0, (screensAt(d).length || 3) - 1);
  const readSavedScreen = (d) => {
    const raw = lsGet(screenKey(d), 0);
    const n = parseInt(raw, 10);
    if (isNaN(n)) return 0;
    return clamp(n, 0, maxScreen(d));
  };
  const writeSavedScreen = (d, s) => { lsSet(screenKey(d), clamp(s, 0, maxScreen(d))); };

  // ---- resume: restore to where the user left off (never restart) -----
  // Used by mount, by the lightbulb reopen, and by "Back to Today".
  const resumeToToday = useCallback(() => {
    const d = clamp(getOnboardingDay() || 1, 1, totalDays);
    const saved = readSavedScreen(d);
    setMode('today');
    setShowLessons(false);
    setConfirmDone(false);
    setViewDay(d);
    setScreen(saved);
    setWhereTone(saved >= 2 ? 'caught' : 'resume');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalDays]);

  // ---- restore: reopen on the day the user was last reading (tw_lesson_day
  // cookie), NOT forced back to today. Falls back to today when the cookie is
  // unset. Screen comes from that day's saved screen. -------------------------
  const restoreSavedDay = useCallback(() => {
    const live = clamp(getOnboardingDay() || 1, 1, totalDays);
    const d = clamp(getLessonDay() || live, 1, totalDays);
    const saved = readSavedScreen(d);
    setMode(d === live ? 'today' : 'review');
    setShowLessons(false);
    setConfirmDone(false);
    setTransition(null);
    setViewDay(d);
    setScreen(saved);
    setWhereTone(d === live ? (saved >= 2 ? 'caught' : 'resume') : 'resume');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totalDays]);

  // ---- mount: load persisted position + decide auto-open --------------
  useEffect(() => {
    // Load persisted drag position with off-screen recovery (snap-back safety).
    try {
      const saved = lsGet('tw_lesson_pos', null);
      if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
        if (typeof window !== 'undefined') {
          const maxX = window.innerWidth - 80;   // keep at least a sliver grabbable
          const maxY = window.innerHeight - 60;
          if (saved.x < -20 || saved.y < -20 || saved.x > maxX || saved.y > maxY) {
            // Parked off-screen / weird -> recover to centered.
            setPos(null);
          } else {
            setPos(saved);
          }
        } else {
          setPos(saved);
        }
      }
    } catch (e) { /* default centered */ }

    // Gating v2: enrollment is the master switch for ALL auto-open behavior.
    // Auto-enroll a GENUINE new user right here, at decision time - App.js also
    // does this on login, but its effect runs AFTER this child's mount effect
    // (React runs child effects first), so relying on it alone would make every
    // new user's first load fall through to the invite instead of the Day-1
    // welcome. Eligibility reads window.current_user_created_at, which the
    // server injects into the page head, so it is available synchronously.
    if (!isEnrolled() && isAutoArcEligible() && !isTipsDismissed()) {
      enrollNow();
    }
    // Still unenrolled => existing user (or unknown created_at - fails safe).
    // Never auto-open - instead, once ever, offer a small non-blocking invite
    // to start the tour (logged-in users only). This is also what makes the
    // retroactive cleanup work: users wrongly enrolled before this fix have a
    // stale tw_onboard_started_at but no tw_lesson_enrolled, so they land here.
    if (!isEnrolled()) {
      setOpen(false);
      const uid = (typeof window !== 'undefined' && window.current_user_id) ? String(window.current_user_id) : '';
      if (uid && !isTipsDismissed() && lsGet('tw_lesson_inviteseen', null) !== '1') {
        lsSet('tw_lesson_inviteseen', '1'); // one-time: mark seen the moment it is shown
        setShowInvite(true);
        setPulse(true);
        try { window.dispatchEvent(new CustomEvent('tw-lessonbox-invite')); } catch (e) { /* noop */ }
        after(() => setPulse(false), 2600);
        after(() => setShowInvite(false), 9000);
      }
      return;
    }

    const d = clamp(getOnboardingDay() || 1, 1, totalDays);
    const lastOpened = parseInt(lsGet('tw_lesson_lastopened', 0), 10) || 0;

    // Respect the global Skip-tips mute: stay collapsed, but the lightbulb
    // still reopens on demand. Do NOT auto-open.
    if (isTipsDismissed()) {
      restoreSavedDay();
      setOpen(false);
      return;
    }

    if (d > lastOpened) {
      // First open of a NEW calendar day -> auto-open to screen 1, fresh, and
      // point the last-viewed-day cookie at the new day.
      lsSet('tw_lesson_lastopened', d);
      writeSavedScreen(d, 0); // a new day always starts fresh at screen 1
      setLessonDay(d);
      setViewDay(d);
      setScreen(0);
      setMode('today');
      setWhereTone('new');
      setOpen(true);
      logEvent('persona', { stage: 'lesson_autoopen', day: d });
    } else {
      // Already auto-opened today (or earlier) -> stay collapsed under the
      // lightbulb; reopening resumes the last-viewed day (tw_lesson_day cookie).
      restoreSavedDay();
      setOpen(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- persist the current screen whenever it changes in TODAY mode ---
  // (review mode never writes progress for other days).
  useEffect(() => {
    if (mode === 'today') writeSavedScreen(viewDay, screen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [screen, viewDay, mode]);

  // ---- auto-load the first opportunity if a {dateRange} screen is open with nothing
  // loaded yet, so the live date-range example points at a real pattern. App.js feeds
  // the live label; OppTable handles the load event. Fires only when nothing is loaded.
  // FIRE ONCE per load cycle: the deps below (open, viewDay, screen) settle in sequence on
  // a page refresh, so without this guard the event dispatched on EACH settle -> OppTable
  // auto-clicked row 0 multiple times -> the opp table "flashed 3 times before it stopped".
  // The guard resets whenever a pattern IS loaded (dateRangeLabel set) or the box closes,
  // so a later genuine "nothing loaded on a {dateRange} screen" can still re-trigger it.
  const loadFirstFiredRef = useRef(false);
  useEffect(() => {
    if (!open || dateRangeLabel) { loadFirstFiredRef.current = false; return; }
    if (loadFirstFiredRef.current) return;
    const sc = screensAt(viewDay)[screen];
    if (!sc) return;
    const txt = [sc.title, sc.lead].concat(Array.isArray(sc.bullets) ? sc.bullets : []).join(' ');
    if (txt.indexOf('{dateRange}') !== -1) {
      loadFirstFiredRef.current = true;
      try { window.dispatchEvent(new CustomEvent('tw-lessonbox-load-first')); } catch (e) { /* noop */ }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, viewDay, screen, dateRangeLabel]);

  // ---- drag handlers (header only) ------------------------------------
  const onDragStart = (clientX, clientY) => {
    const rect = boxRef.current ? boxRef.current.getBoundingClientRect() : { left: 0, top: 0 };
    dragRef.current = { active: true, dx: clientX - rect.left, dy: clientY - rect.top, moved: false };
  };
  const onDragMove = useCallback((clientX, clientY) => {
    if (!dragRef.current.active) return;
    dragRef.current.moved = true;
    const w = boxRef.current ? boxRef.current.offsetWidth : BOX_W;
    const h = boxRef.current ? boxRef.current.offsetHeight : 200;
    const nx = clamp(clientX - dragRef.current.dx, 4, (typeof window !== 'undefined' ? window.innerWidth : 1200) - w - 4);
    const ny = clamp(clientY - dragRef.current.dy, 4, (typeof window !== 'undefined' ? window.innerHeight : 800) - h - 4);
    setPos({ x: nx, y: ny });
  }, [BOX_W]);
  const onDragEnd = useCallback(() => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    setPos((p) => { if (p) lsSet('tw_lesson_pos', p); return p; });
  }, []);

  useEffect(() => {
    const mm = (e) => onDragMove(e.clientX, e.clientY);
    const mu = () => onDragEnd();
    const tm = (e) => { if (e.touches && e.touches[0]) onDragMove(e.touches[0].clientX, e.touches[0].clientY); };
    const tu = () => onDragEnd();
    window.addEventListener('mousemove', mm);
    window.addEventListener('mouseup', mu);
    window.addEventListener('touchmove', tm, { passive: false });
    window.addEventListener('touchend', tu);
    return () => {
      window.removeEventListener('mousemove', mm);
      window.removeEventListener('mouseup', mu);
      window.removeEventListener('touchmove', tm);
      window.removeEventListener('touchend', tu);
    };
  }, [onDragMove, onDragEnd]);

  const snapToCenter = () => { setPos(null); lsSet('tw_lesson_pos', null); };

  // ---- close / reopen -------------------------------------------------
  // Shared bookkeeping for any way the panel closes - remember the viewed day,
  // clear the transient overlay state, collapse to the lightbulb. Split out of
  // closeBox() so muteTips() can close WITHOUT also firing the standard
  // reopen-hint bubble (it shows its own "Muted" confirmation instead).
  const closeBoxCore = () => {
    setLessonDay(viewDay); // remember the day so reopening lands back here
    setShowLessons(false);
    setConfirmDone(false);
    setTransition(null);
    setOpen(false);
  };

  const closeBox = () => {
    closeBoxCore();
    // First several closes: pulse the lightbulb + show the "here's the reopen
    // lightbulb" cue (toolbar pulse + anchored callout) - after that the user
    // knows where it is. The permanent toolbar bulb (with its hover tooltip)
    // stays as the reopen affordance forever.
    const closes = (parseInt(lsGet('tw_lesson_close_count', 0), 10) || 0) + 1;
    lsSet('tw_lesson_close_count', closes);
    if (closes <= 5) {
      try { window.dispatchEvent(new CustomEvent('tw-lessonbox-closed', { detail: { closeCount: closes } })); } catch (e) { /* noop */ }
      setPulse(true);
      setShowHint(true);
      after(() => setPulse(false), 2600);
      after(() => setShowHint(false), 7000);
    }
  };

  const reopenBox = () => {
    setShowHint(false);
    setShowInvite(false);
    setPulse(false);
    if (!isEnrolled()) {
      // Explicit intent overrides the age-based auto-enroll window: clicking the
      // lightbulb while unenrolled, accepting the invite's "Start the tour", or
      // the SubscriptionWelcomeModal handoff all land here. Enroll now and open
      // fresh at Day 1, screen 1.
      enrollNow();
      lsSet('tw_lesson_lastopened', 1);
      writeSavedScreen(1, 0);
      setLessonDay(1);
      setMode('today');
      setShowLessons(false);
      setConfirmDone(false);
      setTransition(null);
      setViewDay(1);
      setScreen(0);
      setWhereTone('new');
      setOpen(true);
      logEvent('persona', { stage: 'lesson_invite_start', day: 1 });
      return;
    }
    // Reopen on the day they were last reading (tw_lesson_day cookie), never
    // forced back to today, never restarted.
    restoreSavedDay();
    setOpen(true);
    const d = clamp(getLessonDay() || getOnboardingDay() || 1, 1, totalDays);
    logEvent('persona', { stage: 'lesson_reopen', day: d });
  };

  // ---- one-time existing-user invite: "No thanks" ----------------------
  // tw_lesson_inviteseen is already set at show-time (mount effect), so this
  // just dismisses the UI - no further persistence needed. Does NOT mute
  // (tw_onboard_dismissed): the lightbulb simply stays quiet and available.
  const dismissInvite = () => {
    setShowInvite(false);
    setPulse(false);
  };

  // ---- mute / unmute daily pop-ups (the footer control in the open panel) ----
  const muteTips = () => {
    setTipsDismissed();
    setDismissed(true);
    closeBoxCore(); // close WITHOUT the standard reopen-hint bubble
    setShowMuteMsg(true);
    setPulse(true);
    try { window.dispatchEvent(new CustomEvent('tw-lessonbox-muted')); } catch (e) { /* noop */ }
    after(() => setPulse(false), 2600);
    after(() => setShowMuteMsg(false), 7000);
    logEvent('persona', { stage: 'lesson_muted', day: viewDay });
  };

  const unmuteTips = () => {
    clearTipsDismissed();
    setDismissed(false);
    if (!isEnrolled()) enrollNow(); // resuming pop-ups for a never-enrolled user opts them in
    logEvent('persona', { stage: 'lesson_unmuted', day: viewDay });
  };

  // ---- CTA screens ("Onboarding Lessons v2") - a screen with a `cta` field
  // (currently only TRIAL_CLOSE_SCREEN) renders a prominent button below its
  // bullets. 'conversion-card' hands off to the existing usage-measured
  // TrialConversionCard (App.js owns the actual dialog + listens for this
  // event); the box then closes with standard bookkeeping - no reopen-hint
  // bubble, same as muteTips() - since the user is being handed somewhere else.
  const handleCtaClick = (cta) => {
    if (!cta) return;
    logEvent('persona', { stage: 'trial_close_cta' });
    if (cta.action === 'conversion-card') {
      try { window.dispatchEvent(new CustomEvent('tw-open-conversion-card')); } catch (e) { /* noop */ }
    }
    closeBoxCore();
  };

  // ---- reopen from the toolbar lightbulb (desktop docks the bulb beside the
  // tooltip icon and dispatches this window event instead of a bottom bulb) ----
  const reopenRef = useRef(reopenBox);
  reopenRef.current = reopenBox;
  useEffect(() => {
    const h = () => reopenRef.current();
    window.addEventListener('tw-lessonbox-open', h);
    return () => window.removeEventListener('tw-lessonbox-open', h);
  }, []);

  // ---- spotlight the REAL chatbot icon while on the Tara lesson (desktop only).
  // Fires only on the change so it never fights the app's own blink triggers. ----
  const chatHiRef = useRef(false);
  useEffect(() => {
    const L = lessonAt(viewDay);
    const want = open && !isMobile && !!(L && L.chatbotLesson);
    if (want !== chatHiRef.current) {
      chatHiRef.current = want;
      if (typeof onHighlightChatbot === 'function') onHighlightChatbot(want);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, viewDay, isMobile]);
  useEffect(() => () => {
    if (chatHiRef.current && typeof onHighlightChatbot === 'function') onHighlightChatbot(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- paging ---------------------------------------------------------
  const screens = screensAt(viewDay);
  const screenCount = screens.length || 3;
  const onScreen3 = screen >= screenCount - 1;

  // Back pages within a day. Next pages within a day; the last screen's "Done"
  // shows the between-days card and continues into the next day (goToNextDay).
  const goBack = () => {
    if (screen > 0) setScreen(screen - 1);
  };
  const goNext = () => {
    if (!onScreen3) { setScreen(screen + 1); return; }
    if (viewDay < totalDays) {
      // More days to come -> mark this day done and show the "End of Day N /
      // Beginning of Day N+1" card; the user continues from there.
      writeSavedScreen(viewDay, screenCount - 1);
      logEvent('persona', { stage: 'lesson_day_done', day: viewDay });
      setTransition({ from: viewDay, to: viewDay + 1 });
      return;
    }
    // Last screen of the FINAL day -> finished: confirm, then collapse.
    writeSavedScreen(viewDay, screenCount - 1);
    setConfirmDone(true);
    logEvent('persona', { stage: 'lesson_arc_complete', day: viewDay });
    after(() => { closeBox(); }, 2600);
  };

  // Continue from the between-days card into the next day's first screen.
  const goToNextDay = () => {
    const next = clamp(viewDay + 1, 1, totalDays);
    setTransition(null);
    setShowLessons(false);
    setConfirmDone(false);
    setMode(next === liveDay ? 'today' : 'review');
    setViewDay(next);
    setScreen(0);
    setWhereTone('resume');
    setLessonDay(next);
    logEvent('persona', { stage: 'lesson_advance', day: next });
  };

  // ---- header links ---------------------------------------------------
  const startDayOver = () => {
    writeSavedScreen(liveDay, 0);
    setMode('today');
    setShowLessons(false);
    setConfirmDone(false);
    setViewDay(liveDay);
    setScreen(0);
    setWhereTone('resume');
  };

  const openReview = (d) => {
    if (d < 1 || d > totalDays) return; // any day in the deck is browsable
    setMode(d === liveDay ? 'today' : 'review');
    setShowLessons(false);
    setConfirmDone(false);
    setViewDay(d);
    setScreen(0);
    if (d === liveDay) setWhereTone(readSavedScreen(d) >= 2 ? 'caught' : 'resume');
  };

  // =====================================================================
  // RENDER
  // =====================================================================

  // A dialog (Terms, upsell, etc.) is up - stay mounted (keep all state) but render
  // nothing, so the lesson box never stacks over a modal. It reappears, in whatever
  // open/collapsed state it was, the moment the dialog closes.
  if (hidden) return null;

  // ---- palette (premium dark violet, independent of light theme) ------
  // "Instrument - quant console" look: dark layered surfaces, violet bloom.
  const C = {
    panel: '#15111E',
    panelGrad: 'linear-gradient(180deg,#1E1830 0%,#15111E 60%,#130F1B 100%)',
    plateGrad: 'linear-gradient(180deg,#1F1A2C,#1A1626)',
    well: '#120E1A',
    text: '#F2EFF8',
    textDim: '#B8B2C8',
    textLabel: '#8A8399',
    textFaint: '#635D74',
    accentText: '#C9B8FF',
    violet: 'rgb(167,139,250)',
    violetBright: '#C4B2FF',
    violetDeep: '#7C5CE0',
    cyan: '#6EE7F0',
    ink: '#14101F',
    edge: 'rgba(167,139,250,0.22)',
    hair: 'rgba(255,255,255,0.06)',
    divider: 'rgba(167,139,250,0.12)',
    grid: 'rgba(167,139,250,0.05)',
    chipBg: 'rgba(167,139,250,0.12)',
    lockBg: 'rgba(167,139,250,0.06)',
    border: tc.border || 'rgb(50, 47, 62)',
  };
  const MONO = '"SF Mono", ui-monospace, "JetBrains Mono", "Roboto Mono", Menlo, Consolas, monospace';

  const keyframes =
    '@keyframes twLbRise{from{opacity:0;transform:translateY(12px) scale(.985)}to{opacity:1;transform:none}}' +
    '@keyframes twLbFade{from{opacity:0}to{opacity:1}}' +
    '@keyframes twLbPulse{0%{box-shadow:0 0 0 0 rgba(167,139,250,0.55)}70%{box-shadow:0 0 0 16px rgba(167,139,250,0)}100%{box-shadow:0 0 0 0 rgba(167,139,250,0)}}' +
    '@keyframes twLbLed{0%,100%{opacity:.45}50%{opacity:1}}' +
    '@keyframes twLbBreathe{0%,100%{box-shadow:0 0 20px rgba(167,139,250,.4),0 10px 30px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.25)}50%{box-shadow:0 0 30px rgba(167,139,250,.6),0 10px 30px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.25)}}' +
    '.tw-lb-link{background:none;border:none;color:' + C.textLabel + ';font-family:' + MONO + ';font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;cursor:pointer;padding:0}' +
    '.tw-lb-link:hover{color:' + C.text + '}' +
    '.tw-lb-primary:hover{filter:brightness(1.07);transform:translateY(-1px)}' +
    '.tw-lb-row:hover{background:rgba(167,139,250,0.10)}' +
    '.tw-lb-x:hover{background:rgba(167,139,250,0.32)}' +
    '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}';

  // ---------------- collapsed: the lightbulb -----------------
  // Pinned where the old Tara launcher sat (bottom-right). The days-remaining
  // pill sits at bottom:86px/right:18px, so the bulb sits just below it.
  if (!open) {
    // Desktop reopens from the toolbar lightbulb (docked beside the tooltip icon),
    // so the box renders nothing here - it never covers the bottom charts. Mobile
    // keeps a bottom-anchored bulb (no toolbar on mobile).
    // Desktop: the reopen lightbulb AND its anchored callout live in the toolbar
    // (DesktopLayout positions the callout just below the real bulb on close, so it never
    // covers it). The box renders nothing here. Mobile keeps a bottom-anchored bulb.
    if (!isMobile) return null;
    return (
      <>
        <style>{keyframes}</style>
        <div style={{ position: 'fixed', bottom: '78px', right: '14px', zIndex: 9100, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          {showInvite && (
            <div style={{
              maxWidth: '220px', background: C.plateGrad, color: C.text, border: '1px solid ' + C.edge,
              borderRadius: '10px', padding: '11px 13px', fontSize: '12.5px', lineHeight: 1.4,
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)', animation: 'twLbFade 240ms ease-out',
            }}>
              <div style={{ color: C.accentText, fontWeight: 700, marginBottom: '3px' }}>New: 7 Quick Daily Lessons</div>
              <div style={{ marginBottom: '9px' }}>Learn to read seasonal patterns in a few minutes a day. Want the tour?</div>
              <div style={{ display: 'flex', gap: '14px' }}>
                <button type="button" className="tw-lb-link" style={{ color: C.accentText }} onClick={reopenBox}>Start the tour</button>
                <button type="button" className="tw-lb-link" onClick={dismissInvite}>No thanks</button>
              </div>
            </div>
          )}
          {showMuteMsg && (
            <div style={{
              maxWidth: '200px', background: C.plateGrad, color: C.text, border: '1px solid ' + C.edge,
              borderRadius: '10px', padding: '9px 12px', fontSize: '12.5px', lineHeight: 1.4,
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)', animation: 'twLbFade 240ms ease-out',
            }}>
              Muted. Your lessons stay right here whenever you want them.
            </div>
          )}
          {showHint && !showInvite && !showMuteMsg && (
            <div style={{
              maxWidth: '190px', background: C.plateGrad, color: C.text, border: '1px solid ' + C.edge,
              borderRadius: '10px', padding: '9px 12px', fontSize: '12.5px', lineHeight: 1.4,
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)', animation: 'twLbFade 240ms ease-out',
            }}>
              Your lessons live here. Tap the lightbulb any time.
            </div>
          )}
          <button
            type="button"
            onClick={reopenBox}
            title="Open your lessons"
            aria-label="Open your lessons"
            style={{
              width: '46px', height: '46px', borderRadius: '50%', cursor: 'pointer',
              border: '1px solid ' + C.edge,
              background: 'radial-gradient(circle at 35% 30%, ' + C.violetBright + ', ' + C.violetDeep + ')',
              color: '#1a1226', fontSize: '22px', lineHeight: '46px', textAlign: 'center',
              boxShadow: '0 0 24px rgba(167,139,250,0.5),0 10px 30px rgba(0,0,0,0.55),inset 0 1px 0 rgba(255,255,255,0.25)',
              animation: pulse ? 'twLbPulse 1.6s ease-out 1' : 'twLbBreathe 3.2s ease-in-out infinite',
            }}
          >
            <span role="img" aria-hidden="true">&#128161;</span>
          </button>
        </div>
      </>
    );
  }

  // ---------------- expanded: the panel -----------------
  const lesson = lessonAt(viewDay);
  const cur = screens[clamp(screen, 0, screenCount - 1)] || { title: '', body: '', pointer: '' };
  const dayTheme = lesson.theme || '';

  // "where am I" line.
  let whereLine;
  if (mode === 'review') {
    whereLine = (viewDay > liveDay ? 'Reading ahead - Day ' : 'Reviewing Day ') + viewDay + ' of ' + totalDays;
  } else if (whereTone === 'new') {
    whereLine = 'Day ' + viewDay + ' of ' + totalDays + ' - new lesson today';
  } else if (whereTone === 'caught') {
    whereLine = viewDay >= totalDays
      ? "Day " + viewDay + " - you're all caught up"
      : "Day " + viewDay + " - all caught up. Day " + (viewDay + 1) + ' is ready tomorrow';
  } else {
    whereLine = 'Day ' + viewDay + ' // picking up where you left off';
  }

  // Day 1 / Screen 1 gets the WELCOME hero treatment (only there).
  const isWelcome = (mode === 'today' && viewDay === 1 && screen === 0);

  const containerStyle = pos
    ? { position: 'fixed', left: pos.x + 'px', top: pos.y + 'px', zIndex: 9100 }
    : { position: 'fixed', left: '50%', top: isMobile ? 'auto' : '50%', bottom: isMobile ? '78px' : 'auto', transform: isMobile ? 'translateX(-50%)' : 'translate(-50%,-50%)', zIndex: 9100 };

  const panelStyle = {
    width: BOX_W + 'px', maxWidth: '94vw', maxHeight: '82vh', boxSizing: 'border-box',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
    position: 'relative',
    background: C.panelGrad, color: C.text,
    border: '1px solid ' + C.edge, borderRadius: '16px',
    boxShadow: '0 0 0 1px rgba(167,139,250,0.10),0 28px 80px -12px rgba(124,92,224,0.45),0 14px 40px rgba(0,0,0,0.70),inset 0 1px 0 rgba(255,255,255,0.07)',
    animation: 'twLbRise 320ms cubic-bezier(0.16,0.84,0.44,1)',
    fontFamily: '"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif',
  };

  return (
    <div ref={boxRef} style={containerStyle}>
      <style>{keyframes}</style>
      <div style={panelStyle}>

        {/* mesh overlay: violet/cyan corner blooms (above background, below content) */}
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', borderRadius: '16px', mixBlendMode: 'screen', opacity: 0.9, background: 'radial-gradient(120% 80% at 15% 0%, rgba(167,139,250,0.14), transparent 55%), radial-gradient(100% 70% at 100% 0%, rgba(110,231,240,0.06), transparent 50%)' }} />

        <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

        {/* ---------- header (drag handle) ---------- */}
        <div
          onMouseDown={(e) => { if (e.button === 0) onDragStart(e.clientX, e.clientY); }}
          onTouchStart={(e) => { if (e.touches && e.touches[0]) onDragStart(e.touches[0].clientX, e.touches[0].clientY); }}
          style={{
            display: 'flex', alignItems: 'center', gap: '8px', cursor: 'grab',
            background: C.plateGrad,
            borderBottom: '1px solid ' + C.divider, padding: '11px 14px',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)',
            userSelect: 'none',
          }}
        >
          <span style={{
            flexShrink: 0, width: '22px', height: '22px', borderRadius: '6px',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: C.chipBg, border: '1px solid ' + C.edge, fontSize: '13px',
            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.10)',
          }} role="img" aria-hidden="true">&#128161;</span>
          <span style={{ fontFamily: MONO, fontSize: '11px', fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase', flex: 1, color: C.textDim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {mode === 'review'
              ? (viewDay > liveDay ? 'DAY ' + viewDay + ' // AHEAD' : 'REVIEWING DAY ' + viewDay)
              : 'DAY ' + viewDay + ' // LESSON'}
          </span>
          <button
            className="tw-lb-link"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => { setTransition(null); setShowLessons((v) => !v); }}
            title="All your lessons"
          >Lessons</button>
          <button
            type="button"
            className="tw-lb-x"
            onMouseDown={(e) => e.stopPropagation()}
            onTouchStart={(e) => e.stopPropagation()}
            onClick={closeBox}
            title="Close - your lessons stay under the lightbulb"
            aria-label="Close lessons"
            style={{
              flexShrink: 0, width: '26px', height: '26px', borderRadius: '7px',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(167,139,250,0.14)', border: '1px solid ' + C.edge,
              color: C.text, fontSize: '18px', lineHeight: 1, cursor: 'pointer', padding: 0,
            }}
          >&times;</button>
        </div>

        {/* ---------- between-days transition card ---------- */}
        {transition ? (
          <div style={{ padding: '34px 18px 28px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '12px', animation: 'twLbFade 240ms ease-out' }}>
            <div style={{ fontFamily: MONO, fontSize: '10px', letterSpacing: '.16em', textTransform: 'uppercase', color: C.textLabel }}>
              {'End of Day ' + transition.from}
            </div>
            <div style={{ width: '1px', height: '26px', background: 'linear-gradient(180deg,' + C.violet + ',rgba(167,139,250,0))' }} />
            <div style={{ fontFamily: MONO, fontSize: '10px', letterSpacing: '.16em', textTransform: 'uppercase', color: C.accentText }}>
              {'Beginning of Day ' + transition.to}
            </div>
            <h3 style={{ margin: '4px 0 2px', fontSize: '18px', fontWeight: 700, letterSpacing: '-0.012em', lineHeight: 1.25, color: C.text }}>
              {fillTokens(lessonAt(transition.to).theme || '')}
            </h3>
            <button
              type="button"
              className="tw-lb-primary"
              onClick={goToNextDay}
              style={{ marginTop: '8px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', background: 'linear-gradient(135deg,' + C.violet + ',' + C.violetDeep + ')', color: C.ink, border: 'none', borderRadius: '9px', padding: '10px 18px', fontSize: '14px', fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 12px rgba(124,92,224,0.40)', whiteSpace: 'nowrap' }}
            >
              {'Start Day ' + transition.to} <FaAngleRight />
            </button>
            <button type="button" className="tw-lb-link" onClick={() => setTransition(null)}>Not yet</button>
          </div>
        ) : showLessons ? (
          <div style={{ padding: '12px 14px 14px', overflowY: 'auto' }}>
            <div style={{ fontSize: '12px', color: C.textDim, marginBottom: '10px' }}>
              Your {totalDays}-day path. Tap any day to read it - peek ahead any time.
            </div>
            {deck.map((L, idx) => {
              const d = idx + 1;
              const isCurrent = d === liveDay;
              const isAhead = d > liveDay;
              return (
                <div
                  key={d}
                  className="tw-lb-row"
                  onClick={() => openReview(d)}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '10px',
                    padding: '9px 10px', borderRadius: '9px', marginBottom: '4px',
                    cursor: 'pointer',
                    background: 'transparent',
                    border: '1px solid ' + (isCurrent ? C.edge : 'transparent'),
                    opacity: isAhead ? 0.82 : 1,
                  }}
                >
                  <span style={{
                    flexShrink: 0, width: '22px', height: '22px', borderRadius: '6px',
                    background: C.chipBg,
                    color: isAhead ? C.accentText : C.violet,
                    fontFamily: MONO, fontVariantNumeric: 'tabular-nums',
                    fontSize: '11px', fontWeight: 700, textAlign: 'center', lineHeight: '22px',
                  }}>{d}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '12.5px', fontWeight: 600, color: C.text }}>
                      Day {d}{isCurrent ? ' - today' : (isAhead ? ' - ahead' : '')}
                    </div>
                    <div style={{ fontSize: '11.5px', lineHeight: 1.35, color: C.textFaint, marginTop: '2px' }}>
                      {fillTokens(L.theme || '')}
                    </div>
                  </div>
                </div>
              );
            })}
            <button className="tw-lb-link" style={{ marginTop: '8px' }} onClick={() => setShowLessons(false)}>Back to Today</button>
          </div>
        ) : (
          // ---------- the lesson body ----------
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

            {/* gauge-style progress rail (top) + MONO counter + where-am-I line */}
            <div style={{ padding: '11px 14px 4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '7px' }}>
                {Array.from({ length: screenCount }).map((_, i) => {
                  const isActive = i === screen;
                  const isDone = i < screen;
                  return (
                    <span key={i} style={{
                      width: isActive ? '26px' : '8px', height: '4px', borderRadius: '4px',
                      background: isActive
                        ? 'linear-gradient(90deg,' + C.violet + ',' + C.violetBright + ')'
                        : (isDone ? 'rgba(167,139,250,0.60)' : 'rgba(167,139,250,0.22)'),
                      boxShadow: isActive ? '0 0 8px rgba(167,139,250,0.55)' : 'none',
                      transition: 'width 220ms cubic-bezier(0.16,0.84,0.44,1)',
                    }} />
                  );
                })}
                <span style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: '10px', color: C.textFaint }}>
                  {String(screen + 1).padStart(2, '0') + '/' + String(screenCount).padStart(2, '0')}
                </span>
              </div>
              <div style={{ fontFamily: MONO, fontSize: '11px', letterSpacing: '.02em', color: C.textLabel }}>{whereLine}</div>
            </div>

            {/* scrollable copy - graph-paper grid (suppressed on the welcome hero) */}
            <div key={screen} style={{
              padding: '6px 16px 12px', overflowY: 'auto', animation: 'twLbFade 200ms ease-out',
              backgroundImage: isWelcome ? 'none' : 'linear-gradient(' + C.grid + ' 1px,transparent 1px),linear-gradient(90deg,' + C.grid + ' 1px,transparent 1px)',
              backgroundSize: '22px 22px',
            }}>
              {isWelcome ? (
                // ---- WELCOME HERO (Day 1 / Screen 1 only) ----
                <>
                  {/* (a) seam - the only place cyan appears */}
                  <div style={{ height: '2px', width: '100%', margin: '0 0 14px', borderRadius: '2px', opacity: 0.75, background: 'linear-gradient(90deg,transparent,' + C.violet + ' 35%,' + C.cyan + ' 65%,transparent)' }} />
                  {/* (b) status chip */}
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '7px', padding: '4px 10px',
                    borderRadius: '999px', background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.30)',
                    marginBottom: '12px',
                  }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: C.violetBright, boxShadow: '0 0 8px ' + C.violetBright, animation: 'twLbLed 2.4s ease-in-out infinite' }} />
                    <span style={{ fontFamily: MONO, fontSize: '10px', fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: C.accentText }}>
                      {'Trial Active - Day ' + viewDay + ' of ' + totalDays}
                    </span>
                  </div>
                  {/* (c) title + lead in a radial bloom */}
                  <div style={{ background: 'radial-gradient(80% 120% at 50% 0%, rgba(167,139,250,0.22), transparent 60%)', padding: '6px 8px 10px', margin: '-6px -8px 8px', borderRadius: '12px' }}>
                    <h3 style={{ margin: '0 0 8px', fontSize: '22px', fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.2, color: C.text }}>
                      {fill(cur.title)}
                    </h3>
                    {cur.lead ? (
                      <p style={{ margin: 0, fontSize: '13.5px', lineHeight: 1.45, color: C.textDim }}>
                        {fill(cur.lead)}
                      </p>
                    ) : null}
                  </div>
                  {/* (d) the 3 bullets as stat-tiles */}
                  {Array.isArray(cur.bullets) && cur.bullets.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '2px' }}>
                      {cur.bullets.map((b, i) => (
                        <div key={i} style={{
                          position: 'relative', display: 'flex', alignItems: 'flex-start', gap: '10px',
                          padding: '11px 13px 11px 14px', borderRadius: '10px', background: C.well,
                          border: '1px solid ' + C.edge, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)', overflow: 'hidden',
                        }}>
                          <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: '2px', background: 'linear-gradient(180deg,' + C.violetBright + ',' + C.violet + ')' }} />
                          <span style={{ flexShrink: 0, width: '18px', textAlign: 'right', fontFamily: MONO, fontSize: '11px', color: C.textFaint, fontVariantNumeric: 'tabular-nums' }}>
                            {String(i + 1).padStart(2, '0')}
                          </span>
                          <span style={{ fontSize: '13px', lineHeight: 1.45, color: C.text }}>{fill(b)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
              <>
              {dayTheme && (
                <div style={{ fontFamily: MONO, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '.16em', color: C.violet, marginBottom: '6px', opacity: 0.9 }}>
                  {fillTokens(dayTheme)}
                </div>
              )}
              <h3 style={{ margin: '0 0 8px', fontSize: '17px', fontWeight: 700, letterSpacing: '-0.012em', lineHeight: 1.25, color: C.text }}>
                {fill(cur.title)}
              </h3>

              {/* Optional one-line setup. */}
              {cur.lead ? (
                <p style={{ margin: '0 0 9px', fontSize: '13px', lineHeight: 1.45, color: C.textDim }}>
                  {fill(cur.lead)}
                </p>
              ) : null}

              {Array.isArray(cur.bullets) && cur.bullets.length > 0 ? (
                onScreen3 && !cur.cta ? (
                  // Try-it screen: numbered keycap steps in the well. (A screen carrying
                  // a `cta` - e.g. TRIAL_CLOSE_SCREEN - is the day's last screen too, but
                  // its bullets are a plain honest read, not "try it" steps, so it keeps
                  // the teaching-tick style below and gets its own button instead.)
                  <div style={{ marginTop: '2px', padding: '14px 14px 15px', borderRadius: '10px', background: C.well, border: '1px solid ' + C.edge, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)' }}>
                    <div style={{ fontFamily: MONO, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '.12em', color: C.violet, marginBottom: '8px', fontWeight: 700 }}>
                      {'// TRY IT NOW'}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {cur.bullets.map((b, i) => (
                        <div key={i} style={{ display: 'flex', gap: '9px', alignItems: 'flex-start' }}>
                          <span style={{ flexShrink: 0, width: '18px', height: '18px', borderRadius: '6px', background: 'rgba(167,139,250,0.12)', border: '1px solid rgba(167,139,250,0.30)', color: C.accentText, fontFamily: MONO, fontVariantNumeric: 'tabular-nums', fontSize: '11px', fontWeight: 700, textAlign: 'center', lineHeight: '18px', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.12)' }}>{i + 1}</span>
                          <span style={{ fontSize: '13px', lineHeight: 1.4, color: C.text }}>{fill(b)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  // Teaching screen: short bullets with a TICK marker.
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '11px', marginTop: '2px' }}>
                    {cur.bullets.map((b, i) => (
                      <div key={i} style={{ display: 'flex', gap: '11px', alignItems: 'flex-start' }}>
                        <span style={{ flexShrink: 0, width: '2px', height: '13px', marginTop: '3px', borderRadius: '1px', background: 'linear-gradient(180deg,' + C.violetBright + ',' + C.violet + ')', boxShadow: '0 0 6px rgba(167,139,250,0.45)' }} />
                        <span style={{ fontSize: '13.5px', lineHeight: 1.45, color: C.text }}>{fill(b)}</span>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                // Fallback for any not-yet-shortened screen: the old paragraph + pointer.
                <>
                  {cur.body ? (
                    <p style={{ margin: 0, fontSize: '13.5px', lineHeight: 1.55, color: C.textDim }}>{fillTokens(cur.body)}</p>
                  ) : null}
                  {onScreen3 && cur.pointer ? (
                    <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '10px', background: C.well, border: '1px solid ' + C.edge }}>
                      <div style={{ fontFamily: MONO, fontSize: '10px', textTransform: 'uppercase', letterSpacing: '.12em', color: C.violet, marginBottom: '3px', fontWeight: 700 }}>{'// TRY IT NOW'}</div>
                      <div style={{ fontSize: '12.5px', lineHeight: 1.45, color: C.text }}>{fillTokens(cur.pointer)}</div>
                    </div>
                  ) : null}
                  {!onScreen3 && cur.pointer ? (
                    <div style={{ marginTop: '10px', fontSize: '11.5px', color: C.textFaint, fontStyle: 'italic', lineHeight: 1.4 }}>Try it: {fillTokens(cur.pointer)}</div>
                  ) : null}
                </>
              )}
              </>
              )}

              {lessonAt(viewDay).chatbotLesson && !isMobile && typeof onOpenChatbot === 'function' && (
                <button
                  type="button"
                  onClick={() => onOpenChatbot()}
                  style={{ marginTop: '13px', display: 'inline-flex', alignItems: 'center', gap: '8px', background: 'linear-gradient(135deg,' + C.violet + ',' + C.violetDeep + ')', color: C.ink, border: 'none', borderRadius: '8px', padding: '9px 15px', fontSize: '13px', fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 12px rgba(124,92,224,0.40)' }}
                >
                  <span style={{ fontSize: '15px', lineHeight: 0 }}>&#128172;</span> Open Tara for me
                </button>
              )}

              {/* CTA screens ("Onboarding Lessons v2") - a prominent button below the
                  bullets, matching the panel's premium-dark accent styling used above. */}
              {cur.cta && (
                <button
                  type="button"
                  onClick={() => handleCtaClick(cur.cta)}
                  style={{ marginTop: '15px', width: '100%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '8px', background: 'linear-gradient(135deg,' + C.violet + ',' + C.violetDeep + ')', color: C.ink, border: 'none', borderRadius: '9px', padding: '12px 18px', fontSize: '14px', fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 16px rgba(124,92,224,0.45)' }}
                >
                  {cur.cta.label}
                </button>
              )}

              {confirmDone && (
                <div style={{ marginTop: '12px', fontSize: '12.5px', lineHeight: 1.45, color: C.accentText }}>
                  Nice work - that is the last lesson. Everything lives under the lightbulb any time you want a refresher.
                </div>
              )}
            </div>

            {/* footer: Back / Next bar + header-ish helper links */}
            <div style={{ borderTop: '1px solid ' + C.divider, padding: '11px 14px', background: C.plateGrad, boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {/* Back walks across days; hidden only at the very first screen of Day 1. */}
                {screen > 0 ? (
                  <button
                    type="button"
                    onClick={goBack}
                    aria-label="Back"
                    title="Back"
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'transparent', border: '1px solid ' + C.hair, color: C.textDim, borderRadius: '8px', padding: '7px 13px', fontSize: '17px', lineHeight: 0, cursor: 'pointer' }}
                  ><FaAngleLeft /></button>
                ) : (
                  <span />
                )}
                <span style={{ flex: 1 }} />
                <button
                  type="button"
                  className="tw-lb-primary"
                  onClick={goNext}
                  disabled={confirmDone}
                  aria-label={onScreen3 ? 'Done' : 'Next'}
                  title={onScreen3 ? 'Done' : 'Next'}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    background: 'linear-gradient(135deg,' + C.violet + ',' + C.violetDeep + ')',
                    color: C.ink, border: 'none', borderRadius: '8px',
                    padding: '7px 16px', fontSize: '17px', fontWeight: 700,
                    boxShadow: '0 2px 12px rgba(124,92,224,0.40)',
                    cursor: confirmDone ? 'default' : 'pointer', opacity: confirmDone ? 0.6 : 1, whiteSpace: 'nowrap',
                  }}
                >
                  {!onScreen3
                    ? <FaAngleRight />
                    : (<><FaCheck style={{ fontSize: '12px' }} /><span style={{ fontFamily: MONO, fontSize: '10px', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>Done</span></>)}
                </button>
              </div>

              {/* quiet utility row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginTop: '8px', flexWrap: 'wrap' }}>
                {viewDay !== liveDay && (
                  <button className="tw-lb-link" onClick={resumeToToday}>Back to Today</button>
                )}
                {mode === 'today' && screen > 0 && (
                  <button className="tw-lb-link" onClick={startDayOver}>Start day over</button>
                )}
                <span style={{ flex: 1 }} />
                {pos && <button className="tw-lb-link" onClick={snapToCenter}>Recenter</button>}
                {dismissed ? (
                  <button className="tw-lb-link" onClick={unmuteTips} title="Resume the daily auto-open">Turn daily pop-ups back on</button>
                ) : (
                  <button className="tw-lb-link" onClick={muteTips} title="Keep reading here any time - just stop the daily auto-open">Stop daily pop-ups</button>
                )}
              </div>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
};

export default LessonBox;
