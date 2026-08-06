import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import OpportunityAICell from './OpportunityAICell'

const mockTippyProps = []

jest.mock('@tippyjs/react', () => {
  const React = require('react')
  return function MockTippy(props) {
    mockTippyProps.push(props)
    const { children, content, visible, disabled, delay, onCreate, onShow, onHide } = props
    const [open, setOpen] = React.useState(Boolean(visible))
    const openRef = React.useRef(Boolean(visible))
    const popperRef = React.useRef(null)
    const showTimeoutRef = React.useRef(null)
    const clearDelayTimeouts = () => {
      if (showTimeoutRef.current) clearTimeout(showTimeoutRef.current)
      showTimeoutRef.current = null
    }
    const show = () => {
      if (disabled) return
      openRef.current = true
      setOpen(true)
      if (onShow) onShow()
    }
    const scheduleFocusShow = () => {
      if (disabled) return
      const showDelay = Array.isArray(delay) ? delay[0] : Number(delay) || 0
      if (openRef.current && showDelay > 0) {
        clearDelayTimeouts()
        showTimeoutRef.current = setTimeout(show, showDelay)
      } else {
        show()
      }
    }
    React.useEffect(() => {
      const instance = {
        get popper() { return popperRef.current },
        clearDelayTimeouts,
        hide: () => {
          openRef.current = false
          setOpen(false)
          if (onHide) onHide()
        },
      }
      if (onCreate) onCreate(instance)
    })
    React.useEffect(() => {
      if (visible) {
        openRef.current = true
        setOpen(true)
      }
    }, [visible])
    React.useEffect(() => () => clearDelayTimeouts(), [])
    const child = React.cloneElement(children, {
      onMouseEnter: show,
      onFocus: scheduleFocusShow,
      onClick: event => {
        if (children.props.onClick) children.props.onClick(event)
        show()
      },
    })
    return <>{child}{open ? <div ref={popperRef}>{content}</div> : null}</>
  }
})

beforeEach(() => {
  mockTippyProps.length = 0
})

afterEach(() => {
  jest.useRealTimers()
})

const latestTippyProps = maxWidth => [...mockTippyProps]
  .reverse()
  .find(props => props.maxWidth === maxWidth)

const expectViewportPopper = props => {
  expect(props.appendTo()).toBe(document.body)
  expect(props.popperOptions.strategy).toBe('fixed')
  const flip = props.popperOptions.modifiers.find(modifier => modifier.name === 'flip')
  const preventOverflow = props.popperOptions.modifiers.find(modifier => modifier.name === 'preventOverflow')
  expect(flip.options).toMatchObject({ rootBoundary: 'viewport', padding: 8 })
  expect(preventOverflow.options).toMatchObject({
    rootBoundary: 'viewport',
    mainAxis: true,
    altAxis: true,
    tether: true,
    padding: 8,
  })
}

const longBundle = {
  key: 'MSFT|119|s',
  basis: 'duration_comparison',
  fullPatternCalendarDays: 120,
  entryDate: '2026-08-05',
  direction: 'Short',
  displayCalendarDays: 90,
  display: {
    calendarDays: 90,
    status: 'available',
    reason: '',
    metrics: { ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 },
  },
  horizons: [
    { calendarDays: 30, status: 'available', reason: '', metrics: { ml_score: 51, win_prob: 0.52, pred_return: 1, pred_mfe: 3 } },
    { calendarDays: 60, status: 'available', reason: '', metrics: { ml_score: 63, win_prob: 0.64, pred_return: 2, pred_mfe: 5 } },
    { calendarDays: 90, status: 'available', reason: '', metrics: { ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 } },
  ],
}

const midLengthComparisonBundle = {
  ...longBundle,
  key: 'MSFT|44|s',
  fullPatternCalendarDays: 45,
  displayCalendarDays: 45,
  display: {
    calendarDays: 45,
    status: 'available',
    reason: '',
    metrics: { ml_score: 66, win_prob: 0.61, pred_return: 2.2, pred_mfe: 4.6 },
  },
  horizons: [
    { calendarDays: 30, status: 'available', reason: '', metrics: { ml_score: 51, win_prob: 0.52, pred_return: 1, pred_mfe: 3 } },
    { calendarDays: 45, status: 'available', reason: '', metrics: { ml_score: 66, win_prob: 0.61, pred_return: 2.2, pred_mfe: 4.6 } },
  ],
}

const fullBundle = {
  key: 'AAPL|44|l',
  basis: 'full_pattern',
  fullPatternCalendarDays: 45,
  entryDate: '2026-08-05',
  direction: 'Long',
  displayCalendarDays: 45,
  display: {
    calendarDays: 45,
    status: 'available',
    reason: '',
    metrics: { ml_score: 70, win_prob: 0.65, pred_return: 3, pred_mfe: 6 },
  },
  horizons: [
    { calendarDays: 45, status: 'available', reason: '', metrics: { ml_score: 70, win_prob: 0.65, pred_return: 3, pred_mfe: 6 } },
  ],
}

const minimumBundle = {
  key: 'AAPL|5|l',
  basis: 'minimum_horizon',
  fullPatternCalendarDays: 6,
  minimumModelCalendarDays: 10,
  entryDate: '2026-08-05',
  direction: 'Long',
  displayCalendarDays: 10,
  display: {
    calendarDays: 10,
    status: 'available',
    isCurrent: false,
    isModelMinimum: true,
    reason: '',
    metrics: { ml_score: 73, win_prob: 0.69, pred_return: 2.5, pred_mfe: 4.9 },
  },
  horizons: [{
    calendarDays: 10,
    status: 'available',
    isCurrent: false,
    isModelMinimum: true,
    reason: '',
    metrics: { ml_score: 73, win_prob: 0.69, pred_return: 2.5, pred_mfe: 4.9 },
  }],
}

test('outlined cell has no visible 90d badge and explains its 30/60/90 comparison on click', () => {
  const parentClick = jest.fn()
  render(
    <div onClick={parentClick}>
      <OpportunityAICell bundle={longBundle} metric="win_prob" symbol="MSFT" cellId="long-win" />
    </div>
  )

  const button = screen.getByRole('button', { name: /AI Win% 73%.*90-day table value; more time lengths available/i })
  expect(button).toHaveClass('opp-ai-cell--checkpoint')
  expect(screen.queryByText('90d')).not.toBeInTheDocument()

  fireEvent.click(button)
  expect(parentClick).not.toHaveBeenCalled()
  const detail = screen.getByRole('dialog', { name: 'AI Win% details' })
  expect(detail).toBeInTheDocument()
  expect(screen.getByText('30')).toBeInTheDocument()
  expect(screen.getByText('60')).toBeInTheDocument()
  expect(screen.getByText('90')).toBeInTheDocument()
  expect(screen.getByText('table value')).toBeInTheDocument()
  expect(screen.getByText(/Pattern starts 2026-08-05.*Short \(benefits if price falls\)/)).toBeInTheDocument()
  expect(screen.getByText(/Each row is recalculated and scored for that many calendar days/i)).toBeInTheDocument()
  expect(detail).toHaveTextContent(/Compare the rows to see how the AI view changes over time/i)
  expect(detail).not.toHaveTextContent(/V3|horizon|recurrence|feature vector|profile/i)
})

test('focus opens metric detail and Escape closes it while retaining a keyboard focus target', () => {
  render(<OpportunityAICell bundle={longBundle} metric="pred_return" symbol="MSFT" cellId="long-return" />)
  const button = screen.getByRole('button', { name: /Predicted Ending Return 4.0%/i })

  button.focus()
  expect(button).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('dialog', { name: 'Predicted Ending Return details' })).toBeInTheDocument()

  fireEvent.keyDown(button, { key: 'Escape' })
  expect(button).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('dialog', { name: 'Predicted Ending Return details' })).not.toBeInTheDocument()
  expect(button).toHaveFocus()
})

test('portaled detail preserves Tab, Shift+Tab, and Escape focus flow', () => {
  jest.useFakeTimers()
  render(
    <OpportunityAICell
      bundle={longBundle}
      metric="pred_return"
      symbol="MSFT"
      cellId="long-return-tab-flow"
      onOpenHelp={jest.fn()}
    />
  )
  const cellButton = screen.getByRole('button', { name: /Predicted Ending Return 4.0%/i })
  cellButton.focus()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  const helpButton = screen.getByRole('button', { name: 'How to use AI Scores' })
  expect(helpButton).toHaveFocus()

  fireEvent.keyDown(helpButton, { key: 'Tab', shiftKey: true })
  expect(cellButton).toHaveFocus()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  expect(helpButton).toHaveFocus()
  fireEvent.keyDown(helpButton, { key: 'Tab' })
  expect(cellButton).toHaveFocus()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  expect(helpButton).toHaveFocus()
  fireEvent.keyDown(helpButton, { key: 'Escape' })
  expect(screen.queryByRole('dialog', { name: 'Predicted Ending Return details' })).not.toBeInTheDocument()
  expect(cellButton).toHaveFocus()
  act(() => { jest.advanceTimersByTime(200) })
  expect(screen.queryByRole('dialog', { name: 'Predicted Ending Return details' })).not.toBeInTheDocument()
})

test('detail and coachmark portal outside table clips with viewport-aware placement', () => {
  render(
    <OpportunityAICell
      bundle={longBundle}
      metric="ml_score"
      symbol="MSFT"
      cellId="viewport-config"
      showCoachmark
      onDismissCoachmark={jest.fn()}
      onOpenHelp={jest.fn()}
    />
  )

  const detail = latestTippyProps(340)
  expect(detail.placement).toBe('bottom')
  expectViewportPopper(detail)
  expect(detail.popperOptions.modifiers.find(modifier => modifier.name === 'flip').options.fallbackPlacements)
    .toEqual(['top', 'right', 'left'])

  const coachmark = latestTippyProps(360)
  expect(coachmark.placement).toBe('bottom-start')
  expectViewportPopper(coachmark)
  expect(coachmark.popperOptions.modifiers.find(modifier => modifier.name === 'flip').options.fallbackPlacements)
    .toEqual(['top-start', 'bottom-end', 'top-end'])
})

test('Escape from an interactive popover control closes details and returns focus to the cell', () => {
  render(
    <OpportunityAICell
      bundle={longBundle}
      metric="pred_return"
      symbol="MSFT"
      cellId="long-return-help"
      onOpenHelp={jest.fn()}
    />
  )
  const cellButton = screen.getByRole('button', { name: /Predicted Ending Return 4.0%/i })
  fireEvent.click(cellButton)
  const helpButton = screen.getByRole('button', { name: 'How to use AI Scores' })
  helpButton.focus()
  fireEvent.keyDown(helpButton, { key: 'Escape' })

  expect(screen.queryByRole('dialog', { name: 'Predicted Ending Return details' })).not.toBeInTheDocument()
  expect(cellButton).toHaveFocus()
})

test('unavailable checkpoint shows a dash, compact state, and stable backend reason', () => {
  const bundle = {
    ...longBundle,
    display: { ...longBundle.display, status: 'unavailable', reason: 'pattern_profile_unavailable' },
    horizons: longBundle.horizons.map(item => item.calendarDays === 90
      ? { ...item, status: 'unavailable', reason: 'pattern_profile_unavailable' }
      : item),
  }
  render(<OpportunityAICell bundle={bundle} metric="ml_score" symbol="MSFT" cellId="long-ais-unavailable" />)
  const button = screen.getByRole('button', { name: /AI Score not assigned.*Temporarily unavailable/i })

  expect(button).toHaveTextContent('—')
  expect(button).toHaveTextContent('Temporarily unavailable')
  fireEvent.click(button)
  expect(screen.getByText('There is not enough usable history to score this time length.')).toBeInTheDocument()
})

test('loading uses an accessible spinner instead of ambiguous dots', () => {
  const bundle = {
    ...longBundle,
    display: { ...longBundle.display, status: 'loading' },
    horizons: longBundle.horizons.map(item => item.calendarDays === 90
      ? { ...item, status: 'loading' }
      : item),
  }
  render(<OpportunityAICell bundle={bundle} metric="ml_score" symbol="MSFT" cellId="long-ais-loading" />)

  const button = screen.getByRole('button', { name: /Loading AI Score.*90-day table value; more time lengths available/i })
  expect(button).not.toHaveTextContent('…')
  expect(button).not.toBeEmptyDOMElement()
})

test('full-pattern score keeps the numeric appearance and names the time length plainly', () => {
  render(<OpportunityAICell bundle={fullBundle} metric="ml_score" symbol="AAPL" cellId="full-ais" />)
  const button = screen.getByRole('button', { name: /AI Score 70.0.*full 45-day pattern/i })

  expect(button).not.toHaveClass('opp-ai-cell--checkpoint')
  expect(button).toHaveTextContent('70.0')
  fireEvent.mouseEnter(button)
  expect(screen.getByText('AI uses the full 45-day pattern')).toBeInTheDocument()
})

test('short pattern explains the ten-day minimum in details without adding a cell tag', () => {
  render(
    <OpportunityAICell
      bundle={minimumBundle}
      metric="ml_score"
      symbol="AAPL"
      cellId="minimum-ais"
    />
  )
  const button = screen.getByRole('button', {
    name: /AI Score 73.0.*10-day AI minimum for a 6-day historical pattern/i,
  })

  expect(button).not.toHaveClass('opp-ai-cell--checkpoint')
  expect(button).toHaveTextContent('73.0')
  expect(button).not.toHaveTextContent('10d')
  fireEvent.click(button)
  const detail = screen.getByRole('dialog', { name: 'AI Score details' })
  expect(screen.getByText('Why AI uses 10 days here')).toBeInTheDocument()
  expect(screen.getByText(/History uses the real 6-day pattern; this AI reading uses 10 days/i)).toBeInTheDocument()
  expect(screen.getByText(/AI's shortest supported length is 10 days.*historical results still use 6 days/i)).toBeInTheDocument()
  expect(screen.getByText('AI minimum')).toBeInTheDocument()
  expect(screen.queryByText('current')).not.toBeInTheDocument()
  expect(detail).not.toHaveTextContent(/horizon|feature vector|recurrence|profile/i)
})

test('first-use coachmark accurately covers a mid-length comparison and stays until dismissed', () => {
  jest.useFakeTimers()
  const dismiss = jest.fn()
  render(
    <OpportunityAICell
      bundle={midLengthComparisonBundle}
      metric="ml_score"
      symbol="MSFT"
      cellId="coachmark"
      showCoachmark
      onDismissCoachmark={dismiss}
      onOpenHelp={jest.fn()}
    />
  )

  expect(screen.getByText('Compare time lengths')).toBeInTheDocument()
  const coachmark = screen.getByRole('dialog', { name: 'AI time-length comparison guide' })
  expect(coachmark).toHaveTextContent(/An outline means more than one AI time length is available/i)
  expect(coachmark).toHaveTextContent(/compare all the time lengths scored for this pattern/i)
  expect(coachmark).toHaveTextContent(/not a warning or a better\/worse rating/i)
  expect(coachmark).not.toHaveTextContent(/30-|60-|90-day views/i)

  act(() => { jest.advanceTimersByTime(10001) })
  expect(dismiss).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'AI time-length comparison guide' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
  expect(dismiss).toHaveBeenCalledTimes(1)
})

test('portaled coachmark owns keyboard focus until dismissal and suppresses inner detail', () => {
  const dismiss = jest.fn()
  render(
    <OpportunityAICell
      bundle={longBundle}
      metric="ml_score"
      symbol="MSFT"
      cellId="coachmark-keyboard"
      showCoachmark
      onDismissCoachmark={dismiss}
      onOpenHelp={jest.fn()}
    />
  )

  const cellButton = screen.getByRole('button', { name: /AI Score 78.0/i })
  cellButton.focus()
  expect(screen.queryByRole('dialog', { name: 'AI Score details' })).not.toBeInTheDocument()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  const learnMore = screen.getByRole('button', { name: 'Learn more' })
  const gotIt = screen.getByRole('button', { name: 'Got it' })
  expect(learnMore).toHaveFocus()

  fireEvent.keyDown(learnMore, { key: 'Tab' })
  expect(gotIt).toHaveFocus()
  fireEvent.keyDown(gotIt, { key: 'Tab' })
  expect(cellButton).toHaveFocus()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  expect(learnMore).toHaveFocus()
  fireEvent.keyDown(learnMore, { key: 'Tab', shiftKey: true })
  expect(cellButton).toHaveFocus()

  fireEvent.keyDown(cellButton, { key: 'Tab' })
  fireEvent.keyDown(learnMore, { key: 'Escape' })
  expect(dismiss).toHaveBeenCalledTimes(1)
  expect(cellButton).toHaveFocus()
})

test('an 85-day pattern keeps its current score and compares only 30 and 60 days', () => {
  const bundle = {
    ...longBundle,
    key: 'AAPL|2026-08-05|84|l',
    fullPatternCalendarDays: 85,
    displayCalendarDays: 85,
    display: {
      calendarDays: 85,
      status: 'available',
      isCurrent: true,
      reason: '',
      metrics: { ml_score: 74, win_prob: 0.68, pred_return: 2.4, pred_mfe: 5.2 },
    },
    horizons: [
      longBundle.horizons[0],
      {
        ...longBundle.horizons[1],
        status: 'available',
        metrics: { ml_score: 63, win_prob: 0.64, pred_return: 2, pred_mfe: 5 },
        selectedRecurrence: {
          status: 'below_threshold',
          sample_size: 10,
          positive_years: 7,
          required_positive_years: 9,
          requested_observations: 10,
          average_return_pct: 0.4,
        },
      },
      {
        calendarDays: 85,
        status: 'available',
        isCurrent: true,
        reason: '',
        metrics: { ml_score: 74, win_prob: 0.68, pred_return: 2.4, pred_mfe: 5.2 },
      },
    ],
  }
  render(<OpportunityAICell bundle={bundle} metric="ml_score" symbol="AAPL" cellId="85-day" />)

  const button = screen.getByRole('button', { name: /AI Score 74.0.*85-day table value/i })
  fireEvent.click(button)
  expect(screen.getByText('table value')).toBeInTheDocument()
  expect(screen.getByText('63.0')).toBeInTheDocument()
  expect(screen.queryByText('Below threshold')).not.toBeInTheDocument()
  expect(screen.getByText(/History filter not met: 7 of 10 past results were profitable in this direction \(needs 9\).*Average historical result: \+0.4%/i)).toBeInTheDocument()
  expect(screen.queryByText('90')).not.toBeInTheDocument()
})
