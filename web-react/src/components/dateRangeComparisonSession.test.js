import {
  dateRangeDraftIsSaved,
  dateRangeKey,
  dateRangesForComparison,
  saveDateRangeDraft,
  startDateRangeSession,
  updateDateRangeSessionDraft,
} from './dateRangeComparisonSession'

test('date-range comparison starts with the current pattern and follows date nudges', () => {
  const started = startDateRangeSession({
    symbol: 'msft',
    market: 0,
    startDate: '2026-10-01',
    daysOut: 92,
  })
  expect(dateRangesForComparison(started)).toEqual([
    expect.objectContaining({ label: 'Date Range 1', start_date: '2026-10-01', days_out: 92 }),
  ])

  const nudged = updateDateRangeSessionDraft(started, {
    symbol: 'MSFT',
    market: '0',
    startDate: '2026-10-02',
    daysOut: 91,
  })
  expect(dateRangesForComparison(nudged)).toEqual([
    expect.objectContaining({ label: 'Date Range 1', start_date: '2026-10-01', days_out: 92 }),
    expect.objectContaining({ label: 'Date Range 2', start_date: '2026-10-02', days_out: 91 }),
  ])
  expect(dateRangeDraftIsSaved(nudged)).toBe(false)
})

test('saving keeps three ranges and later nudges update the third slot', () => {
  let session = startDateRangeSession({
    symbol: 'MSFT',
    market: '0',
    startDate: '2026-10-01',
    daysOut: 92,
  })
  session = saveDateRangeDraft(updateDateRangeSessionDraft(session, {
    symbol: 'MSFT', market: '0', startDate: '2026-09-15', daysOut: 108,
  }))
  session = saveDateRangeDraft(updateDateRangeSessionDraft(session, {
    symbol: 'MSFT', market: '0', startDate: '2026-09-01', daysOut: 122,
  }))
  expect(dateRangesForComparison(session)).toHaveLength(3)

  session = updateDateRangeSessionDraft(session, {
    symbol: 'MSFT', market: '0', startDate: '2026-08-15', daysOut: 139,
  })
  const ranges = dateRangesForComparison(session)
  expect(ranges).toHaveLength(3)
  expect(ranges[2]).toMatchObject({ start_date: '2026-08-15', days_out: 139 })
})

test('ticker or market changes end the date-range comparison session', () => {
  const session = startDateRangeSession({
    symbol: 'MSFT', market: '0', startDate: '2026-10-01', daysOut: 92,
  })
  expect(updateDateRangeSessionDraft(session, {
    symbol: 'NVDA', market: '0', startDate: '2026-10-01', daysOut: 92,
  })).toBeNull()
  expect(updateDateRangeSessionDraft(session, {
    symbol: 'MSFT', market: '3', startDate: '2026-10-01', daysOut: 92,
  })).toBeNull()
  expect(dateRangeKey({ start_date: '2026-10-01', days_out: 92 })).toBe('2026-10-01|92')
})

test('comparison started from an exclusion keeps the original annual-cycle cohort', () => {
  const consecutive = startDateRangeSession({
    symbol: 'HLT',
    market: '2',
    startDate: '2027-02-16',
    daysOut: 177,
    cohortAnchorStartDate: '2026-08-12',
    peCycle: 'cons',
  })
  expect(dateRangesForComparison(consecutive)[0]).toMatchObject({
    start_date: '2027-02-16',
    year_offset: -1,
  })

  const peCycle = startDateRangeSession({
    symbol: 'HLT',
    market: '2',
    startDate: '2027-02-16',
    daysOut: 177,
    cohortAnchorStartDate: '2026-08-12',
    peCycle: 'pe2',
  })
  expect(dateRangesForComparison(peCycle)[0]).toMatchObject({
    start_date: '2027-02-16',
    year_offset: 0,
  })
 
})
