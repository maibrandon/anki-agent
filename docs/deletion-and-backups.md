# Deletion and recovery backups

Version 0.2.0 adds `preview_delete_cards`, `delete_cards`, `preview_delete_deck`, `delete_deck`, and `create_backup`. `search_notes` now includes each note's card IDs so a client can select individual cards without guessing.

## Confirmation is enforced in Anki

1. Search/select exact card IDs, or select an existing normal deck ID from `list_decks`.
2. Call the appropriate read-only preview tool. Show the user the cards, subdecks, orphaned notes that would be removed, and siblings that would survive.
3. Only when the user wants the deletion, call `delete_cards(preview_id)` or `delete_deck(preview_id)`.
4. Anki shows a native confirmation dialog. **The human must click Yes.** No is the default and Escape action. Closing the dialog or waiting 30 seconds cancels. The dialog's details contain the full scope returned by preview. Agents must never control this dialog on the user's behalf.
5. After Yes, Anki revalidates the preview, exports and verifies a recovery backup, checks the request is still active and the target is unchanged, and performs the deletion as one undoable collection operation.

There is no confirmation token or boolean that an agent can supply to approve itself. The local HTTP API rejects `confirmed`, `skip_backup`, or other unknown parameters. Some MCP SDK versions may ignore extra tool arguments; these still cannot approve the native dialog. A chat message alone cannot bypass the Anki prompt. Approval capabilities exist only in memory inside the add-on and are consumed once.

Deletion previews expire after five minutes and are bound to the exact collection, operation, IDs, note content, card state, sibling membership, and deck hierarchy. Relevant edits, reviews, moves, new cards, or subdeck changes invalidate the preview. Profile close clears previews, approvals and retry receipts. Unknown IDs are rejected rather than mapped to Default. The default deck, filtered decks, and cards currently borrowed by filtered decks are protected. Return borrowed cards before previewing removal. Limits are 500 cards and 100 decks per request, with no remote override.

A successful request can be retried with the same preview ID for five minutes in the same app/profile session. It returns the completed result without another deletion. After restart, expired/unknown IDs require a new preview and a new human Yes. Deletion never re-runs a broad search at execution time.

## Card versus note versus deck

`delete_cards` removes only the listed cards. If the last card of a note is removed, Anki also removes that orphaned note. Other cards generated from that note survive. A card can be regenerated later if its note/template is edited.

`delete_deck` removes the selected normal deck and all previewed descendants and their cards. Notes with surviving cards outside the removed decks remain. Every descendant is included in the confirmation. If the scope changes, nothing is deleted.

## Backups

Every approved deletion requires a new `.apkg` recovery package exported through Anki's open collection API. It contains all current notes/cards, associated decks/note types, deck settings, scheduling and media. This avoids depending on an automatic backup that Anki may skip when it considers the collection unchanged. Backup creation does not close or reopen the collection.

Files live in the add-on's `user_files/backups/<profile-path-hash>/` directory. The result returns the exact path. Parent directories are mode 0700 and completed files mode 0600 where supported. Credentials are not exported. Files are local and unencrypted; they contain study material and should be handled like the collection itself. There is no automatic deletion or rotation of these recovery files. They may grow large when media is present.

An archive is checked for CRC errors and saved under a unique final filename before deletion can proceed. Permission failures, full disks, invalid exports, expired requests, or changed targets stop deletion. If export takes longer than the 45-second bridge deadline, the completed backup may remain, but the timed-out request must not subsequently delete anything. Allow time for the operation to finish, then preview/confirm again.

`create_backup()` makes the same recovery package on demand without deleting anything. It accepts no filesystem path or option to disable safeguards.

These packages are **not complete profile clones**: collection preferences and add-on settings are excluded. Standard `.apkg` import omits empty decks, so each package also contains `anki-agent-recovery.json` with all deck names/settings for inspection and manual recreation. Anki's normal collection backups remain available independently.

## Recovery

For an immediate mistake, use Anki's normal **Undo** before making more changes. Each deletion is one undo step.

For recovery after restarting, first import the returned `.apkg` into a separate disposable profile to inspect it. Enable scheduling/deck settings when importing. To recover a missing card whose note still exists, select the import option to always update existing notes; the tested API equivalent is `ImportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, update_notes=1, update_notetypes=1)`.

Package import merges data, rather than rolling the entire collection back. It can update existing notes/schedules depending on import options; it does not remove notes added after the backup. Inspect the import settings and only restore into the real profile with explicit user authorization. No MCP restore/import operation is exposed in this version.

## Updating

The MCP wheel and Anki add-on must both be version 0.2.0 for deletion support. Install the new `.ankiaddon` through Anki's normal add-on installer. Updating code that is already loaded requires one Anki restart; the first-install activation helper intentionally refuses to hot-reload existing code. All ordinary backup and deletion operations afterward run while Anki stays open. Reload your MCP client to discover the additional tools.

## API references

- [Anki package export through the open collection](https://docs.ankiweb.net/addons/the-anki-module)
- [Anki backups and recovery](https://docs.ankiweb.net/manual/backups)
- [Anki background collection operations](https://docs.ankiweb.net/addons/background-ops)
