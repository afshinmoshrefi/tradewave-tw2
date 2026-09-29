const yearCount = (value) => {
  const years = parseInt(value, 10)
  if (!Number.isFinite(years) || years <= 0) return 'available history'
  return `${years} ${years === 1 ? 'year' : 'years'}`
}

export const selectedWindowProjectionLabel = (selectedYears) =>
  `Seasonal Projection (Based on Selected Window, ${yearCount(selectedYears)})`

export const allAvailableYearsProjectionLabel = (maxAvailableYears) =>
  `Seasonal Projection (All Available Years, ${yearCount(maxAvailableYears)})`

