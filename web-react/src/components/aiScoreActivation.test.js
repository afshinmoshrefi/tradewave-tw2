import {
  recordAIScoreViewed,
  resetAIScoreViewedForTests,
} from './aiScoreActivation'

beforeEach(() => {
  resetAIScoreViewedForTests()
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }))
})

afterEach(() => {
  delete global.fetch
})

test('posts the existing activation payload only once for a signed-in user', () => {
  expect(recordAIScoreViewed({ loggedinUser: '42', symbol: 'AAPL', horizon: 90 })).toBe(true)
  expect(recordAIScoreViewed({ loggedinUser: '42', symbol: 'MSFT', horizon: 30 })).toBe(false)

  expect(global.fetch).toHaveBeenCalledTimes(1)
  expect(global.fetch).toHaveBeenCalledWith('/api/activation/ai-score-viewed', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ detail: { symbol: 'AAPL', horizon: 90 } }),
    keepalive: true,
  })
})

test.each([undefined, null, false, '', '0', 0])('does not post for guest identity %p', loggedinUser => {
  expect(recordAIScoreViewed({ loggedinUser, symbol: 'AAPL', horizon: 90 })).toBe(false)
  expect(global.fetch).not.toHaveBeenCalled()
})
