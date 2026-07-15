/**
 * Typed models for the TradeWave Data API v1.
 *
 * These mirror api/openapi.yaml components + api/PATTERNCARD_SPEC.md. They are exported
 * interfaces (not classes); the client returns plain parsed JSON typed against them.
 *
 * SAFETY: derived data only. The API never returns raw prices - there are no price fields
 * here. All movement is expressed as percentages (fields ending in _pct) or as the
 * 0-100 normalized seasonal index.
 *
 * Power-user escape hatch: every response is also a plain JSON object, so unknown or
 * lagging fields are reachable even when not yet typed here. Fields are marked optional
 * defensively so a server-side addition or a degraded row never breaks the types.
 */

export type Direction = 'long' | 'short';
export type Bias = 'bullish' | 'bearish' | 'neutral';
export type RankBy = 'edge' | 'win_rate' | 'sharpe' | 'ml' | 'avg_return';
export type TrendDirection = 'rising' | 'falling' | 'flat';
export type YearResult = 'win' | 'loss';
export type PickResult = 'win' | 'loss' | 'open';

/** A TradeWave market (permanent resource key '0'..'16'). */
export interface Market {
  id: string;
  name: string;
  ml_eligible?: boolean;
  /** Whether this market is in the caller's tier scope. */
  in_scope?: boolean;
  [key: string]: unknown;
}

/** A tradeable symbol within a market. */
export interface Symbol {
  symbol: string;
  name?: string;
  [key: string]: unknown;
}

/** Compact market reference embedded in a PatternCard. */
export interface MarketRef {
  id: string;
  name: string;
  [key: string]: unknown;
}

/**
 * Response envelope for GET /me - identity + capabilities for the caller's key.
 * ml_remaining_today / ml_daily_limit are null when unlimited.
 */
export interface Me {
  /** Opaque, non-secret account equality id used for MCP session admission. */
  mcp_admission_id?: string;
  tier?: string;
  tier_name?: string;
  /** ML calls remaining today (null = unlimited; 0 = daily limit reached). */
  ml_remaining_today?: number | null;
  ml_daily_limit?: number | null;
  /** Max rows per call on the plan. */
  opp_limit?: number;
  /** The plan's rate limits (per_minute / per_day). */
  rate?: { per_minute?: number; per_day?: number; [key: string]: unknown };
  markets_in_scope?: Market[];
  upgrade_url?: string;
  [key: string]: unknown;
}

/**
 * Legacy ML block (used by POST /score and bulk GET /opportunities).
 * Note the legacy names: win_prob, pred_return, pred_mfe.
 * win_prob is the model probability and is DISTINCT from historical win_rate.
 */
export interface MLScore {
  ml_score?: number;
  win_prob?: number;
  pred_return?: number;
  pred_mfe?: number;
  /** Present only on unscored items beyond the daily ML allowance. */
  note?: string;
  [key: string]: unknown;
}

/**
 * PatternCard ML block (used on cards from /scan, /analyze, /daily-pick).
 * Names DIFFER from the legacy MLScore: ml_win_prob, pred_return_pct, pred_mfe_pct.
 * ml_win_prob is the model probability and is DISTINCT from historical_win_rate.
 */
export interface PatternCardML {
  ml_score?: number;
  ml_win_prob?: number;
  pred_return_pct?: number;
  pred_mfe_pct?: number;
  [key: string]: unknown;
}

/** A single ranked seasonal setup (bulk /opportunities primitive). Percentages, never prices. */
export interface Opportunity {
  symbol?: string;
  market?: string;
  direction?: Direction;
  entry_date?: string;
  days_out?: number;
  sharpe_ratio?: number;
  avg_profit_pct?: number;
  median_profit_pct?: number;
  /** REAL historical win rate (share of profitable years), 0..1. May be null past the enrichment cap. */
  win_rate?: number | null;
  /** Lookback window label - stays a string. */
  years?: string;
  /** null unless ML-eligible market within the daily allowance. Legacy field names. */
  ml?: MLScore | null;
  [key: string]: unknown;
}

/** Response envelope for GET /opportunities (single entry-date primitive). */
export interface OpportunityList {
  entry_date?: string;
  /** Always false here - /opportunities does not widen across a window; use /scan. */
  window_supported?: boolean;
  evaluated_count?: number;
  enrichment_capped?: boolean;
  /** ML calls remaining today (null = unlimited; 0 = daily limit reached). */
  ml_remaining_today?: number | null;
  opportunities?: Opportunity[];
  [key: string]: unknown;
}

/** Setup timing. Dates only - no price levels. */
export interface PatternSetup {
  entry_date?: string;
  entry_window?: string;
  hold_days?: number;
  exit_date?: string;
  [key: string]: unknown;
}

/** Headline percent-only stats on a PatternCard. No price levels. */
export interface PatternStats {
  /** 0..1, share of profitable years. DISTINCT from ml.ml_win_prob. */
  historical_win_rate?: number;
  sharpe_ratio?: number;
  avg_return_pct?: number;
  median_return_pct?: number;
  /** Lookback label - stays a string. */
  years?: string;
  [key: string]: unknown;
}

/** One year's realized return. */
export interface YearReturn {
  year?: string;
  return_pct?: number;
  [key: string]: unknown;
}

/** One per-year evidence row in receipts. */
export interface PerYearReturn {
  year?: string;
  return_pct?: number;
  /** 'win' if return_pct > 0 (no threshold, matches the UI). */
  result?: YearResult;
  [key: string]: unknown;
}

/** Shape summary of the HOLD section (entry to exit) of the seasonal curve. */
export interface CurveSummary {
  shape?: string;
  trend?: TrendDirection;
  change_pts?: number;
  /** Day INTO the hold (0 = entry) where the index peaks. */
  peak_day?: number;
  /** Day INTO the hold (0 = entry) where the index troughs. */
  trough_day?: number;
  [key: string]: unknown;
}

/** Live forward-tested record of past daily picks. */
export interface TrackRecordSummary {
  count?: number;
  win_count?: number;
  /** 0..1 realized win rate of past picks. */
  win_rate?: number;
  avg_return_pct?: number;
  note?: string;
  [key: string]: unknown;
}

/** The trust layer - per-year historical evidence. Always present on a BUY/SELL. */
export interface Receipts {
  years_tested?: number;
  wins?: number;
  losses?: number;
  historical_win_rate?: number;
  avg_return_pct?: number;
  median_return_pct?: number;
  best_year?: YearReturn;
  worst_year?: YearReturn;
  per_year?: PerYearReturn[];
  curve_summary?: CurveSummary | null;
  source?: string;
  as_of?: string;
  /** ONLY on the daily-pick card - the live forward-tested record. Absent on /scan and /analyze. */
  live_track_record?: TrackRecordSummary | null;
  [key: string]: unknown;
}

/** Broker-agnostic order ticket. Carries NO price level. */
export interface OrderTicket {
  side?: 'BUY' | 'SELL';
  symbol?: string;
  type?: string;
  time_in_force?: string;
  suggested_entry_date?: string;
  suggested_exit_date?: string;
  /** Hold guidance + a 'size to your own risk' nudge. No price level. */
  note?: string;
  [key: string]: unknown;
}

/** A reminder to fire when the seasonal entry window opens. */
export interface SetReminder {
  type?: string;
  fire_on?: string;
  message?: string;
  [key: string]: unknown;
}

/** The no-broker last mile. Omitted (order_ticket undefined) on a neutral bias. */
export interface NextStep {
  headline?: string;
  order_ticket?: OrderTicket;
  copy_text?: string;
  set_reminder?: SetReminder;
  framing?: string;
  [key: string]: unknown;
}

/**
 * THE unit returned by /scan, /analyze/{symbol} and /daily-pick.
 * DERIVED PATTERNS ONLY - all movement is percentages; order_ticket carries no price level.
 */
export interface PatternCard {
  rank?: number;
  symbol?: string;
  market?: MarketRef;
  direction?: Direction;
  /** bullish | bearish | neutral. neutral = low conviction; next_step.order_ticket omitted. */
  bias?: Bias;
  setup?: PatternSetup;
  /** 0-100 blended ranking score. Explainable. */
  edge_score?: number;
  edge_basis?: string;
  stats?: PatternStats;
  /** null when ML quota is exhausted or the market is not ML-eligible. */
  ml?: PatternCardML | null;
  receipts?: Receipts;
  next_step?: NextStep;
  /** Gateway-composed one-line summary. */
  headline?: string;
  /** Gateway-composed plain-English read. */
  verdict?: string;
  /** Exact regulatory disclaimer, present on every card. */
  disclaimer?: string;
  /** 'ML score shown (Pro).' or the free-tier / daily-limit nudge. */
  tier_notes?: string;
  [key: string]: unknown;
}

/** Response envelope for GET /scan. */
export interface ScanResult {
  generated_at?: string;
  /** The server's plain-English honesty line: what was evaluated/shown, any degradation. */
  summary?: string;
  window?: string;
  rank_by?: RankBy;
  count?: number;
  evaluated_count?: number;
  enrichment_capped?: boolean;
  /** True when the list was cut short by the plan's row cap, not by the filters. */
  capped_by_plan?: boolean;
  /** "N of M" - rows shown of candidates evaluated. */
  shown_of_evaluated?: string;
  /** Present only when capped_by_plan - where to lift the cap. */
  upgrade_url?: string;
  ml_remaining_today?: number | null;
  opportunities?: PatternCard[];
  [key: string]: unknown;
}

/** A compact alternate setup (percent stats only - no card/receipts/ml). */
export interface CompactSetup {
  symbol?: string;
  direction?: Direction;
  entry_date?: string;
  hold_days?: number;
  historical_win_rate?: number;
  sharpe_ratio?: number;
  avg_return_pct?: number;
  median_return_pct?: number;
  years?: string;
  [key: string]: unknown;
}

/** Response envelope for GET /analyze/{symbol}. */
export interface AnalyzeResult {
  card?: PatternCard;
  other_setups?: CompactSetup[];
  as_of?: string;
  [key: string]: unknown;
}

/** Response envelope for GET /daily-pick. */
export interface DailyPickResult {
  card?: PatternCard;
  featured_date?: string;
  track_record?: TrackRecordSummary;
  as_of?: string;
  [key: string]: unknown;
}

/** One realized pick row in the standalone track record. */
export interface TrackRecordPick {
  symbol?: string;
  featured_date?: string;
  return_pct?: number;
  result?: PickResult;
  [key: string]: unknown;
}

/** Response envelope for GET /daily-pick/track-record. */
export interface TrackRecord {
  summary?: {
    count?: number;
    win_count?: number;
    win_rate?: number;
    avg_return_pct?: number;
    [key: string]: unknown;
  };
  picks?: TrackRecordPick[];
  [key: string]: unknown;
}

/** Aggregate seasonal-pattern statistics for a symbol. No raw price series. */
export interface Pattern {
  symbol?: string;
  market?: string;
  /** REAL historical win rate, 0..1. Also inside stats as percent_profitable. */
  win_rate?: number | null;
  /** Publishable percent-only subset of the ChartData4 stats. */
  stats?: Record<string, unknown>;
  [key: string]: unknown;
}

/** One point on the normalized seasonal curve. `index` is a 0-100 relative shape, never a price. */
export interface SeasonalCurvePoint {
  date?: string;
  /** 0-100 relative seasonal index (high/low-normalized, averaged across years). */
  index?: number;
  [key: string]: unknown;
}

/** Response envelope for GET /seasonal-chart. The curve is a relative shape, not prices. */
export interface SeasonalChart {
  symbol?: string;
  market?: string;
  direction?: Direction;
  entry_date?: string;
  days_out?: number | null;
  years?: string;
  win_rate?: number | null;
  seasonal_curve?: SeasonalCurvePoint[];
  stats?: Record<string, unknown>;
  [key: string]: unknown;
}

/** One item posted to POST /score. */
export interface ScoreInput {
  symbol: string;
  date: string;
  days_out: number;
  direction: Direction;
}

/** A scored item (legacy ML names), plus an optional note when unscored past the allowance. */
export interface ScoredItem extends MLScore {
  symbol?: string;
}

/** Successful ML score response. */
export interface ScoreResult {
  scores?: ScoredItem[];
  /** How many items were actually scored. */
  granted?: number;
  ml_remaining_today?: number | null;
  [key: string]: unknown;
}

/**
 * The graceful daily-ML-limit nudge (HTTP 200, NOT an error).
 * Returned by POST /score when the allowance is already fully spent.
 * Surfaced as data; check `requires` to detect it.
 */
export interface MLDailyLimitReached {
  requires: string;
  reason: string;
  message?: string;
  upgrade_url?: string;
  ml_remaining_today?: number;
  [key: string]: unknown;
}

/** POST /score returns either a ScoreResult or the daily-limit nudge. Both are HTTP 200. */
export type ScoreResponse = ScoreResult | MLDailyLimitReached;

/** Narrowing helper: true when a /score response is the daily-ML-limit nudge, not a scored batch. */
export function isMLDailyLimitReached(
  response: ScoreResponse,
): response is MLDailyLimitReached {
  return (
    typeof (response as MLDailyLimitReached).requires === 'string' &&
    (response as MLDailyLimitReached).reason === 'ml_daily_limit'
  );
}
