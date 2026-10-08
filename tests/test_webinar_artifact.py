"""Scope/integrity tests for the complete baseline-plus-webinar candidate."""
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from ops.webinar_artifact import (
    REPAIR_FILES, activation_plan, archive_entries, build, materialize, verify,
)
import ops.webinar_artifact as artifact_module

pytestmark = pytest.mark.unit


def command(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def thaw(root):
    for path in [root, *root.rglob('*')]:
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


@pytest.fixture
def source(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    command(repo, 'init', '-q')
    command(repo, 'config', 'user.email', 'unit@example.com')
    command(repo, 'config', 'user.name', 'Unit')
    for name in (*REPAIR_FILES, 'web/app.py', 'unchanged.txt'):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('baseline ' + name)
    command(repo, 'add', '.')
    command(repo, 'commit', '-qm', 'baseline')
    baseline = command(repo, 'rev-parse', 'HEAD')
    for name in REPAIR_FILES:
        (repo / name).write_text('repair ' + name)
    (repo / 'web/app.py').write_text('unrelated change must not ship')
    (repo / 'new-unrelated.py').write_text('unrelated new feature')
    command(repo, 'add', '.')
    command(repo, 'commit', '-qm', 'repair plus unrelated source')
    overlay = command(repo, 'rev-parse', 'HEAD')
    monkeypatch.setattr(artifact_module, 'TESTED_REPAIR_SHA256', {
        name: artifact_module.digest(('repair ' + name).encode()) for name in REPAIR_FILES
    })
    yield repo, baseline, overlay, tmp_path
    thaw(tmp_path)


def test_complete_artifact_preserves_every_nonrepair_file(source):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    result = build(repo, baseline, overlay, output)
    assert result['preserved_file_count'] == 2
    assert result['approved_for_activation'] is False
    assert (output / 'payload/web/app.py').read_text() == 'baseline web/app.py'
    assert not (output / 'payload/new-unrelated.py').exists()
    assert all((output / 'payload' / name).read_text() == 'repair ' + name for name in REPAIR_FILES)
    assert verify(repo, baseline, overlay, output) == result


@pytest.mark.parametrize('name', ['config.py', 'unchanged.txt'])
def test_content_tampering_is_rejected_for_repair_and_preserved_files(source, name):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    build(repo, baseline, overlay, output)
    path = output / 'payload' / name
    path.chmod(0o644)
    path.write_text('tampered')
    with pytest.raises(ValueError, match='payload differs'):
        verify(repo, baseline, overlay, output)


def test_extra_runtime_file_is_rejected(source):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    build(repo, baseline, overlay, output)
    (output / 'payload').chmod(0o755)
    (output / 'payload/injected.py').write_text('extra')
    with pytest.raises(ValueError, match='payload differs'):
        verify(repo, baseline, overlay, output)


def test_editable_manifest_cannot_expand_scope(source):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    build(repo, baseline, overlay, output)
    path = output / 'manifest.json'
    path.chmod(0o644)
    data = json.loads(path.read_text())
    data['repair_files'].append('web/app.py')
    data['approved_for_activation'] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='manifest differs'):
        verify(repo, baseline, overlay, output)


def test_immutable_build_refuses_to_overwrite_or_write_inside_checkout(source):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    build(repo, baseline, overlay, output)
    with pytest.raises(ValueError, match='already exists'):
        build(repo, baseline, overlay, output)
    with pytest.raises(ValueError, match='separate'):
        build(repo, baseline, overlay, repo / 'artifact')


def test_unreviewed_bytes_inside_an_allowed_path_are_rejected(source):
    repo, baseline, _overlay, root = source
    (repo / 'config.py').write_text('additional unreviewed change')
    command(repo, 'add', '.')
    command(repo, 'commit', '-qm', 'unreviewed config')
    with pytest.raises(ValueError, match='tested task scope'):
        build(repo, baseline, command(repo, 'rev-parse', 'HEAD'), root / 'artifact')


@pytest.mark.parametrize('name,target', [('../escape', None), ('link', '../../escape'), ('link', '/etc/passwd')])
def test_unsafe_archive_paths_and_links_are_rejected(name, target):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        info = tarfile.TarInfo(name)
        if target:
            info.type, info.linkname = tarfile.SYMTYPE, target
        archive.addfile(info)
    with pytest.raises(ValueError):
        archive_entries(buffer.getvalue())


def test_source_metadata_changes_do_not_rebuild_unchanged_runtime_bytes(source):
    repo, baseline, overlay, root = source
    first = build(repo, baseline, overlay, root / 'first')
    (repo / 'docs.txt').write_text('new orchestration/documentation')
    command(repo, 'add', '.')
    command(repo, 'commit', '-qm', 'documentation only')
    second = build(repo, baseline, command(repo, 'rev-parse', 'HEAD'), root / 'second')
    assert first['payload_archive_sha256'] == second['payload_archive_sha256']
    assert first['payload_inventory_sha256'] == second['payload_inventory_sha256']


def test_plan_preserves_gates_and_cannot_activate(source):
    repo, baseline, overlay, root = source
    output = root / 'artifact'
    build(repo, baseline, overlay, output)
    plan = activation_plan(output, 'prod')
    assert plan['execution_allowed'] is False
    assert any('snapshot' in reason for reason in plan['blockers'])
    assert 'MAILERLITE_OUTBOUND_ENABLED=0' in plan['dropin_content_after_gates']
    assert 'MAILERLITE_WEBINAR_REGISTRATION_ENABLED=1' in plan['dropin_content_after_gates']
    assert 'TW2_REACT_BUILD_DIR=/home/flask/web-react/build' in plan['dropin_content_after_gates']
    assert 'tradewave-appserver' not in plan['service_restart_after_gates']


def test_transport_reuses_exact_archive_and_checks_complete_payload(source):
    repo, baseline, overlay, root = source
    original = build(repo, baseline, overlay, root / 'dev')
    staged = materialize(repo, baseline, overlay, root / 'dev', root / 'stage')
    assert staged == original
    assert (root / 'dev/payload.tar.gz').read_bytes() == (root / 'stage/payload.tar.gz').read_bytes()
    assert verify(repo, baseline, overlay, root / 'stage') == original


def test_bad_transport_is_rejected_before_creating_destination(source):
    repo, baseline, overlay, root = source
    build(repo, baseline, overlay, root / 'dev')
    path = root / 'dev/manifest.json'
    path.chmod(0o644)
    data = json.loads(path.read_text())
    data['baseline_sha'] = overlay
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='identity mismatch'):
        materialize(repo, baseline, overlay, root / 'dev', root / 'stage')
    assert not (root / 'stage').exists()
