import { hasUsableTrendScore, trendAlignmentLabel } from './trendScoreState';

export const waveInfoRows = (stats, direction, showTWR) => {
  const scoreKey = direction === 'short' ? 'Trend Short' : 'Trend Long';
  const priorKey = `${scoreKey}1`;
  const available = hasUsableTrendScore(stats, direction);
  const score = stats[scoreKey];
  const prior = stats[priorKey];
  const rows = {
    'Percent Profitable': stats['Percent Profitable'],
    'Sharpe Ratio': stats['Sharpe Ratio'],
  };
  if (showTWR) rows['TradeWave Ratio'] = stats['Sharpe Ratio2'];
  rows['Trend Alignment'] = available
    ? `${trendAlignmentLabel(score)} · ${score}/100`
    : 'Unavailable';

  const priorAvailable = prior !== null && prior !== undefined && prior !== '' && Number.isFinite(Number(prior));
  const trendIcon = available && priorAvailable
    ? Number(score) > Number(prior) ? 'u' : Number(score) < Number(prior) ? 'd' : 'n'
    : '';
  return { rows, trendIcon };
};
