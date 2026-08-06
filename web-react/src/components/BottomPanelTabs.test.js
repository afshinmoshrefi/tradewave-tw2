import React, { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import BottomPanelTabs, { getBottomPanelId, getBottomPanelTabId } from './BottomPanelTabs'

const slides = ['trend_chart', 'wave_stats', 'ai_scores', 'price_chart']

const StatefulTabs = ({ initialSlide = 'wave_stats', onSelect = () => {} }) => {
  const [activeSlide, setActiveSlide] = useState(initialSlide)
  return (
    <BottomPanelTabs
      slides={slides}
      activeSlide={activeSlide}
      onSelect={(slide) => {
        setActiveSlide(slide)
        onSelect(slide)
      }}
    />
  )
}

test('renders labeled, keyboard-focusable tabs and marks the active panel', () => {
  render(
    <BottomPanelTabs
      slides={slides}
      activeSlide="ai_scores"
      onSelect={() => {}}
    />
  )

  expect(screen.getByRole('tab', { name: 'AI Scores' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Price Chart' })).toHaveAttribute('aria-selected', 'false')
  expect(screen.getAllByRole('tab')).toHaveLength(4)
  expect(screen.getByRole('tablist')).toHaveAttribute('aria-orientation', 'horizontal')

  const aiTab = screen.getByRole('tab', { name: 'AI Scores' })
  expect(aiTab).toHaveAttribute('tabindex', '0')
  expect(aiTab).toHaveAttribute('id', getBottomPanelTabId('ai_scores'))
  expect(aiTab).toHaveAttribute('aria-controls', getBottomPanelId('ai_scores'))
  expect(screen.getByRole('tab', { name: 'Trend Chart' })).toHaveAttribute('tabindex', '-1')
})

test('reports the semantic destination instead of a numeric index', () => {
  const onSelect = jest.fn()
  render(
    <BottomPanelTabs
      slides={['trend_chart', 'wave_stats', 'price_chart']}
      activeSlide="wave_stats"
      onSelect={onSelect}
    />
  )

  fireEvent.click(screen.getByRole('tab', { name: 'Price Chart' }))
  expect(onSelect).toHaveBeenCalledWith('price_chart')
})

test('uses roving focus and activates adjacent tabs with Left and Right arrows', () => {
  const onSelect = jest.fn()
  render(<StatefulTabs initialSlide="ai_scores" onSelect={onSelect} />)

  const aiTab = screen.getByRole('tab', { name: 'AI Scores' })
  aiTab.focus()
  fireEvent.keyDown(aiTab, { key: 'ArrowRight' })

  const priceTab = screen.getByRole('tab', { name: 'Price Chart' })
  expect(priceTab).toHaveFocus()
  expect(priceTab).toHaveAttribute('aria-selected', 'true')
  expect(priceTab).toHaveAttribute('tabindex', '0')
  expect(aiTab).toHaveAttribute('tabindex', '-1')

  fireEvent.keyDown(priceTab, { key: 'ArrowRight' })
  expect(screen.getByRole('tab', { name: 'Trend Chart' })).toHaveFocus()

  fireEvent.keyDown(screen.getByRole('tab', { name: 'Trend Chart' }), { key: 'ArrowLeft' })
  expect(screen.getByRole('tab', { name: 'Price Chart' })).toHaveFocus()
  expect(onSelect.mock.calls.map(call => call[0])).toEqual([
    'price_chart',
    'trend_chart',
    'price_chart',
  ])
})

test('Home and End move directly to the first and last tabs', () => {
  render(<StatefulTabs initialSlide="wave_stats" />)

  const statsTab = screen.getByRole('tab', { name: 'Wave Stats' })
  statsTab.focus()
  fireEvent.keyDown(statsTab, { key: 'End' })
  expect(screen.getByRole('tab', { name: 'Price Chart' })).toHaveFocus()
  expect(screen.getByRole('tab', { name: 'Price Chart' })).toHaveAttribute('aria-selected', 'true')

  fireEvent.keyDown(screen.getByRole('tab', { name: 'Price Chart' }), { key: 'Home' })
  expect(screen.getByRole('tab', { name: 'Trend Chart' })).toHaveFocus()
  expect(screen.getByRole('tab', { name: 'Trend Chart' })).toHaveAttribute('aria-selected', 'true')
})
