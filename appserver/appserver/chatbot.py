from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import datetime
import re
import sys
import os
import json
import logging
import hashlib
import hmac
import threading
import time
import uuid
import math
from functools import wraps
import jwt
import redis
import config
from AI_tools_appserver import (
    send_claude_messages,
    CLAUDE_HAIKU_35,   # claude-3-5-haiku-20241022 - very cheap, fast
    CLAUDE_HAIKU_45,   # claude-haiku-4-5-20251001 - fast + cheap
    CLAUDE_SONNET_46,  # claude-sonnet-4-6 - strong + fast
    CLAUDE_OPUS_46,    # claude-opus-4-6 - most capable
)
from openai_tools_appserver import (
    GPT_56_LUNA,
    OpenAIAPIError,
    OpenAIConfigurationError,
    failure_category,
    send_openai_messages,
)
from tradewave_api_calls_cb import (
    get_keyprovider_token, login_appserver, get_financial_groups,
    get_opp_list, get_years_pyears_from_resource_id,
    create_opportunity_url
)
# Phase 1: Tara calls the v1 gateway as a client (one source of truth). Falls back to the
# plain no-tools chat when the gateway is not configured. See docs/TARA_GATEWAY_INTEGRATION.md.
from tara_gateway import (
    classify_investor_intent,
    classify_view_intent,
    guided_next_questions,
    investor_guidance_response,
    loaded_pattern_suitability_response,
    response_violates_investor_contract,
    response_violates_view_contract,
    unsupported_live_data_response,
    TARA_TOOLS_ENABLED,
    _validate_view_spec,
    run_chat_with_openai_tools,
    run_chat_with_tools,
)
from tara_answer_planner import (
    build_bottom_slide_command,
    build_excursion_overlay_command,
    build_deterministic_reply,
    build_hundred_year_pattern_command,
    build_current_table_pick_command,
    build_opportunity_row_load_command,
    build_tooltip_preference_command,
    canonical_pattern_facts,
    explicit_pattern_symbol,
    needs_pattern_ai_context,
    normalize_screen_context,
    requested_full_history_years,
    verified_context_lines,
)
from featured_patterns import is_hundred_year_view_spec
from tara_prompt_context import (
    allowlisted_prompt_stats,
    needs_opportunity_rows,
    needs_yearly_results,
    parse_knowledge_sections,
    prompt_segment_sizes,
    segmented_system_blocks,
    select_topic_knowledge,
)
from tara_model_router import select_tara_provider
from tara_runtime_policy import (
    FALLBACK_MODEL,
    FALLBACK_PROVIDER,
    PRIMARY_MODEL,
    PRIMARY_PROVIDER,
)
from tara_release_fingerprint import runtime_fingerprint


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
CACHE_TTL     = '5m'   # '1h' is supported; keep 5m as the active default for chat sessions
CHATBOT_MODEL = CLAUDE_HAIKU_45
OPENAI_CHATBOT_MODEL = GPT_56_LUNA

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
    "already on screen); answer at the depth requested, prioritizing the record + n, payoff, recency, "
    "outlier dependence, and the strongest counter-signal instead of mechanically listing every metric, and "
    "a bare 'Pattern loaded' / 'Loaded on the chart' with no stat is a HARD FAIL here too, even though no "
    "load action fired.\n"
    "2) When the user asks to LOAD / SHOW / OPEN / PULL UP a symbol or setup, CHANGE the years "
    "or PE cycle, SHOW/HIDE MFE or MAE, or SHOW the Trend Chart / Wave Stats / AI Scores / Price Chart, "
    "you MUST call update_view and do it yourself. "
    "For MFE/MAE use show_mfe/show_mae booleans; for the global guidance tooltips use "
    "show_tooltips. Do not open a guide for a direct view command. Do NOT tell them to use a dropdown, "
    "selectbox, or to click a row - you CAN drive the view for them. After update_view, say in one "
    "short line what you changed. For a lower-panel command use bottom_slide=trend_chart, "
    "wave_stats, ai_scores, or price_chart; confirm the panel in one line without reloading the symbol or "
    "adding unrelated statistics.\n"
    "3) For a date-range preset (a month/quarter/season), first call analyze_symbol with period= to "
    "get the resolved entry_date + days_out, then pass those to update_view.\n"
    "4) SCREENING / 'which <group> stocks ...' questions (e.g. 'which tech stocks tend to rise this time "
    "of year', 'best energy names now', 'top crypto setups'): MAP the group to its SINGLE market id "
    "(tech / technology = NASDAQ 100 = market 1; see the Securities Groups list above) and call "
    "find_best_opportunities with markets=<that one id> (just the id - no extra filters for a plain "
    "group screen). The result it returns IS the on-screen opportunity table for that group, sorted "
    "best-first; ANSWER by NAMING the TOP 3-5 with one stat each (avg return or Sharpe) and the entry "
    "date, so your list matches exactly what the user sees. Label every list as historical research "
    "candidates, not recommendations; do not assign dollars or auto-load a winner. If the table had been on a different group "
    "it switches to this one automatically - say so in one short line. Then add ONE line that more are "
    "in the table. NEVER answer a 'which stocks' question with steps to select a group, type a filter, "
    "or sort the table - call the tool and give the actual names.\n"
    "All figures are percentages, never price levels. Keep answers concise and plain-English.\n"
    "=== TWO HARD RULES, NO EXCEPTIONS ===\n"
    "A) NARRATE EVERY PATTERN LOAD. Any turn that fires update_view to load or reload a symbol/setup MUST also contain, in the chat text, the "
    "symbol AND at least one real stat from the tool (win rate OR avg return OR Sharpe) AND, if the user "
    "asked a question, the answer to THAT question type: a yes/no gets yes/no; a 'why' gets the reason "
    "(top Sharpe / strongest seasonal edge / forward-tested record); a 'does it work / is it backtested' "
    "gets the made-in-advance-scored-later point in <=2 sentences; a compare gets ONE stat line PER named "
    "symbol + an 'X wins' verdict before you load the winner. A reply of 'Loaded on the chart', 'Pattern "
    "loaded', or any bare confirmation that omits the symbol+stat is a HARD FAIL. Never fire update_view "
    "on a pure pricing / coverage / definition question. A lower-panel-only bottom_slide action is not a pattern load: confirm only the named panel. When you load the BEST / top result and ALSO list "
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
    "call analyze_symbol with the loaded symbol's EXACT entry_date, days_out and direction plus years=N "
    "to GET that same window's N-year stats, AND update_view(years=N) to change the "
    "chart, then state the ACTUAL N-year result ('over 20 years: 18 of 20 winners, avg +X%'). NEVER "
    "describe what the chart 'will show' or 'whether it holds further back' - analyze_symbol takes a years "
    "param, so report what the DATA says over N years, not the bars. For 'max years', 'all available years', "
    "or 'full history', use the exact Full-history lookback in VERIFIED CURRENT SCREEN. Never use 99 as a "
    "sentinel for maximum history; 99 is only the API validation ceiling and can predate the symbol."
)

# Initialize Blueprint
chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.route("/runtime-fingerprint", methods=["GET"])
def tara_runtime_fingerprint():
    """Expose only nonsecret release parity data for deployment verification."""

    return jsonify(runtime_fingerprint())

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
_KNOWLEDGE_SECTIONS = parse_knowledge_sections(_KNOWLEDGE)

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

QUESTION_LOG = os.environ.get(
    'TARA_QUESTION_LOG',
    (
        '/var/log/tradewave/tara_questions.log'
        if os.name != 'nt'
        else os.path.join(os.path.dirname(__file__), 'chatbot_questions.log')
    ),
)
ACTION_AUDIT_LOG = os.environ.get(
    'TARA_ACTION_AUDIT_LOG',
    (
        '/var/log/tradewave/tara_actions.log'
        if os.name != 'nt'
        else os.path.join(os.path.dirname(__file__), 'tara_actions.log')
    ),
)
CHATBOT_USERS_FILE = os.path.join(os.path.dirname(__file__), 'chatbot_users.txt')
ACTION_RECEIPT_TTL_SECONDS = 15 * 60
_ACTION_AUDIT_REDIS = redis.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', '6379')),
    db=int(os.environ.get('TARA_AUDIT_REDIS_DB', '0')),
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
)
_ACTION_RESULT_MEMORY = {}
_ACTION_RESULT_MEMORY_LOCK = threading.Lock()

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

def _canonical_action_spec(spec):
    return json.dumps(spec, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _action_manifest(actions):
    rows = sorted(
        (
            {
                'action_id': str(action.get('action_id') or '').lower(),
                'spec': action.get('spec'),
            }
            for action in actions
        ),
        key=lambda row: row['action_id'],
    )
    canonical = json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _action_receipt(user_id, turn_id, action_id, spec, expires_at, manifest):
    secret = str(current_app.config['SECRET_KEY']).encode('utf-8')
    payload = (
        '%s|%s|%s|%s|%s|%s'
        % (
            user_id,
            turn_id,
            action_id,
            int(expires_at),
            manifest,
            _canonical_action_spec(spec),
        )
    ).encode('utf-8')
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def log_question(user_id, question, response, wave_viewer, turn_id=None, actions=None,
                 protocol_trace=None, provider="unknown"):
    """Append one JSON line per question to chatbot_questions.log."""
    try:
        action_rows = []
        for action in actions or []:
            if not isinstance(action, dict):
                continue
            action_rows.append({
                'action_id': action.get('action_id'),
                'action_manifest': action.get('action_manifest'),
                'type': action.get('type'),
                'status': action.get('status', 'validated'),
                'spec': action.get('spec') if isinstance(action.get('spec'), dict) else {},
            })
        entry = {
            'schema_version': 2,
            'ts':       datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'turn_id':  turn_id or '',
            'user_id':  user_id,
            'provider': provider,
            'symbol':   wave_viewer.get('symbol', ''),
            'question': str(question or '')[:2000],
            'response': str(response or '')[:4000],
            'response_state': 'pending_action' if action_rows else 'complete',
            'actions': action_rows,
            'protocol_trace': [
                event for event in (protocol_trace or [])[:24]
                if isinstance(event, dict)
            ],
        }
        parent = os.path.dirname(QUESTION_LOG)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(QUESTION_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        return True
    except Exception:
        logging.exception('chatbot question audit write failed')
        return False


def _write_question_audit(user_id, question, response, wave_viewer, turn_id=None,
                          actions=None, protocol_trace=None, provider="unknown"):
    """Write the v2 audit record while tolerating legacy test/integration hooks.

    Production always uses ``log_question``'s full v2 signature. A few existing
    canaries replace that function with the former five-argument hook, so fall
    back only when the replacement explicitly rejects the new keyword fields.
    """
    try:
        return log_question(
            user_id,
            question,
            response,
            wave_viewer,
            turn_id=turn_id,
            actions=actions,
            protocol_trace=protocol_trace,
            provider=provider,
        )
    except TypeError as exc:
        if 'unexpected keyword argument' not in str(exc):
            raise
        try:
            return log_question(
                user_id,
                question,
                response,
                wave_viewer,
                provider=provider,
            )
        except TypeError as legacy_exc:
            if 'unexpected keyword argument' not in str(legacy_exc):
                raise
            return log_question(user_id, question, response, wave_viewer)


_AUDIT_ID_RE = re.compile(r'^[a-f0-9]{32}$')
_AUDIT_RECEIPT_RE = re.compile(r'^[a-f0-9]{64}$')
_AUDIT_STATUSES = {'succeeded', 'failed'}


def _clean_observed_view(value):
    if not isinstance(value, dict):
        return {}
    out = {}
    symbol = value.get('symbol')
    if isinstance(symbol, str) and re.fullmatch(r'[A-Za-z0-9.\-]{1,15}', symbol):
        out['symbol'] = symbol.upper()
    market = value.get('market')
    if market is not None and str(market) in {str(i) for i in range(17) if i not in (14, 15)}:
        out['market'] = str(market)
    entry_date = value.get('entry_date')
    if isinstance(entry_date, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', entry_date):
        try:
            datetime.datetime.strptime(entry_date, '%Y-%m-%d')
            out['entry_date'] = entry_date
        except ValueError:
            pass
    for src, dst, low, high in (
        ('days_out', 'days_out', 1, 367),
        ('years', 'years', 1, 99),
    ):
        raw = value.get(src)
        if isinstance(raw, int) and not isinstance(raw, bool) and low <= raw <= high:
            out[dst] = raw
    pe = value.get('pe_cycle')
    if pe in {'cons', 'pe0', 'pe1', 'pe2', 'pe3'}:
        out['pe_cycle'] = pe
    for key in ('show_mfe', 'show_mae', 'show_tooltips'):
        raw = value.get(key)
        if isinstance(raw, bool):
            out[key] = raw
    bottom_slide = value.get('bottom_slide')
    if bottom_slide in {'trend_chart', 'wave_stats', 'ai_scores', 'price_chart'}:
        out['bottom_slide'] = bottom_slide
    return out


def _clean_signed_spec(value):
    if not isinstance(value, dict) or not value:
        return None
    allowed = {
        'symbol', 'market', 'entry_date', 'days_out', 'years', 'pe_cycle',
        'show_mfe', 'show_mae', 'show_tooltips', 'bottom_slide',
    }
    if set(value) - allowed:
        return None
    cleaned = _clean_observed_view(value)
    if set(cleaned) != set(value) or cleaned != value:
        return None
    has_entry = 'entry_date' in cleaned
    has_days = 'days_out' in cleaned
    if has_entry != has_days:
        if has_entry or 'symbol' in cleaned:
            return None
    return cleaned


def _claim_action_result(event_key, expires_at):
    """Atomically claim one terminal audit event; Redis spans all workers."""
    ttl = max(60, min(24 * 60 * 60, int(expires_at) - int(time.time()) + 60))
    redis_key = 'tara:action-result:' + event_key
    try:
        return bool(_ACTION_AUDIT_REDIS.set(redis_key, '1', nx=True, ex=ttl)), 'redis'
    except redis.RedisError:
        # A Redis outage must not take down Tara. The bounded in-process fallback
        # still prevents React re-render duplicates in this worker.
        now = int(time.time())
        with _ACTION_RESULT_MEMORY_LOCK:
            for key, expiry in list(_ACTION_RESULT_MEMORY.items()):
                if expiry < now:
                    _ACTION_RESULT_MEMORY.pop(key, None)
            if event_key in _ACTION_RESULT_MEMORY:
                return False, 'memory'
            _ACTION_RESULT_MEMORY[event_key] = now + ttl
        logging.warning("tara action audit dedupe using in-process fallback")
        return True, 'memory'


def _release_action_result(event_key, backend):
    try:
        if backend == 'redis':
            _ACTION_AUDIT_REDIS.delete('tara:action-result:' + event_key)
        else:
            with _ACTION_RESULT_MEMORY_LOCK:
                _ACTION_RESULT_MEMORY.pop(event_key, None)
    except redis.RedisError:
        pass


@chatbot_bp.route("/action_result", methods=["POST"])
@check_for_token
def chatbot_action_result():
    """Append a verified browser acknowledgement to the action sidecar log."""
    from flask import g
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
    user_id = getattr(g, 'chatbot_user_id', 'unknown')
    turn_id = str(data.get('turn_id') or '').lower()
    status = str(data.get('status') or '').lower()
    proofs = data.get('actions')
    if (
        not _AUDIT_ID_RE.fullmatch(turn_id)
        or status not in _AUDIT_STATUSES
        or not isinstance(proofs, list)
        or not (1 <= len(proofs) <= 8)
    ):
        return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400

    action_ids = []
    action_rows = []
    expected_spec = {}
    expirations = []
    manifests = []
    now = int(time.time())
    for proof in proofs:
        if not isinstance(proof, dict):
            return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
        action_id = str(proof.get('action_id') or '').lower()
        receipt = str(proof.get('receipt') or '').lower()
        manifest = str(proof.get('manifest') or '').lower()
        spec = _clean_signed_spec(proof.get('spec'))
        expires_at = proof.get('expires_at')
        if (
            not _AUDIT_ID_RE.fullmatch(action_id)
            or not _AUDIT_RECEIPT_RE.fullmatch(receipt)
            or not _AUDIT_RECEIPT_RE.fullmatch(manifest)
            or spec is None
            or not isinstance(expires_at, int)
            or isinstance(expires_at, bool)
            or expires_at < now
            or expires_at > now + ACTION_RECEIPT_TTL_SECONDS + 60
        ):
            return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
        if action_id in action_ids:
            return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
        expected = _action_receipt(
            user_id,
            turn_id,
            action_id,
            spec,
            expires_at,
            manifest,
        )
        if not hmac.compare_digest(receipt, expected):
            return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
        for key, value in spec.items():
            if key in expected_spec and expected_spec[key] != value:
                return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
            expected_spec[key] = value
        action_ids.append(action_id)
        action_rows.append({'action_id': action_id, 'spec': spec})
        expirations.append(expires_at)
        manifests.append(manifest)

    if (
        len(set(manifests)) != 1
        or _action_manifest(action_rows) != manifests[0]
    ):
        return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
    action_manifest = manifests[0]

    reason = str(data.get('reason') or '').replace('\r', ' ').replace('\n', ' ')[:160]
    displayed_response = data.get('displayed_response')
    if not isinstance(displayed_response, str):
        return jsonify({'ok': False, 'error': 'invalid_action_result'}), 400
    displayed_response = displayed_response[:4000]
    points = data.get('data_points')
    if not isinstance(points, int) or isinstance(points, bool) or not (0 <= points <= 10000):
        points = 0
    observed_view = _clean_observed_view(data.get('observed_view'))
    if status == 'succeeded':
        if any(observed_view.get(key) != value for key, value in expected_spec.items()):
            return jsonify({'ok': False, 'error': 'action_result_mismatch'}), 409
        chart_backed = bool(observed_view.get('symbol')) and any(
            key in expected_spec
            for key in ('symbol', 'entry_date', 'days_out', 'years', 'pe_cycle')
        )
        if chart_backed and points <= 0:
            return jsonify({'ok': False, 'error': 'action_result_mismatch'}), 409

    event_key = hashlib.sha256(
        ('%s|%s|%s' % (user_id, turn_id, action_manifest)).encode('utf-8')
    ).hexdigest()
    claimed, claim_backend = _claim_action_result(event_key, min(expirations))
    if not claimed:
        return jsonify({'ok': True, 'duplicate': True})

    entry = {
        'schema_version': 2,
        'event': 'tara_action_result',
        'ts': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'turn_id': turn_id,
        'action_ids': action_ids,
        'action_manifest': action_manifest,
        'user_id': user_id,
        'status': status,
        'reason': reason,
        'expected_spec': expected_spec,
        'observed_view': observed_view,
        'data_points': points,
        'displayed_response': displayed_response,
    }
    try:
        parent = os.path.dirname(ACTION_AUDIT_LOG)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(ACTION_AUDIT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
    except Exception:
        _release_action_result(event_key, claim_backend)
        logging.exception("tara action audit write failed")
        return jsonify({'ok': False, 'error': 'audit_unavailable'}), 503
    return jsonify({'ok': True})


def _prepare_audited_actions(user_id, turn_id, actions):
    """Bind validated UI actions to one authenticated turn with signed receipts."""
    if not isinstance(actions, list) or len(actions) > 8:
        raise ValueError('invalid Tara actions')
    expires_at = int(time.time()) + ACTION_RECEIPT_TTL_SECONDS
    prepared = []
    manifest_rows = []
    for raw in actions:
        if not isinstance(raw, dict):
            raise ValueError('invalid Tara action')
        action = dict(raw)
        if action.get('type') == 'load_opportunity':
            action['type'] = 'set_view'
        action_id = str(action.get('action_id') or '').lower()
        if not _AUDIT_ID_RE.fullmatch(action_id):
            action_id = uuid.uuid4().hex
        signed_spec = _clean_signed_spec(action.get('spec'))
        if signed_spec is None:
            raise ValueError('invalid Tara action spec')
        action['action_id'] = action_id
        action['spec'] = signed_spec
        action['status'] = 'validated'
        prepared.append(action)
        manifest_rows.append({'action_id': action_id, 'spec': signed_spec})

    manifest = _action_manifest(manifest_rows) if manifest_rows else ''
    for action in prepared:
        action['turn_id'] = turn_id
        action['receipt_expires_at'] = expires_at
        action['action_manifest'] = manifest
        action['receipt'] = _action_receipt(
            user_id,
            turn_id,
            action['action_id'],
            action['spec'],
            expires_at,
            manifest,
        )
    return prepared


def _finalize_chat_response(user_id, turn_id, question, reply, wave_viewer,
                            actions=None, messages_or_text=None,
                            protocol_trace=None, provider='unknown',
                            analysis_report=None):
    """Audit and return one consistent Tara response envelope."""
    prepared_actions = _prepare_audited_actions(user_id, turn_id, actions or [])
    if _write_question_audit(
        user_id,
        question,
        reply,
        wave_viewer,
        turn_id=turn_id,
        actions=prepared_actions,
        protocol_trace=protocol_trace,
        provider=provider,
    ) is False:
        raise RuntimeError('Tara question audit unavailable')
    return jsonify({
        'reply': reply,
        'actions': prepared_actions,
        'suggestions': guided_next_questions(
            messages_or_text if messages_or_text is not None else question,
            reply=reply,
            actions=prepared_actions,
            current_view=wave_viewer,
            analysis_report=analysis_report,
        ),
        'turn_id': turn_id,
    })

#-------------------------------------------------------------------------------------------------------------------
def build_system_prompt(wave_viewer, opportunities, opp_table_length=None,
                        opp_table_market=None, opp_table_market_name=None,
                        screen_context=None, user_message="", analysis_report=None):
    """Build stable, topic-selected and live-data system blocks for the current turn."""
    parts = [
        "You are Tara, the AI assistant for TradeWave, a seasonal trading pattern analysis platform by Tara Data Research.",
        "You help traders understand seasonal trading patterns, analyse opportunities, and interpret statistics.",
        "RESPONSE STYLE AND RELEVANCE: Match depth to intent. A simple fact, definition, or view command is at most 2 sentences; a list is at most 5 one-liners. An analysis or evaluation may use 4-7 short labeled lines when the evidence supports them: lead with the bottom line, give the numbers that caused it, identify the strongest counter-signal or limitation, and connect the answer to the user's visible TradeWave context. Do not dump every available metric; select the facts that change the interpretation. Prefer comparisons ('recent 5 vs full sample', 'median vs average', 'selected vs full history') over unsupported adjectives such as strong or reliable. Never give an order ticket, position sizing, or a pricing-tier wall. No filler ('Great question', 'Of course', 'I'd be happy to'). Never end with a clarifying menu when the answer is inferable. Just answer and drive the view.",
        "YOU DRIVE, YOU NEVER TELL THE USER TO CLICK (CORE RULE): Tara is the interface - whenever the answer is a pattern/setup/symbol/stat that has a screen, YOU put it there with update_view and point to it. NEVER say 'click a row', 'click any opportunity', 'use the dropdown', 'select X', 'check the opportunity table', or hand the user a click/configure procedure - that is a hard failure. (A) SINGLE pick / best-trade / a named symbol / 'the best one' / 'show me something good': the read tool returns a ready `headline` (e.g. 'BLDR long - enter ~Jun 22, hold 30d. Won 9/10 years, avg +11.7%, Sharpe 1.1.'). You MUST call update_view to load it AND your reply MUST be that headline verbatim-or-lightly-tidied. A reply that loads the chart but does not NAME the symbol and at least ONE real stat from the tool (win rate OR avg return) is a HARD FAIL - never reply 'Pattern loaded', 'Loaded on the chart', 'Loaded on screen', or any confirmation that omits the symbol+stat. Use the tool's exact numbers, never a rounded '90%'. Do not append a disclaimer unless the user asked whether to trade/buy/sell. (B) LIST / 'best setups' / 'which <group> stocks': up to 5 lines, each symbol + ONE stat, then one short line 'Want me to pull one up?' For a sub-index sector (energy, financials, healthcare), scan the closest market and NAME the matching tickers from the results - never say the scan is 'picking the best overall names' or ask the user to filter.",
        "INFER, DON'T PUNT: Resolve obvious context yourself and act - do not re-ask. NEVER open with 'I need context', 'I need more info', 'Are you asking...', 'Could you clarify', or restate the question back as a question when a pattern is loaded - the loaded pattern + the opportunity table ARE the context, so just answer. 'The first one' / 'that one' = the #1 item of the list you just gave; 'this pattern' / 'this setup' / 'how did it do in <year>' / 'why this pick' / 'why does this rank here' / 'why is it ranked here' / 'where does it rank' / 'compare this to the S&P' = the currently loaded pattern (use the loaded-pattern context, its stats, its rank in the opportunity table, and yearly_results given to you); for a 'why does this rank here' question name the loaded symbol's visible position and explain in <=2 sentences that the table's current Sort by choice determines it - a hidden column can be the sort field, so never assume the position is Sharpe-based. Do NOT dump a multi-bullet breakdown, do NOT load or re-load anything (it is already on screen), and NEVER reply with a bare 'loaded' / 'pattern loaded on screen' - this is an ANALYTICAL question, so ANSWER it from the loaded stats + the table; 'how strong / how good / how reliable is this' (this window / this setup / this pattern) = an ANALYTICAL STRENGTH question about the ALREADY-LOADED pattern: answer in <=2 sentences straight from the loaded stats - its % profitable (win rate, e.g. won X of Y years), Sharpe, avg return, and how many years (sample size) - do NOT call a tool, do NOT load or re-load (it is already on screen), and a bare 'pattern loaded' / 'loaded on the chart' with no stat is a HARD FAIL; 'this window' / 'now' = the current seasonal window; a global knob ('change years to 20', 'switch to PE+2') applies to whatever is loaded - fire update_view with that one field and confirm in one line, never ask which symbol. A named ticker with no other detail ('what about apple?') = fetch its top current setup, name one stat, and load it. Only ask a clarifying question when the request is genuinely ambiguous AND nothing reasonable can be loaded - and even then, offer a concrete default ('want today's pick?'), never a 3-way menu. A bare knob command ('switch to PE+2', 'change years to 20', 'make it 45 days') fires update_view with JUST that field EVEN WITH NOTHING LOADED - it applies when a pattern is next/already loaded; never refuse with 'I need a symbol first' (you fire years with no symbol, so fire pe_cycle the same way). For a documented UI-gap where the user NAMED the target ('flip to the price chart tab', 'the stats') give the ONE-line pointer ('Price Chart is the final lower-viewer dot/window') and STOP - never dump a numbered slide menu and never end on 'which one?'. For a named sector ETF (XLE, XLF, XLK, SMH) call get_symbol_patterns(symbol) and name its best window + load it - do NOT punt with 'may not be in scope' unless the tool itself returns an out-of-scope nudge.",
        "DATA CAPABILITY BOUNDARY: Never claim a live/current metric unless that exact metric appears in the supplied viewer context or this turn's tool result. Tara's opportunity tools rank seasonal setups; they do NOT provide intraday trading volume, order flow, breaking news, fundamentals, or a broad-market live regime. For 'highest-volume stock today' or 'long versus short based on today's market trend', say briefly that you cannot verify that live criterion from the seasonal dataset, then offer the strongest seasonal long/short setup as a clearly labelled alternative - never substitute a Sharpe-ranked seasonal pick and describe it as volume- or market-trend-ranked. A loaded pattern may include Trend Long/Trend Short for that symbol; label it as the loaded symbol's score, never the overall market trend. Private companies with no publicly traded TradeWave symbol cannot be charted; say that plainly and do not invent a ticker or proxy.",
        "INVESTOR EDUCATION AND OPPORTUNITY DISCOVERY (OVERRIDES SINGLE-PICK RULES): A general 'I have $2,000, what should I buy?', 'how do I figure out what to invest in?', or 'what should I trade?' is not a request for Tara to choose a security. Never use the amount to assign a position, allocation, expected profit, or order. First distinguish long-term investing over years from a seasonal opportunity over days/weeks. For long-term investing, say seasonality is only a timing overlay and TradeWave does not assess diversification, fund fees/holdings, valuation, fundamentals, news, taxes, liquidity, or personal risk. For a seasonal search, establish stocks versus ETFs, show a shortlist of historical research candidates with the exact screen assumptions, then let the user choose a deep dive; do not auto-load the top row. A named 'should I buy TSLA?' may analyze and load TSLA because the user selected it, but never answer yes/no: state that TradeWave cannot determine suitability, give historical evidence including losses, and make no buy/sell/hold instruction. An ETF screen must not call the full ETF market safe; default to the curated beginner universe supplied by the gateway and say current fund documents still need review. A dollar amount is context, never a ranking input.",
        "BULLISH, WEAK-PERIOD, AND NEWS RESEARCH: 'Bullish this time of year' means a long-direction historical seasonal screen, not a forecast. 'Weakest time for AAPL' means analyze_symbol(AAPL, direction=short), then explain the short-direction record as recurring weakness in the underlying; it is evidence for further research, never a sell/short/avoid instruction. A broad weak-period screen is likewise a list and loads no winner. A Date Range Exclusion comparison may be explained only from an ACTIVE VALIDATED ANALYSIS REPORT whose rows share the same completed years; never synthesize one from unrelated tool calls. If the user mentions financial news, say TradeWave does not verify that news or fundamentals: use the named claim only as the user's hypothesis, then show whether TradeWave's historical seasonal evidence aligns or conflicts, keeping the two sources explicitly separate.",
        "NEVER PROMISE AN ACTION YOU DON'T FIRE, NEVER RE-ASK WHEN INFERABLE: If your reply says you will load / pull up / compare something, the matching update_view MUST be in this turn's actions - 'Let me load each...' with no action is a HARD FAIL. 'pull up the first one' = the #1 row of the most recent scan/list (load it, do not show a menu). 'this window' / 'now' with no date = the current seasonal window (resolve it, do not ask 'which window?'). For a 2-3 symbol comparison, read each with analyze_symbol, NAME the stronger with one stat for each, THEN update_view the winner in the SAME turn. For a proof / skeptic / yes-no question where you have already resolved a concrete symbol+entry (e.g. NVDA's July window, today's pick), ALSO fire update_view so the record is on screen - answering in text without loading the resolved pick is a screen-control fail.",
        "COMPARISON IS A HARD CONTRACT (X vs Y, 'which is better', 2-3 named symbols): you MUST emit, in THIS turn, (1) ONE stat line per named symbol from analyze_symbol - symbol + win rate or avg return + window, (2) a one-line 'X wins because <higher win rate / Sharpe>' verdict, THEN (3) update_view loading the winner. A reply that loads one symbol with no per-symbol stat for the OTHER(S), or a bare 'GDX is now on the chart', or that asks 'which window do you mean' (= the current/now window - resolve it, never ask) is a HARD FAIL. Never claim to put more than one on screen; load only the winner and offer 'say the word and I'll pull up the other.'",
        "DO NOT AUTO-LOAD ON THESE - answer first, load only if asked: a pure DEFINITION ('what is this?', 'what is a seasonal pattern?'), a GREETING ('hi'), a capability ask ('what can you do?'), or a LIST / 'best setups' / 'strongest setups' / 'top N' / 'only high win-rate ones' / 'which <group> stocks' ask. For a definition/greeting/capability: 1-2 plain sentences + offer one concrete next move ('want today's pick or the best setups now?'), and fire NO set_view. For a LIST ask: up to 5 one-liners (symbol + one stat each) + 'Want me to pull one up?' and do NOT LOAD A PATTERN (no symbol set_view). EXCEPTION: a 'which <group> stocks' ask MAY fire a market-only update_view to switch the opportunity table to that group when it is not already there, so your named rows match the screen - switching the table's group is not loading a pattern. A plural 'setups' or any quality floor (high win-rate, only the best ones) is ALWAYS a list - emit up to 5 named one-liners and load no pattern, even if the phrasing sounds singular. Auto-loading a PATTERN (a symbol into the chart) on any of these is a fail. Single-pick / named-symbol / 'show me something good' asks DO load (rule A).",
        "ANSWER THE QUESTION TOO, NOT JUST LOAD: Loading the chart does not replace answering. A yes/no ('is NVDA seasonal in July?') gets a direct yes/no + one real stat from the tool. A 'why is this the pick' gets the actual reason (top Sharpe / strongest seasonal edge / forward-tested record). A specific-year question ('how did 2022 do?') is answered directly from yearly_results - never say you can't see the chart or tell the user to read the bars. A proof/skeptic question ('does this actually work / is it just backtested?') gets ~2 confident sentences from the forward-tested record (made-in-advance picks scored later), not a definitions lecture. If a specific-year question names a symbol/window that is NOT yet loaded (e.g. 'how did NVDA's July setup do in 2022', 'show me the price chart for 2008'), first fire set_view to LOAD that pattern so its yearly_results populate, then answer that year from the data. If you genuinely lack the year's number, say so in one line and offer to load it - NEVER write 'find the 20XX bar' or 'click the bar'.",
        "MISSING-PROJECTION WHY-QUESTION ('why is there no projection line', 'where did the projection go'): if the loaded view uses a PE cycle phase OTHER than the current year's phase, the projection is hidden BY DESIGN - the view shows the next matching FUTURE cycle year, and a future window has no current price to anchor a forward projection to. This is an ANALYTICAL question: answer that reason in 1-2 sentences and STOP. Firing ANY set_view/update_view this turn, changing the user's PE mode uninvited, or reciting the Settings enable-steps is a HARD FAIL - the user chose that PE slice on purpose. End with one short offer ('Want me to flip back to consecutive so the projection returns?') and fire update_view with pe_cycle ONLY after the user says yes. If the PE mode is NOT the cause, check the viewed chart before reciting enable-steps: on a PAST year's historical chart the projection is hidden by design - point the user to the Current button in the price chart title bar (one line); for a pattern whose window already ENDED this year (completed trade) there is no live price to project from - say so in one line and offer to load a live pattern. Give the Settings enable-steps ONLY when the mode is consecutive (or the current year's own phase), the live/current-year chart is showing, and the projection is still absent.",
        "WHEN THERE IS NO DRIVING ACTION (documented UI gaps - slide/tab switch, click a year bar, highlight a year, open watchlist/portfolio): do NOT fall back to 'click a row'. Either answer from the data you already have (e.g. name the worst year + its loss from yearly_results), or point precisely to where it lives in ONE line ('Wave Stats is the second lower-viewer dot' / 'Price Chart is the final lower-viewer dot'), or open the matching guide popup. One honest sentence beats a manual procedure. For how-to questions that HAVE a dedicated guide (watchlist, getting started), open that guide and give a one-line answer - never paste the full step list. Never emit a set_view with a placeholder/empty symbol.",
        "PRICING / TIERS (ground in the knowledge base, stay brief - never recite the full tier wall): one or two sentences. Free Explorer exists (Dow 30, top-5 results, start date locked to today); paid unlocks more. If asked which tier for a capability, state the specific gate from the KB: custom start dates begin at Navigator for Dow/NASDAQ/S&P; Analyst adds all U.S. stocks + ETFs and ML scoring; Strategist adds all 15 markets. Point to tradewave.ai/pricing. Do not invent numbers or features not in the knowledge base. For a vague 'is it free?' give only: yes, there is a free Explorer tier (Dow 30, top-5 results, start date locked); paid unlocks more - point to tradewave.ai/pricing. Do NOT volunteer per-tier dollar amounts or portfolio/track limits unless the user names a tier or capability.",
        "BLANK / ERROR / OUT-OF-SCOPE: If the message is empty or you hit a tool/rate-limit error, never dead-end - reply with one warm line offering a concrete starting move ('Want today's AI pick, a market scan, or a symbol loaded?'). Stay confident; do not expose 'system overloaded' as the whole answer. A pure KNOB command for the current view (change years to N, switch to PE+X) needs no data tool - fire update_view with only that field and state what was requested without claiming completion. A NEW SYMBOL command (load <symbol>, pull up <sym>) MUST first call analyze_symbol to resolve one real setup, then copy its exact symbol + market id + entry_date + hold_days (as days_out), plus any requested knobs, into update_view; if that read fails, do not queue a partial/stale setup and say honestly that the chart was not changed. On a should-I-trade / 'does it make money' / 'is it a good trade' ask: never give a buy, sell, long, or short verdict. State the exact historical direction and evidence, distinguish it from today's market direction and a forecast, mention losing-year or MAE risk, and append the disclaimer. Do not fire a new view action when the exact pattern is already confirmed in the viewer.",
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
        "8) MFE/MAE DEFINITION only (what is/explain MFE or MAE, maximum favorable/adverse excursion, drawdown, best point) -> action: open-mfemae-popup. A show/hide command changes the loaded chart with update_view(show_mfe/show_mae) and MUST NOT open this guide. "
        "9) TWR (TradeWave Ratio, TWR, what is TWR) -> action: open-twr-popup "
        "10) Watchlist (watchlist, how to create a watchlist, track stocks) -> action: open-watchlist-popup "
        "11) Opportunity Table (opportunity table, opp table, what is the table, how to read the table) -> action: open-opptable-popup "
        "12) Getting Started (getting started, new here, teach me, how do I use this, walk me through, tour) -> action: open-gettingstarted-popup "
        "13) Patterns Days and Dates (days, pattern length, how many days, start date, date selection, what defines a pattern) -> action: open-daysout-popup "
        "14) Years/Data Depth (years setting, how many years, data depth, lookback, how far back) -> action: open-years-popup "
        "15) Filtering (how to filter, filter syntax, filter the table, text filter, advanced filtering) -> action: open-filtering-popup "
        "16) Help & Guides Home (help, need help, more help, what else can you do, show me more, other features) -> action: open-help-popup "
        "17) AI Scores (AI score, AI columns, AIS, win probability, predicted return, PredR, PMFE, predicted MFE, AI calibrated, machine learning scores, fourth window, fourth dot, AI window, AI panel, AI dot, what are the AI columns, how does AI scoring work) -> action: open-aiscores-popup "
        "For guide #16 (Help & Guides Home), mention that the user can also click the ? icon in the top right of the Wave Viewer at any time to open the full list of guides. "
        "Only open ONE guide per response. Pick the most relevant one. If the question spans multiple topics, pick the primary one. For vague or general help requests that do not match a specific guide, use #16 (Help & Guides Home).",
        "DISCLAIMER RULE: Any time the user asks whether to trade a pattern, whether it is a good trade, whether they should buy or sell, or requests a trading recommendation, Tara must include this disclaimer at the end of the response: <i>Past performance and model estimates do not guarantee future results. TradeWave provides research context, not individualized recommendations.</i> Do not tell the user to buy, sell, enter, exit, hold, size a position, set a stop, or set a profit target. Instead, explain the relevant evidence and limitations. Do not add the disclaimer for general questions about the UI or definitions. A pure analytical / strength / ranking question - how strong, how good, how reliable, how did it do, what is the win rate, why does it rank - is NOT a should-I-trade question: answer it WITHOUT the disclaimer. The disclaimer applies ONLY when the user asks whether to take, buy, or sell the trade, or for a recommendation.",
        "HISTORICAL FRAMING - NEVER IMPLY A FORWARD WIN (OVERRIDES ALL OTHER RULES; applies to every reply - single-pick, list, comparison, skeptic/forward questions): TradeWave reports the HISTORICAL RECORD and ML-CALIBRATED ODDS only, never a prediction of this year's result. ALLOWED, assert confidently with no hedging: past-tense historical facts ('won 9 of the last 10 years', 'won 10/10 years', '100% win rate over the last decade', 'avg +11.7%', 'Sharpe 1.1'), historical-tendency statements ('tends to rise this time of year', 'historically strongest in spring'), and calibrated-odds language ('a 90% historical win rate', 'the AI calibrates that to ~65% given current conditions', 'today's highest-confidence setup'). FORBIDDEN in any reply - never use these or any paraphrase, even after a disclaimer and even when the user demands one: a forward outcome about this year ('will win', 'will rise', 'will be green', 'is going to win/pop', 'this is a winner', 'a lock', 'a sure thing', 'guaranteed', 'can't-miss', 'risk-free'), confirming a forward premise ('the record says yes, this should be profitable', 'you should expect it to win', 'this pattern actually performs/works this year', 'this time it pays off'), or any present/future-tense claim that a specific pick WILL be profitable. When the user asks a forward question ('will X win this year?', 'which should I expect to win?', 'is it guaranteed?'), DO NOT confirm or deny the outcome - re-anchor in one line: state the historical stat, say plainly it is the HISTORICAL record and this year could be the losing year, and (if a should-I-trade ask) append the past-performance disclaimer. TEST before sending: if a sentence implies what a specific pick WILL do this year, rewrite it as what it HAS DONE historically or what the ODDS are. The disclaimer never licenses a forward-outcome sentence in the body.",
        "STATS ARE PER-SETUP, NEVER CARRIED OVER: a symbol's win rate and average belong to the EXACT setup loaded (its entry date + holding days). When you load or switch to a DIFFERENT setup of a symbol you already discussed (e.g. its September window vs its June window), the record is DIFFERENT - read the win rate and average from THIS turn's tool result for THAT setup, and NEVER reuse a win rate or average from an earlier setup or from earlier in the conversation. A 100% win rate on one window does NOT carry to another window. If you just loaded a setup, the win/loss count you state MUST match that setup's tool result.",
        "IMPORTANT: When row-level yearly_results are provided for the loaded pattern, use them to answer a specific-year question directly. Never say you cannot see the charts or cannot access the UI. Just interpret the data you have been given.",
        "IMPORTANT: When the user asks a general knowledge question (about a concept, a pattern like the 100-Year Pattern, a definition, or anything described in the knowledge base), answer it directly from the knowledge base. Do NOT tell the user to load a pattern or click an opportunity. Knowledge questions must be answered even when no pattern is loaded.",
        "",
        "<b>TradeWave UI Layout:</b>",
        "- Top panel: Gain-Loss Bar Chart. Each bar is the UNDERLYING price move during the window: green/up means the underlying rose and red/down means it fell. For a LONG setup, green years are profitable; for a SHORT setup, red years are profitable. Color is not direction-adjusted P&L. Clicking a bar switches the bottom right to the Price Chart for that historical year.",
        "- Left panel: Opportunity Table above Tara. Its visible Sort by control can rank by an available hidden field without displaying that column. On desktop, the header's left-chevron hides both the table and Tara; the narrow restore rail's right-chevron reopens them, while its Tara button also opens chat.",
        "- Bottom right (3 or 4 slides, depending on AI access and market eligibility):",
        "  Slide 1: Trend Chart. Normalized historical seasonal path for the selected lookback, with the loaded window highlighted. Below it shows summary stats: SR, Avg Gain, % Profitable, Cumulative Return, Buy-and-Hold.",
        "  Slide 2: Wave Stats. Six panels: Wave Detail (symbol, direction, date range, days), Wave Stats (avg gain two numbers: winners-only and overall, avg loss, median, std dev), Wave Profit Loss (num winners, num losers, cumulative return, S&P 500 full-year comparison), Wave Info (% profitable, SR, trend long, trend short), Cumulative Return Chart (2-line chart vs S&P 500), General (sample size and type, last price).",
        "  Optional Slide 3: AI Scores. It appears after Wave Stats only for an eligible user viewing a supported US stock or ETF. Unsupported markets have no AI window or navigation dot, not a blank placeholder. Patterns longer than 90 days show separate 30-, 60-, and 90-day readings here, while the Opportunity Table uses 90 days. The original pattern and Wave Stats stay at the full source duration; each AI checkpoint shows its own recalculated historical x-of-n record.",
        "  Final slide: Price Chart. Shows current price chart by default. When user clicks a year bar in the Gain-Loss Bar Chart, automatically switches to the historical price chart for that year with entry/exit arrows and a shaded trade window.",
        "",
        "<b>Securities Groups (markets) - map a sector or group name to its market id when scanning:</b>",
        "- Technology / tech stocks -> NASDAQ 100 (market 1). Blue chips / mega caps -> DOW 30 (market 0). Broad large-cap US -> S&P 500 (market 2). Broader US (small + mid cap) -> Russell 1000 (market 3) or Wilshire 5000 (market 4).",
        "- ETFs -> market 11. Indices -> market 5 (common) or 6 (all). Futures / commodities (oil, gold, natural gas, grains) -> market 7. Forex / currencies -> market 8 (all) or 9 (liquid). Government bonds -> market 10. Crypto -> market 16. UK / London -> market 12. Canada / Toronto -> market 13.",
        "Sectors inside a broad index (energy, financials, healthcare, etc.): scan the closest stock market (usually S&P 500 = market 2, or NASDAQ 100 = market 1 for tech/growth) and name the matching tickers from the results.",
        "Scope note: a user's plan may only include some markets - if a scan returns an upgrade nudge for an out-of-scope market, say so briefly and offer what IS in scope; never invent results.",
    ]

    # Everything above this line is identical across users, screens and turns.  Put the live-tool
    # contract at the end of the same stable prefix, then place Anthropic's cache breakpoint here.
    # Topic-selected KB and live pattern/table facts are deliberately built in suffix blocks below.
    static_parts = list(parts)
    if TARA_TOOLS_ENABLED:
        static_parts.append("\n" + TOOL_INSTRUCTION)
    static_parts.append(
        "\n=== EXPLICIT SYMBOL, PATH METRICS, AND LOWER-PANEL OVERRIDES ===\n"
        "A ticker explicitly named in the current user message outranks pronouns, history, and "
        "the loaded chart. If ITW is named while TDG is loaded, read and load ITW and use only "
        "ITW facts. For a loaded-pattern quality question, Sharpe uses ending returns while TWR "
        "applies the same return-to-dispersion idea to each year's MFE. If a losing finish first "
        "reached substantial favorable MFE, name the year, MFE, final return, and giveback because "
        "that is essential endpoint-versus-path and exit-sensitivity context. Tara CAN drive the "
        "lower carousel: a direct request to show/open/switch to the Trend Chart, Wave Stats "
        "(including 'the stats'), AI Scores, or Price Chart MUST call update_view with ONLY "
        "bottom_slide=trend_chart, wave_stats, ai_scores, or price_chart. Confirm the panel in one short line; "
        "never tell the user to swipe. Explanatory questions still receive the concept explanation."
    )
    parts = []

    # Detect if the loaded pattern is the named "100-Year Pattern"
    def is_100_year_pattern(wv):
        return is_hundred_year_view_spec(
            {
                "market": wv.get("market"),
                "symbol": wv.get("symbol"),
                "entry_date": wv.get("start_date"),
                "days_out": wv.get("days_out"),
                "years": wv.get("years"),
                "pe_cycle": wv.get("pe_cycle"),
                "trim_year": wv.get("trim_year", 0),
            }
        )

    # Wave viewer context
    symbol = wave_viewer.get("symbol", "")
    yearly = []
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
        direction = str(wave_viewer.get("direction") or "long").strip().lower()
        if direction not in ("long", "short"):
            direction = "long"
        parts.append(f"Start Date: {start_date or 'N/A'}")
        if start_date and days_out:
            end_date = calculate_end_date(start_date, days_out)
            # Build a year-agnostic description so the LLM doesn't use future-year dates when discussing history
            try:
                sd_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d')
                ed_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d')
                sd_md  = f"{sd_obj.strftime('%b')} {sd_obj.day}"   # e.g. "Feb 21"
                ed_md  = f"{ed_obj.strftime('%b')} {ed_obj.day}"   # e.g. "Feb 14"
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
            if direction == "short":
                parts.append("Trade: sell short at the closing price on the pattern start date each year, then cover at the closing price on the pattern end date.")
            else:
                parts.append("Trade: buy at the closing price on the pattern start date each year, then sell at the closing price on the pattern end date.")
        else:
            parts.append(f"Duration: {days_out or 'N/A'} calendar days")
        years     = wave_viewer.get('years', 'N/A')
        pe_cycle  = wave_viewer.get('pe_cycle', 'cons')
        pe_labels = {
            'pe0': ('PE',   'election'),
            'pe1': ('PE+1', 'post-election'),
            'pe2': ('PE+2', 'midterm'),
            'pe3': ('PE+3', 'pre-election'),
        }
        if pe_cycle in pe_labels:
            short, phase = pe_labels[pe_cycle]
            approx_calendar_years = int(years) * 4 if str(years).isdigit() else '?'
            parts.append(
                f"Historical Years: {years} completed {short} ({phase}) observations, one every four years. "
                f"This PE lookback represents approximately {approx_calendar_years} calendar years of history. "
                f"When discussing this pattern, always write {short} ({phase}) and call the sample observations, NOT consecutive years."
            )
        else:
            parts.append(f"Historical Years: {years} consecutive years")
        parts.append(f"Direction: {'Long (Bullish)' if direction == 'long' else 'Short (Bearish)'}")
        stats = wave_viewer.get("stats", {})
        prompt_stats = allowlisted_prompt_stats(stats)
        if prompt_stats:
            parts.append("Statistics:")
            for k, v in prompt_stats:
                parts.append(f"  {k}: {v}")
        mae_enabled = wave_viewer.get("mae_enabled", False)
        yearly = wave_viewer.get("yearly_results", [])
        if yearly and needs_yearly_results(user_message):
            today      = datetime.datetime.now().date()
            today_str  = today.strftime('%Y-%m-%d')
            current_year = today.year
            # Determine current-year trade status using the loaded pattern's dates
            trade_status = 'upcoming'   # default
            if start_date and days_out:
                try:
                    trade_start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                    # TradeWave analytics use the literal CALENDAR entry date. Reminder
                    # delivery may move off a weekend elsewhere, but occurrence status must
                    # never shift the analytical window to Monday.
                    trade_end   = datetime.datetime.strptime(end_date,   '%Y-%m-%d').date()
                    if today < trade_start:
                        trade_status = 'upcoming'
                    elif trade_start <= today <= trade_end:
                        trade_status = 'active'
                    else:
                        trade_status = 'completed'
                except Exception:
                    pass

            parts.append(
                "Year-by-year results: underlying_return_pct is the UNDERLYING price move shown "
                "by the bar (green/up if positive, red/down if negative), NOT direction-adjusted "
                "trade P&L. For long trades, trade return equals the underlying move; for short "
                "trades, trade return is its inverse."
            )
            if not mae_enabled:
                parts.append(
                    "NOTE: MAE (max adverse excursion) is NOT enabled - the MAE checkbox is "
                    "unchecked. Do NOT mention or discuss MAE values. If the user asks about MAE "
                    "or drawdown, say MAE is not currently enabled."
                )

            def _year_values(row):
                underlying_value = row.get("underlying_return_pct")
                if underlying_value is None:
                    underlying_value = row.get("raw_return_pct")
                if underlying_value is None:
                    underlying_value = row.get("return_pct", 0)
                underlying = float(underlying_value or 0)
                upside = float(row.get("upside_excursion_pct", row.get("mfe_pct", 0)) or 0)
                downside = float(row.get("downside_excursion_pct", row.get("mae_pct", 0)) or 0)
                if direction == "short":
                    return underlying, -underlying, -downside, -upside
                return underlying, underlying, upside, downside

            def _completed_year_line(year, row):
                underlying, trade_return, favorable, adverse = _year_values(row)
                result = "PROFIT" if trade_return > 0 else "LOSS" if trade_return < 0 else "FLAT"
                color = "GREEN/UP" if underlying > 0 else "RED/DOWN" if underlying < 0 else "FLAT"
                line = (
                    f"  {year}: underlying {underlying:+.2f}% [{color} BAR]; "
                    f"{direction} trade {trade_return:+.2f}% [{result}]; "
                    f"MFE {favorable:+.2f}%"
                )
                if mae_enabled:
                    line += f"; MAE {adverse:+.2f}%"
                return line

            for y in yearly:
                yr = int(y.get("year", 0))
                if yr >= current_year:
                    if trade_status == 'upcoming':
                        parts.append(f"  {yr}: [UPCOMING - pattern has not started yet. Exclude from all statistics.]")
                    elif trade_status == 'active':
                        underlying, trade_return, _, _ = _year_values(y)
                        direction_label = "currently gaining" if trade_return > 0 else "currently losing" if trade_return < 0 else "currently flat"
                        parts.append(
                            f"  {yr}: underlying {underlying:+.2f}%; live {direction} trade "
                            f"{trade_return:+.2f}% [ACTIVE - {direction_label}. This updates daily "
                            "and is not final. Exclude it from historical statistics.]"
                        )
                    else:
                        parts.append(_completed_year_line(yr, y))
                else:
                    parts.append(_completed_year_line(yr, y))
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
                         f"({visible_count} rows shown in the current on-screen Sort by order). These ARE the rows the "
                         f"user is looking at right now. For a 'which {opp_table_market_name} / matching-group stocks' "
                         f"question, answer by naming the TOP rows from this list - it is the on-screen truth.")
        else:
            parts.append(f"\n<b>Opportunity Table</b> ({visible_count} rows shown in the current on-screen Sort by order):")
        if needs_opportunity_rows(user_message):
            parts.append("Date | Symbol | Days | Direction | Avg Profit | Sharpe Ratio")
            for o in opportunities[:12]:  # enough to answer a top-5/rank question without a 30-row dump
                direction = "Long" if str(o.get("direction", "")).upper() in ("L", "LONG") else "Short"
                parts.append(
                    f"{o.get('date','?')} | {o.get('symbol','?')} | {o.get('days_out','?')} days | "
                    f"{direction} | {o.get('avg_profit','?')}% | SR {o.get('sharpe_ratio','?')}"
                )
        # Deterministic rank of the loaded pattern, so Tara never MISCOUNTS its table position
        # when asked "why/where does this rank" (LLMs count list positions unreliably - she said
        # #5 for a row that is #4). The passed order IS the current on-screen Sort by order, so the
        # 1-based index is the visible rank. Hand her the exact number; tell her to use it, not recount.
        loaded_sym = str(wave_viewer.get("symbol", "")).upper()
        if loaded_sym:
            for i, o in enumerate(opportunities):
                if str(o.get("symbol", "")).upper() == loaded_sym:
                    parts.append(
                        f"LOADED-PATTERN RANK: {loaded_sym} is #{i + 1} in the table's current on-screen "
                        f"Sort by order. If asked where or why it ranks, use #{i + 1} EXACTLY - do not "
                        "recount the rows or assume Sharpe is the active sort field."
                    )
                    break
    else:
        parts.append("\n<b>Opportunity Table:</b> Empty or not loaded.")

    if analysis_report:
        report_context = analysis_report.get('context', {})
        parts.append("\n<b>ACTIVE VALIDATED ANALYSIS REPORT</b>")
        parts.append(
            "REPORT CONTRACT (OVERRIDES ORDINARY COMPARISON/VIEW RULES): Explain only this supplied "
            "report snapshot. Do not call tools, fetch symbols, recalculate metrics, re-rank rows, or "
            "change/load the Wave Viewer. All numbers below came from confirmed TradeWave chart responses. "
            "Use the deterministic findings when naming a leader. Write for a 10th-grade reader in 3-6 "
            "short sentences or at most 4 short bullets. Say 'historically stronger', never predict a future "
            "winner. Mention a shortened common-history adjustment when history_adjusted is true."
        )
        parts.append(
            f"Report: {analysis_report.get('title', '')} | id={analysis_report.get('report_id', '')} | "
            f"type={analysis_report.get('report_type', '')} | generated={analysis_report.get('generated_at', '')}"
        )
        parts.append(
            "Context: " + json.dumps(report_context, sort_keys=True, separators=(',', ':'))
        )
        if analysis_report.get('report_type') == 'range_comparison':
            range_rows = {row.get('role'): row for row in analysis_report.get('rows', [])}
            model_cumulative = range_rows.get('remaining_range', {}).get('metrics', {}).get(
                'cumulative_return_pct'
            )
            buy_hold_cumulative = range_rows.get('buy_hold', {}).get('metrics', {}).get(
                'cumulative_return_pct'
            )
            if (
                isinstance(model_cumulative, (int, float))
                and isinstance(buy_hold_cumulative, (int, float))
                and model_cumulative >= -100
                and buy_hold_cumulative >= -100
            ):
                model_value = round(10000 * (1 + model_cumulative / 100))
                buy_hold_value = round(10000 * (1 + buy_hold_cumulative / 100))
                parts.append(
                    f"PRECALCULATED EDUCATION VALUES: A hypothetical $10,000 becomes ${model_value:,} "
                    f"under the Date Range Exclusion Model and ${buy_hold_value:,} under Buy & Hold. "
                    "Use these supplied values; do not recalculate them."
                )
            parts.append(
                "The Date Range Exclusion Model dates are the exact output of the longstanding Wave Viewer "
                "Reverse Date Range action. Never derive, adjust, or second-guess those dates. Every row is "
                "Long and shows the security's actual market return. The Excluded Date Range is supporting "
                "evidence, not a Short trade. The main comparison is Date Range Exclusion Model versus Buy "
                "& Hold. Explain this as historical research and education, not investment advice. Do not "
                "recommend entering or leaving the market."
            )
            parts.append(
                "RANGE EXCLUSION PLAIN-LANGUAGE CONTRACT: Never return a wall of text. For the initial report "
                "explanation, use these four HTML sections, each on its own line: <b>Bottom line</b>, "
                "<b>Why</b>, <b>Important</b>, and <b>Own the shares?</b>. Use <br><br> before each "
                "section after the first and <br> between each Why bullet. Do not use Markdown asterisks. "
                "Bottom line gets one short sentence answering "
                "whether excluding the user's selected dates historically improved the compounded result versus "                "Buy & Hold. Why gets at most two short bullets: first explain the Excluded Date Range using its "
                "average return and 'profitable in X of Y years'; second compare the Exclusion Model with Buy & "
                "Hold using cumulative return and the supplied hypothetical $10,000 values when present. Call the "
                "outside dates the 'remaining dates,' never the 'selected window'. Do not mention Sharpe ratio in "
                "this first explanation. Important gets one short sentence saying this is historical research, not "
                "a prediction or recommendation, and that it does not include taxes, trading costs, or practical "
                "re-entry. Own the shares? gets only this invitation: 'Ask me about covered calls and their risks "
                "during historically weak periods.' Do not explain options unless the user explicitly asks."
            )
            parts.append(
                "COVERED-CALL FOLLOW-UP CONTRACT: Only after the user explicitly asks about covered calls, use "
                "three short HTML sections, each on its own line: <b>How it works</b>, <b>Main risk</b>, and "
                "<b>Before considering it</b>. Use <br><br> between sections and do not use Markdown asterisks. "
                "Explain that some investors who already own the shares research a covered call "
                "to collect option premium. Explain that it limits upside and, if assigned, the shares are sold at "                "the strike price even if the stock keeps rising. State that this report does not test option "
                "premiums, strikes, expirations, assignment risk, taxes, costs, or suitability, and that the user "
                "should review suitability with a licensed financial professional who understands options. Never "
                "recommend a trade, strike, expiration, uncovered call, or claim the seasonal weakness will repeat."
            )
        elif analysis_report.get('report_type') == 'date_range_comparison':
            parts.append(
                "Every row is a Long historical study of the same symbol, and every date range plus "
                "Buy & Hold uses the same completed-year cohort. These are the exact user-selected "
                "ranges; this is not the Date Range Exclusion Model and no range may be derived or changed."
            )
            parts.append(
                "DATE RANGE COMPARISON PLAIN-LANGUAGE CONTRACT: Start with the date range that had "
                "the highest average historical return, naming its exact dates and average. Then say "
                "which range was profitable in the most years and compare each candidate range's worst "
                "historical result with Buy & Hold. Explain any shortened common-history cohort. Use "
                "'profitable in X of Y years,' not only a percentage. Do not call the highest average "
                "the safest, best investment, or expected winner; do not recommend entering, exiting, "
                "or allocating money. End by saying the comparison is historical, excludes taxes and "
                "trading costs, and is not a prediction or personal recommendation."
            )
        else:
            parts.append(
                "Every symbol in this report uses the same displayed date window, direction, and common "
                "historical cohort. The Wave Viewer itself was not changed when report history was shortened."
            )
            parts.append(
                "SYMBOL COMPARISON PLAIN-LANGUAGE CONTRACT: Make the tradeoff understandable on the first "
                "read. Start with which symbol had the highest average return, then separately say which "
                "symbol was profitable in the most years and which had the smaller average losses. Use the "
                "wording 'profitable in X of Y years' instead of giving only a percentage. Do not say "
                "'risk-adjusted performance' or 'drawdown'. Say 'returns were steadier compared with the risk "
                "taken' and 'losses during the period were smaller on average.' If you mention Sharpe ratio, "
                "immediately explain it in the same sentence: 'A higher Sharpe ratio means the historical "
                "returns were steadier compared with the amount of risk taken.' Do not call one result "
                "'stronger overall' unless that same sentence names the exact reasons. Make clear that the "
                "highest average return is not always the result that was profitable most often or had the "
                "smallest losses. End by saying these are historical results for the displayed date window, "
                "not a prediction. Prefer common words over financial labels."
            )
        for row in analysis_report.get('rows', []):
            parts.append(
                "REPORT ROW: " + json.dumps({
                    'role': row.get('role'),
                    'label': row.get('label'),
                    'symbol': row.get('symbol'),
                    'company': row.get('company'),
                    'start_date': row.get('start_date'),
                    'end_date': row.get('end_date'),
                    'direction': row.get('direction'),
                    'sample_years': row.get('sample_years'),
                    'metrics': row.get('metrics', {}),
                    'yearly_results': row.get('yearly_results', []),
                }, sort_keys=True, separators=(',', ':'))
            )


    # Append a compact, allowlisted fact ledger last so current UI state and direction semantics
    # have maximum recency and cannot be contradicted by stale conversation or generic KB prose.
    verified_lines = verified_context_lines(wave_viewer, screen_context)
    named_symbol = explicit_pattern_symbol(user_message)
    loaded_symbol = str(wave_viewer.get("symbol") or "").strip().upper()
    if named_symbol and loaded_symbol and named_symbol != loaded_symbol:
        viewer_year = datetime.datetime.now(datetime.timezone.utc).year
        verified_lines.append(
            f"- EXPLICIT NAMED-SYMBOL OVERRIDE: the user named {named_symbol}, while {loaded_symbol} "
            "is currently loaded. The named symbol overrides 'this', 'it', and the loaded screen. "
            f"Do not answer with or relabel {loaded_symbol}'s statistics. Call analyze_symbol for "
            f"{named_symbol}; reuse an exact entry date, inclusive calendar-day duration, direction, "
            "and lookback from recent conversation only when they are explicitly available. Then call "
            f"update_view with the verified {named_symbol} setup and answer only from {named_symbol} "
            f"facts. For a recurring setup, update_view must anchor the returned month/day to the "
            f"current {viewer_year} occurrence unless the user explicitly requested a historical year. "
            "If the named setup cannot be resolved, say so instead of substituting the loaded symbol."
        )
        current_years = str(wave_viewer.get("years") or "")
        requested_other_lookback = re.search(
            r"\b(?:max(?:imum)?|all|full)(?:\s+available)?\s+(?:years?|history)\b|"
            r"\b\d{1,2}\s*(?:-|\s)?years?\b",
            user_message,
            re.I,
        )
        current_cycle = str(wave_viewer.get("pe_cycle") or "cons").strip().lower()
        if (
            current_years.isdigit()
            and current_cycle in {"cons", "consecutive"}
            and not requested_other_lookback
        ):
            verified_lines.append(
                f"- LOOKBACK INHERITANCE: the viewer is set to {current_years} years and the "
                f"user did not request another lookback. Analyze and load {named_symbol} at "
                f"{current_years} years, not the default 10. If {named_symbol} has fewer "
                "completed observations, use and name its available maximum."
            )
    parts.append("\n" + "\n".join(verified_lines))

    knowledge = select_topic_knowledge(user_message, _KNOWLEDGE_SECTIONS)
    blocks = segmented_system_blocks(
        "\n".join(static_parts),
        knowledge.text,
        "\n".join(parts),
    )
    logging.info(
        "Tara prompt segments chars=%s knowledge_sections=%s yearly_rows=%s opportunity_rows=%s",
        prompt_segment_sizes(blocks),
        knowledge.headings,
        bool(yearly) and needs_yearly_results(user_message),
        bool(opportunities) and needs_opportunity_rows(user_message),
    )
    return blocks


# --- deterministic floor for the loaded-pattern STRENGTH question ----------------------------------
# Haiku (temp 0) occasionally punts an analytical "how strong is this window" with a bare
# "Pattern loaded on the chart." and NO stat. When that happens on a loaded pattern whose stats we
# already have, append the strength line straight from those loaded stats - NOT fabricated (the same
# numbers the prompt already had), confident historical framing, no disclaimer.
def _clean_analysis_report_shape(value):
    """Validate the immutable, API-backed report snapshot supplied by React."""
    if value in (None, {}):
        return None
    if not isinstance(value, dict):
        raise ValueError('invalid analysis report')

    report_type = value.get('report_type')
    if report_type not in {'symbol_comparison', 'range_comparison', 'date_range_comparison'}:
        raise ValueError('invalid analysis report type')
    report_id = value.get('report_id')
    if not isinstance(report_id, str) or not re.fullmatch(r'[A-Za-z0-9._:\-]{1,120}', report_id):
        raise ValueError('invalid analysis report id')

    def clean_text(raw, maximum=160):
        if not isinstance(raw, str):
            return ''
        return re.sub(r'[\r\n\t]+', ' ', raw).strip()[:maximum]

    def clean_date(raw):
        if not isinstance(raw, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            return ''
        try:
            datetime.datetime.strptime(raw, '%Y-%m-%d')
        except ValueError:
            return ''
        return raw

    def clean_number(raw, low=-1000000, high=1000000):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        value_number = float(raw)
        if not math.isfinite(value_number) or not low <= value_number <= high:
            return None
        return value_number

    context_in = value.get('context')
    if not isinstance(context_in, dict):
        raise ValueError('invalid analysis report context')
    context = {}
    for key in ('baseline_symbol', 'symbol'):
        symbol = context_in.get(key)
        if isinstance(symbol, str) and re.fullmatch(r'[A-Za-z0-9.\-]{1,15}', symbol):
            context[key] = symbol.upper()
    for key in ('start_date', 'end_date'):
        date_value = clean_date(context_in.get(key))
        if date_value:
            context[key] = date_value
    for key, low, high in (
        ('days_out', 1, 367),
        ('requested_years', 1, 99),
        ('years_used', 1, 99),
        ('cut_off_year', 0, 2200),
        ('range_count', 1, 3),
    ):
        raw = context_in.get(key)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(raw, bool) and low <= parsed <= high:
            context[key] = parsed
    pe_cycle = context_in.get('pe_cycle')
    if pe_cycle in {'cons', 'pe0', 'pe1', 'pe2', 'pe3'}:
        context['pe_cycle'] = pe_cycle
    direction = context_in.get('direction')
    if direction in {'long', 'short'}:
        context['direction'] = direction
    context['history_adjusted'] = context_in.get('history_adjusted') is True
    context['history_adjustment_approved'] = context_in.get('history_adjustment_approved') is True
    # Date-range comparisons must use the intersection of completed years for
    # every window. That cohort alignment is deterministic and displayed in
    # the report; unlike substituting a shorter symbol history, it is not an
    # optional user override masquerading as the requested sample.
    if (
        report_type != 'date_range_comparison'
        and context['history_adjusted']
        and not context['history_adjustment_approved']
    ):
        raise ValueError('unapproved history adjustment')
    context['includes_buy_hold'] = context_in.get('includes_buy_hold') is True
    common_years = context_in.get('common_years')
    if isinstance(common_years, list):
        clean_years = sorted({
            int(year) for year in common_years
            if isinstance(year, (int, float)) and not isinstance(year, bool) and 1900 <= int(year) <= 2200
        })
        context['common_years'] = clean_years[:99]
    availability = context_in.get('history_availability')
    if isinstance(availability, list):
        clean_availability = []
        for item in availability[:4]:
            if not isinstance(item, dict):
                continue
            symbol = item.get('symbol')
            years = item.get('years')
            if (
                isinstance(symbol, str)
                and re.fullmatch(r'[A-Za-z0-9.\-]{1,15}', symbol)
                and isinstance(years, (int, float))
                and not isinstance(years, bool)
                and 0 <= int(years) <= 200
            ):
                clean_availability.append({'symbol': symbol.upper(), 'years': int(years)})
        context['history_availability'] = clean_availability
    reverse_source = context_in.get('reverse_source')
    if reverse_source == 'wave_viewer_legacy_reverse_date_range':
        context['reverse_source'] = reverse_source

    allowed_finding_keys = {
        'highest_average_return', 'highest_profitable_rate',
        'highest_sharpe_ratio', 'smallest_average_mae',
    }
    findings = context_in.get('findings')
    if isinstance(findings, dict):
        clean_findings = {}
        for key in allowed_finding_keys:
            symbols = findings.get(key)
            if not isinstance(symbols, list):
                continue
            clean_symbols = [
                symbol.upper() for symbol in symbols[:4]
                if isinstance(symbol, str) and re.fullmatch(r'[A-Za-z0-9.\-]{1,15}', symbol)
            ]
            if clean_symbols:
                clean_findings[key] = clean_symbols
        context['findings'] = clean_findings

    allowed_metrics = {
        'average_return_pct', 'median_return_pct', 'profitable_pct',
        'best_return_pct', 'worst_return_pct', 'average_mfe_pct',
        'average_mae_pct', 'sharpe_ratio', 'cumulative_return_pct',
        'annualized_return_pct', 'winners', 'losers',
    }
    if report_type == 'symbol_comparison':
        allowed_roles = {'baseline', 'comparison'}
    elif report_type == 'range_comparison':
        allowed_roles = {'selected_range', 'remaining_range', 'buy_hold'}
    else:
        allowed_roles = {'date_range', 'buy_hold'}
    rows_in = value.get('rows')
    if not isinstance(rows_in, list) or not 2 <= len(rows_in) <= 4:
        raise ValueError('invalid analysis report rows')
    rows = []
    for item in rows_in:
        if not isinstance(item, dict) or item.get('role') not in allowed_roles:
            raise ValueError('invalid analysis report row')
        symbol = item.get('symbol')
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Za-z0-9.\-]{1,15}', symbol):
            raise ValueError('invalid report symbol')
        row = {
            'role': item['role'],
            'label': clean_text(item.get('label'), 80),
            'symbol': symbol.upper(),
            'company': clean_text(item.get('company'), 120),
            'market': clean_text(str(item.get('market', '')), 10),
            'market_label': clean_text(item.get('market_label'), 120),
            'direction': item.get('direction') if item.get('direction') in {'long', 'short'} else 'long',
        }
        for key in ('start_date', 'end_date'):
            date_value = clean_date(item.get(key))
            if date_value:
                row[key] = date_value
        try:
            sample_years = int(item.get('sample_years'))
        except (TypeError, ValueError):
            sample_years = 0
        if 1 <= sample_years <= 99:
            row['sample_years'] = sample_years

        metrics_in = item.get('metrics')
        if not isinstance(metrics_in, dict):
            raise ValueError('invalid report metrics')
        metrics = {}
        for key in allowed_metrics:
            number = clean_number(metrics_in.get(key))
            if number is not None:
                metrics[key] = number
        row['metrics'] = metrics

        yearly_in = item.get('yearly_results')
        yearly = []
        if isinstance(yearly_in, list):
            for result in yearly_in[:99]:
                if not isinstance(result, dict):
                    continue
                year = result.get('year')
                return_pct = clean_number(result.get('return_pct'))
                if not isinstance(year, (int, float)) or isinstance(year, bool) or return_pct is None:
                    continue
                clean_result = {'year': int(year), 'return_pct': return_pct}
                for key in ('mfe_pct', 'mae_pct'):
                    number = clean_number(result.get(key))
                    if number is not None:
                        clean_result[key] = number
                yearly.append(clean_result)
        row['yearly_results'] = yearly
        rows.append(row)

    roles = [row['role'] for row in rows]
    if report_type == 'symbol_comparison':
        if roles[0] != 'baseline' or not all(role == 'comparison' for role in roles[1:]):
            raise ValueError('invalid symbol comparison roles')
    elif report_type == 'range_comparison' and set(roles) != {
        'selected_range', 'remaining_range', 'buy_hold'
    }:
        raise ValueError('invalid range comparison roles')
    elif report_type == 'date_range_comparison' and (
        roles[-1:] != ['buy_hold']
        or not all(role == 'date_range' for role in roles[:-1])
    ):
        raise ValueError('invalid date range comparison roles')

    if report_type == 'symbol_comparison' and context.get('years_used') and context.get('common_years'):
        if len(context['common_years']) < context['years_used']:
            raise ValueError('incomplete common history')

    return {
        'schema_version': 1,
        'report_id': report_id,
        'report_type': report_type,
        'title': clean_text(value.get('title'), 160),
        'generated_at': clean_text(value.get('generated_at'), 40),
        'context': context,
        'rows': rows,
    }


def _clean_analysis_report(value):
    """Strictly validate cross-field report truth before calling it validated."""
    if value in (None, {}):
        return None
    if not isinstance(value, dict) or value.get('schema_version') != 1:
        raise ValueError('invalid analysis report schema')
    try:
        report = _clean_analysis_report_shape(value)
    except (OverflowError, TypeError) as exc:
        raise ValueError('invalid analysis report') from exc
    if report is None:
        return None

    generated_at = report.get('generated_at', '')
    try:
        datetime.datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        generated_at = ''
    report['generated_at'] = generated_at

    report_type = report['report_type']
    context = report['context']
    rows = report['rows']
    required_metrics = {
        'average_return_pct', 'median_return_pct', 'profitable_pct',
        'best_return_pct', 'worst_return_pct', 'average_mfe_pct',
        'average_mae_pct', 'sharpe_ratio', 'cumulative_return_pct',
        'annualized_return_pct', 'winners', 'losers',
    }
    required_context = {
        'requested_years', 'years_used', 'pe_cycle', 'cut_off_year', 'common_years',
    }
    if report_type != 'date_range_comparison':
        required_context.update({'start_date', 'end_date'})
    if not required_context.issubset(context):
        raise ValueError('incomplete analysis report context')
    requested_years = context['requested_years']
    years_used = context['years_used']
    common_years = context['common_years']
    if years_used > requested_years or len(common_years) != years_used:
        raise ValueError('invalid report history')
    if context.get('history_adjusted'):
        if years_used >= requested_years:
            raise ValueError('invalid history adjustment')
        if (
            report_type != 'date_range_comparison'
            and not context.get('history_adjustment_approved')
        ):
            raise ValueError('invalid history adjustment')
    elif years_used != requested_years:
        raise ValueError('unreported history adjustment')

    symbols = [row['symbol'] for row in rows]
    if len(set(symbols)) != len(symbols) and report_type == 'symbol_comparison':
        raise ValueError('duplicate report symbols')
    expected_years = list(common_years)
    for row in rows:
        if not required_metrics.issubset(row.get('metrics', {})):
            raise ValueError('incomplete report metrics')
        if row.get('sample_years') != years_used:
            raise ValueError('mismatched report sample')
        row_years = sorted(result.get('year') for result in row.get('yearly_results', []))
        if row_years != expected_years or len(set(row_years)) != len(row_years):
            raise ValueError('mismatched report cohort')
        metrics = row['metrics']
        winners = metrics.get('winners')
        losers = metrics.get('losers')
        if (
            winners < 0
            or losers < 0
            or int(winners) != winners
            or int(losers) != losers
            or int(winners + losers) != years_used
        ):
            raise ValueError('invalid profitable-year counts')
        # Company and market labels are UI-only. Do not elevate arbitrary
        # client text into Tara's system prompt.
        row['company'] = row['symbol']
        row['market_label'] = ''

    if report_type == 'symbol_comparison':
        required_symbol_context = {'baseline_symbol', 'direction'}
        if not required_symbol_context.issubset(context):
            raise ValueError('incomplete symbol comparison context')
        if rows[0]['symbol'] != context['baseline_symbol']:
            raise ValueError('invalid baseline symbol')
        for index, row in enumerate(rows):
            if row.get('start_date') != context['start_date'] or row.get('end_date') != context['end_date']:
                raise ValueError('mismatched comparison dates')
            if row.get('direction') != context['direction']:
                raise ValueError('mismatched comparison direction')
            row['label'] = f"{row['symbol']} (Current)" if index == 0 else row['symbol']
        if len(rows) < 2 or len(rows) > 4:
            raise ValueError('invalid symbol report size')
        availability = context.get('history_availability')
        if (
            not isinstance(availability, list)
            or len(availability) != len(rows)
            or [item.get('symbol') for item in availability] != symbols
            or any(item.get('years', 0) < years_used for item in availability)
        ):
            raise ValueError('invalid history availability')
        report['title'] = f"{context['baseline_symbol']} Symbol Comparison"
    elif report_type == 'range_comparison':
        if len(rows) != 3:
            raise ValueError('invalid range report size')
        if context.get('reverse_source') != 'wave_viewer_legacy_reverse_date_range':
            raise ValueError('invalid outside-range source')
        range_symbol = context.get('symbol')
        if not range_symbol or any(row['symbol'] != range_symbol for row in rows):
            raise ValueError('mismatched range symbol')
        expected_roles = ['selected_range', 'remaining_range', 'buy_hold']
        if [row['role'] for row in rows] != expected_roles:
            raise ValueError('invalid range comparison order')
        if rows[0].get('start_date') != context['start_date'] or rows[0].get('end_date') != context['end_date']:
            raise ValueError('mismatched selected range')
        if any(row.get('direction') != 'long' for row in rows):
            raise ValueError('invalid range report direction')
        labels = ['Excluded Date Range', 'Date Range Exclusion Model', 'Buy & Hold']
        for row, label in zip(rows, labels):
            if not row.get('start_date') or not row.get('end_date'):
                raise ValueError('missing range dates')
            row['label'] = label
        report['title'] = 'Date Range Exclusion Report'
    else:
        if not 2 <= len(rows) <= 4:
            raise ValueError('invalid date range report size')
        range_symbol = context.get('symbol')
        if not range_symbol or any(row['symbol'] != range_symbol for row in rows):
            raise ValueError('mismatched date range symbol')
        if context.get('direction') != 'long' or any(row.get('direction') != 'long' for row in rows):
            raise ValueError('invalid date range direction')
        if not context.get('includes_buy_hold'):
            raise ValueError('missing buy and hold reference')
        if context.get('range_count') != len(rows) - 1:
            raise ValueError('invalid date range count')
        if [row['role'] for row in rows] != (['date_range'] * (len(rows) - 1) + ['buy_hold']):
            raise ValueError('invalid date range comparison order')
        seen_ranges = set()
        for index, row in enumerate(rows[:-1], start=1):
            start = row.get('start_date')
            end = row.get('end_date')
            if not start or not end or start > end or (start, end) in seen_ranges:
                raise ValueError('invalid comparison date range')
            seen_ranges.add((start, end))
            row['label'] = f'Date Range {index}'
        buy_hold = rows[-1]
        try:
            buy_start = datetime.datetime.strptime(buy_hold.get('start_date', ''), '%Y-%m-%d').date()
            buy_end = datetime.datetime.strptime(buy_hold.get('end_date', ''), '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError('invalid buy and hold range') from exc
        if (
            buy_start.month != 1 or buy_start.day != 1
            or buy_end.month != 1 or buy_end.day != 1
            or buy_end.year != buy_start.year + 1
        ):
            raise ValueError('invalid buy and hold range')
        buy_hold['label'] = 'Buy & Hold'
        report['title'] = f"{range_symbol} Date Range Comparison"

    # Rebuild deterministic leaders from validated metrics instead of trusting
    # client-provided rankings.
    findings = {}
    for finding_key, metric_key in (
        ('highest_average_return', 'average_return_pct'),
        ('highest_profitable_rate', 'profitable_pct'),
        ('highest_sharpe_ratio', 'sharpe_ratio'),
        ('smallest_average_mae', 'average_mae_pct'),
    ):
        values = [row['metrics'][metric_key] for row in rows]
        target = max(values)
        findings[finding_key] = [
            (row['label'] if report_type == 'date_range_comparison' else row['symbol'])
            for row in rows if row['metrics'][metric_key] == target
        ]
    context['findings'] = findings
    return report



_STRENGTH_Q = re.compile(r'\bhow\s+(?:strong|good|reliable|solid)\b|\bstrength\b|\bhow\s+did\s+(?:it|this)\b|\bis\s+(?:it|this)\s+(?:strong|good|reliable)\b', re.I)
_REPLY_HAS_STAT = re.compile(r'\d{1,3}\s*%|\bwon\s+\d+|\d+\s+of\s+\d+|sharpe[^\d]{0,12}\d', re.I)


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
        avg = str(stats.get("Avg Profit") or "").strip()
        facts = canonical_pattern_facts(wv)
        wins = int(facts.get("profitable_years") or 0)
        tot = int(facts.get("sample_size") or 0)
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


def _loaded_full_history_request(years, wave_viewer, market):
    """Build the exact loaded-window override used for a full-history tool turn.

    The model still chooses and narrates the tools, but it cannot turn "max" into the
    API ceiling (99) or silently analyze a different same-symbol setup.  Reuse the
    established ViewSpec validator for the user-supplied screen fields before they are
    forwarded to the provider-neutral tool executor.
    """

    wv = wave_viewer if isinstance(wave_viewer, dict) else {}
    try:
        days_out = int(str(wv.get("days_out")))
    except (TypeError, ValueError):
        days_out = None
    cleaned = _validate_view_spec({
        "symbol": wv.get("symbol"),
        "market": wv.get("market") if wv.get("market") not in (None, "") else market,
        "entry_date": wv.get("start_date"),
        "days_out": days_out,
        "years": years,
    })
    request_spec = {"years": years}
    for field in ("symbol", "market", "entry_date", "days_out"):
        if field in cleaned:
            request_spec[field] = cleaned[field]
    direction = str(wv.get("direction") or "").strip().lower()
    if direction in ("long", "short"):
        request_spec["direction"] = direction
    # requested_full_history_years only resolves consecutive-mode commands.
    request_spec["pe_cycle"] = "consecutive"
    return request_spec


def _clean_chat_history(value):
    if not isinstance(value, list) or len(value) > 24:
        raise ValueError('invalid history')
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('invalid history')
        role = item.get('role')
        content = item.get('content')
        if role not in ('user', 'assistant') or not isinstance(content, str):
            raise ValueError('invalid history')
        out.append({'role': role, 'content': content[:4000]})
    return out


def _clean_wave_viewer(value):
    if not isinstance(value, dict):
        raise ValueError('invalid wave viewer')
    out = {}
    for key in ('company', 'direction', 'view_request_key'):
        raw = value.get(key)
        if isinstance(raw, str):
            out[key] = raw[:200]
    symbol = value.get('symbol')
    if isinstance(symbol, str) and re.fullmatch(r'[A-Za-z0-9.\-]{0,15}', symbol):
        out['symbol'] = symbol.upper()
    market = value.get('market')
    if market is not None and str(market) in {str(i) for i in range(17) if i not in (14, 15)}:
        out['market'] = str(market)
    for key in ('start_date', 'entry_date'):
        raw = value.get(key)
        if isinstance(raw, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            try:
                datetime.datetime.strptime(raw, '%Y-%m-%d')
                out[key] = raw
            except ValueError:
                pass
    for key, low, high in (('days_out', 1, 367), ('years', 1, 99)):
        raw = value.get(key)
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(raw, bool) and low <= parsed <= high:
            out[key] = parsed
    pe = value.get('pe_cycle')
    if pe in {'cons', 'pe0', 'pe1', 'pe2', 'pe3'}:
        out['pe_cycle'] = pe
    out['view_ready'] = value.get('view_ready') is True
    out['mae_enabled'] = value.get('mae_enabled') is True
    last_price = value.get('last_price')
    if isinstance(last_price, (int, float, str)) and not isinstance(last_price, bool):
        out['last_price'] = str(last_price)[:40]

    stats = value.get('stats')
    if isinstance(stats, dict):
        clean_stats = {}
        for key, raw in list(stats.items())[:40]:
            if not isinstance(key, str) or not isinstance(raw, (str, int, float, bool)):
                continue
            clean_stats[key[:80]] = raw if not isinstance(raw, str) else raw[:200]
        if clean_stats:
            out['stats'] = clean_stats

    yearly = value.get('yearly_results')
    if isinstance(yearly, list):
        clean_yearly = []
        for row in yearly[:99]:
            if not isinstance(row, dict):
                continue
            clean_row = {}
            for key in (
                'year', 'return_pct', 'underlying_return_pct', 'raw_return_pct',
                'mfe_pct', 'mae_pct', 'upside_excursion_pct', 'downside_excursion_pct',
            ):
                raw = row.get(key)
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    clean_row[key] = raw
            if 'year' in clean_row and any(
                key in clean_row
                for key in ('return_pct', 'underlying_return_pct', 'raw_return_pct')
            ):
                clean_yearly.append(clean_row)
        if clean_yearly:
            out['yearly_results'] = clean_yearly
    return out


def _clean_opportunities(value):
    if not isinstance(value, list):
        raise ValueError('invalid opportunities')
    allowed = {
        'date', 'symbol', 'days_out', 'direction', 'avg_profit', 'sharpe_ratio',
    }
    out = []
    for row in value[:50]:
        if not isinstance(row, dict):
            continue
        clean = {}
        for key in allowed:
            raw = row.get(key)
            if isinstance(raw, (str, int, float)) and not isinstance(raw, bool):
                clean[key] = raw if not isinstance(raw, str) else raw[:80]
        if clean:
            out.append(clean)
    return out


def _validation_audit_question(incoming_data):
    """Return a bounded, non-structural question label for rejected payloads."""
    if not isinstance(incoming_data, dict):
        return '[invalid request body]'
    value = incoming_data.get('message')
    if isinstance(value, str):
        return value[:2000]
    if value is None:
        return ''
    return '[invalid message type: %s]' % type(value).__name__


def _rejected_chat_response(user_id, turn_id, incoming_data, reply, reason):
    """Audit an authenticated rejected turn without retaining unsafe context."""
    _write_question_audit(
        user_id,
        _validation_audit_question(incoming_data),
        reply,
        {},
        turn_id=turn_id,
        actions=[],
        protocol_trace=[{
            'event': 'validation_failure',
            'reason': reason,
        }],
    )
    return jsonify({
        'reply': reply,
        'actions': [],
        'turn_id': turn_id,
    }), 400



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
    # Allocate the authenticated identity and correlation id before body
    # validation so rejected turns are still observable in the audit.
    from flask import g
    user_id = getattr(g, 'chatbot_user_id', 'unknown')
    turn_id = uuid.uuid4().hex
    protocol_trace = []
    actions = []

    incoming_data = request.get_json(silent=True)
    if not isinstance(incoming_data, dict):
        return _rejected_chat_response(
            user_id, turn_id, incoming_data,
            "I couldn't read that request. Please try again.",
            'invalid_request_body',
        )
    user_message = incoming_data.get("message", "")
    if not isinstance(user_message, str) or len(user_message) > 2000:
        return _rejected_chat_response(
            user_id, turn_id, incoming_data,
            "That message could not be processed. Please shorten it and try again.",
            'invalid_message',
        )
    try:
        history = _clean_chat_history(incoming_data.get("history", []))
        wave_viewer = _clean_wave_viewer(incoming_data.get("wave_viewer", {}))
        opportunities = _clean_opportunities(incoming_data.get("opportunities", []))
        analysis_report = _clean_analysis_report(incoming_data.get("analysis_report"))
    except ValueError:
        return _rejected_chat_response(
            user_id, turn_id, incoming_data,
            "I couldn't validate that request. Please try again.",
            'invalid_context',
        )
    # AI analysis is server-derived. Never accept model scores supplied by the browser,
    # an old tab, or a modified request as verified current-condition evidence.
    wave_viewer.pop("ai_analysis", None)
    screen_context = incoming_data.get("screen_context", {})
    if not isinstance(screen_context, dict):
        screen_context = {}
    opp_table_length = incoming_data.get("opp_table_length")
    if not isinstance(opp_table_length, int) or isinstance(opp_table_length, bool):
        opp_table_length = None
    elif not 0 <= opp_table_length <= 10000:
        opp_table_length = None
    # The market/group the opportunity table is currently showing - lets Tara answer a
    # "which <group> stocks" question FROM the on-screen rows (exact match) when the table is
    # already on that group, instead of an independent scan that diverges from the table.
    opp_table_market = incoming_data.get("opp_table_market")
    opp_table_market_name = incoming_data.get("opp_table_market_name")
    opp_table_years = incoming_data.get("opp_table_years")   # table lookback, for a cross-market OppList4 screen
    opp_table_pe_cycle = incoming_data.get("opp_table_pe_cycle")
    user_token = incoming_data.get("token")                  # user's LTK - reused for the loopback OppList4 fetch
    if str(opp_table_market) not in {str(i) for i in range(17) if i not in (14, 15)}:
        opp_table_market = None
    else:
        opp_table_market = str(opp_table_market)
    if not isinstance(opp_table_market_name, str):
        opp_table_market_name = None
    else:
        opp_table_market_name = opp_table_market_name[:120]
    try:
        opp_table_years = int(opp_table_years)
    except (TypeError, ValueError):
        opp_table_years = None
    if opp_table_years is not None and not 1 <= opp_table_years <= 99:
        opp_table_years = None
    if not isinstance(opp_table_pe_cycle, str):
        opp_table_pe_cycle = None
    elif opp_table_pe_cycle not in {'cons', 'pe0', 'pe1', 'pe2', 'pe3'}:
        opp_table_pe_cycle = None
    if not isinstance(user_token, str) or len(user_token) > 4096:
        user_token = None

    # Blank-message guard: an empty message must never dead-end on the generic 500
    # envelope; return a warm, concrete nudge instead. (Tara-peak loop, 2026-06-21)
    if not (user_message or "").strip():
        blank_reply = (
            "Hi, I'm Tara. Want today's AI pick, a quick market scan, "
            "or a specific symbol loaded?"
        )
        return _finalize_chat_response(
            user_id,
            turn_id,
            user_message,
            blank_reply,
            wave_viewer,
            actions=[],
            messages_or_text=user_message,
            protocol_trace=[{'event': 'blank_message'}],
            provider='deterministic',
        )

    if analysis_report is not None:
        try:
            report_prompt = build_system_prompt(
                wave_viewer,
                opportunities,
                opp_table_length,
                opp_table_market,
                opp_table_market_name,
                screen_context,
                user_message=user_message,
                analysis_report=analysis_report,
            )
            report_override = (
                "FINAL REPORT OVERRIDE: answer from ACTIVE VALIDATED ANALYSIS REPORT only. "
                "Return no actions and make no claim that the Wave Viewer changed."
            )
            if isinstance(report_prompt, list):
                report_prompt = list(report_prompt) + [{"type": "text", "text": report_override}]
            else:
                report_prompt += "\n\n" + report_override
            messages = []
            if isinstance(history, list):
                for item in history[:-1]:
                    if not isinstance(item, dict):
                        continue
                    role = "assistant" if item.get("role") == "assistant" else "user"
                    content = item.get("content")
                    if isinstance(content, str):
                        messages.append({"role": role, "content": content})
            messages.append({"role": "user", "content": user_message})
            provider = select_tara_provider()
            try:
                bot_reply = send_openai_messages(
                    messages,
                    model=OPENAI_CHATBOT_MODEL,
                    system=report_prompt,
                    user_id=user_id,
                )
            except OpenAIConfigurationError:
                raise
            except Exception:
                provider = "anthropic_fallback"
                bot_reply = send_claude_messages(
                    messages,
                    model=CHATBOT_MODEL,
                    system=report_prompt,
                    cache_system=True,
                    cache_ttl=CACHE_TTL,
                )
            investor_intent = classify_investor_intent(messages)
            if response_violates_investor_contract(bot_reply, investor_intent):
                bot_reply = (
                    "TradeWave cannot determine which security is suitable for you. I can explain "
                    "this validated historical report, including losing years and limitations, but "
                    "not give a personal buy, sell, hold, allocation, or return forecast."
                )
            if response_violates_view_contract(bot_reply, actions=[], current_view=wave_viewer):
                bot_reply = (
                    "I couldn't explain this report safely without implying that I changed the chart. "
                    "Please select Explain with Tara again."
                )
            return _finalize_chat_response(
                user_id,
                turn_id,
                user_message,
                bot_reply,
                wave_viewer,
                actions=[],
                messages_or_text=messages,
                protocol_trace=[{
                    'event': 'analysis_report_explanation',
                    'report_id': analysis_report.get('report_id'),
                    'report_type': analysis_report.get('report_type'),
                }],
                provider=provider,
                analysis_report=analysis_report,
            )
        except Exception:
            logging.exception("chatbot report explanation failed for user_id=%s", user_id)
            safe_reply = "Sorry, I couldn't explain that report right now. Please try again."
            _write_question_audit(
                user_id,
                user_message,
                safe_reply,
                wave_viewer,
                turn_id=turn_id,
                actions=[],
                protocol_trace=[{'event': 'backend_exception', 'reason': 'report_turn_failed'}],
                provider='error',
            )
            return jsonify({
                'reply': safe_reply,
                'actions': [],
                'suggestions': guided_next_questions(
                    user_message,
                    reply=safe_reply,
                    current_view=wave_viewer,
                    analysis_report=analysis_report,
                ),
                'turn_id': turn_id,
            })

    try:
        def finish(reply, response_actions=None, provider='deterministic',
                   messages_or_text=None):
            return _finalize_chat_response(
                user_id,
                turn_id,
                user_message,
                reply,
                wave_viewer,
                actions=response_actions or [],
                messages_or_text=(
                    messages_or_text if messages_or_text is not None else user_message
                ),
                protocol_trace=protocol_trace,
                provider=provider,
                analysis_report=analysis_report,
            )

        investor_messages = [
            {
                'role': 'assistant' if item.get('role') == 'assistant' else 'user',
                'content': item.get('content', ''),
            }
            for item in history[:-1]
        ]
        investor_messages.append({'role': 'user', 'content': user_message})
        investor_intent = classify_investor_intent(investor_messages)
        suitability_reply = loaded_pattern_suitability_response(user_message, wave_viewer)
        if suitability_reply:
            protocol_trace.append({
                'event': 'loaded_pattern_suitability_boundary',
                'symbol': str(wave_viewer.get('symbol') or '').upper(),
            })
            return finish(
                suitability_reply,
                [],
                messages_or_text=investor_messages,
            )
        guidance_reply = investor_guidance_response(investor_intent)
        if guidance_reply:
            protocol_trace.append({'event': 'investor_guidance', 'intent': investor_intent})
            return finish(
                guidance_reply,
                [],
                messages_or_text=investor_messages,
            )
        view_intent = classify_view_intent(user_message)
        if view_intent == 'unsupported_live':
            protocol_trace.append({'event': 'capability_boundary', 'intent': view_intent})
            return finish(
                unsupported_live_data_response(),
                [],
                messages_or_text=investor_messages,
            )
        gateway_owned_intents = {
            'seasonal_etf', 'seasonal_stock', 'weak_etf', 'weak_stock',
            'weak_symbol', 'exclusion_study', 'named_security',
        }

        # Resolve the public book/signature pattern before provider routing so every
        # model and subscription tier receives the same exact load parameters.
        hundred_year_command = build_hundred_year_pattern_command(user_message)
        if hundred_year_command is not None:
            cleaned = _validate_view_spec(hundred_year_command.get("spec"))
            required = {
                "market",
                "symbol",
                "entry_date",
                "days_out",
                "years",
                "pe_cycle",
            }
            actions = []
            if required.issubset(cleaned):
                actions.append({"type": "set_view", "spec": cleaned})
            reply = hundred_year_command["reply"]
            return finish(reply, actions)

        # Ordinal table commands are exact UI actions, not language-model decisions. Resolve
        # them from the filtered/sorted visible rows supplied by the browser so "load the 3rd
        # one" cannot count the wrong list, forget the current market, or punt after a refresh.
        row_command = build_opportunity_row_load_command(
            user_message,
            opportunities,
            market=opp_table_market,
            pe_cycle=opp_table_pe_cycle,
        )
        if row_command is not None:
            actions = []
            cleaned = _validate_view_spec(row_command.get("spec"))
            required = {"symbol", "entry_date", "days_out"}
            if required.issubset(cleaned):
                actions.append({
                    "type": "load_opportunity",
                    "rank": row_command["rank"],
                    "spec": cleaned,
                })
            reply = row_command["reply"]
            return finish(reply, actions)

        # A discovery request must use the exact filtered/sorted rows on screen.
        # The visible table's first row is its highest-ranked row, so no model can
        # substitute a historical or off-screen candidate.
        table_pick = None
        if investor_intent not in gateway_owned_intents:
            table_pick = build_current_table_pick_command(
                user_message,
                opportunities,
                market=opp_table_market,
                pe_cycle=opp_table_pe_cycle,
            )
        if table_pick is not None:
            actions = []
            cleaned = _validate_view_spec(table_pick.get("spec"))
            required = {"symbol", "entry_date", "days_out"}
            if required.issubset(cleaned):
                actions.append({
                    "type": "load_opportunity",
                    "rank": table_pick["rank"],
                    "spec": cleaned,
                })
            reply = table_pick["reply"]
            return finish(reply, actions)

        # Tooltip preference language has a direct, reversible UI meaning. Confusion about
        # controls enables the guidance; annoyance with the guidance disables it. Tara also
        # names the visible switch so the user learns how to change the setting later.
        tooltip_command = build_tooltip_preference_command(user_message)
        if tooltip_command is not None:
            cleaned = _validate_view_spec(tooltip_command.get("spec"))
            if cleaned:
                reply = tooltip_command["reply"]
                actions = [{"type": "set_view", "spec": cleaned}]
                return finish(reply, actions)

        # Lower-panel navigation is exact UI state, not an analytical/model decision. Move
        # the desktop carousel immediately for direct commands such as "show me the stats"
        # instead of answering with a swipe instruction that leaves the screen unchanged.
        bottom_slide_command = build_bottom_slide_command(user_message)
        if bottom_slide_command is not None:
            cleaned = _validate_view_spec(bottom_slide_command.get("spec"))
            if cleaned:
                ai_scores_unavailable = (
                    cleaned.get("bottom_slide") == "ai_scores"
                    and not normalize_screen_context(screen_context).get("ai_scores_available")
                )
                if ai_scores_unavailable:
                    reply = (
                        "<b>AI Scores are not available in this view.</b> "
                        "They appear for eligible accounts on supported US stocks and ETFs."
                    )
                    actions = []
                else:
                    reply = bottom_slide_command["reply"]
                    actions = [{"type": "set_view", "spec": cleaned}]
                return finish(reply, actions)

        # A direct show/hide request for MFE/MAE is a reversible chart command, not a
        # definition request or a request for sample extrema. Keep it provider-independent
        # so the overlay is changed reliably and no education popup obscures the chart.
        excursion_command = build_excursion_overlay_command(user_message, wave_viewer)
        if excursion_command is not None:
            cleaned = _validate_view_spec(excursion_command.get("spec"))
            if cleaned:
                reply = excursion_command["reply"]
                actions = [{"type": "set_view", "spec": cleaned}]
                return finish(reply, actions)

        # Historical chart facts are already in the viewer payload. For a true pattern
        # analysis/advice turn, enrich them with the gated, daily-cached ML reading before
        # deterministic planning. The scorer callback is registered by appserver.py at
        # runtime so this blueprint stays importable without a circular dependency.
        if needs_pattern_ai_context(user_message, wave_viewer):
            scorer = current_app.extensions.get("tara_ai_analysis_context")
            if callable(scorer):
                try:
                    ai_analysis = scorer(wave_viewer, user_token, opp_table_market)
                    if isinstance(ai_analysis, dict):
                        wave_viewer["ai_analysis"] = ai_analysis
                except Exception:
                    # The historical analysis must remain available during an ML outage.
                    logging.exception("Tara AI analysis enrichment failed; continuing without it")

        # Questions whose answer is completely determined by the loaded data and current UI state
        # bypass the provider. This prevents direction inversions and guarantees that a broad screen
        # question covers both the top chart and the bottom panel the user is actually viewing.
        planned_reply = None
        if investor_intent not in gateway_owned_intents:
            planned_reply = build_deterministic_reply(
                user_message,
                wave_viewer,
                screen_context,
                opportunities=opportunities,
            )
        if planned_reply is not None:
            return finish(planned_reply, [])

        full_history_years = requested_full_history_years(
            user_message,
            wave_viewer,
            screen_context,
        )
        full_history_request = (
            _loaded_full_history_request(full_history_years, wave_viewer, opp_table_market)
            if full_history_years is not None
            else None
        )
        explicit_named_symbol = explicit_pattern_symbol(user_message)
        loaded_symbol = str(wave_viewer.get("symbol") or "").strip().upper()
        named_symbol_override = (
            explicit_named_symbol
            if explicit_named_symbol
            and loaded_symbol
            and explicit_named_symbol != loaded_symbol
            else None
        )
        named_symbol_lookback = None
        # A bare symbol change inherits the viewer's current consecutive lookback. An
        # explicitly requested N-year/max-history comparison remains authoritative.
        explicit_lookback = re.search(
            r"\b(?:max(?:imum)?|all|full)(?:\s+available)?\s+(?:years?|history)\b|"
            r"\b\d{1,2}\s*(?:-|\s)?years?\b",
            user_message,
            re.I,
        )
        if named_symbol_override and not explicit_lookback:
            raw_years = wave_viewer.get("years")
            pe_cycle = str(wave_viewer.get("pe_cycle") or "cons").strip().lower()
            if pe_cycle in {"cons", "consecutive"} and str(raw_years or "").isdigit():
                inherited = int(str(raw_years))
                if 1 <= inherited <= 99:
                    named_symbol_lookback = inherited
        viewer_entry_year = (
            None
            if re.search(r"\b(?:19|20)\d{2}\b", user_message)
            else datetime.datetime.now(datetime.timezone.utc).year
        )

        system_prompt = build_system_prompt(wave_viewer, opportunities, opp_table_length,
                                            opp_table_market, opp_table_market_name,
                                            screen_context, user_message=user_message)

        # Onboarding / teach-me is handled by the normal behavior rules + the
        # open-gettingstarted-popup guide (INFO POPUPS). The old hardcoded
        # "Click any row" teach-me wall was REMOVED 2026-06-21 (Tara-peak loop
        # round 1): it injected at the TOP of the prompt and overrode every
        # brevity / screen-control rule below it - the #1 failure cluster
        # (cold-onboarding pass rate 20%). Do NOT reintroduce a verbatim
        # click-the-table block.

        # Build provider-neutral conversation history (system instructions go separately).
        # history already includes the current user message as the last item.
        messages = []
        for h in history[:-1]:   # skip last - it's the current user turn
            role = "assistant" if h.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": user_message})

        provider = select_tara_provider()
        logging.info(
            "Tara model turn phase=start provider=%s model=%s tools=%s",
            provider,
            PRIMARY_MODEL,
            TARA_TOOLS_ENABLED,
        )
        response_provider = provider

        actions = []
        try:
            if TARA_TOOLS_ENABLED:
                bot_reply, actions = run_chat_with_openai_tools(
                    messages,
                    system_prompt,
                    user_id,
                    OPENAI_CHATBOT_MODEL,
                    opp_table=opportunities,
                    opp_table_market=opp_table_market,
                    user_token=user_token,
                    opp_table_years=opp_table_years,
                    full_history_request=full_history_request,
                    named_symbol_override=named_symbol_override,
                    named_symbol_lookback=named_symbol_lookback,
                    viewer_entry_year=viewer_entry_year,
                    current_view=wave_viewer,
                    turn_id=turn_id,
                    protocol_trace=protocol_trace,
                )
            else:
                if investor_intent in {
                    'seasonal_etf', 'seasonal_stock', 'weak_etf', 'weak_stock',
                }:
                    bot_reply = (
                        "The historical opportunity screen is temporarily unavailable, so I won't "
                        "invent or choose a candidate. Please try this research screen again in a moment."
                    )
                elif view_intent == 'unsupported_live':
                    bot_reply = unsupported_live_data_response()
                elif view_intent in {'chart', 'view'}:
                    bot_reply = (
                        "Chart controls are temporarily unavailable, so I haven't changed the chart. "
                        "Please try again in a moment."
                    )
                else:
                    bot_reply = send_openai_messages(
                        messages,
                        model=OPENAI_CHATBOT_MODEL,
                        system=system_prompt,
                        user_id=user_id,
                    )
            logging.info(
                "Tara model turn phase=complete provider=%s model=%s status=success",
                PRIMARY_PROVIDER,
                PRIMARY_MODEL,
            )
        except OpenAIConfigurationError:
            # Misconfiguration is a deployment failure, never a reason to silently
            # choose a different model policy at runtime.
            raise
        except Exception as exc:
            # Tool reads are GET-only and update_view actions are not returned until
            # the loop completes, so a fresh Haiku retry is safe after a genuine
            # primary API/connection/adapter failure.
            category = failure_category(exc)
            logging.warning(
                "Tara model fallback primary_provider=%s primary_model=%s "
                "fallback_provider=%s fallback_model=%s category=%s",
                PRIMARY_PROVIDER,
                PRIMARY_MODEL,
                FALLBACK_PROVIDER,
                FALLBACK_MODEL,
                category,
            )
            response_provider = "anthropic_fallback"
            actions = []
            if TARA_TOOLS_ENABLED:
                bot_reply, actions = run_chat_with_tools(
                    messages,
                    system_prompt,
                    user_id,
                    CHATBOT_MODEL,
                    CACHE_TTL,
                    opp_table=opportunities,
                    opp_table_market=opp_table_market,
                    user_token=user_token,
                    opp_table_years=opp_table_years,
                    full_history_request=full_history_request,
                    named_symbol_override=named_symbol_override,
                    named_symbol_lookback=named_symbol_lookback,
                    viewer_entry_year=viewer_entry_year,
                    current_view=wave_viewer,
                    turn_id=turn_id,
                    protocol_trace=protocol_trace,
                )
            else:
                view_intent = classify_view_intent(user_message)
                if investor_intent in {
                    'seasonal_etf', 'seasonal_stock', 'weak_etf', 'weak_stock',
                }:
                    bot_reply = (
                        "The historical opportunity screen is temporarily unavailable, so I won't "
                        "invent or choose a candidate. Please try this research screen again in a moment."
                    )
                elif view_intent == 'unsupported_live':
                    bot_reply = unsupported_live_data_response()
                elif view_intent in {'chart', 'view'}:
                    bot_reply = (
                        "Chart controls are temporarily unavailable, so I haven't changed the chart. "
                        "Please try again in a moment."
                    )
                else:
                    bot_reply = send_claude_messages(
                        messages,
                        model=CHATBOT_MODEL,
                        system=system_prompt,
                        cache_system=True,
                        cache_ttl=CACHE_TTL,
                    )
            logging.info(
                "Tara model turn phase=complete provider=%s model=%s status=fallback_success",
                FALLBACK_PROVIDER,
                FALLBACK_MODEL,
            )

        # Deterministic floor: guarantee a stat on a loaded-pattern strength question
        # (Haiku at temp 0 occasionally punts with a bare "loaded" and no number).
        bot_reply = _ensure_strength_answered(user_message, wave_viewer, bot_reply)
        if response_violates_investor_contract(bot_reply, investor_intent):
            protocol_trace.append({
                'event': 'protocol_violation',
                'reason': 'unsafe_investor_response',
            })
            bot_reply = (
                "TradeWave cannot determine which security is suitable for you. I can provide "
                "tool-grounded historical seasonal evidence, including losing years, but not a "
                "personal buy, sell, hold, allocation, or return forecast."
            )
        if response_violates_view_contract(
            bot_reply, actions=actions, current_view=wave_viewer
        ):
            protocol_trace.append({
                'event': 'protocol_violation',
                'reason': 'unsafe_postprocessed_response',
            })
            if actions:
                symbol_action = next((
                    action.get('spec', {}).get('symbol')
                    for action in reversed(actions)
                    if isinstance(action.get('spec'), dict)
                    and action.get('spec', {}).get('symbol')
                ), '')
                bot_reply = (
                    '<b>%s</b> chart request.' % str(symbol_action).upper()
                    if symbol_action else 'Requested view change.'
                )
            else:
                bot_reply = (
                    "I couldn't complete that chart request safely, so I haven't changed "
                    "the chart. Please try again."
                )

        return finish(
            bot_reply,
            actions,
            provider=response_provider,
            messages_or_text=messages,
        )

    except Exception:
        logging.exception("chatbot.chat failed for user_id=%s", user_id)  # detail server-side only
        safe_reply = "Sorry, something went wrong on my end. Please try again."
        protocol_trace.append({'event': 'backend_exception', 'reason': 'turn_failed'})
        _write_question_audit(
            user_id,
            user_message,
            safe_reply,
            wave_viewer,
            turn_id=turn_id,
            actions=[],
            protocol_trace=protocol_trace,
            provider='error',
        )
        return jsonify({
            'reply': safe_reply,
            'actions': [],
            'suggestions': guided_next_questions(
                user_message,
                reply=safe_reply,
                current_view=wave_viewer,
                analysis_report=analysis_report,
            ),
            'turn_id': turn_id,
        })  # generic message; consistent envelope on every path
