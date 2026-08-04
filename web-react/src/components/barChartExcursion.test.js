import {
  BAR_CHART_EXCURSION_STYLES,
  getExcursionVisibility,
  getNeedleRange,
  normalizeBarChartExcursionStyle,
} from './barChartExcursion';

describe('bar chart excursion rendering helpers', () => {
  test('keeps the current filled rendering as the safe default', () => {
    expect(normalizeBarChartExcursionStyle(null)).toBe(BAR_CHART_EXCURSION_STYLES.FILLED);
    expect(normalizeBarChartExcursionStyle('unknown')).toBe(BAR_CHART_EXCURSION_STYLES.FILLED);
    expect(normalizeBarChartExcursionStyle(BAR_CHART_EXCURSION_STYLES.NEEDLE))
      .toBe(BAR_CHART_EXCURSION_STYLES.NEEDLE);
  });

  test('maps high and low excursions to MFE and MAE for long trades', () => {
    expect(getExcursionVisibility('long', true, false)).toEqual({
      showHigh: true,
      showLow: false,
      highKind: 'MFE',
      lowKind: 'MAE',
    });
  });

  test('reverses favorable and adverse sides for short trades', () => {
    expect(getExcursionVisibility('short', true, false)).toEqual({
      showHigh: false,
      showLow: true,
      highKind: 'MAE',
      lowKind: 'MFE',
    });
  });

  test('builds a full needle or a zero-anchored one-sided needle', () => {
    expect(getNeedleRange(12, -5, true, true)).toEqual({ from: -5, to: 12 });
    expect(getNeedleRange(12, -5, true, false)).toEqual({ from: 0, to: 12 });
    expect(getNeedleRange(12, -5, false, true)).toEqual({ from: -5, to: 0 });
    expect(getNeedleRange(12, -5, false, false)).toBeNull();
  });
});
