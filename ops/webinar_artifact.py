#!/usr/bin/env python3
"""Build and verify an isolated webinar candidate; never activate services.

Every payload file comes from one committed baseline, except the four fixed
paths below. This candidate format does not waive TradeWave release policy.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile


REPAIR_FILES = (
    'config.py', 'web/email_utils.py', 'web/webinar_registration.py', 'webinar_schedule.py',
)
FORMAT = 'tradewave-webinar-candidate-v1'
TESTED_REPAIR_SHA256 = {
    'config.py': 'e6f8ca4426392f1982afc941d88df910088517484c2bdd31ef9aed2773b57cb1',
    'web/email_utils.py': '9e46162bc34193381265c3634fd4fd0675be1cdffeffc300509a5797397332b9',
    'web/webinar_registration.py': 'a1b617b8a70ebd4de25c6593a4a8f1a89d73f5c9b1c1b99f8dd4e70a6d90d1e5',
    'webinar_schedule.py': '9acf7522ff0c73b81dd0fb6a05d6381d855a2efe823e95e377dda02aaf26edc3',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def git(repo, *args, binary=False):
    result = subprocess.check_output(['git', '-C', str(repo), *args], timeout=60)
    return result if binary else result.decode().strip()


def commit(repo, value):
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('a full lowercase commit SHA is required')
    if git(repo, 'rev-parse', '--verify', value + '^{commit}') != value:
        raise ValueError('commit identity mismatch')
    return value


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(p in ('..', '.') for p in path.parts) or '\\' in name:
        raise ValueError('unsafe archive path')
    return str(path)


def archive_entries(data):
    entries = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for item in archive:
            name = safe_name(item.name)
            if item.isdir():
                continue
            if name in entries:
                raise ValueError('duplicate archive path')
            if item.issym():
                target = PurePosixPath(item.linkname)
                if target.is_absolute() or '\\' in item.linkname:
                    raise ValueError('unsafe symlink')
                depth = len(PurePosixPath(name).parent.parts)
                for part in target.parts:
                    depth += -1 if part == '..' else (0 if part == '.' else 1)
                    if depth < 0:
                        raise ValueError('escaping symlink')
                entries[name] = {'kind': 'symlink', 'data': item.linkname.encode(), 'mode': '120000'}
            elif item.isfile():
                entries[name] = {'kind': 'file', 'data': archive.extractfile(item).read(),
                                 'mode': '100755' if item.mode & 0o111 else '100644'}
            else:
                raise ValueError('unsupported archive member')
    return entries


def recipe(repo, baseline, overlay):
    commit(repo, baseline)
    commit(repo, overlay)
    subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', baseline, overlay],
                   check=True, timeout=60, stdout=subprocess.DEVNULL)
    base = archive_entries(git(repo, 'archive', '--format=tar', baseline, binary=True))
    patch = archive_entries(git(repo, 'archive', '--format=tar', overlay, *REPAIR_FILES, binary=True))
    if set(patch) != set(REPAIR_FILES) or not set(REPAIR_FILES).issubset(base):
        raise ValueError('repair path inventory mismatch')
    if any(v['kind'] != 'file' for v in patch.values()):
        raise ValueError('repair paths must be regular files')
    if any(digest(patch[name]['data']) != TESTED_REPAIR_SHA256[name] for name in REPAIR_FILES):
        raise ValueError('repair file bytes differ from the tested task scope')
    entries = {**base, **patch}
    inventory = [{'path': name, 'mode': value['mode'], 'kind': value['kind'],
                  'sha256': digest(value['data'])} for name, value in sorted(entries.items())]
    return entries, inventory


def payload_inventory(root):
    items = []
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            data, kind, mode = os.readlink(path).encode(), 'symlink', '120000'
        elif path.is_file():
            data, kind = path.read_bytes(), 'file'
            mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        elif path.is_dir():
            continue
        else:
            raise ValueError('unexpected payload object')
        items.append({'path': name, 'mode': mode, 'kind': kind, 'sha256': digest(data)})
    return sorted(items, key=lambda item: item['path'])


def write_archive(entries, output):
    with output.open('xb') as file:
        with gzip.GzipFile(filename='', mode='wb', fileobj=file, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as archive:
                for name, value in sorted(entries.items()):
                    info = tarfile.TarInfo(name)
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    if value['kind'] == 'symlink':
                        info.type, info.linkname, info.mode = tarfile.SYMTYPE, value['data'].decode(), 0o777
                        archive.addfile(info)
                    else:
                        info.size = len(value['data'])
                        info.mode = 0o755 if value['mode'] == '100755' else 0o644
                        archive.addfile(info, io.BytesIO(value['data']))


def materialize(repo, baseline, overlay, transport, output):
    """Transport exact existing archive bytes; verify before writing a payload."""
    transport, output = Path(transport).resolve(), Path(output).resolve()
    repo = Path(repo).resolve()
    if output == repo or repo in output.parents or output == Path('/home/flask') or Path('/home/flask') in output.parents:
        raise ValueError('output must be separate from operational and source checkouts')
    if output.exists():
        raise ValueError('immutable output already exists')
    _, expected = recipe(repo, baseline, overlay)
    manifest = json.loads((transport / 'manifest.json').read_text())
    archive_bytes = (transport / 'payload.tar.gz').read_bytes()
    entries = archive_entries(gzip.decompress(archive_bytes))
    inventory = [{'path': name, 'mode': value['mode'], 'kind': value['kind'],
                  'sha256': digest(value['data'])} for name, value in sorted(entries.items())]
    if inventory != expected or manifest.get('inventory') != expected:
        raise ValueError('transport differs from committed recipe')
    identity = {'format': FORMAT, 'purpose': 'candidate-only', 'approved_for_activation': False,
                'baseline_sha': baseline, 'overlay_sha': overlay, 'repair_files': list(REPAIR_FILES),
                'preserved_file_count': len(expected) - len(REPAIR_FILES),
                'payload_inventory_sha256': digest(canonical(expected)),
                'payload_archive_sha256': digest(archive_bytes)}
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError('transport manifest identity mismatch')
    output.mkdir(parents=True)
    payload = output / 'payload'
    payload.mkdir()
    for name, value in sorted(entries.items()):
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.resolve() != path.parent:
            raise ValueError('payload parent escapes through a symlink')
        if value['kind'] == 'symlink':
            path.symlink_to(value['data'].decode())
        else:
            path.write_bytes(value['data'])
            path.chmod(0o555 if value['mode'] == '100755' else 0o444)
    (output / 'payload.tar.gz').write_bytes(archive_bytes)
    (output / 'manifest.json').write_bytes((transport / 'manifest.json').read_bytes())
    verify(repo, baseline, overlay, output)
    for path in sorted(output.rglob('*'), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o555)
        elif not path.is_symlink():
            path.chmod(0o555 if path.stat().st_mode & 0o111 else 0o444)
    output.chmod(0o555)
    return manifest


def build(repo, baseline, overlay, output):
    repo, output = Path(repo).resolve(), Path(output).resolve()
    if output == repo or repo in output.parents or output == Path('/home/flask') or Path('/home/flask') in output.parents:
        raise ValueError('output must be separate from operational and source checkouts')
    if output.exists():
        raise ValueError('immutable output already exists')
    entries, inventory = recipe(repo, baseline, overlay)
    output.mkdir(parents=True)
    payload = output / 'payload'
    payload.mkdir()
    for name, value in sorted(entries.items()):
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.resolve() != path.parent or payload not in path.parent.resolve().parents and path.parent != payload:
            raise ValueError('payload parent escapes through a symlink')
        if value['kind'] == 'symlink':
            path.symlink_to(value['data'].decode())
        else:
            path.write_bytes(value['data'])
            path.chmod(0o555 if value['mode'] == '100755' else 0o444)
    archive = output / 'payload.tar.gz'
    write_archive(entries, archive)
    manifest = {
        'format': FORMAT, 'purpose': 'candidate-only', 'approved_for_activation': False,
        'baseline_sha': baseline, 'overlay_sha': overlay, 'repair_files': list(REPAIR_FILES),
        'preserved_file_count': len(entries) - len(REPAIR_FILES),
        'payload_inventory_sha256': digest(canonical(inventory)),
        'payload_archive_sha256': digest(archive.read_bytes()), 'inventory': inventory,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for path in sorted(payload.rglob('*'), reverse=True):
        if path.is_dir() and not path.is_symlink():
            path.chmod(0o555)
    payload.chmod(0o555)
    archive.chmod(0o444)
    (output / 'manifest.json').chmod(0o444)
    verify(repo, baseline, overlay, output)
    output.chmod(0o555)
    return manifest


def verify(repo, baseline, overlay, output):
    output = Path(output).resolve()
    manifest = json.loads((output / 'manifest.json').read_text())
    _, expected = recipe(repo, baseline, overlay)
    identity = {'format': FORMAT, 'purpose': 'candidate-only', 'approved_for_activation': False,
                'baseline_sha': baseline, 'overlay_sha': overlay, 'repair_files': list(REPAIR_FILES),
                'preserved_file_count': len(expected) - len(REPAIR_FILES),
                'payload_inventory_sha256': digest(canonical(expected)),
                'inventory': expected}
    if any(manifest.get(key) != value for key, value in identity.items()):
        raise ValueError('manifest differs from independently reconstructed Git recipe')
    if payload_inventory(output / 'payload') != expected:
        raise ValueError('payload differs from baseline plus exact repair paths')
    archive_bytes = (output / 'payload.tar.gz').read_bytes()
    archived = archive_entries(gzip.decompress(archive_bytes))
    archive_inventory = [{'path': name, 'mode': value['mode'], 'kind': value['kind'],
                          'sha256': digest(value['data'])} for name, value in sorted(archived.items())]
    if archive_inventory != expected or digest(archive_bytes) != manifest.get('payload_archive_sha256'):
        raise ValueError('archive differs from verified payload')
    return manifest


def activation_plan(output, environment):
    """Produce concrete review material, never execute it or mark it approved."""
    if environment not in ('staging', 'prod'):
        raise ValueError('unsupported environment')
    root = Path(output).resolve() / 'payload'
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', str(root)):
        raise ValueError('activation plan requires a simple absolute POSIX path')
    if not (root / 'web/app.py').is_file():
        raise ValueError('complete payload is required')
    return {
        'execution_allowed': False,
        'blockers': ['Exact integration into canonical main is required',
                     'Current release policy needs explicit scoped-baseline artifact support',
                     'Existing qualified manifest, runtime/browser gates and rollback requirements remain mandatory']
                    + (['Current-day production web/app snapshot facts and human execution remain required'] if environment == 'prod' else []),
        'dropin_path_after_gates': '/etc/systemd/system/tradewave-web.service.d/60-webinar-release.conf',
        'dropin_content_after_gates': '[Service]\nWorkingDirectory=' + str(root / 'web')
            + '\nEnvironment=PYTHONPATH=' + str(root) + ':' + str(root / 'web')
            + '\nEnvironment=TW2_REACT_BUILD_DIR=/home/flask/web-react/build'
            + '\nEnvironment=MAILERLITE_OUTBOUND_ENABLED=0'
            + '\nEnvironment=MAILERLITE_WEBINAR_REGISTRATION_ENABLED=' + ('1' if environment == 'prod' else '0') + '\n',
        'service_restart_after_gates': 'systemctl daemon-reload && systemctl restart tradewave-web',
        'unchanged': ['appserver source/services', 'database schema', 'React pointer/artifact', 'nginx', 'SMN jobs', 'shared secrets and lifecycle flag'],
        'rollback_after_gates': 'Preserve existing unit/drop-in state first. Restore that state, remove only the task-owned new drop-in if previously absent, daemon-reload and restart tradewave-web; verify prior health/source/frontend fingerprints. Do not change shared application pointers.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify', 'plan', 'materialize'))
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--overlay', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--environment', choices=('staging', 'prod'), default='staging')
    parser.add_argument('--transport', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'materialize':
            if args.transport is None:
                raise ValueError('--transport is required')
            manifest = materialize(args.repo, args.baseline, args.overlay, args.transport, args.output)
        elif args.action == 'build':
            manifest = build(args.repo, args.baseline, args.overlay, args.output)
        else:
            manifest = verify(args.repo, args.baseline, args.overlay, args.output)
        result = activation_plan(args.output, args.environment) if args.action == 'plan' else {
            key: manifest[key] for key in ('baseline_sha', 'overlay_sha', 'preserved_file_count', 'payload_inventory_sha256', 'payload_archive_sha256', 'approved_for_activation')
        }
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('ERROR: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
