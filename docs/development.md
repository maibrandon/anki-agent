# Development and packaging

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_anki.py
.venv/bin/python scripts/package_addon.py
.venv/bin/python -m build
```

The tests create temporary collections through Anki's Collection API. The smoke script creates an entirely separate temporary Anki base folder/profile, starts an offscreen Anki app with its own IPC instance key, installs and activates the packaged add-on while that app remains open, and launches the installed MCP server as a stdio subprocess. It exercises all fourteen tools and the local-file example, checks native default-No/Yes/timeout behavior, backups, destructive annotations, rename/reparent/promotion, collisions, selected card moves, retry behavior and undo, and verifies the same collection object stays open. The test harness simulates human button presses only in that disposable instance; production exposes no RPC or environment switch for automatic approval. It neither installs into the default base folder nor opens a live collection. Local socket and Qt execution permissions are required. Install the server before running the smoke script.

Anki 25.9.2 / aqt 25.9.2 are pinned for reproducible API tests. Runtime add-on compatibility with other versions must be checked separately. On older Intel macOS, current cryptography wheels may not be available: the verified environment used `cryptography<47`, `PyQt6<6.10`, and `PyQt6-WebEngine<6.10`. These are environment workarounds, not add-on dependencies.

`dist/anki-agent-0.3.0.ankiaddon` contains the add-on root entry point, manifest, core modules, and license notices. It excludes user credentials, caches, tests, and MCP dependencies. Install it through Anki's Install from file action. The manifest allows distribution outside AnkiWeb.

`python -m build` creates a wheel and source distribution for the separate MCP server. Install the wheel with pip on the same computer as Anki. The SDK and its dependencies are installed by pip; they are not bundled into the add-on. Python packaging metadata carries AGPL-3.0-or-later; dependency licenses remain their own.

Release checklist: run tests and smoke test, inspect archive contents, verify client instructions, document the supported Anki versions, review licenses/dependency notices, and obtain approval before making the repository public or uploading an add-on/package. No automatic publication is configured.
