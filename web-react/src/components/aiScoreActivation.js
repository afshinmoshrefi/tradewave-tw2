// Courtesy client-side dedupe for the first real AI-score view in this browser
// session. The server remains the source of truth and applies its own
// idempotent first-touch guard.
let aiScoreViewedFiredThisSession = false

const isSignedInUser = loggedinUser => {
  if (loggedinUser === null || loggedinUser === undefined || loggedinUser === false) return false
  const identity = String(loggedinUser).trim()
  return identity !== '' && identity !== '0'
}

export const recordAIScoreViewed = ({ loggedinUser, symbol, horizon } = {}) => {
  if (!isSignedInUser(loggedinUser) || aiScoreViewedFiredThisSession) return false

  aiScoreViewedFiredThisSession = true
  try {
    fetch('/api/activation/ai-score-viewed', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        detail: {
          symbol,
          horizon,
        },
      }),
      keepalive: true,
    }).catch(() => { /* fire-and-forget */ })
  } catch (e) { /* never throw from telemetry */ }

  return true
}

// Kept explicit so focused unit tests can isolate the module-level session
// guard without weakening the production dedupe contract.
export const resetAIScoreViewedForTests = () => {
  aiScoreViewedFiredThisSession = false
}
