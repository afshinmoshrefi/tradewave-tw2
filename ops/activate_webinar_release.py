#!/usr/bin/env python3
"""Guarded activation for the explicitly approved October 8 webinar release.

Only tradewave-web and one task-owned drop-in are changed. A rollback watchdog
stays armed until the manager records and validates all external release gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import socket
import subprocess
import sys
import time

import requests

if __package__:
    from .webinar_artifact import REPAIR_FILES, TESTED_REPAIR_SHA256
    from .validate_release_manifest import validate_manifest
else:
    from webinar_artifact import REPAIR_FILES, TESTED_REPAIR_SHA256
    from validate_release_manifest import validate_manifest


RELEASE = 'tw2-20261008-webinar-01'
STATE = Path('/var/lib/tradewave/release-state') / RELEASE
PACKAGE = Path('/home/tradewave-webinar-artifacts/20261008-baseline-c25ffd-repair-0ed01f')
DROPIN = Path('/etc/systemd/system/tradewave-web.service.d/60-webinar-release.conf')
BASELINE = 'c25ffd562dc3058ab41db5b07e9075dd841fb29b'
OVERLAY = '0ed01f68201623f4f2e55bd32827fca10479bb1a'
ARCHIVE = '4e40858ac16075c68799a0086a853a890aaffb5c7ef254e95a7fe04164eb7e5f'
FRONTEND_INDEX = 'cd190cbaf8b4771778ea6fdff05c15ec3b8ab02b0e0cad6b0730560b4460187f'
TIMER = 'tw2-webinar-rollback-' + RELEASE
PYTHON = '/home/flask/venv/bin/python'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*command):
    return subprocess.check_output(command, timeout=60, stderr=subprocess.PIPE).decode().strip()


def flask(*command):
    return run('su', '-s', '/bin/bash', 'flask', '-c', shlex.join(command))


def store(name, value):
    STATE.mkdir(mode=0o750, parents=True, exist_ok=True)
    account = pwd.getpwnam('flask')
    os.chown(STATE, 0, account.pw_gid)
    path = STATE / name
    temporary = STATE / ('.' + name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o640)
    os.chown(temporary, 0, account.pw_gid)
    os.replace(temporary, path)


def environment():
    host = socket.gethostname().lower()
    names = {'tw2-stage-web': 'staging', 'tw2-prod-web': 'prod'}
    if host not in names:
        raise ValueError('only the approved staging/production web hosts are supported')
    return names[host]


def unit_state():
    result = {}
    for key in ('MainPID', 'WorkingDirectory', 'DropInPaths', 'FragmentPath'):
        result[key] = run('systemctl', 'show', 'tradewave-web', '-p', key, '--value')
    result['process_cwd'] = str(Path('/proc/' + result['MainPID'] + '/cwd').resolve())
    result['frontend_pointer'] = str(Path('/home/flask/web-react/build').resolve())
    front = Path(result['frontend_pointer'])
    result['frontend_inventory'] = {p.relative_to(front).as_posix(): sha(p.read_bytes())
                                    for p in sorted(front.rglob('*')) if p.is_file()}
    result['frontend_index_sha256'] = sha((front / 'index.html').read_bytes())
    return result


def content(env):
    root = PACKAGE / 'payload'
    return ('[Service]\nWorkingDirectory=' + str(root / 'web')
            + '\nEnvironment=PYTHONPATH=' + str(root) + ':' + str(root / 'web')
            + '\nEnvironment=TW2_REACT_BUILD_DIR=/home/flask/web-react/build'
            + '\nEnvironment=PYTHONDONTWRITEBYTECODE=1'
            + '\nEnvironment=MAILERLITE_OUTBOUND_ENABLED=0'
            + '\nEnvironment=MAILERLITE_WEBINAR_REGISTRATION_ENABLED=' + ('1' if env == 'prod' else '0')
            + '\nEnvironmentFile=' + str(STATE / 'webinar.env') + '\n')


def environment_content(env):
    root = PACKAGE / 'payload'
    return ('PYTHONPATH=' + str(root) + ':' + str(root / 'web')
            + '\nTW2_REACT_BUILD_DIR=/home/flask/web-react/build'
            + '\nPYTHONDONTWRITEBYTECODE=1\nMAILERLITE_OUTBOUND_ENABLED=0'
            + '\nMAILERLITE_WEBINAR_REGISTRATION_ENABLED=' + ('1' if env == 'prod' else '0') + '\n')


def health():
    last = None
    for _ in range(30):
        try:
            response = requests.get('http://127.0.0.1:5500/healthz', timeout=3)
            if response.status_code == 200:
                body = response.json()
                if body.get('ok') is True or body.get('status') in ('ok', 'healthy'):
                    return body
            last = 'HTTP ' + str(response.status_code)
        except (requests.RequestException, ValueError) as error:
            last = type(error).__name__
        time.sleep(1)
    raise ValueError('web health did not recover: ' + str(last))


def validate_source(repo, manifest):
    controls = Path(__file__).resolve().parent
    schema = json.loads((controls / 'release_manifest.schema.json').read_text())
    errors = validate_manifest(manifest, schema)
    if errors:
        raise ValueError('release manifest fails validation: ' + '; '.join(errors))
    if manifest['release_id'] != RELEASE or manifest['release_kind'] != 'webinar-scoped':
        raise ValueError('unsupported release identity')
    release_sha = manifest['git']['release_sha']
    remote = flask('git', '-C', str(repo), 'ls-remote', 'origin', 'refs/heads/main').split()[0]
    if remote != release_sha or manifest['git']['main_locked_sha'] != release_sha:
        raise ValueError('canonical main moved or source is not locked')
    for name in REPAIR_FILES:
        # check_output.decode().strip() is unsuitable for exact file bytes.
        exact = subprocess.check_output(['su', '-s', '/bin/bash', 'flask', '-c',
            shlex.join(['git', '-C', str(repo), 'show', release_sha + ':' + name])], timeout=60)
        if sha(exact) != TESTED_REPAIR_SHA256[name]:
            raise ValueError('canonical repair bytes differ from approved scope')
    for name in ('activate_webinar_release.py', 'webinar_artifact.py',
                 'validate_release_manifest.py', 'release_manifest.schema.json'):
        exact = subprocess.check_output(['su', '-s', '/bin/bash', 'flask', '-c',
            shlex.join(['git', '-C', str(repo), 'show', release_sha + ':ops/' + name])], timeout=60)
        if sha(exact) != sha((controls / name).read_bytes()):
            raise ValueError('activation control differs from canonical source')
    # Verification performs Git access as flask and emits only hashes.
    flask(PYTHON, str(controls / 'webinar_artifact.py'), 'verify', '--repo', str(repo),
          '--baseline', BASELINE, '--overlay', OVERLAY, '--output', str(PACKAGE))
    if sha((PACKAGE / 'payload.tar.gz').read_bytes()) != ARCHIVE:
        raise ValueError('archive identity differs')


def verify_runtime(env, before):
    now = unit_state()
    expected = str(PACKAGE / 'payload/web')
    if now['WorkingDirectory'] != expected or now['process_cwd'] != expected:
        raise ValueError('live process does not use complete payload')
    if now['frontend_inventory'] != before['frontend_inventory'] or now['frontend_pointer'] != before['frontend_pointer']:
        raise ValueError('frontend changed during web-only activation')
    if DROPIN.read_text() != content(env):
        raise ValueError('task drop-in changed')
    if (STATE / 'webinar.env').read_text() != environment_content(env):
        raise ValueError('task environment changed')
    process_env = {}
    for item in Path('/proc/' + now['MainPID'] + '/environ').read_bytes().split(b'\0'):
        if b'=' in item:
            key, value = item.split(b'=', 1)
            if key in (b'MAILERLITE_OUTBOUND_ENABLED', b'MAILERLITE_WEBINAR_REGISTRATION_ENABLED', b'TW2_REACT_BUILD_DIR', b'PYTHONPATH'):
                process_env[key.decode()] = value.decode()
    if process_env != {'MAILERLITE_OUTBOUND_ENABLED': '0',
            'MAILERLITE_WEBINAR_REGISTRATION_ENABLED': '1' if env == 'prod' else '0',
            'TW2_REACT_BUILD_DIR': '/home/flask/web-react/build',
            'PYTHONPATH': str(PACKAGE / 'payload') + ':' + str(PACKAGE / 'payload/web')}:
        raise ValueError('effective process flags differ from approved scope')
    response = requests.post('http://127.0.0.1:5500/api/webinar/register', json={}, timeout=10)
    if response.status_code != 400 or response.json().get('message') != 'Enter your first name.':
        raise ValueError('non-sending live route validation failed')
    return {'at': datetime.now(timezone.utc).isoformat(), 'environment': env,
            'runtime': now, 'effective_flags': process_env, 'health': health(),
            'non_sending_live_route': {'status': 400, 'message': 'Enter your first name.', 'email_supplied': False},
            'real_subscriber_registration_submitted': False, 'frontend_preserved': True}


def rollback(env):
    before = json.loads((STATE / 'before.json').read_text())
    if DROPIN.exists():
        if DROPIN.read_text() != content(env):
            raise ValueError('rollback refuses changed task drop-in')
        DROPIN.unlink()
    run('systemctl', 'daemon-reload')
    run('systemctl', 'restart', 'tradewave-web')
    restored_health = health()
    restored = unit_state()
    for key in ('WorkingDirectory', 'process_cwd', 'frontend_pointer', 'frontend_inventory', 'DropInPaths'):
        if restored[key] != before[key]:
            raise ValueError('rollback restoration mismatch: ' + key)
    run('systemctl', 'stop', TIMER + '.timer')
    store('rollback-receipt.json', {'verified': True, 'runtime': restored, 'health': restored_health,
                                  'at': datetime.now(timezone.utc).isoformat()})
    return {'rollback_verified': True}


def activate(repo, manifest_path, env):
    manifest = json.loads(manifest_path.read_text())
    validate_source(repo, manifest)
    if manifest['status'] != ('prod_preflight' if env == 'prod' else 'staging_preflight'):
        raise ValueError('manifest is not in correct promotion phase')
    if env == 'staging' and manifest['approvals']['dev']['state'] != 'approved':
        raise ValueError('dev qualification not approved')
    if env == 'prod':
        for name in ('staging', 'production_snapshots', 'production'):
            if manifest['approvals'][name]['state'] != 'approved':
                raise ValueError('missing production prerequisite: ' + name)
        snapshots = manifest['environments']['prod']['snapshots']
        if datetime.now(timezone.utc).date().isoformat() != '2026-10-08' or not all(
            any(host in value and '2026-10-08' in value for value in snapshots)
            for host in ('194.113.195.141', '138.128.240.115')):
            raise ValueError('current-day web/app snapshot evidence missing')
    before = unit_state()
    if DROPIN.exists() or before['DropInPaths'] or before['WorkingDirectory'] != '/home/flask/web':
        raise ValueError('target drift or existing drop-in prevents narrow activation')
    if flask('git', '-C', '/home/flask', 'rev-parse', 'HEAD') != BASELINE or flask('git', '-C', '/home/flask', 'status', '--porcelain'):
        raise ValueError('target tracked source differs from recorded baseline')
    if before['frontend_index_sha256'] != FRONTEND_INDEX:
        raise ValueError('target frontend differs from qualified baseline')
    if DROPIN.parent.is_symlink() or PACKAGE.is_symlink():
        raise ValueError('unsafe activation path')
    if (STATE / 'before.json').exists():
        prior = json.loads((STATE / 'before.json').read_text())
        for key in ('WorkingDirectory', 'process_cwd', 'DropInPaths', 'frontend_pointer', 'frontend_inventory'):
            if prior[key] != before[key]:
                raise ValueError('existing rollback baseline differs: ' + key)
        # Rehearsal/retry may reuse the original immutable rollback baseline.
        # It never overwrites it or accepts an already activated task drop-in.
        before = prior
    else:
        store('before.json', before)
    (STATE / 'effective-unit.before').write_bytes(subprocess.check_output(['systemctl', 'cat', 'tradewave-web']))
    (STATE / 'effective-unit.before').chmod(0o600)
    run('systemd-run', '--collect', '--unit=' + TIMER, '--on-active=20m', PYTHON,
        str(Path(__file__).resolve()), 'rollback', '--repo', str(repo), '--manifest', str(manifest_path))
    try:
        envfile = STATE / 'webinar.env'
        envfile.write_text(environment_content(env))
        envfile.chmod(0o640)
        os.chown(envfile, 0, pwd.getpwnam('flask').pw_gid)
        DROPIN.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        DROPIN.write_text(content(env))
        DROPIN.chmod(0o644)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'restart', 'tradewave-web')
        health()
        result = verify_runtime(env, before)
        store('activation-receipt.json', result)
        return result
    except Exception:
        rollback(env)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('activate', 'verify', 'finalize', 'rollback'))
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('root is required only for the approved scoped service operation')
    env = environment()
    lock = STATE / 'activation.lock'
    STATE.mkdir(mode=0o750, parents=True, exist_ok=True)
    lock.mkdir()
    try:
        if args.action == 'activate':
            result = activate(args.repo, args.manifest, env)
        elif args.action == 'rollback':
            result = rollback(env)
        else:
            manifest = json.loads(args.manifest.read_text())
            validate_source(args.repo, manifest)
            result = verify_runtime(env, json.loads((STATE / 'before.json').read_text()))
            if args.action == 'finalize':
                if manifest['environments'][env]['state'] != 'verified':
                    raise ValueError('all external gates must pass before disarming rollback')
                run('systemctl', 'stop', TIMER + '.timer')
                store('final-receipt.json', result)
        print(json.dumps(result, indent=2))
    except Exception as error:
        print('ERROR: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        return 1
    finally:
        lock.rmdir()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
