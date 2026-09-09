"""Exercise compatibility against the installed SDK, including successful dispatch."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip('mcp')
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcpserver.http_transport import McpHttpCompatibility


def payload(response):
    if 'text/event-stream' in response.headers.get('content-type', ''):
        return next(json.loads(line[5:]) for line in response.text.splitlines()
                    if line.startswith('data:') and line[5:].strip())
    return response.json()


def test_sdk_errors_ids_aliases_and_successful_dispatch():
    async def run():
        server = FastMCP('QA', stateless_http=True, streamable_http_path='/',
                         transport_security=TransportSecuritySettings(
                             allowed_hosts=['localhost'], allowed_origins=['http://localhost']))
        @server.tool()
        def echo(value: str) -> str:
            return value
        app = server.streamable_http_app()
        wrapped = McpHttpCompatibility(app)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=wrapped),
                                         base_url='http://localhost', headers={
                                             'Accept': 'application/json, text/event-stream',
                                             'Content-Type': 'application/json'}) as client:
                cases = [('{', -32700, None),
                         ({'jsonrpc': '2.0'}, -32600, None),
                         ({'jsonrpc': '2.0', 'id': 17}, -32600, 17),
                         ({'jsonrpc': '2.0', 'id': 'request-1', 'method': 'qa/unknown'}, -32601, 'request-1'),
                         ({'jsonrpc': '2.0', 'id': 0, 'method': 'qa/unknown'}, -32601, 0),
                         ({'jsonrpc': '2.0', 'id': True, 'method': 'tools/list'}, -32600, None),
                         ({'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {}}, -32602, 6)]
                for path in ['/', '/mcp', '/mcp/']:
                    for request, code, request_id in cases:
                        response = await client.post(path, content=request if isinstance(request, str) else json.dumps(request))
                        result = payload(response)
                        assert result['error']['code'] == code, result
                        assert result['id'] == request_id
                    initialized = payload(await client.post(path, json={'jsonrpc': '2.0', 'id': 10,
                        'method': 'initialize', 'params': {'protocolVersion': '2025-11-25',
                        'capabilities': {}, 'clientInfo': {'name': 'qa', 'version': '1'}}}))
                    assert initialized['id'] == 10 and 'result' in initialized
                    listing = payload(await client.post(path, json={'jsonrpc': '2.0', 'id': 11, 'method': 'tools/list'}))
                    assert listing['result']['tools'][0]['name'] == 'echo'
                    called = payload(await client.post(path, json={'jsonrpc': '2.0', 'id': 12,
                        'method': 'tools/call', 'params': {'name': 'echo', 'arguments': {'value': 'verified'}}}))
                    assert called['result']['content'][0]['text'] == 'verified'
                    notified = await client.post(path, json={'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                    assert notified.status_code == 202 and not notified.content
                rejected = await client.post('/', content='{', headers={'Host': 'untrusted.example'})
                assert rejected.status_code == 421
                discovery = await client.get('/.well-known/qa-missing')
                assert discovery.status_code == 404
    asyncio.run(run())


def test_auth_failure_is_never_rewritten():
    async def run():
        async def protected(scope, receive, send):
            await receive()
            await send({'type': 'http.response.start', 'status': 401,
                        'headers': [(b'www-authenticate', b'Bearer')]})
            await send({'type': 'http.response.body', 'body': b'authentication required'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=McpHttpCompatibility(protected)),
                                     base_url='http://localhost') as client:
            response = await client.post('/', content='{')
            assert response.status_code == 401
            assert response.headers['www-authenticate'] == 'Bearer'
            assert response.text == 'authentication required'
    asyncio.run(run())
