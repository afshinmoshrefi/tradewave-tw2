"""TradeWave's close-to-close long return, shared by historical engine views."""


def long_return_pct(entry_close, exit_close):
    return round(100 * (exit_close - entry_close) / entry_close, 2)
