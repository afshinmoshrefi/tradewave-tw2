/**
 * @tradewave/sdk - the official TypeScript client for the TradeWave Data API v1.
 *
 * Seasonal trading opportunities and ML win-probability signals for the 17 TradeWave
 * markets, plus the tracked daily AI pick. Signals only - no raw prices.
 *
 *   import { TradeWave } from '@tradewave/sdk';
 *   const tw = new TradeWave({ apiKey: 'tw_live_...' });
 *   const scan = await tw.scan({ window: 'now', minWinRate: 0.6 });
 *   const pick = await tw.dailyPick();
 */

export { TradeWave, DEFAULT_BASE_URL } from './client.js';
export type {
  TradeWaveOptions,
  ScanParams,
  AnalyzeParams,
  OpportunitiesParams,
  SeasonalChartParams,
} from './client.js';

export { SDK_VERSION } from './http.js';

export {
  TradeWaveError,
  AuthError,
  RateLimitError,
  NotFoundError,
  ServerError,
} from './errors.js';

export { isMLDailyLimitReached } from './models.js';

export type {
  Direction,
  Signal,
  RankBy,
  TrendDirection,
  YearResult,
  PickResult,
  Market,
  Me,
  Symbol,
  MarketRef,
  MLScore,
  SignalCardML,
  Opportunity,
  OpportunityList,
  SignalSetup,
  SignalStats,
  YearReturn,
  PerYearReturn,
  CurveSummary,
  TrackRecordSummary,
  Receipts,
  OrderTicket,
  SetReminder,
  NextStep,
  SignalCard,
  ScanResult,
  CompactSetup,
  AnalyzeResult,
  DailyPickResult,
  TrackRecordPick,
  TrackRecord,
  Pattern,
  SeasonalCurvePoint,
  SeasonalChart,
  ScoreInput,
  ScoredItem,
  ScoreResult,
  MLDailyLimitReached,
  ScoreResponse,
} from './models.js';
