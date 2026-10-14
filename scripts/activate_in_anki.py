"""One-time first-install helper. Run INSIDE Anki's debug console, not a shell.

No collection is opened, no restart occurs, and no credentials are printed.
This deliberately refuses to hot-reload an already-loaded add-on.
"""
import importlib
import json
from pathlib import Path
import sys


def activate(archive_path, connection_config=None):
    from aqt import mw
    from aqt.addons import InstallOk
    if mw is None or mw.col is None:
        raise RuntimeError("Open your intended Anki profile first.")
    if "anki_agent" in sys.modules:
        raise RuntimeError("Anki Agent is already loaded. Use its connection menu; upgrades require a restart.")
    archive = Path(archive_path).expanduser().resolve()
    if not archive.is_file() or archive.suffix != ".ankiaddon":
        raise RuntimeError("Supply the built Anki Agent .ankiaddon archive.")
    result = mw.addonManager.install(str(archive), force_enable=True)
    if not isinstance(result, InstallOk) or not result.compatible:
        raise RuntimeError(f"Anki could not install this archive: {result}")
    # Only the disposable test harness provides this argument to avoid port collisions.
    if connection_config is not None:
        connection = Path(mw.addonManager.addonsFolder("anki_agent")) / "user_files" / "connection.json"
        connection.parent.mkdir(exist_ok=True)
        connection.write_text(json.dumps(connection_config))
        connection.chmod(0o600)
    importlib.invalidate_caches()
    module = importlib.import_module("anki_agent")
    if module.startup_error:
        raise RuntimeError(module.startup_error)
    print(f"Anki Agent is active without restarting. Connection file: {module.credential_path}")
    return str(module.credential_path)
