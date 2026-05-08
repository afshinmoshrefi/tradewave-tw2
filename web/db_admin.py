#!/usr/bin/env python3
"""
TW2 web tier - small DB admin script.

Subcommands:

  hash-api-keys
    DEPRECATED. The plaintext users.api_key column has been dropped
    (alembic 5a3c1e2f4d6b). This subcommand now refuses to run and
    exits non-zero so any cron / runbook that still calls it surfaces
    a clear error instead of silently no-op'ing. The hash_api_key()
    helper below is preserved (tests + future seeding still need it).

The HMAC secret is read from API_KEY_HMAC_SECRET in the environment.
If unset, it falls back to APPSERVER_JWT_SECRET from /home/flask/config.py
(the spec allows this as a transition default, since the appserver/web
already share that secret).

Usage:
  (no operational subcommands at present; see deprecation note above)
"""
import argparse
import hashlib
import hmac
import os
import sys


def _maybe_load_secrets_env(path: str = '/etc/tradewave/secrets.env') -> None:
    """Lightweight KEY=VALUE loader for ad-hoc CLI runs (no shell sourcing).

    The systemd units pull /etc/tradewave/secrets.env via EnvironmentFile,
    but `sudo python db_admin.py …` strips the env. So we re-populate
    here, without overwriting anything the parent shell already set."""
    if not os.path.isfile(path):
        return
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                k = k.strip()
                v = v.strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ.setdefault(k, v)
    except PermissionError:
        pass


_maybe_load_secrets_env()

sys.path.insert(0, '/home/flask')
sys.path.insert(0, '/home/flask/web')

import config as tw2_config  # noqa: E402
# NOTE: User is intentionally NOT imported here. The plaintext api_key
# column was dropped in alembic 5a3c1e2f4d6b, so the previous backfill
# loop (filter(User.api_key.isnot(None))) would now raise at the ORM
# layer. Anything still needing the helper imports models lazily.
from models import Session  # noqa: E402  (kept so external callers of this module's Session re-export still work)
_ = Session  # silence unused-import linters


def _hmac_secret() -> bytes:
    explicit = os.environ.get('API_KEY_HMAC_SECRET')
    if explicit:
        return explicit.encode('utf-8')
    fallback = getattr(tw2_config, 'APPSERVER_JWT_SECRET', None)
    if not fallback:
        raise RuntimeError(
            "no HMAC secret available; set API_KEY_HMAC_SECRET in env "
            "or APPSERVER_JWT_SECRET in /home/flask/config.py"
        )
    return fallback.encode('utf-8')


def hash_api_key(plaintext: str, secret: bytes) -> str:
    """HMAC-SHA256 hex digest of an api_key plaintext."""
    return hmac.new(secret, plaintext.encode('utf-8'), hashlib.sha256).hexdigest()


def cmd_hash_api_keys(args) -> int:
    """Refuse to run: the plaintext column this used to read is gone."""
    sys.stderr.write(
        "hash-api-keys is deprecated: users.api_key was dropped in alembic "
        "5a3c1e2f4d6b. There is nothing to backfill from. If you need to "
        "issue a new service-account key, generate one client-side, hash it "
        "with hash_api_key() (using the API_KEY_HMAC_SECRET), and write only "
        "the hash to users.api_key_hash.\n"
    )
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('hash-api-keys', help='Backfill api_key_hash from api_key.')
    args = parser.parse_args()
    if args.cmd == 'hash-api-keys':
        return cmd_hash_api_keys(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == '__main__':
    sys.exit(main())
