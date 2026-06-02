/**
 * Zero-dependency HTTP layer for the TradeWave SDK.
 *
 * Uses the global `fetch` (Node 18+ / 22, Deno, browsers). Adds:
 *  - Bearer auth + a small User-Agent
 *  - configurable timeout via AbortController
 *  - automatic exponential backoff with jitter on 429 and 5xx, honoring Retry-After
 *  - the typed error hierarchy from errors.ts
 *
 * The ML graceful nudge (HTTP 200 with requires/reason or ml:null) is plain success
 * data and is returned as-is, never treated as an error.
 */

import { errorForStatus, RateLimitError, TradeWaveError } from './errors.js';

export const SDK_VERSION = '0.1.0';
export const DEFAULT_BASE_URL = 'https://api.tradewave.ai/v1';
const USER_AGENT = `tradewave-typescript/${SDK_VERSION}`;

export interface HttpClientOptions {
  apiKey: string;
  baseUrl?: string;
  /** Per-request timeout in milliseconds. Default 30000. */
  timeoutMs?: number;
  /** Max automatic retries on 429 / 5xx. Default 3. */
  maxRetries?: number;
  /** Optional custom fetch (for testing). Defaults to the global fetch. */
  fetch?: typeof fetch;
}

export interface RequestOptions {
  /** Query parameters. undefined / null values are dropped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** JSON request body (for POST). */
  body?: unknown;
  method?: 'GET' | 'POST';
}

interface RateLimitInfo {
  limit?: number;
  remaining?: number;
  reset?: number;
}

/** A parsed response: the JSON payload plus rate-limit metadata read off the headers. */
export interface ApiResponse<T> {
  data: T;
  status: number;
  rateLimit: RateLimitInfo;
  /** ml_remaining_today header / body hint surfaced for convenience when present. */
  headers: Headers;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Parse a Retry-After header (seconds or HTTP-date) into milliseconds, or undefined. */
function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(value);
  if (!Number.isNaN(date)) return Math.max(0, date - Date.now());
  return undefined;
}

function readRateLimit(headers: Headers): RateLimitInfo {
  const num = (name: string): number | undefined => {
    const raw = headers.get(name);
    if (raw == null) return undefined;
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  };
  return {
    limit: num('X-RateLimit-Limit'),
    remaining: num('X-RateLimit-Remaining'),
    reset: num('X-RateLimit-Reset'),
  };
}

export class HttpClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly maxRetries: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: HttpClientOptions) {
    if (!options.apiKey) {
      throw new TradeWaveError(
        'A TradeWave API key is required. Pass apiKey or set TRADEWAVE_API_KEY.',
      );
    }
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs ?? 30000;
    this.maxRetries = options.maxRetries ?? 3;
    const f = options.fetch ?? globalThis.fetch;
    if (typeof f !== 'function') {
      throw new TradeWaveError(
        'No global fetch available. Use Node 18+ / 22, or pass a fetch implementation.',
      );
    }
    // Bind so it is not called with the wrong receiver.
    this.fetchImpl = f.bind(globalThis);
  }

  private buildUrl(path: string, query?: RequestOptions['query']): string {
    const url = new URL(this.baseUrl + (path.startsWith('/') ? path : `/${path}`));
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value === undefined || value === null) continue;
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }

  /** Exponential backoff with full jitter, in milliseconds. */
  private backoffMs(attempt: number): number {
    const base = Math.min(1000 * 2 ** attempt, 20000);
    return Math.random() * base;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
    const method = options.method ?? 'GET';
    const url = this.buildUrl(path, options.query);

    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      Accept: 'application/json',
      'User-Agent': USER_AGENT,
    };
    let bodyText: string | undefined;
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      bodyText = JSON.stringify(options.body);
    }

    let lastError: unknown;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      let response: Response;
      try {
        response = await this.fetchImpl(url, {
          method,
          headers,
          body: bodyText,
          signal: controller.signal,
        });
      } catch (err) {
        clearTimeout(timer);
        // Network error / timeout: retry like a transient failure.
        lastError = err;
        const aborted = err instanceof Error && err.name === 'AbortError';
        const msg = aborted
          ? `Request to ${path} timed out after ${this.timeoutMs}ms`
          : `Network error calling ${path}: ${(err as Error).message}`;
        if (attempt < this.maxRetries) {
          await sleep(this.backoffMs(attempt));
          continue;
        }
        throw new TradeWaveError(msg, { cause: err });
      } finally {
        clearTimeout(timer);
      }

      const rateLimit = readRateLimit(response.headers);

      if (response.ok) {
        const data = (await this.parseJson(response)) as T;
        return { data, status: response.status, rateLimit, headers: response.headers };
      }

      // Error path. Read the envelope { error: { code, message } } when present.
      const envelope = await this.parseJson(response).catch(() => undefined);
      const errObj =
        envelope && typeof envelope === 'object' && 'error' in envelope
          ? (envelope as { error?: { code?: string; message?: string } }).error
          : undefined;
      const code = errObj?.code;
      const message =
        errObj?.message ?? `TradeWave API error ${response.status} on ${path}`;
      const retryAfter = parseRetryAfter(response.headers.get('Retry-After'));

      const retryable = response.status === 429 || response.status >= 500;
      if (retryable && attempt < this.maxRetries) {
        // Honor Retry-After when present, else backoff with jitter.
        const waitMs =
          retryAfter !== undefined ? retryAfter : this.backoffMs(attempt);
        await sleep(waitMs);
        lastError = errorForStatus(response.status, message, {
          code,
          retryAfter: retryAfter !== undefined ? retryAfter / 1000 : undefined,
        });
        continue;
      }

      throw errorForStatus(response.status, message, {
        code,
        retryAfter: retryAfter !== undefined ? retryAfter / 1000 : undefined,
      });
    }

    // Exhausted retries on a retryable status.
    if (lastError instanceof RateLimitError || lastError instanceof TradeWaveError) {
      throw lastError;
    }
    throw new TradeWaveError(`Request to ${path} failed after retries`, {
      cause: lastError,
    });
  }

  private async parseJson(response: Response): Promise<unknown> {
    const text = await response.text();
    if (!text) return undefined;
    try {
      return JSON.parse(text);
    } catch (err) {
      throw new TradeWaveError(
        `Failed to parse JSON response (status ${response.status}).`,
        { status: response.status, cause: err },
      );
    }
  }
}
