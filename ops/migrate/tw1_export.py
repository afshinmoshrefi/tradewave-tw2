#!/usr/bin/env python3
"""
TW1 -> TW2 migration, step 1: EXPORT from a TW1 box (READ-ONLY).

Run this ON A TW1 BOX (staging first, then prod). It only issues SELECTs
(MySQL) and SCAN/GET/TYPE (Redis) - it never writes to TW1.

Two exports (the two migrations, source side):
  users  -> tw1_users.jsonl : one JSON object per WP user
                              (wp_user_id, email, registered_at, active_level_ids).
                              Roster + email come from wp_users (MySQL); the LEVEL
                              comes from UMP's api-gate - the authoritative source
                              the appserver itself uses (get_user_memberships_ump),
                              NOT a re-derived SQL query of wp_ihc_user_levels.
  redis  -> tw1_redis.jsonl : every user-scoped appserver db2 key + value
                              (portfolios / reports / watchlists).

MySQL creds + table prefix are read from the box's own wp-config.php; the UMP
api-gate key (key2) is fetched from the keyprovider and refreshed as it rotates.
The SAME script runs unchanged on staging and prod - nothing hardcoded. No
credentials or row values are printed; only counts.

Examples (one line each):
  python3 tw1_export.py users --keystore-url http://localhost:7777 --wordpress-url http://localhost/ --out-dir ./out
  python3 tw1_export.py redis --redis-db 2 --out-dir ./out
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# The only user-scoped keys in appserver redis db2 (verified in appserver.py).
# Deliberately excludes num_today_* (a daily rate-limit counter with a TTL).
USER_KEY_PATTERNS = [
    "user_portfolios_*",
    "user_reports_*",
    "user_watchlists_*",
    "user_watchlist_items_*",
]


def _parse_wp_config(path):
    with open(path, "r", errors="replace") as f:
        txt = f.read()

    def const(name):
        m = re.search(
            r"""define\(\s*['"]%s['"]\s*,\s*['"]([^'"]*)['"]""" % re.escape(name), txt
        )
        return m.group(1) if m else None

    m = re.search(r"""\$table_prefix\s*=\s*['"]([^'"]+)['"]""", txt)
    cfg = {
        "name": const("DB_NAME"),
        "user": const("DB_USER"),
        "password": const("DB_PASSWORD"),
        "host": const("DB_HOST") or "localhost",
        "prefix": (m.group(1) if m else "wp_"),
    }
    missing = [k for k in ("name", "user", "password") if not cfg[k]]
    if missing:
        sys.exit("could not parse %s from %s" % (", ".join(missing), path))
    return cfg


def _mysql_args(cfg):
    host, port, socket = cfg["host"], None, None
    if host.startswith(":"):
        rest = host[1:]
        port, host = (rest, "localhost") if rest.isdigit() else (None, None)
        if not port:
            socket = rest
    elif ":" in host:
        host, _, p = host.partition(":")
        port = p if p.isdigit() else None
        socket = None if p.isdigit() else p
    args = ["mysql", "-u", cfg["user"], "-N", "-B", "--raw",
            "--default-character-set=utf8mb4"]
    if socket:
        args += ["--socket", socket]
    else:
        args += ["-h", host or "localhost"]
        if port:
            args += ["-P", port]
    return args


def _fetch_key2(keystore_url, timeout):
    """The UMP api-gate key, exactly as the appserver's get_keys() obtains it."""
    import requests
    return requests.get(keystore_url, timeout=timeout).json()["key2"]


def _ump_level_ids(wordpress_url, ihch, uid, timeout, host_header=None):
    """Authoritative current level ids for a uid via UMP's api-gate - the same
    call the appserver uses (get_user_memberships_ump). d['response'] is keyed by
    the user's level ids; empty = admin / no membership -> []. host_header lets you
    hit localhost while routing to the WP vhost (nginx routes by Host)."""
    import requests
    url = "%s/?ihc_action=api-gate&ihch=%s&action=get_user_levels&uid=%s" % (
        wordpress_url.rstrip("/"), ihch, uid)
    headers = {"Host": host_header} if host_header else None
    d = requests.get(url, timeout=timeout, headers=headers).json()
    return [str(k) for k in (d.get("response") or {}).keys()]


def export_users(cfg, out_path, keystore_url, ihch_static, wordpress_url, timeout, host_header):
    if not (keystore_url or ihch_static):
        sys.exit("provide --keystore-url (preferred) or --ihch for the UMP api-gate key")

    # Roster + email ONLY from MySQL - no level logic here. UMP owns the level
    # (fetched below); WordPress owns the email, and the api-gate is keyed by uid.
    p = cfg["prefix"]
    sql = (
        "SELECT JSON_OBJECT("
        "'wp_user_id', u.ID,"
        "'email', LOWER(TRIM(u.user_email)),"
        "'registered_at', DATE_FORMAT(u.user_registered, '%Y-%m-%dT%H:%i:%sZ')"
        ") FROM {p}users u "
        "WHERE u.user_email IS NOT NULL AND u.user_email <> '' "
        "ORDER BY u.ID"
    ).format(p=p)
    env = dict(os.environ, MYSQL_PWD=cfg["password"])
    proc = subprocess.run(_mysql_args(cfg) + ["-e", sql, cfg["name"]],
                          env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("mysql failed (rc=%d): %s" % (proc.returncode, proc.stderr.strip()[:500]))
    roster = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]

    key2 = ihch_static or _fetch_key2(keystore_url, timeout)
    key_ts = time.time()
    n = err = paid = 0
    with open(out_path, "w") as out:
        for i, row in enumerate(roster, 1):
            if not ihch_static and time.time() - key_ts > 30:   # key2 rotates ~per minute
                key2, key_ts = _fetch_key2(keystore_url, timeout), time.time()
            uid = row["wp_user_id"]
            try:
                levels = _ump_level_ids(wordpress_url, key2, uid, timeout, host_header)
            except Exception:
                if not ihch_static:                              # maybe the key just rotated
                    key2, key_ts = _fetch_key2(keystore_url, timeout), time.time()
                try:
                    levels = _ump_level_ids(wordpress_url, key2, uid, timeout, host_header)
                except Exception as e:
                    levels, err = None, err + 1
                    print("  WARN uid=%s level fetch failed: %s" % (uid, str(e)[:120]),
                          file=sys.stderr)
            row["active_level_ids"] = levels
            out.write(json.dumps(row) + "\n")
            n += 1
            if levels and any(x != "1" for x in levels):
                paid += 1
            if i % 50 == 0:
                print("  ...%d/%d" % (i, len(roster)), file=sys.stderr)
    print("users exported: %d  (UMP level-fetch errors: %d, non-'1' level: %d)  -> %s"
          % (n, err, paid, out_path))


def export_redis(host, port, db, out_path):
    try:
        import redis
    except ImportError:
        sys.exit("python 'redis' not importable; run with the TW1 appserver venv python")
    r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    r.ping()
    n, skipped = 0, 0
    with open(out_path, "w") as out:
        for pat in USER_KEY_PATTERNS:
            for key in r.scan_iter(match=pat, count=500):
                if r.type(key) != "string":
                    skipped += 1
                    print("  WARN non-string key skipped: %s" % key, file=sys.stderr)
                    continue
                out.write(json.dumps({"key": key, "value": r.get(key)}) + "\n")
                n += 1
    print("redis db%d keys exported: %d  (skipped non-string: %d)  -> %s"
          % (db, n, skipped, out_path))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    su = sub.add_parser("users",
                        help="export WP users (roster from MySQL, levels from UMP api-gate) -> tw1_users.jsonl")
    su.add_argument("--wp-config", default="/var/www/html/wordpress/wp-config.php")
    su.add_argument("--wordpress-url", default="http://localhost/",
                    help="WP site root for the UMP api-gate (local on the TW1 web box)")
    su.add_argument("--keystore-url",
                    help="keyprovider URL returning {key1,key2}; key2 is the UMP api-gate key (preferred)")
    su.add_argument("--ihch",
                    help="static UMP api-gate key (override; expires if the key rotates mid-run)")
    su.add_argument("--host-header",
                    help="Host header to send to --wordpress-url (route localhost -> the WP vhost)")
    su.add_argument("--timeout", type=int, default=10)
    su.add_argument("--out-dir", default=".")
    sr = sub.add_parser("redis", help="export appserver db2 user data -> tw1_redis.jsonl")
    sr.add_argument("--redis-host", default="localhost")
    sr.add_argument("--redis-port", type=int, default=6379)
    sr.add_argument("--redis-db", type=int, default=2)
    sr.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    if a.cmd == "users":
        export_users(_parse_wp_config(a.wp_config), os.path.join(a.out_dir, "tw1_users.jsonl"),
                     a.keystore_url, a.ihch, a.wordpress_url, a.timeout, a.host_header)
    else:
        export_redis(a.redis_host, a.redis_port, a.redis_db,
                     os.path.join(a.out_dir, "tw1_redis.jsonl"))


if __name__ == "__main__":
    main()
