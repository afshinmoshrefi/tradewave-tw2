import { acceptEngineProjection, alignEngineProjection, PROJECTION_METHOD } from './engineProjection';

const expected = { market: '2', symbol: 'TEST', entry_date: '2026-09-05', days_out: 30,
    years: 'pe2-2', price_date: '2026-09-04', price: 50, period_days: 4, timeframe: 'daily' };
const receipt = () => ({ status: 'ok', method: PROJECTION_METHOD,
    owner_function: 'appserver/appserver/seasonal_projection.py::build_projection',
    study: { market: '2', symbol: 'TEST', entry_date: '2026-09-05', days_out: 30, years: 'pe2-2' },
    units: { points: 'price', mean_returns: 'percent_return', side: 'underlying', price_basis: 'engine_adjusted_close' },
    years: [2018, 2022], n: 2, anchor: { date: '2026-09-04', price: 50 },
    horizon: { calendar_days: 4, timeframe: 'daily', start_date: '2026-09-04', end_date: '2026-09-07', grid: 'nominal_calendar_dates' },
    source: { price_history_sha256: 'a'.repeat(64) },
    points: [['2026-09-05', 51.123456789], ['2026-09-06', 49], ['2026-09-07', 55]] });

test('passes engine prices unchanged, including a date with a realtime candle', () => {
    const result = receipt();
    expect(acceptEngineProjection(result, expected)).toBe(result);
    const aligned = alignEngineProjection(result, ['2026-09-03', '2026-09-04', '2026-09-05'], true);
    expect(aligned.projectionData).toEqual([null, 50, 51.123456789, 49, 55]);
    expect(aligned.extraLabels).toEqual(['2026-09-06', '2026-09-07']);
});

test.each(['symbol', 'entry_date', 'years', 'market'])('rejects a stale or normalized %s', key => {
    const result = receipt();
    result.study[key] = 'different';
    expect(acceptEngineProjection(result, expected)).toBeNull();
});

test('rejects old normalized data, changed anchor, and incomplete path', () => {
    expect(acceptEngineProjection({ cons_seas_chart: [['2026-09-05', 70]] }, expected)).toBeNull();
    const result = receipt();
    result.anchor.price = 51;
    expect(acceptEngineProjection(result, expected)).toBeNull();
    result.anchor.price = 50;
    result.points.pop();
    expect(acceptEngineProjection(result, expected)).toBeNull();
});

test('hidden or unanchored illustrations do not appear on the chart', () => {
    expect(alignEngineProjection(receipt(), ['2026-09-04'], false).projectionCount).toBe(0);
    expect(alignEngineProjection(receipt(), ['2026-09-03'], true).projectionCount).toBe(0);
});
