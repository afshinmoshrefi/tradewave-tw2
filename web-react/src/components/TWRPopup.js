import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const TWRPopup = ({ onClose, iconRect }) => {
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
    const rowEven = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'

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

    const ranges = [
        { range: 'Above 2.0', label: 'Excellent, very consistent favorable movement', color: accentGreen },
        { range: '1.0 - 2.0', label: 'Good, solid peak-profit consistency', color: '#4ade80' },
        { range: '0.5 - 1.0', label: 'Moderate, peaks are less reliable', color: accentAmber },
        { range: 'Below 0.5', label: 'Weak, no consistent favorable excursion', color: accentRed },
    ]

    // Trade journey data for SVG visuals
    const tradeJourneys = [
        {
            label: 'Trade A',
            subtitle: 'SR High, TWR High',
            color: accentGreen,
            path: 'M 10,55 C 25,50 45,35 60,25 L 80,18',
            exitY: 18,
            exitLabel: '+8%',
        },
        {
            label: 'Trade B',
            subtitle: 'SR Low, TWR High',
            color: accentAmber,
            path: 'M 10,55 C 20,45 35,15 50,10 C 60,12 70,40 80,48',
            exitY: 48,
            exitLabel: '+3%',
            peakY: 10,
        },
        {
            label: 'Trade C',
            subtitle: 'SR Low, TWR Low',
            color: accentRed,
            path: 'M 10,55 C 18,35 25,60 35,30 C 42,50 55,65 65,40 C 72,50 78,52 80,53',
            exitY: 53,
            exitLabel: '+1%',
        },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>TradeWave Ratio (TWR)</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.06)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            What if the Sharpe Ratio could see the best moment of each trade, not just the end?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            TWR does exactly that. It measures consistency using the peak profit (MFE) instead of the final return.
                        </div>
                    </div>

                    {/* Sharpe vs TWR */}
                    <div className="ts-section-title">Sharpe vs TWR</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderTop: `3px solid ${accentAmber}`, padding: '14px' }}>
                            <div style={{ fontSize: '13px', fontWeight: 800, color: accentAmber, marginBottom: '8px', textAlign: 'center' }}>Sharpe Ratio</div>
                            <div style={{ background: dark ? 'rgba(245,158,11,0.1)' : 'rgba(245,158,11,0.06)', borderRadius: '6px', padding: '8px', textAlign: 'center', marginBottom: '8px' }}>
                                <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '2px' }}>FORMULA</div>
                                <div style={{ fontSize: '12px', fontWeight: 700 }}>
                                    <span style={{ color: accentAmber }}>Average Return</span>
                                    <span style={{ opacity: 0.5 }}> / </span>
                                    <span>Std Dev of Returns</span>
                                </div>
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Measures consistency of the final result. A trade that gains 10% then gives back to +2% scores low.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderTop: `3px solid ${accentBlue}`, padding: '14px' }}>
                            <div style={{ fontSize: '13px', fontWeight: 800, color: accentBlue, marginBottom: '8px', textAlign: 'center' }}>TWR</div>
                            <div style={{ background: dark ? 'rgba(59,130,246,0.1)' : 'rgba(59,130,246,0.06)', borderRadius: '6px', padding: '8px', textAlign: 'center', marginBottom: '8px' }}>
                                <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '2px' }}>FORMULA</div>
                                <div style={{ fontSize: '12px', fontWeight: 700 }}>
                                    <span style={{ color: accentBlue }}>Average MFE</span>
                                    <span style={{ opacity: 0.5 }}> / </span>
                                    <span>Std Dev of MFE</span>
                                </div>
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Measures consistency of the best point reached. That same trade that hit +10% before pulling back scores high.
                            </div>
                        </div>
                    </div>

                    {/* SVG Trade Journeys */}
                    <div className="ts-section-title">Three Trade Journeys Compared</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                        {tradeJourneys.map((tj, i) => (
                            <div key={i} style={{ ...cardStyle, flex: 1, marginBottom: 0, textAlign: 'center', padding: '10px 8px' }}>
                                <div style={{ fontSize: '11px', fontWeight: 700, marginBottom: '2px' }}>{tj.label}</div>
                                <div style={{ fontSize: '9px', color: tj.color, fontWeight: 600, marginBottom: '6px' }}>{tj.subtitle}</div>
                                <svg width="100%" height="70" viewBox="0 0 90 70">
                                    {/* Zero/entry line */}
                                    <line x1="5" y1="55" x2="85" y2="55" stroke={mutedText} strokeWidth="0.5" strokeOpacity="0.3" />
                                    {/* Entry dot */}
                                    <circle cx="10" cy="55" r="2.5" fill={mutedText} fillOpacity="0.5" />
                                    {/* Path */}
                                    <path d={tj.path} fill="none" stroke={tj.color} strokeWidth="2" strokeLinecap="round" />
                                    {/* Exit dot */}
                                    <circle cx="80" cy={tj.exitY} r="2.5" fill={tj.color} />
                                    {/* Exit label */}
                                    <text x="80" y={tj.exitY - 6} textAnchor="middle" fontSize="8" fontWeight="700" fill={tj.color}>{tj.exitLabel}</text>
                                    {/* Labels */}
                                    <text x="10" y="67" textAnchor="middle" fontSize="7" fill={mutedText}>Entry</text>
                                    <text x="80" y="67" textAnchor="middle" fontSize="7" fill={mutedText}>Exit</text>
                                </svg>
                            </div>
                        ))}
                    </div>

                    {/* When TWR > SR */}
                    <div className="ts-section-title">When TWR is Greater Than SR</div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, padding: '14px 16px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                            When TWR is much higher than SR, it means the price consistently makes a strong move in your favor
                            during the trade window, even if the final return is modest. These patterns are excellent for shorter
                            holding periods. Enter the trade, capture the favorable move early, and exit before the pullback.
                        </div>
                    </div>

                    {/* How to Read the Numbers */}
                    <div className="ts-section-title">How to Read the Numbers</div>
                    <table className="ts-range-table">
                        <thead>
                            <tr>
                                <th style={{ color: textColor }}>TWR Value</th>
                                <th style={{ color: textColor }}>What It Means</th>
                            </tr>
                        </thead>
                        <tbody>
                            {ranges.map((r, i) => (
                                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? rowEven : 'transparent' }}>
                                    <td><span style={{ color: r.color, fontWeight: 600 }}>{r.range}</span></td>
                                    <td>{r.label}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {/* Using TWR in Practice */}
                    <div className="ts-section-title">Using TWR in Practice</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {[
                            { step: '1', color: accentBlue, text: 'Sort the opportunity table by TWR to find patterns with consistent favorable movement.' },
                            { step: '2', color: accentPurple, text: 'Compare TWR to SR. A large gap means shorter-duration trading may capture more.' },
                            { step: '3', color: accentGreen, text: 'Look at MFE bars on the bar chart to see when the favorable move typically happens.' },
                        ].map((item, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 14px' }}>
                                <div style={{
                                    width: '28px', height: '28px', borderRadius: '50%', flexShrink: 0,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    background: dark ? `${item.color}20` : `${item.color}15`,
                                    border: `1.5px solid ${item.color}`,
                                    fontSize: '13px', fontWeight: 800, color: item.color,
                                }}>{item.step}</div>
                                <div style={{ fontSize: '12px', lineHeight: 1.5, opacity: 0.85 }}>{item.text}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        TWR is a TradeWave-specific metric. It complements the standard Sharpe Ratio by focusing on
                        intra-trade peak performance rather than final outcomes. Use both together for a complete picture
                        of pattern quality.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default TWRPopup
