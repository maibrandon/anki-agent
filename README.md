# anki-agent

I want to turn my study notes into Anki cards with Codex or Claude Code, without having an agent click through Anki every time.

This project gives AI agents a simple way to work with Anki through MCP (Model Context Protocol). Anki stays open in the background, while a local add-on and MCP server let the agent work with the collection through Anki's own API.

The add-on checks the connection, lists and creates decks, lists note types, searches notes, and previews and creates Basic and Cloze notes in batches. It also previews and deletes cards or decks, but only after you click Yes in Anki. A recovery backup must finish before anything is deleted. The connection is local and authenticated, with fourteen defined tools. Decks can be renamed or moved in the hierarchy, and selected cards can move between normal decks while keeping their IDs and scheduling.

The MVP has been tested with Anki 25.9.2 in a disposable profile, including a real MCP client. Preview shows proposed note content; it does not render card templates. Media and other note structures are outside the first version.

## Default study prompt

The [`study_prompts` folder](study_prompts/) includes a [default prompt for turning course material into Anki Cloze cards](study_prompts/course-material-to-anki-cloze.md). Fill in the deck, topic, assessment scope, and sources before using it with your agent.

[Setup for Codex and Claude Code](docs/setup.md) · [Deck organization](docs/deck-organization.md) · [Deletion and backups](docs/deletion-and-backups.md) · [Local text example](examples/from_text.py) · [Architecture](docs/architecture.md) · [Testing and packaging](docs/development.md)

Licensed under [AGPL-3.0-or-later](LICENSE). No public release or AnkiWeb upload yet.

An independent project, not affiliated with Anki, OpenAI, or Anthropic.
