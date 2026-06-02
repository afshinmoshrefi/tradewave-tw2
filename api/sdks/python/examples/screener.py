"""TradeWave Python SDK - a small seasonal screener.

Scans every in-scope market for high-conviction long setups entering their window
now, ranks by edge score, and prints a clean table with the per-year receipts for
the top hit. Demonstrates error handling and the graceful ML metering.

Run:
    export TRADEWAVE_API_KEY=tw_live_...
    python screener.py
"""

from tradewave import (
    AuthError,
    Client,
    RateLimitError,
    TradeWaveError,
)


def screen() -> None:
    with Client() as tw:
        scan = tw.scan(
            window="now",
            direction="long",
            min_win_rate=0.65,
            min_years=8,
            rank_by="edge",
            limit=15,
        )

        print(f"Scanned at {scan.generated_at} | window={scan.window} "
              f"| evaluated={scan.evaluated_count} | returned={scan.count}")
        if scan.enrichment_capped:
            print("  (win_rate enrichment hit its cap - some rows excluded by "
                  "the min_win_rate filter)")

        actionable = [c for c in scan if c.is_actionable]
        if not actionable:
            print("No high-conviction setups right now. Try lowering min_win_rate "
                  "or widening the window.")
            return

        print(f"\n{'rank':>4}  {'sym':<8}{'dir':<6}{'edge':>5}{'win%':>7}"
              f"{'sharpe':>8}{'avg%':>7}  setup")
        for c in actionable:
            s = c.stats
            win_pct = f"{s.historical_win_rate * 100:.0f}" if s and s.historical_win_rate is not None else "-"
            sharpe = f"{s.sharpe_ratio:.2f}" if s and s.sharpe_ratio is not None else "-"
            avg = f"{s.avg_return_pct:.1f}" if s and s.avg_return_pct is not None else "-"
            entry = c.setup.entry_date if c.setup else "?"
            hold = c.setup.hold_days if c.setup else "?"
            print(f"{c.rank:>4}  {c.symbol or '?':<8}{c.direction or '?':<6}"
                  f"{c.edge_score or 0:>5}{win_pct:>7}{sharpe:>8}{avg:>7}  "
                  f"enter {entry}, hold {hold}d")

        # Per-year receipts for the strongest hit.
        top = actionable[0]
        print(f"\nReceipts for #{top.rank} {top.symbol} "
              f"({top.edge_basis}):")
        if top.receipts:
            r = top.receipts
            print(f"  {r.wins}/{r.years_tested} winning years; "
                  f"best {r.best_year.year if r.best_year else '?'} "
                  f"({r.best_year.return_pct if r.best_year else '?'}%), "
                  f"worst {r.worst_year.year if r.worst_year else '?'} "
                  f"({r.worst_year.return_pct if r.worst_year else '?'}%)")
            for row in r.per_year:
                mark = "+" if row.result == "win" else "-"
                print(f"    {row.year}  {mark} {row.return_pct}%")


def main() -> None:
    try:
        screen()
    except AuthError as exc:
        print("Auth failed - check your TRADEWAVE_API_KEY:", exc.message)
    except RateLimitError as exc:
        print(f"Rate limited; retry after {exc.retry_after}s")
    except TradeWaveError as exc:
        # Base class catches NotFoundError / ServerError / timeouts / network.
        print(f"TradeWave API error (status={exc.status}, code={exc.code}): {exc.message}")


if __name__ == "__main__":
    main()
