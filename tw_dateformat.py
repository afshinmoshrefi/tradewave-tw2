"""
Shared date-range formatting for TradeWave 2.0 - single source of truth so the
range glyph never drifts across the report renderer, SMN pipeline, and home page.

House convention for ranges (dates, months, year-counts):
  * VISIBLE LABEL  (masthead, table cell, badge, heading, OG title)
        -> en-dash U+2013. Spaced when an element contains a space
           ("May 20 - Jun 8"), closed for single tokens ("2020-2024").
        -> use format_date_range() / EN_DASH here.
  * PROSE          (sentences, help text, alt text, meta description)
        -> words: "between X and Y", "from X to Y". Do NOT use this helper.
  * SLUG / URL / FILENAME
        -> ASCII only ("...-to-..."). NEVER an en-dash. Do NOT use this helper.

No em-dash (U+2014) anywhere in content (separate house rule); the prose
parenthetical replacement is " - " (spaced hyphen).
"""
import datetime

EN_DASH = "–"  # en-dash, the range glyph for visible labels


def _to_dt(d):
    if isinstance(d, (datetime.date, datetime.datetime)):
        return d
    return datetime.datetime.strptime(d, "%Y-%m-%d")


def format_date_range(date1, date2, with_year=False):
    """Visible date-range label, e.g. 'May 20 - Jun 8' or 'May 20 - Jun 8, 2026'
    (the connector is an en-dash, not the hyphen shown in this docstring).

    Spaced en-dash because the elements contain a space ('Mon DD'). Accepts
    'YYYY-MM-DD' strings or date/datetime objects. For PROSE or URL SLUGS do NOT
    use this - see the module docstring.
    """
    d1, d2 = _to_dt(date1), _to_dt(date2)
    a = f"{d1.strftime('%b')} {d1.day}"
    b = f"{d2.strftime('%b')} {d2.day}"
    if not with_year:
        return f"{a} {EN_DASH} {b}"
    if d1.year == d2.year:
        return f"{a} {EN_DASH} {b}, {d2.year}"
    return f"{a}, {d1.year} {EN_DASH} {b}, {d2.year}"
