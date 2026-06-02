# tradewave - Python SDK for the TradeWave Data API

Official Python client for the [TradeWave Data API](https://developers.tradewave.ai) (v1):
seasonal trading opportunities and ML win-probability signals for the 17 TradeWave
markets, plus the tracked daily AI pick.

**Signals only.** The API never returns raw prices or OHLCV. All monetary movement is
expressed as percentages, and the seasonal curve is a 0-100 normalized relative shape -
never a price. There are no price fields in this SDK by design.

## Install

```
pip install tradewave
```

Requires Python 3.9+ and `requests` (the only dependency).

## Quickstart

```python
from tradewave import Client

# api_key falls back to the TRADEWAVE_API_KEY env var when omitted.
with Client(api_key="tw_live_...") as tw:
    pick = tw.daily_pick()
    print(pick.card.headline)

    scan = tw.scan(window="now", min_win_rate=0.6)
    for card in scan:                       # iterate ranked cards directly
        print(card.rank, card.symbol, card.edge_score, card.signal)
```

Set the key once in your environment and `Client()` needs no arguments:

```
export TRADEWAVE_API_KEY=tw_live_...
```

```python
from tradewave import Client
tw = Client()          # reads TRADEWAVE_API_KEY
```

## Flagship endpoints

### `scan` - find the best seasonal setups

The flagship scanner. Fans out over your in-scope markets, ranks by `edge_score`, and
returns ranked `SignalCard`s.

```python
scan = tw.scan(
    window="now",          # "now" | "next_2_weeks" | "next_month" | "from..to"
    direction="long",      # "long" | "short"
    min_win_rate=0.6,      # filters on historical_win_rate (NOT ml_win_prob)
    min_years=8,           # trust filter: require years_tested >= N
    rank_by="sharpe",      # edge | win_rate | sharpe | ml | avg_return
    limit=10,
)

print(scan.window, scan.count, "of", scan.evaluated_count, "evaluated")
for card in scan:
    s = card.stats
    print(f"#{card.rank} {card.symbol} {card.direction} "
          f"edge={card.edge_score} win_rate={s.historical_win_rate} -> {card.signal}")
    if card.is_actionable and card.next_step:
        print("   ", card.next_step.copy_text)
```

`window="now"` returns setups whose entry date is within the next ~10 trading days.
Weak setups come back with `signal == "NO_SIGNAL"` and no order ticket - the API never
manufactures a trade.

### `analyze` - deep-dive one symbol

```python
analysis = tw.analyze("GLD", direction="long")
card = analysis.card
print(card.headline)
print(card.verdict)

# Alternate candidate setups for the same symbol:
for setup in analysis.other_setups:
    print(setup.entry_date, setup.hold_days, setup.historical_win_rate)
```

### `daily_pick` - today's AI pick + live track record

```python
pick = tw.daily_pick()
print("Pick:", pick.card.headline)
print("Made on:", pick.featured_date)

tr = pick.track_record                      # live forward-tested record
print(f"{tr.win_count}/{tr.count} wins, avg {tr.avg_return_pct}% per pick")

# The standalone, free-tier record of every past pick:
record = tw.daily_pick_track_record()
for p in record.picks:
    print(p.featured_date, p.symbol, p.result, p.return_pct)
```

## All methods

| Method | Endpoint |
|---|---|
| `list_markets()` | `GET /markets` |
| `list_symbols(market)` | `GET /markets/{id}/symbols` |
| `opportunities(market, from_=, direction=, min_win_rate=, limit=)` | `GET /opportunities` |
| `opportunities_for_symbol(symbol, market=)` | `GET /opportunities/{symbol}` |
| `scan(markets=, window=, direction=, min_win_rate=, min_years=, rank_by=, limit=)` | `GET /scan` |
| `analyze(symbol, market=, direction=, days_out=)` | `GET /analyze/{symbol}` |
| `pattern(market, symbol)` | `GET /patterns/{market}/{symbol}` |
| `seasonal_chart(market, symbol, entry_date=, days_out=)` | `GET /seasonal-chart` |
| `score(opportunities=[...])` | `POST /score` |
| `daily_pick()` | `GET /daily-pick` |
| `daily_pick_track_record()` | `GET /daily-pick/track-record` |

The `/opportunities` `from` parameter is a Python reserved word, so the SDK kwarg is
`from_` (it is sent on the wire as `from`).

## win_rate vs ml_win_prob (read this once)

These are two DISTINCT fields and are intentionally never both called "win rate":

- `stats.historical_win_rate` (and `Opportunity.win_rate`) - the share of past years the
  seasonal window finished profitable. The seasonal record.
- `ml.ml_win_prob` on a `SignalCard` (or `ml.win_prob` on the legacy `MLScore`) - the ML
  model's predicted probability for this specific setup.

## ML scoring and the graceful daily limit

ML is available on every tier but metered per day (free 5/day, Dev 100/day, Pro/Business
unlimited) and only on ML-eligible markets (ids 0-4, 11). The ML model covers
shorter-horizon holds (up to ~90 days); for longer holds `ml` is `null` - that is
expected, not an error.

When the daily allowance is already spent, `score()` returns the graceful upgrade nudge
as **data**, never an exception:

```python
from tradewave import MLDailyLimit

result = tw.score([
    {"symbol": "AAPL", "date": "2026-07-12", "days_out": 18, "direction": "long"},
])

if isinstance(result, MLDailyLimit):
    print("Daily ML limit reached:", result.message, result.upgrade_url)
else:
    print(f"Scored {result.granted}; remaining today: {result.ml_remaining_today}")
```

On cards, an exhausted quota shows up as `card.ml is None` with a `card.tier_notes`
message - again, never an error.

## Error handling

Non-2xx responses raise a typed exception hierarchy. All inherit `TradeWaveError`, which
carries `.status`, `.code`, `.message`, and `.response` (the parsed error body).

```python
from tradewave import (
    Client, TradeWaveError, AuthError, RateLimitError, NotFoundError, ServerError,
)

try:
    tw.analyze("NOPE")
except AuthError as e:           # 401 / 403
    ...
except NotFoundError as e:       # 404
    ...
except RateLimitError as e:      # 429 - e.retry_after holds the wait in seconds
    print("retry after", e.retry_after)
except ServerError as e:         # 5xx
    ...
except TradeWaveError as e:      # base - also covers timeouts / network errors
    print(e.status, e.code, e.message)
```

The client automatically retries on `429` and `5xx` with exponential backoff plus jitter,
honoring `Retry-After` when present (configurable via `max_retries`, default 3). Other
4xx errors are never retried. Rate-limit headers from the last response are available on
`tw.rate_limit` (the `X-RateLimit-*` values).

## Typed models and raw JSON

Every response parses into a dataclass (see `tradewave.models`). Models are tolerant:
they read fields with `.get`, never crash on an unknown or missing key, and preserve the
original payload on `.raw`:

```python
card = tw.daily_pick().card
card.headline            # typed field
card.raw["some_new_field"]   # anything the SDK has not modeled yet
```

If you would rather skip the models entirely, pass `raw=True` to any method to get the
parsed JSON dict:

```python
data = tw.scan(window="now", raw=True)   # plain dict
```

## Configuration

```python
Client(
    api_key="tw_live_...",                       # or TRADEWAVE_API_KEY
    base_url="https://api.tradewave.ai/v1",      # override for dev/staging
    timeout=30,                                   # seconds
    max_retries=3,                                # 429/5xx backoff
)
```

Use it as a context manager (`with Client(...) as tw:`) so the underlying
`requests.Session` is closed for you, or call `tw.close()` when done.

## Examples

- `examples/quickstart.py` - daily pick, scan, analyze, score.
- `examples/screener.py` - a small seasonal screener with receipts and error handling.

## Disclaimer

Educational seasonal + ML signal, not personalized investment advice and not a
recommendation to buy or sell. Past performance is not indicative of future results.
