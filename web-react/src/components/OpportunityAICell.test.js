import React from 'react'
import { render, screen } from '@testing-library/react'
import OpportunityAICell from './OpportunityAICell'

const bundle = ({
  basis = 'full_pattern',
  fullPatternCalendarDays = 45,
  displayCalendarDays = fullPatternCalendarDays,
  status = 'available',
  reason = '',
  metrics = { ml_score: 70, win_prob: 0.73, pred_return: 4, pred_mfe: 8 },
} = {}) => ({
  basis,
  fullPatternCalendarDays,
  displayCalendarDays,
  display: { calendarDays: displayCalendarDays, status, reason, metrics },
  horizons: [{ calendarDays: displayCalendarDays, status, reason, metrics }],
})

test('renders an available AI value as a quiet, non-interactive table cell', () => {
  render(<OpportunityAICell bundle={bundle()} metric="win_prob" symbol="AAPL" />)

  const value = screen.getByLabelText(/AI Win% 73% for AAPL/i)
  expect(value).toHaveTextContent('73%')
  expect(value).toHaveClass('opp-ai-cell--available')
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('does not outline or open a popover for a multi-length score', () => {
  const comparison = bundle({
    basis: 'duration_comparison',
    fullPatternCalendarDays: 120,
    displayCalendarDays: 90,
  })
  comparison.horizons = [
    { ...comparison.display, calendarDays: 30 },
    { ...comparison.display, calendarDays: 60 },
    { ...comparison.display, calendarDays: 90 },
  ]
  render(<OpportunityAICell bundle={comparison} metric="ml_score" symbol="MSFT" />)

  const value = screen.getByLabelText(/AI Score 70.0 for MSFT/i)
  expect(value).not.toHaveClass('opp-ai-cell--checkpoint')
  expect(value).toHaveTextContent('70.0')
  expect(screen.queryByText(/30 days|60 days|90 days/i)).not.toBeInTheDocument()
})

test('shows a compact accessible loading state', () => {
  render(
    <OpportunityAICell
      bundle={bundle({ status: 'loading', metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null } })}
      metric="ml_score"
      symbol="MSFT"
    />
  )

  const loading = screen.getByLabelText('Loading AI Score for MSFT')
  expect(loading).toHaveClass('opp-ai-cell--loading')
  expect(loading).not.toHaveTextContent('…')
  expect(loading).not.toBeEmptyDOMElement()
})

test('shows a dash for unavailable data while keeping the reason accessible', () => {
  render(
    <OpportunityAICell
      bundle={bundle({ status: 'unavailable', reason: 'service_unavailable', metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null } })}
      metric="ml_score"
      symbol="MSFT"
    />
  )

  const unavailable = screen.getByLabelText(/AI Score unavailable for MSFT.*Temporarily unavailable/i)
  expect(unavailable).toHaveTextContent('—')
  expect(unavailable).toHaveClass('opp-ai-cell--unavailable')
})

test('preserves a real zero and adds no short-pattern badge', () => {
  render(
    <OpportunityAICell
      bundle={bundle({
        basis: 'minimum_horizon',
        fullPatternCalendarDays: 6,
        displayCalendarDays: 10,
        metrics: { ml_score: 0, win_prob: 0, pred_return: 0, pred_mfe: 0 },
      })}
      metric="ml_score"
      symbol="AAPL"
    />
  )

  expect(screen.getByLabelText(/AI Score 0.0 for AAPL/i)).toHaveTextContent('0.0')
  expect(screen.queryByText('10d')).not.toBeInTheDocument()
})
