import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const ProjectionPopup = ({ onClose, iconRect }) => {
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
    const accentGreen = '#22c55e'
    const accentRed = '#ef4444'
    const accentBlue = '#3b82f6'
    const accentAmber = '#f59e0b'
    const accentPurple = '#a78bfa'
    const mutedText = dark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.45)'
    const cardBg = dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'
    const cardBorder = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'

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

    const projectionPeriods = [
        { label: '2 Weeks', color: accentBlue, note: 'Tight focus, less time for the trend to play out' },
        { label: '1 Month', color: accentGreen, note: 'Good balance of visibility and reliability' },
        { label: '2 Months', color: accentAmber, note: 'Broader view of the expected seasonal arc' },
        { label: '3 Months', color: accentPurple, note: 'Full seasonal window perspective' },
    ]

    const steps = [
        { num: '1', text: 'The trend chart shows the average seasonal path based on your selected years' },
        { num: '2', text: 'Starting from today\'s closing price, a slice of that trend is extracted for the projection period' },
        { num: '3', text: 'The slice is rescaled to start at the current price and overlaid as a dashed golden line' },
    ]

    const enableSteps = [
        { num: '1', text: 'Open Settings (gear icon)' },
        { num: '2', text: 'Check "Show Projection" under Price Chart' },
        { num: '3', text: 'Select projection period' },
        { num: '4', text: 'Or click the "Proj" button in the price chart title bar' },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Seasonal Projection</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card - amber tint */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.06)', border: `1px solid ${dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Where might the price go if history repeats?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The seasonal projection overlays a dashed golden line on the current price chart,
                            showing the historical seasonal path from today forward, scaled to the current price.
                        </div>
                    </div>

                    {/* How It Works */}
                    <div className="ts-section-title">How It Works</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {steps.map((s, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 14px' }}>
                                <div style={{
                                    width: '26px', height: '26px', borderRadius: '50%',
                                    background: dark ? 'rgba(245,158,11,0.15)' : 'rgba(245,158,11,0.12)',
                                    border: `1px solid ${accentAmber}40`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: '13px', fontWeight: 800, color: accentAmber, flexShrink: 0,
                                }}>{s.num}</div>
                                <div style={{ fontSize: '11px', lineHeight: 1.4 }}>{s.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* SVG price chart visual */}
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <svg width="100%" height="140" viewBox="0 0 400 140" style={{ maxWidth: '400px', display: 'block', margin: '0 auto' }}>
                            {/* Price axis labels */}
                            <text x="12" y="22" fontSize="9" fill={mutedText} fontWeight="500">$340</text>
                            <text x="12" y="62" fontSize="9" fill={mutedText} fontWeight="500">$310</text>
                            <text x="12" y="102" fontSize="9" fill={mutedText} fontWeight="500">$280</text>

                            {/* Grid lines */}
                            <line x1="40" y1="18" x2="385" y2="18" stroke={mutedText} strokeWidth="0.5" strokeOpacity="0.2" />
                            <line x1="40" y1="58" x2="385" y2="58" stroke={mutedText} strokeWidth="0.5" strokeOpacity="0.2" />
                            <line x1="40" y1="98" x2="385" y2="98" stroke={mutedText} strokeWidth="0.5" strokeOpacity="0.2" />

                            {/* Today divider line */}
                            <line x1="220" y1="10" x2="220" y2="115" stroke={mutedText} strokeWidth="1" strokeDasharray="4,3" strokeOpacity="0.5" />
                            <text x="220" y="126" textAnchor="middle" fontSize="10" fill={textColor} fontWeight="600">Today</text>

                            {/* Actual price line (solid blue) */}
                            <polyline
                                points="45,88 65,82 85,85 105,76 125,72 145,78 165,68 185,62 200,58 220,55"
                                fill="none" stroke={accentBlue} strokeWidth="2"
                            />

                            {/* Projection line (dashed golden) */}
                            <polyline
                                points="220,55 240,50 260,44 280,38 300,32 320,28 340,22 360,20 380,18"
                                fill="none" stroke={accentAmber} strokeWidth="2" strokeDasharray="6,4"
                            />

                            {/* Projection area (subtle fill) */}
                            <polygon
                                points="220,55 240,50 260,44 280,38 300,32 320,28 340,22 360,20 380,18 380,98 220,98"
                                fill={accentAmber} opacity="0.06"
                            />

                            {/* Labels */}
                            <text x="130" y="98" textAnchor="middle" fontSize="10" fill={accentBlue} fontWeight="600">Actual Price</text>
                            <text x="310" y="60" textAnchor="middle" fontSize="10" fill={accentAmber} fontWeight="600">Seasonal Projection</text>

                            {/* Small dot at junction */}
                            <circle cx="220" cy="55" r="3" fill={textColor} />
                        </svg>
                        <div style={{ textAlign: 'center', fontSize: '10px', opacity: 0.6, marginTop: '6px' }}>
                            The dashed golden line shows where price historically goes from this point in the seasonal cycle
                        </div>
                    </div>

                    {/* Projection Periods */}
                    <div className="ts-section-title">Projection Periods</div>
                    <div style={{ display: 'flex', gap: '6px', marginBottom: '14px' }}>
                        {projectionPeriods.map((p, i) => (
                            <div key={i} style={{
                                flex: 1, textAlign: 'center', borderRadius: '6px',
                                background: cardBg,
                                border: `1px solid ${p.color}30`,
                                borderTop: `3px solid ${p.color}`,
                                padding: '10px 6px',
                            }}>
                                <div style={{ fontSize: '12px', fontWeight: 700, color: p.color, marginBottom: '4px' }}>{p.label}</div>
                                <div style={{ fontSize: '10px', opacity: 0.6, lineHeight: 1.3 }}>{p.note}</div>
                            </div>
                        ))}
                    </div>

                    {/* What Changes the Projection */}
                    <div className="ts-section-title">What Changes the Projection</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        The projection updates dynamically based on your analysis settings. Three factors shape it:
                    </p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {[
                            { label: 'Years', color: accentBlue, desc: 'More or fewer years averaged into the trend changes the seasonal path' },
                            { label: 'PE Cycle', color: accentPurple, desc: 'Switching to cycle-aware mode uses only years from the same presidential phase' },
                            { label: 'Security', color: accentGreen, desc: 'Each stock, ETF, or index has its own unique seasonal fingerprint' },
                        ].map((item, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '4px', alignSelf: 'stretch', borderRadius: '2px',
                                    backgroundColor: item.color, flexShrink: 0,
                                }} />
                                <div>
                                    <span style={{ fontSize: '11px', fontWeight: 700, color: item.color }}>{item.label}: </span>
                                    <span style={{ fontSize: '11px', opacity: 0.7 }}>{item.desc}</span>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* How to Enable */}
                    <div className="ts-section-title">How to Enable</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '14px' }}>
                        {enableSteps.map((s, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 0' }}>
                                <div style={{
                                    width: '22px', height: '22px', borderRadius: '50%',
                                    background: dark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.1)',
                                    border: `1px solid ${accentBlue}40`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: '11px', fontWeight: 800, color: accentBlue, flexShrink: 0,
                                }}>{s.num}</div>
                                <div style={{ fontSize: '11px', lineHeight: 1.4 }}>{s.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* Important callout */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.05)', border: `1px solid ${dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: accentAmber, marginBottom: '4px' }}>Important</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                            The projection is a guide, not a guarantee. It shows what happened historically,
                            not what will happen. Use it alongside current price action, news, and your own analysis.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        Seasonal projections are derived from historical averages and do not account for
                        current fundamentals, earnings, or macro events. Past seasonal behavior does not
                        guarantee future price movement.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default ProjectionPopup
