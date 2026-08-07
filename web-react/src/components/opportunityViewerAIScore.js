const calendarDaysOrNull = value => {
  const parsed = Number.parseInt(value, 10)
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 367 ? parsed : null
}

const directionKey = value => (
  String(value || '').trim().toLowerCase().startsWith('s') ? 's' : 'l'
)

const directionLabel = value => directionKey(value) === 's' ? 'Short' : 'Long'

const recurrenceMode = value => (
  String(value || '').trim().toLowerCase().startsWith('pe') ? 'pe' : 'consecutive'
)

const sameText = (left, right) => String(left || '') === String(right || '')

export const createOpportunityAISelectionAnchor = ({
  row,
  market,
  years,
  partialYears,
  mode,
}) => {
  const calendarDays = calendarDaysOrNull(row && row.daysOut)
  const symbol = String((row && row.symbol) || '')
  const date = String((row && row.date) || '')
  if (!row || !symbol || !/^\d{4}-\d{2}-\d{2}$/.test(date) || calendarDays === null) {
    return null
  }

  const selectedDirection = directionLabel(row.lOrS || row.direction)
  return {
    market: String(market || ''),
    symbol,
    date,
    calendarDays,
    direction: selectedDirection,
    directionKey: directionKey(selectedDirection),
    years: String(years == null ? '' : years),
    partialYears: String(partialYears == null ? '' : partialYears),
    mode: recurrenceMode(mode),
    row,
  }
}

const anchorMatchesViewer = ({ anchor, market, symbol, date }) => Boolean(
  anchor &&
  sameText(anchor.market, market) &&
  sameText(anchor.symbol, symbol) &&
  sameText(anchor.date, date)
)

export const shouldInvalidateOpportunityAIAnchor = ({ anchor, market, symbol, date }) => (
  Boolean(anchor) && !anchorMatchesViewer({ anchor, market, symbol, date })
)

/**
 * Select the score source for the lower AI panel.
 *
 * An exact Opportunity Table row keeps using the table snapshot. If only the
 * inclusive calendar-day length changed, the clicked row remains the pattern
 * anchor and a synthetic viewer row changes that one value only. Symbol, date,
 * market, direction, years, and recurrence remain fixed to the selected setup.
 */
export const selectOpportunityAIPanelSelection = ({
  scoreSource,
  anchor,
  market,
  symbol,
  date,
  calendarDays,
}) => {
  const days = calendarDaysOrNull(calendarDays)
  const currentSymbol = String(symbol || '')
  const currentDate = String(date || '')
  if (!currentSymbol || !/^\d{4}-\d{2}-\d{2}$/.test(currentDate) || days === null) {
    return null
  }

  const rows = Array.isArray(scoreSource) ? scoreSource : []
  const exactRows = rows.filter(row => (
    sameText(row && row.symbol, currentSymbol) &&
    sameText(row && row.date, currentDate) &&
    calendarDaysOrNull(row && row.daysOut) === days
  ))
  const matchingAnchor = anchorMatchesViewer({
    anchor,
    market,
    symbol: currentSymbol,
    date: currentDate,
  })

  if (exactRows.length > 0) {
    const exactDirection = matchingAnchor
      ? exactRows.find(row => directionKey(row && (row.lOrS || row.direction)) === anchor.directionKey)
      : null
    const exactRow = exactDirection || (!matchingAnchor ? exactRows[0] : null)
    if (exactRow) {
      return {
        origin: 'opportunity_table',
        row: exactRow,
        anchor,
      }
    }
  }

  if (!matchingAnchor) return null

  return {
    origin: 'wave_viewer',
    anchor,
    row: {
      ...anchor.row,
      symbol: currentSymbol,
      date: currentDate,
      daysOut: days,
      lOrS: anchor.direction,
      // These statistics belong to the original table duration. The viewer
      // bundle supplies recalculated recurrence evidence for the new length.
      avg_profit: null,
      sharpe_ratio: null,
    },
  }
}

export const buildOpportunityViewerAIRequest = ({ selection, resourceId }) => {
  if (!selection || selection.origin !== 'wave_viewer' || !selection.anchor) return null

  const row = selection.row || {}
  const anchor = selection.anchor
  const calendarDays = calendarDaysOrNull(row.daysOut)
  const resource = String(resourceId == null ? '' : resourceId)
  const symbol = String(row.symbol || '')
  const date = String(row.date || '')
  const years = String(anchor.years == null ? '' : anchor.years)
  const partialYears = String(anchor.partialYears == null ? '' : anchor.partialYears)
  const mode = recurrenceMode(anchor.mode)
  if (
    !resource || resource === '-1' || !symbol ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date) || calendarDays === null ||
    !years || !partialYears
  ) {
    return null
  }

  const engineDays = calendarDays - 1
  const direction = directionKey(anchor.direction)
  const partial = {
    min_winning_years: partialYears,
    mode,
  }
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
    requestKey: [resource, symbol, date, engineDays, direction, years, partialYears, mode].join('|'),
    resourceId: resource,
    row,
    body: {
      request_origin: 'wave_viewer',
      opportunities: [opportunity],
      table_context: tableContext,
    },
  }
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
