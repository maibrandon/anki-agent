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
import queue

faulthandler.enable()
faulthandler.dump_traceback_later(60)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

import aqt
from aqt.profiles import ProfileManager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def exercise(connection, decisions):
    params = StdioServerParameters(command=sys.executable, args=["-m", "anki_agent_mcp.server"],
                                  cwd=str(connection.parent),
                                  env={**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, "ANKI_AGENT_CONNECTION_FILE": str(connection)})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initial = await session.initialize()
            assert "rename_deck" in initial.instructions and "Never close or restart Anki" in initial.instructions
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"connection_status", "list_decks", "list_note_types", "search_notes", "preview_notes", "create_notes", "create_deck", "preview_delete_cards", "preview_delete_deck", "delete_cards", "delete_deck", "create_backup", "rename_deck", "move_cards"}
            annotations = {t.name: t.annotations for t in tools.tools}
            assert annotations["delete_cards"].destructiveHint and annotations["delete_deck"].destructiveHint
            assert annotations["preview_delete_cards"].readOnlyHint
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
            print("PASS: real Anki app, fourteen MCP tools, correct destructive annotations, deck creation, read-only preview, Basic/Cloze creation, retry, search, error propagation", flush=True)
    result = await asyncio.to_thread(subprocess.run,
        [sys.executable, str(ROOT / "examples/from_text.py"), str(ROOT / "examples/study-notes.txt"), "--deck", "anki-agent", "--create"],
        input="CREATE\n", text=True, capture_output=True,
        env={**os.environ, "ANKI_AGENT_CONNECTION_FILE": str(connection)}, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '"created": 3' in result.stdout, result.stdout
    print("PASS: local text example previewed and created three notes through MCP", flush=True)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            async def call(name, args=None):
                result = await session.call_tool(name, args or {})
                assert not result.isError, result.content
                return result.structuredContent or json.loads(result.content[0].text)
            status = await call("connection_status")
            assert status["addon_version"] == "0.3.0"
            assert {"rename_deck", "move_cards"} <= set(status["operations"])
            decks = (await call("list_decks"))["decks"]
            source = next(d["id"] for d in decks if d["name"] == "anki-agent")
            parent = await call("create_deck", {"name": "Organization"})
            child = await call("create_deck", {"name": "anki-agent::Child"})
            rename = {"deck_id": source, "new_name": "Organization::Questions", "expected_name": "anki-agent"}
            renamed = await call("rename_deck", rename)
            assert renamed["changed_deck_count"] == 2 and renamed["affected_card_count"] == 6
            assert (await call("rename_deck", rename))["already_applied"]
            assert (await session.call_tool("rename_deck", {"deck_id": source, "new_name": "Organization", "expected_name": "Organization::Questions"})).isError
            found = await call("search_notes", {"query": 'deck:"Organization::Questions"'})
            ids = found["notes"][0]["card_ids"]
            assert found["notes"][0]["cards"][0]["deck_id"] == source
            moved = await call("move_cards", {"card_ids": ids, "deck_id": child["deck_id"], "expected_deck_id": source})
            assert moved["moved_count"] == len(ids)
            assert (await call("move_cards", {"card_ids": ids, "deck_id": child["deck_id"], "expected_deck_id": source}))["already_applied"]
            await call("move_cards", {"card_ids": ids, "deck_id": source, "expected_deck_id": child["deck_id"]})
            await call("rename_deck", {"deck_id": source, "new_name": "anki-agent", "expected_name": "Organization::Questions"})
            after = (await call("list_decks"))["decks"]
            assert {"id": parent["deck_id"], "name": "Organization"} in after
            assert {"id": child["deck_id"], "name": "anki-agent::Child"} in after
            print("PASS: MCP instructions, deck rename/reparent/promotion with descendants, collision errors, selected card moves, unchanged IDs and retry no-ops", flush=True)
            deck = await call("create_deck", {"name": "anki-agent-delete-test"})
            specs = [
                {"deck": "anki-agent-delete-test", "note_type": "Basic", "fields": {"Front": "Deletion safety example", "Back": "Must confirm Yes"}},
                {"deck": "anki-agent-delete-test", "note_type": "Cloze", "fields": {"Text": "{{c1::Delete}} needs {{c2::confirmation}}.", "Back Extra": "Disposable only"}},
            ]
            p = await call("preview_notes", {"notes": specs})
            made = await call("create_notes", {"preview_id": p["preview_id"]})
            found = await call("search_notes", {"query": f"nid:{made['note_ids'][0]}"})
            card_ids = found["notes"][0]["card_ids"]
            deletion = await call("preview_delete_cards", {"card_ids": card_ids})
            for choice in ("no", "timeout"):
                decisions.put(choice)
                denied = await session.call_tool("delete_cards", {"preview_id": deletion["preview_id"]})
                assert denied.isError and "confirmation_denied" in denied.content[0].text
                assert (await call("search_notes", {"query": f"nid:{made['note_ids'][0]}"}))["total"] == 1
            # An agent cannot bypass the native dialog with a wire-level boolean.
            # The SDK may ignore unknown arguments; the native approval is still
            # mandatory, so simulate No rather than waiting out the full timer.
            decisions.put("no")
            denied = await session.call_tool("delete_cards", {"preview_id": deletion["preview_id"], "confirmed": True})
            assert denied.isError
            decisions.put("yes")
            deleted = await call("delete_cards", {"preview_id": deletion["preview_id"]})
            assert deleted["deleted_cards"] == 1 and deleted["deleted_notes"] == 1
            assert Path(deleted["backup"]["path"]).is_file()
            replay = await call("delete_cards", {"preview_id": deletion["preview_id"]})
            assert replay["replayed"]
            deck_preview = await call("preview_delete_deck", {"deck_id": deck["deck_id"]})
            assert deck_preview["card_count"] == 2
            decisions.put("no")
            denied = await session.call_tool("delete_deck", {"preview_id": deck_preview["preview_id"]})
            assert denied.isError and "confirmation_denied" in denied.content[0].text
            decisions.put("yes")
            deleted = await call("delete_deck", {"preview_id": deck_preview["preview_id"]})
            assert deleted["deleted_decks"] == 1 and deleted["deleted_cards"] == 2
            assert (await call("search_notes", {"query": 'deck:"anki-agent-delete-test"'}))["total"] == 0
            assert Path((await call("create_backup"))["path"]).is_file()
            print("PASS: native default-No, No/timeout cancellation, approval-bypass rejection, confirmed card/deck deletion, mandatory backups and safe retries", flush=True)


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
        original_collection = aqt.mw.col
        runpy.run_path(str(ROOT / "scripts/activate_in_anki.py"))["activate"](
            ROOT / "dist/anki-agent-0.3.0.ankiaddon", config)
        print("PASS: first-install activation in an already-open Anki app, without restart", flush=True)
        finished = threading.Event()
        decisions = queue.Queue()
        errors = []
        def worker():
            try:
                asyncio.run(exercise(credential, decisions))
            except BaseException:
                errors.append(traceback.format_exc())
                print(errors[-1], flush=True)
            finally:
                finished.set()
        threading.Thread(target=worker, daemon=True).start()
        deadline = time.monotonic() + 90
        while not finished.is_set() and time.monotonic() < deadline:
            app.processEvents()
            # Simulate human button presses ONLY in this disposable test instance.
            # There is no production RPC or environment variable for auto-approval.
            import importlib
            bridge = importlib.import_module("anki_agent")
            if bridge.runner.dialog is not None and not decisions.empty():
                from aqt.qt import QMessageBox
                box = bridge.runner.dialog
                assert box.defaultButton() is box.button(QMessageBox.StandardButton.No)
                choice = decisions.get_nowait()
                if choice == "timeout":
                    box._anki_agent_timer.start(50)
                else:
                    button = QMessageBox.StandardButton.Yes if choice == "yes" else QMessageBox.StandardButton.No
                    box.button(button).click()
            time.sleep(0.005)
        assert finished.is_set(), "MCP smoke test timed out"
        # Inspect only the disposable app's open collection, on its main thread.
        if not errors:
            try:
                assert aqt.mw.col.card_count() == 6
                aqt.mw.col.undo()  # Restore the removed deck and its two Cloze cards.
                assert aqt.mw.col.card_count() == 8
                aqt.mw.col.undo()
                assert aqt.mw.col.card_count() == 9
                assert aqt.mw.col.note_count() == 7
                assert aqt.mw.col is original_collection
                print("PASS: card and deck deletions are independently undoable; unrelated test deck survived", flush=True)
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
