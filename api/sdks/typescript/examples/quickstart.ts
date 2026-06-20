/**
 * TradeWave SDK quickstart (TypeScript / ESM).
 *
 * Run after building the SDK:
 *   npm install && npm run build
 *   TRADEWAVE_API_KEY=tw_live_... npx tsx examples/quickstart.ts
 *
 * (Or import from '@tradewave/sdk' once installed in your own project.)
 */

import {
  TradeWave,
  TradeWaveError,
  RateLimitError,
  AuthError,
  isMLDailyLimitReached,
} from '../src/index.js';

async function main(): Promise<void> {
  // apiKey falls back to process.env.TRADEWAVE_API_KEY when omitted.
  const tw = new TradeWave({ apiKey: process.env.TRADEWAVE_API_KEY });

  try {
    // 1. The daily AI pick as a PatternCard, with its live track record.
    const pick = await tw.dailyPick();
    console.log('Daily pick:', pick.card?.headline);
    console.log('Verdict:', pick.card?.verdict);
    if (pick.track_record) {
      console.log(
        `Live record: ${pick.track_record.win_count}/${pick.track_record.count} wins`,
      );
    }

    // 2. Flagship scan - best seasonal setups entering their window now.
    const scan = await tw.scan({ window: 'now', minWinRate: 0.6, limit: 5 });
    console.log(`\nScan found ${scan.count} setups (window=${scan.window}):`);
    for (const card of scan.opportunities ?? []) {
      console.log(
        `  #${card.rank} ${card.symbol} ${card.bias} - ` +
          `edge ${card.edge_score}, win ${card.stats?.historical_win_rate}`,
      );
    }

    // 3. Deep-dive one symbol.
    const analysis = await tw.analyze('GLD', { market: '11' });
    console.log('\nAnalyze GLD:', analysis.card?.headline);
    console.log('Other setups:', analysis.other_setups?.length ?? 0);

    // 4. ML scoring - the daily-limit nudge is data, not an error.
    const scores = await tw.score([
      { symbol: 'AAPL', date: '2026-07-12', days_out: 18, direction: 'long', market: '2' },
    ]);
    if (isMLDailyLimitReached(scores)) {
      console.log('\nML daily limit reached -', scores.message);
    } else {
      console.log(`\nScored ${scores.granted} item(s); remaining today:`, scores.ml_remaining_today);
    }
  } catch (err) {
    if (err instanceof AuthError) {
      console.error('Auth failed - check your API key.');
    } else if (err instanceof RateLimitError) {
      console.error(`Rate limited; retry after ${err.retryAfter ?? '?'}s.`);
    } else if (err instanceof TradeWaveError) {
      console.error(`TradeWave error [${err.status}/${err.code ?? 'n/a'}]:`, err.message);
    } else {
      throw err;
    }
  }
}

main();
