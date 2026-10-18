const DAY=24*60*60*1000
export const domainForChart=chart=>{
  const dates=chart.datasets.flatMap(d=>d.data.map(p=>p.x))
  return dates.length?dates.reduce((bounds,date)=>[Math.min(bounds[0],date),Math.max(bounds[1],date)],[Infinity,-Infinity]):null
}
export const visibleChart=(chart,range)=>{
  if(!range)return chart
  return {...chart,datasets:chart.datasets.map(d=>{const data=d.data.filter(p=>p.x>=range[0]&&p.x<=range[1]);return {...d,data,pointRadius:data.length===1?4:d.pointRadius}})}
}
export const visibleYBounds=(chart,range)=>{
  const values=visibleChart(chart,range).datasets.flatMap(d=>d.data.map(p=>p.y)).filter(Number.isFinite)
  if(!values.length)return null
  const [low,high]=values.reduce((bounds,value)=>[Math.min(bounds[0],value),Math.max(bounds[1],value)],[Infinity,-Infinity])
  const padding=Math.max((high-low)*0.06,Math.abs(high||low)*0.01,0.01)
  return [low-padding,high+padding]
}
export const moveRange=(domain,range,mode,delta)=>{
  const [min,max]=domain,[start,end]=range
  const span=Math.max(DAY,Math.min(end-start,max-min))
  if(mode==='start')return [Math.max(min,Math.min(start+delta,end-DAY)),end]
  if(mode==='end')return [start,Math.min(max,Math.max(end+delta,start+DAY))]
  const nextStart=Math.max(min,Math.min(start+delta,max-span))
  return [nextStart,nextStart+span]
}
export const overviewPath=(points,domain,bounds)=>{
  if(!points.length||!domain||!bounds)return ''
  const [low,high]=bounds,[start,end]=domain
  const x=v=>((v-start)/Math.max(end-start,1))*1000
  const y=v=>76-((v-low)/Math.max(high-low,1))*72
  return points.map((p,i)=>(i?'L':'M')+x(p.x).toFixed(2)+' '+y(p.y).toFixed(2)).join(' ')
}
export const utcLabel=value=>new Date(value).toISOString().slice(0,10)
