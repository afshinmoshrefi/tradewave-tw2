// Canonical client-side identity for TradeWave's single public signature exhibit.
// The appserver repeats and enforces this contract; this helper only keeps the UI from
// applying ordinary locked-market/year UX while that exact view is loaded.

export const HUNDRED_YEAR_PATTERN = Object.freeze({
  marketId: '5',
  symbol: 'SPX',
  peCycle: 'pe2',
  startMonthDay: '09-27',
  displayDays: 295,
  firstCompletedYear: 1930,
});

const asUtcDate = (value) => {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()));
  }
  return new Date();
};

export const hundredYearOccurrenceStart = (today = new Date()) => {
  const current = asUtcDate(today);
  const year = current.getUTCFullYear() - ((current.getUTCFullYear() - 2) % 4);
  return `${year}-09-27`;
};

const inclusiveEndUtc = (startIso) => {
  const start = new Date(`${startIso}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() + HUNDRED_YEAR_PATTERN.displayDays - 1);
  return start;
};

export const hundredYearCompletedCount = (today = new Date()) => {
  const current = asUtcDate(today);
  let candidate = current.getUTCFullYear() - ((current.getUTCFullYear() - 2) % 4);
  while (inclusiveEndUtc(`${candidate}-09-27`) >= current) candidate -= 4;
  if (candidate < HUNDRED_YEAR_PATTERN.firstCompletedYear) return 0;
  return Math.floor((candidate - HUNDRED_YEAR_PATTERN.firstCompletedYear) / 4) + 1;
};

export const isHundredYearPatternView = ({
  marketId,
  symbol,
  startDate,
  daysOut,
  seasonalYears,
  peCycle,
  trimYear = 0,
  today = new Date(),
} = {}) => (
  String(marketId) === HUNDRED_YEAR_PATTERN.marketId
  && String(symbol || '').trim().toUpperCase() === HUNDRED_YEAR_PATTERN.symbol
  && String(startDate || '') === hundredYearOccurrenceStart(today)
  && Number.parseInt(String(daysOut), 10) === HUNDRED_YEAR_PATTERN.displayDays
  && Number.parseInt(String(seasonalYears), 10) === hundredYearCompletedCount(today)
  && String(peCycle || '').trim().toLowerCase() === HUNDRED_YEAR_PATTERN.peCycle
  && Number.parseInt(String(trimYear || 0), 10) === 0
);
