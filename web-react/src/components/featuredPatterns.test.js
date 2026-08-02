import {
  hundredYearCompletedCount,
  hundredYearOccurrenceStart,
  isHundredYearPatternView,
} from './featuredPatterns';


const beforeStart = new Date('2026-08-02T00:00:00Z');

const exactView = {
  marketId: '5',
  symbol: 'SPX',
  startDate: '2026-09-27',
  daysOut: 295,
  seasonalYears: '24',
  peCycle: 'pe2',
  trimYear: 0,
  today: beforeStart,
};


test('100-Year Pattern client identity uses inclusive calendar semantics', () => {
  expect(hundredYearOccurrenceStart(beforeStart)).toBe('2026-09-27');
  expect(hundredYearCompletedCount(beforeStart)).toBe(24);
  expect(isHundredYearPatternView(exactView)).toBe(true);
});


test.each([
  ['marketId', '6'],
  ['symbol', 'SPY'],
  ['startDate', '2026-09-28'],
  ['daysOut', 294],
  ['seasonalYears', '23'],
  ['peCycle', 'cons'],
  ['trimYear', 1930],
])('changing %s leaves the public signature view', (field, value) => {
  expect(isHundredYearPatternView({ ...exactView, [field]: value })).toBe(false);
});


test('the completed 2026 occurrence raises the cohort to 25', () => {
  const afterEnd = new Date('2027-07-19T00:00:00Z');
  expect(hundredYearOccurrenceStart(afterEnd)).toBe('2026-09-27');
  expect(hundredYearCompletedCount(afterEnd)).toBe(25);
});
