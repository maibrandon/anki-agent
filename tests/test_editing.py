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
