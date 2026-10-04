"""Deterministic discovery of the owner-published US securities snapshots."""
import html
import re


MIDCAP = 'US Midcap Stocks ($2-10B)'
SP400 = 'S&P MidCap 400'
STOCKS = 'US Optionable Stocks & ADRs'
FUNDS = 'US Optionable ETFs & Funds'
LIST_MARKETS = {MIDCAP: '4', SP400: '4', STOCKS: '4', FUNDS: '11'}


def requested_security_list(question):
    text = re.sub(r'\s+', ' ', question.lower()).strip()
    mid = bool(re.search(r'\bmid[ -]?caps?\b', text))
    optionable = bool(re.search(r'\boptionable\b', text))
    if not (mid or optionable):
        return None
    # Leave ranking/analysis requests on their research path. This command owns
    # requests for the universe itself, including its exact name and bare aliases.
    if re.search(r'\b(best|strongest|buy|sell|trade|perform|rank|compare|analyze|analyse)\b', text):
        return None
    if mid:
        return SP400 if re.search(r'\b400\b|s\s*&\s*p', text) else MIDCAP
    return FUNDS if re.search(r'\betfs?\b|\bfunds?\b', text) else STOCKS


def build_security_list_command(question, token, claims, read_catalog, market_access):
    name = requested_security_list(question)
    if name is None:
        return None
    market = LIST_MARKETS[name]
    manual = (
        'To select it yourself, open Settings (gear icon in the left panel), then Securities Groups. '
        'choose Published Lists, check the list, then select its name in the securities dropdown.'
    )
    unavailable = {'reply': f'<b>{html.escape(name)}</b> is not available to this account right now. {manual}', 'actions': []}
    if not token:
        return unavailable
    status, payload = read_catalog('/get_published_lists', token)
    if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get('published_lists'), list):
        return {'reply': 'I could not retrieve the published securities lists. Please try again.', 'actions': []}
    matches = [item for item in payload['published_lists'] if isinstance(item, dict) and item.get('name') == name]
    if len(matches) != 1:
        return unavailable
    item = matches[0]
    level = str(claims.get('user_level', '1'))
    is_admin = bool(claims.get('is_admin'))
    allowed_markets = claims.get('lid') if isinstance(claims.get('lid'), list) else market_access.get(level, [])
    if (item.get('enabled', True) is not True or str(item.get('resource_id')) != market
            or (not is_admin and level not in item.get('access_levels', []))
            or market not in allowed_markets):
        return unavailable
    symbols = item.get('symbols')
    if not isinstance(symbols, list) or not symbols or any(not isinstance(s, str) or not re.fullmatch(r'[A-Z0-9.\-]{1,15}', s) for s in symbols):
        return {'reply': 'That published list could not be validated. Please try again after it is refreshed.', 'actions': []}
    count = len(set(symbols))
    description = {
        MIDCAP: 'US-listed stocks with market capitalizations from $2 billion to $10 billion.',
        SP400: 'The separate S&P MidCap 400 constituent snapshot.',
        STOCKS: 'US-listed optionable stocks and ADRs; ETFs and funds have a separate list.',
        FUNDS: 'US-listed optionable ETFs and funds; stocks and ADRs have a separate list.',
    }[name]
    explanation_only = bool(re.search(r'\bhow\b|\bwhere\b|\bwhat (?:is|are|does)\b|\bexplain\b|\bdon.t (?:switch|open|change)\b', question, re.I))
    actions = [] if explanation_only else [{'type': 'set_view', 'spec': {'market': market, 'published_list': name}}]
    reply = (
        f'<b>{html.escape(name)}</b>: {count:,} symbols. {description} '
        'This is a published snapshot; the opportunity table shows only members with detected patterns in the selected screen. '
        f'{manual}'
    )
    if name == MIDCAP:
        reply += ' Ask "show S&P MidCap 400" for the index list.'
    elif name == STOCKS:
        reply += ' Ask "show optionable ETFs" for the funds list.'
    return {'reply': reply, 'actions': actions}
