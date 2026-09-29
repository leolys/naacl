#!/usr/bin/env python3
"""Audit the four GPT-5.4 cells required before formal cell 257."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.audit_reflection_history_model_scoped_smoke import (  # noqa: E402
    inspect_cells,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (  # noqa: E402
    DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT,
    audited_smoke_artifact_tree,
    build_gpt_model_scoped_smoke_manifest,
    sha256_file,
    write_json,
)


GPT_MODEL = "gpt54"


def audit(root: Path) -> dict[str, Any]:
    manifest = build_gpt_model_scoped_smoke_manifest()
    cells, errors = inspect_cells(
        root=root,
        manifest_name="gpt_model_scoped_smoke_cells.jsonl",
        expected_manifest=manifest,
        selected_cells=manifest,
        experiment_kind="instrumentation_smoke_gpt_model_scoped_non_formal",
        strict_cell_set=True,
    )
    conditions = {str(cell.get("condition") or "") for cell in cells}
    splits = [str(cell.get("benchmark") or "") for cell in cells]
    models = {str(cell.get("model") or "") for cell in cells}
    if conditions != {
        "no_history",
        "previous_step",
        "full_history",
        "structured_falsification",
    }:
        errors.append("GPT model-scoped smoke does not cover four conditions")
    if splits.count("official") != 2 or splits.count("clean") != 2:
        errors.append("GPT model-scoped smoke is not balanced across splits")
    if models != {GPT_MODEL}:
        errors.append("GPT model-scoped smoke contains a non-GPT model")
    if any(cell.get("outcome") == "agent_error" for cell in cells):
        errors.append("GPT model-scoped smoke contains an agent_error")
    evidence_tree = audited_smoke_artifact_tree(root)
    return {
        "gate": "Gate 1 GPT-5.4 model-scoped instrumentation smoke",
        "scope": (
            "Four non-formal GPT-5.4 cells covering all conditions and both "
            "benchmark splits; required before formal cell 257."
        ),
        "approved": not errors and len(cells) == 4,
        "manifest_sha256": (
            sha256_file(root / "gpt_model_scoped_smoke_cells.jsonl")
            if (root / "gpt_model_scoped_smoke_cells.jsonl").is_file()
            else None
        ),
        "completed_cells": len(cells),
        "conditions": sorted(conditions),
        "split_counts": {
            "official": splits.count("official"),
            "clean": splits.count("clean"),
        },
        "invalid_schema_step_count": sum(
            int(cell.get("invalid_schema_steps") or 0) for cell in cells
        ),
        "audited_artifact_tree_sha256": evidence_tree["tree_sha256"],
        "audited_artifact_count": evidence_tree["artifact_count"],
        "audited_artifacts": evidence_tree["artifacts"],
        "cells": cells,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT,
    )
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(root)
    write_json(root / "model_scoped_gate1_audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
