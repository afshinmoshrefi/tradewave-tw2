export const VIEWER_CYCLE_CHANGE_EVENT = 'tradewave:viewer-cycle-change'

export const isViewerCycle = value => (
  ['cons', 'pe0', 'pe1', 'pe2', 'pe3'].includes(value)
)

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
