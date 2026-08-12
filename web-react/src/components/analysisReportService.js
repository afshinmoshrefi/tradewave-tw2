import { appserverURL, getTodayDate, incrementDate, isMarketEntitled, sameResourceFamily } from './Common'
import { twFetch } from './twFetch'
import {
  availableHistoryFromMetadata,
  buildAnalysisReportSnapshot,
  completedChartRows,
  historyAdjustment,
  reportMetrics,
  restrictReportRowsToCommonYears,
} from './analysisReportData'

export class AnalysisReportError extends Error {
  constructor(code, message, details = null) {
    super(message)
    this.name = 'AnalysisReportError'
    this.code = code
    this.details = details
  }
}

const normalizeSymbol = (value) => String(value || '').trim().toUpperCase()

export const parseComparisonSymbols = (values) => (Array.isArray(values) ? values : [values])
  .flatMap(value => String(value || '').split(/[\s,;]+/))
  .map(normalizeSymbol)
  .filter(Boolean)

const requestJson = async (url, signal) => {
  const response = await twFetch(url, { signal })
  let body = null
  if (response.headers.get('content-type')?.includes('application/json')) {
    body = await response.json()
  }
  if (!response.ok) {
    const error = body?.error || `http_${response.status}`
    if (response.status === 403 || error === 'market_not_in_plan') {
      throw new AnalysisReportError('market_locked', 'That symbol belongs to a market that is not included in your plan.')
    }
    if (response.status === 429) {
      throw new AnalysisReportError('rate_limited', 'Too many requests were made at once. Please wait a moment and try again.')
    }
    throw new AnalysisReportError('request_failed', 'The comparison data could not be loaded. Please try again.')
  }
  if (!body) throw new AnalysisReportError('invalid_response', 'The comparison service returned an invalid response.')
  return body
}

export const resolveReportSymbol = async ({
  symbol,
  currentMarket,
  currentMarketLabel,
  token,
  signal,
  securityTypeList2,
  resourceObj,
}) => {
  const normalized = normalizeSymbol(symbol)
  if (!/^[A-Z0-9.-]{1,15}$/.test(normalized)) {
    throw new AnalysisReportError('invalid_symbol', `“${symbol}” is not a valid ticker symbol.`)
  }

  // Resolve through the canonical universe-membership endpoint. NameFromTicker
  // is exchange-wide and can say a symbol exists even when it is not a member
  // of the user's selected/entitled TradeWave resource.
  const url = `${appserverURL()}/ResolveSymbol/${encodeURIComponent(normalized)}?token=${encodeURIComponent(token)}`
  const body = await requestJson(url, signal)
  const matches = Array.isArray(body?.matches) ? body.matches : []
  if (!matches.length) {
    throw new AnalysisReportError('symbol_not_found', `${normalized} was not found.`)
  }
  const entitled = matches.filter(match => isMarketEntitled(
    securityTypeList2 || [],
    resourceObj || {},
    match.resourceID,
  ))
  if (!entitled.length) {
    throw new AnalysisReportError(
      'market_locked',
      `${normalized} is available, but its market is not included in your plan.`,
      { matches },
    )
  }
  const currentMatch = entitled.find(match => String(match.resourceID) === String(currentMarket))
  // ResolveSymbol intentionally returns one representative market per exchange
  // (for example S&P 500 for the whole US-stock family). Prefer that same
  // exchange family over an unrelated cross-market duplicate, but keep using
  // the viewer's selected/entitled market for the report request.
  const currentFamilyMatches = entitled.filter(match => sameResourceFamily(
    Number(match.resourceID),
    Number(currentMarket),
  ))
  const match = currentMatch
    || (currentFamilyMatches.length === 1 ? currentFamilyMatches[0] : null)
    || (entitled.length === 1 ? entitled[0] : null)
  if (!match) {
    throw new AnalysisReportError(
      'ambiguous_symbol',
      `${normalized} exists in more than one market. Load the intended market in the Wave Viewer, then try again.`,
      { matches: entitled },
    )
  }
  const useCurrentMarket = sameResourceFamily(Number(match.resourceID), Number(currentMarket))
  return {
    symbol: normalized,
    company: match.name || normalized,
    market: useCurrentMarket ? String(currentMarket) : String(match.resourceID),
    market_label: useCurrentMarket
      ? (currentMarketLabel || resourceObj?.[currentMarket] || '')
      : (match.label || resourceObj?.[match.resourceID] || ''),
  }
}

const fetchMetadata = async ({ symbol, market, token, signal }) => {
  const url = `${appserverURL()}/StockMetaData/${market}/${encodeURIComponent(symbol)}?token=${encodeURIComponent(token)}`
  const body = await requestJson(url, signal)
  if (!Array.isArray(body?.StockMetaData)) {
    throw new AnalysisReportError('not_enough_data', `${symbol} does not have enough historical data for this report.`)
  }
  return body.StockMetaData
}

export const fetchReportChart = async ({
  symbol,
  market,
  startDate,
  daysOut,
  years,
  peCycle,
  cutOffYear,
  direction,
  token,
  signal,
}) => {
  const processedDays = Math.max(1, Number.parseInt(daysOut, 10) - 1)
  const yearsParam = peCycle && peCycle !== 'cons' ? `${peCycle}-${years}` : String(years)
  let url = `${appserverURL()}/ChartData4/${market}/${startDate}/${encodeURIComponent(symbol)}/${processedDays}/${yearsParam}`
  if (Number(cutOffYear)) url += `/${Number(cutOffYear)}`
  const query = new URLSearchParams({ token: String(token) })
  if (direction === 'long' || direction === 'short') query.set('comparison_direction', direction)
  query.set('report_completed_years', String(years))
  const body = await requestJson(`${url}?${query.toString()}`, signal)
  if (!Array.isArray(body?.ChartData4) || !body.ChartData4.length || !body.stats || !Object.keys(body.stats).length) {
    throw new AnalysisReportError('not_enough_data', `${symbol} does not have enough complete history for this date range.`)
  }
  const effective = body.request || {}
  // ChartData4 has always canonicalized Jan 1 to Jan 2 to avoid its Jan-1
  // boundary edge case. Buy & Hold remains labeled Jan 1–Jan 1 in the report,
  // but this exact server normalization is expected and does not change the
  // report's protected Reverse Date Range inputs.
  const requestedEntryDate = String(startDate || '')
  const todayDate = getTodayDate()
  const requestedYear = Number.parseInt(requestedEntryDate.slice(0, 4), 10)
  const currentYear = Number.parseInt(String(todayDate || '').slice(0, 4), 10)
  let canonicalEntryDate = (
    Number.isFinite(requestedYear)
    && Number.isFinite(currentYear)
    && requestedYear > currentYear
  ) ? String(currentYear) + requestedEntryDate.slice(4) : requestedEntryDate
  if (canonicalEntryDate.endsWith('-01-01')) {
    canonicalEntryDate = incrementDate(canonicalEntryDate, 1)
  }
  const expected = {
    market: String(market),
    symbol: normalizeSymbol(symbol),
    entry_date: canonicalEntryDate,
    days_out: Number(daysOut),
    years: Number(years),
    pe_cycle: peCycle || 'cons',
    cut_off_year: Number(cutOffYear || 0),
    report_completed_years: Number(years),
  }
  const requestMatches = (
    String(effective.market ?? '') === expected.market
    && normalizeSymbol(effective.symbol) === expected.symbol
    && effective.entry_date === expected.entry_date
    && Number(effective.days_out) === expected.days_out
    && Number(effective.years) === expected.years
    && String(effective.pe_cycle || 'cons') === expected.pe_cycle
    && Number(effective.cut_off_year || 0) === expected.cut_off_year
    && Number(effective.report_completed_years) === expected.report_completed_years
    && (!(direction === 'long' || direction === 'short') || effective.comparison_direction === direction)
  )
  if (!requestMatches) {
    throw new AnalysisReportError(
      'request_adjusted',
      'The server adjusted this comparison request, so the report was stopped to prevent an unfair comparison.',
      { expected, effective },
    )
  }
  return { chart: body.ChartData4, stats: body.stats, request: effective }
}

const probeSymbol = async ({ resolved, request, token, signal }) => {
  const metadata = await fetchMetadata({ ...resolved, token, signal })
  const metadataYears = availableHistoryFromMetadata(metadata, request.peCycle)
  if (metadataYears <= 0) {
    throw new AnalysisReportError('not_enough_data', `${resolved.symbol} does not have enough historical data.`)
  }
  const probeYears = Math.max(1, Math.min(request.requestedYears, metadataYears))
  const payload = await fetchReportChart({
    ...resolved,
    startDate: request.startDate,
    daysOut: request.daysOut,
    years: probeYears,
    peCycle: request.peCycle,
    cutOffYear: request.cutOffYear,
    direction: request.direction,
    token,
    signal,
  })
  const completed = completedChartRows(payload.chart).length
  const availableYears = completed < probeYears ? completed : metadataYears
  return { ...resolved, available_years: availableYears }
}

export const preflightSymbolComparison = async ({
  baseline,
  comparisonSymbols,
  startDate,
  daysOut,
  requestedYears,
  peCycle,
  cutOffYear,
  direction,
  token,
  signal,
  securityTypeList2,
  resourceObj,
}) => {
  const symbols = parseComparisonSymbols(comparisonSymbols || [])
  if (!symbols.length) throw new AnalysisReportError('missing_symbols', 'Enter at least one symbol to compare.')
  if (symbols.length > 3) throw new AnalysisReportError('too_many_symbols', 'You can compare up to three additional symbols.')
  const allSymbols = [normalizeSymbol(baseline.symbol), ...symbols]
  if (new Set(allSymbols).size !== allSymbols.length) {
    throw new AnalysisReportError('duplicate_symbol', 'Each comparison symbol must be different.')
  }

  const resolvedComparisons = await Promise.all(symbols.map(symbol => resolveReportSymbol({
    symbol,
    currentMarket: baseline.market,
    currentMarketLabel: baseline.market_label,
    token,
    signal,
    securityTypeList2,
    resourceObj,
  })))
  const resolved = [{ ...baseline, symbol: normalizeSymbol(baseline.symbol) }, ...resolvedComparisons]
  const request = {
    startDate,
    daysOut: Number(daysOut),
    requestedYears: Number(requestedYears),
    peCycle: peCycle || 'cons',
    cutOffYear: Number(cutOffYear || 0),
    direction: direction === 'short' ? 'short' : 'long',
  }
  const availability = await Promise.all(resolved.map(item => probeSymbol({
    resolved: item,
    request,
    token,
    signal,
  })))
  return {
    request,
    symbols: availability,
    history: historyAdjustment(requestedYears, availability, peCycle && peCycle !== 'cons' ? 3 : 5),
  }
}

const commonYearList = (rows) => {
  if (!rows.length) return []
  let common = new Set(rows[0].metrics.yearly_results.map(row => row.year))
  rows.slice(1).forEach(row => {
    const years = new Set(row.metrics.yearly_results.map(result => result.year))
    common = new Set([...common].filter(year => years.has(year)))
  })
  return [...common].sort((a, b) => a - b)
}

const deterministicFindings = (rows) => {
  const leaders = (key, direction = 'max') => {
    const usable = rows.filter(row => Number.isFinite(row.metrics?.[key]))
    if (!usable.length) return []
    const target = Math[direction](...usable.map(row => row.metrics[key]))
    return usable.filter(row => row.metrics[key] === target).map(row => row.symbol)
  }
  return {
    highest_average_return: leaders('average_return_pct'),
    highest_profitable_rate: leaders('profitable_pct'),
    highest_sharpe_ratio: leaders('sharpe_ratio'),
    smallest_average_mae: leaders('average_mae_pct'),
  }
}

export const generateSymbolComparison = async ({ preflight, yearsUsed, adjustmentApproved, token, signal }) => {
  const years = Number(yearsUsed)
  if (!Number.isFinite(years) || years <= 0) {
    throw new AnalysisReportError('not_enough_data', 'There is not enough common history to generate this report.')
  }
  if (years < preflight.request.requestedYears && adjustmentApproved !== true) {
    throw new AnalysisReportError('approval_required', 'Approve the shorter history before generating this report.')
  }
  const payloads = await Promise.all(preflight.symbols.map(item => fetchReportChart({
    ...item,
    startDate: preflight.request.startDate,
    daysOut: preflight.request.daysOut,
    years,
    peCycle: preflight.request.peCycle,
    cutOffYear: preflight.request.cutOffYear,
    direction: preflight.request.direction,
    token,
    signal,
  })))
  const endDate = incrementDate(preflight.request.startDate, preflight.request.daysOut - 1)
  const rows = preflight.symbols.map((item, index) => {
    const metrics = reportMetrics(payloads[index].stats, payloads[index].chart, preflight.request.direction)
    return {
      role: index === 0 ? 'baseline' : 'comparison',
      label: index === 0 ? `${item.symbol} (Current)` : item.symbol,
      ...item,
      start_date: preflight.request.startDate,
      end_date: endDate,
      direction: preflight.request.direction,
      metrics,
    }
  })
  const actualLowest = Math.min(...rows.map(row => row.metrics.sample_years))
  if (actualLowest < years) {
    throw new AnalysisReportError(
      'history_changed',
      `Only ${actualLowest} complete years are available for every symbol. Approve that adjustment to continue.`,
      { years_used: actualLowest },
    )
  }
  const commonYears = commonYearList(rows)
  if (commonYears.length < years) {
    throw new AnalysisReportError(
      'non_common_history',
      'These symbols do not share the same complete historical years. Change one or more symbols and try again.',
      { common_years: commonYears },
    )
  }

  return buildAnalysisReportSnapshot({
    type: 'symbol_comparison',
    title: `${rows[0].symbol} Symbol Comparison`,
    context: {
      baseline_symbol: rows[0].symbol,
      start_date: preflight.request.startDate,
      end_date: endDate,
      days_out: preflight.request.daysOut,
      requested_years: preflight.request.requestedYears,
      years_used: years,
      history_adjusted: years < preflight.request.requestedYears,
      history_adjustment_approved: years < preflight.request.requestedYears ? adjustmentApproved === true : false,
      history_availability: preflight.symbols.map(item => ({ symbol: item.symbol, years: item.available_years })),
      common_years: commonYears.slice(-years),
      pe_cycle: preflight.request.peCycle,
      cut_off_year: preflight.request.cutOffYear,
      direction: preflight.request.direction,
      findings: deterministicFindings(rows),
    },
    rows,
  })
}
const canonicalBuyHoldRange = () => {
  const year = Number.parseInt(getTodayDate().slice(0, 4), 10)
  const startDate = `${year}-01-01`
  const endDate = `${year + 1}-01-01`
  const daysOut = Math.floor((Date.parse(endDate) - Date.parse(startDate)) / 86400000) + 1
  return { start_date: startDate, end_date: endDate, days_out: daysOut }
}

const isCanonicalBuyHoldRange = (range) => (
  String(range?.start_date || '').slice(5) === '01-01'
  && Number(range?.days_out) >= 365
)

export const generateDateRangeComparison = async ({
  baseline,
  ranges,
  requestedYears,
  peCycle,
  cutOffYear,
  token,
  signal,
}) => {
  const symbol = normalizeSymbol(baseline?.symbol)
  const market = String(baseline?.market ?? '')
  if (!symbol || market === '') {
    throw new AnalysisReportError('no_pattern', 'Choose a pattern before comparing date ranges.')
  }
  const uniqueRanges = []
  const seen = new Set()
  ;(Array.isArray(ranges) ? ranges : []).forEach(range => {
    const startDate = String(range?.start_date || '')
    const daysOut = Number.parseInt(range?.days_out, 10)
    const key = `${startDate}|${daysOut}`
    if (
      /^\d{4}-\d{2}-\d{2}$/.test(startDate)
      && Number.isFinite(daysOut)
      && daysOut >= 2
      && !seen.has(key)
      && !isCanonicalBuyHoldRange({ start_date: startDate, days_out: daysOut })
      && uniqueRanges.length < 3
    ) {
      seen.add(key)
      const requestedOffset = Number.parseInt(range?.year_offset, 10)
      uniqueRanges.push({
        start_date: startDate,
        days_out: daysOut,
        year_offset: [-1, 0, 1].includes(requestedOffset) ? requestedOffset : 0,
      })
    }
  })
  if (!uniqueRanges.length) {
    throw new AnalysisReportError(
      'buy_hold_only',
      'Buy & Hold is already included as the reference. Change the dates to add another range.',
    )
  }

  const requested = Number.parseInt(requestedYears, 10)
  const cycle = peCycle || 'cons'
  const minimumYears = cycle === 'cons' ? 5 : 3
  if (!Number.isFinite(requested) || requested < minimumYears) {
    throw new AnalysisReportError('not_enough_data', `At least ${minimumYears} historical years are required.`)
  }
  const metadata = await fetchMetadata({ symbol, market, token, signal })
  const availableYears = availableHistoryFromMetadata(metadata, cycle)
  const candidateYears = availableYears > requested ? Math.min(requested + 1, availableYears) : requested
  const buyHold = canonicalBuyHoldRange()
  const requestRanges = [...uniqueRanges, buyHold]
  const payloads = await Promise.all(requestRanges.map(range => fetchReportChart({
    symbol,
    market,
    startDate: range.start_date,
    daysOut: range.days_out,
    years: candidateYears,
    peCycle: cycle,
    cutOffYear: Number(cutOffYear || 0),
    direction: 'long',
    token,
    signal,
  })))

  const rows = requestRanges.map((range, index) => {
    const buyHoldRow = index === requestRanges.length - 1
    const yearOffset = buyHoldRow ? 0 : Number(range.year_offset || 0)
    const rawMetrics = reportMetrics(payloads[index].stats, payloads[index].chart, 'long')
    const metrics = yearOffset === 0 ? rawMetrics : {
      ...rawMetrics,
      yearly_results: (rawMetrics.yearly_results || []).map(result => ({
        ...result,
        year: Number(result.year) + yearOffset,
      })),
    }
    return {
      role: buyHoldRow ? 'buy_hold' : 'date_range',
      label: buyHoldRow ? 'Buy & Hold' : `Date Range ${index + 1}`,
      symbol,
      company: baseline?.company || symbol,
      market,
      market_label: baseline?.market_label || '',
      start_date: range.start_date,
      end_date: buyHoldRow
        ? buyHold.end_date
        : incrementDate(range.start_date, range.days_out - 1),
      direction: 'long',
      metrics,
    }
  })
  const alignedCandidate = restrictReportRowsToCommonYears(rows)
  const yearsUsed = Math.min(requested, alignedCandidate.common_years.length)
  if (yearsUsed < minimumYears) {
    throw new AnalysisReportError(
      'non_common_history',
      `These date ranges share only ${yearsUsed} completed years. At least ${minimumYears} are needed for a fair comparison.`,
    )
  }
  const aligned = restrictReportRowsToCommonYears(rows, { maxYears: yearsUsed })
  return buildAnalysisReportSnapshot({
    type: 'date_range_comparison',
    title: `${symbol} Date Range Comparison`,
    context: {
      symbol,
      company: baseline?.company || symbol,
      requested_years: requested,
      years_used: yearsUsed,
      history_adjusted: yearsUsed < requested,
      common_years: aligned.common_years,
      pe_cycle: cycle,
      cut_off_year: Number(cutOffYear || 0),
      direction: 'long',
      range_count: uniqueRanges.length,
      includes_buy_hold: true,
    },
    rows: aligned.rows,
  })
}
