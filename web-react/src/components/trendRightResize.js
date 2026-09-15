// Duration requested by dragging the Trend Chart highlight's right edge (TW-BUG-0002).
//
// Opportunity days are inclusive calendar days, end = start + (days - 1). The drag moves
// the end by whole day positions, so the new duration is the current one plus that move.
// It is never re-derived from the overlay width: the width spans days - 1 positions and
// is cut off where the end runs past the chart, which turned a click without movement on
// a 366-day window into 351 days and a 10-day widening of a 30-day window into 39.
//
// visibleDays is how many days the grabbed edge represents when the end runs past the
// chart (the edge sits at the chart boundary, not at the real end). A leftward drag
// measures from that boundary so the result lands where the user released it. A
// rightward drag never shortens the window.
export const rightResizeDays = ({ daysOut, deltaDays, visibleDays, minDays, maxDays }) => {
    const current = Number(daysOut);
    const delta = Math.round(Number(deltaDays));
    if (!Number.isFinite(current) || !Number.isFinite(delta) || delta === 0) return current;

    const anchor = Number.isFinite(visibleDays) ? Math.min(current, visibleDays) : current;
    const requested = delta > 0
        ? Math.max(current, anchor + delta)
        : Math.min(current, anchor + delta);

    return Math.max(minDays, Math.min(maxDays, requested));
};
