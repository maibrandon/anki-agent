import json
import threading
import urllib.request
import urllib.error
import pytest
from anki_agent.transport import make_server
from anki_agent_mcp.client import BridgeClient, BridgeError


@pytest.fixture
def bridge(tmp_path):
    calls = []
    def execute(op, params):
        calls.append(op)
        return {"connected": True}
    server = make_server(0, "x" * 40, execute)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "connection.json"
    path.write_text(json.dumps({"port": server.server_port, "token": "x" * 40}))
    yield server, path, calls
    server.shutdown()
    server.server_close()
    thread.join()


def test_authenticated_client(bridge):
    _, path, calls = bridge
    assert BridgeClient(str(path)).call("status")["connected"]
    assert calls == ["status"]


@pytest.mark.parametrize("override,code", [
    ({"Authorization": "Bearer wrong"}, 401),
    ({"Origin": "https://evil.example"}, 403),
    ({"Host": "evil.example"}, 403),
    ({"Content-Type": "text/plain"}, 415),
])
def test_rejects_untrusted_requests(bridge, override, code):
    server, _, calls = bridge
    headers = {"Authorization": "Bearer " + "x" * 40, "Content-Type": "application/json"}
    headers.update(override)
    req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1", data=b'{"operation":"status","params":{}}', headers=headers)
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == code
    assert not calls


def test_bad_json(bridge):
    server, _, _ = bridge
    req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1", data=b'broken', headers={"Authorization": "Bearer " + "x" * 40, "Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_missing_config(tmp_path):
    with pytest.raises(BridgeError) as exc:
        BridgeClient(str(tmp_path / "missing")).call("status")
    assert exc.value.code == "invalid_configuration"


def test_unavailable_anki(tmp_path):
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    path = tmp_path / "connection.json"
    path.write_text(json.dumps({"port": port, "token": "x" * 40}))
    with pytest.raises(BridgeError) as exc:
        BridgeClient(str(path)).call("status")
    assert exc.value.code == "anki_unavailable"


def test_redirect_never_forwards_token(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            calls.append(self.path)
            self.send_response(307)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/leak")
            self.end_headers()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / "connection.json"
    path.write_text(json.dumps({"port": server.server_port, "token": "x" * 40}))
    try:
        with pytest.raises(BridgeError):
            BridgeClient(str(path)).call("status")
        assert calls == ["/v1"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_busy_request_is_clear_error(bridge):
    server, path, calls = bridge
    server.gate.acquire()
    try:
        with pytest.raises(BridgeError) as exc:
            BridgeClient(str(path)).call("status")
        assert exc.value.code == "busy"
        assert not calls
    finally:
        server.gate.release()
