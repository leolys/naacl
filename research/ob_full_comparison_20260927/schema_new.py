"""Task-indexed output shape: no semantic repair and no evaluator information."""
import copy


def obj(fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields), 'additionalProperties': False}


def arr(item, maximum=None):
    value = {'type': 'array', 'items': item}
    if maximum is not None:
        value['maxItems'] = maximum
    return value


TEXT = {'type': 'string', 'minLength': 1}
STATUS = {'type': 'string', 'enum': ['supported', 'refuted', 'unclear']}
ASSESS = obj({'evidence': TEXT, 'status': STATUS})
READ = obj({'appearance_facts': {**arr(obj({'location': TEXT, 'fact': TEXT}), 8), 'minItems': 1},
            'printed_facts': arr(obj({'location': TEXT, 'fact': TEXT}), 8),
            'public_definitions': arr(TEXT), 'uncertain': arr(TEXT)})


def output_schema(stage, context):
    if stage == 'read':
        return copy.deepcopy(READ)
    if stage == 'decide':
        return obj({'basis': TEXT, 'option_label': {'type': ['string', 'null'], 'enum': context['options'] + [None]}})
    if stage == 'verify':
        return obj({'reviews': obj({r['id']: obj({
            'O': obj({str(i): copy.deepcopy(ASSESS) for i in range(1, len(r['O'])+1)}),
            'B': obj({'reading_checked': TEXT, 'evidence': TEXT, 'status': STATUS})}) for r in context['records']})})
    raise ValueError('unsupported stage')


def shape(value, schema):
    kind = ('null' if value is None else 'boolean' if isinstance(value, bool) else
            'object' if isinstance(value, dict) else 'array' if isinstance(value, list) else
            'string' if isinstance(value, str) else 'integer' if isinstance(value, int) else 'number')
    kinds = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    if kind not in kinds or ('enum' in schema and value not in schema['enum']):
        raise ValueError('shape/enum mismatch')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError('object key coverage')
        for key, child in value.items():
            shape(child, schema['properties'][key])
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            raise ValueError('array bounds')
        for child in value:
            shape(child, schema['items'])
    elif kind == 'string' and schema.get('minLength') and not value.strip():
        raise ValueError('empty text')


def validate(stage, value, context):
    shape(value, output_schema(stage, context))
    return value
