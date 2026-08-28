import { resolveStartDateNudge, trendChartStartDateFor } from './startDateNudge'
import { resolveTrendChartDateRequest } from './trendChartRequestState'
import { incrementDate, trend_chart_left_gap_days } from './Common'

const nudge = (overrides = {}) => resolveStartDateNudge({
  startDate: '2025-10-10',
  daysOut: '272',
  direction: -1,
  consolidatedSeasonalData: [['2025-01-01', 1]],
  ...overrides,
})

test('moving the start earlier lengthens the window and keeps the end date fixed', () => {
  expect(nudge()).toMatchObject({
    ok: true,
    startDate: '2025-10-09',
    daysOut: '273',
  })
})

test('moving the start later shortens the window and keeps the end date fixed', () => {
  expect(nudge({ direction: 1 })).toMatchObject({
    ok: true,
    startDate: '2025-10-11',
    daysOut: '271',
  })
})

test('the end date is unchanged in both directions (entry day is day 1)', () => {
  const endOf = ({ startDate, daysOut }) => incrementDate(startDate, parseInt(daysOut, 10) - 1)
  const original = endOf({ startDate: '2025-10-10', daysOut: '272' })
  expect(endOf(nudge({ direction: -1 }))).toBe(original)
  expect(endOf(nudge({ direction: 1 }))).toBe(original)
})

test('the nudge always returns the matching trend chart start date', () => {
  const result = nudge()
  expect(result.trendChartStartDate)
    .toBe(incrementDate(result.startDate, -trend_chart_left_gap_days))
})

// The regression this module exists for: a start-date control that moved the
// opportunity start without moving the trend start left the pair mismatched, so
// every later trend request was gated off and the chart never came back.
test('the nudged pair still builds a trend chart request', () => {
  const result = nudge()
  expect(resolveTrendChartDateRequest({
    janDecDateRange: false,
    opportunityStartDate: result.startDate,
    trendChartStartDate: result.trendChartStartDate,
    expectedTrendChartStartDate: trendChartStartDateFor(result.startDate),
    janDecStartDate: '2026-01-01',
  })).toMatchObject({ ok: true, chartStartDate: result.trendChartStartDate })
})

test('a start date moved without its trend start is exactly what gets gated off', () => {
  const staleTrendStart = trendChartStartDateFor('2025-10-10')
  expect(resolveTrendChartDateRequest({
    janDecDateRange: false,
    opportunityStartDate: '2025-10-09',
    trendChartStartDate: staleTrendStart,
    expectedTrendChartStartDate: trendChartStartDateFor('2025-10-09'),
    janDecStartDate: '2026-01-01',
  })).toMatchObject({ ok: false, reason: 'unsettled_trend_start_date' })
})

test('refuses to shrink the window below the two-day minimum', () => {
  expect(nudge({ daysOut: '2', direction: 1 })).toMatchObject({ ok: false, reason: 'days_out_out_of_range' })
})

test('refuses to grow the window past the yearly maximum', () => {
  expect(nudge({ daysOut: '366', direction: -1 })).toMatchObject({ ok: false, reason: 'days_out_out_of_range' })
})

test('refuses to move the start before the oldest loaded seasonal day', () => {
  expect(nudge({ startDate: '2025-01-01' })).toMatchObject({ ok: false, reason: 'before_loaded_history' })
})

test('moving later is allowed even when the start sits on the oldest loaded day', () => {
  expect(nudge({ startDate: '2025-01-01', direction: 1 })).toMatchObject({ ok: true })
})

test('rejects unusable input instead of producing a half-applied change', () => {
  expect(nudge({ daysOut: 'abc' })).toMatchObject({ ok: false, reason: 'invalid_days_out' })
  expect(nudge({ direction: 0 })).toMatchObject({ ok: false, reason: 'invalid_direction' })
  expect(nudge({ startDate: '' })).toMatchObject({ ok: false, reason: 'missing_start_date' })
})

test('a cross-year window keeps its end date when the start is nudged', () => {
  // ITW: October 9 -> July 8 the following year.
  const result = resolveStartDateNudge({
    startDate: '2025-10-09',
    daysOut: '273',
    direction: 1,
    consolidatedSeasonalData: [['2025-01-01', 1]],
  })
  expect(result).toMatchObject({ ok: true, startDate: '2025-10-10', daysOut: '272' })
  expect(incrementDate(result.startDate, parseInt(result.daysOut, 10) - 1)).toBe('2026-07-08')
})
