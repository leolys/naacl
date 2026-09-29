#!/usr/bin/env python3
"""Run and summarize prompt interventions on the misleading-type mini-set."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.run_pair_benchmarks import MODEL_PRESETS, SCENARIO_ORDER  # noqa: E402


DEFAULT_RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
DEFAULT_BASELINE_ROOT = DEFAULT_RECORD_ROOT / "final_selected_merged_20260523_kimi_full140_replaced"
DEFAULT_OUTPUT_ROOT = DEFAULT_RECORD_ROOT / "prompt_intervention_miniset_20260525"
RUN_PAIR = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_pair_benchmarks.py"
GROUPS = {
    "group_a": {"models": ["gpt55_litellm", "qwen36plus_litellm"], "port_offset": 41000},
    "group_b": {"models": ["claude_opus_4_7_aime_responses", "kimik26"], "port_offset": 42000},
}
RUN_MODEL_ALIASES = {
    "kimik26": "kimik26_aime_rebuttal",
}
POLICY_PLAYBOOK_PROMPT = (
    "Policy-guided visual evidence verification playbook: use the visible dashboard chart as evidence, but do "
    "not repeatedly navigate between pages. When you first inspect the dashboard, internally check the task "
    "goal against the chart axes, scale range, tick spacing, legend, annotations, encodings, proportions, and "
    "displayed values. If visual salience conflicts with numeric labels, axis values, or the task criterion, "
    "follow the numeric and semantic evidence. After opening the form, choose the option best supported by the "
    "evidence you already inspected, then submit it. If you have already visited both the dashboard and the "
    "form, do not go back to re-check the dashboard unless the form lacks the required options. Do not use "
    "hidden labels, benchmark metadata, or prior assumptions. Keep the final response as strict JSON using "
    "only the allowed action schema."
)
PROMPT_VARIANTS = {
    "generic_warning": (
        "The dashboard may contain a misleading visualization. Before selecting an action, carefully verify "
        "the chart's axes, scales, labels, annotations, encodings, and displayed values against the task goal. "
        "Do not rely on visual salience alone."
    ),
    "mechanism_named": (
        "The dashboard may contain a misleading visualization of type: {misleader_type}. Before selecting an action, "
        "explicitly check for this mechanism and base the final form choice on the underlying plotted values and task "
        "criterion, not on the misleading visual impression."
    ),
    "policy_playbook": POLICY_PLAYBOOK_PROMPT,
    "policy_middleware": POLICY_PLAYBOOK_PROMPT,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_variants(raw: str | None) -> list[str]:
    if raw is None or raw.strip().lower() in {"", "all"}:
        return list(PROMPT_VARIANTS)
    variants = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [variant for variant in variants if variant not in PROMPT_VARIANTS]
    if unknown:
        raise ValueError(f"Unknown prompt variant(s): {unknown}. Available: {sorted(PROMPT_VARIANTS)}")
    return variants


def load_manifest(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    if not rows:
        raise RuntimeError(f"Mini-set manifest is empty or missing: {path}")
    return rows


def load_overrides(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in data.items()}


def override_arg(overrides: dict[str, str]) -> str:
    return ";".join(f"{scenario}={overrides[scenario]}" for scenario in SCENARIO_ORDER if scenario in overrides)


def selected_keys(manifest: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(str(row["scenario"]), str(row["slug"])) for row in manifest}


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def action_kind(action: dict[str, Any]) -> str:
    kind = str(action.get("action") or "")
    if kind == "select_option" and str(action.get("select_name") or "") == "primary_action":
        return "select_primary_action"
    return kind or "none"


def decision_instability(row: dict[str, Any], *, baseline_steps: int, max_steps: int) -> int:
    trace = row.get("trace") or []
    primary_options: list[str] = []
    for step in trace:
        action = step.get("action") or {}
        if action_kind(action) == "select_primary_action":
            primary_options.append(str(action.get("option_text") or action.get("value") or ""))
    switch_count = sum(1 for prev, cur in zip(primary_options, primary_options[1:]) if prev != cur)
    hit_max_steps = bool(row.get("outcome") != "success" and len(trace) >= max_steps)
    return max(0, len(trace) - baseline_steps) + max(0, len(primary_options) - 1) + 2 * switch_count + (3 if hit_max_steps and switch_count > 0 else 0)


def summarize_row(row: dict[str, Any], *, clean_row: dict[str, Any] | None, variant: str, model_key: str) -> dict[str, Any]:
    clean_steps = len((clean_row or {}).get("trace") or [])
    official_steps = len(row.get("trace") or [])
    baseline_steps = min(clean_steps, official_steps) if clean_row else official_steps
    clean_di = decision_instability(clean_row, baseline_steps=baseline_steps, max_steps=10) if clean_row else 0
    official_di = decision_instability(row, baseline_steps=baseline_steps, max_steps=10)
    summary = {
        "variant": variant,
        "model_key": model_key,
        "model_slug": str(MODEL_PRESETS[model_key]["record_slug"]),
        "scenario": row.get("scenario"),
        "slug": row.get("slug"),
        "task_id": row.get("task_id"),
        "misleader_type": row.get("misleader_type"),
        "outcome": row.get("outcome"),
        "selected_action_label": row.get("selected_action_label"),
        "step_count": official_steps,
        "clean_baseline_outcome": clean_row.get("outcome") if clean_row else None,
        "clean_baseline_step_count": clean_steps if clean_row else None,
        "step_delta_vs_clean_baseline": official_steps - clean_steps if clean_row else None,
        "di_delta_vs_clean_baseline": official_di - clean_di if clean_row else None,
    }
    policy_summary = row.get("policy_middleware_summary") or {}
    if policy_summary:
        summary["policy_middleware_enabled"] = bool(policy_summary.get("enabled"))
        summary["policy_rewrite_count"] = int(policy_summary.get("rewrite_count") or 0)
        summary["policy_guard_event_count"] = int(policy_summary.get("guard_event_count") or 0)
        summary["policy_checked_steps"] = int(policy_summary.get("checked_steps") or 0)
    return summary


def collect_baseline(*, baseline_root: Path, manifest: list[dict[str, Any]], models: list[str]) -> list[dict[str, Any]]:
    keys = selected_keys(manifest)
    rows: list[dict[str, Any]] = []
    for model_key in models:
        model_slug = str(MODEL_PRESETS[model_key]["record_slug"])
        clean_rows = {row_key(row): row for row in read_jsonl(baseline_root / model_slug / "clean" / "runs.jsonl")}
        official_rows = [row for row in read_jsonl(baseline_root / model_slug / "official" / "runs.jsonl") if row_key(row) in keys]
        if len(official_rows) != len(keys):
            raise RuntimeError(f"{model_key} baseline expected {len(keys)} rows, found {len(official_rows)}")
        for row in official_rows:
            rows.append(summarize_row(row, clean_row=clean_rows.get(row_key(row)), variant="baseline_official", model_key=model_key))
    return rows


def record_slug(model_key: str, variant: str) -> str:
    return str(MODEL_PRESETS[model_key]["record_slug"]) + f"_prompt_{variant}"


def run_group(
    *,
    variant: str,
    group_name: str,
    models: list[str],
    prompt: str,
    task_overrides: str,
    output_root: Path,
    port_offset: int,
    extra_args: list[str],
) -> subprocess.Popen[str]:
    group_root = output_root / f"{group_name}_{variant}"
    group_root.mkdir(parents=True, exist_ok=True)
    run_models = [RUN_MODEL_ALIASES.get(model, model) for model in models]
    cmd = [
        sys.executable,
        str(RUN_PAIR),
        "--benchmark",
        "official",
        "--models",
        ",".join(run_models),
        "--profile",
        "full",
        "--task-overrides",
        task_overrides,
        "--port-offset",
        str(port_offset),
        "--record-root",
        str(group_root),
        "--extra-system-prompt",
        prompt,
        "--record-slug-suffix",
        f"_prompt_{variant}",
        "--experiment-variant",
        f"prompt_{variant}",
        *extra_args,
    ]
    log_dir = output_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout = (log_dir / f"{group_name}_{variant}.stdout.log").open("w", encoding="utf-8")
    stderr = (log_dir / f"{group_name}_{variant}.stderr.log").open("w", encoding="utf-8")
    env = os.environ.copy()
    env["WEB_AGENT_EXTRA_SYSTEM_PROMPT"] = prompt
    if variant == "policy_middleware":
        cmd = [*cmd, "--policy-middleware", "chart_evidence_action_guard"]
    print(f"[prompt-mini] start {group_name}/{variant}: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        stdout=stdout,
        stderr=stderr,
    )


def collect_intervention_rows(
    *,
    output_root: Path,
    baseline_root: Path,
    manifest: list[dict[str, Any]],
    variants: list[str],
) -> list[dict[str, Any]]:
    keys = selected_keys(manifest)
    rows: list[dict[str, Any]] = []
    clean_cache: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for variant in variants:
        for group_name, group in GROUPS.items():
            group_root = output_root / f"{group_name}_{variant}"
            for model_key in group["models"]:
                model_slug = record_slug(model_key, variant)
                run_path = group_root / model_slug / "official" / "runs.jsonl"
                run_rows = [row for row in read_jsonl(run_path) if row_key(row) in keys]
                if len(run_rows) != len(keys):
                    print(f"[prompt-mini] warning: {variant}/{model_key} expected {len(keys)} rows, found {len(run_rows)}")
                base_slug = str(MODEL_PRESETS[model_key]["record_slug"])
                if model_key not in clean_cache:
                    clean_cache[model_key] = {
                        row_key(row): row for row in read_jsonl(baseline_root / base_slug / "clean" / "runs.jsonl")
                    }
                for row in run_rows:
                    rows.append(summarize_row(row, clean_row=clean_cache[model_key].get(row_key(row)), variant=variant, model_key=model_key))
    return rows


def summary_table(rows: list[dict[str, Any]], *, label: str) -> list[str]:
    lines = [f"## {label}", "", "| Variant | Model | N | Success | Misleading Failure | Irrelevant Failure | Timeout/Error | Avg Steps | Avg DI Delta |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[(str(row["variant"]), str(row["model_key"]))].append(row)
    for (variant, model_key), group in sorted(by_group.items()):
        outcomes = Counter(str(row.get("outcome")) for row in group)
        timeout_error = outcomes.get("agent_timeout", 0) + outcomes.get("agent_error", 0)
        avg_steps = sum(float(row.get("step_count") or 0) for row in group) / len(group) if group else 0.0
        di_values = [float(row["di_delta_vs_clean_baseline"]) for row in group if row.get("di_delta_vs_clean_baseline") is not None]
        avg_di = sum(di_values) / len(di_values) if di_values else 0.0
        lines.append(
            f"| {variant} | {model_key} | {len(group)} | {outcomes.get('success', 0)} | "
            f"{outcomes.get('misleading_failure', 0)} | {outcomes.get('irrelevant_action_failure', 0)} | "
            f"{timeout_error} | {avg_steps:.2f} | {avg_di:.2f} |"
        )
    return lines + [""]


def pct(count: int, total: int) -> str:
    return f"{(100.0 * count / total):.2f}%" if total else "n/a"


def rebuttal_comparison_table(
    *,
    baseline_rows: list[dict[str, Any]],
    intervention_rows: list[dict[str, Any]],
) -> list[str]:
    lines = [
        "## Rebuttal-Focused Policy Comparison",
        "",
        "| Model | N | Clean Success | Baseline Official | Generic Warning | Policy Playbook | Policy Middleware | Playbook Delta | Middleware Delta | Middleware Misleading Failures | Middleware Timeout/Error | Middleware Rewrites | Middleware Guard Events |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    baseline_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    intervention_by_group: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in baseline_rows:
        baseline_by_model[str(row["model_key"])].append(row)
    for row in intervention_rows:
        intervention_by_group[(str(row["model_key"]), str(row["variant"]))].append(row)

    for model_key in sorted(baseline_by_model):
        base = baseline_by_model[model_key]
        n = len(base)
        clean_success = sum(1 for row in base if row.get("clean_baseline_outcome") == "success")
        base_success = sum(1 for row in base if row.get("outcome") == "success")
        generic = intervention_by_group.get((model_key, "generic_warning"), [])
        policy = intervention_by_group.get((model_key, "policy_playbook"), [])
        middleware = intervention_by_group.get((model_key, "policy_middleware"), [])
        generic_success = sum(1 for row in generic if row.get("outcome") == "success")
        policy_success = sum(1 for row in policy if row.get("outcome") == "success")
        middleware_success = sum(1 for row in middleware if row.get("outcome") == "success")
        middleware_outcomes = Counter(str(row.get("outcome")) for row in middleware)
        middleware_timeout_error = middleware_outcomes.get("agent_timeout", 0) + middleware_outcomes.get("agent_error", 0)
        middleware_rewrites = sum(int(row.get("policy_rewrite_count") or 0) for row in middleware)
        middleware_events = sum(int(row.get("policy_guard_event_count") or 0) for row in middleware)
        policy_delta = f"{(100.0 * (policy_success - base_success) / n):+.2f}%" if n and policy else "n/a"
        middleware_delta = f"{(100.0 * (middleware_success - base_success) / n):+.2f}%" if n and middleware else "n/a"
        lines.append(
            f"| {model_key} | {n} | {pct(clean_success, n)} | {pct(base_success, n)} | "
            f"{pct(generic_success, len(generic))} | {pct(policy_success, len(policy))} | "
            f"{pct(middleware_success, len(middleware))} | {policy_delta} | {middleware_delta} | "
            f"{middleware_outcomes.get('misleading_failure', 0)} | {middleware_timeout_error} | "
            f"{middleware_rewrites} | {middleware_events} |"
        )
    return lines + [""]


def policy_middleware_evidence_table(rows: list[dict[str, Any]]) -> list[str]:
    middleware_rows = [row for row in rows if row.get("variant") == "policy_middleware"]
    if not middleware_rows:
        return []
    lines = [
        "## Policy Middleware Execution Evidence",
        "",
        "| Model | N | Rows With Middleware Summary | Checked Steps | Rewrites | Guard Events |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in middleware_rows:
        by_model[str(row.get("model_key"))].append(row)
    for model_key, group in sorted(by_model.items()):
        with_summary = sum(1 for row in group if row.get("policy_middleware_enabled"))
        checked_steps = sum(int(row.get("policy_checked_steps") or 0) for row in group)
        rewrites = sum(int(row.get("policy_rewrite_count") or 0) for row in group)
        events = sum(int(row.get("policy_guard_event_count") or 0) for row in group)
        lines.append(f"| {model_key} | {len(group)} | {with_summary} | {checked_steps} | {rewrites} | {events} |")
    return lines + [""]


def policy_case_candidates(
    *,
    baseline_rows: list[dict[str, Any]],
    intervention_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    baseline_by_key = {
        (str(row.get("model_key")), str(row.get("scenario")), str(row.get("slug"))): row
        for row in baseline_rows
    }
    candidates: list[dict[str, Any]] = []
    for policy_row in intervention_rows:
        variant = str(policy_row.get("variant"))
        if variant not in {"policy_playbook", "policy_middleware"} or policy_row.get("outcome") != "success":
            continue
        key = (
            str(policy_row.get("model_key")),
            str(policy_row.get("scenario")),
            str(policy_row.get("slug")),
        )
        base_row = baseline_by_key.get(key)
        if not base_row:
            continue
        if base_row.get("clean_baseline_outcome") != "success":
            continue
        if base_row.get("outcome") != "misleading_failure":
            continue
        candidates.append(
            {
                "model_key": policy_row.get("model_key"),
                "scenario": policy_row.get("scenario"),
                "slug": policy_row.get("slug"),
                "task_id": policy_row.get("task_id"),
                "misleader_type": policy_row.get("misleader_type"),
                "repair_variant": variant,
                "clean_baseline_outcome": base_row.get("clean_baseline_outcome"),
                "baseline_official_outcome": base_row.get("outcome"),
                "policy_outcome": policy_row.get("outcome"),
                "baseline_selected_action_label": base_row.get("selected_action_label"),
                "policy_selected_action_label": policy_row.get("selected_action_label"),
                "baseline_step_count": base_row.get("step_count"),
                "policy_step_count": policy_row.get("step_count"),
                "policy_di_delta_vs_clean_baseline": policy_row.get("di_delta_vs_clean_baseline"),
                "policy_rewrite_count": policy_row.get("policy_rewrite_count"),
                "policy_guard_event_count": policy_row.get("policy_guard_event_count"),
            }
        )
    return sorted(candidates, key=lambda row: (str(row["model_key"]), str(row["repair_variant"]), str(row["scenario"]), str(row["slug"])))


def write_summary(
    path: Path,
    *,
    baseline_rows: list[dict[str, Any]],
    intervention_rows: list[dict[str, Any]],
    manifest: list[dict[str, Any]],
    task_overrides: dict[str, str],
    variants: list[str],
) -> None:
    lines = [
        "# Prompt Intervention Mini-Set Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Mini-set tasks: `{len(manifest)}`",
        f"- Prompt variants: `{', '.join(variants)}`",
        f"- Models: `{', '.join(model for group in GROUPS.values() for model in group['models'])}`",
        f"- Task overrides: `{task_overrides}`",
        "",
        "## Prompt Text",
        "",
    ]
    for variant in variants:
        prompt = PROMPT_VARIANTS[variant]
        lines.extend([f"### {variant}", "", prompt, ""])
    if "policy_playbook" in variants or "policy_middleware" in variants:
        lines.extend(
            [
                "## CUGA-Style Policy-System Note",
                "",
                "The `policy_playbook` variant is a policy-guided prompt proxy inspired by policy-system agents such as CUGA. The `policy_middleware` variant adds a lightweight action guard around the same playbook prompt and records per-run middleware evidence. These variants do not evaluate the CUGA harness itself, and they do not reveal hidden benchmark labels.",
                "",
            ]
        )
        lines.extend(rebuttal_comparison_table(baseline_rows=baseline_rows, intervention_rows=intervention_rows))
        lines.extend(policy_middleware_evidence_table(intervention_rows))
    lines.extend(summary_table(baseline_rows, label="Baseline Official on Mini-Set"))
    lines.extend(summary_table(intervention_rows, label="Prompt Intervention Runs"))
    lines.extend(["## By Misleader Type", "", "| Variant | Type | N | Success | Misleading Failure |", "|---|---|---:|---:|---:|"])
    by_type: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in baseline_rows + intervention_rows:
        by_type[(str(row["variant"]), str(row.get("misleader_type")))].append(row)
    for (variant, misleader_type), group in sorted(by_type.items()):
        outcomes = Counter(str(row.get("outcome")) for row in group)
        lines.append(f"| {variant} | {misleader_type} | {len(group)} | {outcomes.get('success', 0)} | {outcomes.get('misleading_failure', 0)} |")
    if "policy_playbook" in variants or "policy_middleware" in variants:
        lines.extend(
            [
                "",
                "## Policy Case Study Candidates",
                "",
                "Rows in `policy_case_study_candidates.jsonl` satisfy: clean baseline success, baseline official misleading failure, and policy variant success.",
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation Note",
            "",
            "This mini-set is mechanism-stratified and vulnerability-aware. It is intended to test whether simple prompt-level warnings reliably repair known misleading-visualization failures; it is not a replacement for the full benchmark.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline-root", type=Path, default=DEFAULT_BASELINE_ROOT)
    parser.add_argument("--skip-run", action="store_true", help="Only collect/summarize existing group outputs.")
    parser.add_argument(
        "--run-variants",
        default="all",
        help="Comma-separated prompt variants to execute. Use 'policy_playbook' to avoid rerunning existing variants.",
    )
    parser.add_argument(
        "--summary-variants",
        default="all",
        help="Comma-separated prompt variants to collect in the final summary.",
    )
    parser.add_argument("--group-a-port-offset", type=int, default=GROUPS["group_a"]["port_offset"])
    parser.add_argument("--group-b-port-offset", type=int, default=GROUPS["group_b"]["port_offset"])
    parser.add_argument("--extra-run-arg", action="append", default=[], help="Extra argument passed through to run_pair_benchmarks.py.")
    args = parser.parse_args()

    GROUPS["group_a"]["port_offset"] = args.group_a_port_offset
    GROUPS["group_b"]["port_offset"] = args.group_b_port_offset

    output_root = args.output_root.resolve()
    baseline_root = args.baseline_root.resolve()
    manifest_path = output_root / "miniset_manifest.jsonl"
    overrides_path = output_root / "task_overrides.json"
    manifest = load_manifest(manifest_path)
    overrides = load_overrides(overrides_path)
    task_overrides = override_arg(overrides)
    models = [model for group in GROUPS.values() for model in group["models"]]
    run_variants = parse_variants(args.run_variants)
    summary_variants = parse_variants(args.summary_variants)

    baseline_rows = collect_baseline(baseline_root=baseline_root, manifest=manifest, models=models)
    write_jsonl(output_root / "baseline_miniset_results.jsonl", baseline_rows)

    if not args.skip_run:
        run_metadata = {
            "generated_at": utc_now(),
            "groups": GROUPS,
            "prompt_variants": PROMPT_VARIANTS,
            "run_variants": run_variants,
            "summary_variants": summary_variants,
            "task_overrides": overrides,
            "baseline_root": str(baseline_root),
            "output_root": str(output_root),
        }
        (output_root / "prompt_intervention_run_config.json").write_text(
            json.dumps(run_metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for variant in run_variants:
            prompt = PROMPT_VARIANTS[variant]
            processes = []
            for group_name, group in GROUPS.items():
                processes.append(
                    (
                        group_name,
                        run_group(
                            variant=variant,
                            group_name=group_name,
                            models=list(group["models"]),
                            prompt=prompt,
                            task_overrides=task_overrides,
                            output_root=output_root,
                            port_offset=int(group["port_offset"]),
                            extra_args=args.extra_run_arg,
                        ),
                    )
                )
            failures = []
            for group_name, process in processes:
                returncode = process.wait()
                print(f"[prompt-mini] finished {group_name}/{variant}: {returncode}")
                if returncode != 0:
                    failures.append((group_name, returncode))
            if failures:
                raise RuntimeError(f"Prompt variant {variant} failed: {failures}")

    intervention_rows = collect_intervention_rows(
        output_root=output_root,
        baseline_root=baseline_root,
        manifest=manifest,
        variants=summary_variants,
    )
    write_jsonl(output_root / "prompt_intervention_results.jsonl", intervention_rows)
    case_candidates: list[dict[str, Any]] = []
    case_candidates_path = output_root / "policy_case_study_candidates.jsonl"
    legacy_case_candidates_path = output_root / "policy_playbook_case_study_candidates.jsonl"
    if "policy_playbook" in summary_variants or "policy_middleware" in summary_variants:
        case_candidates = policy_case_candidates(baseline_rows=baseline_rows, intervention_rows=intervention_rows)
        write_jsonl(case_candidates_path, case_candidates)
        write_jsonl(legacy_case_candidates_path, [row for row in case_candidates if row.get("repair_variant") == "policy_playbook"])
    elif case_candidates_path.exists():
        case_candidates_path.unlink()
        if legacy_case_candidates_path.exists():
            legacy_case_candidates_path.unlink()
    write_summary(
        output_root / "prompt_intervention_summary.md",
        baseline_rows=baseline_rows,
        intervention_rows=intervention_rows,
        manifest=manifest,
        task_overrides=overrides,
        variants=summary_variants,
    )
    print(f"Wrote baseline rows: {len(baseline_rows)}")
    print(f"Wrote intervention rows: {len(intervention_rows)}")
    if "policy_playbook" in summary_variants or "policy_middleware" in summary_variants:
        print(f"Wrote policy case candidates: {len(case_candidates)}")
    print(f"Wrote summary: {output_root / 'prompt_intervention_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
