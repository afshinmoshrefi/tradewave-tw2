"""Shared TradeWave text utilities.

Per a hard project rule, em dashes (U+2014) are forbidden in any
TradeWave or SMN content - source code strings, HTML output,
templates, anywhere. Use ` - ` (space-hyphen-space) instead.

Apply `no_em_dash()` to any text that hits a user before serving as a
defensive backstop, even though the source-code sweep should already
keep things clean.
"""
import re

_EM_DASH_RE = re.compile(r"[ \t]*(?:—|&mdash;|&#8212;|&#x2014;)[ \t]*")


def no_em_dash(s: str) -> str:
    """Replace every em dash variant with ` - `, normalizing surrounding spaces.

    Idempotent. Safe to call repeatedly on already-clean text.
    """
    return _EM_DASH_RE.sub(" - ", s)
