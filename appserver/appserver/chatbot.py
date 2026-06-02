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

# Prepended to the system prompt when the gateway tools are live, so the model fetches real
# data instead of inventing numbers. Constant => stays cacheable across turns.
TOOL_INSTRUCTION = (
    "You can call live TradeWave tools (find_best_opportunities, analyze_symbol, "
    "get_symbol_patterns, explain_pick) that query the real TradeWave engine. When the user "
    "asks about opportunities, a symbol's seasonality, the daily pick, or anything needing "
    "current numbers, CALL THE RIGHT TOOL and base your answer ONLY on its result - never "
    "invent setups, win rates, Sharpe ratios, or returns. The user is in the wave-viewer; "
    "prefer the symbol/market already loaded in your context when relevant. Keep answers "
    "concise and plain-English. All figures are percentages, never price levels."
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
    Calculate the end date based on the start_date and num_days.

    Args:
        start_date (str): The start date in the format 'YYYY-MM-DD'.
        num_days (str or int): Number of calendar days for the opportunity.

    Returns:
        str: The calculated end date in the format 'YYYY-MM-DD'.
    """
    num_days = int(num_days)  # Ensure num_days is an integer
    start_date_obj = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_date_obj = start_date_obj + timedelta(days=num_days)
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
def build_system_prompt(wave_viewer, opportunities, opp_table_length=None):
    """Build a system prompt that gives the LLM awareness of the wave viewer and opp table."""
    parts = [
        "You are Tara, the AI assistant for TradeWave, a seasonal trading pattern analysis platform by Tara Data Research.",
        "You help traders understand seasonal trading patterns, analyse opportunities, and interpret statistics.",
        "RESPONSE STYLE: Be very short. 1-3 sentences for simple questions. 3-5 bullet points max for complex ones. No long explanations. No 'Is that what you were asking?' endings. No rephrasing the question back. No filler phrases like 'Great question' or 'Of course'. Just the answer.",
        "FORMAT: Your output is rendered as HTML. Use <br> for line breaks. Use <b> for bold. When listing items, put each on its own line with <br> between them. Never output a wall of text with no line breaks.",
        "INFO POPUPS: When a user asks about a concept that has a guide panel, give a 1-2 sentence answer and auto-open the guide. End with: I just opened the [Name] guide for you. <a href=\"#\" data-action=\"ACTION\" style=\"font-size:0.85em\">[reopen guide]</a><span data-action=\"ACTION\" style=\"display:none\"></span> "
        "The hidden span triggers the popup. Do NOT output the span as visible text. The [reopen guide] link must always be visible. "
        "Available guides and their triggers: "
        "1) Sharpe Ratio (SR, what is sharpe, risk-adjusted) -> action: open-sharpe-popup "
        "2) Trend Score (TL, trend long, trend short, how trend is calculated) -> action: open-trend-popup "
        "3) Seasonal Patterns (seasonality, what is a seasonal pattern, how seasonal trading works) -> action: open-seasonal-popup "
        "4) Trend Chart (trend chart, seasonal trend line, how the trend chart works) -> action: open-trendchart-popup "
        "5) Bar Chart (bar chart, year-by-year, what do the bars mean, green bars red bars) -> action: open-barchart-popup "
        "6) Projection (projection, dashed golden line, where will price go, seasonal projection) -> action: open-projection-popup "
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
        "DISCLAIMER RULE: Any time the user asks whether to trade a pattern, whether it is a good trade, whether they should buy or sell, or requests a trading recommendation, Tara must include this disclaimer at the end of the response: <i>Past performance does not guarantee future results. Always manage your risk.</i> Do not add the disclaimer for general questions about the UI or definitions.",
        "IMPORTANT: You are provided with the full year-by-year data for the loaded pattern (yearly_results). When the user asks about a specific year, look it up in that data and answer directly. Never say you cannot see the charts or cannot access the UI. Just interpret the data you have been given.",
        "IMPORTANT: When the user asks a general knowledge question (about a concept, a pattern like the 100-Year Pattern, a definition, or anything described in the knowledge base), answer it directly from the knowledge base. Do NOT tell the user to load a pattern or click an opportunity. Knowledge questions must be answered even when no pattern is loaded.",
        "",
        "<b>TradeWave UI Layout:</b>",
        "- Top panel: Gain-Loss Bar Chart. Shows each historical year as a bar (green=profit, red=loss) for the currently loaded pattern. Gives a quick visual of year-by-year consistency. Clicking a bar switches the bottom right to the Price Chart for that specific historical year.",
        "- Left panel: Opportunity Table. Ranked list of seasonal opportunities filtered by the user's settings (market, date, years, direction). User clicks a row to load it into the viewer.",
        "- Bottom right (3 slides):",
        "  Slide 1: Trend Chart. Current price line chart with the seasonal window highlighted. Below it shows summary stats: SR, Avg Gain, % Profitable, Cumulative Return, Buy-and-Hold.",
        "  Slide 2: Wave Stats. Six panels: Wave Detail (symbol, direction, date range, days), Wave Stats (avg gain two numbers: winners-only and overall, avg loss, median, std dev), Wave Profit Loss (num winners, num losers, cumulative return, S&P 500 full-year comparison), Wave Info (% profitable, SR, trend long, trend short), Cumulative Return Chart (2-line chart vs S&P 500), General (sample size and type, last price).",
        "  Slide 3: Price Chart. Shows current price chart by default. When user clicks a year bar in the Gain-Loss Bar Chart, automatically switches to the historical price chart for that year with entry/exit arrows and a shaded trade window.",
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
            parts.append(f"Next/current occurrence: {start_date} to {end_date}.")
            parts.append(f"CRITICAL: When discussing ANY historical year (e.g. 2020, 2019, etc.), "
                         f"always express the date range as '{sd_md} to {end_desc}', never as '{start_date} to {end_date}'. "
                         f"Only use the full calendar dates ({start_date} to {end_date}) when explicitly discussing the next/upcoming occurrence.")
            parts.append(f"Trade: buy at closing price on the pattern start date each year, sell at closing price on the pattern end date.")
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
        direction = wave_viewer.get("direction", "long")
        parts.append(f"Direction: {'Long (Bullish)' if direction == 'long' else 'Short (Bearish)'}")
        stats = wave_viewer.get("stats", {})
        if stats:
            parts.append("Statistics:")
            for k, v in stats.items():
                parts.append(f"  {k}: {v}")
        mae_enabled = wave_viewer.get("mae_enabled", False)
        yearly = wave_viewer.get("yearly_results", [])
        if yearly:
            today      = datetime.datetime.now().date()
            today_str  = today.strftime('%Y-%m-%d')
            current_year = today.year
            # Determine current-year trade status using the loaded pattern's dates
            trade_status = 'upcoming'   # default
            if start_date and days_out:
                try:
                    trade_start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    # If start falls on Saturday (5) or Sunday (6), shift to next Monday
                    if trade_start.weekday() == 5:    # Saturday
                        trade_start += timedelta(days=2)
                    elif trade_start.weekday() == 6:  # Sunday
                        trade_start += timedelta(days=1)
                    trade_end   = datetime.datetime.strptime(end_date,   '%Y-%m-%d').date()
                    if today < trade_start:
                        trade_status = 'upcoming'
                    elif trade_start <= today <= trade_end:
                        trade_status = 'active'
                    else:
                        trade_status = 'completed'
                except Exception:
                    pass

            if mae_enabled:
                parts.append("Year-by-year results (return_pct = trade return, mfe_pct = max gain above entry close, mae_pct = max loss below entry close):")
            else:
                parts.append("Year-by-year results (return_pct = trade return, mfe_pct = max gain above entry close). "
                             "NOTE: MAE (max adverse excursion) is NOT enabled - the MAE checkbox is unchecked. "
                             "Do NOT mention or discuss MAE values. If the user asks about MAE or drawdown, tell them MAE is not currently enabled and suggest they check the MAE checkbox in the bar chart controls to enable it.")
            for y in yearly:
                yr = int(y.get("year", 0))
                if yr >= current_year:
                    if trade_status == 'upcoming':
                        parts.append(f"  {yr}: [UPCOMING - pattern has not started yet. Exclude from all statistics.]")
                    elif trade_status == 'active':
                        ret = y.get("return_pct", 0)
                        direction_label = "currently gaining" if ret >= 0 else "currently losing"
                        parts.append(f"  {yr}: {ret:+.2f}%  [ACTIVE - pattern in progress right now, {direction_label}. This return updates daily and is not yet final. Exclude from historical statistics but you can mention it as the live running return.]")
                    else:
                        result = "PROFIT" if y.get("return_pct", 0) >= 0 else "LOSS"
                        if mae_enabled:
                            parts.append(f"  {yr}: {y['return_pct']:+.2f}%  [{result}]  MFE: {y['mfe_pct']:+.2f}%  MAE: {y['mae_pct']:+.2f}%")
                        else:
                            parts.append(f"  {yr}: {y['return_pct']:+.2f}%  [{result}]  MFE: {y['mfe_pct']:+.2f}%")
                else:
                    result = "PROFIT" if y.get("return_pct", 0) >= 0 else "LOSS"
                    if mae_enabled:
                        parts.append(f"  {yr}: {y['return_pct']:+.2f}%  [{result}]  MFE: {y['mfe_pct']:+.2f}%  MAE: {y['mae_pct']:+.2f}%")
                    else:
                        parts.append(f"  {yr}: {y['return_pct']:+.2f}%  [{result}]  MFE: {y['mfe_pct']:+.2f}%")
    else:
        parts.append("\n<b>Wave Viewer:</b> No pattern currently loaded.")

    # Opportunity table context
    if opportunities:
        visible_count = opp_table_length if opp_table_length is not None else len(opportunities)
        parts.append(f"\n<b>Opportunity Table</b> ({visible_count} rows shown, sorted by Sharpe Ratio):")
        parts.append("Date | Symbol | Days | Direction | Avg Profit | Sharpe Ratio")
        for o in opportunities[:30]:  # send at most 30 rows to the LLM
            direction = "Long" if str(o.get("direction", "")).upper() in ("L", "LONG") else "Short"
            parts.append(
                f"{o.get('date','?')} | {o.get('symbol','?')} | {o.get('days_out','?')} days | "
                f"{direction} | {o.get('avg_profit','?')}% | SR {o.get('sharpe_ratio','?')}"
            )
    else:
        parts.append("\n<b>Opportunity Table:</b> Empty or not loaded.")

    if _KNOWLEDGE:
        parts.append(f"\n{_KNOWLEDGE}")

    return "\n".join(parts)


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

    # SEC-C2 - user_id is the authenticated id from the verified JWT.
    from flask import g
    user_id = getattr(g, 'chatbot_user_id', 'unknown')

    try:
        system_prompt = build_system_prompt(wave_viewer, opportunities, opp_table_length)
        if TARA_TOOLS_ENABLED:
            system_prompt = TOOL_INSTRUCTION + "\n\n" + system_prompt

        # Detect onboarding / teach-me intent and inject high-priority instruction
        msg_lower = user_message.lower()
        teach_me_triggers = ['teach me', 'how do i use', "i'm new", 'i am new', 'walk me through',
                             'help me learn', 'how does this work', 'what is this', 'i know nothing',
                             'show me how', 'getting started', 'where do i start', 'how to use']
        if any(t in msg_lower for t in teach_me_triggers):
            teach_me_instruction = (
                "HIGH PRIORITY: The user is asking to learn TradeWave. "
                "Do NOT tell them to click an opportunity. Instead, respond with EXACTLY this HTML (copy it verbatim):\n"
                'TradeWave finds stocks and other securities that repeat the same price move around the same dates every year. '
                'The best ones are already loaded in the opportunity table above.<br><br>'
                '<b>Try it now:</b><br>'
                '1) Click any row in the table.<br>'
                '2) A bar chart appears on the right: green bars = profitable years, red bars = losses.<br>'
                '3) More green bars = more consistent pattern.<br><br>'
                'Click a row and tell me when you are ready. I will walk you through what it all means.'
            )
            system_prompt = teach_me_instruction + "\n\n" + system_prompt

        # Build messages list for Claude (no system role - system goes separately).
        # history already includes the current user message as the last item.
        messages = []
        for h in history[:-1]:   # skip last - it's the current user turn
            role = "assistant" if h.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        if TARA_TOOLS_ENABLED:
            # Tara fetches live data via the gateway tools and narrates the result.
            bot_reply = run_chat_with_tools(messages, system_prompt, user_id, CHATBOT_MODEL, CACHE_TTL)
        else:
            bot_reply = send_claude_messages(messages, model=CHATBOT_MODEL, system=system_prompt, cache_system=True, cache_ttl=CACHE_TTL)

        log_question(user_id, user_message, bot_reply, wave_viewer)

        return jsonify({"reply": bot_reply})

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})




