const normalizeRange = (range) => {
  const startDate = String(range?.start_date || range?.startDate || '')
  const daysOut = Number.parseInt(range?.days_out ?? range?.daysOut, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !Number.isFinite(daysOut) || daysOut < 2) return null
  return { start_date: startDate, days_out: daysOut }
}

export const dateRangeKey = (range) => {
  const normalized = normalizeRange(range)
  return normalized ? `${normalized.start_date}|${normalized.days_out}` : ''
}

export const startDateRangeSession = ({
  symbol,
  market,
  startDate,
  daysOut,
  cohortAnchorStartDate = '',
  peCycle = 'cons',
}) => {
  const initial = normalizeRange({ startDate, daysOut })
  if (!initial || !String(symbol || '').trim()) return null
  return {
    id: `date-ranges-${Date.now()}`,
    symbol: String(symbol).trim().toUpperCase(),
    market: String(market ?? ''),
    ranges: [initial],
    draft: initial,
    cohort_anchor_start_date: /^\d{4}-\d{2}-\d{2}$/.test(cohortAnchorStartDate) ? cohortAnchorStartDate : '',
    pe_cycle: peCycle || 'cons',
  }
}

export const updateDateRangeSessionDraft = (session, {
  symbol,
  market,
  startDate,
  daysOut,
}) => {
  if (!session) return null
  if (String(symbol || '').trim().toUpperCase() !== session.symbol) return null
  if (String(market ?? '') !== session.market) return null
  const draft = normalizeRange({ startDate, daysOut })
  return draft ? { ...session, draft } : session
}

export const dateRangesForComparison = (session) => {
  if (!session) return []
  const saved = (Array.isArray(session.ranges) ? session.ranges : [])
    .map(normalizeRange)
    .filter(Boolean)
    .slice(0, 3)
  const seen = new Set()
  const unique = saved.filter(range => {
    const key = dateRangeKey(range)
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
  const draft = normalizeRange(session.draft)
  const draftKey = dateRangeKey(draft)
  if (draftKey && !seen.has(draftKey)) {
    if (unique.length < 3) unique.push(draft)
    else unique[unique.length - 1] = draft
  }
  const anchorMonthDay = String(session.cohort_anchor_start_date || '').slice(5)
  const consecutiveCycle = !session.pe_cycle || session.pe_cycle === 'cons'
  return unique.map((range, index) => {
    const rangeMonthDay = String(range.start_date || '').slice(5)
    return {
      ...range,
      label: `Date Range ${index + 1}`,
      year_offset: consecutiveCycle && anchorMonthDay && rangeMonthDay < anchorMonthDay ? -1 : 0,
    }
  })
}

export const saveDateRangeDraft = (session) => {
  if (!session) return null
  const ranges = dateRangesForComparison(session).map(({ start_date, days_out }) => ({
    start_date,
    days_out,
  }))
  return { ...session, ranges }
}

export const dateRangeDraftIsSaved = (session) => {
  const draftKey = dateRangeKey(session?.draft)
  return Boolean(draftKey && (session?.ranges || []).some(range => dateRangeKey(range) === draftKey))
}
