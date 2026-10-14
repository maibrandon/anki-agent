# MVP verification

Verified locally on macOS on October 14, 2026 with Python 3.13, Anki/aqt 25.9.2, and MCP Python SDK 1.30.0.

- `python -m pytest -q`: **35 passed**. Real temporary Collection API tests cover Basic/Cloze generation, escaping, validation, duplicates, batch limits, preview expiration/session binding, revalidation, retries, JSON serialization, and undo. Loopback HTTP tests cover authentication, browser/Host rejection, malformed requests, busy responses, unavailable Anki, and refusal to forward credentials on redirects.
- `python scripts/smoke_anki.py`: **passed**. Installed MCP wheel and packaged add-on ran through a real stdio MCP session and a full offscreen Anki app. The test created its own temporary base/profile and `anki-agent` deck. All seven tools worked. Preview wrote nothing; two notes generated three cards; retry returned existing IDs. The local text example created three further notes through MCP. Both batches were undone independently, leaving zero notes.
- Add-on, wheel, and source distribution builds succeeded. Archive inspection confirmed the root entry point, manifest, and licenses, with no connection file or caches. The source distribution includes add-on source, docs, scripts, examples, and tests.
- `pip check`, Python compilation, and `git diff --check` passed.
- Codex command syntax was checked against the installed CLI help. Claude Code instructions were checked against its official documentation; Claude Code itself was not installed or tested. Neither client's personal configuration was changed.

The automated unit and smoke tests never open or modify a live collection. The smoke harness uses a unique Anki IPC key because Anki 25.9.2 otherwise reuses an already-open app even with a different `-b` folder. One earlier test launch was forwarded to an existing instance and aborted before collection access; the harness now prevents that behavior.

After explicit user authorization, the add-on was installed and activated in the user's already-open Anki 25.09.2 app using the one-time helper, without closing or restarting it. A real MCP client created the persistent `anki-agent` deck in the open profile, previewed a Basic/Cloze batch, verified that preview performed no writes, created two notes tagged `anki-agent-test`, and verified that retry created zero additional notes. Every collection write was confined to this requested deck. The test adapted to the actual Cloze field names returned by the collection. The two notes remain available for inspection. No collection database was opened directly.

The helper's console interaction was only for one-time installation; all deck/note operations used MCP. The automatic disposable profile is deleted after testing.

Offscreen Qt prints platform warnings, and Anki's media server prints an unhandled-close warning during shutdown; the completed final smoke test exits successfully. Other Anki versions, Windows/Linux app integration, and AnkiWeb installation/update behavior have not been verified. No public repository release, AnkiWeb upload, or PyPI publication has been performed.
