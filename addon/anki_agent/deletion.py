"""Immutable deletion previews and in-process human approval capabilities.

No wire parameter can create an approval. Only the Anki integration calls approve
following an affirmative response to its native confirmation dialog.
"""
from dataclasses import dataclass
import hashlib
import json
import secrets
import time

from .backups import create_recovery_backup
from .errors import AgentError

DELETE_TTL = 300
MAX_DELETE_CARDS = 500
MAX_DELETE_DECKS = 100
DELETE_OPERATIONS = {"delete_cards", "delete_deck"}


@dataclass
class Plan:
    col: object
    kind: str
    selector: object
    fingerprint: str
    summary: dict
    created: float


class Deletions:
    def __init__(self, backup_root=None):
        self.backup_root = backup_root
        self.plans = {}
        self.grants = {}
        self.completed = {}

    def clear(self):
        self.plans.clear()
        self.grants.clear()
        self.completed.clear()

    def _snapshot(self, col, kind, selector):
        decks = []
        if kind == "delete_cards":
            if not isinstance(selector, list) or not 1 <= len(selector) <= MAX_DELETE_CARDS or any(type(i) is not int or i <= 0 for i in selector) or len(set(selector)) != len(selector):
                raise AgentError("invalid_target", f"Provide 1–{MAX_DELETE_CARDS} distinct positive card IDs.")
            ids = sorted(selector)
        elif kind == "delete_deck":
            if type(selector) is not int or selector <= 0 or selector == 1:
                raise AgentError("invalid_target", "Supply a normal deck ID. The built-in Default deck cannot be deleted.")
            deck = col.decks.get(selector, default=False)
            if not deck:
                raise AgentError("target_missing", "Deck no longer exists.")
            deck_ids = col.decks.deck_and_child_ids(selector)
            if len(deck_ids) > MAX_DELETE_DECKS:
                raise AgentError("deletion_limit", f"At most {MAX_DELETE_DECKS} decks can be removed at once.")
            decks = [col.decks.get(i, default=False) for i in sorted(deck_ids)]
            if any(d is None or d.get("dyn") or d["id"] == 1 for d in decks):
                raise AgentError("invalid_target", "Filtered decks and the Default deck are protected.")
            ids = sorted(col.decks.cids(selector, children=True))
            # Include the native count of home cards borrowed by filtered decks.
            # Reject this situation rather than silently omitting affected cards.
            if col.decks.card_count(selector, include_subdecks=True) != len(ids):
                raise AgentError("filtered_cards", "Return borrowed cards from filtered decks before deleting this deck.")
        else:
            raise AgentError("invalid_target", "Unknown deletion operation.")
        if len(ids) > MAX_DELETE_CARDS:
            raise AgentError("deletion_limit", f"At most {MAX_DELETE_CARDS} cards can be removed at once.")
        cards, note_objects, metadata = [], {}, []
        for cid in ids:
            try:
                card = col.get_card(cid)
                note = col.get_note(card.nid)
            except Exception:
                raise AgentError("target_missing", "A selected card or note no longer exists; preview again.") from None
            if card.odid:
                raise AgentError("filtered_cards", "Return selected cards from filtered decks before deleting them.")
            deck = col.decks.get(card.did, default=False)
            if not deck or deck.get("dyn"):
                raise AgentError("invalid_target", "Selected cards must belong to normal decks.")
            note_objects[note.id] = note
            metadata.append(card._to_backend_card().SerializeToString().hex())
            cards.append({"id": card.id, "note_id": note.id, "deck_id": card.did,
                          "deck": deck["name"], "template_ordinal": card.ord,
                          "note_type": note.note_type()["name"],
                          "fields": {k: v[:500] for k, v in note.items()}})
        selected = set(ids)
        orphaned = []
        preserved = []
        for nid, note in sorted(note_objects.items()):
            siblings = sorted(col.card_ids_of_note(nid))
            if selected.issuperset(siblings):
                orphaned.append(nid)
            preserved.extend(i for i in siblings if i not in selected)
            metadata.append(note._to_backend_note().SerializeToString().hex())
            metadata.append(note.note_type())
            # Sibling membership/deck/scheduling changes invalidate the preview too.
            metadata.extend(col.get_card(i)._to_backend_card().SerializeToString().hex() for i in siblings)
        summary = {"operation": kind, "cards": cards, "card_ids": ids, "card_count": len(ids),
                   "decks": [{"id": d["id"], "name": d["name"]} for d in decks],
                   "deck_count": len(decks), "note_ids_deleted": orphaned,
                   "note_count_deleted": len(orphaned), "sibling_card_ids_preserved": sorted(preserved),
                   "backup_required": True, "confirmation_required": "Explicit Yes in Anki; default is No."}
        fingerprint = hashlib.sha256(json.dumps([metadata, decks, summary], sort_keys=True).encode()).hexdigest()
        return summary, fingerprint

    def preview(self, col, kind, selector):
        summary, fingerprint = self._snapshot(col, kind, selector)
        now = time.monotonic()
        self.plans = {k: p for k, p in self.plans.items() if now - p.created < DELETE_TTL}
        self.completed = {k: value for k, value in self.completed.items() if now - value[0] < DELETE_TTL}
        if len(self.plans) + len(self.completed) >= 100:
            raise AgentError("too_many_previews", "Too many deletion previews; wait for them to expire.")
        preview_id = secrets.token_hex(16)
        self.plans[preview_id] = Plan(col, kind, selector.copy() if isinstance(selector, list) else selector,
                                      fingerprint, summary, now)
        return {**summary, "preview_id": preview_id, "expires_in_seconds": DELETE_TTL, "writes_performed": False}

    def resolve(self, col, kind, preview_id):
        if not isinstance(preview_id, str) or preview_id not in self.plans:
            raise AgentError("invalid_preview", "Preview these deletion targets again first.")
        plan = self.plans[preview_id]
        if plan.col is not col or plan.kind != kind or time.monotonic() - plan.created >= DELETE_TTL:
            raise AgentError("preview_expired", "Deletion preview expired or belongs to a different collection/operation.")
        _, fingerprint = self._snapshot(col, kind, plan.selector)
        if fingerprint != plan.fingerprint:
            raise AgentError("preview_changed", "Targets changed after preview; preview and confirm again.")
        return plan

    def replay(self, col, kind, preview_id):
        if not isinstance(preview_id, str):
            return None
        record = self.completed.get(preview_id)
        if record and record[1] is col and record[2] == kind and time.monotonic() - record[0] < DELETE_TTL:
            return {**record[3], "replayed": True}
        return None

    def approve(self, col, kind, preview_id, displayed_plan):
        # INTERNAL ONLY: invoked by the main-thread native Yes callback.
        plan = self.plans.get(preview_id)
        if plan is None or plan is not displayed_plan or plan.col is not col or plan.kind != kind:
            raise AgentError("confirmation_required", "A matching human confirmation is required.")
        grant = object()
        self.grants[grant] = (preview_id, displayed_plan)
        return grant

    def execute(self, col, kind, preview_id, grant, check_active=lambda: None):
        approval = self.grants.pop(grant, None)
        if approval is None or approval[0] != preview_id:
            raise AgentError("confirmation_required", "Deletion requires an explicit Yes in Anki.")
        plan = self.resolve(col, kind, preview_id)
        if approval[1] is not plan:
            raise AgentError("confirmation_required", "Confirmation no longer matches this preview.")
        check_active()
        backup = create_recovery_backup(col, self.backup_root)
        # Export may take time. Never delete on a timed-out request or stale scope.
        check_active()
        self.resolve(col, kind, preview_id)
        if kind == "delete_cards":
            result = col.remove_cards_and_orphaned_notes(plan.summary["card_ids"])
        else:
            result = col.decks.remove([plan.selector])
        payload = {"deleted_cards": plan.summary["card_count"], "deleted_notes": plan.summary["note_count_deleted"],
                   "deleted_decks": plan.summary["deck_count"], "backup": backup, "replayed": False}
        self.completed[preview_id] = (time.monotonic(), col, kind, payload)
        self.plans.pop(preview_id, None)
        return result.changes, payload
