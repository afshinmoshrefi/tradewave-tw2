// Presentation only. TradeWave's engine owns every price/return calculation.
export const PROJECTION_METHOD = 'mean_historical_price_returns_v1';
const iso = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
const positive = value => typeof value === 'number' && Number.isFinite(value) && value > 0;

export function acceptEngineProjection(result, expected) {
    const s = result?.study;
    const h = result?.horizon;
    if (result?.status !== 'ok' || result.method !== PROJECTION_METHOD ||
        result.owner_function !== 'appserver/appserver/seasonal_projection.py::build_projection' ||
        result.units?.points !== 'price' || result.units?.mean_returns !== 'percent_return' ||
        result.units?.side !== 'underlying' || result.units?.price_basis !== 'engine_adjusted_close' ||
        s?.market !== String(expected.market) || s?.symbol !== expected.symbol ||
        s?.entry_date !== expected.entry_date || s?.days_out !== Number(expected.days_out) ||
        s?.years !== expected.years || result.anchor?.date !== expected.price_date ||
        result.anchor?.price !== Number(expected.price) ||
        h?.calendar_days !== Number(expected.period_days) || h?.timeframe !== expected.timeframe ||
        h?.start_date !== expected.price_date || h?.grid !== 'nominal_calendar_dates' ||
        !iso(h?.end_date) || !positive(result.anchor?.price) ||
        !Array.isArray(result.years) || !result.years.length || result.n !== result.years.length ||
        result.years.some((year, i) => !Number.isInteger(year) || (i > 0 && year <= result.years[i - 1])) ||
        !/^[0-9a-f]{64}$/.test(result.source?.price_history_sha256 || '') ||
        !Array.isArray(result.points) || !result.points.length) return null;
    let previous = result.anchor.date;
    for (const point of result.points) {
        if (!Array.isArray(point) || point.length !== 2 || !iso(point[0]) ||
            point[0] <= previous || point[0] > h.end_date || !positive(point[1])) return null;
        previous = point[0];
    }
    if (previous !== h.end_date) return null;
    return result;
}

export function alignEngineProjection(result, labels, enabled) {
    const empty = { extraLabels: [], projectionData: [], projectionCount: 0 };
    if (!enabled || !result || !labels.length || !labels.includes(result.anchor.date)) return empty;
    const values = new Map([[result.anchor.date, result.anchor.price], ...result.points]);
    const extraLabels = result.points.map(point => point[0]).filter(date => date > labels[labels.length - 1]);
    if (!extraLabels.length) return empty;
    return { extraLabels, projectionCount: extraLabels.length,
        projectionData: [...labels, ...extraLabels].map(date => values.get(date) ?? null) };
}
