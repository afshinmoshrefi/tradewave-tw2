// Build the allowlisted UI snapshot Tara needs to explain what the user can actually see.
// This intentionally carries metadata and derived directional summaries only - never raw price series.

export const BOTTOM_SLIDES = ['trend_chart', 'wave_stats', 'price_chart'];
const BOTTOM_SLIDE_INDEX = Object.freeze(
  BOTTOM_SLIDES.reduce((indices, slide, index) => ({ ...indices, [slide]: index }), {}),
);
const WINDOW_PATH_STATES = ['supports', 'against', 'flat', 'unknown'];

const asArrayWithRows = (value) => Array.isArray(value) && value.length > 0;

// Preserve a genuine 0 while representing absent/invalid chart fields as null. MFE/MAE
// consumers must never turn missing path evidence into a false claim of zero adverse movement.
export const parseOptionalNumber = (value) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
};

// Keep Tara's server-side AI read on the same recurrence identity that produced
// the loaded opportunity row. The minimum-winning-years selection is provenance,
// not a model feature, but it must remain byte-for-byte consistent between the
// table request and Tara's later checkpoint request for both recurrence modes.
export const buildWaveViewerRecurrenceContext = (props = {}) => {
  const cycle = String(props.PEselected || 'cons').trim().toLowerCase();
  const mode = cycle.startsWith('pe') ? 'pe' : 'consecutive';
  const partialYears = String(props.oppTablePartialYears ?? '').trim();
  const context = { mode };
  if (/^[1-9]\d*$/.test(partialYears)) {
    context.partial_years = {
      min_winning_years: partialYears,
      mode,
    };
  }
  return context;
};

// Loading another setup in the same market must leave the opportunity list intact.
// OppTable deduplicates identical query URLs, so clearing same-market rows cannot
// trigger a replacement fetch and strands the table on "Loading ...". A real market
// change does alter the URL and may clear while that new list is fetched.
export const shouldClearOpportunityTable = (currentMarket, targetMarket) => {
  const current = String(currentMarket || '').trim();
  const target = String(targetMarket || '').trim();
  return target !== '' && target !== current;
};

// Tara is desktop-only, where the lower Swiper order is a stable semantic contract:
// Trend Chart, Wave Stats, Price Chart. Return whether a validated move was applied so
// unsupported values cannot accidentally move the carousel.
export const showBottomSlide = (swiper, slide) => {
  const index = BOTTOM_SLIDE_INDEX[slide];
  if (!Number.isInteger(index) || typeof swiper?.slideTo !== 'function') return false;
  swiper.slideTo(index);
  return true;
};

// Apply Tara's global guidance-tooltip action through the same App-level setter used by
// the visible toolbar switch. Return whether an action was applied so malformed values
// cannot be treated as booleans by JavaScript truthiness.
export const applyTooltipPreference = (spec, setTooltipsEnabled) => {
  if (typeof spec?.show_tooltips !== 'boolean' || typeof setTooltipsEnabled !== 'function') {
    return false;
  }
  setTooltipsEnabled(spec.show_tooltips);
  return true;
};

// Tara's ordinal commands refer to what the user can actually see, after TableBox applies
// its active-list mode, text filters, and current sort. Prefer that processed snapshot over
// the raw OppList4 order; use the raw rows only before TableBox has published its first snapshot.
export const buildOpportunityTableContext = (visibleRows, fallbackRows, limit = 50) => {
  const source = Array.isArray(visibleRows)
    ? visibleRows
    : (Array.isArray(fallbackRows) ? fallbackRows : []);
  const safeLimit = Number.isInteger(limit) && limit > 0 ? limit : 50;
  return source.slice(0, safeLimit).map(row => ({
    date: row?.date,
    symbol: row?.symbol,
    days_out: row?.daysOut,
    direction: row?.lOrS,
    avg_profit: row?.avg_profit,
    sharpe_ratio: row?.sharpe_ratio,
  }));
};

export const deriveDirectionFromBars = (bars, fallback = 'long') => {
  if (!Array.isArray(bars)) return fallback === 'short' ? 'short' : 'long';
  let upYears = 0;
  let downYears = 0;
  bars.forEach((row) => {
    const rawReturn = Number.parseFloat(String(row?.pct || '').split(',')[0]);
    if (rawReturn > 0) upYears += 1;
    if (rawReturn < 0) downYears += 1;
  });
  if (downYears > upYears) return 'short';
  if (upYears > downYears) return 'long';
  return fallback === 'short' ? 'short' : 'long';
};

// Summarize the normalized Trend Chart path over the loaded TradeWave window without
// sending the curve (or any raw prices) to Tara.  The curve is a 0-100 normalized index,
// so this intentionally reports direction only - never a percentage return.
export const deriveSeasonalWindowPath = (cycle, startDate, daysOut, direction = 'long') => {
  if (!Array.isArray(cycle) || cycle.length < 2) return 'unknown';
  const days = Number.parseInt(String(daysOut), 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(startDate || '')) || !Number.isInteger(days) || days < 1 || days > 367) {
    return 'unknown';
  }

  const start = new Date(`${startDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime())) return 'unknown';
  const end = new Date(start.getTime());
  // TradeWave counts the entry date as day 1.
  end.setUTCDate(end.getUTCDate() + days - 1);
  const endDate = `${end.getUTCFullYear()}-${String(end.getUTCMonth() + 1).padStart(2, '0')}-${String(end.getUTCDate()).padStart(2, '0')}`;

  const rows = cycle
    .map((row, index) => ({
      index,
      date: String(Array.isArray(row) ? row[0] : ''),
      value: Number(Array.isArray(row) ? row[1] : Number.NaN),
    }))
    .filter(row => /^\d{4}-\d{2}-\d{2}$/.test(row.date) && Number.isFinite(row.value));
  if (rows.length < 2) return 'unknown';

  const findRow = (target) => {
    const exact = rows.find(row => row.date === target);
    if (exact) return exact;
    const monthDay = target.substring(5);
    return rows.find(row => row.date.substring(5) === monthDay) || null;
  };

  const first = findRow(startDate);
  const last = findRow(endDate);
  // A reversed index means the supplied normalized cycle does not contain this whole
  // cross-year window in chronological order; returning unknown is safer than inferring
  // across the chart's normalization boundary.
  if (!first || !last || last.index < first.index) return 'unknown';

  const change = last.value - first.value;
  if (Math.abs(change) < 0.05) return 'flat';
  const supports = String(direction).toLowerCase() === 'short' ? change < 0 : change > 0;
  return supports ? 'supports' : 'against';
};

export const buildChatbotScreenContext = (props = {}) => {
  const swiperIndex = Number.isInteger(props.swiper?.activeIndex)
    ? props.swiper.activeIndex
    : Number(props.initialWindowNum);
  const activeIndex = Number.isInteger(swiperIndex) && swiperIndex >= 0 && swiperIndex <= 2
    ? swiperIndex
    : 0;

  const bars = Array.isArray(props.seasonalBarChartData) ? props.seasonalBarChartData : [];
  const direction = props.rowIndexClicked === -1
    ? deriveDirectionFromBars(bars, props.barChartLongOrShort)
    : (props.barChartLongOrShort === 'short' ? 'short' : 'long');
  const lastBar = bars.length > 0 ? bars[bars.length - 1] : null;
  const lineChartYear = props.lineChartYear == null ? '' : String(props.lineChartYear);
  const lastBarYear = lastBar?.year == null ? '' : String(lastBar.year);
  const latestPlaceholder = lastBar !== null && String(lastBar.pct || '') === '0,0,0';
  const sameYear = lastBarYear !== '' && lastBarYear === lineChartYear;

  // Mirrors StockLineChart's display contract: an initial/no-year chart is current; a zeroed
  // current-year placeholder is current; a non-zero current-year row can still be an active trade.
  const currentPriceChart = lineChartYear === '' || lineChartYear === '0' || (latestPlaceholder && sameYear);
  const activeTradeChart = !currentPriceChart && props.tradeActive === true && sameYear;
  const derivedPriceChartMode = currentPriceChart ? 'current' : (activeTradeChart ? 'active_trade' : 'historical');
  const derivedProjectionCapable = currentPriceChart || activeTradeChart;
  const priceChartIsActive = activeIndex === 2;

  // Prefer the small contract published by StockLineChart itself. It reflects
  // what was actually rendered, including projection eligibility; the derived
  // values remain a rolling-deploy and first-render fallback.
  const reportedPrice = props.priceChartContext && typeof props.priceChartContext === 'object'
    && (!props.priceChartContext.symbol || props.priceChartContext.symbol === props.symbol)
    && (!props.priceChartContext.start_date || props.priceChartContext.start_date === props.startDate)
    && (!props.priceChartContext.days_out || String(props.priceChartContext.days_out) === String(props.daysOut))
    && (!props.priceChartContext.years || String(props.priceChartContext.years) === String(props.seasonalYears))
    && (!props.priceChartContext.pe_cycle || props.priceChartContext.pe_cycle === (props.PEselected || 'cons'))
    ? props.priceChartContext
    : null;
  const reportedMode = reportedPrice?.mode;
  const priceChartMode = ['current', 'active_trade', 'historical'].includes(reportedMode)
    ? reportedMode
    : derivedPriceChartMode;
  const projectionCapable = reportedPrice
    ? reportedPrice.projection_capable === true
    : derivedProjectionCapable;

  const selectedProjectionVisible = priceChartIsActive
    && projectionCapable
    && (reportedPrice
      ? reportedPrice.selected_projection_visible === true
      : props.showProjection === true && asArrayWithRows(props.consolidatedSeasonalData));

  const selectedLookbackRaw = reportedPrice?.selected_years ?? props.seasonalYears;
  const fullHistoryYearsRaw = reportedPrice?.full_history_years ?? props.maxAvailableYears;
  const selectedLookback = selectedLookbackRaw == null ? '' : String(selectedLookbackRaw);
  const fullHistoryYears = fullHistoryYearsRaw == null ? '' : String(fullHistoryYearsRaw);
  const fullHistoryProjectionVisible = priceChartIsActive
    && projectionCapable
    && (reportedPrice
      ? reportedPrice.full_history_projection_visible === true
      : props.showMaxProjection === true && asArrayWithRows(props.maxYearsConsolidatedSeasonalData))
    && fullHistoryYears !== ''
    && fullHistoryYears !== '0'
    && selectedLookback !== fullHistoryYears;

  const rowCount = Number(props.oppTableLength);
  const context = {
    active_bottom_slide: BOTTOM_SLIDES[activeIndex],
    price_chart_mode: priceChartMode,
    selected_projection_visible: selectedProjectionVisible,
    full_history_projection_visible: fullHistoryProjectionVisible,
    opportunity_table_visible: true,
    selected_lookback: selectedLookback,
    full_history_years: fullHistoryYears,
    projection_period: (reportedPrice?.projection_period_days ?? props.projectionPeriod) == null
      ? ''
      : String(reportedPrice?.projection_period_days ?? props.projectionPeriod),
    opportunity_rows: Number.isFinite(rowCount) && rowCount >= 0 ? Math.floor(rowCount) : 0,
    selected_window_path: deriveSeasonalWindowPath(
      props.consolidatedSeasonalData,
      props.startDate,
      props.daysOut,
      direction,
    ),
    full_history_window_path: deriveSeasonalWindowPath(
      props.maxYearsConsolidatedSeasonalData,
      props.startDate,
      props.daysOut,
      direction,
    ),
  };

  // Keep the payload vocabulary closed even if a future refactor changes the helper.
  if (!WINDOW_PATH_STATES.includes(context.selected_window_path)) context.selected_window_path = 'unknown';
  if (!WINDOW_PATH_STATES.includes(context.full_history_window_path)) context.full_history_window_path = 'unknown';

  const reportedYear = reportedPrice?.year == null ? '' : String(reportedPrice.year);
  const priceChartYear = reportedYear || lineChartYear;
  if (priceChartMode !== 'current' && priceChartYear !== '') context.price_chart_year = priceChartYear;
  return context;
};
