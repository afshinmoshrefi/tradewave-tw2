import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const FilteringPopup = ({ onClose, iconRect }) => {
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

    const codeBg = dark ? 'rgba(59,130,246,0.12)' : 'rgba(59,130,246,0.07)'
    const codeBorder = dark ? 'rgba(59,130,246,0.25)' : 'rgba(59,130,246,0.15)'
    const codeColor = dark ? '#93c5fd' : '#2563eb'

    const filters = [
        { filter: 'days range', example: '10-90', desc: 'Only patterns with 10-90 day holding period' },
        { filter: 'avgp', example: 'avgp>5', desc: 'Average profit above 5%' },
        { filter: 'sr', example: 'sr>1.5', desc: 'Sharpe Ratio above 1.5' },
        { filter: 'twr', example: 'twr>2', desc: 'TradeWave Ratio above 2' },
        { filter: 'twa', example: 'twa>7', desc: 'TradeWave Average above 7' },
        { filter: 'tl', example: 'tl>70', desc: 'Trend Long score above 70 (current momentum)' },
        { filter: 'price', example: 'price>50', desc: 'Stock price above $50 (or price<200 for below)' },
        { filter: 'ml', example: 'ml>70', desc: 'AI Score (0-100) above 70 (also: ais)' },
        { filter: 'win', example: 'win>60', desc: 'AI win probability above 60% (also: wp)' },
        { filter: 'predr', example: 'predr>5', desc: 'AI predicted return above 5%' },
        { filter: 'pmfe', example: 'pmfe>8', desc: 'AI predicted max upside above 8%' },
        { filter: 'text', example: 'AAPL', desc: 'Only show patterns for that ticker symbol' },
    ]

    const combos = [
        { name: 'Conservative Trader', filter: '20-60;sr>1.5;avgp>3', desc: 'Medium-term patterns with high consistency and decent returns', color: accentGreen },
        { name: 'Momentum Seeker', filter: '10-30;tl>70;sr>1', desc: 'Short-term patterns where current price trend is strong', color: accentBlue },
        { name: 'AI Conviction', filter: '10-90;ml>70;win>60', desc: 'Patterns the AI model scores highly with a strong win probability', color: accentBlue },
        { name: 'Value Hunter', filter: '60-200;avgp>8;price<100', desc: 'Longer-term patterns in lower-priced stocks with high average returns', color: accentAmber },
    ]

    const rowBg = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Filtering the Opportunity Table</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.06)', border: `1px solid ${dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Find exactly the patterns you are looking for.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The filter textbox lets you narrow thousands of opportunities down to the handful
                            that match your criteria using simple text commands.
                        </div>
                    </div>

                    {/* Filter Syntax */}
                    <div className="ts-section-title">Filter Syntax</div>
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Format</div>
                        <div style={{ background: codeBg, border: `1px solid ${codeBorder}`, borderRadius: '6px', padding: '8px 12px', fontFamily: 'monospace', fontSize: '13px', color: codeColor, marginBottom: '10px' }}>
                            days-range;condition;condition;...
                        </div>
                        <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Example</div>
                        <div style={{ background: codeBg, border: `1px solid ${codeBorder}`, borderRadius: '6px', padding: '8px 12px', fontFamily: 'monospace', fontSize: '13px', color: codeColor, marginBottom: '8px' }}>
                            10-90;avgp&gt;5;sr&gt;1;twr&gt;1.5;twa&gt;7
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.65 }}>
                            Separate each condition with a semicolon. All conditions must be true for a pattern to appear.
                        </div>
                    </div>

                    {/* Available Filters */}
                    <div className="ts-section-title">Available Filters</div>
                    <div style={{ ...cardStyle, padding: '0', overflow: 'hidden' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '70px 90px 1fr', fontSize: '10px', fontWeight: 700, padding: '8px 12px', borderBottom: `1px solid ${cardBorder}`, textTransform: 'uppercase', letterSpacing: '0.3px', color: mutedText }}>
                            <div>Filter</div>
                            <div>Example</div>
                            <div>What It Does</div>
                        </div>
                        {filters.map((f, i) => (
                            <div key={i} style={{ display: 'grid', gridTemplateColumns: '70px 90px 1fr', fontSize: '11px', padding: '7px 12px', background: i % 2 === 0 ? 'transparent' : rowBg, borderBottom: i < filters.length - 1 ? `1px solid ${cardBorder}` : 'none' }}>
                                <div style={{ fontWeight: 600 }}>{f.filter}</div>
                                <div style={{ fontFamily: 'monospace', fontSize: '10px', color: codeColor }}>{f.example}</div>
                                <div style={{ opacity: 0.7 }}>{f.desc}</div>
                            </div>
                        ))}
                    </div>

                    {/* Combining Filters */}
                    <div className="ts-section-title">Combining Filters</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {combos.map((c, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px 12px' }}>
                                <div style={{ width: '4px', alignSelf: 'stretch', borderRadius: '2px', backgroundColor: c.color, flexShrink: 0 }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                                        <span style={{ fontSize: '12px', fontWeight: 700 }}>{c.name}</span>
                                    </div>
                                    <div style={{ background: codeBg, border: `1px solid ${codeBorder}`, borderRadius: '4px', padding: '4px 8px', fontFamily: 'monospace', fontSize: '11px', color: codeColor, marginBottom: '4px', display: 'inline-block' }}>
                                        {c.filter}
                                    </div>
                                    <div style={{ fontSize: '11px', opacity: 0.65, lineHeight: 1.4 }}>{c.desc}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* How Days Range Re-Ranking Works */}
                    <div className="ts-section-title">How Days Range Re-Ranking Works</div>
                    <div style={{ ...cardStyle, borderLeft: `3px solid ${accentBlue}`, padding: '14px 16px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.5, marginBottom: '10px' }}>
                            When you type a days range (e.g., 10-30), the table does not simply hide patterns outside that range.
                            It re-selects the best Sharpe Ratio pattern for each stock within the new range.
                        </div>
                        {/* SVG visual: two tables with arrow */}
                        <svg width="100%" height="80" viewBox="0 0 420 80" style={{ maxWidth: '420px', display: 'block', margin: '0 auto' }}>
                            {/* Left table */}
                            <rect x="10" y="5" width="140" height="65" rx="6" fill={dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'} stroke={cardBorder} strokeWidth="1" />
                            <text x="80" y="22" textAnchor="middle" fontSize="9" fontWeight="700" fill={mutedText}>Before filter</text>
                            <text x="80" y="40" textAnchor="middle" fontSize="11" fontWeight="600" fill={textColor}>MSFT</text>
                            <text x="80" y="56" textAnchor="middle" fontSize="10" fill={accentGreen}>200 days, SR 2.5</text>

                            {/* Arrow */}
                            <line x1="160" y1="38" x2="250" y2="38" stroke={accentBlue} strokeWidth="2" />
                            <polygon points="248,32 260,38 248,44" fill={accentBlue} />
                            <text x="210" y="28" textAnchor="middle" fontSize="9" fontWeight="600" fill={accentBlue}>Re-ranked</text>

                            {/* Right table */}
                            <rect x="270" y="5" width="140" height="65" rx="6" fill={dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.04)'} stroke={`${accentBlue}40`} strokeWidth="1" />
                            <text x="340" y="22" textAnchor="middle" fontSize="9" fontWeight="700" fill={mutedText}>After 10-30 filter</text>
                            <text x="340" y="40" textAnchor="middle" fontSize="11" fontWeight="600" fill={textColor}>MSFT</text>
                            <text x="340" y="56" textAnchor="middle" fontSize="10" fill={accentAmber}>25 days, SR 1.8</text>
                        </svg>
                        <div style={{ fontSize: '11px', opacity: 0.65, marginTop: '8px', lineHeight: 1.4 }}>
                            New stocks can appear because their best pattern within the range was previously hidden
                            by a longer, higher-SR pattern.
                        </div>
                    </div>

                    {/* Required Winning Years */}
                    <div className="ts-section-title">Required Winning Years</div>
                    <div style={{ ...cardStyle, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.5 }}>
                            This separate control sets a minimum win rate. Example: "9 of 10" means 90% of years must be profitable.
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.65, marginTop: '6px', lineHeight: 1.4 }}>
                            It is independent of the text filter. Both are applied together.
                        </div>
                    </div>

                    {/* MFE Threshold Filter */}
                    <div className="ts-section-title">MFE Threshold Filter</div>
                    <div style={{ ...cardStyle, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.5, marginBottom: '6px' }}>
                            The MFE filter in the bottom bar is stricter than text filters. It requires every single year
                            to have reached the minimum MFE level.
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.65, lineHeight: 1.4 }}>
                            A text filter like <span style={{ fontFamily: 'monospace', color: codeColor }}>twr&gt;1.5</span> checks
                            the average across years. The MFE threshold checks every year individually.
                        </div>
                    </div>

                    {/* Expand Mode */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '4px', color: accentPurple }}>Expand Mode</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                            After filtering to a single ticker, click the Expand button to see all holding-period
                            variations for that stock. Compare 20+ patterns at once to find the best holding period.
                        </div>
                    </div>

                    {/* Tips */}
                    <div className="ts-section-title">Tips</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {[
                            'Start simple: just type a ticker name to filter to one stock.',
                            'Add one condition at a time until the list narrows to what you want.',
                            'Clear the filter box to return to the full unfiltered view.',
                        ].map((tip, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px' }}>
                                <div style={{
                                    width: '20px', height: '20px', borderRadius: '50%', flexShrink: 0,
                                    background: dark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.1)',
                                    border: `1px solid ${accentBlue}30`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: '10px', fontWeight: 700, color: accentBlue,
                                }}>{i + 1}</div>
                                <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.4 }}>{tip}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        Filters help you focus on patterns that match your trading style and risk tolerance.
                        Combine multiple conditions to surface only the highest-quality opportunities from
                        the full dataset.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default FilteringPopup
