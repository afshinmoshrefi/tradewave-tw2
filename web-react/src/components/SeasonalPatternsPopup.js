import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const SeasonalPatternsPopup = ({ onClose, iconRect }) => {
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
    const cardBg = dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)'
    const cardBorder = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)'
    const accentGreen = '#22c55e'
    const accentRed = '#ef4444'
    const accentBlue = '#3b82f6'
    const accentAmber = '#f59e0b'
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

    // Mini bar chart data for the visual
    const demoBars = [
        { yr: '2016', pct: 8.2, win: true },
        { yr: '2017', pct: 12.1, win: true },
        { yr: '2018', pct: -3.4, win: false },
        { yr: '2019', pct: 6.7, win: true },
        { yr: '2020', pct: 14.5, win: true },
        { yr: '2021', pct: 9.3, win: true },
        { yr: '2022', pct: -1.8, win: false },
        { yr: '2023', pct: 7.9, win: true },
        { yr: '2024', pct: 11.2, win: true },
        { yr: '2025', pct: 5.6, win: true },
    ]
    const maxBar = Math.max(...demoBars.map(b => Math.abs(b.pct)))

    // Election cycle phases
    const pePhases = [
        { label: 'PE', year: 'Election', color: accentBlue, avg: '6.0%', desc: 'Moderate returns, campaign uncertainty' },
        { label: 'PE+1', year: 'Post-Election', color: accentAmber, avg: '3.0%', desc: 'Weakest - new policies, reforms' },
        { label: 'PE+2', year: 'Midterm', color: '#a78bfa', avg: '4.0%', desc: 'Volatile, often bottoms mid-year' },
        { label: 'PE+3', year: 'Pre-Election', color: accentGreen, avg: '14.2%', desc: 'Strongest - growth-friendly push' },
    ]

    // Driver cards
    const drivers = [
        { icon: '📊', title: 'Earnings Cycles', text: 'Quarterly reports create predictable waves of buying and selling' },
        { icon: '📋', title: 'Tax-Driven Flows', text: 'Year-end tax-loss selling followed by January reinvestment' },
        { icon: '🏭', title: 'Industry Rhythms', text: 'Retail, energy, agriculture follow their own seasonal demand' },
        { icon: '🏦', title: 'Institutional Moves', text: 'Quarter-end rebalancing, summer de-risking, year-end window dressing' },
        { icon: '🧠', title: 'Human Psychology', text: 'New-year optimism, summer lull, risk appetite cycles' },
    ]

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
                    <h2 style={{ color: textColor }}>Seasonal Patterns</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    {/* Hero concept */}
                    <div style={{ ...cardStyle, background: dark ? 'rgba(34,197,94,0.08)' : 'rgba(34,197,94,0.06)', border: `1px solid ${dark ? 'rgba(34,197,94,0.2)' : 'rgba(34,197,94,0.15)'}`, textAlign: 'center', padding: '16px 20px' }}>
                        <div style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
                            What if a stock rises during the same calendar window year after year?
                        </div>
                        <div style={{ fontSize: '12px', opacity: 0.75 }}>
                            Seasonal patterns are recurring price moves tied to specific dates, backed by decades of historical data.
                            They are not predictions - they are observations of what has consistently happened in the past.
                        </div>
                    </div>

                    {/* Calendar timeline visual */}
                    <div className="ts-section-title">A Pattern in Action</div>
                    <p style={{ fontSize: '12px', marginBottom: '8px' }}>
                        Imagine a stock that tends to rise every year between March 5 and April 20.
                        Here is what 10 years of data might look like:
                    </p>

                    {/* Mini bar chart */}
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        {/* Upper half: green bars grow upward from zero line */}
                        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', height: '50px', marginBottom: '0' }}>
                            {demoBars.map((b, i) => {
                                const h = b.win ? (b.pct / maxBar) * 45 : 0
                                return (
                                    <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, justifyContent: 'flex-end', height: '100%' }}>
                                        {b.win && <div style={{ fontSize: '9px', marginBottom: '2px', color: accentGreen, fontWeight: 600 }}>
                                            +{b.pct}%
                                        </div>}
                                        <div style={{
                                            width: '70%',
                                            height: `${h}px`,
                                            backgroundColor: b.win ? accentGreen : 'transparent',
                                            borderRadius: '3px 3px 0 0',
                                            opacity: 0.85,
                                        }} />
                                    </div>
                                )
                            })}
                        </div>
                        {/* Zero line */}
                        <div style={{ height: '1px', backgroundColor: mutedText, opacity: 0.4 }} />
                        {/* Lower half: red bars grow downward from zero line */}
                        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', height: '30px', marginBottom: '0' }}>
                            {demoBars.map((b, i) => {
                                const h = !b.win ? (Math.abs(b.pct) / maxBar) * 25 : 0
                                return (
                                    <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1, justifyContent: 'flex-start', height: '100%' }}>
                                        <div style={{
                                            width: '70%',
                                            height: `${h}px`,
                                            backgroundColor: !b.win ? accentRed : 'transparent',
                                            borderRadius: '0 0 3px 3px',
                                            opacity: 0.85,
                                        }} />
                                        {!b.win && <div style={{ fontSize: '9px', marginTop: '2px', color: accentRed, fontWeight: 600 }}>
                                            {b.pct}%
                                        </div>}
                                    </div>
                                )
                            })}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            {demoBars.map((b, i) => (
                                <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: '9px', color: mutedText }}>{b.yr}</div>
                            ))}
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px', fontSize: '10px' }}>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', backgroundColor: accentGreen, borderRadius: '2px', marginRight: '4px' }} />Profitable year</span>
                            <span><span style={{ display: 'inline-block', width: '8px', height: '8px', backgroundColor: accentRed, borderRadius: '2px', marginRight: '4px' }} />Loss year</span>
                        </div>
                        <div style={{ textAlign: 'center', fontSize: '11px', marginTop: '6px', fontWeight: 500 }}>
                            8 out of 10 years profitable - <span style={{ color: accentGreen }}>80% win rate</span>
                        </div>
                    </div>

                    {/* Why they exist */}
                    <div className="ts-section-title">Why Do Seasonal Patterns Exist?</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        {drivers.map((d, i) => (
                            <div key={i} style={{
                                ...cardStyle,
                                marginBottom: 0,
                                display: 'flex',
                                alignItems: 'flex-start',
                                gap: '8px',
                                ...(i === drivers.length - 1 ? { gridColumn: '1 / -1' } : {}),
                            }}>
                                <div style={{ fontSize: '18px', lineHeight: 1, flexShrink: 0, marginTop: '1px' }}>{d.icon}</div>
                                <div>
                                    <div style={{ fontSize: '11px', fontWeight: 700, marginBottom: '2px' }}>{d.title}</div>
                                    <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>{d.text}</div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Famous patterns - visual cards */}
                    <div className="ts-section-title">Well-Known Seasonal Effects</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '14px' }}>
                        {[
                            { name: 'Sell in May, Go Away', months: 'Nov–Apr', color: accentGreen, desc: 'Markets historically perform better November through April. This pattern dates back centuries.' },
                            { name: 'January Effect', months: 'January', color: accentBlue, desc: 'Small-cap stocks tend to rise in January as investors reinvest after year-end tax-loss selling.' },
                            { name: 'Santa Claus Rally', months: 'Late Dec – Early Jan', color: '#ef4444', desc: 'The last 5 trading days of December and first 2 of January are positive ~78% of the time since 1950.' },
                            { name: 'Pre-Election Rally', months: 'Year 3 of Presidency', color: '#a78bfa', desc: 'The third year of a presidential term averages roughly double the returns of other years.' },
                        ].map((p, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px' }}>
                                <div style={{
                                    width: '4px', alignSelf: 'stretch', borderRadius: '2px',
                                    backgroundColor: p.color, flexShrink: 0,
                                }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                                        <span style={{ fontSize: '12px', fontWeight: 700 }}>{p.name}</span>
                                        <span style={{ fontSize: '10px', color: p.color, fontWeight: 600, background: dark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)', padding: '1px 6px', borderRadius: '3px' }}>{p.months}</span>
                                    </div>
                                    <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.4 }}>{p.desc}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <p style={{ fontSize: '12px', fontStyle: 'italic', opacity: 0.65, marginBottom: '14px' }}>
                        These are just the famous ones. Every stock, ETF, and index has its own unique seasonal fingerprint -
                        specific calendar windows where it has historically moved with unusual consistency.
                    </p>

                    {/* How TradeWave works - scanning visual */}
                    <div className="ts-section-title">How TradeWave Finds Patterns</div>
                    <div style={{ ...cardStyle, textAlign: 'center', padding: '16px' }}>
                        {/* Scanning funnel visual */}
                        <svg width="100%" height="90" viewBox="0 0 400 90" style={{ maxWidth: '400px' }}>
                            {/* Many combinations */}
                            <rect x="20" y="5" width="360" height="22" rx="4" fill={dark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.1)'} stroke={accentBlue} strokeWidth="1" strokeOpacity="0.3" />
                            <text x="200" y="20" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentBlue}>Thousands of date + holding period combinations</text>

                            {/* Arrow */}
                            <polygon points="190,32 210,32 200,42" fill={mutedText} />

                            {/* Filter */}
                            <rect x="80" y="46" width="240" height="22" rx="4" fill={dark ? 'rgba(251,191,36,0.12)' : 'rgba(251,191,36,0.1)'} stroke={accentAmber} strokeWidth="1" strokeOpacity="0.3" />
                            <text x="200" y="61" textAnchor="middle" fontSize="10" fontWeight="600" fill={accentAmber}>Ranked by consistency (Sharpe Ratio)</text>

                            {/* Arrow */}
                            <polygon points="190,73 210,73 200,83" fill={mutedText} />
                        </svg>
                        <div style={{
                            display: 'inline-block',
                            background: dark ? 'rgba(34,197,94,0.12)' : 'rgba(34,197,94,0.08)',
                            border: `1px solid ${dark ? 'rgba(34,197,94,0.25)' : 'rgba(34,197,94,0.2)'}`,
                            borderRadius: '6px', padding: '6px 20px', marginTop: '0px',
                        }}>
                            <span style={{ fontSize: '11px', fontWeight: 700, color: accentGreen }}>Best patterns surface to the top</span>
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.6, marginTop: '8px' }}>
                            For every security, every possible start date and holding period is tested.
                        </div>
                    </div>

                    {/* Adjustable years - visual scale */}
                    <div className="ts-section-title">Adjustable History: 5 to 98 Years</div>
                    <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                        Most seasonal tools lock you into a fixed lookback. TradeWave lets you choose
                        anywhere from <strong>5 to 98 years</strong> of history. Patterns behave differently across time horizons:
                    </p>
                    <div style={{ ...cardStyle, padding: '14px 16px' }}>
                        {/* Years gradient bar */}
                        <div style={{
                            height: '18px', borderRadius: '9px', position: 'relative',
                            background: `linear-gradient(90deg, ${accentBlue}, ${accentGreen}, ${accentAmber})`,
                            marginBottom: '6px',
                        }}>
                            {/* Markers */}
                            {[
                                { pos: '0%', label: '5' },
                                { pos: '15%', label: '10' },
                                { pos: '35%', label: '25' },
                                { pos: '55%', label: '40' },
                                { pos: '100%', label: '98' },
                            ].map((m, i) => (
                                <div key={i} style={{ position: 'absolute', left: m.pos, top: '22px', transform: 'translateX(-50%)', fontSize: '9px', color: mutedText, fontWeight: 600 }}>{m.label}</div>
                            ))}
                        </div>
                        <div style={{ height: '16px' }} />
                        <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                            {[
                                { range: '5–10 yrs', color: accentBlue, text: 'Recent behavior, strong relevance, smaller sample' },
                                { range: '15–30 yrs', color: accentGreen, text: 'The sweet spot - balances recency with significance' },
                                { range: '40–98 yrs', color: accentAmber, text: 'Deep structural patterns that survived multiple market regimes' },
                            ].map((r, i) => (
                                <div key={i} style={{ flex: 1, borderLeft: `3px solid ${r.color}`, paddingLeft: '8px' }}>
                                    <div style={{ fontSize: '10px', fontWeight: 700, color: r.color }}>{r.range}</div>
                                    <div style={{ fontSize: '10px', opacity: 0.65, lineHeight: 1.3, marginTop: '2px' }}>{r.text}</div>
                                </div>
                            ))}
                        </div>
                        <div style={{ fontSize: '11px', marginTop: '10px', opacity: 0.7, fontStyle: 'italic' }}>
                            A pattern visible in both 10-year and 50-year windows is particularly compelling.
                        </div>
                    </div>

                    {/* Presidential Election Cycle */}
                    <div className="ts-section-title">Presidential Election Cycle</div>
                    <p style={{ fontSize: '12px', marginBottom: '10px' }}>
                        Markets follow a <strong>four-year political cycle</strong> alongside the annual calendar.
                        Stock behavior differs depending on where we are in the presidential term:
                    </p>

                    {/* PE cycle visual - 4 connected phases */}
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
                                </div>
                            ))}
                        </div>
                        {/* Arrow flow */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginBottom: '8px' }}>
                            {pePhases.map((p, i) => (
                                <React.Fragment key={i}>
                                    <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: p.color }} />
                                    {i < 3 && <div style={{ width: '30px', height: '2px', backgroundColor: mutedText }} />}
                                </React.Fragment>
                            ))}
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.7, lineHeight: 1.5 }}>
                            <strong>The TradeWave advantage:</strong> Instead of looking at 10 consecutive years, filter to
                            10 midterm years only - spanning roughly 40 calendar years. This reveals patterns unique to
                            specific political phases that are <strong>completely invisible</strong> in standard analysis.
                        </div>
                    </div>

                    <div style={{ ...cardStyle, background: dark ? 'rgba(167,139,250,0.08)' : 'rgba(167,139,250,0.05)', border: `1px solid ${dark ? 'rgba(167,139,250,0.2)' : 'rgba(167,139,250,0.12)'}`, padding: '10px 14px' }}>
                        <div style={{ fontSize: '11px', lineHeight: 1.5 }}>
                            <strong>Example:</strong> A stock shows no clear seasonal pattern over 10 consecutive years.
                            But isolate just the pre-election years and a powerful recurring move appears -
                            one that was hidden in the noise of all four cycle phases mixed together.
                        </div>
                    </div>

                    {/* Reading results */}
                    <div className="ts-section-title">How to Read the Results</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                        {[
                            { metric: 'SR', label: 'Sharpe Ratio', color: accentGreen, desc: 'Primary quality measure. Higher = more consistent returns.' },
                            { metric: '%P', label: '% Profitable', color: accentBlue, desc: 'Win rate across all years. 80%+ is strong.' },
                            { metric: 'Avg', label: 'Average Gain', color: accentAmber, desc: 'Typical return when the pattern is traded.' },
                            { metric: '|||', label: 'Bar Chart', color: '#a78bfa', desc: 'Visual proof. Green bars = wins. More green = more reliable.' },
                        ].map((m, i) => (
                            <div key={i} style={{ ...cardStyle, marginBottom: 0, textAlign: 'center', padding: '10px 8px' }}>
                                <div style={{ fontSize: '18px', fontWeight: 800, color: m.color, fontFamily: 'monospace' }}>{m.metric}</div>
                                <div style={{ fontSize: '11px', fontWeight: 700, marginTop: '2px' }}>{m.label}</div>
                                <div style={{ fontSize: '10px', opacity: 0.6, marginTop: '3px', lineHeight: 1.3 }}>{m.desc}</div>
                            </div>
                        ))}
                    </div>

                    <div className="ts-footer-note">
                        Seasonal patterns reflect historical data. Markets change, and past results do not guarantee
                        future performance. Use seasonal analysis as one input alongside your own research, risk
                        management, and current market conditions.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default SeasonalPatternsPopup
