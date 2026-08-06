import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import AIScoresPopup from './AIScoresPopup'
import { UserContext } from './UserContext'

const renderGuide = onClose => render(
  <UserContext.Provider value={{ UITheme: 'light', seasonalAppDivH: 800 }}>
    <AIScoresPopup onClose={onClose} iconRect={null} />
  </UserContext.Provider>
)

test('AI Scores guide traps focus, makes long content keyboard-scrollable, and closes with Escape', () => {
  jest.useFakeTimers()
  const trigger = document.createElement('button')
  trigger.textContent = 'Open AI guide'
  document.body.appendChild(trigger)
  trigger.focus()
  const onClose = jest.fn()
  const view = renderGuide(onClose)

  const dialog = screen.getByRole('dialog', { name: 'AI Scores' })
  const close = screen.getByRole('button', { name: 'Close AI Scores guide' })
  const body = screen.getByRole('region', { name: 'AI Scores guide content' })
  expect(dialog).toHaveFocus()
  expect(body).toHaveAttribute('tabindex', '0')

  fireEvent.keyDown(window, { key: 'Tab' })
  expect(close).toHaveFocus()
  fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
  expect(body).toHaveFocus()
  fireEvent.keyDown(window, { key: 'Tab' })
  expect(close).toHaveFocus()

  fireEvent.keyDown(window, { key: 'Escape' })
  jest.advanceTimersByTime(200)
  expect(onClose).toHaveBeenCalledTimes(1)
  view.unmount()
  expect(trigger).toHaveFocus()

  trigger.remove()
  jest.useRealTimers()
})

test('guide explains current-score priority, shorter comparisons, screen evidence, and model scope', () => {
  const view = renderGuide(jest.fn())

  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })
  expect(guide.textContent.trim()).toMatch(/^First: What the outline means/)
  expect(screen.getByText(/outlined AI value means that pattern has more than one AI duration/i)).toBeInTheDocument()
  expect(screen.getByText(/outline does not mean the score is better or worse.*not a warning/i)).toBeInTheDocument()
  expect(guide).toHaveTextContent(/For a 1-9-day pattern.*changes only the AI window to 10 calendar days/i)
  expect(guide).toHaveTextContent(/historical pattern and its historical stats stay at the real length/i)
  expect(screen.getByText(/Quick summary: Why this helps/i)).toBeInTheDocument()
  expect(screen.getByText(/history tells you what usually happened.*AI Scores add a second check/i)).toBeInTheDocument()
  expect(screen.getByText(/The two belong side by side/i)).toBeInTheDocument()
  expect(screen.getByText('calibration')).toBeInTheDocument()
  expect(screen.getByText(/calibrated AI Win% would be about 70%/i)).toBeInTheDocument()
  expect(screen.getByText(/a 0-100 relative rank/i)).toBeInTheDocument()
  expect(screen.getByText(/Patterns from 10 through 90 calendar days keep their current full-window reading/i)).toBeInTheDocument()
  expect(guide).toHaveTextContent(/For a 10-90-day pattern, the current duration stays highlighted/i)
  expect(screen.getByText(/patterns over 30 days add 30 days/i)).toBeInTheDocument()
  expect(screen.getByText(/neutral violet outline and dotted underline/)).toBeInTheDocument()
  expect(screen.getByText(/screen result is evidence beside the AI reading, not a reason to erase it/i)).toBeInTheDocument()
  expect(screen.getByText(/validated for near-term horizons through 90 calendar days/)).toBeInTheDocument()
  expect(screen.getByText(/9 profitable years out of 10 \(n=10\)/)).toBeInTheDocument()
  expect(screen.getByText(/US stocks and ETFs/)).toBeInTheDocument()

  view.unmount()
})
