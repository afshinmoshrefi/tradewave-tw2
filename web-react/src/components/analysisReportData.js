const REPORT_SCHEMA_VERSION = 1

export const comparisonReportNotice = ({
  symbol,
  primaryReadyKey,
  currentViewKey,
  chartData,
  actionLabel = 'Compare Symbols',
}) => {
  if (!String(symbol || '').trim()) {
    return {
      code: 'no_pattern',
      title: 'Choose a pattern first',
      message: `Select a pattern from the Opportunity Table, or enter a ticker in the Wave Viewer. Then open Analysis and choose ${actionLabel}.`,
    }
  }
  if (
    primaryReadyKey !== currentViewKey
    || !Array.isArray(chartData)
    || chartData.length === 0
  ) {
    return {
      code: 'pattern_loading',
      title: 'The pattern is still loading',
      message: `Wait for the bars to appear, then open Analysis and choose ${actionLabel} again.`,
    }
  }
  return null
}

const percentNumber = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value !== 'string') return null
  const parsed = Number.parseFloat(value.replace(/,/g, '').replace('%', '').trim())
  return Number.isFinite(parsed) ? parsed : null
}

const round = (value, digits = 2) => {
  if (!Number.isFinite(value)) return null
  const scale = 10 ** digits
  return Math.round((value + Number.EPSILON) * scale) / scale
}

const mean = (values) => {
  const valid = values.filter(Number.isFinite)
  if (!valid.length) return null
  return valid.reduce((sum, value) => sum + value, 0) / valid.length
}

const median = (values) => {
  const valid = values.filter(Number.isFinite).sort((a, b) => a - b)
  if (!valid.length) return null
  const middle = Math.floor(valid.length / 2)
  return valid.length % 2
    ? valid[middle]
    : (valid[middle - 1] + valid[middle]) / 2
}

const sampleStandardDeviation = (values) => {
  const valid = values.filter(Number.isFinite)
  if (valid.length < 2) return 0
  const average = mean(valid)
  const variance = valid.reduce((sum, value) => sum + ((value - average) ** 2), 0) / (valid.length - 1)
  return Math.sqrt(variance)
}

export const compoundedReturn = (values) => {
  const valid = (Array.isArray(values) ? values : []).filter(Number.isFinite)
  if (!valid.length) return null
  const growth = valid.reduce((total, value) => total * (1 + (value / 100)), 1)
  return round((growth - 1) * 100)
}

export const isCompletedChartRow = (row) => {
  if (!row || typeof row !== 'object') return false
  if (!Number.isFinite(Number(row.year))) return false
  // ChartData4 uses this exact sentinel for a future/current-year placeholder.
  // A genuine 0% year is retained because it has real entry/exit prices.
  return !(String(row.pct || '') === '0,0,0' && String(row.price || '') === '0,0')
}

export const completedChartRows = (chartData) => (
  Array.isArray(chartData) ? chartData.filter(isCompletedChartRow) : []
)

export const chartRowResult = (row, direction = 'long') => {
  const values = String(row?.pct || '').split(',').map(Number.parseFloat)
  const rawReturn = Number.isFinite(values[0]) ? values[0] : 0
  const rawHigh = Number.isFinite(values[1]) ? values[1] : 0
  const rawLow = Number.isFinite(values[2]) ? values[2] : 0
  if (direction === 'short') {
    return {
      year: Number(row.year),
      return_pct: round(-rawReturn),
      mfe_pct: round(-rawLow),
      mae_pct: round(-rawHigh),
    }
  }
  return {
    year: Number(row.year),
    return_pct: round(rawReturn),
    mfe_pct: round(rawHigh),
    mae_pct: round(rawLow),
  }
}

export const reportMetrics = (stats = {}, chartData = [], forcedDirection = null) => {
  const direction = forcedDirection === 'short'
    ? 'short'
    : forcedDirection === 'long'
      ? 'long'
      : stats['Trade Dir'] === 'short' ? 'short' : 'long'
  const yearly = completedChartRows(chartData).map(row => chartRowResult(row, direction))
  const returns = yearly.map(row => row.return_pct)
  const mfes = yearly.map(row => row.mfe_pct)
  const maes = yearly.map(row => row.mae_pct)

  return {
    direction,
    sample_years: yearly.length,
    average_return_pct: percentNumber(stats['Avg Profit - All']),
    median_return_pct: percentNumber(stats['Median Profit']),
    profitable_pct: percentNumber(stats['Percent Profitable']),
    best_return_pct: returns.length ? round(Math.max(...returns)) : null,
    worst_return_pct: returns.length ? round(Math.min(...returns)) : null,
    average_mfe_pct: round(mean(mfes)),
    average_mae_pct: round(mean(maes)),
    sharpe_ratio: percentNumber(stats['Sharpe Ratio']),
    // Build cumulative return from the exact completed yearly rows saved in
    // the report. This keeps the headline total consistent with the visible
    // year-by-year results and preserves decimal precision that the legacy
    // stats field removes for display.
    cumulative_return_pct: compoundedReturn(returns),
    annualized_return_pct: percentNumber(stats['Annualized Return']),
    winners: Number.isFinite(Number(stats['Num Winners'])) ? Number(stats['Num Winners']) : null,
    losers: Number.isFinite(Number(stats['Num Losers'])) ? Number(stats['Num Losers']) : null,
    yearly_results: yearly,
  }
}

const monthDay = (value) => {
  const match = String(value || '').match(/^\d{4}-(\d{2}-\d{2})$/)
  return match ? match[1] : ''
}

// ChartData4 labels each observation with the calendar year in which that
// range starts. When the outside range begins earlier in the calendar than the
// selected range, it is the portion that follows the selected range in the
// same annual cycle. Consecutive-year results therefore need a one-year label
// adjustment. PE-filtered requests already return the same election-cycle
// labels for every row and must not be shifted. This relabeling never changes
// dates, returns, or the longstanding Reverse Date Range calculation.
export const alignRangeComparisonCohorts = ({ original, remaining, buyHold, peCycle = 'cons' }) => {
  const originalMonthDay = monthDay(original?.start_date)
  const remainingMonthDay = monthDay(remaining?.start_date)
  const outsideYearOffset = (
    (!peCycle || peCycle === 'cons')
    && originalMonthDay
    && remainingMonthDay
    && remainingMonthDay < originalMonthDay
  ) ? -1 : 0

  const alignedRemaining = outsideYearOffset === 0
    ? remaining
    : {
      ...remaining,
      metrics: {
        ...(remaining?.metrics || {}),
        yearly_results: (remaining?.metrics?.yearly_results || []).map(result => ({
          ...result,
          year: Number(result.year) + outsideYearOffset,
        })),
      },
    }

  const rows = [original, alignedRemaining, buyHold]
  const cohorts = rows.map(row => (
    (row?.metrics?.yearly_results || [])
      .map(result => Number(result.year))
      .filter(Number.isFinite)
      .sort((a, b) => a - b)
  ))
  const commonYears = cohorts.length
    ? cohorts[0].filter(year => cohorts.slice(1).every(cohort => cohort.includes(year)))
    : []

  return {
    original,
    remaining: alignedRemaining,
    buyHold,
    rows,
    cohorts,
    common_years: commonYears,
    outside_year_offset: outsideYearOffset,
    cohort_basis: 'selected_range_annual_cycle',
  }
}

export const rangeComparisonHistoryPlan = ({
  alignment,
  requestedYears,
  minimumYears = 5,
}) => {
  const requested = Number.parseInt(requestedYears, 10)
  const commonYears = Array.isArray(alignment?.common_years)
    ? alignment.common_years.filter(Number.isFinite)
    : []
  const yearsUsed = Number.isFinite(requested)
    ? Math.min(requested, commonYears.length)
    : commonYears.length
  return {
    requested_years: requested,
    years_used: yearsUsed,
    adjustment_required: Number.isFinite(requested) && yearsUsed < requested,
    can_generate: yearsUsed >= minimumYears,
    minimum_years: minimumYears,
  }
}

export const rangeComparisonCandidateYears = (requestedYears, maxAvailableYears) => {
  const requested = Number.parseInt(requestedYears, 10)
  const available = Number.parseInt(maxAvailableYears, 10)
  if (!Number.isFinite(requested)) return 0
  if (!Number.isFinite(available) || available <= requested) return requested
  return Math.min(requested + 1, available)
}

// Range comparisons can have one different boundary year because the selected
// dates, outside dates, and Buy & Hold do not all finish on the same day. Use
// their already-returned shared years instead of repeatedly asking for one
// fewer year, which merely moves the mismatch to the other boundary.
export const restrictRangeComparisonToCommonYears = (
  alignment,
  { riskFreeReturnPct = 4, maxYears = null } = {},
) => {
  const allCommonYears = Array.isArray(alignment?.common_years)
    ? alignment.common_years.filter(Number.isFinite)
    : []
  const limit = Number.parseInt(maxYears, 10)
  const commonYears = Number.isFinite(limit) && limit > 0
    ? allCommonYears.slice(-limit)
    : allCommonYears
  const commonSet = new Set(commonYears)

  const recalculate = (row) => {
    const yearlyResults = (row?.metrics?.yearly_results || [])
      .filter(result => commonSet.has(Number(result.year)))
      .sort((a, b) => Number(a.year) - Number(b.year))
    const returns = yearlyResults.map(result => Number(result.return_pct)).filter(Number.isFinite)
    const mfes = yearlyResults.map(result => Number(result.mfe_pct)).filter(Number.isFinite)
    const maes = yearlyResults.map(result => Number(result.mae_pct)).filter(Number.isFinite)
    const averageReturn = mean(returns)
    const standardDeviation = sampleStandardDeviation(returns)
    const winners = returns.filter(value => value >= 0).length
    const start = Date.parse(row?.start_date)
    const end = Date.parse(row?.end_date)
    const daysOut = Number.isFinite(start) && Number.isFinite(end)
      ? Math.floor((end - start) / 86400000) + 1
      : 0
    const growth = returns.reduce((total, value) => total * (1 + (value / 100)), 1)

    return {
      ...row,
      metrics: {
        ...(row?.metrics || {}),
        sample_years: returns.length,
        average_return_pct: round(averageReturn),
        median_return_pct: round(median(returns)),
        profitable_pct: returns.length ? round((100 * winners) / returns.length) : null,
        best_return_pct: returns.length ? round(Math.max(...returns)) : null,
        worst_return_pct: returns.length ? round(Math.min(...returns)) : null,
        average_mfe_pct: round(mean(mfes)),
        average_mae_pct: round(mean(maes)),
        sharpe_ratio: standardDeviation > 0
          ? round((averageReturn - (riskFreeReturnPct * (daysOut / 365))) / standardDeviation)
          : 0,
        cumulative_return_pct: returns.length ? round((growth - 1) * 100) : null,
        annualized_return_pct: returns.length && growth >= 0
          ? round(((growth ** (1 / returns.length)) - 1) * 100)
          : null,
        winners,
        losers: returns.length - winners,
        yearly_results: yearlyResults,
      },
    }
  }

  const rows = (alignment?.rows || []).map(recalculate)
  return {
    ...alignment,
    original: rows[0],
    remaining: rows[1],
    buyHold: rows[2],
    rows,
    cohorts: rows.map(() => [...commonYears]),
    common_years: commonYears,
  }
}
export const restrictReportRowsToCommonYears = (
  rows,
  { riskFreeReturnPct = 4, maxYears = null } = {},
) => {
  const reportRows = Array.isArray(rows) ? rows : []
  const cohorts = reportRows.map(row => (
    (row?.metrics?.yearly_results || [])
      .map(result => Number(result.year))
      .filter(Number.isFinite)
      .sort((a, b) => a - b)
  ))
  const commonYears = cohorts.length
    ? cohorts[0].filter(year => cohorts.slice(1).every(cohort => cohort.includes(year)))
    : []
  const restricted = restrictRangeComparisonToCommonYears(
    { rows: reportRows, common_years: commonYears },
    { riskFreeReturnPct, maxYears },
  )
  return {
    rows: restricted.rows,
    cohorts: restricted.rows.map(() => [...restricted.common_years]),
    common_years: restricted.common_years,
  }
}


export const protectedRangeViewIsAllowed = ({ transaction, viewKey }) => Boolean(
  transaction
  && viewKey
  && (
    viewKey === transaction.source_key
    || viewKey === transaction.target_key
    || viewKey === transaction.next_view_key
  )
)

export const preservesProtectedRangePair = ({
  transaction,
  currentViewKey,
  nextViewKey,
}) => Boolean(
  transaction?.status === 'ready'
  && (
    (currentViewKey === transaction.source_key && nextViewKey === transaction.target_key)
    || (currentViewKey === transaction.target_key && nextViewKey === transaction.source_key)
  )
)

export const availableHistoryFromMetadata = (metadata, peCycle = 'cons') => {
  if (!Array.isArray(metadata) || metadata.length < 2) return 0
  const firstYear = Number.parseInt(metadata[0], 10)
  const lastYear = Number.parseInt(metadata[1], 10)
  if (!Number.isFinite(firstYear) || !Number.isFinite(lastYear) || lastYear <= firstYear) return 0
  if (peCycle === 'cons') return lastYear - firstYear
  const target = { pe0: 0, pe1: 1, pe2: 2, pe3: 3 }[peCycle]
  if (target === undefined) return lastYear - firstYear
  let count = 0
  for (let year = firstYear; year < lastYear; year += 1) {
    if (year % 4 === target) count += 1
  }
  return count
}

export const historyAdjustment = (requestedYears, symbols, minimumYears = 5) => {
  const requested = Number.parseInt(requestedYears, 10)
  const rows = Array.isArray(symbols) ? symbols : []
  const available = rows
    .map(row => Number.parseInt(row.available_years, 10))
    .filter(value => Number.isFinite(value) && value >= 0)
  const yearsUsed = available.length ? Math.min(requested, ...available) : 0
  return {
    requested_years: requested,
    years_used: yearsUsed,
    adjustment_required: yearsUsed > 0 && yearsUsed < requested,
    can_generate: yearsUsed >= minimumYears,
    minimum_years: minimumYears,
  }
}

export const formatPercent = (value, fallback = '—') => {
  if (!Number.isFinite(value)) return fallback
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${round(value)}%`
}

const sanitizeYearly = (yearly) => (Array.isArray(yearly) ? yearly : []).slice(-99).map(row => ({
  year: Number(row.year),
  return_pct: round(Number(row.return_pct)),
  mfe_pct: round(Number(row.mfe_pct)),
  mae_pct: round(Number(row.mae_pct)),
})).filter(row => Number.isFinite(row.year) && Number.isFinite(row.return_pct))

export const buildAnalysisReportSnapshot = ({ type, title, context, rows, id, generatedAt }) => ({
  schema_version: REPORT_SCHEMA_VERSION,
  report_id: id || `report-${Date.now()}`,
  report_type: type,
  title,
  generated_at: generatedAt || new Date().toISOString(),
  context: { ...context },
  rows: (Array.isArray(rows) ? rows : []).slice(0, 4).map(row => ({
    role: row.role,
    label: row.label,
    symbol: row.symbol,
    company: row.company,
    market: row.market,
    market_label: row.market_label,
    start_date: row.start_date,
    end_date: row.end_date,
    direction: row.direction,
    sample_years: row.metrics?.sample_years,
    metrics: {
      average_return_pct: row.metrics?.average_return_pct,
      median_return_pct: row.metrics?.median_return_pct,
      profitable_pct: row.metrics?.profitable_pct,
      best_return_pct: row.metrics?.best_return_pct,
      worst_return_pct: row.metrics?.worst_return_pct,
      average_mfe_pct: row.metrics?.average_mfe_pct,
      average_mae_pct: row.metrics?.average_mae_pct,
      sharpe_ratio: row.metrics?.sharpe_ratio,
      cumulative_return_pct: row.metrics?.cumulative_return_pct,
      annualized_return_pct: row.metrics?.annualized_return_pct,
      winners: row.metrics?.winners,
      losers: row.metrics?.losers,
    },
    yearly_results: sanitizeYearly(row.metrics?.yearly_results),
  })),
})

// Important: this builder accepts the exact before/after ranges produced by the
// viewer. It intentionally contains no Reverse Date Range arithmetic.
export const buildRangeComparisonSnapshot = ({ original, remaining, buyHold, context, id }) => (
  buildAnalysisReportSnapshot({
    type: 'range_comparison',
    title: 'Date Range Exclusion Report',
    context,
    id,
    rows: [
      { ...original, role: 'selected_range', label: 'Excluded Date Range' },
      { ...remaining, role: 'remaining_range', label: 'Date Range Exclusion Model' },
      { ...buyHold, role: 'buy_hold', label: 'Buy & Hold' },
    ],
  })
)
