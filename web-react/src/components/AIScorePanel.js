import React, { useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import {
  AI_METRICS,
  formatOpportunityAIMetric,
  opportunityAICompactStatus,
  opportunityAIReasonCopy,
} from './opportunityAIScores'
import './styles/AIScorePanel.css'

const METRIC_ORDER = ['win_prob', 'pred_return', 'pred_mfe', 'ml_score']

const SERVICE_FAILURE_REASONS = new Set([
  'context_scoring_failed',
  'provider_unavailable',
  'service_unavailable',
  'tier_unavailable',
])

const METRIC_HELP = Object.freeze({
  win_prob: 'Estimated chance this setup ends with a profit.',
  pred_return: 'Estimated result at the end of this time window.',
  pred_mfe: 'Estimated best move during the window. It is not a target.',
  ml_score: '0-100 return rank. It is not a win chance.',
})

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

const metricValue = (horizon, metric) => {
  const value = horizon && horizon.metrics && horizon.metrics[metric]
  return formatOpportunityAIMetric(metric, value)
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
      <span>
        {sampleSize === 0 ? 'No completed results ' : `${positiveYears} of ${sampleSize} profitable `}
        <strong>(n={sampleSize})</strong>
      </span>
      {filterMissed && required !== null && (
        <small>Needs {required} profitable years for your filter.</small>
      )}
    </span>
  )
}

const StateMessage = ({ kind = 'neutral', title, children }) => (
  <div
    className={`ai-score-panel__state ai-score-panel__state--${kind}`}
    role={kind === 'loading' ? 'status' : undefined}
    aria-live={kind === 'loading' ? 'polite' : undefined}
  >
    <span className="ai-score-panel__state-icon" aria-hidden="true">
      {kind === 'loading' ? <span className="ai-score-panel__spinner" /> : 'i'}
    </span>
    <div>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  </div>
)

const durationExplanation = bundle => {
  if (!bundle) return ''
  const fullDays = Number(bundle.fullPatternCalendarDays)
  const displayDays = Number(bundle.displayCalendarDays)
  const comparisonDays = (bundle.horizons || [])
    .map(horizon => Number(horizon.calendarDays))
    .filter(Number.isFinite)

  if (!Number.isFinite(fullDays) || fullDays < 1) {
    return 'Every AI time length uses calendar days. The start date counts as day 1, and weekends and holidays count.'
  }

  if (bundle.basis === 'minimum_horizon' || (fullDays >= 1 && fullDays < 10)) {
    return `History keeps this ${fullDays}-calendar-day pattern. AI uses 10 calendar days because 10 days is the model's shortest supported time length. The 10-day historical check below applies only to the AI calculation.`
  }

  if (bundle.basis === 'duration_comparison' || comparisonDays.length > 1) {
    if (fullDays > 90) {
      return `This historical pattern lasts ${fullDays} calendar days. AI recalculates separate 30-, 60-, and 90-calendar-day versions. Each row has its own historical check, with the sample size shown. The main AI reading uses ${displayDays} days.`
    }
    const shorterDays = comparisonDays.filter(days => days < fullDays)
    if (shorterDays.length === 0) {
      return `AI scores the full ${fullDays}-calendar-day pattern. The start date counts as day 1, and weekends and holidays count.`
    }
    const shorterText = shorterDays.length > 1
      ? `${shorterDays.slice(0, -1).join(', ')} and ${shorterDays[shorterDays.length - 1]}`
      : shorterDays[0]
    return `AI scores the full ${fullDays}-calendar-day pattern and recalculates ${shorterText}-day version${shorterDays.length === 1 ? '' : 's'} for comparison. Each row has its own historical check, with the sample size shown. The main AI reading uses the full pattern.`
  }

  return `AI scores the full ${fullDays}-calendar-day pattern. The start date counts as day 1, and weekends and holidays count.`
}

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
      copy: 'TradeWave keeps the historical record visible below, but no AI reading is assigned for this time length.',
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

const AIScorePanel = ({ viewModel = {}, onOpenGuide }) => {
  const userContext = useContext(UserContext) || {}
  const UITheme = userContext.UITheme || 'light'
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
  const hasSelection = Boolean(selected || bundle)
  const display = bundle && bundle.display
  const horizons = bundle && Array.isArray(bundle.horizons) ? bundle.horizons : []
  const displayIsLoading = Boolean(loading || (display && display.status === 'loading'))
  const displayIsAvailable = Boolean(display && display.status === 'available')
  const anyAvailable = horizons.some(horizon => horizon && horizon.status === 'available')
  const symbol = firstText(selectedRow.symbol, selectedRow.ticker, viewModel.symbol, bundle && bundle.symbol) || 'Selected pattern'
  const direction = firstText(bundle && bundle.direction, selectedRow.direction, selectedRow.lOrS)
  const entryDate = firstText(bundle && bundle.entryDate, selectedRow.date, selectedRow.entryDate)
  const fullDays = integerOrNull(bundle && bundle.fullPatternCalendarDays)
  const dataAsOf = firstText(
    viewModel.dataAsOf,
    bundle && bundle.dataAsOf,
    bundle && bundle.scorer && bundle.scorer.data_as_of,
    bundle && bundle.metadata && bundle.metadata.data_as_of,
  )
  const directionHelp = direction.toLowerCase().startsWith('s')
    ? 'benefits if price falls'
    : 'benefits if price rises'
  const themeStyle = {
    '--ai-panel-bg': tc.panelBg,
    '--ai-panel-text': tc.text,
    '--ai-panel-muted': tc.textSecondary,
    '--ai-panel-border': tc.border,
    '--ai-panel-card': UITheme === 'dark' ? 'rgb(37, 34, 53)' : 'rgb(255, 255, 255)',
    '--ai-panel-soft': UITheme === 'dark' ? 'rgba(99, 102, 241, 0.12)' : 'rgba(79, 70, 229, 0.055)',
    '--ai-panel-soft-border': UITheme === 'dark' ? 'rgba(129, 140, 248, 0.28)' : 'rgba(79, 70, 229, 0.16)',
  }

  let mainContent
  if (!eligible) {
    mainContent = (
      <StateMessage title="AI Scores are not available for this market">
        AI Scores currently cover U.S. stocks and ETFs. Historical TradeWave results are still available for this market.
      </StateMessage>
    )
  } else if (!enabled) {
    mainContent = (
      <StateMessage title="AI Scores are not available here">
        Historical TradeWave results are still available. AI access may depend on the selected market and account level.
      </StateMessage>
    )
  } else if (!hasSelection) {
    mainContent = (
      <StateMessage title="Select a pattern to see its AI Scores">
        Choose an opportunity from the table. This window will show its main AI reading, time-length comparisons, and available historical sample sizes.
      </StateMessage>
    )
  } else if (displayIsLoading || !bundle) {
    mainContent = (
      <StateMessage kind="loading" title="Checking this pattern">
        TradeWave is calculating the AI readings for the selected pattern. Historical results remain available while this finishes.
      </StateMessage>
    )
  } else {
    const unavailable = !displayIsAvailable ? statusDetails(display, unavailableReason) : null
    mainContent = (
      <>
        <div className="ai-score-panel__context" aria-label="Selected pattern">
          <div>
            <span className="ai-score-panel__eyebrow">Selected pattern</span>
            <h3>{symbol}</h3>
          </div>
          <div className="ai-score-panel__context-chips">
            {direction && <span>{direction} <small>{directionHelp}</small></span>}
            {entryDate && <span>Starts {formatDate(entryDate)}</span>}
            {fullDays !== null && <span>{fullDays} calendar days</span>}
          </div>
        </div>

        <div className="ai-score-panel__overview">
          <div>
            <span className="ai-score-panel__eyebrow">Quick read</span>
            <p>
              History shows what happened in the years you selected. AI Scores add a separate second opinion using the latest completed stock and market data. They do not replace the historical record or guarantee the next result.
            </p>
            <p className="ai-score-panel__calibration">
              AI Win% is calibrated with older results: TradeWave checks older AI estimates against what actually happened, then uses that record to make the profit estimate more realistic.
            </p>
          </div>
          {typeof onOpenGuide === 'function' && (
            <button type="button" className="ai-score-panel__guide-button" onClick={onOpenGuide}>
              How AI Scores work
            </button>
          )}
        </div>

        <div className="ai-score-panel__duration-note">
          <span aria-hidden="true">30</span>
          <p>{durationExplanation(bundle)}</p>
        </div>

        {unavailable && (
          <StateMessage kind={unavailable.kind} title={unavailable.title}>
            {unavailable.copy}
          </StateMessage>
        )}

        <section className="ai-score-panel__reading" aria-labelledby="ai-score-main-reading-title">
          <div className="ai-score-panel__section-heading">
            <div>
              <span className="ai-score-panel__eyebrow">Main AI reading</span>
              <h4 id="ai-score-main-reading-title">{bundle.displayCalendarDays}-calendar-day view</h4>
            </div>
            {!displayIsAvailable && anyAvailable && (
              <span className="ai-score-panel__available-note">Shorter readings are available below</span>
            )}
          </div>
          <div className="ai-score-panel__metrics">
            {METRIC_ORDER.map(metric => {
              const metadata = AI_METRICS[metric]
              return (
                <article key={metric} className="ai-score-panel__metric" data-metric={metric}>
                  <span className="ai-score-panel__metric-label">{metadata.label}</span>
                  <strong>{displayIsAvailable ? metricValue(display, metric) : 'N/A'}</strong>
                  <p>{METRIC_HELP[metric]}</p>
                </article>
              )
            })}
          </div>
        </section>

        {horizons.length > 0 && (
          <section className="ai-score-panel__comparison" aria-labelledby="ai-score-comparison-title">
            <div className="ai-score-panel__section-heading">
              <div>
                <span className="ai-score-panel__eyebrow">Time-length detail</span>
                <h4 id="ai-score-comparison-title">AI readings and historical checks</h4>
              </div>
              <span className="ai-score-panel__calendar-note">All lengths use calendar days. The start date is day 1.</span>
            </div>
            <div className="ai-score-panel__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Time length</th>
                    <th scope="col">History at this length</th>
                    <th scope="col">AI Win%</th>
                    <th scope="col">Ending return</th>
                    <th scope="col">Best move</th>
                    <th scope="col">AI Score</th>
                  </tr>
                </thead>
                <tbody>
                  {horizons.map((horizon, index) => {
                    const isMain = Number(horizon.calendarDays) === Number(bundle.displayCalendarDays)
                    const available = horizon.status === 'available'
                    return (
                      <tr key={`${horizon.calendarDays}-${index}`} className={isMain ? 'ai-score-panel__main-row' : ''}>
                        <th scope="row">
                          <span>{horizon.calendarDays} days</span>
                          {isMain && <small>Main reading</small>}
                        </th>
                        <td><HistoricalRecord recurrence={horizon.selectedRecurrence} /></td>
                        {available ? (
                          <>
                            <td>{metricValue(horizon, 'win_prob')}</td>
                            <td>{metricValue(horizon, 'pred_return')}</td>
                            <td>{metricValue(horizon, 'pred_mfe')}</td>
                            <td>{metricValue(horizon, 'ml_score')}</td>
                          </>
                        ) : (
                          <td colSpan="4" className="ai-score-panel__row-status">
                            <strong>{opportunityAICompactStatus(horizon)}</strong>
                            <span>{opportunityAIReasonCopy(horizon.reason)}</span>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <div className="ai-score-panel__decision-note">
          <strong>Use AI as a second opinion.</strong>
          <span>Start with the historical result and sample size. If history and AI disagree, review the chart, losing years, and risk. Do not average historical win rate with AI Win%.</span>
        </div>

        <p className="ai-score-panel__data-note">
          AI uses stock and market data through {dataAsOf ? formatDate(dataAsOf) : 'the latest completed market day'}. It does not update during the market day.
        </p>
      </>
    )
  }

  return (
    <section
      className="ai-score-panel"
      data-theme={UITheme === 'dark' ? 'dark' : 'light'}
      style={themeStyle}
      aria-labelledby="ai-score-panel-title"
    >
      <div className="ai-score-panel__shell">
        <header className="ai-score-panel__header">
          <div className="ai-score-panel__mark" aria-hidden="true">AI</div>
          <div>
            <h2 id="ai-score-panel-title">AI Scores</h2>
            <p>A clear second opinion for the pattern you selected</p>
          </div>
        </header>
        <div className="ai-score-panel__body">{mainContent}</div>
      </div>
    </section>
  )
}

export default AIScorePanel
