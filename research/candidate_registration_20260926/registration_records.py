"""Structure checks only. A matching action label is not evidence of novelty."""
from copy import deepcopy
from dependencies import records

SCHEMAS = {'register': records.obj({'candidates': records.array(records.PROPOSAL, maximum=2)}),
           'expand': deepcopy(records.SCHEMAS['expand']),
           'verify': deepcopy(records.SCHEMAS['verify'])}


def validate(stage, data, context):
    if stage != 'register':
        return records.validate(stage, data, context)
    records.shape(data, SCHEMAS['register'])
    records.unique(data['candidates'], 'id')
    for candidate in data['candidates']:
        label = candidate['candidate']['option_label']
        if label is not None and label not in context['options']:
            raise ValueError('Not an exact public option')
    return data


def assemble(initial, registered, expansions):
    # Mechanical wrapper only: no semantic repair, candidate filtering or notes mining.
    return records.assemble(initial, {'proposals': registered['candidates']}, expansions)


def action_relations(initial, registered):
    old = [c['C']['option_label'] for c in initial['chains']]
    return [{'candidate_id': c['id'],
             'relation': ('unmapped' if c['candidate']['option_label'] is None else
                          'same_action' if c['candidate']['option_label'] in old else 'different_action'),
             'basis_novelty': 'not_determined_by_action_label'} for c in registered['candidates']]
