const { resolveTrendChartDateRequest } = require('./trendChartRequestState')

test('rejects the stale trend start from the AFL Tara transition', () => {
  expect(resolveTrendChartDateRequest({
    janDecDateRange: false,
    opportunityStartDate: '2026-04-08',
    trendChartStartDate: '2026-07-21',
    expectedTrendChartStartDate: '2026-03-25',
    janDecStartDate: '2026-01-01',
  })).toEqual({
    ok: false,
    reason: 'unsettled_trend_start_date',
  })
})

test('allows the trend request after both dates belong to the same setup', () => {
  expect(resolveTrendChartDateRequest({
    janDecDateRange: false,
    opportunityStartDate: '2026-04-08',
    trendChartStartDate: '2026-03-25',
    expectedTrendChartStartDate: '2026-03-25',
    janDecStartDate: '2026-01-01',
  })).toEqual({
    ok: true,
    chartStartDate: '2026-03-25',
    opportunityStartDate: '2026-04-08',
  })
})

test('Jan-Dec mode uses its full-year chart start independently', () => {
  expect(resolveTrendChartDateRequest({
    janDecDateRange: true,
    opportunityStartDate: '2026-04-08',
    trendChartStartDate: '2026-07-21',
    expectedTrendChartStartDate: '2026-03-25',
    janDecStartDate: '2026-01-01',
  })).toEqual({
    ok: true,
    chartStartDate: '2026-01-01',
    opportunityStartDate: '2026-04-08',
  })
})

const retainedResponses = require('../../../tools/ui_capture/fixtures/trend-chart-responses.json').responses
const rollingChart = retainedResponses.rolling.cons_seas_chart
const retainedOptions = {
  janDecDateRange: false,
  opportunityStartDate: '2026-11-19',
  trendChartStartDate: '2026-11-05',
  expectedTrendChartStartDate: '2026-11-05',
  janDecStartDate: '2026-01-01',
  studyKey: 'AAPL-2-10-cons',
  chartData: rollingChart,
  loadedWindow: { studyKey: 'AAPL-2-10-cons', janDecDateRange: false, chart: rollingChart },
}

test('a large in-range start adjustment keeps the actual engine window', () => {
  expect(resolveTrendChartDateRequest(retainedOptions)).toEqual({
    ok: true,
    chartStartDate: '2025-12-18',
    opportunityStartDate: '2026-11-19',
  })
})

test.each([
  ['2025-12-25', '2025-12-11'],
  ['2025-12-18', '2025-12-04'],
  ['2026-12-17', '2026-12-03'],
])('retains the window for an in-range or boundary start %s', (start, derived) => {
  expect(resolveTrendChartDateRequest({
    ...retainedOptions, opportunityStartDate: start,
    trendChartStartDate: derived, expectedTrendChartStartDate: derived,
  }).chartStartDate).toBe('2025-12-18')
})

test.each([
  ['2025-12-17', '2025-12-03'],
  ['2026-12-18', '2026-12-04'],
])('moving outside the displayed dates starts a fresh window: %s', (start, derived) => {
  expect(resolveTrendChartDateRequest({
    ...retainedOptions, opportunityStartDate: start,
    trendChartStartDate: derived, expectedTrendChartStartDate: derived,
  }).chartStartDate).toBe(derived)
})

test.each([
  ['cleared data', { chartData: [] }],
  ['replaced data', { chartData: retainedResponses.forward.cons_seas_chart }],
  ['symbol change', { studyKey: 'MSFT-2-10-cons' }],
  ['market change', { studyKey: 'AAPL-0-10-cons' }],
  ['year-count change', { studyKey: 'AAPL-2-20-cons' }],
  ['PE change', { studyKey: 'AAPL-2-10-pe2' }],
  ['missing study', { studyKey: undefined }],
  ['missing accepted window', { loadedWindow: null }],
  ['prior Jan-Dec mode', { loadedWindow: { ...retainedOptions.loadedWindow, janDecDateRange: true } }],
])('%s cannot reuse the range', (_name, override) => {
  expect(resolveTrendChartDateRequest({ ...retainedOptions, ...override }).chartStartDate)
    .toBe('2026-11-05')
})

test('a retained window never bypasses the unsettled date-pair guard', () => {
  expect(resolveTrendChartDateRequest({ ...retainedOptions, trendChartStartDate: '2025-12-18' }))
    .toEqual({ ok: false, reason: 'unsettled_trend_start_date' })
})

test('Jan-Dec takes precedence over a retained rolling window', () => {
  expect(resolveTrendChartDateRequest({ ...retainedOptions, janDecDateRange: true }).chartStartDate)
    .toBe('2026-01-01')
})
