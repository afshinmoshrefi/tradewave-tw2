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

  expect(screen.getByText('AI-calibrated chance of a profitable result.')).toBeInTheDocument()
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

  const explanation = screen.getByText(/An outline means you can open the value/i)
  expect(explanation.textContent).toMatch(/^An outline means/i)
  expect(explanation).toHaveTextContent(/not a warning or a quality grade/i)
  expect(explanation).toHaveTextContent(/older cases with similar AI estimates.*share that later finished profitable/i)
  expect(explanation).toHaveTextContent(/checks it against real outcomes/i)
  expect(explanation).toHaveTextContent(/shorter than 10 days use a 10-day AI reading/i)
  expect(explanation).not.toHaveTextContent(/horizon|feature vector|recurrence|profile/i)
  expect(screen.getByRole('button', { name: 'Open the AI Scores guide' })).toHaveTextContent('?')
})
