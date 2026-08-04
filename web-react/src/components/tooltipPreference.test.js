import { initialTooltipsEnabled } from './tooltipPreference';

describe('tooltip preference', () => {
  test('defaults to enabled when no preference has been saved', () => {
    expect(initialTooltipsEnabled(null)).toBe(true);
    expect(initialTooltipsEnabled(undefined)).toBe(true);
  });

  test('restores an explicit disabled preference', () => {
    expect(initialTooltipsEnabled(false)).toBe(false);
    expect(initialTooltipsEnabled('false')).toBe(false);
  });

  test('restores an explicit enabled preference', () => {
    expect(initialTooltipsEnabled(true)).toBe(true);
    expect(initialTooltipsEnabled('true')).toBe(true);
  });
});
