const {
  taraEffectiveResponseMatches,
  taraTrendResponseMatches,
} = require('./taraActionContract')
const {
  isNonCurrentPECycle,
  peCycleAfterYearDelta,
  lineChartYearAfterPatternLoad,
  peCycleForYear,
} = require('./viewerCycleState')

test('2026 identifies PE+2 as current and the other PE phases as non-current', () => {
  expect(peCycleForYear(2026)).toBe('pe2')
  expect(isNonCurrentPECycle('cons', 2026)).toBe(false)
  expect(isNonCurrentPECycle('pe2', 2026)).toBe(false)
  expect(isNonCurrentPECycle('pe0', 2026)).toBe(true)
  expect(isNonCurrentPECycle('pe1', 2026)).toBe(true)
  expect(isNonCurrentPECycle('pe3', 2026)).toBe(true)
})

test('PE phase follows the start-date year in both directions with wraparound', () => {
  expect(peCycleAfterYearDelta('pe2', 1)).toBe('pe3')
  expect(peCycleAfterYearDelta('pe3', 1)).toBe('pe0')
  expect(peCycleAfterYearDelta('pe0', -1)).toBe('pe3')
  expect(peCycleAfterYearDelta('pe2', -1)).toBe('pe1')
  expect(peCycleAfterYearDelta('cons', 1)).toBe('cons')
})

test.each([
  ['pe0', '2028-08-11'],
  ['pe1', '2029-08-11'],
  ['pe3', '2027-08-11'],
])('accepts the established future %s display-year normalization', (peCycle, entryDate) => {
  const requested = {
    market: '0',
    symbol: 'WMT',
    entry_date: entryDate,
    days_out: 241,
    years: 10,
    pe_cycle: peCycle,
  }
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-08-11', cut_off_year: 0 },
    0,
    '2026-08-11',
  )).toBe(true)
  expect(lineChartYearAfterPatternLoad({
    selectedCycle: peCycle,
    currentYear: 2026,
    entryDate,
    lastBarYear: 2024,
  })).toBe(Number(entryDate.slice(0, 4)))
})

test('accepts a future consecutive date moved by the Trend Chart window', () => {
  const requested = {
    market: '0',
    symbol: 'MCD',
    entry_date: '2027-02-24',
    days_out: 28,
    years: 10,
    pe_cycle: 'cons',
  }
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-02-24', cut_off_year: 0 },
    0,
    '2026-08-11',
  )).toBe(true)
})

test('future-date normalization still rejects a changed month or day', () => {
  const requested = {
    market: '0',
    symbol: 'WMT',
    entry_date: '2028-08-11',
    days_out: 241,
    years: 10,
    pe_cycle: 'pe0',
  }
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-08-12', cut_off_year: 0 },
    0,
    '2026-08-11',
  )).toBe(false)
})

test('the trend-chart contract accepts the exact future PE date request', () => {
  const request = {
    market: '0',
    symbol: 'WMT',
    sy: 'pe0-10',
    chart_start_date: '2028-07-28',
    opp_start_date: '2028-08-11',
  }
  expect(taraTrendResponseMatches(request, request)).toBe(true)
  expect(taraTrendResponseMatches(
    request,
    { ...request, opp_start_date: '2026-08-11' },
  )).toBe(false)
})
