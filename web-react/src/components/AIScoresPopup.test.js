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

  expect(screen.getByText(/Quick summary: Why this helps/i)).toBeInTheDocument()
  expect(screen.getByText(/history tells you what usually happened.*AI Scores add a second check/i)).toBeInTheDocument()
  expect(screen.getByText(/The two belong side by side/i)).toBeInTheDocument()
  expect(screen.getByText('calibration')).toBeInTheDocument()
  expect(screen.getByText(/calibrated AI Win% would be about 70%/i)).toBeInTheDocument()
  expect(screen.getByText(/a 0-100 relative rank/i)).toBeInTheDocument()
  expect(screen.getByText(/table keeps the current full-window reading for patterns through 90 calendar days/i)).toBeInTheDocument()
  expect(screen.getByText(/patterns over 30 days add 30 days/i)).toBeInTheDocument()
  expect(screen.getByText(/neutral violet outline and dotted underline/)).toBeInTheDocument()
  expect(screen.getByText(/screen result is evidence beside the AI reading, not a reason to erase it/i)).toBeInTheDocument()
  expect(screen.getByText(/validated for near-term horizons through 90 calendar days/)).toBeInTheDocument()
  expect(screen.getByText(/9 profitable years out of 10 \(n=10\)/)).toBeInTheDocument()
  expect(screen.getByText(/US stocks and ETFs/)).toBeInTheDocument()

  view.unmount()
})
