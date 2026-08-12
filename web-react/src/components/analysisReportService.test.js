import {
  AnalysisReportError,
  fetchReportChart,
  generateDateRangeComparison,
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

test('report chart accepts the established Jan 1 to Jan 2 Buy & Hold normalization', async () => {
  twFetch.mockResolvedValueOnce(chartResponse({
    market: '0',
    symbol: 'DIS',
    entry_date: '2026-01-02',
    days_out: 366,
    years: 10,
    pe_cycle: 'cons',
    cut_off_year: 0,
    report_completed_years: 10,
    comparison_direction: 'long',
  }))

  await expect(fetchReportChart({
    symbol: 'DIS',
    market: '0',
    startDate: '2026-01-01',
    daysOut: 366,
    years: 10,
    peCycle: 'cons',
    cutOffYear: 0,
    direction: 'long',
    token: 'test-token',
  })).resolves.toMatchObject({ chart: [expect.objectContaining({ year: 2025 })] })
})

test('report chart accepts the established future-year start-date normalization', async () => {
  const currentYear = new Date().getFullYear()
  twFetch.mockResolvedValueOnce(chartResponse({
    market: '0',
    symbol: 'CVX',
    entry_date: String(currentYear) + '-02-10',
    days_out: 349,
    years: 61,
    pe_cycle: 'cons',
    cut_off_year: 0,
    report_completed_years: 61,
    comparison_direction: 'long',
  }))

  await expect(fetchReportChart({
    symbol: 'CVX',
    market: '0',
    startDate: String(currentYear + 1) + '-02-10',
    daysOut: 349,
    years: 61,
    peCycle: 'cons',
    cutOffYear: 0,
    direction: 'long',
    token: 'test-token',
  })).resolves.toMatchObject({ chart: [expect.objectContaining({ year: 2025 })] })
})

test('same-symbol date-range reports use common years and add Buy & Hold once', async () => {
  const currentYear = new Date().getFullYear()
  const years = [2020, 2021, 2022, 2023, 2024, 2025]
  const reportChartResponse = request => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ChartData4: years.map((year, index) => ({
        year,
        pct: `${index + 1},${index + 3},-2`,
        price: `100,${101 + index}`,
      })),
      stats: {
        'Trade Dir': 'long',
        'Avg Profit - All': '3.5%',
        'Median Profit': '3%',
        'Percent Profitable': '100%',
        'Sharpe Ratio': '1.2',
      },
      request,
    }),
  })

  twFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({ StockMetaData: ['1990', String(currentYear)] }),
  })
  twFetch.mockResolvedValueOnce(reportChartResponse({
    market: '0', symbol: 'MSFT', entry_date: `${currentYear}-10-01`, days_out: 92,
    years: 6, pe_cycle: 'cons', cut_off_year: 0, report_completed_years: 6, comparison_direction: 'long',
  }))
  twFetch.mockResolvedValueOnce(reportChartResponse({
    market: '0', symbol: 'MSFT', entry_date: `${currentYear}-09-01`, days_out: 122,
    years: 6, pe_cycle: 'cons', cut_off_year: 0, report_completed_years: 6, comparison_direction: 'long',
  }))
  twFetch.mockResolvedValueOnce(reportChartResponse({
    market: '0', symbol: 'MSFT', entry_date: `${currentYear}-01-02`, days_out: 366,
    years: 6, pe_cycle: 'cons', cut_off_year: 0, report_completed_years: 6, comparison_direction: 'long',
  }))

  await expect(generateDateRangeComparison({
    baseline: { symbol: 'MSFT', company: 'Microsoft Corporation', market: '0' },
    ranges: [
      { start_date: `${currentYear}-10-01`, days_out: 92 },
      { start_date: `${currentYear}-09-01`, days_out: 122 },
    ],
    requestedYears: 5,
    peCycle: 'cons',
    cutOffYear: 0,
    token: 'test-token',
  })).resolves.toMatchObject({
    report_type: 'date_range_comparison',
    title: 'MSFT Date Range Comparison',
    context: { years_used: 5, direction: 'long', includes_buy_hold: true },
    rows: [
      { role: 'date_range', label: 'Date Range 1', sample_years: 5 },
      { role: 'date_range', label: 'Date Range 2', sample_years: 5 },
      { role: 'buy_hold', label: 'Buy & Hold', sample_years: 5 },
    ],
  })
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

test('date comparison preserves the exclusion report annual-cycle cohort', async () => {
  const currentYear = new Date().getFullYear()
  const responseFor = (request, years, returns) => ({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({
      ChartData4: years.map((year, index) => ({
        year,
        pct: `${returns[index]},${returns[index] + 2},-2`,
        price: `100,${100 + returns[index]}`,
      })),
      stats: {
        'Trade Dir': 'long',
        'Avg Profit - All': '1%',
        'Median Profit': '1%',
        'Percent Profitable': '100%',
        'Sharpe Ratio': '1',
      },
      request,
    }),
  })

  twFetch.mockResolvedValueOnce({
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => ({ StockMetaData: ['1990', String(currentYear)] }),
  })
  twFetch.mockResolvedValueOnce(responseFor({
    market: '2', symbol: 'HLT', entry_date: `${currentYear}-02-16`, days_out: 177,
    years: 6, pe_cycle: 'cons', cut_off_year: 0, report_completed_years: 6, comparison_direction: 'long',
  }, [2017, 2018, 2019, 2020, 2021, 2022], [1, 2, 3, 4, 5, 6]))
  twFetch.mockResolvedValueOnce(responseFor({
    market: '2', symbol: 'HLT', entry_date: `${currentYear}-01-02`, days_out: 366,
    years: 6, pe_cycle: 'cons', cut_off_year: 0, report_completed_years: 6, comparison_direction: 'long',
  }, [2016, 2017, 2018, 2019, 2020, 2021], [10, 10, 10, 10, 10, 10]))

  const report = await generateDateRangeComparison({
    baseline: { symbol: 'HLT', company: 'Hilton Worldwide Holdings Inc', market: '2' },
    ranges: [{
      start_date: `${currentYear}-02-16`,
      days_out: 177,
      year_offset: -1,
    }],
    requestedYears: 5,
    peCycle: 'cons',
    cutOffYear: 0,
    token: 'test-token',
  })

  expect(report.context).toMatchObject({
    years_used: 5,
    common_years: [2017, 2018, 2019, 2020, 2021],
  })
  expect(report.rows[0].yearly_results).toEqual([
    expect.objectContaining({ year: 2017, return_pct: 2 }),
    expect.objectContaining({ year: 2018, return_pct: 3 }),
    expect.objectContaining({ year: 2019, return_pct: 4 }),
    expect.objectContaining({ year: 2020, return_pct: 5 }),
    expect.objectContaining({ year: 2021, return_pct: 6 }),
  ])
})

