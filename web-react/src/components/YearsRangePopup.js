import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const YearsRangePopup = ({ onClose, iconRect }) => {
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

    const exampleStocks = [
        { years: '5 Years', winRate: '100%', avgP: '12%', sr: '3.2', tint: accentGreen, tintBg: dark ? 'rgba(34,197,94,0.08)' : 'rgba(34,197,94,0.05)', tintBorder: dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.12)', comment: 'Looks amazing' },
        { years: '15 Years', winRate: '80%', avgP: '7%', sr: '1.8', tint: textColor, tintBg: cardBg, tintBorder: cardBorder, comment: 'Still strong' },
        { years: '30 Years', winRate: '67%', avgP: '4%', sr: '0.9', tint: accentAmber, tintBg: dark ? 'rgba(245,158,11,0.08)' : 'rgba(245,158,11,0.05)', tintBorder: dark ? 'rgba(245,158,11,0.2)' : 'rgba(245,158,11,0.12)', comment: 'Pattern weakens over time' },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Years and Data Depth</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.06)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            How far back should you look? The answer changes everything.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The Years setting controls how many years of historical data TradeWave uses.
                            It is the single most important setting that shapes every number you see.
                        </div>
                    </div>

                    {/* One Setting, Everything Changes */}
                    <div className="ts-section-title">One Setting, Everything Changes</div>
                    <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                        The Years selectbox drives two things simultaneously:
                    </p>
                    <div style={{ fontSize: '12px', marginBottom: '6px', paddingLeft: '12px' }}>
                        <div style={{ marginBottom: '4px' }}><strong>1.</strong> The metrics in the opportunity table (SR, AvgP, TWR, TWA, win rate)</div>
                        <div><strong>2.</strong> The number of bars in the Gain-Loss Bar Chart</div>
                    </div>

                    {/* Side-by-side visual */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', borderLeft: `3px solid ${accentBlue}`, padding: '10px 8px' }}>
                            <div style={{ fontSize: '10px', fontWeight: 600, color: accentBlue, marginBottom: '4px' }}>Table</div>
                            <div style={{ fontSize: '11px' }}>Shows <strong>SR 2.1</strong></div>
                            <div style={{ fontSize: '10px', opacity: 0.6 }}>based on 10 years</div>
                        </div>
                        <div style={{ fontSize: '22px', fontWeight: 700, color: mutedText, flexShrink: 0 }}>=</div>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', borderLeft: `3px solid ${accentBlue}`, padding: '10px 8px' }}>
                            <div style={{ fontSize: '10px', fontWeight: 600, color: accentBlue, marginBottom: '4px' }}>Bar Chart</div>
                            <div style={{ fontSize: '11px' }}>Shows <strong>10 bars</strong></div>
                            <div style={{ fontSize: '10px', opacity: 0.6 }}>one per year</div>
                        </div>
                    </div>
                    <p style={{ fontSize: '11px', opacity: 0.65, fontStyle: 'italic', textAlign: 'center', marginBottom: '14px' }}>
                        Table and chart are always in sync. They reflect the same dataset.
                    </p>

                    {/* The Tradeoff */}
                    <div className="ts-section-title">The Tradeoff</div>
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        {/* Gradient bar */}
                        <div style={{
                            height: '18px', borderRadius: '9px', position: 'relative',
                            background: `linear-gradient(90deg, ${accentBlue}, ${accentGreen}, ${accentAmber})`,
                            marginBottom: '6px',
                        }}>
                            {[
                                { pos: '0%', label: '5' },
                                { pos: '10%', label: '10' },
                                { pos: '30%', label: '25' },
                                { pos: '50%', label: '40' },
                                { pos: '100%', label: '98' },
                            ].map((m, i) => (
                                <div key={i} style={{ position: 'absolute', left: m.pos, top: '22px', transform: 'translateX(-50%)', fontSize: '9px', color: mutedText, fontWeight: 600 }}>{m.label}</div>
                            ))}
                        </div>
                        <div style={{ height: '16px' }} />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
                            {[
                                { range: '5-10 years', color: accentBlue, text: 'Most recent behavior. High relevance to current market conditions. Smaller sample size means less statistical confidence.' },
                                { range: '15-30 years', color: accentGreen, text: 'The sweet spot for most analysis. Balances recency with statistical significance. Enough data to trust the pattern.' },
                                { range: '40-98 years', color: accentAmber, text: 'Deep structural patterns that survived multiple market regimes, recessions, and bull markets. High confidence but may include outdated market behavior.' },
                            ].map((r, i) => (
                                <div key={i} style={{ borderLeft: `3px solid ${r.color}`, paddingLeft: '10px' }}>
                                    <div style={{ fontSize: '11px', fontWeight: 700, color: r.color }}>{r.range}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.65, lineHeight: 1.4, marginTop: '2px' }}>{r.text}</div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Same Stock, Different Stories */}
                    <div className="ts-section-title">Same Stock, Different Stories</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '6px' }}>
                        {exampleStocks.map((s, i) => (
                            <div key={i} style={{
                                ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center',
                                background: s.tintBg, border: `1px solid ${s.tintBorder}`, padding: '10px 8px',
                            }}>
                                <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '4px' }}>AAPL - {s.years}</div>
                                <div style={{ fontSize: '10px', lineHeight: 1.6 }}>
                                    Win Rate: <strong>{s.winRate}</strong><br />
                                    AvgP: <strong>{s.avgP}</strong><br />
                                    SR: <strong>{s.sr}</strong>
                                </div>
                                <div style={{ fontSize: '10px', fontStyle: 'italic', opacity: 0.7, marginTop: '4px', color: s.tint }}>{s.comment}</div>
                            </div>
                        ))}
                    </div>
                    <p style={{ fontSize: '11px', fontStyle: 'italic', opacity: 0.65, textAlign: 'center', marginBottom: '14px' }}>
                        A pattern visible in both short and long timeframes is particularly compelling.
                    </p>

                    {/* How to Choose */}
                    <div className="ts-section-title">How to Choose</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {[
                            { title: 'Start with 10 years', text: 'A good default. Recent enough to reflect current market dynamics, large enough sample to be meaningful.', color: accentBlue },
                            { title: 'Check with 20-25 years', text: 'If the pattern still holds, it has proven itself across different market environments.', color: accentGreen },
                            { title: 'Use 40+ for conviction', text: 'If a pattern persists over 40+ years, it is likely driven by structural or cyclical forces, not recent coincidence.', color: accentAmber },
                        ].map((c, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '10px 12px' }}>
                                <div style={{ width: '4px', alignSelf: 'stretch', borderRadius: '2px', backgroundColor: c.color, flexShrink: 0 }} />
                                <div>
                                    <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '2px' }}>{c.title}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>{c.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* PE Cycle and Years */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '4px', color: accentPurple }}>PE Cycle and Years</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                            When PE Cycle is enabled, the Years setting counts cycle years, not consecutive years.
                            Setting Years to 10 with PE+2 means 10 midterm years, spanning roughly 40 calendar years of data.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        The right lookback period depends on your goals. Shorter windows capture recent dynamics,
                        longer windows reveal enduring structural patterns. Experiment with different settings to
                        build conviction in the patterns you trade.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default YearsRangePopup
