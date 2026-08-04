"""Deterministic answer planning for Tara's high-confidence UI explanations.

The language model is useful for interpreting open-ended requests, but it should not have to
guess which chart is visible or derive whether a short trade made money.  This module consumes
the structured screen snapshot sent by ``Chatbot.js`` and the already-loaded pattern data, then
builds concise answers for intents whose truth is completely known in application state.

Keep this module free of Flask/provider imports so its domain behavior stays unit-testable.
"""

from __future__ import annotations

import datetime as _datetime
import html
import math
import re
import statistics
from collections.abc import Iterable
from typing import Any, Dict, List, Mapping, Optional

from featured_patterns import (
    HUNDRED_YEAR_DISPLAY_DAYS,
    hundred_year_completed_count,
    hundred_year_completed_year_bounds,
    hundred_year_end_date,
    hundred_year_occurrence_start,
    hundred_year_occurrence_status,
    hundred_year_view_spec,
)


_SCREEN_OVERVIEW_PATTERNS = (
    re.compile(r"\bwhat (?:am i|are we) looking at\b", re.I),
    re.compile(r"\bwhat (?:is|does) (?:this|the) (?:screen|view|chart(?:s)?) (?:show|showing)\b", re.I),
    re.compile(r"\bexplain (?:what i(?:'m| am) looking at|this screen|the screen|these charts|this view)\b", re.I),
    re.compile(r"\bwalk me through (?:this|the) (?:screen|view|charts?)\b", re.I),
)

_BAR_SEMANTICS_PATTERNS = (
    re.compile(r"\bwhat do (?:the )?(?:green|red|green and red) bars mean\b", re.I),
    re.compile(r"\bwhy (?:are|is) (?:most of )?(?:the )?(?:bars?|chart) (?:green|red)\b", re.I),
    re.compile(r"\bwhy are there (?:so many|mostly) (?:green|red) bars\b", re.I),
    re.compile(r"\b(?:most of )?(?:the )?bars (?:are|look) (?:green|red).{0,35}\b(?:how|why)\b", re.I),
    re.compile(r"\bhow (?:can|does) (?:a |this )?short .{0,30}(?:green|red|bars?)\b", re.I),
    re.compile(r"\b(?:green|red) bars?.{0,30}(?:short|profit|loss|win)\b", re.I),
    re.compile(r"\b(?:bar|bars|colors?) .{0,20}(?:short|profit|loss|win)\b", re.I),
)

_TREND_ALIGNMENT_PATTERNS = (
    re.compile(r"\b(?:what (?:does|is)|explain|define|how does) (?:the )?trend alignment\b", re.I),
    re.compile(r"\bwhy (?:does|is) (?:the )?trend (?:say|show|alignment)\s*(?:aligned|against|neutral)?\b", re.I),
    re.compile(r"\bwhat does (?:aligned|against|neutral) mean\b", re.I),
)

_PATTERN_ANALYSIS_PATTERNS = (
    # A loaded chart makes terse imperatives unambiguous. Keep these out of the
    # provider path so "analyze" is as fast and complete as "analyze this pattern."
    re.compile(
        r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
        r"(?:analy[sz]e|evaluate|assess|review)"
        r"(?:\s+(?:this(?:\s+(?:pattern|setup|window|trade|opportunity|one))?|it))?"
        r"(?:\s+for\s+me)?(?:\s+please|,\s*please)?\s*[?.!]*\s*$",
        re.I,
    ),
    re.compile(r"\b(?:analy[sz]e|evaluate|assess|review) (?:this|the|current|loaded) (?:pattern|setup|window|trade|opportunity)\b", re.I),
    re.compile(r"\b(?:analy[sz]e|evaluate|assess|review|break down) this\s*[?.!]*$", re.I),
    re.compile(r"\b(?:give|show) me (?:an |your )?(?:analysis|assessment|deep dive)(?: of (?:this|the (?:pattern|setup|window)))?\b", re.I),
    re.compile(r"\b(?:analysis|assessment|deep dive) (?:of|on) (?:this|the|current|loaded) (?:pattern|setup|window|trade)\b", re.I),
    re.compile(r"\bhow (?:strong|good|reliable|consistent|robust) (?:is|was) (?:this|the|it)\b", re.I),
    re.compile(r"\bis (?:this|the) (?:pattern|setup|window) (?:strong|reliable|consistent|robust)\b", re.I),
    re.compile(r"\bhow (?:has|did) (?:this|the pattern|the setup|it) (?:perform|performed|do)\b", re.I),
    re.compile(r"\bwhat (?:are|were) (?:its|the) (?:strengths?|weaknesses?|pros? and cons?)\b", re.I),
    re.compile(r"\bwhat do you think (?:of|about) (?:this|the) (?:pattern|setup|window|opportunity)\b", re.I),
    re.compile(r"\btell me about (?:this|the|current|loaded) (?:pattern|setup|window|opportunity)\b", re.I),
    re.compile(r"\bwhat (?:stands out|should i (?:notice|know)|is the story|is the takeaway)\b", re.I),
    re.compile(r"\b(?:give me|what(?:'s| is)) (?:the )?(?:bottom line|read|story|takeaway)\b", re.I),
    re.compile(r"\bmake sense of (?:this|the (?:pattern|setup|window))\b", re.I),
    re.compile(r"\b(?:anything|something) (?:interesting|useful|important) (?:here|about this)\b", re.I),
    re.compile(r"^\s*(?:thoughts|your take|your read)\s*[?.!]*$", re.I),
    re.compile(r"\bdoes (?:this|it|the (?:pattern|setup|window)) (?:make money|work)\b", re.I),
    re.compile(r"\bis (?:this|it|the (?:pattern|setup|window)) historically profitable\b", re.I),
    re.compile(r"\bwhat makes (?:this|it|the (?:pattern|setup|window)) (?:interesting|useful|notable)\b", re.I),
)

_SEASONALITY_VALUE_PATTERNS = (
    re.compile(r"\bconvince me\b.{0,45}\bseasonalit(?:y|ies)\b", re.I),
    re.compile(
        r"\bwhy (?:should|would|do) (?:i|we|someone|traders?) "
        r"(?:use|care about|look at) seasonalit(?:y|ies)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:why is|is|what makes) seasonalit(?:y|ies) (?:actually )?"
        r"(?:useful|helpful|valuable|different|special|powerful|worthwhile)\b",
        re.I,
    ),
    re.compile(
        r"\bwhat(?:'s| is) (?:so )?(?:great|useful|helpful|valuable|different|special) "
        r"about seasonalit(?:y|ies)\b",
        re.I,
    ),
    re.compile(r"\bshow me\b.{0,45}\bwhy seasonalit(?:y|ies) (?:matter|work|help)", re.I),
    re.compile(r"\bwhat can seasonalit(?:y|ies) (?:show|find|detect|see)\b", re.I),
    re.compile(
        r"\bhow is seasonalit(?:y|ies) different from\b.{0,45}"
        r"\b(?:indicators?|technicals?|charts?|traditional analysis)\b",
        re.I,
    ),
    re.compile(
        r"\bseasonalit(?:y|ies)\b.{0,45}\b(?:normal|traditional|technical) "
        r"(?:indicators?|analysis|charts?)\b",
        re.I,
    ),
    re.compile(r"\bsell me on seasonalit(?:y|ies)\b", re.I),
)

_STRATEGY_BUILDING_PATTERNS = (
    re.compile(
        r"\bhelp me (?:come up with|build|create|develop|design|form) "
        r"(?:a |my )?(?:(?:winning|profitable|seasonal|trading|rules?[- ]based) )*"
        r"strateg(?:y|ies)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:build|create|develop|design) (?:me )?(?:a |my )?"
        r"(?:(?:winning|profitable|seasonal|trading|rules?[- ]based) )+strateg(?:y|ies)\b",
        re.I,
    ),
    re.compile(
        r"\bturn (?:this|the pattern|my idea|a seasonal pattern) into "
        r"(?:a )?(?:testable |trading |seasonal )?strategy\b",
        re.I,
    ),
    re.compile(r"\bstrategy (?:with|around|using) measurable (?:odds|probabilit(?:y|ies))\b", re.I),
)

_AI_HORIZON_MODEL_PATTERN = re.compile(
    r"\b(?:ai|machine[- ]learning|model|win probability|predr|pmfe|calibrated probabilit(?:y|ies))\b",
    re.I,
)
_AI_HORIZON_REASON_PATTERN = re.compile(
    r"\b(?:why|how come|explain|reason|only|limit(?:ed)?|stop(?:s|ped)?|"
    r"end(?:s|ed)?|maximum|max|up to|beyond|after)\b",
    re.I,
)
_AI_HORIZON_DAY_PATTERN = re.compile(
    r"\b(\d{2,3})\s*[- ]?\s*(?:calendar\s+)?days?\b",
    re.I,
)

_ADVICE_PATTERNS = re.compile(
    r"\b(?:should i|should we|"
    r"would you(?!\s+(?:please\s+)?(?:analy[sz]e|evaluate|assess|review)\b)|"
    r"would you take|do you recommend|recommend(?:ation)?|"
    r"buy (?:this|it|the (?:stock|setup|pattern|trade))|sell (?:this|it|the (?:stock|setup|pattern|trade))|short it|"
    r"take (?:it|this|the trade)|enter (?:it|this|the trade)|put money|position size|"
    r"good trade|how good is (?:this|the) trade|worth (?:it|trading|taking)|trade it)\b",
    re.I,
)
_SPECIFIC_YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")

_HUNDRED_YEAR_PATTERN_QUESTIONS = (
    re.compile(r"\b(?:the\s+)?(?:100|hundred)[- ]year (?:seasonal )?pattern\b", re.I),
    re.compile(
        r"\b(?:load|show|open|explain|analy[sz]e|tell me about|what is|what's)\b"
        r".{0,35}\b(?:pattern from|pattern in) "
        r"(?:the|my|your|afshin(?:'s)?) book\b",
        re.I,
    ),
    re.compile(
        r"\b(?:the\s+)?pattern (?:from|in) "
        r"(?:the|my|your|afshin(?:'s)?) book\b",
        re.I,
    ),
    re.compile(r"\b(?:the\s+)?book(?:'s)? (?:100[- ]year )?pattern\b", re.I),
    re.compile(r"\bafshin(?:'s)? (?:book|signature|100[- ]year) pattern\b", re.I),
)

# An explicitly named ticker next to a pattern noun outranks pronouns such as
# "this" and the currently loaded chart. Keep the ticker token case-sensitive so
# ordinary phrases such as "this pattern" and company names are not misread as symbols.
_EXPLICIT_PATTERN_SYMBOL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"((?:[$^][A-Z0-9.-]{1,10})|(?:[A-Z][A-Z0-9.$^-]{0,10}))"
    r"(?:['’]s)?(?i:\s+(?:seasonal\s+)?(?:pattern|setup|window|trade|opportunity)\b)"
)
_EXPLICIT_SYMBOL_QUERY_PATTERN = re.compile(
    r"(?i:\b(?:how\s+(?:does|did)|what\s+about|analy[sz]e|evaluate|assess|review|"
    r"show(?:\s+me)?|load|open|pull\s+up|bring\s+up)\s+(?:the\s+)?)"
    r"((?:[$^][A-Z0-9.-]{1,10})|(?:[A-Z][A-Z0-9.$^-]{0,10}))\b"
)
_NON_SYMBOL_PATTERN_WORDS = {
    "AI",
    "CURRENT",
    "LOADED",
    "MFE",
    "MAE",
    "PE",
    "SAME",
    "THAT",
    "THE",
    "THIS",
    "TWR",
}

# In a loaded year-by-year chart, users often describe MFE/MAE in plain language as
# the "max and min for each year."  Requiring both a path-extreme phrase and an
# explicit per-year scope keeps unrelated max/min questions (hold days, win rate,
# filters, and so on) out of this intent.
_PER_YEAR_SCOPE_PATTERN = re.compile(
    r"\b(?:each|every)\s+(?:completed\s+|historical\s+)?year\b|"
    r"\bper[- ]year\b|\byear[- ]by[- ]year\b|"
    r"\bfor\s+(?:all|the)\s+(?:completed\s+|historical\s+)?years\b",
    re.I,
)
_PLAIN_EXCURSION_PAIR_PATTERN = re.compile(
    r"(?:\b(?:max(?:imum)?|high(?:s|est)?|best)\b.{0,40}"
    r"\b(?:min(?:imum)?|low(?:s|est)?|worst)\b)|"
    r"(?:\b(?:min(?:imum)?|low(?:s|est)?|worst)\b.{0,40}"
    r"\b(?:max(?:imum)?|high(?:s|est)?|best)\b)",
    re.I,
)
_MFE_TERM_PATTERN = re.compile(
    r"\b(?:mfe|maximum favorable(?: excursion)?|best (?:move|point))\b", re.I
)
_MAE_TERM_PATTERN = re.compile(
    r"\b(?:mae|maximum adverse(?: excursion)?|worst (?:move|point)|drawdown)\b", re.I
)
_EXCURSION_SHOW_PATTERN = re.compile(
    r"\b(?:show(?:\s+me)?|display|turn\s+on|enable|add|overlay)\b", re.I
)
_EXCURSION_HIDE_PATTERN = re.compile(
    r"\b(?:hide|turn\s+off|disable|remove)\b", re.I
)
_EXCURSION_VALUE_REQUEST_PATTERN = re.compile(
    r"\b(?:list|values?|numbers?|table|breakdown)\b", re.I
)
_PLAIN_EXCURSION_FALSE_POSITIVE_PATTERN = re.compile(
    r"\b(?:win\s*rate|sharpe|hold(?:ing)?\s+days?|returns?|sample|setups?|opportunit)\w*\b",
    re.I,
)

_RECENCY_PATTERNS = (
    re.compile(r"\b(?:recent|lately|latest|last (?:three|four|five|3|4|5) years?)\b", re.I),
    re.compile(r"\b(?:holding up|still work(?:ing)?|weaken(?:ed|ing)?|improv(?:ed|ing)?)\b", re.I),
)
_RISK_PATTERNS = (
    re.compile(r"\b(?:what(?:'s| is) the catch|downside|risk|weakness|failure|when it loses)\b", re.I),
    re.compile(r"\b(?:how bad|how large) (?:are|were|is) (?:the )?loss(?:es)?\b", re.I),
)
_CONSISTENCY_PATTERNS = (
    re.compile(r"\b(?:consistent|consistency|stable|stability|smooth|volatile|volatility|outlier)\b", re.I),
    re.compile(r"\b(?:one big year|single (?:best|big) year|dependent on)\b", re.I),
)
_RANK_PATTERNS = (
    re.compile(r"\b(?:why|where) (?:does|is) (?:this(?: (?:pattern|setup))?|it|the (?:pattern|setup)) rank(?:ed)?\b", re.I),
    re.compile(r"\bwhat(?:'s| is) (?:this|its|the) rank\b", re.I),
    re.compile(r"\bwhy is (?:this|it) (?:number|#)\s*\d+\b", re.I),
)
_DIRECTION_PATTERNS = (
    re.compile(r"\bwhy (?:is|was) (?:this|it|the (?:pattern|setup|opportunity)) (?:a )?(?:short|long|bearish|bullish)\b", re.I),
    re.compile(r"\bhow (?:did|does) (?:tradewave|tara|it) (?:choose|pick|decide|determine|label) (?:the )?(?:direction|short|long)\b", re.I),
)

_MCP_TERM_PATTERN = re.compile(r"\b(?:mcp|model context protocol)\b", re.I)
_EXTERNAL_AI_PATTERN = re.compile(
    r"\b(?:chatgpt|claude(?:\.ai| desktop)?|external ai(?: assistant)?|"
    r"outside ai(?: assistant)?|ai connector)\b",
    re.I,
)
_TRADEWAVE_PRODUCT_PATTERN = re.compile(
    r"\b(?:tradewave|tara|seasonality|seasonal (?:research|pattern|analysis)|wave viewer)\b",
    re.I,
)
_MCP_PRODUCT_CUE_PATTERN = re.compile(
    r"\b(?:what|how|why|where|can|could|does|do|need|use|using|connect|access|"
    r"replace|instead|difference|same|safe|private|cost|plan|key|ask|work)\b",
    re.I,
)
_TARA_PROVIDER_IDENTITY_PATTERN = re.compile(
    r"\b(?:is\s+tara\s+(?:using|running on|running with|powered by)|"
    r"does\s+tara\s+use)\s+(?:chatgpt|claude)\b",
    re.I,
)
_MCP_SETUP_URL = "https://developers.tradewave.ai/mcp"

_TOOLTIPS_OFF_PATTERN = re.compile(
    r"\b(?:turn|switch|shut)\s+(?:all\s+|the\s+)?(?:guidance\s+)?"
    r"(?:tooltips?|hover tips?)\s+off\b|"
    r"\b(?:disable|hide|remove|stop showing|get rid of)\b.{0,35}"
    r"\b(?:tooltips?|hover tips?)\b|"
    r"\b(?:do not|don't|dont)\s+(?:like|want|need)\b.{0,35}"
    r"\b(?:tooltips?|hover tips?)\b|"
    r"\b(?:tooltips?|hover tips?)\b.{0,35}"
    r"\b(?:annoying|distracting|everywhere|cluttered?|too many|in the way)\b",
    re.I,
)
_TOOLTIPS_ON_PATTERN = re.compile(
    r"\b(?:turn|switch)\s+(?:all\s+|the\s+)?(?:guidance\s+)?"
    r"(?:tooltips?|hover tips?)\s+on\b|"
    r"\b(?:enable|show)\b.{0,30}\b(?:tooltips?|hover tips?)\b|"
    r"\b(?:do not|don't|dont|cannot|can't|cant)\s+"
    r"(?:understand|follow|make sense of)\b.{0,45}"
    r"\b(?:controls?|buttons?|icons?|switches?|interface)\b|"
    r"\b(?:controls?|buttons?|icons?|switches?|interface)\b.{0,35}"
    r"\b(?:confusing|overwhelming|unclear|do not make sense|don't make sense)\b|"
    r"\b(?:help me understand|explain)\b.{0,35}"
    r"\b(?:these|the|all these)\s+(?:controls?|buttons?|icons?|switches?)\b|"
    r"\bwhat do\b.{0,30}\b(?:these|the|all these)\s+"
    r"(?:controls?|buttons?|icons?|switches?)\s+do\b",
    re.I,
)
_TOOLTIPS_HELP_PATTERN = re.compile(
    r"\b(?:where (?:is|are)|where can i find|show me where|find)\b.{0,35}"
    r"\b(?:tooltips?|tooltip (?:switch|toggle))\b|"
    r"\bhow (?:do|can) i toggle\b.{0,25}\btooltips?\b|"
    r"^\s*what (?:are|is) (?:the )?(?:guidance )?tooltips?(?: toggle| switch)?\s*[?.!]*\s*$",
    re.I,
)

_FULL_HISTORY_COMMAND_PATTERN = re.compile(
    r"\b(?:load|show(?:\s+me)?|use|set|change|switch|expand|extend|run|"
    r"analy[sz]e|review|look)\b.{0,60}\b(?:max(?:imum)?(?:\s+available)?\s+years?|"
    r"all(?:\s+available)?\s+years?|full(?:\s+available)?\s+history)\b",
    re.I,
)

_OPPORTUNITY_ROW_ACTION_PATTERN = re.compile(
    r"\b(?:load|open|select|chart|pull\s+up|bring\s+up|show(?:\s+me)?)\b",
    re.I,
)
_OPPORTUNITY_ROW_TARGET_PATTERN = re.compile(
    r"\b(?:one|row|item|setup|opportunit(?:y|ies)|pick|list|table)\b",
    re.I,
)
_OPPORTUNITY_ROW_HASH_PATTERN = re.compile(r"#\s*(\d{1,2})\b", re.I)
_OPPORTUNITY_ROW_NUMBER_PATTERN = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)\b|\brow\s*#?\s*(\d{1,2})\b",
    re.I,
)
_OPPORTUNITY_ROW_WORD_PATTERN = re.compile(
    r"\b(top|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b",
    re.I,
)
_OPPORTUNITY_ROW_WORDS = {
    "top": 1,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}

# Moving among the three lower desktop panels is a reversible viewer command. Keep this
# deterministic so a direct request never depends on a model deciding whether Tara can drive
# the carousel. The anchored command prefix deliberately excludes explanatory questions such
# as "what does the Trend Chart show?" and "explain Wave Stats".
_BOTTOM_SLIDE_COMMAND_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:show(?:\s+me)?|open|display|load|pull\s+up|bring\s+up|"
    r"switch(?:\s+me)?(?:\s+over)?(?:\s+to)?|go\s+to|take\s+me\s+to|"
    r"flip\s+to|swipe\s+to)\b",
    re.I,
)
_BOTTOM_SLIDE_TARGETS = (
    (
        "trend_chart",
        "Trend Chart",
        re.compile(r"\b(?:the\s+)?(?:seasonal\s+)?trend\s+chart\b", re.I),
    ),
    (
        "price_chart",
        "Price Chart",
        re.compile(r"\b(?:the\s+)?(?:stock\s+)?price\s+chart\b", re.I),
    ),
    (
        "wave_stats",
        "Wave Stats",
        re.compile(
            r"\b(?:the\s+)?(?:(?:wave|pattern|trade)\s+)?stat(?:s|istics)"
            r"(?:\s+(?:panel|slide|chart))?\b",
            re.I,
        ),
    ),
)

_BOTTOM_SLIDES = {"trend_chart", "wave_stats", "price_chart"}
_PRICE_CHART_MODES = {"current", "active_trade", "historical"}
_WINDOW_PATH_STATES = {"supports", "against", "flat", "unknown"}


def is_screen_overview_question(message: Any) -> bool:
    """Return True only for broad requests to explain the currently visible screen."""

    text = str(message or "").strip()
    return bool(text and any(pattern.search(text) for pattern in _SCREEN_OVERVIEW_PATTERNS))


def is_bar_semantics_question(message: Any) -> bool:
    """Return True for direct questions about bar colors, direction, wins or losses."""

    text = str(message or "").strip()
    return bool(text and any(pattern.search(text) for pattern in _BAR_SEMANTICS_PATTERNS))


def is_trend_alignment_question(message: Any) -> bool:
    """Return True for questions about current momentum versus the loaded direction."""

    text = str(message or "").strip()
    return bool(text and any(pattern.search(text) for pattern in _TREND_ALIGNMENT_PATTERNS))


def is_pattern_analysis_question(message: Any, wave_viewer: Any) -> bool:
    """Return True for a historical analysis of the already-loaded pattern.

    Advice requests stay in the normal policy/tool path, and a question about one named year stays
    in the row-level question path.  A named-symbol analysis is intercepted only when that symbol is
    already loaded, so ``analyze AAPL`` cannot accidentally analyze a different chart.
    """

    text = str(message or "").strip()
    if not text or _ADVICE_PATTERNS.search(text) or _SPECIFIC_YEAR_PATTERN.search(text):
        return False
    wv = wave_viewer if isinstance(wave_viewer, Mapping) else {}
    symbol = str(wv.get("symbol") or "").strip().upper()
    if not symbol:
        return False
    if any(pattern.search(text) for pattern in _PATTERN_ANALYSIS_PATTERNS):
        return True

    named = re.search(
        r"\b(?:analy[sz]e|evaluate|assess|review)\s+(?:the\s+)?([A-Za-z$^.][A-Za-z0-9$^.-]{0,11})\b",
        text,
        re.I,
    )
    return bool(named and named.group(1).upper() == symbol)


def explicit_pattern_symbol(message: Any) -> Optional[str]:
    """Return an uppercase ticker explicitly named in a pattern/view question.

    Besides ``ITW pattern``, accept common compact requests such as ``how does ITW do?``
    and ``show me ITW``. The ticker capture itself remains case-sensitive so ordinary words
    do not become symbols; known analytical acronyms are excluded below.
    """

    text = str(message or "")
    for pattern in (_EXPLICIT_PATTERN_SYMBOL_PATTERN, _EXPLICIT_SYMBOL_QUERY_PATTERN):
        for match in pattern.finditer(text):
            symbol = match.group(1).upper()
            if symbol not in _NON_SYMBOL_PATTERN_WORDS:
                return symbol
    return None


def is_seasonality_value_question(message: Any) -> bool:
    """Whether the user wants the value of seasonality demonstrated, not defined."""

    return _matches_any(message, _SEASONALITY_VALUE_PATTERNS)


def is_strategy_building_question(message: Any) -> bool:
    """Whether the user wants help turning evidence into repeatable research rules."""

    return _matches_any(message, _STRATEGY_BUILDING_PATTERNS)


def is_ai_horizon_explanation_question(message: Any) -> bool:
    """Whether the user wants the reason for the calibrated 30/60/90 horizons."""

    text = str(message or "").strip()
    if not text or not _AI_HORIZON_REASON_PATTERN.search(text):
        return False
    triplet = bool(re.search(r"\b30\b.{0,20}\b60\b.{0,20}\b90\b", text, re.I))
    has_model_term = bool(_AI_HORIZON_MODEL_PATTERN.search(text))
    if not has_model_term and not triplet:
        return False
    numeric_horizons = [
        int(match.group(1)) for match in _AI_HORIZON_DAY_PATTERN.finditer(text)
    ]
    names_ninety_days = bool(
        re.search(r"\bninety\s+(?:calendar\s+)?days?\b", text, re.I)
    )
    names_long_pattern = bool(
        re.search(r"\b(?:full|long(?:er)?)[- ](?:pattern|window|setup)\b", text, re.I)
    )
    return (
        triplet
        or names_ninety_days
        or names_long_pattern
        or any(days >= 90 for days in numeric_horizons)
    )


def _has_loaded_pattern(wave_viewer: Any) -> bool:
    return bool(
        isinstance(wave_viewer, Mapping)
        and str(wave_viewer.get("symbol") or "").strip()
    )


def _matches_any(message: Any, patterns: Iterable[re.Pattern[str]]) -> bool:
    text = str(message or "").strip()
    return bool(text and any(pattern.search(text) for pattern in patterns))


def build_tooltip_preference_command(message: Any) -> Optional[Dict[str, Any]]:
    """Turn global guidance tooltips on or off from clear preference language."""

    text = str(message or "").strip()
    if not text:
        return None
    if _TOOLTIPS_OFF_PATTERN.search(text):
        return {
            "reply": (
                "You can turn guidance tooltips on or off with the <b>Tooltips</b> switch in "
                "the upper-left toolbar, beside the settings gear. I turned them off now."
            ),
            "spec": {"show_tooltips": False},
        }
    if _TOOLTIPS_ON_PATTERN.search(text):
        return {
            "reply": (
                "You can turn guidance tooltips on or off with the <b>Tooltips</b> switch in "
                "the upper-left toolbar, beside the settings gear. I turned them on now so "
                "the controls explain themselves when you hover."
            ),
            "spec": {"show_tooltips": True},
        }
    return None


def build_tooltip_help_reply(message: Any) -> Optional[str]:
    """Explain the tooltip control without changing a preference the user did not choose."""

    text = str(message or "").strip()
    if not text or not _TOOLTIPS_HELP_PATTERN.search(text):
        return None
    return (
        "Guidance tooltips explain controls when you hover over them. The <b>Tooltips</b> "
        "switch is in the upper-left toolbar, beside the settings gear; Tara can also turn "
        "them on or off for you."
    )


def is_mcp_product_question(message: Any) -> bool:
    """Recognize questions about using TradeWave through ChatGPT or Claude."""

    text = str(message or "").strip()
    if not text or _TARA_PROVIDER_IDENTITY_PATTERN.search(text):
        return False
    if _MCP_TERM_PATTERN.search(text):
        return True
    return bool(
        _EXTERNAL_AI_PATTERN.search(text)
        and _TRADEWAVE_PRODUCT_PATTERN.search(text)
        and _MCP_PRODUCT_CUE_PATTERN.search(text)
    )


def _mcp_setup_link(label: str = "Open the MCP setup guide") -> str:
    return (
        f'<a href="{_MCP_SETUP_URL}" target="_blank" rel="noopener noreferrer">'
        f"{html.escape(label)}</a>"
    )


def build_mcp_product_reply(message: Any) -> Optional[str]:
    """Return a plain-language, source-of-truth answer about TradeWave MCP."""

    if not is_mcp_product_question(message):
        return None
    text = str(message or "").strip()

    if re.search(
        r"\b(?:control|change|move|load|open)\b.{0,45}\b(?:wave viewer|viewer|screen|chart)\b|"
        r"\b(?:wave viewer|viewer|screen|chart)\b.{0,45}\b(?:control|change|move|load|open)\b",
        text,
        re.I,
    ):
        return (
            "<b>Tara is the assistant that can see and change your open TradeWave screen.</b> "
            "ChatGPT or Claude can use TradeWave research through MCP and return a link to the "
            "exact Wave Viewer setup, but they do not control the viewer that is already open."
        )

    if re.search(
        r"\b(?:mcp (?:versus|vs\.?) api|api (?:versus|vs\.?) mcp|"
        r"difference between (?:the )?api and mcp)\b",
        text,
        re.I,
    ):
        return (
            "<b>MCP is made for conversations with AI assistants; the API is made for software "
            "code.</b> Both use the same TradeWave gateway and return calculated pattern research. "
            "The normal ChatGPT or Claude MCP connection uses your TradeWave sign-in, while a "
            "developer API connection normally uses an API key."
        )

    if re.search(r"\b(?:api key|access key|secret key|token)\b", text, re.I):
        return (
            "<b>You do not need an API key for the normal ChatGPT or Claude connection.</b> "
            "Add the TradeWave MCP connector, then sign in with your TradeWave account. "
            "Developer tools can use a TradeWave API key instead. "
            + _mcp_setup_link()
            + "."
        )

    if re.search(
        r"\b(?:how|where)\b.{0,35}\b(?:connect|add|set up|setup|start)\b|"
        r"\b(?:connect|add|set up|setup)\b.{0,35}\b(?:mcp|tradewave|chatgpt|claude)\b",
        text,
        re.I,
    ):
        return (
            "<b>Open the TradeWave MCP setup guide and add its server address as a connector "
            "in ChatGPT or Claude.</b> Then choose Connect and sign in with your TradeWave "
            "account. No API key is needed for this normal account connection. "
            + _mcp_setup_link()
            + "."
        )

    if re.search(
        r"\b(?:share|sync|same)\b.{0,35}\b(?:chat|conversation|history|screen state|viewer state)\b|"
        r"\b(?:chat|conversation|history|screen state|viewer state)\b.{0,35}\b(?:share|sync|same)\b",
        text,
        re.I,
    ):
        return (
            "<b>Tara and an outside assistant do not share chat history or screen state.</b> Tara "
            "receives the screen that is open inside TradeWave. ChatGPT or Claude receives the "
            "TradeWave tool results it requests inside its own conversation."
        )

    if re.search(
        r"\b(?:fundamentals?|news|macro|valuation|earnings|other research|outside research)\b",
        text,
        re.I,
    ):
        return (
            "<b>TradeWave MCP supplies seasonal pattern evidence, not company news, fundamentals, "
            "valuation, or macro research.</b> ChatGPT or Claude can add those subjects from other "
            "tools or sources available to it, while keeping them separate from the TradeWave "
            "results."
        )

    if re.search(
        r"\b(?:what (?:should|can) i (?:buy|sell|trade)|tell me what to (?:buy|sell)|"
        r"recommend(?:ation)?|personalized|guarantee|certain|sure thing|winning trade)\b",
        text,
        re.I,
    ):
        return (
            "<b>TradeWave MCP helps an assistant rank and compare opportunities using measured "
            "historical odds, AI-calibrated probabilities, and path risk.</b> It does not know the "
            "future outcome, read your holdings, or turn the research into a personalized buy or "
            "sell decision."
        )

    if re.search(
        r"\b(?:holdings?|positions?|portfolio|raw (?:data|prices?)|price history|live prices?|"
        r"personal data|private|privacy|safe|secure|see my account)\b",
        text,
        re.I,
    ):
        return (
            "<b>TradeWave MCP shares pattern research, not your holdings or raw market-price "
            "history.</b> It returns calculated evidence such as percentage results, charts that "
            "show the pattern's shape, each year's best and worst move (MFE and MAE), and AI scores "
            "allowed by your plan. You approve the connection by signing in with your TradeWave "
            "account."
        )

    if re.search(r"\b(?:cost|price|free|plan|tier|limit|quota|subscription)\b", text, re.I):
        return (
            "<b>The normal MCP connection uses your existing TradeWave account.</b> The markets, "
            "research tools, and AI-score limits available through ChatGPT or Claude follow your "
            "TradeWave plan. "
            + _mcp_setup_link("See MCP setup and access details")
            + "."
        )

    if re.search(
        r"\b(?:same (?:data|numbers?|research|results?)|match(?:ing)? (?:data|numbers?|results?)|"
        r"source of truth|different (?:data|numbers?|results?)|accurate|accuracy|reliable|"
        r"hallucinat(?:e|es|ion))\b",
        text,
        re.I,
    ):
        return (
            "<b>For the same pattern inputs, Tara and MCP receive their calculated numbers from the "
            "same TradeWave gateway.</b> Their wording can differ, and Tara also has the current "
            "TradeWave screen as context. The assistant should present the supplied record rather "
            "than recalculate it; the returned chart and exact Wave Viewer link are the clearest "
            "ways to check the result."
        )

    if re.search(
        r"\b(?:need|replace|instead of|without)\b.{0,55}\b(?:seasonality|seasonal|tradewave|tara)\b|"
        r"\b(?:seasonality|seasonal|tradewave|tara)\b.{0,55}\b(?:need|replace|instead of|without)\b|"
        r"\bnow that (?:there is|there's|i have|we have)\b.{0,30}\b(?:ai|chatgpt|claude)\b",
        text,
        re.I,
    ):
        return (
            "<b>AI and seasonality are not substitutes.</b> TradeWave finds and measures repeating "
            "calendar patterns; AI helps you ask questions and understand the evidence.<br>"
            "<b>Use the assistant you prefer:</b> Tara can see and change the open TradeWave screen. "
            "Or connect TradeWave to ChatGPT or Claude through MCP, a secure link that lets them use "
            "TradeWave's scans, pattern history, charts, and the AI scores included in your plan. "
            "Without that connection, a general AI does not automatically have TradeWave's exact "
            "research. "
            + _mcp_setup_link("Connect TradeWave to ChatGPT or Claude")
            + "."
        )

    if re.search(
        r"\b(?:difference|versus|vs\.?|which (?:one|assistant)|why use tara|need tara|"
        r"instead of tara|replace tara)\b",
        text,
        re.I,
    ):
        return (
            "<b>Tara is best while you are working inside TradeWave.</b> She sees the loaded pattern, "
            "the visible table, and the chart view, and she can change that view for you.<br>"
            "<b>ChatGPT or Claude with MCP is best when you want TradeWave research in that assistant's "
            "workspace.</b> It can scan, analyze, compare, and return charts or exact Wave Viewer links, "
            "then combine the evidence with other research tools you choose."
        )

    if re.search(
        r"\b(?:what can|what does|can (?:chatgpt|claude|mcp)|questions? (?:can|should) i ask|"
        r"example (?:question|prompt)|prompts?)\b",
        text,
        re.I,
    ):
        return (
            "<b>With TradeWave connected, ask ChatGPT or Claude to:</b><br>"
            "Find the strongest seasonal setups entering now.<br>"
            "Analyze one symbol with each year's best and worst move (MFE and MAE).<br>"
            "Compare several opportunities on the same evidence.<br>"
            "Give a morning briefing or explain today's TradeWave pick.<br>"
            "Each result can include TradeWave charts and a link to the exact Wave Viewer setup."
        )

    if re.search(r"\b(?:what is|what's|explain|define|mean)\b", text, re.I):
        return (
            "<b>MCP stands for Model Context Protocol. TradeWave MCP is a secure connection that "
            "lets an AI assistant use TradeWave's research tools.</b> After you connect and sign in, "
            "ChatGPT or Claude can scan seasonal patterns, analyze symbols, compare setups, and "
            "receive TradeWave charts and evidence. "
            + _mcp_setup_link()
            + "."
        )

    return (
        "<b>TradeWave MCP lets ChatGPT or Claude use TradeWave research after you connect your "
        "account.</b> Tara remains the screen-aware assistant inside TradeWave, while the connected "
        "assistant works in its own chat and can return TradeWave evidence and Wave Viewer links. "
        + _mcp_setup_link()
        + "."
    )


def is_pattern_recency_question(message: Any, wave_viewer: Any) -> bool:
    """Whether the user is asking how the loaded record has held up lately."""

    return _has_loaded_pattern(wave_viewer) and _matches_any(message, _RECENCY_PATTERNS)


def is_pattern_risk_question(message: Any, wave_viewer: Any) -> bool:
    """Whether the user wants the loaded pattern's historical failure profile."""

    return _has_loaded_pattern(wave_viewer) and _matches_any(message, _RISK_PATTERNS)


def is_pattern_consistency_question(message: Any, wave_viewer: Any) -> bool:
    """Whether the user is asking about dispersion, smoothness, or outlier dependence."""

    return _has_loaded_pattern(wave_viewer) and _matches_any(message, _CONSISTENCY_PATTERNS)


def is_pattern_advice_question(message: Any, wave_viewer: Any) -> bool:
    """Recognize advice wording so Tara can provide evidence without recommending a trade."""

    return _has_loaded_pattern(wave_viewer) and bool(_ADVICE_PATTERNS.search(str(message or "")))


def needs_pattern_ai_context(message: Any, wave_viewer: Any) -> bool:
    """Whether this turn merits a current-condition AI read of the loaded setup."""

    # These product/research-framework answers explain what the AI probability layer
    # does, but they do not need to block on a live scorer call. Their value is an
    # immediate, deterministic explanation from the already-loaded historical record.
    if (
        is_seasonality_value_question(message)
        or is_strategy_building_question(message)
        or is_ai_horizon_explanation_question(message)
    ):
        return False
    return is_pattern_analysis_question(message, wave_viewer) or is_pattern_advice_question(
        message, wave_viewer
    )


def is_pattern_rank_question(message: Any, wave_viewer: Any) -> bool:
    """Whether the user is asking about the loaded row's opportunity-table rank."""

    return _has_loaded_pattern(wave_viewer) and _matches_any(message, _RANK_PATTERNS)


def is_pattern_direction_question(message: Any, wave_viewer: Any) -> bool:
    """Whether the user is asking why the loaded opportunity is long or short."""

    return _has_loaded_pattern(wave_viewer) and _matches_any(message, _DIRECTION_PATTERNS)


def requested_opportunity_row_rank(message: Any) -> Optional[int]:
    """Return the 1-based visible-table row requested by a direct load command.

    A rank must be paired with an action verb and table-like target language.  That keeps
    dates such as ``load AAPL for August 3rd`` out of this UI intent while accepting the
    natural commands users actually type: ``load the top one``, ``pull up row 2`` and
    ``load the 3rd one on the list``.
    """

    text = str(message or "").strip()
    if not text or not _OPPORTUNITY_ROW_ACTION_PATTERN.search(text):
        return None

    hash_match = _OPPORTUNITY_ROW_HASH_PATTERN.search(text)
    if hash_match:
        rank = int(hash_match.group(1))
        return rank if 1 <= rank <= 50 else None

    if not _OPPORTUNITY_ROW_TARGET_PATTERN.search(text):
        return None

    number_match = _OPPORTUNITY_ROW_NUMBER_PATTERN.search(text)
    if number_match:
        raw_rank = number_match.group(1) or number_match.group(2)
        rank = int(raw_rank)
        return rank if 1 <= rank <= 50 else None

    word_match = _OPPORTUNITY_ROW_WORD_PATTERN.search(text)
    if not word_match:
        return None
    return _OPPORTUNITY_ROW_WORDS[word_match.group(1).lower()]


def build_bottom_slide_command(message: Any) -> Optional[Dict[str, Any]]:
    """Return a deterministic command for a direct lower-panel navigation request.

    The desktop wave viewer's lower carousel has three stable semantic destinations. This
    parser recognizes only an explicit navigation verb followed by one of those destinations;
    concept questions remain in Tara's normal explanation/guide path.
    """

    text = str(message or "").strip()
    prefix = _BOTTOM_SLIDE_COMMAND_PREFIX.search(text) if text else None
    if prefix is None:
        return None
    # "Show me where/what/how ..." asks for an explanation, not navigation.
    if re.match(r"\s+(?:where|what|how|why|whether)\b", text[prefix.end():], re.I):
        return None
    for slide, label, target_pattern in _BOTTOM_SLIDE_TARGETS:
        if target_pattern.search(text):
            return {
                "reply": f"<b>Showing {label}.</b>",
                "spec": {"bottom_slide": slide},
            }
    return None


def requested_full_history_years(
    message: Any,
    wave_viewer: Any,
    screen_context: Any,
) -> Optional[int]:
    """Resolve a loaded-pattern "max years" command to the UI's exact data limit.

    ``99`` is a valid API upper bound, but it is not a full-history sentinel.  The React
    viewer already knows the loaded symbol's consecutive-history limit from StockMetaData
    and sends it as ``full_history_years``.  Use that verified value for commands such as
    "load max years for this" so the read tool and the chart use the same real lookback.

    PE-cycle selectors have a different maximum (the count of observations in one cycle
    position), while ``full_history_years`` is intentionally the consecutive-history value
    used by the second price-chart projection.  Do not substitute it for a PE lookback.
    """

    if not _has_loaded_pattern(wave_viewer):
        return None
    text = str(message or "").strip()
    if not text or not _FULL_HISTORY_COMMAND_PATTERN.search(text):
        return None

    wv = wave_viewer if isinstance(wave_viewer, Mapping) else {}
    pe_cycle = str(wv.get("pe_cycle") or "cons").strip().lower()
    if pe_cycle not in ("cons", "consecutive"):
        return None

    raw = normalize_screen_context(screen_context).get("full_history_years")
    if isinstance(raw, bool) or not str(raw or "").isdigit():
        return None
    years = int(str(raw))
    return years if 1 <= years <= 99 else None


def is_specific_year_question(message: Any, wave_viewer: Any) -> bool:
    """Recognize a question about one year of the already-loaded pattern."""

    text = str(message or "").strip()
    if not _has_loaded_pattern(wave_viewer) or not _SPECIFIC_YEAR_PATTERN.search(text):
        return False
    return bool(
        re.search(
            r"\b(?:how|what|did|was|year|return|perform|happen|mfe|mae|bar|profit|loss)\b",
            text,
            re.I,
        )
    )


def is_per_year_excursion_question(message: Any, wave_viewer: Any) -> bool:
    """Recognize a request for each row's intrawindow best/worst move.

    Plain ``max/min`` language is intentionally accepted only with explicit per-year
    scope.  Without that scope it could mean sample extrema, filter limits, prices,
    holding days, or another unrelated maximum/minimum.
    """

    text = str(message or "").strip()
    if not _has_loaded_pattern(wave_viewer) or not _PER_YEAR_SCOPE_PATTERN.search(text):
        return False
    return bool(
        _PLAIN_EXCURSION_PAIR_PATTERN.search(text)
        or _MFE_TERM_PATTERN.search(text)
        or _MAE_TERM_PATTERN.search(text)
    )


def build_excursion_overlay_command(
    message: Any,
    wave_viewer: Any,
) -> Optional[Dict[str, Any]]:
    """Return a deterministic viewer command for explicit MFE/MAE show/hide requests."""

    if not _has_loaded_pattern(wave_viewer):
        return None
    text = str(message or "").strip()
    show = bool(_EXCURSION_SHOW_PATTERN.search(text))
    hide = bool(_EXCURSION_HIDE_PATTERN.search(text))
    if show == hide or _EXCURSION_VALUE_REQUEST_PATTERN.search(text):
        return None

    plain_pair = bool(_PLAIN_EXCURSION_PAIR_PATTERN.search(text))
    if plain_pair and _PLAIN_EXCURSION_FALSE_POSITIVE_PATTERN.search(text):
        return None
    wants_mfe = plain_pair or bool(_MFE_TERM_PATTERN.search(text))
    wants_mae = plain_pair or bool(_MAE_TERM_PATTERN.search(text))
    if not wants_mfe and not wants_mae:
        return None

    enabled = show
    spec: Dict[str, bool] = {}
    if wants_mfe:
        spec["show_mfe"] = enabled
    if wants_mae:
        spec["show_mae"] = enabled

    symbol = html.escape(str((wave_viewer or {}).get("symbol") or "the pattern").upper())
    direction = str((wave_viewer or {}).get("direction") or "long").strip().lower()
    if direction not in {"long", "short"}:
        direction = "long"
    state = "shown" if enabled else "hidden"
    if wants_mfe and wants_mae:
        reply = (
            f"<b>MFE and MAE are now {state} on {symbol}'s loaded year-by-year chart.</b> "
            f"MFE is each observation's best move in the {direction}'s favor; MAE is its worst move against it."
        )
    elif wants_mfe:
        reply = (
            f"<b>MFE is now {state} on {symbol}'s loaded year-by-year chart.</b> "
            f"It marks each observation's best move in the {direction}'s favor during the window."
        )
    else:
        reply = (
            f"<b>MAE is now {state} on {symbol}'s loaded year-by-year chart.</b> "
            f"It marks each observation's worst move against the {direction} during the window."
        )
    return {"reply": reply, "spec": spec}


def normalize_screen_context(raw: Any) -> Dict[str, Any]:
    """Allowlist the client-provided UI snapshot before it reaches prompts or HTML.

    The screen snapshot is descriptive UI state, never a source of financial calculations.  The
    restricted vocabulary also prevents arbitrary client strings from becoming prompt content.
    """

    src = raw if isinstance(raw, Mapping) else {}
    slide = src.get("active_bottom_slide")
    if slide not in _BOTTOM_SLIDES:
        slide = "unknown"

    mode = src.get("price_chart_mode")
    if mode not in _PRICE_CHART_MODES:
        mode = "unknown"

    out: Dict[str, Any] = {
        "active_bottom_slide": slide,
        "price_chart_mode": mode,
        "selected_projection_visible": src.get("selected_projection_visible") is True,
        "full_history_projection_visible": src.get("full_history_projection_visible") is True,
        "opportunity_table_visible": src.get("opportunity_table_visible") is True,
    }

    for key in ("selected_window_path", "full_history_window_path"):
        value = str(src.get(key) or "unknown").strip().lower()
        out[key] = value if value in _WINDOW_PATH_STATES else "unknown"

    year = src.get("price_chart_year")
    try:
        year_int = int(str(year))
    except (TypeError, ValueError):
        year_int = 0
    if 1900 <= year_int <= 2200:
        out["price_chart_year"] = str(year_int)

    # These stay strings: TradeWave lookbacks can be values such as "20" or "pe2-10".
    for source_key, target_key in (
        ("selected_lookback", "selected_lookback"),
        ("full_history_years", "full_history_years"),
        ("projection_period", "projection_period"),
    ):
        value = src.get(source_key)
        if value is not None:
            value = str(value).strip()
            if value and len(value) <= 24 and re.fullmatch(r"[A-Za-z0-9+_.-]+", value):
                out[target_key] = value

    rows = src.get("opportunity_rows")
    try:
        rows_int = int(str(rows))
    except (TypeError, ValueError):
        rows_int = -1
    if 0 <= rows_int <= 100000:
        out["opportunity_rows"] = rows_int

    return out


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _optional_bool(value: Any) -> Optional[bool]:
    """Parse an explicit availability flag without treating arbitrary text as true."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes"}:
            return True
        if normalized in {"0", "false", "no"}:
            return False
    return None


def _today() -> _datetime.date:
    """Small clock seam so occurrence-boundary tests do not depend on wall time."""

    return _datetime.date.today()


def is_hundred_year_pattern_question(message: Any) -> bool:
    """Return True for the book/signature phrases that always load the public exhibit."""

    text = str(message or "").strip()
    return bool(
        text
        and any(pattern.search(text) for pattern in _HUNDRED_YEAR_PATTERN_QUESTIONS)
    )


def build_hundred_year_pattern_command(
    message: Any,
    *,
    today: Optional[_datetime.date] = None,
) -> Optional[Dict[str, Any]]:
    """Build Tara's deterministic load and explanation for The 100-Year Pattern."""

    if not is_hundred_year_pattern_question(message):
        return None

    current = today or _today()
    spec = hundred_year_view_spec(current)
    occurrence_start = hundred_year_occurrence_start(current)
    occurrence_end = hundred_year_end_date(occurrence_start)
    occurrence_status = hundred_year_occurrence_status(current)
    completed_count = hundred_year_completed_count(current)
    first_completed, last_completed = hundred_year_completed_year_bounds(current)

    if completed_count == 24 and last_completed == 2022:
        record_text = (
            "23 of 24 PE+2 observations were profitable "
            "(96%), averaging +18.8%; 1930 was the one losing observation."
        )
    else:
        record_text = (
            "The book record through 2022 was 23 profitable observations out of 24 "
            "completed PE+2 observations (96%), averaging +18.8%; 1930 was the one loss."
        )

    if occurrence_status == "upcoming":
        days_until = (occurrence_start - current).days
        occurrence_line = (
            f"{occurrence_start.year} is upcoming - it starts "
            f"{occurrence_start.strftime('%b')} {occurrence_start.day}, "
            f"{occurrence_start.year} in {days_until} calendar days and ends "
            f"{occurrence_end.strftime('%b')} {occurrence_end.day}, "
            f"{occurrence_end.year}. Its empty row is shown separately and excluded "
            f"from the completed n={completed_count}."
        )
    elif occurrence_status == "active":
        day_number = (current - occurrence_start).days + 1
        occurrence_line = (
            f"{occurrence_start.year} is active on calendar day {day_number} of "
            f"{HUNDRED_YEAR_DISPLAY_DAYS}. Its partial row is shown separately and "
            f"excluded from the completed n={completed_count} until the window ends "
            f"{occurrence_end.strftime('%b')} {occurrence_end.day}, "
            f"{occurrence_end.year}."
        )
    else:
        occurrence_line = (
            f"The {occurrence_start.year} window ended "
            f"{occurrence_end.strftime('%b')} {occurrence_end.day}, "
            f"{occurrence_end.year}; the viewer now includes it in the completed "
            f"n={completed_count}."
        )

    range_text = (
        f"{first_completed}-{last_completed}"
        if first_completed is not None and last_completed is not None
        else "no completed observations yet"
    )
    lines = [
        "<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">"
        "Loaded The 100-Year Pattern</span> SPX long, PE+2 (midterm years), "
        "September 27 through July 18 of the following year. That is 295 calendar "
        "days, with the entry date counted as day 1.</div>",
        f"<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">"
        f"What the bars show</span> One bar per qualifying midterm-cycle observation. "
        f"The completed cohort contains n={completed_count} observations with entry "
        f"years {range_text}; these are not {completed_count} consecutive calendar "
        f"years.</div>",
        f"<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">"
        f"Historical result</span> {record_text}</div>",
        f"<div class=\"tara-analysis-section\"><span class=\"tara-analysis-heading\">"
        f"Current row</span> {occurrence_line}</div>",
        "<div class=\"tara-analysis-section tara-analysis-scope\"><span "
        "class=\"tara-analysis-heading\">Book</span> This is the pattern documented "
        "in <a href=\"https://www.amazon.com/dp/B0FCX61K4Y\" target=\"_blank\" "
        "rel=\"noopener\">The 100-Year Pattern</a>.</div>",
    ]
    if _ADVICE_PATTERNS.search(str(message or "")):
        lines.append(
            "<div class=\"tara-analysis-section tara-analysis-scope\">Past performance "
            "and model estimates do not guarantee future results. TradeWave provides "
            "research context, not individualized recommendations.</div>"
        )
    return {
        "spec": spec,
        "reply": "<div class=\"tara-analysis\">" + "".join(lines) + "</div>",
    }


def _direction_adjusted_rows(
    yearly_results: Any,
    *,
    direction: str,
    before_year: Optional[int] = None,
    placeholder_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Normalize ChartData4 rows and direction-adjust their trade returns."""

    rows: List[Dict[str, Any]] = []
    if not isinstance(yearly_results, Iterable) or isinstance(
        yearly_results, (str, bytes, Mapping)
    ):
        return rows
    for item in yearly_results:
        if not isinstance(item, Mapping):
            continue
        try:
            year = int(str(item.get("year")))
        except (TypeError, ValueError):
            continue
        underlying_value = item.get("underlying_return_pct")
        if underlying_value is None:
            # Rolling deploy compatibility: the prior React bundle used the
            # explicit raw-price name; much older bundles used return_pct.
            underlying_value = item.get("raw_return_pct")
        if underlying_value is None:
            underlying_value = item.get("return_pct")
        underlying_return = _number(underlying_value)
        if underlying_return is None or (before_year is not None and year >= before_year):
            continue
        upside_excursion = _number(
            item.get("upside_excursion_pct", item.get("mfe_pct"))
        )
        downside_excursion = _number(
            item.get("downside_excursion_pct", item.get("mae_pct"))
        )
        # ChartData4 appends the current year as an exact 0,0,0 placeholder when
        # that occurrence has not produced a completed result. It is not a flat trade.
        if (
            placeholder_year is not None
            and year == placeholder_year
            and underlying_return == 0
            and upside_excursion == 0
            and downside_excursion == 0
        ):
            continue
        trade_return = underlying_return if direction != "short" else -underlying_return
        rows.append(
            {
                "year": year,
                "underlying_return_pct": underlying_return,
                "trade_return_pct": trade_return,
                "upside_excursion_pct": upside_excursion,
                "downside_excursion_pct": downside_excursion,
            }
        )
    return sorted(rows, key=lambda row: row["year"])


def _direction_adjusted_excursions(
    row: Mapping[str, Any], *, direction: str
) -> tuple[Optional[float], Optional[float]]:
    """Return entry-relative MFE/MAE in the loaded trade's direction.

    ChartData4 stores the underlying security's upside and downside excursions.
    A short's favorable move is therefore the inverse of the underlying downside,
    while its adverse move is the inverse of the underlying upside.
    """

    upside = _number(row.get("upside_excursion_pct"))
    downside = _number(row.get("downside_excursion_pct"))
    if direction == "short":
        favorable = -downside if downside is not None else None
        adverse = -upside if upside is not None else None
    else:
        favorable = upside
        adverse = downside
    return favorable, adverse


def _longest_streak(values: Iterable[float], *, profitable: bool) -> int:
    longest = current = 0
    for value in values:
        matches = value > 0 if profitable else value < 0
        current = current + 1 if matches else 0
        longest = max(longest, current)
    return longest


def _ending_streak(values: Iterable[float], *, profitable: bool) -> int:
    count = 0
    for value in reversed(list(values)):
        matches = value > 0 if profitable else value < 0
        if not matches:
            break
        count += 1
    return count


def completed_outcome_facts(
    yearly_results: Any,
    *,
    direction: str = "long",
    current_year: Optional[int] = None,
    completed_before_year: Optional[int] = None,
) -> Dict[str, Any]:
    """Derive chart-consistent trade outcomes from completed historical rows.

    ``ChartData4`` bar values are the underlying security's price move, not direction-adjusted P&L.
    A positive move is profitable for a long and a negative move is profitable for a short.  The
    current-year placeholder and all future rows are excluded before records are computed.
    """

    this_year = current_year or _today().year
    cutoff_year = completed_before_year or this_year
    all_nonplaceholder_rows = _direction_adjusted_rows(
        yearly_results,
        direction=direction,
        placeholder_year=this_year,
    )
    rows = [row for row in all_nonplaceholder_rows if row["year"] < cutoff_year]
    incomplete_rows = [
        row
        for row in all_nonplaceholder_rows
        if cutoff_year <= row["year"] <= this_year
    ]

    profits = [row["trade_return_pct"] for row in rows if row["trade_return_pct"] > 0]
    losses = [row["trade_return_pct"] for row in rows if row["trade_return_pct"] < 0]
    flats = [row["trade_return_pct"] for row in rows if row["trade_return_pct"] == 0]
    up_years = sum(1 for row in rows if row["underlying_return_pct"] > 0)
    down_years = sum(1 for row in rows if row["underlying_return_pct"] < 0)
    sample_size = len(rows)
    trade_returns = [row["trade_return_pct"] for row in rows]
    best = max(rows, key=lambda row: row["trade_return_pct"]) if rows else None
    worst = min(rows, key=lambda row: row["trade_return_pct"]) if rows else None
    compounded_return = None
    if trade_returns and all(value > -100 for value in trade_returns):
        compounded_return = 100.0 * (
            math.prod(1.0 + value / 100.0 for value in trade_returns) - 1.0
        )
    avg_win = (sum(profits) / len(profits)) if profits else None
    avg_loss = (sum(losses) / len(losses)) if losses else None
    ordered_rows = rows
    recent_rows = ordered_rows[-5:]
    prior_rows = ordered_rows[:-5]
    recent_returns = [row["trade_return_pct"] for row in recent_rows]
    prior_returns = [row["trade_return_pct"] for row in prior_rows]
    recent_profits = sum(1 for value in recent_returns if value > 0)
    prior_profits = sum(1 for value in prior_returns if value > 0)
    without_best = list(trade_returns)
    if without_best:
        without_best.remove(max(without_best))
    profit_factor = None
    if losses:
        profit_factor = sum(profits) / abs(sum(losses))
    breakeven_win_rate = None
    if avg_win is not None and avg_loss not in (None, 0):
        breakeven_win_rate = 100.0 * abs(avg_loss) / (avg_win + abs(avg_loss))

    path_rows = []
    for row in rows:
        mfe, mae = _direction_adjusted_excursions(row, direction=direction)
        path_rows.append({**row, "mfe_pct": mfe, "mae_pct": mae})
    mfe_values = [row["mfe_pct"] for row in path_rows if row["mfe_pct"] is not None]
    mae_values = [row["mae_pct"] for row in path_rows if row["mae_pct"] is not None]
    profitable_mae_values = [
        row["mae_pct"]
        for row in path_rows
        if row["trade_return_pct"] > 0 and row["mae_pct"] is not None
    ]
    losing_path_rows = [
        row for row in path_rows if row["trade_return_pct"] < 0
    ]
    losing_mfe_values = [
        row["mfe_pct"]
        for row in losing_path_rows
        if row["mfe_pct"] is not None
    ]
    largest_losing_mfe_row = max(
        (row for row in losing_path_rows if row["mfe_pct"] is not None),
        key=lambda row: row["mfe_pct"],
        default=None,
    )
    only_losing_row = losing_path_rows[0] if len(losing_path_rows) == 1 else None
    worst_mae_row = min(
        (row for row in path_rows if row["mae_pct"] is not None),
        key=lambda row: row["mae_pct"],
        default=None,
    )

    return {
        "sample_size": sample_size,
        "profitable_years": len(profits),
        "losing_years": len(losses),
        "flat_years": len(flats),
        "underlying_up_years": up_years,
        "underlying_down_years": down_years,
        "win_rate_pct": (100.0 * len(profits) / sample_size) if sample_size else None,
        "avg_profitable_return_pct": avg_win,
        "avg_losing_return_pct": avg_loss,
        "avg_trade_return_pct": statistics.fmean(trade_returns) if trade_returns else None,
        "median_trade_return_pct": statistics.median(trade_returns) if trade_returns else None,
        "standard_deviation_pct": statistics.stdev(trade_returns) if len(trade_returns) > 1 else None,
        "derived_cumulative_return_pct": compounded_return,
        "best_year": best["year"] if best else None,
        "best_trade_return_pct": best["trade_return_pct"] if best else None,
        "worst_year": worst["year"] if worst else None,
        "worst_trade_return_pct": worst["trade_return_pct"] if worst else None,
        "completed_years": [row["year"] for row in ordered_rows],
        "first_completed_year": ordered_rows[0]["year"] if ordered_rows else None,
        "payoff_ratio": (avg_win / abs(avg_loss)) if avg_win is not None and avg_loss not in (None, 0) else None,
        "profit_factor": profit_factor,
        "breakeven_win_rate_pct": breakeven_win_rate,
        "avg_without_best_year_pct": (
            statistics.fmean(without_best) if without_best else None
        ),
        "longest_profitable_streak": _longest_streak(trade_returns, profitable=True),
        "longest_losing_streak": _longest_streak(trade_returns, profitable=False),
        "ending_profitable_streak": _ending_streak(trade_returns, profitable=True),
        "ending_losing_streak": _ending_streak(trade_returns, profitable=False),
        "latest_completed_year": ordered_rows[-1]["year"] if ordered_rows else None,
        "latest_trade_return_pct": (
            ordered_rows[-1]["trade_return_pct"] if ordered_rows else None
        ),
        "recent_sample_size": len(recent_rows),
        "recent_profitable_years": recent_profits,
        "recent_win_rate_pct": (
            100.0 * recent_profits / len(recent_rows) if recent_rows else None
        ),
        "recent_avg_trade_return_pct": (
            statistics.fmean(recent_returns) if recent_returns else None
        ),
        "prior_sample_size": len(prior_rows),
        "prior_profitable_years": prior_profits,
        "prior_win_rate_pct": (
            100.0 * prior_profits / len(prior_rows) if prior_rows else None
        ),
        "prior_avg_trade_return_pct": (
            statistics.fmean(prior_returns) if prior_returns else None
        ),
        "mfe_sample_size": len(mfe_values),
        "median_mfe_pct": statistics.median(mfe_values) if mfe_values else None,
        "mae_sample_size": len(mae_values),
        "median_mae_pct": statistics.median(mae_values) if mae_values else None,
        "median_profitable_mae_pct": (
            statistics.median(profitable_mae_values)
            if profitable_mae_values
            else None
        ),
        "losing_mfe_sample_size": len(losing_mfe_values),
        "median_losing_mfe_pct": (
            statistics.median(losing_mfe_values) if losing_mfe_values else None
        ),
        "largest_losing_mfe_pct": (
            largest_losing_mfe_row["mfe_pct"] if largest_losing_mfe_row else None
        ),
        "largest_losing_mfe_year": (
            largest_losing_mfe_row["year"] if largest_losing_mfe_row else None
        ),
        "largest_losing_mfe_finish_pct": (
            largest_losing_mfe_row["trade_return_pct"]
            if largest_losing_mfe_row
            else None
        ),
        "only_losing_year": only_losing_row["year"] if only_losing_row else None,
        "only_losing_return_pct": (
            only_losing_row["trade_return_pct"] if only_losing_row else None
        ),
        "only_losing_mfe_pct": (
            only_losing_row["mfe_pct"] if only_losing_row else None
        ),
        "only_losing_mae_pct": (
            only_losing_row["mae_pct"] if only_losing_row else None
        ),
        "worst_mae_pct": worst_mae_row["mae_pct"] if worst_mae_row else None,
        "worst_mae_year": worst_mae_row["year"] if worst_mae_row else None,
        "excluded_incomplete_observations": len(incomplete_rows),
        # ChartData4's aggregate stats include an active non-zero row. Callers must
        # not label those aggregates as belonging to the completed sample above.
        "stats_include_incomplete_observation": bool(incomplete_rows),
    }


def canonical_pattern_facts(
    wave_viewer: Any, *, current_year: Optional[int] = None
) -> Dict[str, Any]:
    """Return a small, provider-neutral fact ledger for the loaded pattern."""

    wv = wave_viewer if isinstance(wave_viewer, Mapping) else {}
    direction = str(wv.get("direction") or "long").strip().lower()
    if direction not in {"long", "short"}:
        direction = "long"

    this_year = current_year or _today().year
    start_date = str(wv.get("start_date") or "").strip()
    days = str(wv.get("days_out") or "").strip()
    occurrence_timing = _occurrence_timing(start_date, days)
    completed_before_year = this_year
    if occurrence_timing.get("occurrence_status") == "completed":
        completed_before_year = this_year + 1
    elif occurrence_timing.get("occurrence_status") in {"active", "upcoming"}:
        try:
            completed_before_year = int(start_date[:4])
        except (TypeError, ValueError):
            completed_before_year = this_year

    facts = completed_outcome_facts(
        wv.get("yearly_results"),
        direction=direction,
        current_year=this_year,
        completed_before_year=completed_before_year,
    )
    stats = wv.get("stats") if isinstance(wv.get("stats"), Mapping) else {}
    engine_cumulative = _percent_number(stats.get("Cumulative Return"))
    years_text = str(wv.get("years") or "").strip()
    pe_cycle = str(wv.get("pe_cycle") or "cons").strip().lower()
    embedded_cycle = re.fullmatch(r"(pe[0-3])-(\d+)", years_text, re.I)
    if embedded_cycle:
        pe_cycle = embedded_cycle.group(1).lower()
    if pe_cycle not in {"cons", "pe0", "pe1", "pe2", "pe3"}:
        pe_cycle = "cons"

    trend_key = "Trend Short" if direction == "short" else "Trend Long"
    prior_trend_key = "Trend Short1" if direction == "short" else "Trend Long1"
    trend_score = _percent_number(stats.get(trend_key))
    prior_trend_score = _percent_number(stats.get(prior_trend_key))
    explicit_trend_availability = _optional_bool(stats.get("Trend Score Available"))
    if explicit_trend_availability is None:
        # Rolling-deploy compatibility: old ChartData4 responses had no availability
        # bit and used 0/0 when the provider was absent. Preserve real nonzero legacy
        # readings while refusing to call the ambiguous fallback a market conclusion.
        # No score fields at all means the feature is simply outside this payload, not
        # that an attempted provider lookup failed.
        if trend_score is None and prior_trend_score is None:
            trend_score_available = None
        elif trend_score is None or (
            trend_score == 0
            and (prior_trend_score is None or prior_trend_score == 0)
        ):
            trend_score_available = False
        else:
            trend_score_available = True
    else:
        trend_score_available = explicit_trend_availability and trend_score is not None
    if trend_score_available is not True:
        trend_score = None
        prior_trend_score = None
        trend_alignment = None
    elif trend_score > 60:
        trend_alignment = "aligned"
    elif trend_score < 40:
        trend_alignment = "against"
    else:
        trend_alignment = "neutral"

    selection_origin = str(wv.get("selection_origin") or "unknown").strip().lower()
    if selection_origin not in {"scanner", "user_defined"}:
        selection_origin = "unknown"
    earnings_date = str(stats.get("next_earnings_est") or "").strip()
    aggregate_stats_match_completed_sample = not facts.get(
        "stats_include_incomplete_observation"
    )
    occurrence_year = occurrence_timing.get("occurrence_year")
    occurrence_pe_cycle = _pe_cycle_for_year(occurrence_year)
    current_pe_cycle = _pe_cycle_for_year(this_year)
    occurrence_row_is_in_completed_sample = bool(
        occurrence_timing.get("occurrence_status") == "completed"
        and occurrence_year is not None
        and occurrence_year in facts.get("completed_years", [])
    )
    facts.update(
        {
            "symbol": str(wv.get("symbol") or "").strip().upper(),
            "company": str(wv.get("company") or "").strip(),
            "direction": direction,
            "start_date": start_date,
            "days": days,
            "selection_origin": selection_origin,
            # Preserve this exactly; it can be a plain lookback or a PE-cycle slice.
            "years": years_text,
            "pe_cycle": pe_cycle,
            "current_year": this_year,
            "current_pe_cycle": current_pe_cycle,
            "occurrence_pe_cycle": occurrence_pe_cycle,
            "occurrence_is_current_year": occurrence_year == this_year,
            "occurrence_matches_current_pe_cycle": (
                occurrence_pe_cycle is not None
                and occurrence_pe_cycle == current_pe_cycle
            ),
            "loaded_cycle_matches_occurrence": (
                pe_cycle == "cons"
                or occurrence_pe_cycle is None
                or pe_cycle == occurrence_pe_cycle
            ),
            "occurrence_row_is_in_completed_sample": occurrence_row_is_in_completed_sample,
            "sharpe_ratio": (
                _number(stats.get("Sharpe Ratio"))
                if aggregate_stats_match_completed_sample
                else None
            ),
            "tradewave_ratio": (
                _number(stats.get("Sharpe Ratio2"))
                if aggregate_stats_match_completed_sample
                else None
            ),
            "trend_score": trend_score,
            "prior_trend_score": prior_trend_score,
            "trend_alignment": trend_alignment,
            "trend_score_available": trend_score_available,
            "next_earnings_est": earnings_date,
            "earnings_in_window": _date_in_loaded_window(
                earnings_date, start_date, days
            ),
            "cumulative_return_pct": (
                engine_cumulative
                if engine_cumulative is not None and aggregate_stats_match_completed_sample
                else facts.get("derived_cumulative_return_pct")
            ),
            **occurrence_timing,
        }
    )
    return facts


def _percent_number(value: Any) -> Optional[float]:
    """Parse an allowlisted percentage stat such as ``"35%"`` or ``"1,234%"``."""

    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
    return _number(value)


def _month_day(date_text: str) -> Optional[str]:
    try:
        return _datetime.datetime.strptime(date_text, "%Y-%m-%d").strftime("%b %-d")
    except (TypeError, ValueError):
        return None


def _month_day_year(date_text: str) -> Optional[str]:
    try:
        date_value = _datetime.datetime.strptime(date_text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    return f"{date_value.strftime('%b')} {date_value.day}, {date_value.year}"


def build_opportunity_row_load_command(
    message: Any,
    opportunities: Any,
    *,
    market: Any = None,
    pe_cycle: Any = None,
) -> Optional[Dict[str, Any]]:
    """Resolve an ordinal table command against the exact visible row order.

    The client supplies its processed rows after filtering and sorting.  This command therefore
    bypasses both providers: a model never has to infer which list the user means, count rows, or
    choose a market.  ``spec`` is still validated by the normal ViewSpec boundary in ``chatbot.py``.
    """

    rank = requested_opportunity_row_rank(message)
    if rank is None:
        return None

    rows = opportunities if isinstance(opportunities, list) else []
    if not rows:
        return {
            "rank": rank,
            "spec": None,
            "reply": (
                f"<b>I can't load row #{rank} because the opportunity table has no visible rows yet.</b> "
                "As soon as its rows appear, the same command will load it."
            ),
        }
    if rank > len(rows):
        noun = "row" if len(rows) == 1 else "rows"
        return {
            "rank": rank,
            "spec": None,
            "reply": (
                f"<b>The current opportunity table has only {len(rows)} visible {noun}, so there is no row #{rank} to load.</b>"
            ),
        }

    row = rows[rank - 1]
    if not isinstance(row, Mapping):
        return {
            "rank": rank,
            "spec": None,
            "reply": f"<b>Row #{rank} is incomplete, so I did not send a partial setup to the chart.</b>",
        }

    symbol = str(row.get("symbol") or "").strip().upper()
    entry_date = str(row.get("date") or "").strip()
    days_value = _number(row.get("days_out"))
    days = int(days_value) if days_value is not None and days_value.is_integer() else 0
    if (
        not re.fullmatch(r"[A-Z0-9.-]{1,15}", symbol)
        or _month_day(entry_date) is None
        or not 1 <= days <= 366
    ):
        return {
            "rank": rank,
            "spec": None,
            "reply": f"<b>Row #{rank} is incomplete, so I did not send a partial setup to the chart.</b>",
        }

    raw_direction = str(row.get("direction") or "").strip().upper()
    direction = "short" if raw_direction in {"S", "SHORT"} else "long"
    spec: Dict[str, Any] = {
        "symbol": symbol,
        "entry_date": entry_date,
        "days_out": days,
    }
    market_text = str(market or "").strip()
    if market_text:
        spec["market"] = market_text
    cycle = str(pe_cycle or "").strip().lower()
    if cycle in {"cons", "consecutive", "pe0", "pe1", "pe2", "pe3"}:
        spec["pe_cycle"] = cycle

    stats = []
    average = _number(row.get("avg_profit"))
    if average is not None:
        stats.append(f"avg {_pct(average, signed=True, decimals=1)}")
    sharpe = _number(row.get("sharpe_ratio"))
    if sharpe is not None:
        stats.append(f"Sharpe {sharpe:.2f}".rstrip("0").rstrip("."))
    stat_line = f"<br>Table stats: {', '.join(stats)}." if stats else ""
    safe_symbol = html.escape(symbol)
    return {
        "rank": rank,
        "spec": spec,
        "reply": (
            f"<b>Loaded row #{rank}: {safe_symbol} {direction} - enter {_month_day(entry_date)}, "
            f"hold {days} calendar days.</b>{stat_line}"
        ),
    }


def _inclusive_end_date(start_date: str, days: str) -> Optional[str]:
    """TradeWave windows use calendar days and count the entry date as day 1."""

    try:
        start = _datetime.datetime.strptime(start_date, "%Y-%m-%d")
        count = int(days)
    except (TypeError, ValueError):
        return None
    if count < 1 or count > 366:
        return None
    return (start + _datetime.timedelta(days=count - 1)).strftime("%Y-%m-%d")


def _date_in_loaded_window(event_date: str, start_date: str, days: str) -> bool:
    """Return True when an ISO event date falls inside the inclusive current occurrence."""

    end_date = _inclusive_end_date(start_date, days)
    if not end_date:
        return False
    try:
        event = _datetime.datetime.strptime(event_date[:10], "%Y-%m-%d").date()
        start = _datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = _datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    return start <= event <= end


def _occurrence_timing(start_date: str, days: str) -> Dict[str, Any]:
    """Describe the current/next occurrence without treating a live row as historical."""

    end_date = _inclusive_end_date(start_date, days)
    if not end_date:
        return {"occurrence_status": "unknown"}
    try:
        start = _datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end = _datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"occurrence_status": "unknown"}
    today = _today()
    common = {
        "occurrence_start_date": start_date,
        "occurrence_end_date": end_date,
        # Presidential-cycle context is anchored to the entry year. This matters
        # for windows that cross New Year: a Dec 2025 entry remains a PE+1
        # occurrence even while it is active in Jan 2026.
        "occurrence_year": start.year,
    }
    if today < start:
        return {
            **common,
            "occurrence_status": "upcoming",
            "days_until_start": (start - today).days,
        }
    if today <= end:
        return {
            **common,
            "occurrence_status": "active",
            "occurrence_day_number": (today - start).days + 1,
            "calendar_days_remaining": (end - today).days,
            "calendar_dates_remaining_including_today": (end - today).days + 1,
        }
    return {
        **common,
        "occurrence_status": "completed",
        "days_since_end": (today - end).days,
    }


def _pct(value: Optional[float], *, signed: bool = False, decimals: int = 0) -> str:
    if value is None:
        return ""
    rounded = round(value, decimals)
    if rounded == 0:
        rounded = 0.0
    if signed:
        return f"{rounded:+.{decimals}f}%"
    return f"{rounded:.{decimals}f}%"


_PE_LABELS = {
    "pe0": ("PE", "election years"),
    "pe1": ("PE+1", "post-election years"),
    "pe2": ("PE+2", "midterm years"),
    "pe3": ("PE+3", "pre-election years"),
}

_PE_YEAR_DESCRIPTIONS = {
    "pe0": "election year",
    "pe1": "post-election year",
    "pe2": "midterm year",
    "pe3": "pre-election year",
}


def _pe_cycle_for_year(year: Any) -> Optional[str]:
    """Return the presidential-cycle phase for an occurrence's entry year."""

    try:
        year_int = int(str(year))
    except (TypeError, ValueError):
        return None
    if not 1900 <= year_int <= 2200:
        return None
    return f"pe{year_int % 4}"


def _pe_year_text(cycle: Any) -> Optional[str]:
    cycle_text = str(cycle or "").strip().lower()
    if cycle_text not in _PE_LABELS:
        return None
    return f"{_PE_LABELS[cycle_text][0]} ({_PE_YEAR_DESCRIPTIONS[cycle_text]})"


def _pe_observation_text(cycle: Any) -> Optional[str]:
    """Return a compact cycle label that always includes the plain-English phase."""

    cycle_text = str(cycle or "").strip().lower()
    if cycle_text not in _PE_LABELS:
        return None
    short = _PE_LABELS[cycle_text][0]
    phase = _PE_YEAR_DESCRIPTIONS[cycle_text].removesuffix(" year")
    return f"{short} ({phase})"


def _cycle_switch_link(cycle: Any) -> str:
    """Render a validated, client-handled comparison link for the Wave Viewer."""

    cycle_text = str(cycle or "").strip().lower()
    if cycle_text == "cons":
        label = "Switch chart to consecutive years"
    elif cycle_text in _PE_LABELS:
        label = f"Switch chart to {_pe_observation_text(cycle_text)}"
    else:
        return ""
    return (
        '<a href="#" class="tara-analysis-link" '
        f'data-action="switch-viewer-cycle" data-cycle="{cycle_text}">{label}</a>'
    )


def _pe_sample_description(facts: Mapping[str, Any]) -> Optional[str]:
    """Translate a PE observation count into its calendar-history footprint.

    A phase occurs once every four calendar years.  We call it a complete cycle
    sample only when the supplied completed rows are contiguous four-year
    observations in the selected phase; sparse data must not imply missing
    observations were present.
    """

    cycle = str(facts.get("pe_cycle") or "cons").strip().lower()
    cycle_text = _pe_observation_text(cycle)
    count = int(facts.get("sample_size") or 0)
    if cycle_text is None or count <= 0:
        return None

    completed_years = []
    for value in facts.get("completed_years") or []:
        try:
            completed_years.append(int(value))
        except (TypeError, ValueError):
            return (
                f"The loaded sample contains {count} completed {cycle_text} "
                f"observation{'s' if count != 1 else ''}; this phase occurs once every four calendar years."
            )
    completed_years = sorted(set(completed_years))
    is_complete_cycle_sequence = (
        len(completed_years) == count
        and all(_pe_cycle_for_year(year) == cycle for year in completed_years)
        and all(
            later - earlier == 4
            for earlier, later in zip(completed_years, completed_years[1:])
        )
    )
    if is_complete_cycle_sequence:
        calendar_years = count * 4
        return (
            f"Over the {calendar_years} calendar years represented by this PE lookback, there "
            f"{'is' if count == 1 else 'are'} {count} completed {cycle_text} "
            f"observation{'s' if count != 1 else ''}, one every four years."
        )
    return (
        f"The loaded sample contains {count} completed {cycle_text} "
        f"observation{'s' if count != 1 else ''}; this phase occurs once every four calendar years."
    )


def _observation_label(facts: Mapping[str, Any], count: int, *, completed: bool = True) -> str:
    cycle = str(facts.get("pe_cycle") or "cons")
    prefix = "completed " if completed else ""
    if cycle in _PE_LABELS:
        noun = "observation" if count == 1 else "observations"
        return f"{count} {prefix}{_pe_observation_text(cycle)} {noun}"
    noun = "year" if count == 1 else "years"
    return f"{count} {prefix}{noun}"


def _recent_observation_label(facts: Mapping[str, Any], count: int) -> str:
    cycle = str(facts.get("pe_cycle") or "cons")
    if cycle in _PE_LABELS:
        return f"the most recent {count} {_pe_observation_text(cycle)} observations"
    return f"the most recent {count} completed years"


def _pattern_line(facts: Mapping[str, Any]) -> str:
    symbol = html.escape(str(facts.get("symbol") or "This pattern"))
    direction = "short" if facts.get("direction") == "short" else "long"
    start_md = _month_day(str(facts.get("start_date") or ""))
    end_date = _inclusive_end_date(
        str(facts.get("start_date") or ""), str(facts.get("days") or "")
    )
    end_md = _month_day(end_date or "")
    days = str(facts.get("days") or "")

    if start_md and end_md and days:
        return (
            f"<b>{symbol} {direction}</b> runs {start_md} to {end_md} "
            f"({html.escape(days)} calendar days, with the entry date counted as day 1)."
        )
    return f"<b>{symbol} {direction}</b> is the pattern currently loaded."


def _bar_chart_line(facts: Mapping[str, Any]) -> str:
    direction = "short" if facts.get("direction") == "short" else "long"
    n = int(facts.get("sample_size") or 0)
    wins = int(facts.get("profitable_years") or 0)
    losses = int(facts.get("losing_years") or 0)

    if n:
        record = (
            f"It made money in {wins} of {_observation_label(facts, n)} "
            f"({_pct(facts.get('win_rate_pct'))})"
        )
        avg_win = _pct(facts.get("avg_profitable_return_pct"), signed=True, decimals=2)
        avg_loss = _pct(facts.get("avg_losing_return_pct"), signed=True, decimals=2)
        averages = []
        if avg_win:
            averages.append(f"average profitable trade {avg_win}")
        if avg_loss:
            averages.append(f"average losing trade {avg_loss}")
        if averages:
            record += "; " + ", ".join(averages)
        record += "."
    else:
        record = "Each completed historical trade gets one bar."

    metrics: List[str] = []
    if facts.get("sharpe_ratio") is not None:
        metrics.append(f"Sharpe {facts['sharpe_ratio']:.2f}")
    if facts.get("cumulative_return_pct") is not None:
        metrics.append(
            "cumulative short return " + _pct(facts["cumulative_return_pct"], signed=True)
            if direction == "short"
            else "cumulative return " + _pct(facts["cumulative_return_pct"], signed=True)
        )
    if metrics:
        record += " " + "; ".join(metrics).capitalize() + "."

    if direction == "short":
        colors = (
            "The bars show the underlying move: red/down years are profitable short trades, "
            "while green/up years are losing short trades."
        )
    else:
        colors = (
            "The bars show the underlying move: green/up years are profitable long trades, "
            "while red/down years are losing long trades."
        )
    return f"<b>Top Gain-Loss chart:</b> {record} {colors}"


def _price_chart_line(screen: Mapping[str, Any], facts: Mapping[str, Any]) -> str:
    mode = screen.get("price_chart_mode")
    if mode == "historical":
        year = html.escape(str(screen.get("price_chart_year") or "the selected year"))
        base = (
            f"<b>Bottom Price Chart:</b> it is showing {year}, including the historical "
            "entry/exit markers and shaded trade window."
        )
    elif mode == "active_trade":
        base = (
            "<b>Bottom Price Chart:</b> it is showing the active current-year trade through "
            "the latest available close."
        )
    else:
        base = "<b>Bottom Price Chart:</b> it is showing current price action."

    projections: List[str] = []
    if screen.get("selected_projection_visible"):
        lookback = html.escape(str(screen.get("selected_lookback") or facts.get("years") or "selected"))
        projections.append(f"the gold dashed line uses the selected {lookback}-year seasonal history")
    if screen.get("full_history_projection_visible"):
        max_years = html.escape(str(screen.get("full_history_years") or "full available"))
        projections.append(f"the purple dashed line uses the full {max_years}-year history")
    if projections:
        projection_text = " and ".join(projections)
        base += " " + projection_text[:1].upper() + projection_text[1:]
        base += ". These are historical seasonal guides, not guaranteed forecasts."
    selected_path = screen.get("selected_window_path")
    full_path = screen.get("full_history_window_path")
    if selected_path == "supports" and full_path == "supports":
        base += " Both normalized seasonal histories move with this setup's direction across the loaded window."
    elif selected_path == "supports" and full_path == "against":
        base += " The selected-history curve supports the setup, but the full-history curve disagrees, making the seasonal direction lookback-sensitive."
    elif selected_path == "against" and full_path == "supports":
        base += " The full-history curve supports the setup, but the selected-history curve currently disagrees."
    return base


def _bottom_panel_line(screen: Mapping[str, Any], facts: Mapping[str, Any]) -> str:
    slide = screen.get("active_bottom_slide")
    if slide == "price_chart":
        return _price_chart_line(screen, facts)
    if slide == "wave_stats":
        n = int(facts.get("sample_size") or 0)
        sample = f" across the same {n} completed years" if n else ""
        return (
            "<b>Bottom Wave Stats:</b> it breaks down the loaded window's returns, consistency, "
            f"risk and cumulative performance{sample}."
        )
    if slide == "trend_chart":
        return (
            "<b>Bottom Trend Chart:</b> it shows the historical seasonal path for the selected "
            "lookback, with the loaded trade window and summary statistics."
        )
    return (
        "<b>Bottom viewer:</b> it has Trend Chart, Wave Stats and Price Chart slides; the current "
        "client did not identify which slide is active, so all three are available for this pattern."
    )


def build_screen_overview_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any,
    *,
    opportunities: Any = None,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Return a complete deterministic explanation of the visible TradeWave screen."""

    if not is_screen_overview_question(message):
        return None

    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    screen = normalize_screen_context(screen_context)

    if not facts.get("symbol"):
        count = screen.get("opportunity_rows")
        count_text = f" {count}" if isinstance(count, int) and count > 0 else ""
        return (
            f"<b>Opportunity Table:</b> the left panel currently ranks{count_text} seasonal setups by Sharpe. "
            "No pattern is loaded yet, so the chart panels do not have a specific trade to explain."
        )

    lines = [_pattern_line(facts), _bar_chart_line(facts), _bottom_panel_line(screen, facts)]

    if screen.get("opportunity_table_visible"):
        count = screen.get("opportunity_rows")
        if not isinstance(count, int):
            count = len(opportunities) if isinstance(opportunities, list) else 0
        count_text = f" shows {count} rows and" if count > 0 else ""
        lines.append(
            f"<b>Left Opportunity Table:</b> it{count_text} ranks the available setups by Sharpe, best first."
        )

    return "<br>".join(lines)


def build_bar_semantics_reply(
    message: Any,
    wave_viewer: Any,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Explain the chart's color/direction contract without asking the LLM to infer it."""

    if not is_bar_semantics_question(message):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    if not facts.get("symbol"):
        return (
            "The bars show the underlying price move: green is up and red is down. "
            "Green is profitable for a long setup; red is profitable for a short setup."
        )

    n = int(facts.get("sample_size") or 0)
    wins = int(facts.get("profitable_years") or 0)
    record = (
        f" It was profitable in {wins} of {_observation_label(facts, n)} "
        f"({_pct(facts.get('win_rate_pct'))})."
        if n
        else ""
    )
    if facts.get("direction") == "short":
        return (
            "<b>On this short setup, the red/down bars are the profitable years.</b> "
            "The bar color shows the underlying move, so green/up bars are losing short years."
            + record
        )
    return (
        "<b>On this long setup, the green/up bars are the profitable years.</b> "
        "Red/down bars are losing long years." + record
    )


def build_direction_reply(
    message: Any,
    wave_viewer: Any,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Explain why the loaded record is classified long or short from completed rows."""

    if not is_pattern_direction_question(message, wave_viewer):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    n = int(facts.get("sample_size") or 0)
    if not facts.get("symbol") or not n:
        return None
    symbol = html.escape(str(facts["symbol"]))
    direction = str(facts.get("direction") or "long")
    wins = int(facts.get("profitable_years") or 0)
    if direction == "short":
        underlying_count = int(facts.get("underlying_down_years") or 0)
        move = "fell"
        color = "red/down"
    else:
        underlying_count = int(facts.get("underlying_up_years") or 0)
        move = "rose"
        color = "green/up"
    return (
        f"<b>{symbol} is labeled {direction} because the underlying {move} in "
        f"{underlying_count} of {_observation_label(facts, n)}.</b> Those {color} observations "
        f"become {wins} profitable {direction} outcomes ({_pct(facts.get('win_rate_pct'))}); "
        "TradeWave derives direction from the completed per-year net returns, not from a forecast."
    )


def build_trend_alignment_reply(
    message: Any,
    wave_viewer: Any,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Define Trend Alignment and explain the loaded reading in plain language."""

    if not is_trend_alignment_question(message):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    definition = (
        "<b>Trend Alignment compares recent price movement with the loaded seasonal trade "
        "direction.</b> For a long pattern it asks whether price has been moving upward; for a "
        "short pattern it asks whether price has been moving downward. It uses roughly the last "
        "one to two weeks, not the historical seasonal record."
    )
    if not facts.get("symbol"):
        return (
            definition
            + " Above 60 is Aligned, 40–60 is Neutral, and below 40 is Against. Against means "
            "recent movement has not been moving strongly in the seasonal setup's direction."
        )

    direction = "short" if facts.get("direction") == "short" else "long"
    symbol = html.escape(str(facts.get("symbol") or "This symbol"))
    actual = _trend_alignment_plain_language(facts)
    return (
        definition
        + f"<br><b>For this {symbol} {direction} setup:</b> {actual}. "
        "Above 60 is Aligned, 40–60 is Neutral, and below 40 is Against. This is a current-momentum "
        "confirmation check; it does not change the pattern's win rate or predict the outcome."
    )


def _analysis_record_line(facts: Mapping[str, Any]) -> str:
    symbol = html.escape(str(facts.get("symbol") or "This pattern"))
    direction = "short" if facts.get("direction") == "short" else "long"
    start_md = _month_day(str(facts.get("start_date") or ""))
    end_date = _inclusive_end_date(
        str(facts.get("start_date") or ""), str(facts.get("days") or "")
    )
    end_md = _month_day(end_date or "")
    days = html.escape(str(facts.get("days") or ""))
    if start_md and end_md and days:
        identity = (
            f"{symbol} {direction}, {start_md} to {end_md} "
            f"({days} calendar days; entry day is day 1)"
        )
    else:
        identity = f"{symbol} {direction}"

    n = int(facts.get("sample_size") or 0)
    wins = int(facts.get("profitable_years") or 0)
    details = []
    if n:
        first_year = facts.get("first_completed_year")
        latest_year = facts.get("latest_completed_year")
        span = (
            f" from {first_year} through {latest_year}"
            if first_year is not None and latest_year is not None
            else ""
        )
        details.append(
            f"profitable in {wins} of {_observation_label(facts, n)} "
            f"({_pct(facts.get('win_rate_pct'))}){span}"
        )
    if facts.get("avg_trade_return_pct") is not None:
        details.append(
            "gross average return " + _pct(facts["avg_trade_return_pct"], signed=True, decimals=2)
            + " per trade"
        )
    if facts.get("sharpe_ratio") is not None:
        details.append(
            f"Sharpe {facts['sharpe_ratio']:.2f} for cross-year consistency"
        )
    suffix = ": " + ", ".join(details) + "." if details else "."
    return f"<b>Historical record:</b> {identity}{suffix}"


def _analysis_payoff_line(facts: Mapping[str, Any]) -> Optional[str]:
    details = []
    avg_win = facts.get("avg_profitable_return_pct")
    avg_loss = facts.get("avg_losing_return_pct")
    if avg_win is not None:
        details.append(f"profitable years averaged {_pct(avg_win, signed=True, decimals=2)}")
    if avg_loss is not None:
        details.append(f"losing years averaged {_pct(avg_loss, signed=True, decimals=2)}")
    ratio = facts.get("payoff_ratio")
    if ratio is not None:
        details.append(f"average win/loss magnitude was {ratio:.2f}:1")
    cumulative = facts.get("cumulative_return_pct")
    if cumulative is not None:
        details.append(
            "cumulative "
            + ("short " if facts.get("direction") == "short" else "")
            + "return was "
            + _pct(cumulative, signed=True, decimals=0)
        )
    if not details:
        return None
    return "<b>Payoff:</b> " + "; ".join(details) + "."


def _analysis_recent_line(facts: Mapping[str, Any]) -> Optional[str]:
    recent_n = int(facts.get("recent_sample_size") or 0)
    prior_n = int(facts.get("prior_sample_size") or 0)
    if recent_n < 5 or prior_n < 5:
        return None
    recent_wins = int(facts.get("recent_profitable_years") or 0)
    prior_wins = int(facts.get("prior_profitable_years") or 0)
    recent_rate = facts.get("recent_win_rate_pct")
    prior_rate = facts.get("prior_win_rate_pct")
    recent_avg = facts.get("recent_avg_trade_return_pct")
    prior_avg = facts.get("prior_avg_trade_return_pct")

    details = [
        f"latest {recent_n}: {recent_wins} profitable ({_pct(recent_rate)})"
    ]
    if recent_avg is not None:
        details.append(
            "gross average " + _pct(recent_avg, signed=True, decimals=2)
        )
    details.append(
        f"earlier {prior_n}: {prior_wins} profitable ({_pct(prior_rate)})"
        + (
            ", gross average " + _pct(prior_avg, signed=True, decimals=2)
            if prior_avg is not None
            else ""
        )
    )
    comparison = ""
    if None not in (recent_rate, prior_rate, recent_avg, prior_avg):
        if recent_rate <= prior_rate - 15 and recent_avg < prior_avg:
            comparison = " The latest non-overlapping slice was weaker in this sample."
        elif recent_rate >= prior_rate + 15 and recent_avg > prior_avg:
            comparison = " The latest non-overlapping slice was stronger in this sample."
        else:
            comparison = " The two non-overlapping slices give a mixed comparison."
    return "<b>Recent versus earlier:</b> " + "; ".join(details) + "." + comparison


def _analysis_range_line(facts: Mapping[str, Any]) -> Optional[str]:
    details = []
    median = facts.get("median_trade_return_pct")
    stdev = facts.get("standard_deviation_pct")
    if median is not None:
        details.append(f"median trade {_pct(median, signed=True, decimals=2)}")
    if stdev is not None:
        details.append(f"year-to-year standard deviation {_pct(stdev, decimals=2)}")
    if facts.get("best_year") is not None and facts.get("best_trade_return_pct") is not None:
        details.append(
            f"best year {facts['best_year']} ({_pct(facts['best_trade_return_pct'], signed=True, decimals=2)})"
        )
    if facts.get("worst_year") is not None and facts.get("worst_trade_return_pct") is not None:
        details.append(
            f"worst year {facts['worst_year']} ({_pct(facts['worst_trade_return_pct'], signed=True, decimals=2)})"
        )
    if not details:
        return None
    line = "<b>Range:</b> " + "; ".join(details) + "."
    if facts.get("direction") == "short":
        line += " Red/down bars are the profitable short years because the bars show the underlying move."
    return line


def _analysis_bottom_line(facts: Mapping[str, Any]) -> str:
    symbol = html.escape(str(facts.get("symbol") or "This pattern"))
    direction = "short" if facts.get("direction") == "short" else "long"
    win_rate = facts.get("win_rate_pct")
    avg_return = facts.get("avg_trade_return_pct")
    payoff = facts.get("payoff_ratio")
    sharpe = facts.get("sharpe_ratio")
    recent_rate = facts.get("recent_win_rate_pct")
    prior_rate = facts.get("prior_win_rate_pct")
    recent_avg = facts.get("recent_avg_trade_return_pct")
    prior_avg = facts.get("prior_avg_trade_return_pct")

    if avg_return is None or avg_return <= 0 or (sharpe is not None and sharpe < 0):
        lead = f"{symbol}'s historical {direction} record is mixed rather than clearly favorable"
    elif win_rate is not None and win_rate >= 75 and payoff is not None and payoff >= 1:
        lead = f"{symbol}'s loaded {direction} sample is historically favorable on both win frequency and payoff"
    elif win_rate is not None and win_rate >= 70:
        lead = f"{symbol}'s loaded {direction} sample is driven mainly by frequent winning observations"
    elif payoff is not None and payoff >= 1.5:
        lead = f"{symbol}'s loaded {direction} sample is driven more by payoff size than win frequency"
    else:
        lead = f"{symbol}'s historical {direction} record is positive but uneven"

    cautions: List[str] = []
    if (
        recent_rate is not None
        and prior_rate is not None
        and recent_avg is not None
        and prior_avg is not None
        and int(facts.get("recent_sample_size") or 0) >= 5
        and int(facts.get("prior_sample_size") or 0) >= 5
        and recent_rate <= prior_rate - 15
        and recent_avg < prior_avg
    ):
        cautions.append("the latest non-overlapping slice was weaker in this sample")
    if sharpe is not None and 0 <= sharpe < 1:
        cautions.append("cross-year consistency is moderate rather than exceptional")
    n = int(facts.get("sample_size") or 0)
    if n < 10:
        cautions.append("the sample is small")
    elif n < 20:
        cautions.append("the sample is modest")

    suffix = ", but " + " and ".join(cautions) if cautions else ""
    return f"<b>Bottom line:</b> {lead}{suffix}."


def _analysis_driver_line(facts: Mapping[str, Any]) -> Optional[str]:
    n = int(facts.get("sample_size") or 0)
    wins = int(facts.get("profitable_years") or 0)
    avg_win = facts.get("avg_profitable_return_pct")
    avg_loss = facts.get("avg_losing_return_pct")
    payoff = facts.get("payoff_ratio")
    win_rate = facts.get("win_rate_pct")
    breakeven = facts.get("breakeven_win_rate_pct")
    if not n:
        return None

    details = [
        f"{wins} profitable outcomes in {_observation_label(facts, n)}"
    ]
    if avg_win is not None and avg_loss is not None:
        details.append(
            f"average winner {_pct(avg_win, signed=True, decimals=2)} versus "
            f"average loser {_pct(avg_loss, signed=True, decimals=2)}"
        )
    if payoff is not None:
        details.append(f"{payoff:.2f}:1 average payoff ratio")

    sentence = "<b>What drives it:</b> " + "; ".join(details) + "."
    if (
        win_rate is not None
        and breakeven is not None
        and abs(win_rate - breakeven) >= 10
    ):
        sentence += (
            f" With those average outcome sizes, the before-cost break-even hit rate is about "
            f"{_pct(breakeven)}, versus the observed {_pct(win_rate)}."
        )
    cumulative = facts.get("cumulative_return_pct")
    if cumulative is not None:
        sentence += (
            " Hypothetical repeated-window compounded "
            + ("short " if facts.get("direction") == "short" else "")
            + f"return was {_pct(cumulative, signed=True, decimals=0)} before costs."
        )
    return sentence


def _analysis_robustness_line(facts: Mapping[str, Any]) -> Optional[str]:
    median = facts.get("median_trade_return_pct")
    avg_without_best = facts.get("avg_without_best_year_pct")
    avg_return = facts.get("avg_trade_return_pct")
    stdev = facts.get("standard_deviation_pct")
    if median is None and avg_without_best is None and stdev is None:
        return None

    details = []
    if median is not None:
        details.append(f"median outcome {_pct(median, signed=True, decimals=2)}")
    if avg_without_best is not None:
        details.append(
            "average without the single best year "
            + _pct(avg_without_best, signed=True, decimals=2)
        )
    if stdev is not None:
        details.append(f"year-to-year standard deviation {_pct(stdev, decimals=2)}")

    if median is not None and median > 0 and avg_without_best is not None and avg_without_best > 0:
        read = " The positive average does not depend on one standout year within this loaded sample."
    elif avg_return is not None and avg_return > 0 and avg_without_best is not None and avg_without_best <= 0:
        read = " The positive average depends heavily on the single best year."
    elif avg_return is not None and avg_return > 0 and median is not None and median <= 0:
        read = " The average is positive even though the typical observation was not, which signals outlier dependence."
    else:
        read = ""
    return "<b>Robustness:</b> " + "; ".join(details) + "." + read


def _analysis_risk_line(facts: Mapping[str, Any]) -> Optional[str]:
    n = int(facts.get("sample_size") or 0)
    losses = int(facts.get("losing_years") or 0)
    if not n:
        return None
    if losses == 0:
        return (
            f"<b>Ending-loss profile:</b> there were no losing observations in {_observation_label(facts, n)}, "
            "but a perfect historical sample does not establish a loss-free future."
        )

    details = [f"{losses} losing observations"]
    avg_loss = facts.get("avg_losing_return_pct")
    if avg_loss is not None:
        details.append(f"average loss {_pct(avg_loss, signed=True, decimals=2)}")
    if facts.get("worst_year") is not None and facts.get("worst_trade_return_pct") is not None:
        details.append(
            f"worst year {facts['worst_year']} "
            f"({_pct(facts['worst_trade_return_pct'], signed=True, decimals=2)})"
        )
    longest = int(facts.get("longest_losing_streak") or 0)
    if longest > 1:
        details.append(f"longest losing streak {longest}")
    line = "<b>Ending-loss profile:</b> " + "; ".join(details) + "."
    ending = int(facts.get("ending_losing_streak") or 0)
    if ending > 1:
        line += f" The sample ends with {ending} consecutive losing observations."
    return line


def _trend_alignment_plain_language(facts: Mapping[str, Any]) -> str:
    """Explain current momentum versus the seasonal direction without jargon."""

    direction = "short" if facts.get("direction") == "short" else "long"
    trend_name = "Trend Short" if direction == "short" else "Trend Long"
    expected_move = "downward" if direction == "short" else "upward"
    score = facts.get("trend_score")
    alignment = facts.get("trend_alignment")

    if facts.get("trend_score_available") is False or score is None:
        return (
            f"current momentum confirmation is unavailable: TradeWave did not receive a usable "
            f"{trend_name} reading to compare recent price movement with the seasonal {direction} "
            "direction"
        )
    score_text = f"{score:.0f}/100"
    if alignment == "aligned":
        return (
            f"current momentum confirms the seasonal {direction} direction: {trend_name} is "
            f"{score_text} (Aligned), meaning price movement over roughly the last one to two weeks "
            f"has been moving {expected_move}, the same direction as the setup"
        )
    if alignment == "against":
        return (
            f"current momentum does not confirm the seasonal {direction} direction: {trend_name} is "
            f"{score_text} (Against), meaning price movement over roughly the last one to two weeks "
            f"has not been moving strongly {expected_move} with the setup"
        )
    return (
        f"current momentum gives no clear confirmation of the seasonal {direction} direction: "
        f"{trend_name} is {score_text} (Neutral), meaning price movement over roughly the last one "
        f"to two weeks is mixed rather than clearly moving {expected_move} with the setup"
    )


def _analysis_path_line(facts: Mapping[str, Any], screen: Mapping[str, Any]) -> Optional[str]:
    details: List[str] = []
    status = facts.get("occurrence_status")
    if status == "active":
        end_md = _month_day(str(facts.get("occurrence_end_date") or ""))
        details.append(
            "the current occurrence is active"
            + (f" through {end_md}" if end_md else "")
            + ", and its live row remains outside the completed historical record"
        )
    elif status == "upcoming":
        days_until = int(facts.get("days_until_start") or 0)
        details.append(
            f"the next occurrence starts in {days_until} calendar day"
            + ("" if days_until == 1 else "s")
        )
    selected = screen.get("selected_window_path")
    full = screen.get("full_history_window_path")
    selected_years = html.escape(str(screen.get("selected_lookback") or facts.get("years") or "selected"))
    full_years = html.escape(str(screen.get("full_history_years") or "full"))

    if selected == "supports" and full == "supports":
        details.append(
            f"the selected {selected_years}-year and full {full_years}-year normalized seasonal curves "
            "both move with the trade direction across this window"
        )
    elif selected == "supports" and full == "against":
        details.append(
            f"the selected {selected_years}-year curve supports the setup, but the full {full_years}-year "
            "curve moves against it, so the direction is lookback-sensitive"
        )
    elif selected == "against" and full == "supports":
        details.append(
            f"the full {full_years}-year curve supports the setup, but the selected {selected_years}-year "
            "curve does not"
        )
    elif selected == "against":
        details.append("the selected-history normalized seasonal curve moves against the loaded direction")
    elif selected == "supports":
        details.append("the selected-history normalized seasonal curve moves with the loaded direction")

    if facts.get("trend_score_available") is False or facts.get("trend_score") is not None:
        details.append(_trend_alignment_plain_language(facts))

    sharpe = facts.get("sharpe_ratio")
    twr = facts.get("tradewave_ratio")
    if twr is not None and sharpe is not None and twr >= sharpe + 0.25:
        details.append(
            f"TWR {twr:.2f} is above Sharpe {sharpe:.2f}, meaning favorable intrawindow movement "
            "was stronger than the final exit returns alone show"
        )

    if facts.get("earnings_in_window"):
        details.append(
            "the estimated earnings date "
            + html.escape(str(facts.get("next_earnings_est"))[:10])
            + " falls inside this occurrence"
        )

    if not details:
        return None
    return "<b>Current context:</b> " + "; ".join(details) + "."


def _analysis_compact_read_line(facts: Mapping[str, Any]) -> str:
    """Lead a broad analysis with the decision-relevant record, not a metric dump."""

    symbol = html.escape(str(facts.get("symbol") or "This pattern"))
    direction = "short" if facts.get("direction") == "short" else "long"
    start_md = _month_day(str(facts.get("start_date") or ""))
    end_md = _month_day(
        _inclusive_end_date(
            str(facts.get("start_date") or ""), str(facts.get("days") or "")
        )
        or ""
    )
    days = html.escape(str(facts.get("days") or ""))
    if start_md and end_md and days:
        setup = (
            f"{symbol} {direction}, {start_md} to {end_md} "
            f"({days} calendar days; entry day is day 1)"
        )
    else:
        setup = f"{symbol} {direction}"

    n = int(facts.get("sample_size") or 0)
    wins = int(facts.get("profitable_years") or 0)
    losses = int(facts.get("losing_years") or 0)
    first_year = facts.get("first_completed_year")
    latest_year = facts.get("latest_completed_year")
    span = (
        f", {first_year}-{latest_year}"
        if first_year is not None and latest_year is not None
        else ""
    )
    clauses = [
        f"profitable in {wins} of {_observation_label(facts, n)} "
        f"({_pct(facts.get('win_rate_pct'))}{span})"
    ]
    avg_return = facts.get("avg_trade_return_pct")
    median = facts.get("median_trade_return_pct")
    if avg_return is not None:
        clauses.append(
            "gross average " + _pct(avg_return, signed=True, decimals=2)
        )
    if median is not None:
        clauses.append("median " + _pct(median, signed=True, decimals=2))
    sharpe = facts.get("sharpe_ratio")
    if sharpe is not None:
        twr = facts.get("tradewave_ratio")
        if twr is not None:
            clauses.append(
                f"Sharpe {sharpe:.2f} (final returns); TWR {twr:.2f} (MFE)"
            )
        else:
            clauses.append(f"Sharpe {sharpe:.2f} for cross-year consistency")

    win_rate = facts.get("win_rate_pct")
    payoff = facts.get("payoff_ratio")
    if avg_return is None or avg_return <= 0:
        if win_rate is not None and win_rate >= 70:
            verdict = "Frequent winners did not produce a positive gross average"
        else:
            verdict = "The historical evidence is mixed"
    elif median is not None and median <= 0:
        verdict = "The gross average was positive, but the typical observation was not"
    elif losses == 0:
        verdict = "Every completed observation was profitable"
    elif losses == 1:
        verdict = "The historical record was positive in all but one completed observation"
    elif (
        win_rate is not None
        and win_rate >= 75
        and wins >= 2
        and losses >= 2
        and payoff is not None
        and payoff >= 1
    ):
        verdict = "Win frequency and payoff were favorable"
    elif wins >= 2 and losses >= 2 and payoff is not None and payoff >= 1.5:
        verdict = "The positive history was driven more by payoff size than win frequency"
    else:
        verdict = "The loaded sample was positive but uneven"

    if n < 10:
        verdict += "; the sample is small."
    elif n < 20:
        verdict += "; the sample is modest."
    else:
        verdict += "."
    if direction == "short":
        verdict += " Red/down years are the profitable short outcomes."
    return f"<b>Read:</b> {setup}: " + "; ".join(clauses) + ". " + verdict


def _normalized_ai_analysis(wave_viewer: Any) -> Optional[Dict[str, Any]]:
    """Accept only the small server-derived ML context used in analysis prose."""

    if not isinstance(wave_viewer, Mapping):
        return None
    raw = wave_viewer.get("ai_analysis")
    if not isinstance(raw, Mapping):
        return None
    status = str(raw.get("status") or "").strip().lower()
    mode = str(raw.get("mode") or "").strip().lower()
    if status not in {
        "available",
        "unavailable",
        "too_early",
        "after_entry",
        "unsupported_duration",
    } or mode not in {"pattern", "checkpoints"}:
        return None
    full_days_number = _number(raw.get("full_pattern_calendar_days"))
    if full_days_number is None or not full_days_number.is_integer():
        return None
    full_days = int(full_days_number)
    if not 1 <= full_days <= 366:
        return None
    result: Dict[str, Any] = {
        "status": status,
        "mode": mode,
        "full_pattern_calendar_days": full_days,
    }
    days_to_entry = _number(raw.get("days_to_entry"))
    if days_to_entry is not None and days_to_entry.is_integer() and days_to_entry >= 0:
        result["days_to_entry"] = int(days_to_entry)

    horizons = []
    for item in raw.get("horizons") or ():
        if not isinstance(item, Mapping):
            continue
        horizon_number = _number(item.get("calendar_days"))
        if horizon_number is None or not horizon_number.is_integer():
            continue
        horizon = int(horizon_number)
        if not 1 <= horizon <= 90:
            continue
        cleaned: Dict[str, Any] = {"calendar_days": horizon}
        ai_score = _number(item.get("ai_score"))
        win_probability = _number(item.get("win_probability"))
        predicted_return = _number(item.get("predicted_return_pct"))
        predicted_mfe = _number(item.get("predicted_mfe_pct"))
        if ai_score is not None and 0 <= ai_score <= 100:
            cleaned["ai_score"] = ai_score
        if win_probability is not None and 0 <= win_probability <= 1:
            cleaned["win_probability"] = win_probability
        if predicted_return is not None and -1000 <= predicted_return <= 1000:
            cleaned["predicted_return_pct"] = predicted_return
        if predicted_mfe is not None and -1000 <= predicted_mfe <= 1000:
            cleaned["predicted_mfe_pct"] = predicted_mfe
        if len(cleaned) > 1:
            horizons.append(cleaned)
    if horizons:
        result["horizons"] = sorted(horizons, key=lambda item: item["calendar_days"])
    return result


def _ai_probability_comparison(ai_probability: float, historical_pct: Any) -> str:
    if historical_pct is None:
        return ""
    ai_pct = ai_probability * 100
    difference = ai_pct - float(historical_pct)
    if abs(difference) < 0.5:
        return "about level with the rounded historical rate"
    points = max(1, int(round(abs(difference))))
    noun = "percentage point" if points == 1 else "percentage points"
    relation = "above" if difference > 0 else "below"
    return f"{points} {noun} {relation} the historical rate"


def _analysis_ai_context_line(
    facts: Mapping[str, Any], wave_viewer: Any
) -> Optional[str]:
    """Explain ML estimates without blending them into the historical record."""

    context = _normalized_ai_analysis(wave_viewer)
    if context is None:
        return None
    status = context["status"]
    if status == "too_early":
        days_to_entry = context.get("days_to_entry")
        timing = (
            f"; entry is {days_to_entry} calendar days away"
            if isinstance(days_to_entry, int)
            else ""
        )
        return (
            "<b>AI context:</b> No current-condition AI reading is shown yet"
            + timing
            + ". TradeWave waits until the setup is within five calendar days of entry so the inputs are not stale."
        )
    if status == "after_entry":
        return (
            "<b>AI context:</b> No new entry-time AI reading is added after the occurrence starts; "
            "using post-entry data would not be a clean pre-entry comparison."
        )
    if status == "unsupported_duration":
        return (
            "<b>AI context:</b> This duration is outside the model's supported range, so no AI estimate is shown."
        )
    horizons = context.get("horizons") or []
    if status != "available" or not horizons:
        return (
            "<b>AI context:</b> The current-condition model reading is unavailable, and Tara is not treating "
            "the missing values as zero."
        )

    if context["mode"] == "checkpoints":
        readings = []
        for item in horizons:
            metrics = []
            if item.get("win_probability") is not None:
                metrics.append(f"{item['win_probability'] * 100:.0f}% AI Win Probability")
            if item.get("predicted_return_pct") is not None:
                metrics.append(
                    "predicted return "
                    + _pct(item["predicted_return_pct"], signed=True, decimals=1)
                )
            if metrics:
                readings.append(
                    f"&bull; <b>{item['calendar_days']} days:</b> "
                    + "; ".join(metrics)
                )
        if not readings:
            return None
        full_days = context["full_pattern_calendar_days"]
        horizon_days = [
            item["calendar_days"]
            for item in horizons
            if item.get("win_probability") is not None
            or item.get("predicted_return_pct") is not None
        ]
        if len(horizon_days) == 1:
            horizon_text = str(horizon_days[0])
        elif len(horizon_days) == 2:
            horizon_text = f"{horizon_days[0]} and {horizon_days[1]}"
        else:
            horizon_text = ", ".join(str(day) for day in horizon_days[:-1])
            horizon_text += f", and {horizon_days[-1]}"

        probabilities = [
            (item["calendar_days"], item["win_probability"])
            for item in horizons
            if item.get("win_probability") is not None
        ]
        predicted_returns = [
            (item["calendar_days"], item["predicted_return_pct"])
            for item in horizons
            if item.get("predicted_return_pct") is not None
        ]
        standout = ""
        if len(probabilities) >= 2 and len(predicted_returns) >= 2:
            best_probability_days = [
                day
                for day, value in probabilities
                if value == max(item[1] for item in probabilities)
            ]
            best_return_days = [
                day
                for day, value in predicted_returns
                if value == max(item[1] for item in predicted_returns)
            ]

            def format_best_days(days: List[int]) -> str:
                if len(days) == 1:
                    return f"{days[0]} days"
                if len(days) == 2:
                    return f"{days[0]} and {days[1]} days"
                return ", ".join(str(day) for day in days[:-1]) + f", and {days[-1]} days"

            probability_days = format_best_days(best_probability_days)
            return_days = format_best_days(best_return_days)
            if best_probability_days == best_return_days:
                standout = (
                    "The highest AI Win Probability and predicted return both appear over "
                    f"{probability_days}. "
                )
            else:
                standout = (
                    f"The highest AI Win Probability appears over {probability_days}, while "
                    f"the highest predicted return appears over {return_days}. "
                )
        return (
            "<b>AI-calibrated outlook:</b> AI-calibrated probabilities for this opportunity over "
            f"the first {horizon_text} calendar days are as follows:<br>"
            + "<br>".join(readings)
            + "<br>Each outlook begins on the same entry date and evaluates the same direction."
            + "<br><br><b>What stands out:</b> "
            + standout
            + f"The historical analysis above describes the complete {full_days}-day pattern."
        )

    item = horizons[0]
    metrics = []
    if item.get("win_probability") is not None:
        comparison = _ai_probability_comparison(
            item["win_probability"], facts.get("win_rate_pct")
        )
        win_text = f"AI Win Probability {item['win_probability'] * 100:.0f}%"
        if comparison:
            win_text += f" ({comparison})"
        metrics.append(win_text)
    if item.get("predicted_return_pct") is not None:
        metrics.append(
            "PredR " + _pct(item["predicted_return_pct"], signed=True, decimals=1)
        )
    if item.get("predicted_mfe_pct") is not None:
        metrics.append(
            "PMFE " + _pct(item["predicted_mfe_pct"], signed=True, decimals=1)
        )
    if not metrics:
        return None
    horizon = item["calendar_days"]
    return (
        f"<b>AI context:</b> Current-condition model for this same {horizon}-calendar-day window: "
        + "; ".join(metrics)
        + ". AI Win Probability and PredR are estimates, not additional historical observations."
    )


def _analysis_payoff_and_path_line(facts: Mapping[str, Any]) -> Optional[str]:
    """Summarize endpoint payoff and entry-relative intrawindow excursions."""

    details: List[str] = []
    wins = int(facts.get("profitable_years") or 0)
    losses = int(facts.get("losing_years") or 0)
    avg_win = facts.get("avg_profitable_return_pct")
    avg_loss = facts.get("avg_losing_return_pct")
    payoff = facts.get("payoff_ratio")
    if wins >= 2 and losses >= 2 and avg_win is not None and avg_loss is not None:
        payoff_text = (
            f"average winner {_pct(avg_win, signed=True, decimals=2)} versus "
            f"average loser {_pct(avg_loss, signed=True, decimals=2)}"
        )
        if payoff is not None:
            payoff_text += f" ({payoff:.2f}:1)"
        details.append(payoff_text)
    elif wins and losses:
        details.append("the winner/loser payoff comparison is based on too few outcomes to be stable")

    median_mfe = facts.get("median_mfe_pct")
    median_mae = facts.get("median_mae_pct")
    worst_mae = facts.get("worst_mae_pct")
    worst_mae_year = facts.get("worst_mae_year")
    if median_mfe is not None:
        details.append(
            f"median best move {_pct(median_mfe, signed=True, decimals=2)} (MFE)"
        )
    if median_mae is not None:
        details.append(
            f"median adverse move {_pct(median_mae, signed=True, decimals=2)} (MAE)"
        )
    only_losing_year = facts.get("only_losing_year")
    only_losing_mfe = facts.get("only_losing_mfe_pct")
    only_losing_finish = facts.get("only_losing_return_pct")
    if (
        losses == 1
        and only_losing_year is not None
        and only_losing_mfe is not None
        and only_losing_finish is not None
    ):
        giveback = only_losing_mfe - only_losing_finish
        details.append(
            f"the lone losing observation ({only_losing_year}) first reached "
            f"{_pct(only_losing_mfe, signed=True, decimals=2)} MFE before finishing "
            f"{_pct(only_losing_finish, signed=True, decimals=2)}—a "
            f"{giveback:.2f}-percentage-point giveback from its best move"
        )
    elif (
        losses >= 2
        and int(facts.get("losing_mfe_sample_size") or 0) >= 2
        and facts.get("median_losing_mfe_pct") is not None
        and facts["median_losing_mfe_pct"] >= 1.0
    ):
        details.append(
            "losing observations still reached a median "
            + _pct(facts["median_losing_mfe_pct"], signed=True, decimals=2)
            + " MFE before their final losses"
        )
    if worst_mae is not None:
        details.append(
            "worst MAE "
            + _pct(worst_mae, signed=True, decimals=2)
            + (f" in {worst_mae_year}" if worst_mae_year is not None else "")
        )
    worst_finish = facts.get("worst_trade_return_pct")
    worst_year = facts.get("worst_year")
    if worst_finish is not None:
        details.append(
            "worst finish "
            + _pct(worst_finish, signed=True, decimals=2)
            + (f" in {worst_year}" if worst_year is not None else "")
        )
    if not details:
        return None
    line = "<b>Payoff and path:</b> " + "; ".join(details) + "."
    if median_mae is not None or worst_mae is not None:
        line += " MAE is the move against the setup from entry, not peak-to-trough drawdown."
    return line


def _recent_slice_is_weaker(facts: Mapping[str, Any]) -> bool:
    recent_rate = facts.get("recent_win_rate_pct")
    prior_rate = facts.get("prior_win_rate_pct")
    recent_avg = facts.get("recent_avg_trade_return_pct")
    prior_avg = facts.get("prior_avg_trade_return_pct")
    return bool(
        int(facts.get("recent_sample_size") or 0) >= 5
        and int(facts.get("prior_sample_size") or 0) >= 5
        and None not in (recent_rate, prior_rate, recent_avg, prior_avg)
        and recent_rate <= prior_rate - 15
        and recent_avg < prior_avg
    )


def _analysis_chart_context_line(
    facts: Mapping[str, Any], screen: Mapping[str, Any]
) -> Optional[str]:
    """Separate one historical Price Chart path from the aggregate cohort."""

    if (
        screen.get("active_bottom_slide") != "price_chart"
        or screen.get("price_chart_mode") != "historical"
        or not screen.get("price_chart_year")
    ):
        return None
    try:
        viewed_year = int(str(screen["price_chart_year"]))
    except (TypeError, ValueError):
        return None
    viewed_cycle = _pe_cycle_for_year(viewed_year)
    phase = (
        f" ({_PE_LABELS[viewed_cycle][0]}, {_PE_YEAR_DESCRIPTIONS[viewed_cycle]})"
        if viewed_cycle in _PE_LABELS
        else ""
    )
    n = int(facts.get("sample_size") or 0)
    cohort = (
        _observation_label(facts, n)
        if n
        else "the loaded completed cohort"
    )
    return (
        f"<b>Chart context:</b> The Price Chart is showing the {viewed_year} occurrence{phase}, "
        f"which is one historical path. The aggregate statistics cover {cohort}, not {viewed_year} alone."
    )


def _analysis_occurrence_line(facts: Mapping[str, Any]) -> Optional[str]:
    """Explain whether the dated occurrence is upcoming, active, or completed."""

    status = facts.get("occurrence_status")
    start = _month_day_year(str(facts.get("occurrence_start_date") or ""))
    end = _month_day_year(str(facts.get("occurrence_end_date") or ""))
    if status not in {"upcoming", "active", "completed"} or not start or not end:
        return None

    start_md = _month_day(str(facts.get("occurrence_start_date") or ""))
    end_md = _month_day(str(facts.get("occurrence_end_date") or ""))
    start_year = facts.get("occurrence_year")
    try:
        end_year = int(str(facts.get("occurrence_end_date") or "")[:4])
    except (TypeError, ValueError):
        end_year = None
    date_range = (
        f"{start_md} to {end_md}, {start_year}"
        if start_md and end_md and start_year == end_year
        else f"{start} to {end}"
    )

    n = int(facts.get("sample_size") or 0)
    record = f"the completed record (n={n})" if n else "the completed record"
    if status == "upcoming":
        until = int(facts.get("days_until_start") or 0)
        return (
            f"<b>Timing:</b> Upcoming: starts {start} in {until} calendar day"
            f"{'' if until == 1 else 's'} and ends {end}. No result exists yet; its placeholder is "
            f"excluded from {record}."
        )

    if status == "active":
        day_number = int(facts.get("occurrence_day_number") or 0)
        total_days = int(str(facts.get("days") or "0"))
        remaining = int(facts.get("calendar_days_remaining") or 0)
        end_timing = "today" if remaining == 0 else f"in {remaining} calendar day{'' if remaining == 1 else 's'}"
        return (
            f"<b>Timing:</b> Active: calendar day {day_number} of {total_days} in the {date_range} window; "
            f"it ends {end_timing}. The partial live row is excluded from {record}."
        )

    occurrence_year = facts.get("occurrence_year")
    since = int(facts.get("days_since_end") or 0)
    inclusion = (
        f"Its finalized {occurrence_year} observation is included in {record}."
        if facts.get("occurrence_row_is_in_completed_sample")
        else f"The supplied history has no finalized {occurrence_year} row, so it is not counted in {record}."
    )
    return (
        f"<b>Timing:</b> Completed: the {date_range} window ended {since} calendar day"
        f"{'' if since == 1 else 's'} ago. {inclusion}"
    )


def _analysis_cycle_context_line(
    facts: Mapping[str, Any], screen: Mapping[str, Any]
) -> Optional[str]:
    """Recommend the relevant PE/consecutive comparison without inventing its result."""

    del screen  # Reserved for future cohort overlays; current phase comes from the entry year.
    occurrence_year = facts.get("occurrence_year")
    occurrence_cycle = facts.get("occurrence_pe_cycle")
    current_year = facts.get("current_year")
    current_cycle = facts.get("current_pe_cycle")
    occurrence_text = _pe_year_text(occurrence_cycle)
    current_text = _pe_year_text(current_cycle)
    if occurrence_year is None or occurrence_text is None:
        return None

    loaded_cycle = str(facts.get("pe_cycle") or "cons")
    not_current = occurrence_year != current_year
    current_note = ""
    if not_current and current_text:
        current_note = (
            f" Current {current_year} is {current_text}, so the dated occurrence is not "
            "current-year cycle context."
        )

    if loaded_cycle == "cons":
        cycle_label = _pe_observation_text(occurrence_cycle)
        return (
            f"<b>Cycle context:</b> {occurrence_year} is {occurrence_text}; this sample is consecutive."
            f"{current_note} Compare the exact same window in {cycle_label} observations. That cohort is not "
            "loaded, so there is no stronger/weaker conclusion yet. "
            f"Compare n in both views. {_cycle_switch_link(occurrence_cycle)}"
        )

    loaded_text = _pe_year_text(loaded_cycle)
    if loaded_text is None:
        return None
    loaded_label = _pe_observation_text(loaded_cycle)
    sample_description = _pe_sample_description(facts)
    if loaded_cycle != occurrence_cycle:
        occurrence_label = _pe_observation_text(occurrence_cycle)
        return (
            f"<b>Cycle context:</b> The loaded sample isolates {loaded_label} observations, but the "
            f"{occurrence_year} occurrence is {occurrence_text}. Those contexts do not match. "
            f"{sample_description}{current_note} "
            f"Load {occurrence_label} for this occurrence before interpreting it, then compare the exact same "
            "window across consecutive years. Neither comparison is loaded yet. "
            f"{_cycle_switch_link(occurrence_cycle)} {_cycle_switch_link('cons')}"
        )

    return (
        f"<b>Cycle context:</b> This sample already isolates {loaded_label} observations and matches the "
        f"{occurrence_year} occurrence ({_PE_YEAR_DESCRIPTIONS[loaded_cycle]}). {sample_description}"
        f"{current_note} For broader "
        "context, compare the exact same window across consecutive years. That cohort is not loaded, so there "
        f"is no stronger/weaker conclusion yet; compare n in both views. {_cycle_switch_link('cons')}"
    )


def _analysis_compact_context_line(
    facts: Mapping[str, Any], screen: Mapping[str, Any]
) -> Optional[str]:
    """Return only the single most material evidence exception."""

    avg_return = facts.get("avg_trade_return_pct")
    avg_without_best = facts.get("avg_without_best_year_pct")
    median = facts.get("median_trade_return_pct")
    if avg_return is not None and avg_return > 0 and avg_without_best is not None and avg_without_best <= 0:
        issue = "the positive average disappears when the single best observation is removed"
    elif avg_return is not None and avg_return > 0 and median is not None and median <= 0:
        issue = "the average is positive but the median is not, indicating outlier dependence"
    elif _recent_slice_is_weaker(facts):
        recent_n = int(facts.get("recent_sample_size") or 0)
        prior_n = int(facts.get("prior_sample_size") or 0)
        issue = (
            f"the latest {recent_n} were weaker than the earlier {prior_n} in this sample "
            f"({_pct(facts.get('recent_win_rate_pct'))} versus {_pct(facts.get('prior_win_rate_pct'))} profitable)"
        )
    elif screen.get("selected_window_path") == "supports" and screen.get("full_history_window_path") == "against":
        issue = "the selected-history curve supports the setup but the full-history curve opposes it"
    elif int(facts.get("ending_losing_streak") or 0) >= 2:
        issue = f"the sample ends with {int(facts['ending_losing_streak'])} losing observations"
    elif facts.get("earnings_in_window"):
        issue = (
            "the estimated earnings date "
            + html.escape(str(facts.get("next_earnings_est"))[:10])
            + " falls inside the window"
        )
    elif facts.get("trend_alignment") == "against" and facts.get("trend_score") is not None:
        issue = _trend_alignment_plain_language(facts)
    elif (
        screen.get("selected_window_path") == "supports"
        and screen.get("full_history_window_path") == "supports"
        and facts.get("trend_alignment") == "aligned"
        and facts.get("trend_score") is not None
    ):
        issue = "both historical curve views support the direction; " + _trend_alignment_plain_language(facts)
    elif facts.get("trend_score_available") is False:
        issue = _trend_alignment_plain_language(facts)
    elif int(facts.get("sample_size") or 0) < 20:
        issue = "sample depth is the main limitation"
    else:
        return None
    return "<b>What matters now:</b> " + issue + "."


def _analysis_compact_next_check_line(
    facts: Mapping[str, Any], screen: Mapping[str, Any]
) -> Optional[str]:
    avg_return = facts.get("avg_trade_return_pct")
    avg_without_best = facts.get("avg_without_best_year_pct")
    if avg_return is not None and avg_return > 0 and avg_without_best is not None and avg_without_best <= 0:
        check = "inspect the standout year beside the median year and nearby window definitions"
    elif _recent_slice_is_weaker(facts):
        check = "compare this exact window on recent and full-history lookbacks"
    elif screen.get("selected_window_path") == "supports" and screen.get("full_history_window_path") == "against":
        check = "inspect both normalized curves across the exact entry-to-exit window"
    elif facts.get("earnings_in_window"):
        check = "compare historical occurrences with and without earnings inside the window"
    elif facts.get("trend_score_available") is False:
        check = "use the Price Chart for recent direction until a current Trend score is available"
    elif facts.get("trend_alignment") == "against":
        expected_move = "downward" if facts.get("direction") == "short" else "upward"
        check = (
            f"use the Price Chart to verify that recent movement is not yet moving {expected_move} "
            "with the seasonal setup"
        )
    elif int(facts.get("sample_size") or 0) < 10:
        check = "increase the history depth if this symbol has enough completed data"
    elif facts.get("selection_origin") == "scanner":
        check = "compare nearby start dates and hold lengths before treating the scanner peak as stable"
    elif facts.get("worst_mae_year") is not None:
        check = f"inspect {facts['worst_mae_year']} with MFE and MAE shown to see how the worst path developed"
    else:
        return None
    return "<b>Next check:</b> " + check + "."


def _analysis_scope_line(facts: Mapping[str, Any]) -> str:
    costs = "execution costs and taxes"
    if facts.get("direction") == "short":
        costs = "execution costs, taxes, short-borrow costs, and dividends owed"
    line = f"<b>Scope:</b> gross historical results exclude {costs}."
    if facts.get("selection_origin") == "scanner":
        line += " Scanner-selected, in-sample, and selection-sensitive."
    return line + " This is not a forecast or recommendation."


def _render_analysis_sections(lines: Iterable[Optional[str]]) -> str:
    """Render analysis as semantic blocks so narrow chat panels stay scannable."""

    sections = []
    for line in lines:
        if not line:
            continue
        classes = ["tara-analysis-section"]
        if line.startswith(
            (
                "<b>Read:",
                "<b>Why seasonality matters:",
                "<b>Build around measurable odds:",
                "<b>Why TradeWave uses 90-day AI horizons:",
            )
        ):
            classes.append("tara-analysis-lead")
        elif line.startswith("<b>Cycle context:") or line.startswith("<b>Next check:"):
            classes.append("tara-analysis-action")
        elif line.startswith("<b>Scope:"):
            classes.append("tara-analysis-scope")
        sections.append(f'<div class="{" ".join(classes)}">{line}</div>')
    return '<div class="tara-analysis">' + "".join(sections) + "</div>"


def _guide_link(action: str, label: str) -> str:
    """Render one allowlisted client-handled educational link."""

    allowed = {
        "open-filtering-popup",
        "open-seasonal-popup",
        "open-years-popup",
    }
    if action not in allowed:
        return ""
    return (
        '<a href="#" class="tara-analysis-link" '
        f'data-action="{action}">{html.escape(label)}</a>'
    )


def _loaded_pattern_value_line(facts: Mapping[str, Any]) -> Optional[str]:
    """Use the visible chart as the concrete proof of what the detector found."""

    symbol = html.escape(str(facts.get("symbol") or ""))
    n = int(facts.get("sample_size") or 0)
    if not symbol or n <= 0:
        return None
    direction = "short" if facts.get("direction") == "short" else "long"
    start = _month_day(str(facts.get("start_date") or ""))
    end = _month_day(
        _inclusive_end_date(
            str(facts.get("start_date") or ""), str(facts.get("days") or "")
        )
        or ""
    )
    days = html.escape(str(facts.get("days") or ""))
    setup = f"{symbol} {direction}"
    if start and end and days:
        setup += f", {start} to {end} ({days} calendar days)"

    wins = int(facts.get("profitable_years") or 0)
    details = [
        f"profitable in {wins} of {_observation_label(facts, n)} "
        f"({_pct(facts.get('win_rate_pct'))}; n={n})"
    ]
    average = facts.get("avg_trade_return_pct")
    median = facts.get("median_trade_return_pct")
    if average is not None:
        details.append("gross average " + _pct(average, signed=True, decimals=2))
    if median is not None:
        details.append("median " + _pct(median, signed=True, decimals=2))
    return (
        f"<b>What TradeWave detected here:</b> {setup}: "
        + "; ".join(details)
        + ". Each bar is one completed occurrence."
    )


def build_ai_horizon_explanation_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Explain the calibrated horizon positively and without provider drift."""

    if not is_ai_horizon_explanation_question(message):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    try:
        full_days = int(facts.get("days") or 0)
    except (TypeError, ValueError):
        full_days = 0
    if full_days > 90:
        longer_pattern_line = (
            f"<b>For this {full_days}-calendar-day pattern:</b> Tara provides separate 30-, 60-, "
            "and 90-day AI-calibrated outlooks from the same entry date and direction. The "
            f"historical analysis evaluates the complete {full_days}-day pattern."
        )
    else:
        longer_pattern_line = (
            "<b>For longer patterns:</b> Tara provides separate 30-, 60-, and 90-day "
            "AI-calibrated outlooks from the same entry date and direction, while the historical "
            "analysis evaluates the complete seasonal window."
        )
    lines = [
        (
            "<b>Why TradeWave uses 90-day AI horizons:</b> TradeWave's AI models are trained and "
            "calibrated for seasonal windows from 10 to 90 calendar days. Current market "
            "conditions provide useful predictive context over these nearer horizons, and 90 days "
            "keeps each probability within the range where its calibration was tested."
        ),
        longer_pattern_line,
        (
            "<b>How the evidence fits together:</b> AI Win Probability and predicted return add "
            "current-condition context for each named horizon. Historical hit rate, average and "
            "median return, MFE, and MAE describe the pattern across completed years."
        ),
    ]
    return _render_analysis_sections(lines)


def build_seasonality_value_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Demonstrate seasonality's product value without a sales essay or refusal."""

    if not is_seasonality_value_question(message):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    example = _loaded_pattern_value_line(facts)
    if example is None:
        example = (
            "<b>What TradeWave detects:</b> exact calendar windows whose direction, payoff, and "
            "historical path repeated across completed years - evidence that a single chronological "
            "price chart does not organize for you."
        )

    lines = [
        (
            "<b>Why seasonality matters:</b> Traditional indicators describe recent price action. "
            "TradeWave aligns the same calendar window across prior years to detect recurring behavior."
        ),
        example,
        (
            "<b>Flexible pattern detection:</b> Test the exact window over 10, 12, 15, 20, 25, or "
            "maximum history to see whether it is recent, durable, or lookback-sensitive."
        ),
        (
            "<b>From pattern to probability:</b> Historical hit rate is the observed base rate for "
            "the exact window and n. On supported horizons, AI Win Probability adds current context; "
            "MFE and MAE show the path. Card-counter mindset: measure the odds, update the evidence, "
            "and build rules. Find the pattern. Measure the odds. Build your strategy."
        ),
        (
            "<b>Explore it:</b> "
            + _guide_link("open-years-popup", "See flexible lookbacks")
            + " "
            + _guide_link("open-seasonal-popup", "Open the seasonality guide")
        ),
    ]
    return _render_analysis_sections(lines)


def _strategy_starting_evidence_line(facts: Mapping[str, Any]) -> str:
    symbol = html.escape(str(facts.get("symbol") or ""))
    n = int(facts.get("sample_size") or 0)
    if not symbol or n <= 0:
        return (
            "<b>Define the rule:</b> Fix the market, direction, calendar entry rule, and "
            "calendar-day holding range so Tara can search the same hypothesis consistently."
        )
    direction = "short" if facts.get("direction") == "short" else "long"
    wins = int(facts.get("profitable_years") or 0)
    details = [
        f"{wins} profitable outcomes in {_observation_label(facts, n)} "
        f"({_pct(facts.get('win_rate_pct'))}; n={n})"
    ]
    average = facts.get("avg_trade_return_pct")
    median = facts.get("median_trade_return_pct")
    if average is not None:
        details.append("gross average " + _pct(average, signed=True, decimals=2))
    if median is not None:
        details.append("median " + _pct(median, signed=True, decimals=2))
    return (
        f"<b>Starting evidence:</b> The loaded {symbol} {direction} pattern provides an immediate "
        "base rate: " + "; ".join(details) + "."
    )


def build_strategy_framework_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Turn a broad strategy request into a positive, testable research process."""

    if not is_strategy_building_question(message):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    lines = [
        (
            "<b>Build around measurable odds:</b> Fix the market, direction, calendar entry, and "
            "holding period so every result is comparable."
        ),
        _strategy_starting_evidence_line(facts),
        (
            "<b>Stress-test it:</b> Compare 10, 12, 15, 20, 25, and maximum history, plus nearby "
            "start dates, holding periods, and PE-cycle cohorts. Note where the result changes."
        ),
        (
            "<b>Measure probability and path:</b> Pair hit rate with average and median payoff, "
            "losing years, MFE, MAE, and worst finish. Treat AI Win Probability and Trend Alignment "
            "as separate current evidence."
        ),
        (
            "<b>Make it repeatable:</b> Keep the rules unchanged and record future occurrences. You "
            "choose the rules and risk; Tara finds candidates, measures the odds, and challenges weak assumptions."
        ),
        (
            "<b>Build it in TradeWave:</b> "
            + _guide_link("open-filtering-popup", "Define pattern filters")
            + " "
            + _guide_link("open-years-popup", "Test history depth")
        ),
    ]
    return _render_analysis_sections(lines)


def _historical_only_line() -> str:
    return (
        "<b>How to use this read:</b> it describes the historical evidence and its weak points; "
        "it is not a forecast or a trade recommendation."
    )


def _analysis_next_check_line(
    facts: Mapping[str, Any], screen: Mapping[str, Any]
) -> Optional[str]:
    """Suggest one evidence check targeted to the record's largest uncertainty."""

    n = int(facts.get("sample_size") or 0)
    if _recent_slice_is_weaker(facts):
        return (
            "<b>Best next check:</b> compare this exact window on the latest non-overlapping slice, "
            "the earlier sample, and the full available history."
        )
    if screen.get("selected_window_path") == "supports" and screen.get("full_history_window_path") == "against":
        return (
            "<b>Best next check:</b> compare the selected and full-history curves around the entry and exit; "
            "their disagreement is the main uncertainty in this read."
        )
    if facts.get("earnings_in_window"):
        return (
            "<b>Best next check:</b> compare years with and without an earnings event in the window; "
            "the current occurrence contains an estimated earnings date."
        )
    if (
        facts.get("avg_trade_return_pct") is not None
        and facts.get("avg_trade_return_pct") > 0
        and facts.get("avg_without_best_year_pct") is not None
        and facts.get("avg_without_best_year_pct") <= 0
    ):
        return (
            "<b>Best next check:</b> inspect the standout best year beside a typical year; the positive average "
            "does not survive removing that outlier."
        )
    if n and n < 10:
        return (
            "<b>Best next check:</b> increase the history depth if the symbol allows it; the current sample is too "
            "small for a stable read."
        )
    if facts.get("worst_year") is not None:
        return (
            f"<b>Best next check:</b> inspect {facts['worst_year']} on the historical Price Chart to see how this "
            "pattern failed, not just how much it lost."
        )
    return None


def _analysis_read_line(facts: Mapping[str, Any]) -> str:
    n = int(facts.get("sample_size") or 0)
    win_rate = facts.get("win_rate_pct")
    ratio = facts.get("payoff_ratio")
    sharpe = facts.get("sharpe_ratio")

    strengths = []
    if win_rate is not None and win_rate >= 75:
        strengths.append("high historical win frequency")
    elif win_rate is not None and win_rate >= 60:
        strengths.append("more winning than losing years")
    if ratio is not None and ratio >= 1.25:
        strengths.append("favorable average payoff asymmetry")
    if sharpe is not None and sharpe >= 1:
        strengths.append("stronger cross-year risk-adjusted consistency in this sample")
    recent_rate = facts.get("recent_win_rate_pct")
    prior_rate = facts.get("prior_win_rate_pct")
    recent_avg = facts.get("recent_avg_trade_return_pct")
    prior_avg = facts.get("prior_avg_trade_return_pct")
    if (
        recent_rate is not None
        and prior_rate is not None
        and recent_avg is not None
        and prior_avg is not None
        and int(facts.get("recent_sample_size") or 0) >= 5
        and int(facts.get("prior_sample_size") or 0) >= 5
        and recent_rate >= prior_rate + 15
        and recent_avg > prior_avg
    ):
        strengths.append("stronger results in the most recent observations")

    limitations = []
    if n < 10:
        limitations.append(f"a small n={n} sample")
    elif n < 20:
        limitations.append(f"an informative but still modest n={n} sample")
    if sharpe is not None and sharpe < 0.5:
        limitations.append("a sub-0.5 Sharpe that shows uneven results across years")
    elif sharpe is not None and sharpe < 1:
        limitations.append("a sub-1 Sharpe that means the ending results were not exceptionally consistent across years")
    if (
        recent_rate is not None
        and prior_rate is not None
        and recent_avg is not None
        and prior_avg is not None
        and int(facts.get("recent_sample_size") or 0) >= 5
        and int(facts.get("prior_sample_size") or 0) >= 5
        and recent_rate <= prior_rate - 15
        and recent_avg < prior_avg
    ):
        limitations.append("a weaker latest non-overlapping slice in this sample")

    def join_items(items: List[str]) -> str:
        if len(items) < 2:
            return items[0] if items else ""
        return ", ".join(items[:-1]) + " and " + items[-1]

    if strengths:
        label = "strength is" if len(strengths) == 1 else "strengths are"
        text = f"The main {label} " + join_items(strengths) + "."
    else:
        text = "The historical record is mixed rather than clearly strong."
    if limitations:
        label = "limitation is" if len(limitations) == 1 else "limitations are"
        text += f" The main {label} " + join_items(limitations) + "."
    text += " This is historical evidence, not a forecast or a trade recommendation."
    return "<b>Read:</b> " + text


def build_pattern_analysis_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Build a verified answer whose depth and evidence match the analytical intent."""

    focus = ""
    if is_pattern_recency_question(message, wave_viewer):
        focus = "recent"
    elif is_pattern_risk_question(message, wave_viewer):
        focus = "risk"
    elif is_pattern_consistency_question(message, wave_viewer):
        focus = "consistency"
    elif is_pattern_analysis_question(message, wave_viewer):
        focus = "overview"
    if not focus:
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    if not facts.get("symbol") or not facts.get("sample_size"):
        return None
    screen = normalize_screen_context(screen_context)

    if focus == "overview":
        lines = [
            _analysis_compact_read_line(facts),
            _analysis_ai_context_line(facts, wave_viewer),
            _analysis_chart_context_line(facts, screen),
            _analysis_payoff_and_path_line(facts),
            _analysis_occurrence_line(facts),
            _analysis_compact_context_line(facts, screen),
            _analysis_cycle_context_line(facts, screen),
            _analysis_compact_next_check_line(facts, screen),
            _analysis_scope_line(facts),
        ]
        return _render_analysis_sections(lines)

    lines = [_analysis_bottom_line(facts), _analysis_record_line(facts)]
    if focus == "recent":
        recent = _analysis_recent_line(facts)
        if recent:
            lines.append(recent)
        lines.append(_analysis_risk_line(facts))
    elif focus == "risk":
        lines.append(_analysis_payoff_and_path_line(facts))
        lines.append(_analysis_risk_line(facts))
        lines.append(_analysis_robustness_line(facts))
    elif focus == "consistency":
        lines.append(_analysis_robustness_line(facts))
        lines.append(_analysis_range_line(facts))
        recent = _analysis_recent_line(facts)
        if recent:
            lines.append(recent)
    else:
        lines.append(_analysis_driver_line(facts))
        lines.append(_analysis_robustness_line(facts))
        recent = _analysis_recent_line(facts)
        if recent:
            lines.append(recent)
        lines.append(_analysis_risk_line(facts))

    context = _analysis_path_line(facts, screen)
    if context:
        lines.append(context)
    next_check = _analysis_next_check_line(facts, screen)
    if next_check:
        lines.append(next_check)
    lines.append(_analysis_scope_line(facts))
    return _render_analysis_sections(lines)


def build_specific_year_reply(
    message: Any,
    wave_viewer: Any,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Explain one loaded year directly from its bar row, with direction-aware P&L."""

    if not is_specific_year_question(message, wave_viewer):
        return None
    match = _SPECIFIC_YEAR_PATTERN.search(str(message or ""))
    if not match:
        return None
    requested_year = int(match.group(0))
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    if not facts.get("symbol"):
        return None
    this_year = current_year or _datetime.date.today().year
    if requested_year >= this_year:
        return (
            f"<b>{requested_year} is not a completed historical observation.</b> "
            "TradeWave excludes the current-year placeholder and future rows from the record until the window is complete."
        )

    rows = _direction_adjusted_rows(
        (wave_viewer or {}).get("yearly_results"),
        direction=str(facts.get("direction") or "long"),
    )
    row = next((item for item in rows if item["year"] == requested_year), None)
    n = int(facts.get("sample_size") or 0)
    if row is None:
        return (
            f"<b>{requested_year} is not in the loaded sample.</b> The current record contains "
            f"{_observation_label(facts, n)}."
        )

    trade_return = row["trade_return_pct"]
    underlying = row["underlying_return_pct"]
    profitable = trade_return > 0
    result = "profitable" if profitable else "losing" if trade_return < 0 else "flat"
    color = "green/up" if underlying > 0 else "red/down" if underlying < 0 else "flat"
    direction = str(facts.get("direction") or "long")
    line = (
        f"<b>{requested_year} was a {result} {direction} observation:</b> the underlying moved "
        f"{_pct(underlying, signed=True, decimals=2)} ({color} bar), so the direction-adjusted "
        f"trade return was {_pct(trade_return, signed=True, decimals=2)}."
    )

    asks_mfe = bool(re.search(r"\b(?:mfe|maximum favorable|best point)\b", str(message or ""), re.I))
    asks_mae = bool(re.search(r"\b(?:mae|maximum adverse|drawdown|worst point)\b", str(message or ""), re.I))
    excursion_bits = []
    upside = row.get("upside_excursion_pct")
    downside = row.get("downside_excursion_pct")
    favorable = upside if direction == "long" else (-downside if downside is not None else None)
    adverse = downside if direction == "long" else (-upside if upside is not None else None)
    if asks_mfe and favorable is not None:
        excursion_bits.append(f"MFE {_pct(favorable, signed=True, decimals=2)}")
    if asks_mae:
        if not bool((wave_viewer or {}).get("mae_enabled")):
            excursion_bits.append("MAE is not enabled on the current chart")
        elif adverse is not None:
            excursion_bits.append(f"MAE {_pct(adverse, signed=True, decimals=2)}")
    if excursion_bits:
        line += " " + "; ".join(excursion_bits) + "."
    return line


def build_per_year_excursion_reply(
    message: Any,
    wave_viewer: Any,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """List direction-aware MFE/MAE and the final return for each completed row."""

    if not is_per_year_excursion_question(message, wave_viewer):
        return None

    text = str(message or "")
    asks_pair = bool(_PLAIN_EXCURSION_PAIR_PATTERN.search(text))
    show_mfe = asks_pair or bool(_MFE_TERM_PATTERN.search(text))
    show_mae = asks_pair or bool(_MAE_TERM_PATTERN.search(text))
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    direction = str(facts.get("direction") or "long")
    this_year = current_year or _datetime.date.today().year
    rows = _direction_adjusted_rows(
        (wave_viewer or {}).get("yearly_results"),
        direction=direction,
        before_year=this_year,
    )
    if not rows:
        return None

    prepared = []
    for row in rows:
        upside = row.get("upside_excursion_pct")
        downside = row.get("downside_excursion_pct")
        favorable = upside if direction == "long" else (-downside if downside is not None else None)
        adverse = downside if direction == "long" else (-upside if upside is not None else None)
        prepared.append({**row, "mfe_pct": favorable, "mae_pct": adverse})

    metric_names = []
    if show_mfe:
        metric_names.append("the best move (MFE)")
    if show_mae:
        metric_names.append("the worst move (MAE)")
    if len(metric_names) == 2:
        requested = " and ".join(metric_names)
    else:
        requested = metric_names[0]

    n = len(prepared)
    lines = [
        f"<b>You mean {requested} inside each window</b> - not the highest and lowest "
        "end-of-window returns across years.",
        _pattern_line(facts),
    ]

    summary_bits = []
    if show_mfe:
        favorable_values = [row["mfe_pct"] for row in prepared if row["mfe_pct"] is not None]
        if favorable_values:
            summary_bits.append(
                f"median best move {_pct(statistics.median(favorable_values), signed=True, decimals=2)}"
            )
    if show_mae:
        adverse_values = [row["mae_pct"] for row in prepared if row["mae_pct"] is not None]
        if adverse_values:
            summary_bits.append(
                f"median worst move {_pct(statistics.median(adverse_values), signed=True, decimals=2)}"
            )
    if summary_bits:
        lines.append(
            f"<b>Typical path across {_observation_label(facts, n)}:</b> "
            + "; ".join(summary_bits)
            + "."
        )

    lines.append(f"<b>Each completed observation (newest first, n={n}):</b>")
    for row in reversed(prepared):
        values = []
        if show_mfe and row["mfe_pct"] is not None:
            values.append(f"best {_pct(row['mfe_pct'], signed=True, decimals=2)} (MFE)")
        if show_mae and row["mae_pct"] is not None:
            values.append(f"worst {_pct(row['mae_pct'], signed=True, decimals=2)} (MAE)")
        values.append(
            f"finished {_pct(row['trade_return_pct'], signed=True, decimals=2)} on the {direction}"
        )
        lines.append(f"{row['year']}: " + "; ".join(values) + ".")
    return "<br>".join(lines)


def _normalize_opportunity_direction(value: Any) -> str:
    return "short" if str(value or "").strip().lower() in {"s", "short"} else "long"


def _opportunity_date_matches(value: Any, start_date: str) -> bool:
    candidate = str(value or "").strip()
    if not candidate or not start_date:
        return False
    return candidate == start_date or candidate[-5:] == start_date[-5:]


def build_rank_reply(
    message: Any,
    wave_viewer: Any,
    opportunities: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Explain the loaded row's exact visible rank and the neighboring Sharpe gap."""

    if not is_pattern_rank_question(message, wave_viewer) or not isinstance(opportunities, list):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    symbol = str(facts.get("symbol") or "")
    candidates = [
        (index, row)
        for index, row in enumerate(opportunities)
        if isinstance(row, Mapping) and str(row.get("symbol") or "").strip().upper() == symbol
    ]
    exact = [
        (index, row)
        for index, row in candidates
        if _opportunity_date_matches(row.get("date"), str(facts.get("start_date") or ""))
        and str(row.get("days_out") or "") == str(facts.get("days") or "")
        and _normalize_opportunity_direction(row.get("direction")) == facts.get("direction")
    ]
    if len(exact) == 1:
        index, row = exact[0]
    elif len(candidates) == 1:
        index, row = candidates[0]
    else:
        return None

    rank = index + 1
    screen = normalize_screen_context(screen_context)
    total = screen.get("opportunity_rows")
    if not isinstance(total, int) or total < len(opportunities):
        total = len(opportunities)
    sr = _number(row.get("sharpe_ratio"))
    if sr is None:
        sr = facts.get("sharpe_ratio")
    rank_text = f"#{rank} of {total}" if total else f"#{rank}"
    sr_text = f" with Sharpe {sr:.2f}" if sr is not None else ""
    lines = [
        f"<b>{html.escape(symbol)} is {rank_text}{sr_text} in the visible table.</b> "
        "TradeWave ranks this view by Sharpe, so the position reflects risk-adjusted consistency, not win rate alone."
    ]

    neighbors = []
    if index > 0 and isinstance(opportunities[index - 1], Mapping):
        above = opportunities[index - 1]
        above_sr = _number(above.get("sharpe_ratio"))
        label = html.escape(str(above.get("symbol") or "the row above"))
        neighbors.append(f"above: {label}" + (f" at {above_sr:.2f}" if above_sr is not None else ""))
    if index + 1 < len(opportunities) and isinstance(opportunities[index + 1], Mapping):
        below = opportunities[index + 1]
        below_sr = _number(below.get("sharpe_ratio"))
        label = html.escape(str(below.get("symbol") or "the row below"))
        neighbors.append(f"below: {label}" + (f" at {below_sr:.2f}" if below_sr is not None else ""))
    if neighbors:
        lines.append("<b>Nearest comparison:</b> " + "; ".join(neighbors) + ".")

    n = int(facts.get("sample_size") or 0)
    if n:
        lines.append(
            f"Its supporting record is {facts['profitable_years']} profitable outcomes in "
            f"{_observation_label(facts, n)} ({_pct(facts.get('win_rate_pct'))}); that record is context, "
            "while Sharpe determines this table position."
        )
    return "<br>".join(lines)


def build_advice_safe_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any = None,
    *,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Answer a loaded-pattern advice ask with useful evidence, not a recommendation."""

    if not is_pattern_advice_question(message, wave_viewer):
        return None
    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    if not facts.get("symbol") or not facts.get("sample_size"):
        return None
    screen = normalize_screen_context(screen_context)
    lines = [
        "<b>I can evaluate the evidence, but I can't decide whether you should take the trade.</b>",
        _analysis_compact_read_line(facts),
        _analysis_ai_context_line(facts, wave_viewer),
        _analysis_chart_context_line(facts, screen),
        _analysis_payoff_and_path_line(facts),
        _analysis_occurrence_line(facts),
        _analysis_compact_context_line(facts, screen),
        _analysis_cycle_context_line(facts, screen),
        _analysis_compact_next_check_line(facts, screen),
        _analysis_scope_line(facts),
    ]
    return _render_analysis_sections(lines)


def build_deterministic_reply(
    message: Any,
    wave_viewer: Any,
    screen_context: Any,
    *,
    opportunities: Any = None,
    current_year: Optional[int] = None,
) -> Optional[str]:
    """Route high-confidence UI questions to verified, provider-independent replies."""

    tooltip_help = build_tooltip_help_reply(message)
    if tooltip_help is not None:
        return tooltip_help

    mcp_product = build_mcp_product_reply(message)
    if mcp_product is not None:
        return mcp_product

    named_symbol = explicit_pattern_symbol(message)
    loaded_symbol = str(
        (wave_viewer or {}).get("symbol")
        if isinstance(wave_viewer, Mapping)
        else ""
    ).strip().upper()
    if named_symbol and loaded_symbol and named_symbol != loaded_symbol:
        # The loaded facts belong to another security. Let the tool-capable provider
        # resolve and load the explicitly named ticker instead of answering with stale
        # screen data under the wrong name.
        return None

    overview = build_screen_overview_reply(
        message,
        wave_viewer,
        screen_context,
        opportunities=opportunities,
        current_year=current_year,
    )
    if overview is not None:
        return overview
    trend_alignment = build_trend_alignment_reply(
        message, wave_viewer, current_year=current_year
    )
    if trend_alignment is not None:
        return trend_alignment
    bars = build_bar_semantics_reply(message, wave_viewer, current_year=current_year)
    if bars is not None:
        return bars
    direction = build_direction_reply(message, wave_viewer, current_year=current_year)
    if direction is not None:
        return direction
    excursions = build_per_year_excursion_reply(
        message, wave_viewer, current_year=current_year
    )
    if excursions is not None:
        return excursions
    specific_year = build_specific_year_reply(
        message, wave_viewer, current_year=current_year
    )
    if specific_year is not None:
        return specific_year
    rank = build_rank_reply(
        message,
        wave_viewer,
        opportunities,
        screen_context,
        current_year=current_year,
    )
    if rank is not None:
        return rank
    ai_horizon = build_ai_horizon_explanation_reply(
        message,
        wave_viewer,
        screen_context,
        current_year=current_year,
    )
    if ai_horizon is not None:
        return ai_horizon
    seasonality_value = build_seasonality_value_reply(
        message,
        wave_viewer,
        screen_context,
        current_year=current_year,
    )
    if seasonality_value is not None:
        return seasonality_value
    strategy = build_strategy_framework_reply(
        message,
        wave_viewer,
        screen_context,
        current_year=current_year,
    )
    if strategy is not None:
        return strategy
    advice = build_advice_safe_reply(
        message,
        wave_viewer,
        screen_context,
        current_year=current_year,
    )
    if advice is not None:
        return advice
    return build_pattern_analysis_reply(
        message,
        wave_viewer,
        screen_context,
        current_year=current_year,
    )


def verified_context_lines(
    wave_viewer: Any, screen_context: Any, *, current_year: Optional[int] = None
) -> List[str]:
    """Compact, positively stated facts to append near the end of the LLM prompt."""

    facts = canonical_pattern_facts(wave_viewer, current_year=current_year)
    screen = normalize_screen_context(screen_context)
    if not facts.get("symbol"):
        return ["VERIFIED CURRENT SCREEN: no pattern is loaded."]

    lines = [
        "VERIFIED CURRENT SCREEN AND OUTCOME FACTS (these override conversational history):",
        f"- Active bottom slide: {screen.get('active_bottom_slide', 'unknown')}.",
        f"- Loaded trade direction: {facts['direction']}.",
        "- TradeWave windows use CALENDAR days, with the entry date counted as day 1; the end date is start + (days - 1).",
    ]
    occurrence_year = facts.get("occurrence_year")
    occurrence_cycle = facts.get("occurrence_pe_cycle")
    occurrence_cycle_text = _pe_year_text(occurrence_cycle)
    current_year_value = facts.get("current_year")
    current_cycle_text = _pe_year_text(facts.get("current_pe_cycle"))
    if occurrence_year is not None and occurrence_cycle_text:
        lines.append(
            f"- The dated occurrence is anchored to its entry year {occurrence_year}: {occurrence_cycle_text}."
        )
    if occurrence_year != current_year_value and current_cycle_text:
        lines.append(
            f"- Current year {current_year_value} is {current_cycle_text}; the dated occurrence is not current-year cycle context."
        )
    loaded_cycle = str(facts.get("pe_cycle") or "cons")
    if loaded_cycle in _PE_LABELS:
        lines.append(
            f"- Loaded cohort: {_pe_observation_text(loaded_cycle)} observations, not consecutive years."
        )
        sample_description = _pe_sample_description(facts)
        if sample_description:
            lines.append(f"- {sample_description}")
        if occurrence_cycle and loaded_cycle != occurrence_cycle:
            lines.append(
                f"- COHORT/OCCURRENCE MISMATCH: loaded {_pe_observation_text(loaded_cycle)} but entry year {occurrence_year} is {_pe_observation_text(occurrence_cycle)}. Do not treat them as matching context."
            )
    else:
        lines.append("- Loaded cohort: consecutive years.")
    n = int(facts.get("sample_size") or 0)
    if n:
        sample_type = "years"
        if facts.get("pe_cycle") in _PE_LABELS:
            sample_type = f"{_pe_observation_text(facts['pe_cycle'])} observations"
        lines.append(
            f"- Completed historical record: {facts['profitable_years']} profitable, "
            f"{facts['losing_years']} losing, {facts['flat_years']} flat, n={n} {sample_type}."
        )
    if facts["direction"] == "short":
        lines.append(
            "- Yearly values are UNDERLYING price moves. For this SHORT setup, negative returns/red bars are PROFITABLE SHORT trades; positive returns/green bars are LOSING SHORT trades."
        )
    else:
        lines.append(
            "- Yearly values are UNDERLYING price moves. For this LONG setup, positive returns/green bars are profitable and negative returns/red bars are losing."
        )
    if screen.get("active_bottom_slide") == "price_chart":
        lines.append(f"- Price chart mode: {screen.get('price_chart_mode', 'unknown')}.")
        if screen.get("price_chart_mode") == "historical" and screen.get("price_chart_year"):
            viewed_year = int(screen["price_chart_year"])
            viewed_cycle_text = _pe_year_text(_pe_cycle_for_year(viewed_year))
            phase = f"; {viewed_cycle_text}" if viewed_cycle_text else ""
            lines.append(
                f"- Price Chart historical path: {viewed_year}{phase}. This is one year's path, not the aggregate cohort."
            )
        lines.append(
            "- Projection history labels: selected-history lookback=%s; full-history lookback=%s."
            % (
                screen.get("selected_lookback") or facts.get("years") or "unknown",
                screen.get("full_history_years") or "unknown",
            )
        )
        lines.append(
            "- Visible projections: selected-history=%s; full-history=%s."
            % (
                "yes" if screen.get("selected_projection_visible") else "no",
                "yes" if screen.get("full_history_projection_visible") else "no",
            )
        )
    selected_path = screen.get("selected_window_path")
    full_path = screen.get("full_history_window_path")
    if selected_path != "unknown" or full_path != "unknown":
        lines.append(
            f"- Normalized seasonal-curve direction over the loaded window: selected-history={selected_path}; full-history={full_path}. These are direction labels, not return percentages."
        )
    if facts.get("trend_score") is not None:
        trend_phrase = _trend_alignment_plain_language(facts)
        lines.append(
            f"- {trend_phrase[:1].upper()}{trend_phrase[1:]}. The label compares recent "
            "movement with the seasonal trade direction; it is not a historical pattern statistic."
        )
    elif facts.get("trend_score_available") is False:
        lines.append(
            "- Current Trend score is unavailable. Do not interpret the numeric 0 fallback as "
            "movement against the seasonal direction."
        )
    if facts.get("tradewave_ratio") is not None:
        lines.append(
            f"- TradeWave Ratio (TWR) {facts['tradewave_ratio']:.2f} applies the Sharpe-style "
            "return-to-dispersion calculation to each observation's MFE rather than its ending return."
        )
    if (
        int(facts.get("losing_years") or 0) == 1
        and facts.get("only_losing_year") is not None
        and facts.get("only_losing_mfe_pct") is not None
        and facts.get("only_losing_return_pct") is not None
    ):
        giveback = facts["only_losing_mfe_pct"] - facts["only_losing_return_pct"]
        lines.append(
            f"- The lone losing observation, {facts['only_losing_year']}, reached "
            f"{_pct(facts['only_losing_mfe_pct'], signed=True, decimals=2)} MFE before finishing "
            f"{_pct(facts['only_losing_return_pct'], signed=True, decimals=2)}—a "
            f"{giveback:.2f}-percentage-point giveback from its best move. Surface this when "
            "judging pattern quality, TWR, exit sensitivity, or why the final-return record hides useful path information."
        )
    elif (
        int(facts.get("losing_mfe_sample_size") or 0) >= 2
        and facts.get("median_losing_mfe_pct") is not None
    ):
        lines.append(
            "- Losing observations reached a median "
            + _pct(facts["median_losing_mfe_pct"], signed=True, decimals=2)
            + " before their final losses. This is relevant to TWR and exit sensitivity."
        )
    occurrence_status = facts.get("occurrence_status")
    if occurrence_status == "upcoming":
        lines.append(
            f"- Dated occurrence status: upcoming; starts {facts.get('occurrence_start_date')} in "
            f"{facts.get('days_until_start')} calendar days and ends {facts.get('occurrence_end_date')}. "
            "It has no result and any placeholder row is excluded from the completed record."
        )
    elif occurrence_status == "active":
        lines.append(
            f"- Dated occurrence status: active; started {facts.get('occurrence_start_date')}, is on calendar "
            f"day {facts.get('occurrence_day_number')} of {facts.get('days')}, and ends "
            f"{facts.get('occurrence_end_date')} in {facts.get('calendar_days_remaining')} calendar days. "
            "Its live row is partial and excluded from the completed record."
        )
    elif occurrence_status == "completed":
        inclusion = (
            "is included in the completed record"
            if facts.get("occurrence_row_is_in_completed_sample")
            else "is not present as a finalized row in the completed record"
        )
        lines.append(
            f"- Dated occurrence status: completed; ended {facts.get('occurrence_end_date')}. Its "
            f"{occurrence_year} observation {inclusion}."
        )
    lines.append(
        "- For PE-versus-consecutive comparisons, preserve the exact symbol, direction, entry date, and inclusive calendar-day duration. Fetch the alternate cohort before calling it stronger/weaker, and state n for both cohorts. Never switch the user's view uninvited."
    )
    if facts.get("earnings_in_window"):
        lines.append(
            f"- Estimated earnings date {facts.get('next_earnings_est', '')[:10]} falls inside the current occurrence."
        )
    lines.append(
        "- A broad 'what am I looking at?' question must explain the top Gain-Loss chart AND the currently active bottom slide; also mention the left table when it is visible."
    )
    return lines
