import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { OpportunityAIHeaderTooltip } from './TableBox'

test('shows a compact explanation and keeps help inside the AI header tooltip', () => {
  const openHelp = jest.fn()
  render(
    <OpportunityAIHeaderTooltip
      metric="win_prob"
      detailed={false}
      onOpenHelp={openHelp}
    />
  )

  expect(screen.getByText('AI-calibrated win probability.')).toBeInTheDocument()
  const help = screen.getByRole('button', { name: 'Open the AI Scores guide' })
  expect(help).toHaveTextContent('?')
  fireEvent.click(help)
  expect(openHelp).toHaveBeenCalledTimes(1)
})

test('shows the full AI explanation when detailed tooltips are enabled', () => {
  render(
    <OpportunityAIHeaderTooltip
      metric="win_prob"
      detailed
      onOpenHelp={jest.fn()}
    />
  )

  expect(screen.getByText(/How often past cases with similar model readings/i)).toBeInTheDocument()
  expect(screen.getByText(/outlined AI value means that pattern has more than one AI duration/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Open the AI Scores guide' })).toHaveTextContent('?')
})
