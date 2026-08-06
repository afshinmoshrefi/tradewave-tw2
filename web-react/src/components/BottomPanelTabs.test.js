import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import BottomPanelTabs from './BottomPanelTabs'

test('renders labeled, keyboard-focusable tabs and marks the active panel', () => {
  render(
    <BottomPanelTabs
      slides={['trend_chart', 'wave_stats', 'ai_scores', 'price_chart']}
      activeSlide="ai_scores"
      onSelect={() => {}}
    />
  )

  expect(screen.getByRole('tab', { name: 'AI Scores' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByRole('tab', { name: 'Price Chart' })).toHaveAttribute('aria-selected', 'false')
  expect(screen.getAllByRole('tab')).toHaveLength(4)
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
