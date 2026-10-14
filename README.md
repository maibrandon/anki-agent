# anki-agent

I want to turn my study notes into Anki cards with Codex or Claude Code, without having an agent click through Anki every time.

This project gives AI agents a simple way to work with Anki through MCP (Model Context Protocol). Anki stays open in the background, while a local add-on and MCP server let the agent work with the collection through Anki's own API.

The add-on checks the connection, lists and creates decks, lists note types, searches notes, and previews and creates Basic and Cloze notes in batches. It also previews and deletes cards or decks, but only after you click Yes in Anki. A recovery backup must finish before anything is deleted. The connection is local and authenticated, with twelve defined tools.

The MVP has been tested with Anki 25.9.2 in a disposable profile, including a real MCP client. Preview shows proposed note content; it does not render card templates. Media and other note structures are outside the first version.

[Setup for Codex and Claude Code](docs/setup.md) · [Deletion and backups](docs/deletion-and-backups.md) · [Local text example](examples/from_text.py) · [Architecture](docs/architecture.md) · [Testing and packaging](docs/development.md)

Licensed under [AGPL-3.0-or-later](LICENSE). No public release or AnkiWeb upload yet.

An independent project, not affiliated with Anki, OpenAI, or Anthropic.
