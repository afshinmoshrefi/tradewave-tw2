---
title: "Connect an AI agent with MCP"
slug: "connect-an-ai-agent-mcp"
description: "Wire Claude Desktop, Cursor, or ChatGPT to the TradeWave MCP server with BYOK auth and let your agent pull seasonal signals."
order: 5
read_minutes: 8
---

## What MCP gives you

The Model Context Protocol (MCP) is an open standard that lets an AI assistant call external tools through a single connection. Instead of pasting JSON into a chat or writing glue code, you point the assistant at a server, and it discovers the available tools and calls them on your behalf. Ask in plain English, and the agent decides which tool to run.

TradeWave runs a hosted MCP server at `https://mcp.tradewave.ai/mcp`. It exposes the exact same derived signals as the REST API - the server composes the `SignalCard` for you, so your agent gets percentages, a normalized seasonal index, an honest edge score, and a public track record. It never gets raw prices or OHLCV bars. Every response still carries its `disclaimer`: outputs are educational, not personalized advice.

TradeWave is a research partner, not an oracle. It supplies a seasonal plus 62-feature-ML statistical edge and the timing, and it is deliberately blind to fundamentals, valuation, news, catalysts, macro and rates, analyst views, earnings dates, and the live price. That is by design: it pairs with your assistant's own web, news, and reasoning tools. TradeWave brings the seasonal/ML edge, the agent extends it with fundamentals, news, and macro, and the two synthesize one view. Every card carries a research hand-off, and the `describe_tradewave` tool lets the agent self-document the method before it leans on a number.

Authentication is BYOK (bring your own key). Your MCP client sends the same bearer token you use for REST:

```
Authorization: Bearer tw_live_xxx
```

Get a key at https://tradewave.ai/account/api/keys. Treat it like a password and keep it out of shared configs you might commit.

## The flagship tools

The server publishes 16 tools: 5 flagship tools that map to the richest API calls, plus 11 lower-level primitives for agents that want to compose their own workflow. The flagship five lead the menu: `find_best_opportunities`, `analyze_symbol`, `explain_pick`, `whats_seasonal_now`, and `compare_opportunities`. Behind them sit the 11 primitives: `list_markets`, `whoami`, `describe_tradewave`, `list_symbols`, `get_seasonal_opportunities`, `get_symbol_patterns`, `get_seasonal_pattern`, `get_opportunity_chart`, `score_opportunities`, `get_daily_pick`, and `get_pick_track_record`. Two are worth calling out: `whoami` reports your tier and remaining ML allowance, and `describe_tradewave` self-documents the seasonal/ML method so the agent can explain what the numbers mean before it uses them.

| Tool | What it does | Maps to |
| --- | --- | --- |
| `find_best_opportunities` | Sweep markets over a window, filter and rank, return ranked SignalCards | `GET /scan` |
| `analyze_symbol` | One rich SignalCard for a named symbol, plus `other_setups` | `GET /analyze/{symbol}` |
| `explain_pick` | Walk through today's daily pick and its forward-tested receipts | `GET /daily-pick` |
| `whats_seasonal_now` | What is lining up right now across your in-scope markets | `GET /scan?window=now` |
| `compare_opportunities` | Put two or more setups side by side on edge, win rate, and ML | composed |

Each returns the same `SignalCard` shape: `signal` (`BUY`, `SELL`, or `NO_SIGNAL`), `edge_score`, `stats`, an optional `ml` block, and the `receipts` audit trail. When the best available setup is weak, the tool returns `NO_SIGNAL` and no order ticket on purpose. That conflict-free honesty is the point.

## Set up Claude Desktop

Claude Desktop speaks MCP over stdio, so you bridge to the hosted HTTP server with `mcp-remote`. Open your config file:

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
        "https://mcp.tradewave.ai/mcp",
        "--header",
        "Authorization: Bearer tw_live_xxx"
      ]
    }
  }
}
```

Restart Claude Desktop. The TradeWave tools appear in the tools menu, and you can start asking questions in the next section.

## Set up Cursor

Cursor reads MCP servers from `~/.cursor/mcp.json` (or a project-local `.cursor/mcp.json`). The shape is the same:

```json
{
  "mcpServers": {
    "tradewave": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.tradewave.ai/mcp",
        "--header",
        "Authorization: Bearer tw_live_xxx"
      ]
    }
  }
}
```

Reload the window. Cursor's agent can now call `find_best_opportunities` and friends while you work.

## Set up ChatGPT

ChatGPT connects to remote MCP servers over HTTP directly, so there is no `npx` bridge. In the connector settings, add a custom MCP connector pointing at the server URL and supply the auth header:

- Server URL: `https://mcp.tradewave.ai/mcp`
- Header: `Authorization: Bearer tw_live_xxx`

Once the connector is enabled, the TradeWave tools are available to the model in that conversation. Because authentication is header-based BYOK, the key stays in your connector config and never goes into the chat.

## What a good prompt looks like

MCP tools work best when you ask the question you actually have and let the agent pick the tool. Some prompts that route cleanly:

- "Find the best seasonal setups I can trade this week." - the agent calls `find_best_opportunities` with `window=next_2_weeks` and ranks them.
- "Is there a seasonal edge in XLE right now? Show me the receipts." - this hits `analyze_symbol`, then reads the `receipts` block.
- "Explain today's daily pick like I am new to seasonality." - `explain_pick` returns the SignalCard and its forward-tested track record.
- "What is seasonal across my markets today, long only?" - `whats_seasonal_now` filtered to `direction=long`.
- "Compare the energy and tech setups - which has the stronger win rate and ML view?" - `compare_opportunities`.

A useful habit: ask the agent to surface the two probabilities by name so you do not conflate them.

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
  "market": { "id": 11, "name": "ETFs" },
  "direction": "long",
  "signal": "BUY",
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
    "years": 16
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

ML behaves the same as on REST. The model covers US stocks, indices, and ETFs and only shorter seasonal holds (up to about 90 days); longer holds come back with `ml: null`. ML is offered on every tier but metered per day - free accounts get a small daily allowance, while Pro and Business are unlimited. When you run out, the tool still returns a normal result (never an error) with a gentle upgrade nudge and `ml_remaining_today`. The daily pick's ML is always free. See https://tradewave.ai/pricing for current tiers.

## Where to go next

Your agent now has the same flagship calls as the REST API: discovery via `find_best_opportunities`, deep dives via `analyze_symbol`, and the receipts-backed `explain_pick`. Point it at a market, ask the question you actually have, and let it bring back the signal. Every response is educational and carries a disclaimer; it is not personalized advice.
