#!/usr/bin/env python3
"""
TradeWave Daily Top-10 Email Newsletter Generator (TW2)

Lifted from /home/flask/blog/generate_emails.py on .151 (canonical winner of 6
variants — see /home/afshin/F5_EMAIL_NEWSLETTER_REPORT.md). Original sent via
MailerLite immediately; this lift defaults to dry-run and writes the rendered
HTML to a preview file for inspection.

Usage:
    # Render with synthetic demo data (no .151 dependencies needed):
    python generate_email_newsletter.py --demo

    # Render against live TW2 data layer (NOT yet implemented — TODO when
    # /home/flask/site grows a get_top10_data equivalent):
    python generate_email_newsletter.py --live

    # Send via MailerLite (requires MAILERLITE_API_KEY in /etc/tradewave/secrets.env
    # AND TW2 user/group sync — currently blocked):
    python generate_email_newsletter.py --send

The send path is intentionally gated. If MAILERLITE_API_KEY is empty / placeholder,
--send exits cleanly with a "skipped" log line.

Lifted verbatim from .151:
  - content_cell_html, content_row_html
  - create_all_content_cells
  - create_email_html_desktop, create_email_html_smartphone
  - media_query_style_html, content_header, content_footer
  - create_final_email (modulo: writes to --out path instead of /var/www/html/wp-content)

Stubbed (TODO when TW2 data layer lands):
  - load_data_for_email (replaced by demo_dfe in --demo mode)
  - get_users_from_redis, get_email_groups, update_mailerlite
"""

import argparse
import datetime
import os
import sys
from datetime import timedelta

import pandas as pd

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/site/lib')
import config

# MailerLite is imported lazily so --demo / --dry-run never need it at import time.

# ---------------------------------------------------------------------------
# Secrets / config
# ---------------------------------------------------------------------------

# TW1 config.py exposed `mailerlite_token` (read from MAILERLITE_TOKEN env var).
# TW2 standardizes on MAILERLITE_API_KEY in /etc/tradewave/secrets.env.
# We deliberately do NOT fall back to MAILERLITE_TOKEN — the TW1 JWT in there is
# legacy and we want explicit opt-in via the new env var name.
MAILERLITE_API_KEY = os.environ.get('MAILERLITE_API_KEY', '')


def _mailerlite_enabled():
    """True iff MAILERLITE_API_KEY is set to a real key (not empty / placeholder)."""
    if not MAILERLITE_API_KEY:
        return False
    if MAILERLITE_API_KEY.lower() in ('placeholder', 'changeme', 'todo', 'set_me'):
        return False
    return True


# ---------------------------------------------------------------------------
# MailerLite client wrappers (all gated — never run in --demo / --dry-run)
# ---------------------------------------------------------------------------

def _ml_client():
    import mailerlite as MailerLite  # lazy import
    return MailerLite.Client({'api_key': MAILERLITE_API_KEY})


def create_subscriber(email, first_name, last_name, ip, optin_ip):
    return _ml_client().subscribers.create(
        email,
        fields={'name': first_name, 'last_name': last_name},
        ip_address=ip,
        optin_ip=optin_ip,
    )


def get_all_subscribers():
    return _ml_client().subscribers.list(limit=10, page=1, filter={'status': 'active'})


def create_mailerlite_group(group_name):
    return _ml_client().groups.create(group_name)


def assign_subscriber_to_a_group(subscriber_id, group_id):
    return _ml_client().subscribers.assign_subscriber_to_group(int(subscriber_id), int(group_id))


def unassign_subscriber_from_a_group(subscriber_id, group_id):
    return _ml_client().subscribers.unassign_subscriber_from_group(int(subscriber_id), int(group_id))


def get_email_groups():
    """Return ({tt_<name>: group_id}, {<other_name>: group_id})."""
    response = _ml_client().groups.list(limit=100, page=1, sort='name')
    dict_tt, dict_ot = {}, {}
    for g in response['data']:
        if g['name'][:3] == 'tt_':
            dict_tt[g['name'][3:]] = g['id']
        else:
            dict_ot[g['name']] = g['id']
    return dict_tt, dict_ot


def get_num_subscribers(group_id):
    response = _ml_client().groups.get_group_subscribers(group_id, page=1, limit=10, filter={'status': 'active'})
    return len(response['data'])


def create_campaign(campaign_name, subject, from_name, from_email, group_id, content):
    """Lifted verbatim from generate_emails.py — body shape preserved."""
    client = _ml_client()
    response = client.campaigns.create({
        "name": campaign_name,
        "type": "regular",
        "emails": [{
            "subject": subject,
            "from_name": from_name,
            "from": from_email,
            "content": content,
        }],
        "groups": [group_id],
    })
    campaign_id = response['data']['id']
    campaign_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return campaign_id, campaign_time


def schedule_campaign(campaign_id, send_date, send_hour, send_minute):
    return _ml_client().campaigns.schedule(campaign_id, {
        "delivery": "scheduled",
        "schedule": {
            "date": send_date,
            "hours": send_hour,
            "minutes": send_minute,
        },
    })


# ---------------------------------------------------------------------------
# Date helpers (verbatim)
# ---------------------------------------------------------------------------

def today_date_hour_min():
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return dt[:10], dt[11:13], dt[14:16]


def future_date_hour_min(num_minutes):
    dt = datetime.datetime.now()
    f = dt + timedelta(minutes=num_minutes)
    fdate = f.strftime("%y-%m-%d")  # NOTE: %y not %Y — preserved from original
    ftime = f.strftime("%H:%M:%S")
    return fdate[:10], ftime[:2], ftime[3:5]


# ---------------------------------------------------------------------------
# Demo data (replaces load_data_for_email in --demo mode)
# ---------------------------------------------------------------------------

def demo_dfe():
    """Build a synthetic 12-row dataframe shaped like load_data_for_email's output.

    Columns must match what create_all_content_cells expects:
      resource_id, row_pos, Symbol, Date, DaysOut, Direction, Sharpe Ratio,
      Date2, Cumulative Return, Avg Profit, Long Score, Short Score, post_title,
      company, opp_slug, bar_img, cum_img, sea_img, top_10_list_png_m,
      top_10_list_png_d, tn_url, tn_file, load_url, top10_page_url
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.datetime.now() + timedelta(days=21)).strftime("%Y-%m-%d")
    rows = []
    sample_symbols = [
        ('AAPL', 'Apple Inc.'),
        ('MSFT', 'Microsoft Corp.'),
        ('GOOGL', 'Alphabet Inc.'),
        ('NVDA', 'NVIDIA Corp.'),
        ('TSLA', 'Tesla Inc.'),
        ('SPY',  'SPDR S&P 500 ETF'),
        ('QQQ',  'Invesco QQQ Trust'),
        ('GLD',  'SPDR Gold Trust'),
        ('TLT',  '20+ Yr Treasury ETF'),
        ('EURUSD', 'EUR / USD'),
        ('CL=F', 'Crude Oil Futures'),
        ('VTI',  'Vanguard Total Stock'),
    ]
    for i in range(12):
        sym, company = sample_symbols[i]
        rows.append({
            'resource_id': i,
            'row_pos': 0,
            'Symbol': sym,
            'Date': today,
            'DaysOut': 21,
            'Direction': 'LONG' if i % 2 == 0 else 'SHORT',
            'Sharpe Ratio': round(2.5 - i * 0.1, 2),
            'Date2': end_date,
            'Cumulative Return': round(45.0 - i * 1.5, 2),
            'Avg Profit': round(8.5 - i * 0.3, 2),
            'Long Score': 85 - i,
            'Short Score': 35 + i,
            'post_title': f'10-{sym}-{today}',
            'company': company,
            'opp_slug': f'{config.domain_root or "https://example.com/"}top10/{sym}',
            'bar_img': '',
            'cum_img': '',
            'sea_img': '',
            'top_10_list_png_m': '',
            'top_10_list_png_d': '',
            'tn_file': f'tn-{sym}-{today}.png',
            # Use a 1x1 transparent PNG data URI so the email previews even with no image server:
            'tn_url': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
            'load_url': f'{config.domain_root or "https://example.com/"}tradewave-viewer?demo={sym}',
            'top10_page_url': f'{config.domain_root or "https://example.com/"}top10/{i}',
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# HTML rendering (lifted verbatim from generate_emails.py)
# ---------------------------------------------------------------------------

def content_row_html(content1, content2, cols=2):
    content_row = '<tr><td align="center"><table cellpadding="0" cellspacing="0" border="0">'
    if cols == 2:
        content_row += f"""
                <tr style='background-color:transparent'>
                    <td align="center" style="padding: 10px;">
                        {content1}
                    </td>
                    <td align="center" style="padding: 10px;">
                        {content2}
                    </td>
                </tr>
            """
    elif cols == 1:
        content_row += f"""
                <tr >
                    <td align="center" style="padding: 10px">
                        {content1}
                    </td>
                </tr>
            """
    content_row += '</table></td></tr>'
    return content_row


def content_cell_html(d):
    return f"""
                <table cellpadding="0" cellspacing="0" border="0" >
                    <tr>
                        <td>
                            <table cellpadding="0" cellspacing="0" border="0" width='100%' >
                                <tr>
                                    <td width='10%'  height='100%'  style='text-align:center;vertical-align:middle;background-color:{d['num_bg_color']}'>
                                        <span style='color:{d['num_fg_color']};font-weight:bold;font-size:22px'>{d['title_num']}</span>
                                    </td>
                                    <td width='80%' align="center"  height='100%' style='background-color:{d['title_color']};' >
                                        <h3 style="margin: 0;  padding: 5px;">{d['title_text']}</h3>
                                    </td>
                                    <td width='10%' height='100%' style='background-color:{d['title_color']}'>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="{d['report_link']}" target="_blank" rel="noopener noreferrer">
                                <img src="{d['img_src']}" alt="{d['img_alt']}" width="{d['img_width']}" height="{d['img_height']}" style="display: block; border: 0; margin: 0; padding: 0;">
                            </a>
                        </td>
                    </tr>
                    <tr>
                        <td style='background-color:{d['footer_color']}'>
                            <table cellpadding="0" cellspacing="0" border="0" width='100%' >
                                <tr style='height:{d['footer_h']}'>
                                    <td width='25%'   style='text-align:center;vertical-align:middle;background-color:transparent'>
                                       <a style='color:{d['link_color']};font-size{d['link_font_size']};font-weight:bold' href='{d['report_link']}'> Report </a>
                                    </td>
                                    <td width='25%' align="center"   style='background-color:transparent;' >
                                       <a style='color:{d['link_color']};font-size{d['link_font_size']};font-weight:bold' href='{d['load_link']}'> Load </a>
                                    </td>
                                    <td width='50%' align="center" style='background-color:transparent'>
                                        <a style='color:{d['link_color']};font-size{d['link_font_size']};font-weight:bold' href='{d['top10_link']}'>{d['top10_text']}</a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
    """


def create_all_content_cells(dfe):
    base = {
        'num_fg_color': 'white',
        'num_bg_color': 'black',
        'title_color': 'rgb(211,211,211)',
        'footer_color': 'lightblue',
        'footer_h': '30px',
        'img_height': '194',
        'img_width': '350',
        'link_color': 'black',
        'link_font_size': '1rem',
    }
    cell_dict = {}
    for _, r in dfe.iterrows():
        d = dict(base)
        resource_text = config.available_resources[str(r['resource_id'])].replace('STOCKS', ' ').replace('GOVERNMENT BONDS', 'GOV BONDS')
        tt_link_text = config.available_resources[str(r['resource_id'])].replace('STOCKS', ' ').replace('GOVERNMENT BONDS', 'GOV BONDS').replace('FUTURES & COMMODITIES', 'FUTURES & COMM')
        if tt_link_text != 'ETF':
            tt_link_text = tt_link_text.title()
        if resource_text == 'INDICES':
            resource_text += ' ALL'
        if resource_text != 'FUTURES & COMMODITIES':
            resource_text += ' Top 10'
        tt_link_text += ' Top 10'

        d['img_src'] = r['tn_url']
        d['img_alt'] = ''
        d['title_text'] = resource_text
        d['title_num'] = str(r['row_pos'] + 1)
        d['report_link'] = r['opp_slug']
        d['load_link'] = r['load_url']
        d['top10_text'] = tt_link_text
        d['top10_link'] = r['top10_page_url']

        cell_dict[r['resource_id']] = content_cell_html(d)
    return cell_dict


def create_email_html_desktop(cells_dict, flags):
    rows = [
        content_row_html(cells_dict[0], cells_dict[1], 2),
        content_row_html(cells_dict[2], cells_dict[3], 2),
        content_row_html(cells_dict[4], cells_dict[11], 2),
        content_row_html(cells_dict[5], cells_dict[6], 2),
        content_row_html(cells_dict[7], cells_dict[10], 2),
        content_row_html(cells_dict[9], cells_dict[8], 2),
    ]
    if flags == '111111111111':
        return '\n'.join(rows)
    if flags == '111110000001':
        return '\n'.join(rows[:3])
    if flags == '000001111110':
        return '\n'.join(rows[3:])
    return ''


def create_email_html_smartphone(cells_dict, flags):
    rows = [
        content_row_html(cells_dict[0], {}, 1),
        content_row_html(cells_dict[1], {}, 1),
        content_row_html(cells_dict[2], {}, 1),
        content_row_html(cells_dict[3], {}, 1),
        content_row_html(cells_dict[4], {}, 1),
        content_row_html(cells_dict[11], {}, 1),
        content_row_html(cells_dict[5], {}, 1),
        content_row_html(cells_dict[6], {}, 1),
        content_row_html(cells_dict[7], {}, 1),
        content_row_html(cells_dict[10], {}, 1),
        content_row_html(cells_dict[9], {}, 1),
        content_row_html(cells_dict[8], {}, 1),
    ]
    if flags == '111111111111':
        return '\n'.join(rows)
    if flags == '111110000001':
        return '\n'.join(rows[:6])
    if flags == '000001111110':
        return '\n'.join(rows[6:])
    return ''


def media_query_style_html():
    return """
        <style>
        @media screen and (min-width:600px){
            .desktop-version {display:table;}
            .mobile-version {display:none;}
        }
        @media screen and (max-width:599px){
            .desktop-version {display:none;}
            .mobile-version {display:table;}
        }
        </style>
    """


_MARKETS_TEXT = {
    '111111111111': '''
            <ul>
                <li>Dow 30</li><li>Nasdaq 100</li><li>S&P 500</li><li>Russell 1000</li><li>Wilshire 5000</li>
                <li>ETF</li><li>Indices</li><li>Futures & Commodities</li><li>Government Bonds</li><li>Forex</li>
            </ul>
    ''',
    '111111111111-1': '''
            <ul>
                <li>Dow 30</li><li>Nasdaq 100</li><li>S&P 500</li><li>Russell 1000</li><li>Wilshire 5000</li>
            </ul>
    ''',
    '111111111111-2': '''
            <ul>
                <li>ETF</li><li>Indices</li><li>Futures & Commodities</li><li>Government Bonds</li><li>Forex</li>
            </ul>
    ''',
    '111110000001': '''
            <ul>
                <li>Dow 30</li><li>Nasdaq 100</li><li>S&P 500</li><li>Russell 1000</li><li>Wilshire 5000</li><li>ETF</li>
            </ul>
    ''',
    '111110000001-1': '<ul><li>Dow 30</li><li>Nasdaq 100</li><li>S&P 500</li></ul>',
    '111110000001-2': '<ul><li>Russell 1000</li><li>Wilshire 5000</li><li>ETF</li></ul>',
    '000001111110': '''
            <ul>
                <li>Indices Common</li><li>Indices All</li><li>Futures & Commodities</li>
                <li>Government Bonds</li><li>Forex Liquid</li><li>Forex All</li>
            </ul>
    ''',
    '000001111110-1': '<ul><li>Indices Common</li><li>Indices All</li><li>Futures & Commodities</li></ul>',
    '000001111110-2': '<ul><li>Government Bonds</li><li>Forex Liquid</li><li>Forex All</li></ul>',
    '000000000000': '',
}


def content_header(desktop_or_smartphone, flags):
    header_td_width = '720px' if desktop_or_smartphone != 'smartphone' else '360'
    today_date = datetime.datetime.now().strftime("%Y-%m-%d")
    domain = config.domain_root or 'https://tradewave.ai/'
    return f"""
    <tr><td align="center"><table cellpadding="0" cellspacing="0" border="0" style="background-color:transparent" >
        <tr>
            <td height="100px" width="40px" align="left" style='background-color:transparent;padding-bottom:5px'>
                <img src='{domain}static/logo.png' width='70' height='70'>
            </td>
            <td width="520px" height="100px" align="left" style='vertical-align:middle;background-color:transparent'>
                <div>Daily Top 10 Email </div>
                <div>Tara Data Research LLC</div>
                <div><a style='color:black;font-weight:bold;font-size:1.1rem' href='https://tradewave.ai'>TradeWave.AI</a></div>
            </td>
        </tr>
        <tr>
            <td colspan="2" width='{header_td_width}' height="50px" align="left" style='background-color:transparent;padding-left:5px;padding-top:10px;border-top:1px solid black'>
                <span> Discover the top TradeWave opportunities across a range of markets in today's email for {today_date}:<br></span>
            </td>
        </tr>
        <tr>
            <td colspan="2" width='{header_td_width}' height='100px' style='background-color:transparent;display:table-cell'>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style='background-color:transparent'>
                    <tr>
                        <td width="50%" valign="top" style='padding-top:20px'>
                            <div style="width:100%;float:left; background-color: transparent;">{_MARKETS_TEXT[flags + '-1']}</div>
                        </td>
                        <td width="50%" valign="top" style='padding-top:20px'>
                            <div style="width:100%;float:left; background-color: transparent;">{_MARKETS_TEXT[flags + '-2']}</div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table></td></tr>
    """


def content_footer(_desktop_or_smartphone):
    domain = config.domain_root or 'https://tradewave.ai/'
    return f"""
    <tr><td align="center"><table cellpadding="0" cellspacing="0" border="0" style="background-color:lightgray" >
        <tr>
            <td width="720px" height="100px" align="center" style="background-color:lightgray;padding: 10px; border-bottom:1px solid black;margin:10px;">
                <a href='{domain}tradewave-viewer?set=on' style='font-size:1.5rem'> Update your email preferences or unsubscribe </a>
            </td>
        </tr>
    </table></td></tr>
    """


def create_final_email(dfe, flag, out_path=None):
    cells_dict = create_all_content_cells(dfe)
    content_desktop = create_email_html_desktop(cells_dict, flag)
    content_smartphone = create_email_html_smartphone(cells_dict, flag)
    media_query_html = media_query_style_html()
    content = f"""<!DOCTYPE html>
<html>
<head>
    <title>TradeWave Daily Top 10</title>
    {media_query_html}
</head>
<body>
    <!--[if !mso]><!-->
    <table class="desktop-version" width="100%" cellpadding="0" cellspacing="0" border="0" style="table-layout: fixed;background-color:transparent">
        {content_header('desktop', flag)}
        {content_desktop}
        {content_footer('desktop')}
    </table>
    <!--<![endif]-->
    <table class="mobile-version" width="100%" cellpadding="0" cellspacing="0" border="0" style="table-layout: fixed;background-color:transparent">
        {content_header('smartphone', flag)}
        {content_smartphone}
        {content_footer('smartphone')}
    </table>
</body>
</html>
"""
    if out_path:
        with open(out_path, 'w') as f:
            f.write(content)
    return content


# ---------------------------------------------------------------------------
# Stubs for TW1 data layer (TODO when TW2 grows equivalents)
# ---------------------------------------------------------------------------

def load_data_for_email():
    """TW1 version: read top10 hdf + thumbnails JSON + redis. TW2 has none of these
    yet on .176 — a real implementation would query the TW2 appserver / Postgres
    layer that replaces them. Until then, --live mode will exit with this error."""
    raise NotImplementedError(
        "TW2 has no live top10 data layer yet on .176. Use --demo for now. "
        "Wire this up when the daily-pick / top-10 pipeline is lifted."
    )


def get_users_from_redis():
    """TW1 version: scan user_email_settings_* keys on appserver redis db 2.
    TW2: replaced by Postgres `users` + email-prefs columns once that schema lands."""
    raise NotImplementedError(
        "TW2 stores user email prefs in Postgres, not redis. Implement this when "
        "the email-preferences UI ships."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TW2 daily Top 10 email newsletter generator")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--demo', action='store_true', default=True,
                      help='Render with synthetic data (default).')
    mode.add_argument('--live', action='store_true',
                      help='Render with live TW2 data (NOT YET IMPLEMENTED).')
    parser.add_argument('--send', action='store_true',
                        help='After render, create+schedule MailerLite campaign. Requires MAILERLITE_API_KEY.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Force render-only (overrides --send).')
    parser.add_argument('--out', default='/tmp/email_preview.html',
                        help='Path to write rendered HTML preview (default /tmp/email_preview.html).')
    parser.add_argument('--flag', default='111111111111',
                        choices=['111111111111', '111110000001', '000001111110'],
                        help='Market segment flag — which markets to include.')
    args = parser.parse_args()

    # TW2_EMAIL_DRY_RUN env var also forces dry-run, per task spec.
    if os.environ.get('TW2_EMAIL_DRY_RUN'):
        args.dry_run = True

    if args.live:
        # User opted into live mode; fail loud.
        load_data_for_email()  # raises NotImplementedError
        return  # unreachable
    else:
        dfe = demo_dfe()
        print(f"[info] demo mode: synthesized {len(dfe)} rows")

    out_path = args.out
    print(f"[info] rendering email HTML for flag={args.flag} -> {out_path}")
    content = create_final_email(dfe, args.flag, out_path=out_path)
    size_kb = len(content) / 1024.0
    print(f"[info] rendered ({size_kb:.1f} KB) -> {out_path}")

    if not args.send or args.dry_run:
        if args.send and args.dry_run:
            print("[info] --send overridden by --dry-run; not sending.")
        else:
            print("[info] dry-run: not sending. Re-run with --send to mail (requires MAILERLITE_API_KEY).")
        return

    # Send path
    if not _mailerlite_enabled():
        print("[skip] MAILERLITE_API_KEY not set in /etc/tradewave/secrets.env — campaign NOT created.")
        print("[skip] Set MAILERLITE_API_KEY=<real key> and re-run with --send to actually mail.")
        return

    # Live send is currently blocked because TW2 has no user/group sync yet.
    print("[skip] --send requires TW2 user->MailerLite group sync, which is not yet implemented.")
    print("[skip] Stubs: get_users_from_redis(), get_email_groups(), update_mailerlite() — wire these to Postgres first.")
    print("[skip] Render-only path completed successfully; no campaign created.")


if __name__ == '__main__':
    main()
