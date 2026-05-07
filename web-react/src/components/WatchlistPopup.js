import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const WatchlistPopup = ({ onClose, iconRect }) => {
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

    const stepCircle = (num, color) => ({
        width: '24px', height: '24px', borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: dark ? `${color}20` : `${color}15`,
        border: `1.5px solid ${color}`,
        fontSize: '12px', fontWeight: 800, color: color,
    })

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Watchlists</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero card */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.06)', border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            Track the stocks you care about in one place.
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            Watchlists let you create named groups of ticker symbols for quick access and focused analysis.
                        </div>
                    </div>

                    {/* Creating a Watchlist */}
                    <div className="ts-section-title">Creating a Watchlist</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
                        {[
                            { step: '1', text: 'Click the watchlist icon in the top control bar.' },
                            { step: '2', text: "Type a name for your watchlist (e.g., 'My Tech Stocks')." },
                            { step: '3', text: "Select the Securities Group these stocks belong to (e.g., S&P 500 Stocks)." },
                            { step: '4', text: 'Click Add to create the watchlist.' },
                        ].map((item, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px' }}>
                                <div style={stepCircle(item.step, accentBlue)}>{item.step}</div>
                                <div style={{ fontSize: '12px', lineHeight: 1.5, opacity: 0.85 }}>{item.text}</div>
                            </div>
                        ))}
                    </div>

                    {/* Adding Symbols */}
                    <div className="ts-section-title">Adding Symbols</div>
                    <div style={{ ...cardStyle, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                            Type a ticker symbol into the input field and click <strong>Add Symbol</strong> to add it to your watchlist.
                            You can add symbols one at a time, or use <strong>CSV Import</strong> for bulk adding.
                        </div>
                    </div>

                    {/* CSV Import */}
                    <div style={{ ...cardStyle, borderLeft: `3px solid ${accentBlue}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', fontWeight: 700, color: accentBlue, marginBottom: '4px' }}>CSV Import</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.6, opacity: 0.8 }}>
                            Click "Import CSV" to bulk-import symbols from a file. The system auto-detects which Securities Group
                            the symbols belong to. A preview shows how many symbols were recognized before you confirm.
                        </div>
                    </div>

                    {/* SVG Flowchart Visual */}
                    <div style={{ ...cardStyle, padding: '14px 16px', textAlign: 'center' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '8px', opacity: 0.7 }}>How Watchlists Connect</div>
                        <svg width="100%" height="140" viewBox="0 0 420 140" style={{ maxWidth: '420px' }}>
                            {/* Your Symbols box */}
                            <rect x="10" y="35" width="100" height="70" rx="8" fill={dark ? 'rgba(59,130,246,0.12)' : 'rgba(59,130,246,0.08)'} stroke={accentBlue} strokeWidth="1.5" />
                            <text x="60" y="52" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentBlue}>Your Symbols</text>
                            <text x="60" y="68" textAnchor="middle" fontSize="10" fontWeight="600" fill={textColor} fillOpacity="0.7">AAPL</text>
                            <text x="60" y="80" textAnchor="middle" fontSize="10" fontWeight="600" fill={textColor} fillOpacity="0.7">MSFT</text>
                            <text x="60" y="92" textAnchor="middle" fontSize="10" fontWeight="600" fill={textColor} fillOpacity="0.7">TSLA</text>

                            {/* Arrow 1 */}
                            <line x1="115" y1="70" x2="155" y2="70" stroke={mutedText} strokeWidth="1.5" />
                            <polygon points="155,65 165,70 155,75" fill={mutedText} />

                            {/* Watchlist box */}
                            <rect x="170" y="42" width="100" height="56" rx="8" fill={dark ? 'rgba(34,197,94,0.12)' : 'rgba(34,197,94,0.08)'} stroke={accentGreen} strokeWidth="1.5" />
                            <text x="220" y="60" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentGreen}>Watchlist</text>
                            <text x="220" y="78" textAnchor="middle" fontSize="11" fontWeight="600" fill={textColor} fillOpacity="0.8">"Tech Picks"</text>

                            {/* Arrow to Quick Pick */}
                            <line x1="275" y1="58" x2="315" y2="40" stroke={mutedText} strokeWidth="1.5" />
                            <polygon points="312,35 322,38 315,44" fill={mutedText} />

                            {/* Arrow to Securities Filter */}
                            <line x1="275" y1="82" x2="315" y2="100" stroke={mutedText} strokeWidth="1.5" />
                            <polygon points="315,96 322,102 312,105" fill={mutedText} />

                            {/* Quick Pick Dropdown box */}
                            <rect x="325" y="15" width="90" height="40" rx="6" fill={dark ? 'rgba(167,139,250,0.12)' : 'rgba(167,139,250,0.08)'} stroke={accentPurple} strokeWidth="1.5" />
                            <text x="370" y="33" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentPurple}>Quick Pick</text>
                            <text x="370" y="46" textAnchor="middle" fontSize="8" fill={mutedText}>Dropdown</text>

                            {/* Securities Filter box */}
                            <rect x="325" y="85" width="90" height="40" rx="6" fill={dark ? 'rgba(245,158,11,0.12)' : 'rgba(245,158,11,0.08)'} stroke={accentAmber} strokeWidth="1.5" />
                            <text x="370" y="103" textAnchor="middle" fontSize="9" fontWeight="700" fill={accentAmber}>Securities</text>
                            <text x="370" y="116" textAnchor="middle" fontSize="8" fill={mutedText}>Filter</text>
                        </svg>
                    </div>

                    {/* Watchlist as Securities Filter */}
                    <div className="ts-section-title">Watchlist as Securities Filter</div>
                    <div style={{ ...cardStyle, padding: '12px 14px' }}>
                        <div style={{ fontSize: '12px', lineHeight: 1.6, marginBottom: '8px' }}>
                            Check <strong>"Add to Securities List"</strong> in watchlist settings to make your watchlist appear
                            in the Securities Group dropdown. When selected, the opportunity table shows only patterns for stocks
                            in your watchlist, not the entire market group.
                        </div>
                    </div>
                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '12px 14px' }}>
                        <div style={{ fontSize: '11px', fontWeight: 600, color: accentPurple, marginBottom: '4px' }}>Example</div>
                        <div style={{ fontSize: '11px', lineHeight: 1.6, opacity: 0.8 }}>
                            You create a watchlist of 30 stocks from the S&P 500. Adding it to the Securities List lets you
                            select it from the top-right dropdown. Now the opportunity table shows only seasonal patterns for
                            your 30 stocks instead of all 500.
                        </div>
                    </div>

                    {/* Quick Pick vs Securities Filter */}
                    <div className="ts-section-title">Quick Pick vs Securities Filter</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderTop: `3px solid ${accentPurple}`, padding: '14px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 800, color: accentPurple, marginBottom: '6px', textAlign: 'center' }}>Default Watchlist (Quick Pick)</div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Sets which symbols appear as quick-pick options below the symbol input in the wave viewer.
                                Makes it easy to jump between your stocks.
                            </div>
                        </div>
                        <div style={{ ...cardStyle, flex: 1, marginBottom: 0, borderTop: `3px solid ${accentAmber}`, padding: '14px' }}>
                            <div style={{ fontSize: '12px', fontWeight: 800, color: accentAmber, marginBottom: '6px', textAlign: 'center' }}>Securities Filter</div>
                            <div style={{ fontSize: '11px', opacity: 0.75, lineHeight: 1.5 }}>
                                Filters the entire opportunity table to show only patterns for your watchlist symbols.
                                A much deeper integration.
                            </div>
                        </div>
                    </div>

                    {/* Free vs Paid */}
                    <div style={{ ...cardStyle, padding: '10px 14px' }}>
                        <div style={{ fontSize: '11px', lineHeight: 1.5, opacity: 0.75 }}>
                            <strong>Free vs Paid:</strong> Free users can create a limited number of watchlists.
                            Paid subscribers have higher limits.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        Watchlists are saved to your account and persist across sessions. You can edit, rename,
                        or delete watchlists at any time from the watchlist panel.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default WatchlistPopup
