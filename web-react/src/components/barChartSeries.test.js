import { buildBarChartSeries } from './barChartSeries';

describe('buildBarChartSeries', () => {
  const colors = { green: 'green', red: 'red' };

  test('keeps excursion data aligned when zero placeholders precede real history', () => {
    const rows = [
      { year: 1927, pct: '0,0,0' },
      { year: 1928, pct: '0,0,0' },
      { year: 1985, pct: '5,7,-2' },
      { year: 1986, pct: '-3,1,-5' },
    ];

    const series = buildBarChartSeries(rows, colors);

    expect(series.labels).toEqual([1927, 1928, 1985, 1986]);
    expect(series.main).toEqual([0, 0, 5, -3]);
    expect(series.upperRemainders).toEqual([null, null, 2, 1]);
    expect(series.lowerRemainders).toEqual([null, null, -2, -2]);
    expect(series.mainColors).toEqual(['green', 'green', 'green', 'red']);
    expect(series.upperRemainders).toHaveLength(series.labels.length);
    expect(series.lowerRemainders).toHaveLength(series.labels.length);
  });

  test('uses null placeholders for missing excursion values without shifting years', () => {
    const series = buildBarChartSeries(
      [{ year: 2024, pct: '2' }, { year: 2025, pct: '' }],
      colors,
    );

    expect(series.main).toEqual([2, null]);
    expect(series.upperRemainders).toEqual([null, null]);
    expect(series.lowerRemainders).toEqual([null, null]);
  });
});
