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


def _ump_level_ids(wordpress_url, ihch, uid, timeout):
    """Current (non-expired) level ids for a uid via UMP's apigate.php, hit
    DIRECTLY. (The ?ihc_action=api-gate query form is shadowed by TW1's static-/
    try_files and just returns home.html.) d['response'] is keyed by level id,
    each carrying an is_expired flag - we keep the non-expired ones (UMP's own
    expiry determination, not a re-derived SQL one)."""
    import requests
    base = wordpress_url if wordpress_url.endswith("/") else wordpress_url + "/"
    url = ("%swp-content/plugins/indeed-membership-pro/apigate.php"
           "?ihch=%s&action=get_user_levels&uid=%s" % (base, ihch, uid))
    resp = requests.get(url, timeout=timeout).json().get("response") or {}
    if not isinstance(resp, dict):
        return []
    return [str(lid) for lid, info in resp.items()
            if not (isinstance(info, dict) and info.get("is_expired"))]


def _tw1_config():
    """keystoreURL + wordpress_url from the box's OWN config.py - the same values
    the appserver/keyprovider use. No guessing: every TW1 box defines these."""
    for p in ("/home/flask", "/home/flask/appserver/appserver"):
        if p not in sys.path:
            sys.path.insert(0, p)
    import config  # the local TW1 config.py
    return getattr(config, "keystoreURL", None), getattr(config, "wordpress_url", None)


def export_users(cfg, out_path, keystore_url, ihch_static, wordpress_url, timeout):
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
                levels = _ump_level_ids(wordpress_url, key2, uid, timeout)
            except Exception:
                if not ihch_static:                              # maybe the key just rotated
                    key2, key_ts = _fetch_key2(keystore_url, timeout), time.time()
                try:
                    levels = _ump_level_ids(wordpress_url, key2, uid, timeout)
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
    su.add_argument("--wordpress-url", default=None,
                    help="override; default = config.wordpress_url from the box's config.py")
    su.add_argument("--keystore-url", default=None,
                    help="override; default = config.keystoreURL from the box's config.py")
    su.add_argument("--ihch",
                    help="static UMP api-gate key (override; expires if the key rotates mid-run)")
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
        keystore, wpurl = a.keystore_url, a.wordpress_url
        if not (keystore and wpurl):
            try:
                cfg_ks, cfg_wp = _tw1_config()
            except Exception as e:
                sys.exit("could not import the box's config.py for keystoreURL/wordpress_url "
                         "(%s); pass --keystore-url and --wordpress-url" % e)
            keystore = keystore or cfg_ks
            wpurl = wpurl or cfg_wp
        if not keystore or not wpurl:
            sys.exit("missing keystoreURL/wordpress_url (not in config.py, not passed)")
        print("using keystoreURL=%s wordpress_url=%s" % (keystore, wpurl), file=sys.stderr)
        export_users(_parse_wp_config(a.wp_config), os.path.join(a.out_dir, "tw1_users.jsonl"),
                     keystore, a.ihch, wpurl, a.timeout)
    else:
        export_redis(a.redis_host, a.redis_port, a.redis_db,
                     os.path.join(a.out_dir, "tw1_redis.jsonl"))


if __name__ == "__main__":
    main()
