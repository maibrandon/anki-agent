# Architecture

Codex / Claude Code → MCP stdio server → authenticated HTTP on 127.0.0.1 → Anki add-on → Anki's open collection.

The server uses the official MCP Python SDK's stable v1 API. It never opens a collection file. The add-on uses only Python's standard library and Anki's installed APIs. Read operations use `QueryOp`; batch writes use `CollectionOp`. Both enter Anki's serialized collection queue. UI state is read on the main thread; collection work runs in the queue's background worker. The operation callback checks that the collection has not changed before running.

Seven operations are exposed: status, deck listing, note-type listing, note search, batch preview, batch creation, and normal deck creation. There is no arbitrary Python, SQL, file access, deletion, scheduling, sync, remote bind, or media upload operation. Preview constructs and validates unsaved notes, then stores an opaque ID for ten minutes. Create accepts only that ID and revalidates the stored content. Basic structures have two fields and one card template; Cloze structures have two fields. Localized field/model names are accepted; clients must use the returned names. Custom templates fitting those structures are permitted, but the preview is content only, not a rendering of those templates.

All notes in a batch are submitted through `Collection.add_notes`, one backend transaction and undo step. A reserved `anki_agent_batch_<preview_id>` tag is attached to every note. A retry looks up this tag before writing, including after restart. Replays report surviving note IDs and never fill in deleted notes while any tagged notes remain. If all notes are removed or undone, the original preview may be used again within its ten-minute lifetime; after restart it expires. Do not remove provenance tags if you need retry recovery. This is intentionally simpler than a persistent receipt database; it is not permanent exactly-once delivery.

Duplicate first fields are rejected according to Anki's field checks, and identical first fields within a batch are rejected. Existing collection contents can change after preview, so create validates again. Plain-text fields are HTML-escaped and newlines become `<br>`. Cloze syntax remains functional. Model templates already in the collection may contain HTML or scripts; this bridge does not inspect or rewrite them.

The listener binds IPv4 loopback only, requires a bearer token on every request, validates the Host header, rejects browser Origin headers, and sends no CORS headers. JSON bodies are capped at 2 MB. Only one request may execute at a time. Requests have bounded read/execution timeouts. The MCP client ignores proxies and refuses redirects so credentials cannot be sent to another host. Credentials live in the add-on's `user_files/connection.json`, outside the release archive, with mode 0600 on systems supporting it. Local processes with access to that file can operate on the collection; this is not isolation from other programs running as the same user.

Anki add-ons are installed per base folder, not per profile. The bridge operates on the currently open profile. Keep the test base separate, and confirm connection status before writes. No AI API is called by this project. The AI client may send retrieved note contents to its provider according to its own settings. Collection text and local input files are untrusted data and must never be treated as agent instructions.

## Tradeoffs

Two packages require two installation steps, but keep the MCP dependency graph out of Anki. HTTP is simple to debug and portable, but requires token management and local-port availability. Search uses Anki's search API then paginates returned IDs; the response is bounded, but very broad searches may still allocate many IDs. Only deck and note creation are available as mutations, and read-only content previews avoid running card templates on proposed content. Full rendered preview, media, other note types, token rotation UI, and durable external receipts can follow later.

## Guidance checked

- [Anki collection APIs](https://docs.ankiweb.net/addons/the-anki-module)
- [Anki background operations](https://docs.ankiweb.net/addons/background-ops)
- [Anki packaging](https://docs.ankiweb.net/addons/sharing)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
- [Codex MCP configuration](https://developers.openai.com/codex/mcp)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)

Checked October 14, 2026. The code targets the tested Anki 25.9.2 collection/operation API and MCP SDK v1; it does not assume the SDK's main branch API is compatible.
