// Parse before changing any viewer state; malformed links must not leave a
// partially applied market/date/window or crash while reading missing fields.
export function parseViewerPatternLink(search, resources) {
  const query = new URLSearchParams(search)
  const encoded = query.get('o')
  if (!encoded) return null
  let fields
  try { fields = window.atob(encoded).split('|') } catch (_) { return null }
  if (fields.length !== 5) return null
  const [market, rawSymbol, date, days, rawYears] = fields
  const resource = resources[market]
  const symbol = rawSymbol.toUpperCase()
  const years = rawYears.toLowerCase()
  if (!resource || !/^[A-Z0-9.-]{1,15}$/.test(symbol)) return null
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null
  const parsed = new Date(date + 'T00:00:00Z')
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0,10) !== date) return null
  if (!/^\d+$/.test(days) || Number(days) < 1 || Number(days) > 367) return null
  // Viewer history can exceed the public API's 99-year limit (long index
  // histories). The engine and market metadata enforce the actual entitlement.
  if (!/^(?:pe[0-3](?:-[1-9]\d{0,2})?|[1-9]\d{0,2})$/.test(years)) return null
  const rawDirection = (query.get('direction') || '').toLowerCase()
  if (rawDirection && !['long', 'short'].includes(rawDirection)) return null
  return {market, resource, symbol, date, days: String(Number(days)), years,
    direction: rawDirection || null}
}

export function linkedPatternDirection(link, current) {
  if (!link) return null
  const fields = ['resource', 'symbol', 'date', 'days', 'years']
  return fields.every(key => String(link[key]) === String(current[key])) ? link.direction : null
}

export function includeSelectedWindowOption(options, value, maximum) {
  const selected = Number(value)
  if (!Number.isInteger(selected) || selected < 1 || selected > maximum
      || options.some(option => Number(option.value) === selected)) return options
  // A controlled select otherwise displays its first option even while the
  // chart correctly uses a smaller custom analysis window from the API.
  return [{id:selected,value:String(selected),label:String(selected)}, ...options]
}
