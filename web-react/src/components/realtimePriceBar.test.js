import {
    appendRealtimePriceBar,
    findRealtimeQuoteForSymbol,
    getCurrentRealtimeLastPrice,
} from './realtimePriceBar';

describe('appendRealtimePriceBar', () => {
    const history = [
        ['2026-07-31', 95, 97, 94, 96.31, 100000],
        ['2026-08-03', 96.2, 96.5, 95.4, 96.31, 110000],
    ];

    test('appends a genuine current-day OHLCV bar', () => {
        const result = appendRealtimePriceBar(history, {
            date: '2026-08-04',
            price: 94.88,
            open: 94.915,
            high: 94.97,
            low: 93.91,
            volume: 77921,
        }, '2026-08-04');

        expect(result).toHaveLength(3);
        expect(result[2]).toEqual(['2026-08-04', 94.915, 94.97, 93.91, 94.88, 77921]);
    });

    test('does not append a stale quote', () => {
        expect(appendRealtimePriceBar(history, {
            date: '2026-08-03',
            price: 94.88,
        }, '2026-08-04')).toBe(history);
    });

    test('does not append a completed EOD close as an intraday bar', () => {
        const quote = {
            date: '2026-08-04',
            price: 94.88,
            source: 'eod_close',
        };
        expect(appendRealtimePriceBar(history, quote, '2026-08-04')).toBe(history);
    });

    test('does not duplicate a historical row that already contains today', () => {
        const withToday = [...history, ['2026-08-04', 95, 96, 94, 95.5, 120000]];
        expect(appendRealtimePriceBar(withToday, {
            date: '2026-08-04',
            price: 95.7,
        }, '2026-08-04')).toBe(withToday);
    });

    test('keeps the candle range valid when the current price exceeds the quoted range', () => {
        const result = appendRealtimePriceBar(history, {
            date: '2026-08-04',
            price: 98,
            open: 95,
            high: 97,
            low: 94,
            volume: -1,
        }, '2026-08-04');

        expect(result[2]).toEqual(['2026-08-04', 95, 98, 94, 98, 0]);
    });
});

describe('findRealtimeQuoteForSymbol', () => {
    test('finds the selected symbol in either opportunity list', () => {
        const quote = { date: '2026-08-04', price: 94.88 };
        expect(findRealtimeQuoteForSymbol('met', [], [
            { symbol: 'MET', realtimeQuote: quote },
        ])).toBe(quote);
    });
});

describe('getCurrentRealtimeLastPrice', () => {
    const opportunities = [{
        symbol: 'MET',
        realtimeQuote: { date: '2026-08-04', price: 94.88 },
    }];

    test('returns the Opportunity Table price and date when the quote is from today', () => {
        expect(getCurrentRealtimeLastPrice('met', '2026-08-04', opportunities))
            .toEqual(['2026-08-04', 94.88]);
    });

    test('rejects a stale quote', () => {
        expect(getCurrentRealtimeLastPrice('MET', '2026-08-05', opportunities)).toBeNull();
    });

    test('rejects a completed EOD close as a current realtime price', () => {
        const eod = [{
            symbol: 'MET',
            realtimeQuote: {
                date: '2026-08-04',
                price: 94.88,
                source: 'eod_close',
            },
        }];
        expect(getCurrentRealtimeLastPrice('MET', '2026-08-04', eod)).toBeNull();
    });

    test('rejects a missing or invalid price', () => {
        const invalid = [{
            symbol: 'MET',
            realtimeQuote: { date: '2026-08-04', price: 0 },
        }];
        expect(getCurrentRealtimeLastPrice('MET', '2026-08-04', invalid)).toBeNull();
    });
});
