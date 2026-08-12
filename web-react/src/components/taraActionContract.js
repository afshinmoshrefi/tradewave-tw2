const SYMBOL_RE = /^[A-Za-z0-9.-]{1,15}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ACTION_ID_RE = /^[a-f0-9]{32}$/i;
const RECEIPT_RE = /^[a-f0-9]{64}$/i;
const VALID_PE = new Set(['cons', 'consecutive', 'pe0', 'pe1', 'pe2', 'pe3']);
const VALID_MARKETS = new Set(
  Array.from({ length: 17 }, (_, i) => String(i)).filter(id => id !== '14' && id !== '15')
);
const VALID_FIELDS = new Set(['symbol', 'market', 'entry_date', 'days_out', 'years', 'pe_cycle']);

export const TARA_ACTION_TIMEOUT_MS = 30000;

const validDate = (value) => {
  if (typeof value !== 'string' || !DATE_RE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
};

const finiteNumberText = (value, allowPercent = false) => {
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value !== 'string' || value.trim() === '') return false;
  const normalized = allowPercent
    ? value.trim().replace(/%$/, '').replace(/,/g, '')
    : value.trim().replace(/,/g, '');
  return normalized !== '' && Number.isFinite(Number(normalized));
};

export const isValidTaraPrimaryChartData = (rows) => {
  if (!Array.isArray(rows) || rows.length === 0) return false;
  const years = new Set();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return false;
    const year = typeof row.year === 'string' && /^\d{4}$/.test(row.year)
      ? Number(row.year)
      : row.year;
    if (!Number.isInteger(year) || year < 1800 || year > 3000 || years.has(year)) {
      return false;
    }
    years.add(year);
    if (typeof row.pct !== 'string') return false;
    const pctParts = row.pct.split(',');
    if (
      pctParts.length !== 3
      || pctParts.some(value => !finiteNumberText(value))
    ) {
      return false;
    }
    if (typeof row.price !== 'string') return false;
    const priceParts = row.price.split(',');
    if (
      priceParts.length !== 2
      || priceParts.some(value => !finiteNumberText(value))
    ) {
      return false;
    }
  }
  return true;
};

export const isValidTaraPrimaryStats = (stats) => {
  if (!stats || typeof stats !== 'object' || Array.isArray(stats)) return false;
  if (!['long', 'short'].includes(String(stats['Trade Dir'] || '').toLowerCase())) {
    return false;
  }
  return (
    finiteNumberText(stats['Num Winners'])
    && finiteNumberText(stats['Num Losers'])
    && finiteNumberText(stats['Percent Profitable'], true)
    && finiteNumberText(stats['Avg Profit'], true)
    && finiteNumberText(stats['Sharpe Ratio'])
  );
};

export const isValidTaraPrimaryPayload = (rows, stats) => (
  isValidTaraPrimaryChartData(rows) && isValidTaraPrimaryStats(stats)
);

export const isValidTaraTrendChartData = (rows) => {
  if (!Array.isArray(rows) || rows.length < 5) return false;
  let previousDate = '';
  for (const row of rows) {
    if (
      !Array.isArray(row)
      || row.length !== 2
      || !validDate(row[0])
      || typeof row[1] !== 'number'
      || !Number.isFinite(row[1])
      || (previousDate && row[0] <= previousDate)
    ) {
      return false;
    }
    previousDate = row[0];
  }
  return true;
};

const rotateRight = (value, amount) => (
  ((value >>> amount) | (value << (32 - amount))) >>> 0
);

// Small synchronous SHA-256 implementation. The manifest input is guaranteed
// to be ASCII by the strict ViewSpec schema, matching Python's ensure_ascii.
const sha256Hex = (input) => {
  const constants = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ];
  const hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];
  const bytes = Array.from(input, character => {
    const code = character.charCodeAt(0);
    if (code > 0x7f) throw new Error('non_ascii_manifest_input');
    return code;
  });
  const bitLength = bytes.length * 8;
  bytes.push(0x80);
  while (bytes.length % 64 !== 56) bytes.push(0);
  for (let shift = 56; shift >= 0; shift -= 8) {
    bytes.push(shift >= 32 ? 0 : (bitLength >>> shift) & 0xff);
  }

  for (let offset = 0; offset < bytes.length; offset += 64) {
    const words = new Array(64);
    for (let i = 0; i < 16; i += 1) {
      const j = offset + i * 4;
      words[i] = (
        (bytes[j] << 24)
        | (bytes[j + 1] << 16)
        | (bytes[j + 2] << 8)
        | bytes[j + 3]
      ) >>> 0;
    }
    for (let i = 16; i < 64; i += 1) {
      const s0 = (
        rotateRight(words[i - 15], 7)
        ^ rotateRight(words[i - 15], 18)
        ^ (words[i - 15] >>> 3)
      ) >>> 0;
      const s1 = (
        rotateRight(words[i - 2], 17)
        ^ rotateRight(words[i - 2], 19)
        ^ (words[i - 2] >>> 10)
      ) >>> 0;
      words[i] = (words[i - 16] + s0 + words[i - 7] + s1) >>> 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let i = 0; i < 64; i += 1) {
      const sum1 = (rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25)) >>> 0;
      const choose = ((e & f) ^ ((~e) & g)) >>> 0;
      const temp1 = (h + sum1 + choose + constants[i] + words[i]) >>> 0;
      const sum0 = (rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22)) >>> 0;
      const majority = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const temp2 = (sum0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }

  return hash.map(word => word.toString(16).padStart(8, '0')).join('');
};

const canonicalJson = (value) => {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  return `{${Object.keys(value).sort().map(
    key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`
  ).join(',')}}`;
};

export const taraActionManifest = (actions) => {
  const rows = actions.map(action => ({
    action_id: String(action.action_id || '').toLowerCase(),
    spec: action.spec,
  })).sort((left, right) => (
    left.action_id < right.action_id ? -1 : (left.action_id > right.action_id ? 1 : 0)
  ));
  return sha256Hex(canonicalJson(rows));
};

export const normalizeTaraViewSpec = (spec) => {
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) return {};
  if (Object.keys(spec).some(key => !VALID_FIELDS.has(key))) return {};
  const out = {};

  if (Object.prototype.hasOwnProperty.call(spec, 'symbol')) {
    if (typeof spec.symbol !== 'string' || !SYMBOL_RE.test(spec.symbol)) return {};
    out.symbol = spec.symbol.toUpperCase();
  }
  if (Object.prototype.hasOwnProperty.call(spec, 'market')) {
    if (spec.market == null || !VALID_MARKETS.has(String(spec.market))) return {};
    out.market = String(spec.market);
  }
  if (Object.prototype.hasOwnProperty.call(spec, 'entry_date')) {
    if (!validDate(spec.entry_date)) return {};
    out.entry_date = spec.entry_date;
  }
  if (Object.prototype.hasOwnProperty.call(spec, 'days_out')) {
    if (!Number.isInteger(spec.days_out) || spec.days_out < 1 || spec.days_out > 366) return {};
    out.days_out = spec.days_out;
  }
  if (Object.prototype.hasOwnProperty.call(spec, 'years')) {
    if (!Number.isInteger(spec.years) || spec.years < 1 || spec.years > 99) return {};
    out.years = spec.years;
  }
  if (Object.prototype.hasOwnProperty.call(spec, 'pe_cycle')) {
    if (typeof spec.pe_cycle !== 'string' || !VALID_PE.has(spec.pe_cycle.toLowerCase())) return {};
    out.pe_cycle = spec.pe_cycle.toLowerCase() === 'consecutive'
      ? 'cons'
      : spec.pe_cycle.toLowerCase();
  }
  const hasEntry = Object.prototype.hasOwnProperty.call(out, 'entry_date');
  const hasDays = Object.prototype.hasOwnProperty.call(out, 'days_out');
  if (hasEntry !== hasDays) return {};
  return out;
};

export const mergeTaraViewActions = (actions, nowMs = Date.now()) => {
  if (!Array.isArray(actions) || actions.length === 0 || actions.length > 8) {
    return {
      ok: false,
      reason: 'invalid_action_count',
      actionIds: [],
      actionProofs: [],
      spec: {},
    };
  }

  const actionIds = [];
  const actionProofs = [];
  const manifestRows = [];
  let actionManifest = '';
  const merged = {};
  for (const action of actions) {
    if (
      !action
      || action.type !== 'set_view'
      || action.status !== 'validated'
      || typeof action.action_id !== 'string'
      || !ACTION_ID_RE.test(action.action_id)
      || typeof action.receipt !== 'string'
      || !RECEIPT_RE.test(action.receipt)
      || typeof action.action_manifest !== 'string'
      || !RECEIPT_RE.test(action.action_manifest)
      || !Number.isInteger(action.receipt_expires_at)
      || action.receipt_expires_at <= 0
    ) {
      return {
        ok: false,
        reason: 'malformed_view_action',
        actionIds: [],
        actionProofs: [],
        spec: {},
      };
    }
    if (action.receipt_expires_at <= Math.floor(nowMs / 1000)) {
      return {
        ok: false,
        reason: 'expired_action_receipt',
        actionIds: [],
        actionProofs: [],
        spec: {},
      };
    }
    const clean = normalizeTaraViewSpec(action.spec);
    if (Object.keys(clean).length === 0) {
      return {
        ok: false,
        reason: 'invalid_view_spec',
        actionIds: [],
        actionProofs: [],
        spec: {},
      };
    }
    const actionId = action.action_id.toLowerCase();
    const manifest = action.action_manifest.toLowerCase();
    if (actionManifest && manifest !== actionManifest) {
      return {
        ok: false,
        reason: 'conflicting_action_manifest',
        actionIds: [],
        actionProofs: [],
        spec: {},
      };
    }
    actionManifest = manifest;
    if (actionIds.includes(actionId)) {
      return {
        ok: false,
        reason: 'duplicate_action_id',
        actionIds: [],
        actionProofs: [],
        spec: {},
      };
    }
    for (const [key, value] of Object.entries(clean)) {
      if (Object.prototype.hasOwnProperty.call(merged, key) && merged[key] !== value) {
        return {
          ok: false,
          reason: 'conflicting_view_actions',
          actionIds: [],
          actionProofs: [],
          spec: {},
        };
      }
      merged[key] = value;
    }
    actionIds.push(actionId);
    manifestRows.push({ action_id: actionId, spec: action.spec });
    actionProofs.push({
      action_id: actionId,
      receipt: action.receipt.toLowerCase(),
      manifest,
      spec: clean,
      expires_at: action.receipt_expires_at,
    });
  }

  if (actionIds.length === 0 || Object.keys(merged).length === 0) {
    return {
      ok: false,
      reason: 'no_valid_view_actions',
      actionIds: [],
      actionProofs: [],
      spec: {},
    };
  }
  let computedManifest = '';
  try {
    computedManifest = taraActionManifest(manifestRows);
  } catch (error) {
    return {
      ok: false,
      reason: 'invalid_action_manifest',
      actionIds: [],
      actionProofs: [],
      spec: {},
    };
  }
  if (computedManifest !== actionManifest) {
    return {
      ok: false,
      reason: 'invalid_action_manifest',
      actionIds: [],
      actionProofs: [],
      spec: {},
    };
  }
  return {
    ok: true,
    reason: '',
    actionIds,
    actionProofs,
    actionManifest,
    spec: merged,
  };
};

export const taraViewKey = (view) => {
  const v = view || {};
  return [
    String(v.market ?? ''),
    String(v.symbol ?? '').toUpperCase(),
    String(v.entry_date ?? ''),
    String(v.days_out ?? ''),
    String(v.years ?? ''),
    String(v.pe_cycle ?? 'cons').toLowerCase(),
    String(v.cut_off_year ?? 0),
  ].join('|');
};

export const taraViewMatches = (observed, target) => {
  if (!observed || !target) return false;
  return taraViewKey(observed) === taraViewKey(target);
};

export const taraEffectiveResponseMatches = (
  requested,
  effective,
  requestedCutOffYear = 0,
  todayDate = '',
) => {
  if (!effective) return false;
  // ChartData4 has always moved Jan 1 to Jan 2 internally to avoid its
  // year-boundary edge case. Buy & Hold is still the Jan 1-to-Jan 1 feature
  // in the viewer; accept only this exact, established normalization while
  // continuing to reject every other server-adjusted date.
  const requestedEntryDate = String(requested?.entry_date ?? '');
  const todayYear = Number(String(todayDate || '').slice(0, 4));
  const requestedYear = Number(requestedEntryDate.slice(0, 4));
  // ChartData4 normalizes every future display year to the current year while
  // preserving its month/day. This is used by both election-cycle views and
  // ordinary consecutive patterns whose date window is moved into next year.
  const expectedFutureDateNormalization = (
    Number.isInteger(todayYear)
    && todayYear >= 1900
    && Number.isInteger(requestedYear)
    && requestedYear > todayYear
  );
  const normalizedEntryDate = expectedFutureDateNormalization
    ? `${todayYear}${requestedEntryDate.slice(4)}`
    : requestedEntryDate;
  const canonicalEntryDate = normalizedEntryDate.endsWith('-01-01')
    ? `${normalizedEntryDate.slice(0, 4)}-01-02`
    : normalizedEntryDate;
  const expected = {
    ...(requested || {}),
    entry_date: canonicalEntryDate,
    cut_off_year: Number(
      requested?.cut_off_year ?? requestedCutOffYear ?? 0
    ),
  };
  return taraViewKey(expected) === taraViewKey(effective);
};

export const taraTrendResponseMatches = (requested, effective) => {
  if (!requested || !effective) return false;
  return ['market', 'symbol', 'sy', 'chart_start_date', 'opp_start_date']
    .every(key => String(effective[key] ?? '') === String(requested[key] ?? ''));
};

export const taraRequestedSpecMatches = (observed, requestedSpec) => {
  if (!observed || !requestedSpec) return false;
  return Object.entries(requestedSpec).every(([key, value]) => {
    if (key === 'symbol') return String(observed[key] || '').toUpperCase() === value;
    if (key === 'market') return String(observed[key] ?? '') === value;
    if (key === 'pe_cycle') return String(observed[key] || 'cons').toLowerCase() === value;
    if (key === 'days_out' || key === 'years') return Number(observed[key]) === value;
    return observed[key] === value;
  });
};

export const taraActionRequiresChartData = (requestedSpec, target) => {
  if (!target || !target.symbol) return false;
  const requested = requestedSpec || {};
  return ['symbol', 'entry_date', 'days_out', 'years', 'pe_cycle']
    .some(key => Object.prototype.hasOwnProperty.call(requested, key));
};

export const taraActionAllowsViewerRequest = (
  actionState,
  requestView,
  loadGeneration,
) => {
  if (
    !actionState
    || actionState.status !== 'loading'
    || !actionState.requires_chart_data
  ) return true;

  return (
    Number(actionState.load_generation) === Number(loadGeneration)
    && actionState.request_key === taraViewKey(requestView)
  );
};

export const advanceTaraActionFromViewerReport = (previous, report, now = Date.now()) => {
  if (!previous || previous.status !== 'loading' || !report) return previous;
  const source = report.source === 'trend' ? 'trend' : 'primary';
  const sameGeneration = (
    Number.isInteger(previous.load_generation)
    && Number.isInteger(report.load_generation)
    && previous.load_generation === report.load_generation
  );
  const exactRequest = sameGeneration && previous.request_key === report.request_key;
  const sourceStates = { ...(previous.source_states || {}) };

  // A pre-existing request can have the same view key. Only the generation
  // assigned to this action may advance it.
  if (!sameGeneration) return previous;

  if (report.status === 'loading') {
    if (exactRequest) {
      if (sourceStates[source] === 'loading' || sourceStates[source] === 'succeeded') {
        return previous;
      }
      sourceStates[source] = 'loading';
      return {
        ...previous,
        chart_started: true,
        source_states: sourceStates,
      };
    }
    return sourceStates[source] === 'loading' || sourceStates[source] === 'succeeded'
      ? {
        ...previous,
        status: 'failed',
        reason: 'view_superseded',
        finished_at: now,
        observed_view: report.view || null,
      }
      : previous;
  }

  if (!exactRequest) return previous;
  if (report.status === 'failed') {
    return {
      ...previous,
      status: 'failed',
      reason: report.reason || `${source}_load_failed`,
      finished_at: now,
      observed_view: report.view || null,
      source_states: { ...sourceStates, [source]: 'failed' },
    };
  }
  if (report.status !== 'succeeded') return previous;

  sourceStates[source] = 'succeeded';
  const sourcePoints = {
    ...(previous.source_points || {}),
    [source]: Number.isInteger(report.data_points) ? report.data_points : 0,
  };
  const requiredSources = Array.isArray(previous.required_sources)
    ? previous.required_sources
    : ['primary'];
  const allReady = requiredSources.every(required => sourceStates[required] === 'succeeded');
  return {
    ...previous,
    status: allReady ? 'succeeded' : 'loading',
    reason: '',
    finished_at: allReady ? now : null,
    observed_view: report.view || null,
    data_points: Object.values(sourcePoints).reduce((sum, points) => sum + points, 0),
    source_states: sourceStates,
    source_points: sourcePoints,
  };
};

export const advanceTaraViewerDataState = (previous, report) => {
  if (!report || !['loading', 'succeeded', 'failed'].includes(report.status)) {
    return previous;
  }
  const prior = previous || {};
  const priorGeneration = Number.isInteger(prior.load_generation)
    ? prior.load_generation
    : -1;
  if (
    Number.isInteger(report.load_generation)
    && report.load_generation < priorGeneration
  ) {
    return previous;
  }
  const sameAttempt = (
    prior.request_key === report.request_key
    && priorGeneration === report.load_generation
  );
  const source = report.source === 'trend' ? 'trend' : 'primary';
  const sourceStates = sameAttempt ? { ...(prior.source_states || {}) } : {};
  const sourcePoints = sameAttempt ? { ...(prior.source_points || {}) } : {};
  sourceStates[source] = report.status;
  sourcePoints[source] = Number.isInteger(report.data_points) ? report.data_points : 0;

  let status = 'loading';
  if (Object.values(sourceStates).includes('failed')) {
    status = 'failed';
  } else if (
    sourceStates.primary === 'succeeded'
    && sourceStates.trend === 'succeeded'
  ) {
    status = 'succeeded';
  }
  return {
    status,
    request_key: report.request_key,
    load_generation: report.load_generation,
    view: report.view || null,
    data_points: Object.values(sourcePoints).reduce((sum, points) => sum + points, 0),
    reason: status === 'failed' ? (report.reason || prior.reason || '') : '',
    source_states: sourceStates,
    source_points: sourcePoints,
  };
};

export const taraTrendFailureHasPrimaryData = (actionState) => (
  String(actionState?.reason || '').startsWith('trend_')
  && actionState?.source_states?.primary === 'succeeded'
);

export const containsInternalToolMarkup = (text) => (
  /<\s*\/?\s*(?:function_calls?|invoke|parameter)\b/i.test(String(text || ''))
);
