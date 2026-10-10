"""Exercise the actual preference routes with isolated storage and signed claims."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import jwt
import pytest
from flask import Flask, request, jsonify

@pytest.fixture
def client():
    source = Path(__file__).parents[1] / 'appserver/appserver/appserver.py'
    tree = ast.parse(source.read_text())
    names = {'get_securities_prefs', 'set_securities_prefs', 'get_published_lists'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    for n in nodes:
        n.decorator_list = []
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'unit-only-secret-at-least-32-bytes'
    storage = {}
    redis = SimpleNamespace(get=storage.get, set=lambda k,v: storage.__setitem__(k,v))
    ns = dict(app=app, request=request, jsonify=jsonify, jwt=jwt, json=json,
              redis_client2=redis, config=SimpleNamespace(admin_userids=[]))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
    for name in names:
        app.add_url_rule('/'+name, name, ns[name], methods=['POST' if name.startswith('set_') else 'GET'])
    token = jwt.encode(dict(user='regular-user', user_level='6', aud='tw2-appserver', iss='tw2-web'), app.config['SECRET_KEY'], algorithm='HS256')
    return app.test_client(), storage, '?token='+token

def test_new_and_legacy_preferences_default_to_no_hidden_lists(client):
    c, store, q = client
    for existing in [None, {'hidden_groups': ['FOREX ALL'], 'enabled_published': []}]:
        store.clear()
        if existing is not None:
            store['user_securities_prefs_regular-user'] = json.dumps(existing)
        prefs = c.get('/get_securities_prefs'+q).get_json()['securities_prefs']
        assert prefs['hidden_published'] == []
        assert prefs['enabled_published'] == []
        assert prefs['hidden_groups'] == (existing or {}).get('hidden_groups', [])

def test_explicit_hiding_survives_reload_and_is_user_scoped(client):
    c, store, q = client
    body = dict(hidden_groups=['FOREX ALL'], enabled_published=['Legacy'], hidden_published=['Midcaps'])
    assert c.post('/set_securities_prefs'+q, json=body).get_json()['securities_prefs'] == body
    assert c.get('/get_securities_prefs'+q).get_json()['securities_prefs'] == body
    assert list(store) == ['user_securities_prefs_regular-user']
    body['hidden_published'] = []
    c.post('/set_securities_prefs'+q, json=body)
    assert c.get('/get_securities_prefs'+q).get_json()['securities_prefs']['hidden_published'] == []

def test_catalog_still_enforces_enabled_and_access_levels(client):
    c, store, q = client
    store['tw_published_lists'] = json.dumps([
        dict(name='Visible', access_levels=['6'], enabled=True),
        dict(name='Disabled', access_levels=['6'], enabled=False),
        dict(name='Restricted', access_levels=['4'], enabled=True)])
    result = c.get('/get_published_lists'+q).get_json()
    assert [x['name'] for x in result['published_lists']] == ['Visible']
    assert result['is_admin'] is False
