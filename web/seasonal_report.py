"""
Free personalized seasonal report (lead magnet).

Given up to 3 tickers, fetch each one's seasonal record from the appserver
(ChartData4 = the literal fixed-window engine) over the next ~30, ~90 and ~120
days, computed two ways: the last 10 completed years, and the last 10 midterm
(PE-phase-2) election years. Render a LIGHT, table-based HTML email + plain-text
part (light = the email convention; the website + confirm landing stay dark).
NO forward predictions: every figure is the historical record only.

Data path notes (verified 2026-06-22):
  - Mint a service token: GET {appserver}/login/api/{SERVICE_API_KEY} -> {token}.
  - ChartData4/{market}/{date}/{symbol}/{daysOut}/{yrs}?token=...  honors daysOut
    LITERALLY (the gateway /analyze auto-snaps to a detected window - do not use it
    for fixed horizons). yrs="10" (consecutive) or "pe2-10" (midterm phase 2).
  - yrs="10" returns 11 rows incl. the CURRENT in-progress year, whose window is in
    the future -> we DROP the current year so "X of 10 years" is honest, and we
    compute win-rate + avg directly from the per-year rows we display (the dot strip
    and the headline stat can never disagree).
"""
import os
import logging
import datetime
import html as _html
import requests

log = logging.getLogger("tw2.seasonal_report")

# EMAIL palette - LIGHT theme. Emails render light (the convention; dark-bg emails
# read as off and get mangled by client dark-mode); the website + the confirm landing
# page stay dark. Brand kept via the purple accent + the green/red per-year data.
BG = "#F4F6FB"; PANEL = "#FFFFFF"; PANEL2 = "#F1F4FA"
INK = "#0E1726"; MUTED = "#56627A"; FAINT = "#8893A6"
ACCENT = "#7C5CFF"; WIN = "#1F9D63"; LOSS = "#D6455F"
LINE = "#E4E8F0"

# email-safe font stacks (no remote <link> - Gmail/Outlook strip it; rely on fallbacks)
SANS = "'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"

HORIZONS = (30, 90, 120)
SMALL_SAMPLE = 7   # < this many years in a series -> label it honestly
# stocks first (gateway primary-listing preference: S&P 500 -> DOW -> NASDAQ),
# then ETF / index / other markets; Korea (14,15) is dropped.
MARKET_ORDER = [2, 0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16]

SIGNUP_URL = ("https://tradewave.ai/signup?utm_source=lead_report"
              "&utm_medium=email&utm_campaign=seasonal_report")

# fallback display names; production wires _company_name() to the securities list
_NAMES = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.", "NVDA": "NVIDIA Corp.",
    "AMZN": "Amazon.com Inc.", "GOOGL": "Alphabet Inc.", "META": "Meta Platforms",
    "TSLA": "Tesla Inc.", "SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ Trust",
}


# --------------------------------------------------------------------------- IO
def _cfg(name):
    try:
        import config as _c
        return getattr(_c, name, "")
    except Exception:
        return ""


def _appserver_url(override=None):
    url = override or os.environ.get("TW2_APPSERVER_URL") or _cfg("appserver_url")
    return (url or "http://127.0.0.1:5000").rstrip("/")


def _service_key(override=None):
    key = override or os.environ.get("SERVICE_API_KEY") or _cfg("SERVICE_API_KEY")
    if not key:
        raise RuntimeError("SERVICE_API_KEY not available")
    return key


def mint_token(appserver_url=None, service_key=None, timeout=20):
    url = "%s/login/api/%s" % (_appserver_url(appserver_url), _service_key(service_key))
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    tok = r.json().get("token")
    if not tok:
        raise RuntimeError("service login returned no token")
    return tok


def _chartdata(market, date, symbol, days_out, yrs, token, appserver_url=None, timeout=45):
    url = "%s/ChartData4/%s/%s/%s/%s/%s?token=%s" % (
        _appserver_url(appserver_url), market, date, symbol.upper(), days_out, yrs, token)
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


# ------------------------------------------------------------------- transforms
def _extract(chart):
    """All [(year, net_pct)] dict-rows, oldest->newest. Returns [] for junk/unknown
    symbols (the appserver returns a non-empty but non-per-year ChartData4 - e.g. a
    list of strings - for an invalid ticker, so we accept ONLY real year/pct rows)."""
    rows = (chart or {}).get("ChartData4") or (chart or {}).get("chartData4") or []
    out = []
    for e in rows:
        if not isinstance(e, dict):
            continue
        try:
            yr = int(e.get("year"))
            net = float(str(e.get("pct")).split(",")[0])
        except (TypeError, ValueError):
            continue
        out.append((yr, net))
    out.sort(key=lambda t: t[0])
    return out


def _per_year(chart, exclude_year):
    """Real per-year rows minus the current in-progress year (its window is future)."""
    rows = _extract(chart)
    kept = [(yr, net) for yr, net in rows if yr < exclude_year]
    if rows and (len(rows) - len(kept)) != 1:
        # expect exactly one in-progress year dropped; a shape regression would skew
        # the tally silently, so leave a breadcrumb.
        log.debug("per_year dropped=%d (expected 1) rows=%d", len(rows) - len(kept), len(rows))
    return kept


def _summarize(per_year):
    n = len(per_year)
    if not n:
        return None
    wins = sum(1 for _, net in per_year if net > 0)
    avg = sum(net for _, net in per_year) / n
    return {"per_year": per_year, "n": n, "wins": wins,
            "win_rate": wins / n, "avg": avg, "small": n < SMALL_SAMPLE}


def _resolve_market(symbol, token, appserver_url=None):
    """First market id whose ChartData4 has rows for this symbol, else None."""
    today = datetime.date.today()
    for m in MARKET_ORDER:
        c = _chartdata(m, today.isoformat(), symbol, 30, "10", token, appserver_url)
        if _extract(c):   # only a real per-year series counts as coverage
            return m
    return None


def _company_name(symbol, market, token, appserver_url=None):
    # TODO(prod): wire to the appserver securities list for live names.
    return _NAMES.get(symbol.upper(), "")


def resolve_coverage(tickers, appserver_url=None, service_key=None, token=None):
    """Cheap synchronous coverage check (mint + ~1-3 calls/ticker). Lets the
    route reject an all-uncovered request before promising an email. Returns
    {covered, not_covered, markets, token}."""
    token = token or mint_token(appserver_url, service_key)
    seen, covered, missing, mkts = set(), [], [], {}
    for t in (tickers or []):
        s = (t or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        m = _resolve_market(s, token, appserver_url)
        if m is None:
            missing.append(s)
        else:
            covered.append(s); mkts[s] = m
        if len(seen) >= 3:
            break
    return {"covered": covered, "not_covered": missing, "markets": mkts, "token": token}


def build_report_data(tickers, as_of=None, appserver_url=None, service_key=None,
                      token=None, markets=None):
    """
    tickers: list of raw strings (up to 3 used). markets: optional {sym: market_id}
    from resolve_coverage to skip re-resolution. Returns:
      {as_of, as_of_label, phase, tickers:[...], not_covered:[...]}
    """
    as_of = as_of or datetime.date.today()
    phase = as_of.year % 4                      # 2026 % 4 == 2 -> midterm
    date_s = as_of.isoformat()
    consec_yrs = "10"
    midterm_yrs = "pe%d-10" % phase
    token = token or mint_token(appserver_url, service_key)
    markets = markets or {}

    seen, clean = set(), []
    for t in (tickers or []):
        s = (t or "").strip().upper()
        if s and s not in seen:
            seen.add(s); clean.append(s)
        if len(clean) == 3:
            break

    out, missing = [], []
    for sym in clean:
        market = markets.get(sym)
        if market is None:
            market = _resolve_market(sym, token, appserver_url)
        if market is None:
            missing.append(sym); continue
        horizons = {}
        for d in HORIZONS:
            cc = _chartdata(market, date_s, sym, d, consec_yrs, token, appserver_url)
            mc = _chartdata(market, date_s, sym, d, midterm_yrs, token, appserver_url)
            horizons[d] = {
                "consec": _summarize(_per_year(cc, as_of.year)),
                "midterm": _summarize(_per_year(mc, as_of.year)),
            }
        ranked = [(d, horizons[d]["consec"]) for d in HORIZONS if horizons[d]["consec"]]
        ranked.sort(key=lambda x: (x[1]["win_rate"], x[1]["avg"]), reverse=True)
        out.append({
            "symbol": sym,
            "name": _company_name(sym, market, token, appserver_url),
            "market": market,
            "horizons": horizons,
            "strongest": ranked[0][0] if ranked else None,
        })
    return {
        "as_of": as_of,
        "as_of_label": as_of.strftime("%B %-d, %Y"),
        "phase": phase,
        "tickers": out,
        "not_covered": missing,
    }


# ---------------------------------------------------------------------- render
def _pct(v):
    return ("+%.1f%%" if v >= 0 else "%.1f%%") % v


def _stat_tile(caption, s):
    cap = caption + (" - small sample" if (s and s.get("small")) else "")
    if not s:
        body = ('<div style="font-family:%s;font-size:13px;color:%s">no data</div>'
                % (MONO, FAINT))
    else:
        avg_c = WIN if s["avg"] >= 0 else LOSS
        # win-rate count stays neutral (INK) so colour signals up/down, never "good setup"
        body = (
            '<div style="font-family:%s;font-size:22px;font-weight:700;color:%s;line-height:1.1">'
            '%d <span style="color:%s;font-size:14px;font-weight:400">of %d</span></div>'
            '<div style="font-family:%s;font-size:13px;color:%s;margin-top:5px">avg %s</div>'
            % (MONO, INK, s["wins"], FAINT, s["n"], MONO, avg_c, _pct(s["avg"]))
        )
    return (
        '<td class="tile" width="50%%" valign="top" style="padding:4px">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" '
        'bgcolor="%s" style="background:%s;border:1px solid %s;border-radius:10px">'
        '<tr><td style="padding:12px 14px">'
        '<div style="font-family:%s;font-size:10px;letter-spacing:1.2px;text-transform:uppercase;'
        'color:%s;margin-bottom:8px">%s</div>%s</td></tr></table></td>'
        % (PANEL2, PANEL2, LINE, MONO, FAINT, _html.escape(cap), body)
    )


def _dot_strip(s, label, show_years=True):
    if not s or not s["per_year"]:
        return ""
    cells, years = [], []
    for yr, net in s["per_year"]:
        up = net > 0
        cells.append(
            '<td class="dot" width="20" height="18" align="center" valign="middle" '
            'bgcolor="%s" style="background:%s;color:%s">%s</td>'
            % (WIN if up else LOSS, WIN if up else LOSS, "#FFFFFF", "+" if up else "-"))
        if show_years:
            years.append(
                '<td width="20" align="center" style="font-family:%s;font-size:9px;color:%s;'
                'padding-top:4px">%s</td>' % (MONO, FAINT, str(yr)[-2:]))
    years_row = ("<tr>%s</tr>" % "".join(years)) if show_years else ""
    return (
        '<div style="font-family:%s;font-size:9px;letter-spacing:1px;text-transform:uppercase;'
        'color:%s;margin:10px 0 6px">%s, Per Year</div>'
        '<table role="presentation" cellpadding="0" cellspacing="3" border="0"><tr>%s</tr>'
        '%s</table>' % (MONO, FAINT, _html.escape(label), "".join(cells), years_row)
    )


def _gloss(sym, d, s):
    if not s:
        return ""
    lead = ("A perfect past record is still a base rate, not a forecast"
            if s["win_rate"] >= 0.999
            else "Past frequency is a base rate, not a forecast")
    txt = ("Over the last %d years, %s finished higher in this ~%d-day window %d of %d "
           "times, average %s. %s - any year, including this one, can be the year it does "
           "not repeat." % (s["n"], sym, d, s["wins"], s["n"], _pct(s["avg"]), lead))
    return ('<div style="font-family:%s;font-size:12px;font-style:italic;color:%s;'
            'line-height:1.5;margin-top:12px">%s</div>'
            % (SANS, MUTED, _html.escape(txt)))


def _ticker_card(t, as_of_label):
    sym = _html.escape(t["symbol"]); name = _html.escape(t["name"] or "")
    rows = [
        '<tr><td style="padding:16px 16px 4px">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0"><tr>'
        '<td valign="bottom" style="font-family:%s;font-size:24px;font-weight:700;color:%s">%s</td>'
        '<td align="right" valign="bottom" style="font-family:%s;font-size:13px;color:%s">%s</td>'
        '</tr></table>'
        '<div style="font-family:%s;font-size:10px;color:%s;margin-top:4px">'
        'Windows measured from %s</div></td></tr>'
        % (MONO, INK, sym, SANS, FAINT, name, MONO, FAINT, as_of_label)
    ]
    for d in HORIZONS:
        h = t["horizons"][d]
        c, m = h["consec"], h["midterm"]
        consec_n = c["n"] if c else 10
        strip_c = _dot_strip(c, "Last %d Years" % consec_n)
        strip_m = _dot_strip(m, "Midterm Years", show_years=False)
        gloss = _gloss(t["symbol"], d, c) if t["strongest"] == d else ""
        rows.append(
            '<tr><td style="padding:10px 16px 4px">'
            '<div style="font-family:%s;font-size:12px;font-weight:700;letter-spacing:1px;'
            'text-transform:uppercase;color:%s;margin:6px 0 8px">Next ~%d Days</div>'
            '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0"><tr>%s%s</tr></table>'
            '%s%s%s</td></tr>'
            % (MONO, ACCENT, d,
               _stat_tile("Last 10 Years", c), _stat_tile("Midterm Years", m),
               strip_c, strip_m, gloss))
    return (
        '<tr><td style="padding:8px 0">'
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" '
        'bgcolor="%s" style="background:%s;border:1px solid %s;border-radius:12px">'
        '%s<tr><td style="height:12px"></td></tr></table></td></tr>'
        % (PANEL, PANEL, LINE, "".join(rows))
    )


_DISCLAIMER = (
    "This report is educational research, not investment advice. It summarizes the "
    "historical seasonal record for the symbols you entered; it is not personalized "
    "advice, a recommendation, a solicitation, or an offer to buy or sell any security, "
    "and it is not a prediction of how these symbols will perform this year or any future "
    "period. TradeWave is an educational research platform operated by Tara Data Research "
    "LLC, which is not a registered investment adviser or broker-dealer and does not "
    "execute trades. The seasonal statistics are deterministic historical measurements; "
    "the AI score is used only to rank and calibrate patterns and does not predict "
    "outcomes. All data is historical and provided for informational and educational "
    "purposes only. Past results never guarantee future ones, and any year - including "
    "this one - can be a losing year. Trading and investing involve substantial risk, "
    "including the possible loss of principal. You received this email because you "
    "requested a free seasonal research report at tradewave.ai."
)


def _how_to_read():
    items = [
        ("Win rate.", "\"8 of 10\" means the window closed higher in 8 of the last 10 years. "
                      "It is a count of history, never a forecast of this year."),
        ("Average return.", "The mean move across those same windows, losing years included "
                            "and pulling it down - nothing is trimmed."),
        ("Midterm years.", "The subset of past U.S. midterm-election years, shown because "
                           "markets have behaved differently in that part of the cycle. "
                           "Smaller sample, so the count shows its own denominator."),
        ("The squares.", "One per year, oldest to newest. Green closed up, pink closed down. "
                         "The whole record, wins and losses both."),
    ]
    li = "".join(
        '<div style="font-family:%s;font-size:13px;color:%s;line-height:1.55;margin-bottom:10px">'
        '<b style="color:%s">%s</b> %s</div>'
        % (SANS, MUTED, INK, _html.escape(b), _html.escape(body)) for b, body in items)
    return (
        '<tr><td style="padding:8px 0"><table role="presentation" width="100%%" '
        'cellpadding="0" cellspacing="0" bgcolor="%s" style="background:%s;'
        'border-left:3px solid %s;border-radius:8px"><tr><td style="padding:22px 24px">'
        '<div style="font-family:%s;font-size:11px;letter-spacing:1.6px;text-transform:uppercase;'
        'color:%s;margin-bottom:14px">How to Read This</div>%s</td></tr></table></td></tr>'
        % (PANEL, PANEL, ACCENT, MONO, ACCENT, li))


def _cta_button(label, url):
    lbl = _html.escape(label)
    return (
        '<!--[if mso]>'
        '<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" '
        'href="%s" style="height:48px;v-text-anchor:middle;width:320px;" arcsize="21%%" stroke="f" fillcolor="%s">'
        '<w:anchorlock/><center style="color:#ffffff;font-family:%s;font-size:15px;font-weight:600;">%s</center>'
        '</v:roundrect><![endif]-->'
        '<!--[if !mso]><!-->'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>'
        '<td bgcolor="%s" style="background:%s;border-radius:10px">'
        '<a href="%s" style="display:inline-block;font-family:%s;font-size:15px;font-weight:600;'
        'color:#ffffff;text-decoration:none;padding:14px 30px;border-radius:10px">%s</a>'
        '</td></tr></table><!--<![endif]-->'
        % (url, ACCENT, SANS, lbl, ACCENT, ACCENT, url, SANS, lbl))


_EMAIL_STYLE = (
    "@media only screen and (max-width:600px){"
    ".container{width:100%%!important;max-width:100%%!important}"
    ".tile{display:block!important;width:100%%!important;box-sizing:border-box}}"
    ".dot{font-family:%s;font-size:11px;font-weight:700;border-radius:3px}"
) % MONO


def render_email_html(data, unsubscribe_url="{{ unsubscribe_url }}",
                      mailing_address="1 Washington Mall #1129, Boston, MA 02108"):
    syms = [t["symbol"] for t in data["tickers"]]
    sym_list = ", ".join(syms) if syms else "your stocks"
    cards = "".join(_ticker_card(t, data["as_of_label"]) for t in data["tickers"])
    notcov = ""
    if data.get("not_covered"):
        notcov = ('<div style="font-family:%s;font-size:13px;color:%s;margin-top:12px">'
                  'Not in our 15 markets yet: %s. Check the spelling, or try a US stock, '
                  'index, or ETF.</div>'
                  % (SANS, MUTED, _html.escape(", ".join(data["not_covered"]))))
    preheader = ("The last 10 years and past election years for each stock, with the full "
                 "per-year record. Historical research, not advice.")
    return """<!doctype html><html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
<title>Your seasonal report</title>
<style>{style}</style></head>
<body style="margin:0;padding:0;background:{BG};" bgcolor="{BG}">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:{BG}">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG}"><tr><td align="center" style="padding:0">
<table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px">

<tr><td bgcolor="{PANEL}" style="background:{PANEL};padding:22px 24px;border-bottom:1px solid {LINE}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="font-family:{SANS};font-size:24px;font-weight:800;color:{INK}">Trade<span style="color:{ACCENT}">Wave</span></td>
<td align="right" style="font-family:{MONO};font-size:11px;letter-spacing:2.2px;color:{ACCENT}">SEASONAL REPORT</td>
</tr></table></td></tr>
<tr><td style="height:3px;background:{ACCENT};line-height:3px;font-size:3px">&nbsp;</td></tr>

<tr><td bgcolor="{BG}" style="background:{BG};padding:34px 24px 12px">
<div style="font-family:{MONO};font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:{ACCENT};margin-bottom:12px">Your Stocks, the Historical Record</div>
<div style="font-family:{SANS};font-size:26px;font-weight:800;color:{INK};line-height:1.2;margin-bottom:14px">Here Is What History Says About Your Stocks</div>
<div style="font-family:{SANS};font-size:15px;color:{MUTED};line-height:1.6">You asked for the seasonal record on {syms}. Here it is - how often each one finished higher in the same calendar windows in past years, the average move, and the full year-by-year tally. The receipts, not just a number. Same research we run on every market in TradeWave, shown here for the symbols you entered.</div>
{notcov}
<div style="font-family:{SANS};font-size:12px;color:{FAINT};line-height:1.5;margin-top:14px">Historical research filtered to the symbols you asked about, not personalized advice. As of {asof}. Not a prediction, a recommendation, or advice.</div>
</td></tr>

<tr><td style="padding:12px 24px 0" bgcolor="{BG}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{cards}</table></td></tr>

<tr><td style="padding:8px 24px" bgcolor="{BG}"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{howto}</table></td></tr>

<tr><td bgcolor="{BG}" style="background:{BG};padding:34px 24px 30px;border-top:1px solid {LINE}" align="center">
<div style="font-family:{MONO};font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:{ACCENT};margin-bottom:10px">See It Move</div>
<div style="font-family:{SANS};font-size:22px;font-weight:800;color:{INK};line-height:1.25;margin-bottom:12px">This Is the Static Version, the Live One Talks Back</div>
<div style="font-family:{SANS};font-size:14px;color:{MUTED};line-height:1.6;margin-bottom:22px">Open any of these stocks in TradeWave and the full per-year chart redraws live - stretch the lookback to twenty years or every year on record, see the historical seasonal path drawn over this year's calendar, and ask Tara, in plain English, why one window beats another. Every account starts with 7 days of the full platform - every one of the 15 markets, every metric, the model, and Tara.</div>
{cta}
<div style="font-family:{SANS};font-size:12px;color:{FAINT};margin-top:14px">No credit card. Full platform for 7 days, then a free plan that never expires.</div>
</td></tr>

<tr><td bgcolor="{BG}" style="background:{BG};padding:0 24px 24px" align="center">
<div style="font-family:{SANS};font-size:12px;color:{FAINT}">Every figure above opens to its full per-year table in the app. <a href="https://tradewave.ai/scorecard" style="color:{MUTED}">Inspect the public ledger</a></div>
</td></tr>

<tr><td bgcolor="{PANEL}" style="background:{PANEL};padding:22px 24px;border-top:1px solid {LINE}">
<div style="font-family:{SANS};font-size:11px;color:{FAINT};line-height:1.6">{disc}</div>
<div style="font-family:{MONO};font-size:10px;color:{FAINT};margin-top:14px"><a href="{unsub}" style="color:{MUTED}">Unsubscribe</a> &middot; <a href="https://tradewave.ai/privacy" style="color:{MUTED}">Privacy</a> &middot; <a href="https://tradewave.ai/terms" style="color:{MUTED}">Terms</a></div>
<div style="font-family:{MONO};font-size:10px;color:{FAINT};margin-top:8px">Tara Data Research LLC &middot; {addr} &middot; &copy; 2026</div>
</td></tr>

</table></td></tr></table></body></html>""".format(
        BG=BG, PANEL=PANEL, INK=INK, MUTED=MUTED, FAINT=FAINT, ACCENT=ACCENT, LINE=LINE,
        SANS=SANS, MONO=MONO, style=_EMAIL_STYLE, pre=preheader,
        syms=_html.escape(sym_list), asof=data["as_of_label"], notcov=notcov,
        cards=cards, howto=_how_to_read(),
        cta=_cta_button("Start Free - Full Access for 7 Days", SIGNUP_URL),
        disc=_DISCLAIMER, unsub=unsubscribe_url, addr=mailing_address)


def render_email_text(data, unsubscribe_url="{{ unsubscribe_url }}",
                      mailing_address="1 Washington Mall #1129, Boston, MA 02108"):
    lines = ["TradeWave - Your Seasonal Report", "As of %s" % data["as_of_label"], ""]
    lines.append("Historical seasonal record for the symbols you entered. Educational "
                 "research only, not advice. Past results never guarantee future ones.")
    lines.append("")
    for t in data["tickers"]:
        lines.append("%s %s" % (t["symbol"], ("- " + t["name"]) if t["name"] else ""))
        for d in HORIZONS:
            h = t["horizons"][d]
            def fmt(s):
                return ("%d of %d, avg %s" % (s["wins"], s["n"], _pct(s["avg"]))) if s else "no data"
            lines.append("  ~%dd: last 10 yrs %s | midterm %s"
                         % (d, fmt(h["consec"]), fmt(h["midterm"])))
        lines.append("")
    if data["not_covered"]:
        lines.append("Not in our 15 markets yet: %s" % ", ".join(data["not_covered"]))
        lines.append("")
    lines.append("See it live - start free, full access for 7 days, no card: %s" % SIGNUP_URL)
    lines.append("")
    lines.append(_DISCLAIMER)
    lines.append("")
    lines.append("Unsubscribe: %s" % unsubscribe_url)
    lines.append("Tara Data Research LLC - %s" % mailing_address)
    return "\n".join(lines)


# ----------------------------------------------------------- double opt-in
def render_confirm_email(confirm_url, tickers,
                         mailing_address="1 Washington Mall #1129, Boston, MA 02108"):
    """The lightweight DOUBLE-OPT-IN email: a single Confirm button. No report data -
    the heavy per-ticker report is only built + sent after this link is clicked.
    Returns (subject, body_text, html)."""
    syms = ", ".join((t or "").upper() for t in (tickers or []) if t) or "your stocks"
    subject = "Confirm your free seasonal report"
    text = ("TradeWave - confirm your free seasonal report\n\n"
            "You asked for the historical seasonal record on %s. Confirm your email and we "
            "will send it, usually within a couple of minutes.\n\nConfirm: %s\n\n"
            "If you did not request this, just ignore this email - nothing will be sent.\n\n"
            "Educational historical research, not advice. Tara Data Research LLC - %s"
            % (syms, confirm_url, mailing_address))
    html = """<!doctype html><html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
<title>Confirm your free seasonal report</title></head>
<body style="margin:0;padding:0;background:{BG}" bgcolor="{BG}">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;color:{BG}">Confirm your email and we will send your free seasonal report.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="{BG}" style="background:{BG}"><tr><td align="center" style="padding:0">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px">
<tr><td bgcolor="{PANEL}" style="background:{PANEL};padding:22px 24px;border-bottom:1px solid {LINE}">
<span style="font-family:{SANS};font-size:24px;font-weight:800;color:{INK}">Trade<span style="color:{ACCENT}">Wave</span></span></td></tr>
<tr><td style="height:3px;background:{ACCENT};line-height:3px;font-size:3px">&nbsp;</td></tr>
<tr><td bgcolor="{BG}" style="background:{BG};padding:38px 28px" align="center">
<div style="font-family:{MONO};font-size:11px;letter-spacing:1.8px;text-transform:uppercase;color:{ACCENT};margin-bottom:12px">One Last Step</div>
<div style="font-family:{SANS};font-size:24px;font-weight:800;color:{INK};line-height:1.25;margin-bottom:14px">Confirm Your Free Seasonal Report</div>
<div style="font-family:{SANS};font-size:15px;color:{MUTED};line-height:1.6;margin-bottom:26px">You asked for the historical seasonal record on <b style="color:{INK}">{syms}</b>. Confirm your email and we will send it, usually within a couple of minutes.</div>
{cta}
<div style="font-family:{SANS};font-size:13px;color:{FAINT};line-height:1.5;margin-top:24px">If you did not request this, just ignore this email - nothing will be sent.</div>
</td></tr>
<tr><td bgcolor="{PANEL}" style="background:{PANEL};padding:20px 24px;border-top:1px solid {LINE}">
<div style="font-family:{SANS};font-size:11px;color:{FAINT};line-height:1.6">Educational historical research, not investment advice or a recommendation. Operated by Tara Data Research LLC.</div>
<div style="font-family:{MONO};font-size:10px;color:{FAINT};margin-top:8px">Tara Data Research LLC &middot; {addr} &middot; &copy; 2026</div>
</td></tr>
</table></td></tr></table></body></html>""".format(
        BG=BG, PANEL=PANEL, INK=INK, MUTED=MUTED, FAINT=FAINT, ACCENT=ACCENT, LINE=LINE,
        SANS=SANS, MONO=MONO, syms=_html.escape(syms),
        cta=_cta_button("Confirm and Send My Report", confirm_url), addr=mailing_address)
    return subject, text, html


def render_confirm_landing(state, signup_url="https://tradewave.ai/signup"):
    """Branded web page shown after the confirm link is clicked.
    state in {ok, used, expired, invalid}."""
    heads = {
        "ok": ("You Are Confirmed - Your Report Is on Its Way",
               "We are building your seasonal report now. It usually lands in your inbox within a couple of minutes.",
               "Explore TradeWave Free"),
        "used": ("This Link Was Already Used",
                 "Your report is already on its way, or sitting in your inbox. Check spam or promotions if you do not see it.",
                 "Explore TradeWave Free"),
        "expired": ("This Link Has Expired",
                    "Confirmation links last 7 days. You can request a fresh seasonal report any time.",
                    "Get a Fresh Report"),
        "invalid": ("We Could Not Find That Link",
                    "This confirmation link is not valid. You can request a seasonal report any time.",
                    "Get a Report"),
    }
    h, sub, btn = heads.get(state, heads["invalid"])
    btn_url = signup_url if state == "ok" else "https://tradewave.ai/"
    mark = '<div class="mark">&#10003;</div>' if state == "ok" else ''
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>TradeWave</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">'
        '<style>'
        'body{margin:0;background:#0B1220;color:#EAF0F8;font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;'
        'background-image:radial-gradient(900px 460px at 50% -8%,rgba(124,92,255,.14),transparent 60%)}'
        '.wrap{max-width:560px;margin:0 auto;padding:14vh 24px;text-align:center}'
        '.brand{font-weight:800;font-size:28px;letter-spacing:-.02em;margin-bottom:36px}.brand b{color:#7C5CFF}'
        '.mark{width:64px;height:64px;border-radius:50%;margin:0 auto 22px;display:grid;place-items:center;font-size:1.8rem;'
        'background:rgba(63,182,139,.12);border:1px solid rgba(63,182,139,.45);color:#3FB68B}'
        'h1{font-size:1.7rem;line-height:1.2;margin:0 0 14px}p{color:#9FB0C8;line-height:1.6;margin:0 0 28px}'
        '.btn{display:inline-block;background:#7C5CFF;color:#fff;font-weight:600;padding:14px 26px;border-radius:10px;'
        'text-decoration:none;box-shadow:0 8px 30px rgba(124,92,255,.28)}'
        '.fine{color:#6B7A93;font-size:.8rem;margin-top:26px}'
        '</style></head><body><div class="wrap">'
        '<div class="brand">Trade<b>Wave</b></div>'
        + mark
        + '<h1>' + _html.escape(h) + '</h1><p>' + _html.escape(sub) + '</p>'
        + '<a class="btn" href="' + btn_url + '">' + _html.escape(btn) + '</a>'
        + '<div class="fine">Historical seasonal research for educational purposes, not investment advice. Past results never guarantee future ones.</div>'
        + '</div></body></html>'
    )


def render_unsub_landing(state="ok"):
    """Branded page shown after the unsubscribe link / one-click. state in {ok, invalid}."""
    if state == "ok":
        h = "You Are Unsubscribed"
        sub = ("You will no longer receive seasonal report emails. You can get a fresh "
               "report any time at tradewave.ai.")
    else:
        h = "We Could Not Process That Link"
        sub = ("This unsubscribe link is not valid. If you keep receiving emails, reply "
               "to one and we will remove you by hand.")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>TradeWave</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap" rel="stylesheet">'
        '<style>'
        'body{margin:0;background:#0B1220;color:#EAF0F8;font-family:Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased;'
        'background-image:radial-gradient(900px 460px at 50% -8%,rgba(124,92,255,.14),transparent 60%)}'
        '.wrap{max-width:560px;margin:0 auto;padding:14vh 24px;text-align:center}'
        '.brand{font-weight:800;font-size:28px;letter-spacing:-.02em;margin-bottom:36px}.brand b{color:#7C5CFF}'
        'h1{font-size:1.7rem;line-height:1.2;margin:0 0 14px}p{color:#9FB0C8;line-height:1.6;margin:0 0 28px}'
        '.btn{display:inline-block;background:#7C5CFF;color:#fff;font-weight:600;padding:14px 26px;border-radius:10px;'
        'text-decoration:none;box-shadow:0 8px 30px rgba(124,92,255,.28)}'
        '.fine{color:#6B7A93;font-size:.8rem;margin-top:26px}'
        '</style></head><body><div class="wrap">'
        '<div class="brand">Trade<b>Wave</b></div>'
        '<h1>' + _html.escape(h) + '</h1><p>' + _html.escape(sub) + '</p>'
        '<a class="btn" href="https://tradewave.ai/">Go to TradeWave</a>'
        '<div class="fine">You can resubscribe any time by requesting a new report.</div>'
        '</div></body></html>'
    )


if __name__ == "__main__":
    import sys
    tks = sys.argv[1:] or ["AAPL", "MSFT", "NVDA"]
    d = build_report_data(tks)
    for t in d["tickers"]:
        print("\n%s (%s) market=%s strongest=~%sd" % (t["symbol"], t["name"], t["market"], t["strongest"]))
        for h in HORIZONS:
            c = t["horizons"][h]["consec"]; m = t["horizons"][h]["midterm"]
            cs = "%d/%d avg %s%s" % (c["wins"], c["n"], _pct(c["avg"]), " (small)" if c["small"] else "") if c else "none"
            ms = "%d/%d avg %s%s" % (m["wins"], m["n"], _pct(m["avg"]), " (small)" if m["small"] else "") if m else "none"
            print("  ~%3dd  10yr: %-22s  midterm: %s" % (h, cs, ms))
    if d["not_covered"]:
        print("\nnot covered:", d["not_covered"])
    out = "/tmp/seasonal_email_sample.html"
    with open(out, "w") as f:
        f.write(render_email_html(d))
    print("\nwrote", out, "(%d bytes)" % len(open(out).read()))
