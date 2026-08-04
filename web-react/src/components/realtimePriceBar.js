const finiteNumber = (value) => {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
};

export const findRealtimeQuoteForSymbol = (symbol, ...opportunityLists) => {
    const normalizedSymbol = String(symbol || '').toUpperCase();
    for (const list of opportunityLists) {
        if (!Array.isArray(list)) continue;
        const row = list.find(item => String(item?.symbol || '').toUpperCase() === normalizedSymbol);
        if (row?.realtimeQuote) return row.realtimeQuote;
    }
    return null;
};

export const getCurrentRealtimeLastPrice = (symbol, today, ...opportunityLists) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(today || ''))) return null;

    const quote = findRealtimeQuoteForSymbol(symbol, ...opportunityLists);
    const price = finiteNumber(quote?.price);
    if (!quote || quote.date !== today || price == null || price <= 0) return null;

    return [quote.date, price];
};

export const appendRealtimePriceBar = (historicalRows, quote, today) => {
    const rows = Array.isArray(historicalRows) ? historicalRows : [];
    if (!quote || quote.date !== today || !/^\d{4}-\d{2}-\d{2}$/.test(String(today || ''))) {
        return rows;
    }

    const lastRow = rows.length > 0 ? rows[rows.length - 1] : null;
    const lastDate = Array.isArray(lastRow) ? lastRow[0] : '';
    if (lastDate && lastDate >= today) return rows;

    const close = finiteNumber(quote.price);
    if (close == null || close <= 0) return rows;

    const quotedOpen = finiteNumber(quote.open);
    const quotedHigh = finiteNumber(quote.high);
    const quotedLow = finiteNumber(quote.low);
    const open = quotedOpen != null && quotedOpen > 0 ? quotedOpen : close;
    const high = Math.max(open, close, quotedHigh != null && quotedHigh > 0 ? quotedHigh : close);
    const low = Math.min(open, close, quotedLow != null && quotedLow > 0 ? quotedLow : close);
    const quotedVolume = finiteNumber(quote.volume);
    const volume = quotedVolume != null && quotedVolume >= 0 ? quotedVolume : 0;

    return [...rows, [today, open, high, low, close, volume]];
};
