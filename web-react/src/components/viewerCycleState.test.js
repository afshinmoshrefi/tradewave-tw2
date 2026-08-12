const { transitionViewerCycleState } = require('./viewerCycleState')

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
