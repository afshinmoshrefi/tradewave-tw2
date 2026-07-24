const {
  analyzeOpportunityFilter,
  EMPTY_DAY_RANGE,
  filterOpportunityRows,
  getOpportunityDayRange,
  isOpportunityFilterPending,
  opportunityFilterUsesAI,
  sortOpportunityRows,
} = require('./opportunityFilters')

const rows = [
  {
    symbol: 'LOW',
    daysOut: 20,
    avg_profit: 3,
    sharpe_ratio: 1,
    avg_profit2: 4,
    sharpe_ratio2: 1,
    TL: 45,
    price: 25,
    ml_score: 55,
    win_prob: 0.55,
    pred_return: 3,
    pred_mfe: 6,
  },
  {
    symbol: 'GOOD',
    daysOut: 50,
    avg_profit: 5,
    sharpe_ratio: 2.5,
    avg_profit2: 8,
    sharpe_ratio2: 2,
    TL: 80,
    price: 75,
    ml_score: 85,
    win_prob: 0.72,
    pred_return: 8,
    pred_mfe: 12,
  },
  {
    symbol: 'EDGE',
    daysOut: 80,
    avg_profit: 4,
    sharpe_ratio: 1.5,
    avg_profit2: 6,
    sharpe_ratio2: 1.5,
    TL: 65,
    price: 125,
    ml_score: 70,
    win_prob: 0.64,
    pred_return: 5,
    pred_mfe: 9,
  },
  {
    symbol: 'OUTSIDE',
    daysOut: 120,
    avg_profit: 12,
    sharpe_ratio: 4,
    avg_profit2: 14,
    sharpe_ratio2: 3,
    TL: 90,
    price: 150,
    ml_score: 95,
    win_prob: 0.8,
    pred_return: 12,
    pred_mfe: 18,
  },
]

test('extracts the server day range independently from client-only predicates', () => {
  expect(getOpportunityDayRange('10-90')).toBe('10-90')
  expect(getOpportunityDayRange('10-90;')).toBe('10-90')
  expect(getOpportunityDayRange('10-90;avgp>4')).toBe('10-90')
  expect(getOpportunityDayRange('avgp>4; 20 - 60 ;sr>1')).toBe('20-60')
  expect(getOpportunityDayRange('avgp>4')).toBe(EMPTY_DAY_RANGE)
  expect(getOpportunityDayRange('90-10')).toBe(EMPTY_DAY_RANGE)
})

test('restores the range rows when avgp is deleted from a compound filter', () => {
  const rangeOnly = filterOpportunityRows(rows, '10-90')
  expect(rangeOnly.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])

  const trailingSeparator = filterOpportunityRows(rows, '10-90;')
  expect(trailingSeparator.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])

  const compound = filterOpportunityRows(rows, '10-90;avgp>4')
  expect(compound.map(row => row.symbol)).toEqual(['GOOD', 'EDGE'])

  const restored = filterOpportunityRows(rows, '10-90')
  expect(restored.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])
  expect(rows).toHaveLength(4)
})

test('ANDs the supported numeric filters without mutating the source rows', () => {
  const result = filterOpportunityRows(
    rows,
    'sr>2;twa>7;twr>1.5;tl>70;price>50;ml>80;win>70;predr>7;pmfe>10'
  )

  expect(result.map(row => row.symbol)).toEqual(['GOOD', 'OUTSIDE'])
  expect(rows.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE', 'OUTSIDE'])
})

test('keeps aliases and default ticker search working', () => {
  expect(filterOpportunityRows(rows, 'ap>10').map(row => row.symbol)).toEqual(['OUTSIDE'])
  expect(filterOpportunityRows(rows, 'ais>90').map(row => row.symbol)).toEqual(['OUTSIDE'])
  expect(filterOpportunityRows(rows, 'wp<60').map(row => row.symbol)).toEqual(['LOW'])
  expect(filterOpportunityRows(rows, 'good').map(row => row.symbol)).toEqual(['GOOD'])
})

test('returns the same opportunity membership regardless of filter token order', () => {
  const rangeThenAI = filterOpportunityRows(rows, '10-90;predr>3')
  const aiThenRange = filterOpportunityRows(rows, 'predr>3;10-90')
  const standaloneAI = filterOpportunityRows(rows, 'predr>3')

  expect(rangeThenAI.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])
  expect(aiThenRange.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])
  expect(rangeThenAI.every(row => standaloneAI.includes(row))).toBe(true)
  expect(rangeThenAI.length).toBeLessThanOrEqual(standaloneAI.length)
})

test('recognizes when an AI filter must wait for the complete score snapshot', () => {
  expect(opportunityFilterUsesAI('10-90;predr>3')).toBe(true)
  expect(opportunityFilterUsesAI('avgp>4;win<70')).toBe(true)
  expect(opportunityFilterUsesAI('10-90;avgp>4')).toBe(false)

  expect(isOpportunityFilterPending('predr>3', true)).toBe(true)
  expect(isOpportunityFilterPending('predr>3', false)).toBe(false)
  expect(isOpportunityFilterPending('avgp>4', true)).toBe(false)
})

test('sorting changes order without adding or removing filtered opportunities', () => {
  const filtered = filterOpportunityRows(rows, '10-90;predr>3')
  const originalMembership = filtered.map(row => row.symbol).sort()

  const ascending = sortOpportunityRows(filtered, 'win_prob', 'a')
  const descending = sortOpportunityRows(filtered, 'win_prob', 'd')

  expect(ascending.map(row => row.symbol)).toEqual(['LOW', 'EDGE', 'GOOD'])
  expect(descending.map(row => row.symbol)).toEqual(['GOOD', 'EDGE', 'LOW'])
  expect(ascending.map(row => row.symbol).sort()).toEqual(originalMembership)
  expect(descending.map(row => row.symbol).sort()).toEqual(originalMembership)
  expect(filtered.map(row => row.symbol)).toEqual(['LOW', 'GOOD', 'EDGE'])
})

test('distinguishes incomplete and invalid commands from valid empty results', () => {
  expect(analyzeOpportunityFilter('10-90;avgp>')).toMatchObject({ status: 'incomplete', segment: 'avgp>' })
  expect(analyzeOpportunityFilter('win>')).toMatchObject({ status: 'incomplete', segment: 'win>' })
  expect(analyzeOpportunityFilter('predr>')).toMatchObject({ status: 'incomplete', segment: 'predr>' })
  expect(analyzeOpportunityFilter('10-')).toMatchObject({ status: 'incomplete', segment: '10-' })

  expect(analyzeOpportunityFilter('win>>70')).toMatchObject({ status: 'invalid', segment: 'win>>70' })
  expect(analyzeOpportunityFilter('90-10')).toMatchObject({ status: 'invalid', segment: '90-10' })
  expect(analyzeOpportunityFilter('10-90;foobar')).toMatchObject({ status: 'invalid', segment: 'foobar' })

  expect(analyzeOpportunityFilter('avgp>9999')).toMatchObject({ status: 'valid' })
  expect(analyzeOpportunityFilter('AAPL')).toMatchObject({ status: 'valid' })
  expect(analyzeOpportunityFilter('ML')).toMatchObject({ status: 'valid' })
  expect(analyzeOpportunityFilter('10-90;predr>3')).toMatchObject({ status: 'valid' })
})

test('does not partially accept malformed numeric commands', () => {
  expect(filterOpportunityRows(rows, 'win>70oops')).toEqual([])
  expect(filterOpportunityRows(rows, 'predr>3junk')).toEqual([])
})
