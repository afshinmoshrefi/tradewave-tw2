import React, { useCallback, useEffect, useRef, useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import { AI_COLUMNS, AI_METRICS } from './opportunityAIScores'
import './styles/TrendScorePopup.css'

const AIScoresPopup = ({ onClose, iconRect }) => {
    const { UITheme, seasonalAppDivH } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [closing, setClosing] = useState(false)
    const dialogRef = useRef(null)
    const previousFocusRef = useRef(null)
    const closeTimerRef = useRef(null)

    const handleClose = useCallback(() => {
        setClosing(true)
        if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current)
        closeTimerRef.current = window.setTimeout(() => onClose(), 200)
    }, [onClose])

    useEffect(() => {
        const handleKeyDown = event => {
            if (event.key === 'Escape') {
                event.preventDefault()
                handleClose()
                return
            }
            if (event.key !== 'Tab' || !dialogRef.current) return
            const focusable = Array.from(dialogRef.current.querySelectorAll(
                'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            ))
            if (focusable.length === 0) {
                event.preventDefault()
                dialogRef.current.focus()
                return
            }
            const first = focusable[0]
            const last = focusable[focusable.length - 1]
            if (document.activeElement === dialogRef.current) {
                event.preventDefault()
                ;(event.shiftKey ? last : first).focus()
            } else if (event.shiftKey && document.activeElement === first) {
                event.preventDefault()
                last.focus()
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault()
                first.focus()
            }
        }
        previousFocusRef.current = document.activeElement
        window.addEventListener('keydown', handleKeyDown)
        if (dialogRef.current) dialogRef.current.focus()
        return () => {
            window.removeEventListener('keydown', handleKeyDown)
            if (closeTimerRef.current) window.clearTimeout(closeTimerRef.current)
            const previousFocus = previousFocusRef.current
            if (previousFocus && previousFocus.isConnected && typeof previousFocus.focus === 'function') {
                previousFocus.focus()
            }
        }
    }, [handleClose])

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

    const plainMetricNames = {
        ml_score: 'AI Return Rank',
        win_prob: 'AI Win Chance',
        pred_return: 'Estimated End Return',
        pred_mfe: 'Estimated Best Move',
    }
    const columns = AI_COLUMNS.map(key => ({
        col: AI_METRICS[key].shortLabel,
        full: plainMetricNames[key] || AI_METRICS[key].label,
        desc: AI_METRICS[key].description,
        color: '#818cf8',
    }))

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="ai-scores-popup-title"
                tabIndex="-1"
                className={`trend-score-popup ai-scores-popup${closing ? ' closing' : ''}${UITheme === 'dark' ? ' dark-scroll' : ''}`}
                style={popupStyle}
            >

                <div className="ts-header">
                    <h2 id="ai-scores-popup-title" style={{ color: textColor }}>AI Scores</h2>
                    <button className="ts-close-btn" aria-label="Close AI Scores guide" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div
                    className="ts-body ai-scores-body"
                    role="region"
                    aria-label="AI Scores guide content"
                    tabIndex="0"
                >

                    <div style={{
                        background: accentBg,
                        border: `1px solid ${accentBorder}`,
                        borderRadius: '8px',
                        padding: '14px 16px',
                        marginBottom: '16px',
                    }}>
                        <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>
                            Why use AI Scores?
                        </div>
                        <p style={{ marginTop: 0 }}>
                            <strong>History tells you what this pattern did in past years.</strong>{' '}
                            AI uses the latest completed stock and market conditions to estimate today's setup. Compare
                            them to see where current conditions support or conflict with the past results. AI does not
                            replace history or guarantee a profit.
                        </p>
                        <p>
                            TradeWave checks older AI estimates against what really happened and adjusts AI Win Chance
                            using those real results. This reality check is called calibration.
                        </p>

                        <div style={{ fontSize: '16px', fontWeight: 700, margin: '16px 0 8px' }}>
                            How to read the numbers
                        </div>
                        <ul style={{ paddingLeft: '20px', margin: '8px 0 14px' }}>
                            <li style={{ marginBottom: '6px' }}><strong>AI Win Chance:</strong> estimated chance that this checkpoint ends with a profit in the shown Long or Short direction.</li>
                            <li style={{ marginBottom: '6px' }}><strong>Estimated End Return:</strong> estimated gain or loss when this time length ends.</li>
                            <li style={{ marginBottom: '6px' }}><strong>Estimated Best Move:</strong> largest helpful move AI expects before the checkpoint ends. It is not a target.</li>
                            <li><strong>AI Return Rank:</strong> “Higher than 75%” means the estimated end return ranks above 75% of similar AI estimates. It is not a win chance or grade.</li>
                        </ul>

                        <div style={{ fontSize: '16px', fontWeight: 700, margin: '16px 0 8px' }}>
                            Why are there several time views?
                        </div>
                        <p>
                            A pattern can look different after 30, 60, or 90 calendar days. TradeWave scores each
                            ending date separately. These are checkpoints for different holding lengths, not extra
                            votes on the same result.
                        </p>

                        <div style={{ fontSize: '16px', fontWeight: 700, margin: '16px 0 8px' }}>
                            What should I do next?
                        </div>
                        <p style={{ marginBottom: 0 }}>
                            Start with the historical record. Then compare AI Win Chance and Estimated End Return.
                            If the views disagree, slow down and review the losing years, Price Chart, and risk. Do not
                            average the historical percentage with AI Win Chance.
                        </p>
                    </div>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#3b82f6' }}></span>
                        Why history and AI Win Chance can differ
                    </div>
                    <p>
                        AI Win Chance does not change the historical record. If history says 9 of 10 years were
                        profitable, it stays 9 of 10 years.
                    </p>
                    <p>
                        To create AI Win Chance, TradeWave looks at older AI estimates like this one and checks what
                        happened next. If about 7 of 10 similar cases were profitable in the selected direction, AI
                        Win Chance is about 70%. This check creates a separate estimate; it does not add years to the
                        historical sample or rewrite the past results.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#22c55e' }}></span>
                        What the AI looks at
                    </div>
                    <p>
                        The model uses <strong>62 pieces of information</strong> about the pattern, stock, broad market,
                        and calendar. It estimates the ending return and the best favorable move for the shown Long or
                        Short direction.
                    </p>
                    <p>
                        When TradeWave checks older cases, it uses only information that was available at that time and
                        then compares the estimate with what happened later. That keeps future information out of the
                        test.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#a78bfa' }}></span>
                        The four AI readings
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
                        How to read AI Return Rank
                    </div>
                    <p>
                        AI Return Rank compares this estimated ending return with other AI estimates for similar time
                        lengths. “Higher than 80%” means it ranks above about 80% of those comparable estimates. It
                        does not mean an 80% chance of profit. Use AI Win Chance for that estimate.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#818cf8' }}></span>
                        How time lengths work
                    </div>
                    <p>Every time length uses calendar days. The start date is day 1, and weekends and holidays count.</p>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}><strong>1-9 days:</strong> history uses the real length; AI uses 10 days.</li>
                        <li style={{ marginBottom: '6px' }}><strong>10-30 days:</strong> AI scores the full pattern.</li>
                        <li style={{ marginBottom: '6px' }}><strong>31-60 days:</strong> compare 30 days with the full pattern.</li>
                        <li style={{ marginBottom: '6px' }}><strong>61-90 days:</strong> compare 30 and 60 days with the full pattern.</li>
                        <li><strong>More than 90 days:</strong> compare 30, 60, and 90 days; the table shows 90 days.</li>
                    </ul>
                    <p>
                        The AI Scores window shows every applicable reading together. TradeWave recalculates the same
                        opportunity at each shown length. A shorter AI estimate can still appear when that shorter
                        length does not pass your history filter because the AI estimate and history check answer
                        different questions.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#818cf8' }}></span>
                        Long and Short
                    </div>
                    <p>
                        Long means a price rise helps the setup. Short means a price drop helps the setup. A positive
                        Estimated End Return means the estimate helps the direction shown. AI Win Chance also measures
                        a profitable result in that direction.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#9ca3af' }}></span>
                        Good to know
                    </div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            AI scores are available for <strong>US stocks and ETFs</strong>. Other markets
                            (futures, indices, crypto, FX) are not scored at this time.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            AI uses stock and market data from the latest completed market day. On weekends, holidays,
                            or while an update is still finishing, it may use the previous market day. It does not
                            update during the trading day (intraday).
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            A spinner means AI is still calculating. A dash means no score was assigned. Select that
                            row and open the AI Scores window to see why. Zero is a real AI value, not an unavailable sign.
                        </li>
                    </ul>

                    <div style={{
                        background: accentBg,
                        border: `1px solid ${accentBorder}`,
                        borderRadius: '8px',
                        padding: '12px 16px',
                        marginTop: '8px',
                    }}>
                        <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>
                            Want AI values in the Opportunity Table?
                        </div>
                        <div style={{ fontSize: '13px', opacity: 0.8, lineHeight: 1.5 }}>
                            The AI columns start off to keep the table clean. Open Settings, choose Opportunity Table,
                            and turn on AIS, Win%, PredR, or PMFE. The AI Scores window remains available even when all
                            four table columns are hidden. AI scoring also requires an eligible plan and a U.S. stock
                            or ETF market.
                        </div>
                    </div>

                    <div className="ts-footer-note">
                        AI Scores are research evidence, not guarantees or personal recommendations. They cannot
                        predict unexpected news or every market change. Review the historical sample, expected return,
                        possible loss, and your own risk limits before acting.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default AIScoresPopup
