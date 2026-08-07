const {
  buildOpportunityViewerAIRequest,
  createOpportunityAISelectionAnchor,
  opportunityAISelectionMatchesViewer,
  selectOpportunityAIPanelSelection,
  shouldInvalidateOpportunityAIAnchor,
  terminalizeOpportunityViewerScores,
} = require('./opportunityViewerAIScore')

const selectedRow = {
  symbol: 'CAT',
  date: '2026-08-07',
  daysOut: 166,
  lOrS: 'Short',
  avg_profit: 4.2,
  sharpe_ratio: 1.8,
}

const anchor = createOpportunityAISelectionAnchor({
  row: selectedRow,
  market: 'S&P 500',
  years: '10',
  partialYears: '9',
  mode: 'consecutive',
})

test('keeps an exact viewer identity on the Opportunity Table score channel', () => {
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 166,
  })

  expect(selection).toMatchObject({ origin: 'opportunity_table', row: selectedRow })
})

test('changes only inclusive calendar days for a viewer-duration score', () => {
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 150,
  })

  expect(selection).toMatchObject({
    origin: 'wave_viewer',
    row: {
      symbol: 'CAT',
      date: '2026-08-07',
      daysOut: 150,
      lOrS: 'Short',
      avg_profit: null,
      sharpe_ratio: null,
    },
  })

  const request = buildOpportunityViewerAIRequest({ selection, resourceId: 0 })
  expect(request.requestKey).toBe('0|CAT|2026-08-07|149|s|10|9|consecutive')
  expect(request.body).toEqual({
    request_origin: 'wave_viewer',
    opportunities: [{
      symbol: 'CAT',
      date: '2026-08-07',
      daysOut: 149,
      direction: 's',
      years: '10',
      partial: { min_winning_years: '9', mode: 'consecutive' },
      mode: 'consecutive',
      selection_origin: 'user_defined',
    }],
    table_context: {
      years: '10',
      partial: { min_winning_years: '9', mode: 'consecutive' },
      mode: 'consecutive',
      date: '2026-08-07',
      is_default: false,
    },
  })
})

test('fails closed when a non-Buy-and-Hold history cohort changes', () => {
  expect(selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 166,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
  })).toBeNull()
})

test('keeps a selected symbol scoreable when Buy & Hold changes its date and forces Long', () => {
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-01-01',
    calendarDays: 366,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  })

  expect(selection).toMatchObject({
    origin: 'wave_viewer',
    row: {
      symbol: 'CAT',
      date: '2026-01-01',
      daysOut: 366,
      lOrS: 'Long',
    },
    context: {
      years: '63',
      yearCount: '63',
      partialYears: null,
      isBuyAndHold: true,
    },
  })

  const request = buildOpportunityViewerAIRequest({ selection, resourceId: '2' })
  expect(request.body.opportunities[0]).toMatchObject({
    date: '2026-01-01',
    daysOut: 365,
    direction: 'l',
    years: '63',
    partial: null,
  })
})

test('keeps canonical Buy & Hold isolated even when it matches a table date and duration', () => {
  const buyHoldRow = {
    ...selectedRow,
    date: '2026-01-01',
    daysOut: 366,
    lOrS: 'Short',
  }
  const buyHoldAnchor = createOpportunityAISelectionAnchor({
    row: buyHoldRow,
    market: 'S&P 500',
    years: '10',
    partialYears: '9',
    mode: 'consecutive',
  })
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [buyHoldRow],
    anchor: buyHoldAnchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-01-01',
    calendarDays: 366,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  })

  expect(selection).toMatchObject({
    origin: 'wave_viewer',
    row: { lOrS: 'Long' },
    context: { years: '63', partialYears: null, isBuyAndHold: true },
  })
})

test('uses 367 inclusive days for leap-year Buy & Hold and sends engine offset 366', () => {
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2028-01-01',
    calendarDays: 367,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  })
  const request = buildOpportunityViewerAIRequest({ selection, resourceId: '2' })

  expect(request.body.opportunities[0]).toMatchObject({
    date: '2028-01-01',
    daysOut: 366,
    direction: 'l',
    years: '63',
    partial: null,
  })
})

test('preserves a clicked short direction when an exact opposite-direction row exists', () => {
  const long150 = { ...selectedRow, daysOut: 150, lOrS: 'Long' }
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow, long150],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 150,
  })

  expect(selection.origin).toBe('wave_viewer')
  expect(selection.row.lOrS).toBe('Short')
})

test.each([
  { market: 'NASDAQ 100', symbol: 'CAT', date: '2026-08-07' },
  { market: 'S&P 500', symbol: 'IBM', date: '2026-08-07' },
  { market: 'S&P 500', symbol: 'CAT', date: '2026-08-08' },
])('does not reuse the anchor after market, symbol, or entry-date changes', viewer => {
  expect(selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    ...viewer,
    calendarDays: 150,
  })).toBeNull()
})

test('permanently invalidates an anchor when the viewer leaves its identity', () => {
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
  })).toBe(false)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'IBM',
    date: '2026-08-07',
  })).toBe(true)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor: null,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
  })).toBe(false)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-01-01',
    calendarDays: 366,
    isBuyAndHold: true,
  })).toBe(false)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-02-01',
    calendarDays: 335,
    isBuyAndHold: true,
  })).toBe(true)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-01-01',
    calendarDays: 30,
    isBuyAndHold: true,
  })).toBe(true)
  expect(shouldInvalidateOpportunityAIAnchor({
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 30,
    isBuyAndHold: true,
  })).toBe(true)
})

test.each([
  [1, 0],
  [9, 8],
  [10, 9],
  [60, 59],
  [90, 89],
  [91, 90],
  [367, 366],
])('maps %i displayed calendar days to engine offset %i', (calendarDays, engineDays) => {
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays,
  })
  const request = buildOpportunityViewerAIRequest({ selection, resourceId: '0' })

  expect(request.body.opportunities[0].daysOut).toBe(engineDays)
  expect(request.row.daysOut).toBe(calendarDays)
  expect(request.body.opportunities[0].years).toBe('10')
})

test('preserves PE-cycle years as a string', () => {
  const peAnchor = createOpportunityAISelectionAnchor({
    row: selectedRow,
    market: 'S&P 500',
    years: 'pe2-10',
    partialYears: '8',
    mode: 'pe',
  })
  const selection = selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor: peAnchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 150,
  })
  const request = buildOpportunityViewerAIRequest({ selection, resourceId: '2' })

  expect(request.body.opportunities[0]).toMatchObject({
    years: 'pe2-10',
    partial: { min_winning_years: '8', mode: 'pe' },
    mode: 'pe',
  })
})

test('invalidates the anchor when a PE cycle moves the entry date', () => {
  const viewer = {
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2028-08-07',
    mode: 'pe',
    cycle: 'pe0',
  }
  expect(shouldInvalidateOpportunityAIAnchor(viewer)).toBe(true)
  expect(selectOpportunityAIPanelSelection({
    ...viewer,
    scoreSource: [selectedRow],
    calendarDays: 150,
    years: '15',
  })).toBeNull()
})

test('does not treat an arbitrary date range as Buy & Hold from the UI flag alone', () => {
  expect(selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-02-01',
    calendarDays: 335,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  })).toBeNull()
  expect(selectOpportunityAIPanelSelection({
    scoreSource: [selectedRow],
    anchor,
    market: 'S&P 500',
    symbol: 'CAT',
    date: '2026-08-07',
    calendarDays: 30,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  })).toBeNull()
})

test('viewer match includes years, cycle, and Buy & Hold state', () => {
  const selection = {
    symbol: 'CAT',
    date: '2026-01-01',
    daysOut: 366,
    years: '63',
    yearCount: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  }
  const viewer = {
    selection,
    symbol: 'CAT',
    date: '2026-01-01',
    calendarDays: 366,
    years: '63',
    mode: 'consecutive',
    cycle: 'cons',
    isBuyAndHold: true,
  }

  expect(opportunityAISelectionMatchesViewer(viewer)).toBe(true)
  expect(opportunityAISelectionMatchesViewer({ ...viewer, years: '62' })).toBe(false)
  expect(opportunityAISelectionMatchesViewer({ ...viewer, isBuyAndHold: false })).toBe(false)
})

test('keeps a valid current score when unfinished comparisons time out', () => {
  const scores = terminalizeOpportunityViewerScores({
    'CAT|2026-08-07|84|s': {
      status: 'partial',
      display_status: 'available',
      horizons: [
        { calendar_days: 30, status: 'loading' },
        { calendar_days: 60, status: 'loading' },
        { calendar_days: 85, status: 'available', ml_score: 72 },
      ],
    },
  })

  expect(scores['CAT|2026-08-07|84|s']).toMatchObject({
    status: 'partial',
    display_status: 'available',
    horizons: [
      { calendar_days: 30, status: 'unavailable', error: { code: 'service_unavailable' } },
      { calendar_days: 60, status: 'unavailable', error: { code: 'service_unavailable' } },
      { calendar_days: 85, status: 'available', ml_score: 72 },
    ],
  })
})

test('terminalizes a fully unresolved comparison bundle without deleting it', () => {
  const scores = terminalizeOpportunityViewerScores({
    key: {
      status: 'loading',
      display_status: 'loading',
      horizons: [{ calendar_days: 90, status: 'loading' }],
    },
  })

  expect(scores.key).toMatchObject({
    status: 'unavailable',
    display_status: 'unavailable',
    horizons: [{ calendar_days: 90, status: 'unavailable' }],
  })
})
