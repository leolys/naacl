"""Shape and linkage checks only; never fix semantic output."""
def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}

def arr(item):
    return {'type': 'array', 'items': item}

TEXT = {'type': 'string', 'minLength': 1}
STATUS = {'type': 'string', 'enum': ['supported', 'refuted', 'unclear']}
ASSESS = obj({'evidence': TEXT, 'status': STATUS})
SCHEMAS = {
    'read': obj({'appearance_facts': {**arr(obj({'location': TEXT, 'fact': TEXT})), 'minItems': 1, 'maxItems': 8},
                 'printed_facts': {**arr(obj({'location': TEXT, 'fact': TEXT})), 'maxItems': 8},
                 'public_definitions': arr(TEXT), 'uncertain': arr(TEXT)}),
    'verify': obj({'reviews': arr(obj({'id': TEXT,
        'O': arr(obj({'index': {'type': 'integer', 'minimum': 1}, 'evidence': TEXT, 'status': STATUS})),
        'B': obj({'reading_checked': TEXT, 'evidence': TEXT, 'status': STATUS})}))}),
    'decide': obj({'basis': TEXT, 'option_label': {'type': ['string', 'null']}}),
    'supply': obj({'records': arr(obj({'id': TEXT, 'O': arr(TEXT), 'B': TEXT}))})
}

def shape(v, s):
    kind = ('null' if v is None else 'boolean' if isinstance(v, bool) else
            'object' if isinstance(v, dict) else 'array' if isinstance(v, list) else
            'string' if isinstance(v, str) else 'integer' if isinstance(v, int) else 'number')
    kinds = s['type'] if isinstance(s['type'], list) else [s['type']]
    if kind not in kinds or ('enum' in s and v not in s['enum']):
        raise ValueError('shape/enum mismatch')
    if kind == 'object':
        if set(v) != set(s['properties']):
            raise ValueError('extra/missing fields')
        for k in v:
            shape(v[k], s['properties'][k])
    if kind == 'array':
        if len(v) < s.get('minItems', 0):
            raise ValueError('minimum items')
        if len(v) > s.get('maxItems', len(v)):
            raise ValueError('maximum items')
        for x in v:
            shape(x, s['items'])
    if kind == 'string' and s.get('minLength') and not v.strip():
        raise ValueError('empty text')
    if kind == 'integer' and v < s.get('minimum', v):
        raise ValueError('index bounds')

def validate(stage, value, context):
    shape(value, SCHEMAS[stage])
    if stage == 'read' and not value['appearance_facts']:
        raise ValueError('no appearance facts')
    if stage == 'verify':
        expected = {r['id']: r for r in context['records']}
        found = value['reviews']
        if len(found) != len(expected) or {r['id'] for r in found} != set(expected):
            raise ValueError('record coverage')
        for r in found:
            if sorted(x['index'] for x in r['O']) != list(range(1, len(expected[r['id']]['O'])+1)):
                raise ValueError('O coverage')
    if stage == 'decide' and value['option_label'] is not None and value['option_label'] not in context['options']:
        raise ValueError('nonpublic choice')
    if stage == 'supply':
        records = value['records']
        if not 1 <= len(records) <= 3 or len({r['id'] for r in records}) != len(records) or any(not r['O'] for r in records):
            raise ValueError('supply bounds')
    return value
