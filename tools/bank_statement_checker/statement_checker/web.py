"""Web UI: python -m statement_checker.web [--host 127.0.0.1] [--port 8000]

Uses only the standard library. The browser POSTs the raw PDF bytes to
/api/analyze; the file is written to a temp file, analyzed and deleted.
"""

import argparse
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from .analyzer import analyze

MAX_UPLOAD = 20 * 1024 * 1024
INDEX_HTML = (Path(__file__).parent / "web" / "index.html").read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "StatementChecker/1.0"

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML, "text/html; charset=utf-8")
        else:
            self._json(404, {"error": "Không tìm thấy"})

    def do_POST(self):
        if self.path != "/api/analyze":
            return self._json(404, {"error": "Không tìm thấy"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._json(400, {"error": "File rỗng"})
        if length > MAX_UPLOAD:
            return self._json(413, {"error": f"File quá lớn (tối đa {MAX_UPLOAD // 1024 // 1024} MB)"})
        data = self.rfile.read(length)
        name = os.path.basename(unquote(self.headers.get("X-Filename", "upload.pdf")))[:200]

        fd, tmp = tempfile.mkstemp(suffix=".pdf")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            report = analyze(tmp)
        except Exception as exc:
            return self._json(500, {"error": f"Lỗi khi phân tích: {exc}"})
        finally:
            os.unlink(tmp)
        report.path = name
        self._json(200, report.to_dict())

    def log_message(self, fmt, *args):
        # Do not log uploaded file names: statements are sensitive.
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Giao diện web kiểm tra sao kê ngân hàng")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mở trình duyệt tại http://{args.host}:{args.port}  (Ctrl+C để dừng)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
