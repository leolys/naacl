#!/usr/bin/env python3
"""Generate case-level and rebuttal-facing analysis for the CUGA experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_miniset_16paired_20260710"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return str(row["condition"]), str(row["benchmark"]), str(row["scenario"]), str(row["slug"])


def effect(default_outcome: str, playbook_outcome: str) -> str:
    default_success = default_outcome == "success"
    playbook_success = playbook_outcome == "success"
    if not default_success and playbook_success:
        return "recovery"
    if default_success and not playbook_success:
        return "regression"
    if default_success:
        return "unchanged_success"
    return "unchanged_failure"


def exact_mcnemar_p(recoveries: int, regressions: int) -> float:
    discordant = recoveries + regressions
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, i) for i in range(min(recoveries, regressions) + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def actions(row: dict[str, Any]) -> list[str]:
    return [
        str(step.get("action_formatted"))
        for step in row.get("cuga_steps", [])
        if step.get("action_formatted")
    ]


def build_transitions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {key(row): row for row in rows}
    case_keys = sorted({(str(row["scenario"]), str(row["slug"])) for row in rows})
    transitions: list[dict[str, Any]] = []
    for scenario, slug in case_keys:
        cells = {
            (condition, benchmark): by_key[(condition, benchmark, scenario, slug)]
            for condition in ("default", "playbook")
            for benchmark in ("official", "clean")
        }
        default_official = cells[("default", "official")]
        playbook_official = cells[("playbook", "official")]
        default_clean = cells[("default", "clean")]
        playbook_clean = cells[("playbook", "clean")]
        transitions.append(
            {
                "scenario": scenario,
                "slug": slug,
                "case_id": default_official.get("case_id"),
                "misleader_type": default_official.get("misleader_type"),
                "default_official": default_official.get("outcome"),
                "playbook_official": playbook_official.get("outcome"),
                "official_effect": effect(
                    str(default_official.get("outcome")), str(playbook_official.get("outcome"))
                ),
                "default_clean": default_clean.get("outcome"),
                "playbook_clean": playbook_clean.get("outcome"),
                "clean_effect": effect(str(default_clean.get("outcome")), str(playbook_clean.get("outcome"))),
                "default_official_selected_action_id": default_official.get("submission", {}).get(
                    "selected_action_id"
                ),
                "playbook_official_selected_action_id": playbook_official.get("submission", {}).get(
                    "selected_action_id"
                ),
                "default_official_actions": actions(default_official),
                "playbook_official_actions": actions(playbook_official),
                "default_official_action_count": default_official.get("cuga_action_count"),
                "playbook_official_action_count": playbook_official.get("cuga_action_count"),
                "policy_matched_official": playbook_official.get("policy_enactment", {}).get("matched"),
                "policy_matched_clean": playbook_clean.get("policy_enactment", {}).get("matched"),
            }
        )
    return transitions


def cell_metrics(rows: list[dict[str, Any]], condition: str, benchmark: str) -> dict[str, Any]:
    subset = [
        row for row in rows if row.get("condition") == condition and row.get("benchmark") == benchmark
    ]
    outcomes = Counter(str(row.get("outcome")) for row in subset)
    return {
        "n": len(subset),
        "success": outcomes["success"],
        "success_rate": outcomes["success"] / len(subset) if subset else 0.0,
        "misleading_failure": outcomes["misleading_failure"],
        "agent_error": outcomes["agent_error"],
        "avg_actions": sum(int(row.get("cuga_action_count") or 0) for row in subset) / len(subset),
    }


def paired_metrics(rows: list[dict[str, Any]], condition: str) -> dict[str, Any]:
    by_key = {key(row): row for row in rows}
    case_keys = sorted({(str(row["scenario"]), str(row["slug"])) for row in rows})
    pairs = [
        (
            by_key[(condition, "official", scenario, slug)],
            by_key[(condition, "clean", scenario, slug)],
        )
        for scenario, slug in case_keys
    ]
    return {
        "n": len(pairs),
        "official_success": sum(official.get("outcome") == "success" for official, _ in pairs),
        "clean_success": sum(clean.get("outcome") == "success" for _, clean in pairs),
        "official_misleading_clean_success": sum(
            official.get("outcome") == "misleading_failure" and clean.get("outcome") == "success"
            for official, clean in pairs
        ),
        "clean_regression": sum(
            official.get("outcome") == "success" and clean.get("outcome") != "success"
            for official, clean in pairs
        ),
        "both_failed": sum(
            official.get("outcome") != "success" and clean.get("outcome") != "success"
            for official, clean in pairs
        ),
    }


def render_case_table(transitions: list[dict[str, Any]]) -> str:
    lines = [
        "# CUGA Policy-System Case Transitions",
        "",
        "| Scenario | Slug | Mechanism | Default official | Playbook official | Official effect | Default clean | Playbook clean | Clean effect |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in transitions:
        lines.append(
            f"| {row['scenario']} | {row['slug']} | {row['misleader_type']} | "
            f"{row['default_official']} | {row['playbook_official']} | {row['official_effect']} | "
            f"{row['default_clean']} | {row['playbook_clean']} | {row['clean_effect']} |"
        )
    return "\n".join(lines) + "\n"


def render_rebuttal(rows: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> str:
    cells = {
        (condition, benchmark): cell_metrics(rows, condition, benchmark)
        for condition in ("default", "playbook")
        for benchmark in ("official", "clean")
    }
    paired = {condition: paired_metrics(rows, condition) for condition in ("default", "playbook")}
    official_effects = Counter(row["official_effect"] for row in transitions)
    clean_effects = Counter(row["clean_effect"] for row in transitions)
    official_p = exact_mcnemar_p(official_effects["recovery"], official_effects["regression"])
    clean_p = exact_mcnemar_p(clean_effects["recovery"], clean_effects["regression"])
    case_count = len(transitions)
    playbook_rows = [row for row in rows if row.get("condition") == "playbook"]
    default_rows = [row for row in rows if row.get("condition") == "default"]
    playbook_matches = sum(bool(row.get("policy_enactment", {}).get("matched")) for row in playbook_rows)
    default_matches = sum(bool(row.get("policy_enactment", {}).get("matched")) for row in default_rows)
    agent_errors = sum(row.get("outcome") == "agent_error" for row in rows)
    study = next(
        (row for row in transitions if row["official_effect"] == "recovery"),
        next(
            (
                row
                for row in transitions
                if row["official_effect"] in {"regression", "unchanged_failure"}
            ),
            transitions[0],
        ),
    )
    official_net = official_effects["recovery"] - official_effects["regression"]
    if official_net > 0:
        aggregate_interpretation = (
            f"The Playbook yields a net gain of {official_net} official successes, although "
            f"{official_effects['regression']} official regressions remain."
        )
    elif official_net < 0:
        aggregate_interpretation = (
            f"The Playbook yields a net loss of {-official_net} official successes: its "
            f"recoveries are outweighed by {official_effects['regression']} regressions."
        )
    else:
        aggregate_interpretation = (
            "The Playbook does not change aggregate official success because its recoveries "
            "and regressions exactly offset one another."
        )

    lines = [
        "# Reviewer 4H6i: CUGA Policy-System Experiment",
        "",
        "## Protocol",
        "",
        "- Agent: CUGA 0.3.0 legacy Playwright web graph, driven by `gpt-5.4`.",
        f"- Data: {case_count} paired cases, {case_count * 2} clean/official task instances per condition, {len(rows)} trajectories total.",
        "- Conditions: empty policy store (`default`) versus a general chart-evidence Playbook (`playbook`).",
        "- The Playbook contains no task IDs, mechanisms, labels, answers, or evaluator fields.",
        "- CUGA's native policy hook is available in CugaLite/Supervisor but not its legacy Playwright web graph. The adapter calls native `PolicyEnactment.check_and_enact` and passes its returned `playbook_guidance` into the legacy task goal.",
        f"- Intended Playbook matches: {playbook_matches}/{len(playbook_rows)}; unexpected default-policy matches: {default_matches}/{len(default_rows)}.",
        f"- Agent errors: {agent_errors}/{len(rows)}.",
        "",
        "## Aggregate Results",
        "",
        "| Condition | Official success | Official misleading failure | Clean success | Clean - official | Official misleading / clean success | Clean regression | Avg official actions |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in ("default", "playbook"):
        official = cells[(condition, "official")]
        clean = cells[(condition, "clean")]
        pair = paired[condition]
        gap = 100.0 * (clean["success_rate"] - official["success_rate"])
        lines.append(
            f"| {condition} | {official['success']}/{official['n']} ({100 * official['success_rate']:.1f}%) | "
            f"{official['misleading_failure']}/{official['n']} "
            f"({100 * official['misleading_failure'] / official['n']:.1f}%) | "
            f"{clean['success']}/{clean['n']} ({100 * clean['success_rate']:.1f}%) | {gap:+.1f} pp | "
            f"{pair['official_misleading_clean_success']} | {pair['clean_regression']} | "
            f"{official['avg_actions']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Paired Policy Effects",
            "",
            f"- Official: {official_effects['recovery']} recoveries, {official_effects['regression']} regressions, "
            f"{official_effects['unchanged_success']} unchanged successes, and {official_effects['unchanged_failure']} unchanged failures.",
            f"- Clean: {clean_effects['recovery']} recoveries, {clean_effects['regression']} regression, "
            f"{clean_effects['unchanged_success']} unchanged successes, and {clean_effects['unchanged_failure']} unchanged failures.",
            f"- Exact paired McNemar tests: official p={official_p:.4f}; clean p={clean_p:.4f}.",
            f"- {aggregate_interpretation}",
            "",
            f"## Case Study: {study['scenario']}/{study['slug']}",
            "",
            f"- Mechanism: `{study['misleader_type']}`; official policy effect: `{study['official_effect']}`.",
            f"- Default outcome: `{study['default_official']}`; selected action `{study['default_official_selected_action_id']}`.",
            f"- Playbook outcome: `{study['playbook_official']}`; selected action `{study['playbook_official_selected_action_id']}`.",
            f"- Default actions: `{' -> '.join(study['default_official_actions'])}`.",
            f"- Playbook actions: `{' -> '.join(study['playbook_official_actions'])}`.",
            "",
            "## Interpretation",
            "",
            "This comparison directly addresses policy-system agents without assuming that a generic Playbook solves visualization robustness. The paired recovery/regression counts show whether guidance changes decisions beneficially and whether it also causes over-correction. Conclusions should follow the complete fixed sample rather than selected case studies.",
            "",
            "## Suggested Rebuttal Text",
            "",
            f"We thank the reviewer for suggesting policy-system agents. We added a controlled CUGA 0.3.0 experiment on {case_count} clean/official pairs ({len(rows)} trajectories), comparing the same GPT-5.4-backed CUGA browser agent with an empty policy store and with a native CUGA Playbook for chart-evidence verification. CUGA Default achieved {cells[('default', 'official')]['success']}/{case_count} official and {cells[('default', 'clean')]['success']}/{case_count} clean successes; CUGA+Playbook achieved {cells[('playbook', 'official')]['success']}/{case_count} official and {cells[('playbook', 'clean')]['success']}/{case_count} clean successes. On official tasks the policy produced {official_effects['recovery']} recoveries and {official_effects['regression']} regressions, with an exact paired McNemar p-value of {official_p:.4f}. These results quantify both the benefits and failure modes of policy guidance under a fixed paired protocol.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    rows = read_jsonl(root / "runs.jsonl")
    run_config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    expected_cases = int(run_config["manifest_rows"])
    expected_runs = expected_cases * len(run_config["conditions"]) * len(run_config["benchmarks"])
    if len(rows) != expected_runs:
        raise RuntimeError(f"Expected {expected_runs} runs, found {len(rows)}")
    if len({key(row) for row in rows}) != expected_runs:
        raise RuntimeError("Run keys are not unique")
    if any(row.get("outcome") == "agent_error" for row in rows):
        raise RuntimeError("Agent errors remain; analyze only after repair")
    for row in rows:
        expected_match = row.get("condition") == "playbook"
        actual_match = bool(row.get("policy_enactment", {}).get("matched"))
        if actual_match != expected_match:
            raise RuntimeError(f"Unexpected policy match state for {key(row)}")
        if not row.get("submission") and row.get("outcome") != "agent_timeout":
            raise RuntimeError(f"Missing evaluator submission for {key(row)}")
        for step in row.get("cuga_steps", []):
            image_path = step.get("image_before_path")
            if not image_path:
                continue
            path = REPO_ROOT / str(image_path)
            if not path.exists():
                raise RuntimeError(f"Missing step image: {path}")
            digest = step.get("image_before_sha256")
            if digest and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Step image hash mismatch: {path}")
    transitions = build_transitions(rows)
    if len(transitions) != expected_cases:
        raise RuntimeError(f"Expected {expected_cases} paired cases, found {len(transitions)}")
    write_jsonl(root / "case_transitions.jsonl", transitions)
    (root / "case_transitions.md").write_text(render_case_table(transitions), encoding="utf-8")
    (root / "rebuttal_summary.md").write_text(render_rebuttal(rows, transitions), encoding="utf-8")
    print(f"Wrote analysis for {len(rows)} runs and {len(transitions)} paired cases to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
