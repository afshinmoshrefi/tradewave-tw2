"""Small, testable prompt-context router for Tara.

Tara's behavioral contract is a stable system-prompt prefix.  Product knowledge and live
screen data are variable suffixes: only the knowledge sections needed for the current question
are selected, and large row-level datasets are included only for questions that need them.

This module has no Flask or provider imports so prompt selection can be regression tested without
starting the application.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple


MAX_TOPIC_SECTIONS = 3
MAX_TOPIC_KNOWLEDGE_CHARS = 16_000


@dataclass(frozen=True)
class KnowledgeSelection:
    headings: Tuple[str, ...]
    text: str


def parse_knowledge_sections(knowledge_text: str) -> Dict[str, str]:
    """Split the markdown KB into complete ``##`` sections, preserving source order."""

    sections: Dict[str, str] = {}
    heading = ""
    lines = []
    for raw_line in str(knowledge_text or "").splitlines():
        if raw_line.startswith("## "):
            if heading:
                sections[heading] = "\n".join(lines).strip()
            heading = raw_line[3:].strip()
            lines = [raw_line]
        elif heading:
            lines.append(raw_line)
    if heading:
        sections[heading] = "\n".join(lines).strip()
    return sections


# Routes are ordered from narrow/specific to broad.  A question may select more than one section,
# but the hard section/character caps prevent the old full-KB prompt from returning by accident.
_TOPIC_ROUTES: Sequence[Tuple[re.Pattern[str], Tuple[str, ...]]] = (
    (re.compile(r"\b100[- ]year pattern\b", re.I), ("The 100-Year Pattern",)),
    (
        re.compile(
            r"\b(?:guidance tooltips?|tooltip (?:switch|toggle)|all (?:these|the) tooltips|"
            r"tooltips everywhere|turn .{0,20} tooltips? (?:on|off))\b",
            re.I,
        ),
        ("Guidance Tooltips",),
    ),
    (
        re.compile(
            r"\b(?:mcp|model context protocol|ai connector)\b|"
            r"^(?!.*\b(?:is tara using|does tara use|is tara powered by)\b)"
            r"(?=.*\b(?:chatgpt|claude(?:\.ai| desktop)?|external ai(?: assistant)?)\b)"
            r"(?=.*\b(?:tradewave|tara|seasonality|seasonal|connect|connector)\b)",
            re.I,
        ),
        ("TradeWave in ChatGPT and Claude (MCP)",),
    ),
    (
        re.compile(r"\b(?:pricing|price plan|subscription|tier|explorer|navigator|strategist|free|cost)\b", re.I),
        ("Subscription Tiers",),
    ),
    (
        re.compile(r"\b(?:projection|gold(?:en)? dashed|purple dashed|proj(?:ection)?\s*n[- ]?y|forecast line)\b", re.I),
        ("Seasonal Projection on Price Chart", "Chart Range (Current Price Chart)"),
    ),
    (
        re.compile(r"\b(?:ai score|ai columns?|\bais\b|predr|pmfe|win probability|machine learning scor)\w*\b", re.I),
        ("AI Scores (AIS, Win%, PredR, PMFE)",),
    ),
    (
        re.compile(r"\b(?:opportunity table|opp table|filter syntax|required winning years|\bavgp\b|\btwa\b|expand(?:ed)? (?:table|view))\b", re.I),
        ("The Opportunity Table (Left Panel)",),
    ),
    (
        re.compile(r"\b(?:sharpe|risk[- ]adjusted|what makes (?:a )?strong pattern|pattern quality)\b", re.I),
        ("What Makes a Strong Pattern", "Key Concepts and Definitions"),
    ),
    (
        re.compile(r"\b(?:seasonality|seasonal patterns?|seasonal trading|what is a wave|what is an opportunity)\b", re.I),
        ("What is TradeWave", "Key Concepts and Definitions"),
    ),
    (
        re.compile(r"\b(?:trend chart|seasonal trend line)\b", re.I),
        ("Trend Chart Details (Slide 1, Lower Panel)",),
    ),
    (
        re.compile(r"\b(?:trend long|trend short|trend score|\btl\b|\bts\b|trend alignment)\b", re.I),
        ("Trend Long / Trend Short Scores (TL / TS columns in Opportunity Table)", "Trend Alignment (Wave Info Panel)"),
    ),
    (
        re.compile(r"\b(?:gain[- ]loss|bar chart|year[- ]by[- ]year|green bars?|red bars?|bar colors?)\b", re.I),
        ("Gain-Loss Bar Chart (Top Right, Wave Viewer)", "Current Year Bar: Three Possible States"),
    ),
    (
        re.compile(r"\b(?:wave stats|stats (?:view|slide|panel)|lower panel|cumulative return chart)\b", re.I),
        ("Lower Panel Views (below the Gain-Loss Bar Chart)",),
    ),
    (
        re.compile(r"\b(?:weekly price chart|weekly chart)\b", re.I),
        ("Weekly Price Chart",),
    ),
    (
        re.compile(r"\b(?:earnings date|earnings marker|earnings on (?:the )?chart)\b", re.I),
        ("Earnings Dates on Price Chart",),
    ),
    (
        re.compile(r"\b(?:price levels?|support|resistance)\b", re.I),
        ("Price Levels on Price Chart",),
    ),
    (
        re.compile(r"\b(?:price chart|current price chart|historical price chart)\b", re.I),
        ("Chart Range (Current Price Chart)", "Lower Panel Views (below the Gain-Loss Bar Chart)"),
    ),
    (
        re.compile(r"\b(?:mfe|mae|maximum favorable|maximum adverse|drawdown|excursion)\b", re.I),
        ("Key Concepts and Definitions", "Lower Panel Views (below the Gain-Loss Bar Chart)"),
    ),
    (
        re.compile(
            r"(?:\b(?:max(?:imum)?|high(?:s|est)?|best)\b.{0,40}"
            r"\b(?:min(?:imum)?|low(?:s|est)?|worst)\b|"
            r"\b(?:min(?:imum)?|low(?:s|est)?|worst)\b.{0,40}"
            r"\b(?:max(?:imum)?|high(?:s|est)?|best)\b).{0,40}"
            r"\b(?:each|every|per[- ]|year[- ]by[- ]year)",
            re.I,
        ),
        ("Key Concepts and Definitions", "Lower Panel Views (below the Gain-Loss Bar Chart)"),
    ),
    (
        re.compile(r"\b(?:twr|tradewave ratio)\b", re.I),
        ("Key Concepts and Definitions",),
    ),
    (
        re.compile(r"\b(?:pe cycle|presidential election cycle|midterm years?|pre[- ]election|post[- ]election|pe\+?[0-3])\b", re.I),
        ("Key Concepts and Definitions", "Understanding Years: A Common Point of Confusion"),
    ),
    (
        re.compile(r"\b(?:lookback|data depth|years setting|how many years|partial years|consecutive years)\b", re.I),
        ("Understanding Years: A Common Point of Confusion",),
    ),
    (
        re.compile(r"\b(?:calendar days?|holding days?|pattern length|start date|end date|date range|entry date|exit date)\b", re.I),
        ("Key Concepts and Definitions", "Wave Viewer Header Banner (above the Gain-Loss Bar Chart)"),
    ),
    (
        re.compile(r"\b(?:securities group|market group|dow 30|nasdaq 100|s&p 500|russell|wilshire|etfs?|indices|futures|commodit|forex|currenc|crypto|government bonds?)\w*\b", re.I),
        ("Securities Groups (Markets) Explained",),
    ),
    (re.compile(r"\bwatchlist\b", re.I), ("Watchlist",)),
    (re.compile(r"\bportfolio(?: manager)?\b|\breport(?:s|ing)?\b", re.I), ("Portfolio Manager (Popup Window)",)),
    (re.compile(r"\bsettings?\b", re.I), ("Settings Window",)),
    (re.compile(r"\bbest waves?\b", re.I), ("Best Waves Selector (Desktop Only)",)),
    (re.compile(r"\bmonths?\b.*\bquarters?\b|\bmonths?\s*&\s*qtrs?\b|\bseason grouping\b", re.I), ("Months & Qtrs (Time Grouping)",)),
    (re.compile(r"\breverse date range\b", re.I), ("Reverse Date Range",)),
    (re.compile(r"\bdrag(?:ging)?\b.*\b(?:window|trend chart)\b", re.I), ("Interactive Window Dragging on Trend Chart",)),
    (re.compile(r"\bdark mode\b|\blight mode\b|\btheme\b", re.I), ("Dark Mode / Light Mode",)),
    (re.compile(r"\b(?:green|red) square\b|\bdirection indicator\b", re.I), ("The Green or Red Square (Direction Indicator)", "How Trade Direction is Auto-Detected")),
    (re.compile(r"\b(?:how is|how does).*\b(?:trade )?direction\b|\bauto[- ]detect(?:ed|ion)?\b.*\bdirection\b", re.I), ("How Trade Direction is Auto-Detected",)),
    (re.compile(r"\bactive indicator\b|\bactive trade\b", re.I), ("ACTIVE Indicator (Top Banner)", "Current Year Bar: Three Possible States")),
    (re.compile(r"\breal[- ]time price column\b|\bprice column\b", re.I), ("Real-Time Price Column in Opportunity Table",)),
    (re.compile(r"\bstart date (?:nudge )?arrows?\b", re.I), ("Start Date Nudge Arrows (Desktop Only)",)),
    (re.compile(r"\bdownload\b|\bexport\b", re.I), ("Download Controls (Wave Viewer)",)),
    (re.compile(r"\bmobile\b|\bdesktop layout\b|\bphone\b|\btablet\b", re.I), ("Mobile vs Desktop Layout",)),
    (re.compile(r"\blumber\b|\blbr\b|\blb contract\b", re.I), ("Lumber Futures: LB to LBR Transition",)),
    (re.compile(r"\bdata source\b|\bdata provider\b|\bhow often.*update|\bintraday\b|\beod\b", re.I), ("Data Source and Frequency",)),
    (re.compile(r"\bnews room\b|\bseasonalmarketnews\b", re.I), ("TradeWave News Room (seasonalmarketnews.com)",)),
    (re.compile(r"\bwho uses\b|\bendorsement\b|\bnotable users?\b", re.I), ("Notable Users and Endorsements",)),
    (re.compile(r"\baccount\b|\bprofile\b|\bpassword\b", re.I), ("Account & Profile",)),
    (
        re.compile(r"\b(?:getting started|new here|teach me|tour|how (?:do|can) i use tradewave|help me use)\b", re.I),
        ("Getting Started (First-Time User)", "Teach Me How to Use TradeWave (New User Learning Path)"),
    ),
    (
        re.compile(r"\b(?:what is tradewave|what does tradewave do|how can tradewave help|why (?:use|should i use) tradewave|what can (?:tara|you) do)\b", re.I),
        ("What is TradeWave", "How Can TradeWave Help Me Trade"),
    ),
)


_STOPWORDS = {
    "about", "after", "also", "does", "from", "have", "help", "into", "just",
    "looking", "more", "show", "that", "their", "there", "these", "this", "those",
    "trade", "tradewave", "what", "when", "where", "which", "with", "would", "your",
}


def _fallback_heading(message: str, sections: Mapping[str, str]) -> str:
    """Return one likely section for an unclassified knowledge question, or ``""``."""

    if not re.search(r"\b(?:what|how|why|where|explain|define|help|can|does|is)\b", message, re.I):
        return ""
    tokens = {
        token for token in re.findall(r"[a-z0-9+]+", message.lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }
    if not tokens:
        return ""

    best_heading = ""
    best_score = 0
    for heading, section in sections.items():
        heading_words = set(re.findall(r"[a-z0-9+]+", heading.lower()))
        lead_words = set(re.findall(r"[a-z0-9+]+", section[:1200].lower()))
        score = 5 * len(tokens & heading_words) + len(tokens & lead_words)
        if score > best_score:
            best_heading, best_score = heading, score
    return best_heading if best_score >= 5 else ""


def select_topic_knowledge(message: Any, sections: Mapping[str, str]) -> KnowledgeSelection:
    """Select only the complete KB sections relevant to this user turn."""

    text = str(message or "").strip()
    selected = []
    for pattern, headings in _TOPIC_ROUTES:
        if pattern.search(text):
            for heading in headings:
                if heading in sections and heading not in selected:
                    selected.append(heading)
            # The MCP section is intentionally self-contained. General TradeWave and pricing
            # routes would repeat its facts and waste tokens on connected-AI questions.
            if "TradeWave in ChatGPT and Claude (MCP)" in selected:
                break
            if len(selected) >= MAX_TOPIC_SECTIONS:
                break

    # A specific-year request is answered from live row data, not generic product documentation.
    # Avoid adding a weak lexical KB match merely because that row question contains "pattern".
    is_specific_year_question = bool(
        re.search(r"\b(?:19|20)\d{2}\b", text)
        and re.search(r"\b(?:this|it|pattern|setup|window|year|perform|return)\b", text, re.I)
    )
    is_tara_provider_identity_question = bool(
        re.search(
            r"\b(?:is\s+tara\s+(?:using|running on|running with|powered by)|"
            r"does\s+tara\s+use)\s+(?:chatgpt|claude)\b",
            text,
            re.I,
        )
    )
    if not selected and not is_specific_year_question and not is_tara_provider_identity_question:
        fallback = _fallback_heading(text, sections)
        if fallback:
            selected.append(fallback)

    accepted = []
    chunks = []
    total = 0
    for heading in selected:
        section = str(sections.get(heading) or "").strip()
        if not section:
            continue
        if chunks and total + len(section) > MAX_TOPIC_KNOWLEDGE_CHARS:
            continue
        chunks.append(section)
        accepted.append(heading)
        total += len(section)
        if len(chunks) >= MAX_TOPIC_SECTIONS:
            break

    if not chunks:
        return KnowledgeSelection((), "")
    selected_text = (
        "=== SELECTED TRADEWAVE KNOWLEDGE FOR THIS QUESTION ===\n"
        "Use these product facts for the current topic. Do not infer omitted product details.\n"
        + "\n\n".join(chunks)
    )
    return KnowledgeSelection(tuple(accepted), selected_text)


_OPPORTUNITY_ROWS_RE = re.compile(
    r"\b(?:opportunity table|opp table|table rows?|top (?:opportunities|setups|rows)|"
    r"best (?:opportunities|setups)|strongest setups|rank(?:ed|ing)?|where does .* rank|"
    r"which (?:stocks?|setups?|opportunities)|scan|screen(?:ing)?|what(?:'s| is) available|"
    r"(?:load|open|select|pull up|show(?: me)?) (?:the )?"
    r"(?:top|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"#?\d{1,2}(?:st|nd|rd|th)?) (?:one|row|item|setup|opportunity|pick))\b",
    re.I,
)


def needs_yearly_results(message: Any) -> bool:
    """Whether row-level yearly results can materially answer this turn."""

    text = str(message or "")
    per_year_scope = re.search(
        r"\b(?:each|every)\s+(?:completed\s+|historical\s+)?year\b|"
        r"\bper[- ]year\b|\byear[- ]by[- ]year\b|"
        r"\bfor\s+(?:all|the)\s+(?:completed\s+|historical\s+)?years\b",
        text,
        re.I,
    )
    path_extremes = re.search(
        r"\b(?:mfe|mae|maximum favorable|maximum adverse|drawdown|excursion)\b|"
        r"(?:\b(?:max(?:imum)?|high(?:s|est)?|best)\b.{0,40}"
        r"\b(?:min(?:imum)?|low(?:s|est)?|worst)\b)|"
        r"(?:\b(?:min(?:imum)?|low(?:s|est)?|worst)\b.{0,40}"
        r"\b(?:max(?:imum)?|high(?:s|est)?|best)\b)",
        text,
        re.I,
    )
    if per_year_scope and path_extremes:
        return True
    if re.search(
        r"\b(?:19|20)\d{2}\b|\byear[- ]by[- ]year\b|\b(?:best|worst) year\b|"
        r"\boutliers?\b|\b(?:green|red) bars?\b|\bbar chart\b",
        text,
        re.I,
    ):
        return True
    metric = re.search(
        r"\b(?:median|standard deviation|std\.? dev|mfe|mae|drawdown|excursion)\b",
        text,
        re.I,
    )
    if not metric:
        return False
    definition = re.search(r"\b(?:what is|what does|define|explain|how does .* work)\b", text, re.I)
    loaded_reference = re.search(
        r"\b(?:this|it|its|pattern|setup|window|year|what was|how did|which year)\b",
        text,
        re.I,
    )
    return bool(loaded_reference and not definition)


def needs_opportunity_rows(message: Any) -> bool:
    """Whether the model needs actual on-screen opportunity rows in its prompt."""

    text = str(message or "")
    definition = re.search(
        r"\b(?:what is|explain|how does) (?:the )?(?:opportunity|opp) table\b",
        text,
        re.I,
    )
    if definition and not re.search(r"\b(?:my|current|top|row|rank)\b", text, re.I):
        return False
    return bool(_OPPORTUNITY_ROWS_RE.search(text))


_PROMPT_STAT_KEYS = (
    "Trade Dir",
    "Num Winners",
    "Num Losers",
    "Percent Profitable",
    "Avg Profit - All",
    "Avg Profit",
    "Avg Loss",
    "Median Profit",
    "Annualized Return",
    "Cumulative Return",
    "Std Dev",
    "Sharpe Ratio",
    "Sharpe Ratio2",
    "Trend Long",
    "Trend Short",
    "Trend Long1",
    "Trend Short1",
    "Trend Score Available",
    "next_earnings_est",
    "days_to_earnings",
)


def allowlisted_prompt_stats(stats: Any) -> Iterable[Tuple[str, str]]:
    """Yield useful derived statistics only; raw price/volume fields never enter Tara's prompt."""

    if not isinstance(stats, Mapping):
        return ()
    cleaned = []
    for key in _PROMPT_STAT_KEYS:
        value = stats.get(key)
        if value in (None, "") or isinstance(value, (Mapping, list, tuple, set)):
            continue
        safe_value = re.sub(r"\s+", " ", str(value)).strip()[:100]
        if safe_value:
            cleaned.append((key, safe_value))
    return tuple(cleaned)


def segmented_system_blocks(stable_text: str, topic_text: str, dynamic_text: str):
    """Create Anthropic system blocks with one cache breakpoint after the stable prefix."""

    blocks = [
        {
            "type": "text",
            "text": str(stable_text or "").strip(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if str(topic_text or "").strip():
        blocks.append({"type": "text", "text": str(topic_text).strip()})
    if str(dynamic_text or "").strip():
        blocks.append({"type": "text", "text": str(dynamic_text).strip()})
    return blocks


def prompt_segment_sizes(blocks: Any) -> Tuple[int, ...]:
    """Return per-block character counts for diagnostics and efficiency regression tests."""

    if isinstance(blocks, str):
        return (len(blocks),)
    if not isinstance(blocks, (list, tuple)):
        return ()
    return tuple(len(str(block.get("text") or "")) for block in blocks if isinstance(block, Mapping))
