#!/usr/bin/env python3
"""Analyze CUGA v2 control/playbook transitions, guard audits, and v1 comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_v2_guarded_full140_gpt54_20260711"
)
DEFAULT_V1_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_full140_gpt54_20260711"
)
CONTROL = "default_v2_control"
POLICY = "playbook_v2_guarded"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("condition")),
        str(row.get("benchmark")),
        str(row.get("scenario")),
        str(row.get("slug")),
    )


def exact_mcnemar_p(recoveries: int, regressions: int) -> float:
    discordant = recoveries + regressions
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(recoveries, regressions) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def effect(control_outcome: str, policy_outcome: str) -> str:
    control_success = control_outcome == "success"
    policy_success = policy_outcome == "success"
    if not control_success and policy_success:
        return "recovery"
    if control_success and not policy_success:
        return "regression"
    if control_success:
        return "unchanged_success"
    return "unchanged_failure"


def actions(row: dict[str, Any]) -> list[str]:
    return [
        str(step.get("action_formatted") or step.get("name") or "")
        for step in row.get("cuga_steps") or []
        if step.get("action_formatted") or step.get("name")
    ]


def build_transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {key(row): row for row in rows}
    cases = sorted({(str(row["scenario"]), str(row["slug"])) for row in rows})
    transitions: list[dict[str, Any]] = []
    for benchmark in ("official", "clean"):
        for scenario, slug in cases:
            control = by_key.get((CONTROL, benchmark, scenario, slug))
            policy = by_key.get((POLICY, benchmark, scenario, slug))
            if not control or not policy:
                continue
            transitions.append(
                {
                    "benchmark": benchmark,
                    "scenario": scenario,
                    "slug": slug,
                    "case_id": control.get("case_id") or policy.get("case_id"),
                    "misleader_type": control.get("misleader_type") or policy.get("misleader_type"),
                    "control_outcome": control.get("outcome"),
                    "policy_outcome": policy.get("outcome"),
                    "effect": effect(str(control.get("outcome")), str(policy.get("outcome"))),
                    "control_action_count": control.get("cuga_action_count"),
                    "policy_action_count": policy.get("cuga_action_count"),
                    "control_internal_step_count": control.get("cuga_internal_step_count"),
                    "policy_internal_step_count": policy.get("cuga_internal_step_count"),
                    "control_actions": actions(control),
                    "policy_actions": actions(policy),
                    "guard_summary": policy.get("guard_summary") or {},
                }
            )
    return transitions


def cell_metrics(rows: list[dict[str, Any]], condition: str, benchmark: str) -> dict[str, Any]:
    subset = [
        row
        for row in rows
        if row.get("condition") == condition and row.get("benchmark") == benchmark
    ]
    counts = Counter(str(row.get("outcome")) for row in subset)
    n = len(subset)
    return {
        "n": n,
        "success": counts["success"],
        "success_rate": counts["success"] / n if n else 0.0,
        "misleading_failure": counts["misleading_failure"],
        "agent_error": counts["agent_error"],
        "agent_timeout": counts["agent_timeout"],
        "guard_error": sum(bool((row.get("guard_summary") or {}).get("has_guard_error")) for row in subset),
        "avg_actions": (
            sum(int(row.get("cuga_action_count") or 0) for row in subset) / n if n else 0.0
        ),
        "avg_internal_steps": (
            sum(int(row.get("cuga_internal_step_count") or 0) for row in subset) / n
            if n
            else 0.0
        ),
        "avg_elapsed_sec": (
            sum(float(row.get("elapsed_sec") or 0.0) for row in subset) / n if n else 0.0
        ),
    }


def paired_metrics(rows: list[dict[str, Any]], condition: str) -> dict[str, Any]:
    by_key = {key(row): row for row in rows}
    cases = sorted({(str(row["scenario"]), str(row["slug"])) for row in rows})
    pairs = []
    for scenario, slug in cases:
        official = by_key.get((condition, "official", scenario, slug))
        clean = by_key.get((condition, "clean", scenario, slug))
        if official and clean:
            pairs.append((official, clean))
    n = len(pairs)
    official_success = sum(a.get("outcome") == "success" for a, _ in pairs)
    clean_success = sum(b.get("outcome") == "success" for _, b in pairs)
    return {
        "n": n,
        "official_success": official_success,
        "clean_success": clean_success,
        "clean_minus_official_pp": (
            100.0 * (clean_success - official_success) / n if n else 0.0
        ),
        "official_misleading_clean_success": sum(
            a.get("outcome") == "misleading_failure" and b.get("outcome") == "success"
            for a, b in pairs
        ),
        "clean_regression": sum(
            a.get("outcome") == "success" and b.get("outcome") != "success"
            for a, b in pairs
        ),
        "both_failed": sum(
            a.get("outcome") != "success" and b.get("outcome") != "success"
            for a, b in pairs
        ),
    }


def transition_metrics(transitions: list[dict[str, Any]], benchmark: str) -> dict[str, Any]:
    subset = [row for row in transitions if row.get("benchmark") == benchmark]
    counts = Counter(str(row.get("effect")) for row in subset)
    recoveries = counts["recovery"]
    regressions = counts["regression"]
    return {
        "n": len(subset),
        **dict(counts),
        "mcnemar_exact_p": exact_mcnemar_p(recoveries, regressions),
    }


def guard_audit(
    rows: list[dict[str, Any]],
    root: Path,
    *,
    require_policy_events: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    audit_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    forbidden = {
        "ground_truth",
        "misleader_type",
        "expected_action_id",
        "misleading_action_ids",
        "evaluation_hidden_from_agent",
        "outcome",
    }
    for row in rows:
        condition = str(row.get("condition"))
        summary = row.get("guard_summary") or {}
        events = row.get("guard_events") or []
        item = {
            "condition": condition,
            "benchmark": row.get("benchmark"),
            "scenario": row.get("scenario"),
            "slug": row.get("slug"),
            "guard_summary": summary,
            "guard_event_count": len(events),
            "guard_not_reached": condition == POLICY and not events,
            "input_artifacts_verified": 0,
            "input_artifact_errors": [],
        }
        serialized_inputs = json.dumps(
            [event.get("input") for event in events], ensure_ascii=False
        ).lower()
        leaked = sorted(field for field in forbidden if f'"{field}"' in serialized_inputs)
        if leaked:
            item["input_artifact_errors"].append(f"forbidden input keys: {leaked}")
        if condition == POLICY:
            if require_policy_events and not events:
                item["input_artifact_errors"].append("missing guard events")
            if int(summary.get("guard_call_count") or 0) > 2:
                item["input_artifact_errors"].append("guard_call_count exceeds 2")
            if int(summary.get("guard_block_count") or 0) > 1:
                item["input_artifact_errors"].append("guard_block_count exceeds 1")
            for event in events:
                input_data = event.get("input") or {}
                screenshot_path = input_data.get("screenshot_path")
                screenshot_hash = input_data.get("screenshot_sha256")
                if not screenshot_path:
                    continue
                path = REPO_ROOT / str(screenshot_path)
                if not path.exists():
                    item["input_artifact_errors"].append(f"missing screenshot: {screenshot_path}")
                    continue
                if screenshot_hash and hashlib.sha256(path.read_bytes()).hexdigest() != screenshot_hash:
                    item["input_artifact_errors"].append(f"screenshot hash mismatch: {screenshot_path}")
                    continue
                item["input_artifacts_verified"] += 1
        elif events or summary.get("enabled"):
            item["input_artifact_errors"].append("Default condition unexpectedly used Guard")
        if item["input_artifact_errors"]:
            errors.append(
                f"{condition}/{row.get('benchmark')}/{row.get('scenario')}/{row.get('slug')}: "
                + "; ".join(item["input_artifact_errors"])
            )
        audit_rows.append(item)
    return audit_rows, errors


def validate(
    rows: list[dict[str, Any]],
    audit_errors: list[str],
    expected_cases: int,
    strict_smoke: bool,
) -> dict[str, Any]:
    expected_rows = expected_cases * 4
    unique = {key(row) for row in rows}
    policy_rows = [row for row in rows if row.get("condition") == POLICY]
    default_rows = [row for row in rows if row.get("condition") == CONTROL]
    checks = {
        "row_count": len(rows) == expected_rows,
        "unique_key_count": len(unique) == expected_rows,
        "agent_error_zero": not any(row.get("outcome") == "agent_error" for row in rows),
        "guard_error_zero": not any(
            bool((row.get("guard_summary") or {}).get("has_guard_error")) for row in rows
        ),
        "policy_match_all": all(
            bool((row.get("policy_enactment") or {}).get("matched")) for row in policy_rows
        )
        and len(policy_rows) == expected_cases * 2,
        "default_match_zero": not any(
            bool((row.get("policy_enactment") or {}).get("matched")) for row in default_rows
        )
        and len(default_rows) == expected_cases * 2,
        "guard_audit_clean": not audit_errors,
        "default_guard_calls_zero": not any(row.get("guard_events") for row in default_rows),
        "policy_guard_limits": all(
            int((row.get("guard_summary") or {}).get("guard_call_count") or 0) <= 2
            and int((row.get("guard_summary") or {}).get("guard_block_count") or 0) <= 1
            for row in policy_rows
        ),
    }
    if strict_smoke:
        checks["timeout_zero"] = not any(row.get("outcome") == "agent_timeout" for row in rows)
        checks["policy_guard_audit_present"] = all(
            bool(row.get("guard_events"))
            and int((row.get("guard_summary") or {}).get("guard_call_count") or 0) >= 1
            for row in policy_rows
        )
    return {
        "generated_at": utc_now(),
        "expected_cases": expected_cases,
        "expected_rows": expected_rows,
        "actual_rows": len(rows),
        "actual_unique_keys": len(unique),
        "checks": checks,
        "passed": all(checks.values()),
        "audit_errors": audit_errors,
    }


def render_transitions(transitions: list[dict[str, Any]]) -> str:
    lines = [
        "# CUGA v2 Case Transitions",
        "",
        "| Split | Scenario | Slug | Effect | Control | Playbook v2 + Guard | Guard state |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in transitions:
        lines.append(
            f"| {row['benchmark']} | {row['scenario']} | {row['slug']} | {row['effect']} | "
            f"{row['control_outcome']} | {row['policy_outcome']} | "
            f"{row['guard_summary'].get('guard_final_state', '')} |"
        )
    return "\n".join(lines) + "\n"


def render_guard_audit(audit_rows: list[dict[str, Any]], errors: list[str]) -> str:
    policy_rows = [row for row in audit_rows if row.get("condition") == POLICY]
    lines = [
        "# PreSubmitGuard Audit",
        "",
        f"- Policy rows: `{len(policy_rows)}`",
        f"- Guard calls: `{sum(int((row['guard_summary'] or {}).get('guard_call_count') or 0) for row in policy_rows)}`",
        f"- HTTP attempts: `{sum(int((row['guard_summary'] or {}).get('guard_http_attempt_count') or 0) for row in policy_rows)}`",
        f"- Blocks: `{sum(int((row['guard_summary'] or {}).get('guard_block_count') or 0) for row in policy_rows)}`",
        f"- Unresolved allows: `{sum(int((row['guard_summary'] or {}).get('guard_unresolved_count') or 0) for row in policy_rows)}`",
        f"- Guard errors: `{sum(bool((row['guard_summary'] or {}).get('has_guard_error')) for row in policy_rows)}`",
        f"- Guard not reached: `{sum(bool(row.get('guard_not_reached')) for row in policy_rows)}`",
        f"- Audit errors: `{len(errors)}`",
        "",
    ]
    if errors:
        lines.extend(["## Errors", ""] + [f"- {error}" for error in errors])
    return "\n".join(lines) + "\n"


def render_v1_v2(rows: list[dict[str, Any]], v1_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# CUGA Policy-System v1-v2 Comparison",
        "",
        "> Playbook v2 + Guard was refined after inspecting v1 results. This is a post-hoc engineering follow-up, not an independent confirmatory experiment.",
        "",
        "| Version | Condition | Misleading-chart task success | Directed misleading-choice failures | Clean-task success | Clean minus misleading-chart success |",
        "|---|---|---:|---:|---:|---:|",
    ]
    specs = [
        ("v1", "default", v1_rows),
        ("v1", "playbook", v1_rows),
        ("v2", CONTROL, rows),
        ("v2", POLICY, rows),
    ]
    for version, condition, source in specs:
        official = cell_metrics(source, condition, "official")
        clean = cell_metrics(source, condition, "clean")
        gap = 100.0 * (clean["success_rate"] - official["success_rate"])
        lines.append(
            f"| {version} | {condition} | {official['success']}/{official['n']} "
            f"({100 * official['success_rate']:.1f}%) | "
            f"{official['misleading_failure']}/{official['n']} | "
            f"{clean['success']}/{clean['n']} ({100 * clean['success_rate']:.1f}%) | {gap:+.1f} pp |"
        )
    return "\n".join(lines) + "\n"


def render_rebuttal(
    rows: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    validation: dict[str, Any],
) -> str:
    official_effects = transition_metrics(transitions, "official")
    clean_effects = transition_metrics(transitions, "clean")
    lines = [
        "# Reviewer 4H6i: CUGA Playbook v2 + PreSubmitGuard",
        "",
        "## Protocol",
        "",
        "- Agent: CUGA 0.3.0 legacy Playwright web graph, driven by GPT-5.4.",
        "- Conditions: time-matched empty policy store versus an AlwaysTrigger evidence-first Playbook plus a visible-only pre-submit Guard.",
        "- Guard inputs are limited to the current full-page screenshot, visible page text, visible form options, and CUGA's proposed option.",
        "- The Guard never receives task JSON, answer labels, misleading mechanism labels, or evaluator fields; it can block once but cannot replace CUGA's answer.",
        "- The v2 mechanism was refined after v1 diagnostics and is reported as post-hoc.",
        "- `official` is only the internal split identifier; it denotes the task version containing misleading charts.",
        "- Task success means submitting the expected action. A directed misleading-choice failure means submitting one of the task's predefined misleading actions. These outcomes are mutually exclusive but not exhaustive; irrelevant actions, incomplete workflows, timeouts, and agent errors form the remaining outcomes.",
        "",
        "## Aggregate Results",
        "",
        "| Condition | Misleading-chart task success | Directed misleading-choice failures | Clean-task success | Clean minus misleading-chart success | Avg misleading-chart actions | Avg misleading-chart internal steps |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in (CONTROL, POLICY):
        official = cell_metrics(rows, condition, "official")
        clean = cell_metrics(rows, condition, "clean")
        gap = 100.0 * (clean["success_rate"] - official["success_rate"])
        lines.append(
            f"| {condition} | {official['success']}/{official['n']} "
            f"({100 * official['success_rate']:.1f}%) | "
            f"{official['misleading_failure']}/{official['n']} | "
            f"{clean['success']}/{clean['n']} ({100 * clean['success_rate']:.1f}%) | "
            f"{gap:+.1f} pp | {official['avg_actions']:.2f} | {official['avg_internal_steps']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Paired Policy Effects",
            "",
            f"- Misleading-chart task version: `{official_effects.get('recovery', 0)}` recoveries, `{official_effects.get('regression', 0)}` regressions; exact McNemar `p={official_effects['mcnemar_exact_p']:.4f}`.",
            f"- Clean paired task version: `{clean_effects.get('recovery', 0)}` recoveries, `{clean_effects.get('regression', 0)}` regressions; exact McNemar `p={clean_effects['mcnemar_exact_p']:.4f}`.",
            f"- Automated protocol validation: `{'passed' if validation['passed'] else 'failed'}`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--v1-root", type=Path, default=DEFAULT_V1_ROOT)
    parser.add_argument("--expected-cases", type=int, default=140)
    parser.add_argument("--strict-smoke", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    rows = read_jsonl(root / "runs.jsonl")
    if not rows:
        raise RuntimeError(f"no rows found in {root / 'runs.jsonl'}")
    transitions = build_transitions(rows)
    audit_rows, audit_errors = guard_audit(
        rows,
        root,
        require_policy_events=args.strict_smoke,
    )
    validation = validate(rows, audit_errors, args.expected_cases, args.strict_smoke)
    metrics = {
        "generated_at": utc_now(),
        "cells": {
            f"{condition}_{benchmark}": cell_metrics(rows, condition, benchmark)
            for condition in (CONTROL, POLICY)
            for benchmark in ("official", "clean")
        },
        "paired": {
            condition: paired_metrics(rows, condition) for condition in (CONTROL, POLICY)
        },
        "policy_effects": {
            benchmark: transition_metrics(transitions, benchmark)
            for benchmark in ("official", "clean")
        },
        "validation": validation,
    }
    write_jsonl(root / "case_transitions.jsonl", transitions)
    write_jsonl(root / "guard_audit.jsonl", audit_rows)
    (root / "case_transitions.md").write_text(
        render_transitions(transitions), encoding="utf-8"
    )
    (root / "guard_audit.md").write_text(
        render_guard_audit(audit_rows, audit_errors), encoding="utf-8"
    )
    (root / "analysis.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    v1_rows = read_jsonl(args.v1_root.resolve() / "runs.jsonl")
    if v1_rows:
        (root / "v1_v2_comparison.md").write_text(
            render_v1_v2(rows, v1_rows), encoding="utf-8"
        )
    (root / "rebuttal_summary.md").write_text(
        render_rebuttal(rows, transitions, validation), encoding="utf-8"
    )
    print(json.dumps(validation, ensure_ascii=False, indent=2))
    return 0 if validation["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
