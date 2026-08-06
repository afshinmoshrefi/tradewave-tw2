import React from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import Settings from './Settings'
import { UserContext } from './UserContext'

const renderSettings = ({ levels = ['4'], visibility = {}, overrides = {} } = {}) => {
  const props = {
    SetShowSettings: jest.fn(),
    SetShowSecuritiesGroupSettings: jest.fn(),
    trimYear: '',
    SetTrimYear: jest.fn(),
    showSR2: false,
    SetShowSR2: jest.fn(),
    SetOpportunities: jest.fn(),
    barChartExcursionStyle: 'filled',
    SetBarChartExcursionStyle: jest.fn(),
    columnVisibility: visibility,
    SetColumnVisibility: jest.fn(),
    ...overrides,
  }
  const context = {
    numReportsAllowed: 0,
    browserH: 844,
    browserW: 390,
    tableTitleTextSize: '12px',
    rdd: { isMobile: true, isTablet: false },
    resourceObj: {},
    globalTextSize: '12px',
    infoTextSize: '12px',
    loggedinUser: '1',
    token: '',
    wpUserLevels: levels,
    checkboxZoom: 1,
    UITheme: 'light',
  }

  render(
    <UserContext.Provider value={context}>
      <Settings {...props} />
    </UserContext.Provider>
  )
  return props
}

test('mobile Settings offers all four AI table columns in one compact group', () => {
  renderSettings({
    visibility: { ml_score: false, win_prob: false, pred_return: false, pred_mfe: false },
  })

  const group = screen.getByRole('group', { name: 'AI Scores in Opportunity Table' })
  const checkboxes = within(group).getAllByRole('checkbox')

  expect(checkboxes).toHaveLength(4)
  expect(within(group).getByRole('checkbox', { name: /AIS 0-100 return rank/i })).not.toBeChecked()
  expect(within(group).getByRole('checkbox', { name: /Win% Estimated chance of profit/i })).not.toBeChecked()
  expect(within(group).getByRole('checkbox', { name: /PredR Estimated ending return/i })).not.toBeChecked()
  expect(within(group).getByRole('checkbox', { name: /PMFE Estimated best move/i })).not.toBeChecked()
  expect(group).toHaveTextContent(/Full details stay in the AI Scores window/i)
})

test('enabling one mobile AI column preserves every other saved preference', () => {
  const visibility = {
    date: false,
    price: true,
    ml_score: false,
    win_prob: false,
    pred_return: true,
    pred_mfe: false,
  }
  const view = renderSettings({ visibility })

  fireEvent.click(screen.getByRole('checkbox', { name: /Win% Estimated chance of profit/i }))

  expect(view.SetColumnVisibility).toHaveBeenCalledWith({
    ...visibility,
    win_prob: true,
  })
  expect(visibility.win_prob).toBe(false)
})

test('the AI column group clearly explains plan access when unavailable', () => {
  renderSettings({ levels: ['2'] })

  const group = screen.getByRole('group', { name: 'AI Scores in Opportunity Table' })
  expect(within(group).getAllByRole('checkbox')).toHaveLength(4)
  within(group).getAllByRole('checkbox').forEach(checkbox => expect(checkbox).toBeDisabled())
  expect(group).toHaveTextContent(/available on the Analyst plan and above/i)
})
