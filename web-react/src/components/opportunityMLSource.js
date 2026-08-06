import { EMPTY_DAY_RANGE } from './opportunityFilters'

const rangedUnionCache = new WeakMap()

const rowIdentity = (row, index) => {
  const symbol = String((row && row.symbol) || '')
  const date = String((row && row.date) || '')
  const days = String((row && row.daysOut) || '')
  const direction = String((row && (row.lOrS || row.direction)) || '')
  const canonical = `${symbol}|${date}|${days}|${direction}`
  return canonical === '|||'
    ? String((row && row.id) || `row-${index}`)
    : canonical
}

const unionRows = (...groups) => {
  const populated = groups.filter(group => Array.isArray(group) && group.length > 0)
  if (populated.length === 0) return []
  if (populated.length === 1 || populated.every(group => group === populated[0])) {
    return populated[0]
  }

  const selected = []
  const seen = new Set()
  populated.forEach(group => {
    group.forEach((row, index) => {
      const identity = rowIdentity(row, index)
      if (seen.has(identity)) return
      seen.add(identity)
      selected.push(row)
    })
  })
  return selected
}

export const selectDisplayedOpportunityRows = ({
  showActiveOpps,
  opportunities,
  activeOpportunities,
}) => {
  const selected = showActiveOpps ? activeOpportunities : opportunities
  return Array.isArray(selected) ? selected : []
}

export const authoritativeOpportunityTableDate = rows => {
  const source = Array.isArray(rows) ? rows : []
  const match = source.find(row => (
    row && /^\d{4}-\d{2}-\d{2}$/.test(String(row.date || ''))
  ))
  return match ? String(match.date) : ''
}

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

  let scoreSource
  const canCacheUnion =
    nextSnapshot &&
    nextSnapshot.rows.length > 0 &&
    rows.length > 0 &&
    nextSnapshot.rows !== rows
  if (canCacheUnion) {
    const cached = rangedUnionCache.get(nextSnapshot)
    if (
      cached &&
      cached.contextKey === contextKey &&
      cached.dayRange === dayRange &&
      cached.rows === rows
    ) {
      scoreSource = cached.scoreSource
    } else {
      scoreSource = unionRows(nextSnapshot.rows, rows)
      rangedUnionCache.set(nextSnapshot, { contextKey, dayRange, rows, scoreSource })
    }
  } else {
    scoreSource = unionRows(nextSnapshot.rows, rows)
  }

  return {
    snapshot: nextSnapshot,
    // A server-side day range can choose a different representative window
    // for the same ticker. Keep the unfiltered baseline for stable AI-filter
    // semantics, but always add every currently visible identity so no eligible
    // row is stranded at N/A merely because it was not in the baseline set.
    scoreSource,
  }
}
