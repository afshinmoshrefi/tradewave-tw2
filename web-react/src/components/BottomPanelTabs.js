import React from 'react'

const BOTTOM_PANEL_LABELS = Object.freeze({
  trend_chart: 'Trend Chart',
  wave_stats: 'Wave Stats',
  ai_scores: 'AI Scores',
  price_chart: 'Price Chart',
})

const BottomPanelTabs = ({ slides, activeSlide, onSelect }) => (
  <nav className="bottom-panel-tabs" aria-label="Wave Viewer panels">
    <div className="bottom-panel-tabs__rail" role="tablist" aria-label="Pattern details">
      {(Array.isArray(slides) ? slides : []).map(slide => (
        <button
          key={slide}
          type="button"
          role="tab"
          aria-selected={activeSlide === slide}
          className={`bottom-panel-tabs__tab${activeSlide === slide ? ' bottom-panel-tabs__tab--active' : ''}${slide === 'ai_scores' ? ' bottom-panel-tabs__tab--ai' : ''}`}
          onClick={() => onSelect(slide)}
        >
          {BOTTOM_PANEL_LABELS[slide] || slide}
        </button>
      ))}
    </div>
  </nav>
)

export default BottomPanelTabs
