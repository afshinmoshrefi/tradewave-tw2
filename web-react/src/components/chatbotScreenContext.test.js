import {
  applyTooltipPreference,
  buildChatbotScreenContext,
  buildOpportunityTableContext,
  buildWaveViewerRecurrenceContext,
  deriveDirectionFromBars,
  deriveSeasonalWindowPath,
  parseOptionalNumber,
  showBottomSlide,
  shouldClearOpportunityTable,
} from './chatbotScreenContext';

const baseProps = {
  swiper: { activeIndex: 2 },
  initialWindowNum: 0,
  seasonalBarChartData: [{ year: 2026, pct: '0,0,0' }],
  lineChartYear: 2026,
  tradeActive: false,
  showProjection: true,
  consolidatedSeasonalData: [['2026-01-01', 0]],
  showMaxProjection: true,
  maxYearsConsolidatedSeasonalData: [['2026-01-01', 0]],
  maxAvailableYears: 40,
  seasonalYears: '17',
  projectionPeriod: '90',
  oppTableLength: 23,
};

test('preserves real zero excursions but keeps missing values null', () => {
  expect(parseOptionalNumber('0')).toBe(0);
  expect(parseOptionalNumber('-3.25')).toBe(-3.25);
  expect(parseOptionalNumber('')).toBeNull();
  expect(parseOptionalNumber(undefined)).toBeNull();
  expect(parseOptionalNumber('not-a-number')).toBeNull();
});

test('carries the table recurrence selection into Tara checkpoint context', () => {
  expect(buildWaveViewerRecurrenceContext({
    PEselected: 'cons',
    oppTablePartialYears: '9',
  })).toEqual({
    mode: 'consecutive',
    partial_years: { min_winning_years: '9', mode: 'consecutive' },
  });

  expect(buildWaveViewerRecurrenceContext({
    PEselected: 'pe2',
    oppTablePartialYears: 6,
  })).toEqual({
    mode: 'pe',
    partial_years: { min_winning_years: '6', mode: 'pe' },
  });
});

test('does not invent a minimum-winning-years identity before metadata resolves', () => {
  expect(buildWaveViewerRecurrenceContext({
    PEselected: 'cons',
    oppTablePartialYears: '-1',
  })).toEqual({ mode: 'consecutive' });
});

test('preserves opportunity rows for a same-market Tara chart load', () => {
  expect(shouldClearOpportunityTable('S&P 500', 'S&P 500')).toBe(false);
});

test('clears opportunity rows only for a real market change', () => {
  expect(shouldClearOpportunityTable('S&P 500', 'NASDAQ 100')).toBe(true);
  expect(shouldClearOpportunityTable('S&P 500', '')).toBe(false);
});

test('moves Tara lower-panel commands to the exact desktop carousel slide', () => {
  const slideTo = jest.fn();
  const swiper = { slideTo };

  expect(showBottomSlide(swiper, 'trend_chart')).toBe(true);
  expect(showBottomSlide(swiper, 'wave_stats')).toBe(true);
  expect(showBottomSlide(swiper, 'price_chart')).toBe(true);
  expect(slideTo.mock.calls).toEqual([[0], [1], [2]]);
});

test('rejects unknown lower-panel targets without moving the carousel', () => {
  const slideTo = jest.fn();

  expect(showBottomSlide({ slideTo }, 'settings')).toBe(false);
  expect(showBottomSlide(null, 'price_chart')).toBe(false);
  expect(slideTo).not.toHaveBeenCalled();
});

test('applies only explicit boolean Tara tooltip preferences', () => {
  const setTooltipsEnabled = jest.fn();

  expect(applyTooltipPreference({ show_tooltips: true }, setTooltipsEnabled)).toBe(true);
  expect(applyTooltipPreference({ show_tooltips: false }, setTooltipsEnabled)).toBe(true);
  expect(setTooltipsEnabled.mock.calls).toEqual([[true], [false]]);

  expect(applyTooltipPreference({ show_tooltips: 'false' }, setTooltipsEnabled)).toBe(false);
  expect(applyTooltipPreference({}, setTooltipsEnabled)).toBe(false);
  expect(applyTooltipPreference({ show_tooltips: true }, null)).toBe(false);
  expect(setTooltipsEnabled).toHaveBeenCalledTimes(2);
});

test('sends Tara the exact filtered and sorted visible opportunity order', () => {
  const rawRows = [
    { date: '2026-08-03', symbol: 'ROST', daysOut: 17, lOrS: 'Long', avg_profit: 5.2, sharpe_ratio: 2.48 },
    { date: '2026-08-02', symbol: 'PCAR', daysOut: 177, lOrS: 'Long', avg_profit: 19.1, sharpe_ratio: 1.32 },
  ];
  const visibleRows = [rawRows[1]];

  expect(buildOpportunityTableContext(visibleRows, rawRows)).toEqual([
    {
      date: '2026-08-02',
      symbol: 'PCAR',
      days_out: 177,
      direction: 'Long',
      avg_profit: 19.1,
      sharpe_ratio: 1.32,
    },
  ]);
  expect(buildOpportunityTableContext(null, rawRows).map(row => row.symbol)).toEqual(['ROST', 'PCAR']);
});

test('reports the active price chart and both actually visible projections', () => {
  expect(buildChatbotScreenContext(baseProps)).toEqual({
    active_bottom_slide: 'price_chart',
    price_chart_mode: 'current',
    selected_projection_visible: true,
    full_history_projection_visible: true,
    opportunity_table_visible: true,
    selected_lookback: '17',
    full_history_years: '40',
    projection_period: '90',
    opportunity_rows: 23,
    selected_window_path: 'unknown',
    full_history_window_path: 'unknown',
  });
});

test('does not call hidden price-chart projections visible on another slide', () => {
  const context = buildChatbotScreenContext({ ...baseProps, swiper: { activeIndex: 0 } });
  expect(context.active_bottom_slide).toBe('trend_chart');
  expect(context.selected_projection_visible).toBe(false);
  expect(context.full_history_projection_visible).toBe(false);
});

test('prefers the Price Chart render contract over inferred toggle state', () => {
  const context = buildChatbotScreenContext({
    ...baseProps,
    symbol: 'ROST',
    priceChartContext: {
      symbol: 'ROST',
      mode: 'historical',
      year: 2011,
      projection_capable: false,
      selected_projection_visible: false,
      full_history_projection_visible: false,
      projection_period_days: '30',
      selected_years: 'pe2-10',
      full_history_years: 40,
    },
  });

  expect(context.price_chart_mode).toBe('historical');
  expect(context.price_chart_year).toBe('2011');
  expect(context.selected_projection_visible).toBe(false);
  expect(context.selected_lookback).toBe('pe2-10');
  expect(context.projection_period).toBe('30');
});

test('ignores a stale Price Chart contract from a different loaded window', () => {
  const context = buildChatbotScreenContext({
    ...baseProps,
    symbol: 'ROST',
    startDate: '2026-08-03',
    daysOut: '17',
    seasonalYears: '40',
    PEselected: 'cons',
    priceChartContext: {
      symbol: 'ROST',
      start_date: '2026-07-01',
      days_out: '31',
      years: '10',
      pe_cycle: 'cons',
      mode: 'historical',
      year: 2011,
      projection_capable: false,
      selected_projection_visible: false,
      full_history_projection_visible: false,
    },
  });

  expect(context.price_chart_mode).toBe('current');
  expect(context.price_chart_year).toBeUndefined();
});

test('keeps projections visible on an active current-year trade', () => {
  const context = buildChatbotScreenContext({
    ...baseProps,
    seasonalBarChartData: [{ year: 2026, pct: '-1.2,2.0,-3.0' }],
    tradeActive: true,
  });
  expect(context.price_chart_mode).toBe('active_trade');
  expect(context.selected_projection_visible).toBe(true);
  expect(context.full_history_projection_visible).toBe(true);
});

test('preserves PE-cycle lookbacks as strings and identifies a historical chart', () => {
  const context = buildChatbotScreenContext({
    ...baseProps,
    seasonalYears: 'pe2-10',
    seasonalBarChartData: [{ year: 2024, pct: '3.2,4.1,-1.0' }, { year: 2026, pct: '0,0,0' }],
    lineChartYear: 2024,
    tradeActive: false,
  });
  expect(context.selected_lookback).toBe('pe2-10');
  expect(context.price_chart_mode).toBe('historical');
  expect(context.price_chart_year).toBe('2024');
  expect(context.selected_projection_visible).toBe(false);
});

test('derives an arbitrary short window from the underlying yearly moves', () => {
  const bars = [
    ...Array.from({ length: 14 }, (_, i) => ({ year: 2009 + i, pct: '-2.51,1.0,-4.0' })),
    ...Array.from({ length: 3 }, (_, i) => ({ year: 2023 + i, pct: '1.44,3.0,-1.0' })),
    { year: 2026, pct: '0,0,0' },
  ];
  expect(deriveDirectionFromBars(bars, 'long')).toBe('short');
});

test('summarizes normalized seasonal curves by direction without sending curve values', () => {
  const selected = [
    ['2026-07-31', 72],
    ['2026-08-01', 70],
    ['2026-08-05', 64],
    // The inclusive six-day window ends Aug 5; this row must not affect the result.
    ['2026-08-06', 90],
  ];
  const fullHistory = [
    ['2026-07-31', 55],
    ['2026-08-05', 61],
  ];

  expect(deriveSeasonalWindowPath(selected, '2026-07-31', 6, 'short')).toBe('supports');
  expect(deriveSeasonalWindowPath(fullHistory, '2026-07-31', 6, 'short')).toBe('against');

  const context = buildChatbotScreenContext({
    ...baseProps,
    startDate: '2026-07-31',
    daysOut: 6,
    barChartLongOrShort: 'short',
    consolidatedSeasonalData: selected,
    maxYearsConsolidatedSeasonalData: fullHistory,
  });
  expect(context.selected_window_path).toBe('supports');
  expect(context.full_history_window_path).toBe('against');
  expect(JSON.stringify(context)).not.toContain('72');
  expect(JSON.stringify(context)).not.toContain('64');
});

test('keeps the 367-calendar-day boundary inclusive without extending its end date', () => {
  const cycle = [
    ['2026-01-01', 50],
    ['2027-01-02', 60],
    // A 367-day window ends Jan 2; this next row must not reverse the result.
    ['2027-01-03', 10],
  ];

  expect(deriveSeasonalWindowPath(cycle, '2026-01-01', 367, 'long')).toBe('supports');
});

test('uses the derived arbitrary-window direction for the seasonal path summary', () => {
  const bars = [
    { year: 2023, pct: '-2.0,1.0,-3.0' },
    { year: 2024, pct: '-1.0,1.0,-2.0' },
    { year: 2025, pct: '0.5,2.0,-1.0' },
  ];
  const context = buildChatbotScreenContext({
    ...baseProps,
    rowIndexClicked: -1,
    seasonalBarChartData: bars,
    barChartLongOrShort: 'long', // ChartData4's arbitrary-window fallback is unreliable.
    startDate: '2026-07-31',
    daysOut: 6,
    consolidatedSeasonalData: [
      ['2026-07-31', 70],
      ['2026-08-05', 60],
    ],
  });

  expect(context.selected_window_path).toBe('supports');
});
