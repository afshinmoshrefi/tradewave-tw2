"""The approved one-release exception must not broaden ordinary release gates."""
import json
import importlib.util
from pathlib import Path

import pytest

from ops import activate_webinar_release as activate

fixture_spec = importlib.util.spec_from_file_location('release_fixture', Path(__file__).with_name('test_validate_release_manifest.py'))
fixture_module = importlib.util.module_from_spec(fixture_spec)
fixture_spec.loader.exec_module(fixture_module)
manifest, validator, SCHEMA, SHA, DIGEST = (
    getattr(fixture_module, name) for name in ('manifest', 'validator', 'SCHEMA', 'SHA', 'DIGEST')
)

pytestmark = pytest.mark.unit


def scoped():
    value = manifest()
    scope = {
        'baseline_sha': activate.BASELINE, 'overlay_sha': activate.OVERLAY,
        'archive_sha256': activate.ARCHIVE,
        'inventory_sha256': '4029a3514beeabf83ab736c755ae843a967aa59759671bcd7364547b763b4a29',
        'repair_files': list(activate.REPAIR_FILES),
        'approval_event': 'Sentinel_de3245e3870481919c42ac162704ea57',
        'approved_at': '2026-10-08T16:08:07Z',
        'qualification_mode': 'isolated-dev-then-live-staging',
        'executor': 'Codex explicitly designated webinar-only operator',
        'global_outbound_enabled': False,
    }
    value['release_kind'] = 'webinar-scoped'
    value['git']['release_sha'] = SHA
    value['artifacts'].update(scoped_webinar=scope, backend_fingerprint=scope['inventory_sha256'],
        frontend=[{'path': 'index.html', 'sha256': DIGEST, 'source_sha': activate.BASELINE}])
    value['artifacts']['manifest_sha256'] = validator.composite_release_hash(value)
    value['dev_coordination'].update(state='isolated', release_sha=SHA, evidence=['isolated real runtime'])
    return value


def test_specific_scope_and_true_preserved_frontend_provenance_are_valid():
    assert validator.validate_manifest(scoped(), SCHEMA) == []


@pytest.mark.parametrize('field', ['baseline_sha', 'archive_sha256', 'repair_files', 'approval_event', 'global_outbound_enabled'])
def test_scope_identity_and_permission_cannot_be_broadened(field):
    value = scoped()
    replacements = {'baseline_sha': SHA, 'archive_sha256': DIGEST,
        'repair_files': list(activate.REPAIR_FILES) + ['web/app.py'],
        'approval_event': 'unapproved', 'global_outbound_enabled': True}
    value['artifacts']['scoped_webinar'][field] = replacements[field]
    value['artifacts']['manifest_sha256'] = validator.composite_release_hash(value)
    assert validator.validate_manifest(value, SCHEMA)


def test_ordinary_release_cannot_use_scoped_frontend_or_isolated_coordination():
    value = scoped()
    value['release_kind'] = 'hotfix'
    assert validator.validate_manifest(value, SCHEMA)
    del value['artifacts']['scoped_webinar']
    value['dev_coordination']['state'] = 'not_started'
    value['artifacts']['manifest_sha256'] = validator.composite_release_hash(value)
    assert any('source_sha' in error for error in validator.semantic_errors(value))


def test_scoped_identity_is_included_in_approval_hash():
    value = scoped()
    before = validator.composite_release_hash(value)
    value['artifacts']['scoped_webinar']['global_outbound_enabled'] = True
    assert validator.composite_release_hash(value) != before


def test_scope_does_not_bypass_main_lock_or_production_approval():
    value = scoped()
    value['status'] = 'prod_preflight'
    errors = validator.validate_manifest(value, SCHEMA)
    assert any('main_locked_sha' in error for error in errors)
    assert any('production approval' in error for error in errors)


def test_dropin_changes_only_web_configuration_and_keeps_global_writes_off():
    prod = activate.content('prod')
    assert 'MAILERLITE_OUTBOUND_ENABLED=0' in prod
    assert 'MAILERLITE_WEBINAR_REGISTRATION_ENABLED=1' in prod
    assert 'MAILERLITE_WEBINAR_REGISTRATION_ENABLED=0' in activate.content('staging')
    assert 'TW2_REACT_BUILD_DIR=/home/flask/web-react/build' in prod
    assert 'appserver' not in prod
    assert 'EnvironmentFile=' + str(activate.STATE / 'webinar.env') in prod
    assert 'MAILERLITE_OUTBOUND_ENABLED=0' in activate.environment_content('prod')
    assert 'MAILERLITE_WEBINAR_REGISTRATION_ENABLED=1' in activate.environment_content('prod')


def test_activation_rejects_unapproved_host(monkeypatch):
    monkeypatch.setattr(activate.socket, 'gethostname', lambda: 'other-host')
    with pytest.raises(ValueError, match='approved'):
        activate.environment()


def test_rollback_never_removes_a_dropin_changed_by_another_task(tmp_path, monkeypatch):
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'before.json').write_text(json.dumps({}))
    dropin = tmp_path / '60-webinar-release.conf'
    dropin.write_text('different task')
    monkeypatch.setattr(activate, 'STATE', state)
    monkeypatch.setattr(activate, 'DROPIN', dropin)
    commands = []
    monkeypatch.setattr(activate, 'run', lambda *args: commands.append(args))
    with pytest.raises(ValueError, match='refuses changed'):
        activate.rollback('prod')
    assert dropin.read_text() == 'different task'
    assert commands == []
