#!/usr/bin/env python3
"""Run the preregistered cross-step reflection and oscillation pilot."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import random
import signal
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation.reflection_history import (  # noqa: E402
    INTERNAL_METADATA_TERMS,
)

EVAL_DIR = REPO_ROOT / "web_agent_benchmark" / "evaluation"
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "reflection_history_pilot_20260727_restart1"
)
DEFAULT_SMOKE_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "reflection_history_pilot_smoke_gate1_certified_20260727"
)
DEFAULT_SONNET_AUX_SMOKE_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "reflection_history_pilot_smoke_gate1_sonnet_auxiliary_20260727"
)
DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "reflection_history_pilot_smoke_gate1_gpt_scoped_20260727"
)
SELECTION_SOURCE = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "behavior_efficiency_analysis_final_selected_kimi_full140_replaced_20260523"
    / "step_metrics.jsonl"
)
RANDOM_SEED = 20260727
CONDITIONS = (
    "no_history",
    "previous_step",
    "full_history",
    "structured_falsification",
)
MODELS = ("gpt54", "claude_sonnet_4_6_litellm")
SCHEDULING_MODEL_ORDER = ("claude_sonnet_4_6_litellm", "gpt54")
FROZEN_SCHEDULING_CREATED_AT = "2026-07-27T13:17:35.381947+00:00"
CONCURRENCY_INCIDENT_FILENAME = "CONCURRENCY_INCIDENT.json"
RUNNER_LOCK_FILENAME = ".reflection_pilot_runner.lock"
GPT_GATE1_REVIEWER_AGENT_ID = "019fa390-af77-7312-9c16-7b611362f58a"
GPT_GATE1_APPROVAL_FILENAME = "gpt_model_scoped_gate1_approval.json"
SMOKE_ARTIFACT_DIGEST_EXCLUSIONS = {
    "model_scoped_gate1_audit.json",
    RUNNER_LOCK_FILENAME,
}
HIGH_OSCILLATION = {
    "public39": ("pub020", "pub025", "pub032", "pub036"),
    "business47": (
        "b002", "b004", "b007", "b009", "b010", "b035", "b044", "b045",
    ),
    "environment35": ("env024", "env032", "env033", "env034"),
}
LOW_OSCILLATION = {
    "public39": ("pub008", "pub028", "pub034"),
    "business47": ("b003", "b039"),
    "environment35": ("env001", "env008"),
    "health19": ("health018",),
}
CLEAN_SENTINELS = {
    "public39": ("pub028", "pub034", "pub036"),
    "business47": ("b010", "b045"),
    "environment35": ("env001", "env024"),
    "health19": ("health018",),
}
SCENARIOS = {
    "public39": {
        "runner": EVAL_DIR / "run_public39.py",
        "tasks_file": "public39_tasks.jsonl",
    },
    "business47": {
        "runner": EVAL_DIR / "run_business47.py",
        "tasks_file": "business47_tasks.jsonl",
    },
    "environment35": {
        "runner": EVAL_DIR / "run_environment35.py",
        "tasks_file": "environment35_tasks.jsonl",
    },
    "health19": {
        "runner": EVAL_DIR / "run_health19.py",
        "tasks_file": "health19_tasks.jsonl",
    },
}
MODEL_CONFIGS = {
    "gpt54": {
        "record_slug": "gpt54_temp0_top_p1_seed12345",
        "model_id": "gpt-5.4",
        "deployment_id": "dedceaa0-7dbe-476c-a4e6-d50815171e8e",
        "backend": "aime_litellm",
        "api_style": "chat_completions",
        "max_output_tokens": 1024,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://aimemodeldev.myhexin.com/litellm/v1",
            "AIME_LITELLM_PROXY": "http://127.0.0.1:18890",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "dedceaa0-7dbe-476c-a4e6-d50815171e8e",
            "AIME_LITELLM_API_STYLE": "chat_completions",
            "AIME_LITELLM_STRICT_MODEL_IDENTITY": "true",
            "AIME_LITELLM_EXTRA_BODY_JSON": "",
            "AIME_LITELLM_OMIT_TEMPERATURE": "false",
            "AIME_LITELLM_OMIT_TOP_P": "false",
            "AIME_LITELLM_REASONING_CONTENT_FALLBACK": "false",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "all_proxy": "",
            "no_proxy": "",
        },
    },
    "claude_sonnet_4_6_litellm": {
        "record_slug": "claude_sonnet_4_6_litellm_temp0_top_p1_seed12345",
        "model_id": "claude-sonnet-4-6",
        "deployment_id": "4bb890af-7111-410c-9344-061eb678f4ec",
        "backend": "aime_litellm",
        "api_style": "messages",
        "max_output_tokens": 4096,
        "env": {
            "LLM_BACKEND": "aime_litellm",
            "AIME_LITELLM_BASE_URL": "https://aimemodeldev.myhexin.com/litellm/v1",
            "AIME_LITELLM_PROXY": "http://127.0.0.1:18890",
            "AIME_LITELLM_HOST_HEADER": "",
            "AIME_LITELLM_VERIFY_SSL": "true",
            "AIME_LITELLM_MODEL": "4bb890af-7111-410c-9344-061eb678f4ec",
            "AIME_LITELLM_API_STYLE": "messages",
            "AIME_LITELLM_STRICT_MODEL_IDENTITY": "true",
            "AIME_LITELLM_EXTRA_BODY_JSON": "",
            "AIME_LITELLM_MAX_RETRIES": "0",
            "AIME_LITELLM_REQUEST_DELAY_SEC": "2",
            "AIME_LITELLM_HTTP_READ_TIMEOUT_SEC": "300",
            "AIME_LITELLM_OMIT_TEMPERATURE": "true",
            "AIME_LITELLM_OMIT_TOP_P": "false",
            "AIME_LITELLM_REASONING_CONTENT_FALLBACK": "false",
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "ALL_PROXY": "",
            "NO_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "all_proxy": "",
            "no_proxy": "",
        },
    },
}
SMOKE_ASSIGNMENTS = (
    ("official", "business47", "b010", "gpt54", "no_history"),
    (
        "official",
        "environment35",
        "env024",
        "claude_sonnet_4_6_litellm",
        "previous_step",
    ),
    ("clean", "public39", "pub028", "gpt54", "full_history"),
    (
        "clean",
        "health19",
        "health018",
        "claude_sonnet_4_6_litellm",
        "structured_falsification",
    ),
)
SONNET_AUXILIARY_SMOKE_ASSIGNMENTS = (
    (
        "official",
        "business47",
        "b010",
        "claude_sonnet_4_6_litellm",
        "no_history",
    ),
    (
        "clean",
        "public39",
        "pub028",
        "claude_sonnet_4_6_litellm",
        "full_history",
    ),
)
GPT_MODEL_SCOPED_SMOKE_ASSIGNMENTS = (
    ("official", "business47", "b010", "gpt54", "no_history"),
    ("official", "environment35", "env024", "gpt54", "previous_step"),
    ("clean", "public39", "pub028", "gpt54", "full_history"),
    (
        "clean",
        "health19",
        "health018",
        "gpt54",
        "structured_falsification",
    ),
)
HIDDEN_PROMPT_TERMS = INTERNAL_METADATA_TERMS
RETRYABLE_INTERFACE_PATTERNS = (
    "readtimeout",
    "connecttimeout",
    "connectionerror",
    "connection reset",
    "connection refused",
    "remoteprotocolerror",
    "temporarily unavailable",
    "service unavailable",
    "gateway timeout",
    "timed out",
    "read timeout",
    "http 429",
    "status 429",
    "status_code=429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "status 500",
    "status 502",
    "status 503",
    "status 504",
    "empty response",
    "empty model response",
    "empty content",
    "response has no choices",
    "model identity mismatch",
    "model identity audit failed",
)
STOP_RULE_INTERFACE_PATTERNS = tuple(
    pattern
    for pattern in RETRYABLE_INTERFACE_PATTERNS
    if pattern != "model identity audit failed"
)
NON_INTERFACE_HARNESS_PATTERNS = (
    "locator.",
    "playwright",
    "css selector",
    "while parsing css selector",
    "element not found",
)
NON_INTERFACE_PARSER_PATTERNS = (
    "jsondecodeerror",
    "unsupported browser action",
    "malformed action",
    "invalid browser action",
)
AVAILABILITY_PATTERNS = (
    "http 429",
    "status 429",
    "status_code=429",
    "cooling down",
    "rate_limit_error",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def audited_smoke_artifact_tree(root: Path) -> dict[str, Any]:
    files: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        if relative in SMOKE_ARTIFACT_DIGEST_EXCLUSIONS:
            continue
        files.append({
            "path": relative,
            "sha256": sha256_file(path),
        })
    canonical = json.dumps(
        files,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "artifact_count": len(files),
        "tree_sha256": hashlib.sha256(
            canonical.encode("utf-8")
        ).hexdigest(),
        "artifacts": files,
    }


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def all_official_tasks() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for scenario, slugs in HIGH_OSCILLATION.items():
        rows.extend((scenario, slug, "high_oscillation") for slug in slugs)
    for scenario, slugs in LOW_OSCILLATION.items():
        rows.extend((scenario, slug, "low_oscillation_control") for slug in slugs)
    return rows


def build_manifest() -> list[dict[str, Any]]:
    instances = [
        ("official", scenario, slug, stratum)
        for scenario, slug, stratum in all_official_tasks()
    ]
    high_lookup = {
        (scenario, slug)
        for scenario, slugs in HIGH_OSCILLATION.items()
        for slug in slugs
    }
    for scenario, slugs in CLEAN_SENTINELS.items():
        for slug in slugs:
            stratum = (
                "high_oscillation_clean_sentinel"
                if (scenario, slug) in high_lookup
                else "low_oscillation_clean_sentinel"
            )
            instances.append(("clean", scenario, slug, stratum))

    cells: list[dict[str, Any]] = []
    for benchmark, scenario, slug, stratum in instances:
        for model in MODELS:
            for condition in CONDITIONS:
                for repetition in (1, 2):
                    stable_key = (
                        f"{benchmark}|{scenario}|{slug}|{model}|{condition}|{repetition}"
                    )
                    cells.append({
                        "cell_id": hashlib.sha256(
                            stable_key.encode("utf-8")
                        ).hexdigest()[:16],
                        "benchmark": benchmark,
                        "scenario": scenario,
                        "slug": slug,
                        "stratum": stratum,
                        "model": model,
                        "model_id": MODEL_CONFIGS[model]["model_id"],
                        "condition": condition,
                        "repetition": repetition,
                        "temperature": 0.0,
                        "top_p": 1.0,
                        "seed": 12345,
                        "max_steps": 10,
                        "history_token_limit": 3000,
                    })
    random.Random(RANDOM_SEED).shuffle(cells)
    for order, cell in enumerate(cells, 1):
        cell["condition_order"] = order
    if len(cells) != 512:
        raise AssertionError(f"Expected 512 cells, generated {len(cells)}")
    return cells


def build_smoke_manifest() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for order, (benchmark, scenario, slug, model, condition) in enumerate(
        SMOKE_ASSIGNMENTS,
        1,
    ):
        stable_key = f"smoke|{benchmark}|{scenario}|{slug}|{model}|{condition}"
        cells.append({
            "cell_id": "smoke-" + hashlib.sha256(
                stable_key.encode("utf-8")
            ).hexdigest()[:16],
            "benchmark": benchmark,
            "scenario": scenario,
            "slug": slug,
            "stratum": "instrumentation_smoke",
            "model": model,
            "model_id": MODEL_CONFIGS[model]["model_id"],
            "condition": condition,
            "repetition": 0,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 12345,
            "max_steps": 10,
            "history_token_limit": 3000,
            "condition_order": order,
            "formal_experiment_cell": False,
        })
    return cells


def build_sonnet_auxiliary_smoke_manifest() -> list[dict[str, Any]]:
    """Build two non-formal cells that complete Sonnet's condition coverage."""
    cells: list[dict[str, Any]] = []
    for order, (benchmark, scenario, slug, model, condition) in enumerate(
        SONNET_AUXILIARY_SMOKE_ASSIGNMENTS,
        1,
    ):
        stable_key = (
            f"sonnet_auxiliary_smoke|{benchmark}|{scenario}|{slug}|"
            f"{model}|{condition}"
        )
        cells.append({
            "cell_id": "sonnet-aux-smoke-" + hashlib.sha256(
                stable_key.encode("utf-8")
            ).hexdigest()[:16],
            "benchmark": benchmark,
            "scenario": scenario,
            "slug": slug,
            "stratum": "instrumentation_smoke_sonnet_auxiliary",
            "model": model,
            "model_id": MODEL_CONFIGS[model]["model_id"],
            "condition": condition,
            "repetition": 0,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 12345,
            "max_steps": 10,
            "history_token_limit": 3000,
            "condition_order": order,
            "formal_experiment_cell": False,
            "model_scoped_gate": "sonnet_only",
            "counts_as_gpt_smoke": False,
        })
    return cells


def build_gpt_model_scoped_smoke_manifest() -> list[dict[str, Any]]:
    """Build the four non-formal cells required before the GPT queue."""
    cells: list[dict[str, Any]] = []
    for order, (benchmark, scenario, slug, model, condition) in enumerate(
        GPT_MODEL_SCOPED_SMOKE_ASSIGNMENTS,
        1,
    ):
        stable_key = (
            f"gpt_model_scoped_smoke|{benchmark}|{scenario}|{slug}|"
            f"{model}|{condition}"
        )
        cells.append({
            "cell_id": "gpt-scoped-smoke-" + hashlib.sha256(
                stable_key.encode("utf-8")
            ).hexdigest()[:16],
            "benchmark": benchmark,
            "scenario": scenario,
            "slug": slug,
            "stratum": "instrumentation_smoke_gpt_model_scoped",
            "model": model,
            "model_id": MODEL_CONFIGS[model]["model_id"],
            "condition": condition,
            "repetition": 0,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 12345,
            "max_steps": 10,
            "history_token_limit": 3000,
            "condition_order": order,
            "formal_experiment_cell": False,
            "model_scoped_gate": "gpt_only",
            "counts_as_gpt_smoke": True,
        })
    return cells


def validate_selection() -> dict[str, Any]:
    rows = read_jsonl(SELECTION_SOURCE)
    counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row.get("benchmark") != "official":
            continue
        if int(row.get("primary_action_switch_count") or 0) > 0:
            counts[(str(row.get("scenario")), str(row.get("slug")))] += 1
    violations = [
        {"scenario": scenario, "slug": slug, "switching_models": counts[(scenario, slug)]}
        for scenario, slugs in HIGH_OSCILLATION.items()
        for slug in slugs
        if counts[(scenario, slug)] < 3
    ]
    if violations:
        raise RuntimeError(f"Frozen high-oscillation selection no longer validates: {violations}")
    return {
        "selection_source": str(SELECTION_SOURCE.relative_to(REPO_ROOT)),
        "selection_source_sha256": sha256_file(SELECTION_SOURCE),
        "high_oscillation_rule": "primary_action_switch_count > 0 in at least 3/11 main-experiment models",
        "violations": violations,
    }


def prepare_manifest(output_root: Path) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "preregistered_cells.jsonl"
    metadata_path = output_root / "preregistration.json"
    cells = build_manifest()
    selection = validate_selection()
    if manifest_path.exists():
        existing = read_jsonl(manifest_path)
        if existing != cells:
            raise RuntimeError("Frozen manifest differs from regenerated manifest")
    else:
        write_jsonl(manifest_path, cells)
    manifest_hash = sha256_file(manifest_path)
    metadata = {
        "created_at": utc_now(),
        "experiment": "cross_step_reflection_oscillation_pilot",
        "random_seed": RANDOM_SEED,
        "formal_cell_count": len(cells),
        "official_cell_count": sum(c["benchmark"] == "official" for c in cells),
        "clean_cell_count": sum(c["benchmark"] == "clean" for c in cells),
        "models": list(MODELS),
        "conditions": list(CONDITIONS),
        "repetitions": 2,
        "manifest_sha256": manifest_hash,
        "selection": selection,
        "agent_error_policy": "initial attempt plus at most two exact-config retries",
        "missing_stop_rule": "stop effect comparison if any condition exceeds 5% missing",
        "secret_policy": "API keys are read from environment only and never serialized",
    }
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        if previous.get("manifest_sha256") != manifest_hash:
            raise RuntimeError("Preregistration manifest hash changed")
    else:
        write_json(metadata_path, metadata)
    return cells


def prepare_smoke_manifest(output_root: Path) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "instrumentation_smoke_cells.jsonl"
    cells = build_smoke_manifest()
    if path.exists() and read_jsonl(path) != cells:
        raise RuntimeError("Instrumentation smoke manifest changed")
    if not path.exists():
        write_jsonl(path, cells)
    return cells


def prepare_sonnet_auxiliary_smoke_manifest(
    output_root: Path,
) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "sonnet_auxiliary_smoke_cells.jsonl"
    cells = build_sonnet_auxiliary_smoke_manifest()
    if path.exists() and read_jsonl(path) != cells:
        raise RuntimeError("Sonnet auxiliary smoke manifest changed")
    if not path.exists():
        write_jsonl(path, cells)
    return cells


def prepare_gpt_model_scoped_smoke_manifest(
    output_root: Path,
) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "gpt_model_scoped_smoke_cells.jsonl"
    cells = build_gpt_model_scoped_smoke_manifest()
    if path.exists() and read_jsonl(path) != cells:
        raise RuntimeError("GPT model-scoped smoke manifest changed")
    if not path.exists():
        write_jsonl(path, cells)
    return cells


def validate_gpt_model_scoped_gate1(
    formal_output_root: Path,
) -> list[str]:
    errors: list[str] = []
    smoke_root = DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT
    manifest_path = smoke_root / "gpt_model_scoped_smoke_cells.jsonl"
    audit_path = smoke_root / "model_scoped_gate1_audit.json"
    approval_path = (
        formal_output_root / "gate_reviews" / GPT_GATE1_APPROVAL_FILENAME
    )
    if not manifest_path.is_file():
        errors.append("GPT model-scoped smoke manifest is missing")
        return errors
    if read_jsonl(manifest_path) != build_gpt_model_scoped_smoke_manifest():
        errors.append("GPT model-scoped smoke manifest differs from frozen mapping")
    if not audit_path.is_file():
        errors.append("GPT model-scoped automated Gate 1 audit is missing")
        return errors
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("approved") is not True:
        errors.append("GPT model-scoped automated Gate 1 audit is not approved")
    if audit.get("completed_cells") != 4:
        errors.append("GPT model-scoped Gate 1 does not contain four cells")
    if audit.get("errors") != []:
        errors.append("GPT model-scoped Gate 1 audit contains errors")
    if audit.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("GPT model-scoped Gate 1 manifest hash differs")
    current_tree = audited_smoke_artifact_tree(smoke_root)
    if audit.get("audited_artifact_tree_sha256") != current_tree["tree_sha256"]:
        errors.append("GPT model-scoped audited artifact tree changed")
    if audit.get("audited_artifact_count") != current_tree["artifact_count"]:
        errors.append("GPT model-scoped audited artifact count changed")
    if audit.get("audited_artifacts") != current_tree["artifacts"]:
        errors.append("GPT model-scoped audited artifact inventory changed")
    if not approval_path.is_file():
        errors.append("independent GPT model-scoped Gate 1 approval is missing")
        return errors
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("decision") != "APPROVE GPT MODEL-SCOPED GATE 1":
        errors.append("independent GPT Gate 1 decision is not approved")
    if approval.get("reviewer_agent_id") != GPT_GATE1_REVIEWER_AGENT_ID:
        errors.append("independent GPT Gate 1 reviewer differs")
    if approval.get("audit_sha256") != sha256_file(audit_path):
        errors.append("independent GPT Gate 1 approval refers to another audit")
    if approval.get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("independent GPT Gate 1 approval refers to another manifest")
    try:
        expected_root = str(smoke_root.relative_to(REPO_ROOT))
    except ValueError:
        expected_root = str(smoke_root)
    if approval.get("smoke_root") != expected_root:
        errors.append("independent GPT Gate 1 approval refers to another root")
    return errors


def scheduled_cells(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable-partition formal cells by deployment availability."""
    model_rank = {
        model: index for index, model in enumerate(SCHEDULING_MODEL_ORDER)
    }
    if set(model_rank) != set(MODELS):
        raise RuntimeError("Scheduling model order does not cover frozen models")
    ordered = sorted(
        cells,
        key=lambda cell: (
            model_rank[str(cell["model"])],
            int(cell["condition_order"]),
        ),
    )
    if {cell["cell_id"] for cell in ordered} != {
        cell["cell_id"] for cell in cells
    }:
        raise RuntimeError("Availability scheduling changed the formal cell set")
    return ordered


def scheduling_deviation_spec(
    cells: list[dict[str, Any]],
    *,
    manifest_sha256: str,
) -> dict[str, Any]:
    ordered = scheduled_cells(cells)
    queues = []
    for model in SCHEDULING_MODEL_ORDER:
        queue = [cell for cell in ordered if cell["model"] == model]
        queues.append({
            "model": model,
            "cell_count": len(queue),
            "cell_ids": [cell["cell_id"] for cell in queue],
            "original_condition_orders": [
                int(cell["condition_order"]) for cell in queue
            ],
        })
    return {
        "deviation_id": "availability_stratified_scheduling_v1",
        "approval_marker": "APPROVE AVAILABILITY-STRATIFIED SCHEDULING",
        "reviewer_agent_id": "019fa390-af77-7312-9c16-7b611362f58a",
        "reason": (
            "The frozen GPT-5.4 deployment returned repeated HTTP 429 cooldown "
            "responses while the frozen Claude Sonnet 4.6 deployment was healthy."
        ),
        "manifest_sha256": manifest_sha256,
        "cell_count": len(cells),
        "stable_partition_rule": (
            "Run the complete Claude Sonnet 4.6 queue, then the complete GPT-5.4 "
            "queue; preserve original condition_order within each model."
        ),
        "model_queue_order": list(SCHEDULING_MODEL_ORDER),
        "queues": queues,
        "constraints": [
            "Do not modify cell assignments, condition_order, tasks, repetitions, or thresholds.",
            "Do not switch model queues in response to outcome or intermediate effect.",
            "Stop on current-cell deployment unavailability; never fall back to another model.",
            "Analyze condition effects within model and task blocks.",
            "Treat cross-model absolute success-rate comparisons as descriptive because model and calendar time are confounded.",
        ],
        "actual_execution_log": "scheduling_execution_log.jsonl",
    }


def prepare_scheduling_deviation(
    output_root: Path,
    *,
    cells: list[dict[str, Any]],
    manifest_path: Path,
) -> Path:
    path = output_root / "scheduling_deviation.json"
    expected = scheduling_deviation_spec(
        cells,
        manifest_sha256=sha256_file(manifest_path),
    )
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key, value in expected.items():
            if existing.get(key) != value:
                raise RuntimeError(
                    f"Frozen scheduling deviation changed at key {key!r}"
                )
    else:
        write_json(
            path,
            {"created_at": FROZEN_SCHEDULING_CREATED_AT, **expected},
        )
    digest = sha256_file(path)
    digest_path = output_root / "scheduling_deviation.sha256"
    expected_digest_text = f"{digest}  {path.name}\n"
    if digest_path.exists():
        if digest_path.read_text(encoding="utf-8") != expected_digest_text:
            raise RuntimeError("Scheduling deviation SHA-256 record changed")
    else:
        digest_path.write_text(expected_digest_text, encoding="utf-8")
    return path


def runtime_routes() -> dict[str, Any]:
    return {
        "route_revision": "aime_direct_deployment_v1",
        "reason": (
            "The original GPT hexin settings file is unavailable to the current "
            "runtime. AIME model-group routing was rejected because gpt-5.4 "
            "silently fell back to claude-opus-4-7 while its GPT deployments "
            "were cooling down."
        ),
        "base_url": "https://aimemodeldev.myhexin.com/litellm/v1",
        "proxy": "http://127.0.0.1:18890",
        "strict_response_model_identity": True,
        "api_key_source": "AIME_LITELLM_API_KEY environment variable",
        "models": {
            model: {
                "semantic_model_id": config["model_id"],
                "requested_deployment": config["deployment_id"],
                "provider": (
                    "openai" if model == "gpt54" else "anthropic"
                ),
                "api_style": config["api_style"],
                "supports_vision": True,
                "deployment_selection": (
                    "first OpenAI gpt-5.4 deployment returned by /model/info; "
                    "frozen before formal execution"
                    if model == "gpt54"
                    else "first healthy Anthropic claude-sonnet-4-6 deployment "
                    "verified by an HTTP 200 /messages probe"
                ),
            }
            for model, config in MODEL_CONFIGS.items()
        },
        "model_info_source": (
            "GET https://aimemodeldev.myhexin.com/litellm/model/info"
        ),
        "review_status": "pending",
        "review_constraints": (
            "Never switch deployment during formal execution; pause on cooldown; "
            "reject any response whose raw response.model differs from the "
            "requested deployment."
        ),
    }


def prepare_runtime_config(
    output_root: Path,
    *,
    manifest_path: Path,
    experiment_kind: str,
    scheduling_path: Path | None = None,
) -> None:
    routes_path = output_root / "runtime_routes.json"
    routes = runtime_routes()
    if routes_path.exists():
        if json.loads(routes_path.read_text(encoding="utf-8")) != routes:
            raise RuntimeError("Frozen runtime route configuration changed")
    else:
        write_json(routes_path, routes)
    config = {
        "experiment_kind": experiment_kind,
        "manifest_path": str(manifest_path.relative_to(output_root)),
        "manifest_sha256": sha256_file(manifest_path),
        "runtime_routes_path": "runtime_routes.json",
        "runtime_routes_sha256": sha256_file(routes_path),
        "credentials_persisted": False,
    }
    if scheduling_path is not None:
        config.update({
            "scheduling_deviation_path": str(
                scheduling_path.relative_to(output_root)
            ),
            "scheduling_deviation_sha256": sha256_file(scheduling_path),
            "scheduling_execution_log": "scheduling_execution_log.jsonl",
        })
    config_path = output_root / "pilot_run_config.json"
    if config_path.exists():
        previous = json.loads(config_path.read_text(encoding="utf-8"))
        if previous != config:
            legacy = dict(config)
            legacy.pop("scheduling_deviation_path", None)
            legacy.pop("scheduling_deviation_sha256", None)
            legacy.pop("scheduling_execution_log", None)
            has_results = bool(read_jsonl(output_root / "runs.jsonl")) or any(
                (output_root / "cells").glob("*/chosen_result.json")
            )
            if (
                experiment_kind == "formal_512_cell_pilot"
                and previous == legacy
                and not has_results
            ):
                write_json(config_path, config)
            else:
                raise RuntimeError("Pilot run configuration changed")
    else:
        write_json(config_path, config)


def review_provenance_spec() -> dict[str, Any]:
    return {
        "restart_reason": (
            "The original formal root was quarantined after concurrent "
            "orchestrators interleaved scheduling events."
        ),
        "source_formal_root": (
            "web_agent_benchmark/pair_evaluation_records/"
            "reflection_history_pilot_20260727"
        ),
        "source_root_excluded_from_analysis": True,
        "frozen_artifact_sha256": {
            "preregistered_cells.jsonl": (
                "cec5ff50737d2f39dd2cf63ff0eb598b2fd07b0c56526c7a78bcf4be20e6f490"
            ),
            "runtime_routes.json": (
                "861be3495cdca215ce7b0e3e9ae8340be026aa326569564a3d0e2f4a08bc10e8"
            ),
            "scheduling_deviation.json": (
                "fa7325dcf6d3e276f615ef1cdacd1f94160c29d293a744ced2d9cab6c720520e"
            ),
        },
        "inherited_review_records": [
            "gate_reviews/gate0_final_approval.json",
            "gate_reviews/availability_stratified_scheduling_approval.json",
            "gate_reviews/stage_auditor_approval.json",
            "gate_reviews/checkpoint_auditor_approval.json",
            "gate_reviews/sonnet_model_scoped_gate1_design_approval.json",
            "gate_reviews/sonnet_model_scoped_gate1_result_approval.json",
        ],
        "reuse_from_quarantined_root": {
            "chosen_results": 0,
            "attempts": 0,
            "scheduling_events": 0,
        },
    }


def prepare_review_provenance(output_root: Path) -> Path:
    path = output_root / "review_provenance.json"
    expected = review_provenance_spec()
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != expected:
            raise RuntimeError("Review provenance changed")
    else:
        write_json(path, expected)
    return path


def next_scheduling_sequence(output_root: Path) -> int:
    starts = [
        event
        for event in read_jsonl(
            output_root / "scheduling_execution_log.jsonl"
        )
        if event.get("event_type") == "cell_start"
    ]
    return len(starts) + 1


def reconcile_scheduling_finishes(
    output_root: Path,
    cells: list[dict[str, Any]],
) -> int:
    """Append an explicit recovery finish if a crash followed chosen-result write."""
    log_path = output_root / "scheduling_execution_log.jsonl"
    events = read_jsonl(log_path)
    terminals = {
        (
            str(event.get("cell_id") or ""),
            int(event.get("execution_sequence") or 0),
        )
        for event in events
        if event.get("event_type") in {"cell_finish", "cell_abort"}
    }
    starts = {
        (
            str(event.get("cell_id") or ""),
            int(event.get("execution_sequence") or 0),
        ): event
        for event in events
        if event.get("event_type") == "cell_start"
    }
    appended = 0
    chosen_sequences: set[tuple[str, int]] = set()
    for cell in cells:
        chosen_path = (
            output_root
            / "cells"
            / str(cell["cell_id"])
            / "chosen_result.json"
        )
        if not chosen_path.exists():
            continue
        row = json.loads(chosen_path.read_text(encoding="utf-8"))
        scheduling = row.get("pilot_scheduling")
        if not isinstance(scheduling, dict):
            continue
        sequence = int(scheduling.get("execution_sequence") or 0)
        key = (str(cell["cell_id"]), sequence)
        if sequence > 0:
            chosen_sequences.add(key)
        if sequence <= 0 or key in terminals:
            continue
        chosen_mtime = datetime.fromtimestamp(
            chosen_path.stat().st_mtime,
            timezone.utc,
        ).isoformat()
        append_jsonl(log_path, {
            "event_type": "cell_finish",
            "cell_id": cell["cell_id"],
            "execution_sequence": sequence,
            "finished_at": chosen_mtime,
            "outcome": row.get("outcome"),
            "chosen_attempt": row.get("pilot_attempt"),
            "recovered_from_chosen_result": True,
            "recovered_at": utc_now(),
        })
        terminals.add(key)
        appended += 1
    for key, start in starts.items():
        if key in terminals or key in chosen_sequences:
            continue
        append_jsonl(log_path, {
            "event_type": "cell_abort",
            "cell_id": key[0],
            "execution_sequence": key[1],
            "aborted_at": utc_now(),
            "reason": "process_interruption_detected_at_resume",
            "original_condition_order": start.get(
                "original_condition_order"
            ),
            "model_queue": start.get("model_queue"),
        })
        terminals.add(key)
        appended += 1
    return appended


def first_incomplete_scheduled_cell(
    output_root: Path,
    cells: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Require completed formal cells to be a strict schedule prefix."""
    first_incomplete: dict[str, Any] | None = None
    for cell in cells:
        completed = result_for_cell(output_root, cell) is not None
        if not completed and first_incomplete is None:
            first_incomplete = cell
        elif completed and first_incomplete is not None:
            raise RuntimeError(
                "Formal chosen results are not a strict prefix of the frozen "
                f"schedule: {cell['cell_id']} completed after missing "
                f"{first_incomplete['cell_id']}"
            )
    return first_incomplete


def find_free_port(start: int = 52000, end: int = 52999) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port in {start}-{end}")


def preflight(models: set[str]) -> list[str]:
    errors: list[str] = []
    if models.intersection(MODELS) and not os.environ.get("AIME_LITELLM_API_KEY"):
        errors.append("AIME_LITELLM_API_KEY is required for both frozen deployments")
    for model in models.intersection(MODELS):
        env = MODEL_CONFIGS[model]["env"]
        if env.get("AIME_LITELLM_HOST_HEADER") != "":
            errors.append(f"{model} must explicitly clear AIME_LITELLM_HOST_HEADER")
        if env.get("AIME_LITELLM_EXTRA_BODY_JSON") != "":
            errors.append(f"{model} must explicitly clear AIME_LITELLM_EXTRA_BODY_JSON")
    return errors


def validate_identity_evidence(
    *,
    row: dict[str, Any],
    identity_log: Path,
    expected_deployment: str,
) -> dict[str, Any]:
    events = read_jsonl(identity_log)
    errors: list[str] = []
    traced_actions = sum(
        1
        for step in row.get("trace") or []
        if isinstance(step, dict)
        and isinstance(step.get("action"), dict)
        and "_raw" in step["action"]
    )
    if (
        not events
        and traced_actions == 0
        and row.get("error_attribution") != "llm_action_generation_error"
    ):
        return {
            "valid": True,
            "applicability": "not_applicable_before_first_model_request",
            "expected_deployment": expected_deployment,
            "identity_event_count": 0,
            "traced_model_action_count": 0,
            "errors": [],
        }
    if not events:
        errors.append("identity log is missing or empty")
    for index, event in enumerate(events):
        if event.get("identity_validated") is not True:
            errors.append(f"identity event {index} is not validated")
        if event.get("requested_deployment") != expected_deployment:
            errors.append(f"identity event {index} requested deployment differs")
        if (
            event.get("result") == "success"
            and event.get("response_model") != expected_deployment
        ):
            errors.append(f"identity event {index} response model differs")

    for step_index, step in enumerate(row.get("trace") or []):
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if not isinstance(action, dict) or "_raw" not in action:
            continue
        metadata = action.get("_response_metadata")
        if not isinstance(metadata, dict):
            errors.append(f"trace step {step_index} lacks response metadata")
            continue
        if metadata.get("identity_validated") is not True:
            errors.append(f"trace step {step_index} identity is not validated")
        if metadata.get("requested_deployment") != expected_deployment:
            errors.append(f"trace step {step_index} requested deployment differs")
        if metadata.get("response_model") != expected_deployment:
            errors.append(f"trace step {step_index} response model differs")
    if not traced_actions and row.get("error_attribution") != "llm_action_generation_error":
        errors.append("trace contains no auditable model-generated action")
    return {
        "valid": not errors,
        "applicability": "applicable",
        "expected_deployment": expected_deployment,
        "identity_event_count": len(events),
        "traced_model_action_count": traced_actions,
        "errors": errors,
    }


def is_retryable_interface_error(row: dict[str, Any]) -> bool:
    if row.get("outcome") != "agent_error":
        return False
    if row.get("error_attribution") != "llm_action_generation_error":
        return False
    text = " ".join([
        str(row.get("exception") or ""),
        str(row.get("error") or ""),
        json.dumps(row.get("trace") or [], ensure_ascii=False),
    ]).lower()
    if "jsondecodeerror" in text or "unsupported browser action" in text:
        return False
    return any(pattern in text for pattern in RETRYABLE_INTERFACE_PATTERNS)


def classify_stop_rule_interface_error(row: dict[str, Any]) -> dict[str, Any]:
    """Classify final failures for infrastructure stop/reporting only.

    This is intentionally separate from ``is_retryable_interface_error``.
    The latter freezes the within-cell retry policy, while this classifier
    unwraps the parent identity-audit error to avoid counting browser and
    action-schema failures as interface outages.
    """
    if row.get("outcome") != "agent_error":
        return {
            "is_interface_error": False,
            "category": "not_agent_error",
            "matched_evidence": None,
        }
    if row.get("error_attribution") != "llm_action_generation_error":
        return {
            "is_interface_error": False,
            "category": "non_interface_runner",
            "matched_evidence": str(row.get("error_attribution") or ""),
        }

    underlying = " ".join([
        str(row.get("exception_before_identity_rejection") or ""),
        str(row.get("error_before_identity_rejection") or ""),
    ]).lower().strip()
    outer = " ".join([
        str(row.get("exception") or ""),
        str(row.get("error") or ""),
        json.dumps(row.get("trace") or [], ensure_ascii=False),
    ]).lower().strip()
    evidence_text = underlying or outer

    for pattern in NON_INTERFACE_HARNESS_PATTERNS:
        if pattern in evidence_text:
            return {
                "is_interface_error": False,
                "category": "non_interface_harness",
                "matched_evidence": pattern,
            }
    for pattern in NON_INTERFACE_PARSER_PATTERNS:
        if pattern in evidence_text:
            return {
                "is_interface_error": False,
                "category": "non_interface_parser",
                "matched_evidence": pattern,
            }
    if row.get("pilot_availability_http_429") is True:
        return {
            "is_interface_error": True,
            "category": "interface_availability",
            "matched_evidence": "pilot_availability_http_429",
        }
    for pattern in STOP_RULE_INTERFACE_PATTERNS:
        if pattern in evidence_text:
            return {
                "is_interface_error": True,
                "category": "interface_transport_or_provider",
                "matched_evidence": pattern,
            }

    identity = row.get("pilot_identity_audit") or {}
    identity_text = " ".join(
        str(error).lower() for error in identity.get("errors") or []
    )
    for pattern in (
        "requested deployment differs",
        "response model differs",
        "identity log is missing or empty",
    ):
        if pattern in identity_text:
            return {
                "is_interface_error": True,
                "category": "interface_identity",
                "matched_evidence": pattern,
            }
    if "identity event" in identity_text and "not validated" in identity_text:
        return {
            "is_interface_error": True,
            "category": "interface_identity",
            "matched_evidence": "identity event not validated",
        }
    return {
        "is_interface_error": False,
        "category": "non_interface_other_agent_error",
        "matched_evidence": None,
    }


def is_stop_rule_interface_error(row: dict[str, Any]) -> bool:
    return bool(
        classify_stop_rule_interface_error(row)["is_interface_error"]
    )


def classify_physical_agent_error_evidence(
    *,
    output_root: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    if (
        row.get("outcome") != "agent_error"
        or row.get("error_attribution") != "llm_action_generation_error"
    ):
        return {
            "applicable": False,
            "is_interface_error": False,
            "category": "not_llm_action_generation_error",
            "classification_errors": [],
        }
    classification_errors: list[str] = []
    cell = row.get("pilot_cell") or {}
    model = str(cell.get("model") or "")
    expected_deployment = str(
        (MODEL_CONFIGS.get(model) or {}).get("deployment_id") or ""
    )
    attempt_relative = str(row.get("pilot_attempt_dir") or "")
    attempt_dir = output_root / attempt_relative
    events = read_jsonl(attempt_dir / "model_identity_events.jsonl")
    expected_count = int(row.get("pilot_actual_http_request_count") or 0)
    if not expected_deployment:
        classification_errors.append("expected deployment is unavailable")
    if not attempt_relative:
        classification_errors.append("pilot_attempt_dir is missing")
    if not events:
        classification_errors.append(
            "identity event log is missing or empty"
        )
    if len(events) != expected_count:
        classification_errors.append(
            f"identity event count {len(events)} differs from "
            f"recorded HTTP count {expected_count}"
        )
    interface_evidence: list[str] = []
    for index, event in enumerate(events):
        prefix = f"identity event {index}"
        if event.get("event_type") != "http_request":
            classification_errors.append(
                f"{prefix} is not an HTTP request"
            )
            continue
        if event.get("requested_deployment") != expected_deployment:
            interface_evidence.append(
                f"{prefix} requested deployment differs"
            )
        if (
            event.get("result") != "success"
            or event.get("status_code") != 200
        ):
            interface_evidence.append(
                f"{prefix} failed with result={event.get('result')!r}, "
                f"status={event.get('status_code')!r}"
            )
            continue
        if event.get("response_model") != expected_deployment:
            interface_evidence.append(
                f"{prefix} response deployment differs"
            )
        if event.get("identity_validated") is not True:
            interface_evidence.append(
                f"{prefix} identity is not validated"
            )
    return {
        "applicable": True,
        "is_interface_error": bool(interface_evidence),
        "category": (
            "interface_physical_event"
            if interface_evidence
            else "physical_identity_valid"
        ),
        "classification_errors": classification_errors,
        "interface_evidence": interface_evidence,
        "identity_event_count": len(events),
    }


def classify_effective_interface_error(
    *,
    output_root: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    text_classification = classify_stop_rule_interface_error(row)
    physical = classify_physical_agent_error_evidence(
        output_root=output_root,
        row=row,
    )
    if physical["classification_errors"]:
        return {
            "is_interface_error": False,
            "category": "classification_error",
            "matched_evidence": None,
            "classification_errors": physical[
                "classification_errors"
            ],
            "physical_evidence": physical,
            "text_classification": text_classification,
        }
    if physical["is_interface_error"]:
        return {
            "is_interface_error": True,
            "category": str(physical["category"]),
            "matched_evidence": None,
            "classification_errors": [],
            "physical_evidence": physical,
            "text_classification": text_classification,
        }
    return {
        **text_classification,
        "classification_errors": [],
        "physical_evidence": physical,
        "text_classification": text_classification,
    }


def non_interface_failure_identity_errors(
    *,
    output_root: Path,
    row: dict[str, Any],
) -> list[str]:
    classification = classify_stop_rule_interface_error(row)
    if classification["category"] not in {
        "non_interface_harness",
        "non_interface_parser",
    }:
        return []
    physical = classify_physical_agent_error_evidence(
        output_root=output_root,
        row=row,
    )
    errors = list(physical["classification_errors"])
    errors.extend(
        "physical interface evidence contradicts non-interface "
        f"classification: {message}"
        for message in physical.get("interface_evidence") or []
    )
    return errors


def is_availability_error(row: dict[str, Any]) -> bool:
    if row.get("outcome") != "agent_error":
        return False
    if row.get("error_attribution") != "llm_action_generation_error":
        return False
    if row.get("pilot_availability_http_429") is True:
        return True
    text = " ".join([
        str(row.get("exception") or ""),
        str(row.get("exception_before_identity_rejection") or ""),
    ]).lower()
    return any(pattern in text for pattern in AVAILABILITY_PATTERNS)


def probe_deployment(model: str) -> dict[str, Any]:
    config = MODEL_CONFIGS[model]
    deployment = str(config["deployment_id"])
    api_style = str(config["api_style"])
    base_url = str(config["env"]["AIME_LITELLM_BASE_URL"]).rstrip("/")
    url = (
        f"{base_url}/messages"
        if api_style == "messages"
        else f"{base_url}/chat/completions"
    )
    payload = {
        "model": deployment,
        "messages": [{"role": "user", "content": "Reply exactly READY."}],
        "max_tokens": 16,
    }
    started = time.monotonic()
    event: dict[str, Any] = {
        "timestamp": utc_now(),
        "model": model,
        "semantic_model_id": config["model_id"],
        "requested_deployment": deployment,
        "api_style": api_style,
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {os.environ['AIME_LITELLM_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(10, 60),
            verify=True,
            proxies={
                "http": config["env"]["AIME_LITELLM_PROXY"],
                "https": config["env"]["AIME_LITELLM_PROXY"],
            },
        )
    except requests.RequestException as exc:
        return {
            **event,
            "duration_sec": time.monotonic() - started,
            "ready": False,
            "probe_state": "temporarily_unavailable",
            "error_category": type(exc).__name__,
        }
    event["duration_sec"] = time.monotonic() - started
    event["status_code"] = int(response.status_code)
    if response.status_code == 429 or 500 <= response.status_code <= 599:
        return {
            **event,
            "ready": False,
            "probe_state": "temporarily_unavailable",
            "error_category": (
                "rate_limit_or_cooldown"
                if response.status_code == 429
                else "upstream_5xx"
            ),
        }
    if response.status_code in {401, 403, 404}:
        return {
            **event,
            "ready": False,
            "probe_state": "fatal",
            "error_category": f"http_{response.status_code}",
        }
    if not (200 <= response.status_code < 300):
        return {
            **event,
            "ready": False,
            "probe_state": "fatal",
            "error_category": "unexpected_http_status",
        }
    try:
        body = response.json()
    except Exception:
        return {
            **event,
            "ready": False,
            "probe_state": "fatal",
            "error_category": "non_json_2xx",
        }
    if not isinstance(body, dict):
        return {
            **event,
            "ready": False,
            "probe_state": "fatal",
            "error_category": "invalid_json_shape_2xx",
        }
    response_model = str(body.get("model") or "")
    event["response_model"] = response_model
    if response_model != deployment:
        return {
            **event,
            "ready": False,
            "probe_state": "fatal",
            "error_category": "model_identity_mismatch",
        }
    return {
        **event,
        "ready": True,
        "probe_state": "ready",
        "error_category": None,
    }


def wait_for_deployment(
    *,
    output_root: Path,
    model: str,
    poll_sec: int,
    max_wait_sec: int,
) -> None:
    deadline = time.monotonic() + max_wait_sec
    while True:
        event = probe_deployment(model)
        append_jsonl(output_root / "route_availability_probes.jsonl", event)
        print(
            f"[availability] {model} state={event['probe_state']} "
            f"status={event.get('status_code')} "
            f"response_model={event.get('response_model')}"
        )
        if event["ready"]:
            return
        if event["probe_state"] == "fatal":
            raise RuntimeError(
                f"Fatal deployment availability failure for {model}: "
                f"{event['error_category']}"
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Deployment {model} remained unavailable for {max_wait_sec}s"
            )
        time.sleep(min(float(poll_sec), remaining))


def run_process_group(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_sec: int,
) -> tuple[int, str, str, bool, str]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_sec)
        return process.returncode, stdout or "", stderr or "", False, "not_needed"
    except subprocess.TimeoutExpired:
        cleanup = "terminated_process_group"
        try:
            os.killpg(process.pid, signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate(timeout=10)
            cleanup = "killed_process_group"
        return 124, stdout or "", stderr or "", True, cleanup


def result_for_cell(output_root: Path, cell: dict[str, Any]) -> dict[str, Any] | None:
    chosen = output_root / "cells" / cell["cell_id"] / "chosen_result.json"
    if not chosen.exists():
        return None
    return json.loads(chosen.read_text(encoding="utf-8"))


def attempt_base_name(attempt: int, availability_abort_index: int) -> str:
    suffix = (
        ""
        if availability_abort_index == 0
        else f"_after_availability_{availability_abort_index:02d}"
    )
    return f"attempt_{attempt:02d}{suffix}"


def completed_attempt_result(
    cell_dir: Path,
    *,
    attempt: int,
    availability_abort_index: int,
) -> Path | None:
    base = attempt_base_name(attempt, availability_abort_index)
    candidates = [cell_dir / base, *sorted(cell_dir.glob(f"{base}_resume_*"))]
    completed = [
        candidate / "result.json"
        for candidate in candidates
        if (candidate / "result.json").is_file()
    ]
    return completed[-1] if completed else None


def fresh_attempt_dir(
    cell_dir: Path,
    *,
    attempt: int,
    availability_abort_index: int,
) -> Path:
    base = attempt_base_name(attempt, availability_abort_index)
    candidate = cell_dir / base
    if not candidate.exists():
        return candidate
    resume = 1
    while True:
        candidate = cell_dir / f"{base}_resume_{resume:02d}"
        if not candidate.exists():
            return candidate
        resume += 1


def run_attempt(
    *,
    output_root: Path,
    cell: dict[str, Any],
    attempt: int,
    availability_abort_index: int,
    task_timeout_sec: int,
) -> dict[str, Any]:
    cell_dir = output_root / "cells" / cell["cell_id"]
    attempt_dir = fresh_attempt_dir(
        cell_dir,
        attempt=attempt,
        availability_abort_index=availability_abort_index,
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)
    port = find_free_port()
    scenario = SCENARIOS[cell["scenario"]]
    tasks_file = (
        REPO_ROOT
        / "web_agent_benchmark"
        / f"{cell['benchmark']}_benchmark_v1"
        / scenario["tasks_file"]
    )
    runs_out = attempt_dir / "runs.jsonl"
    command = [
        sys.executable,
        str(scenario["runner"]),
        "--mode", "llm_agent",
        "--tasks", cell["slug"],
        "--tasks-file", str(tasks_file),
        "--base-url", f"http://127.0.0.1:{port}",
        "--submissions", str(attempt_dir / "submissions.jsonl"),
        "--runs-out", str(runs_out),
        "--summary-out", str(attempt_dir / "summary.md"),
        "--failures-out", str(attempt_dir / "failures.jsonl"),
        "--screenshot-dir", str(attempt_dir / "screenshots"),
        "--max-steps", str(cell["max_steps"]),
        "--max-output-tokens", str(MODEL_CONFIGS[cell["model"]]["max_output_tokens"]),
        "--temperature", str(cell["temperature"]),
        "--top-p", str(cell["top_p"]),
        "--seed", str(cell["seed"]),
    ]
    env = os.environ.copy()
    env.update(MODEL_CONFIGS[cell["model"]]["env"])
    env["WEB_AGENT_HISTORY_CONDITION"] = cell["condition"]
    env["WEB_AGENT_HISTORY_TOKEN_LIMIT"] = str(cell["history_token_limit"])
    env["WEB_AGENT_MODEL_IDENTITY_LOG"] = str(
        attempt_dir / "model_identity_events.jsonl"
    )
    env["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/reflection_pilot_playwright"
    env.pop("WEB_AGENT_EXTRA_SYSTEM_PROMPT", None)
    env.pop("WEB_AGENT_POLICY_MIDDLEWARE", None)
    started = time.monotonic()
    timed_out = False
    return_code, stdout, stderr, timed_out, cleanup_status = run_process_group(
        command,
        cwd=REPO_ROOT,
        env=env,
        timeout_sec=task_timeout_sec,
    )
    duration = time.monotonic() - started
    (attempt_dir / "stdout.log").write_text(stdout, encoding="utf-8")
    (attempt_dir / "stderr.log").write_text(stderr, encoding="utf-8")
    rows = read_jsonl(runs_out)
    request_events = read_jsonl(attempt_dir / "model_identity_events.jsonl")
    actual_http_request_count = sum(
        event.get("event_type") == "http_request" for event in request_events
    )
    row = rows[0] if len(rows) == 1 else None
    identity_audit = (
        validate_identity_evidence(
            row=row,
            identity_log=attempt_dir / "model_identity_events.jsonl",
            expected_deployment=MODEL_CONFIGS[cell["model"]]["deployment_id"],
        )
        if row is not None
        else {
            "valid": False,
            "expected_deployment": MODEL_CONFIGS[cell["model"]]["deployment_id"],
            "identity_event_count": len(request_events),
            "traced_model_action_count": 0,
            "errors": ["runner produced no result row"],
        }
    )
    if row is not None and not identity_audit["valid"]:
        row = {
            **row,
            "outcome_before_identity_rejection": row.get("outcome"),
            "exception_before_identity_rejection": row.get("exception"),
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception": (
                "model identity audit failed: "
                + "; ".join(identity_audit["errors"])
            ),
        }
    if row is not None:
        row["pilot_availability_http_429"] = any(
            event.get("status_code") == 429 for event in request_events
        )
    status = {
        "timestamp": utc_now(),
        "cell_id": cell["cell_id"],
        "attempt": attempt,
        "return_code": return_code,
        "timed_out": timed_out,
        "cleanup_status": cleanup_status,
        "duration_sec": duration,
        "port": port,
        "row_count": len(rows),
        "actual_http_request_count": actual_http_request_count,
        "outcome": row.get("outcome") if row else "missing_row",
        "error_attribution": row.get("error_attribution") if row else "missing_row",
        "identity_audit": identity_audit,
        "availability_aborted": bool(row and is_availability_error(row)),
        "formal_attempt_consumed": not bool(row and is_availability_error(row)),
        "attempt_dir": str(attempt_dir.relative_to(output_root)),
    }
    write_json(attempt_dir / "attempt_status.json", status)
    append_jsonl(output_root / "attempt_manifest.jsonl", status)
    if row is not None:
        enriched = {
            **row,
            "pilot_identity_audit": identity_audit,
            "pilot_cell": cell,
            "pilot_attempt": attempt,
            "pilot_attempt_dir": status["attempt_dir"],
            "pilot_actual_http_request_count": actual_http_request_count,
            "pilot_availability_aborted": status["availability_aborted"],
            "pilot_formal_attempt_consumed": status["formal_attempt_consumed"],
        }
        write_json(attempt_dir / "result.json", enriched)
        return enriched
    return {
        "outcome": "agent_error",
        "error_attribution": "missing_row",
        "pilot_cell": cell,
        "pilot_attempt": attempt,
        "pilot_attempt_dir": status["attempt_dir"],
        "pilot_actual_http_request_count": actual_http_request_count,
        "pilot_availability_aborted": False,
        "pilot_formal_attempt_consumed": True,
    }


def execute_cell(
    *,
    output_root: Path,
    cell: dict[str, Any],
    task_timeout_sec: int,
    availability_gate: bool,
    availability_poll_sec: int,
    availability_max_wait_sec: int,
    scheduling_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cell_dir = output_root / "cells" / cell["cell_id"]
    cell_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[dict[str, Any]] = []
    chosen: dict[str, Any] | None = None
    attempt = 1
    availability_abort_index = 0
    availability_deadline = time.monotonic() + availability_max_wait_sec
    while attempt <= 3:
        existing_path = completed_attempt_result(
            cell_dir,
            attempt=attempt,
            availability_abort_index=availability_abort_index,
        )
        if existing_path is not None:
            row = json.loads(existing_path.read_text(encoding="utf-8"))
        else:
            row = run_attempt(
                output_root=output_root,
                cell=cell,
                attempt=attempt,
                availability_abort_index=availability_abort_index,
                task_timeout_sec=task_timeout_sec,
            )
        if is_availability_error(row):
            if not availability_gate:
                attempts.append(row)
                chosen = row
                break
            availability_abort_index += 1
            remaining = int(availability_deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError(
                    f"Availability wait budget exhausted within cell {cell['cell_id']}"
                )
            wait_for_deployment(
                output_root=output_root,
                model=str(cell["model"]),
                poll_sec=availability_poll_sec,
                max_wait_sec=remaining,
            )
            continue
        attempts.append(row)
        if not is_retryable_interface_error(row):
            chosen = row
            break
        attempt += 1
        availability_abort_index = 0
    if chosen is None:
        chosen = attempts[-1]
    if scheduling_context is not None:
        chosen = {
            **chosen,
            "pilot_scheduling": dict(scheduling_context),
        }
    write_json(cell_dir / "chosen_result.json", chosen)
    checkpoint = {
        "timestamp": utc_now(),
        "cell_id": cell["cell_id"],
        "condition_order": cell["condition_order"],
        "attempt_count": len(attempts),
        "chosen_attempt": chosen.get("pilot_attempt"),
        "outcome": chosen.get("outcome"),
        "error_attribution": chosen.get("error_attribution"),
        "scheduling_execution_sequence": (
            scheduling_context.get("execution_sequence")
            if scheduling_context is not None
            else None
        ),
    }
    append_jsonl(output_root / "checkpoint_manifest.jsonl", checkpoint)
    return chosen


def aggregate(output_root: Path, cells: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for cell in cells:
        row = result_for_cell(output_root, cell)
        if row is None:
            missing.append(cell)
        else:
            rows.append(row)
    write_jsonl(output_root / "runs.jsonl", rows)
    write_jsonl(output_root / "missing_cells.jsonl", missing)
    counts = Counter(row.get("outcome", "unknown") for row in rows)
    summary = {
        "updated_at": utc_now(),
        "expected_cells": len(cells),
        "completed_cells": len(rows),
        "missing_cells": len(missing),
        "outcome_counts": dict(counts),
    }
    write_json(output_root / "run_progress.json", summary)
    return summary


def interface_stop_rule_state(
    rows: list[dict[str, Any]],
    cells: list[dict[str, Any]],
    *,
    output_root: Path,
) -> dict[str, Any]:
    final_cells = Counter(str(cell["condition"]) for cell in cells)
    allowed = {
        condition: int(count * 0.05)
        for condition, count in final_cells.items()
    }
    observed: Counter[str] = Counter()
    classifications: Counter[str] = Counter()
    sequences: dict[str, list[int]] = {
        condition: [] for condition in final_cells
    }
    classification_errors: list[dict[str, Any]] = []
    for row in rows:
        classification = classify_effective_interface_error(
            output_root=output_root,
            row=row,
        )
        effective_category = str(classification["category"])
        physical_errors = list(
            classification.get("classification_errors") or []
        )
        if physical_errors:
            cell = row.get("pilot_cell") or {}
            classification_errors.append({
                "cell_id": str(cell.get("cell_id") or ""),
                "condition": str(cell.get("condition") or ""),
                "category": effective_category,
                "errors": physical_errors,
            })
        classifications[effective_category] += 1
        if not classification["is_interface_error"]:
            continue
        cell = row.get("pilot_cell") or {}
        condition = str(cell.get("condition") or "")
        observed[condition] += 1
        sequence = int(
            (row.get("pilot_scheduling") or {}).get(
                "execution_sequence"
            )
            or 0
        )
        if condition in sequences and sequence:
            sequences[condition].append(sequence)
    exceeded = {
        condition: observed[condition] > allowed[condition]
        for condition in final_cells
    }
    threshold_triggered = any(exceeded.values())
    return {
        "updated_at": utc_now(),
        "rule": "stop if any condition exceeds 5% final interface failures",
        "triggered": threshold_triggered or bool(classification_errors),
        "threshold_triggered": threshold_triggered,
        "classification_error_triggered": bool(classification_errors),
        "final_cells_by_condition": dict(sorted(final_cells.items())),
        "allowed_interface_errors_by_condition": dict(sorted(allowed.items())),
        "observed_interface_errors_by_condition": {
            condition: observed[condition]
            for condition in sorted(final_cells)
        },
        "interface_error_sequences_by_condition": {
            condition: sorted(sequences[condition])
            for condition in sorted(sequences)
        },
        "failure_classification_counts": dict(
            sorted(classifications.items())
        ),
        "classification_errors": classification_errors,
        "exceeded_by_condition": dict(sorted(exceeded.items())),
    }


def update_interface_stop_rule_state(
    output_root: Path,
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    state = interface_stop_rule_state(
        read_jsonl(output_root / "runs.jsonl"),
        cells,
        output_root=output_root,
    )
    write_json(output_root / "interface_error_stop_state.json", state)
    return state


def output_root_for_args(args: argparse.Namespace) -> Path:
    sonnet_auxiliary_smoke = bool(
        getattr(args, "sonnet_auxiliary_smoke", False)
    )
    gpt_model_scoped_smoke = bool(
        getattr(args, "gpt_model_scoped_smoke", False)
    )
    nonformal_smoke = (
        args.instrumentation_smoke
        or sonnet_auxiliary_smoke
        or gpt_model_scoped_smoke
    )
    if gpt_model_scoped_smoke:
        default_smoke_root = DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT
    elif sonnet_auxiliary_smoke:
        default_smoke_root = DEFAULT_SONNET_AUX_SMOKE_OUTPUT_ROOT
    else:
        default_smoke_root = DEFAULT_SMOKE_OUTPUT_ROOT
    return (
        args.output_root
        or (
            default_smoke_root
            if nonformal_smoke
            else DEFAULT_OUTPUT_ROOT
        )
    ).resolve()


def quarantine_reason(output_root: Path) -> str | None:
    incident_path = output_root / CONCURRENCY_INCIDENT_FILENAME
    if not incident_path.exists():
        return None
    try:
        incident = json.loads(incident_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            f"{CONCURRENCY_INCIDENT_FILENAME} cannot be safely read: "
            f"{type(exc).__name__}: {exc}"
        )
    if incident.get("excluded_from_analysis") is True:
        return str(
            incident.get("reason")
            or "output root is quarantined after a concurrency incident"
        )
    return None


def acquire_output_root_lock(output_root: Path):
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / RUNNER_LOCK_FILENAME
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    handle = os.fdopen(descriptor, "r+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    metadata = {
        "pid": os.getpid(),
        "acquired_at": utc_now(),
        "output_root": str(output_root),
    }
    handle.seek(0)
    handle.truncate()
    json.dump(metadata, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def _run_locked(args: argparse.Namespace) -> int:
    sonnet_auxiliary_smoke = bool(
        getattr(args, "sonnet_auxiliary_smoke", False)
    )
    gpt_model_scoped_smoke = bool(
        getattr(args, "gpt_model_scoped_smoke", False)
    )
    selected_smoke_modes = sum([
        bool(args.instrumentation_smoke),
        sonnet_auxiliary_smoke,
        gpt_model_scoped_smoke,
    ])
    if selected_smoke_modes > 1:
        print(
            "PREFLIGHT ERROR: choose only one instrumentation smoke scope",
            file=sys.stderr,
        )
        return 2
    nonformal_smoke = selected_smoke_modes == 1
    output_root = output_root_for_args(args)
    first_incomplete: dict[str, Any] | None = None
    if not nonformal_smoke:
        prepare_review_provenance(output_root)
    if gpt_model_scoped_smoke:
        cells = prepare_gpt_model_scoped_smoke_manifest(output_root)
        manifest_path = output_root / "gpt_model_scoped_smoke_cells.jsonl"
        experiment_kind = "instrumentation_smoke_gpt_model_scoped_non_formal"
        execution_cells = cells
        scheduling_path = None
    elif sonnet_auxiliary_smoke:
        cells = prepare_sonnet_auxiliary_smoke_manifest(output_root)
        manifest_path = output_root / "sonnet_auxiliary_smoke_cells.jsonl"
        experiment_kind = "instrumentation_smoke_sonnet_auxiliary_non_formal"
        execution_cells = cells
        scheduling_path = None
    elif args.instrumentation_smoke:
        cells = prepare_smoke_manifest(output_root)
        manifest_path = output_root / "instrumentation_smoke_cells.jsonl"
        experiment_kind = "instrumentation_smoke_non_formal"
        execution_cells = cells
        scheduling_path = None
    else:
        cells = prepare_manifest(output_root)
        manifest_path = output_root / "preregistered_cells.jsonl"
        experiment_kind = "formal_512_cell_pilot"
        scheduling_path = prepare_scheduling_deviation(
            output_root,
            cells=cells,
            manifest_path=manifest_path,
        )
        execution_cells = scheduled_cells(cells)
    prepare_runtime_config(
        output_root,
        manifest_path=manifest_path,
        experiment_kind=experiment_kind,
        scheduling_path=scheduling_path,
    )
    if not nonformal_smoke:
        stop_state = update_interface_stop_rule_state(output_root, cells)
        if stop_state["triggered"]:
            print(
                "PREFLIGHT ERROR: preregistered interface-error stop rule "
                "is already triggered",
                file=sys.stderr,
            )
            return 4
    if not nonformal_smoke:
        reconcile_scheduling_finishes(output_root, cells)
        if not args.availability_gate:
            print(
                "PREFLIGHT ERROR: formal pilot requires the availability gate",
                file=sys.stderr,
            )
            return 2
        first_incomplete = first_incomplete_scheduled_cell(
            output_root,
            execution_cells,
        )
        if args.only_cell_id is not None and (
            first_incomplete is None
            or args.only_cell_id != first_incomplete["cell_id"]
        ):
            expected = (
                first_incomplete["cell_id"]
                if first_incomplete is not None
                else "<none: schedule complete>"
            )
            print(
                "PREFLIGHT ERROR: formal --only-cell-id must equal the first "
                f"incomplete scheduled cell ({expected})",
                file=sys.stderr,
            )
            return 2
    if args.manifest_only:
        print(json.dumps(aggregate(output_root, cells), indent=2))
        return 0
    if (
        not nonformal_smoke
        and first_incomplete is not None
        and first_incomplete["model"] == "gpt54"
    ):
        gate_errors = validate_gpt_model_scoped_gate1(output_root)
        if gate_errors:
            for error in gate_errors:
                print(f"PREFLIGHT ERROR: {error}", file=sys.stderr)
            return 2
    selected = [
        cell for cell in execution_cells
        if args.only_cell_id is None or cell["cell_id"] == args.only_cell_id
    ]
    errors = preflight({cell["model"] for cell in selected})
    if errors:
        for error in errors:
            print(f"PREFLIGHT ERROR: {error}", file=sys.stderr)
        return 2
    completed_now = 0
    ready_models: set[str] = set()
    gpt_gate1_validated = False
    for cell in selected:
        if result_for_cell(output_root, cell) is not None:
            continue
        if (
            not nonformal_smoke
            and cell["model"] == "gpt54"
            and not gpt_gate1_validated
        ):
            gate_errors = validate_gpt_model_scoped_gate1(output_root)
            if gate_errors:
                for error in gate_errors:
                    print(f"PREFLIGHT ERROR: {error}", file=sys.stderr)
                return 2
            gpt_gate1_validated = True
        try:
            if args.availability_gate and cell["model"] not in ready_models:
                wait_for_deployment(
                    output_root=output_root,
                    model=str(cell["model"]),
                    poll_sec=args.availability_poll_sec,
                    max_wait_sec=args.availability_max_wait_sec,
                )
                ready_models.add(str(cell["model"]))
            scheduling_context: dict[str, Any] | None = None
            if not nonformal_smoke:
                execution_sequence = next_scheduling_sequence(output_root)
                scheduling_context = {
                    "execution_sequence": execution_sequence,
                    "started_at": utc_now(),
                    "original_condition_order": int(cell["condition_order"]),
                    "model_queue": str(cell["model"]),
                    "scheduling_deviation_sha256": sha256_file(
                        scheduling_path
                    ),
                }
                append_jsonl(
                    output_root / "scheduling_execution_log.jsonl",
                    {
                        "event_type": "cell_start",
                        "cell_id": cell["cell_id"],
                        **scheduling_context,
                    },
                )
            chosen = execute_cell(
                output_root=output_root,
                cell=cell,
                task_timeout_sec=args.task_timeout_sec,
                availability_gate=args.availability_gate,
                availability_poll_sec=args.availability_poll_sec,
                availability_max_wait_sec=args.availability_max_wait_sec,
                scheduling_context=scheduling_context,
            )
            if scheduling_context is not None:
                append_jsonl(
                    output_root / "scheduling_execution_log.jsonl",
                    {
                        "event_type": "cell_finish",
                        "cell_id": cell["cell_id"],
                        "execution_sequence": scheduling_context[
                            "execution_sequence"
                        ],
                        "finished_at": utc_now(),
                        "outcome": chosen.get("outcome"),
                        "chosen_attempt": chosen.get("pilot_attempt"),
                    },
                )
        except (RuntimeError, TimeoutError) as exc:
            aggregate(output_root, cells)
            print(f"AVAILABILITY GATE STOP: {exc}", file=sys.stderr)
            return 3
        completed_now += 1
        progress = aggregate(output_root, cells)
        stop_state = (
            update_interface_stop_rule_state(output_root, cells)
            if not nonformal_smoke
            else None
        )
        print(
            f"[pilot] {progress['completed_cells']}/{progress['expected_cells']} "
            f"{cell['model']} {cell['benchmark']} {cell['scenario']}/{cell['slug']} "
            f"{cell['condition']} rep={cell['repetition']}"
        )
        if stop_state is not None and stop_state["triggered"]:
            print(
                "INTERFACE ERROR STOP: a condition exceeded the "
                "preregistered final 5% ceiling",
                file=sys.stderr,
            )
            return 4
        if args.max_new_cells is not None and completed_now >= args.max_new_cells:
            break
    summary = aggregate(output_root, cells)
    if not nonformal_smoke:
        update_interface_stop_rule_state(output_root, cells)
    print(json.dumps(summary, indent=2))
    return 0


def run(args: argparse.Namespace) -> int:
    output_root = output_root_for_args(args)
    reason = quarantine_reason(output_root)
    if reason is not None:
        print(
            f"PREFLIGHT ERROR: output root is quarantined: {reason}",
            file=sys.stderr,
        )
        return 2
    lock_handle = acquire_output_root_lock(output_root)
    if lock_handle is None:
        print(
            f"PREFLIGHT ERROR: another pilot runner holds "
            f"{output_root / RUNNER_LOCK_FILENAME}",
            file=sys.stderr,
        )
        return 2
    try:
        return _run_locked(args)
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--instrumentation-smoke", action="store_true")
    parser.add_argument("--sonnet-auxiliary-smoke", action="store_true")
    parser.add_argument("--gpt-model-scoped-smoke", action="store_true")
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--max-new-cells", type=int)
    parser.add_argument("--only-cell-id")
    parser.add_argument("--task-timeout-sec", type=int, default=900)
    parser.add_argument(
        "--no-availability-gate",
        action="store_false",
        dest="availability_gate",
        help="Disable pre-cell deployment readiness gating.",
    )
    parser.set_defaults(availability_gate=True)
    parser.add_argument("--availability-poll-sec", type=int, default=300)
    parser.add_argument("--availability-max-wait-sec", type=int, default=21600)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
