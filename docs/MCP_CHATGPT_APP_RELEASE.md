# ChatGPT app release runbook for TradeWave MCP

ChatGPT does **not** continuously mirror the live MCP server. After an app is approved,
ChatGPT uses a frozen snapshot of its tool names, descriptions, inputs, and actions. A server
deployment alone therefore does not update the TradeWave app. OpenAI documents this behavior
and the refresh controls in [Developer mode and MCP apps in ChatGPT](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta).

This is a release gate, not an optional cleanup. A stale snapshot can advertise deleted tools,
hide new tools, or call a current tool with an old input schema.

## 1. Preconditions - do not scan or refresh early

1. Deploy one clean, committed release candidate to the MCP host and restart the service.
2. Verify the public endpoint, OAuth discovery, and exact live schema:

   ```bash
   python3 ops/verify_mcp_contract.py --url https://mcp-dev.trxstat.com/
   ```

3. Continue only after that command reports authenticated negotiation for MCP `2025-11-25`
   and compatibility with `2025-06-18`, the exact 17 tools on both revisions, current input
   schemas, and HTTPS-safe OAuth discovery. The authorization-server metadata must advertise
   dynamic registration (or CIMD), authorization-code + refresh-token grants, PKCE S256,
   public-client token authentication (`none`), and `offline_access`.

Scanning while an old worker is still live can freeze the wrong contract into ChatGPT again.

### Dated standards baseline

As of 2026-07-15, this release intentionally pins the official Python SDK
[`mcp==1.28.1`](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.28.1) and uses
the latest final `2025-11-25` protocol while retaining `2025-06-18` compatibility. The SDK's v2
stateless protocol line is still a breaking prerelease, so it is not a release-candidate dependency.
Re-evaluate v2 only after its final SDK/spec release and a separate ChatGPT interoperability,
OAuth, load, and rollback qualification pass.

## 2. Choose the update path by ChatGPT plan

### Enterprise or Edu - refresh in place

1. Open **Workspace Settings -> Apps**.
2. Find TradeWave, open the **...** menu, and choose **Action control**.
3. Choose **Refresh** to fetch the latest MCP actions and definitions.
4. Review every definition diff.
5. Explicitly enable the new actions. ChatGPT leaves newly discovered actions disabled by
   default.
6. Publish/update the app for the intended workspace access groups.

This preserves the app record. Existing OAuth authorization normally remains associated with
that app, although a user may still be asked to authorize again if credentials expired or the
OAuth scopes/metadata changed.

### Business - recreate and republish

OpenAI currently does not support updating a published Business custom app in place.

1. Keep the existing TradeWave app installed as a rollback path.
2. Open **Workspace Settings -> Apps -> Create**.
3. Enter the released MCP endpoint and the current app metadata/authentication choice.
4. Choose **Scan Tools**. Complete the TradeWave OAuth prompt and wait for the scan to finish.
5. Review the scanned contract against the acceptance checklist below.
6. Choose **Create**, test the draft in a new chat, then publish it from
   **Workspace Settings -> Apps -> Drafts**.
7. Enable/connect the replacement app for the intended users. A recreated app has a new app
   record/ID, so treat it as a reconnect/reinstall and expect OAuth authorization during the
   scan or first connection.
8. Remove the old app only after the replacement passes every acceptance check.

### Pro or an unpublished developer-mode app

Pro supports custom read/fetch MCP apps in developer mode, but the documented in-place action
refresh control is the Enterprise/Edu control above. If the app's Manage/Action control UI does
not offer **Refresh**, recreate it through **Settings -> Apps -> Create -> Scan Tools** and test
the replacement before removing the old entry. Do not assume that editing the name or logo
rescans tools.

## 3. Exact acceptance contract

The refreshed/recreated app must expose exactly these 17 tools, in this order:

1. `find_best_opportunities`
2. `analyze_symbol`
3. `explain_pick`
4. `morning_briefing`
5. `whats_seasonal_now`
6. `compare_opportunities`
7. `list_markets`
8. `whoami`
9. `describe_tradewave`
10. `list_symbols`
11. `get_seasonal_opportunities`
12. `get_symbol_patterns`
13. `get_seasonal_pattern`
14. `get_opportunity_chart`
15. `score_opportunities`
16. `get_daily_pick`
17. `get_pick_track_record`

Reject the release if any of these checks fail:

- `get_opportunity_for_symbol` is absent.
- Descriptions use **Pattern Card** and **neutral**, never `SignalCard` or `NO_SIGNAL`.
- `find_best_opportunities` includes `view`.
- `find_best_opportunities.limit` defaults to 10, caps compact views at 100, and the runtime
  rejects more than 25 evidence-heavy cards for `view=full` before calling the gateway.
- `analyze_symbol` includes `view` and `include_chart`.
- `whats_seasonal_now` and `compare_opportunities` include `view`.
- `compare_opportunities.symbols` requires 2-10 symbols.
- `list_symbols` includes optional `prefix` and `limit`, defaults to a 100-symbol page,
  and caps `limit` at 1000.
- `get_seasonal_opportunities` is explicitly single-date and does not publish an ignored
  `to_date` action input; its MCP result limit defaults to 25 and caps at 100.
- Published choices are canonical enums: `direction=long|short`,
  `view=decision|table|full`, the documented rank/period/PE values, and
  `score_opportunities.market=0|1|2|3|4|11`.
- Win-rate inputs are bounded 0-1; day inputs 1-366; year inputs 1-99; and result limits
  are positive and capped.
- `score_opportunities.opportunities` requires 1-100 typed items with `symbol`, `date`,
  `days_out`, and `direction`.
- `score_opportunities.market` is an optional top-level enum for one ML-eligible
  market per batch (default `2`); `market` is not an item field.
- All tools explicitly advertise `destructiveHint=false` and `openWorldHint=false`.
- Read-only primitives advertise `readOnlyHint=true`. ML-metered tools advertise
  `readOnlyHint=false` because a call can consume the caller's quota.

The repository freezes the same contract in
`site/api_docs/generate_api_extras.py`, validates it hermetically in
`tests/test_mcp_discovery_contract.py`, and validates the deployed server independently through
`ops/verify_mcp_contract.py`.

## 4. Post-publish smoke test

Use a **new chat/task** so the client does not retain the old task's tool catalog.

1. Select the refreshed/replacement TradeWave app.
2. Ask "What can TradeWave do and what plan am I on?" and confirm `whoami` is called.
3. Ask "Explain how to read TradeWave's three win-rate fields" and confirm
   `describe_tradewave` is called.
4. Ask "Good morning - give me my TradeWave briefing" and confirm `morning_briefing` is called.
5. Analyze one symbol with full receipts and chart data; confirm `view=full` and
   `include_chart=true` are accepted.
6. Compare two symbols; confirm the comparison succeeds concurrently and returns current
   Pattern Card language.
7. Confirm the app UI/action list contains 17 enabled actions and no deleted alias.
8. Confirm the OAuth grant includes `offline_access`. Reopen the app in another new chat after
   the initial access-token window (or use the workspace's supported reconnect/refresh test) and
   confirm a tool succeeds without asking the user to authorize again. A first successful login
   alone does not prove refresh-token durability.

Record the released git commit, ChatGPT app ID, plan/update path used, scan time, verifier output,
and smoke-test result in the release record.

## 5. Rollback rule

If the refreshed app fails, disable the newly changed actions or keep users on the old app while
the server is corrected. For a recreated app, **do not remove the old app until the replacement
has passed the exact 17-tool check and the new-chat smoke test**.
