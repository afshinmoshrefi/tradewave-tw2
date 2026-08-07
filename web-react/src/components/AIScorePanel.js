import React, { useContext, useEffect } from 'react'
import Tippy from '@tippyjs/react'
import { BsDownload, BsInfoCircle, BsPencilSquare } from 'react-icons/bs'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import {
  formatOpportunityAIMetric,
  hasAvailableOpportunityAIScores,
  opportunityAICompactStatus,
  opportunityAIReasonCopy,
} from './opportunityAIScores'
import { recordAIScoreViewed } from './aiScoreActivation'
import './styles/AIScorePanel.css'

const SERVICE_FAILURE_REASONS = new Set([
  'context_scoring_failed',
  'provider_unavailable',
  'service_unavailable',
  'tier_unavailable',
])

const firstText = (...values) => {
  const value = values.find(item => item !== null && item !== undefined && String(item).trim())
  return value === undefined ? '' : String(value).trim()
}

const integerOrNull = value => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isInteger(parsed) ? parsed : null
}

const formatDate = value => {
  const text = firstText(value)
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return text
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  if (Number.isNaN(date.getTime())) return text
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date)
}

const recurrenceDetails = recurrence => {
  const sampleSize = integerOrNull(recurrence && (recurrence.sample_size ?? recurrence.sampleSize))
  const positiveYears = integerOrNull(recurrence && (recurrence.positive_years ?? recurrence.positiveYears))
  if (sampleSize === null || positiveYears === null || sampleSize < 0 || positiveYears < 0 || positiveYears > sampleSize) {
    return null
  }
  const required = integerOrNull(recurrence.required_positive_years ?? recurrence.requiredPositiveYears)
  const filterMissed = String(recurrence.status || '').toLowerCase() === 'below_threshold' || (
    required !== null && positiveYears < required
  )
  return { sampleSize, positiveYears, required, filterMissed }
}

const HistoricalRecord = ({ recurrence }) => {
  const details = recurrenceDetails(recurrence)
  if (!details) {
    return <span className="ai-score-panel__muted">Not provided</span>
  }

  const { sampleSize, positiveYears, required, filterMissed } = details

  return (
    <span className="ai-score-panel__history-record">
      <span>{sampleSize === 0 ? 'No completed years' : `${positiveYears} of ${sampleSize} years profitable`}</span>
      {filterMissed && required !== null && <small>Below filter: needs {required} of {sampleSize}</small>}
    </span>
  )
}

const StateMessage = ({ kind = 'neutral', title, children }) => (
  <div
    className={`ai-score-panel__state ai-score-panel__state--${kind}`}
    role={kind === 'loading' ? 'status' : undefined}
    aria-live={kind === 'loading' ? 'polite' : undefined}
  >
    <strong>{title}</strong>
    <span>{children}</span>
  </div>
)

const statusDetails = (display, fallbackReason) => {
  const reason = firstText(display && display.reason, fallbackReason).toLowerCase()
  const status = firstText(display && display.status).toLowerCase()
  const recurrence = display && display.selectedRecurrence
  const historyFilterFailed = status === 'below_threshold' ||
    reason === 'selected_recurrence_below_threshold' ||
    String(recurrence && recurrence.status).toLowerCase() === 'below_threshold'
  const serviceFailure = SERVICE_FAILURE_REASONS.has(reason) ||
    reason.includes('service') ||
    reason.includes('provider') ||
    reason.includes('failed') ||
    reason.includes('error')

  if (reason === 'after_entry') {
    return {
      kind: 'neutral',
      title: 'This pattern has already started',
      copy: opportunityAIReasonCopy(reason),
    }
  }
  if (historyFilterFailed) {
    return {
      kind: 'history',
      title: 'This time length did not pass your history filter',
      copy: 'The historical record remains visible, but no AI reading was assigned for this time length.',
    }
  }
  if (serviceFailure) {
    return {
      kind: 'service',
      title: 'AI Scores are temporarily unavailable',
      copy: 'TradeWave could not finish this AI check. Your historical results are not affected. Try again shortly.',
    }
  }
  return {
    kind: 'neutral',
    title: 'No AI reading is available for this time length',
    copy: opportunityAIReasonCopy(reason),
  }
}

const availableViews = (bundle, display) => {
  const candidates = bundle && Array.isArray(bundle.horizons) && bundle.horizons.length > 0
    ? bundle.horizons
    : display ? [display] : []
  const byDays = new Map()
  candidates.forEach(view => {
    const days = Number(view && view.calendarDays)
    if (Number.isFinite(days)) byDays.set(days, view)
  })
  if (display) {
    const days = Number(display.calendarDays)
    if (Number.isFinite(days) && !byDays.has(days)) byDays.set(days, display)
  }
  return Array.from(byDays.values()).sort((a, b) => Number(a.calendarDays) - Number(b.calendarDays))
}

const ToolbarAction = ({ label, tooltip, tooltipsEnabled, onClick, children }) => (
  <Tippy disabled={!tooltipsEnabled} placement="bottom" content={<div theme="tw">{tooltip}</div>}>
    <button type="button" className="ai-score-panel__toolbar-action" aria-label={label} onClick={onClick}>
      {children}
    </button>
  </Tippy>
)

const PanelToolbar = ({
  title = '',
  onOpenGuide,
  onOpenPortfolio,
  onExportSnapshot,
  showSnapshot = false,
  tooltipsEnabled = false,
  infoTextSize,
}) => (
  <header className="ai-score-panel__toolbar">
    <div className="ai-score-panel__toolbar-left">
      {typeof onOpenPortfolio === 'function' && (
        <ToolbarAction
          label="Open Portfolio Manager"
          tooltip="Portfolio Manager"
          tooltipsEnabled={tooltipsEnabled}
          onClick={onOpenPortfolio}
        >
          <BsPencilSquare aria-hidden="true" />
        </ToolbarAction>
      )}
      {showSnapshot && typeof onExportSnapshot === 'function' && (
        <ToolbarAction
          label="Save Wave Viewer snapshot"
          tooltip="Download Wave Viewer snapshot as JPEG"
          tooltipsEnabled={tooltipsEnabled}
          onClick={onExportSnapshot}
        >
          <BsDownload aria-hidden="true" />
        </ToolbarAction>
      )}
      {typeof onOpenGuide === 'function' && (
        <Tippy placement="top" content={<div theme="tw">Why AI Scores, what they mean, and how to use them</div>}>
          <button type="button" className="ai-score-panel__info-button" aria-label="How to read AI Scores" onClick={onOpenGuide}>
            <BsInfoCircle aria-hidden="true" />
          </button>
        </Tippy>
      )}
    </div>
    <div className="ai-score-panel__toolbar-title" style={{ fontSize: infoTextSize }}>{title}</div>
    <div className="ai-score-panel__toolbar-right" aria-hidden="true" />
  </header>
)

const metricDisplay = (view, metric) => {
  if (!view || view.status !== 'available') return '—'
  const value = view.metrics && view.metrics[metric]
  const formatted = formatOpportunityAIMetric(metric, value)
  if (metric === 'ml_score' && formatted !== 'N/A') {
    return (
      <span className="ai-score-panel__rank-value">
        <span>Higher than {formatted}%</span>
        <small>of similar AI estimates</small>
      </span>
    )
  }
  return formatted
}

const metricTone = (view, metric) => {
  if (metric !== 'pred_return' || !view || view.status !== 'available') return ''
  const value = Number(view.metrics && view.metrics.pred_return)
  if (!Number.isFinite(value) || value === 0) return ''
  return value > 0 ? ' ai-score-panel__value--positive' : ' ai-score-panel__value--negative'
}

const AIViewTable = ({ view, displayDays, selectionOrigin }) => {
  const days = Number(view && view.calendarDays)
  const isTableView = days === Number(displayDays)
  const status = view && view.status === 'available' ? '' : opportunityAICompactStatus(view)
  const isViewerReading = selectionOrigin === 'wave_viewer'
  const primaryLabel = isViewerReading ? 'Used for Wave Viewer' : 'Shown in Opportunity Table'
  const primaryAriaLabel = isViewerReading ? 'used for Wave Viewer' : 'shown in Opportunity Table'

  return (
    <section
      className={`ai-score-panel__view${isTableView ? ' ai-score-panel__view--table' : ''}`}
      aria-label={`${days}-day AI checkpoint${isTableView ? ` (${primaryAriaLabel})` : ''}`}
    >
      <div className="ai-score-panel__view-title">
        <span>{days}-Day Checkpoint</span>
        {isTableView && <small>{primaryLabel}</small>}
        {status && <small>{status}</small>}
      </div>
      <table aria-label={`${days}-day AI scores`}>
        <tbody>
          <tr>
            <th scope="row">Historical Record</th>
            <td><HistoricalRecord recurrence={view && view.selectedRecurrence} /></td>
          </tr>
          <tr className="ai-score-panel__metric-row--primary">
            <th scope="row">AI Win Chance</th>
            <td>{metricDisplay(view, 'win_prob')}</td>
          </tr>
          <tr className="ai-score-panel__metric-row--primary">
            <th scope="row">Estimated End Return</th>
            <td className={metricTone(view, 'pred_return')}>{metricDisplay(view, 'pred_return')}</td>
          </tr>
          <tr>
            <th scope="row">
              <span className="ai-score-panel__metric-label">
                <span>Estimated Best Move</span>
                <small>Not a target</small>
              </span>
            </th>
            <td>{metricDisplay(view, 'pred_mfe')}</td>
          </tr>
          <tr>
            <th scope="row">AI Return Rank</th>
            <td>{metricDisplay(view, 'ml_score')}</td>
          </tr>
        </tbody>
      </table>
    </section>
  )
}

const QuickRead = ({ view, fullDays, selectionOrigin }) => {
  if (!view || view.status !== 'available') return null
  const days = Number(view.calendarDays)
  const winChance = metricDisplay(view, 'win_prob')
  const endReturn = metricDisplay(view, 'pred_return')
  const endReturnNumber = Number(view.metrics && view.metrics.pred_return)
  const history = recurrenceDetails(view.selectedRecurrence)
  const isViewerReading = selectionOrigin === 'wave_viewer'

  return (
    <div
      className="ai-score-panel__quick-read"
      aria-label={`Quick read for the ${isViewerReading ? 'Wave Viewer' : 'Opportunity Table'} AI checkpoint`}
    >
      <strong>Quick read</strong>
      <span>{isViewerReading ? 'Wave Viewer AI reading' : 'Opportunity Table AI score'} ({days} days):</span>
      <b>{winChance} AI win chance</b>
      <span aria-hidden="true">•</span>
      <b className={metricTone(view, 'pred_return')}>
        {Number.isFinite(endReturnNumber) && endReturnNumber > 0 ? '+' : ''}{endReturn} estimated end return
      </b>
      {history && (
        <>
          <span aria-hidden="true">•</span>
          <b>{history.sampleSize === 0
            ? 'No completed historical years'
            : `${history.positiveYears} of ${history.sampleSize} historical years profitable`}</b>
          {history.sampleSize > 0 && history.filterMissed && history.required !== null && (
            <em>{Number(fullDays) > days
              ? `— Shortened ${days}-day history missed your ${history.required}-of-${history.sampleSize} filter; the selected ${fullDays}-day pattern passed.`
              : `— This history missed your ${history.required}-of-${history.sampleSize} filter.`}</em>
          )}
        </>
      )}
    </div>
  )
}

const directionSummary = direction => {
  const value = firstText(direction)
  if (!value) return ''
  if (value.toLowerCase().startsWith('s')) return 'Short — a price drop helps this setup'
  if (value.toLowerCase().startsWith('l')) return 'Long — a price rise helps this setup'
  return value
}

const comparisonExplanation = (bundle, views) => {
  const fullDays = Number(bundle && bundle.fullPatternCalendarDays)
  if (bundle && (bundle.basis === 'minimum_horizon' || (Number.isFinite(fullDays) && fullDays < 10))) {
    return `History stays ${fullDays} days; AI starts at its 10-day minimum. History reports past years, while AI also uses the latest completed stock and market conditions.`
  }
  if (views.length > 1) {
    return 'History reports past years; AI also uses the latest completed stock and market conditions. Each checkpoint ends on a different date, so the numbers can differ.'
  }
  return 'History reports past years; AI also uses the latest completed stock and market conditions, so the two readings can differ.'
}

const AIScorePanel = ({
  viewModel = {},
  onOpenGuide,
  onOpenPortfolio,
  onExportSnapshot,
  tooltipsEnabled = false,
  active = false,
}) => {
  const userContext = useContext(UserContext) || {}
  const UITheme = userContext.UITheme || 'light'
  const loggedinUser = userContext.loggedinUser
  const rdd = userContext.rdd || {}
  const browserH = Number(userContext.browserH) || 0
  const browserW = Number(userContext.browserW) || 0
  const infoTextSize = userContext.infoTextSize || '1vw'
  const tc = themeColors(UITheme)
  const {
    eligible = true,
    enabled = true,
    selected,
    selectionOrigin = '',
    loading = false,
    unavailableReason = '',
    bundle,
  } = viewModel || {}

  const selectedRow = selected && typeof selected === 'object' ? selected : {}
  const selectedSymbol = firstText(selectedRow.symbol, selectedRow.ticker, viewModel.symbol, bundle && bundle.symbol)
  const hasSelection = Boolean(selectedSymbol)
  const display = bundle && bundle.display
  const isViewerReading = selectionOrigin === 'wave_viewer'
  const displayIsLoading = Boolean(loading || (display && display.status === 'loading'))
  const displayIsAvailable = Boolean(display && display.status === 'available')
  const symbol = selectedSymbol || 'Selected pattern'
  const selectedYearCount = integerOrNull(selectedRow.yearCount)
  const selectedMode = firstText(selectedRow.mode).toLowerCase()
  const selectedCycle = firstText(selectedRow.cycle).toLowerCase()
  const selectedCycleLabel = ({ pe0: 'PE', pe1: 'PE+1', pe2: 'PE+2', pe3: 'PE+3' })[selectedCycle]
  const historyLabel = selectedYearCount === null
    ? ''
    : selectedMode === 'pe'
      ? `${selectedYearCount} matching ${selectedCycleLabel || 'cycle'} years`
      : `${selectedYearCount}-year history`
  const isBuyAndHold = selectedRow.isBuyAndHold === true
  const direction = firstText(bundle && bundle.direction, selectedRow.direction, selectedRow.lOrS)
  const entryDate = firstText(bundle && bundle.entryDate, selectedRow.date, selectedRow.entryDate)
  const fullDays = integerOrNull(bundle && bundle.fullPatternCalendarDays)
  const displayDays = integerOrNull(bundle && bundle.displayCalendarDays) ??
    integerOrNull(display && display.calendarDays) ??
    fullDays
  const dataAsOf = firstText(
    viewModel.dataAsOf,
    bundle && bundle.dataAsOf,
    bundle && bundle.scorer && bundle.scorer.data_as_of,
    bundle && bundle.metadata && bundle.metadata.data_as_of,
  )
  const svFont = rdd.isMobile && !rdd.isTablet && browserH > browserW ? '10vw' : '7vw'
  const themeStyle = {
    '--ai-panel-bg': tc.panelBg,
    '--ai-panel-text': tc.text,
    '--ai-panel-muted': tc.textSecondary,
    '--ai-panel-border': tc.border,
    '--ai-control-bar': tc.controlBar,
    '--ai-control-text': tc.textOnControl,
    '--ai-stats-bar': tc.statsBarBg,
    '--ai-stat-label': tc.statLabelBg,
    '--ai-stat-value': tc.statValueBg,
    '--ai-watermark': tc.watermark,
    '--ai-table-border': UITheme === 'dark' ? '#60a5fa' : '#2563eb',
    '--ai-positive': UITheme === 'dark' ? '#22c55e' : '#15803d',
    '--ai-negative': UITheme === 'dark' ? '#f87171' : '#b91c1c',
    '--ai-warning': UITheme === 'dark' ? '#f59e0b' : '#b45309',
  }

  const hasRealScoreData = hasAvailableOpportunityAIScores({ panel: bundle })
  useEffect(() => {
    if (active !== true || !eligible || !enabled || !hasRealScoreData) return
    recordAIScoreViewed({
      loggedinUser,
      symbol: symbol === 'Selected pattern' ? undefined : symbol,
      horizon: fullDays ?? displayDays ?? undefined,
    })
  }, [active, eligible, enabled, hasRealScoreData, loggedinUser, symbol, fullDays, displayDays])

  if (!hasSelection) {
    return (
      <section className="ai-score-panel ai-score-panel--empty" data-theme={UITheme === 'dark' ? 'dark' : 'light'} style={themeStyle} aria-label="AI Scores">
        <PanelToolbar
          onOpenPortfolio={onOpenPortfolio}
          tooltipsEnabled={tooltipsEnabled}
          infoTextSize={infoTextSize}
        />
        <div className="ai-score-panel__empty-body">
          <div className="barchart-background">
            <span className="ai-score-panel__empty-label" style={{ fontSize: svFont, color: tc.watermark }}>AI Scores</span>
          </div>
        </div>
      </section>
    )
  }

  const toolbarTitle = `AI Scores for ${symbol}${dataAsOf ? ` • Data through ${formatDate(dataAsOf)}` : ''}`

  if (!eligible || !enabled) {
    return (
      <section className="ai-score-panel" data-theme={UITheme === 'dark' ? 'dark' : 'light'} style={themeStyle} aria-label="AI Scores">
        <PanelToolbar
          title={toolbarTitle}
          onOpenGuide={onOpenGuide}
          onOpenPortfolio={onOpenPortfolio}
          onExportSnapshot={onExportSnapshot}
          showSnapshot
          tooltipsEnabled={tooltipsEnabled}
          infoTextSize={infoTextSize}
        />
        <div className="ai-score-panel__simple-body">
          <StateMessage title={eligible ? 'AI Scores are not available here' : 'AI Scores are not available for this market'}>
            {eligible
              ? 'Historical TradeWave results are still available. AI access may depend on the selected market and account level.'
              : 'AI Scores currently cover U.S. stocks and ETFs. Historical TradeWave results are still available for this market.'}
          </StateMessage>
        </div>
      </section>
    )
  }

  if (displayIsLoading || !bundle) {
    return (
      <section className="ai-score-panel" data-theme={UITheme === 'dark' ? 'dark' : 'light'} style={themeStyle} aria-label="AI Scores">
        <PanelToolbar
          title={`AI Scores for ${symbol}`}
          onOpenGuide={onOpenGuide}
          onOpenPortfolio={onOpenPortfolio}
          onExportSnapshot={onExportSnapshot}
          showSnapshot
          tooltipsEnabled={tooltipsEnabled}
          infoTextSize={infoTextSize}
        />
        <div className="ai-score-panel__simple-body">
          <StateMessage kind="loading" title={`Loading AI Scores for ${symbol}...`}>
            Historical results remain available while this finishes.
          </StateMessage>
        </div>
      </section>
    )
  }

  const views = availableViews(bundle, display)
  const tableView = views.find(view => Number(view && view.calendarDays) === Number(displayDays)) || display
  const unavailable = !displayIsAvailable ? statusDetails(display, unavailableReason) : null
  const contextItems = [
    isBuyAndHold ? 'Buy & Hold' : '',
    directionSummary(direction),
    entryDate ? `Starts ${formatDate(entryDate)}` : '',
    fullDays !== null ? `${fullDays}-day historical pattern` : '',
    historyLabel,
    displayDays !== null
      ? (isViewerReading
          ? `Wave Viewer uses the ${displayDays}-day AI reading`
          : `Opportunity Table uses the ${displayDays}-day AI score`)
      : '',
  ].filter(Boolean)

  return (
    <section className="ai-score-panel" data-theme={UITheme === 'dark' ? 'dark' : 'light'} style={themeStyle} aria-label="AI Scores">
      <PanelToolbar
        title={toolbarTitle}
        onOpenGuide={onOpenGuide}
        onOpenPortfolio={onOpenPortfolio}
        onExportSnapshot={onExportSnapshot}
        showSnapshot
        tooltipsEnabled={tooltipsEnabled}
        infoTextSize={infoTextSize}
      />
      <div className="ai-score-panel__content">
        <div className="ai-score-panel__pattern-line" aria-label="Selected pattern">
          {contextItems.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>

        {displayIsAvailable && (
          <QuickRead
            view={tableView}
            fullDays={fullDays}
            selectionOrigin={selectionOrigin}
          />
        )}

        <div className="ai-score-panel__explanation-line">{comparisonExplanation(bundle, views)}</div>

        {unavailable && (
          <StateMessage kind={unavailable.kind} title={unavailable.title}>{unavailable.copy}</StateMessage>
        )}

        <div
          className="ai-score-panel__views"
          style={{
            '--ai-view-count': Math.max(views.length, 1),
            '--ai-stack-height': `${Math.max(views.length, 1) * 185}px`,
          }}
        >
          {views.map(view => (
            <AIViewTable
              key={view.calendarDays}
              view={view}
              displayDays={displayDays}
              selectionOrigin={selectionOrigin}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

export default AIScorePanel
