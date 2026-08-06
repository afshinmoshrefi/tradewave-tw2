export const isValidWaveViewerDaysOut = value => (
  Number.isInteger(value) && value >= 1 && value <= 367
)
