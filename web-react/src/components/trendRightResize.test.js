import { rightResizeDays } from './trendRightResize';
import { incrementDate, minDaysOut, maxDaysOut } from './Common';

const limits = { minDays: minDaysOut, maxDays: maxDaysOut };

describe('rightResizeDays', () => {
    test('a press and release without movement keeps a 366-day window whose end runs past the chart', () => {
        // TW-BUG-0002 audit: Jan 1 start drawn from index 14 to the 365 boundary.
        expect(rightResizeDays({ daysOut: 366, deltaDays: 0, visibleDays: 352, ...limits })).toBe(366);
    });

    test('sub-day jitter is not a duration change', () => {
        expect(rightResizeDays({ daysOut: 366, deltaDays: 0.4, visibleDays: 352, ...limits })).toBe(366);
        expect(rightResizeDays({ daysOut: 30, deltaDays: -0.49, ...limits })).toBe(30);
    });

    test('widening a fully visible 30-day window by ten positions gives 40 inclusive days', () => {
        const days = rightResizeDays({ daysOut: 30, deltaDays: 10, ...limits });
        expect(days).toBe(40);
        expect(incrementDate('2026-05-01', days - 1)).toBe('2026-06-09');
    });

    test('narrowing and single-day moves are exact', () => {
        expect(rightResizeDays({ daysOut: 30, deltaDays: -10, ...limits })).toBe(20);
        expect(rightResizeDays({ daysOut: 30, deltaDays: 1, ...limits })).toBe(31);
        expect(rightResizeDays({ daysOut: 30, deltaDays: -1, ...limits })).toBe(29);
    });

    test('a leftward drag from a clipped edge lands where the edge was released', () => {
        // The edge sits at the chart boundary, 352 days in; ten positions left is 342 days.
        const days = rightResizeDays({ daysOut: 366, deltaDays: -10, visibleDays: 352, ...limits });
        expect(days).toBe(342);
        expect(incrementDate('2026-01-01', days - 1)).toBe('2026-12-08');
    });

    test('a rightward drag from a clipped edge never shortens the window', () => {
        expect(rightResizeDays({ daysOut: 366, deltaDays: 5, visibleDays: 352, ...limits })).toBe(366);
        expect(rightResizeDays({ daysOut: 200, deltaDays: 30, visibleDays: 180, ...limits })).toBe(210);
    });

    test('an unclipped span equal to the duration behaves like no clipping', () => {
        expect(rightResizeDays({ daysOut: 151, deltaDays: -7, visibleDays: 151, ...limits })).toBe(144);
    });

    test('keeps the minimum and maximum duration', () => {
        expect(rightResizeDays({ daysOut: 5, deltaDays: -20, ...limits })).toBe(minDaysOut);
        expect(rightResizeDays({ daysOut: 360, deltaDays: 50, ...limits })).toBe(maxDaysOut);
    });

    test('accepts the string duration the viewer sometimes carries', () => {
        expect(rightResizeDays({ daysOut: '30', deltaDays: 0, ...limits })).toBe(30);
        expect(rightResizeDays({ daysOut: '30', deltaDays: 2, ...limits })).toBe(32);
    });
});
