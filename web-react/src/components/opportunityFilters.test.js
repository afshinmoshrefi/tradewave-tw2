const {
  analyzeOpportunityFilter,
  EMPTY_DAY_RANGE,
  filterOpportunityRows,
  getOpportunityDayRange,
  isOpportunityFilterPending,
  opportunityFilterUsesAI,
  sortOpportunityRows,
  toOpportunityEngineDayRange,
} = require('./opportunityFilters')
const {
  normalizeOpportunityAIScore,
  opportunityAIFlatFields,
} = require('./opportunityAIScores')

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

test('converts displayed inclusive calendar-day ranges only at the engine boundary', () => {
  expect(toOpportunityEngineDayRange('10-90')).toBe('9-89')
  expect(toOpportunityEngineDayRange('91-150')).toBe('90-149')
  expect(toOpportunityEngineDayRange('1-367')).toBe('0-366')
  expect(toOpportunityEngineDayRange(EMPTY_DAY_RANGE)).toBe(EMPTY_DAY_RANGE)
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

test('sorting a hidden field keeps missing values last in both directions', () => {
  const hiddenFieldRows = [
    { date: '2026-08-05', symbol: 'MISSING', daysOut: 40, lOrS: 'Long', pred_return: null },
    { date: '2026-08-05', symbol: 'LOWER', daysOut: 40, lOrS: 'Long', pred_return: -2 },
    { date: '2026-08-05', symbol: 'HIGHER', daysOut: 40, lOrS: 'Long', pred_return: 4 },
  ]

  expect(sortOpportunityRows(hiddenFieldRows, 'pred_return', 'a').map(row => row.symbol))
    .toEqual(['LOWER', 'HIGHER', 'MISSING'])
  expect(sortOpportunityRows(hiddenFieldRows, 'pred_return', 'd').map(row => row.symbol))
    .toEqual(['HIGHER', 'LOWER', 'MISSING'])
})

test('long-pattern AI sort and filters use the displayed 90-day checkpoint, not a stronger shorter checkpoint', () => {
  const longRow = { symbol: 'LONG', date: '2026-08-05', daysOut: 120, lOrS: 'Long' }
  const longBundle = normalizeOpportunityAIScore({
    row: longRow,
    scores: {
      'LONG|2026-08-05|119|l': {
        basis: 'recalculated_checkpoints',
        horizons: [
          { calendar_days: 30, ml_score: 99, win_prob: 0.95, pred_return: 12, pred_mfe: 18 },
          { calendar_days: 60, ml_score: 80, win_prob: 0.8, pred_return: 8, pred_mfe: 12 },
          { calendar_days: 90, ml_score: 40, win_prob: 0.45, pred_return: 1, pred_mfe: 3 },
        ],
      },
    },
  })
  const displayedLong = { ...longRow, ...opportunityAIFlatFields(longBundle) }
  const fullWindow = { symbol: 'FULL', daysOut: 60, ml_score: 70, win_prob: 0.7, pred_return: 5, pred_mfe: 7 }

  expect(filterOpportunityRows([displayedLong, fullWindow], 'ais>60').map(row => row.symbol)).toEqual(['FULL'])
  expect(sortOpportunityRows([displayedLong, fullWindow], 'ml_score', 'd').map(row => row.symbol)).toEqual(['FULL', 'LONG'])
})

test('short-pattern AI sort and filters use the displayed ten-day model minimum', () => {
  const source = { symbol: 'SHORT', date: '2026-08-05', daysOut: 6, lOrS: 'Long' }
  const bundle = normalizeOpportunityAIScore({
    row: source,
    scores: {
      'SHORT|2026-08-05|5|l': {
        basis: 'minimum_model_horizon',
        horizons: [{
          calendar_days: 10,
          status: 'available',
          ml_score: 82,
          win_prob: 0.71,
          pred_return: 3.4,
          pred_mfe: 6.2,
        }],
      },
    },
  })
  const displayedShort = { ...source, ...opportunityAIFlatFields(bundle) }
  const lower = { symbol: 'LOWER', daysOut: 20, ml_score: 70, win_prob: 0.6, pred_return: 2, pred_mfe: 4 }

  expect(filterOpportunityRows([displayedShort, lower], 'ais>80').map(row => row.symbol)).toEqual(['SHORT'])
  expect(sortOpportunityRows([displayedShort, lower], 'ml_score', 'd').map(row => row.symbol)).toEqual(['SHORT', 'LOWER'])
})

test('below-threshold AI readings remain null and sort below real zero in both directions', () => {
  const source = { symbol: 'BELOW', date: '2026-08-05', daysOut: 120, lOrS: 'Long' }
  const bundle = normalizeOpportunityAIScore({
    row: source,
    scores: {
      'BELOW|2026-08-05|119|l': {
        basis: 'duration_comparison',
        horizons: [
          { calendar_days: 30, status: 'available', ml_score: 75, win_prob: 0.7, pred_return: 4, pred_mfe: 7 },
          { calendar_days: 60, status: 'below_threshold' },
          { calendar_days: 90, status: 'below_threshold' },
        ],
      },
    },
  })
  const below = { ...source, ...opportunityAIFlatFields(bundle) }
  const realZero = {
    symbol: 'ZERO', date: '2026-08-05', daysOut: 30, lOrS: 'Long',
    ml_score: 0, win_prob: 0, pred_return: 0, pred_mfe: 0,
  }

  expect(below.ml_score).toBeNull()
  expect(filterOpportunityRows([below, realZero], 'ais<1').map(row => row.symbol)).toEqual(['ZERO'])
  expect(sortOpportunityRows([below, realZero], 'ml_score', 'a').map(row => row.symbol)).toEqual(['ZERO', 'BELOW'])
  expect(sortOpportunityRows([below, realZero], 'ml_score', 'd').map(row => row.symbol)).toEqual(['ZERO', 'BELOW'])
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
