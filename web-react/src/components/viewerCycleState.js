export const transitionViewerCycleState = ({
  savedStates,
  currentCycle,
  nextCycle,
  currentView,
  defaultNextView,
}) => {
  const states = {
    ...(savedStates || {}),
    [currentCycle]: { ...currentView },
  }

  return {
    savedStates: states,
    nextView: states[nextCycle]
      ? { ...states[nextCycle] }
      : { ...defaultNextView },
  }
}

export const VIEWER_CYCLE_CHANGE_EVENT = 'tradewave:viewer-cycle-change'

export const isViewerCycle = value => (
  ['cons', 'pe0', 'pe1', 'pe2', 'pe3'].includes(value)
)

export const peCycleForYear = (year) => {
  const numericYear = Number(year)
  if (!Number.isInteger(numericYear)) return ''
  return `pe${((numericYear % 4) + 4) % 4}`
}

export const peCycleAfterYearDelta = (selectedCycle, yearDelta) => {
  const cycle = String(selectedCycle || 'cons').toLowerCase()
  if (!/^pe[0-3]$/.test(cycle)) return cycle

  const delta = Number(yearDelta)
  if (!Number.isInteger(delta)) return cycle
  const currentPhase = Number(cycle.slice(2))
  return `pe${((currentPhase + delta) % 4 + 4) % 4}`
}

export const isNonCurrentPECycle = (selectedCycle, currentYear) => {
  const cycle = String(selectedCycle || 'cons').toLowerCase()
  if (!/^pe[0-3]$/.test(cycle)) return false
  return cycle !== peCycleForYear(currentYear)
}

export const lineChartYearAfterPatternLoad = ({
  selectedCycle,
  currentYear,
  entryDate,
  lastBarYear,
}) => {
  if (isNonCurrentPECycle(selectedCycle, currentYear)) {
    const entryYear = Number(String(entryDate || '').slice(0, 4))
    if (Number.isInteger(entryYear)) return entryYear
  }
  return lastBarYear
}
