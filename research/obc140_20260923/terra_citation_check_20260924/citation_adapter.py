"""Separate located public-task citations from visual evidence; never edit verdicts."""
import copy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import panel_core as core

VERSION = "public_task_citation_v1"


def source_field(public, location):
    if not isinstance(location, str) or not location.strip():
        raise ValueError("task citation needs exact public field path")
    path = location.strip()
    for prefix in ("public_task.", "task."):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    value = public
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError("task citation field unavailable: " + path)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("task citation must locate one nonempty public text field")
    return path, value


def separate_task_citations(value, public):
    core.engine.assert_public(public)
    result = copy.deepcopy(value)
    alias = public.get("task_alias")
    task_refs = {"task", "public_task"}
    if isinstance(alias, str) and alias:
        task_refs.add(alias)
    moves = []
    for check_index, check in enumerate(result.get("checks", [])):
        if "task_evidence" in check:
            raise ValueError("task_evidence is adapter-owned; raw evidence must declare its source")
        visual, task = [], []
        for evidence_index, citation in enumerate(check.get("evidence", [])):
            if citation.get("ref") == "chart_1":
                visual.append(citation)
                continue
            if citation.get("ref") not in task_refs:
                raise ValueError("unobserved evidence source")
            if not isinstance(citation.get("content"), str) or not citation["content"].strip():
                raise ValueError("task citation has no model text")
            path, text = source_field(public, citation.get("location"))
            bound = {**citation, "source_kind": "public_task", "source_field": path,
                     "source_text": text, "binding_status": "source_bound_content_not_verified"}
            task.append(bound)
            moves.append({"check_index": check_index, "chain_id": check.get("chain_id"),
                          "original_evidence_index": evidence_index,
                          "original": copy.deepcopy(citation), "bound": copy.deepcopy(bound)})
        check["evidence"] = visual
        if task:
            check["task_evidence"] = task
    return result, moves


def validate_stage(phase, value, record, config):
    if phase != "verification":
        return core.validate_stage(phase, value, record, config)
    separated, moves = separate_task_citations(value, record["public_task"])
    # Reuse every original chain-coverage, chart-evidence and recommendation guard.
    verdict = core.engine.validate_verification(
        record["normalized"], separated, record["public_task"]["option_labels"], ("chart_1",))
    store = core.engine.RuleStore()
    store.update(record["normalized"], verdict, metric=record["public_task"]["primary_field_label"])
    checks = {check["chain_id"]: check for check in verdict["checks"]}
    for state, rule in zip(store.records, record["normalized"]["rules"]):
        task_evidence = [citation
                         for chain in record["normalized"]["chains"] if chain["rule_id"] == rule["id"]
                         for citation in checks[chain["chain_id"]].get("task_evidence", [])]
        if task_evidence:
            state["task_evidence"] = copy.deepcopy(task_evidence)
    return {"verification_raw": copy.deepcopy(value), "verification": verdict,
            "rule_state": store.records, "citation_adapter": {"version": VERSION, "moves": moves,
            "semantics": "source binding only; model claims and verdicts not independently certified"}}
