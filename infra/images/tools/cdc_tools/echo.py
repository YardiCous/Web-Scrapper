"""Placeholder HTTP service (scorer, gateway, frontend) until the real image exists.

Logs each request (CloudEvent headers and a short body summary) and answers 200 with a JSON echo.
A JSON body containing "_force_error": true gets a 500, used to test the dead-letter path.
"""
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import SERVICE, log

PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/healthz":
            log("request", method="GET", path=self.path)
        self._reply(200, {"service": SERVICE, "placeholder": True, "path": self.path})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        ce = {k.lower(): v for k, v in self.headers.items() if k.lower().startswith("ce-")}
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        fail = isinstance(body, dict) and body.get("_force_error") is True
        log("request", method="POST", path=self.path, bytes=len(raw), cloudevent=ce,
            listing_id=body.get("listing_id") if isinstance(body, dict) else None, status=500 if fail else 200)
        if fail:
            self._reply(500, {"error": "forced"})
        else:
            self._reply(200, {"service": SERVICE, "placeholder": True, "received_bytes": len(raw)})

    def log_message(self, *_args):
        pass  # replaced by the JSON log line above


def run():
    server = ThreadingHTTPServer(("", PORT), Handler)
    # shutdown() must run outside the serving thread.
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    log("listening", port=PORT)
    server.serve_forever()
    log("stopped")
    return 0
