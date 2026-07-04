#!/usr/bin/env python3
"""PathPilot UI server — serves the custom frontend and proxies ADK API calls.

Usage:
  1. Start the ADK backend:   adk web src/pathpilot
  2. Start this proxy:        python ui/serve.py
  3. Open browser:            http://localhost:3000
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import http.client
import os

PORT     = 3000
ADK_HOST = "localhost"
ADK_PORT = 8000
UI_DIR   = os.path.dirname(os.path.abspath(__file__))

MIME = {
    "html": "text/html; charset=utf-8",
    "js":   "application/javascript",
    "css":  "text/css",
    "ico":  "image/x-icon",
    "png":  "image/png",
    "svg":  "image/svg+xml",
}

API_PREFIXES = ("/apps/", "/run_sse", "/version", "/list-apps", "/dev/")


class Handler(BaseHTTPRequestHandler):

    def _is_api(self):
        return any(self.path.startswith(p) for p in API_PREFIXES)

    # ── Static files ──────────────────────────────────────────────────────────
    def do_GET(self):
        if self._is_api():
            self._proxy()
            return
        path = self.path.split("?")[0].lstrip("/")
        if not path:
            path = "index.html"
        filepath = os.path.join(UI_DIR, path)
        if not os.path.isfile(filepath):
            self.send_error(404)
            return
        ext = path.rsplit(".", 1)[-1] if "." in path else ""
        ct  = MIME.get(ext, "application/octet-stream")
        with open(filepath, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    # ── Proxy ─────────────────────────────────────────────────────────────────
    def do_POST(self):   self._proxy()
    def do_DELETE(self): self._proxy()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")

    def _proxy(self):
        length = int(self.headers.get("content-length", 0))
        body   = self.rfile.read(length) if length else None
        hdrs   = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "keep-alive", "content-length")
        }
        if body:
            hdrs["content-length"] = str(len(body))

        conn = http.client.HTTPConnection(ADK_HOST, ADK_PORT, timeout=120)
        try:
            conn.request(self.command, self.path, body=body, headers=hdrs)
            resp = conn.getresponse()

            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in ("transfer-encoding", "connection", "keep-alive"):
                    continue
                self.send_header(k, v)
            self._cors_headers()
            self.end_headers()

            # Stream chunks — critical for SSE to forward events as they arrive
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
        except Exception as e:
            try:
                self.send_error(502, f"ADK backend unavailable: {e}")
            except Exception:
                pass
        finally:
            conn.close()

    def log_message(self, fmt, *args):
        pass  # keep terminal clean


if __name__ == "__main__":
    print(f"\n  PathPilot UI  →  http://localhost:{PORT}")
    print(f"  ADK backend   →  http://{ADK_HOST}:{ADK_PORT}")
    print(f"  Stop with Ctrl+C\n")
    with ThreadingHTTPServer(("", PORT), Handler) as srv:
        srv.serve_forever()
