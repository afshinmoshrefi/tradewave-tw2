import { waveInfoRows } from './waveInfoRows';

const stats = {
  'Percent Profitable': '100.0%',
  'Sharpe Ratio': '2.15',
  'Sharpe Ratio2': '1.87',
  'SMA 50': '188.8884',
  'Trend Long': 37,
  'Trend Long1': 37,
  'Trend Short': 72,
  'Trend Short1': 69,
  'Trend Score Available': true,
};

test('Wave Info uses named engine metrics and one direction-matched trend row', () => {
  const { rows, trendIcon } = waveInfoRows(stats, 'long', true);
  expect(Object.keys(rows)).toEqual(['Percent Profitable', 'Sharpe Ratio', 'TradeWave Ratio', 'Trend Alignment']);
  expect(Object.values(rows)).toEqual(['100.0%', '2.15', '1.87', 'Against · 37/100']);
  expect(trendIcon).toBe('n');

  const short = waveInfoRows(stats, 'short', true);
  expect(short.rows['Trend Alignment']).toBe('Aligned · 72/100');
  expect(short.trendIcon).toBe('u');
});

test('TWR respects visibility and unavailable trend has no arrow', () => {
  const result = waveInfoRows({ ...stats, 'Trend Score Available': false }, 'long', false);
  expect(Object.keys(result.rows)).toEqual(['Percent Profitable', 'Sharpe Ratio', 'Trend Alignment']);
  expect(result.rows['Trend Alignment']).toBe('Unavailable');
  expect(result.trendIcon).toBe('');
});

test('provider-confirmed zero is a usable trend score', () => {
  const result = waveInfoRows({ ...stats, 'Trend Long': 0, 'Trend Long1': 0, 'Trend Short': 0, 'Trend Short1': 0 }, 'long', false);
  expect(result.rows['Trend Alignment']).toBe('Against · 0/100');
  expect(result.trendIcon).toBe('n');
});
