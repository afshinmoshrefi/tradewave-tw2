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
