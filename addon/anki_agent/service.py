"""Collection operations. Called only inside Anki's serialized operation queue."""
import copy
import html
import re
import secrets
import time
from dataclasses import dataclass

from .errors import AgentError
from .backups import create_recovery_backup
from .deletion import Deletions, DELETE_OPERATIONS

OPERATIONS = {"status", "list_decks", "list_note_types", "search_notes", "preview_notes", "create_notes", "create_deck", "preview_delete_cards", "preview_delete_deck", "delete_cards", "delete_deck", "create_backup"}
MAX_BATCH = 50
TTL = 600


@dataclass
class WriteResult:
    changes: object
    payload: dict


class Service:
    def __init__(self, backup_root=None):
        self.previews = {}
        self.deletions = Deletions(backup_root)

    def clear(self):
        self.previews.clear()
        self.deletions.clear()

    def validate_request(self, operation, params):
        if operation not in OPERATIONS:
            raise AgentError("unknown_operation", "Operation is not supported.")
        if not isinstance(params, dict):
            raise AgentError("invalid_request", "params must be an object.")
        allowed = {"status": set(), "list_decks": set(), "list_note_types": set(),
                   "search_notes": {"query", "limit", "offset"},
                   "preview_notes": {"notes"}, "create_notes": {"preview_id"}, "create_deck": {"name"},
                   "preview_delete_cards": {"card_ids"}, "preview_delete_deck": {"deck_id"},
                   "delete_cards": {"preview_id"}, "delete_deck": {"preview_id"}, "create_backup": set()}
        if set(params) - allowed[operation]:
            raise AgentError("invalid_request", "Unknown parameters.")

    def dispatch(self, col, operation, params):
        self.validate_request(operation, params)
        if operation == "status":
            return {"connected": True, "collection_available": col is not None,
                    "protocol_version": 1, "max_batch": MAX_BATCH}
        if col is None:
            raise AgentError("collection_unavailable", "Open an Anki profile with a collection first.")
        if operation in DELETE_OPERATIONS:
            raise AgentError("confirmation_required", "Deletion must be confirmed with Yes in Anki; request it through the Anki integration.")
        return getattr(self, operation)(col, **params)

    def create_backup(self, col):
        return create_recovery_backup(col, self.deletions.backup_root)

    def preview_delete_cards(self, col, card_ids=None):
        return self.deletions.preview(col, "delete_cards", card_ids)

    def preview_delete_deck(self, col, deck_id=None):
        return self.deletions.preview(col, "delete_deck", deck_id)

    def list_decks(self, col):
        return {"decks": [{"id": d.id, "name": d.name} for d in col.decks.all_names_and_ids()]}

    def create_deck(self, col, name=None):
        if not isinstance(name, str) or not name.strip() or name != name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
            raise AgentError("invalid_deck", "Use a nonempty deck name of at most 100 characters without control characters or surrounding whitespace.")
        existing = col.decks.by_name(name)
        if existing and existing.get("dyn"):
            raise AgentError("invalid_deck", "That name belongs to a filtered deck.")
        result = col.decks.add_normal_deck_with_name(name)
        return WriteResult(result.changes, {"deck_id": result.id, "name": col.decks.get(result.id)["name"], "created": existing is None})

    def list_note_types(self, col):
        return {"note_types": [{"id": m["id"], "name": m["name"],
                                "fields": [f["name"] for f in m["flds"]],
                                "supported": self._supported(m)} for m in col.models.all()]}

    @staticmethod
    def _supported(model):
        # Match stock structures, including localized names, rather than model names.
        fields = [f["name"] for f in model["flds"]]
        return ((model["type"] == 0 and len(fields) == 2 and len(model["tmpls"]) == 1)
                or (model["type"] == 1 and len(fields) == 2))

    def search_notes(self, col, query="", limit=20, offset=0):
        if not isinstance(query, str) or len(query) > 1000:
            raise AgentError("invalid_request", "query must be a string of at most 1000 characters.")
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise AgentError("invalid_request", "limit must be 1–100 and offset must be nonnegative.")
        try:
            ids = col.find_notes(query)
        except Exception:
            raise AgentError("invalid_search", "Invalid Anki search query.") from None
        notes = []
        for nid in ids[offset:offset + limit]:
            n = col.get_note(nid)
            notes.append({"id": n.id, "note_type": n.note_type()["name"],
                          "fields": dict(n.items()), "tags": list(n.tags),
                          "card_ids": list(col.card_ids_of_note(n.id))})
        return {"notes": notes, "total": len(ids), "offset": offset,
                "has_more": offset + limit < len(ids)}

    def _validate(self, col, specs):
        if not isinstance(specs, list) or not 1 <= len(specs) <= MAX_BATCH:
            raise AgentError("invalid_batch", f"Provide between 1 and {MAX_BATCH} notes.")
        prepared, seen, errors = [], set(), []
        for index, spec in enumerate(specs):
            try:
                if not isinstance(spec, dict) or set(spec) - {"deck", "note_type", "fields", "tags"}:
                    raise ValueError("Each note needs deck, note_type, fields, and optional tags.")
                if not isinstance(spec.get("deck"), str) or not isinstance(spec.get("note_type"), str):
                    raise ValueError("deck and note_type must be names.")
                deck = col.decks.by_name(spec["deck"])
                model = col.models.by_name(spec["note_type"])
                if not deck or deck.get("dyn"):
                    raise ValueError("Deck does not exist or is a filtered deck.")
                if not model or not self._supported(model):
                    raise ValueError("Note type must have a Basic or Cloze structure with two fields.")
                fields = spec.get("fields")
                names = [f["name"] for f in model["flds"]]
                if not isinstance(fields, dict) or set(fields) != set(names):
                    raise ValueError(f"fields must contain exactly: {', '.join(names)}.")
                if any(not isinstance(v, str) or len(v) > 20000 or "\x00" in v or "\x1f" in v for v in fields.values()):
                    raise ValueError("Fields must be text, at most 20000 characters, without NUL or field separators.")
                if not fields[names[0]].strip():
                    raise ValueError("First field cannot be empty.")
                if model["type"] == 1 and not re.search(r"\{\{c[1-9]\d*::[^{}]+\}\}", fields[names[0]]):
                    raise ValueError("Cloze text needs at least one {{c1::answer}} deletion.")
                tags = spec.get("tags", [])
                if not isinstance(tags, list) or len(tags) > 20 or any(
                    not isinstance(t, str) or not re.fullmatch(r"[\w:-]{1,100}", t) or t.startswith("anki_agent_") for t in tags
                ):
                    raise ValueError("Use at most 20 tags containing letters, digits, underscores, colons or hyphens; anki_agent_ is reserved.")
                note = col.new_note(model)
                for name in names:
                    note[name] = html.escape(fields[name], quote=False).replace("\n", "<br>")
                note.tags = list(dict.fromkeys(tags))
                key = (model["id"], note.fields[0])
                if key in seen or note.fields_check():
                    raise ValueError("Duplicate first field for this note type, or empty note.")
                seen.add(key)
                prepared.append((note, deck["id"]))
            except (ValueError, TypeError, KeyError) as exc:
                errors.append({"index": index, "message": str(exc)})
        if errors:
            raise AgentError("invalid_batch", "Batch validation failed; no notes were created.", errors)
        return prepared

    def preview_notes(self, col, notes=None):
        self._validate(col, notes)
        now = time.monotonic()
        self.previews = {k: v for k, v in self.previews.items() if now - v[0] < TTL}
        if len(self.previews) >= 100:
            raise AgentError("too_many_previews", "Too many pending previews; wait for them to expire.")
        preview_id = secrets.token_hex(16)
        self.previews[preview_id] = (now, col, copy.deepcopy(notes))
        return {"preview_id": preview_id, "expires_in_seconds": TTL, "notes": notes,
                "count": len(notes), "writes_performed": False,
                "notice": "Plain text will be escaped. This is a content preview, not rendered card HTML."}

    def create_notes(self, col, preview_id=None):
        if not isinstance(preview_id, str) or not re.fullmatch(r"[0-9a-f]{32}", preview_id):
            raise AgentError("invalid_preview", "Provide a preview_id returned by preview_notes.")
        # Provenance tag is committed atomically with the notes. Recover retries even
        # after a lost HTTP response or Anki restart, without a second database.
        marker = "anki_agent_batch_" + preview_id
        existing = list(col.find_notes("tag:" + marker))
        if existing:
            return WriteResult(None, {"note_ids": existing, "created": 0, "replayed": True})
        preview = self.previews.get(preview_id)
        if not preview or preview[1] is not col or time.monotonic() - preview[0] >= TTL:
            raise AgentError("preview_expired", "Preview expired or belongs to a different session; preview again.")
        notes = self._validate(col, preview[2])
        from anki.collection import AddNoteRequest
        for note, _ in notes:
            note.tags.append(marker)
        # Anki's backend applies add_notes as one undoable transaction.
        result = col.add_notes([AddNoteRequest(note=note, deck_id=did) for note, did in notes])
        return WriteResult(result, {"note_ids": [n.id for n, _ in notes], "created": len(notes), "replayed": False})
