"""Bounded six-condition static counterquestion pilot; archived inputs stay read-only.

--prepare never constructs an API client. --live requires MODEL_API_KEY and a
new output directory. Neither mode resumes or overwrites a previous run.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

# Read-only imports must not leave bytecode in historical experiment folders.
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
PROJECT = RESEARCH.parent
OLD = RESEARCH / "obc140_runtime_aligned_20260924"
PANEL = RESEARCH / "obc140_20260923"
NATIVE = PANEL / "terra140_native_zh_20260924"
CITATIONS = PANEL / "terra_citation_check_20260924"
METHOD = RESEARCH / "competing_rules_20260923"
PREVIOUS = RESEARCH / "counterquestion_b001_20260925"
for path in (PANEL, NATIVE, CITATIONS, METHOD, OLD):
    sys.path.insert(0, str(path))
import panel_core as core
import citation_adapter
import public_inputs
from budget import BudgetedPanelAPI, EstimatedBudget

_legacy_spec = importlib.util.spec_from_file_location(
    "counterquestion_b001_readonly", PREVIOUS / "run_diagnostic.py")
legacy = importlib.util.module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(legacy)
sys.path.insert(0, str(HERE))
import prompts_v2 as prompts

KINDS = ("supports_action", "challenges_support", "underdetermined")
EXPECTED_CASES = (
    ("b001_original", "b001", "archived_first_proposal_support",
     "research/obc140_runtime_aligned_20260924/prepared/tasks/b001/chart.jpeg"),
    ("b001_clean_control", "b001", "fresh_single_argument",
     ".aris/dataset_inventory_20260918/raw/assets/clean140/business47/b001/figure.png"),
    ("b002_original", "b002", "archived_first_proposal_support",
     "research/obc140_runtime_aligned_20260924/prepared/tasks/b002/chart.jpeg"),
    ("env001_original", "env001", "archived_first_proposal_support",
     "research/obc140_runtime_aligned_20260924/prepared/tasks/env001/chart.jpeg"),
    ("health001_original", "health001", "archived_first_proposal_support",
     "research/obc140_runtime_aligned_20260924/prepared/tasks/health001/chart.png"),
    ("pub013_original", "pub013", "archived_first_proposal_support",
     "research/obc140_runtime_aligned_20260924/prepared/tasks/pub013/chart.jpeg"),
)
PROMPTS = {"seed": prompts.SEED, "questions": prompts.QUESTIONER,
           "competitors": prompts.COMPETITOR, "verification": prompts.VERIFICATION}


def now():
    return datetime.now(timezone.utc).isoformat()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def text_paths(value):
    return legacy.text_paths(value)


def require_dict(value, label):
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    public_inputs.assert_public(value)


def evidence_ok(value, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError("Missing chart evidence list")
    for row in value:
        require_dict(row, "evidence")
        if row.get("ref") != "chart_1" or not all(nonempty(row.get(k)) for k in ("location", "content")):
            raise ValueError("Evidence needs actual chart_1 reference, location and content")


def validate_rule(rule):
    require_dict(rule, "rule")
    if not all(nonempty(rule.get(k)) for k in ("id", "text", "component", "conditions")):
        raise ValueError("Rule needs ID, interpretation, component and conditions")


def validate_chain(chain, rule_ids, options):
    require_dict(chain, "chain")
    if chain.get("rule_id") not in rule_ids or not nonempty(chain.get("claim")):
        raise ValueError("Chain needs a known rule and nonempty claim")
    evidence_ok(chain.get("observations"))
    if chain.get("claim_kind") not in KINDS:
        raise ValueError("Unknown claim_kind")
    if "option_label" not in chain:
        raise ValueError("Missing option_label, including explicit null for non-actions")
    if chain["claim_kind"] == "supports_action":
        if chain["option_label"] not in options:
            raise ValueError("Action support needs an exact public option")
    elif chain["option_label"] is not None:
        raise ValueError("A challenge or uncertainty claim must have null option_label")


def normalize_arguments(combined, origins):
    """Canonical O-B-C projection, exact equality deduplication, separate provenance.

    Text, capitalization, whitespace and observation order are never repaired.
    Candidate dependency/discriminator records remain in combined_raw and the
    sidecar, because their old/new wording identifies origin to the verifier.
    """
    rule_keys, rule_content = {}, {}
    for rule in combined["rules"]:
        item = {k: copy.deepcopy(rule[k]) for k in ("text", "component", "conditions")}
        key = canonical(item)
        rule_keys[rule["id"]] = key
        rule_content[key] = item
    sorted_rule_keys = sorted(rule_content)
    rule_ids = {key: "r%d" % (i + 1) for i, key in enumerate(sorted_rule_keys)}
    rules = [{"id": rule_ids[key], **rule_content[key]} for key in sorted_rule_keys]
    raw_keys, unique = [], {}
    for chain in combined["chains"]:
        item = {k: copy.deepcopy(chain[k]) for k in
                ("observations", "claim_kind", "option_label", "claim")}
        item["rule_id"] = rule_ids[rule_keys[chain["rule_id"]]]
        key = canonical(item)
        raw_keys.append(key)
        unique[key] = item
    keys = sorted(unique)
    chain_ids = {key: "c%d" % (i + 1) for i, key in enumerate(keys)}
    chains = [{"chain_id": chain_ids[key], **unique[key]} for key in keys]
    mapping, seen = [], set()
    for index, (chain, origin, key) in enumerate(zip(combined["chains"], origins, raw_keys)):
        duplicate = key in seen
        mapping.append({**copy.deepcopy(origin), "raw_combined_index": index,
                        "source_rule_id": chain["rule_id"],
                        "normalized_rule_id": rule_ids[rule_keys[chain["rule_id"]]],
                        "normalized_chain_id": chain_ids[key],
                        "exact_duplicate": duplicate,
                        "counted_as_new": origin["source"] == "new" and not duplicate,
                        "question_ids": copy.deepcopy(chain.get("question_ids", [])),
                        "difference_from_base": chain.get("difference_from_base"),
                        "discriminator": copy.deepcopy(chain.get("discriminator"))})
        seen.add(key)
    return {"combined_raw": copy.deepcopy(combined), "normalized": {"rules": rules, "chains": chains},
            "candidate_provenance": mapping,
            "normalization_audit": {"raw_chain_count": len(raw_keys), "unique_chain_count": len(keys),
                "unique_new_count": sum(row["counted_as_new"] for row in mapping),
                "exact_duplicate_count": len(raw_keys) - len(keys),
                "semantic_distinctness": "not_programmatically_assessed",
                "text_coercions": [],
                "projection": "verifier receives O-B-C plus claim_kind; dependency and origin records are sidecar-only",
                "rule_policy": "verbatim field equality; sorted IDs; no word-based semantic gate"}}


def validate_seed(value, public):
    require_dict(value, "seed")
    rules, chains = value.get("rules"), value.get("chains")
    if not isinstance(rules, list) or len(rules) != 1 or not isinstance(chains, list) or len(chains) != 1:
        raise ValueError("Seed requires exactly one rule and one chain")
    validate_rule(rules[0])
    chain = copy.deepcopy(chains[0])
    if "claim_kind" in chain and chain["claim_kind"] != "supports_action":
        raise ValueError("Seed must propose one action")
    chain["claim_kind"] = "supports_action"
    validate_chain(chain, {rules[0]["id"]}, public["option_labels"])
    return normalize_arguments({"rules": rules, "chains": [chain]},
        [{"source": "seed", "source_id": chains[0].get("chain_id", "seed_0")}])["normalized"]


def validate_questions(value, base):
    require_dict(value, "questions")
    inventory = value.get("visual_inventory")
    evidence_ok(inventory, allow_empty=True)
    if len(inventory) > 8:
        raise ValueError("Visual inventory exceeds eight localized facts")
    # Retain the previous structural validator, with the two new required fields.
    legacy.validate_questions(value, base)
    for row in value["questions"]:
        if not nonempty(row.get("current_bridge")) or not isinstance(row.get("uncertainty"), str):
            raise ValueError("Question needs current_bridge and an uncertainty string")
        for field in ("target_chain_ids", "target_rule_ids"):
            if len(row[field]) != len(set(row[field])):
                raise ValueError("Duplicate question target")
    return copy.deepcopy(value)


def merge_candidates(value, base, questions, public):
    require_dict(value, "competitors")
    new, rules = value.get("new_chains"), value.get("new_rules")
    if not isinstance(new, list) or len(new) > 2 or not isinstance(rules, list):
        raise ValueError("Expected zero to two new chains and a rule list")
    for rule in rules:
        validate_rule(rule)
    rids = [rule["id"] for rule in rules]
    if len(set(rids)) != len(rids) or set(rids) & {rule["id"] for rule in base["rules"]}:
        raise ValueError("New rule IDs duplicate or collide with base rules")
    qids = {row["id"] for row in questions["questions"]}
    ids = []
    for chain in new:
        validate_chain(chain, set(rids), public["option_labels"])
        cid, dependencies = chain.get("candidate_id"), chain.get("question_ids")
        if not nonempty(cid) or cid in ids:
            raise ValueError("Missing or duplicate candidate ID")
        ids.append(cid)
        if (not isinstance(dependencies, list) or not dependencies
                or len(set(dependencies)) != len(dependencies) or not set(dependencies) <= qids):
            raise ValueError("Candidate needs actual question dependencies")
        if not nonempty(chain.get("difference_from_base")):
            raise ValueError("Missing stated bridge difference")
        discriminator = chain.get("discriminator")
        require_dict(discriminator, "discriminator")
        if not all(nonempty(discriminator.get(k)) for k in ("base_reading", "observable_check")):
            raise ValueError("Incomplete discriminator")
        if "alternative_reading" not in discriminator:
            raise ValueError("Discriminator needs alternative_reading, possibly null for a non-action")
        alternative = discriminator["alternative_reading"]
        if not nonempty(alternative) and not (alternative is None and chain["claim_kind"] != "supports_action"):
            raise ValueError("Action support needs an alternative reading; non-actions may use null")
        if discriminator.get("availability") not in ("visible", "unreadable", "not_available"):
            raise ValueError("Unknown discriminator availability")
    if set(rids) != {chain["rule_id"] for chain in new}:
        raise ValueError("Every new rule must be referenced")
    responses = value.get("question_responses")
    if (not isinstance(responses, list) or len(responses) != len(qids)
            or {row.get("question_id") for row in responses} != qids):
        raise ValueError("Every actual question needs exactly one response")
    for row in responses:
        expected = {chain["candidate_id"] for chain in new if row["question_id"] in chain["question_ids"]}
        dependencies = row.get("candidate_ids")
        if (not isinstance(dependencies, list) or len(set(dependencies)) != len(dependencies)
                or set(dependencies) != expected or not nonempty(row.get("reason"))):
            raise ValueError("Response dependencies disagree with generated candidates")
        if row.get("resolution") != ("candidate_generated" if expected else "no_supported_alternative"):
            raise ValueError("Question resolution disagrees with candidate dependencies")
    combined = {"rules": copy.deepcopy(base["rules"] + rules),
                "chains": copy.deepcopy(base["chains"] + new)}
    origins = ([{"source": "base", "source_id": c["chain_id"]} for c in base["chains"]]
               + [{"source": "new", "source_id": c["candidate_id"]} for c in new])
    return normalize_arguments(combined, origins)


def validate_verification(value, normalized, public):
    require_dict(value, "verification")
    if "recommendation" not in value or not isinstance(value.get("unresolved_reason"), str):
        raise ValueError("Verifier needs recommendation and unresolved_reason")
    separated, moves = citation_adapter.separate_task_citations(value, public)
    checks = separated.get("checks")
    wanted = {chain["chain_id"] for chain in normalized["chains"]}
    if (not isinstance(checks, list) or len(checks) != len(wanted)
            or {check.get("chain_id") for check in checks} != wanted):
        raise ValueError("Incomplete, duplicate or unknown verifier checks")
    for check in checks:
        if any(check.get(k) not in ("supported", "refuted", "undetermined") for k in ("O", "B", "implication")):
            raise ValueError("Invalid evidence status")
        if not nonempty(check.get("reason")):
            raise ValueError("Verifier needs a brief reason")
        evidence_ok(check.get("evidence"))
    rec = value["recommendation"]
    if rec is not None and rec not in public["option_labels"]:
        raise ValueError("Recommendation is not an exact public option or null")
    by_id = {check["chain_id"]: check for check in checks}
    supported = lambda chain: all(by_id[chain["chain_id"]][k] == "supported" for k in ("O", "B", "implication"))
    action_chains = [c for c in normalized["chains"] if c["claim_kind"] == "supports_action"]
    supported_options = sorted({c["option_label"] for c in action_chains if supported(c)})
    reasons = []
    if rec is not None:
        if rec not in supported_options:
            reasons.append("no_fully_supported_action_chain_for_recommendation")
        if len(supported_options) > 1:
            reasons.append("multiple_fully_supported_action_options")
        for rid in {c["rule_id"] for c in action_chains if c["option_label"] == rec and supported(c)}:
            if len({by_id[c["chain_id"]]["B"] for c in normalized["chains"] if c["rule_id"] == rid}) > 1:
                reasons.append("shared_rule_has_disputed_bridge_checks")
                break
    verdict = copy.deepcopy(separated)
    if reasons:
        verdict["recommendation"] = None
    # This inherited RuleStore only snapshots B status. It never selects an action.
    store = core.engine.RuleStore()
    store.update(normalized, verdict, metric=public["primary_field_label"])
    for state, rule in zip(store.records, normalized["rules"]):
        task_evidence = [citation for chain in normalized["chains"] if chain["rule_id"] == rule["id"]
                         for citation in by_id[chain["chain_id"]].get("task_evidence", [])]
        if task_evidence:
            state["task_evidence"] = copy.deepcopy(task_evidence)
    return {"verification_raw": copy.deepcopy(value), "verification_validated": verdict,
            "verification": copy.deepcopy(verdict), "rule_state": store.records,
            "rule_state_limit": "original simplified B-status snapshot; no cross-step validity demonstrated; active is not an executable action",
            "recommendation_guard": {"raw_recommendation": rec,
                "validated_recommendation": verdict["recommendation"], "changed": rec != verdict["recommendation"],
                "reasons": reasons, "fully_supported_action_options": supported_options,
                "policy": "original structural guard restricted to supports_action options: require fully supported recommendation, reject multiple fully supported public options and disputed shared-rule B checks; semantic incompatibility remains the verifier's judgment",
                "model_verdicts_edited": False, "model_unresolved_reason_edited": False,
                "model_changed_its_mind": "not_inferred_from_guard_coercion"},
            "citation_adapter": {"version": citation_adapter.VERSION, "moves": moves,
                "semantics": "source binding only; model evidence content not independently certified"}}


def load_case(case, project_root=PROJECT):
    project_root = Path(project_root)
    archive = project_root / "research/obc140_runtime_aligned_20260924"
    public_path = archive / "prepared/tasks" / case["task_id"] / "public.json"
    chart_path = project_root / case["chart"]
    public = core.read(public_path)
    if not isinstance(public, dict) or set(public) != public_inputs.PUBLIC_KEYS:
        raise ValueError("Unexpected public task fields")
    public_inputs.assert_public(public)
    hashes = {str(p): core.digest(p) for p in (public_path, chart_path)}
    inputs = {"task": public, "base_arguments": None, "base_proposal": None,
              "chart_source": str(chart_path), "public_source": str(public_path),
              "source_sha256": hashes, "seed_provenance": {"mode": case["seed_mode"]}}
    # This branch deliberately returns before constructing any archived run path.
    if case["seed_mode"] == "fresh_single_argument":
        inputs["seed_provenance"].update(archived_arm_records_read=False,
            seed_schema_default={"claim_kind": "supports_action"})
        return inputs
    if case["seed_mode"] != "archived_first_proposal_support":
        raise ValueError("Unknown seed mode")
    folder = archive / "run/tasks" / case["task_id"]
    proposal_path = folder / "proposal/round_001/validated.json"
    generation_path = folder / "generation/round_001/validated.json"
    proposal_value = core.read(proposal_path)
    proposal = proposal_value["proposal"]
    option = proposal["action"]["option"]
    if option not in public["option_labels"]:
        raise ValueError("Archived proposal does not name a public option")
    generation_value = core.read(generation_path)
    generated = generation_value.get("generated") if isinstance(generation_value, dict) else None
    consulted = [proposal_path]
    if generation_path.is_file():
        consulted.append(generation_path)
    if not isinstance(generated, dict) or not isinstance(generated.get("chains"), list):
        generation_path = folder / "generation/round_001/parsed.json"
        generated = core.read(generation_path)
        consulted.append(generation_path)
    matches = [(index, chain) for index, chain in enumerate(generated["chains"])
               if chain.get("option_label") == option]
    if not matches:
        raise ValueError("No archived original-order chain supports the initial proposal")
    index, chain = matches[0]
    selected_rules = [rule for rule in generated["rules"] if rule["id"] == chain["rule_id"]]
    if len(selected_rules) != 1:
        raise ValueError("Archived selected chain lacks exactly one rule")
    seed = {"rules": copy.deepcopy(selected_rules), "chains": [copy.deepcopy(chain)]}
    inputs["base_arguments"] = validate_seed(seed, public)
    inputs["base_proposal"] = copy.deepcopy(proposal)
    inputs["seed_original"] = seed
    inputs["seed_provenance"].update(
        generation_path=str(generation_path), proposal_path=str(proposal_path),
        original_chain_index=index, original_rule_id=chain["rule_id"],
        selection="first generated chain in original order whose option_label equals proposal.action.option",
        inherited_model_calls_not_new=2,
        seed_schema_default={"claim_kind": "supports_action"},
        inherited_text_policy="verbatim; existing visual comparisons remain seed-exposed, not newly discovered")
    hashes.update({str(p): core.digest(p) for p in consulted})
    public_inputs.assert_public(inputs["base_arguments"])
    return inputs


def build_context(stage, inputs, result):
    common = core.common_context(inputs["task"])
    base = result.get("base_arguments", inputs.get("base_arguments"))
    if stage == "seed":
        context = common
    elif stage == "questions":
        context = {**common, "base_arguments": base}
    elif stage == "competitors":
        context = {**common, "base_arguments": base, "counterquestions": result["questions"]}
    elif stage == "verification":
        context = {**common, "arguments": result["normalized"],
                   "public_task_text_paths": text_paths(inputs["task"])}
    else:
        raise ValueError("Unknown stage")
    public_inputs.assert_public(context)
    return copy.deepcopy(context)


def source_files():
    modules = [core, core.engine, citation_adapter, public_inputs, legacy, prompts]
    modules += [sys.modules[name] for name in
                ("budget", "analyze_usage", "format_replay", "prompts_observation_v4", "prompts")]
    return sorted({Path(__file__).resolve(), *(Path(module.__file__).resolve() for module in modules),
                   HERE / "config.json", HERE / "manifest.json", HERE / "IMPLEMENTATION_SPEC.md"}, key=str)


IMPORTED_SOURCE_SHA256 = {str(path): core.digest(path) for path in source_files()}


def validate_config(config, manifest):
    required = {"endpoint": "https://api.apiyi.com/v1/chat/completions", "model": "gpt-5.6-terra",
                "max_request_attempts": 24, "max_estimated_usd": 3.0,
                "max_attempts_per_call": 2, "concurrency": 1, "quality_retries": False,
                "max_new_candidates": 2, "browser_operations": 0, "gpu_enabled": False,
                "wandb": False, "temperature": 0, "allow_trailing_json_closers": False,
                "phase_max_tokens": {"generation": 3800, "verification": 3800},
                "attempt_reserve_usd": 0.25, "estimated_input_usd_per_m": 2.5,
                "estimated_output_usd_per_m": 12, "proxy": None, "timeout_seconds": 120}
    if any(config.get(k) != v for k, v in required.items()):
        raise ValueError("Bounded pilot configuration changed")
    if tuple((c["case_id"], c["task_id"], c["seed_mode"], c["chart"]) for c in manifest["cases"]) != EXPECTED_CASES:
        raise ValueError("Predeclared case panel or order changed")
    if (manifest.get("planned_logical_calls") != 19 or manifest.get("max_request_attempts") != 24
            or manifest.get("max_estimated_usd") != 3.0):
        raise ValueError("Predeclared panel budget changed")


def freeze_sources(output):
    frozen = {}
    for path in source_files():
        digest = core.digest(path)
        if digest != IMPORTED_SOURCE_SHA256[str(path)]:
            raise ValueError("Runtime source changed after import; start a fresh process")
        destination = output / "runtime_source" / path.relative_to(PROJECT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        if core.digest(destination) != digest:
            raise ValueError("Runtime snapshot changed during copying")
        frozen[str(path)] = digest
    core.dump(output / "runtime.json", {"created_at": now(), "python": sys.version,
        "executable": sys.executable, "source_sha256": frozen,
        "credential_source": "MODEL_API_KEY environment only; never recorded",
        "snapshot_scope": "actual imported project runtime plus config, manifest and implementation specification",
        "rule_store_limit": "original simplified status snapshot; no cross-step validity demonstrated"})


def budget_fields(budget, start_index=0):
    budget.reconcile()
    events = budget.value["events"][start_index:]
    return {"request_attempts": len(events),
            "estimated_ledger_usd": float(sum((Decimal(str(e["charged_estimated_usd"]))
                                              for e in events), Decimal(0))),
            "actual_bill_usd": None, "api_cost_source": {"ledger": str(budget.path.resolve()),
                "event_indices": list(range(start_index, len(budget.value["events"]))),
                "accounting_status": [e["accounting_status"] for e in events],
                "warning": "estimated input/output proxy or retained reserve, not provider invoice"}}


def save_case(folder, result, budget=None, start_index=0):
    if budget is not None:
        result.update(budget_fields(budget, start_index))
    result["source_preservation"] = {p: Path(p).is_file() and core.digest(p) == digest
                                      for p, digest in result["inputs"]["source_sha256"].items()}
    core.dump(folder / "result.json", result)


def run(output, live=False, api_factory=BudgetedPanelAPI):
    output = Path(output).resolve()
    if output.parent != HERE:
        raise ValueError("Output must be a new direct child of this experiment directory")
    if output.exists():
        raise FileExistsError("Refusing to reuse a previous output directory")
    config, manifest = core.read(HERE / "config.json"), core.read(HERE / "manifest.json")
    validate_config(config, manifest)
    if live and not os.environ.get("MODEL_API_KEY"):
        raise ValueError("--live requires an authorized MODEL_API_KEY in the process environment")
    # Read and validate the complete fixed panel before making any request.
    all_inputs = [load_case(case) for case in manifest["cases"]]
    output.mkdir(parents=True, exist_ok=False)
    freeze_sources(output)
    core.dump(output / "prompt_templates.json", PROMPTS)
    budget = EstimatedBudget(output / "budget.json", config)
    results = []
    for case, inputs in zip(manifest["cases"], all_inputs):
        folder = output / "cases" / case["case_id"]
        folder.mkdir(parents=True, exist_ok=False)
        chart_path = folder / ("chart" + Path(inputs["chart_source"]).suffix)
        shutil.copyfile(inputs["chart_source"], chart_path)
        shutil.copyfile(inputs["public_source"], folder / "public.json")
        result = {"case_id": case["case_id"], "task_id": case["task_id"],
            "status": "prepared_not_sent", "created_at": now(), "inputs": inputs,
            "base_arguments": inputs["base_arguments"], "seed_provenance": inputs["seed_provenance"],
            "stages": {}, "questions": None, "competitors": None, "normalized": None,
            "candidate_provenance": [], "verification_raw": None, "verification_validated": None,
            "rule_state": [], "failure": None, "request_attempts": 0, "estimated_ledger_usd": 0,
            "actual_bill_usd": None, "api_cost_source": {"ledger": str(budget.path), "event_indices": []},
            "browser_operations": 0, "gpu_operations": 0, "translation_api_calls": 0}
        stage = "seed" if case["seed_mode"] == "fresh_single_argument" else "questions"
        core.dump(folder / "prepared_first_context.json", build_context(stage, inputs, result))
        core.dump(folder / "inputs.json", inputs)
        save_case(folder, result)
        results.append(result)
    summary = {"status": "prepared_not_sent", "created_at": now(), "scope": manifest["scope"],
               "planned_logical_calls": 19, "cases": [], "semantic_success": "not_assessed_by_runner",
               "browser_operations": 0, "gpu_operations": 0, "global_stop": None}

    def save_summary():
        summary["cases"] = [{"case_id": r["case_id"], "status": r["status"],
                             "request_attempts": r["request_attempts"], "failure": r["failure"],
                             "result": str(output / "cases" / r["case_id"] / "result.json")}
                            for r in results]
        summary.update(budget_fields(budget))
        summary["structurally_completed_cases"] = sum(r["status"] == "completed" for r in results)
        summary["runtime_source_preservation"] = {p: Path(p).is_file() and core.digest(p) == digest
            for p, digest in core.read(output / "runtime.json")["source_sha256"].items()}
        core.dump(output / "summary.json", summary)

    save_summary()
    if not live:
        return summary
    summary["status"] = "running"
    stop = None
    try:
        api = api_factory(config, budget)
    except (core.ServiceStop, core.UnknownRequestOutcome) as exc:
        stop = {"type": type(exc).__name__, "reason": str(exc), "stage": "client_initialization"}
    for case, result in zip(manifest["cases"], results):
        folder, inputs = output / "cases" / case["case_id"], result["inputs"]
        if stop:
            result["status"] = "not_attempted_global_stop"
            result["failure"] = {"type": "GlobalStop", "reason": stop["reason"]}
            save_case(folder, result)
            continue
        start_index = len(budget.value["events"])
        stages = (["seed"] if case["seed_mode"] == "fresh_single_argument" else []) + ["questions", "competitors", "verification"]
        result["status"] = "running"
        current = None
        try:
            for current in stages:
                wire_phase = "verification" if current == "verification" else "generation"
                context = build_context(current, inputs, result)
                result["stages"][current] = {"status": "running", "started_at": now(), "wire_phase": wire_phase}
                save_case(folder, result, budget, start_index)
                core.dump(folder / current / "input_context.json", context)
                chart_path = folder / ("chart" + Path(inputs["chart_source"]).suffix)
                value = api.call(folder / current / "round_001", case["case_id"], wire_phase,
                                 PROMPTS[current], context, [("chart_1", chart_path)])
                core.dump(folder / current / "raw.json", value)
                # Preserve the complete parsed model value even if validation fails.
                result[current + "_raw"] = copy.deepcopy(value)
                if current == "seed":
                    result["base_arguments"] = validate_seed(value, inputs["task"])
                    result["seed_normalization"] = {"claim_kind_default": "supports_action", "text_coercions": []}
                elif current == "questions":
                    result["questions"] = validate_questions(value, result["base_arguments"])
                elif current == "competitors":
                    result["competitors"] = copy.deepcopy(value)
                    result.update(merge_candidates(value, result["base_arguments"], result["questions"], inputs["task"]))
                    core.dump(folder / "candidate_provenance.json", result["candidate_provenance"])
                else:
                    result.update(validate_verification(value, result["normalized"], inputs["task"]))
                result["stages"][current].update(status="completed", finished_at=now())
                core.dump(folder / current / "accepted.json", result.get("verification_validated")
                          if current == "verification" else value)
                save_case(folder, result, budget, start_index)
            result["status"] = "completed"
        except (core.ServiceStop, core.UnknownRequestOutcome) as exc:
            stop = {"type": type(exc).__name__, "reason": str(exc), "case_id": case["case_id"], "stage": current}
            result["status"], result["failure"] = "stopped_global", copy.deepcopy(stop)
        except Exception as exc:
            result["status"] = "failed_stage_no_quality_retry"
            result["failure"] = {"type": type(exc).__name__, "reason": str(exc), "stage": current}
        finally:
            if result["failure"] and current in result["stages"]:
                result["stages"][current].update(status="failed", failure=result["failure"], finished_at=now())
            result["finished_at"] = now()
            save_case(folder, result, budget, start_index)
            summary["global_stop"] = stop
            save_summary()
    summary["global_stop"] = stop
    summary["status"] = ("stopped_global" if stop else "completed" if all(r["status"] == "completed" for r in results)
                         else "completed_with_case_failures")
    summary["finished_at"] = now()
    save_summary()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="Freeze inputs and runtime without network")
    mode.add_argument("--live", action="store_true", help="Run the authorized fixed panel using MODEL_API_KEY")
    parser.add_argument("--output", type=Path, default=HERE / "run")
    args = parser.parse_args()
    result = run(args.output, live=args.live)
    print(json.dumps({k: result[k] for k in ("status", "cases", "request_attempts", "estimated_ledger_usd")}, ensure_ascii=False))
