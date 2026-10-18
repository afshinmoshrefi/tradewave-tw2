import React from 'react'
import {fireEvent, render, screen, waitFor} from '@testing-library/react'
import {BuyHoldAcrossTimeDialog,buyHoldChartData} from './BuyHoldAcrossTimeDialog'
import {twFetch} from './twFetch'
jest.mock('react-chartjs-2',()=>({Line:({data,options})=><div data-testid="line-chart" data-min={options.scales.x.min} data-max={options.scales.x.max} data-axis={options.scales.x.type} data-tick={options.scales.x.ticks.callback(Date.parse('2020-02-28T00:00:00Z'))} data-color={options.scales.x.ticks.color}>{data.datasets.map(d=>d.label).join('; ')}</div>}))
jest.mock('./twFetch',()=>({twFetch:jest.fn()}))
const point={purchase_date:'2020-02-28',entry_date:'2020-02-28',anniversary_date:'2024-02-28',exit_date:'2024-02-28',return_pct:41.25,ending_value:1412.5}
const secondPoint={...point,purchase_date:'2020-03-02',entry_date:'2020-03-02',anniversary_date:'2024-03-02',exit_date:'2024-03-04',return_pct:43.1,ending_value:1431}
const response={initial_value:1000,as_of:'2026-10-17',price_basis:'Adjusted close',date_convention:'Anniversary then next trading session',history_start:null,
  series:[{symbol:'MSFT',holding_years:4,data_through:'2026-10-17',points:[secondPoint,point]},{symbol:'WMT',holding_years:6,data_through:'2026-10-17',points:[]}]}
afterEach(()=>jest.clearAllMocks())
test('retains all engine values and dates in the chart source for both views',()=>{
  const value=buyHoldChartData(response,'ending_value')
  const gain=buyHoldChartData(response,'return_pct')
  expect(value.datasets[0].data).toHaveLength(2)
  expect(value.datasets[0].data[0]).toEqual({x:Date.parse('2020-02-28T00:00:00Z'),y:1412.5,source:point})
  expect(value.datasets[0].data[1].x-value.datasets[0].data[0].x).toBe(3*24*60*60*1000)
  expect(gain.datasets[0].data[0]).toEqual({x:Date.parse('2020-02-28T00:00:00Z'),y:41.25,source:point})
  expect(value.datasets).toHaveLength(1)
})
test('loads selected company and holding periods, then shows coverage and empty series',async()=>{
  twFetch.mockResolvedValue({ok:true,json:async()=>response})
  render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={0} initialSymbol="MSFT" token="test-token"/>)
  expect(screen.getByRole('checkbox',{name:'6 years'})).toBeChecked()
  await waitFor(()=>expect(screen.getByText(/data through 2026-10-17/)).toBeInTheDocument())
  expect(screen.getByText(/WMT · 6 years/)).toBeInTheDocument()
  expect(screen.getByText(/First completed purchase shown 2020-02-28/)).toBeInTheDocument()
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-min', String(Date.parse('2020-02-28T00:00:00Z')))
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-max', String(Date.parse('2020-03-02T00:00:00Z')))
  expect(screen.getByText(/purchases 2020-02-28 to 2020-03-02/)).toBeInTheDocument()
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-axis','linear')
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-tick','2020')
  expect(screen.getByTestId('line-chart').getAttribute('data-color')).toBeTruthy()
  expect(screen.getByText(/Each trading-day purchase date is a separate completed hold/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Company tickers'),{target:{value:'MSFT,AAPL,WMT'}})
  fireEvent.click(screen.getByRole('checkbox',{name:'4 years'}))
  fireEvent.click(screen.getByRole('button',{name:'Compare history'}))
  await waitFor(()=>expect(twFetch).toHaveBeenCalledTimes(2))
  expect(twFetch.mock.calls[1][0]).toContain('symbols=MSFT%2CAAPL%2CWMT')
  expect(twFetch.mock.calls[1][0]).toContain('holding_years=4%2C6')
  fireEvent.click(screen.getByRole('button',{name:'Total gain (%)'}))
  expect(screen.getByRole('button',{name:'Total gain (%)'})).toHaveAttribute('aria-pressed','true')
})
test('unsupported market does not request and service errors are visible',async()=>{
  const first=render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={10} initialSymbol="MSFT" token="test-token"/>)
  expect(screen.getByText(/currently supports U.S. stock markets/)).toBeInTheDocument()
  expect(twFetch).not.toHaveBeenCalled()
  first.unmount()
  twFetch.mockResolvedValue({ok:false,json:async()=>({error:'Historical access is unavailable for this market.'})})
  render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={0} initialSymbol="MSFT" token="test-token"/>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Historical access is unavailable for this market.')
})

test('missing token explains why no request runs',()=>{
  render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={0} initialSymbol="MSFT" token=""/>)
  expect(screen.getByText(/Waiting for your session to load/)).toBeInTheDocument()
  expect(twFetch).not.toHaveBeenCalled()
})
