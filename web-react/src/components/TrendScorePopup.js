import React, { useState, useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

const TrendScorePopup = ({ onClose }) => {

    const { UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const isDark = UITheme === 'dark'
    const [closing, setClosing] = useState(false)

    const handleClose = () => {
        setClosing(true)
        setTimeout(onClose, 200)
    }

    const overlayBg = isDark ? 'rgba(0,0,0,0.65)' : 'rgba(0,0,0,0.35)'
    const popupBg = isDark ? 'rgb(28, 25, 40)' : 'rgb(255, 255, 255)'
    const textColor = tc.text
    const subtleBorder = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)'
    const cardBg = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.025)'
    const thBorder = isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)'

    const components = [
        ['Price vs 20-day MA', 'How far price is above the 20-day moving average'],
        ['Price vs 50-day MA', 'Same for the 50-day average'],
        ['Price vs 100-day MA', 'Same for the 100-day average'],
        ['Price vs 200-day MA', 'Same for the 200-day average'],
        ['MACD Direction', 'Is the MACD signal line rising or falling?'],
        ['MACD Value', 'Is MACD above or below zero?'],
        ['EMA5 vs WMA13', 'Is the fast average leading the slower one?'],
        ['Parabolic SAR', 'Is the SAR indicator below price (bullish) or above?'],
        ['RSI (14)', 'Relative Strength Index - above 50 scores higher'],
        ['ADX Trend Strength', 'How strong is the trend, confirmed by price direction'],
    ]

    const ranges = [
        ['80-100', 'Strongly supports the tested direction', '#16a34a'],
        ['61-79', 'Supports the tested direction', '#22c55e'],
        ['40-60', 'Neutral - no clear confirmation', '#9ca3af'],
        ['20-39', 'Does not support the tested direction', '#f59e0b'],
        ['0-19', 'Strongly does not support the tested direction', '#ef4444'],
    ]

    return (
        <div className="trend-score-overlay" style={{ backgroundColor: overlayBg }} onClick={handleClose}>
            <div
                className={`trend-score-popup ${closing ? 'ts-closing' : ''}`}
                style={{ backgroundColor: popupBg, color: textColor }}
                onClick={e => e.stopPropagation()}
            >
                <div className="ts-header">
                    <h2>Trend Scores &amp; Alignment</h2>
                    <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                </div>

                <div className="ts-body">
                    <p>
                        Seasonal patterns tell you what a stock has <em>historically</em> done at a given time of year - but they don't tell you what the stock is doing <em>right now</em>. Is it actually following the pattern? Is it trending up, down, or going nowhere?
                    </p>
                    <p>
                        <strong>Trend Long</strong> asks how strongly price has been moving upward over roughly the last one to two weeks. <strong>Trend Short</strong> asks how strongly it has been moving downward. These are current-momentum readings to compare with the seasonal data.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#a855f7' }}></span>
                        What Trend Alignment Means
                    </div>
                    <p>
                        Trend Alignment chooses the score that matches the loaded setup. A <strong>long</strong> setup uses Trend Long and asks whether recent movement has been upward. A <strong>short</strong> setup uses Trend Short and asks whether recent movement has been downward.
                    </p>
                    <p>
                        <strong>Aligned</strong> means recent movement confirms the seasonal direction. <strong>Against</strong> means recent movement has not been moving strongly in that direction. <strong>Neutral</strong> means there is no clear confirmation. This does not change the historical win rate and does not predict the outcome.
                    </p>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#3b82f6' }}></span>
                        Reading the Direction-Specific Score
                    </div>

                    <div className="ts-score-bar-container" style={{ backgroundColor: cardBg, borderColor: subtleBorder }}>
                        <div className="ts-score-labels">
                            <span>Against direction</span>
                            <span>Neutral</span>
                            <span>Aligned direction</span>
                        </div>
                        <div className="ts-score-bar"></div>
                        <div className="ts-score-ticks">
                            <span>0</span><span>20</span><span>40</span><span>60</span><span>80</span><span>100</span>
                        </div>
                    </div>

                    <div style={{ margin: '0 0 14px' }}>
                        {ranges.map(([range, label, color]) => (
                            <div className="ts-score-range-row" key={range} style={{ borderColor: subtleBorder }}>
                                <span className="ts-range-label" style={{ color }}>{range}</span>
                                <span>{label}</span>
                            </div>
                        ))}
                    </div>

                    <div className="ts-section-title">
                        <span className="ts-dot" style={{ backgroundColor: '#22c55e' }}></span>
                        How It's Calculated
                    </div>
                    <p>
                        The score uses 10 technical components, each worth <strong>0 - 10 points</strong>, for a total of 0 - 100. Trend Long reads them for upward confirmation; Trend Short reads them for downward confirmation:
                    </p>

                    <table className="ts-formula-table">
                        <thead>
                            <tr>
                                <th style={{ borderColor: thBorder }}>Component</th>
                                <th style={{ borderColor: thBorder }}>What it measures</th>
                                <th className="ts-pts" style={{ borderColor: thBorder }}>Pts</th>
                            </tr>
                        </thead>
                        <tbody>
                            {components.map(([name, desc]) => (
                                <tr key={name}>
                                    <td style={{ fontWeight: 500, borderColor: subtleBorder }}>{name}</td>
                                    <td style={{ borderColor: subtleBorder }}>{desc}</td>
                                    <td className="ts-pts" style={{ borderColor: subtleBorder }}>0-10</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    <p className="ts-note">
                        Each distance component is scaled to the stock's own volatility (ATR), so a calm utility stock and a volatile growth stock are measured on equal footing. If TradeWave cannot retrieve a usable score, it shows Unavailable; that must not be interpreted as a real score of zero.
                    </p>
                </div>
            </div>
        </div>
    )
}

export default TrendScorePopup
