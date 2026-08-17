// Keep lower-carousel state semantic so inserting an optional panel does not change
// what a saved destination means. The arrays are frozen because their order is the
// desktop Swiper contract.
export const BOTTOM_SLIDES = Object.freeze([
  'trend_chart',
  'wave_stats',
  'price_chart',
]);

export const BOTTOM_SLIDES_WITH_AI = Object.freeze([
  'trend_chart',
  'wave_stats',
  'ai_scores',
  'price_chart',
]);

const AI_SCORE_MARKETS = new Set([
  'DOW 30 STOCKS',
  'NASDAQ 100 STOCKS',
  'S&P 500 STOCKS',
  'RUSSELL 1000 STOCKS',
  'WILSHIRE 5000',
  'ETFS',
]);

export const supportsAIScoreSlide = market => (
  AI_SCORE_MARKETS.has(String(market || '').trim().toUpperCase())
);

// Phone portrait carries its own carousel. Same contract as the desktop lower
// carousel above: semantic names, so inserting the optional AI panel cannot
// silently change where an existing chartTo() destination lands. Owner decision
// 2026-08-17: AI Scores sit between the bar chart and the price chart.
export const MOBILE_SLIDES = Object.freeze([
  'bar_chart',
  'price_chart',
  'trade_detail',
  'cumulative_return',
  'seasonal_chart',
]);

export const MOBILE_SLIDES_WITH_AI = Object.freeze([
  'bar_chart',
  'ai_scores',
  'price_chart',
  'trade_detail',
  'cumulative_return',
  'seasonal_chart',
]);

// Chart headers shared with desktop still call chartTo(0/1/2). On phone portrait
// those numbers have always meant bar chart / price chart / trade detail, so map
// them to those names rather than to raw indices that the AI slide would shift.
export const MOBILE_LEGACY_SLIDES = Object.freeze([
  'bar_chart',
  'price_chart',
  'trade_detail',
]);

export const getMobileSlides = ({ hasAIScores = false } = {}) => (
  hasAIScores === true ? MOBILE_SLIDES_WITH_AI : MOBILE_SLIDES
);

export const getMobileSlideIndex = (slide, options = {}) => (
  getMobileSlides(options).indexOf(slide)
);

// Accepts a legacy number or a semantic name and returns the index to slide to,
// or -1 when the destination is not present (e.g. ai_scores on a non-AI market).
export const resolveMobileSlideIndex = (destination, { hasAIScores = false } = {}) => {
  const semantic = typeof destination === 'number'
    ? MOBILE_LEGACY_SLIDES[destination]
    : destination;
  if (!semantic) return -1;
  return getMobileSlideIndex(semantic, { hasAIScores });
};

export const getBottomSlides = ({ hasAIScores = false } = {}) => (
  hasAIScores === true ? BOTTOM_SLIDES_WITH_AI : BOTTOM_SLIDES
);

export const getBottomSlideIndex = (slide, options = {}) => (
  getBottomSlides(options).indexOf(slide)
);

export const sanitizeBottomSlide = (
  slide,
  { hasAIScores = false, fallback = 'trend_chart' } = {},
) => {
  const slides = getBottomSlides({ hasAIScores });
  if (slides.includes(slide)) return slide;
  if (slides.includes(fallback)) return fallback;
  return BOTTOM_SLIDES[0];
};

export const getBottomSlideName = (
  index,
  { hasAIScores = false, fallback = 'trend_chart' } = {},
) => {
  const slides = getBottomSlides({ hasAIScores });
  return Number.isInteger(index) && slides[index]
    ? slides[index]
    : sanitizeBottomSlide(fallback, { hasAIScores });
};

// A saved AI Scores destination must survive the short period before OppTable
// resolves the selected market's eligibility. Show Wave Stats as a harmless
// placeholder, but do not replace the saved semantic destination until the
// market has definitively resolved as unsupported.
export const resolveBottomSlidePresentation = (
  requestedSlide,
  {
    hasAIScores = false,
    aiEligibilityResolved = true,
    fallback = 'wave_stats',
  } = {},
) => {
  const preserveRequestedSlide = requestedSlide === 'ai_scores'
    && hasAIScores !== true
    && aiEligibilityResolved !== true;
  const visibleSlide = preserveRequestedSlide
    ? sanitizeBottomSlide(fallback, { hasAIScores: false })
    : sanitizeBottomSlide(requestedSlide, { hasAIScores, fallback });

  return {
    visibleSlide,
    preserveRequestedSlide,
  };
};
