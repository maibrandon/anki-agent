# Deck organization

Version 0.3.0 adds two tools to address [issue #1](https://github.com/maibrandon/anki-agent/issues/1). Both run through Anki's serialized `CollectionOp` queue while the app and collection stay open. They use `DeckManager.rename` and `Collection.set_deck`; they do not edit the database directly.

Ask the user to authorize the exact source and destination before changing organization. A clear request to rename/reparent a named deck or move specified cards supplies that authorization. These operations preserve content and do not require deletion previews or the native deletion dialog. Deletion still requires its own matching preview, recovery backup and explicit human Yes in Anki. Use `create_backup` first if the user wants a recovery snapshot as well as Anki undo.

## Rename, reparent or promote a deck

Resolve the source ID and current name with `list_decks`. Call:

```json
{
  "deck_id": 123456789,
  "expected_name": "Course::Practice Sources::Official Questions",
  "new_name": "Course midterm practise"
}
```

This is `rename_deck`. A name without `::` promotes the deck to the top level. To place it under another deck, use that parent's exact fully qualified name, for example `Archive::Course midterm practise`. Create the destination parent explicitly first if it is missing.

The same deck ID, descendant IDs, cards, scheduling and deck settings survive. Descendant names follow the renamed prefix. Empty source parents and unrelated decks remain. Each changed call is one undo step. The result includes old/new names, the affected deck IDs and names, the card count across the tree, and whether anything changed. At most 100 decks, including descendants, may be renamed in one call.

Names are normalized to Unicode NFC and limited to 100 characters, including the full path of each descendant. Components must be nonempty and trimmed, separated by `::`, with no other colons or control characters. Default (ID 1), filtered decks, filtered descendants, missing IDs/parents, cycles, and collisions are rejected before mutation. Anki's native collision behavior can add a suffix; this bridge explicitly refuses collisions instead. Names are checked with Anki's lookup, including case-insensitive and Unicode-equivalent collisions. Use the exact spelling of the destination parent.

## Move selected cards

Read `search_notes`: each note retains `card_ids` and now also includes `cards` entries with `id`, `deck_id`, and `original_deck_id` (nonzero when borrowed by a filtered deck). Resolve the destination with `list_decks`. Call `move_cards`:

```json
{
  "card_ids": [111111111, 222222222],
  "expected_deck_id": 123456789,
  "deck_id": 987654321
}
```

Move 1–500 distinct cards from one expected source deck to a normal destination deck. Group cards by current source deck for multiple calls. This affects only selected cards; sibling cards of the same note stay in their decks. No notes or cards are recreated. Card IDs, note IDs and scheduling remain intact. Default may be a source or destination for card moves; its identity and name are protected from deck renaming. Filtered sources/destinations and borrowed cards are rejected. Missing cards or unexpected sources abort the entire call before mutation. Each changed batch is one undo step.

The result includes selected card/note IDs, observed old and destination deck IDs, source/destination names and moved/selected counts. Verify with `search_notes` and `list_decks`.

## Retry and concurrency

After a timeout, retry the **identical arguments**. A deck already at the desired name returns `already_applied: true` with zero changed decks. Cards already at the destination are skipped. No-op retries add no undo entry. These checks survive connector/Anki restarts without a receipt database.

`expected_name` prevents a rename from overwriting a later rename. `expected_deck_id` prevents a move from taking cards from an unexpected third deck. If either precondition fails, inspect current state and get fresh authorization. These are desired-state operations, not permanent exactly-once receipts: a later undo or move back to the original source allows the same call to apply again. Retry counts and old names describe the state observed during that call, not the lost response. Use Anki undo to reverse an accidental organization change.

## Updating an existing installation

Both the add-on and MCP server need 0.3.0. The MCP server's initialization instructions describe the new tools; there is no separate Codex skill to install. The existing `codex mcp add anki-agent ...` registration still works with the same executable and connection-file paths.

Check `connection_status` for `addon_version` and an `operations` list containing `rename_deck` and `move_cards`. An older add-on may have neither field and cannot execute the tools. Reload the MCP client after updating its package to refresh tool discovery and instructions.

Updating an already-loaded add-on needs a coordinated Anki restart. Tell the user and obtain approval before closing/restarting Anki or changing a running connector, particularly when another agent session is using it. Do not hot-reload loaded modules. Normal operations after the update keep Anki open. Until the upgrade is scheduled, report the missing capability; do not fall back to screen automation.
