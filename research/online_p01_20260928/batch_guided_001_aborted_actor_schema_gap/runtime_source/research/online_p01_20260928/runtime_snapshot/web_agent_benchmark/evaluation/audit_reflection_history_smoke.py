#!/usr/bin/env python3
"""Audit the four non-formal reflection instrumentation smoke runs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    MODEL_CONFIGS,
    build_smoke_manifest,
    read_jsonl,
    sha256_file,
    write_json,
)
from web_agent_benchmark.evaluation.audit_reflection_history_stage import (
    audit_cell,
)


DEFAULT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "reflection_history_pilot_smoke_gate1_certified_20260727"
)
SECRET_PATTERNS = (
    re.compile(rb"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE),
    re.compile(rb"AIME_LITELLM_API_KEY\s*=\s*\S+", re.IGNORECASE),
    re.compile(rb"[\"']api[_-]?key[\"']?\s*[:=]\s*[\"'][^\"']{8,}", re.IGNORECASE),
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(root: Path) -> dict[str, Any]:
    expected = build_smoke_manifest()
    expected_by_id = {row["cell_id"]: row for row in expected}
    manifest_path = root / "instrumentation_smoke_cells.jsonl"
    errors: list[str] = []
    cells: list[dict[str, Any]] = []
    if not manifest_path.exists():
        errors.append("instrumentation smoke manifest is missing")
        actual_manifest = []
    else:
        actual_manifest = read_jsonl(manifest_path)
        if actual_manifest != expected:
            errors.append("instrumentation smoke manifest differs from frozen mapping")

    for cell_id, cell in expected_by_id.items():
        chosen_path = root / "cells" / cell_id / "chosen_result.json"
        if not chosen_path.exists():
            errors.append(f"{cell_id}: chosen result is missing")
            continue
        row = load_json(chosen_path)
        cell_errors: list[str] = []
        if row.get("pilot_cell") != cell:
            cell_errors.append("pilot_cell differs from smoke manifest")
        audit_result = row.get("pilot_identity_audit") or {}
        if audit_result.get("valid") is not True:
            cell_errors.append("identity audit is not valid")
        expected_deployment = MODEL_CONFIGS[cell["model"]]["deployment_id"]
        if audit_result.get("expected_deployment") != expected_deployment:
            cell_errors.append("identity audit deployment differs")
        cell_errors.extend(audit_cell(root=root, cell=cell, row=row))

        trace = row.get("trace") or []
        if not trace:
            cell_errors.append("trace is empty")
        model_actions = 0
        payload_hashes: list[str] = []
        invalid_schema_steps = 0
        for index, step in enumerate(trace):
            action = step.get("action") if isinstance(step, dict) else None
            history = step.get("pilot_history") if isinstance(step, dict) else None
            if not isinstance(action, dict) or "_raw" not in action:
                continue
            model_actions += 1
            metadata = action.get("_response_metadata") or {}
            if metadata.get("requested_deployment") != expected_deployment:
                cell_errors.append(f"step {index}: requested deployment differs")
            if metadata.get("response_model") != expected_deployment:
                cell_errors.append(f"step {index}: response model differs")
            if metadata.get("identity_validated") is not True:
                cell_errors.append(f"step {index}: response identity is not validated")
            if metadata.get("hidden_prompt_terms_seen") != []:
                cell_errors.append(
                    f"step {index}: internal metadata appears in full request payload"
                )
            payload_hash = str(metadata.get("request_payload_sha256") or "")
            if len(payload_hash) != 64:
                cell_errors.append(f"step {index}: request payload hash is missing")
            else:
                payload_hashes.append(payload_hash)
            if not isinstance(history, dict):
                cell_errors.append(f"step {index}: pilot history metadata is missing")
                continue
            invalid_schema_steps += int(history.get("schema_valid") is not True)
            injected = int(history.get("history_records_injected") or 0)
            available = int(history.get("history_records_available") or 0)
            condition = cell["condition"]
            if condition == "no_history" and injected != 0:
                cell_errors.append(f"step {index}: no_history injected records")
            elif condition == "previous_step":
                wanted = 0 if index == 0 else 1
                if injected != wanted:
                    cell_errors.append(
                        f"step {index}: previous_step injected {injected}, expected {wanted}"
                    )
            elif condition == "full_history":
                if injected != available:
                    cell_errors.append(
                        f"step {index}: full_history did not inject all available records"
                    )
            elif condition == "structured_falsification":
                wanted = 0 if index == 0 else 1
                if injected != wanted:
                    cell_errors.append(
                        f"step {index}: structured ledger injection differs"
                    )
            screenshot = Path(str(step.get("screenshot") or ""))
            if not screenshot.is_file():
                cell_errors.append(f"step {index}: screenshot is missing")
            ui_sanitization = step.get("pilot_ui_sanitization") or {}
            if (
                ui_sanitization.get(
                    "applied_before_screenshot_and_state_capture"
                )
                is not True
            ):
                cell_errors.append(
                    f"step {index}: UI sanitization timing is not auditable"
                )
            if step.get("pilot_hidden_terms_seen") != []:
                cell_errors.append(
                    f"step {index}: internal metadata appears in full DOM text"
                )

        if model_actions == 0:
            cell_errors.append("no model-generated action was recorded")
        request_count = int(row.get("pilot_actual_http_request_count") or 0)
        if request_count != model_actions:
            cell_errors.append(
                f"HTTP requests ({request_count}) differ from model actions ({model_actions})"
            )
        if int(audit_result.get("identity_event_count") or 0) != request_count:
            cell_errors.append("identity event count differs from HTTP request count")
        cells.append({
            "cell_id": cell_id,
            "model": cell["model"],
            "benchmark": cell["benchmark"],
            "scenario": cell["scenario"],
            "slug": cell["slug"],
            "condition": cell["condition"],
            "outcome": row.get("outcome"),
            "trace_steps": len(trace),
            "model_actions": model_actions,
            "actual_http_requests": request_count,
            "identity_valid": audit_result.get("valid"),
            "request_payload_hashes": payload_hashes,
            "invalid_schema_steps": invalid_schema_steps,
            "errors": cell_errors,
        })
        errors.extend(f"{cell_id}: {message}" for message in cell_errors)

    secret_hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            secret_hits.append(str(path.relative_to(root)))
    if secret_hits:
        errors.append(f"credential-like text found in: {secret_hits}")

    return {
        "gate": "Gate 1 instrumentation smoke",
        "approved": not errors and len(cells) == 4,
        "expected_cells": 4,
        "completed_cells": len(cells),
        "manifest_sha256": (
            sha256_file(manifest_path) if manifest_path.exists() else None
        ),
        "cells": cells,
        "secret_hits": secret_hits,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    report = audit(root)
    write_json(root / "gate1_smoke_audit.json", report)
    lines = [
        "# Gate 1 Instrumentation Smoke Audit",
        "",
        f"- Approved: **{report['approved']}**",
        f"- Completed: {report['completed_cells']}/{report['expected_cells']}",
        f"- Manifest SHA-256: `{report['manifest_sha256']}`",
        "",
        "| Cell | Model | Split | Condition | Outcome | Steps | HTTP | Identity |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in report["cells"]:
        lines.append(
            f"| {row['cell_id']} | {row['model']} | {row['benchmark']} | "
            f"{row['condition']} | {row['outcome']} | {row['trace_steps']} | "
            f"{row['actual_http_requests']} | {row['identity_valid']} |"
        )
    if report["errors"]:
        lines.extend(["", "## Blocking Errors", ""])
        lines.extend(f"- {error}" for error in report["errors"])
    (root / "gate1_smoke_audit.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
