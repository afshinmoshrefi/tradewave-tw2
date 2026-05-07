import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const DaysOutPopup = ({ onClose, iconRect }) => {
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

    // Holding period cards
    const holdingPeriods = [
        { days: '15 days', color: accentBlue, label: 'Short-term', desc: 'Captures quick moves' },
        { days: '45 days', color: accentGreen, label: 'Medium-term', desc: 'Balances opportunity and risk' },
        { days: '120 days', color: accentAmber, label: 'Long-term', desc: 'Captures broader seasonal arcs' },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Days Out and Date Selection</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.06)', border: `1px solid ${dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Every seasonal pattern is defined by two things: when it starts and how long it lasts.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The start date and holding period (Days Out) together define the exact calendar window of a trade.
                        </div>
                    </div>

                    {/* How a Pattern is Defined - timeline SVG */}
                    <div className="ts-section-title">How a Pattern is Defined</div>
                    <div style={{ ...cardStyle, textAlign: 'center', padding: '16px 12px' }}>
                        <svg width="100%" viewBox="0 0 420 90" style={{ maxWidth: '420px' }}>
                            {/* Timeline bar */}
                            <rect x="40" y="35" width="340" height="8" rx="4" fill={dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'} />

                            {/* Active window highlight */}
                            <rect x="100" y="33" width="200" height="12" rx="4" fill={accentBlue} fillOpacity="0.15" />

                            {/* Entry marker - green triangle */}
                            <polygon points="100,30 107,18 93,18" fill={accentGreen} />
                            <text x="100" y="13" textAnchor="middle" fontSize="10" fontWeight="700" fill={accentGreen}>Entry</text>
                            <text x="100" y="58" textAnchor="middle" fontSize="9" fontWeight="600" fill={accentGreen}>Mar 5</text>

                            {/* Exit marker - red triangle */}
                            <polygon points="300,30 307,18 293,18" fill={accentRed} />
                            <text x="300" y="13" textAnchor="middle" fontSize="10" fontWeight="700" fill={accentRed}>Exit</text>
                            <text x="300" y="58" textAnchor="middle" fontSize="9" fontWeight="600" fill={accentRed}>Apr 20</text>

                            {/* Bracket and label */}
                            <line x1="110" y1="68" x2="290" y2="68" stroke={accentAmber} strokeWidth="1.5" />
                            <line x1="110" y1="64" x2="110" y2="72" stroke={accentAmber} strokeWidth="1.5" />
                            <line x1="290" y1="64" x2="290" y2="72" stroke={accentAmber} strokeWidth="1.5" />
                            <text x="200" y="83" textAnchor="middle" fontSize="11" fontWeight="700" fill={accentAmber}>46 Days</text>

                            {/* Timeline ticks */}
                            {[40, 130, 220, 310, 380].map((x, i) => (
                                <line key={i} x1={x} y1="44" x2={x} y2="48" stroke={mutedText} strokeWidth="1" />
                            ))}
                        </svg>
                        <div style={{ fontSize: '11px', opacity: 0.7, marginTop: '6px' }}>
                            Buy at close on entry date. Sell at close on exit date.
                        </div>
                    </div>

                    {/* Start Date */}
                    <div className="ts-section-title">Start Date</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '12px' }}>
                        <div style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '10px 12px' }}>
                            <div style={{ width: '4px', alignSelf: 'stretch', borderRadius: '2px', backgroundColor: accentBlue, flexShrink: 0 }} />
                            <div>
                                <div style={{ fontSize: '11px', fontWeight: 700, color: accentBlue, marginBottom: '2px' }}>What it controls</div>
                                <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.5 }}>
                                    The calendar date when the seasonal trade begins. All patterns in the opportunity table share the same
                                    start date range based on your current settings.
                                </div>
                            </div>
                        </div>
                        <div style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '10px 12px' }}>
                            <div style={{ width: '4px', alignSelf: 'stretch', borderRadius: '2px', backgroundColor: accentGreen, flexShrink: 0 }} />
                            <div>
                                <div style={{ fontSize: '11px', fontWeight: 700, color: accentGreen, marginBottom: '2px' }}>Start Date Nudge</div>
                                <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.5 }}>
                                    On desktop, use the small arrows next to the start date to shift it forward or back by one day.
                                    The end date stays fixed, so the holding period adjusts automatically.
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Days Out (Holding Period) */}
                    <div className="ts-section-title">Days Out (Holding Period)</div>
                    <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                        Days Out is the number of calendar days from entry to exit. Different holding periods reveal different
                        seasonal behaviors for the same stock and start date.
                    </p>

                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                        {holdingPeriods.map((hp, i) => (
                            <div key={i} style={{
                                ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', padding: '12px 8px',
                                borderTop: `3px solid ${hp.color}`,
                            }}>
                                <div style={{ fontSize: '16px', fontWeight: 800, color: hp.color }}>{hp.days}</div>
                                <div style={{ fontSize: '10px', fontWeight: 600, marginTop: '4px', opacity: 0.8 }}>{hp.label}</div>
                                <div style={{ fontSize: '10px', opacity: 0.6, marginTop: '4px', lineHeight: 1.3 }}>{hp.desc}</div>
                            </div>
                        ))}
                    </div>

                    <div style={{ ...cardStyle, padding: '10px 14px' }}>
                        <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                            The Days selectbox in the wave viewer banner lets you change the holding period. The start date stays
                            the same, and the end date adjusts.
                        </div>
                    </div>

                    {/* How Days Range Filter Works */}
                    <div className="ts-section-title">How Days Range Filter Works</div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, padding: '14px 16px' }}>
                        <div style={{ fontSize: '11px', lineHeight: 1.6, marginBottom: '10px' }}>
                            When you type a days range in the filter (e.g., 10-90), the table does not simply hide patterns outside that range.
                        </div>
                        <div style={{ fontSize: '11px', lineHeight: 1.6, marginBottom: '10px', fontWeight: 600 }}>
                            It re-runs the best-Sharpe selection within the new range. This means new patterns can appear that were hidden
                            before because a longer pattern was outranking them.
                        </div>
                        <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '10px 12px', marginBottom: 0 }}>
                            <div style={{ fontSize: '11px', lineHeight: 1.5 }}>
                                <strong>Example:</strong> MSFT shows a 200-day pattern with SR 2.5 (the best overall). Filter to 10-30 days:
                                the 200-day pattern is excluded, and a 25-day MSFT pattern with SR 1.8 now appears.
                            </div>
                        </div>
                    </div>

                    {/* Tips */}
                    <div className="ts-section-title">Tips</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {[
                            { text: 'Shorter patterns (10-30 days) are good for active traders who want quick, focused moves.', color: accentBlue },
                            { text: 'Longer patterns (60-200 days) capture broader seasonal trends and may have higher average returns.', color: accentGreen },
                            { text: 'Use the Expand button after filtering by ticker to see every holding period variation for one stock.', color: accentPurple },
                        ].map((tip, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '6px', height: '6px', borderRadius: '50%',
                                    backgroundColor: tip.color, flexShrink: 0, marginTop: '5px',
                                }} />
                                <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>{tip.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* Free User Note */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.05)', border: `1px solid ${dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.15)'}`, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 14px' }}>
                        <svg width="18" height="18" viewBox="0 0 18 18" style={{ flexShrink: 0, marginTop: '1px' }}>
                            <circle cx="9" cy="9" r="8" fill={accentAmber} fillOpacity="0.15" stroke={accentAmber} strokeWidth="1" />
                            <text x="9" y="13" textAnchor="middle" fontSize="11" fontWeight="800" fill={accentAmber}>!</text>
                        </svg>
                        <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: accentAmber, marginBottom: '2px' }}>Free User Note</div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Free accounts cannot change the start date. The date is locked to the current day.
                                Upgrade to explore patterns at any date.
                            </div>
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        Seasonal patterns reflect historical tendencies, not guarantees. Use Days Out and date selection
                        as research tools alongside your own analysis and risk management.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default DaysOutPopup
