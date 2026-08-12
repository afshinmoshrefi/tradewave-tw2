import { AI_COLUMNS } from './opportunityAIScores'

export const OPPORTUNITY_COLUMN_VISIBILITY_KEY = 'oppTableColumnVisibility'
export const OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION_KEY = 'oppTableAIColumnDefaultsVersion'
export const OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION = 1

// Keep the opportunity table focused on historical evidence by default. AI
// readings remain available in Settings, but the user must choose to add them.
export const DEFAULT_OPPORTUNITY_COLUMN_VISIBILITY = Object.freeze({
  date: true,
  symbol: true,
  daysOut: true,
  lOrS: true,
  sharpe_ratio: true,
  avg_profit: true,
  price: true,
  ml_score: false,
  win_prob: false,
  pred_return: false,
  pred_mfe: false,
  avg_profit2: false,
  sharpe_ratio2: false,
  TL: false,
})

const isPlainPreferenceObject = value => (
  value !== null && typeof value === 'object' && !Array.isArray(value)
)

const needsAIColumnDefaultMigration = savedVersion => {
  const numericVersion = Number(savedVersion)
  return !Number.isFinite(numericVersion) || numericVersion < OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION
}

/**
 * Resolves the saved preference without touching browser storage.
 *
 * Version 1 intentionally turns every AI column off once. Earlier builds made
 * Win% and PredR visible by default, so an unversioned saved value cannot tell
 * us whether those fields were a real choice or just the old default. After
 * this one-time reset, the version marker preserves every later user choice.
 */
export const resolveOpportunityColumnVisibility = ({
  savedVisibility = null,
  savedAIColumnDefaultsVersion = null,
} = {}) => {
  const saved = isPlainPreferenceObject(savedVisibility) ? savedVisibility : {}
  const visibility = {
    ...DEFAULT_OPPORTUNITY_COLUMN_VISIBILITY,
    ...saved,
  }
  const needsMigration = needsAIColumnDefaultMigration(savedAIColumnDefaultsVersion)

  if (needsMigration) {
    AI_COLUMNS.forEach(column => {
      visibility[column] = false
    })
  }

  return {
    visibility,
    needsMigration,
    version: OPPORTUNITY_AI_COLUMN_DEFAULTS_VERSION,
  }
}
