const yearCount = (value) => {
  const years = parseInt(value, 10)
  if (!Number.isFinite(years) || years <= 0) return 'available history'
  return `${years} ${years === 1 ? 'year' : 'years'}`
}

export const selectedWindowProjectionLabel = (selectedYears) =>
  `Seasonal Projection (Based on Selected Window, ${yearCount(selectedYears)})`

export const allAvailableYearsProjectionLabel = (maxAvailableYears) =>
  `Seasonal Projection (All Available Years, ${yearCount(maxAvailableYears)})`

// The control must not depend on the projection data already being loaded.
// When the line is off, turning it on is what starts that fetch.
export const shouldShowAllYearsProjectionControl = ({
  projectionCapable,
  isMobile,
  selectedYears,
  maxAvailableYears,
}) => {
  const selected = parseInt(selectedYears, 10)
  const maximum = parseInt(maxAvailableYears, 10)
  return projectionCapable === true
    && isMobile !== true
    && Number.isFinite(maximum)
    && maximum > 0
    && selected !== maximum
}
