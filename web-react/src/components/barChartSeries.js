// Pure year-by-year bar-series construction.  Every returned series is index-aligned
// with labels, including all-zero current/pre-history placeholders from ChartData4.

const finiteNumber = (value) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const rounded = (value) => Number(value.toFixed(2));

export const buildBarChartSeries = (rows, colors) => {
  const labels = [];
  const main = [];
  const mainColors = [];
  const upperRemainders = [];
  const lowerRemainders = [];

  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const parts = String(row?.pct || '').split(',');
    const close = finiteNumber(parts[0]);
    const high = finiteNumber(parts[1]);
    const low = finiteNumber(parts[2]);

    labels.push(row?.year);
    main.push(close);
    mainColors.push(close !== null && close < 0 ? colors.red : colors.green);

    let upper = null;
    let lower = null;
    if (close !== null && high !== null) {
      if (close >= 0 && high > 0) upper = rounded(high - close);
      else if (close < 0 && high >= 0) upper = rounded(high);
      else if (close < 0 && high < 0) upper = 0;
    }
    if (close !== null && low !== null) {
      if (close <= 0 && low < 0) lower = rounded(low - close);
      else if (close > 0 && low <= 0) lower = rounded(low);
      else if (close > 0 && low > 0) lower = 0;
    }

    // Push exactly once per label.  In particular, 0,0,0 must be null/null rather
    // than omitted; omission compresses the arrays and paints later years under old labels.
    upperRemainders.push(upper);
    lowerRemainders.push(lower);
  });

  return { labels, main, mainColors, upperRemainders, lowerRemainders };
};
