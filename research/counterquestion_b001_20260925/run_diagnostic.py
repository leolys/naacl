"""One seeded b001 diagnostic. Reuses the prior transport/budget/validators read-only."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
OLD = RESEARCH / "obc140_runtime_aligned_20260924"
PANEL = RESEARCH / "obc140_20260923"
NATIVE = PANEL / "terra140_native_zh_20260924"
CITATIONS = PANEL / "terra_citation_check_20260924"
METHOD = RESEARCH / "competing_rules_20260923"
for path in (PANEL, NATIVE, CITATIONS, METHOD, OLD):
    sys.path.insert(0, str(path))
import panel_core as core
import citation_adapter
import public_inputs
from budget import BudgetedPanelAPI, EstimatedBudget
sys.path.insert(0, str(HERE))
from prompts import QUESTIONER, COMPETITOR, VERIFICATION

KINDS = ["evidence_sufficiency", "rule_assumptions", "alternative_explanation"]


def now():
    return datetime.now(timezone.utc).isoformat()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def text_paths(value, prefix=""):
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in text_paths(v, prefix + ("." if prefix else "") + k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in text_paths(v, prefix + "." + str(i))]
    return [prefix] if nonempty(value) else []


def evidence_ok(rows, allow_empty=False):
    if not isinstance(rows, list) or (not rows and not allow_empty):
        raise ValueError("Missing chart evidence list")
    for row in rows:
        if row.get("ref") != "chart_1" or not all(nonempty(row.get(k)) for k in ("location", "content")):
            raise ValueError("Evidence lacks actual chart reference/location/text")


def validate_questions(value, base):
    rows = value.get("questions", [])
    if len(rows) != 3 or [r.get("id") for r in rows] != ["q1", "q2", "q3"] or [r.get("kind") for r in rows] != KINDS:
        raise ValueError("Exactly three linked critical-question kinds required")
    chains = {c["chain_id"] for c in base["chains"]}
    rules = {r["id"] for r in base["rules"]}
    for row in rows:
        for key, allowed in (("target_chain_ids", chains), ("target_rule_ids", rules)):
            if not row.get(key) or not isinstance(row[key], list) or not set(row[key]) <= allowed:
                raise ValueError("Question targets a missing inherited argument")
        if not all(nonempty(row.get(k)) for k in ("question", "brief_assessment", "discriminating_check")):
            raise ValueError("Incomplete counterquestion record")
        if row.get("candidate_bridge") is not None and not nonempty(row["candidate_bridge"]):
            raise ValueError("Alternative bridge must be text or null")
        evidence_ok(row.get("chart_evidence"), allow_empty=True)
    if not nonempty(value.get("questioning_summary")):
        raise ValueError("Missing questioning summary")
    public_inputs.assert_public(value)
    return value


def merge_candidates(value, base, questions, public):
    new = value.get("new_chains")
    rules = value.get("new_rules")
    if not isinstance(new, list) or len(new) > 2 or not isinstance(rules, list):
        raise ValueError("Expected zero to two new candidate chains")
    qids = {q["id"] for q in questions["questions"]}
    ids = [c.get("candidate_id") for c in new]
    if any(not nonempty(i) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError("Duplicate or missing candidate IDs")
    rids = [r.get("id") for r in rules]
    if (any(not nonempty(i) for i in rids) or len(set(rids)) != len(rids)
            or set(rids) & {r["id"] for r in base["rules"]}):
        raise ValueError("New rule IDs collide or are invalid")
    if any(not all(nonempty(rule.get(k)) for k in ("text", "component", "conditions")) for rule in rules):
        raise ValueError("New rule must state its interpretation, component and scope")
    for chain in new:
        if not isinstance(chain.get("question_ids"), list) or not chain["question_ids"] or not set(chain["question_ids"]) <= qids:
            raise ValueError("Candidate lacks genuine question dependency")
        if chain.get("rule_id") not in rids or not nonempty(chain.get("difference_from_base")):
            raise ValueError("Candidate missing distinct bridge or new rule")
        if not nonempty(chain.get("claim")):
            raise ValueError("New chain lacks a derived claim")
        evidence_ok(chain.get("observations"))
    if set(rids) != {c["rule_id"] for c in new}:
        raise ValueError("Unreferenced new rules")
    responses = value.get("question_responses", [])
    if len(responses) != len(qids) or {r.get("question_id") for r in responses} != qids:
        raise ValueError("Every actual question needs a response")
    for row in responses:
        expected = {c["candidate_id"] for c in new if row["question_id"] in c["question_ids"]}
        if not isinstance(row.get("candidate_ids"), list) or set(row["candidate_ids"]) != expected or not nonempty(row.get("reason")):
            raise ValueError("Question response links do not match candidate sources")
        required = "candidate_generated" if expected else "no_supported_alternative"
        if row.get("resolution") != required:
            raise ValueError("Question resolution inconsistent with new chains")
    public_inputs.assert_public(value)
    combined = {"rules": copy.deepcopy(base["rules"] + rules),
                "chains": copy.deepcopy(base["chains"] + new)}
    normalized = core.engine.normalized_candidates(combined, public["option_labels"], 2, cap_by_order=False)
    # Retain all raw records and map the existing deterministic normalization;
    # equality deduplication is not evidence that semantic alternatives are absent.
    mapping = []
    for i, chain in enumerate(combined["chains"]):
        rule = next(r for r in combined["rules"] if r["id"] == chain["rule_id"])
        matches = []
        for c in normalized["chains"]:
            nr = next(r for r in normalized["rules"] if r["id"] == c["rule_id"])
            if (all(c[k] == chain[k] for k in ("observations", "option_label", "claim"))
                    and all(str(nr[k]).strip().casefold() == str(rule[k]).strip().casefold()
                            for k in ("text", "component", "conditions"))):
                matches.append(c["chain_id"])
        if len(matches) != 1:
            raise ValueError("Cannot trace raw candidate through normalization")
        mapping.append({"source": "inherited" if i < len(base["chains"]) else "new",
                        "source_id": chain.get("candidate_id", chain.get("chain_id")),
                        "question_ids": chain.get("question_ids", []), "normalized_chain_id": matches[0]})
    if len({row["normalized_chain_id"] for row in mapping}) != len(mapping):
        raise ValueError("Purported new candidate is an exact normalized restatement; not a new competing chain")
    return {"combined_raw": combined, "normalized": normalized, "candidate_provenance": mapping}


def source_files():
    return [HERE / "run_diagnostic.py", HERE / "prompts.py", HERE / "config.json",
            OLD / "public_inputs.py", PANEL / "panel_core.py", NATIVE / "budget.py",
            PANEL / "apiyi_selection_20260924/analyze_usage.py", CITATIONS / "citation_adapter.py",
            METHOD / "engine.py", METHOD / "format_replay.py", METHOD / "prompts_observation_v4.py"]


def seed(output):
    old_record = OLD / "run/tasks/b001/record.json"
    old_public = OLD / "prepared/tasks/b001/public.json"
    old_chart = OLD / "prepared/tasks/b001/chart.jpeg"
    record, public = core.read(old_record), core.read(old_public)
    if record["public_task"] != public or len(record["normalized"]["chains"]) != 1:
        raise ValueError("Expected the unchanged original one-chain b001 seed")
    if set(public) != public_inputs.PUBLIC_KEYS:
        raise ValueError("Unexpected public task fields")
    public_inputs.assert_public(public)
    inputs = {"task": public, "base_proposal": record["proposal"], "base_arguments": record["normalized"]}
    public_inputs.assert_public(inputs)
    output.mkdir(parents=True, exist_ok=False)
    core.dump(output / "seed_input.json", inputs)
    shutil.copyfile(old_chart, output / "chart.jpeg")
    frozen = {}
    for path in source_files():
        rel = path.relative_to(RESEARCH)
        target = output / "runtime_source" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        frozen[str(path)] = core.digest(path)
    core.dump(output / "runtime.json", {"created_at": now(), "python": sys.version,
        "source_sha256": frozen, "seed_sha256": {str(p): core.digest(p) for p in (old_record, old_public, old_chart)},
        "seed_reuse": "original proposal and single normalized argument only; no old verifier verdict/state",
        "scope": "given-state static diagnostic, not new independent sampling or GUI execution"})
    return inputs


def run(output, live=False):
    config = core.read(HERE / "config.json")
    if (config["model"] != "gpt-5.6-terra" or config["endpoint"] != "https://api.apiyi.com/v1/chat/completions"
            or config["max_request_attempts"] != 9 or config["max_estimated_usd"] != 1
            or config["concurrency"] != 1 or config["quality_retries"]):
        raise ValueError("Bounded single-case configuration changed")
    if live and not os.environ.get("MODEL_API_KEY"):
        raise ValueError("No authorized credential in process environment")
    inputs = seed(output)
    common = core.common_context(inputs["task"])
    contexts = {"counterquestions": {**common, "base_arguments": inputs["base_arguments"]}}
    result = {"status": "prepared_not_sent", "created_at": now(), "task_slug": "b001",
              "stages": {}, "base_proposal": inputs["base_proposal"],
              "base_arguments": inputs["base_arguments"], "browser_operations": 0,
              "gpu_operations": 0, "translation_api_calls": 0, "inherited_model_calls_not_new": 2}
    core.dump(output / "prompt_templates.json", {"counterquestions": QUESTIONER, "competitors": COMPETITOR, "verification": VERIFICATION})
    core.dump(output / "prepared_question_context.json", contexts["counterquestions"])
    core.dump(output / "result.json", result)
    if not live:
        return result
    budget = EstimatedBudget(output / "budget.json", config)
    api = BudgetedPanelAPI(config, budget)
    images = [("chart_1", output / "chart.jpeg")]
    current = None
    try:
        for current, wire_phase, prompt in (("counterquestions", "generation", QUESTIONER),
                ("competitors", "generation", COMPETITOR), ("verification", "verification", VERIFICATION)):
            if current == "competitors":
                contexts[current] = {**common, "base_arguments": inputs["base_arguments"],
                                     "counterquestions": result["counterquestions"]}
            elif current == "verification":
                contexts[current] = {**common, "arguments": result["normalized"],
                                     "public_task_text_paths": text_paths(inputs["task"])}
            public_inputs.assert_public(contexts[current])
            result["stages"][current] = {"status": "running", "wire_phase": wire_phase, "started_at": now()}
            core.dump(output / "result.json", result)
            value = api.call(output / current / "round_001", "b001", wire_phase, prompt, contexts[current], images)
            core.dump(output / current / "raw.json", value)
            try:
                if current == "counterquestions":
                    result["counterquestions"] = validate_questions(value, inputs["base_arguments"])
                elif current == "competitors":
                    result["competitors"] = value
                    result.update(merge_candidates(value, inputs["base_arguments"], result["counterquestions"], inputs["task"]))
                else:
                    result.update(citation_adapter.validate_stage("verification", value,
                                  {"normalized": result["normalized"], "public_task": inputs["task"]}, config))
            except Exception as exc:
                result["stages"][current].update(status="invalid", error=str(exc), finished_at=now())
                result["status"] = "stopped_with_invalid_stage"
                break
            result["stages"][current].update(status="completed", finished_at=now())
            core.dump(output / current / "accepted.json", value)
            core.dump(output / "result.json", result)
        else:
            result["status"] = "completed"
    except Exception as exc:
        result["status"] = "stopped_with_failed_stage"
        if current:
            result["stages"][current].update(status="failed", error_type=type(exc).__name__, finished_at=now())
        result["failure"] = type(exc).__name__
    finally:
        budget.reconcile()
        result["request_attempts"] = budget.value["request_attempts"]
        result["estimated_ledger_usd"] = budget.value["estimated_ledger_usd"]
        result["actual_bill_usd"] = None
        runtime = core.read(output / "runtime.json")
        result["source_preservation"] = {p: core.digest(p) == h for p, h in runtime["seed_sha256"].items()}
        result["finished_at"] = now()
        core.dump(output / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, default=HERE / "run")
    args = parser.parse_args()
    if args.output.resolve().parent != HERE:
        raise ValueError("Diagnostic output must be a new direct child of this experiment directory")
    result = run(args.output, args.live)
    print(json.dumps({k: result.get(k) for k in ("status", "stages", "request_attempts", "estimated_ledger_usd")}, ensure_ascii=False))
