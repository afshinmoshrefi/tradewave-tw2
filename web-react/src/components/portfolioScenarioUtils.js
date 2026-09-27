// Keep imported rows separate: two lines for one ticker can be two positions.
export function parseHoldings(text) {
  const records = [];
  let row = [], field = '', quoted = false;
  const source = String(text || '').replace(/^\uFEFF/, '');
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '"') {
      if (quoted && source[i + 1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && (char === ',' || char === '\t')) {
      row.push(field.trim()); field = '';
    } else if (!quoted && (char === '\n' || char === '\r')) {
      row.push(field.trim()); field = '';
      if (row.some(Boolean)) records.push(row);
      row = [];
      if (char === '\r' && source[i + 1] === '\n') i++;
    } else field += char;
  }
  if (quoted) return { rows: [], errors: ['A quoted field is not closed.'] };
  row.push(field.trim());
  if (row.some(Boolean)) records.push(row);
  if (!records.length) return { rows: [], errors: ['Add at least one holding.'] };
  const normalize = value => value.toLowerCase().replace(/[\s_-]/g, '');
  const header = records[0].map(normalize);
  const symbolColumn = header.findIndex(value => ['ticker', 'symbol', 'security'].includes(value));
  const sharesColumn = header.findIndex(value => ['shares', 'quantity', 'numshares', 'amount'].includes(value));
  const categoryColumn = header.findIndex(value => ['resourceid', 'resource', 'category', 'group'].includes(value));
  const hasHeader = symbolColumn !== -1 || sharesColumn !== -1;
  const columns = { symbol: hasHeader ? symbolColumn : 0, shares: hasHeader ? sharesColumn : 1, category: hasHeader ? categoryColumn : 2 };
  if (columns.symbol < 0 || columns.shares < 0) return { rows: [], errors: ['A header needs both ticker and shares columns.'] };
  const rows = [], errors = [];
  records.slice(hasHeader ? 1 : 0).forEach((cells, index) => {
    const line = index + (hasHeader ? 2 : 1);
    const symbol = String(cells[columns.symbol] || '').trim().toUpperCase();
    const sharesText = String(cells[columns.shares] || '').trim().replace(/,/g, '');
    const resourceID = columns.category < 0 ? '' : String(cells[columns.category] || '').trim();
    if (!symbol || !/^[A-Z0-9.^_-]{1,32}$/.test(symbol)) errors.push(`Line ${line}: enter a valid ticker.`);
    if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(sharesText) || Number(sharesText) <= 0 || !Number.isFinite(Number(sharesText))) errors.push(`Line ${line}: shares must be a positive number (fractions allowed).`);
    if (cells.length > 3 && !hasHeader) errors.push(`Line ${line}: expected ticker, shares, optional category.`);
    if (symbol && /^(?:\d+(?:\.\d+)?|\.\d+)$/.test(sharesText) && Number(sharesText) > 0) rows.push({ symbol, shares: Number(sharesText), ...(resourceID ? { resourceID } : {}) });
  });
  if (rows.length > 500) errors.push('Import up to 500 rows at a time.');
  return { rows, errors };
}

export function selectScenarioRows(rows, statuses) {
  return Array.isArray(statuses) && statuses.length ? rows.filter(row => statuses.includes(String(row.status || '0'))) : rows;
}

export function repeatedTickers(rows) {
  const counts = rows.reduce((result, row) => ({ ...result, [row.symbol]: (result[row.symbol] || 0) + 1 }), {});
  return Object.entries(counts).filter(([, count]) => count > 1).map(([symbol, count]) => `${symbol} ×${count}`);
}
