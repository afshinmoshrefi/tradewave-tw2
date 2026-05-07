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
        { range: 'Above 2.0', label: 'Excellent - very strong, consistent pattern', color: '#22c55e' },
        { range: '1.0 - 2.0', label: 'Good - solid pattern worth considering', color: '#4ade80' },
        { range: '0.5 - 1.0', label: 'Moderate - pattern exists but returns are less consistent', color: '#f59e0b' },
        { range: '0.0 - 0.5', label: 'Weak - average gain is small relative to the variability', color: '#fb923c' },
        { range: 'Below 0.0', label: 'Negative - the pattern loses money on average', color: '#ef4444' },
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
                        The Sharpe Ratio answers one simple question: <strong>is the profit worth the risk?</strong> It
                        compares how much a pattern gains on average to how much those gains bounce around from year to year.
                        A pattern that makes 5% every year like clockwork is far more useful than one that makes 20% one
                        year and loses 15% the next, even though their averages might look similar.
                    </p>

                    <div className="ts-section-title">How to Read It</div>
                    <p>
                        Think of it like a restaurant rating. A high Sharpe Ratio means the pattern delivers
                        <strong> reliable, repeatable</strong> results. A low one means the results are all over the place -
                        some years great, some years terrible - so you cannot count on it.
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
                        Sharpe Ratio = <strong>Average Profit</strong> divided by <strong>Standard Deviation of Profits</strong>.
                    </p>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Average Profit</strong> - the typical gain (or loss) the pattern produces each year.
                            If a pattern averages +4% per year, that is the numerator.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            <strong>Standard Deviation</strong> - how spread out the yearly results are. If every year
                            is close to +4%, the standard deviation is small. If results swing wildly between +20% and
                            -12%, the standard deviation is large.
                        </li>
                    </ul>
                    <p>
                        When the average profit is large and the standard deviation is small, you get a high Sharpe
                        Ratio. That is the ideal pattern: <strong>consistent gains with low variability</strong>.
                    </p>

                    <div className="ts-section-title">Important: Compare Apples to Apples</div>
                    <p>
                        The Sharpe Ratio depends on how many years of data go into the calculation. A 10-year pattern
                        and a 20-year pattern can produce very different Sharpe Ratios even if the underlying behavior
                        is similar, because more years means more data points, which changes both the average and the
                        variability. <strong>Only compare Sharpe Ratios between patterns that use the same number of
                        years.</strong> For example, compare two 10-year patterns to each other, or two 20-year
                        patterns, but do not compare a 10-year Sharpe with a 20-year Sharpe.
                    </p>

                    <div className="ts-section-title">How TradeWave Uses It</div>
                    <ul style={{ paddingLeft: '20px', margin: '8px 0 12px' }}>
                        <li style={{ marginBottom: '6px' }}>
                            The opportunity table is <strong>sorted by Sharpe Ratio by default</strong>. It is the
                            primary ranking metric. The patterns at the top are the ones with the best combination
                            of profit and consistency. When you open the opportunity table, you are already looking
                            at the highest-quality patterns first.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Use it as a <strong>first filter</strong>. A pattern with a high Sharpe Ratio and a high
                            win rate (% profitable) is a strong candidate. A high Sharpe with a low win rate means a
                            few big winners are driving the average, which is riskier.
                        </li>
                        <li style={{ marginBottom: '6px' }}>
                            Compare patterns by Sharpe Ratio rather than by average profit alone. A 2% average gain
                            with a 2.5 Sharpe is usually a better trade than a 6% average gain with a 0.4 Sharpe.
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
                        best price reached during the pattern window each year. The TWR is the Sharpe Ratio
                        calculated on those MFE values instead of closing values.
                    </p>
                    <p>
                        Why does this matter? Some patterns have a low standard Sharpe Ratio but a high TWR. That
                        means in many years the price moves significantly in the right direction early on, even if
                        it gives some of that back by the end of the window. These patterns can be
                        <strong> excellent candidates for short-term trades</strong>. You enter the trade and exit
                        early when the move happens, rather than holding to the pattern's end date.
                    </p>
                    <p>
                        Look for patterns where the TWR is notably higher than the Sharpe Ratio. That gap tells you
                        the pattern has a habit of making a strong move in your favor before pulling back, which is a
                        signal that a shorter holding period might capture more consistent profits.
                    </p>

                    <div className="ts-footer-note">
                        The Sharpe Ratio shown in TradeWave uses the seasonal pattern's historical returns without
                        subtracting a risk-free rate, since the focus is on comparing patterns to each other rather
                        than to a Treasury yield.
                    </div>
                </div>

            </div>
        </div>,
        document.body
    )
}

export default SharpeRatioPopup
