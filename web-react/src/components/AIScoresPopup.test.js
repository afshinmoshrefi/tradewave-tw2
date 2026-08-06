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

test('guide starts with the AI Scores window and gives a plain-English decision checklist', () => {
  const view = renderGuide(jest.fn())

  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })
  expect(guide.textContent.trim()).toMatch(/^Start in the AI Scores window/)
  expect(guide).toHaveTextContent(/Select an opportunity, then open AI Scores after Wave Stats/i)
  expect(guide).toHaveTextContent(/shows all available time lengths.*historical sample size/i)
  expect(guide).toHaveTextContent(/four AI columns are off by default/i)
  expect(guide).toHaveTextContent(/sort by an AI value without showing that column/i)

  expect(guide).toHaveTextContent(/AI Scores in plain English/i)
  expect(guide).toHaveTextContent(/History shows what happened.*years you selected/i)
  expect(guide).toHaveTextContent(/separate second opinion using the latest completed stock and market data/i)
  expect(guide).toHaveTextContent(/neither one guarantees what happens next/i)
  expect(guide).toHaveTextContent(/Win%: estimated chance of a profitable result/i)
  expect(guide).toHaveTextContent(/PredR: estimated return when the time window ends/i)
  expect(guide).toHaveTextContent(/PMFE: estimated best move.*not a target/i)
  expect(guide).toHaveTextContent(/AIS: 0-100 rank.*not a win chance/i)

  expect(guide).toHaveTextContent(/Start with history.*sample size.*n=10/i)
  expect(guide).toHaveTextContent(/Compare AI Win%.*history and AI agree.*evidence points in the same direction.*still not proof/i)
  expect(guide).toHaveTextContent(/large difference.*inspect the chart, losing years, and risk.*not an automatic buy or sell signal.*Do not average the two percentages together/i)
  expect(guide).toHaveTextContent(/Check move size.*PredR estimates the ending result.*PMFE estimates the best favorable move/i)
  expect(guide).toHaveTextContent(/Compare time lengths.*timing may matter.*does not choose an entry or exit/i)
  expect(guide).toHaveTextContent(/Use AIS last.*not Win%, a confidence grade, or a final answer/i)

  view.unmount()
})

test('guide keeps history and calibrated AI Win% separate and explains model limits', () => {
  const view = renderGuide(jest.fn())
  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })

  expect(guide).toHaveTextContent(/AI Win% does not change the historical record/i)
  expect(guide).toHaveTextContent(/history says 9 of 10 years were profitable.*stays 9 of 10.*n=10/i)
  expect(guide).toHaveTextContent(/older AI estimates.*checks what happened next/i)
  expect(guide).toHaveTextContent(/7 of 10 similar cases were profitable.*AI Win% is about 70%/i)
  expect(screen.getByText('calibration')).toBeInTheDocument()
  expect(guide).toHaveTextContent(/separate estimate.*does not add years.*or rewrite its win rate/i)

  expect(guide).toHaveTextContent(/62 pieces of information/i)
  expect(guide).toHaveTextContent(/uses only information that was available at that time/i)
  expect(guide).toHaveTextContent(/keeps future information out of the test/i)
  expect(guide).toHaveTextContent(/AIS of 80 ranks above about 80%/i)
  expect(guide).toHaveTextContent(/does not mean an 80% chance of profit/i)

  view.unmount()
})

test('guide explains calendar-day comparisons, availability, and what to do before acting', () => {
  const view = renderGuide(jest.fn())
  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })

  expect(guide).toHaveTextContent(/Every time length uses calendar days.*start date is day 1.*weekends and holidays count/i)
  expect(guide).toHaveTextContent(/10-30 days: AI scores the full pattern/i)
  expect(guide).toHaveTextContent(/31-60 days: compare 30 days with the full pattern/i)
  expect(guide).toHaveTextContent(/61-90 days: compare 30 and 60 days with the full pattern/i)
  expect(guide).toHaveTextContent(/More than 90 days: compare 30, 60, and 90 days; the table shows 90 days/i)
  expect(guide).toHaveTextContent(/AI Scores window shows every applicable reading together/i)
  expect(guide).toHaveTextContent(/AI estimate and history check answer different questions/i)
  expect(guide).toHaveTextContent(/Long means the setup benefits if price rises.*Short means it benefits if price falls/i)

  expect(guide).toHaveTextContent(/US stocks and ETFs/i)
  expect(guide).toHaveTextContent(/stock and market data from the latest completed market day/i)
  expect(guide).toHaveTextContent(/does not update during the trading day \(intraday\)/i)
  expect(guide).toHaveTextContent(/spinner means AI is still calculating.*dash means no score was assigned.*Select that row and open the AI Scores window.*Zero is a real AI value/i)
  expect(guide).toHaveTextContent(/Review the historical sample, expected return, possible loss, and your own risk limits before acting/i)

  expect(guide).not.toHaveTextContent(/ensemble|horizon tier|walk-forward|feature vector|pattern profile|recurrence|direction-adjusted|today's conditions/i)

  view.unmount()
})
