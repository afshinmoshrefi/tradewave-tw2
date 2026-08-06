const {
  authoritativeOpportunityTableDate,
  selectDisplayedOpportunityRows,
  selectOpportunityMLScoreSource,
} = require('./opportunityMLSource')

test('uses the server row date across the UTC/New York midnight boundary', () => {
  const rows = [{
    symbol: 'AAPL',
    date: '2026-08-05',
    // At 2026-08-06 00:30 UTC New York is still August 5. No browser clock is
    // consulted; the date already resolved by OppList remains authoritative.
    daysOut: 30,
  }]

  expect(authoritativeOpportunityTableDate(rows)).toBe('2026-08-05')
})

const baselineRows = [{ id: 'baseline-a' }, { id: 'baseline-b' }]
const rangeRows = [{ id: 'range-a' }, { id: 'range-b' }, { id: 'range-c' }]

test('keeps the unfiltered source and adds every visible ranged identity', () => {
  const baseline = selectOpportunityMLScoreSource({
    snapshot: null,
    contextKey: 'sp500|10|8',
    dayRange: '-',
    opportunities: baselineRows,
  })
  const ranged = selectOpportunityMLScoreSource({
    snapshot: baseline.snapshot,
    contextKey: 'sp500|10|8',
    dayRange: '10-90',
    opportunities: rangeRows,
  })

  expect(ranged.scoreSource).toEqual([...baselineRows, ...rangeRows])
  expect(ranged.snapshot).toBe(baseline.snapshot)
})

test('scores a reranked visible window for the same ticker instead of hiding it', () => {
  const baselineRow = {
    symbol: 'AAPL', date: '2026-08-05', daysOut: 45, lOrS: 'Long',
  }
  const rangedRow = {
    symbol: 'AAPL', date: '2026-08-12', daysOut: 150, lOrS: 'Long',
  }
  const baseline = selectOpportunityMLScoreSource({
    snapshot: null,
    contextKey: 'sp500|10|8',
    dayRange: '-',
    opportunities: [baselineRow],
  })
  const ranged = selectOpportunityMLScoreSource({
    snapshot: baseline.snapshot,
    contextKey: 'sp500|10|8',
    dayRange: '90-180',
    opportunities: [rangedRow],
  })

  expect(ranged.scoreSource).toEqual([baselineRow, rangedRow])
})

test('keeps the ranged union reference stable across unrelated rerenders', () => {
  const snapshot = { contextKey: 'sp500|standard', rows: baselineRows }
  const first = selectOpportunityMLScoreSource({
    snapshot,
    contextKey: 'sp500|standard',
    dayRange: '91-150',
    opportunities: rangeRows,
  })
  const second = selectOpportunityMLScoreSource({
    snapshot,
    contextKey: 'sp500|standard',
    dayRange: '91-150',
    opportunities: rangeRows,
  })

  expect(second.scoreSource).toBe(first.scoreSource)
})

test('selects the rows actually displayed in standard and active modes', () => {
  expect(selectDisplayedOpportunityRows({
    showActiveOpps: false,
    opportunities: baselineRows,
    activeOpportunities: rangeRows,
  })).toBe(baselineRows)
  expect(selectDisplayedOpportunityRows({
    showActiveOpps: true,
    opportunities: baselineRows,
    activeOpportunities: rangeRows,
  })).toBe(rangeRows)
})

test('preserves the baseline while the unfiltered source reloads', () => {
  const baseline = selectOpportunityMLScoreSource({
    snapshot: null,
    contextKey: 'sp500|10|8',
    dayRange: '-',
    opportunities: baselineRows,
  })
  const loading = selectOpportunityMLScoreSource({
    snapshot: baseline.snapshot,
    contextKey: 'sp500|10|8',
    dayRange: '-',
    opportunities: [],
  })

  expect(loading.scoreSource).toBe(baselineRows)
})

test('does not reuse another table context baseline', () => {
  const previous = {
    contextKey: 'sp500|10|8',
    rows: baselineRows,
  }
  const next = selectOpportunityMLScoreSource({
    snapshot: previous,
    contextKey: 'nasdaq|10|8',
    dayRange: '10-90',
    opportunities: rangeRows,
  })

  expect(next.scoreSource).toBe(rangeRows)
  expect(next.snapshot).toEqual({
    contextKey: 'nasdaq|10|8',
    rows: [],
  })
})
