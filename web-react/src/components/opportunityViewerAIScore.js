const calendarDaysOrNull = value => {
  const parsed = Number.parseInt(value, 10)
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 367 ? parsed : null
}

const isoDayNumber = value => {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const timestamp = Date.UTC(year, month - 1, day)
  const date = new Date(timestamp)
  if (
    Number.isNaN(timestamp) ||
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) return null
  return Math.floor(timestamp / 86400000)
}

const isoFromDayNumber = dayNumber => (
  new Date(Number(dayNumber) * 86400000).toISOString().slice(0, 10)
)

export const currentNewYorkMarketDate = (now = new Date()) => {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

export const activeOpportunityAIRemainingWindow = ({
  row,
  marketDate,
  isBuyAndHold = false,
}) => {
  if (!row || isBuyAndHold) return null
  const startDay = isoDayNumber(row.date)
  const todayDay = isoDayNumber(marketDate)
  const calendarDays = calendarDaysOrNull(row.daysOut)
  if (startDay === null || todayDay === null || calendarDays === null) return null

  const endDay = startDay + calendarDays - 1
  if (todayDay <= startDay || todayDay > endDay) return null

  return {
    adjusted: true,
    originalDate: String(row.date),
    originalCalendarDays: calendarDays,
    endDate: isoFromDayNumber(endDay),
    effectiveDate: String(marketDate),
    effectiveCalendarDays: endDay - todayDay + 1,
  }
}

const directionKey = value => (
  String(value || '').trim().toLowerCase().startsWith('s') ? 's' : 'l'
)

const directionLabel = value => directionKey(value) === 's' ? 'Short' : 'Long'

const recurrenceMode = value => (
  String(value || '').trim().toLowerCase().startsWith('pe') ? 'pe' : 'consecutive'
)

const sameText = (left, right) => String(left || '') === String(right || '')

const PE_YEARS_RE = /^pe([0-3])-(\d+)$/

const positiveYearCountOrNull = value => {
  const normalized = String(value == null ? '' : value).trim().toLowerCase()
  const peMatch = normalized.match(PE_YEARS_RE)
  const count = peMatch ? peMatch[2] : normalized
  return /^\d+$/.test(count) && Number.parseInt(count, 10) > 0 ? count : null
}

const cycleFromDate = date => {
  const year = Number.parseInt(String(date || '').substring(0, 4), 10)
  return Number.isInteger(year) ? `pe${year % 4}` : ''
}

const normalizeCycle = (value, date) => {
  const normalized = String(value || '').trim().toLowerCase()
  return /^pe[0-3]$/.test(normalized) ? normalized : cycleFromDate(date)
}

const viewerHistoryContext = ({ years, mode, cycle, date }) => {
  const rawYears = String(years == null ? '' : years).trim().toLowerCase()
  const peMatch = rawYears.match(PE_YEARS_RE)
  const normalizedMode = peMatch ? 'pe' : recurrenceMode(mode)
  const yearCount = positiveYearCountOrNull(rawYears)
  if (!yearCount) return null
  if (normalizedMode === 'pe') {
    const normalizedCycle = peMatch ? `pe${peMatch[1]}` : normalizeCycle(cycle, date)
    if (!normalizedCycle) return null
    return {
      years: `${normalizedCycle}-${yearCount}`,
      yearCount,
      mode: 'pe',
      cycle: normalizedCycle,
    }
  }
  return {
    years: yearCount,
    yearCount,
    mode: 'consecutive',
    cycle: 'cons',
  }
}

export const createOpportunityAISelectionAnchor = ({
  row,
  market,
  years,
  partialYears,
  mode,
  cycle,
}) => {
  const calendarDays = calendarDaysOrNull(row && row.daysOut)
  const symbol = String((row && row.symbol) || '')
  const date = String((row && row.date) || '')
  if (!row || !symbol || !/^\d{4}-\d{2}-\d{2}$/.test(date) || calendarDays === null) {
    return null
  }

  const selectedDirection = directionLabel(row.lOrS || row.direction)
  const history = viewerHistoryContext({ years, mode, cycle, date })
  if (!history) return null
  const selectedPartialYears = positiveYearCountOrNull(partialYears)
  return {
    market: String(market || ''),
    symbol,
    date,
    calendarDays,
    direction: selectedDirection,
    directionKey: directionKey(selectedDirection),
    // Keep the exact table request value for duration-only recalculations.
    // PE table requests may use plain years plus mode while the Wave Viewer
    // exposes the concrete cycle separately.
    years: String(years == null ? '' : years).trim().toLowerCase(),
    yearCount: history.yearCount,
    partialYears: selectedPartialYears,
    mode: history.mode,
    cycle: history.cycle,
    row,
  }
}

const anchorMatchesViewerSymbol = ({ anchor, market, symbol }) => Boolean(
  anchor &&
  sameText(anchor.market, market) &&
  sameText(anchor.symbol, symbol)
)

const isCanonicalBuyAndHoldViewer = ({ date, calendarDays, isBuyAndHold }) => {
  if (!isBuyAndHold) return false
  const match = String(date || '').match(/^(\d{4})-01-01$/)
  const days = calendarDaysOrNull(calendarDays)
  if (!match || days === null) return false
  const year = Number.parseInt(match[1], 10)
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  return days === (leapYear ? 367 : 366)
}

export const shouldInvalidateOpportunityAIAnchor = ({
  anchor,
  market,
  symbol,
}) => Boolean(
  anchor && !anchorMatchesViewerSymbol({ anchor, market, symbol })
)

/**
 * Select the score source for the lower AI panel.
 *
 * An exact Opportunity Table identity keeps using the table snapshot. Viewer
 * changes use an isolated score request built from the current Wave Viewer.
 * Canonical Buy & Hold always forces Long. The table anchor is an optimization
 * for an exact table row, never a requirement for displaying the current score.
 */
export const selectOpportunityAIPanelSelection = ({
  scoreSource,
  anchor,
  market,
  symbol,
  date,
  calendarDays,
  years,
  mode,
  cycle,
  direction,
  isBuyAndHold = false,
}) => {
  const days = calendarDaysOrNull(calendarDays)
  const currentSymbol = String(symbol || '')
  const currentDate = String(date || '')
  if (!currentSymbol || !/^\d{4}-\d{2}-\d{2}$/.test(currentDate) || days === null) {
    return null
  }

  const matchingSymbol = anchorMatchesViewerSymbol({
    anchor,
    market,
    symbol: currentSymbol,
  })
  const sameDate = Boolean(matchingSymbol && sameText(anchor.date, currentDate))
  const canonicalBuyAndHold = isCanonicalBuyAndHoldViewer({
    date: currentDate,
    calendarDays: days,
    isBuyAndHold,
  })
  if (isBuyAndHold && !canonicalBuyAndHold) return null

  const history = years == null
    ? (anchor ? {
        years: anchor.years,
        yearCount: anchor.yearCount,
        mode: anchor.mode,
        cycle: anchor.cycle,
      } : null)
    : viewerHistoryContext({ years, mode, cycle, date: currentDate })
  if (!history) return null

  const selectedDirection = canonicalBuyAndHold
    ? 'Long'
    : directionLabel(direction || (anchor && anchor.direction) || 'Long')
  const sameHistory = Boolean(anchor && (
    sameText(anchor.yearCount, history.yearCount) &&
    sameText(anchor.mode, history.mode) &&
    (history.mode !== 'pe' || sameText(anchor.cycle, history.cycle))
  ))

  const sourceContextMatches = (
    matchingSymbol &&
    !canonicalBuyAndHold &&
    sameDate &&
    sameHistory &&
    directionKey(selectedDirection) === anchor.directionKey
  )

  const rows = Array.isArray(scoreSource) ? scoreSource : []
  const exactRows = rows.filter(row => (
    sameText(row && row.symbol, currentSymbol) &&
    sameText(row && row.date, currentDate) &&
    calendarDaysOrNull(row && row.daysOut) === days
  ))
  if (sourceContextMatches && exactRows.length > 0) {
    const exactRow = exactRows.find(row => (
      directionKey(row && (row.lOrS || row.direction)) === anchor.directionKey
    ))
    if (exactRow) {
      return {
        origin: 'opportunity_table',
        row: exactRow,
        anchor,
        context: {
          years: anchor.years,
          yearCount: anchor.yearCount,
          partialYears: anchor.partialYears,
          mode: anchor.mode,
          cycle: anchor.cycle,
          isBuyAndHold: canonicalBuyAndHold,
        },
      }
    }
  }

  const preserveTableRecurrence = !canonicalBuyAndHold && sourceContextMatches
  const anchorRow = matchingSymbol && anchor && anchor.row ? anchor.row : {}

  return {
    origin: 'wave_viewer',
    anchor: matchingSymbol ? anchor : null,
    context: {
      years: preserveTableRecurrence ? anchor.years : history.years,
      yearCount: history.yearCount,
      partialYears: preserveTableRecurrence ? anchor.partialYears : null,
      mode: history.mode,
      cycle: history.cycle,
      isBuyAndHold: canonicalBuyAndHold,
    },
    row: {
      ...anchorRow,
      symbol: currentSymbol,
      date: currentDate,
      daysOut: days,
      lOrS: selectedDirection,
      // These statistics belong to the original table duration. The viewer
      // bundle supplies recalculated recurrence evidence for the new length.
      avg_profit: null,
      sharpe_ratio: null,
    },
  }
}

export const buildOpportunityViewerAIRequest = ({ selection, resourceId, marketDate = '' }) => {
  if (!selection) return null

  const sourceRow = selection.row || {}
  const context = selection.context || {}
  const activeWindow = activeOpportunityAIRemainingWindow({
    row: sourceRow,
    marketDate,
    isBuyAndHold: Boolean(context.isBuyAndHold),
  })
  const row = activeWindow ? {
    ...sourceRow,
    date: activeWindow.effectiveDate,
    daysOut: activeWindow.effectiveCalendarDays,
    avg_profit: null,
    sharpe_ratio: null,
  } : sourceRow
  const calendarDays = calendarDaysOrNull(row.daysOut)
  const resource = String(resourceId == null ? '' : resourceId)
  const symbol = String(row.symbol || '')
  const date = String(row.date || '')
  const years = String(context.years == null ? '' : context.years)
  const partialYears = positiveYearCountOrNull(context.partialYears)
  const mode = recurrenceMode(context.mode)
  if (
    !resource || resource === '-1' || !symbol ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date) || calendarDays === null || !years
  ) {
    return null
  }

  const engineDays = calendarDays - 1
  const direction = directionKey(row.lOrS || row.direction)
  const partial = partialYears
    ? { min_winning_years: partialYears, mode }
    : null
  const opportunity = {
    symbol,
    date,
    daysOut: engineDays,
    direction,
    years,
    partial,
    mode,
    selection_origin: 'user_defined',
  }
  const tableContext = {
    years,
    partial,
    mode,
    date,
    is_default: false,
  }

  return {
    requestKey: [resource, symbol, date, engineDays, direction, years, partialYears || 'none', mode].join('|'),
    resourceId: resource,
    row,
    sourceRow,
    activeWindow,
    body: {
      request_origin: 'wave_viewer',
      opportunities: [opportunity],
      table_context: tableContext,
    },
  }
}

export const opportunityAISelectionMatchesViewer = ({
  selection,
  symbol,
  date,
  calendarDays,
  years,
  mode,
  cycle,
  direction,
  isBuyAndHold = false,
}) => {
  if (!selection || typeof selection !== 'object') return false
  const history = viewerHistoryContext({ years, mode, cycle, date })
  if (!history) return false
  const selectedYearCount = positiveYearCountOrNull(
    selection.yearCount == null ? selection.years : selection.yearCount,
  )
  return Boolean(
    sameText(selection.symbol, symbol) &&
    sameText(selection.date, date) &&
    calendarDaysOrNull(selection.daysOut) === calendarDaysOrNull(calendarDays) &&
    sameText(selectedYearCount, history.yearCount) &&
    sameText(recurrenceMode(selection.mode), history.mode) &&
    (history.mode !== 'pe' || sameText(selection.cycle, history.cycle)) &&
    (!direction || directionKey(selection.direction) === directionKey(direction)) &&
    Boolean(selection.isBuyAndHold) === Boolean(isBuyAndHold)
  )
}

const isLoadingStatus = value => ['loading', 'pending', 'queued'].includes(
  String(value || '').trim().toLowerCase(),
)

const terminalizeLoadingHorizon = horizon => {
  if (!horizon || typeof horizon !== 'object' || !isLoadingStatus(horizon.status)) {
    return horizon
  }
  return {
    ...horizon,
    status: 'unavailable',
    error: {
      code: 'service_unavailable',
      message: 'AI scoring is temporarily unavailable.',
      retryable: true,
    },
  }
}

const terminalizeLoadingBundle = bundle => {
  if (!bundle || typeof bundle !== 'object') return bundle

  const horizons = Array.isArray(bundle.horizons)
    ? bundle.horizons.map(terminalizeLoadingHorizon)
    : bundle.horizons
  const checkpoints = Array.isArray(bundle.checkpoints)
    ? bundle.checkpoints.map(terminalizeLoadingHorizon)
    : bundle.checkpoints
  const detailRows = Array.isArray(horizons)
    ? horizons
    : (Array.isArray(checkpoints) ? checkpoints : [])
  const hasAvailableDetail = detailRows.some(item => (
    String((item && item.status) || '').toLowerCase() === 'available'
  ))
  const next = {
    ...bundle,
    ...(Array.isArray(horizons) ? { horizons } : {}),
    ...(Array.isArray(checkpoints) ? { checkpoints } : {}),
  }

  if (isLoadingStatus(next.status)) {
    next.status = hasAvailableDetail ? 'partial' : 'unavailable'
  }
  if (isLoadingStatus(next.display_status)) {
    next.display_status = 'unavailable'
  }
  if (next.display && typeof next.display === 'object') {
    next.display = terminalizeLoadingHorizon(next.display)
  }
  return next
}

/**
 * A timeout may arrive after MLScoreBatch already returned a usable current
 * score while its comparison horizons were still loading. Preserve every
 * received value and mark only unresolved loading rows unavailable.
 */
export const terminalizeOpportunityViewerScores = scores => {
  if (!scores || typeof scores !== 'object') return {}
  return Object.keys(scores).reduce((result, key) => {
    const score = scores[key]
    if (score && score.bundle && typeof score.bundle === 'object') {
      result[key] = { ...score, bundle: terminalizeLoadingBundle(score.bundle) }
    } else if (score && score.ai_bundle && typeof score.ai_bundle === 'object') {
      result[key] = { ...score, ai_bundle: terminalizeLoadingBundle(score.ai_bundle) }
    } else {
      result[key] = terminalizeLoadingBundle(score)
    }
    return result
  }, {})
}
