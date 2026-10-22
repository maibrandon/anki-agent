import json
import os
from pathlib import Path
import urllib.error
import urllib.request


class BridgeError(Exception):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details


class BridgeClient:
    def __init__(self, connection_file=None):
        self.connection_file = connection_file or os.environ.get("ANKI_AGENT_CONNECTION_FILE")

    def call(self, operation, **params):
        if not self.connection_file:
            raise BridgeError("not_configured", "Set ANKI_AGENT_CONNECTION_FILE to the add-on's connection.json path.")
        try:
            config = json.loads(Path(self.connection_file).expanduser().read_text())
            port, token = config["port"], config["token"]
            if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or len(token) < 32:
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise BridgeError("invalid_configuration", "Connection file is missing, unreadable, or invalid. Start Anki with the add-on installed.") from None
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1", data=json.dumps({"operation": operation, "params": params}).encode(),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
        # Ignore system proxies and refuse redirects, so the credential can never
        # be forwarded to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *_args, **_kwargs):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=50) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                exc.close()
                raise BridgeError("redirect_refused", "The local bridge attempted a redirect; no credentials were forwarded.") from None
            try:
                with exc:
                    payload = json.load(exc)
            except (ValueError, OSError):
                raise BridgeError("bridge_error", f"Local bridge returned HTTP {exc.code}.") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise BridgeError("anki_unavailable", "Cannot reach Anki. Keep Anki open with the add-on enabled. If a write timed out, retry identical tool arguments (the same preview_id when used).") from None
        except ValueError:
            raise BridgeError("bridge_error", "Local bridge returned an invalid response.") from None
        if not isinstance(payload, dict) or "ok" not in payload:
            raise BridgeError("bridge_error", "Local bridge returned an invalid response.")
        if not payload["ok"]:
            error = payload.get("error", {})
            raise BridgeError(error.get("code", "bridge_error"), error.get("message", "Bridge error."), error.get("details"))
        return payload["result"]
