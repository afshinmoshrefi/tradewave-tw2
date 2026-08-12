import React, { useRef } from 'react'
import Tippy from '@tippyjs/react'

const BOTTOM_PANEL_LABELS = Object.freeze({
  trend_chart: 'Trend Chart',
  wave_stats: 'Wave Stats',
  ai_scores: 'AI Scores',
  price_chart: 'Price Chart',
})

const safeIdPart = slide => String(slide || 'unknown').replace(/[^a-z0-9_-]/gi, '-')

export const getBottomPanelTabId = slide => `bottom-panel-tab-${safeIdPart(slide)}`
export const getBottomPanelId = slide => `bottom-panel-${safeIdPart(slide)}`

const BottomPanelTabs = ({ slides, activeSlide, onSelect }) => {
  const tabRefs = useRef([])
  const availableSlides = Array.isArray(slides) ? slides : []
  const selectedIndex = Math.max(0, availableSlides.indexOf(activeSlide))
  const selectedSlide = availableSlides[selectedIndex]

  const selectAndFocus = (index) => {
    const slide = availableSlides[index]
    if (!slide) return
    if (typeof onSelect === 'function') onSelect(slide)
    const tab = tabRefs.current[index]
    if (tab && typeof tab.focus === 'function') tab.focus()
  }

  const handleKeyDown = (event, index) => {
    if (availableSlides.length === 0) return
    let nextIndex = null
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % availableSlides.length
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + availableSlides.length) % availableSlides.length
    if (event.key === 'Home') nextIndex = 0
    if (event.key === 'End') nextIndex = availableSlides.length - 1
    if (nextIndex === null) return
    event.preventDefault()
    selectAndFocus(nextIndex)
  }

  return (
    <nav className="bottom-panel-tabs" aria-label="Wave Viewer panels">
      <div
        className="bottom-panel-tabs__rail"
        role="tablist"
        aria-label="Pattern details"
        aria-orientation="horizontal"
      >
        {availableSlides.map((slide, index) => {
          const selected = selectedSlide === slide
          const label = BOTTOM_PANEL_LABELS[slide] || slide
          return (
            <Tippy
              key={slide}
              placement="top"
              content={<div theme="tw">{label}</div>}
            >
              <button
                ref={element => { tabRefs.current[index] = element }}
                id={getBottomPanelTabId(slide)}
                type="button"
                role="tab"
                aria-controls={getBottomPanelId(slide)}
                aria-selected={selected}
                tabIndex={selected ? 0 : -1}
                className={`bottom-panel-tabs__tab${selected ? ' bottom-panel-tabs__tab--active' : ''}`}
                onClick={() => onSelect && onSelect(slide)}
                onKeyDown={event => handleKeyDown(event, index)}
              >
                <span className="bottom-panel-tabs__dot" aria-hidden="true" />
                <span className="bottom-panel-tabs__label">{label}</span>
              </button>
            </Tippy>
          )
        })}
      </div>
    </nav>
  )
}

export default BottomPanelTabs
