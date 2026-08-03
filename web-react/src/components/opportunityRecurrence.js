const toPositiveInteger = (value) => {
  const parsed = parseInt(value, 10)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export const resolveOpportunityRecurrence = (
  metadata,
  requestedYears,
  preferredPartialYears,
  yearsCap = null,
) => {
  const cap = toPositiveInteger(yearsCap)
  const rows = (Array.isArray(metadata) ? metadata : [])
    .map(row => ({
      years: toPositiveInteger(row && row[0]),
      partialYears: toPositiveInteger(row && row[1]),
    }))
    .filter(row =>
      row.years !== null &&
      row.partialYears !== null &&
      row.partialYears <= row.years &&
      (cap === null || row.years <= cap)
    )

  if (rows.length === 0) return null

  const availableYears = [...new Set(rows.map(row => row.years))].sort((a, b) => a - b)
  const requested = toPositiveInteger(requestedYears)
  let years = requested

  if (years === null || !availableYears.includes(years)) {
    const belowRequested = requested === null
      ? []
      : availableYears.filter(value => value <= requested)
    years = belowRequested.length > 0
      ? belowRequested[belowRequested.length - 1]
      : availableYears[0]
  }

  const availablePartialYears = [...new Set(
    rows
      .filter(row => row.years === years)
      .map(row => row.partialYears)
  )].sort((a, b) => b - a)

  const preferred = toPositiveInteger(preferredPartialYears)
  let partialYears = preferred

  if (partialYears === null || !availablePartialYears.includes(partialYears)) {
    const atOrBelowPreferred = preferred === null
      ? []
      : availablePartialYears.filter(value => value <= preferred)
    partialYears = atOrBelowPreferred.length > 0
      ? atOrBelowPreferred[0]
      : availablePartialYears[0]
  }

  return {
    years: String(years),
    partialYears: String(partialYears),
  }
}
