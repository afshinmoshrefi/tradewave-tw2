export const BAR_CHART_EXCURSION_STYLES = Object.freeze({
  FILLED: 'filled',
  TICKS: 'ticks',
  NEEDLE: 'needle',
});

export const normalizeBarChartExcursionStyle = (style) => {
  const validStyles = Object.values(BAR_CHART_EXCURSION_STYLES);
  return validStyles.includes(style) ? style : BAR_CHART_EXCURSION_STYLES.TICKS;
};

export const getExcursionVisibility = (direction, showMFE, showMAE) => {
  const isShort = direction === 'short';
  return {
    showHigh: isShort ? showMAE : showMFE,
    showLow: isShort ? showMFE : showMAE,
    highKind: isShort ? 'MAE' : 'MFE',
    lowKind: isShort ? 'MFE' : 'MAE',
  };
};

export const getNeedleRange = (high, low, showHigh, showLow) => {
  if (showHigh && showLow) return { from: low, to: high };
  if (showHigh) return { from: 0, to: high };
  if (showLow) return { from: low, to: 0 };
  return null;
};

export const getCappedNeedleCapHalfWidth = (barWidth) => {
  const safeBarWidth = Number.isFinite(barWidth) && barWidth > 0 ? barWidth : 12;
  return safeBarWidth / 4;
};

export const getPositionalExcursionColors = (mfeColor, maeColor) => ({
  highColor: mfeColor,
  lowColor: maeColor,
});

export const getBarChartZeroLineColor = (theme) => (
  theme === 'dark'
    ? 'rgba(220, 225, 232, 0.28)'
    : 'rgba(25, 30, 35, 0.24)'
);
