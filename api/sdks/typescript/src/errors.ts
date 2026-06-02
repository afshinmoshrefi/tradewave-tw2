/**
 * Typed exception hierarchy for the TradeWave SDK.
 *
 * Non-2xx responses carry a JSON error envelope: { "error": { "code", "message" } }.
 * Every error exposes .status (HTTP status), .code (machine code from the envelope,
 * may be undefined) and .message.
 *
 * Note: the ML graceful nudge (HTTP 200 with requires:"upgrade" /
 * reason:"ml_daily_limit", or ml:null + tier_notes on cards) is NOT an error and is
 * surfaced as data, never thrown.
 */

/** Base class for every error raised by the SDK. */
export class TradeWaveError extends Error {
  /** HTTP status code, when the error came from an HTTP response (else 0). */
  readonly status: number;
  /** Machine-readable code from the error envelope, when present. */
  readonly code: string | undefined;

  constructor(
    message: string,
    options: { status?: number; code?: string; cause?: unknown } = {},
  ) {
    super(message, options.cause !== undefined ? { cause: options.cause } : undefined);
    this.name = new.target.name;
    this.status = options.status ?? 0;
    this.code = options.code;
    // Maintain prototype chain across the TS->ES transpile boundary.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 401 / 403 - missing, invalid, or unauthorized API key. */
export class AuthError extends TradeWaveError {}

/** 404 - the requested resource (symbol, market, ...) was not found. */
export class NotFoundError extends TradeWaveError {}

/**
 * 429 - rate limit exceeded.
 * `retryAfter` is the server's Retry-After hint in seconds, when present.
 */
export class RateLimitError extends TradeWaveError {
  readonly retryAfter: number | undefined;

  constructor(
    message: string,
    options: { status?: number; code?: string; retryAfter?: number; cause?: unknown } = {},
  ) {
    super(message, options);
    this.retryAfter = options.retryAfter;
  }
}

/** 5xx - the server failed to fulfil a valid request. */
export class ServerError extends TradeWaveError {}

/**
 * Build the right error subclass for an HTTP status.
 * Used internally by the HTTP layer.
 */
export function errorForStatus(
  status: number,
  message: string,
  options: { code?: string; retryAfter?: number; cause?: unknown } = {},
): TradeWaveError {
  if (status === 401 || status === 403) {
    return new AuthError(message, { status, code: options.code, cause: options.cause });
  }
  if (status === 404) {
    return new NotFoundError(message, { status, code: options.code, cause: options.cause });
  }
  if (status === 429) {
    return new RateLimitError(message, {
      status,
      code: options.code,
      retryAfter: options.retryAfter,
      cause: options.cause,
    });
  }
  if (status >= 500) {
    return new ServerError(message, { status, code: options.code, cause: options.cause });
  }
  return new TradeWaveError(message, { status, code: options.code, cause: options.cause });
}
