import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

// Real CAT (Caterpillar) price data, normalized 0-100, for 10 PE+2 (midterm) years
// Each array has 50 evenly-spaced data points spanning Jan-Dec
const CAT_PE2 = {
    2022: [49.99,67.49,77.32,59.97,49.21,44.59,46.88,26.79,33.92,54.53,62.1,69.41,70.5,62.25,64.72,81.89,58.95,63.16,47.6,52.1,59.61,71.57,62.25,35.06,28.97,12.29,13.17,20.71,22.82,25.59,28.65,42.61,42.23,29.76,22.37,26.98,11.55,6.46,19.36,20.72,26.69,43.53,65.03,78.48,86.89,92.39,90.89,85.06,84.74,93.15],
    2018: [74.23,90.76,94.4,95.49,85.66,70.74,77.32,78.73,63.48,69.42,71.15,57.59,58.44,50.68,63.48,70.18,55.03,57.96,73.04,74.55,74.8,68.85,75.6,62.06,40.56,40.05,48.86,44.77,44.54,54.96,52.42,39.08,48.15,51.74,49.22,55.82,70.97,71.71,80.73,54.81,50.56,0.0,16.15,40.94,22.95,20.74,32.18,20.17,25.96,13.91],
    2014: [12.04,11.42,22.56,0.0,29.9,33.61,40.1,43.07,39.17,40.87,36.7,41.26,50.99,57.71,64.17,70.04,76.3,70.74,83.49,61.76,67.01,72.45,89.47,84.77,88.5,92.85,92.07,93.63,77.87,61.09,65.74,80.29,89.32,91.98,91.55,77.79,67.97,59.64,47.95,31.29,41.63,58.93,66.69,68.07,66.42,86.55,57.2,42.42,20.75,30.88],
    2010: [16.17,28.32,22.26,11.12,6.07,6.03,14.74,13.55,17.08,17.54,20.7,24.74,26.47,30.04,38.24,37.61,44.76,28.76,36.29,18.1,25.58,16.1,21.55,33.95,31.43,19.23,30.48,32.58,44.11,46.47,48.73,40.78,37.11,31.85,43.47,48.2,58.33,65.61,65.01,64.88,63.12,64.31,66.77,71.59,68.15,73.2,83.96,88.81,96.63,99.87],
    2006: [0.0,14.63,18.04,18.88,48.98,47.17,58.88,62.03,70.38,58.04,72.73,78.44,62.24,75.88,81.29,86.23,77.27,95.12,85.98,64.8,71.71,50.28,37.61,52.89,63.54,73.18,67.41,52.14,57.17,53.16,61.15,43.43,48.04,35.14,50.7,38.86,36.96,36.11,35.52,47.28,50.49,21.31,15.33,13.63,19.36,25.05,21.82,25.94,22.21,16.64],
    2002: [68.61,68.26,54.61,58.77,63.32,52.33,64.29,72.58,86.66,98.23,100.0,89.74,88.93,92.13,93.06,77.02,73.39,71.5,72.85,77.83,75.7,65.48,60.51,60.12,55.3,51.29,44.89,36.21,36.02,41.8,34.67,40.34,40.88,39.99,33.55,32.9,15.97,19.55,14.0,4.67,25.07,27.96,26.96,33.47,40.18,54.61,61.86,47.47,41.42,48.75],
    1998: [42.81,25.38,24.77,26.3,48.93,59.94,66.67,60.24,60.24,67.28,84.4,79.82,72.48,70.03,80.12,84.71,73.09,74.01,81.35,95.41,79.51,73.7,59.02,69.72,60.55,67.89,60.24,63.3,43.73,40.37,35.47,39.76,34.86,18.35,27.83,25.08,11.32,40.98,16.82,36.7,36.39,27.52,33.03,40.06,41.9,48.93,57.19,41.29,20.49,10.09],
    1994: [0.0,3.59,9.96,34.66,47.01,50.6,52.99,67.73,62.15,80.08,88.85,93.63,68.53,97.61,76.89,45.02,62.15,73.71,54.58,67.33,57.77,57.77,50.2,61.75,37.45,35.86,57.37,60.96,56.57,65.34,45.42,53.79,56.98,83.67,72.12,56.98,68.13,52.99,60.16,69.72,71.32,82.47,82.47,80.08,73.71,44.23,60.16,46.61,49.01,56.18],
    1990: [69.66,68.8,63.24,57.26,54.7,56.41,57.69,62.39,75.64,81.62,74.36,76.49,77.77,75.64,74.36,73.08,82.05,82.91,86.32,94.02,100.0,97.01,95.72,92.73,85.47,48.29,51.28,50.86,45.73,35.47,23.08,27.77,23.08,21.37,17.09,14.53,14.1,12.39,16.67,4.27,0.86,16.24,5.98,6.84,15.81,15.39,6.41,18.8,26.5,28.63],
    1986: [25.67,19.59,30.4,36.49,47.97,55.41,70.27,64.87,75.68,75.68,80.4,79.73,85.8,66.21,69.59,87.16,100.0,81.08,83.11,77.02,97.3,87.16,79.06,82.43,69.59,71.62,77.02,40.54,45.95,42.56,52.03,51.35,56.76,70.94,70.94,53.37,41.89,10.81,2.7,6.08,5.41,0.68,16.89,12.84,8.79,14.19,13.52,17.57,16.21,20.27],
}
const CAT_AVG = [35.92,39.82,41.76,39.89,48.17,47.68,54.98,55.2,58.44,64.33,69.14,69.09,66.22,67.82,70.59,71.29,70.3,69.9,70.46,68.29,70.9,66.04,63.1,63.55,56.14,51.25,54.28,49.57,47.45,46.68,44.74,45.92,47.74,47.48,47.88,43.05,39.72,37.63,35.89,34.04,37.15,34.3,39.53,44.6,44.42,47.53,48.52,43.41,40.39,41.84]

const TrendChartPopup = ({ onClose, iconRect }) => {
    const { UITheme, seasonalAppDivH } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [closing, setClosing] = useState(false)
    const dark = UITheme === 'dark'

    const handleClose = () => {
        setClosing(true)
        setTimeout(() => onClose(), 200)
    }

    const handleOverlayClick = (e) => {
        if (e.target === e.currentTarget) handleClose()
    }

    const bgColor = dark ? '#1e1e2e' : '#ffffff'
    const textColor = tc.text
    const cardBg = dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'
    const cardBorder = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'
    const accentGreen = '#22c55e'
    const accentBlue = '#3b82f6'
    const accentAmber = '#f59e0b'
    const accentPurple = '#a78bfa'
    const mutedText = dark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.45)'
    const gridLine = dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'

    const popupMaxH = seasonalAppDivH ? seasonalAppDivH * 0.9 : window.innerHeight * 0.85
    const popupStyle = { backgroundColor: bgColor, color: textColor, maxHeight: `${popupMaxH}px` }
    if (!iconRect) {
        popupStyle.position = 'fixed'
        popupStyle.left = '50%'
        popupStyle.top = '50%'
        popupStyle.transform = 'translate(-50%, -50%)'
    } else {
        const appEl = document.querySelector('.seasonal-barchart-container') || document.getElementById('right-content')
        const appTop = appEl ? appEl.getBoundingClientRect().top : 0
        const appH = seasonalAppDivH || window.innerHeight
        const centerY = appTop + appH / 2
        popupStyle.position = 'fixed'
        popupStyle.right = `${window.innerWidth - iconRect.left + 8}px`
        popupStyle.top = `${centerY}px`
        popupStyle.transform = 'translateY(-50%)'
        popupStyle.left = 'auto'
    }

    const cardStyle = {
        background: cardBg,
        border: `1px solid ${cardBorder}`,
        borderRadius: '8px',
        padding: '12px',
        marginBottom: '10px',
    }

    // SVG chart dimensions
    const svgW = 420, svgH = 150, padL = 30, padR = 10, padT = 18, padB = 20
    const chartW = svgW - padL - padR
    const chartH = svgH - padT - padB

    // Convert normalized 0-100 data to SVG path
    const toPath = (data) => {
        return 'M ' + data.map((v, i) => {
            const x = padL + (i / (data.length - 1)) * chartW
            const y = padT + chartH - (v / 100) * chartH // invert: 100=top, 0=bottom
            return `${x.toFixed(1)},${y.toFixed(1)}`
        }).join(' L ')
    }

    // Grid lines
    const grids = () => {
        const lines = []
        for (let i = 1; i <= 4; i++) {
            const y = padT + (chartH / 5) * i
            lines.push(<line key={i} x1={padL} y1={y} x2={svgW - padR} y2={y} stroke={gridLine} strokeWidth="1" />)
        }
        return lines
    }

    // Month labels along x-axis
    const monthLabels = ['Jan', 'Mar', 'May', 'Jul', 'Sep', 'Nov']
    const monthPositions = [0, 0.167, 0.333, 0.5, 0.667, 0.833]

    const yearColors = {
        2022: '#ef4444', 2018: '#f97316', 2014: '#eab308', 2010: '#22c55e', 2006: '#14b8a6',
        2002: '#06b6d4', 1998: '#3b82f6', 1994: '#8b5cf6', 1990: '#d946ef', 1986: '#f43f5e'
    }

    const yearKeys = Object.keys(CAT_PE2).map(Number).sort((a, b) => b - a)

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>The Trend Chart</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            If history repeated itself, where would the price go next?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The Trend Chart answers this by combining years of historical price data into one line
                            that shows the most probable path prices have followed during a calendar window.
                        </div>
                    </div>

                    {/* The Problem: messy individual years */}
                    <div className="ts-section-title">The Challenge: Every Year Is Different</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        Here is real data from <strong>Caterpillar (CAT)</strong> across 10 midterm election
                        years (PE+2). Each colored line shows how CAT's price moved during one year,
                        normalized to the same scale. Notice how chaotic it looks with all 10 years on one chart:
                    </p>

                    <div style={{ ...cardStyle, padding: '10px 8px 6px', textAlign: 'center' }}>
                        <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`} style={{ maxWidth: '420px' }}>
                            {grids()}
                            {/* Individual year lines */}
                            {yearKeys.map(yr => (
                                <path key={yr} d={toPath(CAT_PE2[yr])}
                                    fill="none" stroke={yearColors[yr]} strokeWidth="1.3" opacity="0.55" />
                            ))}
                            {/* Month labels */}
                            {monthLabels.map((m, i) => (
                                <text key={m} x={padL + monthPositions[i] * chartW} y={svgH - 2} fontSize="9" fill={mutedText} textAnchor="middle">{m}</text>
                            ))}
                            {/* Year legend - two rows */}
                            {yearKeys.map((yr, i) => {
                                const row = Math.floor(i / 5)
                                const col = i % 5
                                return (
                                    <React.Fragment key={yr}>
                                        <line x1={padL + col * 75} y1={6 + row * 11} x2={padL + col * 75 + 12} y2={6 + row * 11} stroke={yearColors[yr]} strokeWidth="2" />
                                        <text x={padL + col * 75 + 16} y={9 + row * 11} fontSize="8" fill={mutedText}>{yr}</text>
                                    </React.Fragment>
                                )
                            })}
                        </svg>
                        <div style={{ fontSize: '11px', color: accentAmber, fontWeight: 600, marginTop: '4px' }}>
                            10 years of real CAT data - hard to see a clear direction
                        </div>
                    </div>

                    {/* The Solution: average them */}
                    <div className="ts-section-title">The Solution: Combine Them Into One Line</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        TradeWave takes all those individual years and mathematically averages them into a
                        single line. The random noise of any single year cancels out, and what remains is
                        the <strong>underlying seasonal tendency</strong>:
                    </p>

                    <div style={{ ...cardStyle, padding: '10px 8px 6px', textAlign: 'center' }}>
                        <svg width="100%" viewBox={`0 0 ${svgW} ${svgH}`} style={{ maxWidth: '420px' }}>
                            {grids()}
                            {/* Faded individual lines */}
                            {yearKeys.map(yr => (
                                <path key={yr} d={toPath(CAT_PE2[yr])}
                                    fill="none" stroke={dark ? '#444' : '#d0d0d0'} strokeWidth="0.8" opacity="0.4" />
                            ))}
                            {/* Average line - bold */}
                            <path d={toPath(CAT_AVG)}
                                fill="none" stroke={accentBlue} strokeWidth="3" />
                            {/* Month labels */}
                            {monthLabels.map((m, i) => (
                                <text key={m} x={padL + monthPositions[i] * chartW} y={svgH - 2} fontSize="9" fill={mutedText} textAnchor="middle">{m}</text>
                            ))}
                        </svg>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', marginTop: '4px', fontSize: '10px' }}>
                            <span><span style={{ display: 'inline-block', width: '14px', height: '3px', backgroundColor: dark ? '#444' : '#d0d0d0', marginRight: '4px', verticalAlign: 'middle' }} />Individual years (faded)</span>
                            <span><span style={{ display: 'inline-block', width: '14px', height: '3px', backgroundColor: accentBlue, marginRight: '4px', verticalAlign: 'middle' }} /><strong>Trend line (average)</strong></span>
                        </div>
                        <div style={{ fontSize: '11px', color: accentGreen, fontWeight: 600, marginTop: '6px' }}>
                            Now you can see the probable price path: CAT tends to rise into spring, then decline through fall in midterm years
                        </div>
                    </div>

                    {/* What it tells you */}
                    <div className="ts-section-title">How to Read the Trend Chart</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        {[
                            { icon: '📈', label: 'Line going up', text: 'Prices have historically risen during this period across the years analyzed', color: accentGreen },
                            { icon: '📉', label: 'Line going down', text: 'Prices have historically fallen during this period across the years analyzed', color: '#ef4444' },
                            { icon: '➡️', label: 'Flat line', text: 'No strong directional tendency - prices moved sideways on average', color: accentAmber },
                            { icon: '🎯', label: 'Highlighted window', text: 'The shaded area marks the specific seasonal pattern you are looking at', color: accentBlue },
                        ].map((item, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, padding: '10px', display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
                                <div style={{ fontSize: '16px', flexShrink: 0 }}>{item.icon}</div>
                                <div>
                                    <div style={{ fontSize: '11px', fontWeight: 700, color: item.color }}>{item.label}</div>
                                    <div style={{ fontSize: '10px', opacity: 0.7, lineHeight: 1.3, marginTop: '2px' }}>{item.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Different year selections change the trend */}
                    <div className="ts-section-title">Your Settings Shape the Trend</div>
                    <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                        The trend line changes depending on how many years you analyze and which type of years
                        you select. This is what makes TradeWave powerful - you control the lens:
                    </p>

                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {[
                                { label: '10 Years', desc: 'Average of the last 10 years of price data', color: accentBlue, icon: '🔍' },
                                { label: '60 Years', desc: 'Average of 60 years - a much deeper historical view', color: accentGreen, icon: '📚' },
                                { label: 'PE Cycle', desc: 'Only midterm years, or only election years - a 4-year political filter', color: accentPurple, icon: '🏛️' },
                            ].map((s, i) => (
                                <div key={i} style={{
                                    flex: 1, textAlign: 'center', borderRadius: '8px',
                                    background: dark ? `${s.color}12` : `${s.color}08`,
                                    border: `1px solid ${s.color}25`,
                                    padding: '10px 6px',
                                }}>
                                    <div style={{ fontSize: '20px', marginBottom: '4px' }}>{s.icon}</div>
                                    <div style={{ fontSize: '12px', fontWeight: 700, color: s.color }}>{s.label}</div>
                                    <div style={{ fontSize: '10px', opacity: 0.6, marginTop: '4px', lineHeight: 1.3 }}>{s.desc}</div>
                                </div>
                            ))}
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.7, marginTop: '10px', lineHeight: 1.5, textAlign: 'center', fontStyle: 'italic' }}>
                            Each setting produces a different trend line because different years are included in the average.
                            The trend chart always reflects exactly what you have selected.
                        </div>
                    </div>

                    {/* Projection section */}
                    <div className="ts-section-title">Seasonal Projection on the Price Chart</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        You may notice a <strong style={{ color: '#daa520' }}>dashed golden line</strong> on
                        the current price chart. That is the <strong>Seasonal Projection</strong>. It takes
                        a portion of the trend chart starting from today and overlays it on the actual price,
                        scaled to match the current price level.
                    </p>

                    {/* Projection visual - use a slice of real CAT avg data */}
                    <div style={{ ...cardStyle, padding: '10px 8px 6px', textAlign: 'center' }}>
                        <svg width="100%" viewBox="0 0 420 120" style={{ maxWidth: '420px' }}>
                            {/* Grid */}
                            {[1, 2, 3].map(i => (
                                <line key={i} x1="30" y1={i * 30} x2="410" y2={i * 30} stroke={gridLine} strokeWidth="1" />
                            ))}
                            {/* Actual price line (rising into a pattern window) */}
                            <path d="M 30,88 L 55,85 L 80,82 L 105,78 L 130,80 L 155,72 L 180,65 L 205,60 L 230,55 L 255,50 L 270,47"
                                fill="none" stroke={accentBlue} strokeWidth="2" />
                            {/* Projection dashed line (based on trend chart shape - decline) */}
                            <path d="M 270,47 L 290,50 L 310,54 L 330,58 L 350,56 L 370,60 L 390,65 L 410,68"
                                fill="none" stroke="#daa520" strokeWidth="2.5" strokeDasharray="6,4" />
                            {/* Today marker */}
                            <line x1="270" y1="12" x2="270" y2="108" stroke={accentAmber} strokeWidth="1" strokeDasharray="3,3" />
                            <text x="270" y="10" fontSize="9" fill={accentAmber} textAnchor="middle" fontWeight="600">Today</text>
                            {/* Labels */}
                            <text x="150" y="102" fontSize="9" fill={accentBlue} textAnchor="middle" fontWeight="500">Actual Price</text>
                            <text x="350" y="102" fontSize="9" fill="#daa520" textAnchor="middle" fontWeight="500">Seasonal Projection</text>
                            {/* Price axis */}
                            <text x="24" y="90" fontSize="8" fill={mutedText} textAnchor="end">$280</text>
                            <text x="24" y="60" fontSize="8" fill={mutedText} textAnchor="end">$310</text>
                            <text x="24" y="30" fontSize="8" fill={mutedText} textAnchor="end">$340</text>
                        </svg>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', marginTop: '4px', fontSize: '10px' }}>
                            <span><span style={{ display: 'inline-block', width: '14px', height: '2px', backgroundColor: accentBlue, marginRight: '4px', verticalAlign: 'middle' }} />Actual price</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><svg width="14" height="4"><line x1="0" y1="2" x2="14" y2="2" stroke="#daa520" strokeWidth="2" strokeDasharray="3,2" /></svg><strong>Seasonal projection</strong></span>
                        </div>
                    </div>

                    <div style={{ ...cardStyle, background: dark ? 'rgba(218,165,32,0.08)' : 'rgba(218,165,32,0.05)', border: `1px solid ${dark ? 'rgba(218,165,32,0.2)' : 'rgba(218,165,32,0.15)'}`, padding: '10px 14px' }}>
                        <div style={{ fontSize: '11px', lineHeight: 1.6 }}>
                            <strong>How the projection works:</strong> TradeWave takes the trend chart's path from
                            today forward and rescales it to start at the current price. It shows where the price
                            would go <em>if it followed the same historical seasonal trend</em>. You can adjust the
                            projection to look 2 weeks, 1 month, 2 months, or 3 months ahead in Settings.
                        </div>
                    </div>

                    {/* Practical usage */}
                    <div className="ts-section-title">Putting It All Together</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '12px' }}>
                        {[
                            { step: '1', text: 'Select a pattern from the opportunity table. The trend chart loads automatically, showing the average historical price path for that security.', color: accentBlue },
                            { step: '2', text: 'Look at the trend chart to see the big picture - is the typical seasonal movement up, down, or sideways during this part of the year?', color: accentGreen },
                            { step: '3', text: 'The highlighted window on the trend chart marks the specific pattern you selected. See if the trend rises or falls during that window.', color: accentAmber },
                            { step: '4', text: 'Enable the projection on the price chart to see where the historical trend suggests the price could go from here. Compare it to the actual price action.', color: accentPurple },
                        ].map((s, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '22px', height: '22px', borderRadius: '50%',
                                    backgroundColor: s.color, color: '#fff', fontSize: '12px',
                                    fontWeight: 800, display: 'flex', alignItems: 'center',
                                    justifyContent: 'center', flexShrink: 0,
                                }}>{s.step}</div>
                                <div style={{ fontSize: '11px', lineHeight: 1.5 }}>{s.text}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        The trend chart and projection are based on historical averages. They show what has
                        typically happened, not what will happen. Always combine seasonal analysis with current
                        market conditions and your own risk management.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default TrendChartPopup
