"""Structural validation only; there is no truth, gold, or semantic acceptance gate."""
from copy import deepcopy


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array(item, maximum=None, minimum=0):
    result = {'type': 'array', 'items': item, 'minItems': minimum}
    if maximum is not None:
        result['maxItems'] = maximum
    return result


TEXT = {'type': 'string', 'minLength': 1}
C = obj({'claim': TEXT, 'option_label': {'type': ['string', 'null']}})
B = obj({'rule': TEXT, 'conditions': array(TEXT)})
OBS = obj({'location': TEXT, 'content': TEXT})
CHAIN = obj({'id': TEXT, 'O': array(OBS, minimum=1), 'B': B, 'C': C})
PROPOSAL = obj({'id': TEXT, 'candidate': C, 'visual_cues': array(TEXT, minimum=1),
                'reading_to_try': TEXT, 'assumptions': array(TEXT)})
SCHEMAS = {
    'propose': obj({'proposals': array(PROPOSAL, maximum=2), 'notes': TEXT}),
    'expand': obj({'proposal_id': TEXT, 'outcome': {'type': 'string', 'enum': ['expanded', 'unexpanded']},
                   'chains': array(CHAIN, maximum=1), 'reason': TEXT}),
    'verify': obj({'checks': array(obj({'chain_id': TEXT,
               'O_status': {'type': 'string', 'enum': ['supported', 'refuted', 'uncertain']},
               'B_status': {'type': 'string', 'enum': ['supported', 'refuted', 'uncertain']},
               'inference': {'type': 'string', 'enum': ['valid', 'invalid', 'incomplete']},
               'reason': TEXT, 'visible_evidence': array(TEXT)}), maximum=6), 'summary': TEXT})}


def shape(value, schema):
    kind = ('null' if value is None else 'boolean' if isinstance(value, bool) else 'object' if isinstance(value, dict)
            else 'array' if isinstance(value, list) else 'string' if isinstance(value, str) else 'number')
    expected = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
    if kind not in expected or ('enum' in schema and value not in schema['enum']):
        raise ValueError('Record shape/enum mismatch')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ValueError('Missing or extra record fields')
        for key in value:
            shape(value[key], schema['properties'][key])
    elif kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', float('inf')):
            raise ValueError('Record array outside limits')
        for item in value:
            shape(item, schema['items'])
    elif kind == 'string' and schema.get('minLength', 0) and not value.strip():
        raise ValueError('Blank required record text')


def unique(records, key):
    ids = [r[key] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate record IDs')
    return set(ids)


def validate(stage, data, context):
    shape(data, SCHEMAS[stage])
    if stage == 'propose':
        unique(data['proposals'], 'id')
        candidates = [p['candidate'] for p in data['proposals']]
    elif stage == 'expand':
        if data['proposal_id'] != context['proposal']['id']:
            raise ValueError('Expansion references another proposal')
        if (data['outcome'] == 'expanded') != bool(data['chains']):
            raise ValueError('Expansion outcome/chain count mismatch')
        unique(data['chains'], 'id')
        candidates = [c['C'] for c in data['chains']]
    else:
        if unique(data['checks'], 'chain_id') != unique(context['chains'], 'id'):
            raise ValueError('Verifier must cover every supplied chain exactly once')
        candidates = []
    if any(c['option_label'] is not None and c['option_label'] not in context['options'] for c in candidates):
        raise ValueError('Candidate label is not an exact public option')
    return data


def assemble(initial, proposals, expansions):
    """Retain ALL records, even retargeted or same-action ones; only rename IDs."""
    chains, links = deepcopy(initial['chains']), []
    for index, proposal in enumerate(proposals['proposals']):
        expansion = expansions[index]
        link = {'proposal_id': proposal['id'], 'proposal': deepcopy(proposal),
                'expansion_status': expansion['status'], 'chain_ids': []}
        if expansion['status'] == 'accepted':
            data = expansion['data']
            link.update(outcome=data['outcome'], reason=data['reason'])
            for chain in data['chains']:
                chain = deepcopy(chain)
                chain['id'] = 'proposal_%02d_%s' % (index, chain['id'])
                if chain['id'] in {c['id'] for c in chains}:
                    raise ValueError('New ID collides with preserved initial chain')
                link['chain_ids'].append(chain['id'])
                link['same_action_label'] = chain['C']['option_label'] == proposal['candidate']['option_label']
                link['same_claim_text'] = chain['C']['claim'] == proposal['candidate']['claim']
                # These are audit signals, NOT a filter or semantic equality judgment.
                chains.append(chain)
        else:
            link['error'] = expansion.get('error')
        links.append(link)
    return {'chains': chains, 'proposal_links': links,
            'note': 'No semantic deduplication or selection performed; unexpanded proposals remain here.'}
