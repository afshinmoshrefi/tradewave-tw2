import React from 'react'
import { render, screen } from '@testing-library/react'
import { AnalysisReportView } from './AnalysisReportDialog'

const metrics = (cumulative, average) => ({
  average_return_pct: average,
  median_return_pct: average,
  profitable_pct: 60,
  best_return_pct: 12,
  worst_return_pct: -8,
  average_mfe_pct: 7,
  average_mae_pct: -4,
  sharpe_ratio: 1.1,
  cumulative_return_pct: cumulative,
  annualized_return_pct: 4,
  winners: 27,
  losers: 18,
})

const row = (role, label, startDate, endDate, cumulative, average) => ({
  role,
  label,
  symbol: 'CAT',
  start_date: startDate,
  end_date: endDate,
  direction: 'long',
  sample_years: 45,
  metrics: metrics(cumulative, average),
  yearly_results: [
    { year: 2024, return_pct: average },
    { year: 2025, return_pct: average },
  ],
})

const report = {
  report_type: 'range_comparison',
  title: 'Date Range Exclusion Report',
  context: {
    symbol: 'CAT',
    start_date: '2026-10-26',
    end_date: '2027-04-22',
    years_used: 45,
    pe_cycle: 'cons',
    common_years: [2024, 2025],
    cohort_basis: 'selected_range_annual_cycle',
  },
  rows: [
    row('selected_range', 'Excluded Date Range', '2026-10-26', '2027-04-22', -28, -3),
    row('remaining_range', 'Date Range Exclusion Model', '2026-04-23', '2026-10-25', 132, 5),
    row('buy_hold', 'Buy & Hold', '2026-01-01', '2027-01-01', 96, 4),
  ],
}

test('date range exclusion report uses clear education-first language', () => {
  render(<AnalysisReportView report={report} />)

  expect(screen.getByRole('heading', { name: 'Date Range Exclusion Report' })).toBeInTheDocument()
  expect(screen.getByText('45 completed years compared')).toBeInTheDocument()
  expect(screen.getByText(/What happened during the excluded dates/i)).toBeInTheDocument()
  expect(screen.getByText(/not treated as a Short trade/i)).toBeInTheDocument()
  expect(screen.getByText('Research and education only')).toBeInTheDocument()
  expect(screen.getByText(/not investment, tax, legal, or financial advice/i)).toBeInTheDocument()
  expect(screen.queryByText(/matched annual cycles/i)).not.toBeInTheDocument()
})

test('date range exclusion report compares the model with Buy and Hold', () => {
  render(<AnalysisReportView report={report} />)

  expect(screen.getByText('Main historical comparison')).toBeInTheDocument()
  expect(screen.getAllByText('Date Range Exclusion Model').length).toBeGreaterThan(0)
  expect(screen.getAllByText('Buy & Hold').length).toBeGreaterThan(0)
  expect(screen.getByText(/produced a cumulative return of \+132%/i)).toBeInTheDocument()
  expect(screen.queryByText(/^Short$/)).not.toBeInTheDocument()
  expect(screen.getAllByText('Average return per year')).toHaveLength(2)
  expect(screen.getAllByText('Cumulative return').length).toBeGreaterThanOrEqual(2)
  expect(screen.getAllByText('+5%').some(element => element.tagName === 'STRONG')).toBe(true)

})
test('a negative exclusion-model result is red and explains why Wave Viewer Short results differ', () => {
  const negativeReport = {
    ...report,
    rows: report.rows.map(existing => (
      existing.role === 'remaining_range'
        ? { ...existing, metrics: { ...existing.metrics, cumulative_return_pct: -69.54 } }
        : existing.role === 'buy_hold'
          ? { ...existing, metrics: { ...existing.metrics, cumulative_return_pct: 60489.48 } }
          : existing
    )),
  }

  render(<AnalysisReportView report={negativeReport} />)

  const negativeValue = screen.getAllByText('-69.54%').find(element => element.tagName === 'STRONG')
  const positiveValue = screen.getAllByText('+60489.48%').find(element => element.tagName === 'STRONG')
  expect(negativeValue).toHaveClass('is-negative')
  expect(positiveValue).toHaveClass('is-positive')
  expect(screen.getByText(/even if the Wave Viewer labels that period Short/i)).toBeInTheDocument()
  expect(screen.getByText(/This is not a Short trade/i)).toBeInTheDocument()
})

test('an adjusted exclusion report explains shared date results without mentioning multiple symbols', () => {
  const adjustedReport = {
    ...report,
    context: {
      ...report.context,
      requested_years: 60,
      years_used: 59,
      history_adjusted: true,
    },
  }
  render(<AnalysisReportView report={adjustedReport} />)

  expect(screen.getByText(/excluded dates, remaining dates, and Buy & Hold share 59 fully completed years/i)).toBeInTheDocument()
  expect(screen.queryByText(/one or more symbols/i)).not.toBeInTheDocument()
})

test('symbol comparison explains a reduced history using the actual symbols', () => {
  const symbolReport = {
    report_type: 'symbol_comparison',
    title: 'MSFT Symbol Comparison',
    context: {
      requested_years: 17,
      years_used: 16,
      history_adjusted: true,
      history_availability: [
        { symbol: 'MSFT', years: 39 },
        { symbol: 'AVGO', years: 16 },
      ],
    },
    rows: [
      { ...row('baseline', 'MSFT (Current)', '', '', 100, 10), symbol: 'MSFT', company: 'Microsoft Corporation' },
      { ...row('comparison', 'AVGO', '', '', 120, 12), symbol: 'AVGO', company: 'Broadcom Inc.' },
    ],
  }

  render(<AnalysisReportView report={symbolReport} />)

  expect(screen.getByText(
    'You started with a 17-year Microsoft Corporation (MSFT) pattern. AVGO has only 16 complete years for these dates, so this report compares MSFT and AVGO using the same 16 years.',
  )).toBeInTheDocument()
  expect(screen.queryByText(/You requested 17 years/i)).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Average return in the last 16 completed years' })).toBeInTheDocument()
  expect(screen.getByText(/AVGO had the highest average return at \+12% per year across the 16 years studied/i)).toBeInTheDocument()
})


test('PE comparison names the election-cycle years in the return heading and summary', () => {
  const peReport = {
    report_type: 'symbol_comparison',
    title: 'HON Symbol Comparison',
    context: {
      years_used: 7,
      pe_cycle: 'pe2',
    },
    rows: [
      { ...row('baseline', 'HON (Current)', '', '', 70, 13), symbol: 'HON', company: 'Honeywell International Inc.' },
      { ...row('comparison', 'NVDA', '', '', 180, 53), symbol: 'NVDA', company: 'NVIDIA Corporation' },
    ],
  }

  render(<AnalysisReportView report={peReport} />)

  expect(screen.getByRole('heading', {
    name: 'Average return in the last 7 midterm election years (PE+2)',
  })).toBeInTheDocument()
  expect(screen.getByText(
    /NVDA had the highest average return at \+53% per year across the 7 midterm election years studied/i,
  )).toBeInTheDocument()
})


test('date range comparison explains same ticker, same years, and Buy and Hold', () => {
  const dateRangeReport = {
    report_type: 'date_range_comparison',
    title: 'MSFT Date Range Comparison',
    context: {
      symbol: 'MSFT',
      requested_years: 10,
      years_used: 10,
      pe_cycle: 'cons',
      common_years: [2024, 2025],
    },
    rows: [
      { ...row('date_range', 'Date Range 1', '2026-10-01', '2026-12-31', 80, 8), symbol: 'MSFT' },
      { ...row('date_range', 'Date Range 2', '2026-07-01', '2026-12-31', 60, 6), symbol: 'MSFT' },
      { ...row('buy_hold', 'Buy & Hold', '2026-01-01', '2027-01-01', 50, 5), symbol: 'MSFT' },
    ],
  }

  render(<AnalysisReportView report={dateRangeReport} />)

  expect(screen.getByRole('heading', { name: 'MSFT Date Range Comparison' })).toBeInTheDocument()
  expect(screen.getByText(/Same ticker. Same historical years. Different dates/i)).toBeInTheDocument()
  expect(screen.getByText('Actual stock returns (Long)')).toBeInTheDocument()
  expect(screen.getByText(/Buy & Hold is included as a full-year reference/i)).toBeInTheDocument()
  expect(screen.getAllByText('Date Range 1: Oct 1 to Dec 31').length).toBeGreaterThanOrEqual(2)
  expect(screen.getAllByText('Date Range 2: Jul 1 to Dec 31').length).toBeGreaterThanOrEqual(2)
  expect(screen.getByText(/Date Range 1: Oct 1 to Dec 31 had the highest average return/i)).toBeInTheDocument()
  expect(screen.getByText('Research and education only')).toBeInTheDocument()
})

