"""TradeWave Python SDK - quickstart.

Run:
    export TRADEWAVE_API_KEY=tw_live_...
    python quickstart.py

Shows the daily pick, a 'now' scan, and a single-symbol deep dive. Derived data
only - all movement is percentages, never prices.
"""

from tradewave import Client, MLDailyLimit


def main() -> None:
    # api_key is read from TRADEWAVE_API_KEY when omitted.
    with Client() as tw:
        # 1) Today's AI pick (a full PatternCard + its live track record).
        pick = tw.daily_pick()
        if pick.card:
            print("DAILY PICK:", pick.card.headline)
            print("  verdict :", pick.card.verdict)
        tr = pick.track_record
        if tr:
            print(f"  record  : {tr.win_count}/{tr.count} wins, "
                  f"avg {tr.avg_return_pct}% per pick")

        # 2) Scan for the best seasonal setups entering their window now.
        print("\nWHAT'S SEASONAL NOW (win rate >= 60%):")
        scan = tw.scan(window="now", min_win_rate=0.6, limit=5)
        if scan.count == 0:
            print("  Nothing right now - try widening markets/window/min_win_rate.")
        for card in scan:  # ScanResult iterates its ranked cards directly
            wr = card.stats.historical_win_rate if card.stats else None
            print(f"  #{card.rank} {card.symbol} {card.direction} "
                  f"edge={card.edge_score} win_rate={wr} -> {card.bias}")

        # 3) Deep-dive one symbol.
        print("\nDEEP DIVE on GLD:")
        analysis = tw.analyze("GLD")
        card = analysis.card
        if card:
            print(" ", card.headline)
            if card.is_actionable and card.next_step and card.next_step.copy_text:
                print("  ticket:", card.next_step.copy_text)
            # ML is metered per day; None here just means not scored (never an error).
            if card.ml:
                print(f"  ML: score={card.ml.ml_score} win_prob={card.ml.ml_win_prob}")
            elif card.tier_notes:
                print("  ML note:", card.tier_notes)

        # 4) ML scores for a batch. The daily-limit nudge is DATA, not an error.
        result = tw.score([
            {"symbol": "AAPL", "date": "2026-07-12", "days_out": 18, "direction": "long"},
        ], market="2")
        if isinstance(result, MLDailyLimit):
            print("\nML daily limit reached:", result.message)
        else:
            print(f"\nScored {result.granted} item(s); "
                  f"ML remaining today: {result.ml_remaining_today}")


if __name__ == "__main__":
    main()
