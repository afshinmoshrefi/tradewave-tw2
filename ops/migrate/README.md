# TW1 -> TW2 user + data migration

Two migrations, one pipeline. Every script reads its DB / Stripe / Redis
coordinates **from the box it runs on**, so the same files run on staging then
prod with nothing hardcoded. **Test the whole thing on staging first.**

```
TW1 WEB  (WordPress/MySQL)              TW1 APPSERVER  (redis db2)
  tw1_export.py users                    tw1_export.py redis
        │  tw1_users.jsonl                      │  tw1_redis.jsonl
        ▼  (scp)                                │  (scp)
TW2 WEB  (Postgres + Stripe)                    │
  import_users.py                               │
   ├─ id_map.jsonl ──────────────┐ (scp)        │
   └─ payer_report.txt (review!)  │             │
                                  ▼             ▼
                         TW2 APP  (redis db2)
                           import_redis.py  (needs id_map.jsonl + tw1_redis.jsonl)
                             └─ db2 keys rewritten to the new uuids

TW1 prod is 2-tier: the users list lives in WordPress/MySQL on the WEB box;
the saved-data lives in the APPSERVER's local redis. So step 1 runs on TWO
different TW1 boxes (.151 dev co-locates them; prod does not).
```

- **Step 1a `tw1_export.py users`** runs on the **TW1 web** server. READ-ONLY. Roster + email from a trivial `wp_users` SELECT; the **level comes from UMP's api-gate** (`action=get_user_levels`, the authoritative source the appserver uses), so it needs `--keystore-url` (the keyprovider that hands out the rotating api-gate key2) and `--wordpress-url` that actually reaches WordPress - use the **same value the TW1 appserver uses** (`config.wordpress_url`); plain `localhost` hits the default nginx, not the WP vhost, so either use the real URL or pass `--host-header <WP server_name>` to route localhost to the vhost. ~1 api-gate call per user.
- **Step 1b `tw1_export.py redis`** runs on the **TW1 appserver** (its local redis db2). READ-ONLY (SCAN/GET only).
- **Step 2 `import_users.py`** runs on a TW2 **web** box (has `POSTGRES_DSN` + `STRIPE_SECRET_KEY`). Upserts the `users` table, links Stripe by email, emits `id_map.jsonl` + `payer_report.txt`.
- **Step 3 `import_redis.py`** runs on the TW2 **app** box (appserver redis db2). Rewrites the user-id in each key and loads it.

Copy `tw1_export.py` to BOTH TW1 boxes (web + appserver).

## Run it via the ops runner (preferred - matches the `ops/staging` convention)

These python scripts are wrapped by orchestrators you run the standard way:

```
sudo         /home/flask/ops/staging/run.sh prod migrate_users_from_tw1.sh   # Track A (users), DRY-RUN
sudo APPLY=1 /home/flask/ops/staging/run.sh prod migrate_users_from_tw1.sh   # commit
# migrate_redis_from_tw1.sh (Track B, saved data) - added next
```

First fill the `TGT_TW1_*` coordinates in `ops/staging/prod_target.env` (the `CONFIRM` placeholders). The orchestrator does the temp-key bridge to TW1, runs the export on TW1 web + the import on TW2 prod-web (live Stripe), and pulls `payer_report.txt` + `id_map.jsonl` back to `.176`. The per-box python commands below are what it wraps - run them by hand only for debugging.

## Safety properties
- **Dry-run by default.** Steps 2 and 3 write nothing until you pass `--apply`.
- **Read-only source.** Step 1 never writes to TW1.
- **Idempotent.** Re-running upserts by `lower(email)`; redis skips keys already present (unless `--overwrite`).
- **Never downgrade.** An existing user's tier is only ever raised, never lowered; `roles` and `workos_user_id` are never touched.
- **Loud on anomalies.** Tier mismatches, unmappable Stripe prices, paid-in-WP-but-no-active-sub, and unmapped redis ids are all reported, never silently resolved.
- **Review gate.** Eyeball `payer_report.txt` (only ~22 lines that matter) before `--apply`.

## Prereqs
- Use each box's venv python (`/home/flask/venv/bin/python`) so `redis`, `requests`, `stripe`, SQLAlchemy and `config.py` import.
- File moves (scp): `tw1_users.jsonl` (TW1 web -> TW2 web); `tw1_redis.jsonl` (TW1 appserver -> TW2 app); `id_map.jsonl` (TW2 web -> TW2 app). TW2 app ends up holding both `tw1_redis.jsonl` and `id_map.jsonl`.
- Optional but recommended for prod: a `legacy_price_map.json` `{ "price_xxx": "strategist", ... }` built from the Stripe **active-subscriptions** export (covers the ~14 no-metadata legacy prices). On staging test-mode Stripe it's usually unneeded.

## STAGING run (do this first)
```
# 1a) On the TW1 STAGING WEB box (read-only). Levels via UMP api-gate -> --wordpress-url must reach WP
#     (use the TW1 appserver's config.wordpress_url; or localhost + --host-header <WP server_name>):
/home/flask/venv/bin/python tw1_export.py users --wordpress-url "<TW1 appserver config.wordpress_url>" --keystore-url http://localhost:7777 --out-dir /tmp/mig
#    -> scp /tmp/mig/tw1_users.jsonl to TW2 stage-web
# 1b) On the TW1 STAGING APPSERVER (its local redis, read-only):
python3 tw1_export.py redis --redis-db 2 --out-dir /tmp/mig    # -> scp /tmp/mig/tw1_redis.jsonl to TW2 stage-app

# 2) On TW2 STAGE-WEB - dry-run, then review, then apply:
/home/flask/venv/bin/python import_users.py --in tw1_users.jsonl --out-dir /tmp/mig          # DRY-RUN
less /tmp/mig/payer_report.txt                                                                # review the paid/flagged users
/home/flask/venv/bin/python import_users.py --in tw1_users.jsonl --out-dir /tmp/mig --apply  # commit
#    -> scp /tmp/mig/id_map.jsonl to TW2 stage-app (next to tw1_redis.jsonl)

# 3) On TW2 STAGE-APP - dry-run, then apply:
/home/flask/venv/bin/python import_redis.py --redis-in tw1_redis.jsonl --id-map id_map.jsonl --scan-values   # DRY-RUN
/home/flask/venv/bin/python import_redis.py --redis-in tw1_redis.jsonl --id-map id_map.jsonl --apply         # load db2
```

### Verify (staging)
```
# Postgres (on stage-web): counts + a payer spot-check
/home/flask/venv/bin/python - <<'PY'
from web.models import Session, User
s=Session(); print("users:", s.query(User).count(),
  "paid:", s.query(User).filter(User.tier!='explorer').count(),
  "payers missing customer:", s.query(User).filter(User.tier!='explorer', User.stripe_customer_id.is_(None)).count())
PY
# Redis (on stage-app): a migrated user's portfolios exist under the new uuid
redis-cli -n 2 GET user_portfolios_<uuid-from-id_map>
```
Then log in to stage as a migrated user and confirm tier + watchlists/portfolios render in /app.

## PROD run
Identical, on the prod boxes, with `--legacy-price-map legacy_price_map.json` added to step 2, **after** the final user delta at cutover. Same dry-run -> review `payer_report.txt` -> `--apply` discipline.

## Rollback
The import is additive. To undo a bad staging run: `delete from users where workos_user_id is null and email <> '<owner>'` (only migration-seeded rows have a null workos id pre-cutover), and on the app box clear the loaded keys (they are namespaced by the new uuids in `id_map.jsonl`). Never blanket-`FLUSHDB` db2.

## What this does NOT do
- Create WorkOS identities or send any email - that's the credential step (the "set your password" relaunch email), handled separately.
- Touch DNS, the appserver, or the React build.
