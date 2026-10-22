"""Undoable deck organization through Anki APIs, inside the collection queue."""
import unicodedata

from .errors import AgentError

MAX_MOVE_CARDS = 500


def normal_deck(col, deck_id):
    if type(deck_id) is not int or deck_id <= 0:
        raise AgentError("invalid_deck", "Provide a positive integer deck ID from list_decks.")
    deck = col.decks.get(deck_id, default=False)
    if deck is None:
        raise AgentError("deck_not_found", "The requested deck no longer exists.")
    if deck.get("dyn"):
        raise AgentError("filtered_deck", "Filtered decks are not supported for organization.")
    return deck


def deck_name(value):
    if not isinstance(value, str):
        raise AgentError("invalid_deck_name", "Provide a fully qualified deck name.")
    value = unicodedata.normalize("NFC", value)
    parts = value.split("::")
    if (not value or len(value) > 100 or any(
        not p or p != p.strip() or ":" in p for p in parts
    ) or any(unicodedata.category(c).startswith("C") for c in value)):
        raise AgentError("invalid_deck_name", "Use at most 100 characters, with nonempty trimmed components separated by :: and no control characters or other colons.")
    return value


def rename_deck(col, deck_id, new_name, expected_name):
    deck = normal_deck(col, deck_id)
    if deck_id == 1:
        raise AgentError("protected_deck", "The Default deck cannot be renamed or reparented.")
    target = deck_name(new_name)
    expected = deck_name(expected_name)
    old = deck["name"]
    ids = list(col.decks.deck_and_child_ids(deck_id))
    tree = [normal_deck(col, did) for did in ids]
    if len(tree) > 100:
        raise AgentError("scope_too_large", "Organize at most 100 decks, including descendants, at once.")
    # Same desired state is a safe no-op, including after a lost response/restart.
    if old != target and old != expected:
        raise AgentError("deck_changed", "The deck name changed; list decks and obtain fresh authorization.")
    parent_name = target.rpartition("::")[0]
    if parent_name:
        parent = col.decks.by_name(parent_name)
        if parent is None:
            raise AgentError("parent_not_found", "Create the destination parent explicitly first.")
        normal_deck(col, parent["id"])
        if parent["id"] in ids:
            raise AgentError("deck_cycle", "A deck cannot be placed beneath itself or a descendant.")
        if parent["name"] != parent_name:
            raise AgentError("invalid_deck_name", "Use the destination parent's exact name from list_decks.")
    planned = []
    for member in tree:
        name = target + member["name"][len(old):]
        deck_name(name)
        collision = col.decks.by_name(name)
        if collision is not None and collision["id"] != member["id"]:
            raise AgentError("deck_collision", "A destination name already belongs to another deck; no decks were changed.", {"name": name, "deck_id": collision["id"]})
        planned.append({"deck_id": member["id"], "old_name": member["name"], "new_name": name})
    card_count = col.decks.card_count(deck_id, include_subdecks=True)
    changes = None if old == target else col.decks.rename(deck_id, target)
    return changes, {"deck_id": deck_id, "old_name": old,
                     "new_name": col.decks.get(deck_id, default=False)["name"],
                     "decks": planned, "affected_deck_ids": ids,
                     "affected_card_count": card_count,
                     "changed_deck_count": 0 if changes is None else len(ids),
                     "already_applied": changes is None}


def move_cards(col, card_ids, deck_id, expected_deck_id):
    target = normal_deck(col, deck_id)
    source = normal_deck(col, expected_deck_id)
    if (not isinstance(card_ids, list) or not 1 <= len(card_ids) <= MAX_MOVE_CARDS
            or any(type(cid) is not int or cid <= 0 for cid in card_ids)
            or len(set(card_ids)) != len(card_ids)):
        raise AgentError("invalid_cards", f"Provide 1–{MAX_MOVE_CARDS} distinct positive integer card IDs.")
    cards = []
    for cid in card_ids:
        try:
            card = col.get_card(cid)
        except Exception:
            raise AgentError("card_not_found", "A selected card no longer exists; no cards were moved.", {"card_id": cid}) from None
        normal_deck(col, card.did)
        if card.odid:
            raise AgentError("filtered_card", "Cards borrowed by filtered decks cannot be moved.")
        if card.did not in {expected_deck_id, deck_id}:
            raise AgentError("card_changed", "A card left the expected source deck; inspect it and obtain fresh authorization.", {"card_id": cid, "deck_id": card.did})
        cards.append(card)
    pending = [card.id for card in cards if card.did != deck_id]
    changes = col.set_deck(pending, deck_id).changes if pending else None
    return changes, {"deck_id": deck_id, "deck_name": target["name"],
                     "expected_deck_id": expected_deck_id, "expected_deck_name": source["name"],
                     "card_ids": card_ids, "note_ids": sorted({card.nid for card in cards}),
                     "cards": [{"card_id": card.id, "old_deck_id": card.did, "new_deck_id": deck_id} for card in cards],
                     "selected_count": len(cards), "moved_count": len(pending),
                     "already_applied": not pending}
