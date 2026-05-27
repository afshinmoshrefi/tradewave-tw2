"""Gateway Flask app. Run on dev:
    cd /home/flask && ./venv-api/bin/python -m apiserver.app          # dev server
    ./venv-api/bin/gunicorn -b 127.0.0.1:8088 apiserver.app:app       # prod-style
Binds to loopback only - it is NEVER internet-facing directly; nginx + the cloudflared
tunnel front it (api-dev.trxstat.com -> :80 -> nginx -> this).
"""
import logging

from flask import Flask, jsonify

from .routes import v1

logging.basicConfig(level=logging.INFO)


def create_app():
    app = Flask(__name__)
    app.register_blueprint(v1, url_prefix="/v1")

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "service": "tradewave-apiserver"}

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": {"code": "not_found", "message": "no such endpoint"}}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": {"code": "internal", "message": "internal error"}}), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8088, debug=True)
