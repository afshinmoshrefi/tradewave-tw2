export const EMPTY_DAY_RANGE = '-'

const splitFilterSegments = (filterText) => String(filterText || '')
  .split(';')
  .map(segment => segment.trim())
  .filter(segment => segment.length > 0)

const AI_FILTER_PATTERN = /^(?:ml|ais|win|wp|predr|pmfe)\s*[><]/i
const NUMBER_PATTERN = String.raw`\d+(?:\.\d+)?`
const COMMAND_NAMES = [
  'avgp',
  'predr',
  'price',
  'pmfe',
  'ais',
  'win',
  'twa',
  'twr',
  'sr',
  'ap',
  'tl',
  'ml',
  'wp',
]
const VALID_COMMAND_PATTERNS = [
  new RegExp(`^sr\\s*>\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^(?:ap|avgp)\\s*>\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^twa\\s*>\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^twr\\s*>\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^tl\\s*>\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^price\\s*[><]\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^(?:ml|ais)\\s*[><]\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^(?:win|wp)\\s*[><]\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^predr\\s*[><]\\s*${NUMBER_PATTERN}$`, 'i'),
  new RegExp(`^pmfe\\s*[><]\\s*${NUMBER_PATTERN}$`, 'i'),
]

export const opportunityFilterUsesAI = (filterText) =>
  splitFilterSegments(filterText).some(segment => AI_FILTER_PATTERN.test(segment))

export const isOpportunityFilterPending = (filterText, mlScoresLoading) =>
  Boolean(mlScoresLoading) && opportunityFilterUsesAI(filterText)

export const analyzeOpportunityFilter = (filterText) => {
  const segments = splitFilterSegments(filterText)

  for (const segment of segments) {
    if (VALID_COMMAND_PATTERNS.some(pattern => pattern.test(segment))) continue

    if (/^\d+\s*-\s*\d+$/.test(segment)) {
      const [start, end] = segment.split('-').map(value => parseInt(value.trim(), 10))
      if (end > start) continue
      return {
        status: 'invalid',
        segment,
        message: 'The ending day must be greater than the starting day.',
      }
    }

    if (/^\d+\s*-\s*$/.test(segment)) {
      return {
        status: 'incomplete',
        segment,
        message: 'Finish the day range, for example 10-90.',
      }
    }

    const lower = segment.toLowerCase()
    const compact = lower.replace(/\s+/g, '')
    const exactCommand = COMMAND_NAMES.find(command =>
      new RegExp(`^${command}(?:\\s|[><]|$)`, 'i').test(segment)
    )
    const partialCommand = compact.length >= 2 && /^[a-z]+$/.test(compact)
      ? COMMAND_NAMES.find(command => command.startsWith(compact))
      : null

    if (exactCommand) {
      // Two-letter aliases can also be real ticker symbols (for example ML).
      // Adding an operator unambiguously turns one into a filter command.
      if (compact === exactCommand && exactCommand.length === 2) continue

      const isIncomplete =
        compact === exactCommand ||
        compact === `${exactCommand}>` ||
        compact === `${exactCommand}<`
      return {
        status: isIncomplete ? 'incomplete' : 'invalid',
        segment,
        message: isIncomplete
          ? `Finish the ${exactCommand} filter by entering a number.`
          : `Check the syntax for "${segment}".`,
      }
    }

    if (partialCommand && compact.length >= 3) {
      return {
        status: 'incomplete',
        segment,
        message: `Finish the ${partialCommand} filter.`,
      }
    }

    // Anything else remains a normal text/ticker search.
  }

  return { status: 'valid', segment: '', message: '' }
}

export const getOpportunityDayRange = (filterText) => {
  const segments = splitFilterSegments(filterText)

  for (const segment of segments) {
    if (!/^\d+\s*-\s*\d+$/.test(segment)) continue

    const [start, end] = segment.split('-').map(value => parseInt(value.trim(), 10))
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
      return `${start}-${end}`
    }
  }

  return EMPTY_DAY_RANGE
}

export const filterOpportunityRows = (rows, filterText) => {
  let filtered = Array.isArray(rows) ? rows : []
  const filters = splitFilterSegments(filterText)

  filters.forEach(segment => {
    const lowerSegment = segment.toLowerCase()
    let match

    if ((match = segment.match(/^sr\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.sharpe_ratio >= threshold)
    }
    else if ((match = segment.match(/^(?:ap|avgp)\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.avg_profit >= threshold)
    }
    else if (/^\d+\s*-\s*\d+$/.test(segment)) {
      const [start, end] = segment.split('-').map(value => parseInt(value.trim(), 10))
      filtered = filtered.filter(item => item.daysOut >= start && item.daysOut <= end)
    }
    else if ((match = segment.match(/^twa\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.avg_profit2 >= threshold)
    }
    else if ((match = segment.match(/^twr\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.sharpe_ratio2 >= threshold)
    }
    else if ((match = segment.match(/^tl\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.TL !== null && item.TL >= threshold)
    }
    else if ((match = segment.match(/^price\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.price != null && (operator === '>' ? item.price >= threshold : item.price <= threshold)
      )
    }
    else if ((match = segment.match(/^(?:ml|ais)\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.ml_score != null && (operator === '>' ? item.ml_score >= threshold : item.ml_score <= threshold)
      )
    }
    else if ((match = segment.match(/^(?:win|wp)\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.win_prob != null &&
        (operator === '>' ? item.win_prob * 100 >= threshold : item.win_prob * 100 <= threshold)
      )
    }
    else if ((match = segment.match(/^predr\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.pred_return != null &&
        (operator === '>' ? item.pred_return >= threshold : item.pred_return <= threshold)
      )
    }
    else if ((match = segment.match(/^pmfe\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.pred_mfe != null &&
        (operator === '>' ? item.pred_mfe >= threshold : item.pred_mfe <= threshold)
      )
    }
    else {
      filtered = filtered.filter(item =>
        JSON.stringify(item).toLowerCase().includes(lowerSegment)
      )
    }
  })

  return filtered
}

const compareOpportunityValues = (left, right) => {
  if (typeof left === 'number' && typeof right === 'number') {
    return left - right
  }

  const leftText = String(left)
  const rightText = String(right)
  if (leftText < rightText) return -1
  if (leftText > rightText) return 1
  return 0
}

const opportunityRowIdentity = (row) => [
  row && row.date,
  row && row.symbol,
  row && row.daysOut,
  row && row.lOrS,
].map(value => String(value == null ? '' : value)).join('|')

export const sortOpportunityRows = (rows, column, direction = 'd') => {
  const sorted = Array.isArray(rows) ? [...rows] : []
  if (!column) return sorted

  const directionMultiplier = direction === 'a' ? 1 : -1

  sorted.sort((leftRow, rightRow) => {
    const left = leftRow && leftRow[column]
    const right = rightRow && rightRow[column]

    if (left == null && right == null) {
      return opportunityRowIdentity(leftRow).localeCompare(opportunityRowIdentity(rightRow))
    }
    if (left == null) return 1
    if (right == null) return -1

    const primary = compareOpportunityValues(left, right)
    if (primary !== 0) return primary * directionMultiplier

    return opportunityRowIdentity(leftRow).localeCompare(opportunityRowIdentity(rightRow))
  })

  return sorted
}
