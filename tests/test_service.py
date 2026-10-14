import copy
import json
import pytest
from anki_agent.errors import AgentError
from anki_agent.service import Service


def test_connection_without_collection(service):
    assert service.dispatch(None, "status", {})["collection_available"] is False
    with pytest.raises(AgentError, match="Open an Anki"):
        service.dispatch(None, "list_decks", {})
    with pytest.raises(AgentError) as err:
        service.dispatch(None, "eval", {})
    assert err.value.code == "unknown_operation"


def test_preview_create_retry_restart_and_undo(service, col, basic):
    before = col.note_count()
    preview = service.preview_notes(col, [basic])
    assert col.note_count() == before
    result = service.create_notes(col, preview["preview_id"]).payload
    assert result["created"] == 1
    assert col.card_count() == 1
    replay = Service().create_notes(col, preview["preview_id"]).payload
    json.dumps(replay)  # Anki returns protobuf containers; wire results must be JSON.
    assert replay["replayed"] and replay["note_ids"] == result["note_ids"]
    assert col.note_count() == 1
    col.undo()
    assert col.note_count() == 0


def test_basic_cloze_escape_and_search(service, col, basic):
    basic["fields"]["Front"] = "<script>alert(1)</script>\n&"
    cloze = {"deck": "Default", "note_type": "Cloze", "fields": {"Text": "{{c1::Earth}} orbits {{c2::the Sun}}.", "Back Extra": "Astronomy"}}
    preview = service.preview_notes(col, [basic, cloze])
    result = service.create_notes(col, preview["preview_id"]).payload
    assert len(result["note_ids"]) == 2
    assert col.card_count() == 3
    found = service.search_notes(col, "tag:test")
    assert found["total"] == 1
    assert found["notes"][0]["fields"]["Front"] == "&lt;script&gt;alert(1)&lt;/script&gt;<br>&amp;"
    assert service.search_notes(col, "", limit=1)["has_more"]
    assert any(d["name"] == "Default" for d in service.list_decks(col)["decks"])
    assert any(m["name"] == "Cloze" and m["supported"] for m in service.list_note_types(col)["note_types"])


@pytest.mark.parametrize("change", [
    {"deck": "Missing"}, {"fields": {"Front": "only"}},
    {"tags": ["anki_agent_reserved"]}, {"tags": ["bad tag"]},
    {"note_type": "Basic (and reversed card)"},
    {"fields": {"Front": "", "Back": "answer"}},
])
def test_invalid_batch_never_writes(service, col, basic, change):
    invalid = copy.deepcopy(basic)
    invalid.update(change)
    with pytest.raises(AgentError) as err:
        service.preview_notes(col, [basic, invalid])
    assert err.value.details[0]["index"] == 1
    assert col.note_count() == 0


def test_duplicate_within_batch_and_existing(service, col, basic):
    with pytest.raises(AgentError):
        service.preview_notes(col, [basic, basic])
    p = service.preview_notes(col, [basic])
    service.create_notes(col, p["preview_id"])
    with pytest.raises(AgentError):
        service.preview_notes(col, [basic])


def test_revalidates_before_write(service, col, basic):
    p = service.preview_notes(col, [basic])
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = basic["fields"]["Front"]
    col.add_note(note, col.decks.id("Default"))
    with pytest.raises(AgentError):
        service.create_notes(col, p["preview_id"])
    assert col.note_count() == 1


def test_preview_expiry_and_session_binding(service, col, basic, monkeypatch):
    p = service.preview_notes(col, [basic])
    monkeypatch.setattr("anki_agent.service.time.monotonic", lambda: 10**15)
    with pytest.raises(AgentError) as err:
        service.create_notes(col, p["preview_id"])
    assert err.value.code == "preview_expired"
    assert col.note_count() == 0


def test_no_cloze_marker_rejected(service, col):
    with pytest.raises(AgentError):
        service.preview_notes(col, [{"deck": "Default", "note_type": "Cloze", "fields": {"Text": "No deletion", "Back Extra": ""}}])


def test_preview_bound_to_collection(service, col, basic, tmp_path):
    from anki.collection import Collection
    p = service.preview_notes(col, [basic])
    other = Collection(str(tmp_path / "other.anki2"))
    try:
        with pytest.raises(AgentError) as err:
            service.create_notes(other, p["preview_id"])
        assert err.value.code == "preview_expired"
        assert other.note_count() == 0
    finally:
        other.close()


@pytest.mark.parametrize("notes", [[], [None], [{}], "text"])
def test_malformed_notes(service, col, notes):
    with pytest.raises(AgentError):
        service.preview_notes(col, notes)
    assert col.note_count() == 0


def test_batch_limit_and_search_bounds(service, col, basic):
    with pytest.raises(AgentError):
        service.preview_notes(col, [basic] * 51)
    with pytest.raises(AgentError):
        service.search_notes(col, limit=101)
    with pytest.raises(AgentError):
        service.search_notes(col, offset=-1)


def test_create_deck_idempotent_and_undo(service, col):
    result = service.create_deck(col, "anki-agent").payload
    assert result["created"]
    again = service.create_deck(col, "anki-agent").payload
    assert not again["created"] and again["deck_id"] == result["deck_id"]
    col.undo()
    assert col.decks.by_name("anki-agent") is None


@pytest.mark.parametrize("name", [None, "", " name ", "a\nb", "a" * 101])
def test_invalid_deck_name(service, col, name):
    with pytest.raises(AgentError):
        service.create_deck(col, name)
