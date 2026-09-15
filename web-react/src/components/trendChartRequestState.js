export const resolveTrendChartDateRequest = ({
  janDecDateRange,
  opportunityStartDate,
  trendChartStartDate,
  expectedTrendChartStartDate,
  janDecStartDate,
  studyKey,
  loadedWindow,
  chartData,
}) => {
  if (!opportunityStartDate) {
    return { ok: false, reason: 'missing_opportunity_start_date' }
  }

  if (janDecDateRange) {
    if (!janDecStartDate) {
      return { ok: false, reason: 'missing_jan_dec_start_date' }
    }
    return {
      ok: true,
      chartStartDate: janDecStartDate,
      opportunityStartDate,
    }
  }

  // The derived trend-start state must belong to the same opportunity date.
  // During a multi-field viewer transition, an older trend start can otherwise
  // be paired with the new symbol/date and sent to the appserver.
  if (
    !trendChartStartDate
    || !expectedTrendChartStartDate
    || trendChartStartDate !== expectedTrendChartStartDate
  ) {
    return { ok: false, reason: 'unsettled_trend_start_date' }
  }

  // Keep the visible rolling window while its start control moves inside it.
  // Only a validated response for this study, still displayed by the parent,
  // can supply the retained bounds. Cleared/replaced data and study/mode changes
  // deliberately start a fresh window. The date-pair guard above still applies.
  const retainWindow = (
    typeof studyKey === 'string' && studyKey.length > 0
    && loadedWindow?.studyKey === studyKey
    && loadedWindow.janDecDateRange === false
    && Array.isArray(chartData) && chartData.length > 0
    && loadedWindow.chart === chartData
    && opportunityStartDate >= chartData[0][0]
    && opportunityStartDate <= chartData[chartData.length - 1][0]
  )

  return {
    ok: true,
    chartStartDate: retainWindow ? chartData[0][0] : trendChartStartDate,
    opportunityStartDate,
  }
}
