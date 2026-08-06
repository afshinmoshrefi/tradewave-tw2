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

const appendToDocumentBody = () => document.body

const viewportPopperOptions = fallbackPlacements => ({
  strategy: 'fixed',
  modifiers: [
    {
      name: 'flip',
      options: {
        fallbackPlacements,
        rootBoundary: 'viewport',
        padding: 8,
      },
    },
    {
      name: 'preventOverflow',
      options: {
        rootBoundary: 'viewport',
        mainAxis: true,
        altAxis: true,
        tether: true,
        padding: 8,
      },
    },
  ],
})

const DETAIL_POPPER_OPTIONS = viewportPopperOptions(['top', 'right', 'left'])
const COACHMARK_POPPER_OPTIONS = viewportPopperOptions(['top-start', 'bottom-end', 'top-end'])

const focusableControls = root => root
  ? Array.from(root.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
  : []

const finiteNumberOrNull = value => {
  if (value === null || value === undefined || value === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const statusLabel = (metric, horizon) => {
  if (horizon.status === 'loading') return 'Loading'
  if (horizon.status !== 'available') return '—'
  return formatOpportunityAIMetric(metric, horizon.metrics[metric])
}

const recurrenceEvidence = horizon => {
  const recurrence = horizon && horizon.selectedRecurrence
  if (!recurrence || typeof recurrence !== 'object') return null
  const sample = finiteNumberOrNull(recurrence.sample_size)
  const positive = finiteNumberOrNull(recurrence.positive_years)
  const required = finiteNumberOrNull(recurrence.required_positive_years)
  const requested = finiteNumberOrNull(recurrence.requested_observations)
  if (
    sample === null || sample < 0 ||
    positive === null || positive < 0 || positive > sample ||
    required === null || required < 1 ||
    requested === null || requested < sample
  ) return null
  const average = finiteNumberOrNull(recurrence.average_return_pct)
  const recurrenceStatus = String(recurrence.status || '').toLowerCase()
  const incomplete = recurrenceStatus === 'insufficient_history' || sample < requested
  const meetsRequirement = recurrenceStatus !== 'below_threshold' && !incomplete && positive >= required
  let summary
  if (incomplete) {
    summary = `Screen check incomplete: ${sample} of ${requested} observations available; ${positive} positive; requires ${required}.`
  } else if (meetsRequirement) {
    summary = `Meets screen: ${positive} of ${sample} positive; requires ${required}.`
  } else {
    summary = `Does not meet screen: ${positive} of ${sample} positive; requires ${required}.`
  }
  return {
    summary,
    average: Number.isFinite(average) ? ` Historical average return ${average >= 0 ? '+' : ''}${average.toFixed(1)}%.` : '',
    meetsRequirement,
  }
}

const OpportunityAIDetail = ({ bundle, metric, onOpenHelp, onEscape, onTabBoundary, detailId }) => {
  const metadata = AI_METRICS[metric]
  const isDurationComparison = (
    bundle.basis === 'duration_comparison' || bundle.basis === 'checkpoint'
  ) && Array.isArray(bundle.horizons) && bundle.horizons.length > 1
  const isMinimumHorizon = bundle.basis === 'minimum_horizon'
  return (
    <div
      id={detailId}
      className="opp-ai-detail"
      role="dialog"
      aria-label={`${metadata.label} details`}
      tabIndex={-1}
      onClick={event => event.stopPropagation()}
      onKeyDown={event => {
        if (event.key === 'Escape' && onEscape) {
          onEscape(event)
        } else if (event.key === 'Tab' && onTabBoundary) {
          onTabBoundary(event)
        }
      }}
    >
      <div className="opp-ai-detail__title">
        {isDurationComparison
          ? 'How this pattern changes by duration'
          : isMinimumHorizon
            ? '10-day AI reading for a shorter pattern'
            : metadata.label}
      </div>
      {(isDurationComparison || isMinimumHorizon) && (
        <div className="opp-ai-detail__metric">{metadata.label}</div>
      )}
      <div className="opp-ai-detail__description">{metadata.description}</div>
      <div className="opp-ai-detail__basis">
        {isDurationComparison
          ? `${bundle.fullPatternCalendarDays}-day pattern duration comparison`
          : isMinimumHorizon
            ? `${bundle.fullPatternCalendarDays}-day historical pattern; AI uses the 10-day model minimum`
            : `Full ${bundle.fullPatternCalendarDays}-day pattern window`}
      </div>
      <div className="opp-ai-detail__context">
        Entry {bundle.entryDate || 'date unavailable'} · {bundle.direction || 'Direction unavailable'}
      </div>
      {isDurationComparison && (
        <div className="opp-ai-detail__checkpoint-note">
          V3 scores each recalculated duration. The recurrence line separately shows whether that duration still meets your selected historical screen.
        </div>
      )}
      {isMinimumHorizon && (
        <div className="opp-ai-detail__checkpoint-note">
          The historical pattern and its statistics stay at {bundle.fullPatternCalendarDays} calendar days. V3's shortest AI horizon is 10 calendar days, so only this separate AI reading covers 10 days.
        </div>
      )}
      <table className="opp-ai-detail__table">
        <thead>
          <tr><th>Calendar days</th><th>{metadata.shortLabel}</th></tr>
        </thead>
        <tbody>
          {bundle.horizons.map(horizon => {
            const evidence = recurrenceEvidence(horizon)
            return <tr key={horizon.calendarDays}>
              <td>
                {horizon.calendarDays}
                {horizon.isCurrent && (
                  <span className="opp-ai-detail__shown">current</span>
                )}
                {!horizon.isCurrent && bundle.fullPatternCalendarDays > 90 && horizon.calendarDays === bundle.displayCalendarDays && (
                  <span className="opp-ai-detail__shown">shown</span>
                )}
                {isMinimumHorizon && horizon.calendarDays === bundle.displayCalendarDays && (
                  <span className="opp-ai-detail__shown">model minimum</span>
                )}
              </td>
              <td>
                <span className={`opp-ai-detail__value opp-ai-detail__value--${horizon.status}`}>
                  {statusLabel(metric, horizon)}
                </span>
                {horizon.status !== 'available' && horizon.status !== 'loading' && (
                  <span className="opp-ai-detail__state">{opportunityAICompactStatus(horizon)}</span>
                )}
                {evidence && (
                  <span className="opp-ai-detail__reason">
                    {evidence.summary}
                    {!evidence.meetsRequirement ? evidence.average : ''}
                  </span>
                )}
                {horizon.status === 'unavailable' && !evidence && (
                  <span className="opp-ai-detail__reason">{opportunityAIReasonCopy(horizon.reason)}</span>
                )}
              </td>
            </tr>
          })}
        </tbody>
      </table>
      <div className="opp-ai-detail__calendar-note">Calendar days; the entry day counts as day 1.</div>
      {typeof onOpenHelp === 'function' && (
        <button
          type="button"
          className="opp-ai-detail__help"
          onClick={onOpenHelp}
        >About AI scores</button>
      )}
    </div>
  )
}

const CheckpointCoachmark = ({ onDismiss, onOpenHelp, onEscape, onTabBoundary }) => {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, 10000)
    return () => window.clearTimeout(timer)
  }, [onDismiss])

  return (
    <div
      className="opp-ai-coachmark"
      role="dialog"
      aria-label="AI duration comparison guide"
      tabIndex={-1}
      onClick={event => event.stopPropagation()}
      onKeyDown={event => {
        if (event.key === 'Escape' && onEscape) {
          onEscape(event)
        } else if (event.key === 'Tab' && onTabBoundary) {
          onTabBoundary(event)
        }
      }}
    >
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
  const coachmarkTippyRef = useRef(null)
  const buttonRef = useRef(null)
  const [open, setOpen] = useState(false)

  const handleTippyCreate = useCallback(instance => {
    tippyRef.current = instance
  }, [])
  const handleTippyShow = useCallback(() => setOpen(true), [])
  const handleTippyHide = useCallback(() => setOpen(false), [])

  const focusCellAndClearTippyDelays = useCallback(() => {
    if (buttonRef.current) buttonRef.current.focus()
    ;[tippyRef.current, coachmarkTippyRef.current].forEach(instance => {
      if (instance && typeof instance.clearDelayTimeouts === 'function') {
        instance.clearDelayTimeouts()
      }
    })
  }, [])

  const focusDetail = useCallback(() => {
    const popper = tippyRef.current && tippyRef.current.popper
    const detail = popper && popper.querySelector('.opp-ai-detail')
    if (!detail) return false
    const controls = focusableControls(detail)
    ;(controls[0] || detail).focus()
    return true
  }, [])

  const focusCoachmark = useCallback(() => {
    const popper = coachmarkTippyRef.current && coachmarkTippyRef.current.popper
    const coachmark = popper && popper.querySelector('.opp-ai-coachmark')
    if (!coachmark) return false
    const controls = focusableControls(coachmark)
    ;(controls[0] || coachmark).focus()
    return true
  }, [])

  const handleKeyDown = useCallback(event => {
    event.stopPropagation()
    if (event.key === 'Escape' && tippyRef.current) {
      event.preventDefault()
      focusCellAndClearTippyDelays()
      tippyRef.current.hide()
    } else if (event.key === 'Tab' && !event.shiftKey && showCoachmark && focusCoachmark()) {
      event.preventDefault()
    } else if (event.key === 'Tab' && !event.shiftKey && open && focusDetail()) {
      // Interactive Tippy content is portaled to document.body to escape the
      // table's scroll clips, so move focus into it explicitly.
      event.preventDefault()
    }
  }, [focusCellAndClearTippyDelays, focusCoachmark, focusDetail, open, showCoachmark])

  const handleDetailTabBoundary = useCallback(event => {
    const detail = event.currentTarget
    const controls = focusableControls(detail)
    const currentIndex = controls.indexOf(event.target)
    event.preventDefault()
    event.stopPropagation()
    if (controls.length === 0 || currentIndex < 0) {
      focusCellAndClearTippyDelays()
    } else if (event.shiftKey && currentIndex > 0) {
      controls[currentIndex - 1].focus()
    } else if (!event.shiftKey && currentIndex < controls.length - 1) {
      controls[currentIndex + 1].focus()
    } else {
      focusCellAndClearTippyDelays()
    }
  }, [focusCellAndClearTippyDelays])

  const handleCoachmarkTabBoundary = useCallback(event => {
    const coachmark = event.currentTarget
    const controls = focusableControls(coachmark)
    const currentIndex = controls.indexOf(event.target)
    event.preventDefault()
    event.stopPropagation()
    if (controls.length === 0 || currentIndex < 0) {
      focusCellAndClearTippyDelays()
    } else if (event.shiftKey && currentIndex > 0) {
      controls[currentIndex - 1].focus()
    } else if (!event.shiftKey && currentIndex < controls.length - 1) {
      controls[currentIndex + 1].focus()
    } else {
      focusCellAndClearTippyDelays()
    }
  }, [focusCellAndClearTippyDelays])

  const dismissCoachmark = useCallback(event => {
    if (event && typeof event.preventDefault === 'function') {
      event.preventDefault()
      event.stopPropagation()
    }
    focusCellAndClearTippyDelays()
    if (typeof onDismissCoachmark === 'function') onDismissCoachmark()
  }, [focusCellAndClearTippyDelays, onDismissCoachmark])

  const closeDetail = useCallback(event => {
    if (event) {
      event.preventDefault()
      event.stopPropagation()
    }
    // Focus while the popover is still open, then hide it. Focusing after hide
    // would immediately fire Tippy's focus trigger and reopen the detail.
    focusCellAndClearTippyDelays()
    if (tippyRef.current) tippyRef.current.hide()
  }, [focusCellAndClearTippyDelays])

  const openHelpFromCell = useCallback(() => {
    if (tippyRef.current) tippyRef.current.hide()
    if (onOpenHelp) onOpenHelp(buttonRef.current)
  }, [onOpenHelp])

  if (!metadata || !bundle) return <span className="opp-ai-state opp-ai-state--unavailable">—</span>

  const display = bundle && bundle.display
  const isDurationComparison = (
    bundle.basis === 'duration_comparison' || bundle.basis === 'checkpoint'
  ) && Array.isArray(bundle.horizons) && bundle.horizons.length > 1
  const isMinimumHorizon = bundle.basis === 'minimum_horizon'
  const state = display ? display.status : 'unavailable'
  const formatted = state === 'available'
    ? formatOpportunityAIMetric(metric, display.metrics[metric])
    : state === 'loading' ? '' : '—'
  const compactState = state === 'available' || state === 'loading'
    ? ''
    : opportunityAICompactStatus(display)
  const horizonCopy = isDurationComparison
    ? `${bundle.displayCalendarDays}-day displayed horizon with duration comparison`
    : isMinimumHorizon
      ? `10-day AI model minimum for a ${bundle.fullPatternCalendarDays}-day historical pattern`
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
        content={<OpportunityAIDetail bundle={bundle} metric={metric} onOpenHelp={openHelpFromCell} onEscape={closeDetail} onTabBoundary={handleDetailTabBoundary} detailId={detailId} />}
        appendTo={appendToDocumentBody}
        placement="bottom"
        popperOptions={DETAIL_POPPER_OPTIONS}
        trigger="mouseenter focus click"
        interactive
        disabled={showCoachmark}
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
        appendTo={appendToDocumentBody}
        placement="bottom-start"
        popperOptions={COACHMARK_POPPER_OPTIONS}
        maxWidth={360}
        hideOnClick={false}
        content={<CheckpointCoachmark onDismiss={dismissCoachmark} onOpenHelp={openHelpFromCell} onEscape={dismissCoachmark} onTabBoundary={handleCoachmarkTabBoundary} />}
        onCreate={instance => { coachmarkTippyRef.current = instance }}
        onClickOutside={dismissCoachmark}
      >
        {cell}
      </Tippy>
    )
  }

  return cell
}

export default OpportunityAICell
