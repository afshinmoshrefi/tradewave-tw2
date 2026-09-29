export const BAR_CHART_EXCURSION_STYLES = Object.freeze({
  FILLED: 'filled',
  TICKS: 'ticks',
  NEEDLE: 'needle',
});

export const normalizeBarChartExcursionStyle = (style) => {
  const validStyles = Object.values(BAR_CHART_EXCURSION_STYLES);
  return validStyles.includes(style) ? style : BAR_CHART_EXCURSION_STYLES.FILLED;
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
