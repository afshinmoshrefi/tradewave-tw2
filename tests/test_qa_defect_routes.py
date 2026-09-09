"""User-reported Tara regressions through the real chat route and planner."""
import sys
from pathlib import Path

import pytest
from flask import Flask, g

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'appserver' / 'appserver'))
import chatbot
import tara_answer_planner as planner


@pytest.fixture
def chat(monkeypatch):
    monkeypatch.setattr(chatbot, 'log_question', lambda *a, **kw: None)
    monkeypatch.setattr(chatbot, 'select_tara_provider',
                        lambda *a, **kw: pytest.fail('Verified answers must bypass the model'))
    app = Flask(__name__)

    def ask(message, wave, context=None, history=None):
        calls = []
        def score(selected, token, market):
            assert 'ai_analysis' not in selected  # Never trust a browser's numeric claims.
            calls.append(selected.copy())
            return context
        app.extensions['tara_ai_analysis_context'] = score
        body = {'message': message, 'history': history or [], 'token': 'test-token',
                'wave_viewer': wave, 'screen_context': {}, 'opportunities': [],
                'opp_table_market': '2'}
        with app.test_request_context('/chatbot/chat', method='POST', json=body):
            g.chatbot_user_id = 'qa-regression'
            payload = chatbot.chat.__wrapped__().get_json()
        assert payload['actions'] == []
        return payload['reply'], calls
    return ask


@pytest.mark.parametrize('wave', [{}, {'symbol': 'KMB', 'days_out': '9', 'years': '10'}])
@pytest.mark.parametrize('message', [
    'How does TradeWave test a seasonal pattern?',
    'I am asking about the testing methodology, not for a shortlist. Explain how TradeWave tests a seasonal pattern, what the years count, and how win rate is calculated.',
])
def test_methodology_does_not_enter_screening_funnel(chat, wave, message):
    reply, calls = chat(message, wave, history=[{'role': 'user', 'content': 'Find seasonal patterns'}])
    assert 'How TradeWave tests' in reply
    assert 'completed sample' in reply
    assert 'Historical win rate' in reply
    assert 'curated ETF screen' not in reply
    assert not calls


@pytest.mark.parametrize('days, expected', [(9, '10 days and is not presented as an exact score'),
                                          (30, 'exact 30-day window'), (133, '90-day reading')])
def test_exact_window_question_uses_selected_horizon(chat, days, expected):
    message = 'Is the AI win chance displayed here for my exact nine-day window? Explain its scoring horizon.'
    reply, calls = chat(message, {'symbol': 'KMB', 'start_date': '2026-09-09',
                                'days_out': str(days), 'direction': 'short', 'years': '10'})
    assert expected in reply
    assert not calls


@pytest.mark.parametrize('message', [
    'What AI Win Chance percentage is currently displayed for this AAPL pattern, and is it the same as its historical win rate?',
    'The AI Scores panel is open now. What AI Win Chance percentage does it show for AAPL, and how does that differ from the historical win rate?',
])
@pytest.mark.parametrize('probability, label', [(0.75, '75%'), (0.0, '0%')])
def test_visible_probability_fetches_trusted_value(chat, message, probability, label):
    context = {'status': 'available', 'mode': 'pattern', 'full_pattern_calendar_days': 30,
               'horizons': [{'calendar_days': 30, 'win_probability': probability}]}
    reply, calls = chat(message, {'symbol': 'AAPL', 'days_out': '30',
                                'ai_analysis': {'win_probability': 0.99}}, context)
    assert len(calls) == 1
    assert '30-day AI Win Probability: ' + label in reply
    assert 'historical win rate' in reply
    assert '99%' not in reply


def test_missing_context_does_not_deny_website_data(chat):
    reply, calls = chat('What AI Win Chance is displayed?', {'symbol': 'AAPL'}, None)
    assert len(calls) == 1
    assert 'could not retrieve' in reply
    assert 'does not mean the AI Scores panel has no value' in reply


def test_initial_qa_analysis_retrieves_ai_context(chat):
    message = ('Explain this selected AAPL pattern. State its direction, entry and exit dates, '
               'holding period, completed years, wins and losses, average return, and what the AI probability means.')
    wave = {'symbol': 'AAPL', 'start_date': '2026-09-09', 'days_out': '30',
            'direction': 'long', 'years': '10', 'yearly_results': [
                {'year': year, 'underlying_return_pct': 2 if year % 2 else -1}
                for year in range(2016, 2026)]}
    context = {'status': 'available', 'mode': 'pattern', 'full_pattern_calendar_days': 30,
               'horizons': [{'calendar_days': 30, 'win_probability': 0.75}]}
    reply, calls = chat(message, wave, context)
    assert len(calls) == 1
    assert '75%' in reply
    assert 'AI' in reply and 'historical' in reply.lower()


def test_probability_definition_and_other_symbol_do_not_fetch_loaded_score():
    wave = {'symbol': 'AAPL'}
    assert not planner.is_loaded_ai_value_question('What does AI Win Probability mean?', wave)
    assert not planner.is_loaded_ai_value_question('What AI Win Probability is displayed for MSFT?', wave)
