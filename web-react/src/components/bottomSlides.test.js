import {
  BOTTOM_SLIDES,
  BOTTOM_SLIDES_WITH_AI,
  getBottomSlideIndex,
  getBottomSlideName,
  getBottomSlides,
  sanitizeBottomSlide,
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

test('inserts AI Scores after Wave Stats without changing semantic destinations', () => {
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
