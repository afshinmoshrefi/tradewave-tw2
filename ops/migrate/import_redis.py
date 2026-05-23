#!/usr/bin/env python3
"""
TW1 -> TW2 migration, step 3: REMAP + LOAD redis user data into TW2.

Run this ON THE TW2 APP BOX (staging first, then prod) - the appserver's
persistent redis (db2) lives there. It rewrites the wp-user-id segment of each
key to the TW2 uuid (from the users import) and loads it into db2.

  reads  : tw1_redis.jsonl  (from tw1_export.py redis)
           id_map.jsonl     (from import_users.py --apply)
  writes : TW2 redis db2 (only with --apply; dry-run by default)

Keys handled (id segment rewritten wp_id -> uuid):
  user_portfolios_<id>           user_reports_<id>
  user_watchlists_<id>           user_watchlist_items_<id>_<name>
Idempotent: a key already present in TW2 db2 is left alone unless --overwrite.
"""
import argparse
import json
import re
import sys

TRAILING = ("user_portfolios_", "user_reports_", "user_watchlists_")
ITEMS_RE = re.compile(r"^user_watchlist_items_(\d+)_(.+)$")


def remap_key(key, id2uuid):
    """Return (new_key, wp_id). new_key is None if unmapped (wp_id set) or the
    key is an unrecognized pattern (wp_id None)."""
    m = ITEMS_RE.match(key)
    if m:
        wp = m.group(1)
        if wp not in id2uuid:
            return None, wp
        return "user_watchlist_items_%s_%s" % (id2uuid[wp], m.group(2)), wp
    for pfx in TRAILING:
        if key.startswith(pfx):
            wp = key[len(pfx):]
            if not wp.isdigit():        # TW1 ids are integers
                return None, wp
            return (pfx + id2uuid[wp]) if wp in id2uuid else None, wp
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redis-in", default="tw1_redis.jsonl")
    ap.add_argument("--id-map", default="id_map.jsonl")
    ap.add_argument("--redis-host", default="localhost")
    ap.add_argument("--redis-port", type=int, default=6379)
    ap.add_argument("--redis-db", type=int, default=2)
    ap.add_argument("--overwrite", action="store_true",
                    help="overwrite keys already present in TW2 db2")
    ap.add_argument("--scan-values", action="store_true",
                    help="report (do not rewrite) any old wp id found inside a value")
    ap.add_argument("--apply", action="store_true", help="write to redis (default: dry-run)")
    a = ap.parse_args()

    id2uuid = {}
    with open(a.id_map) as f:
        for l in f:
            l = l.strip()
            if not l:
                continue
            m = json.loads(l)
            if m.get("uuid") and m.get("wp_user_id") is not None:
                id2uuid[str(m["wp_user_id"])] = m["uuid"]
    if not id2uuid:
        sys.exit("id_map has no uuid entries - run import_users.py --apply first")

    import redis
    r = redis.Redis(host=a.redis_host, port=a.redis_port, db=a.redis_db, decode_responses=True)
    r.ping()

    total = mapped = wrote = exists = unmapped = bad = valhits = 0
    unmapped_ids = set()
    with open(a.redis_in) as f:
        for l in f:
            l = l.strip()
            if not l:
                continue
            rec = json.loads(l)
            total += 1
            key, val = rec["key"], rec["value"]
            newkey, wp = remap_key(key, id2uuid)
            if newkey is None:
                if wp is None:
                    bad += 1
                    print("  UNRECOGNIZED key pattern: %s" % key, file=sys.stderr)
                else:
                    unmapped += 1
                    unmapped_ids.add(wp)
                continue
            mapped += 1
            if a.scan_values and isinstance(val, str) and re.search(r"\b%s\b" % re.escape(wp), val):
                valhits += 1
                print("  VALUE contains old id %s in key %s (review by hand)" % (wp, key),
                      file=sys.stderr)
            if not a.apply:
                continue
            if not a.overwrite and r.exists(newkey):
                exists += 1
                continue
            r.set(newkey, val)
            wrote += 1

    print("%s  total=%d mapped=%d wrote=%d existing-skipped=%d unmapped=%d unrecognized=%d value-id-hits=%d"
          % ("APPLIED" if a.apply else "DRY-RUN (nothing written)",
             total, mapped, wrote, exists, unmapped, bad, valhits))
    if unmapped_ids:
        print("  unmapped wp ids (no uuid in id_map; users not migrated?): %s"
              % ", ".join(sorted(unmapped_ids)[:50]))


if __name__ == "__main__":
    main()
