# Verification

## Version 0.3.0 — October 22, 2026

Verified locally with Python 3.13, Anki/aqt 25.9.2 and MCP SDK 1.30.0:

- `python -m pytest -q`: **86 passed**. New temporary-collection tests cover rename, promotion, reparenting with descendants, retained parent decks and settings, case/Unicode collisions, malformed names, cycles, missing/stale IDs, filtered/default protection, card moves, unchanged scheduling/card/note IDs, untouched siblings, whole-batch validation, retry no-ops, and undo. An older add-on produces an actionable upgrade error.
- Packaged wheel and add-on passed the complete offscreen app/MCP test with **all fourteen tools**, delivered MCP initialization guidance, descendant rename/reparent/promotion, collision errors, selected card moves and retries. Existing creation, native deletion confirmation, mandatory backups, local text-file workflow, and undo tests also passed. The same disposable collection stayed open throughout.
- Tests used a temporary Python environment for the new wheel, a unique Anki IPC key, temporary profile/base and separate port. They did not modify the open live app, installed connector, or live collection.
- Both 0.3.0 packages built successfully; archive contents and source distribution were checked for expected source and absence of credentials/caches.

The existing Codex registration launches the MCP executable directly; it does not install a separate `SKILL.md`. Agent guidance is carried by MCP server initialization instructions and tool descriptions. Both now explain deck organization, source-state preconditions, retry limits and coordinated restarts. Existing sessions must reconnect to load changed MCP instructions/tools.

After the user confirmed that the other session had finished and authorized a restart, Anki was closed normally and both installed packages were upgraded to 0.3.0. Existing credentials and recovery backups were preserved, and previous add-on program files were archived locally for rollback. Anki reopened successfully. A fresh MCP session verified add-on version 0.3.0, an available collection, fourteen tools, and the updated initialization instructions. Live verification used only connection status, deck listing and note-type listing; no live notes, cards or decks were changed by verification. All organization mutation tests remained confined to disposable collections.

## Earlier verification

Verified locally on macOS on October 14, 2026 with Python 3.13, Anki/aqt 25.9.2, and MCP Python SDK 1.30.0.

- `python -m pytest -q`: **59 passed**. Real temporary Collection API tests cover Basic/Cloze generation, escaping, validation, duplicates, limits, preview/session binding, revalidation, retries, JSON serialization, and undo. Deletion tests cover mandatory approval, one-use capabilities, stale scope, profile changes, filtered/default deck protection, cross-deck siblings, backup failure, cancellation after backup, and recovery import with scheduling/media. Loopback HTTP tests cover authentication, browser/Host rejection, malformed requests, busy responses, unavailable Anki, and refusal to forward credentials on redirects.
- `python scripts/smoke_anki.py`: **passed**. Installed MCP wheel and packaged add-on ran through a real stdio MCP session and a full offscreen Anki app. The test created its own temporary base/profile and `anki-agent` deck. All twelve tools worked with correct destructive/read-only annotations. Preview wrote nothing; Basic/Cloze creation and retry worked. The local text example created three further notes through MCP. The test simulated native No, timeout and Yes responses only in the disposable instance. No/timeout caused no deletion; Yes created a verified backup before card/deck deletion; retries did not delete again. Both deletions were undone independently and an unrelated deck survived. The same collection object remained open throughout.
- Add-on, wheel, and source distribution builds succeeded. Archive inspection confirmed the root entry point, manifest, and licenses, with no connection file or caches. The source distribution includes add-on source, docs, scripts, examples, and tests.
- `pip check`, Python compilation, and `git diff --check` passed.
- Codex command syntax was checked against the installed CLI help. Claude Code instructions were checked against its official documentation; Claude Code itself was not installed or tested. Neither client's personal configuration was changed.

The automated unit and smoke tests never open or modify a live collection. The smoke harness uses a unique Anki IPC key because Anki 25.9.2 otherwise reuses an already-open app even with a different `-b` folder. One earlier test launch was forwarded to an existing instance and aborted before collection access; the harness now prevents that behavior.

During the original v0.1.0 MVP verification, after explicit user authorization, the add-on was installed and activated in the user's already-open Anki 25.09.2 app using the one-time helper, without closing or restarting it. A real MCP client created the persistent `anki-agent` deck in the open profile, previewed a Basic/Cloze batch, verified that preview performed no writes, created two notes tagged `anki-agent-test`, and verified that retry created zero additional notes. Every collection write was confined to this requested deck. The test adapted to the actual Cloze field names returned by the collection. The two notes remain available for inspection. No collection database was opened directly.

Version 0.2.0 deletion and backup tests ran only in disposable profiles. The installed normal-profile add-on has not been upgraded by this change, and no live deletion was attempted.

The helper's console interaction was only for one-time installation; all deck/note operations used MCP. The automatic disposable profile is deleted after testing.

Offscreen Qt prints platform warnings, and Anki's media server prints an unhandled-close warning during shutdown; the completed final smoke test exits successfully. Other Anki versions, Windows/Linux app integration, and AnkiWeb installation/update behavior have not been verified. No public repository release, AnkiWeb upload, or PyPI publication has been performed.
