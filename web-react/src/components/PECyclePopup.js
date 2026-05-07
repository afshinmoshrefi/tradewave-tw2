import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const PECyclePopup = ({ onClose, iconRect }) => {
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

    const pePhases = [
        { label: 'PE', year: 'Election', color: accentBlue, avg: '6.0%', desc: 'Campaign uncertainty, mixed returns' },
        { label: 'PE+1', year: 'Post-Election', color: accentAmber, avg: '3.0%', desc: 'Weakest year, new policies enacted' },
        { label: 'PE+2', year: 'Midterm', color: accentPurple, avg: '4.0%', desc: 'Volatile, often bottoms mid-year' },
        { label: 'PE+3', year: 'Pre-Election', color: accentGreen, avg: '14.2%', desc: 'Strongest year, growth-friendly push' },
    ]

    const whyCards = [
        {
            title: 'Policy Cycle',
            color: accentBlue,
            text: 'New presidents push unpopular reforms early (PE+1), saving voter-friendly spending for pre-election (PE+3)',
        },
        {
            title: 'Market Psychology',
            color: accentAmber,
            text: 'Uncertainty peaks around elections, then gradually lifts as the new administration\'s direction becomes clear',
        },
        {
            title: 'Legislative Rhythm',
            color: accentPurple,
            text: 'Midterm elections (PE+2) create a second wave of uncertainty, after which markets historically rally strongly',
        },
    ]

    // Bar chart data for the 4-year visual
    const barData = [
        { label: 'PE', avg: 6.0, color: accentBlue },
        { label: 'PE+1', avg: 3.0, color: accentAmber },
        { label: 'PE+2', avg: 4.0, color: accentPurple },
        { label: 'PE+3', avg: 14.2, color: accentGreen },
    ]
    const barMax = Math.max(...barData.map(b => b.avg))

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Presidential Election Cycle</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card - purple tint */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.06)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Markets follow a hidden four-year rhythm tied to elections.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            The Presidential Election Cycle is one of the most well-documented patterns in market history.
                            Different years of the cycle produce remarkably different market behavior.
                        </div>
                    </div>

                    {/* The Four Phases */}
                    <div className="ts-section-title">The Four Phases</div>
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
                            {pePhases.map((p, i) => (
                                <div key={i} style={{
                                    flex: 1, textAlign: 'center', borderRadius: '6px',
                                    background: dark ? `${p.color}15` : `${p.color}10`,
                                    border: `1px solid ${p.color}30`,
                                    padding: '8px 4px',
                                }}>
                                    <div style={{ fontSize: '14px', fontWeight: 800, color: p.color }}>{p.label}</div>
                                    <div style={{ fontSize: '9px', fontWeight: 600, marginTop: '2px', opacity: 0.8 }}>{p.year}</div>
                                    <div style={{
                                        fontSize: '16px', fontWeight: 800, color: p.color,
                                        marginTop: '4px',
                                    }}>{p.avg}</div>
                                    <div style={{ fontSize: '9px', opacity: 0.55, marginTop: '2px', lineHeight: 1.2 }}>avg return</div>
                                    <div style={{ fontSize: '9px', opacity: 0.6, marginTop: '4px', lineHeight: 1.2 }}>{p.desc}</div>
                                </div>
                            ))}
                        </div>
                        {/* Connected dot-and-line flow */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                            {pePhases.map((p, i) => (
                                <React.Fragment key={i}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: p.color }} />
                                    {i < 3 && <div style={{ width: '30px', height: '2px', backgroundColor: mutedText }} />}
                                </React.Fragment>
                            ))}
                        </div>
                    </div>

                    {/* Why This Happens */}
                    <div className="ts-section-title">Why This Happens</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {whyCards.map((c, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '4px', alignSelf: 'stretch', borderRadius: '2px',
                                    backgroundColor: c.color, flexShrink: 0,
                                }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '12px', fontWeight: 700, color: c.color, marginBottom: '2px' }}>{c.title}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>{c.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* SVG bar chart visual */}
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '10px', textAlign: 'center', opacity: 0.7 }}>
                            Average Market Returns by Cycle Year
                        </div>
                        <svg width="100%" height="130" viewBox="0 0 320 130" style={{ maxWidth: '320px', display: 'block', margin: '0 auto' }}>
                            {/* Base line */}
                            <line x1="30" y1="100" x2="300" y2="100" stroke={mutedText} strokeWidth="1" strokeOpacity="0.3" />

                            {barData.map((b, i) => {
                                const barW = 50
                                const gap = 15
                                const x = 42 + i * (barW + gap)
                                const scale = 75 / barMax
                                const barH = b.avg * scale
                                const y = 100 - barH
                                return (
                                    <g key={i}>
                                        <rect x={x} y={y} width={barW} height={barH} rx="4" fill={b.color} opacity="0.8" />
                                        <text x={x + barW / 2} y={y - 6} textAnchor="middle" fontSize="11" fontWeight="700" fill={b.color}>
                                            {b.avg}%
                                        </text>
                                        <text x={x + barW / 2} y="115" textAnchor="middle" fontSize="10" fontWeight="600" fill={textColor}>
                                            {b.label}
                                        </text>
                                    </g>
                                )
                            })}
                        </svg>
                    </div>

                    {/* How TradeWave Uses the PE Cycle */}
                    <div className="ts-section-title">How TradeWave Uses the PE Cycle</div>

                    <div style={{ ...cardStyle, padding: '10px 14px', marginBottom: '6px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, marginBottom: '3px' }}>Standard Mode</div>
                        <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                            By default, TradeWave analyzes consecutive years (10 most recent years).
                            Seasonal patterns are based on all years regardless of cycle.
                        </div>
                    </div>

                    <div style={{ ...cardStyle, padding: '10px 14px', marginBottom: '8px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, marginBottom: '3px' }}>PE Cycle Mode</div>
                        <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                            Check the PE checkbox in the opportunity table to switch to cycle-aware discovery.
                            Instead of 10 consecutive years, it looks at 10 years of the same cycle phase,
                            spanning roughly 40 calendar years.
                        </div>
                    </div>

                    {/* Example card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: accentBlue, marginBottom: '4px' }}>Example</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                            In 2026 (PE+2/midterm), checking the box filters to only midterm years:
                            2022, 2018, 2014, 2010... This reveals patterns specific to midterm election dynamics
                            that are invisible in standard mode.
                        </div>
                    </div>

                    {/* The Hidden Advantage */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 700, color: accentPurple, marginBottom: '4px' }}>The Hidden Advantage</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                            A stock may show no clear seasonal pattern over 10 consecutive years.
                            But isolate just the pre-election years and a powerful recurring move appears.
                            PE Cycle filtering reveals patterns hidden in the noise of mixed cycle phases.
                        </div>
                    </div>

                    {/* How to use */}
                    <div className="ts-section-title">How to Use in TradeWave</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '14px' }}>
                        {[
                            { num: '1', text: 'Look at the PE label in the opportunity table controls. It shows the current cycle phase (e.g., PE+2 in 2026).' },
                            { num: '2', text: 'Check the box to switch the entire analysis to that cycle phase. The table, bar chart, and all stats update.' },
                        ].map((s, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 0' }}>
                                <div style={{
                                    width: '22px', height: '22px', borderRadius: '50%',
                                    background: dark ? 'rgba(167,139,250,0.15)' : 'rgba(167,139,250,0.1)',
                                    border: `1px solid ${accentPurple}40`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontSize: '11px', fontWeight: 800, color: accentPurple, flexShrink: 0,
                                }}>{s.num}</div>
                                <div style={{ fontSize: '11px', lineHeight: 1.4 }}>{s.text}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        Historical averages are based on S&P 500 data spanning multiple decades. Individual securities
                        may behave differently. The presidential cycle is a statistical tendency, not a rule.
                        Past patterns do not guarantee future results.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default PECyclePopup
