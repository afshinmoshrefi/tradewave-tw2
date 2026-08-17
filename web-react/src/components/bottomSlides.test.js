import {
  BOTTOM_SLIDES,
  BOTTOM_SLIDES_WITH_AI,
  getBottomSlideIndex,
  getBottomSlideName,
  getBottomSlides,
  getMobileSlides,
  resolveBottomSlidePresentation,
  resolveMobileSlideIndex,
  sanitizeBottomSlide,
  supportsAIScoreSlide,
} from './bottomSlides';

test('keeps the legacy three-slide order when AI Scores is unavailable', () => {
  expect(getBottomSlides()).toBe(BOTTOM_SLIDES);
  expect(getBottomSlides({ hasAIScores: false })).toEqual([
    'trend_chart',
    'wave_stats',
    'price_chart',
  ]);
  expect(getBottomSlideIndex('price_chart')).toBe(2);
});

test('adds AI Scores as the third lower-panel destination', () => {
  expect(getBottomSlides({ hasAIScores: true })).toBe(BOTTOM_SLIDES_WITH_AI);
  expect(getBottomSlides({ hasAIScores: true })).toEqual([
    'trend_chart',
    'wave_stats',
    'ai_scores',
    'price_chart',
  ]);
  expect(getBottomSlideIndex('ai_scores', { hasAIScores: true })).toBe(2);
  expect(getBottomSlideIndex('price_chart', { hasAIScores: true })).toBe(3);
});

test('shows the AI Score destination only for U.S. stock groups and ETFs', () => {
  expect(supportsAIScoreSlide('DOW 30 STOCKS')).toBe(true);
  expect(supportsAIScoreSlide('NASDAQ 100 STOCKS')).toBe(true);
  expect(supportsAIScoreSlide('S&P 500 STOCKS')).toBe(true);
  expect(supportsAIScoreSlide('RUSSELL 1000 STOCKS')).toBe(true);
  expect(supportsAIScoreSlide('WILSHIRE 5000')).toBe(true);
  expect(supportsAIScoreSlide('ETFs')).toBe(true);
  expect(supportsAIScoreSlide('FUTURES & COMMODITIES')).toBe(false);
  expect(supportsAIScoreSlide('TORONTO STOCKS')).toBe(false);
});

test('rejects unavailable destinations and supports an intentional fallback', () => {
  expect(getBottomSlideIndex('ai_scores')).toBe(-1);
  expect(sanitizeBottomSlide('ai_scores')).toBe('trend_chart');
  expect(sanitizeBottomSlide('ai_scores', { fallback: 'wave_stats' })).toBe('wave_stats');
  expect(sanitizeBottomSlide('ai_scores', { hasAIScores: true })).toBe('ai_scores');
  expect(sanitizeBottomSlide('settings', { fallback: 'settings' })).toBe('trend_chart');
});

test('resolves numeric Swiper positions through the active semantic slide list', () => {
  expect(getBottomSlideName(2)).toBe('price_chart');
  expect(getBottomSlideName(2, { hasAIScores: true })).toBe('ai_scores');
  expect(getBottomSlideName(3, { hasAIScores: true })).toBe('price_chart');
  expect(getBottomSlideName(9, { hasAIScores: true, fallback: 'wave_stats' })).toBe('wave_stats');
});

test('preserves a saved AI Scores destination until market eligibility resolves', () => {
  expect(resolveBottomSlidePresentation('ai_scores', {
    hasAIScores: false,
    aiEligibilityResolved: false,
  })).toEqual({
    visibleSlide: 'wave_stats',
    preserveRequestedSlide: true,
  });
});

test('restores AI Scores when eligible and falls back only after an ineligible result', () => {
  expect(resolveBottomSlidePresentation('ai_scores', {
    hasAIScores: true,
    aiEligibilityResolved: true,
  })).toEqual({
    visibleSlide: 'ai_scores',
    preserveRequestedSlide: false,
  });
  expect(resolveBottomSlidePresentation('ai_scores', {
    hasAIScores: false,
    aiEligibilityResolved: true,
  })).toEqual({
    visibleSlide: 'wave_stats',
    preserveRequestedSlide: false,
  });
});

// --- Phone-portrait carousel (owner request 2026-08-17) --------------------

test('the AI slide sits between the bar chart and the price chart, and only on AI markets', () => {
  expect(getMobileSlides({ hasAIScores: true })).toEqual([
    'bar_chart', 'ai_scores', 'price_chart', 'trade_detail', 'cumulative_return', 'seasonal_chart',
  ])
  expect(getMobileSlides({ hasAIScores: false })).toEqual([
    'bar_chart', 'price_chart', 'trade_detail', 'cumulative_return', 'seasonal_chart',
  ])
  expect(getMobileSlides()).not.toContain('ai_scores')
})

test('legacy chartTo numbers keep their destinations after the AI slide is inserted', () => {
  // 0/1/2 have always meant bar chart / price chart / trade detail on a phone.
  // Inserting ai_scores at index 1 must not silently turn chartTo(1) into it.
  const withAI = { hasAIScores: true }
  expect(resolveMobileSlideIndex(0, withAI)).toBe(0)   // bar chart
  expect(resolveMobileSlideIndex(1, withAI)).toBe(2)   // price chart, shifted
  expect(resolveMobileSlideIndex(2, withAI)).toBe(3)   // trade detail, shifted

  const noAI = { hasAIScores: false }
  expect(resolveMobileSlideIndex(0, noAI)).toBe(0)
  expect(resolveMobileSlideIndex(1, noAI)).toBe(1)
  expect(resolveMobileSlideIndex(2, noAI)).toBe(2)
})

test('a semantic phone destination resolves, and ai_scores is unreachable off AI markets', () => {
  expect(resolveMobileSlideIndex('ai_scores', { hasAIScores: true })).toBe(1)
  expect(resolveMobileSlideIndex('seasonal_chart', { hasAIScores: true })).toBe(5)
  // Not present -> -1, so chartTo() no-ops instead of sliding somewhere wrong.
  expect(resolveMobileSlideIndex('ai_scores', { hasAIScores: false })).toBe(-1)
  expect(resolveMobileSlideIndex(undefined, { hasAIScores: true })).toBe(-1)
})

test('phone AI eligibility uses the same market allowlist as the desktop carousel', () => {
  for (const market of ['DOW 30 STOCKS', 'S&P 500 STOCKS', 'ETFs', 'etfs']) {
    expect(supportsAIScoreSlide(market)).toBe(true)
  }
  for (const market of ['CRYPTO CURRENCIES', 'INDICES ALL', 'FUTURES & COMMODITIES',
                        'FOREX ALL', 'GOVERNMENT BONDS', 'LONDON EXCHANGE', 'TORONTO STOCKS']) {
    expect(supportsAIScoreSlide(market)).toBe(false)
  }
})
