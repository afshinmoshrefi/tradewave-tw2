export const OPPORTUNITY_AI_COLUMN_CONTROLS = Object.freeze([
  Object.freeze({
    key: 'ml_score',
    label: 'AIS',
    description: '0-100 return rank',
  }),
  Object.freeze({
    key: 'win_prob',
    label: 'Win%',
    description: 'Estimated chance of profit',
  }),
  Object.freeze({
    key: 'pred_return',
    label: 'PredR',
    description: 'Estimated ending return',
  }),
  Object.freeze({
    key: 'pred_mfe',
    label: 'PMFE',
    description: 'Estimated best move',
  }),
])

const AI_COLUMN_KEYS = new Set(OPPORTUNITY_AI_COLUMN_CONTROLS.map(column => column.key))

export const setOpportunityAIColumnVisible = (currentVisibility, column, visible) => {
  const current = currentVisibility && typeof currentVisibility === 'object' && !Array.isArray(currentVisibility)
    ? currentVisibility
    : {}

  if (!AI_COLUMN_KEYS.has(column)) return { ...current }
  return {
    ...current,
    [column]: Boolean(visible),
  }
}
