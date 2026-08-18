import {
  normalizeTaraGuidedQuestions,
  taraRetryQuestions,
  taraStarterQuestions,
} from './taraGuidedQuestions';

test('normalizes and caps server-provided guided questions', () => {
  expect(normalizeTaraGuidedQuestions([
    { label: ' First ', prompt: ' Ask one ' },
    { label: 'Duplicate', prompt: 'ask one' },
    { label: 'Second', prompt: 'Ask two' },
    null,
    { label: 'Third', prompt: 'Ask three' },
    { label: 'Fourth', prompt: 'Ask four' },
  ])).toEqual([
    { label: 'First', prompt: 'Ask one' },
    { label: 'Second', prompt: 'Ask two' },
    { label: 'Third', prompt: 'Ask three' },
  ]);
});

test('starter questions surface opportunity, current-pattern, and Buy & Hold paths', () => {
  const questions = taraStarterQuestions('aapl');

  expect(questions).toHaveLength(3);
  expect(questions[0].label).toBe('Find opportunities');
  expect(questions[1]).toEqual({
    label: 'Study AAPL',
    prompt: "Analyze AAPL's current seasonal pattern",
  });
  expect(questions[2].prompt).toMatch(/Buy & Hold workflow/);
});

test('starter questions never interpolate an invalid symbol', () => {
  const questions = taraStarterQuestions('AAPL<script>');

  expect(questions[1]).toEqual({
    label: 'Learn the method',
    prompt: 'How does TradeWave test a seasonal pattern?',
  });
});

test('retry questions preserve the failed question and provide a safe next path', () => {
  expect(taraRetryQuestions('SPY', 'Load the graph')).toEqual([
    { label: 'Try the question again', prompt: 'Load the graph' },
    { label: 'Retry SPY', prompt: "Load SPY's seasonal pattern again" },
    { label: 'Choose another path', prompt: 'What can I research with Tara right now?' },
  ]);
});
