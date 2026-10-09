#!/usr/bin/env python3
"""Local stand-in for the production V2 ML scorer health payload.

Dev's live scorer reports provenance fields, so the morning homepage job
there keeps selecting picks and will not reproduce the production stall.
Point TW2_ML_SCORER_URL at this process to exercise the V2 freshness gate.

/select returns an empty pick list on purpose. A gate that opens does not
append a symbol to featured_history.json.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


# The production V2 /health body. No metadata, data_as_of, or
# context_data_complete. uptime_seconds is illustrative; the gate ignores it.
V2_HEALTH = {
    "feature_count": 59,
    "status": "ok",
    "tiers": ["10_30", "31_60", "61_90"],
    "uptime_seconds": 86400,
    "vix_cutoff": 35,
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.split("?", 1)[0] != "/health":
            self.send_error(404)
            return
        self._send(V2_HEALTH)

    def do_POST(self):  # noqa: N802
        if self.path.split("?", 1)[0] != "/select":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        print("select called", flush=True)
        self._send({
            "picks": [],
            "candidates_after_prefilter": 0,
            "candidates_scored": 0,
            "candidates_passing_win_prob": 0,
            "elapsed_ms": 1,
        })

    def log_message(self, fmt, *args):
        print("stub %s" % (fmt % args), flush=True)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("V2 scorer stub on http://127.0.0.1:8765", flush=True)
    print("health keys: %s" % ",".join(V2_HEALTH), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
