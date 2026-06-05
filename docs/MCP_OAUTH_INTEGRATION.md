# MCP OAuth (consumer connect via WorkOS) - integration spec + plan

Status: IN PROGRESS (started 2026-06-05). Goal = a researcher adds TradeWave to ChatGPT or
Claude.ai, logs in with their TradeWave account (WorkOS), and gets real seasonal data in chat.
North-star + decisions: memory `project_mcp_consumer_oauth_goal`. Research-validated 2026-06-05.

## 1. Architecture (the spec-mandated, stable pattern)

OAuth role split (MCP spec, stable since 2025-06-18):
- **WorkOS AuthKit = the Authorization Server** (hosted, $0 extra; part of AuthKit, free <1M MAU).
  Runs login UI + consent, `/authorize`, `/token`, JWKS, RFC 8414 AS metadata, PKCE-S256, refresh,
  and client registration via **DCR (RFC 7591) + CIMD** - the piece that makes ChatGPT + Claude
  connect with zero manual setup. We build NONE of this.
- **TradeWave MCP server = the Resource Server.** We add only: (a) RFC 9728 protected-resource
  metadata, (b) 401 + `WWW-Authenticate` on missing/invalid token, (c) **validate the WorkOS JWT
  (audience-checked) on every request.** The official MCP SDK (`mcp` 1.27.2, what we already run)
  does (a)+(b) for us when `auth=AuthSettings(...)` + `token_verifier=...` are set; we supply (c).

Flow: ChatGPT/Claude -> discover our `/.well-known/oauth-protected-resource` -> follow to WorkOS AS
-> DCR/CIMD register -> OAuth 2.1 + PKCE login -> bearer JWT -> our MCP validates it -> tool call.

## 2. How a logged-in researcher maps to their tier (the key design)

We do NOT migrate users. The token is the identity carrier; we resolve it to the existing tier:

1. The MCP `TokenVerifier` validates the incoming credential. It accepts BOTH:
   - a **WorkOS OAuth JWT** (consumer apps) -> verified against WorkOS JWKS -> subject = `workos_user_id`;
   - a **`tw_live_` BYOK key** (dev tools / API customers) -> the existing path (unchanged).
   One unified verifier so BYOK and OAuth coexist behind the SDK's auth gate.
2. Per tool call the MCP calls the gateway:
   - BYOK -> forward the `tw_live_` key (unchanged).
   - OAuth -> call with the **MCP service key** + header **`X-TW-Principal-WorkOS: <workos_sub>`**.
3. The gateway, for the trusted **`mcp` service tier only**, resolves `workos_sub` -> `users` row
   (`db.get_user_by_workos_id`, keyed on the existing `users.workos_user_id` column) -> applies that
   user's **REAL** api tier (free/dev/pro) + meters under their real user_id. (This differs from the
   Tara `cb:` delegation, which keeps the fixed chatbot tier - here we want the user's real tier.)

INVARIANT: the `X-TW-Principal-WorkOS` delegation is honored ONLY for the `service:true` `mcp` tier
(like the chatbot one). The MCP service key is powerful (acts as any user at their real tier) so it is
loopback-internal + secrets.env only, never logged. The trust chain is: WorkOS signed the user -> the
MCP validated that WorkOS JWT (JWKS) -> the gateway trusts the MCP service principal. A `workos_sub`
with no matching `users` row is REJECTED (401), never defaulted.

## 3. What we build (file-level)

- `apiserver/tiers.py` - add an `mcp` INTERNAL_TIER (`service:true`); keep it OUT of the sold catalog.
- `apiserver/db.py` - `get_user_by_workos_id(workos_user_id)` -> {user_id, email, tier, api_tier, roles}.
- `apiserver/auth.py` - in the delegation, when the caller is the `mcp` service tier and a valid
  `X-TW-Principal-WorkOS` header is present: resolve the WorkOS user -> their REAL tier/entitlements +
  real user_id (reject if no user). Regex-validate the sub.
- `mcpserver/server.py` - a `WorkOSTokenVerifier(TokenVerifier)` (PyJWT + cached WorkOS JWKS; verify
  iss=authkit domain, aud=our resource id, exp; subject=`sub`) that ALSO accepts `tw_live_` keys
  (delegating to the gateway's existing check); wire `FastMCP(auth=AuthSettings(issuer_url=<authkit>,
  resource_server_url=<public mcp url>, required_scopes=[...]), token_verifier=...)`. Tool handlers:
  on an OAuth principal, call the gateway with the mcp service key + `X-TW-Principal-WorkOS`.
- `apiserver/provision_mcp_key.py` (mirror `provision_chatbot_key.py`) - mint the `mcp` service key.
- config/secrets: `WORKOS_AUTHKIT_DOMAIN` (already in config.py for web), `TW2_MCP_PUBLIC_URL`
  (the canonical resource id / audience), `MCP_GATEWAY_KEY` (the mcp service key).

## 4. WorkOS dashboard steps (OPERATOR - I cannot do these)

In the WorkOS dashboard (same project as the web tier):
1. Enable AuthKit as an OAuth/MCP authorization server (AuthKit -> "Connect"/MCP).
2. Create the OAuth Application for the MCP; register the **resource indicator** = the canonical
   public MCP URL (e.g. `https://mcp.tradewave.ai` prod / `https://mcp-dev.trxstat.com` dev).
3. Enable **Dynamic Client Registration** (and CIMD) so ChatGPT/Claude self-register.
4. Give me, for secrets.env per env: the **AuthKit domain** (`https://<project>.authkit.app`), the
   **resource/audience** value, and confirm the JWKS URL.
(Branded login = the $99/mo Custom Domain add-on - DEFERRED until this is running + proven useful.)

## 5. Testing

- Local (me): unit-test the `WorkOSTokenVerifier` with a self-signed test JWKS (we cannot mint a real
  WorkOS token); test the gateway `workos_sub -> real tier` path directly; confirm the protected-resource
  metadata + 401 WWW-Authenticate are served.
- End-to-end (operator, after WorkOS config + deploy): add the connector in ChatGPT Developer mode and
  in Claude.ai custom connectors, complete the WorkOS login, run a tool, confirm tier-correct results.

## 6. Marketing (in scope - per Afshin)

Update the consumer story on the dev portal + the MCP setup/connect docs: "Add TradeWave to ChatGPT or
Claude, log in with your TradeWave account, ask for the edge." Files: `site/api_marketing/generate.py`
(mcp page) + the connect-an-ai-agent learn lesson. Ship to PROD only once the OAuth is live (market
after it ships).

## 7. Status / sequencing

[in progress] gateway tier-resolution (tiers/db/auth) -> [next] MCP verifier + AuthSettings ->
provision script -> marketing -> operator WorkOS config -> deploy dev -> operator connect test.
