# Dev activation for TW-BUG-0001 + TW-BUG-0002, modeled on
# /var/tmp/trend-chart-stable-window-20260915/activate-dev.py (Codex, 2026-09-15).
from pathlib import Path
import datetime, hashlib, json, os, subprocess, urllib.request

root = Path('/home/tradewave-worktrees/claude-tw-bug-0001-0002-dev-20260915')
sha = '99bce08d5c6cbbac88dd8832466e00a85cdca700'
expected_main = '12b2849e'
artifact = Path('/home/flask/web-react/releases/build-' + sha)
frontend = Path('/home/flask/web-react/build')
previous = Path('/home/flask/web-react/build-previous')
backend = Path('/home/flask/.tw2-app-current')
lock = Path('/var/lib/tradewave/release-state/dev-activation.lock')
out = Path('/var/tmp/claude-tw-bug-0001-0002-20260915')

def run(args, **kwargs):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(args[:4]) + '\n' + result.stdout[-3000:])
    return result.stdout.strip()

def git(*args):
    return run(['git', '-C', str(root), *args])

def digest_tree(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}

def replace_link(path, target):
    temporary = path.with_name(path.name + '.claude-bug-0001-0002-' + str(os.getpid()))
    os.symlink(target, temporary)
    os.replace(temporary, path)

def http_bytes(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        assert response.status == 200
        return response.read()

assert os.geteuid() != 0, 'Run as flask'
assert not git('status', '--porcelain'), 'Candidate must be clean'
assert git('rev-parse', 'HEAD') == sha
assert (artifact / '.tradewave-source-sha').read_text().strip() == sha
assert digest_tree(artifact) == digest_tree(root / 'web-react/build'), 'Artifact copy differs'
assert frontend.is_symlink() and previous.is_symlink() and backend.is_symlink()

lock.mkdir()  # Atomic; refuse another owner.
owner = {'task': 'claude-tw-bug-0001-0002-20260915', 'executor': 'Claude Code (claude-opus-5)', 'session': 'ac415bed-b1cf-4689-be18-536911d44893', 'pid': os.getpid(), 'sha': sha, 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
(lock / 'owner.json').write_text(json.dumps(owner, indent=2))
receipt = {'candidate': sha, 'owner': owner, 'activated': False, 'frontend_verified': False, 'main_advanced': False}
old_front = os.readlink(frontend)
old_previous = os.readlink(previous)
old_backend = os.readlink(backend)
old_bundle = json.loads((frontend / 'asset-manifest.json').read_text())['files']['main.js']
old_bundle_hash = hashlib.sha256((frontend / old_bundle.removeprefix('/app/')).read_bytes()).hexdigest()
receipt['rollback'] = {'frontend': old_front, 'build_previous': old_previous, 'backend_unchanged': old_backend, 'bundle': old_bundle, 'bundle_sha256': old_bundle_hash}
backend_root = backend.resolve()
backend_hash_before = hashlib.sha256((backend_root / 'appserver/appserver/appserver.py').read_bytes()).hexdigest()

try:
    git('fetch', 'origin')
    assert git('rev-parse', 'origin/main').startswith(expected_main), 'Main moved; release lock and reintegrate'
    (out / 'activation.json').write_text(json.dumps(receipt, indent=2))
    replace_link(previous, old_front)
    replace_link(frontend, str(artifact))
    receipt['activated'] = True
    manifest = json.loads((artifact / 'asset-manifest.json').read_text())
    bundle = manifest['files']['main.js']
    assert http_bytes('http://127.0.0.1' + bundle) == (artifact / bundle.removeprefix('/app/')).read_bytes()
    assert bundle.split('/')[-1].encode() in http_bytes('http://127.0.0.1:5500/internal/capture/app'), 'Served app shell does not reference the candidate bundle'
    health = json.loads(http_bytes('http://127.0.0.1:5500/healthz'))
    assert health.get('frontend') == 'ok', 'Web frontend readiness failed'
    receipt['health'] = health
    # Live rendered checks against the served bundle (no --build): rotation + resize in parallel, then fresh landscape.
    procs = {m: subprocess.Popen(['node', str(out / 'verify-bugs.cjs'), '--mode', m, '--out', str(out / ('live-' + m))], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for m in ['rotate', 'resize']}
    outputs = {m: p.communicate(timeout=300)[0] for m, p in procs.items()}
    landscape = subprocess.run(['node', str(out / 'verify-bugs.cjs'), '--mode', 'landscape', '--out', str(out / 'live-landscape')], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    outputs['landscape'] = landscape.stdout
    (out / 'live-output.txt').write_text('\n'.join('== ' + m + '\n' + o for m, o in outputs.items()))
    print((out / 'live-output.txt').read_text(), flush=True)
    live = {}
    for m, code in [('rotate', procs['rotate'].returncode), ('resize', procs['resize'].returncode), ('landscape', landscape.returncode)]:
        evidence = json.loads((out / ('live-' + m) / 'receipt.json').read_text())
        live[m] = {'exit': code, 'complete': evidence['execution_complete'], 'cases': len(evidence['cases']), 'passed': sum(c['pass'] for c in evidence['cases']), 'bundles': sorted({str(c['state'].get('bundle')) for c in evidence['cases']})}
        assert code == 0 and evidence['execution_complete'], m + ' run did not complete'
        assert all(c['pass'] for c in evidence['cases']), m + ' live case failed'
        assert all(str(c['state'].get('bundle')).endswith(bundle) for c in evidence['cases']), m + ' did not exercise the candidate bundle'
    assert live['rotate']['cases'] == 14 and live['resize']['cases'] == 13 and live['landscape']['cases'] == 1
    receipt['live'] = live
    receipt['frontend_verified'] = True
    # Non-forced push rejects an independent main update automatically.
    receipt['push'] = git('push', 'origin', 'HEAD:main')
    receipt['main_advanced'] = True
    git('fetch', 'origin')
    receipt['main'] = git('rev-parse', 'origin/main')
    assert receipt['main'] == sha, 'Main changed after activation'
    assert not git('status', '--porcelain')
    assert frontend.resolve() == artifact and os.readlink(backend) == old_backend
    assert hashlib.sha256((backend_root / 'appserver/appserver/appserver.py').read_bytes()).hexdigest() == backend_hash_before
    receipt['artifact_file_hashes'] = digest_tree(artifact)
    receipt['backend_source_sha'] = run(['git', '-C', str(backend_root), 'rev-parse', 'HEAD'])
    receipt['backend_diff_from_candidate'] = run(['git', '-C', str(backend_root), 'diff', sha, '--stat', '--', 'web', 'appserver', 'apiserver', 'mcpserver', 'config.py', 'requirements.txt'])
    receipt['full_application_parity'] = not bool(receipt['backend_diff_from_candidate'])
    receipt['limitation'] = 'Existing uncommitted OppList4 sparse-data handling is preserved in the unchanged active backend; full application parity awaits its separate clean integration.'
    print(json.dumps({key: receipt[key] for key in ['candidate', 'frontend_verified', 'main_advanced', 'main', 'full_application_parity', 'backend_diff_from_candidate', 'live']}, indent=2), flush=True)
except BaseException as error:
    receipt['failure'] = str(error)
    if receipt['activated'] and not receipt['main_advanced']:
        replace_link(frontend, old_front)
        replace_link(previous, old_previous)
        restored = hashlib.sha256(http_bytes('http://127.0.0.1' + old_bundle)).hexdigest()
        assert restored == old_bundle_hash, 'ROLLBACK FAILED: original bundle does not match'
        receipt['rolled_back'] = True
    raise
finally:
    receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / 'activation.json').write_text(json.dumps(receipt, indent=2))
    assert json.loads((lock / 'owner.json').read_text())['pid'] == os.getpid()
    (lock / 'owner.json').unlink()
    lock.rmdir()
