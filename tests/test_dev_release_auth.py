import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest

@pytest.fixture
def auth_module():
    path = Path(__file__).parents[1] / 'ops/dev_mcp_release_auth.py'
    spec = importlib.util.spec_from_file_location('dev_release_auth_tested', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('bad', [None, 'issuer', 'audience', 'expired', 'non-user'])
def test_real_signature_identity_checks_and_no_token_output(auth_module, monkeypatch, capsys, bad):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = dict(iss=auth_module.ISSUER, aud=auth_module.RESOURCE, sub='user_release_test', exp=int(time.time()) + 300)
    if bad == 'issuer': claims['iss'] = 'https://wrong.example'
    if bad == 'audience': claims['aud'] = 'https://mcp.tradewave.ai/'
    if bad == 'expired': claims['exp'] = int(time.time()) - 60
    if bad == 'non-user': claims['sub'] = 'client_service_not_user'
    access = jwt.encode(claims, key, algorithm='RS256')
    monkeypatch.setattr(jwt, 'PyJWKClient', lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key())))
    saved = []
    monkeypatch.setattr(auth_module, 'save', lambda name, value: saved.append((name, value.copy())))
    tokens = dict(access_token=access, refresh_token='private-refresh-fixture')
    if bad:
        with pytest.raises((jwt.InvalidTokenError, SystemExit)):
            auth_module.record_tokens(tokens)
        assert saved == []
    else:
        auth_module.record_tokens(tokens)
        assert saved[0][0] == 'tokens.json'
        assert saved[0][1]['verified_subject'] == 'user_release_test'
    output = capsys.readouterr().out
    assert access not in output and 'private-refresh-fixture' not in output

def test_saved_credentials_private_and_symlink_refused(auth_module, monkeypatch, tmp_path):
    monkeypatch.setattr(auth_module, 'AUTH_ROOT', tmp_path)
    auth_module.save('test.json', {'private': 'fixture'})
    assert (tmp_path / 'test.json').stat().st_mode & 0o777 == 0o600
    outside = tmp_path / 'outside.json'
    outside.write_text('unchanged')
    (tmp_path / 'linked.json').symlink_to(outside)
    with pytest.raises(SystemExit):
        auth_module.save('linked.json', {'private': 'fixture'})
    assert outside.read_text() == 'unchanged'
