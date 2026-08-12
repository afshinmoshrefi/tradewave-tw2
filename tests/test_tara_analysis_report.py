import pytest

import chatbot


pytestmark = pytest.mark.unit


def _row(role, label, symbol='MSFT'):
    return {
        'role': role,
        'label': label,
        'symbol': symbol,
        'company': 'Microsoft Corporation',
        'market': '2',
        'market_label': 'S&P 500 STOCKS',
        'start_date': '2026-10-01',
        'end_date': '2026-12-31',
        'direction': 'long',
        'sample_years': 10,
        'metrics': {
            'average_return_pct': 4.2,
            'median_return_pct': 3.8,
            'profitable_pct': 80.0,
            'best_return_pct': 12.0,
            'worst_return_pct': -5.0,
            'average_mfe_pct': 7.0,
            'average_mae_pct': -3.0,
            'sharpe_ratio': 1.3,
            'cumulative_return_pct': 51.0,
            'annualized_return_pct': 4.2,
            'winners': 8,
            'losers': 2,
        },
        'yearly_results': [
            {'year': year, 'return_pct': 4.0, 'mfe_pct': 7.0, 'mae_pct': -3.0}
            for year in range(2016, 2026)
        ],
    }


def _symbol_report():
    return {
        'schema_version': 1,
        'report_id': 'symbol-report-1',
        'report_type': 'symbol_comparison',
        'title': 'MSFT Symbol Comparison',
        'generated_at': '2026-08-07T12:00:00Z',
        'context': {
            'baseline_symbol': 'MSFT',
            'start_date': '2026-10-01',
            'end_date': '2026-12-31',
            'days_out': 92,
            'requested_years': 20,
            'years_used': 10,
            'history_adjusted': True,
            'history_adjustment_approved': True,
            'common_years': list(range(2016, 2026)),
            'pe_cycle': 'cons',
            'cut_off_year': 0,
            'direction': 'long',
            'history_availability': [
                {'symbol': 'MSFT', 'years': 40},
                {'symbol': 'NVDA', 'years': 10},
            ],
            'findings': {'highest_average_return': ['NVDA']},
        },
        'rows': [
            _row('baseline', 'MSFT (Current)'),
            _row('comparison', 'NVDA', 'NVDA'),
        ],
    }


def _range_report():
    selected = _row('selected_range', 'Excluded Date Range')
    outside = _row('remaining_range', 'Date Range Exclusion Model')
    outside.update({'start_date': '2026-01-01', 'end_date': '2026-09-30'})
    buy_hold = _row('buy_hold', 'Buy & Hold')
    buy_hold.update({'start_date': '2026-01-01', 'end_date': '2027-01-01'})
    return {
        'schema_version': 1,
        'report_id': 'range-report-1',
        'report_type': 'range_comparison',
        'title': 'forged title',
        'generated_at': '2026-08-07T12:00:00Z',
        'context': {
            'symbol': 'MSFT',
            'start_date': '2026-10-01',
            'end_date': '2026-12-31',
            'requested_years': 10,
            'years_used': 10,
            'history_adjusted': False,
            'history_adjustment_approved': False,
            'common_years': list(range(2016, 2026)),
            'pe_cycle': 'cons',
            'cut_off_year': 0,
            'reverse_source': 'wave_viewer_legacy_reverse_date_range',
        },
        'rows': [selected, outside, buy_hold],
    }


def test_report_cleaner_accepts_approved_common_history_snapshot():
    cleaned = chatbot._clean_analysis_report(_symbol_report())
    assert cleaned['report_id'] == 'symbol-report-1'
    assert cleaned['context']['years_used'] == 10
    assert cleaned['context']['history_adjustment_approved'] is True
    assert cleaned['rows'][1]['symbol'] == 'NVDA'
    assert cleaned['rows'][0]['metrics']['average_return_pct'] == 4.2


def test_report_cleaner_rejects_an_unapproved_history_reduction():
    report = _symbol_report()
    report['context']['history_adjustment_approved'] = False
    with pytest.raises(ValueError, match='unapproved history adjustment'):
        chatbot._clean_analysis_report(report)


def test_report_prompt_forbids_tools_and_recalculation():
    report = chatbot._clean_analysis_report(_symbol_report())
    prompt = chatbot.build_system_prompt({}, [], analysis_report=report)
    assert 'ACTIVE VALIDATED ANALYSIS REPORT' in prompt
    assert 'Do not call tools' in prompt
    assert 'Do not' in prompt and 'recalculate metrics' in prompt
    assert 'MSFT Symbol Comparison' in prompt
    assert 'NVDA' in prompt


def test_symbol_report_prompt_requires_plain_language_tradeoff_explanation():
    report = chatbot._clean_analysis_report(_symbol_report())
    prompt = chatbot.build_system_prompt({}, [], analysis_report=report)

    assert 'SYMBOL COMPARISON PLAIN-LANGUAGE CONTRACT' in prompt
    assert "profitable in X of Y years" in prompt
    assert "Do not say 'risk-adjusted performance' or 'drawdown'" in prompt
    assert "losses during the period were smaller on average" in prompt
    assert (
        'A higher Sharpe ratio means the historical returns were steadier compared with the amount '
        'of risk taken.'
    ) in prompt
    assert 'not a prediction' in prompt


def test_report_cleaner_rejects_scriptable_symbols_and_non_finite_metrics():
    report = _symbol_report()
    report['rows'][1]['symbol'] = '<script>'
    with pytest.raises(ValueError, match='invalid report symbol'):
        chatbot._clean_analysis_report(report)

    report = _symbol_report()
    report['rows'][1]['metrics']['average_return_pct'] = float('inf')
    with pytest.raises(ValueError, match='incomplete report metrics'):
        chatbot._clean_analysis_report(report)


def test_report_cleaner_rejects_non_finite_years_without_server_error():
    report = _symbol_report()
    report['context']['common_years'] = [float('inf')]
    with pytest.raises(ValueError, match='invalid analysis report'):
        chatbot._clean_analysis_report(report)


def test_symbol_report_requires_identical_dates_direction_and_cohort():
    report = _symbol_report()
    report['rows'][1]['direction'] = 'short'
    with pytest.raises(ValueError, match='mismatched comparison direction'):
        chatbot._clean_analysis_report(report)

    report = _symbol_report()
    report['rows'][1]['yearly_results'][-1]['year'] = 2015
    with pytest.raises(ValueError, match='mismatched report cohort'):
        chatbot._clean_analysis_report(report)


def test_range_report_requires_exact_roles_and_rebuilds_prompt_labels():
    cleaned = chatbot._clean_analysis_report(_range_report())
    assert cleaned['title'] == 'Date Range Exclusion Report'
    assert [row['label'] for row in cleaned['rows']] == [
        'Excluded Date Range', 'Date Range Exclusion Model', 'Buy & Hold',
    ]
    assert all(row['direction'] == 'long' for row in cleaned['rows'])
    assert all(row['company'] == 'MSFT' for row in cleaned['rows'])

    report = _range_report()
    report['rows'].append(_row('buy_hold', 'Duplicate'))
    with pytest.raises(ValueError, match='invalid range report size'):
        chatbot._clean_analysis_report(report)


def test_range_report_prompt_requires_scannable_sections_and_gates_covered_calls():
    report = chatbot._clean_analysis_report(_range_report())
    prompt = chatbot.build_system_prompt({}, [], analysis_report=report)

    assert 'RANGE EXCLUSION PLAIN-LANGUAGE CONTRACT' in prompt
    assert '<b>Bottom line</b>' in prompt
    assert '<b>Why</b>' in prompt
    assert '<b>Important</b>' in prompt
    assert '<b>Own the shares?</b>' in prompt
    assert 'Do not use Markdown asterisks' in prompt
    assert "never the 'selected window'" in prompt
    assert 'Do not mention Sharpe ratio in this first explanation' in prompt
    assert 'Do not explain options unless the user explicitly asks' in prompt
    assert 'COVERED-CALL FOLLOW-UP CONTRACT' in prompt
    assert '<b>How it works</b>' in prompt
    assert '<b>Main risk</b>' in prompt
    assert '<b>Before considering it</b>' in prompt
    assert 'Never recommend a trade, strike, expiration, uncovered call' in prompt
    assert 'PRECALCULATED EDUCATION VALUES' in prompt
    assert 'A hypothetical $10,000 becomes $15,100' in prompt


def test_range_report_rejects_short_trade_results():
    report = _range_report()
    report['rows'][0]['direction'] = 'short'
    with pytest.raises(ValueError, match='invalid range report direction'):
        chatbot._clean_analysis_report(report)
