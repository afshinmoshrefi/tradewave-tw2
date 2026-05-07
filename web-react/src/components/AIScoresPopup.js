import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const AIScoresPopup = ({ onClose, iconRect }) => {
    const { UITheme, seasonalAppDivH } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [closing, setClosing] = useState(false)

    const handleClose = () => {
        setClosing(true)
        setTimeout(() => onClose(), 200)
    }

    const handleOverlayClick = (e) => {
        if (e.target === e.currentTarget) handleClose()
    }

    const bgColor = UITheme === 'dark' ? '#1e1e2e' : '#ffffff'
    const textColor = tc.text
    const rowEven = UITheme === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'
    const accentBg = UITheme === 'dark' ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)'
    const accentBorder = UITheme === 'dark' ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'

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

    const columns = [
        { col: 'AIS', full: 'AI Score', desc: 'A composite quality score from 0 to 100. Higher means the AI sees stronger conditions supporting this pattern right now. Think of it as an overall confidence rating that combines multiple signals into one number.', color: '#3b82f6' },
        { col: 'Win%', full: 'AI Win Probability', desc: 'The AI-calibrated probability that this pattern will be profitable. Unlike the historical win rate (which only counts past years), this factors in current market conditions to give a more realistic estimate.', color: '#22c55e' },
        { col: 'PredR', full: 'Predicted Return', desc: 'The AI-estimated average return for this pattern given current conditions. This adjusts the historical average profit by considering what the market environment looks like today.', color: '#a78bfa' },
        { col: 'PMFE', full: 'Predicted MFE', desc: 'The AI-estimated maximum favorable excursion, the best expected intra-trade peak before the pattern exit date. Useful for setting profit targets or deciding when to take early profits.', color: '#f59e0b' },
    ]

    const scores = [
        { range: '80 - 100', label: 'Very strong AI confidence in the pattern', color: '#22c55e' },
        { range: '60 - 79', label: 'Solid conditions supporting the historical pattern', color: '#4ade80' },
        { range: '40 - 59', label: 'Moderate - mixed signals from current data', color: '#f59e0b' },
        { range: '20 - 39', label: 'Weak - current conditions do not favor this pattern', color: '#fb923c' },
        { range: '0 - 19', label: 'Very weak - conditions conflict with the historical pattern', color: '#ef4444' },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${UITheme === 'dark' ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>AI Scores</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#3b82f6' }}></span>
                        Why AI Scores Exist
                    </div>
                    <p>
                        TradeWave finds seasonal patterns by looking at history: windows where a stock has
                        moved in the same direction year after year. That historical track record is powerful,
                        but it does not account for what is happening in the market <em>right now</em>.
                    </p>
                    <p>
                        The AI scoring layer bridges that gap. It takes each historical pattern and
                        recalibrates the statistics using current market conditions, giving you a
                        forward-looking view grounded in both history and the present.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#22c55e' }}></span>
                        How It Works
                    </div>
                    <p>
                        For each pattern in the opportunity table, the AI analyzes <strong>59 features</strong> that
                        describe the security and the broader market at this moment. These features include price
                        trends, volatility, momentum, sector conditions, and more. An ensemble classifier
                        trained on <strong>37 million data points</strong> then produces four calibrated scores.
                    </p>
                    <p>
                        The result is a set of statistics that reflect not just "what has this pattern done
                        historically" but "given what the market looks like today, how likely is this pattern
                        to work again."
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#a78bfa' }}></span>
                        The Four Columns
                    </div>
                    <table className="ts-range-table">
                        <thead>
                            <tr>
                                <th style={{ color: textColor }}>Column</th>
                                <th style={{ color: textColor }}>Name</th>
                                <th style={{ color: textColor }}>What It Tells You</th>
                            </tr>
                        </thead>
                        <tbody>
                            {columns.map((c, i) => (
                                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? rowEven : 'transparent' }}>
                                    <td><span style={{ color: c.color, fontWeight: 600 }}>{c.col}</span></td>
                                    <td style={{ fontWeight: 500 }}>{c.full}</td>
                                    <td>{c.desc}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#f59e0b' }}></span>
                        Reading the AI Score (AIS)
                    </div>
                    <table className="ts-range-table">
                        <thead>
                            <tr>
                                <th style={{ color: textColor }}>AIS Range</th>
                                <th style={{ color: textColor }}>What It Means</th>
                            </tr>
                        </thead>
                        <tbody>
                            {scores.map((s, i) => (
                                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? rowEven : 'transparent' }}>
                                    <td><span style={{ color: s.color, fontWeight: 600 }}>{s.range}</span></td>
                                    <td>{s.label}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#14b8a6' }}></span>
                        How to Use AI Scores
                    </div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Pair with historical stats.</strong> A pattern with a high Sharpe Ratio
                            and a high AI Score means both history and current conditions agree. That is the
                            strongest signal.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Compare Win% to historical win rate.</strong> If the historical percent
                            profitable is 90% but AI Win% is 55%, the AI is seeing something in current
                            conditions that makes this year less favorable. Worth investigating before taking
                            the trade.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Use PMFE for profit targets.</strong> If PMFE is higher than PredR, the
                            pattern tends to overshoot before settling. Consider taking partial profits early.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Scores update daily.</strong> The AI re-scores every pattern each trading
                            day using the latest market data. What you see reflects conditions as of today.
                        </li>
                    </ul>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#9ca3af' }}></span>
                        Good to Know
                    </div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            AI scores are available for <strong>US stocks and ETFs</strong>. Other markets
                            (futures, indices, crypto, FX) are not scored at this time.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Patterns longer than <strong>90 days</strong> are not scored. These show <strong>---</strong> in
                            the AI columns. The AI models are trained on patterns up to 90 days in length.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            When scores are loading, you will see a small spinning indicator. Scores that are
                            already cached appear instantly, while new scores fill in progressively.
                        </li>
                    </ul>

                    <div style={{
                        background: accentBg,
                        border: `1px solid ${accentBorder}`,
                        borderRadius: '8px',
                        padding: '12px 16px',
                        marginTop: '8px',
                    }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '4px' }}>
                            Don't see the AI columns?
                        </div>
                        <div style={{ fontSize: '11px', opacity: 0.8, lineHeight: 1.5 }}>
                            AI scoring is available to TradeWave subscribers with an eligible plan. If you
                            are viewing US stocks or ETFs and do not see the AIS, Win%, PredR, and PMFE
                            columns, your current plan may not include this feature. Upgrading your
                            subscription gives you access to AI-calibrated scores that can help you
                            make more informed decisions alongside the historical data you already use.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        AI scores are calibrated estimates based on machine learning models and current market
                        data. They are not guarantees. Past performance and AI predictions do not guarantee
                        future results. Always manage your risk.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default AIScoresPopup
