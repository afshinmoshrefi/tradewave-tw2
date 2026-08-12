import {
  allAvailableYearsProjectionLabel,
  selectedWindowProjectionLabel,
  shouldShowAllYearsProjectionControl,
} from './projectionLabels'

describe('projection labels', () => {
  test('describes the selected lookback window', () => {
    expect(selectedWindowProjectionLabel('30')).toBe(
      'Seasonal Projection (Based on Selected Window, 30 years)'
    )
  })

  test('describes all available history', () => {
    expect(allAvailableYearsProjectionLabel(39)).toBe(
      'Seasonal Projection (All Available Years, 39 years)'
    )
  })

  test('uses the singular form for one year', () => {
    expect(selectedWindowProjectionLabel(1)).toContain('1 year)')
  })

  test('keeps the all-years control visible before its data has loaded', () => {
    expect(shouldShowAllYearsProjectionControl({
      projectionCapable: true,
      isMobile: false,
      selectedYears: 10,
      maxAvailableYears: 39,
    })).toBe(true)
  })

  test('hides the all-years control when both projections would be identical', () => {
    expect(shouldShowAllYearsProjectionControl({
      projectionCapable: true,
      isMobile: false,
      selectedYears: 39,
      maxAvailableYears: 39,
    })).toBe(false)
  })
})
