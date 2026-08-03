import {
  VIEWER_CYCLE_CHANGE_EVENT,
  isViewerCycle,
  transitionViewerCycleState,
} from './viewerCycleState'

test('accepts only supported Wave Viewer cycle actions', () => {
  expect(VIEWER_CYCLE_CHANGE_EVENT).toBe('tradewave:viewer-cycle-change')
  expect(['cons', 'pe0', 'pe1', 'pe2', 'pe3'].every(isViewerCycle)).toBe(true)
  expect(isViewerCycle('pe4')).toBe(false)
  expect(isViewerCycle(undefined)).toBe(false)
})

test('cycle actions save and restore each view date and lookback', () => {
  const consecutiveView = {
    startDate: '2026-08-03',
    trendChartStartDate: '2026-05-05',
    seasonalYears: '40',
  }
  const peView = {
    startDate: '2026-08-03',
    trendChartStartDate: '2026-05-05',
    seasonalYears: '10',
  }

  const toPE = transitionViewerCycleState({
    savedStates: {},
    currentCycle: 'cons',
    nextCycle: 'pe2',
    currentView: consecutiveView,
    defaultNextView: peView,
  })
  expect(toPE.nextView).toEqual(peView)

  const backToConsecutive = transitionViewerCycleState({
    savedStates: toPE.savedStates,
    currentCycle: 'pe2',
    nextCycle: 'cons',
    currentView: peView,
    defaultNextView: peView,
  })
  expect(backToConsecutive.nextView).toEqual(consecutiveView)
  expect(backToConsecutive.savedStates.pe2).toEqual(peView)
})
