from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import datetime
import re
import sys
import os
import json
import logging
from functools import wraps
import jwt
from AI_tools_appserver import (
    send_claude_messages,
    CLAUDE_HAIKU_35,   # claude-3-5-haiku-20241022 - very cheap, fast
    CLAUDE_HAIKU_45,   # claude-haiku-4-5-20251001 - fast + cheap
    CLAUDE_SONNET_46,  # claude-sonnet-4-6 - strong + fast
    CLAUDE_OPUS_46,    # claude-opus-4-6 - most capable
)
from tradewave_api_calls_cb import (
    get_keyprovider_token, login_appserver, get_financial_groups,
    get_opp_list, get_years_pyears_from_resource_id,
    create_opportunity_url
)
# Phase 1: Tara calls the v1 gateway as a client (one source of truth). Falls back to the
# plain no-tools chat when the gateway is not configured. See docs/TARA_GATEWAY_INTEGRATION.md.
from tara_gateway import run_chat_with_tools, TARA_TOOLS_ENABLED


# -----------------------------------------------------------------
# SEC-C2 - local check_for_token decorator. Mirrors appserver.py's
# check_for_token (aud='tw2-appserver', iss='tw2-web', algorithms=['HS256']).
# Defined locally to avoid circular import: appserver.py imports chatbot_bp
# at module load before its own check_for_token is defined.
# Stashes decoded claims on flask.g.chatbot_jwt for the route to read.
# -----------------------------------------------------------------
def _client_meta():
    return (
        request.headers.get("X-Forwarded-For", request.remote_addr),
        request.headers.get("User-Agent", "-"),
    )


def check_for_token(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        # Token is accepted from query string (parity with appserver.py
        # check_for_token) and falls back to JSON body for chatbot/chat
        # which historically posted {"token": ...} as part of the body.
        token = request.args.get('token')
        if not token and request.is_json:
            try:
                token = (request.get_json(silent=True) or {}).get('token')
            except Exception:
                token = None
        if not token:
            ip, ua = _client_meta()
            logging.warning("chatbot.check_for_token: missing token ip=%s ua=%s", ip, ua)
            return jsonify({'message': 'Missing token'}), 403
        try:
            data = jwt.decode(
                token, current_app.config['SECRET_KEY'],
                algorithms=['HS256'],
                audience='tw2-appserver',
                issuer='tw2-web',
            )
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'session expired'}), 401
        except jwt.InvalidAudienceError:
            ip, ua = _client_meta()
            logging.warning("chatbot.check_for_token: invalid/missing audience ip=%s ua=%s", ip, ua)
            return jsonify({'message': 'invalid token'}), 401
        except jwt.InvalidIssuerError:
            ip, ua = _client_meta()
            logging.warning("chatbot.check_for_token: invalid/missing issuer ip=%s ua=%s", ip, ua)
            return jsonify({'message': 'invalid token'}), 401
        except jwt.DecodeError:
            ip, ua = _client_meta()
            logging.warning("chatbot.check_for_token: decode error ip=%s ua=%s", ip, ua)
            return jsonify({'message': 'invalid token'}), 401
        except jwt.InvalidTokenError:
            ip, ua = _client_meta()
            logging.warning("chatbot.check_for_token: invalid token ip=%s ua=%s", ip, ua)
            return jsonify({'message': 'invalid token'}), 401
        # Stash for the wrapped route - resolve user_id once, here.
        from flask import g
        g.chatbot_jwt = data
        g.chatbot_user_id = str(data.get('user') or data.get('sub') or data.get('user_id') or 'unknown')
        return func(*args, **kwargs)
    return wrapped

# -----------------------------------------------------------------
# Model selection - change this to test different models:
#   CLAUDE_HAIKU_35   very cheap  (~$0.001 / 1k tokens)
#   CLAUDE_HAIKU_45   cheap       (~$0.002 / 1k tokens)
#   CLAUDE_SONNET_46  balanced    (~$0.015 / 1k tokens)
#   CLAUDE_OPUS_46    most capable (~$0.075 / 1k tokens)
# -----------------------------------------------------------------
# -----------------------------------------------------------------
# Cache TTL - '5m' or '1h'
#   '5m' - $1.25/MTok to write, resets on every hit. Good for active users.
#   '1h' - $2.00/MTok to write, survives 1hr of inactivity. Good for sporadic use.
# -----------------------------------------------------------------
CACHE_TTL     = '5m'   # '1h' not yet enabled - see chatbot_readme.txt
CHATBOT_MODEL = CLAUDE_HAIKU_45

# Appended to the system prompt (recency: it must win over the base 'tell the user where to
# click' persona) when the gateway tools are live. Constant => stays cacheable across turns.
TOOL_INSTRUCTION = (
    "=== LIVE TOOLS (these OVERRIDE any earlier instruction about telling the user where to click) ===\n"
    "You have live tools that query the real TradeWave engine - find_best_opportunities, "
    "analyze_symbol, get_symbol_patterns, explain_pick - AND update_view, which lets YOU drive the "
    "wave-viewer directly. Rules:\n"
    "1) For anything needing current numbers (opportunities, a symbol's seasonality, the daily pick), "
    "CALL the right read tool and answer ONLY from its result - never invent setups, win rates, "
    "Sharpe ratios, or returns. EXCEPTION - ALREADY-LOADED PATTERN: when a pattern is already loaded "
    "and its stats + yearly_results are in your context, an ANALYTICAL question about THAT pattern "
    "('how strong / how good / how reliable is this', 'how did it do', 'why does it rank') is answered "
    "DIRECTLY from those provided stats - do NOT call a read tool and do NOT fire update_view (it is "
    "already on screen); state its % profitable (win rate), Sharpe, and avg return in <=2 sentences, and "
    "a bare 'Pattern loaded' / 'Loaded on the chart' with no stat is a HARD FAIL here too, even though no "
    "load action fired.\n"
    "2) When the user asks to LOAD / SHOW / OPEN / PULL UP a symbol or setup, or to CHANGE the years "
    "or PE cycle, you MUST call update_view and do it yourself. Do NOT tell them to use a dropdown, "
    "selectbox, or to click a row - you CAN drive the view for them. After update_view, say in one "
    "short line what you changed.\n"
    "3) For a date-range preset (a month/quarter/season), first call analyze_symbol with period= to "
    "get the resolved entry_date + days_out, then pass those to update_view.\n"
    "4) SCREENING / 'which <group> stocks ...' questions (e.g. 'which tech stocks tend to rise this time "
    "of year', 'best energy names now', 'top crypto setups'): MAP the group to its SINGLE market id "
    "(tech / technology = NASDAQ 100 = market 1; see the Securities Groups list above) and call "
    "find_best_opportunities with markets=<that one id> (just the id - no extra filters for a plain "
    "group screen). The result it returns IS the on-screen opportunity table for that group, sorted "
    "best-first; ANSWER by NAMING the TOP 3-5 with one stat each (avg return or Sharpe) and the entry "
    "date, so your list matches exactly what the user sees. If the table had been on a different group "
    "it switches to this one automatically - say so in one short line. Then add ONE line that more are "
    "in the table. NEVER answer a 'which stocks' question with steps to select a group, type a filter, "
    "or sort the table - call the tool and give the actual names.\n"
    "All figures are percentages, never price levels. Keep answers concise and plain-English.\n"
    "=== TWO HARD RULES, NO EXCEPTIONS ===\n"
    "A) NARRATE EVERY LOAD. Any turn that fires update_view MUST also contain, in the chat text, the "
    "symbol AND at least one real stat from the tool (win rate OR avg return OR Sharpe) AND, if the user "
    "asked a question, the answer to THAT question type: a yes/no gets yes/no; a 'why' gets the reason "
    "(top Sharpe / strongest seasonal edge / forward-tested record); a 'does it work / is it backtested' "
    "gets the made-in-advance-scored-later point in <=2 sentences; a compare gets ONE stat line PER named "
    "symbol + an 'X wins' verdict before you load the winner. A reply of 'Loaded on the chart', 'Pattern "
    "loaded', or any bare confirmation that omits the symbol+stat is a HARD FAIL. Never fire update_view "
    "on a pure pricing / coverage / definition question. When you load the BEST / top result and ALSO list "
    "runner-ups, NAME THE LOADED ONE FIRST with its stat ('FAST long, won 10/10 years, +16.1% - loaded'), "
    "then the others; leaving the loaded pick as a bare 'now on the chart' while you name OTHER tickers is a HARD FAIL.\n"
    "B) NEVER INSTRUCT A CLICK, EVEN WHEN A TOOL ERRORS OR THE ANSWER HAS A LOAD PATH. Forbidden in any "
    "reply: 'check/search the table', 'check the AI Score/PE column', 'switch the Securities Group', "
    "'check the PE+2 checkbox', 'use the Mode dropdown', 'filter manually'. If a read tool errors or "
    "returns nothing for a symbol, say so in ONE line and offer to scan the closest market or load a known "
    "symbol - do NOT hand a manual procedure. 'the first one' / 'that one' = #1 of your last list (load it, "
    "no menu). 'this window' / 'now' = the current seasonal window (resolve it, no 'which window?'). "
    "Concept / named-pattern questions (PE cycle, the 100-Year Pattern) are ANSWERED from knowledge + the "
    "matching guide; you may OFFER to load via update_view, but do NOT tell the user to click a "
    "checkbox/dropdown to learn it.\n"
    "C) LOOKBACK / YEARS CHANGE = FETCH THEN NARRATE THE NEW NUMBER. When the user asks to change the "
    "lookback or 'show me the N-year record / how it looks over N years' for the loaded pattern, you MUST "
    "call analyze_symbol(symbol, years=N) to GET the N-year stats AND update_view(years=N) to change the "
    "chart, then state the ACTUAL N-year result ('over 20 years: 18 of 20 winners, avg +X%'). NEVER "
    "describe what the chart 'will show' or 'whether it holds further back' - analyze_symbol takes a years "
    "param, so report what the DATA says over N years, not the bars."
)

# Initialize Blueprint
chatbot_bp = Blueprint("chatbot", __name__)

# Load knowledge base at startup
def _load_knowledge():
    try:
        path = os.path.join(os.path.dirname(__file__), 'chatbot_knowledge.txt')
        lines = []
        with open(path, 'r') as f:
            for line in f:
                stripped = line.rstrip()
                # Skip single-# comment lines but keep ## markdown headers
                if stripped.startswith('#') and not stripped.startswith('##'):
                    continue
                lines.append(stripped)
        return '\n'.join(lines).strip()
    except Exception as e:
        print(f'[WARN] Could not load chatbot_knowledge.txt: {e}')
        return ''

_KNOWLEDGE = _load_knowledge()

# Cache financial groups
financial_groups = get_financial_groups()
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def inc_date_day(d, i):
    return (datetime.datetime.strptime(d, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------
def inc_date_year(d, i):
    return ((datetime.datetime.strptime(d, '%Y-%m-%d') + relativedelta(years=i)).strftime('%Y-%m-%d'))
#-------------------------------------------------------------------------------------------------------------------
def get_appserver_token():
    """
    Dynamically fetch and return a valid appserver_token.
    """
    keyprovider_token = get_keyprovider_token()
    return login_appserver(keyprovider_token)

#-------------------------------------------------------------------------------------------------------------------
def calculate_end_date(start_date, num_days):
    """
    Calculate the inclusive end date based on the start_date and num_days.

    Args:
        start_date (str): The start date in the format 'YYYY-MM-DD'.
        num_days (str or int): Number of calendar days for the opportunity.

    Returns:
        str: The calculated end date in the format 'YYYY-MM-DD'.
    """
    num_days = int(num_days)  # Ensure num_days is an integer
    start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = start_date_obj + timedelta(days=max(num_days - 1, 0))
    return end_date_obj.strftime("%Y-%m-%d")

#-------------------------------------------------------------------------------------------------------------------
def parse_date(user_message):
    """
    Parse the date from the user's input message, including special expressions and misspellings.
    If no date is found, defaults to today's date.

    Args:
        user_message (str): The user's input message.

    Returns:
        tuple: (month, day) where month is the full name (e.g., "December") and day is a valid day of the month.
    """
    user_message_lower = user_message.lower()

    # Handle special expressions
    today = datetime.datetime.now()

    # Handle "today"
    if "today" in user_message_lower:
        return today.strftime("%B"), str(today.day)

    # Handle "tomorrow" with misspellings like "tommorow"
    if re.search(r"\btomm?or?row\b", user_message_lower):
        tomorrow = today + timedelta(days=1)
        return tomorrow.strftime("%B"), str(tomorrow.day)

    # Handle "yesterday"
    if "yesterday" in user_message_lower:
        yesterday = today - timedelta(days=1)
        return yesterday.strftime("%B"), str(yesterday.day)

    # Handle "day after tomorrow"
    if "day after tomorrow" in user_message_lower:
        day_after_tomorrow = today + timedelta(days=2)
        return day_after_tomorrow.strftime("%B"), str(day_after_tomorrow.day)

    # Handle "next week"
    if "next week" in user_message_lower:
        next_week = today + timedelta(days=7)
        return next_week.strftime("%B"), str(next_week.day)

    # Handle "next month"
    if "next month" in user_message_lower:
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)  # Safely calculate next month
        return next_month.strftime("%B"), str(next_month.day)

    # Parse specific dates like "January 15"
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d+)",
        user_message_lower,
        re.IGNORECASE
    )
    if date_match:
        month, day = date_match.groups()
        try:
            # Validate and return the date
            date = datetime.datetime.strptime(f"{month[:3]} {day}", "%b %d")
            return date.strftime("%B"), str(date.day)
        except ValueError:
            # Handle invalid dates like "February 30"
            return today.strftime("%B"), str(today.day)

    # Default to today's date if no match
    return today.strftime("%B"), str(today.day)

#-------------------------------------------------------------------------------------------------------------------
def construct_day_range(user_message):
    """
    Construct the day_range parameter based on user input.

    Args:
        user_message (str): The user's input message.

    Returns:
        tuple: (min_days, max_days) as integers, or None if no range is specified.
    """
    user_message_lower = user_message.lower()

    # Handle "shorter than X days" or "less than X days"
    shorter_than_match = re.search(r"(?:shorter than|less than) (\d+) days", user_message_lower)
    if shorter_than_match:
        max_days = int(shorter_than_match.group(1))
        return (2, max_days)  # Default min length to 2 days

    # Handle "between X and Y days" or "min length X and max length Y days"
    between_match = re.search(
        r"(?:between (\d+) and (\d+)|min length (\d+) and max length (\d+)) days",
        user_message_lower,
    )
    if between_match:
        min_days = int(between_match.group(1) or between_match.group(3))
        max_days = int(between_match.group(2) or between_match.group(4))
        return (min_days, max_days)

    # Return None if no valid range is specified
    return None



#-------------------------------------------------------------------------------------------------------------------
def get_resource_id(user_message):
    """
    Match financial group from user input. Handles variations like 's&p500', 's and p',
    'sandp500', and accounts for singular/plural forms like 'ETF' and 'ETFs'.
    """
    # Normalize user message
    user_message_lower = user_message.lower().replace("&", "and").replace("stocks", "").strip()

    # Handle special cases
    special_cases = {
        "s and p": "s&p 500",
        "sandp": "s&p 500",
        "sandp500": "s&p 500",
    }
    for key, value in special_cases.items():
        if key in user_message_lower:
            user_message_lower = user_message_lower.replace(key, value)

    user_keywords = set(user_message_lower.split())  # Split into individual keywords

    # Handle singular/plural normalization for user input
    user_keywords = {word.rstrip('s') if word.endswith('s') else word + 's' for word in user_keywords}

    best_match = None
    highest_match_score = 0  # Track the best match score

    for rid, group_name in financial_groups.items():
        # Normalize the group name
        group_name_lower = group_name.lower().replace("&", "and").replace("stocks", "").strip()
        group_keywords = set(group_name_lower.split())  # Split into individual keywords

        # Handle singular/plural normalization for group keywords
        group_keywords = {word.rstrip('s') if word.endswith('s') else word + 's' for word in group_keywords}

        # Calculate the match score as the number of overlapping keywords
        match_score = len(user_keywords & group_keywords)

        # Update the best match if this group has a higher score
        if match_score > highest_match_score:
            best_match = rid
            highest_match_score = match_score

    # Return the best match or default to Wilshire 5000 if no match found
    return best_match if best_match else "4"


#-------------------------------------------------------------------------------------------------------------------
def filter_results_by_day_range(results, min_days, max_days):
    """
    Filter results based on the specified day range.

    Args:
        results (list): The list of opportunities returned by get_opp_list.
        min_days (int): Minimum number of days.
        max_days (int): Maximum number of days.

    Returns:
        list: Filtered results.
    """
    filtered = []
    for opp in results:
        num_days = int(opp[2])  # Num days is at index 2 in the result
        if min_days <= num_days <= max_days:
            filtered.append(opp)
    return filtered

#-------------------------------------------------------------------------------------------------------------------
def get_opportunities(user_message, context="wordpress"):
    """
    Process the user's query to fetch financial opportunities and return an HTML table with responsive headers.
    """
    try:
        # Match financial group
        resource_id = get_resource_id(user_message)

        # Parse the date from the user's message
        month, day = parse_date(user_message)

        # Construct the day range
        day_range = construct_day_range(user_message)
        filter_explanation = ""
        if day_range:
            min_days, max_days = day_range
            if min_days == 2 and max_days:
                filter_explanation = f" less than {max_days} days"
            else:
                filter_explanation = f" between {min_days} and {max_days} days"

        # Get years and pyears
        years, pyears = get_years_pyears_from_resource_id(int(resource_id))

        # Fetch a valid appserver_token
        appserver_token = get_appserver_token()

        # Determine whether to use OppList or OppActiveList
        key = "OppActiveList" if "active" in user_message.lower() else "OppList"

        # Fetch opportunities
        result = get_opp_list(resource_id, month, day, years, pyears, "-", appserver_token)

        if not result or not result.get(key):
            return f"<p>No opportunities found in {key} for {financial_groups[resource_id]} on {month} {day}.</p>"

        # Filter results based on day range if specified
        opportunities = result[key]
        if day_range:
            min_days, max_days = day_range
            opportunities = filter_results_by_day_range(opportunities, min_days, max_days)

        # Define column headers for desktop and mobile
        headers_desktop = ["Symbol", "Start Date", "End Date", "Num Days", "Sharpe Ratio", "Avg Return"]
        headers_desktop_wv = ["SYM", "START", "END", "Days", "SR", "AVG_R"]
        headers_mobile = ["Sym", "Start", "Days", "SR", "AvgR"]

        table_headers = headers_desktop_wv if context == "wave-viewer" else headers_desktop

        # Build the desktop and mobile header rows
        header_desktop_html = "".join(
            f'<th style="border: 1px solid darkgray; padding: 8px;">{header}</th>'
            for header in table_headers
        )
        header_mobile_html = "".join(
            f'<th style="border: 1px solid darkgray; padding: 8px;">{header}</th>'
            for header in headers_mobile if header != "End"  # Skip "End Date" for mobile
        )

        # Build table rows with proper formatting and color coding
        table_rows = []
        for opp in opportunities[:5]:  # Limit to top 5 opportunities
            symbol = opp[1]
            start_date = opp[0]
            num_days = int(opp[2])
            sharpe_ratio = float(opp[4])
            avg_return = float(opp[5])

            # Calculate end date
            end_date = calculate_end_date(start_date, num_days)

            # Color coding for Sharpe Ratio
            sharpe_color = "green" if sharpe_ratio > 2 else "black"

            # Color coding for Avg Return
            return_color = "green" if avg_return > 5 else "black"

            # Create the wave-viewer URL for this opportunity
            anchor_url = create_opportunity_url(
                resource_id, symbol, start_date, num_days, 10  # history_years = 10
            )

            if context == "wordpress":
                # Existing WordPress behavior with anchor
                row_html = f"""
                    <tr style="cursor: pointer;" onclick="window.open('{anchor_url}', '_blank')">
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{symbol}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{start_date}</td>
                        <td class="hide-mobile" style="border: 1px solid darkgray; padding: 8px; text-align: center;">{end_date}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{num_days}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: right; color: {sharpe_color};">{sharpe_ratio:.2f}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: right; color: {return_color};">{avg_return:.2f}%</td>
                    </tr>
                """
            else:
                # New behavior for Wave Viewer with data-* attributes
                row_html = f"""
                    <tr style="cursor: pointer;"
                        data-rid="{resource_id}"
                        data-date="{start_date}"
                        data-tcsd="{inc_date_day(start_date, -14)}"
                        data-symbol="{symbol}"
                        data-days="{num_days}"
                        data-years="{years}">
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{symbol}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{start_date}</td>
                        <td class="hide-mobile" style="border: 1px solid darkgray; padding: 8px; text-align: center;">{end_date}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: center;">{num_days}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: right; color: {sharpe_color};">{sharpe_ratio:.2f}</td>
                        <td style="border: 1px solid darkgray; padding: 8px; text-align: right; color: {return_color};">{avg_return:.2f}%</td>
                    </tr>
                """
            table_rows.append(row_html)

        # Build the final HTML table
        table_html = f"""
        <table style="border-collapse: collapse; width: 100%; border: 1px solid darkgray; font-family: Arial, sans-serif;">
            <thead class="desktop-only">
                <tr style="background-color: #f2f2f2; font-weight: bold; text-align: center;">
                    {header_desktop_html}
                </tr>
            </thead>
            <thead class="mobile-only">
                <tr style="background-color: #f2f2f2; font-weight: bold; text-align: center;">
                    {header_mobile_html}
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        """

        # Return the table HTML with an explanatory message
        return f"<p>Here are the best wave opportunities I found for you{filter_explanation}! These are for {financial_groups[resource_id]} on {month} {day}:</p>{table_html}"

    except Exception as e:
        return f"<p>Error fetching opportunities: {str(e)}</p>"

#-------------------------------------------------------------------------------------------------------------------
# @chatbot_bp.route("/chat", methods=["POST"])
# def chat():
#     """
#     Endpoint to process chat messages and respond with OpenAI GPT or TradeWave APIs.
#     """
#     user_message = request.json.get("message", "")
#     try:
#         # Check if the user message contains relevant keywords
#         keywords = ["opportunities", "opportunity", "pattern", "patterns", "sharpe ratio","seasonal","seasonals","opps","opp"]
#         if any(keyword in user_message.lower() for keyword in keywords):
#             # If the message is about financial opportunities
#             bot_reply = get_opportunities(user_message)
#         else:
#             # Otherwise, use the default OpenAI GPT response
#             response = client.chat.completions.create(
#                 model="gpt-4",
#                 messages=[{"role": "user", "content": user_message}]
#             )
#             bot_reply = response.choices[0].message.content

#         return jsonify({"reply": bot_reply})

#     except Exception as e:
#         return jsonify({"reply": f"Error: {str(e)}"})

QUESTION_LOG    = os.path.join(os.path.dirname(__file__), 'chatbot_questions.log')
CHATBOT_USERS_FILE = os.path.join(os.path.dirname(__file__), 'chatbot_users.txt')

def _load_chatbot_users():
    """Read allowed user IDs from chatbot_users.txt. File is read fresh each call so no restart needed."""
    try:
        with open(CHATBOT_USERS_FILE, 'r') as f:
            return {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
    except Exception:
        return set()

@chatbot_bp.route("/chatbot_access", methods=["GET"])
@check_for_token
def chatbot_access():
    """Return {"allowed": true/false} for the user identified by the JWT token.

    SEC-C2 - this route is now protected by check_for_token (aud/iss/HS256
    enforced). The previous bare-except fail-open path that let unauthenticated
    callers in with user_id='unknown' is gone; check_for_token returns 401/403
    before this body runs if the token is missing or invalid.
    """
    from flask import g
    user_id = getattr(g, 'chatbot_user_id', 'unknown')
    # chatbot is available to all users (free and paid)
    allowed = True
    return jsonify({"allowed": allowed, "user_id": user_id})

def log_question(user_id, question, response, wave_viewer):
    """Append one JSON line per question to chatbot_questions.log."""
    try:
        entry = {
            'ts':       datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'user_id':  user_id,
            'symbol':   wave_viewer.get('symbol', ''),
            'question': question,
            'response': response[:500] if response else '',  # truncate long replies
        }
        with open(QUESTION_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception as e:
        print(f'[WARN] chatbot log failed: {e}')

#-------------------------------------------------------------------------------------------------------------------
def _is_short(direction):
    """Return whether a loaded TradeWave direction is short/bearish."""
    return str(direction or '').strip().lower().startswith('s')


def _as_float(value, default=0.0):
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('%', '').strip()
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value):
    try:
        return int(float(str(value).replace(',', '').replace('%', '').strip()))
    except (TypeError, ValueError):
        return None


def _raw_year_return(row):
    """Read the raw underlying-price return, including old React payloads.

    New clients send ``raw_return_pct``. During a rolling deploy, an older
    bundle may still send the same raw value under the misleading historical
    name ``return_pct``; retain that fallback until all clients have rolled.
    """
    if not isinstance(row, dict):
        return None
    value = row.get('raw_return_pct')
    if value is None:
        value = row.get('return_pct')
    if value is None:
        return None
    return _as_float(value, None)


def _trade_year_return(raw_return, direction):
    if raw_return is None:
        return None
    return -raw_return if _is_short(direction) else raw_return


def _is_trade_win(raw_return, direction):
    if raw_return is None:
        return False
    # Match ChartData4: long zero-return years are wins; short wins require the
    # underlying price to fall. (The current-year zero stub is excluded first.)
    return raw_return < 0 if _is_short(direction) else raw_return >= 0


def _trade_excursions(row, direction):
    raw_mfe = _as_float((row or {}).get('mfe_pct'))
    raw_mae = _as_float((row or {}).get('mae_pct'))
    if _is_short(direction):
        return -raw_mae, -raw_mfe
    return raw_mfe, raw_mae


def _loaded_trade_status(wave_viewer, today=None):
    """Return upcoming/active/completed for the loaded current-year window."""
    wv = wave_viewer or {}
    start_date = str(wv.get('start_date') or '')
    days_out = wv.get('days_out')
    if not start_date or days_out in (None, ''):
        return 'upcoming'
    try:
        today = today or datetime.datetime.now().date()
        trade_start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
        # The engine enters on the next available market day when the calendar
        # start is a weekend. The inclusive calendar end date never moves.
        if trade_start.weekday() == 5:
            trade_start += timedelta(days=2)
        elif trade_start.weekday() == 6:
            trade_start += timedelta(days=1)
        trade_end = datetime.datetime.strptime(
            calculate_end_date(start_date, days_out), '%Y-%m-%d'
        ).date()
        if today < trade_start:
            return 'upcoming'
        if today <= trade_end:
            return 'active'
        return 'completed'
    except (TypeError, ValueError):
        return 'upcoming'


def _completed_year_rows(wave_viewer, today=None):
    """Yield completed rows only; ChartData4's current-year zero stub is not history."""
    wv = wave_viewer or {}
    today = today or datetime.datetime.now().date()
    current_year = today.year
    current_status = _loaded_trade_status(wv, today)
    completed = []
    for row in wv.get('yearly_results') or []:
        if not isinstance(row, dict) or _raw_year_return(row) is None:
            continue
        try:
            year = int(row.get('year'))
        except (TypeError, ValueError):
            continue
        if year < current_year or (year == current_year and current_status == 'completed'):
            completed.append(row)
    return completed


def _historical_record(wave_viewer):
    """Return direction-aware winners/losers, preferring engine aggregate stats."""
    wv = wave_viewer or {}
    stats = wv.get('stats') or {}
    winners = _as_int(stats.get('Num Winners'))
    losers = _as_int(stats.get('Num Losers'))
    if winners is not None and losers is not None:
        return winners, losers

    direction = wv.get('direction', 'long')
    rows = _completed_year_rows(wv)
    winners = sum(_is_trade_win(_raw_year_return(row), direction) for row in rows)
    return winners, len(rows) - winners


def _pattern_date_labels(wave_viewer):
    wv = wave_viewer or {}
    start_date = str(wv.get('start_date') or '')
    days_out = wv.get('days_out')
    if not start_date or days_out in (None, ''):
        return '', '', ''
    try:
        end_date = calculate_end_date(start_date, days_out)
        start_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        end_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        return start_obj.strftime('%b %-d'), end_obj.strftime('%b %-d'), end_date
    except (TypeError, ValueError):
        return start_date, '', ''


def _projection_period_label(value):
    days = _as_int(value)
    return {
        14: '2-week',
        30: '1-month',
        60: '2-month',
        90: '3-month',
    }.get(days, f'{days}-day' if days is not None else 'selected-horizon')


def _visible_lower_view_overview(wave_viewer):
    """Explain the lower Wave Viewer slide the client says is actually visible."""
    wv = wave_viewer or {}
    slide = str(wv.get('visible_slide') or '').strip().lower()
    start_label, end_label, _ = _pattern_date_labels(wv)
    date_range = f" ({start_label} to {end_label})" if start_label and end_label else ''

    if slide == 'trend_chart':
        return (
            "<b>Bottom chart - Trend Chart:</b> This compresses the selected historical years "
            f"into their typical seasonal price path and highlights the loaded window{date_range}. "
            "It shows recurring timing and shape, not a forecast of this year's result."
        )

    if slide == 'wave_stats':
        winners, losers = _historical_record(wv)
        sample = winners + losers
        sample_text = f" across {sample} completed years" if sample else ''
        return (
            "<b>Bottom panel - Wave Stats:</b> This is the direction-adjusted numerical breakdown"
            f"{sample_text}: winners, losers, average gain/loss, Sharpe, cumulative return, and "
            "the comparison metrics for the same loaded window."
        )

    if slide == 'price_chart':
        price = wv.get('price_chart') or {}
        mode = str(price.get('mode') or '').lower()
        if mode == 'historical' and price.get('year'):
            intro = f"This shows the underlying's actual price action for {price.get('year')} around the loaded window{date_range}."
        else:
            timeframe = str(price.get('timeframe') or 'daily').lower()
            intro = f"This shows the underlying's actual current {timeframe} price action and where the loaded window{date_range} sits in context."

        projection_bits = []
        if price.get('selected_projection_visible'):
            horizon = _projection_period_label(price.get('projection_period_days'))
            selected_years = str(price.get('selected_years') or wv.get('years') or '').strip()
            sample = f"loaded {selected_years}-year sample" if selected_years else "loaded historical sample"
            projection_bits.append(
                f"The dashed golden line is the {horizon} seasonal projection from the {sample}, anchored to the latest close"
            )
        if price.get('full_history_projection_visible'):
            horizon = _projection_period_label(price.get('projection_period_days'))
            full_years = _as_int(price.get('full_history_years'))
            sample = f"all {full_years} available consecutive years" if full_years else "all available consecutive years"
            projection_bits.append(
                f"the dashed purple line is the {horizon} full-history projection from {sample}"
            )

        projection_text = ''
        if projection_bits:
            projection_text = " " + "; ".join(projection_bits) + ". These are rescaled historical-average guides, not price predictions."
            if _is_short(wv.get('direction')):
                projection_text += " For this short setup, a falling projected path is favorable to the trade and a rising path is unfavorable."
        return "<b>Bottom chart - Price Chart:</b> " + intro + projection_text

    # Rolling-deploy fallback for an older client that has not begun sending the
    # active slide yet. Name the lower panel without pretending to know which of
    # its three views is currently selected.
    return (
        "<b>Bottom panel:</b> Its three slides add the typical seasonal path (Trend Chart), "
        "the numerical record (Wave Stats), and actual market context (Price Chart)."
    )


_LOADED_OVERVIEW_Q = re.compile(
    r"\bwhat\s+(?:am|are)\s+(?:i|we)\s+looking\s+at\b|"
    r"\b(?:explain|describe|walk\s+me\s+through)\s+(?:this|the)\s+"
    r"(?:setup|pattern|chart|window)\b|\bwhat\s+is\s+this\s+(?:setup|pattern|chart|window)\b",
    re.I,
)


def _loaded_pattern_overview(user_message, wave_viewer):
    """Build the authoritative short explanation without asking an LLM to infer signs."""
    wv = wave_viewer or {}
    symbol = str(wv.get('symbol') or '').strip().upper()
    if not symbol or not _LOADED_OVERVIEW_Q.search(user_message or ''):
        return None

    direction = 'short' if _is_short(wv.get('direction')) else 'long'
    days = _as_int(wv.get('days_out'))
    start_label, end_label, _ = _pattern_date_labels(wv)
    date_range = f", {start_label} to {end_label}" if start_label and end_label else ''
    setup = f"<b>{symbol} {direction}{date_range}</b> is a {direction} seasonal window"
    if days is not None:
        day_word = 'day' if days == 1 else 'days'
        setup += f" covering exactly {days} calendar {day_word}; TradeWave counts {start_label or 'the entry date'} as day 1"
    setup += "."

    stats = wv.get('stats') or {}
    winners, losers = _historical_record(wv)
    sample = winners + losers
    pct = str(stats.get('Percent Profitable') or '').strip()
    avg_win = str(stats.get('Avg Profit') or '').strip()
    avg_loss = str(stats.get('Avg Loss') or '').strip()
    sharpe = str(stats.get('Sharpe Ratio') or '').strip()
    cumulative = str(stats.get('Cumulative Return') or '').strip()

    if direction == 'short':
        record = (
            f"<b>Top bar chart:</b> Historically, the price fell in {winners} of {sample} completed years"
            if sample else "Historically, price-down years are the profitable years"
        )
        record += "; those red/down bars are profitable short years, while green/up bars are losing short years."
    else:
        record = (
            f"<b>Top bar chart:</b> Historically, the price rose or held flat in {winners} of {sample} completed years"
            if sample else "Historically, price-up years are the profitable years"
        )
        record += "; green/up bars are profitable long years, while red/down bars are losing long years."

    stat_bits = []
    if pct:
        stat_bits.append(f"{pct} profitable")
    if avg_win:
        stat_bits.append(f"average winner {avg_win}")
    if avg_loss:
        stat_bits.append(f"average loser {avg_loss}")
    if sharpe:
        stat_bits.append(f"Sharpe {sharpe}")
    if cumulative:
        stat_bits.append(f"cumulative return {cumulative}")
    stats_line = " Direction-adjusted stats: " + ", ".join(stat_bits) + "." if stat_bits else ''
    lower_view = _visible_lower_view_overview(wv)
    return setup + "<br><br>" + record + stats_line + "<br><br>" + lower_view


def build_system_prompt(wave_viewer, opportunities, opp_table_length=None,
                        opp_table_market=None, opp_table_market_name=None):
    """Build a system prompt that gives the LLM awareness of the wave viewer and opp table."""
    parts = [
        "You are Tara, the AI assistant for TradeWave, a seasonal trading pattern analysis platform by Tara Data Research.",
        "You help traders understand seasonal trading patterns, analyse opportunities, and interpret statistics.",
        "RESPONSE STYLE: Be very short and confident. A simple/single answer is at most 2 sentences; a list is at most 5 one-liners. Never recite a full card, a year-by-year table, best/worst/median years, an order ticket, position sizing, a pricing-tier breakdown, or a multi-step how-to procedure in chat - that content lives on the screen or in a guide. No bullet-list feature tours. No filler ('Great question', 'Of course', 'I'd be happy to'). Never end with a question like 'is that what you meant?' or a clarifying menu when the answer is inferable. Just answer and drive the view.",
        "YOU DRIVE, YOU NEVER TELL THE USER TO CLICK (CORE RULE): Tara is the interface - whenever the answer is a pattern/setup/symbol/stat that has a screen, YOU put it there with update_view and point to it. NEVER say 'click a row', 'click any opportunity', 'use the dropdown', 'select X', 'check the opportunity table', or hand the user a click/configure procedure - that is a hard failure. (A) SINGLE pick / best-trade / a named symbol / 'the best one' / 'show me something good': the read tool returns a ready `headline` (e.g. 'BLDR long - enter ~Jun 22, hold 30d. Won 9/10 years, avg +11.7%, Sharpe 1.1.'). You MUST call update_view to load it AND your reply MUST be that headline verbatim-or-lightly-tidied. A reply that loads the chart but does not NAME the symbol and at least ONE real stat from the tool (win rate OR avg return) is a HARD FAIL - never reply 'Pattern loaded', 'Loaded on the chart', 'Loaded on screen', or any confirmation that omits the symbol+stat. Use the tool's exact numbers, never a rounded '90%'. Do not append a disclaimer unless the user asked whether to trade/buy/sell. (B) LIST / 'best setups' / 'which <group> stocks': up to 5 lines, each symbol + ONE stat, then one short line 'Want me to pull one up?' For a sub-index sector (energy, financials, healthcare), scan the closest market and NAME the matching tickers from the results - never say the scan is 'picking the best overall names' or ask the user to filter.",
        "INFER, DON'T PUNT: Resolve obvious context yourself and act - do not re-ask. NEVER open with 'I need context', 'I need more info', 'Are you asking...', 'Could you clarify', or restate the question back as a question when a pattern is loaded - the loaded pattern + the opportunity table ARE the context, so just answer. 'The first one' / 'that one' = the #1 item of the list you just gave; 'this pattern' / 'this setup' / 'how did it do in <year>' / 'why this pick' / 'why does this rank here' / 'why is it ranked here' / 'where does it rank' / 'compare this to the S&P' = the currently loaded pattern (use the loaded-pattern context, its stats, its rank in the opportunity table, and yearly_results given to you); for a 'why does this rank here' question name the loaded symbol's Sharpe + its position in the table and the one reason in <=2 sentences (it is Sharpe-ranked, so a higher-Sharpe row outranks it) - do NOT dump a multi-bullet breakdown, do NOT load or re-load anything (it is already on screen), and NEVER reply with a bare 'loaded' / 'pattern loaded on screen' - this is an ANALYTICAL question, so ANSWER it from the loaded stats + the table; 'how strong / how good / how reliable is this' (this window / this setup / this pattern) = an ANALYTICAL STRENGTH question about the ALREADY-LOADED pattern: answer in <=2 sentences straight from the loaded stats - its % profitable (win rate, e.g. won X of Y years), Sharpe, avg return, and how many years (sample size) - do NOT call a tool, do NOT load or re-load (it is already on screen), and a bare 'pattern loaded' / 'loaded on the chart' with no stat is a HARD FAIL; 'this window' / 'now' = the current seasonal window; a global knob ('change years to 20', 'switch to PE+2') applies to whatever is loaded - fire update_view with that one field and confirm in one line, never ask which symbol. A named ticker with no other detail ('what about apple?') = fetch its top current setup, name one stat, and load it. Only ask a clarifying question when the request is genuinely ambiguous AND nothing reasonable can be loaded - and even then, offer a concrete default ('want today's pick?'), never a 3-way menu. A bare knob command ('switch to PE+2', 'change years to 20', 'make it 45 days') fires update_view with JUST that field EVEN WITH NOTHING LOADED - it applies when a pattern is next/already loaded; never refuse with 'I need a symbol first' (you fire years with no symbol, so fire pe_cycle the same way). For a documented UI-gap where the user NAMED the target ('flip to the price chart tab', 'the stats') give the ONE-line pointer ('Price Chart is slide 3 - swipe to it') and STOP - never dump a numbered 3-slide menu and never end on 'which one?'. For a named sector ETF (XLE, XLF, XLK, SMH) call get_symbol_patterns(symbol) and name its best window + load it - do NOT punt with 'may not be in scope' unless the tool itself returns an out-of-scope nudge.",
        "NEVER PROMISE AN ACTION YOU DON'T FIRE, NEVER RE-ASK WHEN INFERABLE: If your reply says you will load / pull up / compare something, the matching update_view MUST be in this turn's actions - 'Let me load each...' with no action is a HARD FAIL. 'pull up the first one' = the #1 row of the most recent scan/list (load it, do not show a menu). 'this window' / 'now' with no date = the current seasonal window (resolve it, do not ask 'which window?'). For a 2-3 symbol comparison, read each with analyze_symbol, NAME the stronger with one stat for each, THEN update_view the winner in the SAME turn. For a proof / skeptic / yes-no question where you have already resolved a concrete symbol+entry (e.g. NVDA's July window, today's pick), ALSO fire update_view so the record is on screen - answering in text without loading the resolved pick is a screen-control fail.",
        "COMPARISON IS A HARD CONTRACT (X vs Y, 'which is better', 2-3 named symbols): you MUST emit, in THIS turn, (1) ONE stat line per named symbol from analyze_symbol - symbol + win rate or avg return + window, (2) a one-line 'X wins because <higher win rate / Sharpe>' verdict, THEN (3) update_view loading the winner. A reply that loads one symbol with no per-symbol stat for the OTHER(S), or a bare 'GDX is now on the chart', or that asks 'which window do you mean' (= the current/now window - resolve it, never ask) is a HARD FAIL. Never claim to put more than one on screen; load only the winner and offer 'say the word and I'll pull up the other.'",
        "DO NOT AUTO-LOAD ON THESE - answer first, load only if asked: a pure DEFINITION ('what is this?', 'what is a seasonal pattern?'), a GREETING ('hi'), a capability ask ('what can you do?'), or a LIST / 'best setups' / 'strongest setups' / 'top N' / 'only high win-rate ones' / 'which <group> stocks' ask. For a definition/greeting/capability: 1-2 plain sentences + offer one concrete next move ('want today's pick or the best setups now?'), and fire NO set_view. For a LIST ask: up to 5 one-liners (symbol + one stat each) + 'Want me to pull one up?' and do NOT LOAD A PATTERN (no symbol set_view). EXCEPTION: a 'which <group> stocks' ask MAY fire a market-only update_view to switch the opportunity table to that group when it is not already there, so your named rows match the screen - switching the table's group is not loading a pattern. A plural 'setups' or any quality floor (high win-rate, only the best ones) is ALWAYS a list - emit up to 5 named one-liners and load no pattern, even if the phrasing sounds singular. Auto-loading a PATTERN (a symbol into the chart) on any of these is a fail. Single-pick / named-symbol / 'show me something good' asks DO load (rule A).",
        "ANSWER THE QUESTION TOO, NOT JUST LOAD: Loading the chart does not replace answering. A yes/no ('is NVDA seasonal in July?') gets a direct yes/no + one real stat from the tool. A 'why is this the pick' gets the actual reason (top Sharpe / strongest seasonal edge / forward-tested record). A specific-year question ('how did 2022 do?') is answered directly from yearly_results - never say you can't see the chart or tell the user to read the bars. A proof/skeptic question ('does this actually work / is it just backtested?') gets ~2 confident sentences from the forward-tested record (made-in-advance picks scored later), not a definitions lecture. If a specific-year question names a symbol/window that is NOT yet loaded (e.g. 'how did NVDA's July setup do in 2022', 'show me the price chart for 2008'), first fire set_view to LOAD that pattern so its yearly_results populate, then answer that year from the data. If you genuinely lack the year's number, say so in one line and offer to load it - NEVER write 'find the 20XX bar' or 'click the bar'.",
        "MISSING-PROJECTION WHY-QUESTION ('why is there no projection line', 'where did the projection go'): if the loaded view uses a PE cycle phase OTHER than the current year's phase, the projection is hidden BY DESIGN - the view shows the next matching FUTURE cycle year, and a future window has no current price to anchor a forward projection to. This is an ANALYTICAL question: answer that reason in 1-2 sentences and STOP. Firing ANY set_view/update_view this turn, changing the user's PE mode uninvited, or reciting the Settings enable-steps is a HARD FAIL - the user chose that PE slice on purpose. End with one short offer ('Want me to flip back to consecutive so the projection returns?') and fire update_view with pe_cycle ONLY after the user says yes. If the PE mode is NOT the cause, check the viewed chart before reciting enable-steps: on a PAST year's historical chart the projection is hidden by design - point the user to the Current button in the price chart title bar (one line); for a pattern whose window already ENDED this year (completed trade) there is no live price to project from - say so in one line and offer to load a live pattern. Give the Settings enable-steps ONLY when the mode is consecutive (or the current year's own phase), the live/current-year chart is showing, and the projection is still absent.",
        "WHEN THERE IS NO DRIVING ACTION (documented UI gaps - slide/tab switch, click a year bar, highlight a year, open watchlist/portfolio): do NOT fall back to 'click a row'. Either answer from the data you already have (e.g. name the worst year + its loss from yearly_results), or point precisely to where it lives in ONE line ('Wave Stats is slide 2, swipe to it' / 'Price Chart is slide 3'), or open the matching guide popup. One honest sentence beats a manual procedure. For how-to questions that HAVE a dedicated guide (watchlist, getting started), open that guide and give a one-line answer - never paste the full step list. Never emit a set_view with a placeholder/empty symbol.",
        "PRICING / TIERS (ground in the knowledge base, stay brief - never recite the full tier wall): one or two sentences. Free Explorer exists (Dow 30, top-5 results, start date locked to today); paid unlocks more. If asked which tier for a capability, state the specific gate from the KB: custom start dates begin at Navigator for Dow/NASDAQ/S&P; Analyst adds all U.S. stocks + ETFs and ML scoring; Strategist adds all 15 markets. Point to tradewave.ai/pricing. Do not invent numbers or features not in the knowledge base. For a vague 'is it free?' give only: yes, there is a free Explorer tier (Dow 30, top-5 results, start date locked); paid unlocks more - point to tradewave.ai/pricing. Do NOT volunteer per-tier dollar amounts or portfolio/track limits unless the user names a tier or capability.",
        "BLANK / ERROR / OUT-OF-SCOPE: If the message is empty or you hit a tool/rate-limit error, never dead-end - reply with one warm line offering a concrete starting move ('Want today's AI pick, a market scan, or a symbol loaded?'). Stay confident; do not expose 'system overloaded' as the whole answer. A pure VIEW COMMAND (load <symbol>, change years to N, switch to PE+X, pull up <sym> over N years on the midterm cycle) needs NO data tool - fire update_view with the requested fields and confirm in one line, even if a read tool just errored; never answer a load/knob command with an 'overloaded' message. On a should-I-trade / 'does it make money' / 'is it a good trade' ask: keep it to 2 sentences max (one stat line + the verdict), fire set_view to put the pick on screen, append the disclaimer - do NOT write history/forward/ML as separate paragraphs or a 'Bottom line'.",
        "FORMAT: Your output is rendered as HTML. Use <br> for line breaks. Use <b> for bold. When listing items, put each on its own line with <br> between them, INCLUDING a <br> after the LAST item; then put any closing sentence or question (e.g. 'Want me to pull one up?') on its own line after a <br><br> - never let it run onto the last list item. Never output a wall of text with no line breaks. NEVER use the em-dash character (—) anywhere in a reply - write ' - ' (spaced hyphen) instead; date ranges may use the en-dash.",
        "INFO POPUPS: When a user asks about a concept that has a guide panel, give a 1-2 sentence answer and auto-open the guide. End with: I just opened the [Name] guide for you. <a href=\"#\" data-action=\"ACTION\" style=\"font-size:0.85em\">[reopen guide]</a><span data-action=\"ACTION\" style=\"display:none\"></span> "
        "The hidden span triggers the popup. Do NOT output the span as visible text. The [reopen guide] link must always be visible. "
        "Available guides and their triggers: "
        "1) Sharpe Ratio (SR, what is sharpe, risk-adjusted) -> action: open-sharpe-popup "
        "2) Trend Score (TL, trend long, trend short, how trend is calculated) -> action: open-trend-popup "
        "3) Seasonal Patterns (seasonality, what is a seasonal pattern, how seasonal trading works) -> action: open-seasonal-popup "
        "4) Trend Chart (trend chart, seasonal trend line, how the trend chart works) -> action: open-trendchart-popup "
        "5) Bar Chart (bar chart, year-by-year, what do the bars mean, green bars red bars) -> action: open-barchart-popup "
        "6) Projection (projection, dashed golden line, purple dashed line, purple projection, Proj N-Y, full-history projection, where will price go, seasonal projection) -> action: open-projection-popup "
        "7) PE Cycle (presidential election cycle, PE cycle, midterm, election year, PE+1 PE+2 PE+3) -> action: open-pecycle-popup "
        "8) MFE/MAE (MFE, MAE, maximum favorable excursion, maximum adverse excursion, drawdown, best point) -> action: open-mfemae-popup "
        "9) TWR (TradeWave Ratio, TWR, what is TWR) -> action: open-twr-popup "
        "10) Watchlist (watchlist, how to create a watchlist, track stocks) -> action: open-watchlist-popup "
        "11) Opportunity Table (opportunity table, opp table, what is the table, how to read the table) -> action: open-opptable-popup "
        "12) Getting Started (getting started, new here, teach me, how do I use this, walk me through, tour) -> action: open-gettingstarted-popup "
        "13) Patterns Days and Dates (days, pattern length, how many days, start date, date selection, what defines a pattern) -> action: open-daysout-popup "
        "14) Years/Data Depth (years setting, how many years, data depth, lookback, how far back) -> action: open-years-popup "
        "15) Filtering (how to filter, filter syntax, filter the table, text filter, advanced filtering) -> action: open-filtering-popup "
        "16) Help & Guides Home (help, need help, more help, what else can you do, show me more, other features) -> action: open-help-popup "
        "17) AI Scores (AI score, AI columns, AIS, win probability, predicted return, PredR, PMFE, predicted MFE, AI calibrated, machine learning scores, what are the AI columns, how does AI scoring work) -> action: open-aiscores-popup "
        "For guide #16 (Help & Guides Home), mention that the user can also click the ? icon in the top right of the Wave Viewer at any time to open the full list of guides. "
        "Only open ONE guide per response. Pick the most relevant one. If the question spans multiple topics, pick the primary one. For vague or general help requests that do not match a specific guide, use #16 (Help & Guides Home).",
        "DISCLAIMER RULE: Any time the user asks whether to trade a pattern, whether it is a good trade, whether they should buy or sell, or requests a trading recommendation, Tara must include this disclaimer at the end of the response: <i>Past performance does not guarantee future results. Always manage your risk.</i> Do not add the disclaimer for general questions about the UI or definitions. A pure analytical / strength / ranking question - how strong, how good, how reliable, how did it do, what is the win rate, why does it rank - is NOT a should-I-trade question: answer it WITHOUT the disclaimer. The disclaimer applies ONLY when the user asks whether to take, buy, or sell the trade, or for a recommendation.",
        "HISTORICAL FRAMING - NEVER IMPLY A FORWARD WIN (OVERRIDES ALL OTHER RULES; applies to every reply - single-pick, list, comparison, skeptic/forward questions): TradeWave reports the HISTORICAL RECORD and ML-CALIBRATED ODDS only, never a prediction of this year's result. ALLOWED, assert confidently with no hedging: past-tense historical facts ('won 9 of the last 10 years', 'won 10/10 years', '100% win rate over the last decade', 'avg +11.7%', 'Sharpe 1.1'), historical-tendency statements ('tends to rise this time of year', 'historically strongest in spring'), and calibrated-odds language ('a 90% historical win rate', 'the AI calibrates that to ~65% given current conditions', 'today's highest-confidence setup'). FORBIDDEN in any reply - never use these or any paraphrase, even after a disclaimer and even when the user demands one: a forward outcome about this year ('will win', 'will rise', 'will be green', 'is going to win/pop', 'this is a winner', 'a lock', 'a sure thing', 'guaranteed', 'can't-miss', 'risk-free'), confirming a forward premise ('the record says yes, this should be profitable', 'you should expect it to win', 'this pattern actually performs/works this year', 'this time it pays off'), or any present/future-tense claim that a specific pick WILL be profitable. When the user asks a forward question ('will X win this year?', 'which should I expect to win?', 'is it guaranteed?'), DO NOT confirm or deny the outcome - re-anchor in one line: state the historical stat, say plainly it is the HISTORICAL record and this year could be the losing year, and (if a should-I-trade ask) append the past-performance disclaimer. TEST before sending: if a sentence implies what a specific pick WILL do this year, rewrite it as what it HAS DONE historically or what the ODDS are. The disclaimer never licenses a forward-outcome sentence in the body.",
        "STATS ARE PER-SETUP, NEVER CARRIED OVER: a symbol's win rate and average belong to the EXACT setup loaded (its entry date + holding days). When you load or switch to a DIFFERENT setup of a symbol you already discussed (e.g. its September window vs its June window), the record is DIFFERENT - read the win rate and average from THIS turn's tool result for THAT setup, and NEVER reuse a win rate or average from an earlier setup or from earlier in the conversation. A 100% win rate on one window does NOT carry to another window. If you just loaded a setup, the win/loss count you state MUST match that setup's tool result.",
        "IMPORTANT: You are provided with the full year-by-year data for the loaded pattern (yearly_results). When the user asks about a specific year, look it up in that data and answer directly. Never say you cannot see the charts or cannot access the UI. Just interpret the data you have been given.",
        "IMPORTANT: When the user asks a general knowledge question (about a concept, a pattern like the 100-Year Pattern, a definition, or anything described in the knowledge base), answer it directly from the knowledge base. Do NOT tell the user to load a pattern or click an opportunity. Knowledge questions must be answered even when no pattern is loaded.",
        "",
        "<b>TradeWave UI Layout:</b>",
        "- Top panel: Gain-Loss Bar Chart. Each bar shows the UNDERLYING PRICE return for one historical year: green/up means the price rose and red/down means it fell. For a LONG, green/up is profitable; for a SHORT, red/down is profitable and green/up is a loss. Color is price direction, not universal trade P/L. Clicking a bar switches the bottom right to the Price Chart for that specific historical year.",
        "- Left panel: Opportunity Table. Ranked list of seasonal opportunities filtered by the user's settings (market, date, years, direction). User clicks a row to load it into the viewer.",
        "- Bottom right (3 slides):",
        "  Slide 1: Trend Chart. Current price line chart with the seasonal window highlighted. Below it shows summary stats: SR, Avg Gain, % Profitable, Cumulative Return, Buy-and-Hold.",
        "  Slide 2: Wave Stats. Six panels: Wave Detail (symbol, direction, date range, days), Wave Stats (avg gain two numbers: winners-only and overall, avg loss, median, std dev), Wave Profit Loss (num winners, num losers, cumulative return, S&P 500 full-year comparison), Wave Info (% profitable, SR, trend long, trend short), Cumulative Return Chart (2-line chart vs S&P 500), General (sample size and type, last price).",
        "  Slide 3: Price Chart. Shows current price chart by default. When user clicks a year bar in the Gain-Loss Bar Chart, automatically switches to the historical price chart for that year with entry/exit arrows and a shaded trade window.",
        "",
        "<b>Securities Groups (markets) - map a sector or group name to its market id when scanning:</b>",
        "- Technology / tech stocks -> NASDAQ 100 (market 1). Blue chips / mega caps -> DOW 30 (market 0). Broad large-cap US -> S&P 500 (market 2). Broader US (small + mid cap) -> Russell 1000 (market 3) or Wilshire 5000 (market 4).",
        "- ETFs -> market 11. Indices -> market 5 (common) or 6 (all). Futures / commodities (oil, gold, natural gas, grains) -> market 7. Forex / currencies -> market 8 (all) or 9 (liquid). Government bonds -> market 10. Crypto -> market 16. UK / London -> market 12. Canada / Toronto -> market 13.",
        "Sectors inside a broad index (energy, financials, healthcare, etc.): scan the closest stock market (usually S&P 500 = market 2, or NASDAQ 100 = market 1 for tech/growth) and name the matching tickers from the results.",
        "Scope note: a user's plan may only include some markets - if a scan returns an upgrade nudge for an out-of-scope market, say so briefly and offer what IS in scope; never invent results.",
    ]

    # Detect if the loaded pattern is the named "100-Year Pattern"
    def is_100_year_pattern(wv):
        sym      = (wv.get('symbol') or '').upper()
        sd       = wv.get('start_date', '')   # e.g. "2022-09-27"
        days     = wv.get('days_out', '')
        pe       = wv.get('pe_cycle', 'cons')
        spx_syms = {'SPX', '$SPX', 'SP500', 'SPY'}
        if sym not in spx_syms: return False
        if pe != 'pe2': return False
        try:
            month = int(sd.split('-')[1])
            day   = int(sd.split('-')[2])
            if not (month == 9 and 24 <= day <= 30): return False
        except: return False
        try:
            d = int(str(days))
            if not (290 <= d <= 310): return False
        except: return False
        return True

    # Wave viewer context
    symbol = wave_viewer.get("symbol", "")
    if symbol:
        parts.append("\n<b>Currently Loaded Pattern (Wave Viewer):</b>")
        if is_100_year_pattern(wave_viewer):
            parts.append("*** NAMED PATTERN ALERT: This is 'The 100-Year Pattern' - a famous seasonal pattern on SPX discovered by the TradeWave founder and published in the book 'The 100-Year Pattern' (Amazon: https://www.amazon.com/dp/B0FCX61K4Y). When discussing this pattern, always refer to it by name. ***")
        if wave_viewer.get("company"):
            parts.append(f"Company: {wave_viewer['company']} ({symbol})")
        else:
            parts.append(f"Symbol: {symbol}")
        start_date = wave_viewer.get('start_date', '')
        days_out   = wave_viewer.get('days_out', '')
        parts.append(f"Start Date: {start_date or 'N/A'}")
        if start_date and days_out:
            end_date = calculate_end_date(start_date, days_out)
            # Build a year-agnostic description so the LLM doesn't use future-year dates when discussing history
            try:
                sd_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                ed_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                sd_md  = sd_obj.strftime('%b %-d')   # e.g. "Feb 21"
                ed_md  = ed_obj.strftime('%b %-d')   # e.g. "Feb 14"
                end_desc = f"{ed_md} of the following year" if ed_obj.year > sd_obj.year else ed_md
            except Exception:
                sd_md    = start_date[5:]
                ed_md    = end_date[5:]
                end_desc = ed_md
            parts.append(f"End Date:   {end_date}")
            parts.append(f"Pattern Date Range (year-agnostic): {sd_md} to {end_desc} ({days_out} calendar days). "
                         f"This pattern recurs on these same month-day dates each year.")
            parts.append(f"DAY-COUNT GROUND TRUTH: TradeWave windows are measured in CALENDAR days, the entry date is day 1, and this window is EXACTLY {days_out} calendar days. Use that supplied count verbatim; do not subtract the dates and do not call it a different number of days.")
            parts.append(f"Next/current occurrence: {start_date} to {end_date}.")
            parts.append(f"CRITICAL: When discussing ANY historical year (e.g. 2020, 2019, etc.), "
                         f"always express the date range as '{sd_md} to {end_desc}', never as '{start_date} to {end_date}'. "
                         f"Only use the full calendar dates ({start_date} to {end_date}) when explicitly discussing the next/upcoming occurrence.")
            if _is_short(wave_viewer.get('direction')):
                parts.append("Trade: enter the short at the closing price on the pattern start date each year, then cover at the closing price on the pattern end date.")
            else:
                parts.append("Trade: buy at the closing price on the pattern start date each year, then sell at the closing price on the pattern end date.")
        else:
            parts.append(f"Duration: {days_out or 'N/A'} calendar days")
        years     = wave_viewer.get('years', 'N/A')
        pe_cycle  = wave_viewer.get('pe_cycle', 'cons')
        pe_labels = {
            'pe0': ('PE',   'election years (every 4 years)'),
            'pe1': ('PE+1', 'post-election years (every 4 years)'),
            'pe2': ('PE+2', 'midterm election years (every 4 years)'),
            'pe3': ('PE+3', 'pre-election years (every 4 years)'),
        }
        if pe_cycle in pe_labels:
            short, desc = pe_labels[pe_cycle]
            approx_calendar_years = int(years) * 4 if str(years).isdigit() else '?'
            parts.append(f"Historical Years: {years} {short} years - only {desc}. "
                         f"This covers approximately {approx_calendar_years} calendar years of history. "
                         f"When discussing this pattern, always mention it uses {short} cycle years, NOT consecutive years.")
        else:
            parts.append(f"Historical Years: {years} consecutive years")
        direction = 'short' if _is_short(wave_viewer.get("direction", "long")) else 'long'
        parts.append(f"Direction: {'Long (Bullish)' if direction == 'long' else 'Short (Bearish)'}")
        if _is_short(direction):
            parts.append("SHORT GROUND TRUTH: The aggregate statistics below are already direction-adjusted. A year when the underlying price FELL is a profitable short year. The visible bar chart still colors raw price movement, so RED/DOWN bars are profitable short years and GREEN/UP bars are losing short years. Never say a bearish setup won because most bars were green; for this short, historical wins correspond to price-down/red bars.")
        else:
            parts.append("LONG GROUND TRUTH: The aggregate statistics below are direction-adjusted. A GREEN/UP bar is a profitable long year and a RED/DOWN bar is a losing long year.")
        stats = wave_viewer.get("stats", {})
        if stats:
            parts.append("Statistics:")
            for k, v in stats.items():
                parts.append(f"  {k}: {v}")
        mae_enabled = wave_viewer.get("mae_enabled", False)
        yearly = wave_viewer.get("yearly_results", [])
        if yearly:
            today      = datetime.datetime.now().date()
            current_year = today.year
            trade_status = _loaded_trade_status(wave_viewer, today)

            completed_rows = _completed_year_rows(wave_viewer, today)
            green_count = sum(_raw_year_return(row) >= 0 for row in completed_rows)
            red_count = sum(_raw_year_return(row) < 0 for row in completed_rows)
            winners, losers = _historical_record(wave_viewer)
            parts.append(
                f"AUTHORITATIVE COMPLETED RECORD: {winners} profitable and {losers} losing years; "
                f"the raw-price bar chart has {green_count} green/up and {red_count} red/down completed bars. "
                "Never state a different majority, and always state the completed sample size with a record or win rate."
            )

            if mae_enabled:
                parts.append("Year-by-year results (raw price return/color first, then the DIRECTION-ADJUSTED trade return/result and trade MFE/MAE):")
            else:
                parts.append("Year-by-year results (raw price return/color first, then the DIRECTION-ADJUSTED trade return/result and trade MFE). "
                             "NOTE: MAE (max adverse excursion) is NOT enabled - the MAE checkbox is unchecked. "
                             "Do NOT mention or discuss MAE values. If the user asks about MAE or drawdown, tell them MAE is not currently enabled and suggest they check the MAE checkbox in the bar chart controls to enable it.")
            for y in yearly:
                try:
                    yr = int(y.get("year", 0))
                except (TypeError, ValueError):
                    continue
                raw_ret = _raw_year_return(y)
                if raw_ret is None:
                    continue
                trade_ret = _trade_year_return(raw_ret, direction)
                color = "GREEN/UP" if raw_ret >= 0 else "RED/DOWN"
                result = "PROFIT" if _is_trade_win(raw_ret, direction) else ("BREAKEVEN" if trade_ret == 0 else "LOSS")
                trade_mfe, trade_mae = _trade_excursions(y, direction)
                if yr >= current_year:
                    if trade_status == 'upcoming':
                        parts.append(f"  {yr}: [UPCOMING - pattern has not started yet. Exclude from all statistics.]")
                    elif trade_status == 'active':
                        direction_label = "currently gaining" if trade_ret >= 0 else "currently losing"
                        parts.append(f"  {yr}: raw price {raw_ret:+.2f}% ({color}); {direction} trade {trade_ret:+.2f}% [ACTIVE - pattern in progress right now, {direction_label}. This return updates daily and is not yet final. Exclude from historical statistics but you can mention it as the live running return.]")
                    else:
                        if mae_enabled:
                            parts.append(f"  {yr}: raw price {raw_ret:+.2f}% ({color}); {direction} trade {trade_ret:+.2f}% [{result}]  trade MFE: {trade_mfe:+.2f}%  trade MAE: {trade_mae:+.2f}%")
                        else:
                            parts.append(f"  {yr}: raw price {raw_ret:+.2f}% ({color}); {direction} trade {trade_ret:+.2f}% [{result}]  trade MFE: {trade_mfe:+.2f}%")
                else:
                    if mae_enabled:
                        parts.append(f"  {yr}: raw price {raw_ret:+.2f}% ({color}); {direction} trade {trade_ret:+.2f}% [{result}]  trade MFE: {trade_mfe:+.2f}%  trade MAE: {trade_mae:+.2f}%")
                    else:
                        parts.append(f"  {yr}: raw price {raw_ret:+.2f}% ({color}); {direction} trade {trade_ret:+.2f}% [{result}]  trade MFE: {trade_mfe:+.2f}%")
        parts.append(
            "VISIBLE LOWER VIEW GROUND TRUTH: " +
            _visible_lower_view_overview(wave_viewer).replace('<b>', '').replace('</b>', '')
        )
    else:
        parts.append("\n<b>Wave Viewer:</b> No pattern currently loaded.")

    # Opportunity table context
    if opportunities:
        visible_count = opp_table_length if opp_table_length is not None else len(opportunities)
        # Name the market/group the table is currently on so Tara can tell whether it already
        # matches a "which <group> stocks" question and answer FROM these exact on-screen rows.
        if opp_table_market_name:
            mkt_id = f" (market {opp_table_market})" if opp_table_market not in (None, "") else ""
            parts.append(f"\n<b>Opportunity Table</b> - currently showing <b>{opp_table_market_name}</b>{mkt_id} "
                         f"({visible_count} rows shown, sorted by Sharpe Ratio, best first). These ARE the rows the "
                         f"user is looking at right now. For a 'which {opp_table_market_name} / matching-group stocks' "
                         f"question, answer by naming the TOP rows from this list - it is the on-screen truth.")
        else:
            parts.append(f"\n<b>Opportunity Table</b> ({visible_count} rows shown, sorted by Sharpe Ratio):")
        parts.append("Date | Symbol | Days | Direction | Avg Profit | Sharpe Ratio")
        for o in opportunities[:30]:  # send at most 30 rows to the LLM
            direction = "Long" if str(o.get("direction", "")).upper() in ("L", "LONG") else "Short"
            parts.append(
                f"{o.get('date','?')} | {o.get('symbol','?')} | {o.get('days_out','?')} days | "
                f"{direction} | {o.get('avg_profit','?')}% | SR {o.get('sharpe_ratio','?')}"
            )
        # Deterministic rank of the loaded pattern, so Tara never MISCOUNTS its table position
        # when asked "why/where does this rank" (LLMs count list positions unreliably - she said
        # #5 for a row that is #4). The passed order IS the on-screen Sharpe order, so the 1-based
        # index is the visible rank. Hand her the exact number; tell her to use it, not recount.
        loaded_sym = str(wave_viewer.get("symbol", "")).upper()
        if loaded_sym:
            for i, o in enumerate(opportunities):
                if str(o.get("symbol", "")).upper() == loaded_sym:
                    parts.append(
                        f"LOADED-PATTERN RANK: {loaded_sym} is #{i + 1} in this table (by Sharpe, best "
                        f"first). If asked where or why it ranks, use #{i + 1} EXACTLY - do not recount the rows."
                    )
                    break
    else:
        parts.append("\n<b>Opportunity Table:</b> Empty or not loaded.")

    if _KNOWLEDGE:
        parts.append(f"\n{_KNOWLEDGE}")

    return "\n".join(parts)


# --- deterministic floor for the loaded-pattern STRENGTH question ----------------------------------
# Haiku (temp 0) occasionally punts an analytical "how strong is this window" with a bare
# "Pattern loaded on the chart." and NO stat. When that happens on a loaded pattern whose stats we
# already have, append the strength line straight from those loaded stats - NOT fabricated (the same
# numbers the prompt already had), confident historical framing, no disclaimer.
_STRENGTH_Q = re.compile(r'\bhow\s+(?:strong|good|reliable|solid)\b|\bstrength\b|\bhow\s+did\s+(?:it|this)\b|\bis\s+(?:it|this)\s+(?:strong|good|reliable)\b', re.I)
_REPLY_HAS_STAT = re.compile(r'\d{1,3}\s*%|\bwon\s+\d+|\d+\s+of\s+\d+|sharpe[^\d]{0,12}\d', re.I)
_SHORT_COLOR_CONTRADICTION = re.compile(
    r"\bmost\s+(?:of\s+the\s+)?bars?\s+(?:are|were|look)\s+green\b|"
    r"\bgreen(?:/up)?\s+bars?\s+(?:are|were|mean|show|represent)\s+(?:the\s+)?(?:profitable|winning|winners?|profits?)\b|"
    r"\bred(?:/down)?\s+bars?\s+(?:are|were|mean|show|represent)\s+(?:the\s+)?(?:losing|loss|losses)\b|"
    r"\bunusual\s+for\s+(?:a\s+)?short\s+pattern\b",
    re.I,
)
_DAY_CLAIM = re.compile(r'\b(\d+)\s*(?:-|\s)\s*day\b', re.I)


def _ensure_strength_answered(user_message, wave_viewer, reply):
    try:
        if not _STRENGTH_Q.search(user_message or ""):
            return reply
        wv = wave_viewer or {}
        sym = (wv.get("symbol") or "").strip()
        stats = wv.get("stats") or {}
        if not sym or not stats:
            return reply
        if _REPLY_HAS_STAT.search(reply or ""):
            return reply                      # she already stated a real stat - leave it
        pct = str(stats.get("Percent Profitable") or "").strip()
        sr = str(stats.get("Sharpe Ratio") or "").strip()
        avg = str(stats.get("Avg Profit - All") or stats.get("Avg Profit") or "").strip()
        wins, losses = _historical_record(wv)
        tot = wins + losses
        bits = []
        if pct:
            bits.append(pct + " profitable" + ((" (won %d of %d years)" % (wins, tot)) if tot else ""))
        elif tot:
            bits.append("won %d of %d years" % (wins, tot))
        if avg:
            bits.append("avg " + avg)
        if sr:
            bits.append("Sharpe " + sr)
        if not bits:
            return reply
        line = "Historically, %s's loaded window has been %s." % (sym, ", ".join(bits))
        sep = "<br>" if (reply or "").strip() else ""
        return (reply or "").rstrip() + sep + line
    except Exception:
        return reply


def _guard_loaded_pattern_reply(user_message, wave_viewer, reply):
    """Replace known sign/day-count contradictions with loaded, deterministic facts."""
    try:
        wv = wave_viewer or {}
        if not wv.get('symbol'):
            return reply

        overview = _loaded_pattern_overview(user_message, wv)
        if overview:
            return overview

        reply_text = reply or ''
        if _is_short(wv.get('direction')) and _SHORT_COLOR_CONTRADICTION.search(reply_text):
            return _loaded_pattern_overview("what am I looking at?", wv) or reply

        exact_days = _as_int(wv.get('days_out'))
        describes_window = re.search(r'\b(?:seasonal|pattern|window|setup)\b', reply_text, re.I)
        if exact_days is not None and describes_window:
            stated_days = [_as_int(match.group(1)) for match in _DAY_CLAIM.finditer(reply_text)]
            if any(value is not None and value != exact_days for value in stated_days):
                return _loaded_pattern_overview("what am I looking at?", wv) or reply
        return reply
    except Exception:
        return reply


#-------------------------------------------------------------------------------------------------------------------
@chatbot_bp.route("/chat", methods=["POST"])
@check_for_token
def chat():
    """
    Endpoint to process chat messages with wave-viewer and opportunity-table context.

    SEC-C2 - this route is now protected by check_for_token (aud/iss/HS256
    enforced). The previous bare-except fail-open path that let unauthenticated
    callers burn Anthropic credits with user_id='unknown' is gone; the
    decorator returns 401/403 before this body runs if the token is missing
    or invalid, and the decoded user_id is read from flask.g.
    """
    incoming_data = request.json or {}
    user_message  = incoming_data.get("message", "")
    history       = incoming_data.get("history", [])   # list of {role, content}
    wave_viewer   = incoming_data.get("wave_viewer", {})
    opportunities = incoming_data.get("opportunities", [])
    opp_table_length = incoming_data.get("opp_table_length")
    # The market/group the opportunity table is currently showing - lets Tara answer a
    # "which <group> stocks" question FROM the on-screen rows (exact match) when the table is
    # already on that group, instead of an independent scan that diverges from the table.
    opp_table_market = incoming_data.get("opp_table_market")
    opp_table_market_name = incoming_data.get("opp_table_market_name")
    opp_table_years = incoming_data.get("opp_table_years")   # table lookback, for a cross-market OppList4 screen
    user_token = incoming_data.get("token")                  # user's LTK - reused for the loopback OppList4 fetch

    # Blank-message guard: an empty message must never dead-end on the generic 500
    # envelope; return a warm, concrete nudge instead. (Tara-peak loop, 2026-06-21)
    if not (user_message or "").strip():
        return jsonify({"reply": "Hi, I'm Tara. Want today's AI pick, a quick market scan, or a specific symbol loaded?", "actions": []})

    # SEC-C2 - user_id is the authenticated id from the verified JWT.
    from flask import g
    user_id = getattr(g, 'chatbot_user_id', 'unknown')

    try:
        # A generic explanation of an already-loaded setup is fully determined
        # by the supplied viewer data. Answer it here so an LLM cannot re-count
        # inclusive dates or invert short-year signs/colors.
        deterministic_overview = _loaded_pattern_overview(user_message, wave_viewer)
        if deterministic_overview:
            log_question(user_id, user_message, deterministic_overview, wave_viewer)
            return jsonify({"reply": deterministic_overview, "actions": []})

        system_prompt = build_system_prompt(wave_viewer, opportunities, opp_table_length,
                                            opp_table_market, opp_table_market_name)
        if TARA_TOOLS_ENABLED:
            system_prompt = system_prompt + "\n\n" + TOOL_INSTRUCTION

        # Onboarding / teach-me is handled by the normal behavior rules + the
        # open-gettingstarted-popup guide (INFO POPUPS). The old hardcoded
        # "Click any row" teach-me wall was REMOVED 2026-06-21 (Tara-peak loop
        # round 1): it injected at the TOP of the prompt and overrode every
        # brevity / screen-control rule below it - the #1 failure cluster
        # (cold-onboarding pass rate 20%). Do NOT reintroduce a verbatim
        # click-the-table block.

        # Build messages list for Claude (no system role - system goes separately).
        # history already includes the current user message as the last item.
        messages = []
        for h in history[:-1]:   # skip last - it's the current user turn
            role = "assistant" if h.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        actions = []
        if TARA_TOOLS_ENABLED:
            # Tara fetches live data via the gateway tools and narrates the result; `actions`
            # carries any wave-viewer changes the model requested (Phase 2) for the client to apply.
            bot_reply, actions = run_chat_with_tools(messages, system_prompt, user_id, CHATBOT_MODEL, CACHE_TTL,
                                                     opp_table=opportunities, opp_table_market=opp_table_market,
                                                     user_token=user_token, opp_table_years=opp_table_years)
        else:
            bot_reply = send_claude_messages(messages, model=CHATBOT_MODEL, system=system_prompt, cache_system=True, cache_ttl=CACHE_TTL)

        # Deterministic floor: guarantee a stat on a loaded-pattern strength question
        # (Haiku at temp 0 occasionally punts with a bare "loaded" and no number).
        bot_reply = _ensure_strength_answered(user_message, wave_viewer, bot_reply)
        bot_reply = _guard_loaded_pattern_reply(user_message, wave_viewer, bot_reply)

        log_question(user_id, user_message, bot_reply, wave_viewer)

        return jsonify({"reply": bot_reply, "actions": actions})

    except Exception as e:
        logging.exception("chatbot.chat failed for user_id=%s", user_id)  # detail server-side only
        return jsonify({"reply": "Sorry, something went wrong on my end. Please try again.",
                        "actions": []})  # generic message; consistent envelope on every path
