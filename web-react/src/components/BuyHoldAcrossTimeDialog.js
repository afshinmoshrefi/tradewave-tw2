import React, {useEffect,useMemo,useRef,useState} from 'react'
import ReactDOM from 'react-dom'
import {Line} from 'react-chartjs-2'
import {appserverURL,themeColors} from './Common'
import {twFetch} from './twFetch'
import {domainForChart,visibleChart,visibleYBounds,moveRange,overviewPath,utcLabel} from './buyHoldRange'
import './styles/BuyHoldAcrossTimeDialog.css'
const PERIODS=[1,2,4,6,10,15,20]
const COLORS=['#2368b2','#da6b32','#198669','#824eaa','#b74f6c','#96751a','#14869a','#626f93','#b26b23']
const money=v=>Number.isFinite(v)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2}).format(v):'-'
const percent=v=>Number.isFinite(v)?v.toFixed(2)+'%':'-'
const period=y=>y+(y===1?' year':' years')
const purchaseRange=points=>{const dates=points.map(p=>p.purchase_date).sort();return dates[0]+' to '+dates[dates.length-1]}
export const isSupportedBuyHoldMarket=id=>/^[0-4]$/.test(String(id))
export const parseBuyHoldSymbols=text=>{
  const values=String(text).split(/[\s,]+/).map(s=>s.trim().toUpperCase()).filter(Boolean)
  if(!values.length)throw Error('Enter at least one company ticker.')
  if(values.length>3)throw Error('Compare up to three company tickers.')
  if(new Set(values).size!==values.length)throw Error('Enter each ticker only once.')
  if(values.some(s=>!/^[A-Z][A-Z0-9.^-]{0,14}$/.test(s)))throw Error('Use valid ticker symbols separated by commas.')
  return values
}
export const buyHoldChartData=(response,metric)=>{
  const series=Array.isArray(response?.series)?response.series:[]
  return {datasets:series.filter(s=>s.points?.length).map((s,i)=>({
    label:s.symbol+' · '+period(s.holding_years),
    data:s.points.map(p=>({x:Date.parse(p.purchase_date+'T00:00:00Z'),y:metric==='return_pct'?p.return_pct:p.ending_value,source:p})).sort((a,b)=>a.x-b.x),
    borderColor:COLORS[i%COLORS.length],backgroundColor:COLORS[i%COLORS.length],
    borderWidth:2,pointRadius:0,pointHoverRadius:5,tension:0,spanGaps:false
  }))}
}
const options=(metric,color,domain,yBounds)=>({
  responsive:true,maintainAspectRatio:false,animation:false,
  interaction:{mode:'nearest',intersect:false},
  plugins:{legend:{position:'bottom',labels:{boxWidth:15,color}},tooltip:{callbacks:{
    title:items=>items[0]?.raw?.source?.purchase_date||'',
    label:context=>{const p=context.raw.source;return [
      context.dataset.label,'Value of $1,000: '+money(p.ending_value),'Total gain: '+percent(p.return_pct),
      'Entry: '+p.entry_date,'Anniversary: '+p.anniversary_date,'Exit: '+p.exit_date]}
  }}},
  scales:{
    x:{type:'linear',min:domain[0],max:domain[1],title:{display:true,text:'Purchase date',color},ticks:{color,maxTicksLimit:8,maxRotation:0,callback:value=>new Date(value).toISOString().slice(0,4)}},
    y:{...(yBounds?{min:yBounds[0],max:yBounds[1]}:{}),title:{display:true,text:metric==='return_pct'?'Total gain (%)':'Value of $1,000',color},ticks:{color,callback:v=>metric==='return_pct'?v+'%':money(v)}}
  }
})
export const BuyHoldAcrossTimeDialog=({onClose,UITheme,resourceID,initialSymbol,token})=>{
  const [symbolsText,setSymbolsText]=useState(String(initialSymbol||'MSFT').toUpperCase())
  const [years,setYears]=useState([6])
  const [metric,setMetric]=useState('ending_value')
  const [query,setQuery]=useState({symbols:[String(initialSymbol||'MSFT').toUpperCase()],years:[6]})
  const [response,setResponse]=useState(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(false)
  const [range,setRange]=useState(null)
  const [brush,setBrush]=useState(null)
  const closeRef=useRef(null),previousFocus=useRef(document.activeElement)
  const mainChartRef=useRef(null),mainDragRef=useRef(null),navRef=useRef(null),navDragRef=useRef(null)
  const tc=themeColors(UITheme),supported=isSupportedBuyHoldMarket(resourceID)
  const chart=useMemo(()=>buyHoldChartData(response,metric),[response,metric])
  const domain=useMemo(()=>domainForChart(chart),[chart])
  const selectedRange=range||domain
  const displayed=useMemo(()=>visibleChart(chart,range),[chart,range])
  const yBounds=useMemo(()=>visibleYBounds(chart,range),[chart,range])
  const fullYBounds=useMemo(()=>visibleYBounds(chart,null),[chart])
  const overviewPaths=useMemo(()=>chart.datasets.map(d=>({label:d.label,color:d.borderColor,path:overviewPath(d.data,domain,fullYBounds)})),[chart,domain,fullYBounds])
  useEffect(()=>{setRange(null);setBrush(null)},[response])
  useEffect(()=>{
    const old=document.body.style.overflow;document.body.style.overflow='hidden';closeRef.current?.focus()
    const key=e=>{if(e.key==='Escape')onClose();if(e.key==='Tab'){const nodes=[...document.querySelectorAll('.tw-bhat-dialog button:not(:disabled),.tw-bhat-dialog input:not(:disabled)')];if(!nodes.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}}
    window.addEventListener('keydown',key)
    return()=>{document.body.style.overflow=old;window.removeEventListener('keydown',key);previousFocus.current?.focus?.()}
  },[onClose])
  useEffect(()=>{
    if(!supported||!token)return undefined
    const controller=new AbortController()
    setLoading(true);setError('');setResponse(null)
    const params=new URLSearchParams({resourceID:String(resourceID),symbols:query.symbols.join(','),holding_years:query.years.join(','),token})
    twFetch(appserverURL()+'/buy_hold_across_time?'+params,{signal:controller.signal})
      .then(async res=>{let body;try{body=await res.json()}catch(_){throw Error('The comparison service returned an invalid response.')}
        if(!res.ok)throw Error(body?.error||'The comparison could not be loaded. Please try again.')
        if(!Array.isArray(body?.series))throw Error('The comparison service returned an invalid response.')
        return body})
      .then(body=>{if(!controller.signal.aborted)setResponse(body)})
      .catch(err=>{if(!controller.signal.aborted)setError(err.message||'The comparison could not be loaded.')})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return()=>controller.abort()
  },[query,resourceID,token,supported])
  const submit=e=>{e.preventDefault();try{const symbols=parseBuyHoldSymbols(symbolsText);if(!years.length)throw Error('Choose at least one holding period.')
    setError('');setQuery({symbols,years:[...years].sort((a,b)=>a-b)})}catch(err){setError(err.message)}}
  const toggle=y=>setYears(current=>current.includes(y)?current.length>1?current.filter(v=>v!==y):current:current.length<3?[...current,y]:current)
  const mainX=event=>{
    const chartInstance=mainChartRef.current,canvas=chartInstance?.canvas
    if(!chartInstance?.scales?.x||!canvas)return null
    return Math.max(domain[0],Math.min(domain[1],chartInstance.scales.x.getValueForPixel(event.clientX-canvas.getBoundingClientRect().left)))
  }
  const startMain=event=>{
    if(event.button!==0||event.target.tagName!=='CANVAS'||!domain||event.nativeEvent.sourceCapabilities?.firesTouchEvents)return
    const x=mainX(event)
    if(x===null)return
    mainDragRef.current={startX:event.clientX,startDate:x}
  }
  const moveMain=event=>{
    const drag=mainDragRef.current
    if(!drag||!domain)return
    if(!(event.buttons&1)){mainDragRef.current=null;setBrush(null);return}
    if(Math.abs(event.clientX-drag.startX)<6)return
    const x=mainX(event)
    if(x===null)return
    const rect=event.currentTarget.getBoundingClientRect()
    setBrush([Math.max(0,Math.min(drag.startX,event.clientX)-rect.left),Math.min(rect.width,Math.abs(event.clientX-drag.startX))])
  }
  const endMain=event=>{
    const drag=mainDragRef.current
    mainDragRef.current=null;setBrush(null)
    if(!drag||Math.abs(event.clientX-drag.startX)<6||!domain)return
    const x=mainX(event)
    if(x===null)return
    const next=[Math.min(x,drag.startDate),Math.max(x,drag.startDate)]
    if(next[1]-next[0]>=24*60*60*1000)setRange(next)
  }
  const startNav=event=>{
    const mode=event.target.closest('[data-drag]')?.dataset.drag
    if(!mode||!domain||domain[0]===domain[1])return
    event.preventDefault()
    navDragRef.current={mode,clientX:event.clientX,range:[...selectedRange]}
    navRef.current?.setPointerCapture?.(event.pointerId)
  }
  const moveNav=event=>{
    const drag=navDragRef.current
    if(!drag||!domain)return
    const width=navRef.current?.getBoundingClientRect().width||1
    const delta=(event.clientX-drag.clientX)/width*(domain[1]-domain[0])
    setRange(moveRange(domain,drag.range,drag.mode,delta))
  }
  const endNav=event=>{
    navDragRef.current=null
    if(navRef.current?.hasPointerCapture?.(event.pointerId))navRef.current.releasePointerCapture(event.pointerId)
  }
  const keyNav=(event,mode)=>{
    if(!domain)return
    let direction=event.key==='ArrowLeft'?-1:event.key==='ArrowRight'?1:0
    if(!direction)return
    event.preventDefault()
    const step=Math.max(24*60*60*1000,(domain[1]-domain[0])*(event.shiftKey?0.1:0.02))
    setRange(moveRange(domain,selectedRange,mode,direction*step))
  }
  const selectionLeft=domain&&selectedRange?(selectedRange[0]-domain[0])/Math.max(domain[1]-domain[0],1)*100:0
  const selectionWidth=domain&&selectedRange?(selectedRange[1]-selectedRange[0])/Math.max(domain[1]-domain[0],1)*100:100
  const empty=response?.series?.filter(s=>!s.points?.length)||[]
  const filled=response?.series?.filter(s=>s.points?.length)||[]
  const allDates=filled.flatMap(s=>s.points.map(p=>p.purchase_date)).sort()
  const firstPurchase=allDates[0]||null
  return ReactDOM.createPortal(
    <div className="tw-bhat-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
      <section className="tw-bhat-dialog" role="dialog" aria-modal="true" aria-label="Buy & Hold Across Time"
        style={{'--bhat-bg':tc.panelBg,'--bhat-card':tc.statValueBg,'--bhat-text':tc.text,'--bhat-muted':tc.textSecondary,'--bhat-border':tc.border}}>
        <header className="tw-bhat-header"><div><p className="tw-bhat-eyebrow">Historical analysis</p><h2>Buy & Hold Across Time</h2><p>Compare completed calendar-year holds for purchases made on different trading days.</p></div>
          <button type="button" ref={closeRef} className="tw-bhat-close" aria-label="Close Buy & Hold Across Time" onClick={onClose}>×</button></header>
        <div className="tw-bhat-body">
          {!supported?<p role="status" className="tw-bhat-message">This historical comparison currently supports U.S. stock markets. Select a U.S. stock market to use it.</p>:!token?<p role="status" className="tw-bhat-message">Waiting for your session to load. Sign in to view this historical comparison.</p>:<>
            <form onSubmit={submit} className="tw-bhat-form">
              <label className="tw-bhat-symbols">Company tickers <span>Up to 3, separated by commas</span><input aria-label="Company tickers" value={symbolsText} onChange={e=>setSymbolsText(e.target.value)} placeholder="MSFT, AAPL, WMT"/></label>
              <fieldset><legend>Holding period <span>Choose up to 3</span></legend><div className="tw-bhat-years">{PERIODS.map(y=><label key={y} className={years.includes(y)?'is-selected':''}><input type="checkbox" checked={years.includes(y)} disabled={!years.includes(y)&&years.length>=3} onChange={()=>toggle(y)}/>{period(y)}</label>)}</div></fieldset>
              <button type="submit" className="tw-bhat-run">Compare history</button>
            </form>
            <div className="tw-bhat-results" aria-live="polite">
              {loading&&<p role="status" className="tw-bhat-message">Loading completed historical holds…</p>}
              {error&&<p role="alert" className="tw-bhat-message tw-bhat-error">{error}</p>}
              {response&&<>
                <div className="tw-bhat-result-head"><div><h3>Each purchase date, its completed outcome</h3><p>Each trading-day purchase date is a separate completed hold. Lines connect comparable historical outcomes; they do not show one investment growing over time.</p></div>
                  <div className="tw-bhat-metric" role="group" aria-label="Chart measure"><button type="button" aria-pressed={metric==='ending_value'} onClick={()=>setMetric('ending_value')}>Value of $1,000</button><button type="button" aria-pressed={metric==='return_pct'} onClick={()=>setMetric('return_pct')}>Total gain (%)</button></div></div>
                {chart.datasets.length?<div className="tw-bhat-zoom">
                  <div className="tw-bhat-view-head"><span aria-live="polite">Viewing {utcLabel(selectedRange[0])} to {utcLabel(selectedRange[1])}</span><button type="button" onClick={()=>setRange(null)} disabled={!range}>Reset view</button></div>
                  <div className="tw-bhat-chart" role="img" aria-label="Historical buy and hold comparison chart" onMouseDown={startMain} onMouseMove={moveMain} onMouseUp={endMain} onMouseLeave={()=>{mainDragRef.current=null;setBrush(null)}}>
                    {displayed.datasets.some(d=>d.data.length)?<Line ref={mainChartRef} data={displayed} options={options(metric,tc.textSecondary||tc.text,selectedRange,yBounds)}/>:<p role="status" className="tw-bhat-message">No purchase dates in this selected window. Move or widen the range below.</p>}
                    {brush&&<div className="tw-bhat-brush" style={{left:brush[0],width:brush[1]}}/>}
                  </div>
                  {domain[0]!==domain[1]&&<div className="tw-bhat-nav-wrap"><p>Drag the handles to resize, or drag the highlighted window to move through history. Drag across the main chart to zoom.</p>
                    <div ref={navRef} className="tw-bhat-nav" onPointerDown={startNav} onPointerMove={moveNav} onPointerUp={endNav} onPointerCancel={endNav}>
                      <svg viewBox="0 0 1000 80" preserveAspectRatio="none" aria-hidden="true">{overviewPaths.map(d=><path key={d.label} d={d.path} fill="none" stroke={d.color} strokeWidth="1.5" opacity=".7"/>)}</svg>
                      <div className="tw-bhat-nav-window" data-drag="pan" role="slider" tabIndex="0" aria-label="Move purchase-date window" aria-valuemin={domain[0]} aria-valuemax={domain[1]} aria-valuenow={selectedRange[0]} aria-valuetext={utcLabel(selectedRange[0])+' to '+utcLabel(selectedRange[1])} onKeyDown={e=>keyNav(e,'pan')} style={{left:selectionLeft+'%',width:selectionWidth+'%'}}/>
                      <button type="button" className="tw-bhat-nav-handle" data-drag="start" aria-label="Purchase range start" onKeyDown={e=>keyNav(e,'start')} style={{left:'clamp(16px, '+selectionLeft+'%, calc(100% - 16px))'}}/>
                      <button type="button" className="tw-bhat-nav-handle" data-drag="end" aria-label="Purchase range end" onKeyDown={e=>keyNav(e,'end')} style={{left:'clamp(16px, '+(selectionLeft+selectionWidth)+'%, calc(100% - 16px))'}}/>
                    </div>
                  </div>}
                </div>:<p role="status" className="tw-bhat-message">No completed holding periods are available for this selection.</p>}
                <div className="tw-bhat-coverage"><strong>Coverage</strong><span>First completed purchase shown {firstPurchase||'none'} · Data as of {response.as_of||'unavailable'}</span>{response.history_start&&<span>Available history begins {response.history_start}</span>}{filled.map(s=><span key={s.symbol+s.holding_years}>{s.symbol} · {period(s.holding_years)}: purchases {purchaseRange(s.points)}; data through {s.data_through||'unavailable'}; only completed exits shown ({s.points.length} purchase dates)</span>)}</div>
                {!!empty.length&&<div className="tw-bhat-empty"><strong>No completed history</strong>{empty.map(s=><span key={s.symbol+s.holding_years}>{s.symbol} · {period(s.holding_years)}</span>)}</div>}
                <p className="tw-bhat-footnote">{response.price_basis||'Adjusted closing prices'} · {response.date_convention||'Calendar-year anniversaries use the next available trading session.'} Historical outcomes only; no forecasts, taxes, or fees.</p>
              </>}
            </div>
          </>}
        </div>
      </section>
    </div>,document.body)
}
