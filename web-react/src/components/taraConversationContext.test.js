const {
  formatTaraPatternLabel,
  normalizeTaraPatternContext,
  resolveTaraActionPatternContext,
  taraConversationHasUserWork,
  taraPatternChangeWasChatDriven,
  taraPatternContextKey,
  taraPatternResetMessage,
} = require('./taraConversationContext');

const nvda = {
  market: '2',
  symbol: 'NVDA',
  entry_date: '2026-08-01',
  days_out: 104,
  years: 10,
  pe_cycle: 'cons',
  cut_off_year: 0,
};

test('formats a beginner-friendly inclusive date range', () => {
  expect(formatTaraPatternLabel(nvda)).toBe('NVDA · Aug 1-Nov 12 · 10 years');
  expect(taraPatternResetMessage(nvda)).toContain('Ask Tara about this chart.');
});

test('formats a cross-year range without hiding either year', () => {
  expect(formatTaraPatternLabel({
    ...nvda,
    symbol: 'AFL',
    entry_date: '2026-04-08',
    days_out: 312,
  })).toBe('AFL · Apr 8, 2026-Feb 13, 2027 · 10 years');
});

test('the context key changes for every analysis-defining input', () => {
  const original = taraPatternContextKey(nvda);
  ['market', 'symbol', 'entry_date', 'days_out', 'years', 'pe_cycle', 'cut_off_year']
    .forEach(field => {
      const replacements = {
        market: '3',
        symbol: 'MSFT',
        entry_date: '2026-07-01',
        days_out: 105,
        years: 20,
        pe_cycle: 'pe2',
        cut_off_year: 2020,
      };
      expect(taraPatternContextKey({ ...nvda, [field]: replacements[field] })).not.toBe(original);
    });
});

test('display-only settings are not part of the pattern identity', () => {
  expect(taraPatternContextKey({ ...nvda, show_mfe: false, show_mae: true }))
    .toBe(taraPatternContextKey(nvda));
});

test('resolves the final Tara target including opportunity-table years', () => {
  const target = resolveTaraActionPatternContext(nvda, [
    { type: 'set_view', spec: { symbol: 'MSFT', entry_date: '2026-07-01', days_out: 135 } },
    { type: 'load_opportunity', spec: { market: '3', years: 35 }, rank: 1 },
  ], { oppTableYears: '12', maxAvailableYears: 45 });
  expect(target).toEqual({
    market: '3',
    symbol: 'MSFT',
    entry_date: '2026-07-01',
    days_out: 135,
    years: 12,
    pe_cycle: 'cons',
    cut_off_year: 0,
  });
});

test('recognizes only actual user work as a previous chat', () => {
  expect(taraConversationHasUserWork([{ role: 'bot', text: 'Hello' }], [])).toBe(false);
  expect(taraConversationHasUserWork([{ role: 'user', text: 'Analyze this' }], [])).toBe(true);
  expect(taraConversationHasUserWork([], [{ role: 'user', content: 'Analyze this' }])).toBe(true);
});

test('preserves chat for Tara-driven changes but not unrelated manual changes', () => {
  const key = taraPatternContextKey(nvda);
  expect(taraPatternChangeWasChatDriven({ currentKey: key, pendingTargetKey: key })).toBe(true);
  expect(taraPatternChangeWasChatDriven({
    currentKey: key,
    actionState: { status: 'loading', request_key: key },
  })).toBe(true);
  expect(taraPatternChangeWasChatDriven({
    currentKey: key,
    actionState: { status: 'succeeded', request_key: key },
  })).toBe(false);
  expect(taraPatternChangeWasChatDriven({
    currentKey: key,
    pendingTargetKey: taraPatternContextKey({ ...nvda, symbol: 'MSFT' }),
  })).toBe(false);
});

test('rejects incomplete contexts so initial renders cannot reset chat', () => {
  expect(normalizeTaraPatternContext({ ...nvda, symbol: '' })).toBeNull();
  expect(taraPatternContextKey({ ...nvda, entry_date: '' })).toBe('');
});
