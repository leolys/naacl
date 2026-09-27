"""
Iterative profiled runner that keeps launching batch generation jobs until a
target number of generated misleading samples is reached.

The runner:
- launches `run_batch_generation.py` in profiled mode in sequential windows
- aggregates hard/soft successes across iterations
- maintains a derived dataset JSON so scheduler deficits reflect prior wins
- copies successful compact records into one aggregate folder
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import validator

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_JSON = REPO_ROOT / "datasets" / "VLAT_comprehensive_dataset_structured_fixed.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "adversarial_pipeline" / "profiled_runs" / f"iterative_to_100_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
DEFAULT_SERVER_PACKAGE_195_OUTPUT_ROOT = REPO_ROOT / "generated_datasets" / "server_package_195_misleading" / "iterative_runs" / f"iterative_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
VLAT_DIR = REPO_ROOT / "source_datasets" / "VLAT"
QUESTIONS_CSV = VLAT_DIR / "VLAT Questions.csv"
IMAGES_DIR = VLAT_DIR / "Images"
SERVER_PACKAGE_195_DIR = REPO_ROOT / "source_datasets" / "server_package_195"
SERVER_PACKAGE_195_QA_CSV = SERVER_PACKAGE_195_DIR / "ChartQA_CoVis_195_QA_with_images.csv"
ALL_SUCCESSES = "all_successes"
REVIEWED_VALID_ONLY = "reviewed_valid_only"
ERROR_PROFILES_JSON = REPO_ROOT / "adversarial_pipeline" / "error_type_profiles.json"


def _aggregate_subdir_name(aggregate_mode: str) -> str:
    if aggregate_mode == REVIEWED_VALID_ONLY:
        return "aggregate_reviewed_valid_only"
    return "aggregate"


def _write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load_error_profiles() -> dict[str, dict[str, Any]]:
    data = _load_json(ERROR_PROFILES_JSON, {})
    profiles = data.get("profiles", [])
    return {profile.get("error_type"): profile for profile in profiles if profile.get("error_type")}


def _ensure_dirs(root: Path, aggregate_subdir: str) -> None:
    for sub in (
        f"{aggregate_subdir}/json",
        f"{aggregate_subdir}/charts",
        "iteration_logs",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _load_base_rows(dataset_json: Path) -> list[dict[str, Any]]:
    data = json.loads(dataset_json.read_text(encoding="utf-8"))
    return list(data.get("qa_pairs", []))


def _parse_vis_ids(vis_ids: str | None) -> set[str] | None:
    if not vis_ids:
        return None
    parsed = {item.strip() for item in vis_ids.split(",") if item.strip()}
    return parsed or None


def _estimate_candidate_pool_size(vis_filter: set[str] | None, source_dataset: str) -> int:
    if source_dataset == "server_package_195":
        if not SERVER_PACKAGE_195_QA_CSV.exists():
            return 0
        total = 0
        with open(SERVER_PACKAGE_195_QA_CSV, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                image_rel = row.get("image_path", "").strip()
                if not image_rel:
                    continue
                vis = Path(image_rel).stem
                if vis_filter and vis not in vis_filter:
                    continue
                if not (SERVER_PACKAGE_195_DIR / image_rel).exists():
                    continue
                total += 1
        return total

    if not QUESTIONS_CSV.exists():
        return 0
    total = 0
    with open(QUESTIONS_CSV, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row.get("dropped", "no").strip().lower() == "yes":
                continue
            vis = row.get("vis", "").strip()
            if vis_filter and vis not in vis_filter:
                continue
            if not (IMAGES_DIR / f"{vis}.png").exists():
                continue
            total += 1
    return total


def _choose_cycle_step(candidate_pool_size: int, requested_stride: int) -> int:
    if candidate_pool_size <= 1:
        return 1
    step = max(1, requested_stride)
    step %= candidate_pool_size
    if step == 0:
        step = 1
    while math.gcd(step, candidate_pool_size) != 1:
        step += 1
        if step >= candidate_pool_size:
            step = 1
    return step


def _derived_dataset_path(root: Path, aggregate_subdir: str) -> Path:
    return root / aggregate_subdir / "derived_current_dataset.json"


def _aggregate_records_path(root: Path, aggregate_subdir: str) -> Path:
    return root / aggregate_subdir / "aggregate_records.json"


def _aggregate_summary_path(root: Path, aggregate_subdir: str) -> Path:
    return root / aggregate_subdir / "aggregate_summary.json"


def _iteration_manifest_path(root: Path, aggregate_subdir: str) -> Path:
    return root / aggregate_subdir / "iterations.jsonl"


def _refresh_derived_dataset(
    root: Path,
    base_rows: list[dict[str, Any]],
    aggregate_records: list[dict[str, Any]],
    aggregate_subdir: str,
) -> Path:
    rows = list(base_rows)
    for record in aggregate_records:
        rows.append(record)
    path = _derived_dataset_path(root, aggregate_subdir)
    _write_json(path, {"qa_pairs": rows})
    return path


def _count_successes(records: list[dict[str, Any]]) -> tuple[int, int, int]:
    total = len(records)
    hard = sum(1 for record in records if record.get("success_type") == "hard_success")
    soft = sum(1 for record in records if record.get("success_type") == "soft_success")
    return total, hard, soft


def _source_success_json_dir(iter_dir: Path, aggregate_mode: str) -> Path:
    if aggregate_mode == REVIEWED_VALID_ONLY:
        return iter_dir / "successful_reviewed" / "valid_success" / "json"
    return iter_dir / "successful_only" / "json"


def _full_success_state_path(iter_dir: Path, sample_id: str) -> Path:
    return iter_dir / "successful" / f"{sample_id}.json"


def _revalidate_reviewed_record(
    *,
    iter_dir: Path,
    reviewed_record: dict[str, Any],
    error_profiles: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    sample_id = reviewed_record.get("sample_id")
    if not sample_id:
        return False, "missing sample_id in reviewed record"
    full_state_path = _full_success_state_path(iter_dir, sample_id)
    if not full_state_path.exists():
        return False, f"missing full successful state: {full_state_path}"

    state = _load_json(full_state_path, {})
    rounds = state.get("rounds") or []
    if not rounds:
        return False, "full successful state has no rounds"

    last_round = rounds[-1]
    attack_plan = last_round.get("attack_plan") or {}
    matplotlib_code = last_round.get("matplotlib_code") or ""
    error_type = reviewed_record.get("error_type") or attack_plan.get("target_error_type")
    profile = error_profiles.get(error_type, {})
    result = validator.validate_attack_plan(
        attack_plan,
        matplotlib_code,
        question=state.get("attack_question"),
        options=state.get("attack_options"),
        gold_answer=state.get("attack_gold_answer"),
        task_mode=state.get("task_mode"),
        error_profile=profile,
        prev_attack_plan=None,
        source_chart_path=state.get("source_chart_path"),
        source_chart_type=state.get("chart_type") or reviewed_record.get("chart_type"),
    )
    return result.is_valid, result.reason


def _copy_iteration_successes(
    root: Path,
    iter_dir: Path,
    iteration_idx: int,
    aggregate_records: list[dict[str, Any]],
    *,
    aggregate_mode: str,
    aggregate_subdir: str,
    error_profiles: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    success_json_dir = _source_success_json_dir(iter_dir, aggregate_mode)
    if not success_json_dir.exists():
        return []

    added: list[dict[str, Any]] = []
    for path in sorted(success_json_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if aggregate_mode == REVIEWED_VALID_ONLY:
            ok, reason = _revalidate_reviewed_record(
                iter_dir=iter_dir,
                reviewed_record=record,
                error_profiles=error_profiles or {},
            )
            if not ok:
                continue
        agg_id = f"iter{iteration_idx:03d}__{record['sample_id']}"
        image_rel = record.get("image_path")
        chart_src = iter_dir / image_rel if image_rel else None
        chart_suffix = Path(image_rel).suffix if image_rel else ".png"
        chart_dst = root / aggregate_subdir / "charts" / f"{agg_id}{chart_suffix}"
        if chart_src and chart_src.exists():
            shutil.copy2(chart_src, chart_dst)

        enriched = dict(record)
        enriched["aggregate_id"] = agg_id
        enriched["source_iteration"] = iteration_idx
        enriched["aggregate_mode"] = aggregate_mode
        if "target_error_type" not in enriched and enriched.get("error_type"):
            enriched["target_error_type"] = enriched["error_type"]
        llm_judge = enriched.get("llm_judge")
        if isinstance(llm_judge, dict):
            if "judge_verdict" not in enriched and llm_judge.get("verdict"):
                enriched["judge_verdict"] = llm_judge["verdict"]
            if "successful_review_bucket" not in enriched and llm_judge.get("suggested_bucket"):
                enriched["successful_review_bucket"] = llm_judge["suggested_bucket"]
        elif aggregate_mode == REVIEWED_VALID_ONLY:
            enriched.setdefault("judge_verdict", "valid")
            enriched.setdefault("successful_review_bucket", "valid_success")
        if aggregate_mode == REVIEWED_VALID_ONLY:
            enriched.setdefault("judge_verdict", "valid")
            enriched.setdefault("successful_review_bucket", "valid_success")
        if chart_src and chart_src.exists():
            enriched["image_path"] = str(chart_dst.relative_to(root))

        json_dst = root / aggregate_subdir / "json" / f"{agg_id}.json"
        _write_json(json_dst, enriched)
        aggregate_records.append(enriched)
        added.append(enriched)
    return added


def _append_iteration_manifest(root: Path, aggregate_subdir: str, obj: dict[str, Any]) -> None:
    with open(_iteration_manifest_path(root, aggregate_subdir), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _build_command(args: argparse.Namespace, current_dataset_json: Path, output_dir: Path, start_offset: int) -> list[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "adversarial_pipeline" / "run_batch_generation.py"),
        "--source_dataset",
        args.source_dataset,
        "--scheduler_mode",
        "profiled",
        "--current_dataset_json",
        str(current_dataset_json),
        "--max_samples",
        str(args.batch_max_samples),
        "--start_offset",
        str(start_offset),
        "--output_dir",
        str(output_dir),
    ]
    if args.vis_ids:
        cmd.extend(["--vis_ids", args.vis_ids])
    if args.target_error_types:
        cmd.extend(["--target_error_types", args.target_error_types])
    if args.target_count_per_type is not None:
        cmd.extend(["--target_count_per_type", str(args.target_count_per_type)])
    if args.floor_per_error_type is not None:
        cmd.extend(["--floor_per_error_type", str(args.floor_per_error_type)])
    if args.task_mode_override:
        cmd.extend(["--task_mode_override", args.task_mode_override])
    if args.max_rounds is not None:
        cmd.extend(["--max_rounds", str(args.max_rounds)])
    return cmd


def _run_iteration(cmd: list[str], env: dict[str, str], log_path: Path) -> int:
    with open(log_path, "w", encoding="utf-8") as log_fh:
        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_fh.write(line)
        return process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Iteratively run profiled replenishment until target successes are reached.")
    parser.add_argument(
        "--source_dataset",
        type=str,
        default="vlat",
        choices=["vlat", "server_package_195"],
        help="Which source chart dataset to draw candidates from.",
    )
    parser.add_argument("--target_success_total", type=int, default=100)
    parser.add_argument("--batch_max_samples", type=int, default=24)
    parser.add_argument("--max_iterations", type=int, default=80)
    parser.add_argument("--floor_per_error_type", type=int, default=12)
    parser.add_argument("--target_error_types", type=str, default=None)
    parser.add_argument("--target_count_per_type", type=int, default=None)
    parser.add_argument("--task_mode_override", type=str, default=None)
    parser.add_argument("--max_rounds", type=int, default=None)
    parser.add_argument("--dataset_json", type=str, default=str(DEFAULT_DATASET_JSON))
    parser.add_argument("--output_root", type=str, default=None)
    parser.add_argument("--vis_ids", type=str, default=None, help="Comma-separated source chart ids to keep for targeted iterative runs.")
    parser.add_argument("--offset_stride", type=int, default=None)
    parser.add_argument(
        "--aggregate_mode",
        type=str,
        default=ALL_SUCCESSES,
        choices=[ALL_SUCCESSES, REVIEWED_VALID_ONLY],
        help="Which success bucket should be aggregated into the derived dataset.",
    )
    parser.add_argument(
        "--rebuild_only",
        action="store_true",
        help="Do not launch new iterations. Rebuild the aggregate from existing iter_* folders only.",
    )
    parser.add_argument(
        "--offset_mode",
        type=str,
        default="cycle",
        choices=["cycle", "linear"],
        help="How to advance start_offset across iterations. 'cycle' revisits the candidate pool modularly.",
    )
    parser.add_argument(
        "--max_empty_iterations",
        type=int,
        default=3,
        help="Stop after this many consecutive iterations with zero processed samples.",
    )
    parser.add_argument(
        "--max_stale_iterations",
        type=int,
        default=8,
        help="Stop after this many consecutive iterations with zero newly added successes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.output_root:
        root = Path(args.output_root)
    elif args.source_dataset == "server_package_195":
        root = DEFAULT_SERVER_PACKAGE_195_OUTPUT_ROOT
    else:
        root = DEFAULT_OUTPUT_ROOT
    aggregate_subdir = _aggregate_subdir_name(args.aggregate_mode)
    _ensure_dirs(root, aggregate_subdir)
    error_profiles = _load_error_profiles()

    base_rows = _load_base_rows(Path(args.dataset_json))
    aggregate_records = _load_json(_aggregate_records_path(root, aggregate_subdir), [])
    derived_dataset = _refresh_derived_dataset(root, base_rows, aggregate_records, aggregate_subdir)

    env = dict(os.environ)
    env.setdefault("LLM_BACKEND", "hexin_openai")
    env.setdefault("HEXIN_MODEL", "gpt-5.4")
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(key, None)

    stride = args.offset_stride or args.batch_max_samples
    vis_filter = _parse_vis_ids(args.vis_ids)
    candidate_pool_size = _estimate_candidate_pool_size(vis_filter, args.source_dataset)
    cycle_step = _choose_cycle_step(candidate_pool_size, stride) if args.offset_mode == "cycle" else stride

    total, hard, soft = _count_successes(aggregate_records)
    iteration_idx = 1
    empty_iterations = 0
    stale_iterations = 0

    if args.rebuild_only:
        aggregate_records = []
        aggregate_dir = root / aggregate_subdir
        if aggregate_dir.exists():
            shutil.rmtree(aggregate_dir)
        _ensure_dirs(root, aggregate_subdir)

        iter_dirs = sorted(
            [
                path
                for path in root.glob("iter_*")
                if path.is_dir()
            ]
        )
        last_iter_dir: str | None = None
        for idx, iter_dir in enumerate(iter_dirs, start=1):
            added = _copy_iteration_successes(
                root,
                iter_dir,
                idx,
                aggregate_records,
                aggregate_mode=args.aggregate_mode,
                aggregate_subdir=aggregate_subdir,
                error_profiles=error_profiles,
            )
            _append_iteration_manifest(
                root,
                aggregate_subdir,
                {
                    "iteration": idx,
                    "output_dir": str(iter_dir),
                    "added_successes": len(added),
                    "aggregate_mode": args.aggregate_mode,
                    "rebuild_only": True,
                },
            )
            last_iter_dir = str(iter_dir)

        derived_dataset = _refresh_derived_dataset(root, base_rows, aggregate_records, aggregate_subdir)
        total, hard, soft = _count_successes(aggregate_records)
        _write_json(
            _aggregate_records_path(root, aggregate_subdir),
            aggregate_records,
        )
        _write_json(
            _aggregate_summary_path(root, aggregate_subdir),
            {
                "target_success_total": args.target_success_total,
                "aggregate_total_success": total,
                "aggregate_hard_success": hard,
                "aggregate_soft_success": soft,
                "iterations_completed": len(iter_dirs),
                "last_iteration_output_dir": last_iter_dir,
                "aggregate_records_path": str(_aggregate_records_path(root, aggregate_subdir)),
                "derived_dataset_path": str(derived_dataset),
                "vis_ids": args.vis_ids,
                "source_dataset": args.source_dataset,
                "target_error_types": args.target_error_types,
                "candidate_pool_size": candidate_pool_size,
                "offset_mode": args.offset_mode,
                "offset_step": cycle_step,
                "aggregate_mode": args.aggregate_mode,
                "rebuild_only": True,
            },
        )
        print(
            f"Rebuilt aggregate mode '{args.aggregate_mode}'. total={total} hard={hard} soft={soft} iterations={len(iter_dirs)}",
            flush=True,
        )
        return

    while total < args.target_success_total and iteration_idx <= args.max_iterations:
        iter_dir = root / f"iter_{iteration_idx:03d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        if args.offset_mode == "cycle" and candidate_pool_size > 0:
            start_offset = ((iteration_idx - 1) * cycle_step) % candidate_pool_size
        else:
            start_offset = (iteration_idx - 1) * stride
        cmd = _build_command(args, derived_dataset, iter_dir, start_offset)

        print(
            f"\n=== Iteration {iteration_idx} | current total={total} hard={hard} soft={soft} "
            f"| start_offset={start_offset} | offset_mode={args.offset_mode} | candidate_pool={candidate_pool_size} ===",
            flush=True,
        )
        exit_code = _run_iteration(
            cmd,
            env=env,
            log_path=root / "iteration_logs" / f"iter_{iteration_idx:03d}.log",
        )

        batch_summary = _load_json(iter_dir / "batch_summary.json", {})
        added = _copy_iteration_successes(
            root,
            iter_dir,
            iteration_idx,
            aggregate_records,
            aggregate_mode=args.aggregate_mode,
            aggregate_subdir=aggregate_subdir,
            error_profiles=error_profiles,
        )
        derived_dataset = _refresh_derived_dataset(root, base_rows, aggregate_records, aggregate_subdir)
        processed_samples = int(batch_summary.get("processed_samples") or 0)

        total, hard, soft = _count_successes(aggregate_records)
        reason_counts = Counter()
        batch_results = _load_json(iter_dir / "batch_results.json", [])
        for row in batch_results:
            reason = row.get("why_succeeded_or_failed", "")
            if "QA refactor failed" in reason:
                reason_counts["qa_refactor_failed"] += 1
            elif "no compatible target error type" in reason:
                reason_counts["no_compatible_target"] += 1
            elif row.get("final_success"):
                reason_counts[row.get("success_type") or "success"] += 1
            else:
                reason_counts["attack_failed_after_rounds"] += 1

        if processed_samples == 0:
            empty_iterations += 1
        else:
            empty_iterations = 0

        if added:
            stale_iterations = 0
        else:
            stale_iterations += 1

        _append_iteration_manifest(
            root,
            aggregate_subdir,
            {
                "iteration": iteration_idx,
                "exit_code": exit_code,
                "start_offset": start_offset,
                "output_dir": str(iter_dir),
                "batch_summary": batch_summary,
                "added_successes": len(added),
                "aggregate_total": total,
                "aggregate_hard": hard,
                "aggregate_soft": soft,
                "candidate_pool_size": candidate_pool_size,
                "offset_mode": args.offset_mode,
                "offset_step": cycle_step,
                "aggregate_mode": args.aggregate_mode,
                "empty_iterations": empty_iterations,
                "stale_iterations": stale_iterations,
                "reason_counts": dict(reason_counts),
            },
        )
        _write_json(_aggregate_records_path(root, aggregate_subdir), aggregate_records)
        _write_json(
            _aggregate_summary_path(root, aggregate_subdir),
            {
                "target_success_total": args.target_success_total,
                "aggregate_total_success": total,
                "aggregate_hard_success": hard,
                "aggregate_soft_success": soft,
                "iterations_completed": iteration_idx,
                "last_iteration_output_dir": str(iter_dir),
                "aggregate_records_path": str(_aggregate_records_path(root, aggregate_subdir)),
                "derived_dataset_path": str(derived_dataset),
                "vis_ids": args.vis_ids,
                "source_dataset": args.source_dataset,
                "target_error_types": args.target_error_types,
                "candidate_pool_size": candidate_pool_size,
                "offset_mode": args.offset_mode,
                "offset_step": cycle_step,
                "aggregate_mode": args.aggregate_mode,
            },
        )

        if empty_iterations >= args.max_empty_iterations:
            print(
                f"Stopping early after {empty_iterations} consecutive empty iterations.",
                flush=True,
            )
            break

        if stale_iterations >= args.max_stale_iterations:
            print(
                f"Stopping early after {stale_iterations} consecutive stale iterations with no added successes.",
                flush=True,
            )
            break

        iteration_idx += 1

    print(
        f"\nFinished iterative replenishment. aggregate_total={total} hard={hard} soft={soft} "
        f"target={args.target_success_total} iterations={iteration_idx - 1}",
        flush=True,
    )


if __name__ == "__main__":
    main()
