#!/usr/bin/env python3
"""Local actor endpoint proxy v2 — schema-guided batch (declared infra difference).

Batch B (schema-guided): forwards OpenAI-compatible chat completions to the
local vLLM server and injects a phase-appropriate response_format json_schema.
Schemas mirror ONLY the hard structural requirements that the sealed core
already enforces (typed fields, enums, id patterns, non-empty arrays where the
core raises SchemaError). No semantic constraint (existence of chain ids,
coverage completeness, evidence truth) is expressed or enforced.
Unknown system prompts fall back to response_format json_object (batch A
behaviour). Payloads/responses are otherwise forwarded unchanged.
"""
import json
import sys
from pathlib import Path

import requests as rq
from flask import Flask, Response, request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

UP = "http://127.0.0.1:8058"
app = Flask(__name__)


def S(name, top):
    return {"name": name, "schema": dict(top)}


def obj(required, properties=None, extra=None):
    d = {"type": "object", "required": list(required)}
    if properties:
        d["properties"] = properties
    if extra:
        d.update(extra)
    return d


def str_field(min_len=1):
    return {"type": "string", "minLength": min_len}


def arr(items, min_items=None):
    d = {"type": "array", "items": items}
    if min_items is not None:
        d["minItems"] = min_items
    return d


CHART_CITE = obj(["ref", "location", "content"], {
    "ref": {"type": "string", "pattern": "^chart"},
    "location": str_field(), "content": str_field()})

TASK_CITE = obj(["ref", "path", "content"], {
    "ref": {"enum": ["public_task"]}, "path": str_field(), "content": {}})

CITE = obj(["ref"], {"ref": {"type": "string"}, "location": {"type": "string"},
                     "path": {"type": "string"}, "content": {}})

RULE_ITEM = obj(["id", "text"], {"id": str_field(), "text": str_field(),
                                 "version": {"type": "integer"},
                                 "component": {"type": "string"},
                                 "conditions": {"type": "string"}})

CHAIN_ITEM = obj(["rule_id", "observations", "option_label", "claim"], {
    "chain_id": {"type": "string"}, "rule_id": {"type": "string"},
    "observations": arr(CHART_CITE, min_items=1),
    "task_evidence": arr(TASK_CITE),
    "option_label": str_field(), "claim_kind": {"type": "string"},
    "claim": str_field(), "question_ids": arr({"type": "string"}),
    "relationship": {"type": "string"}})

DIM = obj(["status", "evidence", "reason"], {
    "status": {"enum": ["supported", "refuted", "undetermined"]},
    "evidence": arr(CITE), "reason": str_field()})

QITEM = obj(["id", "target_chain_ids", "focus", "question"], {
    "id": str_field(), "target_chain_ids": arr(str_field(), min_items=1),
    "focus": {"enum": ["observations", "rule_conditions", "coverage"]},
    "question": str_field()})

SCHEMA_ACTOR = S("actor_proposal", obj(
    ["action", "brief_basis", "chart_dependent", "used_rules", "supporting_chain_ids"],
    {"action": obj(["kind"], {
        "kind": {"enum": ["open_link", "select", "fill", "check", "select_field", "submit", "unresolved"]},
        "label": {"type": "string"}, "option": {"type": "string"},
        "field": {"type": "string"}, "value": {}}),
     "brief_basis": str_field(), "chart_dependent": {"type": "boolean"},
     "used_rules": arr({}), "supporting_chain_ids": arr({}),
     "challenge": {"anyOf": [{"type": "null"}, {"type": "object"}]}}))

SCHEMA_GENERATE = S("initial_set", obj(
    ["rules", "chains"], {"rules": arr(RULE_ITEM), "chains": arr(CHAIN_ITEM)}))

SCHEMA_QUESTIONS = S("counterquestions", obj(
    ["questions", "summary"], {"questions": arr(QITEM), "summary": str_field()}))

SCHEMA_SUPPLEMENT = S("supplement", obj(
    ["new_rules", "new_chains", "refinements", "question_responses"],
    {"new_rules": arr(obj(["id", "text"], {
        "id": {"type": "string", "pattern": "^supp_r\\d+$"}, "text": str_field(),
        "version": {"type": "integer"}, "component": {"type": "string"},
        "conditions": {"type": "string"}})),
     "new_chains": arr(obj(["chain_id", "rule_id", "observations", "option_label", "claim"], {
        "chain_id": {"type": "string", "pattern": "^supp_c\\d+$"},
        "rule_id": {"type": "string"},
        "observations": arr(CHART_CITE, min_items=1),
        "task_evidence": arr(TASK_CITE),
        "option_label": str_field(), "claim_kind": {"type": "string"},
        "claim": str_field(), "question_ids": arr({"type": "string"}),
        "relationship": {"type": "string"}})),
     "refinements": arr(obj(["id", "target_chain_id"], {
        "id": {"type": "string", "pattern": "^refine_\\d+$"},
        "target_chain_id": {"type": "string"}, "target_rule_id": {"type": "string"},
        "target_rule_version": {"type": "integer"},
        "question_ids": arr({"type": "string"}), "relationship": {"type": "string"}})),
     "question_responses": arr(obj(["question_id", "outcome", "record_ids", "covered_chain_ids", "reason"], {
        "question_id": {"type": "string"},
        "outcome": {"enum": ["new_explanation", "refined_existing", "already_covered", "unresolved"]},
        "record_ids": arr({"type": "string"}), "covered_chain_ids": arr({"type": "string"}),
        "reason": str_field()}))}))

SCHEMA_VERIFY = S("verification", obj(
    ["checks", "summary"],
    {"checks": arr(obj(["target_id", "O", "B", "implication"], {
        "target_id": {"type": "string"}, "O": DIM, "B": DIM, "implication": DIM})),
     "summary": str_field()}))


def _phase_map():
    import prompts
    return [(prompts.ACTOR, SCHEMA_ACTOR), (prompts.GENERATE, SCHEMA_GENERATE),
            (prompts.QUESTIONS, SCHEMA_QUESTIONS), (prompts.SUPPLEMENT, SCHEMA_SUPPLEMENT),
            (prompts.VERIFY, SCHEMA_VERIFY)]


PHASES = None


@app.post("/v1/chat/completions")
def chat():
    global PHASES
    if PHASES is None:
        PHASES = _phase_map()
    body = request.get_json(force=True)
    fmt = {"type": "json_object"}
    messages = body.get("messages") or []
    if messages and isinstance(messages[0].get("content"), str):
        for prompt, schema in PHASES:
            if messages[0]["content"] == prompt:
                fmt = {"type": "json_schema", "json_schema": schema}
                break
    body.setdefault("response_format", fmt)
    try:
        up = rq.post(UP + "/v1/chat/completions", json=body, timeout=(10, 900))
    except rq.RequestException as e:
        msg = "proxy_upstream_%s" % type(e).__name__
        return Response(json.dumps({"error": {"message": msg, "type": "proxy_upstream_error"}}),
                        status=502, content_type="application/json")
    headers = {"Content-Type": up.headers.get("Content-Type", "application/json")}
    if "x-request-id" in up.headers:
        headers["x-request-id"] = up.headers["x-request-id"]
    return Response(up.content, status=up.status_code, headers=headers)


@app.get("/v1/models")
def models():
    r = rq.get(UP + "/v1/models", timeout=10)
    return Response(r.content, status=r.status_code,
                    content_type=r.headers.get("Content-Type", "application/json"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8059, threaded=True)
