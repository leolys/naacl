"""Mechanical input projection and shape validation, without semantic repairs."""
from copy import deepcopy


def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


def array(item):
    return {'type': 'array', 'items': item}


TEXT = {'type': 'string', 'minLength': 1}
STATUS = {'type': 'string', 'enum': ['supported', 'refuted', 'unclear']}
ASSESSMENT = obj({'evidence': TEXT, 'status': STATUS})
SCHEMAS = {
    'ob_verify': obj({'reviews': array(obj({
        'id': TEXT,
        'O': array(obj({'index': {'type': 'integer', 'minimum': 1}, 'evidence': TEXT, 'status': STATUS})),
        'B': obj({'visual_decoding': ASSESSMENT, 'task_applicability': ASSESSMENT})
    }))}),
    'decide': obj({'basis': TEXT, 'option_label': {'type': ['string', 'null']}})
}


def project(context, candidate_set):
    """No independent C, previous check, source/arm label, or evaluator fields."""
    return {**{k: deepcopy(context[k]) for k in ('goal', 'public_task', 'options')},
            'records': [{'id': 'r%d' % (i + 1), 'O': deepcopy(c['O']), 'B': deepcopy(c['B'])}
                        for i, c in enumerate(candidate_set['chains'])]}


def decision_input(projected, reviews):
    return {**deepcopy(projected), 'ob_checks': deepcopy(reviews['reviews'])}


def shape(value, schema):
    kind = ('null' if value is None else 'boolean' if isinstance(value, bool)
            else 'object' if isinstance(value, dict) else 'array' if isinstance(value, list)
            else 'string' if isinstance(value, str) else 'integer' if isinstance(value, int) else 'number')
    expected = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    if kind not in expected or ('enum' in schema and value not in schema['enum']):
        raise ValueError('Invalid shape or enum')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError('Missing or extra fields')
        for k, v in value.items():
            shape(v, schema['properties'][k])
    elif kind == 'array':
        for v in value:
            shape(v, schema['items'])
    elif kind == 'string' and schema.get('minLength') and not value.strip():
        raise ValueError('Blank text')
    elif kind == 'integer' and value < schema.get('minimum', value):
        raise ValueError('Index out of bounds')


def validate(stage, value, context):
    shape(value, SCHEMAS[stage])
    if stage == 'ob_verify':
        reviews = value['reviews']
        expected = {r['id']: r for r in context['records']}
        if len(reviews) != len(expected) or {r['id'] for r in reviews} != set(expected):
            raise ValueError('Each record must have exactly one review')
        for r in reviews:
            indices = [v['index'] for v in r['O']]
            if sorted(indices) != list(range(1, len(expected[r['id']]['O']) + 1)):
                raise ValueError('Each O item must have exactly one check')
    elif value['option_label'] is not None and value['option_label'] not in context['options']:
        raise ValueError('Choice is not a public option')
    return value
