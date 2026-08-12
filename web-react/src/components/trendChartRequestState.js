export const resolveTrendChartDateRequest = ({
  janDecDateRange,
  opportunityStartDate,
  trendChartStartDate,
  expectedTrendChartStartDate,
  janDecStartDate,
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

  // The non-Jan-Dec trend window must belong to the same opportunity date.
  // During a multi-field viewer transition, an older trend start can otherwise
  // be paired with the new symbol/date and sent to the appserver.
  if (
    !trendChartStartDate
    || !expectedTrendChartStartDate
    || trendChartStartDate !== expectedTrendChartStartDate
  ) {
    return { ok: false, reason: 'unsettled_trend_start_date' }
  }

  return {
    ok: true,
    chartStartDate: trendChartStartDate,
    opportunityStartDate,
  }
}
