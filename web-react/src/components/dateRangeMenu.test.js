import { analysisActionsMenu, monthsAndQtrs, monthsAndQtrsMenu } from './Common'

describe('Wave Viewer date-range controls', () => {
  test('keeps action calculations available but removes actions from the menu', () => {
    expect(monthsAndQtrs.some((option) => option.value === 'Buy & Hold')).toBe(true)
    expect(monthsAndQtrs.some((option) => option.value === 'Reverse Date Range')).toBe(true)
    expect(monthsAndQtrsMenu.some((option) => option.value === 'Buy & Hold')).toBe(false)
    expect(monthsAndQtrsMenu.some((option) => option.value === 'Reverse Date Range')).toBe(false)
  })

  test('uses a hidden menu heading instead of an actionable first item', () => {
    expect(monthsAndQtrsMenu[0]).toMatchObject({
      value: 'Months & Qtrs',
      label: 'Months & Qtrs',
      hidden: true,
    })
  })

  test('groups current pattern commands under the Analysis heading', () => {
    expect(analysisActionsMenu[0]).toMatchObject({
      value: 'Analysis',
      label: 'Analysis',
      hidden: true,
    })
    expect(analysisActionsMenu.slice(1)).toEqual([
      expect.objectContaining({ value: 'Compare Symbols' }),
      expect.objectContaining({ value: 'Compare Date Ranges', label: 'Compare Date Ranges...' }),
      expect.objectContaining({ value: 'Buy & Hold', label: 'Buy & Hold' }),
      expect.objectContaining({ value: 'Reverse Date Range', label: 'Exclude Current Range' }),
    ])
  })
})
