const {
  DEFAULT_OPPORTUNITY_SORT,
  OPPORTUNITY_SORT_FIELDS,
  buildOpportunitySortOptions,
  opportunitySortUsesAI,
  opportunitySortValue,
  parseOpportunitySortValue,
  selectOpportunitySortFields,
} = require('./opportunitySorting')

const columns = fields => fields.map(field => field.column)

test('the default sort is Sharpe Ratio from highest to lowest', () => {
  expect(DEFAULT_OPPORTUNITY_SORT).toEqual({ column: 'sharpe_ratio', direction: 'd' })
  expect(buildOpportunitySortOptions()[0]).toMatchObject({
    value: 'sharpe_ratio:d',
    label: 'Sharpe Ratio: Highest first',
  })
})

test('base sort fields are available even when their table columns are hidden', () => {
  const visibleFields = selectOpportunitySortFields({ showSR2: false })

  expect(columns(visibleFields)).toEqual([
    'sharpe_ratio',
    'symbol',
    'date',
    'daysOut',
    'lOrS',
    'avg_profit',
    'TL',
    'price',
  ])
  expect(visibleFields).not.toHaveProperty('columnVisibility')
})

test('TWA and TWR follow the secondary-stat availability flag', () => {
  expect(columns(selectOpportunitySortFields({ showSR2: false }))).not.toEqual(
    expect.arrayContaining(['avg_profit2', 'sharpe_ratio2'])
  )
  expect(columns(selectOpportunitySortFields({ showSR2: true }))).toEqual(
    expect.arrayContaining(['avg_profit2', 'sharpe_ratio2'])
  )
})

test.each([
  { hasAI: false, mlEnabled: true, marketEligible: true },
  { hasAI: true, mlEnabled: false, marketEligible: true },
  { hasAI: true, mlEnabled: true, marketEligible: false },
])('AI sort fields stay unavailable unless every AI gate is open: %o', availability => {
  const availableColumns = columns(selectOpportunitySortFields(availability))
  expect(availableColumns).not.toEqual(
    expect.arrayContaining(['ml_score', 'win_prob', 'pred_return', 'pred_mfe'])
  )
})

test('all four AI fields become sortable without requiring visible AI columns', () => {
  const availableColumns = columns(selectOpportunitySortFields({
    hasAI: true,
    mlEnabled: true,
    marketEligible: true,
  }))

  expect(availableColumns).toEqual(
    expect.arrayContaining(['ml_score', 'win_prob', 'pred_return', 'pred_mfe'])
  )
})

test('each available field has clear options for both directions', () => {
  const options = buildOpportunitySortOptions({
    hasAI: true,
    mlEnabled: true,
    marketEligible: true,
    showSR2: true,
  })

  expect(options).toHaveLength(OPPORTUNITY_SORT_FIELDS.length * 2)
  expect(options.find(option => option.value === 'symbol:a').label).toBe('Ticker: A to Z')
  expect(options.find(option => option.value === 'date:d').label).toBe('Start Date: Latest first')
  expect(options.find(option => option.value === 'win_prob:d')).toMatchObject({
    label: 'AI Win%: Highest first',
    isAI: true,
  })
})

test('sort values round-trip and reject malformed or unknown fields', () => {
  expect(opportunitySortValue('pred_return', 'd')).toBe('pred_return:d')
  expect(parseOpportunitySortValue('pred_return:d')).toEqual({ column: 'pred_return', direction: 'd' })
  expect(parseOpportunitySortValue('pred_return:x')).toBeNull()
  expect(parseOpportunitySortValue('unknown:d')).toBeNull()
  expect(parseOpportunitySortValue('symbol:a:extra')).toBeNull()
})

test('AI sort detection accepts a column or a complete sort state', () => {
  expect(opportunitySortUsesAI('ml_score')).toBe(true)
  expect(opportunitySortUsesAI({ column: 'win_prob', direction: 'd' })).toBe(true)
  expect(opportunitySortUsesAI({ column: 'sharpe_ratio', direction: 'd' })).toBe(false)
  expect(opportunitySortUsesAI(null)).toBe(false)
})
