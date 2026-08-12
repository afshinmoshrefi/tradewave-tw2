const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const SYMBOL_RE = /^[A-Z0-9.-]{1,15}$/;
const VALID_CYCLES = new Set(['cons', 'pe0', 'pe1', 'pe2', 'pe3']);
const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

const positiveInteger = (value) => {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
};

const validDate = (value) => {
  if (typeof value !== 'string' || !DATE_RE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};

const normalizeCycle = (value) => {
  const cycle = String(value || 'cons').toLowerCase();
  return VALID_CYCLES.has(cycle) ? cycle : 'cons';
};

export const normalizeTaraPatternContext = (view) => {
  const source = view || {};
  const symbol = String(source.symbol || '').trim().toUpperCase();
  const entryDate = source.entry_date || source.start_date || '';
  const daysOut = positiveInteger(source.days_out);
  const years = positiveInteger(source.years);
  if (!SYMBOL_RE.test(symbol) || !validDate(entryDate) || !daysOut || !years) return null;

  return {
    market: String(source.market ?? ''),
    symbol,
    entry_date: entryDate,
    days_out: daysOut,
    years,
    pe_cycle: normalizeCycle(source.pe_cycle),
    cut_off_year: Math.max(0, Number.parseInt(String(source.cut_off_year || 0), 10) || 0),
  };
};

export const taraPatternContextKey = (view) => {
  const context = normalizeTaraPatternContext(view);
  if (!context) return '';
  return [
    context.market,
    context.symbol,
    context.entry_date,
    context.days_out,
    context.years,
    context.pe_cycle,
    context.cut_off_year,
  ].join('|');
};

const addCalendarDays = (dateString, count) => {
  const [year, month, day] = dateString.split('-').map(Number);
  const result = new Date(Date.UTC(year, month - 1, day + count));
  return result.toISOString().slice(0, 10);
};

const shortDate = (dateString, includeYear) => {
  const [year, month, day] = dateString.split('-').map(Number);
  return `${MONTH_NAMES[month - 1]} ${day}${includeYear ? `, ${year}` : ''}`;
};

const cycleLabel = (cycle) => {
  if (cycle === 'pe0') return 'PE election year';
  if (cycle === 'pe1') return 'PE+1';
  if (cycle === 'pe2') return 'PE+2';
  if (cycle === 'pe3') return 'PE+3';
  return '';
};

export const formatTaraPatternLabel = (view, compact = false) => {
  const context = normalizeTaraPatternContext(view);
  if (!context) return '';
  const endDate = addCalendarDays(context.entry_date, context.days_out - 1);
  const crossesYear = endDate.slice(0, 4) !== context.entry_date.slice(0, 4);
  const range = `${shortDate(context.entry_date, crossesYear)}-${shortDate(endDate, crossesYear)}`;
  const parts = [
    context.symbol,
    range,
    compact ? `${context.years}Y` : `${context.years} years`,
  ];
  const peLabel = cycleLabel(context.pe_cycle);
  if (peLabel) parts.push(peLabel);
  if (context.cut_off_year > 0) parts.push(`through ${context.cut_off_year}`);
  return parts.join(' · ');
};

export const taraPatternResetMessage = (view) => {
  const label = formatTaraPatternLabel(view);
  return label
    ? `<b>New chart loaded:</b> ${label}.<br>Ask Tara about this chart.`
    : 'A new chart was loaded. Ask Tara about this chart.';
};

export const taraConversationHasUserWork = (messages, history) => (
  (Array.isArray(history) && history.length > 0)
  || (Array.isArray(messages) && messages.some(message => message?.role === 'user'))
);

export const resolveTaraActionPatternContext = (
  currentView,
  actions,
  { oppTableYears, maxAvailableYears } = {},
) => {
  let target = normalizeTaraPatternContext(currentView);
  if (!target || !Array.isArray(actions)) return target;

  actions.forEach(action => {
    if (!action || !['set_view', 'load_opportunity'].includes(action.type)) return;
    const spec = action.spec;
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return;
    const next = { ...target };
    if (spec.market != null) next.market = String(spec.market);
    if (typeof spec.symbol === 'string') next.symbol = spec.symbol.toUpperCase();
    if (typeof spec.entry_date === 'string') next.entry_date = spec.entry_date;
    if (Number.isInteger(spec.days_out)) next.days_out = spec.days_out;
    if (Number.isInteger(spec.years)) next.years = spec.years;
    if (typeof spec.pe_cycle === 'string') next.pe_cycle = normalizeCycle(spec.pe_cycle);
    if (action.type === 'load_opportunity') {
      const tableYears = positiveInteger(oppTableYears);
      if (tableYears) next.years = tableYears;
    }
    const cap = positiveInteger(maxAvailableYears);
    if (next.pe_cycle === 'cons' && cap) next.years = Math.min(next.years, cap);
    target = normalizeTaraPatternContext(next) || target;
  });

  return target;
};

export const taraPatternChangeWasChatDriven = ({
  currentKey,
  pendingTargetKey,
  actionState,
}) => {
  if (!currentKey) return false;
  if (pendingTargetKey && currentKey === pendingTargetKey) return true;
  return Boolean(
    actionState
    && actionState.status === 'loading'
    && actionState.request_key === currentKey
  );
};
