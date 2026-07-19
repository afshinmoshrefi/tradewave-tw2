---
title: "Connect TradeWave to ChatGPT or Claude"
slug: "connect-an-ai-agent-mcp"
description: "Add the TradeWave server, sign in to your TradeWave account, and start asking market-research questions."
order: 5
read_minutes: 5
---

## Connect TradeWave

Use the instructions for the application you want to connect:

- [ChatGPT](#chatgpt)
- [Claude.ai and Claude Desktop](#claudeai-and-claude-desktop)

You will add this TradeWave server URL:

```text
{{MCP_URL}}
```

After you add the server, TradeWave opens its own sign-in page. Sign in with your TradeWave account and approve access.

## ChatGPT

ChatGPT currently exposes custom MCP connections through either **Plugins** or **Apps**, depending on the account and workspace.

### If your account has Settings → Plugins

1. In ChatGPT, open **Settings → Security and login** and turn on **Developer mode**.
2. Open **Settings → Plugins**, or go directly to [chatgpt.com/plugins](https://chatgpt.com/plugins).
3. Select the plus button to create a developer-mode app.
4. Enter these details:

   - **Name:** TradeWave
   - **Description:** Seasonal market research, ML scoring, and the published daily-pick record
   - **MCP server URL:** `{{MCP_URL}}`

5. Select **Create**. When TradeWave opens, sign in and approve access. A successful connection displays the tools advertised by TradeWave.
6. Start a new chat. Select **+ → More → TradeWave** to make the tools available in that conversation.

### Business, Enterprise, and Edu workspaces

A workspace administrator must allow custom MCP apps. Admins and authorized developers create TradeWave under **Workspace settings → Apps → Create** or **Settings → Apps → Create**, enter the details above, select **Scan Tools**, complete TradeWave authorization, and then select **Create**. After the app is approved for the workspace, members connect it under **Settings → Apps** and enable it in a chat.

If neither **Plugins** nor the custom-app controls are available, ask your workspace administrator whether custom MCP apps are enabled. OpenAI maintains the current paths in its [Connect from ChatGPT guide](https://developers.openai.com/apps-sdk/deploy/connect-chatgpt) and [workspace MCP guide](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta).

## Claude.ai and Claude Desktop

TradeWave is a remote connector, so a connection added to your Claude account is available in Claude.ai and Claude Desktop.

### Free, Pro, and Max accounts

1. Open **Customize → Connectors**.
2. Select **+**, then **Add custom connector**.
3. Enter **TradeWave** as the name and `{{MCP_URL}}` as the remote MCP server URL.
4. Select **Add**, then **Connect**.
5. Sign in to TradeWave and approve access.
### Team and Enterprise workspaces

An Owner must first open **Organization settings → Connectors**, select **Add → Custom → Web**, and add the TradeWave server URL. After that, each member opens **Customize → Connectors**, finds TradeWave, selects **Connect**, and completes TradeWave sign-in.

### Enable TradeWave in a conversation

Select **+ → Connectors** and enable TradeWave for the conversation where you want to use it. Anthropic maintains the current account and workspace paths in its [custom connector guide](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

## Confirm the connection

Start a new conversation with TradeWave enabled and ask:

> Use TradeWave's `whoami` tool and tell me which TradeWave plan and markets it recognizes.

A successful test visibly shows a TradeWave tool call. Confirm that the returned plan and markets match the TradeWave account you authorized.

## Try one research question

> What seasonal opportunities are entering their window in the next two weeks?

You can ask follow-up questions in ordinary language. Ask for the supporting years, Trend Chart, or published record when you want more evidence.

Historical win rate, ML win probability, and the published-pick win rate measure different things. The [MCP overview]({{MCP_SETUP_URL}}#results) explains each result.

Your available markets and ML usage follow the TradeWave plan on the account you authorized. If a feature is outside that plan, the tool returns a clear explanation.

## Troubleshooting

### ChatGPT created the app, but TradeWave is not available in chat

Start a new conversation, select **+ → More**, and choose TradeWave. Creating the app does not automatically enable it in every conversation.

### Claude does not show Add custom connector

In a Team or Enterprise workspace, ask an Owner to add the connector under **Organization settings → Connectors**. You can then connect your own TradeWave account under **Customize → Connectors**.

### The TradeWave sign-in page keeps reopening

Remove the TradeWave connection from the application, add `{{MCP_URL}}` again, and complete sign-in in the same browser session.

### The connection works, but a market or ML result is unavailable

Ask TradeWave which plan, markets, and ML allowance it recognizes. Access follows the TradeWave account used during authorization.

## Other clients

Cursor and other developer clients can connect to TradeWave as a remote Streamable HTTP MCP server when their OAuth implementation is compatible. Add `{{MCP_URL}}` using the client's remote-server configuration, then complete the TradeWave sign-in flow.

Some developer clients and versions handle remote OAuth differently. If direct sign-in does not work, follow the [developer-key fallback in the MCP reference]({{DOCS_URL}}/mcp-reference.html#developer-authentication). This fallback is for developer clients only; it does not change the ChatGPT or Claude instructions above.

Check TradeWave results against current price, news, fundamentals, earnings, and your own risk process.
