"""Guarded, undoable edits of existing answer fields through Anki APIs."""
import html
from .errors import AgentError


def update_note_fields(col, notes):
    if not isinstance(notes, list) or not 1 <= len(notes) <= 100:
        raise AgentError('invalid_batch', 'Provide 1-100 note updates.')
    seen, pending = set(), []
    for spec in notes:
        if not isinstance(spec, dict) or set(spec) != {'note_id', 'fields', 'expected_fields'}:
            raise AgentError('invalid_request', 'Each update requires note_id, fields, expected_fields.')
        nid, fields, expected = spec['note_id'], spec['fields'], spec['expected_fields']
        if type(nid) is not int or nid <= 0 or nid in seen:
            raise AgentError('invalid_note', 'Use distinct positive integer note IDs.')
        seen.add(nid)
        if (not isinstance(fields, dict) or not fields or not isinstance(expected, dict)
                or set(fields) != set(expected)):
            raise AgentError('invalid_fields', 'Expected fields must match updated fields exactly.')
        try:
            note = col.get_note(nid)
        except Exception:
            raise AgentError('note_not_found', 'A selected note no longer exists.') from None
        first = note.note_type()['flds'][0]['name']
        if any(k not in note or k == first for k in fields):
            raise AgentError('invalid_fields', 'Only existing non-first fields may be edited; card-generating text is protected.')
        desired = {}
        for key, value in fields.items():
            if (not isinstance(value, str) or len(value) > 20000 or '\x00' in value or '\x1f' in value
                    or not isinstance(expected[key], str)):
                raise AgentError('invalid_fields', 'Use plain text up to 20000 characters and exact current HTML as expected_fields.')
            desired[key] = html.escape(value, quote=False).replace('\n', '<br>')
            if note[key] not in (expected[key], desired[key]):
                raise AgentError('note_changed', 'A field changed since inspection; no notes were updated.', {'note_id': nid, 'field': key})
        if any(note[k] != v for k, v in desired.items()):
            for key, value in desired.items():
                note[key] = value
            pending.append(note)
    changes = col.update_notes(pending) if pending else None
    return changes, {'note_ids': sorted(seen), 'updated': len(pending), 'already_applied': not pending}
