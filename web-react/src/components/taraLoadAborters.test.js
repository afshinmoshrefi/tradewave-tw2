import { createTaraLoadAborters } from './taraLoadAborters'

const TARA_VIEW = '5|SPX|2026-09-27|295|24|pe2|0'   // Tara's 100-Year Pattern
const USER_VIEW = '5|SPX|2026-09-01|30|24|pe2|0'    // the user then picks September

test('cancels the loads belonging to the transaction being torn down', () => {
  const reg = createTaraLoadAborters()
  const primary = jest.fn()
  const trend = jest.fn()
  reg.register(1, primary, TARA_VIEW)
  reg.register(1, trend, TARA_VIEW)

  expect(reg.cancel(1, TARA_VIEW)).toBe(2)
  expect(primary).toHaveBeenCalledTimes(1)
  expect(trend).toHaveBeenCalledTimes(1)
  expect(reg.pendingCount(1)).toBe(0)
})

// The reported bug. A load generation is bumped only by a Tara action, so the
// user's next chart load reuses it. Tearing down the finished transaction used
// to abort that load, and an aborted fetch reports no terminal state, so the
// viewer sat on 'loading' and the chart never returned.
test('leaves a later load for a different view untouched', () => {
  const reg = createTaraLoadAborters()
  const taraLoad = jest.fn()
  reg.register(1, taraLoad, TARA_VIEW)
  reg.release(1)                       // Tara's transaction succeeded

  const userLoad = jest.fn()           // user picks September; same generation
  reg.register(1, userLoad, USER_VIEW)

  expect(reg.cancel(1, TARA_VIEW)).toBe(0)
  expect(userLoad).not.toHaveBeenCalled()
  expect(reg.pendingCount(1)).toBe(1)
})

test('cancels only the matching view when both are in flight', () => {
  const reg = createTaraLoadAborters()
  const taraLoad = jest.fn()
  const userLoad = jest.fn()
  reg.register(1, taraLoad, TARA_VIEW)
  reg.register(1, userLoad, USER_VIEW)

  expect(reg.cancel(1, TARA_VIEW)).toBe(1)
  expect(taraLoad).toHaveBeenCalledTimes(1)
  expect(userLoad).not.toHaveBeenCalled()
  expect(reg.pendingCount(1)).toBe(1)
})

test('an unscoped cancel still clears the whole generation', () => {
  const reg = createTaraLoadAborters()
  const a = jest.fn()
  const b = jest.fn()
  reg.register(2, a, TARA_VIEW)
  reg.register(2, b, USER_VIEW)

  expect(reg.cancel(2)).toBe(2)
  expect(a).toHaveBeenCalledTimes(1)
  expect(b).toHaveBeenCalledTimes(1)
  expect(reg.pendingCount(2)).toBe(0)
})

test('a cancel never reaches another generation', () => {
  const reg = createTaraLoadAborters()
  const older = jest.fn()
  reg.register(1, older, TARA_VIEW)
  expect(reg.cancel(2, TARA_VIEW)).toBe(0)
  expect(older).not.toHaveBeenCalled()
})

test('unregistering removes the load so a later cancel cannot reach it', () => {
  const reg = createTaraLoadAborters()
  const load = jest.fn()
  const unregister = reg.register(1, load, TARA_VIEW)
  unregister()
  expect(reg.cancel(1, TARA_VIEW)).toBe(0)
  expect(load).not.toHaveBeenCalled()
  expect(reg.pendingCount(1)).toBe(0)
})

test('release drops bookkeeping without aborting anything', () => {
  const reg = createTaraLoadAborters()
  const load = jest.fn()
  reg.register(1, load, TARA_VIEW)
  reg.release(1)
  expect(load).not.toHaveBeenCalled()
  expect(reg.pendingCount(1)).toBe(0)
})

test('one failing abort does not stop the rest of the transaction cancelling', () => {
  const reg = createTaraLoadAborters()
  const boom = jest.fn(() => { throw new Error('abort exploded') })
  const ok = jest.fn()
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
  reg.register(1, boom, TARA_VIEW)
  reg.register(1, ok, TARA_VIEW)

  expect(reg.cancel(1, TARA_VIEW)).toBe(2)
  expect(ok).toHaveBeenCalledTimes(1)
  warn.mockRestore()
})

test('ignores registrations that cannot be cancelled later', () => {
  const reg = createTaraLoadAborters()
  expect(typeof reg.register(null, jest.fn(), TARA_VIEW)).toBe('function')
  expect(typeof reg.register(1, 'not a function', TARA_VIEW)).toBe('function')
  expect(reg.pendingCount(1)).toBe(0)
})

test('a load registered without a key is still cancelled by its transaction', () => {
  const reg = createTaraLoadAborters()
  const load = jest.fn()
  reg.register(1, load)
  expect(reg.cancel(1)).toBe(1)
  expect(load).toHaveBeenCalledTimes(1)
})
