const SCORE_KEYS = ['Trend Long', 'Trend Short', 'Trend Long1', 'Trend Short1'];

const isFiniteScore = (value) => (
  value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
);

export const hasUsableTrendScore = (stats, direction = 'long') => {
  if (!stats || typeof stats !== 'object') return false;
  const hasAvailability = Object.prototype.hasOwnProperty.call(stats, 'Trend Score Available');
  const availability = stats['Trend Score Available'];
  if (availability === false || String(availability).toLowerCase() === 'false') return false;

  // Before the availability bit existed, an unavailable provider produced four
  // zeros. A real zero remains valid when the new response explicitly marks it so.
  const legacyAllZero = !hasAvailability && SCORE_KEYS.every(key => Number(stats[key]) === 0);
  if (legacyAllZero) return false;

  const scoreKey = direction === 'short' ? 'Trend Short' : 'Trend Long';
  return isFiniteScore(stats[scoreKey]);
};

export const hasUsableBatchTrendScore = (score) => {
  if (!score || typeof score !== 'object') return false;
  if (score.available === false || String(score.available).toLowerCase() === 'false') return false;
  const hasAvailability = Object.prototype.hasOwnProperty.call(score, 'available');
  const legacyAllZero = !hasAvailability && ['lscore', 'sscore', 'lscore1', 'sscore1']
    .every(key => Number(score[key]) === 0);
  return !legacyAllZero && isFiniteScore(score.lscore);
};

export const trendAlignmentLabel = (score) => {
  const numericScore = Number(score);
  if (!Number.isFinite(numericScore)) return 'Unavailable';
  if (numericScore > 60) return 'Aligned';
  if (numericScore < 40) return 'Against';
  return 'Neutral';
};
