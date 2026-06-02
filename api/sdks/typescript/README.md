# @tradewave/sdk

Official TypeScript / JavaScript client for the **TradeWave Data API v1**.

Seasonal trading opportunities and ML win-probability signals for the 17 TradeWave
markets, plus the tracked daily AI pick. **Signals only** - the API never returns raw
prices; all movement is expressed as percentages and the seasonal curve is a normalized
0-100 index.

- Zero runtime dependencies (uses the global `fetch`; Node 18+ / 22, Deno, modern browsers)
- ESM, strict, fully typed (typed models + a raw escape hatch)
- Automatic retries with backoff on 429 / 5xx, honoring `Retry-After`
- A typed error hierarchy

## Install

```bash
npm install @tradewave/sdk
```

## Quickstart

```ts
import { TradeWave } from '@tradewave/sdk';

// apiKey falls back to process.env.TRADEWAVE_API_KEY when omitted.
const tw = new TradeWave({ apiKey: 'tw_live_...' });

// Today's AI pick as a SignalCard, with its live track record.
const pick = await tw.dailyPick();
console.log(pick.card?.headline, '-', pick.card?.verdict);

// Flagship scan - best seasonal setups entering their window now.
const scan = await tw.scan({ window: 'now', minWinRate: 0.6, limit: 5 });
for (const card of scan.opportunities ?? []) {
  console.log(`#${card.rank} ${card.symbol} ${card.signal} (edge ${card.edge_score})`);
}
```

## Configuration

```ts
const tw = new TradeWave({
  apiKey: 'tw_live_...',                 // or set TRADEWAVE_API_KEY
  baseUrl: 'https://api.tradewave.ai/v1', // override for dev: https://api-dev.trxstat.com/v1
  timeoutMs: 30000,                       // per-request timeout (default 30s)
  maxRetries: 3,                          // retries on 429 / 5xx (default 3)
});
```

## Flagship endpoints

```ts
// scan() - ranked SignalCards across your in-scope markets (default rank by sharpe).
const scan = await tw.scan({
  markets: '2,11',        // csv of ids or names; default = all in-scope
  window: 'now',          // 'now' | 'next_2_weeks' | 'next_month' | 'from..to'
  direction: 'long',
  minWinRate: 0.6,        // filter on historical_win_rate (share of profitable years)
  minYears: 5,            // trust filter
  rankBy: 'sharpe',       // edge | win_rate | sharpe | ml | avg_return
  limit: 10,
});

// analyze() - one symbol fused into one rich SignalCard + alternate setups.
const analysis = await tw.analyze('GLD', { market: '11', direction: 'long' });
console.log(analysis.card?.receipts?.per_year);
```

## Daily pick

```ts
const pick = await tw.dailyPick();
console.log(pick.card?.headline);
console.log(pick.track_record);              // live forward-tested record

const record = await tw.dailyPickTrackRecord(); // standalone realized win/loss record
console.log(record.summary, record.picks?.length);
```

## Primitives

```ts
await tw.listMarkets();                          // the 17 markets + your scope
await tw.listSymbols('2');                       // symbols in a market
await tw.opportunities({ market: '2', minWinRate: 0.6 });
await tw.opportunitiesForSymbol('AAPL', '2');
await tw.pattern('2', 'AAPL');                   // aggregate seasonal stats
await tw.seasonalChart({ market: '2', symbol: 'AAPL' }); // normalized 0-100 curve
```

## ML scoring and the graceful nudge

ML is available on every tier, **metered per day** (free 5/day, unlimited on Pro). When
the daily allowance is already spent, `score()` returns a **graceful 200 nudge** - it is
returned as data, never thrown. Use `isMLDailyLimitReached` to narrow:

```ts
import { isMLDailyLimitReached } from '@tradewave/sdk';

const result = await tw.score([
  { symbol: 'AAPL', date: '2026-07-12', days_out: 18, direction: 'long', market: '2' },
]);

if (isMLDailyLimitReached(result)) {
  console.log('Upgrade for unlimited ML -', result.message);
} else {
  console.log(`Scored ${result.granted}; remaining today:`, result.ml_remaining_today);
}
```

On SignalCards the same situation shows up as `card.ml === null` with a `card.tier_notes`
nudge - also data, never an error.

## Error handling

Non-2xx responses raise a typed error. Each carries `.status`, `.code`, and `.message`.

```ts
import {
  TradeWaveError,   // base
  AuthError,        // 401 / 403
  RateLimitError,   // 429 - carries .retryAfter (seconds)
  NotFoundError,    // 404
  ServerError,      // 5xx
} from '@tradewave/sdk';

try {
  await tw.analyze('NOPE');
} catch (err) {
  if (err instanceof RateLimitError) {
    console.error(`Rate limited; retry after ${err.retryAfter}s`);
  } else if (err instanceof AuthError) {
    console.error('Check your API key');
  } else if (err instanceof TradeWaveError) {
    console.error(`[${err.status}/${err.code}] ${err.message}`);
  }
}
```

The SDK retries 429 and 5xx automatically with exponential backoff and jitter (honoring
`Retry-After`); other 4xx are not retried.

## Raw escape hatch

The typed models tolerate extra / missing fields, but if you need the untouched JSON plus
status and rate-limit headers:

```ts
const res = await tw.raw('/scan', { query: { window: 'now' } });
console.log(res.status, res.rateLimit, res.data);
```

## Build (from source)

```bash
npm install
npm run build   # runs tsc -> dist/
```

## Safety and brand

Signals only - no raw OHLCV / last price / price-by-date. Returns are percentages, never
price levels. `order_ticket` carries no price level (side / type / TIF / dates / note
only). The `historical_win_rate` (share of profitable years) and `ml_win_prob` (the ML
model's probability) are distinct fields - never conflate them.
