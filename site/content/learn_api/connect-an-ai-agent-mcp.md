---
title: "Connect an AI agent with MCP"
slug: "connect-an-ai-agent-mcp"
description: "Connect ChatGPT, Claude.ai, or Claude Desktop to TradeWave with a simple sign-in, or wire Cursor and other BYOK clients with an API key."
order: 5
read_minutes: 8
---

## What MCP gives you

The Model Context Protocol (MCP) is an open standard that lets an AI assistant call external tools through a single connection. Instead of pasting JSON into a chat or writing glue code, you point the assistant at a server, and it discovers the available tools and calls them on your behalf. Ask in plain English, and the agent decides which tool to run.

TradeWave runs a hosted MCP server at `{{MCP_URL}}`. It exposes the exact same detected seasonal patterns as the REST API - the server composes a Pattern Card for you, so your agent gets the win-rate percentages, a normalized seasonal index, an honest edge score, an ML view, and a public track record. It never gets raw prices or OHLCV bars. Every response still carries its `disclaimer`: outputs are educational, not personalized advice.

Think of TradeWave as a research partner with one job. It supplies a seasonal-plus-62-feature-ML statistical edge and the timing, and it is deliberately blind to fundamentals, valuation, news, catalysts, macro and rates, analyst views, earnings dates, and the live price. That is by design: it pairs with your assistant's own web, news, and reasoning tools. TradeWave brings the seasonal and ML edge, the agent extends it with fundamentals, news, and macro, and the two synthesize one view.

The intended loop is explicit, and it is worth wiring into your agent's instructions:

1. Call `describe_tradewave` first. It self-documents the seasonal and ML method, ships a "SEASONAL ANALYSIS KNOBS" glossary, and lists per-market coverage, so the agent knows what every field means and which markets support which calls before it leans on a number.
2. Pull a card. Every Pattern Card carries an `extend_research` block that names, in the card itself, exactly what TradeWave cannot see (fundamentals, news, macro, earnings, the live price) and what to verify with your own tools.
3. Loop back. Take the seasonal and ML edge plus the timing from the card, then use your web, news, and earnings tools to check the things the card told you it cannot see, and synthesize one view. The card hands the research off to you on purpose; it does not pretend to be the whole answer.

Authentication depends on the client:

- **OAuth clients (ChatGPT, Claude.ai, Claude Desktop) - sign in, no API key.** Paste the server URL into the app's connector settings, click Connect, and log in with your TradeWave account. The OAuth flow is discovered automatically, and your plan follows the account you sign in with.
- **BYOK clients (including Cursor) - bring your own key.** The client sends the same bearer token you use for REST:

```
Authorization: Bearer tw_live_xxx
```

For the BYOK path, get a key at {{CONSOLE_URL}}. Treat it like a password and keep it out of shared configs you might commit. Want to wire up a client and see a real card before you sign up? Drop in the public demo token `tw_demo_explore` instead of your own key - it returns live Explorer-tier cards so your first call works immediately.

## The flagship tools

The server publishes 17 tools: 6 flagship tools that map to the richest API calls, plus 11 lower-level primitives for agents that want to compose their own workflow. The flagship six lead the menu: `find_best_opportunities`, `analyze_symbol`, `explain_pick`, `morning_briefing`, `whats_seasonal_now`, and `compare_opportunities`. Behind them sit the 11 primitives: `list_markets`, `whoami`, `describe_tradewave`, `list_symbols`, `get_seasonal_opportunities`, `get_symbol_patterns`, `get_seasonal_pattern`, `get_opportunity_chart`, `score_opportunities`, `get_daily_pick`, and `get_pick_track_record`. Two are worth calling out: `whoami` reports your tier and remaining ML allowance, and `describe_tradewave` self-documents the seasonal and ML method so the agent can explain what the numbers mean before it uses them.

| Tool | What it does | Maps to |
| --- | --- | --- |
| `find_best_opportunities` | Sweep markets over a window, filter and rank, return ranked Pattern Cards | `GET /scan` |
| `analyze_symbol` | One rich Pattern Card for a named symbol, plus `other_setups` | `GET /analyze/{symbol}` |
| `explain_pick` | Walk through today's daily pick and its forward-tested receipts | `GET /daily-pick` |
| `morning_briefing` | The one-call start of the day: today's pick, the live track record, and the top setups entering their window | `GET /daily-pick` + `GET /daily-pick/track-record` + `GET /scan` (composed) |
| `whats_seasonal_now` | What is lining up right now across your in-scope markets | `GET /scan?window=now` |
| `compare_opportunities` | Put two or more setups side by side on edge, win rate, and ML | composed |

The card-bearing tools all return the same Pattern Card shape: a `bias` field (`bullish`, `bearish`, or `neutral`), `edge_score`, `stats`, an optional `ml` block, and the `receipts` audit trail. When the best available setup is weak, the tool returns a `neutral` bias and no order ticket on purpose. That conflict-free honesty is the point.

## Progressive disclosure: decide cheap, then pull the receipts

Every flagship tool takes a `view` knob, so you spend tokens only where the decision needs them.

| `view` | What you get | Use it for |
| --- | --- | --- |
| `decision` | The verdict and the few numbers a decision turns on - the **default over MCP** | The lean read; a scan that should not flood the context window |
| `table` | Compact one-line rows, one per setup | A shortlist you want to skim, rank, or compare |
| `full` | The complete card: years tested, wins and losses, per-year returns, best and worst year, and the Trend Chart curve | The one card you are about to act on |

The pattern in practice is two calls: scan lean, then go deep on the winner.

```
find_best_opportunities(markets=["2"])              # view=decision by default - a short, cheap read
analyze_symbol("XLE", view=full, include_chart=true) # the full receipts, with the Trend Chart inline
```

`analyze_symbol` with `include_chart=true` (the REST equivalent is `include=chart`) returns the Trend Chart curve and the per-year bars in the same response, so you do not make a second call to `get_opportunity_chart` just to see the shape. The raw REST API defaults to `view=full`; MCP defaults to `view=decision` because an agent reading a card wants the verdict first.

## The lookback band

Pattern detection takes two knobs: `years` (the lookback - how far back to scan) and `min_winning_years` (the win-rate floor - how many of those years had to be profitable). `min_winning_years` defaults to about 90% of `years`, and it must stay inside the market's band. So `years=20` gives a valid `20-18`, while an out-of-band combo like `20-9` is rejected with the valid range named back to you (for example, "min_winning_years must be between 17 and 20"). The floor is market-specific: S&P 500 sits near 85% at a 20-year lookback, Wilshire near 90%, FOREX Liquid near 70%.

Per-symbol pattern detection (`get_symbol_patterns`) exists for five markets only - ids 0, 1, 2, 7, 9 (DOW 30, NASDAQ 100, S&P 500, Futures & Commodities, FOREX Liquid). For any other market the per-symbol tool returns a clear error; reach for `find_best_opportunities` to scan that market instead. `list_markets` reports each market's pattern-detection coverage and an example band, so the agent can check before it calls.

## Set up ChatGPT

ChatGPT connects to remote MCP servers over HTTP directly, and it signs you in - there is no `npx` bridge and no API key. In ChatGPT, open Settings, then Connectors (enable Developer mode under Advanced if you have not already), choose Create, and paste the server URL:

- Server URL: `{{MCP_URL}}`
- Auth: OAuth - sign in with your TradeWave account

ChatGPT discovers the sign-in flow from the server automatically. Click Connect, log in with your TradeWave account, and approve. Once the connector is enabled, the TradeWave tools are available to the model in that conversation, and your plan follows the account you signed in with.

## Set up Claude.ai

Claude.ai works the same way: paste the server URL, click Connect, sign in. In Claude.ai, open Settings, then Connectors, choose Add custom connector, and paste the server URL:

- Server URL: `{{MCP_URL}}`
- Auth: OAuth - sign in with your TradeWave account

Click Connect and log in with your TradeWave account when prompted. No API key needed - the tools appear in the conversation's tools menu once connected.

## Set up Claude Desktop

Claude Desktop can connect directly to the hosted server with OAuth. Open Settings, choose Connectors, add a custom connector, and paste `{{MCP_URL}}`. Click Connect and sign in with your TradeWave account. Your MCP access follows that web account, including an active trial or teaser.

If you specifically need the BYOK path, you can instead bridge to the hosted server with `mcp-remote` and an API key. Open your config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add a `tradewave` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "tradewave": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "{{MCP_URL}}",
        "--header",
        "Authorization: Bearer tw_live_xxx"
      ]
    }
  }
}
```

Restart Claude Desktop after adding the optional local BYOK configuration. The TradeWave tools appear in the tools menu, and you can start asking questions in the next section.

## Set up Cursor (BYOK)

Cursor reads MCP servers from `~/.cursor/mcp.json` (or a project-local `.cursor/mcp.json`). The shape is the same:

```json
{
  "mcpServers": {
    "tradewave": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "{{MCP_URL}}",
        "--header",
        "Authorization: Bearer tw_live_xxx"
      ]
    }
  }
}
```

Reload the window. Cursor's agent can now call `find_best_opportunities` and friends while you work.

## What a good prompt looks like

MCP tools work best when you ask the question you actually have and let the agent pick the tool. Some prompts that route cleanly:

- "Good morning - what's my briefing?" - `morning_briefing` returns today's pick, the live track record, and what is entering its window, in one call.
- "Find the best seasonal setups I can trade this week." - the agent calls `find_best_opportunities` with `window=next_2_weeks` and ranks them.
- "Is there a seasonal edge in XLE right now? Show me the receipts." - this hits `analyze_symbol`, then reads the `receipts` block.
- "Explain today's daily pick like I am new to seasonality." - `explain_pick` returns the Pattern Card and its forward-tested track record.
- "What is seasonal across my markets today, long only?" - `whats_seasonal_now` filtered to `direction=long`.
- "Compare the energy and tech setups - which has the stronger win rate and ML view?" - `compare_opportunities`.

A useful habit: ask the agent to surface these three numbers by name so you do not conflate them. They are not interchangeable - one is a frequency, one is a probability, and one is a live forward-tested result.

| Field | Meaning | Range |
| --- | --- | --- |
| `historical_win_rate` | Seasonal in-sample share of past years that were profitable | 0..1 |
| `ml_win_prob` | The 62-feature ML model's predicted probability for this setup | 0..1 |
| `track_record.win_rate` | The live, forward-tested hit rate of the published daily picks | 0..1 |

These are three different numbers. One is the seasonal historical record, one is a forward-looking per-instance ML prediction, and one is the live forward-tested result of real published picks. They answer different questions, so never let your agent blend them into a single "win rate."

## What the agent gets back

Here is a trimmed result from `find_best_opportunities`, illustrative only - your live values will differ:

```json
{
  "rank": 1,
  "symbol": "XLE",
  "market": { "id": "11", "name": "ETFs" },
  "direction": "long",
  "bias": "bullish",
  "setup": {
    "entry_date": "2026-06-05",
    "entry_window": "2026-06-03..2026-06-08",
    "hold_days": 21,
    "exit_date": "2026-06-26"
  },
  "edge_score": 78,
  "stats": {
    "historical_win_rate": 0.81,
    "sharpe_ratio": 1.9,
    "avg_return_pct": 3.4,
    "median_return_pct": 3.1,
    "years": "16"
  },
  "ml": { "ml_score": 72, "ml_win_prob": 0.69, "pred_return_pct": 2.8, "pred_mfe_pct": 4.5 },
  "next_step": {
    "order_ticket": {
      "side": "buy",
      "symbol": "XLE",
      "type": "MARKET",
      "time_in_force": "DAY",
      "suggested_entry_date": "2026-06-05",
      "suggested_exit_date": "2026-06-26"
    }
  },
  "headline": "Energy ETF has risen in 13 of the last 16 Junes",
  "disclaimer": "Educational, not personalized advice."
}
```

Notice the `order_ticket` carries `side`, `symbol`, `type`, `time_in_force`, and dates - and no price or limit level. TradeWave shows the edge and the timing; you place the trade at any broker. We never take your trades.

## ML and metering over MCP

ML behaves the same as on REST. The model covers US stocks, indices, and ETFs and only shorter seasonal holds (up to about 90 days); longer holds come back with `ml: null`. ML is offered on every tier but metered per day - free accounts get a small daily allowance, while Pro and Business are unlimited. When you run out, the tool still returns a normal result (never an error) with a gentle upgrade nudge and `ml_remaining_today`. The daily pick's ML is always free. See {{PRICING_URL}} for current tiers.

## Where to go next

Your agent now has the same flagship calls as the REST API: discovery via `find_best_opportunities`, deep dives via `analyze_symbol`, and the receipts-backed `explain_pick`. Point it at a market, ask the question you actually have, scan lean with `view=decision`, then go `view=full` on the card you act on. Let `describe_tradewave` teach the method first, and let each card's `extend_research` block tell you what to verify with your own tools.

One posture to keep front of mind: TradeWave is educational only. The seasonal patterns are impersonal and identical for everyone, the platform never reads or advises on your holdings, and every pattern-bearing response carries the same educational disclaimer. It is an edge and a timing input, not personalized advice.
