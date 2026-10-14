# anki-agent

I want to turn my study notes into Anki cards with Codex or Claude Code, without having an agent click through Anki every time.

This project aims to give AI agents a simple way to work with Anki through MCP (Model Context Protocol). Anki stays open in the background, while a local add-on and MCP server let the agent work with the collection through Anki's own API.

The first version will focus on checking the connection, listing decks and note types, searching notes, and previewing and creating Basic and Cloze notes in batches. The connection will be local and authenticated, with a small set of defined operations.

Early development. The add-on and MCP server are not implemented yet. Testing will use a disposable Anki profile before any release.

An independent project, not affiliated with Anki, OpenAI, or Anthropic.
