#!/usr/bin/env python3
"""Dev-only WorkOS PKCE login and private renewable release-test credentials."""
import argparse
import datetime as dt
import json
import base64
import hashlib
import hmac
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import os
from pathlib import Path
import stat
import sys
import time
import subprocess

import requests

AUTH_ROOT = Path('/var/lib/tradewave/release-auth/dev')
ISSUER = 'https://rapid-fish-71-staging.authkit.app'
RESOURCE = 'https://mcp-dev.trxstat.com/'

def private_root():
    if os.geteuid() != 0:
        raise SystemExit('Run on the dev host as root; no credentials are printed.')
    configured = {}
    for line in Path('/etc/tradewave/secrets.env').read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            configured[key.strip()] = value.strip().strip('"').strip("'")
    if configured.get('TW2_ENV') != 'dev':
        raise SystemExit('Refusing authentication setup outside configured dev environment')
    for key, value in configured.items():
        os.environ.setdefault(key, value)
    for p in [AUTH_ROOT.parent, AUTH_ROOT]:
        if p.is_symlink():
            raise SystemExit('Refusing symlink in credential storage path')
        p.mkdir(mode=0o700, exist_ok=True)
        os.chmod(p, 0o700)

def save(name, value):
    target = AUTH_ROOT / name
    if target.is_symlink():
        raise SystemExit('Refusing symlink credential file')
    temp = AUTH_ROOT / (name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, target)

def read(name):
    p = AUTH_ROOT / name
    s = p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o600:
        raise SystemExit('Credential file must be a root-owned regular file, mode 600')
    return json.loads(p.read_text())

def post(endpoint, data=None, payload=None):
    result = requests.post(ISSUER + endpoint, data=data, json=payload, timeout=30)
    try:
        body = result.json()
    except ValueError:
        raise SystemExit(f'Auth server returned HTTP {result.status_code} without JSON')
    if not result.ok:
        # Error classifications only. Never serialize token payloads or descriptions.
        error = body.get('error', body.get('code', 'unknown'))
        return None, str(error), result.status_code
    return body, None, result.status_code

def credential_fields(client):
    result = {'client_id': client['client_id']}
    if client.get('client_secret'):
        result['client_secret'] = client['client_secret']
    return result

def record_tokens(tokens):
    import jwt
    jwks = jwt.PyJWKClient(ISSUER + '/oauth2/jwks')
    signing_key = jwks.get_signing_key_from_jwt(tokens['access_token']).key
    claims = jwt.decode(tokens['access_token'], signing_key, algorithms=['RS256'],
                        audience=[RESOURCE, RESOURCE.rstrip('/')], issuer=ISSUER,
                        options={'require': ['exp', 'sub', 'iss', 'aud']})
    if not str(claims['sub']).startswith('user_'):
        raise SystemExit('OAuth subject is not a user; refusing service-client substitution')
    tokens['verified_expires_at'] = claims['exp']
    tokens['resource'] = RESOURCE
    tokens['verified_subject'] = claims['sub']
    tokens['stored_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    save('tokens.json', tokens)
    print(json.dumps({'oauth_signature_issuer_audience_verified': True,
                      'refresh_token_available': bool(tokens.get('refresh_token')),
                      'expires_at': claims['exp']}))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['register', 'authorize', 'callback', 'refresh', 'status', 'run-gate'])
    args = parser.parse_args()
    private_root()
    if args.action == 'register':
        if (AUTH_ROOT / 'client.json').exists():
            read('client.json')
            print('Existing dev release client retained')
            return
        client, error, status = post('/oauth2/register', payload={
            'client_name': 'TradeWave Dev Release Verification',
            'redirect_uris': ['http://127.0.0.1:8766/callback'],
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'], 'token_endpoint_auth_method': 'none',
            'scope': 'openid profile email offline_access',
        })
        if error:
            raise SystemExit(f'Dev client registration failed: HTTP {status}, {error}')
        save('client.json', client)
        print('Dev release OAuth client registered; credentials stored root-only on dev')
        return
    if args.action == 'status':
        status = {'client_registered': (AUTH_ROOT / 'client.json').exists(),
                  'tokens_stored': (AUTH_ROOT / 'tokens.json').exists()}
        if status['tokens_stored']:
            t = read('tokens.json')
            status.update(refresh_available=bool(t.get('refresh_token')), expires_at=t.get('verified_expires_at'))
        print(json.dumps(status))
        return
    client = read('client.json')
    if args.action == 'run-gate':
        subprocess.run([sys.executable, __file__, 'refresh'], check=True)
        tokens = read('tokens.json')
        api = read('api-key.json')
        env = dict(os.environ, TW2_TEST_OAUTH_TOKEN=tokens['access_token'], TW2_TEST_API_KEY=api['raw_key'])
        gate = Path(__file__).with_name('verify_mvp_release.py')
        result = subprocess.run([sys.executable, str(gate), '--api-base', 'https://api-dev.trxstat.com/v1',
                                 '--mcp-url', RESOURCE + 'mcp', '--concurrency', '50', '--requests', '200'], env=env)
        raise SystemExit(result.returncode)
    elif args.action == 'authorize':
        pending = dict(verifier=secrets.token_urlsafe(48), state=secrets.token_urlsafe(32),
                       started_at=time.time(), redirect_uri='http://127.0.0.1:8766/callback')
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pending['verifier'].encode()).digest()).decode().rstrip('=')
        save('pending.json', pending)
        query = dict(client_id=client['client_id'], response_type='code',
                     redirect_uri=pending['redirect_uri'], state=pending['state'],
                     code_challenge=challenge, code_challenge_method='S256',
                     scope='openid profile email offline_access', resource=RESOURCE)
        print(ISSUER + '/oauth2/authorize?' + urlencode(query))
    elif args.action == 'callback':
        pending = read('pending.json')
        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Authorization codes must never enter request logs.
            def do_GET(self):
                q = parse_qs(urlparse(self.path).query)
                if urlparse(self.path).path != '/callback':
                    self.send_error(404)
                    return
                if time.time() - pending['started_at'] > 1200 or not hmac.compare_digest(q.get('state', [''])[0], pending['state']):
                    self.send_error(400, 'Invalid or expired OAuth state')
                    return
                if 'code' not in q:
                    self.send_error(400, 'Authorization was not granted')
                    return
                data = credential_fields(client)
                data.update(grant_type='authorization_code', code=q['code'][0],
                            code_verifier=pending['verifier'], redirect_uri=pending['redirect_uri'])
                tokens, error, status = post('/oauth2/token', data=data)
                if error:
                    self.send_error(400, 'Token exchange failed')
                    print(f'Token exchange failed: HTTP {status}, {error}', flush=True)
                    self.server.failed = True
                    return
                try:
                    record_tokens(tokens)
                except Exception:
                    self.send_error(400, 'Token identity verification failed')
                    self.server.failed = True
                    print('Token signature, issuer, audience or user verification failed', flush=True)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                self.wfile.write(b'TradeWave dev release authentication is connected. You can close this tab. No production changes were made.')
                self.server.complete = True
        with HTTPServer(('127.0.0.1', 8766), Callback) as server:
            server.timeout = 10
            server.complete = False
            server.failed = False
            print('Dev OAuth callback ready on loopback port 8766', flush=True)
            while not server.complete and not server.failed and time.time() - pending['started_at'] < 1200:
                server.handle_request()
            if not server.complete:
                raise SystemExit('Dev OAuth sign-in not completed; no token retained')
    elif args.action == 'refresh':
        old = read('tokens.json')
        data = credential_fields(client)
        data.update(grant_type='refresh_token', refresh_token=old['refresh_token'])
        tokens, error, status = post('/oauth2/token', data=data)
        if error:
            raise SystemExit(f'Refresh failed: HTTP {status}, {error}; interactive sign-in may be required')
        tokens.setdefault('refresh_token', old['refresh_token'])
        record_tokens(tokens)

if __name__ == '__main__':
    try:
        main()
    except requests.RequestException:
        raise SystemExit('Authentication network request failed; no credential values logged')
