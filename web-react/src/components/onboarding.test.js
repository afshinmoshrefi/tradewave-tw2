// Unit tests for the pure logic in onboarding.js - the day counter (the off-by-one
// regression guard) and the trial-state derivation. Common.js storage is mocked with
// an in-memory store; "now" is controlled with jest fake timers. Run under a
// behind-UTC timezone (TZ=America/New_York) to prove the local-date parse fix.
// NB: jest.mock() factory may only reference `mock`-prefixed outer vars (jest hoists it).
let mockLs = {};
let mockCk = {};
jest.mock('./Common', () => ({
  lsGet: (k, d = null) => (k in mockLs ? mockLs[k] : d),
  lsSet: (k, v) => { mockLs[k] = v; },
  getCookie: (n) => (n in mockCk ? mockCk[n] : null),
  setCookie: (n, v) => { mockCk[n] = v; },
}));

const {
  getOnboardingDay, getTrialState, ONBOARDING_DAYS, isOnboardingArcActive,
  getAccountAgeDays, isAutoArcEligible, isEnrolled, setEnrolled, enrollNow,
} = require('./onboarding');

beforeEach(() => {
  mockLs = {};
  mockCk = {};
  window.current_user_id = '0';
  window.tw2_user_tier = 'explorer';
  window.tw2_trial_ends_at = '';
  delete window.current_user_created_at;
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-06-25T12:00:00')); // local noon
});
afterEach(() => { jest.useRealTimers(); });

describe('getOnboardingDay (Gating v2)', () => {
  test('NOT enrolled, no start date -> returns 0 (inactive) and seeds nothing', () => {
    expect(getOnboardingDay()).toBe(0);
    expect(mockLs['tw_onboard_started_at']).toBeUndefined();
  });
  test('enrolled, first call today seeds and returns Day 1 (no UTC off-by-one)', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    expect(getOnboardingDay()).toBe(1);
    expect(mockLs['tw_onboard_started_at']).toBe('2026-06-25');
  });
  test('started 3 calendar days ago -> Day 4 (start date already present, enrollment irrelevant)', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-22';
    expect(getOnboardingDay()).toBe(4);
  });
  test('clamps to the 7-day arc', () => {
    mockLs['tw_onboard_started_at'] = '2026-01-01';
    expect(getOnboardingDay()).toBe(ONBOARDING_DAYS.length);
  });
  test('corrupt start value reseeds and returns Day 1 regardless of enrollment', () => {
    mockLs['tw_onboard_started_at'] = 'not-a-date';
    expect(getOnboardingDay()).toBe(1);
  });
});

describe('getTrialState', () => {
  test('future trial-end -> onTrial with correct days remaining', () => {
    window.tw2_trial_ends_at = new Date('2026-06-29T12:00:00').toISOString();
    const s = getTrialState();
    expect(s.onTrial).toBe(true);
    expect(s.daysRemaining).toBe(4);
    expect(s.tier).toBe('explorer');
  });
  test('past trial-end -> silent (no clock)', () => {
    window.tw2_trial_ends_at = new Date('2026-06-20T12:00:00').toISOString();
    const s = getTrialState();
    expect(s.onTrial).toBe(false);
    expect(s.daysRemaining).toBeNull();
  });
  test('no trial-end (a payer) -> silent, tier preserved', () => {
    window.tw2_trial_ends_at = '';
    window.tw2_user_tier = 'navigator';
    const s = getTrialState();
    expect(s.onTrial).toBe(false);
    expect(s.daysRemaining).toBeNull();
    expect(s.tier).toBe('navigator');
  });
  test('trial ending later today still reads as 1 day left, never 0', () => {
    window.tw2_trial_ends_at = new Date('2026-06-25T20:00:00').toISOString();
    expect(getTrialState().daysRemaining).toBe(1);
  });
});

describe('isOnboardingArcActive (Gating v2 - enrollment is the master switch)', () => {
  test('NOT enrolled, brand-new (no start) -> NOT active', () => {
    expect(isOnboardingArcActive()).toBe(false);
  });
  test('NOT enrolled but has a stale start date (the retroactive-cleanup case: a user wrongly '
    + 'auto-enrolled before this fix) -> still NOT active', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-25';
    expect(isOnboardingArcActive()).toBe(false);
  });
  test('enrolled, brand-new (no start yet) -> active', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('enrolled, started today -> active', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    mockLs['tw_onboard_started_at'] = '2026-06-25';
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('enrolled, Day 7 (6 days ago) -> still active', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    mockLs['tw_onboard_started_at'] = '2026-06-19';
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('enrolled, Day 8 (7 days ago) -> arc done', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    mockLs['tw_onboard_started_at'] = '2026-06-18';
    expect(isOnboardingArcActive()).toBe(false);
  });
  test('enrolled but dismissed -> done regardless of day', () => {
    mockLs['tw_lesson_enrolled'] = '1';
    mockLs['tw_onboard_started_at'] = '2026-06-25';
    mockCk['tw_onboard_dismissed_0'] = '1';
    expect(isOnboardingArcActive()).toBe(false);
  });
});

describe('getAccountAgeDays / isAutoArcEligible (Gating v2 - fails safe on missing data)', () => {
  test('no created_at -> null age, NOT eligible', () => {
    expect(getAccountAgeDays()).toBeNull();
    expect(isAutoArcEligible()).toBe(false);
  });
  test('unparseable created_at -> null age, NOT eligible', () => {
    window.current_user_created_at = 'not-a-date';
    expect(getAccountAgeDays()).toBeNull();
    expect(isAutoArcEligible()).toBe(false);
  });
  test('created today -> age 0, eligible', () => {
    window.current_user_created_at = '2026-06-25';
    expect(getAccountAgeDays()).toBe(0);
    expect(isAutoArcEligible()).toBe(true);
  });
  test('created 7 days ago -> age 7, eligible (boundary inclusive)', () => {
    window.current_user_created_at = '2026-06-18';
    expect(getAccountAgeDays()).toBe(7);
    expect(isAutoArcEligible()).toBe(true);
  });
  test('created 8 days ago -> age 8, NOT eligible (an existing user, not a new signup)', () => {
    window.current_user_created_at = '2026-06-17';
    expect(getAccountAgeDays()).toBe(8);
    expect(isAutoArcEligible()).toBe(false);
  });
});

describe('isEnrolled / setEnrolled / enrollNow', () => {
  test('not enrolled by default', () => {
    expect(isEnrolled()).toBe(false);
  });
  test('setEnrolled flips the flag', () => {
    setEnrolled();
    expect(isEnrolled()).toBe(true);
  });
  test('enrollNow enrolls, seeds a fresh start date, and resets progress markers', () => {
    mockLs['tw_lesson_lastopened'] = 5;
    mockLs['tw_lesson_screen_3'] = 2;
    enrollNow();
    expect(isEnrolled()).toBe(true);
    expect(mockLs['tw_onboard_started_at']).toBe('2026-06-25');
    expect(mockLs['tw_lesson_lastopened']).toBe(0);
    expect(mockLs['tw_lesson_screen_3']).toBe(0);
    expect(getOnboardingDay()).toBe(1);
  });
});
