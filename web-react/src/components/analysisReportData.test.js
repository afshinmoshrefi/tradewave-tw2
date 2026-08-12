import {
  availableHistoryFromMetadata,
  alignRangeComparisonCohorts,
  buildRangeComparisonSnapshot,
  chartRowResult,
  comparisonReportNotice,
  compoundedReturn,
  completedChartRows,
  historyAdjustment,
  preservesProtectedRangePair,
  protectedRangeViewIsAllowed,
  rangeComparisonCandidateYears,
  rangeComparisonHistoryPlan,
  reportMetrics,
  restrictRangeComparisonToCommonYears,
  restrictReportRowsToCommonYears,} from './analysisReportData'

test('comparison reports tell an empty viewer to choose a pattern first', () => {
  expect(comparisonReportNotice({
    symbol: '',
    primaryReadyKey: '',
    currentViewKey: 'empty-view',
    chartData: [],
  })).toMatchObject({
    code: 'no_pattern',
    title: 'Choose a pattern first',
  })
})

test('comparison reports distinguish a loading pattern from an empty viewer', () => {
  expect(comparisonReportNotice({
    symbol: 'MSFT',
    primaryReadyKey: 'older-view',
    currentViewKey: 'current-view',
    chartData: [],
  })).toMatchObject({
    code: 'pattern_loading',
    title: 'The pattern is still loading',
  })
  expect(comparisonReportNotice({
    symbol: 'MSFT',
    primaryReadyKey: 'current-view',
    currentViewKey: 'current-view',
    chartData: [{ year: 2025 }],
  })).toBeNull()
})

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
    cumulative_return_pct: 6.08,
  })
})

test('cumulative return compounds the exact report rows with decimal precision', () => {
  expect(compoundedReturn([-10, -20])).toBe(-28)
  expect(compoundedReturn([10, 20])).toBe(32)
  expect(compoundedReturn([])).toBeNull()
})

test('an excluded weak range stays Long instead of becoming a Short result', () => {
  const stats = {
    'Trade Dir': 'short',
    'Cumulative Return': '32%',
  }
  const chart = [
    { year: 2024, pct: '-10,2,-12', price: '100,90' },
    { year: 2025, pct: '-20,3,-22', price: '100,80' },
  ]
  expect(reportMetrics(stats, chart, 'long')).toMatchObject({
    direction: 'long',
    cumulative_return_pct: -28,
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
  expect(report.title).toBe('Date Range Exclusion Report')
  expect(report.rows.map(row => row.label)).toEqual([
    'Excluded Date Range', 'Date Range Exclusion Model', 'Buy & Hold',
  ])
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

test('PE range report keeps matching cycle-year labels when the outside range starts earlier', () => {
  const cycleYears = [{ year: 2014 }, { year: 2018 }, { year: 2022 }]
  const aligned = alignRangeComparisonCohorts({
    original: { start_date: '2026-08-12', metrics: { yearly_results: cycleYears } },
    remaining: { start_date: '2026-06-03', metrics: { yearly_results: cycleYears } },
    buyHold: { start_date: '2026-01-01', metrics: { yearly_results: cycleYears } },
    peCycle: 'pe2',
  })

  expect(aligned.outside_year_offset).toBe(0)
  expect(aligned.common_years).toEqual([2014, 2018, 2022])
})

test('range report transaction survives toggling between the excluded and outside views', () => {
  const transaction = {
    status: 'ready',
    source_key: 'excluded-range',
    target_key: 'outside-range',
  }

  expect(protectedRangeViewIsAllowed({ transaction, viewKey: 'excluded-range' })).toBe(true)
  expect(protectedRangeViewIsAllowed({ transaction, viewKey: 'outside-range' })).toBe(true)
  expect(protectedRangeViewIsAllowed({ transaction, viewKey: 'unrelated-range' })).toBe(false)
  expect(preservesProtectedRangePair({
    transaction,
    currentViewKey: 'outside-range',
    nextViewKey: 'excluded-range',
  })).toBe(true)
  expect(preservesProtectedRangePair({
    transaction,
    currentViewKey: 'excluded-range',
    nextViewKey: 'outside-range',
  })).toBe(true)
})

test('date-range reports restrict every range and Buy & Hold to the same years', () => {
  const makeRow = (label, years) => ({
    label,
    start_date: '2026-03-01',
    end_date: '2026-05-01',
    metrics: {
      yearly_results: years.map(year => ({
        year,
        return_pct: year - 2020,
        mfe_pct: 5,
        mae_pct: -3,
      })),
    },
  })
  const aligned = restrictReportRowsToCommonYears([
    makeRow('Date Range 1', [2021, 2022, 2023, 2024, 2025]),
    makeRow('Date Range 2', [2020, 2021, 2022, 2023, 2024]),
    makeRow('Buy & Hold', [2021, 2022, 2023, 2024, 2025]),
  ], { maxYears: 3 })

  expect(aligned.common_years).toEqual([2022, 2023, 2024])
  expect(aligned.rows).toHaveLength(3)
  aligned.rows.forEach(row => {
    expect(row.metrics.sample_years).toBe(3)
    expect(row.metrics.yearly_results.map(result => result.year)).toEqual([2022, 2023, 2024])
  })
})

test('range report history uses the shared completed years and reports an adjustment', () => {
  expect(rangeComparisonHistoryPlan({
    alignment: { common_years: [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025] },
    requestedYears: 10,
  })).toEqual({
    requested_years: 10,
    years_used: 8,
    adjustment_required: true,
    can_generate: true,
    minimum_years: 5,
  })
})

test('range report uses an extra available candidate to preserve 60 shared years', () => {
  expect(rangeComparisonCandidateYears(60, 63)).toBe(61)
  expect(rangeComparisonCandidateYears(60, 60)).toBe(60)

  const results = (first, last) => Array.from(
    { length: last - first + 1 },
    (_, index) => ({
      year: first + index,
      return_pct: 1,
      mfe_pct: 2,
      mae_pct: -1,
    }),
  )
  const alignment = alignRangeComparisonCohorts({
    original: {
      start_date: '2026-06-11',
      end_date: '2026-06-26',
      metrics: { yearly_results: results(1966, 2026) },
    },
    remaining: {
      start_date: '2026-06-27',
      end_date: '2027-06-10',
      metrics: { yearly_results: results(1965, 2025) },
    },
    buyHold: {
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      metrics: { yearly_results: results(1965, 2025) },
    },
  })
  const plan = rangeComparisonHistoryPlan({ alignment, requestedYears: 60 })
  const restricted = restrictRangeComparisonToCommonYears(alignment, { maxYears: plan.years_used })

  expect(plan).toMatchObject({ years_used: 60, adjustment_required: false })
  expect(restricted.common_years).toHaveLength(60)
  expect(restricted.rows.every(row => row.metrics.sample_years === 60)).toBe(true)
})

test('range report keeps the shared cohort and recalculates every row from it', () => {
  const result = (year, returnPct) => ({
    year,
    return_pct: returnPct,
    mfe_pct: returnPct + 2,
    mae_pct: returnPct - 2,
  })
  const alignment = alignRangeComparisonCohorts({
    original: {
      start_date: '2026-06-11',
      end_date: '2026-06-26',
      metrics: { yearly_results: [result(2024, 10), result(2025, -5), result(2026, 20)] },
    },
    remaining: {
      start_date: '2026-06-27',
      end_date: '2027-06-10',
      metrics: { yearly_results: [result(2024, 5), result(2025, 15)] },
    },
    buyHold: {
      start_date: '2026-01-01',
      end_date: '2026-12-31',
      metrics: { yearly_results: [result(2024, 8), result(2025, 12)] },
    },
  })

  expect(alignment.common_years).toEqual([2024, 2025])

  const restricted = restrictRangeComparisonToCommonYears(alignment)

  expect(restricted.rows.map(row => row.metrics.sample_years)).toEqual([2, 2, 2])
  expect(restricted.cohorts).toEqual([
    [2024, 2025],
    [2024, 2025],
    [2024, 2025],
  ])
  expect(restricted.original.metrics).toMatchObject({
    average_return_pct: 2.5,
    profitable_pct: 50,
    cumulative_return_pct: 4.5,
    winners: 1,
    losers: 1,
  })
})