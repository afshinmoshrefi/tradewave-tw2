import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const BarChartPopup = ({ onClose, iconRect }) => {
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

    const demoBars = [
        { yr: '2016', pct: 8.2, win: true },
        { yr: '2017', pct: 12.1, win: true },
        { yr: '2018', pct: -3.4, win: false },
        { yr: '2019', pct: 6.7, win: true },
        { yr: '2020', pct: 14.5, win: true },
        { yr: '2021', pct: 9.3, win: true },
        { yr: '2022', pct: -1.8, win: false },
        { yr: '2023', pct: 7.9, win: true },
    ]
    const maxBar = Math.max(...demoBars.map(b => Math.abs(b.pct)))

    // MFE/MAE demo data for the 3-bar illustration
    const mfeMaeBars = [
        { yr: '2021', pct: 9.3, mfe: 14.1, mae: -2.5, win: true },
        { yr: '2022', pct: -1.8, mfe: 3.2, mae: -6.1, win: false },
        { yr: '2023', pct: 7.9, mfe: 11.5, mae: -1.2, win: true },
    ]
    const mfeMax = Math.max(...mfeMaeBars.map(b => Math.max(Math.abs(b.pct), b.mfe, Math.abs(b.mae))))

    const cardStyle = {
        background: cardBg,
        border: `1px solid ${cardBorder}`,
        borderRadius: '8px',
        padding: '12px',
        marginBottom: '10px',
    }

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>The Year-by-Year Bar Chart</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.06)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            What did the price do in each historical window?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            Each bar shows the underlying price return for one historical year. The loaded
                            Long or Short direction determines whether that move made the trade profitable.
                        </div>
                    </div>

                    {/* Reading the Bars */}
                    <div className="ts-section-title">Reading the Bars</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        Green/up bars mean the underlying price rose. Red/down bars mean it fell. Green is
                        profitable for a Long; red is profitable for a Short. Bar height reflects the raw
                        price-return magnitude for that year's holding window.
                    </p>

                    {/* SVG bar chart visual */}
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <svg width="100%" height="160" viewBox="0 0 400 160" style={{ maxWidth: '400px', display: 'block', margin: '0 auto' }}>
                            {/* Zero line */}
                            <line x1="30" y1="95" x2="390" y2="95" stroke={mutedText} strokeWidth="1" strokeOpacity="0.4" />
                            <text x="22" y="98" textAnchor="end" fontSize="9" fill={mutedText}>0%</text>

                            {demoBars.map((b, i) => {
                                const barW = 36
                                const gap = 8
                                const x = 38 + i * (barW + gap)
                                const scale = 70 / maxBar
                                const barH = Math.abs(b.pct) * scale
                                const y = b.win ? 95 - barH : 95
                                const color = b.win ? accentGreen : accentRed
                                return (
                                    <g key={i}>
                                        <rect x={x} y={y} width={barW} height={barH} rx="3" fill={color} opacity="0.85" />
                                        <text x={x + barW / 2} y={b.win ? y - 4 : y + barH + 11} textAnchor="middle" fontSize="9" fontWeight="600" fill={color}>
                                            {b.win ? '+' : ''}{b.pct}%
                                        </text>
                                        <text x={x + barW / 2} y="150" textAnchor="middle" fontSize="9" fill={mutedText}>
                                            {b.yr}
                                        </text>
                                    </g>
                                )
                            })}

                            {/* Labels */}
                            <text x="395" y="78" textAnchor="end" fontSize="9" fill={accentGreen} fontWeight="600">Price up</text>
                            <text x="395" y="118" textAnchor="end" fontSize="9" fill={accentRed} fontWeight="600">Price down</text>
                        </svg>

                        <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px', fontSize: '10px' }}>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', backgroundColor: accentGreen, borderRadius: '2px', marginRight: '4px' }} />Green = price rose</span>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', backgroundColor: accentRed, borderRadius: '2px', marginRight: '4px' }} />Red = price fell</span>
                            <span style={{ opacity: 0.6 }}>Bar height = percent return</span>
                        </div>
                    </div>

                    {/* MFE and MAE Overlays */}
                    <div className="ts-section-title">MFE and MAE Overlays</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        Beyond the final return, the bar chart can show two important intra-trade markers
                        that reveal what happened during the holding window.
                    </p>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        <div style={{ ...cardStyle, marginBottom: 0, borderLeft: `3px solid ${accentGreen}`, padding: '10px 12px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentGreen, marginBottom: '3px' }}>MFE (Max Favorable Excursion)</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                The highest point the price reached in your favor during the holding window.
                                Like a "best moment" marker. Shown as an upward triangle above or near each bar.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, marginBottom: 0, borderLeft: `3px solid ${accentRed}`, padding: '10px 12px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentRed, marginBottom: '3px' }}>MAE (Max Adverse Excursion)</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                The deepest the price went against you during the holding window.
                                Like a "worst moment" marker. Shown as a downward triangle below bars.
                            </div>
                        </div>
                    </div>

                    {/* MFE/MAE SVG illustration */}
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        <svg width="100%" height="150" viewBox="0 0 300 150" style={{ maxWidth: '300px', display: 'block', margin: '0 auto' }}>
                            {/* Zero line */}
                            <line x1="20" y1="80" x2="280" y2="80" stroke={mutedText} strokeWidth="1" strokeOpacity="0.4" />
                            <text x="14" y="83" textAnchor="end" fontSize="8" fill={mutedText}>0%</text>

                            {mfeMaeBars.map((b, i) => {
                                const barW = 50
                                const gap = 25
                                const x = 40 + i * (barW + gap)
                                const scale = 55 / mfeMax
                                const barH = Math.abs(b.pct) * scale
                                const y = b.win ? 80 - barH : 80
                                const color = b.win ? accentGreen : accentRed

                                // MFE triangle position (above zero line)
                                const mfeY = 80 - b.mfe * scale
                                // MAE triangle position (below zero line)
                                const maeY = 80 + Math.abs(b.mae) * scale

                                return (
                                    <g key={i}>
                                        <rect x={x} y={y} width={barW} height={barH} rx="3" fill={color} opacity="0.75" />

                                        {/* MFE marker - upward triangle */}
                                        <polygon
                                            points={`${x + barW / 2 - 5},${mfeY + 4} ${x + barW / 2 + 5},${mfeY + 4} ${x + barW / 2},${mfeY - 4}`}
                                            fill={accentBlue}
                                        />
                                        <text x={x + barW + 4} y={mfeY + 3} fontSize="8" fill={accentBlue} fontWeight="600">
                                            +{b.mfe}%
                                        </text>

                                        {/* MAE marker - downward triangle */}
                                        <polygon
                                            points={`${x + barW / 2 - 5},${maeY - 4} ${x + barW / 2 + 5},${maeY - 4} ${x + barW / 2},${maeY + 4}`}
                                            fill={accentAmber}
                                        />
                                        <text x={x + barW + 4} y={maeY + 3} fontSize="8" fill={accentAmber} fontWeight="600">
                                            {b.mae}%
                                        </text>

                                        {/* Year label */}
                                        <text x={x + barW / 2} y="140" textAnchor="middle" fontSize="9" fill={mutedText}>{b.yr}</text>
                                    </g>
                                )
                            })}

                            {/* Legend */}
                            <polygon points="25,112 31,112 28,106" fill={accentBlue} />
                            <text x="34" y="113" fontSize="8" fill={accentBlue} fontWeight="600">MFE</text>
                            <polygon points="70,106 76,106 73,112" fill={accentAmber} />
                            <text x="79" y="113" fontSize="8" fill={accentAmber} fontWeight="600">MAE</text>
                        </svg>
                        <div style={{ textAlign: 'center', fontSize: '10px', opacity: 0.6, marginTop: '4px' }}>
                            Triangles mark the best and worst points reached during each year's holding window
                        </div>
                    </div>

                    {/* What to Look For */}
                    <div className="ts-section-title">What to Look For</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        <div style={{ ...cardStyle, marginBottom: 0, borderTop: `3px solid ${accentGreen}`, textAlign: 'center', padding: '10px 10px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentGreen, marginBottom: '4px' }}>Match the Direction</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Long wins are green/up. Short wins are red/down. Confirm the exact record with % Profitable.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, marginBottom: 0, borderTop: `3px solid ${accentBlue}`, textAlign: 'center', padding: '10px 10px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentBlue, marginBottom: '4px' }}>Consistent Heights</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Bars of similar height mean steady returns, not one lucky year carrying the average.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, marginBottom: 0, borderTop: `3px solid ${accentAmber}`, textAlign: 'center', padding: '10px 10px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentAmber, marginBottom: '4px' }}>Contained Losses</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Losing years should be small: red/down for Longs, green/up for Shorts.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, marginBottom: 0, borderTop: `3px solid ${accentPurple}`, textAlign: 'center', padding: '10px 10px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: accentPurple, marginBottom: '4px' }}>MFE vs Return</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                If MFE is much higher than the final bar, the price moved in your favor early then pulled back. A shorter holding period might capture more.
                            </div>
                        </div>
                    </div>

                    {/* Clicking a Year Bar */}
                    <div className="ts-section-title">Clicking a Year Bar</div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, padding: '12px 14px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <svg width="40" height="40" viewBox="0 0 40 40" style={{ flexShrink: 0 }}>
                            <rect x="4" y="8" width="32" height="24" rx="3" fill="none" stroke={accentBlue} strokeWidth="1.5" />
                            <polyline points="8,26 14,18 20,22 26,14 32,16" fill="none" stroke={accentGreen} strokeWidth="1.5" />
                            <polygon points="12,14 14,10 16,14" fill={accentAmber} />
                            <polygon points="28,24 30,28 26,28" fill={accentRed} />
                        </svg>
                        <div>
                            <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '3px' }}>Open the Historical Price Chart</div>
                            <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>
                                Click any bar to open the historical price chart for that specific year. Entry and exit
                                points are marked with arrows so you can see exactly how the trade would have played out.
                            </div>
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        The bar chart reflects historical data for the selected seasonal window. Past performance
                        does not guarantee future results. Use the bar chart alongside other analysis tools
                        to evaluate the quality and consistency of a seasonal pattern.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default BarChartPopup
