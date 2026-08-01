const {
  VIEWER_CYCLE_CHANGE_EVENT,
  isViewerCycle,
  transitionViewerCycleState,
} = require('./viewerCycleState')

test('accepts only supported Wave Viewer cycle actions', () => {
  expect(VIEWER_CYCLE_CHANGE_EVENT).toBe('tradewave:viewer-cycle-change')
  expect(['cons', 'pe0', 'pe1', 'pe2', 'pe3'].every(isViewerCycle)).toBe(true)
  expect(isViewerCycle('pe4')).toBe(false)
  expect(isViewerCycle(undefined)).toBe(false)
})

test('restores the exact consecutive view after inspecting a PE cycle', () => {
  const consecutive = {
    startDate: '2026-07-24',
    trendChartStartDate: '2026-07-10',
    seasonalYears: '10',
  }
  const peDefault = {
    startDate: '2028-07-24',
    trendChartStartDate: '2028-07-10',
    seasonalYears: '10',
  }

  const toPE = transitionViewerCycleState({
    savedStates: {},
    currentCycle: 'cons',
    nextCycle: 'pe0',
    currentView: consecutive,
    defaultNextView: peDefault,
  })
  expect(toPE.nextView).toEqual(peDefault)

  const peAdjustedByMetadata = {
    ...toPE.nextView,
    seasonalYears: '6',
  }
  const backToConsecutive = transitionViewerCycleState({
    savedStates: toPE.savedStates,
    currentCycle: 'pe0',
    nextCycle: 'cons',
    currentView: peAdjustedByMetadata,
    defaultNextView: peAdjustedByMetadata,
  })

  expect(backToConsecutive.nextView).toEqual(consecutive)
})

test('remembers separate settings for each PE cycle', () => {
  const fromPE1 = transitionViewerCycleState({
    savedStates: {
      cons: { startDate: '2026-07-24', trendChartStartDate: '2026-07-10', seasonalYears: '10' },
    },
    currentCycle: 'pe1',
    nextCycle: 'pe2',
    currentView: { startDate: '2029-07-24', trendChartStartDate: '2029-07-10', seasonalYears: '5' },
    defaultNextView: { startDate: '2030-07-24', trendChartStartDate: '2030-07-10', seasonalYears: '5' },
  })

  const backToPE1 = transitionViewerCycleState({
    savedStates: fromPE1.savedStates,
    currentCycle: 'pe2',
    nextCycle: 'pe1',
    currentView: fromPE1.nextView,
    defaultNextView: fromPE1.nextView,
  })

  expect(backToPE1.nextView).toEqual({
    startDate: '2029-07-24',
    trendChartStartDate: '2029-07-10',
    seasonalYears: '5',
  })
})
