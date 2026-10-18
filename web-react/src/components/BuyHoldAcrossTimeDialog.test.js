import React from 'react'
import {fireEvent, render, screen, waitFor} from '@testing-library/react'
import {BuyHoldAcrossTimeDialog,buyHoldChartData} from './BuyHoldAcrossTimeDialog'
import {twFetch} from './twFetch'
import {visibleChart,visibleYBounds,moveRange} from './buyHoldRange'
jest.mock('react-chartjs-2',()=>{
  const React=require('react')
  return {Line:React.forwardRef(({data,options},ref)=>{
    React.useImperativeHandle(ref,()=>({canvas:{getBoundingClientRect:()=>({left:0})},scales:{x:{getValueForPixel:pixel=>options.scales.x.min+(pixel/400)*(options.scales.x.max-options.scales.x.min)}}}))
    return <canvas data-testid="line-chart" data-count={data.datasets.reduce((n,d)=>n+d.data.length,0)} data-min={options.scales.x.min} data-max={options.scales.x.max} data-tooltip={options.plugins.tooltip.callbacks.label({raw:{source:data.datasets[0].data[0].source},dataset:data.datasets[0]}).join("|")} data-ymin={options.scales.y.min} data-ymax={options.scales.y.max} data-axis={options.scales.x.type} data-tick={options.scales.x.ticks.callback(Date.parse('2020-02-28T00:00:00Z'))} data-color={options.scales.x.ticks.color}/>
  })}
})
jest.mock('./twFetch',()=>({twFetch:jest.fn()}))
const point={purchase_date:'2020-02-28',entry_date:'2020-02-28',anniversary_date:'2024-02-28',exit_date:'2024-02-28',return_pct:41.25,ending_value:1412.5}
const secondPoint={...point,purchase_date:'2020-03-02',entry_date:'2020-03-02',anniversary_date:'2024-03-02',exit_date:'2024-03-04',return_pct:43.1,ending_value:1431}
const response={initial_value:1000,as_of:'2026-10-17',price_basis:'Adjusted close',date_convention:'Anniversary then next trading session',history_start:null,
  series:[{symbol:'MSFT',holding_years:4,data_through:'2026-10-17',points:[secondPoint,point]},{symbol:'WMT',holding_years:6,data_through:'2026-10-17',points:[]}]}
beforeAll(()=>{window.PointerEvent=window.MouseEvent})
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
  expect(Number(screen.getByTestId('line-chart').getAttribute('data-ymin'))).toBeGreaterThan(0)
  expect(screen.getByTestId('line-chart').getAttribute('data-tooltip')).toContain('Entry: 2020-02-28|Anniversary: 2024-02-28|Exit: 2024-02-28')
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

test('overview handles resize and pan without refetching or changing selected controls',async()=>{
  twFetch.mockResolvedValue({ok:true,json:async()=>response})
  render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={0} initialSymbol="MSFT" token="test-token"/>)
  await screen.findByTestId('line-chart')
  const nav=screen.getByRole('slider',{name:'Move purchase-date window'}).parentElement
  nav.getBoundingClientRect=()=>({width:400,left:0})
  const start=screen.getByRole('button',{name:'Purchase range start'})
  fireEvent.pointerDown(start,{pointerId:1,clientX:0})
  fireEvent.pointerMove(nav,{pointerId:1,clientX:180})
  fireEvent.pointerUp(nav,{pointerId:1,clientX:180})
  expect(screen.getByText(/Viewing 2020-02-29 to 2020-03-02/)).toBeInTheDocument()
  const before=screen.getByRole('slider',{name:'Move purchase-date window'}).getAttribute('aria-valuetext')
  fireEvent.pointerDown(screen.getByRole('slider',{name:'Move purchase-date window'}),{pointerId:2,clientX:180})
  fireEvent.pointerMove(nav,{pointerId:2,clientX:100})
  fireEvent.pointerUp(nav,{pointerId:2,clientX:100})
  const after=screen.getByRole('slider',{name:'Move purchase-date window'}).getAttribute('aria-valuetext')
  expect(after).not.toBe(before)
  expect(twFetch).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('checkbox',{name:'6 years'})).toBeChecked()
  fireEvent.click(screen.getByRole('button',{name:'Reset view'}))
  expect(screen.getByText(/Viewing 2020-02-28 to 2020-03-02/)).toBeInTheDocument()
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-count','2')
})
test('main chart mouse drag zooms and visible Y bounds follow original points',async()=>{
  twFetch.mockResolvedValue({ok:true,json:async()=>response})
  render(<BuyHoldAcrossTimeDialog onClose={()=>{}} UITheme="light" resourceID={0} initialSymbol="MSFT" token="test-token"/>)
  const canvas=await screen.findByTestId('line-chart')
  fireEvent.mouseDown(canvas,{button:0,clientX:200})
  fireEvent.mouseMove(canvas,{buttons:1,clientX:400})
  fireEvent.mouseUp(canvas,{button:0,clientX:400})
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-count','1')
  expect(Number(screen.getByTestId('line-chart').getAttribute('data-ymin'))).toBeGreaterThan(1400)
  expect(screen.getByText(/Viewing 2020-02-29 to 2020-03-02/)).toBeInTheDocument()
  expect(twFetch).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button',{name:'Total gain (%)'}))
  expect(screen.getByTestId('line-chart')).toHaveAttribute('data-count','1')
  expect(screen.getByRole('checkbox',{name:'6 years'})).toBeChecked()
})

test('range helpers clamp handles and pan width, and keep unmodified engine point references',()=>{
  const chart=buyHoldChartData(response,'ending_value')
  const [early,late]=chart.datasets[0].data
  const domain=[early.x,late.x]
  const selected=[early.x+24*60*60*1000,late.x]
  expect(moveRange(domain,selected,'start',10*24*60*60*1000)[0]).toBe(late.x-24*60*60*1000)
  const panned=moveRange(domain,selected,'pan',-10*24*60*60*1000)
  expect(panned[1]-panned[0]).toBe(selected[1]-selected[0])
  expect(panned[0]).toBe(domain[0])
  const visible=visibleChart(chart,[late.x,late.x])
  expect(visible.datasets[0].data).toHaveLength(1)
  expect(visible.datasets[0].data[0]).toBe(late)
  expect(visible.datasets[0].pointRadius).toBe(4)
  expect(visible.datasets[0].data[0].source).toBe(secondPoint)
  const bounds=visibleYBounds(chart,[late.x,late.x])
  expect(bounds[0]).toBeGreaterThan(0)
  expect(bounds[0]).toBeLessThan(secondPoint.ending_value)
  expect(bounds[1]).toBeGreaterThan(secondPoint.ending_value)
  expect(visibleYBounds(chart,[early.x+1,late.x-1])).toBeNull()
})
