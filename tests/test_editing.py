import pytest
from anki_agent.errors import AgentError


def make(service, col, basic):
    p=service.preview_notes(col, [basic])
    return service.create_notes(col,p['preview_id']).payload['note_ids'][0]


def test_edit_undo_retry_and_preserve(service,col,basic):
    nid=make(service,col,basic)
    before=col.get_note(nid); cards=[(c.id,c.did,c.queue,c.due,c.ivl,c.reps) for c in before.cards()]
    updates=[{'note_id':nid,'fields':{'Back':'Clean <answer>\nExplanation'},'expected_fields':{'Back':before['Back']}}]
    result=service.dispatch(col,'update_note_fields',{'notes':updates})
    assert result.payload['updated']==1
    after=col.get_note(nid)
    assert after['Back']=='Clean &lt;answer&gt;<br>Explanation'
    assert after['Front']==before['Front'] and after.tags==before.tags
    assert [(c.id,c.did,c.queue,c.due,c.ivl,c.reps) for c in after.cards()]==cards
    assert service.update_note_fields(col,updates).payload['already_applied']
    col.undo()
    assert col.get_note(nid)['Back']==before['Back']


def test_stale_batch_does_not_partially_write(service,col,basic):
    nid=make(service,col,basic);basic['fields']['Front']='another'
    nid2=make(service,col,basic)
    with pytest.raises(AgentError,match='changed'):
        service.update_note_fields(col,[{'note_id':nid,'fields':{'Back':'clean'},'expected_fields':{'Back':basic['fields']['Back']}},{'note_id':nid2,'fields':{'Back':'clean'},'expected_fields':{'Back':'stale'}}])
    assert col.get_note(nid)['Back']==basic['fields']['Back']


@pytest.mark.parametrize('field',['Front','Missing'])
def test_protect_card_generation(service,col,basic,field):
    nid=make(service,col,basic)
    with pytest.raises(AgentError):service.update_note_fields(col,[{'note_id':nid,'fields':{field:'new'},'expected_fields':{field:'old'}}])


def test_rewrite_cloze_prompt_preserves_cards_and_scheduling(service, col):
    note = col.new_note(col.models.by_name("Cloze"))
    note["Text"] = "Old {{c1::question}} and {{c2::answer}}"
    col.add_note(note, 1)
    before = [(c.id, c.ord, c.due, c.ivl, c.reps) for c in note.cards()]
    result = service.update_note_fields(col, [{
        "note_id": note.id,
        "fields": {"Text": "Rewritten {{c2::answer}} and {{c1::question}}"},
        "expected_fields": {"Text": note["Text"]},
    }])
    updated = col.get_note(note.id)
    assert result.payload["updated"] == 1
    assert updated["Text"] == "Rewritten {{c2::answer}} and {{c1::question}}"
    assert [(c.id, c.ord, c.due, c.ivl, c.reps) for c in updated.cards()] == before
    col.undo()
    assert col.get_note(note.id)["Text"] == note["Text"]


@pytest.mark.parametrize("replacement", ["No cloze", "{{c2::changed}}", "{{c1::old}} {{c2::new}}"])
def test_reject_cloze_rewrites_that_change_card_numbers(service, col, replacement):
    note = col.new_note(col.models.by_name("Cloze"))
    note["Text"] = "{{c1::old}}"
    col.add_note(note, 1)
    with pytest.raises(AgentError, match="preserve the existing cloze"):
        service.update_note_fields(col, [{
            "note_id": note.id,
            "fields": {"Text": replacement},
            "expected_fields": {"Text": note["Text"]},
        }])
    assert col.get_note(note.id)["Text"] == note["Text"]
