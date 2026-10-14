"""Anki entry point. This file is the root of the .ankiaddon archive."""
import json
import os
from pathlib import Path
import secrets
import threading

from aqt import mw, gui_hooks
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import QAction
from aqt.utils import showInfo, showWarning

from .anki_agent.errors import AgentError
from .anki_agent.service import Service, OPERATIONS, WriteResult
from .anki_agent.transport import make_server

service = Service()
server = None
startup_error = None
pending = threading.Lock()
credential_path = Path(__file__).parent / "user_files" / "connection.json"


def execute(operation, params):
    if operation not in OPERATIONS:
        raise AgentError("unknown_operation", "Operation is not supported.")
    if not pending.acquire(blocking=False):
        raise AgentError("busy", "Anki is still processing the previous operation; retry shortly.")
    finished = threading.Event()
    outcome = {}
    cancelled = threading.Event()

    def success(result):
        outcome["result"] = result.payload if isinstance(result, WriteResult) else result
        pending.release()
        finished.set()

    def failure(exc):
        outcome["error"] = exc if isinstance(exc, AgentError) else AgentError("anki_error", "Anki could not complete the operation.")
        pending.release()
        finished.set()

    def start():
        if cancelled.is_set():
            return failure(AgentError("timeout", "Request expired before execution."))
        # Read UI state only on the main thread, before entering the op queue.
        col = mw.col
        if operation == "status":
            return success(service.dispatch(col, operation, params))
        if col is None:
            return failure(AgentError("collection_unavailable", "Open an Anki profile first."))

        def run(active_col):
            if cancelled.is_set():
                raise AgentError("timeout", "Request expired before execution.")
            if active_col is not col:
                raise AgentError("collection_changed", "The profile changed; preview again.")
            result = service.dispatch(active_col, operation, params)
            if isinstance(result, WriteResult) and result.changes is None:
                # CollectionOp expects an OpChanges value even for a replay.
                from anki.collection import OpChanges
                result.changes = OpChanges()
            return result

        try:
            if operation in {"create_notes", "create_deck"}:
                CollectionOp(parent=mw, op=run).success(success).failure(failure).run_in_background()
            else:
                QueryOp(parent=mw, op=run, success=success).failure(failure).run_in_background()
        except Exception as exc:
            failure(exc)

    mw.taskman.run_on_main(start)
    if not finished.wait(45):
        cancelled.set()
        # Keep pending locked until the callback finishes; a running write may
        # already have committed. Retrying the same preview ID recovers it.
        raise AgentError("timeout", "Anki timed out. A write may have completed; retry the same preview_id.")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def start_server():
    global server, startup_error
    try:
        credential_path.parent.mkdir(exist_ok=True)
        if credential_path.exists():
            config = json.loads(credential_path.read_text())
        else:
            config = {"token": secrets.token_urlsafe(32), "port": 8767}
            fd = os.open(credential_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(config, stream)
        os.chmod(credential_path, 0o600)
        server = make_server(config["port"], config["token"], execute)
        threading.Thread(target=server.serve_forever, daemon=True, name="anki-agent-http").start()
    except Exception as exc:
        startup_error = f"Anki Agent could not start ({type(exc).__name__}). Check the connection file and whether port 8767 is already in use."


def connection_info():
    if startup_error:
        showWarning(startup_error)
    else:
        showInfo(f"Anki Agent is listening on 127.0.0.1:{server.server_port}.\n\nConnection file (contains a secret; do not share):\n{credential_path}")


def profile_closed(*_args):
    service.clear()


start_server()
action = QAction("Anki Agent connection", mw)
action.triggered.connect(connection_info)
mw.form.menuTools.addAction(action)
gui_hooks.profile_will_close.append(profile_closed)
