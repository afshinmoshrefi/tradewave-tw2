const MAX_GUIDED_QUESTIONS = 3;

const cleanSymbol = (value) => {
  const symbol = String(value || '').trim().toUpperCase();
  return /^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol) ? symbol : '';
};

export const normalizeTaraGuidedQuestions = (value) => {
  if (!Array.isArray(value)) return [];
  const seen = new Set();
  const questions = [];
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const label = typeof item.label === 'string' ? item.label.trim().slice(0, 60) : '';
    const prompt = typeof item.prompt === 'string' ? item.prompt.trim().slice(0, 240) : '';
    const key = prompt.toLowerCase();
    if (!label || !prompt || seen.has(key)) continue;
    seen.add(key);
    questions.push({ label, prompt });
    if (questions.length === MAX_GUIDED_QUESTIONS) break;
  }
  return questions;
};

export const taraStarterQuestions = (currentSymbol) => {
  const symbol = cleanSymbol(currentSymbol);
  return normalizeTaraGuidedQuestions([
    {
      label: 'Find opportunities',
      prompt: "Show me today's strongest seasonal setups",
    },
    symbol ? {
      label: `Study ${symbol}`,
      prompt: `Analyze ${symbol}'s current seasonal pattern`,
    } : {
      label: 'Learn the method',
      prompt: 'How does TradeWave test a seasonal pattern?',
    },
    {
      label: 'Invest for years',
      prompt: 'Show me the Buy & Hold workflow for long-term investors',
    },
  ]);
};

export const taraRetryQuestions = (currentSymbol, originalPrompt = '') => {
  const symbol = cleanSymbol(currentSymbol);
  const retryPrompt = typeof originalPrompt === 'string'
    ? originalPrompt.trim().slice(0, 240)
    : '';
  return normalizeTaraGuidedQuestions([
    retryPrompt && {
      label: 'Try the question again',
      prompt: retryPrompt,
    },
    symbol && {
      label: `Retry ${symbol}`,
      prompt: `Load ${symbol}'s seasonal pattern again`,
    },
    {
      label: 'Choose another path',
      prompt: 'What can I research with Tara right now?',
    },
  ]);
};
