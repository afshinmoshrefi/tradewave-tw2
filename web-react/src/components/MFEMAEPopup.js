import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const MFEMAEPopup = ({ onClose, iconRect }) => {
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

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>MFE and MAE</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(34,197,94,0.08)' : 'rgba(34,197,94,0.06)', border: `1px solid ${dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            How far did the price move in your favor, and how far did it move against you?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            MFE and MAE go beyond the final return to show the full journey of each trade.
                        </div>
                    </div>

                    {/* The Basics */}
                    <div className="ts-section-title">The Basics</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderLeft: `3px solid ${accentGreen}`, padding: '12px 14px' }}>
                            <div style={{ fontSize: '13px', fontWeight: 800, color: accentGreen, marginBottom: '4px' }}>MFE</div>
                            <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '6px' }}>Maximum Favorable Excursion</div>
                            <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                                The best price reached in your favor during the holding window. Think of it as the peak profit opportunity before the trade closed.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderLeft: `3px solid ${accentRed}`, padding: '12px 14px' }}>
                            <div style={{ fontSize: '13px', fontWeight: 800, color: accentRed, marginBottom: '4px' }}>MAE</div>
                            <div style={{ fontSize: '10px', fontWeight: 600, color: mutedText, marginBottom: '6px' }}>Maximum Adverse Excursion</div>
                            <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.8 }}>
                                The worst price moved against you during the holding window. Think of it as the deepest drawdown you would have experienced.
                            </div>
                        </div>
                    </div>

                    {/* SVG Price Path Visual */}
                    <div style={{ ...cardStyle, padding: '14px 16px', textAlign: 'center' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '8px', opacity: 0.7 }}>Price Journey During One Trade Period</div>
                        <svg width="100%" height="180" viewBox="0 0 440 180" style={{ maxWidth: '440px' }}>
                            {/* Grid lines */}
                            {[40, 70, 100, 130, 160].map((y, i) => (
                                <line key={i} x1="50" y1={y} x2="400" y2={y} stroke={mutedText} strokeWidth="0.5" strokeOpacity="0.2" />
                            ))}

                            {/* Entry dashed line */}
                            <line x1="70" y1="25" x2="70" y2="170" stroke={mutedText} strokeWidth="1" strokeDasharray="4,3" strokeOpacity="0.5" />
                            <text x="70" y="18" textAnchor="middle" fontSize="9" fontWeight="600" fill={mutedText}>Entry</text>

                            {/* Exit dashed line */}
                            <line x1="380" y1="25" x2="380" y2="170" stroke={mutedText} strokeWidth="1" strokeDasharray="4,3" strokeOpacity="0.5" />
                            <text x="380" y="18" textAnchor="middle" fontSize="9" fontWeight="600" fill={mutedText}>Exit</text>

                            {/* Price path: entry at 100, rises to peak ~50 (MFE), dips to ~140 (MAE), ends at ~75 */}
                            <path
                                d="M 70,110 C 110,105 140,65 190,50 C 230,38 260,55 290,80 C 310,95 330,135 340,140 C 355,145 365,90 380,80"
                                fill="none"
                                stroke={accentBlue}
                                strokeWidth="2.5"
                                strokeLinecap="round"
                            />

                            {/* MFE peak dotted line */}
                            <line x1="50" y1="38" x2="400" y2="38" stroke={accentGreen} strokeWidth="1" strokeDasharray="3,3" strokeOpacity="0.6" />
                            {/* MFE label */}
                            <rect x="165" y="26" width="72" height="16" rx="3" fill={dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.12)'} />
                            <text x="201" y="37" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentGreen}>MFE +12%</text>
                            {/* MFE dot */}
                            <circle cx="190" cy="50" r="4" fill={accentGreen} />

                            {/* MAE trough dotted line */}
                            <line x1="50" y1="140" x2="400" y2="140" stroke={accentRed} strokeWidth="1" strokeDasharray="3,3" strokeOpacity="0.6" />
                            {/* MAE label */}
                            <rect x="310" y="148" width="64" height="16" rx="3" fill={dark ? 'rgba(239,68,68,0.2)' : 'rgba(239,68,68,0.12)'} />
                            <text x="342" y="159" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentRed}>MAE -4%</text>
                            {/* MAE dot */}
                            <circle cx="340" cy="140" r="4" fill={accentRed} />

                            {/* Entry level line */}
                            <line x1="50" y1="110" x2="400" y2="110" stroke={mutedText} strokeWidth="0.5" strokeDasharray="2,4" strokeOpacity="0.3" />
                            <text x="48" y="113" textAnchor="end" fontSize="8" fill={mutedText}>Entry Price</text>

                            {/* Exit point */}
                            <circle cx="380" cy="80" r="4" fill={accentBlue} />
                            <rect x="385" y="72" width="50" height="16" rx="3" fill={dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'} />
                            <text x="410" y="83" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentBlue}>Final +7%</text>

                            {/* Entry point */}
                            <circle cx="70" cy="110" r="4" fill={textColor} fillOpacity="0.6" />
                        </svg>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '4px', fontSize: '10px' }}>
                            <span><span style={{ display: 'inline-block', width: '16px', height: '2px', backgroundColor: accentBlue, borderRadius: '1px', marginRight: '4px', verticalAlign: 'middle' }} />Price path</span>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: accentGreen, marginRight: '4px', verticalAlign: 'middle' }} />MFE peak</span>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: accentRed, marginRight: '4px', verticalAlign: 'middle' }} />MAE trough</span>
                        </div>
                    </div>

                    {/* Why This Matters */}
                    <div className="ts-section-title">Why This Matters</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {[
                            { title: 'Better Exit Timing', color: accentGreen, text: 'If MFE is consistently much higher than the final return, the trade often peaks early then gives back gains. You could exit earlier to capture more profit.' },
                            { title: 'Risk Management', color: accentAmber, text: 'MAE shows the worst drawdown you should expect. If a pattern has MAE of -8% across most years, set your stop-loss below that level.' },
                            { title: 'Pattern Quality', color: accentPurple, text: 'A pattern with high MFE and low MAE moves strongly in your favor with little pullback. That is an ideal trade profile.' },
                        ].map((item, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px' }}>
                                <div style={{ width: '4px', alignSelf: 'stretch', borderRadius: '2px', backgroundColor: item.color, flexShrink: 0 }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '12px', fontWeight: 700, marginBottom: '3px' }}>{item.title}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>{item.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Reading MFE/MAE on the Bar Chart */}
                    <div className="ts-section-title">Reading MFE/MAE on the Bar Chart</div>
                    <div style={{ ...cardStyle, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                            The year-by-year bar chart in the wave viewer can display MFE and MAE as overlays on each bar.
                            To enable them, use the <strong>MFE</strong> and <strong>MAE</strong> checkboxes in the wave viewer header.
                            When enabled, you will see markers on each year's bar showing the peak favorable move and the deepest adverse
                            move for that year. This lets you visually compare the intra-trade journey across all years at a glance.
                        </div>
                    </div>

                    {/* MFE Filter in the Opportunity Table */}
                    <div className="ts-section-title">MFE Filter in the Opportunity Table</div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                            The bottom bar includes an MFE threshold filter. When you set a minimum MFE value,
                            only patterns where <strong>every single year</strong> reached at least that MFE level will appear.
                            This is not an average. It is a per-year guarantee. If you set MFE to 2%, then every year in
                            the pattern must have hit at least +2% in favorable movement during the holding window.
                        </div>
                    </div>

                    {/* TWR Connection */}
                    <div className="ts-section-title">TradeWave Ratio (TWR) Connection</div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                            The TradeWave Ratio (TWR) uses MFE instead of the final return in its Sharpe-style calculation.
                            While the standard Sharpe Ratio measures the consistency of start-to-end returns, TWR measures
                            the consistency of the best point reached during each trade. Patterns with a high TWR
                            consistently make a strong favorable move, even if they give some back before the exit date.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        MFE and MAE are calculated from historical intraday highs and lows during each pattern's holding window.
                        Past price behavior does not guarantee future results. Use MFE and MAE as tools to refine your
                        entry, exit, and risk management decisions.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default MFEMAEPopup
