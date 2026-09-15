#!/usr/bin/env python3
"""Provision the authorized dev-only release-test API identity, never a customer."""
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlparse

from dev_mcp_release_auth import AUTH_ROOT, private_root, read, save

def main():
    private_root()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from apiserver import auth, db, settings
    if urlparse(settings.POSTGRES_DSN).hostname not in ('127.0.0.1', 'localhost'):
        raise SystemExit('Refusing non-loopback credential database')
    email = 'release-verification@internal.tradewave'
    name = 'dev-release-verification'
    if (AUTH_ROOT / 'api-key.json').exists():
        credential = read('api-key.json')
    else:
        credential = dict(raw_key='tw_test_' + secrets.token_urlsafe(32), purpose=name)
        save('api-key.json', credential)
    digest = auth.hash_key(credential['raw_key'])
    with db.cursor(commit=True) as cur:
        cur.execute('SELECT id, api_tier, roles FROM users WHERE email=%s', (email,))
        row = cur.fetchone()
        if row:
            if row['api_tier'] != 'business' or row['roles'] != ['service_account']:
                raise SystemExit('Existing release identity differs; no account changed')
            user_id = row['id']
        else:
            cur.execute("INSERT INTO users (email, api_tier, first_name, roles) VALUES (%s, 'business', %s, '[\"service_account\"]'::jsonb) RETURNING id", (email, 'Dev Release Verification'))
            user_id = cur.fetchone()['id']
        cur.execute('SELECT user_id, revoked_at FROM api_keys WHERE key_hash=%s', (digest,))
        key = cur.fetchone()
        if key:
            if key['user_id'] != user_id or key['revoked_at'] is not None:
                raise SystemExit('Stored test key is mismatched or revoked; no key reactivated')
        else:
            cur.execute('INSERT INTO api_keys (user_id, name, key_hash, prefix) VALUES (%s,%s,%s,%s)', (user_id, name, digest, credential['raw_key'][:12]))
    print('Dedicated dev test identity/key ready; customer accounts, Stripe and production unchanged')
    print('Uses existing Business-tier rate limits for the 200-request gate; no delegation or rate-limit bypass')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Dev test credential provisioning failed; inspect locally without printing credentials')
