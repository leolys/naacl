"""Three generated fields; metadata and reversible adaptation are code-owned."""
from bindings import records

EMPTY = {'O': [], 'B': '', 'C': ''}
SCHEMA = records.obj({'O': records.array({'type': 'string', 'minLength': 1}),
                      'B': {'type': 'string'}, 'C': {'type': 'string'}})


def validate(data):
    records.shape(data, SCHEMA)
    if data != EMPTY and (not data['O'] or not data['B'].strip() or not data['C'].strip()):
        raise ValueError('Either a complete three-field record or the exact empty record is required')
    return data


def adapt(data, identifier, public_options):
    """Add fields required by the frozen verifier without inserting reasoning."""
    if data == EMPTY:
        return None
    return {'id': identifier,
            'O': [{'location': 'Location stated in content', 'content': text} for text in data['O']],
            'B': {'rule': data['B'], 'conditions': []},
            'C': {'claim': data['C'], 'option_label': data['C'] if data['C'] in public_options else None}}


def recover(chain):
    return {'O': [o['content'] for o in chain['O']], 'B': chain['B']['rule'], 'C': chain['C']['claim']}


def action_relation(candidate, data):
    expected = candidate['candidate'].get('option_label') or candidate['candidate']['claim']
    return {'expected': expected, 'returned': data['C'], 'exact_match': expected == data['C'],
            'note': 'Exact action text only; not a semantic fidelity or correctness judgment.'}
