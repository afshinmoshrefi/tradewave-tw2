export const AI_COLUMNS = ['ml_score', 'win_prob', 'pred_return', 'pred_mfe']

// Keep optional AI columns easy to spot in either theme with the established
// Opportunity Table header green.
export const opportunityAIHeaderColor = theme => (
  theme === 'dark' ? 'rgb(100, 220, 140)' : 'rgb(22, 163, 74)'
)

export const AI_METRICS = Object.freeze({
  ml_score: Object.freeze({
    shortLabel: 'AIS',
    label: 'AI Score',
    shortDescription: '0-100 rank of the AI-estimated ending return. Not a win chance.',
    description: 'Ranks this estimated ending return against other AI readings for similar time lengths. Higher means it ranks above more readings in that group. AIS is not Win%, a confidence grade, or a promise.',
  }),
  win_prob: Object.freeze({
    shortLabel: 'Win%',
    label: 'AI Win%',
    shortDescription: 'AI-calibrated chance of a profitable result.',
    description: 'Among older cases with similar AI estimates, this is the share that later finished profitable in the Long or Short direction shown. TradeWave checks it against real outcomes, but it cannot predict the next result with certainty.',
  }),
  pred_return: Object.freeze({
    shortLabel: 'PredR',
    label: 'Predicted Ending Return',
    shortDescription: 'Estimated return when this time window ends.',
    description: 'The AI-estimated percentage return at the end of this time window. A positive number favors the selected direction: a rise for Long or a decline for Short. It is an estimate, not a promised return.',
  }),
  pred_mfe: Object.freeze({
    shortLabel: 'PMFE',
    label: 'Estimated Best Move',
    shortDescription: 'Estimated best move during this time window. Not a target.',
    description: 'The AI-estimated best move in the selected Long or Short direction before the window ends. It does not say when that move may happen, and it is not a price target or exit instruction.',
  }),
})

const CHECKPOINT_DAYS = [30, 60, 90]
const REQUIRED_OPPORTUNITY_COLUMNS = new Set(['symbol', 'daysOut', 'sharpe_ratio'])
// Phone portrait shows the decision-grade columns only. Membership, not order -
// the rendered order still follows columnOrder, which keeps Price last.
const MOBILE_OPPORTUNITY_COLUMNS = new Set(['symbol', 'date', 'daysOut', 'lOrS', 'avg_profit', 'sharpe_ratio', 'price'])

// One definition of "phone portrait" for the opportunity table. Re-deriving this
// inline per component is what let the mobile column set and the column selector
// drift apart in the first place.
export const isPhonePortrait = (rdd, height, width) => Boolean(
  rdd && rdd.isMobile && !rdd.isTablet && height > width
)

// Phone portrait always drops the year (MM-DD): the full YYYY-MM-DD does not fit
// beside six other columns, the "Short Dates" toggle lives only in DesktopLayout
// (never mounted on a phone, so a phone user cannot reach it), and the opportunity
// table's controls row already prints the year once. The persisted preference is
// never mutated - this only widens where it applies.
export const resolveOpportunityShortDates = ({ shortDates, phonePortrait }) => (
  Boolean(shortDates) || Boolean(phonePortrait)
)
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
  date: 48, // always MM-DD on a phone, see resolveOpportunityShortDates
  daysOut: 45,
  lOrS: 38,
  avg_profit: 50,
  sharpe_ratio: 45,
  price: 52,
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
  'too_far_ahead',
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
      return column === 'ml_score' && Boolean(columnVisibility && columnVisibility[column] === true)
    }
    if (!mlEnabled) return false
    return Boolean(columnVisibility && columnVisibility[column] === true)
  }
  if (isMobilePortrait) return MOBILE_OPPORTUNITY_COLUMNS.has(column)
  if (REQUIRED_OPPORTUNITY_COLUMNS.has(column)) return true
  return !columnVisibility || columnVisibility[column] !== false
})

// A terminal reason applies to every AI metric for the displayed horizon.
export const opportunityTableCellLayout = columns => {
  const individual = columns.map(key => ({ key, span: 1 }))
  const unavailable = []
  for (const key of columns) {
    const last = unavailable[unavailable.length - 1]
    if (last && AI_COLUMNS.includes(last.key) && AI_COLUMNS.includes(key)) {
      last.span += 1
    } else {
      unavailable.push({ key, span: 1 })
    }
  }
  return { individual, unavailable }
}

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
  const error = source?.error
  const legacyStatus = TERMINAL_UNAVAILABLE.has(source?.status) ? source.status : ''
  return String(
    source?.reason || error?.code || (source?.vix_blocked === true ? 'vix_blocked' : '') ||
    (typeof error === 'string' ? error : error?.message) || source?.message || legacyStatus
  )
}

// Older vix_blocked responses omit the cutoff. Their deployed scorer uses 35.
const LEGACY_VIX_CUTOFF = 35

const reportedVixCutoff = source => {
  const error = source?.error
  const message = typeof error === 'string' ? error : error?.message
  const fromMessage = typeof message === 'string'
    ? message.match(/\bexceeds cutoff \((\d+(?:\.\d+)?)\)/i)?.[1]
    : undefined
  return [source?.vix_cutoff, source?.scorer?.vix_cutoff, error?.vix_cutoff, fromMessage]
    .filter(value => typeof value === 'number' || typeof value === 'string')
    .map(numberOrNull)
    .find(value => value > 0)
}

export const opportunityVixRecovery = horizon =>
  `Scores resume at a close of ${horizon?.vixCutoff ?? LEGACY_VIX_CUTOFF} or lower`

// The VIX close and its date come from the scorer's volatility gate (the same
// source that pauses scoring): structured fields first, then the gate's own
// "VIX=41.2 exceeds cutoff (35)" text, then the scorer's data date.
const reportedVixValue = source => {
  const error = source?.error
  const message = typeof error === 'string' ? error : error?.message
  const fromMessage = typeof message === 'string'
    ? message.match(/\bVIX\s*=\s*(\d+(?:\.\d+)?)/i)?.[1]
    : undefined
  return [source?.vix_value, error?.vix_value, source?.vix, error?.vix, fromMessage]
    .filter(value => typeof value === 'number' || typeof value === 'string')
    .map(numberOrNull)
    .find(value => value > 0 && value < 1000)
}

const reportedVixDate = source => {
  const error = source?.error
  return [source?.vix_date, error?.vix_date, source?.scorer?.data_as_of]
    .map(value => String(value || '').slice(0, 10))
    .find(value => /^\d{4}-\d{2}-\d{2}$/.test(value))
}

const formatVixNumber = value => {
  const number = Number(value)
  return Number.isFinite(number) ? String(Math.round(number * 100) / 100) : ''
}

const formatVixDate = isoDate => {
  if (!isoDate) return ''
  const [year, month, day] = isoDate.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('en-US', { timeZone: 'UTC', month: 'long', day: 'numeric', year: 'numeric' })
}

export const OPPORTUNITY_VIX_PAUSED_TITLE = 'AI scoring is paused while volatility is high'

export const opportunityVixPausedCopy = horizon => {
  const limit = formatVixNumber(horizon?.vixCutoff ?? LEGACY_VIX_CUTOFF)
  const value = horizon?.vixValue == null ? '' : formatVixNumber(horizon.vixValue)
  const date = value ? formatVixDate(horizon?.vixDate) : ''
  const opening = value
    ? `The VIX closed at ${value}${date ? ` on ${date}` : ''}, above the scoring limit of ${limit}.`
    : `The latest VIX close is above the scoring limit of ${limit}.`
  return `${opening} AI readings are paused for all patterns and resume once the VIX closes at ${limit} or lower.`
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
    vixCutoff: reportedVixCutoff(source),
    vixValue: reportedVixValue(source),
    vixDate: reportedVixDate(source),
    metrics,
    isCurrent: Boolean(source && firstDefined(source.is_current, source.isCurrent, false)),
    isModelMinimum: Boolean(source && firstDefined(source.is_model_minimum, source.isModelMinimum, false)),
    selectedRecurrence: source && firstDefined(source.selected_recurrence, source.selectedRecurrence, null),
    scorer: source && source.scorer && typeof source.scorer === 'object' ? source.scorer : null,
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

const scoreProgressValue = rawScore => {
  const payload = scorePayload(rawScore)
  if (!payload || typeof payload !== 'object') return null
  const compactHorizon = horizon => ({
    days: firstDefined(horizon && horizon.calendar_days, horizon && horizon.calendarDays, horizon && horizon.daysOut),
    status: String(firstDefined(horizon && horizon.status, '')),
    reason: reasonFrom(horizon),
    metrics: metricsFrom(horizon),
  })
  const horizons = firstDefined(payload.horizons, payload.checkpoints, [])
  return {
    status: String(firstDefined(payload.status, '')),
    displayStatus: String(firstDefined(payload.display_status, payload.display && payload.display.status, '')),
    metrics: metricsFrom(payload),
    display: payload.display ? compactHorizon(payload.display) : null,
    horizons: Array.isArray(horizons) ? horizons.map(compactHorizon) : [],
  }
}

// Poll responses may repeat the same partial/loading bundle while a provider is
// unavailable. Ignore timestamps and other metadata so identical responses do
// not falsely reset the no-progress guard forever.
export const opportunityAIScoreProgressSignature = scores => JSON.stringify(
  Object.keys(scores && typeof scores === 'object' ? scores : {})
    .sort()
    .map(key => [key, scoreProgressValue(scores[key])]),
)

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

  // The volatility gate applies across checkpoints. Some legacy bundles report
  // the cutoff only in a checkpoint error, separate from the display horizon.
  let vixCutoff = reportedVixCutoff(payload)
  let vixValue = reportedVixValue(payload)
  let vixDate = reportedVixDate(payload)
  const normalizedByDay = new Map()
  horizonList.forEach(horizon => {
    const normalized = normalizeHorizon(horizon, fallbackStatus, fallbackReason)
    vixCutoff = vixCutoff ?? normalized.vixCutoff
    vixValue = vixValue ?? normalized.vixValue
    vixDate = vixDate ?? normalized.vixDate
    if (normalized.calendarDays !== null) normalizedByDay.set(normalized.calendarDays, normalized)
  })

  const horizons = expectedDays.map(calendarDays => {
    const horizon = normalizedByDay.get(calendarDays)
    if (horizon) {
      return {
        ...horizon,
        vixCutoff: horizon.vixCutoff ?? vixCutoff,
        vixValue: horizon.vixValue ?? vixValue,
        vixDate: horizon.vixDate ?? vixDate,
      }
    }
    return {
      calendarDays,
      vixCutoff,
      vixValue,
      vixDate,
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
  const scorer = firstDefined(
    payload && payload.scorer,
    display && display.scorer,
    ...horizons.map(horizon => horizon.scorer),
  )
  const normalizedScorer = scorer && typeof scorer === 'object' ? {
    dataAsOf: String(firstDefined(scorer.data_as_of, scorer.latest_data_date, '')),
    modelRelease: String(firstDefined(scorer.model_release, scorer.model_version, '')),
  } : null

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
    scorer: normalizedScorer,
    dataAsOf: normalizedScorer ? normalizedScorer.dataAsOf : '',
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
  after_entry: {
    label: 'Pattern already started',
    detail: 'AI Scores combine historical patterns with current market data. Current data includes information from after this pattern started, so it cannot provide a new estimate of conditions at entry. Historical results remain available.',
  },
  context_scoring_failed: {
    label: 'Scoring unavailable',
    detail: 'AI scoring is temporarily unavailable. Try again shortly.',
  },
  incomplete_feature_vector: {
    label: 'Missing model data',
    detail: 'TradeWave does not have all the data needed to score this time length.',
  },
  invalid_checkpoint_context: {
    label: 'Pattern data unverified',
    detail: 'TradeWave could not verify the data for this time length.',
  },
  nonfinite_pattern_profile: {
    label: 'Incomplete pattern history',
    detail: 'TradeWave does not have all the data needed to score this time length.',
  },
  pattern_profile_unavailable: {
    label: 'Not enough history',
    detail: 'There is not enough usable history to score this time length.',
  },
  pattern_definitions_unavailable: {
    label: 'Missing pattern history',
    detail: 'TradeWave does not have the historical pattern data needed for this ticker and time length.',
  },
  prebuilt_profile_mismatch: {
    label: 'Pattern data unverified',
    detail: 'TradeWave could not verify the data for this time length.',
  },
  selected_recurrence_below_threshold: {
    label: 'History filter not met',
    detail: 'This time length does not pass your history filter.',
  },
  selected_recurrence_insufficient_history: {
    label: 'Not enough history',
    detail: 'There is not enough completed history to check this time length.',
  },
  provider_unavailable: {
    label: 'Scorer unavailable',
    detail: 'AI scoring is temporarily unavailable. Try again shortly.',
  },
  service_unavailable: {
    label: 'Scoring unavailable',
    detail: 'AI scoring is temporarily unavailable. Try again shortly.',
  },
  target_entry_unavailable: {
    label: 'No entry price',
    detail: 'A starting price is not available for this date.',
  },
  target_price_unavailable: {
    label: 'Missing price history',
    detail: 'TradeWave does not have enough price history for this ticker.',
  },
  tier_unavailable: {
    label: 'Model unavailable',
    detail: 'The AI model for this time length is temporarily unavailable.',
  },
  too_early: {
    label: 'Entry over 5 days away',
    detail: 'AI Scores combine historical patterns with current market data, and current conditions may change before entry. Check back within five calendar days of the pattern start.',
  },
  too_far_ahead: {
    label: 'Entry over 5 days away',
    detail: 'AI Scores combine historical patterns with current market data, and current conditions may change before entry. Check back within five calendar days of the pattern start.',
  },
  unavailable: {
    label: 'Reason unavailable',
    detail: 'No AI score is available for this time length.',
  },
  unsupported_duration: {
    label: 'Unsupported duration',
    detail: 'AI models cover time lengths from 10 through 90 calendar days.',
  },
  unsupported_market: {
    label: 'Market outside coverage',
    detail: 'AI Scores are available only for U.S. stocks and ETFs.',
  },
  vix_blocked: {
    label: 'High volatility (VIX)',
    detail: 'The latest daily close of the volatility index (VIX) is above the scoring limit.',
  },
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

export const opportunityAIRetryDelayMs = attempt => {
  const safeAttempt = Math.max(0, Math.min(Number.parseInt(attempt, 10) || 0, 5))
  return Math.min(15000 * (2 ** safeAttempt), 300000)
}

export const opportunityAIReasonCopy = (reason, horizon) => {
  const value = String(reason || '').trim()
  if (!value) return 'No AI score is available for this time length.'
  const key = value.toLowerCase()
  if (key === 'vix_blocked') return opportunityVixPausedCopy(horizon)
  if (AI_REASON_COPY[key]?.detail) return AI_REASON_COPY[key].detail
  return 'AI scoring is temporarily unavailable. Try again shortly.'
}

export const opportunityAIIsUnavailable = horizon => (
  !horizon || horizon.status === 'unavailable' || horizon.status === 'below_threshold'
)

export const opportunityAICompactStatus = horizon => {
  if (horizon?.status === 'below_threshold') return 'History filter not met'
  const reason = String(horizon?.reason || '').trim().toLowerCase()
  const label = AI_REASON_COPY[reason]?.label
  if (label) return label
  if (reason.includes('insufficient_history') || reason.includes('not enough')) return 'Not enough history'
  return 'Reason unavailable'
}
