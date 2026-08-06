const {
  AI_COLUMNS,
  AI_DURATION_OUTLINE_DESCRIPTION,
  advanceOpportunityAIPollBudget,
  findOpportunityAIScore,
  formatOpportunityAIMetric,
  normalizeOpportunityAIScore,
  opportunityAIFlatFields,
  opportunityAIHeaderColor,
  opportunityAIHeaderTooltip,
  opportunityAIShortHeaderTooltip,
  opportunityAILegacyKey,
  opportunityAIReasonCopy,
  opportunityTableMinimumWidth,
  selectOpportunityVisibleColumns,
  shouldShowCheckpointCoachmark,
} = require('./opportunityAIScores')

const fullRow = { symbol: 'AAPL', date: '2026-08-05', daysOut: 45, lOrS: 'Long' }
const longRow = { symbol: 'MSFT', date: '2026-08-05', daysOut: 120, lOrS: 'Short' }

test('keeps the established green AI column headings in both themes', () => {
  expect(opportunityAIHeaderColor('light')).toBe('rgb(22, 163, 74)')
  expect(opportunityAIHeaderColor('dark')).toBe('rgb(100, 220, 140)')
})

test('keeps legacy flat scores compatible for a full-window pattern', () => {
  const scores = {
    'AAPL|44|l': { ml_score: 0, win_prob: 0.61, pred_return: -1.2, pred_mfe: 4.5 },
  }
  const bundle = normalizeOpportunityAIScore({ row: fullRow, scores })

  expect(opportunityAILegacyKey(fullRow)).toBe('AAPL|44|l')
  expect(bundle).toMatchObject({
    basis: 'full_pattern',
    fullPatternCalendarDays: 45,
    displayCalendarDays: 45,
    display: { calendarDays: 45, status: 'available' },
  })
  expect(bundle.horizons).toHaveLength(1)
  expect(opportunityAIFlatFields(bundle)).toMatchObject({
    ml_score: 0,
    win_prob: 0.61,
    pred_return: -1.2,
    pred_mfe: 4.5,
    ml_pending: false,
  })
})

test('labels a short historical pattern with the ten-day AI model minimum', () => {
  const row = { symbol: 'AAPL', date: '2026-08-05', daysOut: 6, lOrS: 'Long' }
  const scores = {
    'AAPL|2026-08-05|5|l': {
      basis: 'minimum_model_horizon',
      full_pattern_calendar_days: 6,
      display_horizon_days: 10,
      source: { date: '2026-08-05', direction: 'l', calendar_days: 6 },
      horizons: [{
        calendar_days: 10,
        daysOut: 9,
        status: 'available',
        is_model_minimum: true,
        ml_score: 73,
        win_prob: 0.69,
        pred_return: 2.5,
        pred_mfe: 4.9,
      }],
    },
  }

  const bundle = normalizeOpportunityAIScore({ row, scores })

  expect(bundle).toMatchObject({
    basis: 'minimum_horizon',
    fullPatternCalendarDays: 6,
    minimumModelCalendarDays: 10,
    displayCalendarDays: 10,
    display: {
      calendarDays: 10,
      status: 'available',
      isCurrent: false,
      isModelMinimum: true,
    },
  })
  expect(bundle.horizons).toHaveLength(1)
  expect(opportunityAIFlatFields(bundle)).toMatchObject({
    ml_score: 73,
    win_prob: 0.69,
    pred_return: 2.5,
    pred_mfe: 4.9,
    ml_pending: false,
  })
  expect(shouldShowCheckpointCoachmark({ hasAI: true, seen: false, visible: true, bundle })).toBe(false)
})

test('shows a pending short row at the ten-day minimum before a score arrives', () => {
  const row = { symbol: 'AAPL', date: '2026-08-05', daysOut: 4, lOrS: 'Long' }
  const bundle = normalizeOpportunityAIScore({
    row,
    scores: {},
    pendingKeys: new Set(['AAPL|3|l']),
    loading: true,
  })

  expect(bundle).toMatchObject({
    basis: 'minimum_horizon',
    fullPatternCalendarDays: 4,
    displayCalendarDays: 10,
    display: { calendarDays: 10, status: 'loading', isCurrent: false },
  })
})

test('all AI heading tooltips explain the outline and short-pattern minimum in plain language', () => {
  AI_COLUMNS.forEach(metric => {
    const tooltip = opportunityAIHeaderTooltip(metric)
    expect(tooltip).toContain(AI_DURATION_OUTLINE_DESCRIPTION)
    expect(tooltip).toMatch(/shorter than 10 days.*10-day AI reading/i)
    expect(tooltip).not.toMatch(/horizon|feature vector|recurrence|profile/i)
  })
})

test('AI headings give compact explanations that say how to read each number', () => {
  expect(opportunityAIShortHeaderTooltip('ml_score'))
    .toBe('0-100 rank of the AI-estimated ending return. Not a win chance.')
  expect(opportunityAIShortHeaderTooltip('win_prob'))
    .toBe('AI-calibrated chance of a profitable result.')
  expect(opportunityAIShortHeaderTooltip('pred_return'))
    .toBe('Estimated return when this time window ends.')
  expect(opportunityAIShortHeaderTooltip('pred_mfe'))
    .toBe('Estimated best move during this time window. Not a target.')
})

test('normalizes long-pattern checkpoints and always displays the 90-day reading', () => {
  const scores = {
    'MSFT|2026-08-05|119|s': {
      basis: 'checkpoint',
      full_pattern_calendar_days: 120,
      horizons: [
        { calendar_days: 30, status: 'available', ai_score: 51, win_probability: 0.52, predicted_return_pct: 1, predicted_mfe_pct: 3 },
        { calendar_days: 60, status: 'available', ai_score: 63, win_probability: 0.64, predicted_return_pct: 2, predicted_mfe_pct: 5 },
        { calendar_days: 90, status: 'available', ai_score: 78, win_probability: 0.73, predicted_return_pct: 4, predicted_mfe_pct: 8 },
      ],
    },
  }
  const bundle = normalizeOpportunityAIScore({ row: longRow, scores })

  expect(bundle.horizons.map(item => item.calendarDays)).toEqual([30, 60, 90])
  expect(bundle.display.metrics).toEqual({ ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 })
  expect(bundle).toMatchObject({ entryDate: '2026-08-05', direction: 'Short' })
  expect(opportunityAIFlatFields(bundle).ml_score).toBe(78)
})

test('pins the inclusive 90/91 calendar-day UI boundary', () => {
  const atLimit = normalizeOpportunityAIScore({
    row: { symbol: 'AAPL', date: '2026-08-05', daysOut: 90, lOrS: 'Long' },
    scores: { 'AAPL|89|l': { ml_score: 60, win_prob: 0.6, pred_return: 2, pred_mfe: 4 } },
  })
  const beyondLimit = normalizeOpportunityAIScore({
    row: { symbol: 'AAPL', date: '2026-08-05', daysOut: 91, lOrS: 'Long' },
    scores: {
      'AAPL|2026-08-05|90|l': {
        basis: 'recalculated_checkpoints',
        source: { date: '2026-08-05', direction: 'l' },
        horizons: [
          { calendar_days: 30, ml_score: 30, win_prob: 0.5, pred_return: 1, pred_mfe: 2 },
          { calendar_days: 60, ml_score: 50, win_prob: 0.6, pred_return: 2, pred_mfe: 3 },
          { calendar_days: 90, ml_score: 70, win_prob: 0.7, pred_return: 3, pred_mfe: 5 },
        ],
      },
    },
  })

  expect(atLimit).toMatchObject({ basis: 'full_pattern', displayCalendarDays: 90 })
  expect(atLimit.horizons.map(item => item.calendarDays)).toEqual([90])
  expect(beyondLimit).toMatchObject({ basis: 'duration_comparison', displayCalendarDays: 90 })
  expect(beyondLimit.horizons.map(item => item.calendarDays)).toEqual([30, 60, 90])
})

test('does not substitute an available shorter checkpoint when 90 days is loading', () => {
  const scores = {
    'MSFT|2026-08-05|119|s': {
      mode: 'checkpoints',
      horizons: [
        { calendar_days: 30, ml_score: 51, win_prob: 0.52, pred_return: 1, pred_mfe: 3 },
        { calendar_days: 60, ml_score: 63, win_prob: 0.64, pred_return: 2, pred_mfe: 5 },
        { calendar_days: 90, status: 'loading' },
      ],
    },
  }
  const bundle = normalizeOpportunityAIScore({ row: longRow, scores })

  expect(bundle.display).toMatchObject({ calendarDays: 90, status: 'loading' })
  expect(opportunityAIFlatFields(bundle)).toMatchObject({ ml_score: null, ml_pending: true })
})

test('an 85-day comparison keeps 85 current and never invents a 90-day horizon', () => {
  const row = { symbol: 'AAPL', date: '2026-08-05', daysOut: 85, lOrS: 'Long' }
  const scores = {
    'AAPL|2026-08-05|84|l': {
      basis: 'duration_comparison',
      source: { date: '2026-08-05', direction: 'l' },
      horizons: [
        { calendar_days: 30, status: 'available', ml_score: 51, win_prob: 0.52, pred_return: 1, pred_mfe: 3 },
        {
          calendar_days: 60,
          status: 'available',
          ml_score: 63,
          win_prob: 0.64,
          pred_return: 2,
          pred_mfe: 5,
          selected_recurrence: {
            status: 'below_threshold',
            sample_size: 10,
            positive_years: 7,
            required_positive_years: 9,
            requested_observations: 10,
          },
        },
        { calendar_days: 85, status: 'available', is_current: true, ml_score: 74, win_prob: 0.68, pred_return: 2.4, pred_mfe: 5.2 },
      ],
    },
  }

  const bundle = normalizeOpportunityAIScore({ row, scores })

  expect(bundle).toMatchObject({
    basis: 'duration_comparison',
    displayCalendarDays: 85,
    display: { calendarDays: 85, status: 'available', isCurrent: true },
  })
  expect(bundle.horizons.map(item => item.calendarDays)).toEqual([30, 60, 85])
  expect(bundle.horizons[1]).toMatchObject({
    status: 'available',
    metrics: { ml_score: 63, win_prob: 0.64, pred_return: 2, pred_mfe: 5 },
    selectedRecurrence: { positive_years: 7, required_positive_years: 9 },
  })
  expect(opportunityAIFlatFields(bundle).ml_score).toBe(74)
})

test('represents terminal unavailability explicitly and never treats partial metrics as available', () => {
  const scores = {
    'MSFT|2026-08-05|119|s': {
      basis: 'checkpoint',
      status: 'unavailable',
      reason: 'pattern_profile_unavailable',
      horizons: [
        { calendar_days: 90, status: 'available', ml_score: 72 },
      ],
    },
  }
  const bundle = normalizeOpportunityAIScore({ row: longRow, scores })

  expect(bundle.display).toMatchObject({
    calendarDays: 90,
    status: 'unavailable',
    reason: 'pattern_profile_unavailable',
  })
  expect(opportunityAIFlatFields(bundle).ml_score).toBeNull()
})

test('uses a structured backend error code instead of stringifying the error object', () => {
  const bundle = normalizeOpportunityAIScore({
    row: longRow,
    scores: {
      'MSFT|2026-08-05|119|s': {
        basis: 'recalculated_checkpoints',
        horizons: [{
          calendar_days: 90,
          status: 'unavailable',
          error: { code: 'pattern_profile_unavailable', message: 'internal detail', retryable: false },
        }],
      },
    },
  })

  expect(bundle.display.reason).toBe('pattern_profile_unavailable')
  expect(bundle.display.reason).not.toBe('[object Object]')
})

test('matches a date-qualified bundle key before falling back to the legacy key', () => {
  const scores = {
    'AAPL|2026-08-05|44|l': { ml_score: 80, win_prob: 0.7, pred_return: 2, pred_mfe: 4 },
    'AAPL|44|l': { ml_score: 20, win_prob: 0.4, pred_return: -2, pred_mfe: 1 },
  }

  expect(findOpportunityAIScore(fullRow, scores).key).toBe('AAPL|2026-08-05|44|l')
})

test('never steals an adjacent displayed duration through a raw-offset key collision', () => {
  const missing45DayRow = { symbol: 'AAPL', date: '2026-08-05', daysOut: 45, lOrS: 'Long' }
  const scores = {
    // This is the legitimate raw offset for a different displayed 46-day row.
    'AAPL|2026-08-05|45|l': { ml_score: 99, win_prob: 0.99, pred_return: 9, pred_mfe: 12 },
    'AAPL|45|l': { ml_score: 98, win_prob: 0.98, pred_return: 8, pred_mfe: 11 },
  }

  expect(findOpportunityAIScore(missing45DayRow, scores).score).toBeNull()
})

test('formats all four metrics and preserves numeric zero', () => {
  expect(formatOpportunityAIMetric('ml_score', 0)).toBe('0.0')
  expect(formatOpportunityAIMetric('win_prob', 0.625)).toBe('63%')
  expect(formatOpportunityAIMetric('pred_return', -1.25)).toBe('-1.3%')
  expect(formatOpportunityAIMetric('pred_mfe', null)).toBe('N/A')
})

test('only offers the coachmark for the first unseen available checkpoint surface', () => {
  const bundle = normalizeOpportunityAIScore({
    row: longRow,
    scores: {
      'MSFT|2026-08-05|119|s': {
        basis: 'checkpoint',
        horizons: [{ calendar_days: 90, ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 }],
      },
    },
  })

  expect(shouldShowCheckpointCoachmark({ hasAI: true, seen: false, visible: true, bundle })).toBe(true)
  expect(shouldShowCheckpointCoachmark({ hasAI: true, seen: true, visible: true, bundle })).toBe(false)
  expect(shouldShowCheckpointCoachmark({ hasAI: false, seen: false, visible: true, bundle })).toBe(false)
})

test('phone portrait keeps a compact core plus configured Win% and PredR defaults', () => {
  const columns = selectOpportunityVisibleColumns({
    columnOrder: ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'],
    showSR2: false,
    hasAI: true,
    mlEnabled: true,
    isMobilePortrait: true,
    columnVisibility: { ml_score: false, win_prob: true, pred_return: true, pred_mfe: false },
  })

  expect(columns).toEqual(['symbol', 'daysOut', 'sharpe_ratio', 'win_prob', 'pred_return'])
  expect(opportunityTableMinimumWidth({ columns, isMobilePortrait: true })).toBeLessThanOrEqual(390)
})

test('all four configured AI columns still fit the compact 390px portrait table', () => {
  const columns = selectOpportunityVisibleColumns({
    columnOrder: ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'],
    showSR2: false,
    hasAI: true,
    mlEnabled: true,
    marketEligible: true,
    isMobilePortrait: true,
    columnVisibility: { ml_score: true, win_prob: true, pred_return: true, pred_mfe: true },
  })

  expect(columns).toEqual(['symbol', 'daysOut', 'sharpe_ratio', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'])
  expect(opportunityTableMinimumWidth({ columns, isMobilePortrait: true })).toBeLessThanOrEqual(390)
})

test('market and tier gating preserve the configured locked teaser visibility', () => {
  const base = {
    columnOrder: ['symbol', 'daysOut', 'sharpe_ratio', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'],
    showSR2: false,
    isMobilePortrait: true,
    columnVisibility: { ml_score: false, win_prob: true, pred_return: true, pred_mfe: true },
  }

  expect(selectOpportunityVisibleColumns({ ...base, hasAI: true, mlEnabled: false, marketEligible: true }))
    .toEqual(['symbol', 'daysOut', 'sharpe_ratio'])
  expect(selectOpportunityVisibleColumns({ ...base, hasAI: false, mlEnabled: false, marketEligible: true }))
    .toEqual(['symbol', 'daysOut', 'sharpe_ratio'])
  expect(selectOpportunityVisibleColumns({
    ...base,
    hasAI: false,
    mlEnabled: false,
    marketEligible: true,
    columnVisibility: { ...base.columnVisibility, ml_score: true },
  })).toEqual(['symbol', 'daysOut', 'sharpe_ratio', 'ml_score'])
  expect(selectOpportunityVisibleColumns({ ...base, hasAI: false, mlEnabled: false, marketEligible: false }))
    .toEqual(['symbol', 'daysOut', 'sharpe_ratio'])
})

test('polling becomes a terminal unavailable state after bounded no-progress responses', () => {
  let state = { attempts: 0, noProgressRounds: 0 }
  for (let round = 0; round < 8; round += 1) {
    state = advanceOpportunityAIPollBudget({
      ...state,
      previousPendingCount: 5,
      nextPendingCount: 5,
      receivedScoreCount: 0,
    })
  }
  expect(state).toMatchObject({ attempts: 8, noProgressRounds: 8, exhausted: true })

  const recovered = advanceOpportunityAIPollBudget({
    attempts: 4,
    noProgressRounds: 3,
    previousPendingCount: 5,
    nextPendingCount: 4,
    receivedScoreCount: 1,
  })
  expect(recovered).toMatchObject({ attempts: 5, noProgressRounds: 0, exhausted: false })
})

test('stable unavailable codes become useful plain-language explanations without backend jargon', () => {
  expect(opportunityAIReasonCopy('pattern_definitions_unavailable')).toMatch(/historical pattern data/i)
  expect(opportunityAIReasonCopy('prebuilt_profile_mismatch')).toMatch(/could not verify the data/i)
  expect(opportunityAIReasonCopy('target_entry_unavailable')).toMatch(/starting price/i)
  expect(opportunityAIReasonCopy('target_price_unavailable')).toMatch(/price history/i)
  expect(opportunityAIReasonCopy('invalid_checkpoint_context')).toMatch(/could not verify the data/i)
  expect(opportunityAIReasonCopy('context_scoring_failed')).toMatch(/temporarily unavailable/i)

  const userFacingReasons = [
    'incomplete_feature_vector',
    'nonfinite_pattern_profile',
    'prebuilt_profile_mismatch',
    'selected_recurrence_below_threshold',
    'invalid_checkpoint_context',
  ].map(opportunityAIReasonCopy).join(' ')
  expect(userFacingReasons).not.toMatch(/feature vector|nonfinite|profile|recurrence|checkpoint/i)
  expect(opportunityAIReasonCopy('opaque_internal_failure_detail')).toBe(
    'AI scoring is temporarily unavailable. Try again shortly.'
  )
})
