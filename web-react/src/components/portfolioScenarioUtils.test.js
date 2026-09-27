import { parseHoldings, repeatedTickers, selectScenarioRows } from './portfolioScenarioUtils';

test('CSV import preserves fractional quantities, quoted commas and separate repeated tickers', () => {
  const parsed = parseHoldings('ticker,shares,category\nAAPL,.5,0\nAAPL,"1,000.25",0\nSPY,2,11');
  expect(parsed.errors).toEqual([]);
  expect(parsed.rows).toEqual([
    { symbol: 'AAPL', shares: 0.5, resourceID: '0' },
    { symbol: 'AAPL', shares: 1000.25, resourceID: '0' },
    { symbol: 'SPY', shares: 2, resourceID: '11' }
  ]);
  expect(repeatedTickers(parsed.rows)).toEqual(['AAPL ×2']);
});

test('invalid quantity blocks the entire import and none of its rows are silently accepted', () => {
  const parsed = parseHoldings('ticker,shares\nAAPL,1.25\nMSFT,-2');
  expect(parsed.errors).toContain('Line 3: shares must be a positive number (fractions allowed).');
});

test('clearing color selection includes every row, including zero shares for explicit correction', () => {
  const rows = [{ symbol: 'AAPL', status: '0', num_shares: '0' }, { symbol: 'SPY', status: '3', num_shares: '2.5' }];
  expect(selectScenarioRows(rows, [])).toEqual(rows);
  expect(selectScenarioRows(rows, ['0'])).toEqual([rows[0]]);
  expect(selectScenarioRows(rows, ['0', '3'])).toEqual(rows);
});
