import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const SharpeRatioPopup = ({ onClose, iconRect }) => {
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

    const ranges = [
        { range: 'Above 2.0', label: 'Very high historical excess return relative to cross-year variability', color: '#22c55e' },
        { range: '1.0 - 2.0', label: 'High historical excess return relative to cross-year variability', color: '#4ade80' },
        { range: '0.5 - 1.0', label: 'Moderate historical excess return relative to cross-year variability', color: '#f59e0b' },
        { range: '0.0 - 0.5', label: 'Low historical excess return relative to cross-year variability', color: '#fb923c' },
        { range: 'Below 0.0', label: 'Average return is below the prorated risk-free benchmark', color: '#ef4444' },
    ]

    return ReactDOM.createPortal(
        <div className="trend-score-overlay" onClick={handleOverlayClick}>
            <div className={`trend-score-popup${closing ? ' closing' : ''}${UITheme === 'dark' ? ' dark-scroll' : ''}`} style={popupStyle}>

                <div className="ts-header">
                    <h2 style={{ color: textColor }}>Sharpe Ratio</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">
                    <p>
                        The Sharpe Ratio compares a pattern's historical average return above the configured risk-free
                        benchmark with the variation in its ending returns from year to year. It is a measure of
                        <strong> cross-year consistency</strong>, not a complete measure of risk. It does not describe
                        the path taken inside each window or the largest adverse move before the exit date.
                    </p>

                    <div className="ts-section-title">How to Read It</div>
                    <p>
                        A higher value means the average historical excess return was larger relative to the dispersion
                        of the yearly ending results in the loaded sample. It does not prove that the pattern is reliable,
                        repeatable, statistically significant, or likely to behave the same way in the next window.
                    </p>

                    <table className="ts-range-table">
                        <thead>
                            <tr>
                                <th style={{ color: textColor }}>Sharpe Ratio</th>
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

                    <div className="ts-section-title">The Formula (Simplified)</div>
                    <p>
                        Sharpe Ratio = (<strong>Average Profit</strong> minus the configured annual risk-free rate,
                        prorated to the window length) divided by <strong>Standard Deviation of Profits</strong>.
                    </p>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Average Profit</strong> - the arithmetic mean of the yearly direction-adjusted
                            ending returns. The prorated risk-free return is subtracted from that mean in the numerator.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Standard Deviation</strong> - how spread out the yearly results are. If every year
                            is close to +4%, the standard deviation is small. If results swing wildly between +20% and
                            -12%, the standard deviation is large.
                        </li>
                    </ul>
                    <p>
                        When the average profit is large and the standard deviation is small, you get a high Sharpe
                        Ratio. Read that value alongside the sample size, median return, win rate, MFE/MAE path,
                        and recent-versus-earlier results; no one statistic establishes pattern quality by itself.
                    </p>

                    <div className="ts-section-title">Important: Compare Apples to Apples</div>
                    <p>
                        Sharpe estimates can move materially when the sample changes, especially when only a few years
                        are available. Comparisons are most meaningful when patterns use the same Years setting,
                        window convention, direction convention, and risk-free-rate configuration. Always keep the
                        number of completed observations (<strong>n</strong>) visible when comparing them.
                    </p>

                    <div className="ts-section-title">How TradeWave Uses It</div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            The opportunity table is <strong>sorted by Sharpe Ratio by default</strong>. It is the
                            primary ranking metric, so the first rows rank highest on this particular in-sample
                            return-to-variability measure. That ordering is not a guarantee or a complete quality rank.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Treat it as <strong>one piece of evidence</strong>. Check whether the mean and median agree,
                            whether a few outliers dominate the result, how large MAE became inside the window, and
                            whether the latest non-overlapping years differ from the earlier sample.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Average return and Sharpe answer different questions. The average describes magnitude;
                            Sharpe describes that average relative to cross-year dispersion. Neither determines which
                            pattern is appropriate for an individual user.
                        </li>
                    </ul>

                    <div className="ts-section-title">TWR (TradeWave Ratio)</div>
                    <p>
                        The standard Sharpe Ratio measures consistency from the start of a pattern to its end. But
                        what if a pattern tends to go up early and then pulls back before the end date? The final
                        return might look modest, yet there was a strong move in your favor during the window.
                    </p>
                    <p>
                        The <strong>TradeWave Ratio (TWR)</strong> captures exactly this. Instead of using the
                        start-to-end return, it uses the <strong>MFE (Maximum Favorable Excursion)</strong>, which is the
                        largest direction-adjusted favorable return reached during the pattern window each year. The TWR is the Sharpe Ratio
                        calculated on those MFE values instead of closing values.
                    </p>
                    <p>
                        A higher TWR than standard Sharpe means favorable intrawindow excursions were more consistent
                        than the ending returns in the loaded sample. MFE records the best level reached, but it does
                        not reveal when that level occurred, whether it was practically capturable, or which exit rule
                        would have worked out of sample.
                    </p>
                    <p>
                        Look for patterns where the TWR is notably higher than the Sharpe Ratio. That gap tells you
                        that some favorable excursion was later given back before the stated exit. Use the per-year
                        MFE/MAE bars and adjacent-window comparisons to investigate the path; the gap alone does not
                        prescribe a profit target or a shorter holding period.
                    </p>

                    <div className="ts-footer-note">
                        The Sharpe Ratio shown in TradeWave subtracts the configured annual risk-free rate,
                        prorated to the seasonal window's calendar-day length, before dividing by the standard
                        deviation of the historical pattern returns. Results are gross of execution costs, taxes,
                        short-borrow costs, and dividends, and scanner-ranked results are selection-sensitive.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default SharpeRatioPopup
