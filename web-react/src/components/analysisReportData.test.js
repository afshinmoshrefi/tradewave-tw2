import {
  availableHistoryFromMetadata,
  alignRangeComparisonCohorts,
  buildRangeComparisonSnapshot,
  chartRowResult,
  completedChartRows,
  historyAdjustment,
  reportMetrics,
} from './analysisReportData'

test('future placeholder rows are not counted as historical observations', () => {
  const rows = [
    { year: 2024, pct: '0,2,-1', price: '100,100' },
    { year: 2025, pct: '4,6,-2', price: '100,104' },
    { year: 2026, pct: '0,0,0', price: '0,0' },
  ]
  expect(completedChartRows(rows).map(row => row.year)).toEqual([2024, 2025])
})

test('direction-aware MFE and MAE use the supplied chart observations', () => {
  const row = { year: 2025, pct: '-3,5,-8', price: '100,97' }
  expect(chartRowResult(row, 'long')).toMatchObject({ return_pct: -3, mfe_pct: 5, mae_pct: -8 })
  expect(chartRowResult(row, 'short')).toMatchObject({ return_pct: 3, mfe_pct: 8, mae_pct: -5 })
})

test('report metrics use average of all years instead of average winning year', () => {
  const stats = {
    'Trade Dir': 'long',
    'Avg Profit - All': '3%',
    'Avg Profit': '9%',
    'Median Profit': '2%',
    'Percent Profitable': '60%',
    'Sharpe Ratio': '1.2',
    'Cumulative Return': '34%',
    'Num Winners': '3',
    'Num Losers': '2',
  }
  const chart = [
    { year: 2024, pct: '2,6,-1', price: '100,102' },
    { year: 2025, pct: '4,7,-2', price: '100,104' },
  ]
  expect(reportMetrics(stats, chart)).toMatchObject({
    average_return_pct: 3,
    sample_years: 2,
    average_mfe_pct: 6.5,
    average_mae_pct: -1.5,
  })
})

test('history preflight lowers every symbol to the least available history', () => {
  expect(historyAdjustment(20, [
    { symbol: 'MSFT', available_years: 39 },
    { symbol: 'NVDA', available_years: 27 },
    { symbol: 'ARM', available_years: 10 },
  ])).toEqual({
    requested_years: 20,
    years_used: 10,
    adjustment_required: true,
    can_generate: true,
    minimum_years: 5,
  })
})

test('PE reports keep the existing three-year minimum', () => {
  expect(historyAdjustment(6, [
    { symbol: 'MSFT', available_years: 3 },
    { symbol: 'NVDA', available_years: 4 },
  ], 3)).toMatchObject({
    years_used: 3,
    can_generate: true,
    minimum_years: 3,
  })
})

test('metadata history mirrors consecutive and PE availability rules', () => {
  expect(availableHistoryFromMetadata(['2000-01-03', '2026-08-07'], 'cons')).toBe(26)
  expect(availableHistoryFromMetadata(['2000-01-03', '2026-08-07'], 'pe2')).toBe(6)
})

test('range report consumes exact existing ranges without deriving a complement', () => {
  const original = { start_date: '2026-10-01', end_date: '2026-12-31', metrics: {} }
  const remaining = { start_date: '2026-01-01', end_date: '2026-09-30', metrics: {} }
  const report = buildRangeComparisonSnapshot({
    original,
    remaining,
    buyHold: { start_date: '2026-01-01', end_date: '2027-01-01', metrics: {} },
    context: { symbol: 'MSFT' },
    id: 'range-test',
  })
  expect(report.rows[0].start_date).toBe(original.start_date)
  expect(report.rows[1].start_date).toBe(remaining.start_date)
  expect(report.rows[1].end_date).toBe(remaining.end_date)
})

test('range report pairs an earlier-calendar outside range with the selected annual cycle', () => {
  const original = {
    start_date: '2026-08-07',
    metrics: { yearly_results: [{ year: 2024 }, { year: 2025 }] },
  }
  const remaining = {
    start_date: '2026-06-08',
    metrics: { yearly_results: [{ year: 2025 }, { year: 2026 }] },
  }
  const buyHold = {
    start_date: '2026-01-01',
    metrics: { yearly_results: [{ year: 2024 }, { year: 2025 }] },
  }

  const aligned = alignRangeComparisonCohorts({ original, remaining, buyHold })

  expect(aligned.outside_year_offset).toBe(-1)
  expect(aligned.common_years).toEqual([2024, 2025])
  expect(aligned.remaining.metrics.yearly_results.map(row => row.year)).toEqual([2024, 2025])
  expect(remaining.metrics.yearly_results.map(row => row.year)).toEqual([2025, 2026])
})

test('range report keeps year labels when the outside range starts later in the calendar', () => {
  const yearly = [{ year: 2024 }, { year: 2025 }]
  const aligned = alignRangeComparisonCohorts({
    original: { start_date: '2026-05-01', metrics: { yearly_results: yearly } },
    remaining: { start_date: '2026-09-02', metrics: { yearly_results: yearly } },
    buyHold: { start_date: '2026-01-01', metrics: { yearly_results: yearly } },
  })

  expect(aligned.outside_year_offset).toBe(0)
  expect(aligned.common_years).toEqual([2024, 2025])
})
