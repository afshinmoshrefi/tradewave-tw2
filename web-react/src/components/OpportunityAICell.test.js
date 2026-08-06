import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import OpportunityAICell from './OpportunityAICell'

jest.mock('@tippyjs/react', () => {
  const React = require('react')
  return function MockTippy({ children, content, visible, onCreate, onShow, onHide }) {
    const [open, setOpen] = React.useState(Boolean(visible))
    React.useEffect(() => {
      const instance = {
        hide: () => { setOpen(false); if (onHide) onHide() },
      }
      if (onCreate) onCreate(instance)
    }, [onCreate, onHide])
    React.useEffect(() => {
      if (visible) setOpen(true)
    }, [visible])
    const show = () => { setOpen(true); if (onShow) onShow() }
    const child = React.cloneElement(children, {
      onMouseEnter: show,
      onFocus: show,
      onClick: event => {
        if (children.props.onClick) children.props.onClick(event)
        show()
      },
    })
    return <>{child}{open ? content : null}</>
  }
})

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

test('checkpoint cell has no visible 90d badge and exposes 30/60/90 detail on click', () => {
  const parentClick = jest.fn()
  render(
    <div onClick={parentClick}>
      <OpportunityAICell bundle={longBundle} metric="win_prob" symbol="MSFT" cellId="long-win" />
    </div>
  )

  const button = screen.getByRole('button', { name: /AI Win Probability 73%.*90-day displayed horizon with duration comparison/i })
  expect(button).toHaveClass('opp-ai-cell--checkpoint')
  expect(screen.queryByText('90d')).not.toBeInTheDocument()

  fireEvent.click(button)
  expect(parentClick).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'AI Win Probability details' })).toBeInTheDocument()
  expect(screen.getByText('30')).toBeInTheDocument()
  expect(screen.getByText('60')).toBeInTheDocument()
  expect(screen.getByText('90')).toBeInTheDocument()
  expect(screen.getByText('shown')).toBeInTheDocument()
  expect(screen.getByText(/Entry 2026-08-05.*Short/)).toBeInTheDocument()
  expect(screen.getByText(/V3 scores each recalculated duration/i)).toBeInTheDocument()
})

test('focus opens metric detail and Escape closes it while retaining a keyboard focus target', () => {
  render(<OpportunityAICell bundle={longBundle} metric="pred_return" symbol="MSFT" cellId="long-return" />)
  const button = screen.getByRole('button', { name: /Predicted Return 4.0%/i })

  button.focus()
  expect(button).toHaveAttribute('aria-expanded', 'true')
  expect(screen.getByRole('dialog', { name: 'Predicted Return details' })).toBeInTheDocument()

  fireEvent.keyDown(button, { key: 'Escape' })
  expect(button).toHaveAttribute('aria-expanded', 'false')
  expect(screen.queryByRole('dialog', { name: 'Predicted Return details' })).not.toBeInTheDocument()
  expect(button).toHaveFocus()
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
  const cellButton = screen.getByRole('button', { name: /Predicted Return 4.0%/i })
  fireEvent.click(cellButton)
  const helpButton = screen.getByRole('button', { name: 'About AI scores' })
  helpButton.focus()
  fireEvent.keyDown(helpButton, { key: 'Escape' })

  expect(screen.queryByRole('dialog', { name: 'Predicted Return details' })).not.toBeInTheDocument()
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
  expect(screen.getByText('No qualifying historical profile was available for this horizon.')).toBeInTheDocument()
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

  const button = screen.getByRole('button', { name: /Loading AI Score.*90-day displayed horizon with duration comparison/i })
  expect(button).not.toHaveTextContent('…')
  expect(button.querySelector('span[style*="animation"]')).toBeInTheDocument()
})

test('full-window score keeps the legacy numeric appearance and labels the complete window', () => {
  render(<OpportunityAICell bundle={fullBundle} metric="ml_score" symbol="AAPL" cellId="full-ais" />)
  const button = screen.getByRole('button', { name: /AI Score 70.0.*full 45-day window/i })

  expect(button).not.toHaveClass('opp-ai-cell--checkpoint')
  expect(button).toHaveTextContent('70.0')
  fireEvent.mouseEnter(button)
  expect(screen.getByText('Full 45-day pattern window')).toBeInTheDocument()
})

test('short pattern shows a ten-day label without the duration-comparison outline', () => {
  render(
    <OpportunityAICell
      bundle={minimumBundle}
      metric="ml_score"
      symbol="AAPL"
      cellId="minimum-ais"
      showMinimumHorizonLabel
    />
  )
  const button = screen.getByRole('button', {
    name: /AI Score 73.0.*10-day AI model minimum for a 6-day historical pattern/i,
  })

  expect(button).not.toHaveClass('opp-ai-cell--checkpoint')
  expect(button).toHaveTextContent('73.0')
  expect(button).toHaveTextContent('10d')
  fireEvent.click(button)
  expect(screen.getByText('10-day AI reading for a shorter pattern')).toBeInTheDocument()
  expect(screen.getByText(/6-day historical pattern; AI uses the 10-day model minimum/i)).toBeInTheDocument()
  expect(screen.getByText(/historical pattern and its statistics stay at 6 calendar days/i)).toBeInTheDocument()
  expect(screen.getByText('model minimum')).toBeInTheDocument()
  expect(screen.queryByText('current')).not.toBeInTheDocument()
})

test('first-use coachmark uses the checkpoint wording and remains actionable', () => {
  const dismiss = jest.fn()
  render(
    <OpportunityAICell
      bundle={longBundle}
      metric="ml_score"
      symbol="MSFT"
      cellId="coachmark"
      showCoachmark
      onDismissCoachmark={dismiss}
      onOpenHelp={jest.fn()}
    />
  )

  expect(screen.getByText(/table keeps the current pattern score through 90 days/i)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Got it' }))
  expect(dismiss).toHaveBeenCalled()
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

  const button = screen.getByRole('button', { name: /AI Score 74.0.*85-day displayed horizon/i })
  fireEvent.click(button)
  expect(screen.getByText('current')).toBeInTheDocument()
  expect(screen.getByText('63.0')).toBeInTheDocument()
  expect(screen.queryByText('Below threshold')).not.toBeInTheDocument()
  expect(screen.getByText(/Does not meet screen: 7 of 10 positive; requires 9.*Historical average return \+0.4%/i)).toBeInTheDocument()
  expect(screen.queryByText('90')).not.toBeInTheDocument()
})
