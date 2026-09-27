"""Simple structured-output schemas and non-semantic record validation.

No truth/correctness or topic-specific keyword filtering occurs here. A schema
pass means syntactic and reference consistency, never semantic validity.
"""

from copy import deepcopy


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _array(item, maximum=None, minimum=0):
    result = {"type": "array", "items": item, "minItems": minimum}
    if maximum is not None:
        result["maxItems"] = maximum
    return result


TEXT = {"type": "string", "minLength": 1}
CHAIN = _object({
    "id": TEXT,
    "O": _array(_object({"location": TEXT, "content": TEXT}), minimum=1),
    "B": _object({"rule": TEXT, "conditions": _array(TEXT)}),
    "C": _object({"claim": TEXT, "option_label": {"type": ["string", "null"]}}),
})
QUESTIONS = _object({
    "questions": _array(_object({"id": TEXT, "question": TEXT}), maximum=2),
    "summary": TEXT,
})
SCHEMAS = {
    "initial": _object({"chains": _array(CHAIN, maximum=3), "notes": TEXT}),
    "questions_old": deepcopy(QUESTIONS),
    "questions_new": deepcopy(QUESTIONS),
    "supplement": _object({
        "new_chains": _array(CHAIN, maximum=2),
        "question_responses": _array(_object({
            "question_id": TEXT,
            "outcome": {"type": "string", "enum": [
                "new_chain", "already_covered", "no_grounded_candidate"]},
            "new_chain_ids": _array(TEXT),
            "reason": TEXT,
        }), maximum=2),
    }),
    "verify": _object({
        "checks": _array(_object({
            "chain_id": TEXT,
            "O_status": {"type": "string", "enum": ["supported", "refuted", "uncertain"]},
            "B_status": {"type": "string", "enum": ["supported", "refuted", "uncertain"]},
            "inference": {"type": "string", "enum": ["valid", "invalid", "incomplete"]},
            "reason": TEXT,
            "visible_evidence": _array(TEXT),
        }), maximum=5),
        "summary": TEXT,
    }),
}


class ValidationError(ValueError):
    """Structural or reference error; not an assessment of model reasoning."""


def _validate_shape(value, schema, path):
    accepted = schema.get("type")
    accepted = accepted if isinstance(accepted, list) else [accepted]
    actual = ("null" if value is None else "boolean" if isinstance(value, bool)
              else "object" if isinstance(value, dict) else "array" if isinstance(value, list)
              else "string" if isinstance(value, str) else "number" if isinstance(value, (int, float))
              else "unsupported")
    if actual not in accepted:
        raise ValidationError("{}: expected {}, got {}".format(path, accepted, actual))
    if "enum" in schema and value not in schema["enum"]:
        raise ValidationError("{}: unexpected enum value".format(path))
    if actual == "object":
        props = schema["properties"]
        missing = set(schema["required"]) - set(value)
        extra = set(value) - set(props)
        if missing or extra:
            raise ValidationError("{}: missing={} extra={}".format(path, sorted(missing), sorted(extra)))
        for key, child in value.items():
            _validate_shape(child, props[key], path + "." + key)
    elif actual == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValidationError("{}: array length outside bounds".format(path))
        for index, child in enumerate(value):
            _validate_shape(child, schema["items"], "{}[{}]".format(path, index))
    elif actual == "string" and schema.get("minLength", 0) > 0 and not value.strip():
        raise ValidationError("{}: expected nonempty text".format(path))


def _ids(records, key, path):
    result = [record[key] for record in records]
    if len(result) != len(set(result)):
        raise ValidationError("{}: duplicate IDs".format(path))
    return set(result)


def _validate_chains(chains, options, path):
    ids = _ids(chains, "id", path)
    for chain in chains:
        label = chain["C"]["option_label"]
        if label is not None and label not in options:
            raise ValidationError("{}: option_label is not an exact public option".format(path))
    return ids


def validate(stage, data, context):
    """Validate without mutation and return the original data object.

    context['options'] must be exact public label strings. questions stages use
    initial_chains; supplement uses initial_chains plus questions (question
    records, not a full output wrapper); verify uses chains. No hidden labels
    or case-specific knowledge is accessed. Semantic checks are model/human work.
    """
    if stage not in SCHEMAS:
        raise ValidationError("unknown stage: " + str(stage))
    _validate_shape(data, SCHEMAS[stage], stage)
    options = context.get("options", [])
    if not isinstance(options, list) or any(not isinstance(label, str) for label in options):
        raise ValidationError("context.options must be a list of exact public strings")
    if stage == "initial":
        _validate_chains(data["chains"], options, stage)
    elif stage in ("questions_old", "questions_new"):
        _ids(data["questions"], "id", stage)
    elif stage == "supplement":
        existing = _ids(context.get("initial_chains", []), "id", "context.initial_chains")
        added = _validate_chains(data["new_chains"], options, stage)
        if existing & added:
            raise ValidationError("supplement: new chain ID collides with an initial chain")
        questions = _ids(context.get("questions", []), "id", "context.questions")
        responses = _ids(data["question_responses"], "question_id", "supplement.responses")
        if responses != questions:
            raise ValidationError("supplement: responses must cover exactly the actual question IDs")
        linked = set()
        for response in data["question_responses"]:
            refs = response["new_chain_ids"]
            if len(refs) != len(set(refs)):
                raise ValidationError("supplement: repeated new_chain_ids in response")
            if not set(refs) <= added:
                raise ValidationError("supplement: response links a nonexistent added chain")
            if (response["outcome"] == "new_chain") != bool(refs):
                raise ValidationError("supplement: outcome and new_chain_ids disagree")
            linked.update(refs)
        if linked != added:
            raise ValidationError("supplement: every new chain must be linked by a response")
    elif stage == "verify":
        supplied = _ids(context.get("chains", []), "id", "context.chains")
        checked = _ids(data["checks"], "chain_id", "verify.checks")
        if checked != supplied:
            raise ValidationError("verify: checks must cover exactly all supplied chain IDs")
    return data
