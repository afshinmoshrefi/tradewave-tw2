"""One-release production SSO setup. Run on the TradeWave web host only."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from datetime import datetime, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SHA = 'c25ffd562dc3058ab41db5b07e9075dd841fb29b'
assert os.geteuid() == 0
assert '194.113.195.141' in subprocess.check_output(['hostname', '-I'], text=True)
assert subprocess.check_output(['sudo', '-u', 'flask', 'git', '-C', '/home/flask', 'rev-parse', 'HEAD'], text=True).strip() == SHA
source = Path('/home/flask/web/app.py').read_text()
assert '@app.route("/smn-dashboard/login"' in source
env = Path('/etc/tradewave/secrets.env')
original = env.read_bytes()
assert not any(line.strip().startswith((b'TW2_SMN_DASHBOARD_SSO_KEY=', b'TW2_SMN_DASHBOARD_URL=')) for line in original.splitlines())
backup = Path('/root/tradewave-snapshots/smn-sso-20261002')
if backup.exists():
    assert (backup / 'secrets.env.before').read_bytes() == original, 'Original configuration drift'
else:
    backup.mkdir(mode=0o700)
    shutil.copy2(env, backup / 'secrets.env.before')
    os.chown(backup / 'secrets.env.before', env.stat().st_uid, env.stat().st_gid)
keydir = Path('/etc/tradewave/smn-sso')
flask = pwd.getpwnam('flask')
key = keydir / 'private.pem'
public = keydir / 'public.pem'
if keydir.exists():
    private_key = serialization.load_pem_private_key(key.read_bytes(), password=None)
    assert public.read_bytes() == private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert key.stat().st_uid == 0 and key.stat().st_mode & 0o777 == 0o640
else:
    keydir.mkdir(mode=0o750)
    os.chown(keydir, 0, flask.pw_gid)
    private_key = Ed25519PrivateKey.generate()
    with os.fdopen(os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
        out.write(private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chown(key, 0, flask.pw_gid)
    os.chmod(key, 0o640)
    public.write_bytes(private_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    os.chmod(public, 0o644)
nginx = Path('/etc/nginx/sites-available/tw2-prod-web')
nginx_original = nginx.read_bytes()
assert b'/smn-dashboard/login' not in nginx_original
anchor = b'    location = /login     { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }'
assert nginx_original.count(anchor) == 1
nginx_changed = nginx_original.replace(anchor, anchor + b'\n    location = /smn-dashboard/login { proxy_pass http://tw2_web; include /etc/nginx/snippets/tw2-proxy-headers.conf; }')
assert not (backup / 'nginx.before').exists()
shutil.copy2(nginx, backup / 'nginx.before')
changed = original.rstrip(b'\n') + b'\nTW2_SMN_DASHBOARD_SSO_KEY=/etc/tradewave/smn-sso/private.pem\nTW2_SMN_DASHBOARD_URL=https://seasonalmarketnews.com/smn-dashboard\n'
try:
    subprocess.run(['sudo', '-u', 'flask', '/home/flask/venv/bin/python', '-c', 'from cryptography.hazmat.primitives.serialization import load_pem_private_key; k=load_pem_private_key(open("/etc/tradewave/smn-sso/private.pem","rb").read(),password=None); k.public_key().verify(k.sign(b"configuration-check"),b"configuration-check")'], check=True)
    env.write_bytes(changed)
    nginx.write_bytes(nginx_changed)
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['systemctl', 'restart', 'tradewave-web.service'], check=True)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', 'tradewave-web.service'], check=True)
    import time
    status = ''
    for _ in range(10):
        status = subprocess.check_output(['curl', '--max-time', '10', '-sS', '-o', '/dev/null', '-w', '%{http_code}', 'https://tradewave.ai/smn-dashboard/login'], text=True)
        if status in ('302', '303'):
            break
        time.sleep(1)
    assert status in ('302', '303'), status
    proof = dict(status='production_verified', scope='deployed route, configured signing key, unauthenticated redirect; real admin browser verification pending', dashboard_login_url='https://tradewave.ai/smn-dashboard/login', release_sha=SHA, verified_by='Codex under Afshin one-release authorization', source_route_verified=True, signing_key_readable_by_service=True, public_key_sha256=hashlib.sha256(public.read_bytes()).hexdigest(), checked_at=datetime.now(timezone.utc).isoformat(), unauthenticated_http_status=int(status))
    (backup / 'sso-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))
except BaseException:
    if nginx.read_bytes() == nginx_changed:
        shutil.copy2(backup / 'nginx.before', nginx)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
    if env.read_bytes() == changed:
        shutil.copy2(backup / 'secrets.env.before', env)
        st = (backup / 'secrets.env.before').stat()
        os.chown(env, st.st_uid, st.st_gid)
        subprocess.run(['systemctl', 'restart', 'tradewave-web.service'], check=False)
    raise
