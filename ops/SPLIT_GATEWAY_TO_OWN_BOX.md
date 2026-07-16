# Splitting the API/MCP gateway onto its own box

The gateway (`apiserver/`, :8088) + MCP server (`mcpserver/`, :9090) launch **co-located on
the app box** (their own systemd processes, talking to the appserver over loopback). This is
the right topology at launch: the gateway is a thin proxy, the appserver is the bottleneck,
and loopback keeps the hot path (and Tara's chatbot round-trip) cheap.

Move them to a **dedicated box** when any trigger hits:
- public API/scan/ML load starts degrading the paid wave-viewer UX (noisy neighbor),
- you want the public attack surface OFF the box holding the full dataset + ML models + redis,
- the Business-tier SLA wants independent scaling, or
- the MCP SSE connection profile needs separate tuning.

## Why this is a config flip, not a rewrite

The gateway holds no authoritative data locally. Its shared state lives off-box and is
reached over the network:
- Postgres (`api_keys` + usage) via `POSTGRES_DSN`,
- gateway Redis db4 (rate limits, ML quota, API-key helpers, seasonal curves, and the
  shared scan-core cache) via `TW2_GATEWAY_REDIS_URL`,
- the appserver (all market/seasonal data) via `TW2_APPSERVER_URL`.

When `TW2_GATEWAY_REDIS_URL` is unset, the current co-located deployment keeps using
`REDIS_HOST`/`REDIS_PORT`/`API_REDIS_DB`. A split deployment must set the URL to a Redis
service reachable by every API node. This preserves cache hits and distributed single-flight
locks across boxes. The gateway never reads the appserver's private db0 keys.

So moving it means provisioning a box, repointing a handful of `secrets.env` values, and
moving the edge. Several gateway instances can later run behind a load balancer as long as
they share the same Postgres and gateway Redis. Keep **MCP on the SAME box as the gateway** so
`API_BASE_URL` stays loopback.

## Steps (operator runs these; author-only otherwise)

1. **Provision the box** (VLAN-joined, `10.0.0.x`). Clone the repo to `/home/flask`, create
   `venv-api`, install: `bash ops/bootstrap_api_services.sh` (installs venv-api + the two units
   + health-check). Do NOT expose origin ports publicly.

2. **`secrets.env` on the GATEWAY box** - set:
   | var | value | why |
   |---|---|---|
   | `TW2_APISERVER_BIND` | `10.0.0.<gw>:8088` | gateway must be reachable cross-box (default is loopback) |
   | `TW2_APPSERVER_URL` | `http://10.0.0.<app>:80` | reach the appserver over the VLAN (PER-ENV port: :80 staging/prod) |
   | `TW2_GATEWAY_REDIS_URL` | `redis://10.0.0.<redis>:6379/4` | shared gateway counters, cache, and cross-node single-flight; use `rediss://` and credentials where required |
   | `POSTGRES_DSN` | (same DB as web/app) | the api_keys + usage tables |
   | `API_KEY_HMAC_SECRET` / `APPSERVER_JWT_SECRET` | (same as web/app per env) | keys + JWTs must verify identically |
   | `API_BASE_URL` | leave default (`http://127.0.0.1:8088/v1`) | MCP is co-located on this box |
   | `TW2_MCP_HOST` | `127.0.0.1` (or `10.0.0.<gw>` if nginx fronts MCP cross-box) | |

3. **`secrets.env` on the APP box** - repoint Tara at the new gateway:
   | var | value |
   |---|---|
   | `TW2_GATEWAY_URL` | `http://10.0.0.<gw>:8088/v1` |
   Then `systemctl restart tradewave-appserver` (Tara reads it at start).

4. **Firewall / VLAN** - allow: gateway box -> appserver `:80`, gateway box -> Postgres, gateway
   box -> redis; and app box -> gateway `:8088` (Tara). Keep all origin ports off the public net.

5. **Edge** - point the public `api-*` / `mcp-*` hostnames at the new box (Cloudflare tunnel
   ingress on the gateway box, or the web-box nginx upstream over the VLAN). All TW2 hosts are
   tunnels - never an A record.

6. **Stop the co-located units on the app box**: `systemctl disable --now tradewave-apiserver
   tradewave-mcpserver` (the gateway now lives on the new box).

7. **Verify**: on the gateway box `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088/v1/markets`
   with a key (expect 401 without, 200 with); from the app box confirm Tara still answers
   (`/chatbot/chat` narrates a real card); check the public `api.`/`mcp.` hostnames.

**Rollback**: re-enable the app-box units, set `TW2_GATEWAY_URL` back to loopback, repoint the
edge. Gateway Redis contains derived, expiring data and counters, not authoritative market
data, so there is no local data migration in either direction. Keep the same gateway Redis
during rollback so rate and quota counters remain continuous.

## What did NOT need changing

`TW2_APPSERVER_URL`, `TW2_GATEWAY_REDIS_URL`, and `TW2_GATEWAY_URL` are env-driven
(`apiserver/settings.py`, `config.py`). The unit files also parameterize the two bind values
(`TW2_APISERVER_BIND`, `TW2_MCP_HOST`/`TW2_MCP_PORT`). Defaults preserve the co-located
behavior, so the same code and units run in either topology.
