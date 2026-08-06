import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import AIScorePanel from './AIScorePanel'
import { UserContext } from './UserContext'
import { resetAIScoreViewedForTests } from './aiScoreActivation'

const renderPanel = (viewModel, options = {}) => render(
  <UserContext.Provider value={{
    UITheme: options.theme || 'light',
    loggedinUser: options.loggedinUser,
  }}>
    <AIScorePanel
      viewModel={viewModel}
      onOpenGuide={options.onOpenGuide}
      active={options.active}
    />
  </UserContext.Provider>
)

const recurrence = (positiveYears, sampleSize, extra = {}) => ({
  status: 'qualified',
  positive_years: positiveYears,
  sample_size: sampleSize,
  required_positive_years: 6,
  ...extra,
})

const longBundle = {
  basis: 'duration_comparison',
  fullPatternCalendarDays: 120,
  entryDate: '2026-08-05',
  direction: 'Short',
  displayCalendarDays: 90,
  dataAsOf: '2026-08-04',
  display: {
    calendarDays: 90,
    status: 'available',
    reason: '',
    metrics: { ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 },
    selectedRecurrence: recurrence(8, 10),
  },
  horizons: [
    {
      calendarDays: 30,
      status: 'available',
      reason: '',
      metrics: { ml_score: 51, win_prob: 0.52, pred_return: 1, pred_mfe: 3 },
      selectedRecurrence: recurrence(6, 10),
    },
    {
      calendarDays: 60,
      status: 'available',
      reason: '',
      metrics: { ml_score: 63, win_prob: 0.64, pred_return: 2, pred_mfe: 5 },
      selectedRecurrence: recurrence(7, 10),
    },
    {
      calendarDays: 90,
      status: 'available',
      reason: '',
      metrics: { ml_score: 78, win_prob: 0.73, pred_return: 4, pred_mfe: 8 },
      selectedRecurrence: recurrence(8, 10),
    },
  ],
}

test('presents a long selected pattern as a clear decision-support summary', () => {
  const onOpenGuide = jest.fn()
  renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: 'MSFT' },
    bundle: longBundle,
  }, { onOpenGuide })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/A clear second opinion for the pattern you selected/i)
  expect(panel).toHaveTextContent(/MSFT/)
  expect(panel).toHaveTextContent(/Short.*benefits if price falls/i)
  expect(panel).toHaveTextContent(/Starts Aug 5, 2026/i)
  expect(panel).toHaveTextContent(/120 calendar days/i)
  expect(within(panel).getByLabelText('90 calendar days')).toHaveTextContent('90')

  expect(panel).toHaveTextContent(/History shows what happened in the years you selected/i)
  expect(panel).toHaveTextContent(/separate second opinion/i)
  expect(panel).toHaveTextContent(/do not replace the historical record or guarantee the next result/i)
  expect(panel).toHaveTextContent(/AI Win% is calibrated with older results/i)

  const mainReading = within(panel).getByRole('region', { name: '90-calendar-day view' })
  expect(mainReading).toHaveTextContent(/AI Win%73%Estimated chance/i)
  expect(mainReading).toHaveTextContent(/Predicted Ending Return4.0%Estimated result/i)
  expect(mainReading).toHaveTextContent(/Estimated Best Move8.0%.*not a target/i)
  expect(mainReading).toHaveTextContent(/AI Score78.0.*not a win chance/i)

  expect(panel).toHaveTextContent(/recalculates separate 30-, 60-, and 90-calendar-day versions/i)
  const table = within(panel).getByRole('table')
  expect(within(table).getByRole('row', { name: /30 days.*6 of 10 profitable.*n=10.*52%.*1.0%.*3.0%.*51.0/i })).toBeInTheDocument()
  expect(within(table).getByRole('row', { name: /60 days.*7 of 10 profitable.*n=10.*64%.*2.0%.*5.0%.*63.0/i })).toBeInTheDocument()
  expect(within(table).getByRole('row', { name: /90 days.*Main reading.*8 of 10 profitable.*n=10.*73%.*4.0%.*8.0%.*78.0/i })).toBeInTheDocument()
  expect(panel).toHaveTextContent(/All lengths use calendar days.*start date is day 1/i)
  expect(panel).toHaveTextContent(/Do not average historical win rate with AI Win%/i)
  expect(panel).toHaveTextContent(/data through Aug 4, 2026.*does not update during the market day/i)

  fireEvent.click(screen.getByRole('button', { name: 'How AI Scores work' }))
  expect(onOpenGuide).toHaveBeenCalledTimes(1)
})

test('explains the separate 10-day AI minimum without changing a short historical pattern', () => {
  const minimumBundle = {
    basis: 'minimum_horizon',
    fullPatternCalendarDays: 6,
    minimumModelCalendarDays: 10,
    entryDate: '2026-08-05',
    direction: 'Long',
    displayCalendarDays: 10,
    display: {
      calendarDays: 10,
      status: 'available',
      reason: '',
      metrics: { ml_score: 73, win_prob: 0.69, pred_return: 2.5, pred_mfe: 4.9 },
    },
    horizons: [{
      calendarDays: 10,
      status: 'available',
      reason: '',
      metrics: { ml_score: 73, win_prob: 0.69, pred_return: 2.5, pred_mfe: 4.9 },
    }],
  }
  renderPanel({ selected: { symbol: 'AAPL' }, bundle: minimumBundle })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/6 calendar days/i)
  expect(panel).toHaveTextContent(/History keeps this 6-calendar-day pattern/i)
  expect(panel).toHaveTextContent(/AI uses 10 calendar days because 10 days is the model's shortest supported time length/i)
  expect(panel).toHaveTextContent(/10-day historical check below applies only to the AI calculation/i)
  expect(panel).toHaveTextContent(/10-calendar-day view/i)
  expect(within(panel).getByLabelText('10 calendar days')).toHaveTextContent('10')
  expect(panel).toHaveTextContent(/Long.*benefits if price rises/i)
})

test('records a real score only while the panel is active and the user is signed in', () => {
  resetAIScoreViewedForTests()
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }))

  const viewModel = {
    eligible: true,
    enabled: true,
    selected: { symbol: 'MSFT', daysOut: 120 },
    bundle: longBundle,
  }
  const view = renderPanel(viewModel, { active: false, loggedinUser: '42' })
  expect(global.fetch).not.toHaveBeenCalled()

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light', loggedinUser: '0' }}>
      <AIScorePanel viewModel={viewModel} active />
    </UserContext.Provider>
  )
  expect(global.fetch).not.toHaveBeenCalled()

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light', loggedinUser: '42' }}>
      <AIScorePanel viewModel={viewModel} active />
    </UserContext.Provider>
  )
  expect(global.fetch).toHaveBeenCalledTimes(1)
  expect(global.fetch).toHaveBeenCalledWith('/api/activation/ai-score-viewed', expect.objectContaining({
    method: 'POST',
    body: JSON.stringify({ detail: { symbol: 'MSFT', horizon: 120 } }),
  }))

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light', loggedinUser: '42' }}>
      <AIScorePanel viewModel={{ ...viewModel, selected: { symbol: 'AAPL' } }} active />
    </UserContext.Provider>
  )
  expect(global.fetch).toHaveBeenCalledTimes(1)
  delete global.fetch
})

test('does not record an active panel when every AI reading is unavailable', () => {
  resetAIScoreViewedForTests()
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }))
  const unavailableMetrics = { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null }
  renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: 'MSFT' },
    bundle: {
      ...longBundle,
      display: { ...longBundle.display, status: 'unavailable', metrics: unavailableMetrics },
      horizons: longBundle.horizons.map(horizon => ({
        ...horizon,
        status: 'unavailable',
        metrics: unavailableMetrics,
      })),
    },
  }, { active: true, loggedinUser: '42' })

  expect(global.fetch).not.toHaveBeenCalled()
  delete global.fetch
})

test('shows clear empty, loading, and unsupported-market states', () => {
  const view = renderPanel({ eligible: true, enabled: true, selected: null, bundle: null })
  expect(screen.getByText('Select a pattern to see its AI Scores')).toBeInTheDocument()
  expect(screen.getByText(/Choose an opportunity from the table/i)).toBeInTheDocument()

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light' }}>
      <AIScorePanel viewModel={{ eligible: true, enabled: true, selected: { symbol: 'AAPL' }, loading: true }} />
    </UserContext.Provider>
  )
  expect(screen.getByRole('status')).toHaveTextContent(/Checking this pattern/i)

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light' }}>
      <AIScorePanel viewModel={{ eligible: false, enabled: true }} />
    </UserContext.Provider>
  )
  expect(screen.getByText('AI Scores are not available for this market')).toBeInTheDocument()
  expect(screen.getByText(/currently cover U.S. stocks and ETFs/i)).toBeInTheDocument()
})

test('distinguishes a service failure from a failed history filter', () => {
  const unavailableBundle = {
    ...longBundle,
    display: {
      calendarDays: 90,
      status: 'unavailable',
      reason: 'service_unavailable',
      metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null },
    },
    horizons: [{
      calendarDays: 90,
      status: 'unavailable',
      reason: 'service_unavailable',
      metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null },
    }],
  }
  const view = renderPanel({ selected: { symbol: 'MSFT' }, bundle: unavailableBundle })
  expect(screen.getByText('AI Scores are temporarily unavailable')).toBeInTheDocument()
  expect(screen.getByText(/historical results are not affected/i)).toBeInTheDocument()

  const historyBundle = {
    ...unavailableBundle,
    display: {
      ...unavailableBundle.display,
      status: 'below_threshold',
      reason: 'selected_recurrence_below_threshold',
      selectedRecurrence: recurrence(7, 10, { status: 'below_threshold', required_positive_years: 9 }),
    },
    horizons: [{
      ...unavailableBundle.horizons[0],
      status: 'below_threshold',
      reason: 'selected_recurrence_below_threshold',
      selectedRecurrence: recurrence(7, 10, { status: 'below_threshold', required_positive_years: 9 }),
    }],
  }
  view.rerender(
    <UserContext.Provider value={{ UITheme: 'dark' }}>
      <AIScorePanel viewModel={{ selected: { symbol: 'MSFT' }, bundle: historyBundle }} />
    </UserContext.Provider>
  )

  expect(screen.getByText('This time length did not pass your history filter')).toBeInTheDocument()
  expect(screen.getByText(/7 of 10 profitable/i)).toBeInTheDocument()
  expect(screen.getByText(/Needs 9 profitable years for your filter/i)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'AI Scores' })).toHaveAttribute('data-theme', 'dark')
})
