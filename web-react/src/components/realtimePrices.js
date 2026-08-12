export const finiteQuoteNumber = (value, { positive = false } = {}) => {
  if (value === null || value === undefined || typeof value === 'boolean') return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  if (positive && number <= 0) return null;
  return number;
};

export const normalizeRealtimeQuote = (quote) => {
  if (!quote || typeof quote !== 'object') return null;
  const price = finiteQuoteNumber(quote.price, { positive: true });
  if (price === null) return null;
  const normalized = {
    price,
    change_p: finiteQuoteNumber(quote.change_p),
    open: finiteQuoteNumber(quote.open),
    high: finiteQuoteNumber(quote.high),
    low: finiteQuoteNumber(quote.low),
    volume: finiteQuoteNumber(quote.volume),
    timestamp: finiteQuoteNumber(quote.timestamp),
    date: typeof quote.date === 'string' ? quote.date : '',
  };
  if (quote.source === 'eod_close') normalized.source = 'eod_close';
  return normalized;
};
