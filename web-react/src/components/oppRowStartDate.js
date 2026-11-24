import { currentNewYorkMarketDate } from "./opportunityViewerAIScore"

// TW-BUG-0037. A logged-in user on a free ("F") market is start-date-locked to the
// US market date: the appserver answers ChartData4 for today (America/New_York) and
// echoes that date, and SeasonalBarChart discards any response whose echoed
// entry_date differs from the one requested. A row dated before today therefore has
// to request today, or the chart stays blank. Paid ("P") markets keep the row date.
// The markets entry in the users security list carries its type: "F" (free,
// date-locked) or "P" (premium). The list is keyed by value in some callers and by
// label in others, so match either.
export const isStartDateLocked = ({ loggedinUser, securityTypeList, selectedSecurity }) => {
  if (String(loggedinUser ?? "0") === "0") return false
  const list = Array.isArray(securityTypeList) ? securityTypeList : []
  const entry = list.find(item => item && (item.value === selectedSecurity || item.label === selectedSecurity))
  return Boolean(entry && entry.type === "F")
}

export const oppRowStartDate = ({ rowDate, locked, marketDate = currentNewYorkMarketDate() }) => {
  if (!locked) return rowDate
  // Only move a row that started before today; a future-dated row keeps its own
  // date so the server lock (not the client) stays the single authority there.
  return rowDate && rowDate < marketDate ? marketDate : rowDate
}
