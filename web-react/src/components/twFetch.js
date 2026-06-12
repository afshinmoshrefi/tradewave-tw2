// twFetch.js - resilient fetch for appserver data calls.
//
// Why: the appserver is rate-limited and session tokens expire. Raw fetch()
// turned every transient 429/5xx/network blip - and every expired token in a
// long-lived tab - into a silently blank component (the "no data until I
// refresh" symptom). This wrapper makes the client self-heal:
//
//   1. Transient failures (429/502/503/504 and network-level errors) retry up
//      to MAX_RETRIES times with exponential backoff + jitter, honoring a
//      Retry-After header when the server sends one. Non-GET requests retry
//      only on 429/503 - statuses where the request was definitely NOT
//      processed - so a mutation can never double-apply on an ambiguous
//      502/504.
//   2. A 401 (expired appserver session token) re-runs the /login handshake
//      ONCE (single-flight across concurrent 401s) via the handler App.js
//      registers with registerTwFetchAuth, swaps the fresh token into the
//      request URL and replays the request. If the handshake itself fails
//      (the page's LTK has expired too) the registered onSessionExpired
//      handler shows the existing "Session Expired - reload" overlay.
//
// Usage: drop-in replacement for fetch(url, options). Extra options:
//   onRetry(attempt, status) - called before each backoff sleep so callers
//      can surface an inline "retrying..." state instead of a blank screen
//      (status is 0 for a network-level error).
//   skipAuthRetry: true      - for the login handshake itself (a 401 there
//      means the LTK is dead; re-running the handshake would loop).

const MAX_RETRIES = 3;
const BASE_DELAY_MS = 600;
const MAX_DELAY_MS = 15000;
const RELOGIN_REUSE_MS = 10000; // requests already in flight with the old token reuse the fresh one
const RETRYABLE_GET = [429, 502, 503, 504];
const RETRYABLE_MUTATE = [429, 503];

let authHandlers = {};
let reloginPromise = null;
let lastRelogin = { token: null, at: 0 };
let sessionDead = false; // once the handshake fails, stop hammering /login - the overlay forces a reload

export const registerTwFetchAuth = (handlers) => {
  authHandlers = { ...authHandlers, ...handlers };
  sessionDead = false;
};

const reloginOnce = () => {
  if (sessionDead || typeof authHandlers.relogin !== 'function') return Promise.resolve(null);
  if (lastRelogin.token && Date.now() - lastRelogin.at < RELOGIN_REUSE_MS) {
    return Promise.resolve(lastRelogin.token);
  }
  if (!reloginPromise) {
    reloginPromise = Promise.resolve()
      .then(() => authHandlers.relogin())
      .catch(() => null)
      .then((newToken) => {
        reloginPromise = null;
        if (newToken) {
          lastRelogin = { token: newToken, at: Date.now() };
        }
        else {
          sessionDead = true;
          if (typeof authHandlers.onSessionExpired === 'function') authHandlers.onSessionExpired();
        }
        return newToken;
      });
  }
  return reloginPromise;
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const backoffMs = (retries, res) => {
  if (res && res.headers) {
    const retryAfter = res.headers.get('Retry-After');
    if (retryAfter) {
      const secs = Number(retryAfter);
      if (!Number.isNaN(secs) && secs >= 0) return Math.min(secs * 1000, MAX_DELAY_MS);
      const when = Date.parse(retryAfter); // HTTP-date form
      if (!Number.isNaN(when)) return Math.min(Math.max(when - Date.now(), 0), MAX_DELAY_MS);
    }
  }
  return Math.min(BASE_DELAY_MS * Math.pow(2, retries) + Math.random() * 300, MAX_DELAY_MS);
};

// every appserver data call carries the session token as a query param
const swapUrlToken = (url, newToken) =>
  url.replace(/([?&]token=)[^&]*/, `$1${encodeURIComponent(newToken)}`);

export const twFetch = (url, options = {}) => {
  const { onRetry, skipAuthRetry, ...fetchOptions } = options;
  const method = (fetchOptions.method || 'GET').toUpperCase();
  const retryableStatuses = method === 'GET' ? RETRYABLE_GET : RETRYABLE_MUTATE;

  const throwIfAborted = () => {
    if (fetchOptions.signal && fetchOptions.signal.aborted) {
      throw new DOMException('Aborted', 'AbortError');
    }
  };

  const attempt = (attemptUrl, retries, authRetried) =>
    fetch(attemptUrl, fetchOptions).then(
      (res) => {
        if (res.status === 401 && !skipAuthRetry && !authRetried) {
          return reloginOnce().then((newToken) =>
            newToken ? attempt(swapUrlToken(attemptUrl, newToken), retries, true) : res
          );
        }
        if (retryableStatuses.indexOf(res.status) !== -1 && retries < MAX_RETRIES) {
          if (onRetry) onRetry(retries + 1, res.status);
          return sleep(backoffMs(retries, res)).then(() => {
            throwIfAborted();
            return attempt(attemptUrl, retries + 1, authRetried);
          });
        }
        return res;
      },
      (err) => {
        // network-level failure - retry GETs only; an abort rejects immediately
        if ((err && err.name === 'AbortError') || method !== 'GET' || retries >= MAX_RETRIES) throw err;
        if (onRetry) onRetry(retries + 1, 0);
        return sleep(backoffMs(retries, null)).then(() => {
          throwIfAborted();
          return attempt(attemptUrl, retries + 1, authRetried);
        });
      }
    );

  return attempt(url, 0, false);
};
