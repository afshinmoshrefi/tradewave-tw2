/**
 * @tradewave/sdk - the official TypeScript client for the TradeWave Data API v1.
 *
 * Seasonal trading patterns and ML win-probability estimates for the 15 TradeWave
 * markets, plus the tracked daily AI pick. Derived data only - no raw prices.
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
  Bias,
  RankBy,
  TrendDirection,
  YearResult,
  PickResult,
  Market,
  Me,
  Symbol,
  MarketRef,
  MLScore,
  PatternCardML,
  Opportunity,
  OpportunityList,
  PatternSetup,
  PatternStats,
  YearReturn,
  PerYearReturn,
  CurveSummary,
  TrackRecordSummary,
  Receipts,
  OrderTicket,
  SetReminder,
  NextStep,
  PatternCard,
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
