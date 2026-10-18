import React, {useEffect,useMemo,useRef,useState} from 'react'
import ReactDOM from 'react-dom'
import {Line} from 'react-chartjs-2'
import {appserverURL,themeColors} from './Common'
import {twFetch} from './twFetch'
import './styles/BuyHoldAcrossTimeDialog.css'
const PERIODS=[1,2,4,6,10,15,20]
const COLORS=['#2368b2','#da6b32','#198669','#824eaa','#b74f6c','#96751a','#14869a','#626f93','#b26b23']
const money=v=>Number.isFinite(v)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2}).format(v):'-'
const percent=v=>Number.isFinite(v)?v.toFixed(2)+'%':'-'
const period=y=>y+(y===1?' year':' years')
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
  const labels=[...new Set(series.flatMap(s=>(s.points||[]).map(p=>p.purchase_date)))].sort()
  return {labels,datasets:series.filter(s=>s.points?.length).map((s,i)=>({
    label:s.symbol+' · '+period(s.holding_years),
    data:s.points.map(p=>({x:p.purchase_date,y:metric==='return_pct'?p.return_pct:p.ending_value,source:p})),
    borderColor:COLORS[i%COLORS.length],backgroundColor:COLORS[i%COLORS.length],
    borderWidth:2,pointRadius:0,pointHoverRadius:5,tension:0,spanGaps:false
  }))}
}
const options=metric=>({
  responsive:true,maintainAspectRatio:false,normalized:true,animation:false,
  interaction:{mode:'nearest',intersect:false},
  plugins:{legend:{position:'bottom',labels:{boxWidth:15}},tooltip:{callbacks:{
    title:items=>items[0]?.raw?.source?.purchase_date||'',
    label:context=>{const p=context.raw.source;return [
      context.dataset.label,'Value of $1,000: '+money(p.ending_value),'Total gain: '+percent(p.return_pct),
      'Entry: '+p.entry_date+'; anniversary: '+p.anniversary_date+'; exit: '+p.exit_date]}
  }}},
  scales:{
    x:{type:'category',title:{display:true,text:'Purchase date'},ticks:{maxTicksLimit:8,maxRotation:0,callback:(v,i,t)=>t[i]?.label?.slice(0,7)||''}},
    y:{title:{display:true,text:metric==='return_pct'?'Total gain (%)':'Value of $1,000'},ticks:{callback:v=>metric==='return_pct'?v+'%':money(v)}}
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
  const closeRef=useRef(null),previousFocus=useRef(document.activeElement)
  const tc=themeColors(UITheme),supported=isSupportedBuyHoldMarket(resourceID)
  const chart=useMemo(()=>buyHoldChartData(response,metric),[response,metric])
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
  const empty=response?.series?.filter(s=>!s.points?.length)||[]
  const filled=response?.series?.filter(s=>s.points?.length)||[]
  return ReactDOM.createPortal(
    <div className="tw-bhat-overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}>
      <section className="tw-bhat-dialog" role="dialog" aria-modal="true" aria-label="Buy & Hold Across Time"
        style={{'--bhat-bg':tc.panelBg,'--bhat-card':tc.statValueBg,'--bhat-text':tc.text,'--bhat-muted':tc.textSecondary,'--bhat-border':tc.border}}>
        <header className="tw-bhat-header"><div><p className="tw-bhat-eyebrow">Historical analysis</p><h2>Buy & Hold Across Time</h2><p>Compare completed calendar-year holds for purchases made on different trading days.</p></div>
          <button type="button" ref={closeRef} className="tw-bhat-close" aria-label="Close Buy & Hold Across Time" onClick={onClose}>×</button></header>
        <div className="tw-bhat-body">
          {!supported?<p role="status" className="tw-bhat-message">This historical comparison currently supports U.S. stock markets. Select a U.S. stock market to use it.</p>:<>
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
                {chart.datasets.length?<div className="tw-bhat-chart" role="img" aria-label="Historical buy and hold comparison chart"><Line data={chart} options={options(metric)}/></div>:<p role="status" className="tw-bhat-message">No completed holding periods are available for this selection.</p>}
                <div className="tw-bhat-coverage"><strong>Coverage</strong><span>History starts {response.history_start||'unavailable'} · Data as of {response.as_of||'unavailable'}</span>{filled.map(s=><span key={s.symbol+s.holding_years}>{s.symbol} · {period(s.holding_years)}: data through {s.data_through||'unavailable'}; only completed exits shown ({s.points.length} purchase dates)</span>)}</div>
                {!!empty.length&&<div className="tw-bhat-empty"><strong>No completed history</strong>{empty.map(s=><span key={s.symbol+s.holding_years}>{s.symbol} · {period(s.holding_years)}</span>)}</div>}
                <p className="tw-bhat-footnote">{response.price_basis||'Adjusted closing prices'} · {response.date_convention||'Calendar-year anniversaries use the next available trading session.'} Historical outcomes only; no forecasts, taxes, or fees.</p>
              </>}
            </div>
          </>}
        </div>
      </section>
    </div>,document.body)
}
