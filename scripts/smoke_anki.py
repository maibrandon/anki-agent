"""End-to-end disposable Anki app + MCP test. Never uses the default base folder."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import runpy
import sys
import tempfile
import threading
import time
import traceback
import faulthandler

faulthandler.enable()
faulthandler.dump_traceback_later(25)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

import aqt
from aqt.profiles import ProfileManager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def exercise(connection):
    params = StdioServerParameters(command=sys.executable, args=["-m", "anki_agent_mcp.server"],
                                  cwd=str(connection.parent),
                                  env={**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, "ANKI_AGENT_CONNECTION_FILE": str(connection)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"connection_status", "list_decks", "list_note_types", "search_notes", "preview_notes", "create_notes", "create_deck"}
            async def call(name, args=None):
                print("Testing", name, flush=True)
                result = await session.call_tool(name, args or {})
                assert not result.isError, result.content
                return result.structuredContent or json.loads(result.content[0].text)
            assert (await call("connection_status"))["collection_available"]
            assert (await call("create_deck", {"name": "anki-agent"}))["created"]
            assert not (await call("create_deck", {"name": "anki-agent"}))["created"]
            assert (await call("list_decks"))["decks"]
            assert (await call("list_note_types"))["note_types"]
            assert (await call("search_notes"))["total"] == 0
            notes = [
                {"deck": "anki-agent", "note_type": "Basic", "fields": {"Front": "MCP stands for?", "Back": "Model Context Protocol"}},
                {"deck": "anki-agent", "note_type": "Cloze", "fields": {"Text": "{{c1::Anki}} creates {{c2::cards}} from notes.", "Back Extra": "Smoke test"}},
            ]
            preview = await call("preview_notes", {"notes": notes})
            assert (await call("search_notes"))["total"] == 0
            created = await call("create_notes", {"preview_id": preview["preview_id"]})
            assert created["created"] == 2
            again = await call("create_notes", {"preview_id": preview["preview_id"]})
            assert again["replayed"] and again["note_ids"] == created["note_ids"]
            assert (await call("search_notes"))["total"] == 2
            invalid = await session.call_tool("preview_notes", {"notes": notes})
            assert invalid.isError
            print("PASS: real Anki app, seven MCP tools, deck creation, read-only preview, Basic/Cloze creation, retry, search, error propagation", flush=True)
    result = await asyncio.to_thread(subprocess.run,
        [sys.executable, str(ROOT / "examples/from_text.py"), str(ROOT / "examples/study-notes.txt"), "--deck", "anki-agent", "--create"],
        input="CREATE\n", text=True, capture_output=True,
        env={**os.environ, "ANKI_AGENT_CONNECTION_FILE": str(connection)}, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '"created": 3' in result.stdout, result.stdout
    print("PASS: local text example previewed and created three notes through MCP", flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix="anki-agent-smoke-") as folder:
        base = Path(folder)
        addon = base / "addons21" / "anki_agent"
        subprocess.run([sys.executable, str(ROOT / "scripts/package_addon.py")], check=True)
        credential = addon / "user_files" / "connection.json"
        # Avoid colliding with the user's open Anki bridge.
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = {"port": port, "token": "disposable-test-token-" + os.urandom(24).hex()}
        pm = ProfileManager(base)
        pm.setupMeta()
        pm.create("Agent Test")
        pm.load("Agent Test")
        pm.meta["firstRun"] = False
        pm.meta["defaultLang"] = "en_US"
        pm.meta["check_for_updates"] = False
        pm.meta["last_addon_update_check"] = int(time.time())
        pm.profile["autoSync"] = False
        pm.save()
        pm.db.close()
        # Anki 25.9.2 uses one IPC key per OS user even for different -b paths.
        # Isolate the test key so it cannot forward to an already-open live app.
        aqt.AnkiApp.KEY = "anki-agent-smoke-" + os.urandom(16).hex()
        app = aqt._run(["anki", "-b", str(base), "-p", "Agent Test"], exec=False)
        sys.excepthook = sys.__excepthook__
        assert app
        deadline = time.monotonic() + 60
        while aqt.mw.col is None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert aqt.mw.col is not None, "Disposable profile did not open"
        runpy.run_path(str(ROOT / "scripts/activate_in_anki.py"))["activate"](
            ROOT / "dist/anki-agent-0.1.0.ankiaddon", config)
        print("PASS: first-install activation in an already-open Anki app, without restart", flush=True)
        finished = threading.Event()
        errors = []
        def worker():
            try:
                asyncio.run(exercise(credential))
            except BaseException:
                errors.append(traceback.format_exc())
                print(errors[-1], flush=True)
            finally:
                finished.set()
        threading.Thread(target=worker, daemon=True).start()
        deadline = time.monotonic() + 90
        while not finished.is_set() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert finished.is_set(), "MCP smoke test timed out"
        # Inspect only the disposable app's open collection, on its main thread.
        if not errors:
            try:
                assert aqt.mw.col.card_count() == 6
                aqt.mw.col.undo()  # Undo the local text example's batch.
                assert aqt.mw.col.card_count() == 3
                aqt.mw.col.undo()
                assert aqt.mw.col.note_count() == 0
                print("PASS: batch generated three cards and is undoable as one operation", flush=True)
            except BaseException:
                errors.append(traceback.format_exc())
        import importlib
        bridge = importlib.import_module("anki_agent")
        bridge.server.shutdown()
        bridge.server.server_close()
        faulthandler.cancel_dump_traceback_later()
        aqt.mw.unloadProfileAndExit()
        app.exec()
        if errors:
            raise AssertionError(errors[0])


if __name__ == "__main__":
    main()
