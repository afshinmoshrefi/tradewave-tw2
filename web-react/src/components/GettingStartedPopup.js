import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const GettingStartedPopup = ({ onClose, iconRect }) => {
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

    // Step cards
    const steps = [
        { num: '1', color: accentBlue, text: 'The opportunity table on the left already shows patterns ranked by quality. No setup needed.' },
        { num: '2', color: accentGreen, text: 'Click any row. The bar chart shows price direction by year: green/up wins for a long setup; red/down wins for a short setup.' },
        { num: '3', color: accentAmber, text: 'Swipe to the middle slide to see detailed stats: win rate, average profit, Sharpe Ratio.' },
        { num: '4', color: accentPurple, text: 'Swipe to the last slide to see the current price chart with the seasonal window timing.' },
    ]

    // What to explore
    const explores = [
        { icon: '🌐', title: 'Change the Market', text: 'Use the Securities Group dropdown (top right) to explore S&P 500, NASDAQ 100, ETFs, Crypto, and more.' },
        { icon: '📅', title: 'Filter by Month', text: 'Use Months & Qtrs to see patterns starting in a specific month or quarter.' },
        { icon: '📊', title: 'Adjust History', text: 'The Years setting controls how many years of data are analyzed. More years = larger sample.' },
        { icon: '💾', title: 'Save a Pattern', text: 'Click the + icon above the bar chart to save a pattern to your portfolio.' },
        { icon: '💬', title: 'Ask Tara', text: 'Type any question in the chat. Tara can explain what you see, teach concepts, and guide you step by step.' },
    ]

    // Key terms
    const terms = [
        { term: 'SR', def: 'Sharpe Ratio, consistency score' },
        { term: 'AvgP', def: 'Average profit across all years' },
        { term: 'TWR', def: 'TradeWave Ratio, uses peak profit' },
        { term: 'MFE', def: 'Best point reached during trade' },
        { term: 'MAE', def: 'Worst drawdown during trade' },
        { term: 'Win Rate', def: 'Percentage of profitable years' },
    ]

    // Layout diagram colors
    const zoneBg = (color) => dark ? `${color}15` : `${color}10`
    const zoneBorder = (color) => `${color}35`

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Getting Started with TradeWave</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(34,197,94,0.08)' : 'rgba(34,197,94,0.06)', border: `1px solid ${dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            See your first seasonal pattern in under 60 seconds.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            TradeWave finds calendar windows where stocks tend to move in the same direction year after year.
                            Here is how to start.
                        </div>
                    </div>

                    {/* Your First Pattern */}
                    <div className="ts-section-title">Your First Pattern</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {steps.map((s, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '12px', padding: '14px 16px' }}>
                                <div style={{
                                    width: '28px', height: '28px', borderRadius: '50%',
                                    backgroundColor: s.color, color: '#fff', fontSize: '14px',
                                    fontWeight: 800, display: 'flex', alignItems: 'center',
                                    justifyContent: 'center', flexShrink: 0,
                                }}>{s.num}</div>
                                <div style={{ fontSize: '12px', lineHeight: 1.6, paddingTop: '4px' }}>{s.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* Understanding the Layout */}
                    <div className="ts-section-title">Understanding the Layout</div>
                    <div style={{ ...cardStyle, padding: '14px', textAlign: 'center' }}>
                        <svg width="100%" viewBox="0 0 440 200" style={{ maxWidth: '440px' }}>
                            {/* Top bar */}
                            <rect x="10" y="5" width="420" height="30" rx="6" fill={zoneBg(accentAmber)} stroke={zoneBorder(accentAmber)} strokeWidth="1" />
                            <text x="220" y="24" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentAmber}>Controls: Markets, Date, Settings</text>

                            {/* Left side */}
                            <rect x="10" y="42" width="170" height="150" rx="6" fill={zoneBg(accentBlue)} stroke={zoneBorder(accentBlue)} strokeWidth="1" />
                            <text x="95" y="110" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentBlue}>Opportunity Table</text>
                            <text x="95" y="126" textAnchor="middle" fontSize="9" fill={accentBlue} fillOpacity="0.7">+ Chatbot</text>

                            {/* Right top */}
                            <rect x="188" y="42" width="242" height="72" rx="6" fill={zoneBg(accentGreen)} stroke={zoneBorder(accentGreen)} strokeWidth="1" />
                            <text x="309" y="82" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentGreen}>Bar Chart</text>

                            {/* Right bottom - 3 slides */}
                            <rect x="188" y="120" width="242" height="72" rx="6" fill={zoneBg(accentPurple)} stroke={zoneBorder(accentPurple)} strokeWidth="1" />
                            <text x="309" y="152" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentPurple}>3 Slides: Trend | Stats | Price</text>
                            <text x="309" y="168" textAnchor="middle" fontSize="9" fill={accentPurple} fillOpacity="0.7">Swipe to navigate</text>

                            {/* Connector arrows */}
                            <line x1="180" y1="80" x2="188" y2="80" stroke={mutedText} strokeWidth="1" strokeDasharray="3,2" />
                            <line x1="180" y1="155" x2="188" y2="155" stroke={mutedText} strokeWidth="1" strokeDasharray="3,2" />
                        </svg>
                    </div>

                    {/* What to Explore Next */}
                    <div className="ts-section-title">What to Explore Next</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {explores.map((e, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px 14px' }}>
                                <div style={{ fontSize: '18px', lineHeight: 1, flexShrink: 0, marginTop: '1px' }}>{e.icon}</div>
                                <div>
                                    <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '2px' }}>{e.title}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>{e.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Key Terms */}
                    <div className="ts-section-title">Key Terms (Quick Reference)</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginBottom: '14px' }}>
                        {terms.map((t, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, textAlign: 'center', padding: '10px 8px' }}>
                                <div style={{ fontSize: '14px', fontWeight: 800, color: accentBlue, fontFamily: 'monospace' }}>{t.term}</div>
                                <div style={{ fontSize: '10px', opacity: 0.6, marginTop: '4px', lineHeight: 1.3 }}>{t.def}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        TradeWave is designed to help you research, not to give trading advice. Always do your own analysis.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default GettingStartedPopup
