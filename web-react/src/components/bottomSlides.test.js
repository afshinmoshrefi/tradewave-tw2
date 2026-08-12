import {
  BOTTOM_SLIDES,
  BOTTOM_SLIDES_WITH_AI,
  getBottomSlideIndex,
  getBottomSlideName,
  getBottomSlides,
  resolveBottomSlidePresentation,
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
