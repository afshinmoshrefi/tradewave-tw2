#!/usr/bin/env python3
"""
TW1 -> TW2 migration, step 1: EXPORT from a TW1 box (READ-ONLY).

  users  -> tw1_users.jsonl : one JSON object per WP user
                              (wp_user_id, email, registered_at, active_level_ids).
                              EVERYTHING via UMP's api-gate (no MySQL, no wp-config) -
                              the same apigate.php + keystore the appserver uses:
                                list_levels        -> the level ids
                                get_level_users    -> the user roster per level
                                user_get_details   -> email
                                get_user_levels    -> that user's non-expired levels
  redis  -> tw1_redis.jsonl : every user-scoped appserver db2 key + value
                              (portfolios / reports / watchlists).

keystoreURL + wordpress_url default from the box's own config.py (override with
flags). key2 is fetched from the keystore and refreshed as it rotates. Because
`users` no longer touches MySQL, BOTH exports can run on the TW1 appserver. No
credentials or row values are printed; only counts.

Examples:
  python3 tw1_export.py users --out-dir /tmp/mig                         # config-driven
  python3 tw1_export.py users --wordpress-url https://tradewave.ai/ --out-dir /tmp/mig
  python3 tw1_export.py redis --redis-db 2 --out-dir /tmp/mig
"""
import argparse
import json
import os
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


def _tw1_config():
    """keystoreURL + wordpress_url from the box's OWN config.py - the same values
    the appserver/keyprovider use. No guessing: every TW1 box defines these."""
    for p in ("/home/flask", "/home/flask/appserver/appserver"):
        if p not in sys.path:
            sys.path.insert(0, p)
    import config  # the local TW1 config.py
    return getattr(config, "keystoreURL", None), getattr(config, "wordpress_url", None)


def _fetch_key2(keystore_url, timeout):
    """The UMP api-gate key2, exactly as the appserver's get_keys() obtains it."""
    import requests
    return requests.get(keystore_url, timeout=timeout).json()["key2"]


def _ump(wordpress_url, ihch, action, params, timeout):
    """Call UMP's apigate.php DIRECTLY (the ?ihc_action=api-gate query form is
    shadowed by TW1's static-/ try_files). Returns the 'response' payload, or
    raises if it's a string (e.g. 'Access Denied' = action not enabled in UMP)."""
    import requests
    base = wordpress_url if wordpress_url.endswith("/") else wordpress_url + "/"
    qs = "".join("&%s=%s" % (k, v) for k, v in params.items())
    url = ("%swp-content/plugins/indeed-membership-pro/apigate.php?ihch=%s&action=%s%s"
           % (base, ihch, action, qs))
    resp = requests.get(url, timeout=timeout).json().get("response")
    if isinstance(resp, str):
        raise RuntimeError("api '%s' -> %r (enable it in UMP -> Settings -> API)" % (action, resp))
    return resp


def export_users(out_path, keystore_url, ihch_static, wordpress_url, timeout):
    if not (keystore_url or ihch_static):
        sys.exit("need a keystore (config.keystoreURL / --keystore-url) or --ihch")

    state = {"k": ihch_static, "t": 0.0}

    def key2():
        if ihch_static:
            return ihch_static
        if not state["k"] or time.time() - state["t"] > 30:   # key2 rotates ~per minute
            state["k"], state["t"] = _fetch_key2(keystore_url, timeout), time.time()
        return state["k"]

    def call(action, params, _retry=True):
        try:
            return _ump(wordpress_url, key2(), action, params, timeout)
        except Exception:
            if _retry and not ihch_static:
                state["t"] = 0.0          # force a key refresh in case it rotated
                return call(action, params, _retry=False)
            raise

    # 1) the level ids
    levels = call("list_levels", {})
    level_ids = ([str(lvl.get("level_id")) for lvl in levels
                  if isinstance(lvl, dict) and lvl.get("level_id") is not None]
                 if isinstance(levels, list) else [])
    if not level_ids:
        sys.exit("list_levels returned nothing usable: %r" % (levels,))
    print("levels: %s" % ",".join(level_ids), file=sys.stderr)

    # 2) roster = union of users across every level
    uids = set()
    for lid in level_ids:
        rows = call("get_level_users", {"lid": lid})
        for it in (rows or []):
            if isinstance(it, dict) and it.get("user_id") is not None:
                uids.add(str(it["user_id"]))
    print("roster: %d users" % len(uids), file=sys.stderr)

    # 3) per user: email (user_get_details) + non-expired levels (get_user_levels)
    n = err = paid = 0
    ordered = sorted(uids, key=lambda x: int(x) if x.isdigit() else 0)
    with open(out_path, "w") as out:
        for i, uid in enumerate(ordered, 1):
            try:
                d = call("user_get_details", {"uid": uid})
                lv = call("get_user_levels", {"uid": uid})
            except Exception as e:
                err += 1
                print("  WARN uid=%s fetch failed: %s" % (uid, str(e)[:140]), file=sys.stderr)
                continue
            email = (d.get("user_email") or "").strip().lower() if isinstance(d, dict) else ""
            registered = d.get("user_registered") if isinstance(d, dict) else None
            active = ([str(k) for k, info in lv.items()
                       if isinstance(info, dict) and not info.get("is_expired")]
                      if isinstance(lv, dict) else [])
            out.write(json.dumps({"wp_user_id": uid, "email": email,
                                  "registered_at": registered,
                                  "active_level_ids": active}) + "\n")
            n += 1
            if any(x != "1" for x in active):
                paid += 1
            if i % 50 == 0:
                print("  ...%d/%d" % (i, len(ordered)), file=sys.stderr)
    print("users exported: %d  (errors: %d, non-'1' level: %d)  -> %s"
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
    su = sub.add_parser("users", help="export WP users via the UMP api-gate -> tw1_users.jsonl")
    su.add_argument("--wordpress-url", default=None,
                    help="override; default = config.wordpress_url from the box's config.py")
    su.add_argument("--keystore-url", default=None,
                    help="override; default = config.keystoreURL from the box's config.py")
    su.add_argument("--ihch", help="static UMP api-gate key (override; expires if it rotates)")
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
                sys.exit("could not import config.py for keystoreURL/wordpress_url (%s); "
                         "pass --keystore-url and --wordpress-url" % e)
            keystore = keystore or cfg_ks
            wpurl = wpurl or cfg_wp
        if not wpurl or not (keystore or a.ihch):
            sys.exit("missing wordpress_url and/or keystore (not in config.py, not passed)")
        print("using keystoreURL=%s wordpress_url=%s" % (keystore, wpurl), file=sys.stderr)
        try:
            export_users(os.path.join(a.out_dir, "tw1_users.jsonl"),
                         keystore, a.ihch, wpurl, a.timeout)
        except RuntimeError as e:
            sys.exit("export failed: %s" % e)
    else:
        export_redis(a.redis_host, a.redis_port, a.redis_db,
                     os.path.join(a.out_dir, "tw1_redis.jsonl"))


if __name__ == "__main__":
    main()
