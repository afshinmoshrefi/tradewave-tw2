import { EMPTY_DAY_RANGE } from './opportunityFilters'

export const selectOpportunityMLScoreSource = ({
  snapshot,
  contextKey,
  dayRange,
  opportunities,
}) => {
  const rows = Array.isArray(opportunities) ? opportunities : []
  let nextSnapshot =
    snapshot && snapshot.contextKey === contextKey
      ? snapshot
      : { contextKey, rows: [] }

  if (dayRange === EMPTY_DAY_RANGE && rows.length > 0) {
    nextSnapshot = { contextKey, rows }
  }

  return {
    snapshot: nextSnapshot,
    scoreSource: nextSnapshot.rows.length > 0 ? nextSnapshot.rows : rows,
  }
}
