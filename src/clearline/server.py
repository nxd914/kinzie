from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import OUTPUT_DIR, WEB_DIR
from .pipeline import run_pipeline


class ClearLineHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._write_json({"status": "ok"})
            return
        if parsed.path == "/api/reconciliation":
            artifacts = run_pipeline()
            payload = json.loads(artifacts.dashboard_path.read_text(encoding="utf-8"))
            self._write_json(payload)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8000), ClearLineHandler)
    print("ClearLine running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

