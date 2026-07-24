const { selectOpportunityMLScoreSource } = require('./opportunityMLSource')

const baselineRows = [{ id: 'baseline-a' }, { id: 'baseline-b' }]
const rangeRows = [{ id: 'range-a' }, { id: 'range-b' }, { id: 'range-c' }]

test('keeps AI scoring anchored to the unfiltered source while a day range is active', () => {
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

  expect(ranged.scoreSource).toBe(baselineRows)
  expect(ranged.snapshot).toBe(baseline.snapshot)
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
