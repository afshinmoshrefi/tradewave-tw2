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
      onOpenPortfolio={options.onOpenPortfolio}
      onExportSnapshot={options.onExportSnapshot}
      tooltipsEnabled={options.tooltipsEnabled}
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
    selectedRecurrence: recurrence(8, 10, { status: 'below_threshold', required_positive_years: 9 }),
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
      selectedRecurrence: recurrence(8, 10, { status: 'below_threshold', required_positive_years: 9 }),
    },
  ],
}

test('presents a long selected pattern as compact stats-style decision tables', () => {
  const onOpenGuide = jest.fn()
  renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: 'MSFT' },
    bundle: longBundle,
  }, { onOpenGuide })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/AI Scores for MSFT.*Data through Aug 4, 2026/i)
  expect(panel).toHaveTextContent(/Short.*price drop helps this setup.*Starts Aug 5, 2026.*120-day historical pattern.*Opportunity Table uses the 90-day AI score/i)
  expect(panel).toHaveTextContent(/Quick read.*Opportunity Table AI score \(90 days\).*73% AI win chance.*\+4.0% estimated end return.*8 of 10 historical years profitable.*Shortened 90-day history missed your 9-of-10 filter.*selected 120-day pattern passed/i)
  expect(panel).toHaveTextContent(/History reports past years.*latest completed stock and market conditions/i)
  expect(panel).toHaveTextContent(/Each checkpoint ends on a different date.*numbers can differ/i)

  const views = within(panel).getAllByRole('table')
  expect(views).toHaveLength(3)
  const thirty = within(panel).getByRole('table', { name: '30-day AI scores' })
  expect(within(thirty).getByRole('row', { name: /Historical Record.*6 of 10 years profitable/i })).toBeInTheDocument()
  expect(within(thirty).getByRole('row', { name: /AI Win Chance.*52%/i })).toBeInTheDocument()
  expect(within(thirty).getByRole('row', { name: /Estimated End Return.*1.0%/i })).toBeInTheDocument()
  expect(within(thirty).getByRole('row', { name: /Estimated Best Move.*Not a target.*3.0%/i })).toBeInTheDocument()
  expect(within(thirty).getByRole('row', { name: /AI Return Rank.*Higher than 51.0%.*similar AI estimates/i })).toBeInTheDocument()

  const mainView = within(panel).getByRole('region', { name: '90-day AI checkpoint (shown in Opportunity Table)' })
  expect(mainView).toHaveClass('ai-score-panel__view--table')
  expect(mainView).toHaveTextContent(/90-Day Checkpoint.*Shown in Opportunity Table/i)
  expect(mainView).toHaveTextContent(/8 of 10 years profitable/i)
  expect(mainView).toHaveTextContent(/Below filter: needs 9 of 10/i)
  expect(mainView).toHaveTextContent(/AI Win Chance73%/i)
  expect(mainView).toHaveTextContent(/Estimated End Return4.0%/i)
  expect(mainView).toHaveTextContent(/Estimated Best MoveNot a target8.0%/i)
  expect(mainView).toHaveTextContent(/AI Return RankHigher than 78.0%of similar AI estimates/i)

  expect(panel).not.toHaveTextContent(/Why AI\?|How to use it|Calendar days|AI Score78|PredR|PMFE|\/ 100/i)

  fireEvent.click(screen.getByRole('button', { name: 'How to read AI Scores' }))
  expect(onOpenGuide).toHaveBeenCalledTimes(1)
})

test('labels a changed duration as the current Wave Viewer reading', () => {
  renderPanel({
    eligible: true,
    enabled: true,
    selectionOrigin: 'wave_viewer',
    selected: { symbol: 'MSFT', date: '2026-08-05', daysOut: 120, direction: 'Short' },
    bundle: longBundle,
  })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/120-day historical pattern.*Wave Viewer uses the 90-day AI reading/i)
  expect(panel).toHaveTextContent(/Quick read.*Wave Viewer AI reading \(90 days\)/i)
  expect(within(panel).getByRole('region', { name: /90-day AI checkpoint \(used for Wave Viewer\)/i }))
    .toHaveTextContent(/90-Day Checkpoint.*Used for Wave Viewer/i)
  expect(panel).not.toHaveTextContent(/Shown in Opportunity Table|Opportunity Table uses/i)
})

test('keeps a 63-year Buy & Hold selection visible with the honest after-entry explanation', () => {
  const unavailable = {
    calendarDays: 90,
    status: 'unavailable',
    reason: 'after_entry',
    metrics: { ml_score: null, win_prob: null, pred_return: null, pred_mfe: null },
  }
  renderPanel({
    eligible: true,
    enabled: true,
    selectionOrigin: 'wave_viewer',
    selected: {
      symbol: 'MRK',
      date: '2026-01-01',
      daysOut: 366,
      direction: 'Long',
      years: '63',
      yearCount: '63',
      mode: 'consecutive',
      cycle: 'cons',
      isBuyAndHold: true,
    },
    bundle: {
      basis: 'duration_comparison',
      fullPatternCalendarDays: 366,
      entryDate: '2026-01-01',
      direction: 'Long',
      displayCalendarDays: 90,
      display: unavailable,
      horizons: [
        { ...unavailable, calendarDays: 30 },
        { ...unavailable, calendarDays: 60 },
        unavailable,
      ],
    },
  })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/Buy & Hold.*Long.*Starts Jan 1, 2026.*366-day historical pattern.*63-year history.*Wave Viewer uses the 90-day AI reading/i)
  expect(panel).toHaveTextContent(/This pattern has already started.*new AI reading is not available/i)
  expect(panel).toHaveTextContent(/Pattern already started/i)
  expect(panel).not.toHaveTextContent(/Temporarily unavailable/i)
  expect(panel).not.toHaveClass('ai-score-panel--empty')
  expect(panel).not.toHaveTextContent(/Loading AI Scores/i)
})

test('offers the same Portfolio Manager and Wave Viewer snapshot actions as the other lower panels', () => {
  const onOpenPortfolio = jest.fn()
  const onExportSnapshot = jest.fn()
  renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: 'MSFT' },
    bundle: longBundle,
  }, { onOpenPortfolio, onExportSnapshot })

  fireEvent.click(screen.getByRole('button', { name: 'Open Portfolio Manager' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save Wave Viewer snapshot' }))

  expect(onOpenPortfolio).toHaveBeenCalledTimes(1)
  expect(onExportSnapshot).toHaveBeenCalledTimes(1)
})

test('keeps Portfolio Manager available but hides snapshot until a pattern is selected', () => {
  const onOpenPortfolio = jest.fn()
  renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: '' },
    bundle: null,
  }, { onOpenPortfolio, onExportSnapshot: jest.fn() })

  fireEvent.click(screen.getByRole('button', { name: 'Open Portfolio Manager' }))
  expect(onOpenPortfolio).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button', { name: 'Save Wave Viewer snapshot' })).not.toBeInTheDocument()
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
  expect(panel).toHaveTextContent(/Long.*price rise helps this setup.*6-day historical pattern.*Opportunity Table uses the 10-day AI score/i)
  expect(panel).toHaveTextContent(/History stays 6 days.*AI starts at its 10-day minimum/i)
  expect(panel).toHaveTextContent(/History reports past years.*latest completed stock and market conditions/i)
  const table = within(panel).getByRole('table', { name: '10-day AI scores' })
  expect(within(table).getByRole('row', { name: /AI Win Chance.*69%/i })).toBeInTheDocument()
  expect(within(panel).getByRole('region', { name: '10-day AI checkpoint (shown in Opportunity Table)' })).toHaveClass('ai-score-panel__view--table')
})

test('quick read says when no historical years are complete without creating an impossible filter message', () => {
  const zeroHistoryView = {
    calendarDays: 30,
    status: 'available',
    reason: '',
    metrics: { ml_score: 50, win_prob: 0.55, pred_return: 1.2, pred_mfe: 2.4 },
    selectedRecurrence: recurrence(0, 0),
  }
  renderPanel({
    selected: { symbol: 'AAPL' },
    bundle: {
      fullPatternCalendarDays: 30,
      displayCalendarDays: 30,
      direction: 'Long',
      display: zeroHistoryView,
      horizons: [zeroHistoryView],
    },
  })

  const panel = screen.getByRole('region', { name: 'AI Scores' })
  expect(panel).toHaveTextContent(/Quick read.*No completed historical years/i)
  expect(panel).not.toHaveTextContent(/0 of 0 historical years|below your 6-of-0/i)
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

test('matches the other lower windows when the viewer is empty, including stale placeholder state', () => {
  const view = renderPanel({
    eligible: true,
    enabled: true,
    selected: { symbol: '', date: '', daysOut: 30 },
    loading: true,
    bundle: null,
  })
  const emptyLabel = screen.getByText('AI Scores')
  expect(emptyLabel).toHaveClass('ai-score-panel__empty-label')
  expect(emptyLabel).toHaveStyle({ fontSize: '7vw' })
  expect(screen.getByRole('region', { name: 'AI Scores' })).toHaveClass('ai-score-panel--empty')
  expect(screen.queryByRole('button', { name: 'How to read AI Scores' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Select a pattern|Choose an opportunity|Loading AI Scores/i)).not.toBeInTheDocument()

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light' }}>
      <AIScorePanel viewModel={{ eligible: true, enabled: true, selected: { symbol: 'AAPL' }, loading: true }} />
    </UserContext.Provider>
  )
  expect(screen.getByRole('status')).toHaveTextContent(/Loading AI Scores for AAPL/i)
  expect(screen.getByRole('status')).toHaveTextContent(/Historical results remain available/i)

  view.rerender(
    <UserContext.Provider value={{ UITheme: 'light' }}>
      <AIScorePanel viewModel={{ eligible: false, enabled: true, selected: { symbol: 'EURUSD' } }} />
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
  expect(screen.getByText(/7 of 10 years profitable/i)).toBeInTheDocument()
  expect(screen.getByText(/Below filter: needs 9 of 10/i)).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'AI Scores' })).toHaveAttribute('data-theme', 'dark')
  expect(screen.getByRole('region', { name: 'AI Scores' })).toHaveStyle({ '--ai-negative': '#f87171' })
})
