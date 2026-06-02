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

The gateway is **stateless / shared-nothing**. It holds no data locally - its only state lives
off-box and is reached over the network:
- Postgres (`api_keys` + usage) via `POSTGRES_DSN`,
- Redis db4 (rate-limit + ML-quota counters) via `REDIS_HOST`/`REDIS_PORT`/`API_REDIS_DB`,
- the appserver (all market/seasonal data) via `TW2_APPSERVER_URL`.

So moving it = provision a box + repoint a handful of `secrets.env` values + move the edge.
(Stateless is also why you could later run several gateway instances behind a load balancer,
all sharing the same Postgres + redis.) Keep **MCP on the SAME box as the gateway** so
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
   | `REDIS_HOST` | `10.0.0.<redis>` | the shared db4 (rate/quota) - point at wherever it lives |
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
edge. Stateless gateway = no data to migrate either direction.

## What did NOT need changing

`TW2_APPSERVER_URL`, `REDIS_HOST`, `TW2_GATEWAY_URL` were already env-driven (`apiserver/settings.py`,
`config.py`). The only code change to enable this was parameterizing the two hardcoded-loopback
values in the unit files (`TW2_APISERVER_BIND`, `TW2_MCP_HOST`/`TW2_MCP_PORT`) - defaults preserve
the co-located behavior, so the units are identical to run in either topology.
