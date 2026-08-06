const {
  OPPORTUNITY_AI_COLUMN_CONTROLS,
  setOpportunityAIColumnVisible,
} = require('./opportunityAIColumnControls')

test('offers all four AI score columns with plain descriptions', () => {
  expect(OPPORTUNITY_AI_COLUMN_CONTROLS).toEqual([
    { key: 'ml_score', label: 'AIS', description: '0-100 return rank' },
    { key: 'win_prob', label: 'Win%', description: 'Estimated chance of profit' },
    { key: 'pred_return', label: 'PredR', description: 'Estimated ending return' },
    { key: 'pred_mfe', label: 'PMFE', description: 'Estimated best move' },
  ])
})

test('changing one AI column preserves every other column preference', () => {
  const current = {
    date: false,
    symbol: true,
    price: true,
    ml_score: false,
    win_prob: false,
    pred_return: false,
    pred_mfe: false,
  }

  const next = setOpportunityAIColumnVisible(current, 'win_prob', true)

  expect(next).toEqual({
    ...current,
    win_prob: true,
  })
  expect(current.win_prob).toBe(false)
  expect(next).not.toBe(current)
})

test('all four AI columns can be enabled independently', () => {
  const enabled = OPPORTUNITY_AI_COLUMN_CONTROLS.reduce(
    (visibility, column) => setOpportunityAIColumnVisible(visibility, column.key, true),
    { date: true }
  )

  expect(enabled).toMatchObject({
    date: true,
    ml_score: true,
    win_prob: true,
    pred_return: true,
    pred_mfe: true,
  })
})

test('unknown columns cannot be added through the AI control helper', () => {
  expect(setOpportunityAIColumnVisible({ date: true }, 'unknown', true)).toEqual({ date: true })
})
