import React, { useState, useContext } from 'react'
import ReactDOM from 'react-dom'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import './styles/TrendScorePopup.css'

import GettingStartedPopup from './GettingStartedPopup'
import OppTablePopup from './OppTablePopup'
import FilteringPopup from './FilteringPopup'
import BarChartPopup from './BarChartPopup'
import SeasonalPatternsPopup from './SeasonalPatternsPopup'
import TrendChartPopup from './TrendChartPopup'
import ProjectionPopup from './ProjectionPopup'
import SharpeRatioPopup from './SharpeRatioPopup'
import TWRPopup from './TWRPopup'
import TrendScorePopup from './TrendScorePopup'
import MFEMAEPopup from './MFEMAEPopup'
import PECyclePopup from './PECyclePopup'
import DaysOutPopup from './DaysOutPopup'
import YearsRangePopup from './YearsRangePopup'
import WatchlistPopup from './WatchlistPopup'
import AIScoresPopup from './AIScoresPopup'

const guides = [
    { key: 'gettingstarted', label: 'Getting Started', desc: 'Platform tour, your first pattern in 60 seconds', icon: '🚀', color: '#22c55e', category: 'start' },
    { key: 'opptable', label: 'Opportunity Table', desc: 'Reading columns, ranking, default vs expanded mode', icon: '📋', color: '#3b82f6', category: 'core' },
    { key: 'filtering', label: 'Filtering', desc: 'Filter syntax, combining conditions, re-ranking', icon: '🔍', color: '#f59e0b', category: 'core' },
    { key: 'barchart', label: 'Year-by-Year Bar Chart', desc: 'Reading bars, MFE/MAE overlays, clicking years', icon: '📊', color: '#22c55e', category: 'core' },
    { key: 'seasonal', label: 'Seasonal Patterns', desc: 'What seasonality is, why patterns exist, how they are found', icon: '🌊', color: '#3b82f6', category: 'concepts' },
    { key: 'trendchart', label: 'Trend Chart', desc: 'How years combine into one line, reading the trend', icon: '📈', color: '#14b8a6', category: 'concepts' },
    { key: 'projection', label: 'Seasonal Projection', desc: 'The dashed golden line, projection periods, how it works', icon: '🎯', color: '#daa520', category: 'concepts' },
    { key: 'sharpe', label: 'Sharpe Ratio', desc: 'Risk-adjusted consistency, formula, how to compare', icon: '⚖️', color: '#22c55e', category: 'metrics' },
    { key: 'twr', label: 'TradeWave Ratio (TWR)', desc: 'Peak-profit consistency, when TWR > SR matters', icon: '💎', color: '#3b82f6', category: 'metrics' },
    { key: 'trendscore', label: 'Trend Score', desc: '0-100 real-time trend reading, 10 technical components', icon: '🧭', color: '#a78bfa', category: 'metrics' },
    { key: 'aiscores', label: 'AI Scores', desc: 'Estimated win chance, ending return, best move, and AIS rank', icon: '🤖', color: '#818cf8', category: 'metrics' },
    { key: 'mfemae', label: 'MFE and MAE', desc: 'Best and worst points during a trade, risk management', icon: '📐', color: '#ef4444', category: 'metrics' },
    { key: 'pecycle', label: 'Presidential Election Cycle', desc: 'The 4-year market rhythm, PE filtering in TradeWave', icon: '🏛️', color: '#a78bfa', category: 'advanced' },
    { key: 'daysout', label: 'Days Out and Dates', desc: 'Holding period, start date, days range filter behavior', icon: '📅', color: '#f59e0b', category: 'advanced' },
    { key: 'years', label: 'Years and Data Depth', desc: 'How many years to analyze, tradeoffs, 5 to 98 years', icon: '📚', color: '#3b82f6', category: 'advanced' },
    { key: 'watchlist', label: 'Watchlists', desc: 'Create lists, CSV import, securities filter', icon: '⭐', color: '#22c55e', category: 'advanced' },
]

const categories = [
    { key: 'start', label: 'Start Here' },
    { key: 'core', label: 'Core Features' },
    { key: 'concepts', label: 'Key Concepts' },
    { key: 'metrics', label: 'Metrics and Scores' },
    { key: 'advanced', label: 'Advanced' },
]

const HelpPanelPopup = ({ onClose }) => {
    const { UITheme, seasonalAppDivH } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [closing, setClosing] = useState(false)
    const [activeGuide, setActiveGuide] = useState(null)
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
    const hoverBg = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)'
    const mutedText = dark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.45)'
    const categoryLabelColor = dark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)'

    const popupMaxH = seasonalAppDivH ? seasonalAppDivH * 0.9 : window.innerHeight * 0.85
    const popupStyle = {
        backgroundColor: bgColor,
        color: textColor,
        maxHeight: `${popupMaxH}px`,
        position: 'fixed',
        left: '50%',
        top: '50%',
        transform: 'translate(-50%, -50%)',
    }

    const guideMap = {
        gettingstarted: GettingStartedPopup,
        opptable: OppTablePopup,
        filtering: FilteringPopup,
        barchart: BarChartPopup,
        seasonal: SeasonalPatternsPopup,
        trendchart: TrendChartPopup,
        projection: ProjectionPopup,
        sharpe: SharpeRatioPopup,
        twr: TWRPopup,
        trendscore: TrendScorePopup,
        mfemae: MFEMAEPopup,
        pecycle: PECyclePopup,
        daysout: DaysOutPopup,
        years: YearsRangePopup,
        watchlist: WatchlistPopup,
        aiscores: AIScoresPopup,
    }

    const ActiveComponent = activeGuide ? guideMap[activeGuide] : null

    return ReactDOM.createPortal(
        <>
            <div className="trend-score-overlay" onClick={handleOverlayClick}>
                <div className={`trend-score-popup${closing ? ' closing' : ''}${dark ? ' dark-scroll' : ''}`} style={popupStyle}>

                    <div className="ts-header">
                        <h2 style={{ color: textColor }}>Help and Guides</h2>
                        <button className="ts-close-btn" style={{ color: textColor }} onClick={handleClose}>&times;</button>
                    </div>

                    <div className="ts-body">

                        {/* Intro */}
                        <div style={{
                            background: dark ? 'rgba(59,130,246,0.08)' : 'rgba(59,130,246,0.05)',
                            border: `1px solid ${dark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.12)'}`,
                            borderRadius: '8px', padding: '12px 16px', marginBottom: '14px', textAlign: 'center',
                        }}>
                            <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>
                                Learn TradeWave at your own pace
                            </div>
                            <div style={{ fontSize: '11px', opacity: 0.7 }}>
                                Click any guide below to open a visual, interactive explanation.
                                New to the platform? Start with "Getting Started" at the top.
                            </div>
                        </div>

                        {/* Guide list grouped by category */}
                        {categories.map(cat => {
                            const items = guides.filter(g => g.category === cat.key)
                            return (
                                <div key={cat.key} style={{ marginBottom: '12px' }}>
                                    <div style={{
                                        fontSize: '9px', fontWeight: 700, textTransform: 'uppercase',
                                        letterSpacing: '1.2px', color: categoryLabelColor,
                                        marginBottom: '6px', paddingLeft: '4px',
                                    }}>
                                        {cat.label}
                                    </div>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                        {items.map(g => (
                                            <div
                                                key={g.key}
                                                onClick={() => setActiveGuide(g.key)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', gap: '10px',
                                                    background: cardBg, border: `1px solid ${cardBorder}`,
                                                    borderRadius: '8px', padding: '8px 12px',
                                                    cursor: 'pointer', transition: 'background 0.15s',
                                                }}
                                                onMouseEnter={e => e.currentTarget.style.background = hoverBg}
                                                onMouseLeave={e => e.currentTarget.style.background = cardBg}
                                            >
                                                <div style={{
                                                    width: '30px', height: '30px', borderRadius: '8px',
                                                    background: dark ? `${g.color}18` : `${g.color}12`,
                                                    border: `1px solid ${g.color}30`,
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    fontSize: '15px', flexShrink: 0,
                                                }}>
                                                    {g.icon}
                                                </div>
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <div style={{ fontSize: '12px', fontWeight: 600 }}>{g.label}</div>
                                                    <div style={{ fontSize: '10px', opacity: 0.6, lineHeight: 1.3, marginTop: '1px' }}>{g.desc}</div>
                                                </div>
                                                <div style={{ fontSize: '14px', opacity: 0.3, flexShrink: 0 }}>&#8250;</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )
                        })}

                        <div style={{
                            fontSize: '10px', opacity: 0.5, textAlign: 'center',
                            marginTop: '4px', paddingBottom: '4px',
                        }}>
                            You can also ask Tara any question in the chat and she will open the relevant guide automatically.
                        </div>

                    </div>
                </div>
            </div>

            {/* Render the active guide popup on top */}
            {ActiveComponent && <ActiveComponent onClose={() => setActiveGuide(null)} iconRect={null} />}
        </>,
        document.body
    )
}

export default HelpPanelPopup
