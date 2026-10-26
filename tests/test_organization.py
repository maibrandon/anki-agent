"""Exercise native Anki backend transactions only on temporary collections."""
import copy
import json

import pytest

from anki_agent.errors import AgentError
from anki_agent.service import Service


def deck(col, name):
    return col.decks.add_normal_deck_with_name(name).id


def note(col, did, text='{{c1::one}} and {{c2::two}}'):
    n = col.new_note(col.models.by_name('Cloze'))
    n['Text'] = text
    col.add_note(n, did)
    return n


def schedule(col, cid):
    c = col.get_card(cid)
    return {key: getattr(c, key) for key in ('id', 'nid', 'ord', 'type', 'queue', 'due', 'ivl', 'factor', 'reps', 'lapses', 'left', 'odue', 'odid', 'flags', 'custom_data')}


def test_rename_promote_reparent_descendants_preserve_settings_and_undo(service, col):
    old_parent = deck(col, 'Course::Practice Sources')
    did = deck(col, 'Course::Practice Sources::Official Questions')
    child = deck(col, 'Course::Practice Sources::Official Questions::Hard')
    destination = deck(col, 'Archive')
    note(col, did)
    note(col, child, '{{c1::child}}')
    ids = list(col.find_cards(''))
    schedules = {cid: schedule(col, cid) for cid in ids}
    settings = {i: copy.deepcopy(col.decks.get(i)) for i in (did, child)}
    p = service.dispatch(col, 'rename_deck', {'deck_id': did, 'new_name': 'Course midterm practise', 'expected_name': settings[did]['name']}).payload
    json.dumps(p)
    assert p['changed_deck_count'] == 2 and p['affected_card_count'] == 3
    assert set(p['affected_deck_ids']) == {did, child}
    assert col.decks.get(old_parent)['name'] == 'Course::Practice Sources'
    assert col.decks.get(child)['name'] == 'Course midterm practise::Hard'
    for i in (did, child):
        after = col.decks.get(i)
        assert {k: v for k, v in after.items() if k not in ('name', 'mod', 'usn')} == {k: v for k, v in settings[i].items() if k not in ('name', 'mod', 'usn')}
    again = Service().rename_deck(col, did, 'Course midterm practise', settings[did]['name']).payload
    assert again['already_applied'] and again['changed_deck_count'] == 0
    col.undo()  # Retry did not add an undo entry.
    assert col.decks.get(did)['name'] == settings[did]['name']
    service.rename_deck(col, did, 'Archive::Questions', settings[did]['name'])
    assert col.decks.get(child)['name'] == 'Archive::Questions::Hard'
    assert col.decks.get(destination)['name'] == 'Archive'
    assert {cid: schedule(col, cid) for cid in ids} == schedules
    col.undo()
    assert col.decks.get(child)['name'] == settings[child]['name']


def test_collision_rejected_including_case_and_unicode(service, col):
    did = deck(col, 'Source')
    child = deck(col, 'Source::Child')
    deck(col, 'Taken::Child')
    deck(col, 'Café')
    for target in ('Taken', 'taken', 'Cafe\u0301'):
        with pytest.raises(AgentError) as e:
            service.rename_deck(col, did, target, 'Source')
        assert e.value.code == 'deck_collision'
        assert col.decks.get(did)['name'] == 'Source'
        assert col.decks.get(child)['name'] == 'Source::Child'


@pytest.mark.parametrize('name', [None, '', ' X', 'X ', 'A::::B', 'A:::B', ':X', 'A:: B', 'A\nB', 'A\x7fB', 'A'*101])
def test_bad_names_never_write(service, col, name):
    did = deck(col, 'Source')
    with pytest.raises(AgentError):
        service.rename_deck(col, did, name, 'Source')
    assert col.decks.get(did)['name'] == 'Source'


def test_reject_cycles_missing_parent_default_filtered_and_stale(service, col):
    did = deck(col, 'Source')
    deck(col, 'Source::Child')
    filtered = col.decks.new_filtered('Filtered')
    for args, code in [
        ((did, 'Source::Renamed', 'Source'), 'deck_cycle'),
        ((did, 'Source::Child::Renamed', 'Source'), 'deck_cycle'),
        ((did, 'Missing::Renamed', 'Source'), 'parent_not_found'),
        ((did, 'Filtered::Renamed', 'Source'), 'filtered_deck'),
        ((1, 'Renamed', 'Default'), 'protected_deck'),
        ((filtered, 'Renamed', 'Filtered'), 'filtered_deck'),
        ((9999999, 'Renamed', 'Missing'), 'deck_not_found'),
        ((True, 'Renamed', 'Source'), 'invalid_deck'),
        ((did, 'Renamed', 'Stale name'), 'deck_changed'),
    ]:
        with pytest.raises(AgentError) as e:
            service.rename_deck(col, *args)
        assert e.value.code == code
    assert col.decks.get(did)['name'] == 'Source'
    assert col.decks.by_name('Missing') is None


def test_filtered_descendant_blocks_whole_tree(service, col):
    did = deck(col, 'Source')
    col.decks.new_filtered('Source::Filtered')
    with pytest.raises(AgentError, match='Filtered'):
        service.rename_deck(col, did, 'Renamed', 'Source')
    assert col.decks.get(did)['name'] == 'Source'


def test_move_cards_preserves_scheduling_siblings_ids_retry_and_undo(service, col):
    src, dst = deck(col, 'Source'), deck(col, 'Destination')
    n = note(col, src)
    first, sibling = col.card_ids_of_note(n.id)
    card = col.get_card(first)
    card.type, card.queue, card.ivl, card.factor = 2, 2, 123, 2350
    card.reps, card.lapses, card.due, card.flags = 25, 2, 456, 3
    col.update_card(card)
    before = {cid: schedule(col, cid) for cid in (first, sibling)}
    result = service.dispatch(col, 'move_cards', {'card_ids': [first], 'deck_id': dst, 'expected_deck_id': src}).payload
    json.dumps(result)
    assert result['moved_count'] == 1 and result['note_ids'] == [n.id]
    assert result['cards'] == [{'card_id': first, 'old_deck_id': src, 'new_deck_id': dst}]
    assert col.get_card(first).did == dst and col.get_card(sibling).did == src
    assert {cid: schedule(col, cid) for cid in (first, sibling)} == before
    assert Service().move_cards(col, [first], dst, src).payload['already_applied']
    col.undo()
    assert col.get_card(first).did == src
    assert col.note_count() == 1 and col.card_count() == 2
    assert {cid: schedule(col, cid) for cid in (first, sibling)} == before
    found = service.search_notes(col)['notes'][0]
    assert found['cards'][0]['deck_id'] == src and found['card_ids'] == list(col.card_ids_of_note(n.id))


def test_move_batch_all_or_nothing_and_source_precondition(service, col):
    src, dst, other = (deck(col, n) for n in ('Source', 'Destination', 'Other'))
    n = note(col, src)
    first, second = col.card_ids_of_note(n.id)
    col.set_deck([second], other)
    with pytest.raises(AgentError) as e:
        service.move_cards(col, [first, second], dst, src)
    assert e.value.code == 'card_changed' and col.get_card(first).did == src
    with pytest.raises(AgentError) as e:
        service.move_cards(col, [first, 9999999], dst, src)
    assert e.value.code == 'card_not_found' and col.get_card(first).did == src
    # A mixed retry skips cards at the destination and moves only source cards.
    col.set_deck([second], dst)
    r = service.move_cards(col, [first, second], dst, src).payload
    assert r['moved_count'] == 1 and r['selected_count'] == 2


@pytest.mark.parametrize('ids', [None, [], [True], [-1], [1, 1], list(range(1, 502)), 'cards'])
def test_move_invalid_selection(service, col, ids):
    with pytest.raises(AgentError) as e:
        service.move_cards(col, ids, 1, 1)
    assert e.value.code == 'invalid_cards'


def test_move_filtered_cards_and_bad_destination_never_write(service, col):
    src, dst = deck(col, 'Source'), deck(col, 'Destination')
    filtered = col.decks.new_filtered('Filtered')
    n = note(col, src)
    first, second = col.card_ids_of_note(n.id)
    for target in (9999999, filtered, True, None):
        with pytest.raises(AgentError):
            service.move_cards(col, [first], target, src)
        assert col.get_card(first).did == src
    card = col.get_card(second)
    card.odid, card.did = src, filtered
    col.update_card(card)
    with pytest.raises(AgentError):
        service.move_cards(col, [first, second], dst, src)
    assert col.get_card(first).did == src


def test_dispatch_validates_operations_and_collection(service):
    for op in ('rename_deck', 'move_cards'):
        with pytest.raises(AgentError) as e:
            service.dispatch(None, op, {})
        assert e.value.code == 'collection_unavailable'
        with pytest.raises(AgentError) as e:
            service.validate_request(op, {'arbitrary': True})
        assert e.value.code == 'invalid_request'
    status = service.dispatch(None, 'status', {})
    assert status['addon_version'] == '0.4.0'
    assert {'rename_deck', 'move_cards'} <= set(status['operations'])


def test_older_addon_reports_coordinated_upgrade(monkeypatch):
    from anki_agent_mcp import server
    from anki_agent_mcp.client import BridgeError
    def unsupported(*args, **kwargs):
        raise BridgeError('unknown_operation', 'Operation is not supported.')
    monkeypatch.setattr(server.client, 'call', unsupported)
    with pytest.raises(ValueError, match='addon_update_required.*do not close Anki without approval'):
        server.rename_deck(123, 'New', 'Old')
