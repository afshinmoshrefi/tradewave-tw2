import { incrementDate, trend_chart_left_gap_days } from './Common'

export const MIN_NUDGE_DAYS_OUT = 2
export const MAX_NUDGE_DAYS_OUT = 366

// The trend chart is fetched with a start date that sits a fixed gap BEFORE the
// opportunity start, and `resolveTrendChartDateRequest` refuses to build a URL
// unless the stored trend start still matches that derived value. Any control
// that moves the opportunity start must therefore move the trend start with it.
// Returning both from one place keeps the two in lockstep: a control that moved
// only the opportunity start left the pair permanently mismatched, so the next
// refetch (a years change, a cycle change) was gated off and the trend chart and
// the stats that read the same data never came back.
export const trendChartStartDateFor = (startDate) =>
  incrementDate(startDate, -trend_chart_left_gap_days)

// Shift the opportunity start by one day while the END date stays put, so the
// holding window grows or shrinks by the same day. Entry day is day 1, so moving
// the start forward one day removes one day from the window.
export const resolveStartDateNudge = ({
  startDate,
  daysOut,
  direction,
  consolidatedSeasonalData,
}) => {
  const currentDaysOut = parseInt(daysOut, 10)
  if (!Number.isInteger(currentDaysOut)) {
    return { ok: false, reason: 'invalid_days_out' }
  }
  if (direction !== 1 && direction !== -1) {
    return { ok: false, reason: 'invalid_direction' }
  }
  if (!startDate) {
    return { ok: false, reason: 'missing_start_date' }
  }

  const nextDaysOut = currentDaysOut - direction
  if (nextDaysOut < MIN_NUDGE_DAYS_OUT || nextDaysOut > MAX_NUDGE_DAYS_OUT) {
    return { ok: false, reason: 'days_out_out_of_range' }
  }

  const nextStartDate = incrementDate(startDate, direction)

  // Moving the start earlier cannot go past the oldest loaded seasonal day.
  if (
    direction < 0
    && Array.isArray(consolidatedSeasonalData)
    && consolidatedSeasonalData.length > 0
    && nextStartDate < consolidatedSeasonalData[0][0]
  ) {
    return { ok: false, reason: 'before_loaded_history' }
  }

  return {
    ok: true,
    startDate: nextStartDate,
    daysOut: String(nextDaysOut),
    trendChartStartDate: trendChartStartDateFor(nextStartDate),
  }
}
