import {
  AnalysisReportError,
  fetchReportChart,
  parseComparisonSymbols,
  preflightSymbolComparison,
  resolveReportSymbol,
} from './analysisReportService'
import { twFetch } from './twFetch'

jest.mock('./twFetch', () => ({ twFetch: jest.fn() }))

test('analysis report errors preserve a stable UI error code', () => {
  const error = new AnalysisReportError('history_changed', 'History changed', { years_used: 8 })
  expect(error).toMatchObject({
    name: 'AnalysisReportError',
    code: 'history_changed',
    message: 'History changed',
    details: { years_used: 8 },
  })
})

test('comparison symbols can be entered as comma, space, or semicolon separated lists', () => {
  expect(parseComparisonSymbols(['wmt, AVGO', ' nvda; msft '])).toEqual(['WMT', 'AVGO', 'NVDA', 'MSFT'])
})

test('the three-symbol limit applies across every entered list and row', async () => {
  await expect(preflightSymbolComparison({
    baseline: { symbol: 'KLAC' },
    comparisonSymbols: ['WMT, AVGO', 'NVDA MSFT'],
  })).rejects.toMatchObject({ code: 'too_many_symbols' })
})

const chartResponse = (request) => ({
  ok: true,
  status: 200,
  headers: { get: () => 'application/json' },
  json: async () => ({
    ChartData4: [{ year: 2025, pct: '4,7,-2', price: '100,104' }],
    stats: { 'Trade Dir': 'long', 'Avg Profit - All': '4%' },
    request,
  }),
})

test('report chart requires the server to echo completed years and direction', async () => {
  twFetch.mockResolvedValueOnce(chartResponse({
    market: '2',
    symbol: 'MSFT',
    entry_date: '2026-10-01',
    days_out: 92,
    years: 10,
    pe_cycle: 'cons',
    cut_off_year: 0,
    report_completed_years: 10,
    comparison_direction: 'long',
  }))
  await expect(fetchReportChart({
    symbol: 'MSFT',
    market: '2',
    startDate: '2026-10-01',
    daysOut: 92,
    years: 10,
    peCycle: 'cons',
    cutOffYear: 0,
    direction: 'long',
    token: 'test-token',
  })).resolves.toMatchObject({ chart: [expect.objectContaining({ year: 2025 })] })
  expect(twFetch.mock.calls[0][0]).toContain('report_completed_years=10')
  expect(twFetch.mock.calls[0][0]).toContain('comparison_direction=long')
})

test('report chart stops when the server omits the fixed direction echo', async () => {
  twFetch.mockResolvedValueOnce(chartResponse({
    market: '2',
    symbol: 'MSFT',
    entry_date: '2026-10-01',
    days_out: 92,
    years: 10,
    pe_cycle: 'cons',
    cut_off_year: 0,
    report_completed_years: 10,
  }))
  await expect(fetchReportChart({
    symbol: 'MSFT',
    market: '2',
    startDate: '2026-10-01',
    daysOut: 92,
    years: 10,
    peCycle: 'cons',
    cutOffYear: 0,
    direction: 'long',
    token: 'test-token',
  })).rejects.toMatchObject({ code: 'request_adjusted' })
})

test('symbol resolution prefers the current exchange family over a cross-market duplicate', async () => {
  twFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      matches: [
        { resourceID: '2', label: 'S&P 500 STOCKS', name: 'NVIDIA Corporation' },
        { resourceID: '7', label: 'LONDON EXCHANGE', name: 'NVIDIA Corporation' },
      ],
    }),
  })

  await expect(resolveReportSymbol({
    symbol: 'nvda',
    currentMarket: '1',
    currentMarketLabel: 'NASDAQ 100 STOCKS',
    token: 'test-token',
    securityTypeList2: [
      { label: 'S&P 500 STOCKS', type: 'P' },
      { label: 'LONDON EXCHANGE', type: 'P' },
    ],
    resourceObj: {
      1: 'NASDAQ 100 STOCKS',
      2: 'S&P 500 STOCKS',
      7: 'LONDON EXCHANGE',
    },
  })).resolves.toMatchObject({
    symbol: 'NVDA',
    company: 'NVIDIA Corporation',
    market: '1',
    market_label: 'NASDAQ 100 STOCKS',
  })
})
