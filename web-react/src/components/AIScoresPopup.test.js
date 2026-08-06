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

test('guide starts with four plain-English questions a new user needs answered', () => {
  const view = renderGuide(jest.fn())

  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })
  expect(guide.textContent.trim()).toMatch(/^Why use AI Scores\?/)
  expect(guide).toHaveTextContent(/History tells you what this pattern did in past years/i)
  expect(guide).toHaveTextContent(/latest completed stock and market conditions.*today's setup/i)
  expect(guide).toHaveTextContent(/current conditions support or conflict with the past results/i)
  expect(guide).toHaveTextContent(/does not replace history or guarantee a profit/i)
  expect(guide).toHaveTextContent(/older AI estimates.*what really happened.*adjusts AI Win Chance.*real results/i)

  expect(guide).toHaveTextContent(/How to read the numbers/i)
  expect(guide).toHaveTextContent(/AI Win Chance: estimated chance.*checkpoint ends with a profit.*Long or Short direction/i)
  expect(guide).toHaveTextContent(/Estimated End Return: estimated gain or loss/i)
  expect(guide).toHaveTextContent(/Estimated Best Move: largest helpful move.*not a target/i)
  expect(guide).toHaveTextContent(/AI Return Rank:.*Higher than 75%.*similar AI estimates.*not a win chance or grade/i)

  expect(guide).toHaveTextContent(/Why are there several time views/i)
  expect(guide).toHaveTextContent(/30, 60, or 90 calendar days/i)
  expect(guide).toHaveTextContent(/checkpoints for different holding lengths.*not extra votes/i)
  expect(guide).toHaveTextContent(/What should I do next/i)
  expect(guide).toHaveTextContent(/Start with the historical record.*compare AI Win Chance and Estimated End Return/i)
  expect(guide).toHaveTextContent(/views disagree.*losing years.*Price Chart.*risk/i)
  expect(guide).toHaveTextContent(/Do not average the historical percentage with AI Win Chance/i)

  view.unmount()
})

test('guide keeps history and calibrated AI Win Chance separate and explains model limits', () => {
  const view = renderGuide(jest.fn())
  const guide = screen.getByRole('region', { name: 'AI Scores guide content' })

  expect(guide).toHaveTextContent(/AI Win Chance does not change the historical record/i)
  expect(guide).toHaveTextContent(/history says 9 of 10 years were profitable.*stays 9 of 10 years/i)
  expect(guide).toHaveTextContent(/older AI estimates.*checks what happened next/i)
  expect(guide).toHaveTextContent(/7 of 10 similar cases were profitable.*AI Win Chance is about 70%/i)
  expect(guide).toHaveTextContent(/reality check is called calibration/i)
  expect(guide).toHaveTextContent(/separate estimate.*does not add years.*or rewrite the past results/i)

  expect(guide).toHaveTextContent(/62 pieces of information/i)
  expect(guide).toHaveTextContent(/uses only information that was available at that time/i)
  expect(guide).toHaveTextContent(/keeps future information out of the test/i)
  expect(guide).toHaveTextContent(/Higher than 80%.*ranks above about 80%/i)
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
  expect(guide).toHaveTextContent(/Long means a price rise helps the setup.*Short means a price drop helps the setup/i)

  expect(guide).toHaveTextContent(/US stocks and ETFs/i)
  expect(guide).toHaveTextContent(/stock and market data from the latest completed market day/i)
  expect(guide).toHaveTextContent(/does not update during the trading day \(intraday\)/i)
  expect(guide).toHaveTextContent(/spinner means AI is still calculating.*dash means no score was assigned.*Select that row and open the AI Scores window.*Zero is a real AI value/i)
  expect(guide).toHaveTextContent(/Review the historical sample, expected return, possible loss, and your own risk limits before acting/i)

  expect(guide).not.toHaveTextContent(/ensemble|horizon tier|walk-forward|feature vector|pattern profile|recurrence|direction-adjusted|today's conditions/i)

  view.unmount()
})
