const REPORT_SCHEMA_VERSION = 1

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
    cumulative_return_pct: percentNumber(stats['Cumulative Return']),
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
// same annual cycle. Relabeling that outside row by one year pairs the two
// already-calculated observations; it does not change dates, returns, or the
// longstanding Reverse Date Range calculation.
export const alignRangeComparisonCohorts = ({ original, remaining, buyHold }) => {
  const originalMonthDay = monthDay(original?.start_date)
  const remainingMonthDay = monthDay(remaining?.start_date)
  const outsideYearOffset = (
    originalMonthDay
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
    title: `${context.symbol} Range Comparison`,
    context,
    id,
    rows: [
      { ...original, role: 'selected_range', label: 'Selected Range' },
      { ...remaining, role: 'remaining_range', label: 'Outside Selected Range' },
      { ...buyHold, role: 'buy_hold', label: 'Buy & Hold' },
    ],
  })
)
