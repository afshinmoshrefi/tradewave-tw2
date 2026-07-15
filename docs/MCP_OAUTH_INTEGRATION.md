# MCP OAuth (consumer connect via WorkOS) - integration spec + plan

Status: RELEASE CANDIDATE (hardened and revalidated 2026-07-15). Goal = a researcher adds
TradeWave to ChatGPT or Claude.ai, logs in with their TradeWave account (WorkOS), and gets
their tier-correct seasonal data in chat.

## 1. Architecture (the spec-mandated, stable pattern)

OAuth role split (MCP spec, stable since 2025-06-18):
- **WorkOS AuthKit = the Authorization Server** (hosted, $0 extra; part of AuthKit, free <1M MAU).
  Runs login UI + consent, `/authorize`, `/token`, JWKS, RFC 8414 AS metadata, PKCE-S256, refresh,
  and client registration via **DCR (RFC 7591)** (or CIMD when advertised) - the piece that makes ChatGPT + Claude
  connect with zero manual setup. We build NONE of this.
- **TradeWave MCP server = the Resource Server.** We add only: (a) RFC 9728 protected-resource
  metadata, (b) 401 + `WWW-Authenticate` on missing/invalid token, (c) **validate the WorkOS JWT
  (audience-checked) on every request.** The hash-locked official MCP SDK (`mcp` 1.28.1)
  does (a)+(b) for us when `auth=AuthSettings(...)` + `token_verifier=...` are set; we supply (c)
  through an asynchronous, single-flight, bounded JWKS resolver.

Flow: ChatGPT/Claude -> discover our `/.well-known/oauth-protected-resource` -> follow to WorkOS AS
-> DCR/CIMD register -> OAuth 2.1 + PKCE login -> bearer JWT -> our MCP validates it -> tool call.

## 2. How a logged-in researcher maps to their tier (the key design)

We do NOT migrate users. The token is the identity carrier; we resolve it to the existing tier:

1. The MCP `TokenVerifier` validates the incoming credential. It accepts BOTH:
   - a **WorkOS OAuth JWT** (consumer apps) -> verified against WorkOS JWKS -> subject = `workos_user_id`;
   - a **`tw_` BYOK key** (dev tools / API customers) -> connect-time validation plus the
     gateway's authoritative validation on each real call. The connect-time `/me` response must
     carry a gateway-issued `mcp_admission_id` (`acct_` + 64 lowercase hex), an opaque HMAC of the
     owning account. The SDK session owner still includes the exact API-key hash, so one key cannot
     use another key's session; only capacity accounting is collapsed across all keys on the account.
   One unified verifier so BYOK and OAuth coexist behind the SDK's auth gate.
2. Per tool call the MCP calls the gateway:
   - BYOK -> forward the `tw_live_` key (unchanged).
   - OAuth -> call with the **MCP service key** + header **`X-TW-Principal-WorkOS: <workos_sub>`**.
3. The gateway, for the trusted **`mcp` service tier only**, resolves `workos_sub` -> `users` row
   (`db.get_user_by_workos_id`, keyed on the existing `users.workos_user_id` column) -> applies that
   user's real web-mirrored MCP tier (Explorer/Navigator/Analyst/Strategist, merged safely with any
   separately held API entitlement) + meters under their real user_id. (This differs from the Tara
   `cb:` delegation, which keeps the fixed chatbot tier.)

INVARIANT: the `X-TW-Principal-WorkOS` delegation is honored ONLY for the `service:true` `mcp` tier
(like the chatbot one). The MCP service key is powerful (acts as any user at their real tier) so it is
loopback-internal + the root-managed least-privilege `mcpserver.env`, never logged. The broad platform
secrets file is not inherited by the MCP process. The trust chain is: WorkOS signed the user -> the
MCP validated that WorkOS JWT (JWKS) -> the gateway trusts the MCP service principal. A `workos_sub`
with no matching `users` row is REJECTED (401), never defaulted.

SESSION FAIRNESS: the process retains at most 128 stateful sessions and at most 24 per real
principal. OAuth capacity is keyed by the verified WorkOS subject, deliberately excluding dynamic
OAuth `client_id`; BYOK capacity is keyed by the gateway-issued account id, deliberately excluding
the individual API key. This supports the 20-session release target without allowing DCR or a plan's
multi-key allowance to multiply capacity. Pending handshakes count atomically. Authenticated requests
without a session id may create a transport only via POST; sessionless GET/DELETE/HEAD/PUT are rejected
before MCP SDK 1.28.1 can allocate state. Idle sessions reap after 30 minutes and DELETE frees the slot.

SECURITY BOUNDARY: OS isolation stops the MCP worker from reading or modifying `/home/flask` and the
broad platform secrets, but the loopback gateway is intentionally still trusted. It authenticates the
service key, resolves the delegated subject, selects and meters the tier, and supplies every tool result;
a compromised gateway or its current database role could forge those outcomes. Eliminating that trust
requires a separately isolated gateway and narrower database roles, a platform re-architecture outside
this MCP release candidate.

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
- config/secrets: deployment reads non-secret WorkOS/public/smoke metadata from the broad source. Its
  fixed root controller transactionally provisions or rotates the service key, removes any legacy broad
  assignment, and writes the key only in the explicit allowlist at `/etc/tradewave/mcpserver.env`
  (`root:root`, `0600`). systemd reads that file before
  dropping to the dedicated `tradewave-mcp` identity; the MCP process cannot browse
  `/etc/tradewave` or the mutable `/home/flask` checkout.

## 4. WorkOS / ChatGPT operator gates

The dev WorkOS authorization-server metadata, DCR, PKCE-S256 authorize route, and refresh-token
grant route have been probed successfully. For a new environment, configure the same project:
1. Enable AuthKit as an OAuth/MCP authorization server (AuthKit -> "Connect"/MCP).
2. Create the OAuth Application for the MCP; register the **resource indicator** = the canonical
   public MCP URL (e.g. `https://mcp.tradewave.ai` prod / `https://mcp-dev.trxstat.com` dev).
3. Enable **Dynamic Client Registration** (and CIMD) so ChatGPT/Claude self-register.
4. Store the **AuthKit domain** (`https://<project>.authkit.app`) and canonical resource/audience
   in the root-managed deployment source; never place a WorkOS management API key in the MCP
   runtime environment.
(Branded login = the $99/mo Custom Domain add-on - DEFERRED until this is running + proven useful.)

## 5. Testing

- Local (me): unit-test the `WorkOSTokenVerifier` with a self-signed test JWKS (we cannot mint a real
  WorkOS token); test the gateway `workos_sub -> real tier` path directly; confirm the protected-resource
  metadata + 401 WWW-Authenticate are served.
- End-to-end release gate: deploy the immutable candidate; pass exact-17/current+legacy protocol and
  20-session public load probes; refresh/recreate the frozen ChatGPT app; complete WorkOS login with
  `offline_access`; run `whoami`/`list_markets`; and confirm tier-correct scope plus refresh durability.

## 6. Marketing (in scope - per Afshin)

Update the consumer story on the dev portal + the MCP setup/connect docs: "Add TradeWave to ChatGPT or
Claude, log in with your TradeWave account, ask for the edge." Files: `site/api_marketing/generate.py`
(mcp page) + the connect-an-ai-agent learn lesson. Ship to PROD only once the OAuth is live (market
after it ships).

## 7. Status / sequencing

[implemented locally; release validation pending] gateway tier resolution, async verifier/AuthSettings,
bounded sessions and pools, least-privilege runtime, two-phase service-key rotation, hashed/audited
dependencies, immutable gateway+MCP deploy and rollback gates. The transaction versions both sides of
their `/me.mcp_admission_id` contract, canaries the gateway first and MCP against that candidate, switches
gateway then MCP, and restores MCP then gateway on failure. Verification uses a fresh sacrificial ordinary
key minted only after the durable journal exists and revoked before the journal can close; there is no
permanent verifier bearer. [release gate] finish adversarial controller tests ->
deploy dev -> prove rollback and forward recovery -> refresh/recreate ChatGPT app -> exact-17, tier,
and refresh-token smoke test.
