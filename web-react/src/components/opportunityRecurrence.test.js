const {
  resolveOpportunityRecurrence,
  resolveViewerDeepLinkOpportunityRecurrence,
} = require('./opportunityRecurrence')

const consecutiveMetadata = [
  [10, 10],
  [10, 9],
  [10, 8],
  [15, 15],
  [15, 10],
  [15, 8],
]

test('preserves the preferred recurrence when changing years and returning', () => {
  const expanded = resolveOpportunityRecurrence(consecutiveMetadata, 15, 8)
  expect(expanded).toEqual({ years: '15', partialYears: '8' })

  const restored = resolveOpportunityRecurrence(consecutiveMetadata, 10, expanded.partialYears)
  expect(restored).toEqual({ years: '10', partialYears: '8' })
})

test('uses the nearest valid recurrence instead of silently choosing the maximum', () => {
  expect(resolveOpportunityRecurrence(consecutiveMetadata, 10, 15))
    .toEqual({ years: '10', partialYears: '10' })
  expect(resolveOpportunityRecurrence(consecutiveMetadata, 12, 8))
    .toEqual({ years: '10', partialYears: '8' })
})

test('keeps consecutive and PE recurrence selections independently restorable', () => {
  const peMetadata = [
    [6, 6],
    [6, 5],
    [10, 10],
  ]

  const consecutive = resolveOpportunityRecurrence(consecutiveMetadata, 10, 8)
  const pe = resolveOpportunityRecurrence(peMetadata, 6, 6)
  const restored = resolveOpportunityRecurrence(
    consecutiveMetadata,
    consecutive.years,
    consecutive.partialYears,
  )

  expect(pe).toEqual({ years: '6', partialYears: '6' })
  expect(restored).toEqual({ years: '10', partialYears: '8' })
})

test('honors the plan years cap while resolving metadata', () => {
  expect(resolveOpportunityRecurrence(consecutiveMetadata, 15, 8, 10))
    .toEqual({ years: '10', partialYears: '8' })
})

test('keeps viewer deep-link years separate from the opportunity table recurrence', () => {
  expect(resolveViewerDeepLinkOpportunityRecurrence('6', 10, 8))
    .toEqual({ years: '10', partialYears: '8' })
})
