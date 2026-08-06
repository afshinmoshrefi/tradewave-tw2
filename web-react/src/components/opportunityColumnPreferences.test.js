const {
  DEFAULT_OPPORTUNITY_COLUMN_VISIBILITY,
  OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION,
  resolveOpportunityColumnVisibility,
} = require('./opportunityColumnPreferences')
const { AI_COLUMNS } = require('./opportunityAIScores')

test('new users start with every AI column off', () => {
  const result = resolveOpportunityColumnVisibility()

  expect(result.needsMigration).toBe(true)
  expect(result.version).toBe(OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION)
  expect(AI_COLUMNS.every(column => result.visibility[column] === false)).toBe(true)
  expect(result.visibility).toMatchObject({
    date: true,
    symbol: true,
    daysOut: true,
    lOrS: true,
    sharpe_ratio: true,
    avg_profit: true,
    price: true,
  })
})

test('the one-time migration removes AI columns inherited from the old defaults', () => {
  const savedVisibility = {
    date: false,
    win_prob: true,
    pred_return: true,
    ml_score: true,
    pred_mfe: true,
  }

  const result = resolveOpportunityColumnVisibility({ savedVisibility })

  expect(result.needsMigration).toBe(true)
  expect(result.visibility.date).toBe(false)
  expect(AI_COLUMNS.every(column => result.visibility[column] === false)).toBe(true)
  expect(savedVisibility).toEqual({
    date: false,
    win_prob: true,
    pred_return: true,
    ml_score: true,
    pred_mfe: true,
  })
})

test('after migration, explicit AI choices persist', () => {
  const result = resolveOpportunityColumnVisibility({
    savedVisibility: {
      win_prob: true,
      pred_return: false,
      ml_score: true,
      pred_mfe: false,
    },
    savedAIColumnDefaultsVersion: OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION,
  })

  expect(result.needsMigration).toBe(false)
  expect(result.visibility).toMatchObject({
    win_prob: true,
    pred_return: false,
    ml_score: true,
    pred_mfe: false,
  })
})

test('a newer saved version is never migrated backward', () => {
  const result = resolveOpportunityColumnVisibility({
    savedVisibility: { win_prob: true },
    savedAIColumnDefaultsVersion: OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION + 1,
  })

  expect(result.needsMigration).toBe(false)
  expect(result.visibility.win_prob).toBe(true)
})

test('malformed saved visibility falls back to a fresh complete default', () => {
  const result = resolveOpportunityColumnVisibility({
    savedVisibility: ['win_prob'],
    savedAIColumnDefaultsVersion: OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION,
  })

  expect(result.visibility).toEqual(DEFAULT_OPPORTUNITY_COLUMN_VISIBILITY)
  expect(result.visibility).not.toBe(DEFAULT_OPPORTUNITY_COLUMN_VISIBILITY)
})
