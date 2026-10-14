import zipfile
from pathlib import Path

import pytest

from anki_agent.deletion import Deletions
from anki_agent.errors import AgentError


@pytest.fixture
def deletion(tmp_path):
    return Deletions(tmp_path / "recovery")


def add_note(col, name="Basic", text="Question", deck="To delete"):
    model = col.models.by_name(name)
    n = col.new_note(model)
    n.fields[0] = text
    n.fields[1] = "Answer"
    col.add_note(n, col.decks.id(deck))
    return n


def grant(deletion, col, kind, preview):
    plan = deletion.resolve(col, kind, preview["preview_id"])
    return deletion.approve(col, kind, preview["preview_id"], plan)


def test_card_preview_readonly_and_no_approval_no_deletion(deletion, col):
    note = add_note(col)
    ids = list(col.card_ids_of_note(note.id))
    p = deletion.preview(col, "delete_cards", ids)
    assert p["card_ids"] == ids and p["note_count_deleted"] == 1
    assert col.note_count() == 1
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], object())
    assert exc.value.code == "confirmation_required"
    assert col.note_count() == 1


def test_agent_cannot_supply_yes(service, col):
    with pytest.raises(AgentError) as exc:
        service.dispatch(col, "delete_cards", {"preview_id": "x", "confirmed": True})
    assert exc.value.code == "invalid_request"
    with pytest.raises(AgentError) as exc:
        service.dispatch(col, "delete_deck", {"preview_id": "x"})
    assert exc.value.code == "confirmation_required"


def test_delete_card_keeps_cloze_sibling_backup_and_undo(deletion, col):
    note = add_note(col, "Cloze", "{{c1::one}} and {{c2::two}}")
    ids = sorted(col.card_ids_of_note(note.id))
    p = deletion.preview(col, "delete_cards", [ids[0]])
    assert p["sibling_card_ids_preserved"] == [ids[1]]
    assert p["note_count_deleted"] == 0
    changes, result = deletion.execute(col, "delete_cards", p["preview_id"], grant(deletion, col, "delete_cards", p))
    assert changes.card
    assert col.card_count() == 1 and col.note_count() == 1
    backup = Path(result["backup"]["path"])
    assert zipfile.is_zipfile(backup) and backup.stat().st_mode & 0o777 == 0o600
    assert result["deleted_notes"] == 0
    assert deletion.replay(col, "delete_cards", p["preview_id"])["replayed"]
    col.undo()
    assert col.card_count() == 2


def test_delete_deck_includes_children_and_preserves_other_deck(deletion, col):
    add_note(col, deck="Parent")
    add_note(col, text="Child question", deck="Parent::Child")
    outside = add_note(col, text="Outside", deck="Outside")
    did = col.decks.id("Parent", create=False)
    p = deletion.preview(col, "delete_deck", did)
    assert p["deck_count"] == 2 and p["card_count"] == 2
    _, result = deletion.execute(col, "delete_deck", p["preview_id"], grant(deletion, col, "delete_deck", p))
    assert result["deleted_decks"] == 2
    assert col.decks.by_name("Parent") is None
    assert col.decks.by_name("Parent::Child") is None
    assert col.note_count() == 1 and col.get_note(outside.id)
    col.undo()
    assert col.decks.by_name("Parent::Child") and col.note_count() == 3


def test_changed_note_invalidates_approval(deletion, col):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    approval = grant(deletion, col, "delete_cards", p)
    note.fields[0] = "Changed since preview"
    col.update_note(note)
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], approval)
    assert exc.value.code == "preview_changed" and col.note_count() == 1


def test_new_descendant_invalidates_deck_preview(deletion, col):
    add_note(col, deck="Parent")
    p = deletion.preview(col, "delete_deck", col.decks.id("Parent"))
    approval = grant(deletion, col, "delete_deck", p)
    col.decks.id("Parent::New")
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_deck", p["preview_id"], approval)
    assert exc.value.code == "preview_changed"


def test_backup_failure_blocks_deletion(deletion, col, monkeypatch):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    def fail(**kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(col, "export_anki_package", fail)
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], grant(deletion, col, "delete_cards", p))
    assert exc.value.code == "backup_failed" and col.card_count() == 1


def test_timeout_after_backup_does_not_delete(deletion, col):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    calls = []
    def check():
        calls.append(True)
        if len(calls) == 2:
            raise AgentError("timeout", "Expired")
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], grant(deletion, col, "delete_cards", p), check)
    assert exc.value.code == "timeout" and col.card_count() == 1


def test_expiration_and_clear_revoke_grants(deletion, col, monkeypatch):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    approval = grant(deletion, col, "delete_cards", p)
    monkeypatch.setattr("anki_agent.deletion.time.monotonic", lambda: 10**15)
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], approval)
    assert exc.value.code == "preview_expired"
    deletion.clear()
    assert not deletion.grants and not deletion.plans


@pytest.mark.parametrize("ids", [[], [True], [0], [-1], [1, 1], list(range(1, 502))])
def test_rejects_invalid_card_targets(deletion, col, ids):
    with pytest.raises(AgentError):
        deletion.preview(col, "delete_cards", ids)


def test_default_and_missing_deck_rejected(deletion, col):
    for did in [1, 9999999, True, None]:
        with pytest.raises(AgentError):
            deletion.preview(col, "delete_deck", did)


def test_grant_cannot_be_reused(deletion, col):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    approval = grant(deletion, col, "delete_cards", p)
    deletion.execute(col, "delete_cards", p["preview_id"], approval)
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], approval)
    assert exc.value.code == "confirmation_required"


def test_backup_restores_cards_scheduling_media_and_deck(deletion, col, tmp_path):
    from anki.collection import Collection, ImportAnkiPackageRequest, ImportAnkiPackageOptions
    note = add_note(col, "Cloze", "{{c1::one}} and {{c2::two}} <img src=\"recovery.png\">")
    col.media.write_data("recovery.png", b"test image bytes")
    ids = sorted(col.card_ids_of_note(note.id))
    card = col.get_card(ids[0])
    card.queue, card.type, card.ivl, card.reps, card.due = 2, 2, 12, 3, 42
    col.update_card(card)
    p = deletion.preview(col, "delete_cards", [ids[0]])
    _, result = deletion.execute(col, "delete_cards", p["preview_id"], grant(deletion, col, "delete_cards", p))
    restored = Collection(str(tmp_path / "restored.anki2"))
    try:
        restored.import_anki_package(ImportAnkiPackageRequest(package_path=result["backup"]["path"],
            options=ImportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, update_notes=1, update_notetypes=1)))
        assert restored.card_count() == 2 and restored.note_count() == 1
        restored_card = restored.get_card(ids[0])
        assert (restored_card.ivl, restored_card.reps, restored_card.due) == (12, 3, 42)
        assert restored.decks.by_name("To delete")
        assert (Path(restored.media.dir()) / "recovery.png").read_bytes() == b"test image bytes"
    finally:
        restored.close()
    # Also verify recovery of a missing card when its note still exists.
    col.import_anki_package(ImportAnkiPackageRequest(package_path=result["backup"]["path"],
        options=ImportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, update_notes=1, update_notetypes=1)))
    assert col.card_count() == 2 and col.note_count() == 1


def test_deleted_card_cannot_invalidate_other_plan(deletion, col):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    other = add_note(col, text="Other")
    q = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(other.id)))
    with pytest.raises(AgentError):
        deletion.execute(col, "delete_cards", q["preview_id"], grant(deletion, col, "delete_cards", p))
    assert col.card_count() == 2


def test_filtered_decks_and_borrowed_cards_are_protected(deletion, col):
    note = add_note(col, deck="Home")
    filtered = col.decks.new_filtered("Filtered")
    with pytest.raises(AgentError):
        deletion.preview(col, "delete_deck", filtered)
    card = col.get_card(list(col.card_ids_of_note(note.id))[0])
    card.odid, card.did = card.did, filtered
    col.update_card(card)
    with pytest.raises(AgentError) as exc:
        deletion.preview(col, "delete_deck", card.odid)
    assert exc.value.code == "filtered_cards"
    with pytest.raises(AgentError) as exc:
        deletion.preview(col, "delete_cards", [card.id])
    assert exc.value.code == "filtered_cards"


def test_empty_deck_can_be_deleted_with_backup(deletion, col):
    import json
    did = col.decks.id("Empty")
    p = deletion.preview(col, "delete_deck", did)
    _, result = deletion.execute(col, "delete_deck", p["preview_id"], grant(deletion, col, "delete_deck", p))
    assert result["deleted_cards"] == 0 and result["deleted_decks"] == 1
    with zipfile.ZipFile(result["backup"]["path"]) as package:
        metadata = json.loads(package.read("anki-agent-recovery.json"))
        assert any(d["name"] == "Empty" for d in metadata["decks"])
    assert col.decks.by_name("Empty") is None
    col.undo()
    assert col.decks.by_name("Empty")


def test_deck_deletion_preserves_sibling_card_in_other_deck(deletion, col):
    note = add_note(col, "Cloze", "{{c1::home}} and {{c2::outside}}", deck="Parent")
    ids = sorted(col.card_ids_of_note(note.id))
    outside = col.decks.id("Outside")
    col.set_deck([ids[1]], outside)
    p = deletion.preview(col, "delete_deck", col.decks.id("Parent"))
    assert p["note_count_deleted"] == 0
    assert p["sibling_card_ids_preserved"] == [ids[1]]
    deletion.execute(col, "delete_deck", p["preview_id"], grant(deletion, col, "delete_deck", p))
    assert col.card_count() == 1 and col.note_count() == 1
    assert col.get_card(ids[1]).did == outside


def test_profile_change_rejects_pending_deletion(deletion, col, tmp_path):
    from anki.collection import Collection
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    approval = grant(deletion, col, "delete_cards", p)
    other = Collection(str(tmp_path / "other-profile.anki2"))
    try:
        with pytest.raises(AgentError) as exc:
            deletion.execute(other, "delete_cards", p["preview_id"], approval)
        assert exc.value.code == "preview_expired"
        assert col.note_count() == 1
    finally:
        other.close()


def test_clear_revokes_approved_operation(deletion, col):
    note = add_note(col)
    p = deletion.preview(col, "delete_cards", list(col.card_ids_of_note(note.id)))
    approval = grant(deletion, col, "delete_cards", p)
    deletion.clear()
    with pytest.raises(AgentError) as exc:
        deletion.execute(col, "delete_cards", p["preview_id"], approval)
    assert exc.value.code == "confirmation_required" and col.note_count() == 1
