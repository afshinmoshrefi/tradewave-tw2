/**
 * TradeWave Data API v1 client.
 *
 * Usage:
 *   import { TradeWave } from '@tradewave/sdk';
 *   const tw = new TradeWave({ apiKey: 'tw_live_...' });
 *   await tw.scan({ window: 'now', minWinRate: 0.6 });
 *   await tw.dailyPick();
 *
 * The apiKey falls back to process.env.TRADEWAVE_API_KEY when not passed.
 *
 * SAFETY: signals only - the API returns percentages and a normalized seasonal index,
 * never raw prices. The daily-ML-limit nudge on score() is returned as data (check
 * isMLDailyLimitReached), never thrown.
 */

import { HttpClient, DEFAULT_BASE_URL, type ApiResponse } from './http.js';

export { DEFAULT_BASE_URL };
import { TradeWaveError } from './errors.js';
import type {
  AnalyzeResult,
  DailyPickResult,
  Direction,
  Market,
  Me,
  OpportunityList,
  Opportunity,
  Pattern,
  RankBy,
  ScanResult,
  ScoreInput,
  ScoreResponse,
  SeasonalChart,
  Symbol,
  TrackRecord,
} from './models.js';

/** Options for constructing a TradeWave client. */
export interface TradeWaveOptions {
  /** API key like 'tw_live_...'. Falls back to process.env.TRADEWAVE_API_KEY. */
  apiKey?: string;
  /**
   * Override the base URL. When omitted, falls back to process.env.TRADEWAVE_API_URL
   * (then TRADEWAVE_BASE_URL), else the default https://api.tradewave.ai/v1
   */
  baseUrl?: string;
  /** Per-request timeout in milliseconds. Default 30000. */
  timeoutMs?: number;
  /** Max automatic retries on 429 / 5xx. Default 3. */
  maxRetries?: number;
  /** Custom fetch (for testing); defaults to the global fetch. */
  fetch?: typeof fetch;
}

export interface ScanParams {
  /** csv of ids or aliases e.g. '2,11' or 'sp500,etf'. Default = all in-scope markets. */
  markets?: string;
  /** 'now' | 'next_2_weeks' | 'next_month' | a 'from..to' range. Default 'now'. */
  window?: string;
  direction?: Direction;
  /** Filter on historical_win_rate (share of profitable years), 0..1. */
  minWinRate?: number;
  /** Trust filter - require years_tested >= N. */
  minYears?: number;
  /** Ranking key. Default 'sharpe'. */
  rankBy?: RankBy;
  /** Tier-capped result count. */
  limit?: number;
}

export interface AnalyzeParams {
  /** Permanent resource key '0'..'16'. Resolved if the symbol is unique. */
  market?: string;
  direction?: Direction;
  /** Holding period in days. */
  daysOut?: number;
}

export interface OpportunitiesParams {
  /** Market id '0'..'16' (required). */
  market: string;
  /** entry_date to evaluate; defaults to today. */
  from?: string;
  /** Accepted but ignored - does not widen the window. Use scan() for windows. */
  to?: string;
  direction?: Direction;
  /** Filter on the REAL historical win_rate (share of profitable years), 0..1. */
  minWinRate?: number;
  limit?: number;
}

export interface SeasonalChartParams {
  market: string;
  symbol: string;
  entryDate?: string;
  daysOut?: number;
  direction?: Direction;
  /** Lookback window label - stays a string. */
  years?: string;
}

function resolveApiKey(passed?: string): string {
  if (passed) return passed;
  const env =
    typeof process !== 'undefined' && process.env
      ? process.env.TRADEWAVE_API_KEY
      : undefined;
  if (env) return env;
  throw new TradeWaveError(
    'No API key provided. Pass { apiKey } or set TRADEWAVE_API_KEY.',
  );
}

function resolveBaseUrl(passed?: string): string {
  if (passed) return passed;
  const env =
    typeof process !== 'undefined' && process.env
      ? process.env.TRADEWAVE_API_URL ?? process.env.TRADEWAVE_BASE_URL
      : undefined;
  return env ?? DEFAULT_BASE_URL;
}

export class TradeWave {
  private readonly http: HttpClient;
  /** The resolved base URL in use. */
  readonly baseUrl: string;

  constructor(options: TradeWaveOptions = {}) {
    const apiKey = resolveApiKey(options.apiKey);
    this.baseUrl = resolveBaseUrl(options.baseUrl);
    this.http = new HttpClient({
      apiKey,
      baseUrl: this.baseUrl,
      timeoutMs: options.timeoutMs,
      maxRetries: options.maxRetries,
      fetch: options.fetch,
    });
  }

  // ---- Flagship endpoints -------------------------------------------------

  /**
   * FLAGSHIP. Scan in-scope markets for the best seasonal setups (ranked SignalCards).
   * Prefer this over the low-level primitives.
   */
  async scan(params: ScanParams = {}): Promise<ScanResult> {
    const res = await this.http.request<ScanResult>('/scan', {
      query: {
        markets: params.markets,
        window: params.window,
        direction: params.direction,
        min_win_rate: params.minWinRate,
        min_years: params.minYears,
        rank_by: params.rankBy,
        limit: params.limit,
      },
    });
    return res.data;
  }

  /**
   * FLAGSHIP. Deep-dive one symbol into a single rich SignalCard plus alternate setups.
   */
  async analyze(symbol: string, params: AnalyzeParams = {}): Promise<AnalyzeResult> {
    const res = await this.http.request<AnalyzeResult>(
      `/analyze/${encodeURIComponent(symbol)}`,
      {
        query: {
          market: params.market,
          direction: params.direction,
          days_out: params.daysOut,
        },
      },
    );
    return res.data;
  }

  // ---- Identity -------------------------------------------------------------

  /**
   * Identity + capabilities for your API key: plan tier, ML allowance left today
   * (null = unlimited), row cap, rate limits, and in-scope markets. Reads only -
   * never consumes ML allowance.
   */
  async me(): Promise<Me> {
    const res = await this.http.request<Me>('/me');
    return res.data;
  }

  // ---- Markets ------------------------------------------------------------

  /** List the 17 markets and the caller's access scope. */
  async listMarkets(): Promise<Market[]> {
    const res = await this.http.request<{ markets?: Market[] }>('/markets');
    return res.data.markets ?? [];
  }

  /**
   * List symbols in a market (permanent resource key '0'..'16').
   *
   * A full market is large (the S&P 500 list alone is ~150KB), so the endpoint
   * pages: `prefix` filters by ticker prefix (case-insensitive) and `limit`
   * caps the rows returned. Use raw() for the total/matched truncation counters.
   */
  async listSymbols(
    market: string,
    params: { prefix?: string; limit?: number } = {},
  ): Promise<Symbol[]> {
    const res = await this.http.request<{ symbols?: Symbol[] }>(
      `/markets/${encodeURIComponent(market)}/symbols`,
      { query: { prefix: params.prefix, limit: params.limit } },
    );
    return res.data.symbols ?? [];
  }

  // ---- Opportunities (primitives) -----------------------------------------

  /**
   * Ranked seasonal opportunities for ONE market at a single entry_date.
   * Does NOT widen across a window - use scan() for windows.
   */
  async opportunities(params: OpportunitiesParams): Promise<OpportunityList> {
    const res = await this.http.request<OpportunityList>('/opportunities', {
      query: {
        market: params.market,
        from: params.from,
        to: params.to,
        direction: params.direction,
        min_win_rate: params.minWinRate,
        limit: params.limit,
      },
    });
    return res.data;
  }

  /** Seasonal opportunities for one symbol within a market. */
  async opportunitiesForSymbol(symbol: string, market: string): Promise<Opportunity[]> {
    const res = await this.http.request<{ opportunities?: Opportunity[] }>(
      `/opportunities/${encodeURIComponent(symbol)}`,
      { query: { market } },
    );
    return res.data.opportunities ?? [];
  }

  /** Aggregate seasonal-pattern stats for a symbol (no price series). */
  async pattern(market: string, symbol: string): Promise<Pattern> {
    const res = await this.http.request<Pattern>(
      `/patterns/${encodeURIComponent(market)}/${encodeURIComponent(symbol)}`,
    );
    return res.data;
  }

  /**
   * Seasonal trendchart as DATA: the year-averaged, normalized 0-100 seasonal index
   * curve. The index is a relative shape, never a price.
   */
  async seasonalChart(params: SeasonalChartParams): Promise<SeasonalChart> {
    const res = await this.http.request<SeasonalChart>('/seasonal-chart', {
      query: {
        market: params.market,
        symbol: params.symbol,
        entry_date: params.entryDate,
        days_out: params.daysOut,
        direction: params.direction,
        years: params.years,
      },
    });
    return res.data;
  }

  // ---- Scoring ------------------------------------------------------------

  /**
   * ML scores for opportunities (all tiers, metered per day; ML-eligible markets only).
   *
   * Returns either a ScoreResult (scores[]) or the graceful daily-limit nudge
   * (MLDailyLimitReached) - both are HTTP 200, never an error. Use
   * isMLDailyLimitReached() to narrow.
   */
  async score(opportunities: ScoreInput[]): Promise<ScoreResponse> {
    const res = await this.http.request<ScoreResponse>('/score', {
      method: 'POST',
      body: { opportunities },
    });
    return res.data;
  }

  // ---- Daily pick ---------------------------------------------------------

  /** Today's AI pick as a SignalCard, with its live track record. */
  async dailyPick(): Promise<DailyPickResult> {
    const res = await this.http.request<DailyPickResult>('/daily-pick');
    return res.data;
  }

  /** Historical track record of past daily picks (realized win/loss). */
  async dailyPickTrackRecord(): Promise<TrackRecord> {
    const res = await this.http.request<TrackRecord>('/daily-pick/track-record');
    return res.data;
  }

  // ---- Raw escape hatch ---------------------------------------------------

  /**
   * Raw request escape hatch - returns the parsed JSON plus status / rate-limit /
   * headers, so power users are never blocked by a model lag. `path` is relative to
   * the base URL (e.g. '/scan').
   */
  async raw<T = unknown>(
    path: string,
    options: { method?: 'GET' | 'POST'; query?: Record<string, string | number | boolean | undefined | null>; body?: unknown } = {},
  ): Promise<ApiResponse<T>> {
    return this.http.request<T>(path, options);
  }
}
