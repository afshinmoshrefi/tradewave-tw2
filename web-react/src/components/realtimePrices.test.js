import { finiteQuoteNumber, normalizeRealtimeQuote } from './realtimePrices';

test('accepts finite numeric quote values', () => {
  expect(normalizeRealtimeQuote({ price: '137.16', change_p: '-0.25' })).toEqual({
    price: 137.16,
    change_p: -0.25,
    open: null,
    high: null,
    low: null,
    volume: null,
    timestamp: null,
    date: '',
  });
});

test.each(['NA', 'NaN', Infinity, -Infinity, null, undefined, 0, -2])(
  'rejects an unusable price: %p',
  (price) => {
    expect(normalizeRealtimeQuote({ price, change_p: 1 })).toBeNull();
  },
);

test('retains a valid price but removes an unusable percentage change', () => {
  expect(normalizeRealtimeQuote({ price: 10, change_p: 'NA' })).toEqual({
    price: 10,
    change_p: null,
    open: null,
    high: null,
    low: null,
    volume: null,
    timestamp: null,
    date: '',
  });
  expect(finiteQuoteNumber(false)).toBeNull();
});

test('preserves a complete valid quote for price-chart and stats consumers', () => {
  expect(normalizeRealtimeQuote({
    price: '137.16',
    change_p: '-0.25',
    open: '136.40',
    high: '138.10',
    low: '135.90',
    volume: '1250000',
    timestamp: '1785859200',
    date: '2026-08-04',
  })).toEqual({
    price: 137.16,
    change_p: -0.25,
    open: 136.4,
    high: 138.1,
    low: 135.9,
    volume: 1250000,
    timestamp: 1785859200,
    date: '2026-08-04',
  });
});

test('preserves a completed-close source label without treating it as realtime', () => {
  expect(normalizeRealtimeQuote({
    price: '159.12',
    change_p: '0.8',
    date: '2026-08-05',
    source: 'eod_close',
  })).toMatchObject({
    price: 159.12,
    change_p: 0.8,
    date: '2026-08-05',
    source: 'eod_close',
  });
});
