"""Versioned, state-blind actor syntax adapter. Never trust model-made receipts."""
import json

from research.decision_evidence_audit import core, models

VERSION = 'actor_action_envelope_v2'
ACTOR_PHASES = {'prefix', 'actor_continuation'}
FIELDS = {'action', 'text', 'select_name', 'option_text'}
KINDS = {'click_link', 'click_button', 'submit_form', 'select_option', 'finish'}


def normalize(text):
    """Accept one JSON envelope only; leave already-flat output byte-identical."""
    stripped = text.strip()
    if stripped.startswith('```json\n') and stripped.endswith('```'):
        stripped = stripped[8:-3].strip()
    elif stripped.startswith('```\n') and stripped.endswith('```'):
        stripped = stripped[4:-3].strip()
    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return text, dict(status='unchanged_non_envelope')
    if not isinstance(parsed, dict) or not isinstance(parsed.get('action'), dict):
        return text, dict(status='unchanged_non_envelope')
    inner = parsed['action']
    kind = inner.get('action')
    required = ('select_name', 'option_text') if kind == 'select_option' else ('text',)
    if kind == 'submit_form' or kind == 'finish':
        required = ()  # Preserve default submit text and ordinary no-submit stopping.
    valid = (isinstance(kind, str) and kind in KINDS
             and all(isinstance(inner.get(k), str) and inner[k].strip() for k in required)
             and all(isinstance(v, str) for k, v in inner.items() if k in FIELDS))
    if not valid:
        return '{"action":"invalid"}', dict(status='rejected_invalid_envelope')
    action = {k: v for k, v in inner.items() if k in FIELDS}
    return json.dumps(action, ensure_ascii=False), dict(status='unwrapped', normalized_action=action,
        discarded_outer_fields=sorted(k for k in parsed if k != 'action'),
        discarded_inner_fields=sorted(k for k in inner if k not in FIELDS))


class ActionCodecModel(models.RecordedModel):
    def call(self, **kwargs):
        # Base recorder writes untouched model text first. No request changes.
        reply = super().call(**kwargs)
        if kwargs['phase'] not in ACTOR_PHASES:
            return reply
        normalized, audit = normalize(reply.text)
        request_id = reply.metadata['request_id']
        path = kwargs['response_dir'].parent / 'action_codec' / (request_id + '.json')
        core.write_json(path, dict(version=VERSION, phase=kwargs['phase'], request_id=request_id,
            raw_response_path=str(kwargs['response_dir'] / (request_id + '.json')),
            normalized_text=normalized, **audit))
        return models.ModelReply(normalized, dict(reply.metadata, action_codec=VERSION,
            action_codec_audit=str(path)))
