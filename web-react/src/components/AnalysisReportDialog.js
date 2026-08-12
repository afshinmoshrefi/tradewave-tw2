import React, { useEffect, useMemo, useState } from 'react'
import ReactDOM from 'react-dom'
import { BsArrowLeft, BsPlus, BsTrash, BsX } from 'react-icons/bs'
import { themeColors } from './Common'
import { formatPercent } from './analysisReportData'
import {
  AnalysisReportError,
  generateSymbolComparison,
  parseComparisonSymbols,
  preflightSymbolComparison,
} from './analysisReportService'
import './styles/AnalysisReportDialog.css'

const metricColumns = [
  ['average_return_pct', 'Average Return'],
  ['median_return_pct', 'Typical Return'],
  ['profitable_pct', 'Profitable Years'],
  ['best_return_pct', 'Best Year'],
  ['worst_return_pct', 'Worst Year'],
  ['average_mfe_pct', 'Avg MFE'],
  ['average_mae_pct', 'Avg MAE'],
  ['sharpe_ratio', 'Sharpe'],
  ['cumulative_return_pct', 'Cumulative Return'],
]

const prettyDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return value || '—'
  const [, month, day] = value.split('-')
  const date = new Date(2000, Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const reportRowLabel = (row, reportType) => {
  const label = row?.label || row?.symbol
  if (
    reportType === 'date_range_comparison'
    && row?.role === 'date_range'
    && row?.start_date
    && row?.end_date
  ) {
    return `${label}: ${prettyDate(row.start_date)} to ${prettyDate(row.end_date)}`
  }
  return label
}

const metricText = (key, value, metrics = {}) => {
  if (key === 'sharpe_ratio') return Number.isFinite(value) ? String(value) : '—'
  if (key === 'profitable_pct' && Number.isFinite(metrics.winners)) {
    const sample = Number.isFinite(metrics.losers)
      ? metrics.winners + metrics.losers
      : null
    return sample ? `${metrics.winners}/${sample} (${formatPercent(value)})` : formatPercent(value)
  }
  return formatPercent(value)
}

const formatDollars = (value) => Number.isFinite(value)
  ? new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
  : 'Not available'

const hypotheticalValue = (cumulativeReturn) => (
  Number.isFinite(cumulativeReturn)
    ? 10000 * (1 + (cumulativeReturn / 100))
    : null
)

const leader = (rows, key) => {
  const usable = rows.filter(row => Number.isFinite(row.metrics?.[key]))
  if (!usable.length) return null
  return usable.reduce((best, row) => row.metrics[key] > best.metrics[key] ? row : best)
}

const historicalYearGroup = (peCycle, years) => {
  const count = Number(years) || 0
  const cycle = String(peCycle || 'cons').toLowerCase()
  if (cycle === 'pe0') return { title: `the last ${count} presidential election years (PE)`, studied: `the ${count} presidential election years studied` }
  if (cycle === 'pe1') return { title: `the last ${count} post-election years (PE+1)`, studied: `the ${count} post-election years studied` }
  if (cycle === 'pe2') return { title: `the last ${count} midterm election years (PE+2)`, studied: `the ${count} midterm election years studied` }
  if (cycle === 'pe3') return { title: `the last ${count} pre-election years (PE+3)`, studied: `the ${count} pre-election years studied` }
  return { title: `the last ${count} completed years`, studied: `the ${count} years studied` }
}

const averageReturnTitle = (report) => {
  const rows = report?.rows || []
  const years = report?.context?.years_used || rows[0]?.sample_years || rows[0]?.metrics?.sample_years
  return `Average return in ${historicalYearGroup(report?.context?.pe_cycle, years).title}`
}

const PlainLanguageSummary = ({ report }) => {
  const rows = report.rows || []
  if (!rows.length) return null
  const years = report.context?.years_used || rows[0]?.sample_years || rows[0]?.metrics?.sample_years
  const studiedYears = historicalYearGroup(report.context?.pe_cycle, years).studied
  if (report.report_type === 'symbol_comparison') {
    const averageLeader = leader(rows, 'average_return_pct')
    const consistencyLeader = leader(rows, 'profitable_pct')
    return (
      <div className="tw-report-summary">
        <strong>What this comparison shows</strong>
        <p>
          These symbols were measured with one shared setup and the same {years} historical years.
          {averageLeader ? ` ${averageLeader.symbol} had the highest average return at ${formatPercent(averageLeader.metrics.average_return_pct)} per year across ${studiedYears}.` : ''}
          {consistencyLeader ? ` ${consistencyLeader.symbol} was profitable most often at ${formatPercent(consistencyLeader.metrics.profitable_pct)} of the years.` : ''}
        </p>
        <p className="tw-report-caution">A stronger historical result does not guarantee that the symbol will lead in the future.</p>
      </div>
    )
  }
  if (report.report_type === 'date_range_comparison') {
    const averageLeader = leader(rows, 'average_return_pct')
    const consistencyLeader = leader(rows, 'profitable_pct')
    return (
      <div className="tw-report-summary">
        <strong>What this comparison shows</strong>
        <p>
          Every result uses actual stock returns for the same ticker and the same historical years. Only the dates change.
          {averageLeader ? ` ${reportRowLabel(averageLeader, report.report_type)} had the highest average return at ${formatPercent(averageLeader.metrics.average_return_pct)}.` : ''}
          {consistencyLeader ? ` ${reportRowLabel(consistencyLeader, report.report_type)} was profitable most often at ${formatPercent(consistencyLeader.metrics.profitable_pct)} of the years.` : ''}
        </p>
        <p className="tw-report-caution">Buy &amp; Hold is included as a full-year reference. These historical results do not predict what will happen next.</p>
      </div>
    )
  }


  const selected = rows.find(row => row.role === 'selected_range')
  const outside = rows.find(row => row.role === 'remaining_range')
  const buyHold = rows.find(row => row.role === 'buy_hold')
  const outsideCumulative = outside?.metrics?.cumulative_return_pct
  const buyHoldCumulative = buyHold?.metrics?.cumulative_return_pct
  const comparisonReady = Number.isFinite(outsideCumulative) && Number.isFinite(buyHoldCumulative)
  const improved = comparisonReady && outsideCumulative > buyHoldCumulative
  return (
    <div className="tw-report-summary">
      <strong>What this report studies</strong>
      <p>
        This report asks whether excluding {selected ? `${prettyDate(selected.start_date)} to ${prettyDate(selected.end_date)}` : 'the selected dates'} changed {outside?.symbol || buyHold?.symbol || 'the ticker'}&apos;s historical result.
        {' '}The Exclusion Model counts actual stock returns during the remaining dates. It always treats those dates as time invested in the stock, even if the Wave Viewer labels that period Short. Buy &amp; Hold counts returns throughout each full year.
      </p>
      {comparisonReady && (
        <p>
          <strong>Historical finding:</strong> The Exclusion Model produced a cumulative return of {formatPercent(outsideCumulative)}, compared with {formatPercent(buyHoldCumulative)} for Buy &amp; Hold. Excluding the selected dates {improved ? 'improved' : 'did not improve'} the historical result in these {years} completed years.
        </p>
      )}
      <p className="tw-report-caution">This is a research calculation. It is not a recommendation to enter or leave the market on specific dates.</p>
    </div>
  )
}

const yearGroupLabel = (peCycle) => {
  if (!peCycle || peCycle === 'cons') return 'Consecutive years'
  return `PE+${String(peCycle).replace('pe', '')} years`
}

const ComparedUsing = ({ report }) => {
  const context = report.context || {}
  const rows = report.rows || []
  const years = context.years_used || rows[0]?.sample_years || rows[0]?.metrics?.sample_years
  const symbolComparison = report.report_type === 'symbol_comparison'
  const dateRangeComparison = report.report_type === 'date_range_comparison'
  const items = symbolComparison
    ? [
      ['Date range', `${prettyDate(context.start_date)} to ${prettyDate(context.end_date)}`],
      ['History', `${years} completed years`],
      ['Direction', context.direction === 'short' ? 'Short' : 'Long'],
      ['Year group', yearGroupLabel(context.pe_cycle)],
    ]
    : dateRangeComparison
      ? [
        ['Ticker', context.symbol || rows[0]?.symbol || '-'],
        ['History', `${years} completed years compared`],
        ['Return type', 'Actual stock returns (Long)'],
        ['Year selection', yearGroupLabel(context.pe_cycle)],
      ]
      : [
      ['Ticker', context.symbol || rows[0]?.symbol || '—'],
      ['Excluded dates', `${prettyDate(context.start_date)} to ${prettyDate(context.end_date)}`],
      ['History', `${years} completed years compared`],
      ['Year selection', yearGroupLabel(context.pe_cycle)],
    ]
  if (Number(context.cut_off_year) > 0) items.push(['History ends', String(context.cut_off_year)])

  return (
    <section className="tw-report-setup" aria-label="Shared comparison settings">
      <div className="tw-report-setup-heading">
        <strong>Compared using</strong>
        <span>These settings apply to every result below.</span>
      </div>
      <dl>
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {!symbolComparison && !dateRangeComparison && context.cohort_basis === 'selected_range_annual_cycle' && (
        <p>
          Every result uses the same completed historical years. The year-by-year table keeps the excluded dates, remaining dates, and Buy &amp; Hold results together.
        </p>
      )}
    </section>
  )
}

const AverageReturnBars = ({ rows, report }) => {
  const values = rows.map(row => row.metrics?.average_return_pct).filter(Number.isFinite)
  const maxAbs = Math.max(1, ...values.map(Math.abs))
  return (
    <section className="tw-report-section">
      <h3>{averageReturnTitle(report)}</h3>
      <div className="tw-report-bars">
        {rows.map(row => {
          const value = row.metrics?.average_return_pct
          const width = Number.isFinite(value) ? Math.min(50, (Math.abs(value) / maxAbs) * 48) : 0
          return (
            <div className="tw-report-bar-row" key={`${row.role}-${row.symbol}-${row.label}`}>
              <div className="tw-report-bar-label">{reportRowLabel(row, report?.report_type)}</div>
              <div className="tw-report-bar-track">
                <span className="tw-report-zero" />
                {Number.isFinite(value) && (
                  <span
                    className={`tw-report-value-bar ${value < 0 ? 'is-negative' : 'is-positive'}`}
                    style={value < 0 ? { right: '50%', width: `${width}%` } : { left: '50%', width: `${width}%` }}
                  />
                )}
              </div>
              <div className="tw-report-bar-value">{formatPercent(value)}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

const RangeModelComparison = ({ rows }) => {
  const outside = rows.find(row => row.role === 'remaining_range')
  const buyHold = rows.find(row => row.role === 'buy_hold')
  if (!outside || !buyHold) return null
  const outsideAverage = outside.metrics?.average_return_pct
  const buyHoldAverage = buyHold.metrics?.average_return_pct
  const outsideCumulative = outside.metrics?.cumulative_return_pct
  const buyHoldCumulative = buyHold.metrics?.cumulative_return_pct
  const outsideValue = hypotheticalValue(outsideCumulative)
  const buyHoldValue = hypotheticalValue(buyHoldCumulative)
  const difference = Number.isFinite(outsideValue) && Number.isFinite(buyHoldValue)
    ? outsideValue - buyHoldValue
    : null
  return (
    <section className="tw-report-section">
      <h3>Main historical comparison</h3>
      <div className="tw-report-result-grid">
        <article>
          <span>Date Range Exclusion Model</span>
          <section className="tw-report-result-metrics">
            <div className="tw-report-result-metric">
              <strong className={Number.isFinite(outsideAverage) && outsideAverage < 0 ? 'is-negative' : 'is-positive'}>{formatPercent(outsideAverage)}</strong>
              <small>Average return per year</small>
            </div>
            <div className="tw-report-result-metric">
              <strong className={Number.isFinite(outsideCumulative) && outsideCumulative < 0 ? 'is-negative' : 'is-positive'}>{formatPercent(outsideCumulative)}</strong>
              <small>Cumulative return</small>
            </div>
          </section>
          <p>Counts actual stock returns from {prettyDate(outside.start_date)} to {prettyDate(outside.end_date)} while the excluded dates are left out. This is not a Short trade.</p>
          <div>{formatDollars(outsideValue)} <small>from a hypothetical $10,000</small></div>
        </article>
        <article>
          <span>Buy &amp; Hold</span>
          <section className="tw-report-result-metrics">
            <div className="tw-report-result-metric">
              <strong className={Number.isFinite(buyHoldAverage) && buyHoldAverage < 0 ? 'is-negative' : 'is-positive'}>{formatPercent(buyHoldAverage)}</strong>
              <small>Average return per year</small>
            </div>
            <div className="tw-report-result-metric">
              <strong className={Number.isFinite(buyHoldCumulative) && buyHoldCumulative < 0 ? 'is-negative' : 'is-positive'}>{formatPercent(buyHoldCumulative)}</strong>
              <small>Cumulative return</small>
            </div>
          </section>
          <p>Counts returns throughout the full annual period during the same completed years.</p>
          <div>{formatDollars(buyHoldValue)} <small>from a hypothetical $10,000</small></div>
        </article>
      </div>
      {Number.isFinite(difference) && (
        <p className="tw-report-result-difference">
          The historical Exclusion Model ended with {formatDollars(Math.abs(difference))} {difference >= 0 ? 'more' : 'less'} than Buy &amp; Hold in this hypothetical comparison.
        </p>
      )}
    </section>
  )
}

const ExcludedRangeEvidence = ({ rows, years }) => {
  const selected = rows.find(row => row.role === 'selected_range')
  if (!selected) return null
  return (
    <section className="tw-report-section tw-report-excluded-evidence">
      <h3>What happened during the excluded dates?</h3>
      <p>
        From {prettyDate(selected.start_date)} to {prettyDate(selected.end_date)}, {selected.symbol}&apos;s actual market return averaged {formatPercent(selected.metrics?.average_return_pct)} per completed year and compounded to {formatPercent(selected.metrics?.cumulative_return_pct)} across the {years} years studied.
      </p>
      <p>This is supporting evidence for the research model. It is not treated as a Short trade.</p>
    </section>
  )
}

const ResearchLimitations = () => (
  <section className="tw-report-limitations">
    <strong>Research and education only</strong>
    <p>
      This report is not investment, tax, legal, or financial advice. It does not estimate taxes, trading costs, account rules, or whether repeatedly leaving and re-entering the market would be practical. It also does not test an options approach. Historical results can change and do not predict future results.
    </p>
  </section>
)

const MetricsTable = ({ rows, report }) => (
  <section className="tw-report-section">
    <h3>Results at a glance</h3>
    <div className="tw-report-table-wrap">
      <table className="tw-report-table tw-report-metrics-table">
        <thead>
          <tr>
            <th>Result</th>
            {rows.map(row => (
              <th key={`${row.role}-${row.symbol}-${row.label}`}>
                <span className="tw-report-column-label">
                  {reportRowLabel(row, report?.report_type)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricColumns.map(([key, label]) => (
            <tr key={key}>
              <th>{label}</th>
              {rows.map(row => (
                <td key={`${key}-${row.role}-${row.symbol}-${row.label}`}>{metricText(key, row.metrics?.[key], row.metrics)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    <div className="tw-report-definitions">
      <span><strong>MFE:</strong> average best move during the window.</span>
      <span><strong>MAE:</strong> average worst move against the pattern.</span>
      <span><strong>Sharpe:</strong> return compared with year-to-year variation.</span>
    </div>
  </section>
)

const YearlyTable = ({ rows, commonYears, report }) => {
  const years = (commonYears?.length
    ? [...commonYears]
    : [...new Set(rows.flatMap(row => (row.yearly_results || []).map(result => result.year)))]
  ).sort((a, b) => b - a)
  if (!years.length) return null
  return (
    <details className="tw-report-yearly">
      <summary>See year-by-year results</summary>
      <div className="tw-report-table-wrap">
        <table className="tw-report-table tw-report-yearly-table">
          <thead><tr><th>Year</th>{rows.map(row => <th key={`${row.role}-${row.symbol}-${row.label}`}>{reportRowLabel(row, report?.report_type)}</th>)}</tr></thead>
          <tbody>
            {years.map(year => (
              <tr key={year}>
                <th>{year}</th>
                {rows.map(row => {
                  const result = (row.yearly_results || []).find(item => item.year === year)
                  return <td key={`${row.role}-${row.symbol}-${row.label}-${year}`}>{formatPercent(result?.return_pct)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

const HistoryAdjustmentNote = ({ report }) => {
  const rows = report.rows || []
  const context = report.context || {}
  if (report.report_type === 'range_comparison') {
    return (
      <div className="tw-report-history-note">
        This report started with {context.requested_years} years. The excluded dates, remaining dates, and Buy &amp; Hold share {context.years_used} fully completed years, so all three results use those same {context.years_used} years.
      </div>
    )
  }
  if (report.report_type === 'date_range_comparison') {
    return (
      <div className="tw-report-history-note">
        This comparison started with {context.requested_years} years. Every date range and Buy &amp; Hold uses the same {context.years_used} completed years, so the comparison stays fair.
      </div>
    )
  }
  const baseline = rows.find(row => row.role === 'baseline') || rows[0]
  const comparisonSymbols = rows
    .filter(row => row.role === 'comparison')
    .map(row => row.symbol)
    .filter(Boolean)
  const limitedSymbols = (context.history_availability || [])
    .filter(item => Number(item.years) === Number(context.years_used) && item.symbol !== baseline?.symbol)
    .map(item => item.symbol)
  const limitingSymbol = limitedSymbols[0] || comparisonSymbols[0]
  const baselineName = baseline?.company
    ? `${baseline.company} (${baseline.symbol})`
    : baseline?.symbol
  const comparedSymbols = [baseline?.symbol, ...comparisonSymbols].filter(Boolean)
  const comparisonLabel = comparedSymbols.length === 2
    ? comparedSymbols.join(' and ')
    : 'all selected symbols'

  if (!baselineName || !limitingSymbol) {
    return (
      <div className="tw-report-history-note">
        This comparison started with {context.requested_years} years. One or more symbols have only {context.years_used} complete years for these dates, so every symbol is compared using the same {context.years_used} years.
      </div>
    )
  }

  return (
    <div className="tw-report-history-note">
      You started with a {context.requested_years}-year {baselineName} pattern. {limitingSymbol} has only {context.years_used} complete years for these dates, so this report compares {comparisonLabel} using the same {context.years_used} years.
    </div>
  )
}

export const AnalysisReportView = ({ report, onExplain }) => {
  const rows = report.rows || []
  const adjusted = report.context?.history_adjusted
  const rangeReport = report.report_type === 'range_comparison'
  const years = report.context?.years_used || rows[0]?.sample_years || rows[0]?.metrics?.sample_years
  const selected = rows.find(row => row.role === 'selected_range')
  const rangeComparisonRows = rows.filter(row => row.role === 'remaining_range' || row.role === 'buy_hold')
  return (
    <>
      <div className="tw-report-heading">
        <div>
          <div className="tw-report-eyebrow">TradeWave Analysis</div>
          <h2>{report.title}</h2>
          <p>
            {report.report_type === 'symbol_comparison'
              ? 'A side-by-side look at the same pattern across different tickers.'
              : report.report_type === 'date_range_comparison'
                ? 'Same ticker. Same historical years. Different dates. Buy & Hold is included as a reference.'
                : `${report.context?.symbol || selected?.symbol || ''} · Excluding ${prettyDate(selected?.start_date)} to ${prettyDate(selected?.end_date)} · ${years} completed years`}
          </p>
        </div>
        {adjusted && <span className="tw-report-adjusted-badge">Adjusted to common history</span>}
      </div>
      {adjusted && <HistoryAdjustmentNote report={report} />}
      <ComparedUsing report={report} />
      <PlainLanguageSummary report={report} />
      {rangeReport ? (
        <>
          <RangeModelComparison rows={rows} />
          <ExcludedRangeEvidence rows={rows} years={years} />
          <details className="tw-report-more-details">
            <summary>See more historical details</summary>
            <AverageReturnBars rows={rangeComparisonRows} report={report} />
            <MetricsTable rows={rows} report={report} />
            <YearlyTable rows={rows} commonYears={report.context?.common_years} report={report} />
          </details>
          <ResearchLimitations />
        </>
      ) : (
        <>
          <AverageReturnBars rows={rows} report={report} />
          <MetricsTable rows={rows} report={report} />
          <YearlyTable rows={rows} commonYears={report.context?.common_years} report={report} />
          {report.report_type === 'date_range_comparison' && <ResearchLimitations />}
        </>
      )}
      <div className="tw-report-footer">
        <span>Historical research only. Past results do not guarantee future results.</span>
        {onExplain && <button type="button" className="tw-report-primary" onClick={() => onExplain(report)}>Explain with Tara</button>}
      </div>
    </>
  )
}

const DialogFrame = ({ UITheme, title, onClose, children, wide = true, compact = false }) => {
  const tc = themeColors(UITheme)
  useEffect(() => {
    const oldOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = event => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = oldOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])
  return ReactDOM.createPortal(
    <div className="tw-report-overlay" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
      <div
        className={`tw-report-dialog${wide ? ' is-wide' : ''}${compact ? ' is-compact' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          '--report-bg': tc.panelBg,
          '--report-card': tc.statValueBg,
          '--report-text': tc.text,
          '--report-muted': tc.textSecondary,
          '--report-border': tc.border,
          '--report-control': tc.controlBar,
          '--report-positive': tc.barGreen,
          '--report-negative': tc.barRed,
        }}
      >
        <button type="button" className="tw-report-close" aria-label="Close report" onClick={onClose}><BsX /></button>
        <div className="tw-report-scroll">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

export const AnalysisReportDialog = ({ report, UITheme, onClose, onExplain }) => {
  if (!report) return null
  return (
    <DialogFrame UITheme={UITheme} title={report.title} onClose={onClose}>
      <AnalysisReportView report={report} onExplain={onExplain} />
    </DialogFrame>
  )
}

export const AnalysisReportNoticeDialog = ({ notice, UITheme, onClose }) => {
  if (!notice) return null
  return (
    <DialogFrame UITheme={UITheme} title={notice.title} onClose={onClose} wide={false} compact>
      <div className="tw-report-builder tw-report-notice">
        <div className="tw-report-eyebrow">Analysis Report</div>
        <h2>{notice.title}</h2>
        <p>{notice.message}</p>
        <div className="tw-report-actions">
          <button type="button" className="tw-report-primary" onClick={onClose}>Got it</button>
        </div>
      </div>
    </DialogFrame>
  )
}

export const SymbolComparisonDialog = ({
  open,
  UITheme,
  onClose,
  onExplain,
  baseline,
  viewer,
  token,
  securityTypeList2,
  resourceObj,
}) => {
  const [symbols, setSymbols] = useState([''])
  const [stage, setStage] = useState('input')
  const [error, setError] = useState('')
  const [preflight, setPreflight] = useState(null)
  const [report, setReport] = useState(null)
  const controller = useMemo(() => new AbortController(), [open]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => () => controller.abort(), [controller])
  useEffect(() => {
    if (!open) return
    setSymbols([''])
    setStage('input')
    setError('')
    setPreflight(null)
    setReport(null)
  }, [open, baseline?.symbol])

  if (!open) return null

  const updateSymbol = (index, value) => setSymbols(current => current.map((item, i) => i === index ? value.toUpperCase() : item))
  const removeSymbol = index => setSymbols(current => current.filter((_, i) => i !== index))
  const addSymbol = () => setSymbols(current => current.length < 3 ? [...current, ''] : current)
  const enteredSymbolCount = parseComparisonSymbols(symbols).length

  const buildPreflight = async () => {
    setError('')
    setStage('checking')
    try {
      const next = await preflightSymbolComparison({
        baseline,
        comparisonSymbols: symbols,
        ...viewer,
        token,
        signal: controller.signal,
        securityTypeList2,
        resourceObj,
      })
      setPreflight(next)
      if (next.history.adjustment_required) {
        setStage('adjustment')
      } else {
        await buildReport(next, next.history.years_used, false)
      }
    } catch (caught) {
      if (caught?.name === 'AbortError') return
      setError(caught instanceof AnalysisReportError ? caught.message : 'The comparison could not be prepared. Please try again.')
      setStage('input')
    }
  }

  const buildReport = async (source, years, adjustmentApproved) => {
    setError('')
    setStage('generating')
    try {
      const nextReport = await generateSymbolComparison({
        preflight: source,
        yearsUsed: years,
        adjustmentApproved,
        token,
        signal: controller.signal,
      })
      setReport(nextReport)
      setStage('report')
    } catch (caught) {
      if (caught?.name === 'AbortError') return
      if (caught?.code === 'history_changed' && caught.details?.years_used > 0) {
        const next = {
          ...source,
          history: {
            ...source.history,
            years_used: caught.details.years_used,
            adjustment_required: true,
          },
        }
        setPreflight(next)
        setError(caught.message)
        setStage('adjustment')
        return
      }
      setError(caught instanceof AnalysisReportError ? caught.message : 'The report could not be generated. Please try again.')
      setStage('input')
    }
  }

  return (
    <DialogFrame UITheme={UITheme} title="Compare Symbols" onClose={onClose} wide={stage === 'report'}>
      {stage === 'report' && report ? (
        <AnalysisReportView report={report} onExplain={onExplain} />
      ) : stage === 'adjustment' && preflight ? (
        <div className="tw-report-builder">
          <div className="tw-report-builder-icon">!</div>
          <h2>Use the same history for every symbol</h2>
          <p>
            Not every symbol has {preflight.history.requested_years} complete years for this date range.
            To make the comparison fair, every symbol must use {preflight.history.years_used} years.
          </p>
          <div className="tw-report-availability">
            {preflight.symbols.map(item => (
              <div key={`${item.market}-${item.symbol}`}><strong>{item.symbol}</strong><span>{item.available_years} years available</span></div>
            ))}
          </div>
          {error && <div className="tw-report-error">{error}</div>}
          {!preflight.history.can_generate && (
            <div className="tw-report-error">
              At least {preflight.history.minimum_years} complete years are required for this report. Change one or more symbols to continue.
            </div>
          )}
          <p className="tw-report-small">This changes only the report. Your Wave Viewer will remain at {viewer.requestedYears} years.</p>
          <div className="tw-report-actions">
            <button type="button" className="tw-report-secondary" onClick={() => { setStage('input'); setError('') }}><BsArrowLeft /> Change Symbols</button>
            <button
              type="button"
              className="tw-report-primary"
              disabled={!preflight.history.can_generate}
              onClick={() => buildReport(preflight, preflight.history.years_used, true)}
            >Use {preflight.history.years_used} Years</button>
          </div>
        </div>
      ) : (
        <div className="tw-report-builder">
          <div className="tw-report-eyebrow">Analysis Report</div>
          <h2>Compare Symbols</h2>
          <p>Compare the current pattern with up to three other symbols using the same dates, historical years, and direction.</p>
          <div className="tw-report-current-pattern">
            <span>Current pattern</span>
            <strong>{baseline.symbol}</strong>
            <small>{baseline.company}</small>
          </div>
          <div className="tw-report-symbol-fields">
            {symbols.map((symbol, index) => (
              <label key={index}>
                <span>{index === 0 ? 'Comparison symbols' : `Additional symbol ${index + 1}`}</span>
                <div>
                  <input
                    autoFocus={index === 0}
                    value={symbol}
                    maxLength={50}
                    placeholder={index === 0 ? 'Example: WMT, AVGO' : 'Ticker symbol'}
                    aria-describedby={index === 0 ? 'tw-report-symbol-help' : undefined}
                    onChange={event => updateSymbol(index, event.target.value)}
                    onKeyDown={event => { if (event.key === 'Enter') buildPreflight() }}
                  />
                  {symbols.length > 1 && <button type="button" aria-label={`Remove comparison symbol ${index + 1}`} onClick={() => removeSymbol(index)}><BsTrash /></button>}
                </div>
                {index === 0 && <small id="tw-report-symbol-help">Enter up to three tickers, separated by commas or spaces. You can also add a separate row.</small>}
              </label>
            ))}
          </div>
          {symbols.length < 3 && enteredSymbolCount < 3 && <button type="button" className="tw-report-add" onClick={addSymbol}><BsPlus /> Add another symbol</button>}
          <div className="tw-report-context-line">
            {prettyDate(viewer.startDate)} to {prettyDate(incrementEnd(viewer.startDate, viewer.daysOut))}
            {' · '}{viewer.requestedYears} requested years
            {' · '}{viewer.direction === 'short' ? 'Short' : 'Long'}
          </div>
          {error && <div className="tw-report-error">{error}</div>}
          <div className="tw-report-actions">
            <button type="button" className="tw-report-secondary" onClick={onClose}>Cancel</button>
            <button type="button" className="tw-report-primary" disabled={stage === 'checking' || stage === 'generating'} onClick={buildPreflight}>
              {stage === 'checking' ? 'Checking History…' : stage === 'generating' ? 'Building Report…' : 'Compare Symbols'}
            </button>
          </div>
        </div>
      )}
    </DialogFrame>
  )
}

const incrementEnd = (startDate, daysOut) => {
  if (!startDate || !Number(daysOut)) return ''
  const date = new Date(`${startDate}T12:00:00`)
  date.setDate(date.getDate() + Number(daysOut) - 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
