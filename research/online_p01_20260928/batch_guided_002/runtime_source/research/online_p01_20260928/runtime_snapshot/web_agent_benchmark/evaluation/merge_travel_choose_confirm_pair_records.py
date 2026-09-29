#!/usr/bin/env python3
"""Merge disjoint model runs for the travel choose-confirm pair."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    by_model: dict[str, Counter[str]] = {}
    by_condition: dict[str, Counter[str]] = {}
    for row in rows:
        by_model.setdefault(str(row["model_name"]), Counter())[str(row["outcome"])] += 1
        by_condition.setdefault(str(row["version_id"]), Counter())[str(row["outcome"])] += 1
    lines = [
        "# Travel Choose-Confirm Expanded Pair Summary",
        "",
        f"- Total runs: `{len(rows)}`",
        f"- Models: `{len(by_model)}`",
        f"- Agent errors: `{sum(row.get('outcome') == 'agent_error' for row in rows)}`",
        "",
        "## By Model",
        "",
        "| Model | Outcomes |",
        "|---|---|",
    ]
    for model, outcomes in sorted(by_model.items()):
        lines.append(f"| {model} | `{dict(outcomes)}` |")
    lines.extend(["", "## By Condition", "", "| Condition | Outcomes |", "|---|---|"])
    for condition, outcomes in sorted(by_condition.items()):
        lines.append(f"| {condition} | `{dict(outcomes)}` |")
    lines.extend(
        [
            "",
            "## Runs",
            "",
            "| Model | Condition | Outcome | Selected route | Trap visited | Recovered |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for row in rows:
        path_trace = (row.get("submission") or {}).get("path_trace") or {}
        selected = f"{path_trace.get('selected_state')}:{path_trace.get('selected_county')}"
        lines.append(
            f"| {row['model_name']} | {row['version_id']} | {row['outcome']} | {selected} | "
            f"{bool(path_trace.get('visited_trap_state_before_submit'))} | "
            f"{bool(path_trace.get('recovered_to_expected_route'))} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def merge(inputs: list[Path], output: Path) -> None:
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    output.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for root in inputs:
        root = root.resolve()
        for row in read_jsonl(root / "runs.jsonl"):
            key = (str(row["model_slug"]), str(row["version_id"]))
            if key in seen:
                raise SystemExit(f"Duplicate model-condition row: {key}")
            seen.add(key)
            rows.append(row)
        for model_slug in sorted({str(row["model_slug"]) for row in rows if (root / str(row["model_slug"])).is_dir()}):
            source = root / model_slug
            destination = output / model_slug
            if source.is_dir() and not destination.exists():
                shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    rows.sort(key=lambda row: (str(row["model_name"]), str(row["version_id"])))
    write_jsonl(output / "runs.jsonl", rows)
    write_jsonl(output / "failures.jsonl", [row for row in rows if row.get("outcome") != "success"])
    write_summary(output / "summary.md", rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", action="append", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    merge(args.input_root, args.output_root.resolve())
    print(args.output_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
