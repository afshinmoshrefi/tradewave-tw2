import { currentNewYorkMarketDate } from "./opportunityViewerAIScore"

// TW-BUG-0037. A logged-in user on a free ("F") market is start-date-locked to the
// US market date: the appserver answers ChartData4 for today (America/New_York) and
// echoes that date, and SeasonalBarChart discards any response whose echoed
// entry_date differs from the one requested. A row dated before today therefore has
// to request today, or the chart stays blank. Paid ("P") markets keep the row date.
export const isStartDateLocked = ({ loggedinUser, selectedSecurityType }) => (
  String(loggedinUser ?? "0") !== "0" && selectedSecurityType === "F"
)

export const oppRowStartDate = ({ rowDate, locked, marketDate = currentNewYorkMarketDate() }) => {
  if (!locked) return rowDate
  // Only move a row that started before today; a future-dated row keeps its own
  // date so the server lock (not the client) stays the single authority there.
  return rowDate && rowDate < marketDate ? marketDate : rowDate
}
