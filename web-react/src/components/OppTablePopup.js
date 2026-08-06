import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const OppTablePopup = ({ onClose, iconRect }) => {
    const { UITheme, seasonalAppDivH } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [closing, setClosing] = useState(false)
    const dark = UITheme === 'dark'

    const handleClose = () => { setClosing(true); setTimeout(() => onClose(), 200) }
    const handleOverlayClick = (e) => { if (e.target === e.currentTarget) handleClose() }

    const bgColor = dark ? '#1e1e2e' : '#ffffff'
    const textColor = tc.text
    const cardBg = dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'
    const cardBorder = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'
    const accentGreen = '#22c55e'
    const accentRed = '#ef4444'
    const accentBlue = '#3b82f6'
    const accentAmber = '#f59e0b'
    const accentPurple = '#a78bfa'
    const mutedText = dark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.45)'

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

    // Sample table data
    const tableHeaders = ['Date', 'Ticker', 'Days', 'Dir', 'AvgP', 'SR', 'TWA', 'TWR']
    const tableRows = [
        ['03-15', 'AAPL', '45', 'Long', '8.2', '2.1', '7.5', '2.4'],
        ['03-15', 'MSFT', '30', 'Long', '5.1', '1.8', '6.2', '1.9'],
        ['03-16', 'BA', '60', 'Short', '4.5', '1.5', '5.8', '1.6'],
    ]

    // Column guide cards
    const columnCards = [
        { title: 'Date & Ticker', color: accentBlue, text: 'The pattern start date and the security symbol. Click any row to load it.' },
        { title: 'Days & Dir', color: accentGreen, text: 'How many calendar days the pattern holds, and whether it is Long (bullish) or Short (bearish).' },
        { title: 'AvgP (Average Profit)', color: accentAmber, text: 'The average percent return across all years in the sample.' },
        { title: 'SR (Sharpe Ratio)', color: accentGreen, text: 'Risk-adjusted consistency. Higher = more reliable. The table is sorted by SR by default.' },
        { title: 'TWA & TWR', color: accentPurple, text: 'TradeWave Average and TradeWave Ratio. Additional quality metrics. TWR uses peak profit (MFE) instead of final return.' },
        { title: 'TL & Price', color: accentBlue, text: 'Real-time trend score and current stock price. TL shows current price momentum (0-100).' },
        { title: 'AIS, Win%, PredR & PMFE', color: '#818cf8', text: 'Current-condition model readings. Patterns under 10 days use the 10-day model minimum, which is explained in the AI value tooltip. Patterns from 10 through 90 days use their current duration. An outline means more durations are available to compare, and longer rows show the bounded 90-day checkpoint.' },
    ]

    const headerBg = dark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.08)'
    const rowBg1 = dark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)'
    const rowBg2 = 'transparent'

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>The Opportunity Table</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(34,197,94,0.08)' : 'rgba(34,197,94,0.06)', border: `1px solid ${dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Your starting point for every trade idea.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The opportunity table is the heart of TradeWave. It ranks thousands of seasonal patterns
                            by quality so the best ones float to the top.
                        </div>
                    </div>

                    {/* What You See - SVG table mockup */}
                    <div className="ts-section-title">What You See</div>
                    <div style={{ ...cardStyle, padding: '10px 8px 6px', textAlign: 'center', overflowX: 'auto' }}>
                        <svg width="100%" viewBox="0 0 480 110" style={{ maxWidth: '480px' }}>
                            {/* Header row */}
                            <rect x="5" y="5" width="470" height="22" rx="4" fill={headerBg} />
                            {tableHeaders.map((h, i) => (
                                <text key={i} x={35 + i * 58} y="20" fontSize="10" fontWeight="700" fill={accentBlue} textAnchor="middle">{h}</text>
                            ))}
                            {/* Data rows */}
                            {tableRows.map((row, ri) => {
                                const y = 32 + ri * 24
                                return (
                                    <React.Fragment key={ri}>
                                        <rect x="5" y={y} width="470" height="22" rx="3" fill={ri % 2 === 0 ? rowBg1 : rowBg2} />
                                        {row.map((cell, ci) => {
                                            let fill = textColor
                                            if (ci === 3) fill = cell === 'Long' ? accentGreen : accentRed
                                            if (ci === 1) fill = accentAmber
                                            return (
                                                <text key={ci} x={35 + ci * 58} y={y + 15} fontSize="10" fill={fill} textAnchor="middle" fontWeight={ci === 1 ? '700' : '400'}>{cell}</text>
                                            )
                                        })}
                                    </React.Fragment>
                                )
                            })}
                            {/* Hover highlight hint */}
                            <rect x="5" y="32" width="470" height="22" rx="3" fill={accentBlue} fillOpacity="0.06" stroke={accentBlue} strokeWidth="1" strokeOpacity="0.2" />
                        </svg>
                        <div style={{ fontSize: '10px', color: mutedText, marginTop: '4px' }}>
                            Rows are clickable. The highlighted row loads the pattern into the Wave Viewer.
                        </div>
                    </div>

                    {/* Column Guide */}
                    <div className="ts-section-title">Column Guide</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        {columnCards.map((c, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '4px', alignSelf: 'stretch', borderRadius: '2px',
                                    backgroundColor: c.color, flexShrink: 0,
                                }} />
                                <div>
                                    <div style={{ fontSize: '11px', fontWeight: 700, color: c.color, marginBottom: '2px' }}>{c.title}</div>
                                    <div style={{ fontSize: '10px', opacity: 0.7, lineHeight: 1.4 }}>{c.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* How Patterns Are Ranked - funnel SVG */}
                    <div className="ts-section-title">How Patterns Are Ranked</div>
                    <div style={{ ...cardStyle, textAlign: 'center', padding: '16px' }}>
                        <svg width="100%" height="110" viewBox="0 0 400 110" style={{ maxWidth: '400px' }}>
                            {/* Wide top bar */}
                            <rect x="10" y="5" width="380" height="24" rx="4" fill={dark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.1)'} stroke={accentBlue} strokeWidth="1" strokeOpacity="0.3" />
                            <text x="200" y="21" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentBlue}>Every possible start date + holding period for every stock</text>

                            {/* Arrow */}
                            <polygon points="190,34 210,34 200,44" fill={mutedText} />

                            {/* Middle bar */}
                            <rect x="70" y="48" width="260" height="24" rx="4" fill={dark ? 'rgba(251,191,36,0.12)' : 'rgba(251,191,36,0.1)'} stroke={accentAmber} strokeWidth="1" strokeOpacity="0.3" />
                            <text x="200" y="64" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentAmber}>Best Sharpe Ratio pattern per stock kept</text>

                            {/* Arrow */}
                            <polygon points="190,77 210,77 200,87" fill={mutedText} />

                            {/* Narrow bottom bar */}
                            <rect x="120" y="90" width="160" height="24" rx="4" fill={dark ? 'rgba(34,197,94,0.12)' : 'rgba(34,197,94,0.08)'} stroke={accentGreen} strokeWidth="1" strokeOpacity="0.3" />
                            <text x="200" y="106" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentGreen}>Sorted by Sharpe Ratio, best at top</text>
                        </svg>
                    </div>

                    {/* Default vs Expanded Mode */}
                    <div className="ts-section-title">Default vs Expanded Mode</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                        <div style={{
                            ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', padding: '12px',
                            borderLeft: `3px solid ${accentBlue}`,
                        }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentBlue, marginBottom: '4px' }}>Default</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Shows the single best pattern per stock. Clean, focused list.
                            </div>
                        </div>
                        <div style={{
                            ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', padding: '12px',
                            borderLeft: `3px solid ${accentPurple}`,
                        }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentPurple, marginBottom: '4px' }}>Expanded</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Shows ALL pattern variations per stock. Use with a ticker filter to compare holding periods.
                            </div>
                        </div>
                    </div>

                    {/* Clicking a Row */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 14px' }}>
                        <svg width="20" height="20" viewBox="0 0 20 20" style={{ flexShrink: 0, marginTop: '1px' }}>
                            <circle cx="10" cy="10" r="9" fill={accentBlue} fillOpacity="0.15" stroke={accentBlue} strokeWidth="1" />
                            <polygon points="8,6 15,10 8,14" fill={accentBlue} />
                        </svg>
                        <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: accentBlue, marginBottom: '2px' }}>Clicking a Row</div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Click any row to load that pattern into the Wave Viewer. The bar chart, stats, and trend chart all update instantly.
                            </div>
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        Historical columns describe the complete seasonal pattern; AI columns add current-condition readings for their labeled horizon. Patterns are ranked by consistency, not by profit alone.
                        Always combine seasonal analysis with your own research and risk management.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default OppTablePopup
