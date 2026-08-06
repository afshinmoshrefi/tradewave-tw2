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

    const columns = AI_COLUMNS.map(key => ({
        col: AI_METRICS[key].shortLabel,
        full: AI_METRICS[key].label,
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
                className={`trend-score-popup${closing ? ' closing' : ''}${UITheme === 'dark' ? ' dark-scroll' : ''}`}
                style={popupStyle}
            >

                <div className="ts-header">
                    <h2 id="ai-scores-popup-title" style={{ color: textColor }}>AI Scores</h2>
                    <button className="ts-close-btn" aria-label="Close AI Scores guide" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div
                    className="ts-body"
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
                        <div style={{ fontSize: '15px', fontWeight: 700, marginBottom: '8px' }}>
                            First: What the outline means
                        </div>
                        <p style={{ marginTop: 0 }}>
                            <strong>An outlined AI value means that pattern has more than one AI duration to view.</strong>{' '}
                            Open it to compare them. The outline does not mean the score is better or worse, and it is
                            not a warning.
                        </p>
                        <p>
                            For a <strong>1-9-day pattern</strong>, TradeWave changes only the AI window to 10 calendar
                            days, the shortest duration the model scores. The historical pattern and its historical
                            stats stay at the real length. This single AI reading is not outlined because there is no
                            second duration to compare. A small <strong>10d</strong> label marks it in the first visible
                            AI column.
                        </p>
                        <div style={{ fontSize: '15px', fontWeight: 700, margin: '14px 0 8px' }}>
                            Quick summary: Why this helps
                        </div>
                        <p>
                            <strong>TradeWave history tells you what usually happened. AI Scores add a second check:
                            does this pattern still look favorable under today's stock and market conditions?</strong>
                            The two belong side by side. History shows how repeatable the pattern was, while AI adds
                            current context.
                        </p>
                        <p>
                            <strong>Why it matters:</strong> a pattern may have risen in 9 of 10 past years, but today's
                            setup can be different. The historical result stays 9 of 10. AI then reality-checks that raw
                            historical probability for today's conditions by comparing older model readings with what
                            actually happened next. If similar readings made money 7 out of 10 times, the calibrated AI
                            Win% would be about 70%. That is <strong>calibration</strong>: checking a model percentage
                            against real results and adjusting it instead of leaving it as a raw guess.
                        </p>
                        <ul style={{ paddingLeft: '20px', margin: '8px 0' }}>
                            <li style={{ marginBottom: '5px' }}><strong>Win%:</strong> how often similar model readings later made money.</li>
                            <li style={{ marginBottom: '5px' }}><strong>PredR:</strong> the estimated return at the end of the shown time window.</li>
                            <li style={{ marginBottom: '5px' }}><strong>PMFE:</strong> the estimated best favorable move during the window.</li>
                            <li><strong>AIS:</strong> a 0-100 relative rank; it is not a win probability.</li>
                        </ul>
                        <p style={{ marginBottom: 0 }}>
                            <strong>How to use it:</strong> compare historical Win% with AI Win%. Agreement adds support.
                            A large difference tells you to inspect the setup more closely; it is not an automatic buy
                            or sell signal. Then use PredR and PMFE to understand the possible size of the move.
                        </p>
                    </div>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#3b82f6' }}></span>
                        More Detail: Why AI Scores Exist
                    </div>
                    <p>
                        TradeWave finds seasonal patterns by looking at history: windows where a stock has
                        moved in the same direction year after year. That historical track record is powerful,
                        but it does not account for what is happening in the market <em>right now</em>.
                    </p>
                    <p>
                        The AI scoring layer adds separate current-condition estimates alongside each historical
                        pattern. The historical statistics remain unchanged, so you can compare the past record with
                        a model view built from the latest available inputs.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#22c55e' }}></span>
                        How Calibration Works
                    </div>
                    <p>
                        TradeWave V3 uses <strong>62 inputs</strong> about the pattern, the stock, the market, and the
                        calendar. Separate models estimate the ending return and the best favorable move for the
                        selected direction and time window.
                    </p>
                    <p>
                        For calibration, older model readings are kept in time order and compared with what happened
                        afterward. Similar PredR readings are grouped together, and Win% reports the share of that
                        group that really finished profitable. AIS reports where PredR ranks within the matching time
                        range. This is why AI Win% can be different from the pattern's historical win rate: they answer
                        related but different questions.
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
                    <p>
                        AIS is the 0-100 percentile position of the ensemble's direction-adjusted PredR within that
                        horizon tier's 20-bin walk-forward calibration distribution. It is a <strong>relative rank</strong>,
                        not a probability, an overall confidence score, or a classifier output. Win% is the probability
                        field; an AIS of 80 does not mean an 80% chance of profit.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#818cf8' }}></span>
                        Current Score and Duration Comparison
                    </div>
                    <p>
                        Patterns from 10 through 90 calendar days keep their current full-window reading in the table.
                        Open an outlined value to compare supported shorter durations: patterns over 30 days add 30
                        days, patterns over 60 days also add 60 days, and patterns over 90 days add the bounded 90-day
                        checkpoint. A longer pattern therefore shows the <strong>90-calendar-day checkpoint</strong> in
                        the table, not a score of its complete historical window. The one exception at the lower end is
                        a 1-9-day pattern, which uses the clearly labeled 10-day AI model minimum while its historical
                        statistics stay at the real pattern length.
                    </p>
                    <p>
                        TradeWave windows are inclusive calendar days: the entry day counts as day 1.
                    </p>
                    <p>
                        The neutral violet outline and dotted underline identify a duration comparison. They do not mean the
                        reading is good, bad, bullish, or bearish. At each shorter duration, TradeWave recalculates the
                        same selected historical recurrence and shows whether it still meets your table screen. That
                        screen result is evidence beside the AI reading, not a reason to erase it. A shorter duration
                        can still have an AI score when it does not pass your historical screen because the two readings
                        answer different questions. TradeWave stops at
                        90 days because these models were
                        validated for near-term horizons through 90 calendar days, where current conditions are most
                        useful. Patterns above 90 days are summarized at the 30-, 60-, and 90-day checkpoints.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#818cf8' }}></span>
                        Long and Short Examples
                    </div>
                    <p>
                        For a long pattern, a positive PredR means the model estimates a price gain in the long
                        direction. For a short pattern, a positive direction-adjusted PredR means a price decline would
                        favor the short direction. Win% also follows the selected direction, so it estimates how often
                        that direction was profitable in the matching calibration group.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#14b8a6' }}></span>
                        How to Use AI Scores
                    </div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Pair with historical stats.</strong> Use the model outputs alongside Sharpe Ratio,
                            sample size, median, MFE/MAE, and outlier dependence rather than treating AIS as a verdict.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Compare Win% to historical win rate.</strong> If the historical record is
                            9 profitable years out of 10 (n=10) but AI Win% is 55%, the AI is seeing something in current
                            conditions that makes this year's estimate less favorable. That discrepancy is a useful
                            prompt to inspect the inputs and the historical distribution.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Compare PMFE with PredR.</strong> A higher PMFE suggests the model estimates a
                            larger favorable intrawindow move than the ending return. It does not show when that move
                            might occur or prescribe a target, partial sale, or early exit.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Compare durations.</strong> For a 10-90-day pattern, the current duration stays
                            highlighted. Shorter readings show whether the seasonal edge appears quickly, develops
                            later, or falls below its selected historical requirement.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Scores update with completed data.</strong> The AI uses the latest completed
                            end-of-day inputs. On weekends, holidays, or before an update finishes, that data may be
                            from the prior market session.
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
                            A pattern of 31-60 days compares 30 days with the current duration. A pattern of 61-90 days
                            compares 30 and 60 days with the current duration. Those comparisons never extend beyond
                            the original pattern. The separate 1-9-day minimum-horizon rule is the only exception: its
                            AI reading uses 10 days and is labeled 10d, while its historical statistics remain unchanged.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Patterns longer than <strong>90 calendar days</strong> show the 90-day checkpoint in the
                            table. Open the value to see all three bounded checkpoint readings.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            A loading marker means calculation is in progress. A dash with a clear data or service
                            message explains why no AI reading was assigned. Failing the selected historical screen does
                            not erase a valid model reading. Numeric zero remains a valid model value and is never used
                            as an unavailable marker.
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
                        future results. They are research inputs, not individualized recommendations.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default AIScoresPopup
