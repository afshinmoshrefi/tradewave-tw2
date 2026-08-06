export const AI_COLUMNS = ['ml_score', 'win_prob', 'pred_return', 'pred_mfe']
export const AI_CHECKPOINT_COACHMARK_KEY = 'tw_ai_duration_comparison_coachmark_seen_v2'

// Keep the AI group easy to spot in either theme. This is the established
// Opportunity Table header green; checkpoint identity remains violet in cells.
export const opportunityAIHeaderColor = theme => (
  theme === 'dark' ? 'rgb(100, 220, 140)' : 'rgb(22, 163, 74)'
)

export const AI_METRICS = Object.freeze({
  ml_score: Object.freeze({
    shortLabel: 'AIS',
    label: 'AI Score',
    description: 'A 0-100 rank showing how strong PredR is compared with other model readings in the same time range. It is not a chance of winning.',
  }),
  win_prob: Object.freeze({
    shortLabel: 'Win%',
    label: 'AI Win Probability',
    description: 'How often past cases with similar model readings later finished profitable in the selected direction. This percentage is checked against real results.',
  }),
  pred_return: Object.freeze({
    shortLabel: 'PredR',
    label: 'Predicted Return',
    description: 'The model estimate for the return at the end of this time window. A positive number favors the selected Long or Short direction.',
  }),
  pred_mfe: Object.freeze({
    shortLabel: 'PMFE',
    label: 'Predicted MFE',
    description: 'The model estimate for the best move in the selected direction at any point during this time window. It is not a price target or exit instruction.',
  }),
})

export const AI_DURATION_OUTLINE_DESCRIPTION = 'An outlined AI value means that pattern has more than one AI duration to view. Open it to compare them. The outline does not mean the score is better or worse, and it is not a warning.'

export const opportunityAIHeaderTooltip = metric => {
  const metadata = AI_METRICS[metric]
  if (!metadata) return ''
  return `${metadata.label} (${metadata.shortLabel}). ${metadata.description} ${AI_DURATION_OUTLINE_DESCRIPTION} For a 1-9-day historical pattern, AI uses the model's 10-day minimum. Click to sort.`
}

const CHECKPOINT_DAYS = [30, 60, 90]
const REQUIRED_OPPORTUNITY_COLUMNS = new Set(['symbol', 'daysOut', 'sharpe_ratio'])
const MOBILE_OPPORTUNITY_COLUMNS = new Set(['symbol', 'daysOut', 'sharpe_ratio'])
const DESKTOP_COLUMN_MIN_WIDTH = Object.freeze({
  symbol: 70,
  date: 80,
  daysOut: 60,
  price: 65,
  avg_profit: 65,
  win_prob: 60,
  pred_return: 65,
  pred_mfe: 65,
  ml_score: 55,
})
const MOBILE_COLUMN_MIN_WIDTH = Object.freeze({
  symbol: 58,
  daysOut: 45,
  sharpe_ratio: 45,
  ml_score: 58,
  win_prob: 58,
  pred_return: 58,
  pred_mfe: 58,
})
const TERMINAL_UNAVAILABLE = new Set([
  'after_entry',
  'error',
  'failed',
  'not_available',
  'too_early',
  'unavailable',
  'unsupported',
  'unsupported_duration',
  'unsupported_market',
])

const numberOrNull = value => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const firstDefined = (...values) => values.find(value => value !== undefined && value !== null)

const directionKey = row => String(row && row.lOrS).toLowerCase().startsWith('s') ? 's' : 'l'

export const opportunityAILegacyKey = row => {
  const calendarDays = parseInt(row && row.daysOut, 10)
  return `${row && row.symbol}|${calendarDays - 1}|${directionKey(row)}`
}

export const opportunityAIKeyCandidates = row => {
  const symbol = String((row && row.symbol) || '')
  const entryDate = String((row && row.date) || '')
  const calendarDays = parseInt(row && row.daysOut, 10)
  const engineDays = calendarDays - 1
  const direction = directionKey(row)
  const explicit = firstDefined(row && row.ai_score_key, row && row.score_key, row && row.request_key)

  return [
    explicit,
    `${symbol}|${entryDate}|${engineDays}|${direction}`,
    `${symbol}|${engineDays}|${direction}`,
  ].filter((value, index, values) => value && values.indexOf(value) === index)
}

export const findOpportunityAIScore = (row, scores) => {
  if (!scores || typeof scores !== 'object') return { key: opportunityAILegacyKey(row), score: null }
  const candidates = opportunityAIKeyCandidates(row)
  const key = candidates.find(candidate => Object.prototype.hasOwnProperty.call(scores, candidate))
  return { key: key || candidates[0], score: key ? scores[key] : null }
}

export const selectOpportunityVisibleColumns = ({
  columnOrder,
  showSR2,
  hasAI,
  mlEnabled,
  marketEligible = true,
  isMobilePortrait,
  columnVisibility,
}) => (Array.isArray(columnOrder) ? columnOrder : []).filter(column => {
  if (!showSR2 && (column === 'avg_profit2' || column === 'sharpe_ratio2')) return false
  if (AI_COLUMNS.includes(column)) {
    if (!marketEligible) return false
    if (!hasAI) {
      return column === 'ml_score' && (!columnVisibility || columnVisibility[column] !== false)
    }
    if (!mlEnabled) return false
    return !columnVisibility || columnVisibility[column] !== false
  }
  if (isMobilePortrait) return MOBILE_OPPORTUNITY_COLUMNS.has(column)
  if (REQUIRED_OPPORTUNITY_COLUMNS.has(column)) return true
  return !columnVisibility || columnVisibility[column] !== false
})

export const opportunityTableMinimumWidth = ({ columns, isMobilePortrait, shortDates = false }) => {
  const widths = isMobilePortrait
    ? MOBILE_COLUMN_MIN_WIDTH
    : { ...DESKTOP_COLUMN_MIN_WIDTH, date: shortDates ? 55 : DESKTOP_COLUMN_MIN_WIDTH.date }
  const fallback = isMobilePortrait ? 45 : 55
  return (Array.isArray(columns) ? columns : [])
    .reduce((total, column) => total + (widths[column] || fallback), 0)
}

const normalizeStatus = status => {
  const value = String(status || '').trim().toLowerCase()
  if (value === 'pending' || value === 'loading' || value === 'queued') return 'loading'
  if (value === 'available' || value === 'cached' || value === 'ready' || value === 'success') return 'available'
  if (value === 'below_threshold' || value === 'below-threshold' || value === 'not_qualified') return 'below_threshold'
  if (TERMINAL_UNAVAILABLE.has(value)) return 'unavailable'
  return null
}

const metricsFrom = source => {
  const value = source && (source.metrics || source.score || source.values || source)
  if (!value || typeof value !== 'object') {
    return { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null }
  }
  return {
    ml_score: numberOrNull(firstDefined(value.ml_score, value.ai_score, value.aiScore)),
    win_prob: numberOrNull(firstDefined(value.win_prob, value.win_probability, value.winProbability)),
    pred_return: numberOrNull(firstDefined(value.pred_return, value.predicted_return_pct, value.predictedReturnPct)),
    pred_mfe: numberOrNull(firstDefined(value.pred_mfe, value.predicted_mfe_pct, value.predictedMfePct)),
  }
}

const hasCompleteMetrics = metrics => AI_COLUMNS.every(column => metrics[column] !== null)

const reasonFrom = source => {
  const error = source && source.error
  return String(firstDefined(
    source && source.reason,
    error && typeof error === 'object' ? firstDefined(error.code, error.message) : error,
    source && source.message,
    '',
  ))
}

const horizonCalendarDays = source => {
  const explicit = numberOrNull(firstDefined(
    source && source.calendar_days,
    source && source.calendarDays,
    source && source.horizon_calendar_days,
  ))
  if (explicit !== null) return explicit
  const engineDays = numberOrNull(firstDefined(source && source.daysOut, source && source.days_out))
  return engineDays === null ? null : engineDays + 1
}

const normalizeHorizon = (source, fallbackStatus, fallbackReason) => {
  const metrics = metricsFrom(source)
  const explicitStatus = normalizeStatus(source && source.status)
  const metricsAvailable = hasCompleteMetrics(metrics)
  const status = explicitStatus === 'available' && !metricsAvailable
    ? 'unavailable'
    : (explicitStatus || (metricsAvailable ? 'available' : fallbackStatus))
  return {
    calendarDays: horizonCalendarDays(source),
    status: status || 'unavailable',
    reason: reasonFrom(source) || fallbackReason || '',
    metrics,
    isCurrent: Boolean(source && firstDefined(source.is_current, source.isCurrent, false)),
    isModelMinimum: Boolean(source && firstDefined(source.is_model_minimum, source.isModelMinimum, false)),
    selectedRecurrence: source && firstDefined(source.selected_recurrence, source.selectedRecurrence, null),
  }
}

const pendingMatches = (pendingKeys, candidates) => {
  if (!pendingKeys) return false
  if (typeof pendingKeys.has === 'function') return candidates.some(key => pendingKeys.has(key))
  if (Array.isArray(pendingKeys)) return pendingKeys.some(value => candidates.includes(String(value)))
  return false
}

const scorePayload = score => score && (score.bundle || score.ai_bundle || score)

export const hasAvailableOpportunityAIScores = scores => {
  if (!scores || typeof scores !== 'object') return false
  return Object.values(scores).some(rawScore => {
    const payload = scorePayload(rawScore)
    if (!payload || typeof payload !== 'object') return false
    if (hasCompleteMetrics(metricsFrom(payload))) return true
    const horizons = firstDefined(payload.horizons, payload.checkpoints)
    return Array.isArray(horizons) && horizons.some(horizon => hasCompleteMetrics(metricsFrom(horizon)))
  })
}

/**
 * Normalize legacy flat ML scores and the checkpoint bundle contract into one
 * presentation model. All public horizon labels are inclusive calendar days.
 */
export const normalizeOpportunityAIScore = ({
  row,
  scores,
  pendingKeys,
  loading = false,
  unavailableReason = '',
}) => {
  const fullPatternCalendarDays = parseInt(row && row.daysOut, 10)
  const candidates = opportunityAIKeyCandidates(row)
  const found = findOpportunityAIScore(row, scores)
  const payload = scorePayload(found.score)
  const source = payload && payload.source && typeof payload.source === 'object'
    ? payload.source
    : {}
  const requestedBasis = String(firstDefined(payload && payload.basis, payload && payload.mode, '')).toLowerCase()
  const isMinimumHorizon = fullPatternCalendarDays >= 1 && fullPatternCalendarDays < 10
  const basis = isMinimumHorizon || [
    'minimum_horizon',
    'minimum-horizon',
    'minimum_model_horizon',
  ].includes(requestedBasis)
    ? 'minimum_horizon'
    : requestedBasis === 'duration_comparison' || requestedBasis === 'duration-comparison'
    ? 'duration_comparison'
    : requestedBasis === 'checkpoint' || requestedBasis === 'checkpoints' || requestedBasis === 'recalculated_checkpoints' || fullPatternCalendarDays > 90
      ? 'duration_comparison'
      : 'full_pattern'
  const expectedDays = basis === 'minimum_horizon'
    ? [10]
    : basis === 'duration_comparison'
    ? [...new Set([
        ...CHECKPOINT_DAYS.filter(days => days < fullPatternCalendarDays),
        ...(fullPatternCalendarDays <= 90 ? [fullPatternCalendarDays] : []),
      ])].sort((left, right) => left - right)
    : [fullPatternCalendarDays]
  const isPending = pendingMatches(pendingKeys, candidates) || (!payload && loading)
  const payloadStatus = normalizeStatus(payload && payload.status)
  const fallbackStatus = isPending || payloadStatus === 'loading' ? 'loading' : 'unavailable'
  const fallbackReason = reasonFrom(payload) || unavailableReason

  const rawHorizons = firstDefined(
    payload && payload.horizons,
    payload && payload.checkpoints,
    payload && payload.scores,
  )
  const horizonList = Array.isArray(rawHorizons)
    ? [...rawHorizons]
    : (rawHorizons && typeof rawHorizons === 'object'
      ? Object.keys(rawHorizons).map(key => ({ calendar_days: Number(key), ...rawHorizons[key] }))
      : [])

  // A bundle may provide the displayed score separately from its detail list.
  if (payload && payload.display && typeof payload.display === 'object') {
    horizonList.push({
      calendar_days: firstDefined(
        payload.display.calendar_days,
        payload.display.calendarDays,
        basis === 'minimum_horizon' ? 10 : fullPatternCalendarDays > 90 ? 90 : fullPatternCalendarDays,
      ),
      ...payload.display,
    })
  }

  // Legacy <=90 responses are one flat score object with no horizon wrapper.
  if (payload && horizonList.length === 0) {
    horizonList.push({
      calendar_days: basis === 'minimum_horizon'
        ? 10
        : fullPatternCalendarDays > 90 ? 90 : fullPatternCalendarDays,
      ...payload,
    })
  }

  const normalizedByDay = new Map()
  horizonList.forEach(horizon => {
    const normalized = normalizeHorizon(horizon, fallbackStatus, fallbackReason)
    if (normalized.calendarDays !== null) normalizedByDay.set(normalized.calendarDays, normalized)
  })

  const horizons = expectedDays.map(calendarDays => {
    if (normalizedByDay.has(calendarDays)) return normalizedByDay.get(calendarDays)
    return {
      calendarDays,
      status: fallbackStatus,
      reason: fallbackReason,
      metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null },
      isCurrent: basis !== 'minimum_horizon' && fullPatternCalendarDays <= 90 && calendarDays === fullPatternCalendarDays,
      isModelMinimum: basis === 'minimum_horizon',
      selectedRecurrence: null,
    }
  })
  const displayCalendarDays = basis === 'minimum_horizon'
    ? 10
    : fullPatternCalendarDays > 90 ? 90 : fullPatternCalendarDays
  const display = horizons.find(horizon => horizon.calendarDays === displayCalendarDays) || horizons[horizons.length - 1]

  return {
    key: found.key,
    basis,
    fullPatternCalendarDays,
    entryDate: String(firstDefined(source.date, row && row.date, '')),
    direction: String(firstDefined(source.direction, directionKey(row))).toLowerCase().startsWith('s') ? 'Short' : 'Long',
    minimumModelCalendarDays: basis === 'minimum_horizon' ? 10 : null,
    displayCalendarDays,
    display,
    horizons,
  }
}

export const opportunityAIFlatFields = bundle => {
  const available = bundle && bundle.display && bundle.display.status === 'available'
  const metrics = available ? bundle.display.metrics : {}
  return {
    ml_score: metrics.ml_score == null ? null : metrics.ml_score,
    win_prob: metrics.win_prob == null ? null : metrics.win_prob,
    pred_return: metrics.pred_return == null ? null : metrics.pred_return,
    pred_mfe: metrics.pred_mfe == null ? null : metrics.pred_mfe,
    ml_pending: Boolean(bundle && bundle.display && bundle.display.status === 'loading'),
  }
}

export const formatOpportunityAIMetric = (metric, value) => {
  if (!Number.isFinite(value)) return 'N/A'
  if (metric === 'win_prob') return `${(value * 100).toFixed(0)}%`
  if (metric === 'pred_return' || metric === 'pred_mfe') return `${value.toFixed(1)}%`
  return value.toFixed(1)
}

const AI_REASON_COPY = Object.freeze({
  after_entry: 'This current-condition score is unavailable after the pattern entry.',
  context_scoring_failed: 'AI scoring is temporarily unavailable. Try again shortly.',
  incomplete_feature_vector: 'The recalculated historical profile is incomplete for this horizon.',
  invalid_checkpoint_context: 'This checkpoint request does not contain a valid pattern identity.',
  nonfinite_pattern_profile: 'The recalculated historical profile is incomplete for this horizon.',
  pattern_profile_unavailable: 'No qualifying historical profile was available for this horizon.',
  pattern_definitions_unavailable: 'Historical pattern definitions are not available for this ticker and horizon.',
  prebuilt_profile_mismatch: 'The recalculated historical profile could not be verified for this horizon.',
  selected_recurrence_below_threshold: 'The recalculated pattern is below its selected historical requirement.',
  selected_recurrence_insufficient_history: 'The selected recurrence does not have enough completed history at this horizon.',
  provider_unavailable: 'AI scoring is temporarily unavailable. Try again shortly.',
  service_unavailable: 'AI scoring is temporarily unavailable. Try again shortly.',
  target_entry_unavailable: 'A valid price entry could not be established for this date.',
  target_price_unavailable: 'Price history is not available for this ticker.',
  tier_unavailable: 'The model for this checkpoint is temporarily unavailable.',
  too_early: 'AI scores become available closer to the pattern entry date.',
  too_far_ahead: 'AI scores become available closer to the pattern entry date.',
  unavailable: 'No AI score is available for this horizon.',
  unsupported_duration: 'This full-window duration is outside the calibrated AI range.',
  unsupported_market: 'AI scores are currently available for supported U.S. stocks and ETFs.',
  vix_blocked: 'AI scoring is paused while volatility is outside the model operating range.',
})

export const advanceOpportunityAIPollBudget = ({
  attempts = 0,
  noProgressRounds = 0,
  previousPendingCount = 0,
  nextPendingCount = 0,
  receivedScoreCount = 0,
  maxAttempts = 30,
  maxNoProgressRounds = 8,
}) => {
  const nextAttempts = attempts + 1
  const progressed = Number(receivedScoreCount) > 0 || Number(nextPendingCount) < Number(previousPendingCount)
  const nextNoProgressRounds = progressed ? 0 : noProgressRounds + 1
  return {
    attempts: nextAttempts,
    noProgressRounds: nextNoProgressRounds,
    exhausted: nextAttempts >= maxAttempts || nextNoProgressRounds >= maxNoProgressRounds,
  }
}

export const opportunityAIReasonCopy = reason => {
  const value = String(reason || '').trim()
  if (!value) return 'No AI score is available for this horizon.'
  const key = value.toLowerCase()
  if (AI_REASON_COPY[key]) return AI_REASON_COPY[key]
  if (value.includes(' ')) return value
  return 'AI scoring is temporarily unavailable. Try again shortly.'
}

export const opportunityAICompactStatus = horizon => {
  if (!horizon) return 'Temporarily unavailable'
  if (horizon.status === 'below_threshold') return 'Below threshold'
  const reason = String(horizon.reason || '').toLowerCase()
  if (reason.includes('insufficient_history') || reason.includes('not enough')) return 'Not enough history'
  if (reason === 'too_early' || reason === 'too_far_ahead') return 'Not available yet'
  return 'Temporarily unavailable'
}

export const shouldShowCheckpointCoachmark = ({ hasAI, seen, bundle, visible }) => Boolean(
  hasAI &&
  !seen &&
  visible &&
  bundle &&
  bundle.basis === 'duration_comparison' &&
  Array.isArray(bundle.horizons) &&
  bundle.horizons.length > 1 &&
  bundle.display &&
  bundle.display.status === 'available'
)
