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

const { getOnboardingDay, getTrialState, ONBOARDING_DAYS, isOnboardingArcActive } = require('./onboarding');

beforeEach(() => {
  mockLs = {};
  mockCk = {};
  window.current_user_id = '0';
  window.tw2_user_tier = 'explorer';
  window.tw2_trial_ends_at = '';
  jest.useFakeTimers();
  jest.setSystemTime(new Date('2026-06-25T12:00:00')); // local noon
});
afterEach(() => { jest.useRealTimers(); });

describe('getOnboardingDay', () => {
  test('first call today seeds and returns Day 1 (no UTC off-by-one)', () => {
    expect(getOnboardingDay()).toBe(1);
    expect(mockLs['tw_onboard_started_at']).toBe('2026-06-25');
  });
  test('started 3 calendar days ago -> Day 4', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-22';
    expect(getOnboardingDay()).toBe(4);
  });
  test('clamps to the 7-day arc', () => {
    mockLs['tw_onboard_started_at'] = '2026-01-01';
    expect(getOnboardingDay()).toBe(ONBOARDING_DAYS.length);
  });
  test('corrupt start value reseeds and returns Day 1', () => {
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

describe('isOnboardingArcActive', () => {
  test('brand-new user (no start) -> active', () => {
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('started today -> active', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-25';
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('Day 7 (6 days ago) -> still active', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-19';
    expect(isOnboardingArcActive()).toBe(true);
  });
  test('Day 8 (7 days ago) -> arc done', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-18';
    expect(isOnboardingArcActive()).toBe(false);
  });
  test('dismissed -> done regardless of day', () => {
    mockLs['tw_onboard_started_at'] = '2026-06-25';
    mockCk['tw_onboard_dismissed_0'] = '1';
    expect(isOnboardingArcActive()).toBe(false);
  });
});
