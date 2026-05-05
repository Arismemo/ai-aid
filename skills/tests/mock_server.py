"""Tiny stdlib HTTP server that mirrors enough of the ai-aid API for shell tests.
Logs every request to stdout so tests can assert what was sent.

Run: python3 mock_server.py PORT
"""
from __future__ import annotations
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Quiet default access log; we'll emit our own structured log
        pass

    def _emit(self, code: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def _log_call(self, method: str, body: dict | None):
        sys.stdout.write(json.dumps({
            "method": method,
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
        }, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def do_GET(self):
        self._log_call("GET", None)
        path = urlparse(self.path).path
        if path == "/health":
            self._emit(200, {"ok": True, "db": "ok", "events_buffered": 0})
            return
        if path.startswith("/api/requests/"):
            rid = path.rsplit("/", 1)[-1]
            self._emit(200, {"id": rid, "client_id": "alice", "answers": []})
            return
        if path == "/api/requests":
            self._emit(200, [])
            return
        self._emit(404, {"error": "not_found", "message": "no route"})

    def do_POST(self):
        body = self._read()
        self._log_call("POST", body)
        path = urlparse(self.path).path
        if path == "/api/requests":
            # Reject obvious bad input to test error paths
            if "goal" in body and not body.get("goal"):
                self._emit(400, {"error": "bad_request", "message": "missing goal"})
                return
            self._emit(201, {"id": "00000000-0000-0000-0000-000000000001",
                              "status": "open", "created_at": 1})
            return
        if path.endswith("/answers"):
            if "/cannot/" in path:
                self._emit(403, {"error": "forbidden", "message": "cannot solve own request"})
                return
            self._emit(201, {"id": "answer-1", "created_at": 2})
            return
        if path.endswith("/close"):
            self._emit(200, {"id": "abc", "status": "closed", "closed_at": 3})
            return
        self._emit(404, {"error": "not_found", "message": "no route"})

    def do_DELETE(self):
        self._log_call("DELETE", None)
        self.send_response(204)
        self.end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    sys.stderr.write(f"mock listening on {srv.server_address[1]}\n")
    sys.stderr.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
