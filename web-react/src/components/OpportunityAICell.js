import React from 'react'
import { CellSpinner } from './Common'
import {
  AI_METRICS,
  formatOpportunityAIMetric,
  opportunityAICompactStatus,
  opportunityAIIsUnavailable,
  opportunityVixCompactLabel,
} from './opportunityAIScores'

// AI cells are intentionally quiet. The selected opportunity's full explanation,
// history evidence, and time-length comparison live in the AI Scores panel.
const OpportunityAICell = ({ bundle, metric, symbol, grouped = false }) => {
  const metadata = AI_METRICS[metric]
  const display = bundle && bundle.display
  const state = display ? display.status : 'unavailable'

  if (!metadata || opportunityAIIsUnavailable(display)) {
    const isVixWarning = state === 'unavailable' && display?.reason?.trim().toLowerCase() === 'vix_blocked'
    const compactState = isVixWarning ? opportunityVixCompactLabel(display) : opportunityAICompactStatus(display)
    const ReasonText = isVixWarning ? 'mark' : 'span'
    const label = grouped ? 'AI scores' : metadata?.label || 'AI score'
    return (
      <ReasonText
        className="opp-ai-cell opp-ai-cell--unavailable"
        aria-label={`${label} unavailable for ${symbol || 'this pattern'}. ${compactState}. Select the row and open AI Scores for details.`}
      >
        {compactState}
      </ReasonText>
    )
  }

  if (state === 'loading') {
    return (
      <span
        className="opp-ai-cell opp-ai-cell--loading"
        aria-label={`Loading ${metadata.label} for ${symbol || 'this pattern'}`}
      >
        <CellSpinner />
      </span>
    )
  }

  const formatted = formatOpportunityAIMetric(metric, display.metrics[metric])
  return (
    <span
      className="opp-ai-cell opp-ai-cell--available"
      aria-label={`${metadata.label} ${formatted} for ${symbol || 'this pattern'}. Select the row and open AI Scores for details.`}
    >
      {formatted}
    </span>
  )
}

export default OpportunityAICell
