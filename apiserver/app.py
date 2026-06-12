"""Gateway Flask app. Run on dev:
    cd /home/flask && ./venv-api/bin/python -m apiserver.app          # dev server
    ./venv-api/bin/gunicorn -b 127.0.0.1:8088 apiserver.app:app       # prod-style
Binds to loopback only - it is NEVER internet-facing directly; nginx + the cloudflared
tunnel front it (api-dev.trxstat.com -> :80 -> nginx -> this).
"""
import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .routes import v1
from .settings import CORS_ORIGINS

logging.basicConfig(level=logging.INFO)


def _cors_allow_origin(origin):
    """Return the Origin to echo back, or None to omit CORS (same-origin / disallowed)."""
    if not origin:
        return None
    if CORS_ORIGINS == ["*"]:
        return origin            # safe: bearer-token auth, no cookies/credentials
    return origin if origin in CORS_ORIGINS else None


def create_app():
    app = Flask(__name__)
    app.register_blueprint(v1, url_prefix="/v1")

    @app.after_request
    def _add_cors(resp):
        # The browser playground calls /v1 cross-origin. Flask's automatic OPTIONS response
        # passes through here too, so preflight gets these headers (and needs no auth).
        allow = _cors_allow_origin(request.headers.get("Origin"))
        if allow:
            resp.headers["Access-Control-Allow-Origin"] = allow
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resp.headers["Access-Control-Max-Age"] = "600"
            existing_vary = resp.headers.get("Vary")
            resp.headers["Vary"] = f"{existing_vary}, Origin" if existing_vary else "Origin"
        return resp

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "service": "tradewave-apiserver"}

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": {"code": "not_found", "message": "no such endpoint"}}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": {"code": "internal", "message": "internal error"}}), 500

    @app.errorhandler(HTTPException)
    def http_exception(e):
        # Uniform error envelope for EVERY other HTTP error (405, 400 from routing, 413,
        # ...). Without this, e.g. POST /v1/scan returned Flask's HTML 405 page - the one
        # break in an otherwise all-JSON contract. The specific 404/500 handlers above
        # still win (Flask prefers the most specific handler).
        code = (e.name or "error").lower().replace(" ", "_")   # 405 -> method_not_allowed
        resp = jsonify({"error": {"code": code, "message": e.description}})
        resp.status_code = e.code or 500
        if getattr(e, "valid_methods", None):                  # 405 carries Allow
            resp.headers["Allow"] = ", ".join(sorted(e.valid_methods))
        return resp

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8088, debug=True)
