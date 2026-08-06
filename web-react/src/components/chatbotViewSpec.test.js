const { isValidWaveViewerDaysOut } = require('./chatbotViewSpec')

test('keeps the inclusive 367-calendar-day Tara actuation boundary', () => {
  expect(isValidWaveViewerDaysOut(1)).toBe(true)
  expect(isValidWaveViewerDaysOut(366)).toBe(true)
  expect(isValidWaveViewerDaysOut(367)).toBe(true)
  expect(isValidWaveViewerDaysOut(368)).toBe(false)
  expect(isValidWaveViewerDaysOut(true)).toBe(false)
})
