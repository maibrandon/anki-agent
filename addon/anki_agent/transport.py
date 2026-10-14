"""Small loopback-only HTTP bridge; no browser access or arbitrary dispatch."""
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .errors import AgentError

MAX_BODY = 2_000_000


def make_server(port, token, execute):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("A token of at least 32 characters is required.")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_args):
            pass  # Never log tokens, queries, or note contents.

        def respond(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def fail(self, status, code, message):
            self.respond(status, {"ok": False, "error": {"code": code, "message": message}})

        def do_POST(self):
            if self.path != "/v1":
                return self.fail(404, "not_found", "Use /v1.")
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or self.headers.get("Origin"):
                return self.fail(403, "forbidden_origin", "Only local non-browser clients are allowed.")
            auth = self.headers.get("Authorization", "")
            if not hmac.compare_digest(auth.encode(), ("Bearer " + token).encode()):
                return self.fail(401, "unauthorized", "Missing or invalid token.")
            if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
                return self.fail(415, "invalid_content_type", "Use application/json with Content-Length.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.fail(413, "request_too_large", "Request body must be 1–2000000 bytes.")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict) or set(request) != {"operation", "params"} or not isinstance(request["operation"], str):
                    raise ValueError()
            except (ValueError, UnicodeError, TimeoutError):
                return self.fail(400, "invalid_request", "Invalid JSON request.")
            if not self.server.gate.acquire(blocking=False):
                return self.fail(503, "busy", "Another request is running; retry shortly.")
            try:
                result = execute(request["operation"], request["params"])
                self.respond(200, {"ok": True, "result": result})
            except AgentError as exc:
                self.respond(400, {"ok": False, "error": exc.as_dict()})
            except Exception:
                self.fail(500, "internal_error", "Anki operation failed. Check Anki's add-on diagnostics.")
            finally:
                self.server.gate.release()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.gate = threading.Lock()
    return server
