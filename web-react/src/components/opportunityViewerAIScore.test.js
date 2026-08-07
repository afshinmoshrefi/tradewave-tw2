const {
  buildOpportunityViewerAIRequest,
  createOpportunityAISelectionAnchor,
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
