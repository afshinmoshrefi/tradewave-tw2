import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import WatchlistSettings from './WatchlistSettings'
import { UserContext } from './UserContext'
import { twFetch } from './twFetch'

jest.mock('./twFetch', () => ({ twFetch: jest.fn() }))
jest.mock('./TextBox', () => ({ name, text, tbBlur, tbEnter }) =>
  <input aria-label={name} value={text} onChange={tbBlur} onKeyDown={tbEnter} />)
jest.mock('./SelectBox', () => ({ name, value, optionList, sbChanged }) =>
  <select aria-label={name} value={value} onChange={sbChanged}>
    {optionList.map(o => <option key={o.value} value={o.value}>{o.label || o.value}</option>)}
  </select>)
jest.mock('./CheckBox', () => ({ name, checked, cbChanged }) =>
  <input type="checkbox" aria-label={name} checked={checked} onChange={cbChanged} />)

beforeEach(() => jest.clearAllMocks())

test.each(['invalid_symbol', 'invalid_watchlist'])('server %s after a stale successful preview keeps the list and shows rejection', async (rejection) => {
  twFetch.mockImplementation(url => Promise.resolve({ json: () => Promise.resolve(
    url.includes('/get_user_watchlist_items/') ? { watchlist_items: ['AAPL'] } :
    url.includes('/NameFromTicker/') ? { name: 'Stale preview name' } :
    { watchlist_items: rejection, message: 'BFA not found in this market' }
  ) }))
  const setDefaultItems = jest.fn()
  render(<UserContext.Provider value={{ browserH: 900, browserW: 1400, rdd: { isMobile: false }, globalTextSize: '14px', token: 'test' }}>
    <WatchlistSettings UITheme="dark" watchlists={[{ name: 'Test', resourceId: '4', resourceName: 'US', isDefault: true }]}
      securityTypeList={[]} defaultWatchlistName="Test" numWatchlistItemsAllowed={100}
      SetDefaultWatchlistItems={setDefaultItems} SetShowWatchlistSettings={() => {}} />
  </UserContext.Provider>)
  expect(await screen.findByText('AAPL')).toBeInTheDocument()
  fireEvent.change(screen.getByRole('textbox', { name: 'wl_new_symbol' }), { target: { value: 'BFA' } })
  fireEvent.click(screen.getByRole('button', { name: /Add Symbol/ }))
  expect(await screen.findByText('BFA not found in this market')).toBeInTheDocument()
  expect(screen.getByText('AAPL')).toBeInTheDocument()
  expect(screen.getByText('Symbols in Test: 1 / 100')).toBeInTheDocument()
  expect(screen.queryByText(/Stale preview name.*added/)).toBeNull()
  expect(screen.queryByText('BFA')).toBeNull()
  expect(screen.getByRole('textbox', { name: 'wl_new_symbol' })).toHaveValue('BFA')
  expect(setDefaultItems).not.toHaveBeenCalled()
  expect(twFetch).toHaveBeenCalledTimes(3)
})
