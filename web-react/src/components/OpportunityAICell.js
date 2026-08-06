import React, { useCallback, useEffect, useRef, useState } from 'react'
import Tippy from '@tippyjs/react'
import { CellSpinner } from './Common'
import {
  AI_METRICS,
  formatOpportunityAIMetric,
  opportunityAICompactStatus,
  opportunityAIReasonCopy,
} from './opportunityAIScores'

const safeIdPart = value => String(value || '').replace(/[^a-zA-Z0-9_-]/g, '-')

const statusLabel = (metric, horizon) => {
  if (horizon.status === 'loading') return 'Loading'
  if (horizon.status !== 'available') return '—'
  return formatOpportunityAIMetric(metric, horizon.metrics[metric])
}

const recurrenceEvidence = horizon => {
  const recurrence = horizon && horizon.selectedRecurrence
  if (!recurrence || typeof recurrence !== 'object') return null
  const sample = Number(recurrence.sample_size)
  const positive = Number(recurrence.positive_years)
  const required = Number(recurrence.required_positive_years)
  if (!Number.isFinite(sample) || !Number.isFinite(positive) || !Number.isFinite(required) || sample <= 0) return null
  const average = Number(recurrence.average_return_pct)
  return {
    summary: `${positive} of ${sample} positive; requires ${required} of ${Number(recurrence.requested_observations) || sample}.`,
    average: Number.isFinite(average) ? ` Historical average return ${average >= 0 ? '+' : ''}${average.toFixed(1)}%.` : '',
  }
}

const OpportunityAIDetail = ({ bundle, metric, onOpenHelp, onEscape, detailId }) => {
  const metadata = AI_METRICS[metric]
  const isDurationComparison = bundle.basis === 'duration_comparison' || bundle.basis === 'checkpoint'
  return (
    <div
      id={detailId}
      className="opp-ai-detail"
      role="dialog"
      aria-label={`${metadata.label} details`}
      onClick={event => event.stopPropagation()}
      onKeyDown={event => {
        if (event.key === 'Escape' && onEscape) onEscape(event)
      }}
    >
      <div className="opp-ai-detail__title">
        {isDurationComparison
          ? 'How this pattern changes by duration'
          : metadata.label}
      </div>
      {isDurationComparison && (
        <div className="opp-ai-detail__metric">{metadata.label}</div>
      )}
      <div className="opp-ai-detail__description">{metadata.description}</div>
      <div className="opp-ai-detail__basis">
        {isDurationComparison
          ? `${bundle.fullPatternCalendarDays}-day pattern duration comparison`
          : `Full ${bundle.fullPatternCalendarDays}-day pattern window`}
      </div>
      <div className="opp-ai-detail__context">
        Entry {bundle.entryDate || 'date unavailable'} · {bundle.direction || 'Direction unavailable'}
      </div>
      {isDurationComparison && (
        <div className="opp-ai-detail__checkpoint-note">
          The same selected historical recurrence is checked at each shorter duration. V3 assigns an AI reading only when that recalculated pattern still meets the requirement.
        </div>
      )}
      <table className="opp-ai-detail__table">
        <thead>
          <tr><th>Calendar days</th><th>{metadata.shortLabel}</th></tr>
        </thead>
        <tbody>
          {bundle.horizons.map(horizon => (
            <tr key={horizon.calendarDays}>
              <td>
                {horizon.calendarDays}
                {horizon.isCurrent && (
                  <span className="opp-ai-detail__shown">current</span>
                )}
                {!horizon.isCurrent && bundle.fullPatternCalendarDays > 90 && horizon.calendarDays === bundle.displayCalendarDays && (
                  <span className="opp-ai-detail__shown">shown</span>
                )}
              </td>
              <td>
                <span className={`opp-ai-detail__value opp-ai-detail__value--${horizon.status}`}>
                  {statusLabel(metric, horizon)}
                </span>
                {horizon.status !== 'available' && horizon.status !== 'loading' && (
                  <span className="opp-ai-detail__state">{opportunityAICompactStatus(horizon)}</span>
                )}
                {recurrenceEvidence(horizon) && (
                  <span className="opp-ai-detail__reason">
                    {recurrenceEvidence(horizon).summary}
                    {horizon.status === 'below_threshold' ? recurrenceEvidence(horizon).average : ''}
                  </span>
                )}
                {horizon.status === 'unavailable' && !recurrenceEvidence(horizon) && (
                  <span className="opp-ai-detail__reason">{opportunityAIReasonCopy(horizon.reason)}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="opp-ai-detail__calendar-note">Calendar days; the entry day counts as day 1.</div>
      {typeof onOpenHelp === 'function' && (
        <button
          type="button"
          className="opp-ai-detail__help"
          onClick={onOpenHelp}
          onKeyDown={event => {
            if (event.key === 'Escape' && onEscape) onEscape(event)
          }}
        >About AI scores</button>
      )}
    </div>
  )
}

const CheckpointCoachmark = ({ onDismiss, onOpenHelp }) => {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 10000)
    return () => window.clearTimeout(timer)
  }, [onDismiss])

  return (
    <div className="opp-ai-coachmark" role="status" onClick={event => event.stopPropagation()}>
      <div className="opp-ai-coachmark__title">Duration comparison</div>
      <div>The table keeps the current pattern score through 90 days. Hover or tap to compare the shorter 30- and 60-day readings; longer patterns also include 90 days.</div>
      <div className="opp-ai-coachmark__actions">
        <button type="button" onClick={() => { onDismiss(); if (onOpenHelp) onOpenHelp() }}>Learn more</button>
        <button type="button" onClick={onDismiss}>Got it</button>
      </div>
    </div>
  )
}

const OpportunityAICell = ({
  bundle,
  metric,
  symbol,
  cellId,
  showCoachmark = false,
  onDismissCoachmark,
  onOpenHelp,
}) => {
  const metadata = AI_METRICS[metric]
  const tippyRef = useRef(null)
  const buttonRef = useRef(null)
  const [open, setOpen] = useState(false)

  const handleTippyCreate = useCallback(instance => {
    tippyRef.current = instance
  }, [])
  const handleTippyShow = useCallback(() => setOpen(true), [])
  const handleTippyHide = useCallback(() => setOpen(false), [])

  const handleKeyDown = useCallback(event => {
    event.stopPropagation()
    if (event.key === 'Escape' && tippyRef.current) {
      event.preventDefault()
      tippyRef.current.hide()
      if (buttonRef.current) buttonRef.current.focus()
    }
  }, [])

  const closeDetail = useCallback(event => {
    if (event) {
      event.preventDefault()
      event.stopPropagation()
    }
    // Focus while the popover is still open, then hide it. Focusing after hide
    // would immediately fire Tippy's focus trigger and reopen the detail.
    if (buttonRef.current) buttonRef.current.focus()
    if (tippyRef.current) tippyRef.current.hide()
  }, [])

  const openHelpFromCell = useCallback(() => {
    if (tippyRef.current) tippyRef.current.hide()
    if (onOpenHelp) onOpenHelp(buttonRef.current)
  }, [onOpenHelp])

  if (!metadata || !bundle) return <span className="opp-ai-state opp-ai-state--unavailable">—</span>

  const display = bundle && bundle.display
  const isDurationComparison = bundle.basis === 'duration_comparison' || bundle.basis === 'checkpoint'
  const state = display ? display.status : 'unavailable'
  const formatted = state === 'available'
    ? formatOpportunityAIMetric(metric, display.metrics[metric])
    : state === 'loading' ? '' : '—'
  const compactState = state === 'available' || state === 'loading'
    ? ''
    : opportunityAICompactStatus(display)
  const horizonCopy = isDurationComparison
    ? `${bundle.displayCalendarDays}-day displayed horizon with duration comparison`
    : `full ${bundle ? bundle.fullPatternCalendarDays : ''}-day window`
  const detailId = `opp-ai-detail-${safeIdPart(cellId || `${symbol}-${metric}-${bundle && bundle.key}`)}`
  const ariaLabel = state === 'loading'
    ? `Loading ${metadata.label} for ${symbol}, ${horizonCopy}`
    : state !== 'available'
      ? `${metadata.label} not assigned for ${symbol}, ${horizonCopy}. ${compactState}. Open details.`
      : `${metadata.label} ${formatted} for ${symbol}, ${horizonCopy}. Open details.`

  const cell = (
    <span className="opp-ai-cell-wrap">
      <Tippy
        content={<OpportunityAIDetail bundle={bundle} metric={metric} onOpenHelp={openHelpFromCell} onEscape={closeDetail} detailId={detailId} />}
        placement="top"
        trigger="mouseenter focus click"
        interactive
        maxWidth={340}
        delay={[120, 80]}
        onCreate={handleTippyCreate}
        onShow={handleTippyShow}
        onHide={handleTippyHide}
        onClickOutside={instance => instance.hide()}
      >
        <button
          ref={buttonRef}
          type="button"
          className={`opp-ai-cell opp-ai-cell--${state}${isDurationComparison ? ' opp-ai-cell--checkpoint' : ''}`}
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls={detailId}
          onClick={event => event.stopPropagation()}
          onKeyDown={handleKeyDown}
        >
          <span className="opp-ai-cell__value" aria-hidden="true">
            {state === 'loading' ? <CellSpinner /> : formatted}
          </span>
          {compactState && (
            <span className="opp-ai-cell__status" aria-hidden="true">{compactState}</span>
          )}
        </button>
      </Tippy>
    </span>
  )

  if (showCoachmark && typeof onDismissCoachmark === 'function') {
    return (
      <Tippy
        visible
        interactive
        placement="bottom-start"
        maxWidth={360}
        hideOnClick={false}
        content={<CheckpointCoachmark onDismiss={onDismissCoachmark} onOpenHelp={openHelpFromCell} />}
        onClickOutside={onDismissCoachmark}
      >
        {cell}
      </Tippy>
    )
  }

  return cell
}

export default OpportunityAICell
