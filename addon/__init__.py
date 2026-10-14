"""Anki entry point. This file is the root of the .ankiaddon archive."""
import json
import os
from pathlib import Path
import secrets
import threading

from aqt import mw, gui_hooks
from aqt.qt import QAction
from aqt.utils import showInfo, showWarning

from .anki_agent.service import Service
from .anki_agent.integration import Runner
from .anki_agent.transport import make_server

service = Service(backup_root=Path(__file__).parent / "user_files" / "backups")
server = None
startup_error = None
credential_path = Path(__file__).parent / "user_files" / "connection.json"


runner = Runner(mw, service)


def execute(operation, params):
    return runner.execute(operation, params)


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
    if runner.dialog is not None:
        runner.dialog.reject()


start_server()
action = QAction("Anki Agent connection", mw)
action.triggered.connect(connection_info)
mw.form.menuTools.addAction(action)
gui_hooks.profile_will_close.append(profile_closed)
