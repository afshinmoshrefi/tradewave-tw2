---
title: "Rate limits, quotas, and tiers in practice"
slug: "rate-limits-and-tiers"
description: "Read the X-RateLimit headers, back off on 429 and 5xx, handle the ML upgrade nudge, and manage keys in the TradeWave console."
order: 7
read_minutes: 8
---

## Three limits, three behaviors

A robust TradeWave client has to respect three independent budgets. They are easy to confuse, so separate them up front - each one fails differently, and that difference is the whole point:

| Limit | Scope | What happens at the edge |
| --- | --- | --- |
| **Per-minute rate limit** | Requests per key per minute | A real **HTTP 429**, with `Retry-After`. Back off and retry. |
| **Per-day request quota** | Requests per key per day | A real **HTTP 429** once exhausted. Resets daily. |
| **Daily ML allowance** | ML scorings per key per day | Never an error. **HTTP 200** with `ml: null` and an upgrade nudge. |

The headline distinction: rate and quota limits are transport-level guards that say "slow down" or "come back tomorrow," while the ML allowance is a **product** limit that degrades gracefully instead of failing. Your seasonal signal still arrives even when your ML budget is gone. Everything below is illustrative; live responses carry a `disclaimer` and are educational, not personalized advice.

We do not hardcode the exact per-minute, per-day, or ML-allowance numbers here, because they vary by tier and can change. Read them off the [API pricing page]({{PRICING_URL}}) and your [console]({{CONSOLE_URL}}). Qualitatively: free accounts get a small daily ML allowance, while Pro and Business are unlimited.

## The X-RateLimit headers

Every response carries rate-limit headers so you never have to guess where you stand. Read them on the way out and you can stay just under the line:

```
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 117
X-RateLimit-Reset: 1717329600
```

| Header | Meaning |
| --- | --- |
| `X-RateLimit-Limit` | Your ceiling for the current window |
| `X-RateLimit-Remaining` | Requests left in this window |
| `X-RateLimit-Reset` | Unix epoch second when the window resets |

When you do hit a 429, the response adds a `Retry-After` header (in seconds). Honor it exactly - it is the server telling you precisely how long to wait, which beats any guess.

## opp_limit: the per-call result cap

Separate from rate limits, the discovery endpoints cap how many results one call returns via the `limit` query parameter (often called `opp_limit` internally). On `GET /scan` and `GET /opportunities`, ask for what you will actually use:

```bash
curl "{{API_BASE}}/scan?markets=0,3&window=next_month&rank_by=sharpe&limit=10" \
  -H "Authorization: Bearer tw_live_xxx"
```

Pulling `limit=10` strong setups beats pulling hundreds you will never read. Smaller responses are faster, and since each call counts once against your per-minute and per-day budgets regardless of `limit`, asking for the right page size is free efficiency. Rank with `rank_by` (`edge`, `win_rate`, `sharpe`, `ml`, or `avg_return`) so the best results land at the top of your capped page.

## The ML upgrade nudge is a 200, not a 429

This is the trap that breaks naive clients. When a free-tier caller runs out of daily ML allowance, the gateway does **not** return 429 and does **not** raise. It returns a normal **HTTP 200** with the seasonal signal fully intact, `ml: null`, an `ml_remaining_today` counter, and a gentle upgrade message in `tier_notes`:

```json
{
  "symbol": "AAPL",
  "signal": "BUY",
  "stats": { "historical_win_rate": 0.74, "sharpe_ratio": 1.8, "years": "17" },
  "ml": null,
  "ml_remaining_today": 0,
  "tier_notes": "Daily ML allowance reached - seasonal signal shown. Upgrade for unlimited ML."
}
```

Treat "out of ML budget" exactly like "ML not eligible for this setup": fall back to the seasonal `stats` and keep going. The same `ml is None` branch also covers ML-ineligible markets and holds longer than about 90 days, where you instead see `tier_notes: "ML score not available for this setup - the ML model covers shorter seasonal holds (up to about 90 days)."` Remember the two distinct probabilities: `historical_win_rate` is the share of profitable years, while `ml_win_prob` is the model's predicted probability - never collapse them into one "win rate." And `GET /daily-pick` always returns a free ML block that never touches your allowance, so it is the cheapest way to keep an ML read in your pipeline.

## A robust Python client

Here is a small, production-shaped client that reads the rate headers, backs off with exponential delay plus jitter on 429 and 5xx, honors `Retry-After`, and treats the ML nudge as a normal branch:

```python
import random
import time
import requests

BASE = "{{API_BASE}}"
HEADERS = {"Authorization": "Bearer tw_live_xxx"}


def get(path, params=None, max_retries=5):
    """GET with header-aware throttling and exponential backoff."""
    for attempt in range(max_retries + 1):
        resp = requests.get(f"{BASE}{path}", headers=HEADERS,
                             params=params, timeout=30)

        # Proactively slow down before we hit the wall.
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None and int(remaining) <= 1:
            reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
            pause = max(0, reset - int(time.time()))
            if pause:
                time.sleep(min(pause, 60))

        # Retry on rate-limit and transient server errors.
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            if retry_after is not None:
                delay = float(retry_after)            # server told us exactly
            else:
                delay = (2 ** attempt) + random.uniform(0, 1)  # backoff + jitter
            time.sleep(delay)
            continue

        resp.raise_for_status()
        return resp.json()

    raise RuntimeError("exhausted retries")


def render(card):
    hist = card["stats"]["historical_win_rate"]   # share of profitable years
    ml = card.get("ml")
    if ml is None:
        # Ineligible market, >90-day hold, OR out of ML allowance - all land here.
        note = card.get("tier_notes", "ML not available.")
        left = card.get("ml_remaining_today")
        tail = f" (ml_remaining_today={left})" if left is not None else ""
        print(f"{card['symbol']}: hist_win_rate={hist:.0%}; ML n/a - {note}{tail}")
    else:
        # ml_win_prob is the MODEL's prediction, distinct from hist_win_rate.
        print(f"{card['symbol']}: hist_win_rate={hist:.0%}  "
              f"ml_win_prob={ml['ml_win_prob']:.0%}")


data = get("/scan", {"markets": "0,3", "window": "next_month",
                     "rank_by": "sharpe", "limit": 10})
for card in data["opportunities"]:
    render(card)
```

The key idea: a 429 is recoverable (wait, then retry), a 5xx is transient (back off, then retry), and the ML nudge is not a failure at all (it arrives as a 200 you simply branch on). Never retry a 200 just because `ml` is `null`.

## Key management: create, rotate, revoke

Your API keys live in the [console]({{CONSOLE_URL}}). Treat them like passwords:

- **Create** a key per environment or per service, so you can see usage and limits attributed cleanly. Keys look like `tw_live_xxx`.
- **Rotate** on a schedule and before any suspected exposure. Generate the new key, deploy it, confirm traffic has moved, then revoke the old one - that overlap means **zero downtime**.
- **Revoke** immediately if a key leaks. A revoked key fails authentication on the very next request.

Keep keys server-side and out of source control, logs, and client bundles. Rate limits and quotas are tracked **per key**, so a separate key per service also stops one noisy job from starving another.

## Where to go next

- [Your first TradeWave API call](/learn/first-api-call) - get a key and read a `SignalCard`.
- [Using the ML win-probability model](/learn/ml-win-probability) - the full `ml` block, metering, and the 90-day horizon.
- [Cross-market screener](/learn/cross-market-screener) - drive `GET /scan` with `rank_by` and `limit`.

Building an AI agent? The same signals - and the same per-key limits and graceful ML metering - apply over MCP at {{MCP_URL}} (sign in with your TradeWave account from ChatGPT or Claude.ai, or bring your own key in the `Authorization` header from dev tools), with tools like `find_best_opportunities` and `analyze_symbol`. We show the edge and the timing; you place the trade at any broker. Every response is educational and carries a disclaimer, not personalized advice.
