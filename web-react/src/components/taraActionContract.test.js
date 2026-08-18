import {
  advanceTaraActionFromViewerReport,
  advanceTaraViewerDataState,
  containsInternalToolMarkup,
  isValidTaraPrimaryChartData,
  isValidTaraPrimaryPayload,
  isValidTaraPrimaryStats,
  isValidTaraTrendChartData,
  mergeTaraViewActions,
  normalizeTaraViewSpec,
  taraActionManifest,
  taraActionAllowsViewerRequest,
  taraActionRequiresChartData,
  taraEffectiveResponseMatches,
  taraRequestedSpecMatches,
  taraTrendFailureHasPrimaryData,
  taraTrendResponseMatches,
  taraViewKey,
} from './taraActionContract';


const receipt = 'c'.repeat(64);
const expires = 4102444800;

const signedActions = (entries, receiptExpiresAt = expires) => {
  const rows = entries.map(([id, spec]) => ({
    action_id: id.repeat(32),
    spec,
  }));
  const manifest = taraActionManifest(rows);
  return rows.map(row => ({
    ...row,
    turn_id: 'f'.repeat(32),
    type: 'set_view',
    status: 'validated',
    receipt,
    action_manifest: manifest,
    receipt_expires_at: receiptExpiresAt,
  }));
};

const action = (id, spec, receiptExpiresAt = expires) => (
  signedActions([[id, spec]], receiptExpiresAt)[0]
);


test('normalizes a strict complete view spec', () => {
  expect(normalizeTaraViewSpec({
    symbol: 'tsla',
    market: 2,
    entry_date: '2026-07-24',
    days_out: 21,
    years: 10,
    pe_cycle: 'consecutive',
  })).toEqual({
    symbol: 'TSLA',
    market: '2',
    entry_date: '2026-07-24',
    days_out: 21,
    years: 10,
    pe_cycle: 'cons',
  });
});


test.each([
  { entry_date: '2026-07-24' },
  { entry_date: '2026-02-30', days_out: 21 },
  { symbol: 'TSLA', unexpected: true },
])('rejects partial, impossible, or unknown view fields: %p', spec => {
  expect(normalizeTaraViewSpec(spec)).toEqual({});
});


test('accepts bounded duration and exact state-only controls', () => {
  expect(normalizeTaraViewSpec({ days_out: 367 })).toEqual({ days_out: 367 });
  expect(normalizeTaraViewSpec({ days_out: 368 })).toEqual({});
  expect(normalizeTaraViewSpec({
    show_mfe: true,
    show_mae: false,
    show_tooltips: true,
    bottom_slide: 'wave_stats',
  })).toEqual({
    show_mfe: true,
    show_mae: false,
    show_tooltips: true,
    bottom_slide: 'wave_stats',
  });
  expect(normalizeTaraViewSpec({ show_mfe: 'true' })).toEqual({});
  expect(normalizeTaraViewSpec({ bottom_slide: 'settings' })).toEqual({});
});


test('merges compatible signed actions and preserves audit proofs', () => {
  const actions = signedActions([
    ['a', { market: '2' }],
    ['b', {
      market: '2',
      symbol: 'TSLA',
      entry_date: '2026-07-24',
      days_out: 21,
    }],
  ]);
  const result = mergeTaraViewActions(actions);

  expect(result.ok).toBe(true);
  expect(result.spec).toEqual({
    market: '2',
    symbol: 'TSLA',
    entry_date: '2026-07-24',
    days_out: 21,
  });
  expect(result.actionProofs).toEqual([
    {
      action_id: 'a'.repeat(32),
      receipt,
      manifest: actions[0].action_manifest,
      spec: { market: '2' },
      expires_at: expires,
    },
    {
      action_id: 'b'.repeat(32),
      receipt,
      manifest: actions[0].action_manifest,
      spec: {
        market: '2',
        symbol: 'TSLA',
        entry_date: '2026-07-24',
        days_out: 21,
      },
      expires_at: expires,
    },
  ]);
});


test('rejects conflicting actions rather than applying the last setter', () => {
  const result = mergeTaraViewActions(signedActions([
    ['a', { market: '2' }],
    ['b', { market: '1' }],
  ]));
  expect(result).toMatchObject({
    ok: false,
    reason: 'conflicting_view_actions',
  });
});


test('rejects a missing or malformed action receipt', () => {
  const unsigned = action('a', { market: '2' });
  delete unsigned.receipt;
  expect(mergeTaraViewActions([unsigned])).toMatchObject({
    ok: false,
    reason: 'malformed_view_action',
  });
});


test('recomputes the Python-compatible complete action manifest', () => {
  const rows = [
    { action_id: 'b'.repeat(32), spec: {
      symbol: 'TSLA',
      market: '2',
      entry_date: '2026-07-24',
      days_out: 21,
    } },
    { action_id: 'a'.repeat(32), spec: { market: '2' } },
  ];
  expect(taraActionManifest(rows)).toBe(
    '18407cbbc7f2cc366441ef1ccdd1ef79bf8707f74a93d44b7b271e21ed54e623'
  );
});


test('rejects an expired action before applying it', () => {
  const expired = action('a', { market: '2' }, 100);
  expect(mergeTaraViewActions([expired], 100000)).toMatchObject({
    ok: false,
    reason: 'expired_action_receipt',
  });
});


test('rejects a valid-looking subset of a signed complete action set', () => {
  const actions = signedActions([
    ['a', { market: '2' }],
    ['b', { years: 20 }],
  ]);
  expect(mergeTaraViewActions([actions[0]])).toMatchObject({
    ok: false,
    reason: 'invalid_action_manifest',
  });
});


test('rejects a spec tampered after the manifest was signed', () => {
  const actions = signedActions([['a', { market: '2' }]]);
  actions[0].spec = { market: '1' };
  expect(mergeTaraViewActions(actions)).toMatchObject({
    ok: false,
    reason: 'invalid_action_manifest',
  });
});


test('validates usable ChartData4 rows and required stats', () => {
  const rows = [
    { year: 2024, pct: '4.2,7.1,-2.3', price: '100,104.2' },
    { year: '2025', pct: '-1.5,3.0,-4.8', price: '110,108.35' },
  ];
  const stats = {
    'Trade Dir': 'long',
    'Num Winners': '1',
    'Num Losers': '1',
    'Percent Profitable': '50%',
    'Avg Profit': '4.2%',
    'Sharpe Ratio': '0.81',
  };
  expect(isValidTaraPrimaryChartData(rows)).toBe(true);
  expect(isValidTaraPrimaryStats(stats)).toBe(true);
  expect(isValidTaraPrimaryPayload(rows, stats)).toBe(true);
  expect(isValidTaraPrimaryPayload([{}], stats)).toBe(false);
  expect(isValidTaraPrimaryPayload(
    [{ year: 2025, pct: '4.2,not-a-number,-2.3', price: '100,104.2' }],
    stats,
  )).toBe(false);
  expect(isValidTaraPrimaryPayload(
    [{ year: 2025, pct: '4.2,7.1,-2.3', price: 'not-a-price' }],
    stats,
  )).toBe(false);
  expect(isValidTaraPrimaryPayload(rows, { ...stats, 'Trade Dir': '' })).toBe(false);
});


test('validates every consolidated seasonal row before success', () => {
  const rows = Array.from({ length: 5 }, (_, index) => [
    `2026-07-${String(index + 1).padStart(2, '0')}`,
    40 + index,
  ]);
  expect(isValidTaraTrendChartData(rows)).toBe(true);
  expect(isValidTaraTrendChartData(Array(5).fill(null))).toBe(false);
  expect(isValidTaraTrendChartData([
    ...rows.slice(0, 4),
    ['2026-07-05', null],
  ])).toBe(false);
});


test('state-only acknowledgement checks only the requested fields', () => {
  const observed = {
    market: '2',
    symbol: '',
    entry_date: '2026-07-23',
    days_out: 30,
    years: 10,
    pe_cycle: 'cons',
  };
  expect(taraRequestedSpecMatches(observed, { market: '2' })).toBe(true);
  expect(taraRequestedSpecMatches(observed, { market: '1' })).toBe(false);
});


test('view keys include every ChartData4 input', () => {
  expect(taraViewKey({
    market: '2',
    symbol: 'tsla',
    entry_date: '2026-07-24',
    days_out: 21,
    years: 10,
    pe_cycle: 'pe2',
    cut_off_year: 2020,
  })).toBe('2|TSLA|2026-07-24|21|10|pe2|2020');
});

test('rejects a response normalized to a different date, years, or cutoff', () => {
  const requested = {
    market: '2',
    symbol: 'TSLA',
    entry_date: '2026-07-24',
    days_out: 21,
    years: 10,
    pe_cycle: 'cons',
  };
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, cut_off_year: 0 },
    0,
  )).toBe(true);
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-07-23', cut_off_year: 0 },
    0,
  )).toBe(false);
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, years: 5, cut_off_year: 0 },
    0,
  )).toBe(false);
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, cut_off_year: 2020 },
    0,
  )).toBe(false);
});

test('accepts only the established Jan 1 to Jan 2 Buy and Hold normalization', () => {
  const requested = {
    market: '0',
    symbol: 'MCD',
    entry_date: '2026-01-01',
    days_out: 366,
    years: 17,
    pe_cycle: 'cons',
  };

  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-01-02', cut_off_year: 0 },
    0,
  )).toBe(true);
  expect(taraEffectiveResponseMatches(
    requested,
    { ...requested, entry_date: '2026-01-03', cut_off_year: 0 },
    0,
  )).toBe(false);
});

test('requires the consolidated seasonal response to echo the exact request', () => {
  const request = {
    market: '2',
    symbol: 'TSLA',
    sy: 'pe2-10',
    chart_start_date: '2026-07-10',
    opp_start_date: '2026-07-24',
  };
  expect(taraTrendResponseMatches(request, request)).toBe(true);
  expect(taraTrendResponseMatches(
    request,
    { ...request, opp_start_date: '2026-08-01' },
  )).toBe(false);
});


test('chart data is required for a chart-backed action but not a market-only switch', () => {
  expect(taraActionRequiresChartData(
    { market: '2' },
    { market: '2', symbol: '' },
  )).toBe(false);
  expect(taraActionRequiresChartData(
    { market: '2', years: 20 },
    { market: '2', symbol: '' },
  )).toBe(false);
  expect(taraActionRequiresChartData(
    { years: 20 },
    { market: '2', symbol: 'TSLA' },
  )).toBe(true);
});

test('a Tara chart request waits until the viewer reaches the exact target generation', () => {
  const target = {
    market: '2',
    symbol: 'AFL',
    entry_date: '2026-04-08',
    days_out: 312,
    years: 10,
    pe_cycle: 'cons',
    cut_off_year: 0,
  };
  const actionState = {
    status: 'loading',
    requires_chart_data: true,
    request_key: taraViewKey(target),
    load_generation: 8,
  };

  expect(taraActionAllowsViewerRequest(
    actionState,
    { ...target, years: 35 },
    8,
  )).toBe(false);
  expect(taraActionAllowsViewerRequest(actionState, target, 7)).toBe(false);
  expect(taraActionAllowsViewerRequest(actionState, target, 8)).toBe(true);
});


test('detects provider-internal tool markup', () => {
  expect(containsInternalToolMarkup(
    '<function_calls><invoke><parameter>TSLA</parameter></invoke></function_calls>',
  )).toBe(true);
  expect(containsInternalToolMarkup('<b>TSLA</b> evidence')).toBe(false);
});


test('only the exact latest viewer request can complete a Tara action', () => {
  const tslaKey = '2|TSLA|2026-07-24|21|10|cons|0';
  const unhKey = '2|UNH|2026-07-24|21|10|cons|0';
  const pending = {
    status: 'loading',
    chart_started: false,
    request_key: tslaKey,
    load_generation: 7,
    required_sources: ['primary'],
  };
  const started = advanceTaraActionFromViewerReport(
    pending,
    { status: 'loading', request_key: tslaKey, load_generation: 7 },
    100,
  );
  expect(started.chart_started).toBe(true);

  const staleSuccess = advanceTaraActionFromViewerReport(
    started,
    {
      status: 'succeeded',
      request_key: unhKey,
      load_generation: 7,
      data_points: 10,
      view: { symbol: 'UNH' },
    },
    200,
  );
  expect(staleSuccess).toBe(started);

  const succeeded = advanceTaraActionFromViewerReport(
    started,
    {
      status: 'succeeded',
      request_key: tslaKey,
      load_generation: 7,
      data_points: 10,
      view: { symbol: 'TSLA' },
    },
    300,
  );
  expect(succeeded).toMatchObject({
    status: 'succeeded',
    data_points: 10,
    finished_at: 300,
    observed_view: { symbol: 'TSLA' },
  });
});


test('a new viewer load supersedes an already-started Tara action', () => {
  const result = advanceTaraActionFromViewerReport(
    {
      status: 'loading',
      chart_started: true,
      request_key: '2|TSLA|2026-07-24|21|10|cons|0',
      load_generation: 4,
      source_states: { primary: 'loading' },
    },
    {
      status: 'loading',
      request_key: '2|UNH|2026-07-24|21|10|cons|0',
      load_generation: 4,
      view: { symbol: 'UNH' },
    },
    400,
  );
  expect(result).toMatchObject({
    status: 'failed',
    reason: 'view_superseded',
    finished_at: 400,
    observed_view: { symbol: 'UNH' },
  });
});

test('an older same-key generation cannot complete a new action', () => {
  const key = '2|TSLA|2026-07-24|21|10|cons|0';
  const pending = {
    status: 'loading',
    request_key: key,
    load_generation: 9,
    required_sources: ['primary'],
  };
  const next = advanceTaraActionFromViewerReport(
    pending,
    {
      status: 'succeeded',
      request_key: key,
      load_generation: 8,
      data_points: 20,
    },
    100,
  );
  expect(next).toBe(pending);
});

test('both primary and consolidated data must succeed for a full view', () => {
  const key = '2|TSLA|2026-07-24|21|10|cons|0';
  const pending = {
    status: 'loading',
    request_key: key,
    load_generation: 3,
    required_sources: ['primary', 'trend'],
  };
  const primary = advanceTaraActionFromViewerReport(
    pending,
    {
      source: 'primary',
      status: 'succeeded',
      request_key: key,
      load_generation: 3,
      data_points: 10,
    },
    100,
  );
  expect(primary.status).toBe('loading');
  const complete = advanceTaraActionFromViewerReport(
    primary,
    {
      source: 'trend',
      status: 'succeeded',
      request_key: key,
      load_generation: 3,
      data_points: 365,
    },
    200,
  );
  expect(complete.status).toBe('succeeded');
  expect(complete.data_points).toBe(375);
});

test('viewer readiness also requires both chart sources', () => {
  const key = '2|TSLA|2026-07-24|21|10|cons|0';
  const primary = advanceTaraViewerDataState(
    null,
    {
      source: 'primary',
      status: 'succeeded',
      request_key: key,
      load_generation: 4,
      data_points: 10,
    },
  );
  expect(primary.status).toBe('loading');
  const failed = advanceTaraViewerDataState(
    primary,
    {
      source: 'trend',
      status: 'failed',
      request_key: key,
      load_generation: 4,
      reason: 'trend_network_error',
    },
  );
  expect(failed.status).toBe('failed');
  const ready = advanceTaraViewerDataState(
    primary,
    {
      source: 'trend',
      status: 'succeeded',
      request_key: key,
      load_generation: 4,
      data_points: 365,
    },
  );
  expect(ready.status).toBe('succeeded');
  expect(ready.data_points).toBe(375);
});


test('a trend-first failure does not claim that the primary pattern arrived', () => {
  expect(taraTrendFailureHasPrimaryData({
    reason: 'trend_network_error',
    source_states: { trend: 'failed' },
  })).toBe(false);
  expect(taraTrendFailureHasPrimaryData({
    reason: 'trend_network_error',
    source_states: { primary: 'loading', trend: 'failed' },
  })).toBe(false);
  expect(taraTrendFailureHasPrimaryData({
    reason: 'trend_network_error',
    source_states: { primary: 'succeeded', trend: 'failed' },
  })).toBe(true);
});


test('a manual primary-input refetch becomes ready after its matching trend verification', () => {
  const oldKey = '2|TSLA|2026-07-24|21|10|cons|0';
  const nextKey = '2|TSLA|2026-07-24|30|10|cons|0';
  const readyBeforeChange = {
    status: 'succeeded',
    request_key: oldKey,
    load_generation: 0,
    source_states: { primary: 'succeeded', trend: 'succeeded' },
    source_points: { primary: 10, trend: 365 },
  };
  const primaryLoading = advanceTaraViewerDataState(readyBeforeChange, {
    source: 'primary',
    status: 'loading',
    request_key: nextKey,
    load_generation: 0,
  });
  const primaryReady = advanceTaraViewerDataState(primaryLoading, {
    source: 'primary',
    status: 'succeeded',
    request_key: nextKey,
    load_generation: 0,
    data_points: 10,
  });
  expect(primaryReady.status).toBe('loading');
  const fullyReady = advanceTaraViewerDataState(primaryReady, {
    source: 'trend',
    status: 'succeeded',
    request_key: nextKey,
    load_generation: 0,
    data_points: 365,
  });
  expect(fullyReady).toMatchObject({
    status: 'succeeded',
    request_key: nextKey,
    source_states: { primary: 'succeeded', trend: 'succeeded' },
  });
});
