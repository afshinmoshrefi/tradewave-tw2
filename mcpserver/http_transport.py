"""Narrow JSON-RPC error compatibility for the installed MCP HTTP SDK.

All requests still pass through the SDK's auth, transport security, and dispatch.
Only completed SDK error replies for invalid input are normalized. Successful
requests, notifications, OAuth routes, and security failures are untouched.
"""

import json

from mcp.types import ClientRequest, JSONRPCMessage
from pydantic import ValidationError


def _request_methods():
    schema = ClientRequest.model_json_schema()
    return {
        definition["properties"]["method"]["const"]
        for definition in schema.get("$defs", {}).values()
        if "const" in definition.get("properties", {}).get("method", {})
    }


_METHODS = _request_methods()


def _input_error(body):
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return -32700, "Parse error", None
    request_id = value.get("id") if isinstance(value, dict) else None
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        request_id = None
        if isinstance(value, dict) and "id" in value:
            return -32600, "Invalid Request", None
    try:
        JSONRPCMessage.model_validate(value)
    except ValidationError:
        return -32600, "Invalid Request", request_id
    if isinstance(value, dict) and "id" in value and "method" in value:
        if value["method"] not in _METHODS:
            return -32601, "Method not found", request_id
    return None


def _has_rpc_error(body, content_type):
    try:
        if "text/event-stream" in content_type:
            messages = [json.loads(line[5:].strip()) for line in body.decode().splitlines()
                        if line.startswith("data:") and line[5:].strip()]
        else:
            messages = [json.loads(body)]
    except (ValueError, UnicodeDecodeError):
        return False
    return any(isinstance(message, dict) and isinstance(message.get("error"), dict)
               and message["error"].get("code") in {-32600, -32602, -32700}
               for message in messages)


class McpHttpCompatibility:
    """Keep root and legacy /mcp aliases, and repair SDK error classifications."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") in ("/mcp", "/mcp/"):
            scope = {**scope, "path": "/", "raw_path": b"/"}
        if scope.get("path") != "/" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)

        body = bytearray()
        problem = None
        response_start = None
        response_parts = []

        async def observe_receive():
            nonlocal problem
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    problem = _input_error(body)
                    body.clear()
            return message

        async def normalize_send(message):
            nonlocal response_start
            if message["type"] == "http.response.start":
                if problem and message["status"] in (200, 202, 400):
                    response_start = message
                    return
            elif message["type"] == "http.response.body" and response_start:
                response_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                response_body = b"".join(response_parts)
                headers = response_start.get("headers", [])
                content_type = dict(headers).get(b"content-type", b"").decode()
                if (_has_rpc_error(response_body, content_type)
                        or (response_start['status'] == 202 and problem[0] == -32600)):
                    code, reason, request_id = problem
                    response_body = json.dumps({"jsonrpc": "2.0", "id": request_id,
                                                "error": {"code": code, "message": reason}}).encode()
                    headers = [(key, value) for key, value in headers
                               if key.lower() not in (b"content-type", b"content-length")]
                    headers += [(b"content-type", b"application/json"),
                                (b"content-length", str(len(response_body)).encode())]
                    response_start = {**response_start, "status": 400, "headers": headers}
                await send(response_start)
                await send({"type": "http.response.body", "body": response_body})
                return
            await send(message)

        await self.app(scope, observe_receive, normalize_send)
