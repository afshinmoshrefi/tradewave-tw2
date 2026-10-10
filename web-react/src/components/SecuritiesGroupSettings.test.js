import React, { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SecuritiesGroupSettings from './SecuritiesGroupSettings'
import { UserContext } from './UserContext'

jest.mock('./CheckBox', () => ({ name, checked, cbChanged }) => <input type="checkbox" aria-label={name} checked={checked} onChange={cbChanged} />)
const lists = [
  { name: 'Midcaps', resource_name: 'US', symbols: ['AAPL'], enabled: true },
  { name: 'New list', resource_name: 'US', symbols: ['AAPL'], enabled: true },
  { name: 'Disabled', resource_name: 'US', symbols: ['AAPL'], enabled: false }
]
const originalFetch = global.fetch
beforeEach(() => { global.fetch = jest.fn((url, options) => Promise.resolve({ json: () => Promise.resolve({ securities_prefs: JSON.parse(options.body) }) })) })
afterEach(() => { global.fetch = originalFetch })
function View({ prefs = { hidden_groups: [], enabled_published: [] }, admin = false }) {
  const [value, setValue] = useState(prefs)
  return <UserContext.Provider value={{browserH:900,browserW:1400,rdd:{isMobile:false},token:'test',loggedinUser:'regular'}}>
    <SecuritiesGroupSettings UITheme="dark" securitiesPrefs={value} SetSecuritiesPrefs={setValue} publishedLists={lists} isAdmin={admin} securityTypeList2={[]} resourceObj={{}} SetShowSecuritiesGroupSettings={() => {}} />
  </UserContext.Provider>
}
test('legacy empty opt-in defaults to every enabled published list checked', () => {
  render(<View />)
  fireEvent.click(screen.getByText('Published Lists'))
  expect(screen.getByRole('checkbox', {name:'pl_Midcaps'})).toBeChecked()
  expect(screen.getByRole('checkbox', {name:'pl_New list'})).toBeChecked()
  expect(screen.queryByRole('checkbox', {name:'pl_Disabled'})).toBeNull()
})
test('explicit hide persists without hiding a newly published list and can be reversed', async () => {
  render(<View prefs={{hidden_groups:['FOREX ALL'],enabled_published:[],hidden_published:['Midcaps']}} />)
  fireEvent.click(screen.getByText('Published Lists'))
  expect(screen.getByRole('checkbox', {name:'pl_Midcaps'})).not.toBeChecked()
  expect(screen.getByRole('checkbox', {name:'pl_New list'})).toBeChecked()
  fireEvent.click(screen.getByRole('checkbox', {name:'pl_Midcaps'}))
  await waitFor(() => expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({hidden_groups:['FOREX ALL'],enabled_published:[],hidden_published:[]}))
  fireEvent.click(screen.getByRole('checkbox', {name:'pl_New list'}))
  await waitFor(() => expect(JSON.parse(global.fetch.mock.calls[1][1].body).hidden_published).toEqual(['New list']))
})
test('admin management retains disabled lists for re-enabling', () => {
  render(<View admin />)
  fireEvent.click(screen.getByText('Admin'))
  expect(screen.getByRole('checkbox', {name:'en_Disabled'})).not.toBeChecked()
})
