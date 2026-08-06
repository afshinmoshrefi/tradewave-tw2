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
