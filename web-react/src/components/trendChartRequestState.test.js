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
