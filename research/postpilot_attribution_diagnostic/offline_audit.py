"""Read existing pilot artifacts only. No model client, browser, or scorer imports.

Writes a new offline report directory; never changes source results or labels.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.path_compat import resolve_path

PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_RUN = PROJECT / "research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/live_panel_04"


def read(path):
    return json.loads(resolve_path(path).read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def transition(before, after, expected):
    if after is None or after == "":
        return "no_output_or_no_submission"
    if before == expected:
        return "correct_to_correct" if after == expected else "correct_to_wrong"
    if after == expected:
        return "wrong_to_correct"
    return "wrong_to_same_wrong" if after == before else "wrong_to_different_wrong"


def pixels_equal(a, b):
    with Image.open(resolve_path(a)) as x, Image.open(resolve_path(b)) as y:
        return x.size == y.size and x.convert("RGBA").tobytes() == y.convert("RGBA").tobytes()


def metadata_images(request, directory):
    result = []
    for artifact in request.get("image_artifacts", []):
        path = resolve_path(artifact, base=directory)
        with Image.open(path) as im:
            result.append(dict(artifact=artifact, path=str(path), size=list(im.size), mode=im.mode))
    return result


def first_request(directory):
    paths = sorted((directory / "requests").glob("*.json"))
    if not paths:
        raise ValueError(f"No recorded request: {directory}")
    return paths[0], read(paths[0])


def supplied_history_count(context):
    # H_base replaces legacy policy fields before recording the actual request.
    return len(context.get("recent_executed_actions_and_public_receipts", []))


def input_pair(unit, ordinal):
    left_path, left = first_request(unit / "B2/verification")
    right_path, right = first_request(unit / "B3/verification")
    a = metadata_images(left, unit / "B2/verification")
    b = metadata_images(right, unit / "B3/verification")
    lc, rc = left["public_context"], right["public_context"]
    left_options, right_options = lc.get("visible_options"), rc.get("visible_options")
    pixel_map = [[pixels_equal(x["path"], y["path"]) for y in b] for x in a]
    return dict(ordinal=ordinal, B2_request=str(left_path), B3_request=str(right_path),
        B2_images=a, B3_images=b, B2_image_to_B3_image_pixel_equality=pixel_map,
        same_goal=lc.get("user_goal") == rc.get("user_goal"), same_option_order=left_options == right_options,
        same_system_prompt=left["system_prompt"] == right["system_prompt"],
        same_user_prompt=left["user_prompt"] == right["user_prompt"],
        B2_context_keys=list(lc), B3_context_keys=list(rc),
        B2_has_current_selection="current_selection" in lc,
        B3_has_current_selection="current_selection" in rc,
        B2_history_actions=supplied_history_count(lc),
        B3_history_actions=supplied_history_count(rc),
        history_field="recent_executed_actions_and_public_receipts",
        B3_prior_model_responses=len(rc.get("prior_agent_responses", [])),
        B3_image_order=rc.get("supplied_image_ids"),
        B2_full_request=left, B3_full_request=right,
        limit="Pixel comparison applies to stored supplied images, not undocumented upstream preprocessing.")


def raw_specs(manifest):
    result = []
    for task in manifest["rows"]:
        for arm in task["assets"]:
            path = PROJECT / "web_agent_benchmark/benchmark_v2_open/splits" / arm / (task["family"] + "_tasks.jsonl")
            found = []
            for line_number, line in enumerate(path.read_text().splitlines(), 1):
                raw = json.loads(line)
                if raw.get("task_slug") == task["task_slug"]:
                    found.append((line_number, raw))
            if len(found) != 1:
                raise ValueError(f"Expected one raw spec for {task['task_slug']}/{arm}, got {len(found)}")
            line_number, raw = found[0]
            expected = next(a["label"] for a in raw["action_space"] if a["action_id"] == raw["expected_action_id"])
            recorded_expected = task["public_task"]["option_labels"][task["offline_expected_option_position"] - 1]
            result.append(dict(task_slug=task["task_slug"], arm=arm, source=str(path), line=line_number,
                source_case_id=task["source_case_id"], figure=task["assets"][arm],
                public_task=task["public_task"], expected_option=expected,
                matches_preselected_expected_option=expected == recorded_expected,
                original_readiness=raw.get("task_readiness", "legacy_unspecified"),
                original_scoring_status=raw.get("scoring_status", "legacy_unspecified"),
                ground_truth=raw.get("ground_truth"), intermediate_decision=raw.get("intermediate_decision"),
                visible_evidence_pre_run_audit=task["evidence_audit"],
                human_confirmation="Separate provenance record required; readiness is not a human review verdict."))
    return result


def collect_review_records(manifest):
    """Exact source-case joins; approval fields alone do not identify a human."""
    cases = {r["source_case_id"]: r["task_slug"] for r in manifest["rows"]}
    directories = ["health_tasks", "environment_energy_tasks", "public_affairs_tasks",
                   "selected_cases_supplemental_fixed_misleaders", "selected_cases_workflow_ready",
                   "selected_cases_final_suitable", "selected_cases_target_aware"]
    records = []
    for directory in directories:
        path = PROJECT / "web_agent_benchmark" / directory / "review_annotations.json"
        annotations = read(path).get("annotations", {})
        for key, value in annotations.items():
            if value.get("case_id") not in cases:
                continue
            line = next((i for i, text in enumerate(path.read_text().splitlines(), 1)
                         if '"case_id"' in text and json.dumps(value["case_id"]) in text), None)
            records.append(dict(task_slug=cases[value["case_id"]], source=str(path),
                line=line, annotation_key=key, original_record=value,
                human_identity="not_recorded_in_this_annotation",
                interpretation="Existing review record retained verbatim. Do not infer no review from draft, or human authorship from filename."))
    return records


def response_routes(unit, ordinal, model):
    if model != "M_strong":
        return []
    result = []
    for path in sorted(unit.rglob("responses/*.json")):
        response = read(path)
        meta = response.get("metadata") or {}
        request_path = path.parent.parent / "requests" / path.name
        request = read(request_path) if request_path.exists() else {}
        result.append(dict(ordinal=ordinal, response=str(path), request=str(request_path),
            request_id=response.get("request_id"), phase=request.get("phase"), ok=response.get("ok"),
            requested_model=meta.get("requested_model"), response_model=meta.get("response_model"),
            gateway_reported_route=meta.get("gateway_reported_route"),
            usage_reported_model_name=(meta.get("usage") or {}).get("model_name"),
            wire_artifact=meta.get("wire_artifact"),
            transport_attempt_count=meta.get("transport_attempt_count"),
            supplied_images=meta.get("supplied_images"),
            provider_preprocessing=meta.get("provider_preprocessing")))
    return result


def wire_inventory():
    # Explicit historical cost segments. Earlier identity/engineering attempts
    # are accounting scope, not additional completed task trajectories.
    base = PROJECT / "research/prospective_simple_check_pilot"
    runs = ["authorized_pilot_20260907_v1/live_panel_01",
            "route_tolerant_20260907_v1/live_panel_01",
            "route_tolerant_20260907_v1/live_panel_02",
            "resumed_pilot_20260907_v1/live_panel_03",
            "internal_api_continuation_20260908_v1/live_panel_04"]
    records = []
    for name in runs:
        ledger_path = base / name / "api_wire/api_spend.json"
        ledger = read(ledger_path)
        for ordinal, entry in enumerate(ledger["entries"], 1):
            wire = ledger_path.parent / f"call_{ordinal:04d}"
            response = read(wire / "response.json") if (wire / "response.json").exists() else None
            records.append(dict(source_ledger=str(ledger_path), entry_ordinal=ordinal,
                request_id=entry.get("request_id"), status=entry["status"],
                wire_directory=str(wire), request_exists=(wire / "request.json").exists(),
                response_exists=response is not None,
                requested_model=entry.get("requested_model"), response_model=entry.get("response_model"),
                gateway_reported_route=entry.get("gateway_reported_route"),
                wire_response_model=response.get("model") if response else None,
                wire_usage_route=(response.get("usage") or {}).get("model_name") if response else None,
                http_status=entry.get("http_status"), attempt=entry.get("logical_transport_attempt", entry.get("attempt")),
                failed_usage="unknown_not_zero" if response is None else "see_original_response"))
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, output = resolve_path(args.run).resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a new output directory; old audit outputs are not overwritten.")
    table = read(run / "evaluator/CASE_TABLE.json")
    manifest = read(run / "TASK_MANIFEST.json")
    specs = raw_specs(manifest)
    expected = {(x["task_slug"], x["arm"]): x["expected_option"] for x in specs}
    base = sorted((r for r in table if r["strategy"] == "B0"), key=lambda r: r["ordinal"])
    pool, inputs, routes, rows, prefix_changes = [], [], [], [], []
    for row in base:
        unit = resolve_path(row.get("source_directory", run / "online" / f"unit_{row['ordinal']:02d}"))
        cp_path = unit / "prefix/checkpoint.json"
        cp = read(cp_path)
        pool.append(dict(ordinal=row["ordinal"], task_slug=row["task_slug"], arm=row["arm"], model=row["model"],
            source_directory=str(unit), checkpoint=str(cp_path), current_selection=cp["current_selection"],
            pending_proposal=cp["pending_proposal"], selected_for_new_diagnostic=None))
        inputs.append(input_pair(unit, row["ordinal"]))
        routes += response_routes(unit, row["ordinal"], row["model"])
        gold = expected[row["task_slug"], row["arm"]]
        if (cp["current_selection"] == gold) != row["checkpoint_correct"]:
            raise ValueError(f"Old checkpoint score mismatch at {row['ordinal']}")
        sequence, previous = [], None
        for step in read(unit / "prefix/timeline.json"):
            a, receipt = step.get("action") or {}, step.get("receipt") or {}
            if a.get("action") == "select_option" and a.get("select_name") == "primary_action" and receipt.get("executed"):
                current = a["option_text"]
                sequence.append(dict(step=step["step"], option=current, correct=current == gold))
                if previous is not None:
                    prefix_changes.append(dict(ordinal=row["ordinal"], task_slug=row["task_slug"],
                        step=step["step"], before=previous, after=current,
                        transition=transition(previous, current, gold)))
                previous = current
        pool[-1]["executed_selection_sequence"] = sequence
        for r in (x for x in table if x["ordinal"] == row["ordinal"]):
            final = (r.get("actor_final_submission") or {}).get("option") if r["confirmed_completion"] else None
            rec = r.get("verifier_recommendation") if r["verification_executed"] else None
            exe = r.get("executor_selection")
            if bool(final == gold and r["confirmed_completion"]) != r["confirmed_correct_completion"]:
                raise ValueError(f"Old final score mismatch at {row['ordinal']}/{r['strategy']}")
            rows.append(dict(ordinal=row["ordinal"], task_slug=row["task_slug"], model=row["model"], arm=row["arm"],
                strategy=r["strategy"], original=cp["current_selection"], expected=gold,
                recommendation=rec, execution_selection=exe, final_submission=final,
                verification_executed=r["verification_executed"], confirmed_submission=r["confirmed_completion"],
                recommendation_transition=transition(cp["current_selection"], rec, gold),
                execution_transition=transition(cp["current_selection"], exe, gold),
                final_transition=transition(cp["current_selection"], final, gold),
                actor_changed_executed_selection=final != exe if final is not None else None,
                source_directory=str(unit)))
    wire = wire_inventory()
    groups = []
    for model in ("M_small", "M_strong"):
        for arm in ("official140", "clean140"):
            subset = [r for r in rows if r["model"] == model and r["arm"] == arm]
            n0 = sum(r["strategy"] == "B0" and r["final_submission"] == r["expected"] for r in subset)
            for strategy in ("B0", "B2", "B3"):
                sub = [r for r in subset if r["strategy"] == strategy]
                n = sum(r["final_submission"] == r["expected"] for r in sub)
                groups.append(dict(model=model, arm=arm, strategy=strategy, count=len(sub), correct=n,
                    delta_correct_vs_B0=n-n0, relative_correct_count_change_vs_B0=(n-n0)/n0 if n0 else None,
                    recommendation=dict(Counter(r["recommendation_transition"] for r in sub)),
                    execution=dict(Counter(r["execution_transition"] for r in sub)),
                    final=dict(Counter(r["final_transition"] for r in sub))))
    summary = dict(created_at=datetime.now(timezone.utc).isoformat(), source_run=str(run),
        base_tasks=len(manifest["rows"]), existing_checkpoints=len(base), existing_strategy_records=len(rows),
        input_pairs=len(inputs),
        all_B2_one_image=all(len(x["B2_images"]) == 1 for x in inputs),
        all_B3_two_initial_images=all(len(x["B3_images"]) == 2 for x in inputs),
        all_B2_dashboard_equals_B3_dashboard=all(x["B2_image_to_B3_image_pixel_equality"] == [[False, True]] for x in inputs),
        all_same_goal_and_option_order=all(x["same_goal"] and x["same_option_order"] for x in inputs),
        all_system_prompts_differ=all(not x["same_system_prompt"] for x in inputs),
        B3_actual_public_receipt_counts=dict(Counter(x["B3_history_actions"] for x in inputs)),
        B3_prior_model_response_counts=dict(Counter(x["B3_prior_model_responses"] for x in inputs)),
        original_scores_reconciled=True,
        old_API_wire_attempts=len(wire), old_API_wire_statuses=dict(Counter(r["status"] for r in wire)),
        old_API_completed_routes=dict(Counter(r["gateway_reported_route"] or "not_reported" for r in wire if r["status"] == "completed")),
        linked_trajectory_API_response_records=len(routes),
        linked_successful_API_routes=dict(Counter(r["gateway_reported_route"] or "not_reported" for r in routes if r["ok"])),
        new_target_model_calls=0, new_browser_transitions=0, new_live_results="未运行",
        selected_four_tasks=None, blocking_document="Codex_PostPilot_Attribution_Diagnostic.md not found in workspace search",
        groups=groups, natural_prefix_selection_events=dict(Counter(x["transition"] for x in prefix_changes)),
        conclusion="Old B2/B3 comparison confounds context, image count/layout, prompts, and tool access; no causal attribution from these records alone.")
    output.mkdir(parents=True)
    for name, value in [("RAW_SPEC_ALIGNMENT.json", specs), ("EXISTING_CHECKPOINT_INDEX.json", pool),
                        ("TRANSITION_LAYERS.json", rows), ("PREFIX_SELECTION_TRANSITIONS.json", prefix_changes),
                        ("B2_B3_ACTUAL_INPUTS.json", inputs), ("API_ROUTE_BY_RESPONSE.json", routes),
                        ("API_WIRE_INVENTORY.json", wire), ("OFFLINE_SUMMARY.json", summary)]:
        write(output / name, value)
    lines = ["# 旧面板结果转移分层（仅离线复核）", "",
        "沿用原数据集 expected action；标注资格与人工审核另行对齐，不由字段或本脚本推翻人工审核。",
        "correct_to_correct=正确保持；correct_to_wrong=正确改错；wrong_to_correct=错误改对；wrong_to_same_wrong=保持原错；wrong_to_different_wrong=改成另一错。",
        "B0 的 recommendation 为未运行，不是核验失败。各组8个checkpoint，三策略为共享状态分支，不是独立任务。", "",
        "|模型|图表条件|方法|正确保持|正确改错|错误改对|保持原错|改成另一错|最终正确数|相对B0正确数变化|",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for g in groups:
        counts = [g["final"].get(k, 0) for k in ["correct_to_correct", "correct_to_wrong", "wrong_to_correct", "wrong_to_same_wrong", "wrong_to_different_wrong"]]
        delta = f"{g['relative_correct_count_change_vs_B0']:+.1%}" if g["relative_correct_count_change_vs_B0"] is not None else "N/A"
        lines.append("|" + "|".join(map(str, [g["model"], g["arm"], g["strategy"], *counts, g["correct"], delta])) + "|")
    lines += ["", "M_small=本地Qwen8B；M_strong=内网API请求Sol但上游权重未验证；official140=误导条件；clean140=原对照。", "",
        "推荐/实际选项/最终提交全部逐行见 TRANSITION_LAYERS.json；普通前缀的选择事件单独见 PREFIX_SELECTION_TRANSITIONS.json，不能把反复改选次数当独立样本。"]
    (output / "TRANSITION_REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
