// Unit tests for the resilient appserver fetch wrapper.
// Proves the retry/backoff, Retry-After, mutation-safety and 401 re-login
// behavior without a live appserver.

const resp = (status, headers = {}) => ({
  status,
  ok: status >= 200 && status < 300,
  headers: { get: (k) => (k in headers ? headers[k] : null) },
});

let twFetch;
let registerTwFetchAuth;

beforeEach(() => {
  jest.resetModules(); // fresh module state (relogin cache, sessionDead flag)
  ({ twFetch, registerTwFetchAuth } = require('./twFetch'));
  global.fetch = jest.fn();
});

test('retries a 429 with Retry-After and resolves on success', async () => {
  global.fetch
    .mockResolvedValueOnce(resp(429, { 'Retry-After': '0' }))
    .mockResolvedValueOnce(resp(429, { 'Retry-After': '0' }))
    .mockResolvedValueOnce(resp(200));

  const onRetry = jest.fn();
  const res = await twFetch('/appserver/OppList4/2?token=abc', { onRetry });

  expect(res.status).toBe(200);
  expect(global.fetch).toHaveBeenCalledTimes(3);
  expect(onRetry).toHaveBeenCalledTimes(2);
  expect(onRetry).toHaveBeenCalledWith(1, 429);
});

test('gives up after MAX_RETRIES and returns the failing response', async () => {
  global.fetch.mockResolvedValue(resp(503, { 'Retry-After': '0' }));

  const res = await twFetch('/appserver/ChartData4/2?token=abc');

  expect(res.status).toBe(503);
  expect(global.fetch).toHaveBeenCalledTimes(4); // initial + 3 retries
});

test('does NOT retry an ambiguous 502 on a mutation (POST)', async () => {
  global.fetch.mockResolvedValue(resp(502));

  const res = await twFetch('/appserver/add_user_watchlist_item/x/AAPL?token=abc', { method: 'POST' });

  expect(res.status).toBe(502);
  expect(global.fetch).toHaveBeenCalledTimes(1);
});

test('retries a network error for GET', async () => {
  global.fetch
    .mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(resp(200));

  const res = await twFetch('/appserver/getResourcesObj?token=abc');

  expect(res.status).toBe(200);
  expect(global.fetch).toHaveBeenCalledTimes(2);
});

test('401 re-runs the login handshake once and replays with the fresh token', async () => {
  const relogin = jest.fn(() => Promise.resolve('NEWTOK'));
  const onSessionExpired = jest.fn();
  registerTwFetchAuth({ relogin, onSessionExpired });

  global.fetch
    .mockResolvedValueOnce(resp(401))
    .mockResolvedValueOnce(resp(200));

  const res = await twFetch('/appserver/get_user_watchlist_names?token=OLDTOK&mode=pe');

  expect(res.status).toBe(200);
  expect(relogin).toHaveBeenCalledTimes(1);
  expect(onSessionExpired).not.toHaveBeenCalled();
  expect(global.fetch).toHaveBeenLastCalledWith(
    '/appserver/get_user_watchlist_names?token=NEWTOK&mode=pe',
    expect.any(Object)
  );
});

test('concurrent 401s share a single re-login (single-flight)', async () => {
  let resolveRelogin;
  const relogin = jest.fn(() => new Promise((r) => { resolveRelogin = r; }));
  registerTwFetchAuth({ relogin, onSessionExpired: jest.fn() });

  global.fetch.mockImplementation((url) =>
    Promise.resolve(url.includes('NEWTOK') ? resp(200) : resp(401))
  );

  const p1 = twFetch('/appserver/a?token=OLD');
  const p2 = twFetch('/appserver/b?token=OLD');
  await new Promise((r) => setTimeout(r, 10)); // let both hit the 401 path
  resolveRelogin('NEWTOK');

  const [r1, r2] = await Promise.all([p1, p2]);
  expect(r1.status).toBe(200);
  expect(r2.status).toBe(200);
  expect(relogin).toHaveBeenCalledTimes(1);
});

test('failed re-login surfaces session expiry and stops hammering /login', async () => {
  const relogin = jest.fn(() => Promise.resolve(null));
  const onSessionExpired = jest.fn();
  registerTwFetchAuth({ relogin, onSessionExpired });

  global.fetch.mockResolvedValue(resp(401));

  const res1 = await twFetch('/appserver/a?token=OLD');
  const res2 = await twFetch('/appserver/b?token=OLD');

  expect(res1.status).toBe(401);
  expect(res2.status).toBe(401);
  expect(relogin).toHaveBeenCalledTimes(1); // sessionDead short-circuits the second one
  expect(onSessionExpired).toHaveBeenCalledTimes(1);
});

test('login handshake itself never auth-retries (skipAuthRetry)', async () => {
  const relogin = jest.fn();
  registerTwFetchAuth({ relogin, onSessionExpired: jest.fn() });

  global.fetch.mockResolvedValue(resp(401));

  const res = await twFetch('/appserver/login/1/6/D/L/deadltk', { skipAuthRetry: true });

  expect(res.status).toBe(401);
  expect(relogin).not.toHaveBeenCalled();
  expect(global.fetch).toHaveBeenCalledTimes(1);
});
