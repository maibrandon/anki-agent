import pytest

from anki.consts import QUEUE_TYPE_SUSPENDED

from anki_agent.errors import AgentError


def test_suspend_exact_card_is_retryable_and_undoable(service, col):
    note = col.new_note(col.models.by_name("Cloze"))
    note["Text"] = "{{c1::first}} and {{c2::second}}"
    col.add_note(note, 1)
    first, sibling = note.cards()
    result = service.dispatch(col, "suspend_cards", {"card_ids": [first.id]})
    assert result.payload["suspended_count"] == 1
    assert col.get_card(first.id).queue == QUEUE_TYPE_SUSPENDED
    assert col.get_card(sibling.id).queue == sibling.queue
    assert service.suspend_cards(col, [first.id]).payload["already_applied"]
    col.undo()
    assert col.get_card(first.id).queue == first.queue


def test_suspend_missing_card_rejects_entire_batch(service, col):
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = "Question"
    col.add_note(note, 1)
    card, = note.cards()
    with pytest.raises(AgentError, match="no cards were suspended"):
        service.suspend_cards(col, [card.id, 1])
    assert col.get_card(card.id).queue == card.queue
