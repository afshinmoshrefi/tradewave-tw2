"""Validation of the one thing a model may add to an engine reply: a short lead.

TW-TASK-0035 phase B. A deterministic route's reply (the "draft") is sent to the user
word for word. The model may only put a short lead in front of it that answers the
question directly. This module decides whether that lead is allowed. It is pure text
logic with no I/O, so every rule here is unit-tested against the review probes.

The lead is checked clause by clause against the draft:

* every number in a clause, with its sign and its percent mark, must stand together in
  ONE clause of the draft, next to the same qualifier words (fell / rose, average /
  median, best / worst, underlying / short-side ...), on a draft line that names the
  same symbol. That is what stops a figure being moved to another symbol, a sign or a
  direction being flipped, n being changed, or best and worst being swapped;
* a date, a superlative, a sector word, a direction word or a "full / complete / only"
  claim needs the same support;
* a stated count ("three names") must equal the number of rows in the draft;
* nothing may come from anywhere else: not the user's message, not earlier turns, not
  the knowledge base, not the model's own knowledge;
* advice, forecasts, inferences, action claims and any mention of the draft are refused.

Anything the rules cannot confirm is refused, and the caller then sends the draft alone.
"""

from __future__ import annotations

import html
import re
from typing import List, Optional, Tuple

MAX_LEAD_WORDS = 60

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.I)
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])([+\-−]?)(\d[\d,]*(?:\.\d+)?)(\s?%)?")
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
}
_COUNT_NOUN = (r"(?:names?|stocks?|etfs?|symbols?|tickers?|setups?|rows?|patterns?|windows?|"
               r"candidates?|results?|securities|companies|opportunities)")
_COUNT_RE = re.compile(
    r"\b(%s|\d{1,3})\s+(?:[A-Za-z&0-9]+\s+){0,3}?%s\b" % ("|".join(_COUNT_WORDS), _COUNT_NOUN),
    re.I)
_BOTH_RE = re.compile(r"\b(?:both|all\s+(?:three|four|five)|each)\b", re.I)

# Words that carry meaning a figure depends on. canonical form -> pattern.
_QUALIFIERS = (
    ("fell", r"\bfell\b|\bfall(?:s|en|ing)?\b"),
    ("rose", r"\brose\b|\bris(?:e|es|en|ing)\b"),
    ("up", r"\bup\s+in\b|\bwent\s+up\b|\bfinished\s+up\b"),
    ("down", r"\bdown\s+in\b|\bwent\s+down\b|\bfinished\s+down\b"),
    ("profitable", r"\bprofitable\b"),
    ("won", r"\bwon\b|\bwinn(?:er|ers|ing)\b|\bwins?\b"),
    ("loss", r"\blos(?:t|s|ses|ing|er|ers)\b"),
    ("gain", r"\bgain(?:s|ed|ing)?\b"),
    ("decline", r"\bdeclin(?:e|es|ed|ing)\b|\bdropp?(?:ed|ing|s)?\b(?!\s+inside)"),
    ("long", r"\blong\b(?![-\s]term)"),
    ("short", r"\bshort\b"),
    ("bullish", r"\bbullish\b"),
    ("bearish", r"\bbearish\b"),
    ("average", r"\baverag(?:e|ed|es|ing)\b|\bavg\b|\bmean\b"),
    ("median", r"\bmedian\b"),
    ("sharpe", r"\bsharpe\b"),
    ("winrate", r"\bwin\s*[-\s]?rate\b"),
    ("best", r"\bbest\b"),
    ("worst", r"\bworst\b"),
    ("deepest", r"\bdeepest\b"),
    ("largest", r"\blargest\b|\bbiggest\b"),
    # "latest" (the furthest into the window) and "most recent" (the newest cycle) are
    # different facts; the review caught a model answering one with the other.
    ("latest", r"\blatest\b"),
    ("recent", r"\bmost\s+recent\b|\brecent(?:ly)?\b|\bnewest\b|\blast\s+(?:cycle|year|time)\b"),
    ("earliest", r"\bearliest\b"),
    ("highest", r"\bhigh(?:est|er)\b"),
    ("lowest", r"\blow(?:est|er)\b"),
    ("strong", r"\bstrong(?:er|est)?\b"),
    ("weak", r"\bweak(?:er|est)?\b"),
    ("consistent", r"\bconsisten(?:t|cy)\b"),
    ("top", r"\btop(?:s|ped)?\b|\bleads?\b|\bled\b|\bleading\b|\bahead\b|\bbetter\b|"
            r"\bbeat(?:s|en)?\b|\boutperform\w*\b|\bedg(?:ed|es)\b|\boutpac\w+\b"),
    # a ranking the model worked out itself ("INTC was next", "CVX trailed")
    ("rank", r"\bnext\b|\bsecond\b|\bthird\b|\brunner[-\s]up\b|\bfollowed\s+by\b|\bbehind\b|"
             r"\btrail(?:s|ed|ing)?\b|\blagg?(?:s|ed|ing)?\b|\bworse\b"),
    ("mfe", r"\bmfe\b"),
    ("mae", r"\bmae\b"),
    ("underlying", r"\bunderlying\b"),
    ("shortside", r"\bshort[-\s]side\b"),
    ("ai", r"\bai\b|\bais\b|\bpredr\b|\bpmfe\b"),
    # totality: "the full screen", "the complete list", "only two"
    ("total", r"\b(?:full|complete|entire|whole|every|only|all)\b"),
    # sectors: membership is never asserted from the model's own knowledge
    ("tech", r"\btech(?:nology)?\b|\bsoftware\b|\bsemiconductors?\b|\bchips?\b"),
    ("energy", r"\benergy\b|\boil\b"),
    ("financial", r"\bfinancials?\b|\bbanks?\b|\bbanking\b"),
    ("health", r"\bhealth\s?care\b|\bpharma\w*\b|\bbiotech\w*\b"),
    ("sector", r"\bsector\b|\bindustr(?:y|ial|ials)\b|\butilit(?:y|ies)\b|\bretail\w*\b|"
               r"\bconsumer\b|\bmaterials\b|\breal\s+estate\b"),
)
_QUALIFIER_RES = tuple((name, re.compile(pattern, re.I)) for name, pattern in _QUALIFIERS)
# Qualifiers that need support even in a clause with no number.
_ALWAYS_CHECKED = frozenset({
    "fell", "rose", "up", "down", "bullish", "bearish", "long", "short", "best", "worst",
    "deepest", "largest", "latest", "recent", "earliest", "highest", "lowest", "strong", "weak",
    "consistent", "top", "rank", "total", "tech", "energy", "financial", "health", "sector", "ai",
})

_REFUSED = (
    ("advice", re.compile(
        r"\byou\s+(?:should|could|might|may\s+want)\b|\bi\s+(?:would|'d|recommend|suggest)\b|"
        r"\bconsider(?:ing)?\b|\bworth\s+(?:a\s+look|buying|shorting|considering|watching)\b|"
        r"\b(?:good|great|solid|attractive|safe|smart|ideal)\s+(?:buy|short|trade|candidate|pick|"
        r"entry|opportunity|bet|choice)\b|\bcandidate\s+to\b|\b(?:buy|sell|short)\s+(?:it|them|this)\b|"
        r"\bgo\s+(?:long|short)\b", re.I)),
    ("forecast", re.compile(
        r"\bwill\b|\bwon['’]t\b|\bgoing\s+to\b|\blikely\b|\bprobabl[ey]\b|\bexpect(?:s|ed)?\b|"
        r"\bshould\s+(?:rise|fall|gain|drop|continue|repeat)\b|\bpredict\w*\b|\bforecast\w*\b|"
        r"\bthis\s+year\b[^.]{0,40}\b(?:rise|fall|gain|drop)\b", re.I)),
    ("inference", re.compile(
        r"\btherefore\b|\bwhich\s+means\b|\bthis\s+means\b|\bthat\s+means\b|\bsuggest(?:s|ing)\b|"
        r"\bimpl(?:y|ies|ying)\b|\bindicat(?:es|ing)\b|\bbecause\b|\bso\s+(?:it|the|this|that|its)\b|"
        r"\bdue\s+to\b|\bdriven\s+by\b|\bconfirms?\b|\bproves?\b|\breliabl[ey]\b|\bsafe\b|\brisk[-\s]free\b",
        re.I)),
    ("action", re.compile(
        r"\b(?:i|we)(?:'ve|\s+have|'m|\s+am|'ll|\s+will)?\s+(?:just\s+|now\s+|also\s+)?"
        r"(?:load|loaded|loading|open|opened|opening|switch|switched|switching|set|added|adding|"
        r"saved|saving|queued|pulled|pulling|put|putting|show|showing|changed|changing)\b|"
        r"\b(?:is|are)\s+now\b|\bon\s+(?:your|the)\s+(?:chart|screen)\b", re.I)),
    ("draft", re.compile(r"\bdraft\b|\bengine\b|\binstructions?\b", re.I)),
    ("markup", re.compile(r"\[\[|<\s*/?\s*(?:function_calls?|invoke|parameter)\b|\*\*|^#", re.I | re.M)),
)

_NOT_SYMBOLS = frozenset("""
A I AI AIS API ETF ETFS MFE MAE TWR TWA PE US USA USD SR KB MCP PMFE Q1 Q2 Q3 Q4 YTD NASDAQ DOW
S&P SP THE AND OR NOT NO YES OK TV CEO IPO GDP FAQ PDF CSV UI ID N/A EST UTC
""".split())
_SYMBOL_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9&.\-])([A-Z][A-Z0-9]{1,5}(?:[.\-][A-Z0-9]{1,4})?)(?![A-Za-z0-9&])")
_BOLD_SYMBOL_RE = re.compile(r"<b>\s*([A-Z][A-Z0-9.\-=^]{0,14})\s*</b>")
_UNIT_SPLIT_RE = re.compile(r"<br\s*/?>|</?div[^>]*>|</?li[^>]*>|</?p[^>]*>|\n", re.I)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
# A comma inside "1,234" or before the year of a date ("Jun 2, 1931") is not a clause break.
_COMMA = r",\s+(?!\d{3}\b)(?!(?:19|20)\d{2}\b)"
_DRAFT_CLAUSE_SPLIT_RE = re.compile(r";\s+|" + _COMMA + r"|\s*[()]\s*")
_LEAD_CLAUSE_SPLIT_RE = re.compile(
    r";\s+|" + _COMMA + r"|\s*[():]\s+|\s*[()]\s*|\s+(?:and|but|while|whereas|versus|vs\.?|"
    r"against|with|compared\s+(?:with|to))\s+", re.I)


def plain(text) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", str(text or "")))).strip()


def _normal(raw: str) -> str:
    value = raw.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    value = value.lstrip("0")
    if not value or value.startswith("."):
        value = "0" + value
    return value


def tokens(text: str) -> List[Tuple[str, str, str]]:
    """Dates and numbers of one clause as (kind, sign, value).

    A date is one token ("nov18"), so the 31 of "Aug 31" is never a free 31. A minus is
    a sign only when it stands directly before the digits and is not a range dash
    between two numbers or dates.
    """

    out = []
    work = text
    for match in list(_DATE_RE.finditer(work)):
        out.append(("date", "", match.group(1).lower()[:3] + str(int(match.group(2)))))
    work = _DATE_RE.sub(lambda m: " " * len(m.group(0)), work)
    for match in _NUMBER_RE.finditer(work):
        sign = match.group(1).replace("−", "-")
        before = work[:match.start()].rstrip()
        if sign == "-" and before and (before[-1].isdigit() or before[-1] == "%"):
            sign = ""                                   # "10-20", "5%-10%": a range
        kind = "pct" if match.group(3) else "num"
        out.append((kind, sign, _normal(match.group(2))))
    return out


def qualifiers(text: str) -> set:
    return {name for name, pattern in _QUALIFIER_RES if pattern.search(text)}


def _token_supported(token, pool) -> bool:
    kind, sign, value = token
    for other_kind, other_sign, other_value in pool:
        if other_kind != kind or other_value != value:
            continue
        if sign == other_sign or (sign == "" and other_sign == "+"):
            return True
    return False


class Draft:
    """The engine reply broken into lines (which name symbols) and clauses (which hold figures)."""

    def __init__(self, draft_html: str):
        self.html = str(draft_html or "")
        self.symbols = []
        for match in _BOLD_SYMBOL_RE.finditer(self.html):
            if match.group(1) not in self.symbols:
                self.symbols.append(match.group(1))
        text = plain(self.html)
        for match in _SYMBOL_TOKEN_RE.finditer(text):
            token = match.group(1)
            if token not in _NOT_SYMBOLS and token not in self.symbols and re.search(
                    r"[A-Z]{2}", token):
                self.symbols.append(token)
        self.units = []                       # (unit text, [clauses])
        self.rows = 0
        for piece in _UNIT_SPLIT_RE.split(self.html):
            is_row = bool(re.match(r"\s*(?:\d{1,2}[.)]\s*|[•\-–]\s*)?<b>\s*[A-Z]", piece))
            piece_plain = plain(piece)
            if not piece_plain:
                continue
            if is_row and re.search(r"\d", piece_plain):
                self.rows += 1
                parts = [piece_plain]
            else:
                parts = _SENTENCE_SPLIT_RE.split(piece_plain)
            for part in parts:
                if part.strip():
                    self.units.append(
                        (part, [c for c in _DRAFT_CLAUSE_SPLIT_RE.split(part) if c and c.strip()]))

    def unit_names(self, unit: str, symbol: str) -> bool:
        return bool(re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(symbol), unit))

    def supports(self, symbol: Optional[str], wanted_tokens, wanted_qualifiers) -> bool:
        """One draft clause, on a line that names ``symbol``, holds all of it together."""

        single_subject = len(self.symbols) <= 1
        for unit, clauses in self.units:
            if symbol and not single_subject and not self.unit_names(unit, symbol):
                continue
            unit_qualifiers = qualifiers(unit)
            for clause in clauses + ([unit] if not wanted_tokens else []):
                pool = tokens(clause)
                if not all(_token_supported(token, pool) for token in wanted_tokens):
                    continue
                have = qualifiers(clause)
                # Direction and totality words must sit in the same clause as the figure;
                # a line-level word (the row's own "short") may qualify a no-number clause.
                scope = have if wanted_tokens else (have | unit_qualifiers)
                if wanted_qualifiers <= scope:
                    return True
        return False


def _lead_symbols(clause: str, draft: Draft) -> Tuple[List[str], List[str]]:
    known, unknown = [], []
    for match in _SYMBOL_TOKEN_RE.finditer(clause):
        token = match.group(1)
        if token in draft.symbols:
            if token not in known:
                known.append(token)
        elif token not in _NOT_SYMBOLS and not re.search(
                r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(token), plain(draft.html)):
            unknown.append(token)
    return known, unknown


def validate_lead(lead, draft_html) -> Tuple[bool, str]:
    """(True, "") when the lead adds nothing the draft does not say; else (False, reason)."""

    text = plain(lead)
    if not text:
        return False, "empty"
    if re.search(r"<\s*(?:br|div|li|ul|ol|table|a)\b", str(lead), re.I):
        return False, "markup"
    if len(text.split()) > MAX_LEAD_WORDS:
        return False, "length"
    for reason, pattern in _REFUSED:
        if pattern.search(text):
            return False, reason
    draft = Draft(draft_html)
    draft_plain = plain(draft.html)
    if text in draft_plain:
        return False, "repeats_draft"
    for match in _COUNT_RE.finditer(text):
        raw = match.group(1).lower()
        count = _COUNT_WORDS.get(raw) if not raw.isdigit() else int(raw)
        if draft.rows and count != draft.rows and not raw.isdigit():
            return False, "count"
        if draft.rows and raw.isdigit() and count != draft.rows and not draft.supports(
                None, [("num", "", raw)], set()):
            return False, "count"
        if not draft.rows and not raw.isdigit():
            return False, "count"
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        carried = None
        for clause in _LEAD_CLAUSE_SPLIT_RE.split(sentence):
            if not clause or not clause.strip():
                continue
            known, unknown = _lead_symbols(clause, draft)
            if unknown:
                return False, "symbol_not_in_draft"
            if known:
                carried = known
            subjects = known or carried or [None]
            if _BOTH_RE.search(clause) and len(draft.symbols) > 1 and not known:
                subjects = list(draft.symbols)
            wanted_tokens = tokens(clause)
            found = qualifiers(clause)
            if wanted_tokens:
                wanted_qualifiers = found
            else:
                wanted_qualifiers = found & _ALWAYS_CHECKED
                if not wanted_qualifiers:
                    continue
            for subject in subjects:
                if not draft.supports(subject, wanted_tokens, wanted_qualifiers):
                    return False, "unsupported:" + (subject or "-")
    return True, ""


def compose(lead, draft_html) -> str:
    """The lead, then the engine reply exactly as the engine wrote it."""

    return "%s<br><br>%s" % (str(lead).strip(), str(draft_html))
