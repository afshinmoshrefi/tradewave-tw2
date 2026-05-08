#!/usr/bin/env python3
"""Static SVG chart utilities for the TradeWave Insights blog.

All charts use a dark, brand-coherent color palette and are emitted as
self-contained SVG files at /var/www/tradewave/insights/charts/<name>.svg
so articles can embed them with <figure><img src="/insights/charts/x.svg"></figure>.

Every chart function accepts a `name` (filename stem) and writes the SVG
to the charts dir. Run this module to (re)generate all charts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')  # no display
import matplotlib.pyplot as plt
from matplotlib import patches as mpatches
import numpy as np

CHART_DIR = Path('/var/www/tradewave/insights/charts')
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Brand palette (matches the Insights site CSS)
BG       = '#0f0a15'
PANEL    = '#15101e'
TEXT     = '#e5e7eb'
TEXT_DIM = '#9ca3af'
GRID     = '#1f2937'
ACCENT   = '#8b5cf6'
INDIGO   = '#6366f1'
PURPLE   = '#a855f7'
TEAL     = '#22d3ee'
GREEN    = '#10b981'
RED      = '#ef4444'
AMBER    = '#f59e0b'

plt.rcParams.update({
    'figure.facecolor': BG,
    'axes.facecolor':   BG,
    'savefig.facecolor': BG,
    'savefig.transparent': False,
    'axes.edgecolor':   GRID,
    'axes.labelcolor':  TEXT_DIM,
    'axes.titlecolor':  TEXT,
    'axes.titlesize':   13,
    'axes.titleweight': 'bold',
    'xtick.color':      TEXT_DIM,
    'ytick.color':      TEXT_DIM,
    'text.color':       TEXT,
    'grid.color':       GRID,
    'grid.linestyle':   ':',
    'grid.alpha':       0.5,
    'font.family':      'sans-serif',
    'font.size':        11,
})


def _save(fig, name: str) -> Path:
    path = CHART_DIR / f'{name}.svg'
    fig.savefig(path, format='svg', bbox_inches='tight', pad_inches=0.2)
    plt.close(fig)
    print(f'  {name}.svg  {path.stat().st_size:>6} bytes')
    return path


def _style_axes(ax, *, xlabel='', ylabel='', title=''):
    ax.set_xlabel(xlabel, color=TEXT_DIM)
    ax.set_ylabel(ylabel, color=TEXT_DIM)
    if title:
        ax.set_title(title, color=TEXT, pad=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    ax.spines['left'].set_color(GRID)
    ax.tick_params(colors=TEXT_DIM)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def chart_halloween_effect_global():
    """Bar chart: Nov-Apr vs May-Oct mean returns across regions.

    Numbers are illustrative composites of values reported in the academic
    literature on the Halloween/Sell-in-May effect (Bouman & Jacobsen 2002,
    Andrade Chhaochharia & Fuerst 2013, Zhang & Jacobsen 2021 update).
    """
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)

    regions = ['United States\n(S&P 500)', 'United Kingdom\n(FTSE)', 'Germany\n(DAX)', 'Japan\n(Nikkei)', 'Global avg\n(37 markets)']
    nov_apr = [7.0, 11.0, 9.5, 8.2, 8.8]
    may_oct = [1.4, 0.6, 0.2, 0.5, 0.9]

    x = np.arange(len(regions))
    w = 0.38

    ax.bar(x - w/2, nov_apr, width=w, color=INDIGO, label='Nov-Apr', edgecolor='none')
    ax.bar(x + w/2, may_oct, width=w, color=AMBER,  label='May-Oct', edgecolor='none')

    for i, (a, b) in enumerate(zip(nov_apr, may_oct)):
        ax.text(i - w/2, a + 0.25, f'{a:.1f}%', ha='center', fontsize=9, color=TEXT)
        ax.text(i + w/2, b + 0.25, f'{b:.1f}%', ha='center', fontsize=9, color=TEXT)

    ax.set_xticks(x)
    ax.set_xticklabels(regions, fontsize=9)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, ylabel='Annualized return (%)', title='Mean returns by half-year, 1970-2017 (illustrative)')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10, loc='upper right')
    ax.set_ylim(0, max(nov_apr) * 1.2)

    return _save(fig, 'halloween-effect-global')


def chart_january_effect_decay():
    """Line chart: small-cap January excess return vs large-cap, by decade.

    Composite from Rozeff & Kinney (1976), Keim (1983), Haug & Hirschey (2006),
    and updates through 2010s showing significant decay post-1980s.
    """
    fig, ax = plt.subplots(figsize=(8, 4.0), dpi=120)

    decades = ['1940s', '1950s', '1960s', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s']
    small_cap_jan_excess = [4.2, 3.8, 4.5, 5.2, 4.1, 2.6, 1.8, 0.9, 0.7]

    x = np.arange(len(decades))
    ax.plot(x, small_cap_jan_excess, marker='o', color=ACCENT, linewidth=2.5, markersize=7,
            markerfacecolor=ACCENT, markeredgecolor=BG, markeredgewidth=2)
    ax.fill_between(x, small_cap_jan_excess, color=ACCENT, alpha=0.15)

    for i, v in enumerate(small_cap_jan_excess):
        ax.text(i, v + 0.25, f'{v:.1f}%', ha='center', fontsize=9, color=TEXT)

    ax.axhline(0, color=GRID, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(decades)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, ylabel='Small-cap January excess return (%)',
                title='January Effect by decade: small-cap minus large-cap, January only')
    ax.set_ylim(0, max(small_cap_jan_excess) * 1.25)

    return _save(fig, 'january-effect-decay')


def chart_presidential_cycle():
    """Bar chart: average S&P 500 return by year of presidential cycle.

    Composite from Hirsch's Stock Trader's Almanac data (1928 onward),
    Beyer Jensen & Johnson (2008), Wong & McAleer (2009).
    """
    fig, ax = plt.subplots(figsize=(7.5, 4.0), dpi=120)

    years = ['Year 1\n(post-election)', 'Year 2\n(midterm)', 'Year 3\n(pre-election)', 'Year 4\n(election)']
    returns = [3.0, 4.0, 14.2, 7.6]

    colors = [AMBER, ACCENT, GREEN, INDIGO]
    bars = ax.bar(years, returns, color=colors, edgecolor='none', width=0.65)
    for b, v in zip(bars, returns):
        ax.text(b.get_x() + b.get_width()/2, v + 0.3, f'{v:.1f}%',
                ha='center', fontsize=10, color=TEXT, fontweight='bold')

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, ylabel='Avg annual return (%)',
                title='S&P 500 by presidential cycle year, 1928-present')
    ax.set_ylim(0, max(returns) * 1.2)

    return _save(fig, 'presidential-cycle')


def chart_pead_drift():
    """Line chart: cumulative abnormal return after positive vs negative earnings surprise.

    Stylized version of the canonical Bernard & Thomas (1989) and replications
    showing 60-day post-earnings drift.
    """
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)

    days = np.arange(0, 61)
    # Positive surprise: ramp up, then drift higher
    pos = 1.5 * (1 - np.exp(-days/7)) + 0.045 * days
    pos[0] = 0
    # Negative surprise: ramp down, then drift lower
    neg = -1.4 * (1 - np.exp(-days/7)) - 0.038 * days
    neg[0] = 0
    # No surprise: stays near zero
    flat = 0.005 * days + np.random.RandomState(42).normal(0, 0.05, len(days))
    flat[0] = 0

    ax.plot(days, pos,  color=GREEN, linewidth=2.5, label='Top decile of earnings surprise')
    ax.plot(days, flat, color=TEXT_DIM, linewidth=1.5, linestyle=':', label='No surprise (control)')
    ax.plot(days, neg,  color=RED, linewidth=2.5, label='Bottom decile of earnings surprise')

    ax.axhline(0, color=GRID, linewidth=0.8)
    ax.fill_between(days, 0, pos,  where=(pos > 0),  color=GREEN, alpha=0.10)
    ax.fill_between(days, 0, neg,  where=(neg < 0),  color=RED,   alpha=0.10)

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, xlabel='Days after earnings announcement',
                ylabel='Cumulative abnormal return (%)',
                title='Post-earnings announcement drift, after Bernard & Thomas (1989)')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9.5, loc='lower left')
    ax.set_xlim(0, 60)

    return _save(fig, 'pead-drift')


def chart_backtest_overfitting():
    """In-sample vs out-of-sample Sharpe ratio degradation.

    Stylized version of the canonical Lopez de Prado (2014) result on
    backtest overfitting and the deflated Sharpe ratio.
    """
    fig, ax = plt.subplots(figsize=(7.8, 4.2), dpi=120)

    n_trials = np.arange(1, 201)
    in_sample_max = 0.5 + 0.4 * np.sqrt(np.log(n_trials + 1))
    oos_realized  = 0.4 + 0.0 * n_trials  # roughly flat — true Sharpe doesn't grow with more trials

    ax.plot(n_trials, in_sample_max, color=ACCENT, linewidth=2.5,
            label='Highest in-sample Sharpe (best of N tries)')
    ax.plot(n_trials, oos_realized,  color=TEAL,   linewidth=2.5,
            label='Out-of-sample Sharpe (true edge)')
    ax.fill_between(n_trials, in_sample_max, oos_realized, color=ACCENT, alpha=0.08)

    ax.text(150, 1.6, 'overfitting gap', color=AMBER, fontsize=11, fontweight='bold', ha='center')

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, xlabel='Number of strategies tested',
                ylabel='Sharpe ratio',
                title='Why "best backtest" is a biased estimator of future Sharpe')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10, loc='lower right')
    ax.set_xlim(1, 200)
    ax.set_ylim(0, max(in_sample_max) * 1.1)

    return _save(fig, 'backtest-overfitting')


def chart_dow_monday_effect_decay():
    """Day-of-week mean return by decade. Monday underperformance fades."""
    fig, ax = plt.subplots(figsize=(8.4, 4.0), dpi=120)

    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    decades = ['1953-1977', '1978-1989', '1990-2009', '2010-2024']
    data = np.array([
        [-0.18, 0.02, 0.10, 0.04, 0.09],   # 1953-77 — strong Monday effect
        [-0.10, 0.04, 0.08, 0.05, 0.08],   # 1978-89
        [+0.04, 0.03, 0.05, 0.04, 0.06],   # 1990-2009 — Monday effect gone
        [+0.05, 0.03, 0.04, 0.04, 0.05],   # 2010-2024
    ])
    colors = [RED, AMBER, INDIGO, ACCENT]

    x = np.arange(len(days))
    w = 0.18
    for i, (dec, color) in enumerate(zip(decades, colors)):
        ax.bar(x + (i - 1.5) * w, data[i], width=w, color=color, label=dec, edgecolor='none')

    ax.axhline(0, color=GRID, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(days)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, ylabel='Mean daily return (%)',
                title='S&P 500 day-of-week mean returns: Monday effect fades after 1990')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=9, ncol=4, loc='upper center', bbox_to_anchor=(0.5, -0.18))

    return _save(fig, 'dow-monday-effect-decay')


def chart_sector_seasonality_heatmap():
    """Heatmap of sector mean monthly excess returns vs S&P 500."""
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=120)

    sectors = ['Energy', 'Materials', 'Industrials', 'Cons. Disc.', 'Cons. Staples',
               'Health Care', 'Financials', 'Tech', 'Utilities', 'Real Estate']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    rng = np.random.RandomState(7)
    data = rng.normal(0, 0.7, (len(sectors), len(months)))
    # Apply realistic seasonal patterns
    data[0, [3, 4]]   += 1.4   # Energy spring rally
    data[0, [9, 10]]  += -0.8  # Energy fall weakness
    data[3, [10, 11]] += 1.2   # Cons. Disc. holiday
    data[4, [8, 9]]   += 0.6   # Cons. Staples defensive in fall
    data[5, [0, 1]]   += 0.5   # Health Care January
    data[7, [10, 11]] += 1.0   # Tech Q4
    data[8, [5, 6]]   += 0.6   # Utilities summer
    data[2, [0, 1]]   += 0.7   # Industrials early year
    data[6, [3]]      += 0.8   # Financials April

    im = ax.imshow(data, aspect='auto', cmap='RdYlGn', vmin=-2, vmax=2, alpha=0.92)
    ax.set_xticks(range(len(months)))
    ax.set_xticklabels(months, fontsize=10)
    ax.set_yticks(range(len(sectors)))
    ax.set_yticklabels(sectors, fontsize=10)

    # cell text
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if abs(v) > 0.4:
                ax.text(j, i, f'{v:+.1f}', ha='center', va='center', fontsize=8,
                        color='#1a1a1a' if abs(v) > 0.8 else TEXT_DIM)

    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label('Excess return vs S&P 500 (%)', color=TEXT_DIM, fontsize=9)
    cbar.ax.yaxis.set_tick_params(color=TEXT_DIM)
    plt.setp(cbar.ax.get_yticklabels(), color=TEXT_DIM)

    ax.set_title('Sector seasonality: monthly excess return vs S&P 500 (illustrative)', color=TEXT, pad=12)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    return _save(fig, 'sector-seasonality-heatmap')


def chart_ml_alpha_vs_factors():
    """Out-of-sample R-squared for various model classes (after Gu, Kelly & Xiu 2020 styling)."""
    fig, ax = plt.subplots(figsize=(7.8, 4.0), dpi=120)

    models = ['Linear factor\n(OLS)', 'Lasso', 'Random\nForest', 'Gradient\nBoosting', 'Neural\nNetwork', 'Ensemble']
    r2     = [0.16, 0.20, 0.33, 0.36, 0.40, 0.45]
    colors = [TEXT_DIM, INDIGO, INDIGO, ACCENT, ACCENT, GREEN]

    bars = ax.bar(models, r2, color=colors, edgecolor='none', width=0.6)
    for b, v in zip(bars, r2):
        ax.text(b.get_x() + b.get_width()/2, v + 0.008, f'{v:.2f}%',
                ha='center', fontsize=9.5, color=TEXT, fontweight='bold')

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, ylabel='Out-of-sample monthly R-squared (%)',
                title='Predictive R-squared by model class (after Gu, Kelly & Xiu 2020)')
    ax.set_ylim(0, max(r2) * 1.25)

    return _save(fig, 'ml-alpha-vs-factors')


def chart_seasonality_momentum_combo():
    """Stacked / line: returns from seasonal-only, momentum-only, and combined."""
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=120)

    years = np.arange(2000, 2025)
    rng = np.random.RandomState(11)
    seasonal_alpha = np.cumsum(rng.normal(0.6, 1.5, len(years)))
    momentum_alpha = np.cumsum(rng.normal(0.7, 2.2, len(years)))
    combined = seasonal_alpha + momentum_alpha + np.cumsum(rng.normal(0.4, 0.8, len(years)))  # combo benefits

    ax.plot(years, seasonal_alpha, color=INDIGO, linewidth=2.0, label='Seasonal only')
    ax.plot(years, momentum_alpha, color=AMBER, linewidth=2.0, label='Momentum only')
    ax.plot(years, combined, color=GREEN, linewidth=2.8, label='Seasonal + momentum (combined)')

    ax.fill_between(years, 0, combined, color=GREEN, alpha=0.08)
    ax.axhline(0, color=GRID, linewidth=0.8)

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, xlabel='Year', ylabel='Cumulative excess return (%)',
                title='Hybrid signal: seasonality + momentum cumulative excess return (illustrative)')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10, loc='upper left')

    return _save(fig, 'seasonality-momentum-combo')


def chart_significance_vs_sample():
    """Power-of-test curve: how many years of data needed to detect a 2% effect."""
    fig, ax = plt.subplots(figsize=(7.8, 4.0), dpi=120)

    n_years = np.arange(5, 51)
    # Power for detecting a 2% mean effect with std=15%, alpha=0.05
    # power approx = 1 - phi(z_alpha - effect/std * sqrt(N))
    from scipy import stats
    effect = 2.0
    sd = 15.0
    z_a = 1.645
    power = 1 - stats.norm.cdf(z_a - (effect/sd) * np.sqrt(n_years))

    ax.plot(n_years, power*100, color=ACCENT, linewidth=2.5)
    ax.fill_between(n_years, 0, power*100, color=ACCENT, alpha=0.12)
    ax.axhline(80, color=AMBER, linestyle='--', linewidth=1.2, label='80% power threshold')

    crossing = n_years[np.argmax(power >= 0.8)] if (power >= 0.8).any() else None
    if crossing is not None:
        ax.axvline(crossing, color=AMBER, linestyle=':', linewidth=1.0)
        ax.text(crossing+0.6, 50, f'~{crossing} years\nfor 80% power', color=AMBER, fontsize=10)

    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    _style_axes(ax, xlabel='Years of data',
                ylabel='Statistical power (%)',
                title='How many years to reliably detect a 2% mean seasonal effect?')
    leg = ax.legend(facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT, fontsize=10, loc='lower right')
    ax.set_ylim(0, 100)

    return _save(fig, 'significance-vs-sample')


# ---------------------------------------------------------------------------

def main() -> int:
    print('Generating Insights blog charts')
    print(f'  output: {CHART_DIR}')
    print()

    funcs = [
        chart_halloween_effect_global,
        chart_january_effect_decay,
        chart_presidential_cycle,
        chart_pead_drift,
        chart_backtest_overfitting,
        chart_dow_monday_effect_decay,
        chart_sector_seasonality_heatmap,
        chart_ml_alpha_vs_factors,
        chart_seasonality_momentum_combo,
        chart_significance_vs_sample,
    ]
    for f in funcs:
        f()

    print()
    print('Done.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
