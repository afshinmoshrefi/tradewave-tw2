export const EMPTY_DAY_RANGE = '-'

// Filter text is frequently pasted (from the filtering help popup, a chat
// reply, a doc, a spreadsheet) rather than typed. Pasted text carries dash
// look-alikes and invisible formatting characters that render exactly like the
// documented ASCII form, so "10-90" can look correct on screen and still miss
// every filter pattern. Fold those to their ASCII equivalent BEFORE parsing:
// otherwise the segment falls through to the ticker-shape check and is
// reported as an unknown filter the user cannot see anything wrong with.

// Zero-width and joiner characters carry no meaning here - drop them outright.
const INVISIBLE_PATTERN = /[\u200B-\u200D\u2060\uFEFF]/g

// Every hyphen/dash/minus look-alike, plus the soft hyphen (U+00AD), which is
// invisible on screen but sits exactly where a user believes a hyphen is.
const TYPOGRAPHIC_DASH_PATTERN =
  /[\u00AD\u058A\u05BE\u1400\u1806\u2010-\u2015\u2043\u2212\u2E17\u2E1A\u2E3A\u2E3B\u2E40\u301C\u3030\u30A0\uFE31\uFE32\uFE58\uFE63\uFF0D]/g

// Full-width forms arrive from IME keyboards and from spreadsheet exports.
const FULLWIDTH_PATTERN = /[\uFF01-\uFF5E]/g
const foldFullwidth = (char) => String.fromCharCode(char.charCodeAt(0) - 0xFEE0)

export const normalizeOpportunityFilterText = (filterText) => String(filterText || '')
  .replace(INVISIBLE_PATTERN, '')
  .replace(TYPOGRAPHIC_DASH_PATTERN, '-')
  .replace(FULLWIDTH_PATTERN, foldFullwidth)

const splitFilterSegments = (filterText) => normalizeOpportunityFilterText(filterText)
  .split(';')
  .map(segment => segment.trim())
  .filter(segment => segment.length > 0)

const AI_FILTER_PATTERN = /^(?:ml|ais|win|wp|predr|pmfe)\s*[><]/i
const NUMBER_PATTERN = String.raw`\d+(?:\.\d+)?`
const TICKER_SEARCH_PATTERN = /^[a-z][a-z0-9.-]{0,4}$/i
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
      // Treat the bare token as text search; adding an operator unambiguously
      // turns it into a filter command.
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

    // Bare text is intentionally limited to ticker-shaped searches. Treating
    // every unknown word as a JSON substring search hides misspelled commands
    // (for example "foobar") and can match an unrelated internal field.
    if (!TICKER_SEARCH_PATTERN.test(segment)) {
      return {
        status: 'invalid',
        segment,
        message: `Unknown filter "${segment}". Use a ticker or a documented filter command.`,
      }
    }
  }

  return { status: 'valid', segment: '', message: '' }
}

export const getOpportunityDayRange = (filterText) => {
  const segments = splitFilterSegments(filterText)

  for (const segment of segments) {
    if (!/^\d+\s*-\s*\d+$/.test(segment)) continue

    const [start, end] = segment.split('-').map(value => parseInt(value.trim(), 10))
    if (!Number.isNaN(start) && !Number.isNaN(end) && end > start) {
      // The entry day is day 1, so a typed "0-30" names the same window as
      // "1-30". Normalise it HERE, at the one place the query range is derived,
      // so every consumer sees a legal range: the engine converter, the ML
      // checkpoint context (which rejects a zero start outright), and the
      // change detection that decides whether to refetch.
      return `${Math.max(start, 1)}-${end}`
    }
  }

  return EMPTY_DAY_RANGE
}

// The table label is an inclusive calendar-day count (entry day is day 1),
// while OppList4 stores the analytics engine's zero-based daysOut value.
// Convert only at that server boundary; client filtering and telemetry keep
// the displayed calendar-day range.
export const toOpportunityEngineDayRange = (displayRange) => {
  if (displayRange === EMPTY_DAY_RANGE) return EMPTY_DAY_RANGE
  const match = String(displayRange || '').match(/^(\d+)-(\d+)$/)
  if (!match) return EMPTY_DAY_RANGE
  // The entry day is day 1, so a typed "0-30" means the same window as "1-30".
  // CLAMP that start instead of rejecting the range: returning the empty
  // sentinel left the OppList4 URL identical to the unfiltered one, the fetch
  // dedupe then skipped the request the filter had already cleared the rows
  // for, and the table sat on "Loading ..." forever.
  const start = Math.max(parseInt(match[1], 10), 1)
  const end = parseInt(match[2], 10)
  if (end < start) return EMPTY_DAY_RANGE
  return `${start - 1}-${end - 1}`
}

export const filterOpportunityRows = (rows, filterText) => {
  let filtered = Array.isArray(rows) ? rows : []
  const filters = splitFilterSegments(filterText)

  filters.forEach(segment => {
    const lowerSegment = segment.toLowerCase()
    let match

    // Sharpe Ratio: "SR>2"
    if ((match = segment.match(/^sr\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.sharpe_ratio >= threshold)
    }
    // Average Profit: "AP>10" or "AVGP>10"
    else if ((match = segment.match(/^(?:ap|avgp)\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.avg_profit >= threshold)
    }
    // Days Range: "10-40"
    else if (/^\d+\s*-\s*\d+$/.test(segment)) {
      const [start, end] = segment.split('-').map(value => parseInt(value.trim(), 10))
      filtered = filtered.filter(item => item.daysOut >= start && item.daysOut <= end)
    }
    // TradeWave Average Profit: "TWA>10"
    else if ((match = segment.match(/^twa\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.avg_profit2 >= threshold)
    }
    // TradeWave Ratio: "TWR>2"
    else if ((match = segment.match(/^twr\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.sharpe_ratio2 >= threshold)
    }
    // Trend Long: "TL>50"
    else if ((match = segment.match(/^tl\s*>\s*(\d+(?:\.\d+)?)$/i))) {
      const threshold = parseFloat(match[1])
      filtered = filtered.filter(item => item.TL !== null && item.TL >= threshold)
    }
    // Price: "price>100" or "price<50"
    else if ((match = segment.match(/^price\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.price != null && (operator === '>' ? item.price >= threshold : item.price <= threshold)
      )
    }
    // AI Score: "ML>70" or "AIS>70"
    else if ((match = segment.match(/^(?:ml|ais)\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.ml_score != null && (operator === '>' ? item.ml_score >= threshold : item.ml_score <= threshold)
      )
    }
    // Win Probability: "WIN>60" or "WP>60"; stored as 0-1.
    else if ((match = segment.match(/^(?:win|wp)\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.win_prob != null &&
        (operator === '>' ? item.win_prob * 100 >= threshold : item.win_prob * 100 <= threshold)
      )
    }
    // Predicted Return: "PREDR>5"
    else if ((match = segment.match(/^predr\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.pred_return != null &&
        (operator === '>' ? item.pred_return >= threshold : item.pred_return <= threshold)
      )
    }
    // Predicted Max Favorable Excursion: "PMFE>8"
    else if ((match = segment.match(/^pmfe\s*([><])\s*(\d+(?:\.\d+)?)$/i))) {
      const operator = match[1]
      const threshold = parseFloat(match[2])
      filtered = filtered.filter(item =>
        item.pred_mfe != null &&
        (operator === '>' ? item.pred_mfe >= threshold : item.pred_mfe <= threshold)
      )
    }
    // Default text search across all columns.
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

    // Missing values stay at the bottom in either direction.
    if (left == null && right == null) {
      return opportunityRowIdentity(leftRow).localeCompare(opportunityRowIdentity(rightRow))
    }
    if (left == null) return 1
    if (right == null) return -1

    const primary = compareOpportunityValues(left, right)
    if (primary !== 0) return primary * directionMultiplier

    // A stable identity tie-break makes repeated sorts deterministic even when
    // many rows share the same displayed value.
    return opportunityRowIdentity(leftRow).localeCompare(opportunityRowIdentity(rightRow))
  })

  return sorted
}
