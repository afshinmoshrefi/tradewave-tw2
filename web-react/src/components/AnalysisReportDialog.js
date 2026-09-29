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
  ['cumulative_return_pct', 'Cumulative'],
]

const prettyDate = (value) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(value || ''))) return value || '—'
  const [, month, day] = value.split('-')
  const date = new Date(2000, Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
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

const leader = (rows, key) => {
  const usable = rows.filter(row => Number.isFinite(row.metrics?.[key]))
  if (!usable.length) return null
  return usable.reduce((best, row) => row.metrics[key] > best.metrics[key] ? row : best)
}

const PlainLanguageSummary = ({ report }) => {
  const rows = report.rows || []
  if (!rows.length) return null
  const years = report.context?.years_used || rows[0]?.sample_years || rows[0]?.metrics?.sample_years
  if (report.report_type === 'symbol_comparison') {
    const averageLeader = leader(rows, 'average_return_pct')
    const consistencyLeader = leader(rows, 'profitable_pct')
    return (
      <div className="tw-report-summary">
        <strong>What this comparison shows</strong>
        <p>
          These symbols were measured with one shared setup and the same {years} historical years.
          {averageLeader ? ` ${averageLeader.symbol} had the highest average return at ${formatPercent(averageLeader.metrics.average_return_pct)}.` : ''}
          {consistencyLeader ? ` ${consistencyLeader.symbol} was profitable most often at ${formatPercent(consistencyLeader.metrics.profitable_pct)} of the years.` : ''}
        </p>
        <p className="tw-report-caution">A stronger historical result does not guarantee that the symbol will lead in the future.</p>
      </div>
    )
  }

  const selected = rows.find(row => row.role === 'selected_range')
  const outside = rows.find(row => row.role === 'remaining_range')
  const buyHold = rows.find(row => row.role === 'buy_hold')
  return (
    <div className="tw-report-summary">
      <strong>What this comparison shows</strong>
      <p>
        Each result uses the same {years} completed annual cycles: the selected dates, the dates outside that range, and Buy &amp; Hold.
        {outside && buyHold
          ? ` The outside range averaged ${formatPercent(outside.metrics?.average_return_pct)}, compared with ${formatPercent(buyHold.metrics?.average_return_pct)} for Buy & Hold.`
          : ''}
        {selected ? ` The selected range averaged ${formatPercent(selected.metrics?.average_return_pct)}.` : ''}
      </p>
      <p className="tw-report-caution">The direction badge matters: TradeWave may classify the two seasonal ranges differently. Buy &amp; Hold is always Long.</p>
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
  const items = symbolComparison
    ? [
      ['Date range', `${prettyDate(context.start_date)} to ${prettyDate(context.end_date)}`],
      ['History', `${years} completed years`],
      ['Direction', context.direction === 'short' ? 'Short' : 'Long'],
      ['Year group', yearGroupLabel(context.pe_cycle)],
    ]
    : [
      ['Ticker', context.symbol || rows[0]?.symbol || '—'],
      ['History', `${years} matched annual cycles`],
      ['Year group', yearGroupLabel(context.pe_cycle)],
      ['Annual cycle starts', prettyDate(context.cohort_anchor_date || context.start_date)],
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
      {!symbolComparison && context.cohort_basis === 'selected_range_annual_cycle' && (
        <p>
          Year-by-year results are paired to the cycle that starts on {prettyDate(context.cohort_anchor_date || context.start_date)}.
          This keeps each selected window beside the outside dates that follow it.
        </p>
      )}
    </section>
  )
}

const AverageReturnBars = ({ rows }) => {
  const values = rows.map(row => row.metrics?.average_return_pct).filter(Number.isFinite)
  const maxAbs = Math.max(1, ...values.map(Math.abs))
  return (
    <section className="tw-report-section">
      <h3>Average historical return</h3>
      <div className="tw-report-bars">
        {rows.map(row => {
          const value = row.metrics?.average_return_pct
          const width = Number.isFinite(value) ? Math.min(50, (Math.abs(value) / maxAbs) * 48) : 0
          return (
            <div className="tw-report-bar-row" key={`${row.role}-${row.symbol}-${row.label}`}>
              <div className="tw-report-bar-label">{row.label || row.symbol}</div>
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

const MetricsTable = ({ rows, reportType }) => (
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
                  {reportType === 'symbol_comparison' ? (row.label || row.symbol) : row.label}
                </span>
                {reportType === 'range_comparison' && (
                  <span className={`tw-report-direction is-${row.direction}`}>{row.direction === 'short' ? 'Short' : 'Long'}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricColumns.map(([key, label]) => (
            <tr key={key}>
              <th>{label}</th>
              {rows.map(row => (
                <td key={`${key}-${row.role}-${row.symbol}`}>{metricText(key, row.metrics?.[key], row.metrics)}</td>
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

const YearlyTable = ({ rows, commonYears }) => {
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
          <thead><tr><th>Year</th>{rows.map(row => <th key={`${row.role}-${row.symbol}`}>{row.label || row.symbol}</th>)}</tr></thead>
          <tbody>
            {years.map(year => (
              <tr key={year}>
                <th>{year}</th>
                {rows.map(row => {
                  const result = (row.yearly_results || []).find(item => item.year === year)
                  return <td key={`${row.role}-${row.symbol}-${year}`}>{formatPercent(result?.return_pct)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

export const AnalysisReportView = ({ report, onExplain }) => {
  const rows = report.rows || []
  const adjusted = report.context?.history_adjusted
  return (
    <>
      <div className="tw-report-heading">
        <div>
          <div className="tw-report-eyebrow">TradeWave Analysis</div>
          <h2>{report.title}</h2>
          <p>
            {report.report_type === 'symbol_comparison'
              ? 'A side-by-side look at the same pattern across different tickers.'
              : 'Selected dates, outside dates, and Buy & Hold shown side by side.'}
          </p>
        </div>
        {adjusted && <span className="tw-report-adjusted-badge">Adjusted to common history</span>}
      </div>
      {adjusted && (
        <div className="tw-report-history-note">
          You requested {report.context.requested_years} years. This report uses {report.context.years_used} years because that is the lowest complete history available across the selected symbols.
        </div>
      )}
      <ComparedUsing report={report} />
      <PlainLanguageSummary report={report} />
      <AverageReturnBars rows={rows} />
      <MetricsTable rows={rows} reportType={report.report_type} />
      <YearlyTable rows={rows} commonYears={report.context?.common_years} />
      <div className="tw-report-footer">
        <span>Historical research only. Past performance does not guarantee future results.</span>
        {onExplain && <button type="button" className="tw-report-primary" onClick={() => onExplain(report)}>Explain with Tara</button>}
      </div>
    </>
  )
}

const DialogFrame = ({ UITheme, title, onClose, children, wide = true }) => {
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
        className={`tw-report-dialog ${wide ? 'is-wide' : ''}`}
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
