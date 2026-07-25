import { finiteQuoteNumber, normalizeRealtimeQuote } from './realtimePrices';

test('accepts finite numeric quote values', () => {
  expect(normalizeRealtimeQuote({ price: '137.16', change_p: '-0.25' })).toEqual({
    price: 137.16,
    change_p: -0.25,
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
  });
  expect(finiteQuoteNumber(false)).toBeNull();
});
