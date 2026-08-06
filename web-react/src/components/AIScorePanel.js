import React, { useContext, useEffect } from 'react'
import Tippy from '@tippyjs/react'
import { BsInfoCircle } from 'react-icons/bs'
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

const recurrenceIsValid = recurrence => {
  const sampleSize = integerOrNull(recurrence && (recurrence.sample_size ?? recurrence.sampleSize))
  const positiveYears = integerOrNull(recurrence && (recurrence.positive_years ?? recurrence.positiveYears))
  return sampleSize !== null && positiveYears !== null && sampleSize >= 0 && positiveYears >= 0 && positiveYears <= sampleSize
}

const HistoricalRecord = ({ recurrence }) => {
  if (!recurrenceIsValid(recurrence)) {
    return <span className="ai-score-panel__muted">Not provided</span>
  }

  const sampleSize = Number(recurrence.sample_size ?? recurrence.sampleSize)
  const positiveYears = Number(recurrence.positive_years ?? recurrence.positiveYears)
  const required = integerOrNull(recurrence.required_positive_years ?? recurrence.requiredPositiveYears)
  const filterMissed = String(recurrence.status || '').toLowerCase() === 'below_threshold' || (
    required !== null && positiveYears < required
  )

  return (
    <span className="ai-score-panel__history-record">
      <span>{sampleSize === 0 ? 'No completed years' : `${positiveYears} of ${sampleSize} years profitable`}</span>
      {filterMissed && required !== null && <small>Your filter needs {required} profitable years</small>}
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

const joinDayLengths = days => {
  const values = days.filter(Number.isFinite)
  if (values.length < 2) return values.join('')
  if (values.length === 2) return `${values[0]} and ${values[1]}`
  return `${values.slice(0, -1).join(', ')}, and ${values[values.length - 1]}`
}

const timeLengthExplanation = (bundle, views) => {
  const fullDays = Number(bundle && bundle.fullPatternCalendarDays)
  const days = views.map(view => Number(view && view.calendarDays)).filter(Number.isFinite)
  const dayList = joinDayLengths(days)

  if (bundle && (bundle.basis === 'minimum_horizon' || (Number.isFinite(fullDays) && fullDays < 10))) {
    return `This is a ${fullDays}-day historical pattern. AI uses 10 days because 10 days is its shortest view. The historical pattern stays ${fullDays} days.`
  }
  if (days.length > 1 && Number.isFinite(fullDays) && fullDays > 90) {
    return `Why several views? This ${fullDays}-day pattern is checked at ${dayList} days because the AI model stops at 90 days. Each view has a different ending date—not another vote on the same result.`
  }
  if (days.length === 1 && Number.isFinite(fullDays) && fullDays > 90) {
    return `This ${fullDays}-day pattern uses a ${days[0]}-day AI view because the AI model stops at 90 days.`
  }
  if (days.length > 1) {
    return `Why several views? The same start date is checked at ${dayList} days. Each view has a different ending date—not another vote on the same result.`
  }
  if (Number.isFinite(fullDays)) {
    return `This AI view checks the full ${fullDays}-day pattern.`
  }
  return 'Each AI view checks one calendar-day ending date for the selected pattern.'
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

const PanelToolbar = ({ title = '', onOpenGuide, infoTextSize }) => (
  <header className="ai-score-panel__toolbar">
    <div className="ai-score-panel__toolbar-left">
      {typeof onOpenGuide === 'function' && (
        <Tippy placement="top" content={<div theme="tw">How to read AI Scores</div>}>
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
  return metric === 'ml_score' && formatted !== 'N/A' ? `${formatted} / 100` : formatted
}

const metricTone = (view, metric) => {
  if (metric !== 'pred_return' || !view || view.status !== 'available') return ''
  const value = Number(view.metrics && view.metrics.pred_return)
  if (!Number.isFinite(value) || value === 0) return ''
  return value > 0 ? ' ai-score-panel__value--positive' : ' ai-score-panel__value--negative'
}

const AIViewTable = ({ view, displayDays, fullDays }) => {
  const days = Number(view && view.calendarDays)
  const isMain = days === Number(displayDays)
  const isFullPattern = days === Number(fullDays)
  const status = view && view.status === 'available' ? '' : opportunityAICompactStatus(view)
  const titleSuffix = isMain ? ' • Main' : isFullPattern ? ' • Full pattern' : ''

  return (
    <section
      className={`ai-score-panel__view${isMain ? ' ai-score-panel__view--main' : ''}`}
      aria-label={`${days}-day AI view${isMain ? ' (main)' : ''}`}
    >
      <div className="ai-score-panel__view-title">
        <span>{days}-Day View{titleSuffix}</span>
        {status && <small>{status}</small>}
      </div>
      <table aria-label={`${days}-day AI scores`}>
        <tbody>
          <tr>
            <th scope="row">Historical Record</th>
            <td><HistoricalRecord recurrence={view && view.selectedRecurrence} /></td>
          </tr>
          <tr>
            <th scope="row">AI Win Chance</th>
            <td>{metricDisplay(view, 'win_prob')}</td>
          </tr>
          <tr>
            <th scope="row">Estimated End Return</th>
            <td className={metricTone(view, 'pred_return')}>{metricDisplay(view, 'pred_return')}</td>
          </tr>
          <tr>
            <th scope="row">Estimated Best Move</th>
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

const AIScorePanel = ({ viewModel = {}, onOpenGuide, active = false }) => {
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
    loading = false,
    unavailableReason = '',
    bundle,
  } = viewModel || {}

  const selectedRow = selected && typeof selected === 'object' ? selected : {}
  const selectedSymbol = firstText(selectedRow.symbol, selectedRow.ticker, viewModel.symbol, bundle && bundle.symbol)
  const hasSelection = Boolean(selectedSymbol)
  const display = bundle && bundle.display
  const displayIsLoading = Boolean(loading || (display && display.status === 'loading'))
  const displayIsAvailable = Boolean(display && display.status === 'available')
  const symbol = selectedSymbol || 'Selected pattern'
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
    '--ai-main-border': UITheme === 'dark' ? '#60a5fa' : '#2563eb',
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
        <PanelToolbar infoTextSize={infoTextSize} />
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
        <PanelToolbar title={toolbarTitle} onOpenGuide={onOpenGuide} infoTextSize={infoTextSize} />
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
        <PanelToolbar title={`AI Scores for ${symbol}`} onOpenGuide={onOpenGuide} infoTextSize={infoTextSize} />
        <div className="ai-score-panel__simple-body">
          <StateMessage kind="loading" title={`Loading AI Scores for ${symbol}...`}>
            Historical results remain available while this finishes.
          </StateMessage>
        </div>
      </section>
    )
  }

  const views = availableViews(bundle, display)
  const unavailable = !displayIsAvailable ? statusDetails(display, unavailableReason) : null
  const contextItems = [
    direction,
    entryDate ? `Starts ${formatDate(entryDate)}` : '',
    fullDays !== null ? `${fullDays}-day historical pattern` : '',
    displayDays !== null ? `${displayDays}-day main AI view` : '',
  ].filter(Boolean)

  return (
    <section className="ai-score-panel" data-theme={UITheme === 'dark' ? 'dark' : 'light'} style={themeStyle} aria-label="AI Scores">
      <PanelToolbar title={toolbarTitle} onOpenGuide={onOpenGuide} infoTextSize={infoTextSize} />
      <div className="ai-score-panel__content">
        <div className="ai-score-panel__pattern-line" aria-label="Selected pattern">
          {contextItems.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
        </div>

        <div className="ai-score-panel__why-line">
          <strong>Why AI?</strong>
          <span>It adds the latest completed stock and market data as a second check beside this pattern's history.</span>
        </div>

        <div className="ai-score-panel__length-line">
          {timeLengthExplanation(bundle, views)}
        </div>

        {unavailable && (
          <StateMessage kind={unavailable.kind} title={unavailable.title}>{unavailable.copy}</StateMessage>
        )}

        <div className="ai-score-panel__views" style={{ '--ai-view-count': Math.max(views.length, 1) }}>
          {views.map(view => (
            <AIViewTable
              key={view.calendarDays}
              view={view}
              displayDays={displayDays}
              fullDays={fullDays}
            />
          ))}
        </div>

        <div className="ai-score-panel__decision-line">
          <strong>How to use it:</strong>
          <span>Start with the historical record. Then compare AI Win Chance and Estimated End Return across the views. Mixed results mean timing matters—review losing years and the Price Chart.</span>
        </div>

        <div className="ai-score-panel__footnote">
          Calendar days; the start date is day 1. AI is an estimate, not a guarantee. Do not average historical results with AI Win Chance.
        </div>
      </div>
    </section>
  )
}

export default AIScorePanel
