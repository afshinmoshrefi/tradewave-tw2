import { AI_COLUMNS } from './opportunityAIScores'

export const DEFAULT_OPPORTUNITY_SORT = Object.freeze({
  column: 'sharpe_ratio',
  direction: 'd',
})

// This is intentionally independent of column visibility. The Sort by control
// can use any available field without making the table wider.
export const OPPORTUNITY_SORT_FIELDS = Object.freeze([
  Object.freeze({
    column: 'sharpe_ratio',
    label: 'Sharpe Ratio',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
  }),
  Object.freeze({
    column: 'symbol',
    label: 'Ticker',
    ascendingLabel: 'A to Z',
    descendingLabel: 'Z to A',
    preferredDirection: 'a',
  }),
  Object.freeze({
    column: 'date',
    label: 'Start Date',
    ascendingLabel: 'Earliest first',
    descendingLabel: 'Latest first',
    preferredDirection: 'a',
  }),
  Object.freeze({
    column: 'daysOut',
    label: 'Pattern Length',
    ascendingLabel: 'Shortest first',
    descendingLabel: 'Longest first',
    preferredDirection: 'a',
  }),
  Object.freeze({
    column: 'lOrS',
    label: 'Direction',
    ascendingLabel: 'Long first',
    descendingLabel: 'Short first',
    preferredDirection: 'a',
  }),
  Object.freeze({
    column: 'avg_profit',
    label: 'Average Profit',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
  }),
  Object.freeze({
    column: 'avg_profit2',
    label: 'TradeWave Average',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresSR2: true,
  }),
  Object.freeze({
    column: 'sharpe_ratio2',
    label: 'TradeWave Ratio',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresSR2: true,
  }),
  Object.freeze({
    column: 'TL',
    label: 'Trend Long',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
  }),
  Object.freeze({
    column: 'price',
    label: 'Price',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
  }),
  Object.freeze({
    column: 'ml_score',
    label: 'AI Score',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresAI: true,
  }),
  Object.freeze({
    column: 'win_prob',
    label: 'AI Win%',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresAI: true,
  }),
  Object.freeze({
    column: 'pred_return',
    label: 'Predicted Ending Return',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresAI: true,
  }),
  Object.freeze({
    column: 'pred_mfe',
    label: 'Estimated Best Move',
    ascendingLabel: 'Lowest first',
    descendingLabel: 'Highest first',
    preferredDirection: 'd',
    requiresAI: true,
  }),
])

const OPPORTUNITY_SORT_COLUMNS = new Set(OPPORTUNITY_SORT_FIELDS.map(field => field.column))

export const opportunitySortValue = (column, direction) => `${column}:${direction}`

export const parseOpportunitySortValue = value => {
  const [column, direction, extra] = String(value || '').split(':')
  if (extra !== undefined || !OPPORTUNITY_SORT_COLUMNS.has(column)) return null
  if (direction !== 'a' && direction !== 'd') return null
  return { column, direction }
}

export const opportunitySortUsesAI = sort => {
  const column = typeof sort === 'string' ? sort : sort && sort.column
  return AI_COLUMNS.includes(column)
}

export const selectOpportunitySortFields = ({
  hasAI = false,
  mlEnabled = false,
  marketEligible = true,
  showSR2 = false,
} = {}) => {
  const allowAI = Boolean(hasAI && mlEnabled && marketEligible)
  return OPPORTUNITY_SORT_FIELDS.filter(field => {
    if (field.requiresAI && !allowAI) return false
    if (field.requiresSR2 && !showSR2) return false
    return true
  })
}

export const buildOpportunitySortOptions = availability => (
  selectOpportunitySortFields(availability).flatMap(field => {
    const directions = field.preferredDirection === 'a' ? ['a', 'd'] : ['d', 'a']
    return directions.map(direction => ({
      value: opportunitySortValue(field.column, direction),
      column: field.column,
      direction,
      fieldLabel: field.label,
      directionLabel: direction === 'a' ? field.ascendingLabel : field.descendingLabel,
      label: `${field.label}: ${direction === 'a' ? field.ascendingLabel : field.descendingLabel}`,
      isAI: Boolean(field.requiresAI),
    }))
  })
)
