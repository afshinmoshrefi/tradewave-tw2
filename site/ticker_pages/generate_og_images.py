#!/usr/bin/env python3
"""
Generate OG (Open Graph) preview images for ticker pages.

Creates a 1200x630 PNG per ticker showing:
- Ticker symbol + company name
- AI score (if active)
- Monthly return bar chart
- Best/worst month callout
- TradeWave branding

Called from generate_ticker_pages.py after collecting ticker data.
Can also run standalone for testing.

Usage:
    python generate_og_images.py  (generates for all Phase 1 tickers)
    python generate_og_images.py --tickers AAPL,JPM --out /tmp/og_test/
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# Fonts - use DejaVu (available on all Ubuntu). If Inter is installed, use that.
FONT_PATHS = {
    'bold': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    'regular': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
}

# Colors matching the dark-blue theme
BG_COLOR = (15, 10, 21)
CARD_BG = (12, 18, 37)
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = (156, 163, 175)
TEXT_MUTED = (107, 114, 128)
ACCENT = (99, 102, 241)
SUCCESS = (16, 185, 129)
DANGER = (239, 68, 68)
WARNING = (245, 158, 11)

# OG image dimensions (standard)
WIDTH = 1200
HEIGHT = 630


def get_font(style, size):
    try:
        return ImageFont.truetype(FONT_PATHS[style], size)
    except Exception:
        return ImageFont.load_default()


def generate_og_image(data, output_path):
    """Generate a single OG image for a ticker.

    data dict should contain:
        symbol, company_name, ai_score (or None), best_month, worst_month,
        monthly_returns (dict of month -> {avg_return, win_rate}),
        years_of_data
    """
    img = Image.new('RGB', (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Subtle accent line at the very top (thin, doesn't cover content)
    draw.rectangle([(0, 0), (WIDTH, 4)], fill=ACCENT)

    symbol = data['symbol']
    company = data.get('company_name') or symbol
    ai_score = data.get('ai_score')
    best_month = data.get('best_month')
    worst_month = data.get('worst_month')
    monthly = data.get('monthly_returns') or {}
    years = data.get('years_of_data') or 0
    active_count = data.get('active_patterns') or 0
    if isinstance(active_count, list):
        active_count = len(active_count)

    font_symbol = get_font('bold', 64)
    font_company = get_font('regular', 24)
    font_label = get_font('bold', 16)
    font_value = get_font('bold', 22)
    font_bar_label = get_font('bold', 14)
    font_bar_value = get_font('bold', 13)
    font_brand = get_font('bold', 20)
    font_subtitle = get_font('regular', 16)

    # === LEFT SIDE: Ticker info ===
    left_x = 60
    y = 50

    # Ticker symbol
    draw.text((left_x, y), symbol, fill=ACCENT, font=font_symbol)
    y += 75

    # Company name
    draw.text((left_x, y), company, fill=TEXT_SECONDARY, font=font_company)
    y += 40

    # Subtitle
    draw.text((left_x, y), 'Seasonal Stock Pattern', fill=TEXT_MUTED, font=font_subtitle)
    y += 50

    # Active patterns count
    if active_count > 0:
        draw.text((left_x, y), 'Active Patterns', fill=TEXT_MUTED, font=font_label)
        draw.text((left_x + 140, y - 2), '%d' % active_count, fill=ACCENT, font=font_value)
        y += 34

    # AI Score pill (if active)
    if ai_score is not None:
        label = 'AI Score'
        draw.text((left_x, y), label, fill=TEXT_MUTED, font=font_label)
        score_text = '%.1f' % ai_score
        draw.text((left_x + 90, y - 2), score_text, fill=WARNING, font=font_value)
        y += 34

    # Best month
    if best_month and best_month in monthly:
        ret = monthly[best_month].get('avg_return', 0)
        wr = monthly[best_month].get('win_rate', 0)
        draw.text((left_x, y), 'Best Month', fill=TEXT_MUTED, font=font_label)
        y += 24
        draw.text((left_x, y), '%s  %+.1f%%  (%d%% win rate)' % (best_month, ret, wr),
                   fill=SUCCESS, font=font_value)
        y += 36

    # Worst month
    if worst_month and worst_month in monthly:
        ret = monthly[worst_month].get('avg_return', 0)
        draw.text((left_x, y), 'Worst Month', fill=TEXT_MUTED, font=font_label)
        y += 24
        draw.text((left_x, y), '%s  %+.1f%%' % (worst_month, ret),
                   fill=DANGER, font=font_value)
        y += 36

    # Years of data
    draw.text((left_x, y), '%d years of historical data' % years, fill=TEXT_MUTED, font=font_subtitle)

    # === RIGHT SIDE: Bar chart ===
    months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    chart_x = 520
    chart_y = 80
    chart_w = 620
    chart_h = 420
    bar_area_top = chart_y + 30
    bar_area_bottom = chart_y + chart_h - 40
    bar_area_h = bar_area_bottom - bar_area_top
    mid_y = bar_area_top + bar_area_h // 2

    # Chart background
    draw.rounded_rectangle(
        [(chart_x - 20, chart_y - 10), (chart_x + chart_w + 20, chart_y + chart_h + 20)],
        radius=16, fill=CARD_BG
    )

    # Zero line
    draw.line([(chart_x, mid_y), (chart_x + chart_w, mid_y)], fill=TEXT_MUTED, width=1)

    # Get max for scaling
    returns = []
    for m in months_order:
        if m in monthly:
            returns.append(monthly[m].get('avg_return', 0))
    max_abs = max(abs(r) for r in returns) if returns else 1
    if max_abs < 0.1:
        max_abs = 1

    bar_slot = chart_w / 12
    bar_w = bar_slot * 0.6
    half_h = bar_area_h // 2

    for i, m in enumerate(months_order):
        if m not in monthly:
            continue
        ret = monthly[m].get('avg_return', 0)
        bar_x = chart_x + i * bar_slot + (bar_slot - bar_w) / 2

        bar_h = abs(ret) / max_abs * half_h
        bar_h = max(bar_h, 2)  # minimum visible height

        color = SUCCESS if ret >= 0 else DANGER
        is_best = (m == best_month)

        if ret >= 0:
            y1 = mid_y - bar_h
            y2 = mid_y
        else:
            y1 = mid_y
            y2 = mid_y + bar_h

        # Ensure coordinates are valid (integers, y1 < y2).
        bx1 = int(bar_x)
        bx2 = int(bar_x + bar_w)
        by1 = int(min(y1, y2))
        by2 = int(max(y1, y2))
        if by2 - by1 < 2:
            by2 = by1 + 2

        # Bar
        draw.rectangle([(bx1, by1), (bx2, by2)], fill=color)

        # Gold border for best month
        if is_best:
            draw.rectangle([(bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2)], outline=WARNING, width=2)

        # Value label
        val_text = '%+.1f%%' % ret
        bbox = draw.textbbox((0, 0), val_text, font=font_bar_value)
        tw = bbox[2] - bbox[0]
        if ret >= 0:
            draw.text((bar_x + bar_w / 2 - tw / 2, y1 - 18), val_text, fill=color, font=font_bar_value)
        else:
            draw.text((bar_x + bar_w / 2 - tw / 2, y2 + 4), val_text, fill=color, font=font_bar_value)

        # Month label
        bbox = draw.textbbox((0, 0), m, font=font_bar_label)
        tw = bbox[2] - bbox[0]
        draw.text((bar_x + bar_w / 2 - tw / 2, bar_area_bottom + 8), m, fill=TEXT_SECONDARY, font=font_bar_label)

    # === BRANDING ===
    brand_y = HEIGHT - 45
    # Divider line
    draw.line([(left_x, brand_y - 12), (WIDTH - 60, brand_y - 12)], fill=(31, 41, 55), width=1)
    draw.text((left_x, brand_y), 'TradeWave', fill=ACCENT, font=font_brand)
    # Tagline instead of raw URL
    draw.text((left_x + 140, brand_y + 3), 'Seasonal Stock Pattern Analysis',
              fill=TEXT_MUTED, font=font_subtitle)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, 'PNG', optimize=True)


def generate_all_og_images(hub_entries, output_dir):
    """Generate OG images for all tickers. Called from generate_ticker_pages.py."""
    og_dir = os.path.join(output_dir, 'og')
    os.makedirs(og_dir, exist_ok=True)
    count = 0
    for entry in hub_entries:
        sym = entry['symbol']
        out_path = os.path.join(og_dir, '%s.png' % sym)
        try:
            generate_og_image(entry, out_path)
            count += 1
        except Exception as e:
            print('  [%s] OG image failed: %s' % (sym, e))
    return count


if __name__ == '__main__':
    # Standalone test mode
    parser = argparse.ArgumentParser(description='Generate OG images for ticker pages.')
    parser.add_argument('--tickers', default='AAPL', help='Comma-separated tickers')
    parser.add_argument('--out', default='/tmp/og_test/', help='Output directory')
    args = parser.parse_args()

    sys.path.insert(0, '/home/flask')
    import config
    sys.path.insert(0, '/home/flask/site/ticker_pages')
    from ticker_data import login_appserver, fetch_realtime_prices, collect_ticker_data

    session = login_appserver()
    prices = fetch_realtime_prices()

    for sym in args.tickers.split(','):
        sym = sym.strip().upper()
        data = collect_ticker_data(sym, session, prices)
        out_path = os.path.join(args.out, 'og', '%s.png' % sym)
        generate_og_image(data, out_path)
        print('Generated: %s' % out_path)
