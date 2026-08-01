import {
  hasUsableBatchTrendScore,
  hasUsableTrendScore,
  trendAlignmentLabel,
} from './trendScoreState';

const zeroScores = {
  'Trend Long': 0,
  'Trend Short': 0,
  'Trend Long1': 0,
  'Trend Short1': 0,
};

test('an explicitly available zero is real while the legacy all-zero fallback is missing', () => {
  expect(hasUsableTrendScore(zeroScores, 'long')).toBe(false);
  expect(hasUsableTrendScore({ ...zeroScores, 'Trend Score Available': true }, 'long')).toBe(true);
  expect(trendAlignmentLabel(0)).toBe('Against');
});

test('an unavailable provider never becomes an Against reading', () => {
  const stats = {
    ...zeroScores,
    'Trend Long': 85,
    'Trend Score Available': false,
  };
  expect(hasUsableTrendScore(stats, 'long')).toBe(false);
  expect(hasUsableBatchTrendScore({ lscore: 0, available: false })).toBe(false);
  expect(hasUsableBatchTrendScore({ lscore: 0, sscore: 0, lscore1: 0, sscore1: 0 })).toBe(false);
});

test('alignment thresholds preserve the product contract', () => {
  expect(trendAlignmentLabel(61)).toBe('Aligned');
  expect(trendAlignmentLabel(60)).toBe('Neutral');
  expect(trendAlignmentLabel(40)).toBe('Neutral');
  expect(trendAlignmentLabel(39)).toBe('Against');
});
