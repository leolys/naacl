"""
Uncapped batch runner for server_package_195 — maximizes successful misleading samples.

Key differences from run_batch_generation.py:
- No per-source-chart success cap (every sample is always eligible)
- No quota-driven stop condition (runs until all samples are exhausted or --max-samples hit)
- Uses profiled scheduler to pick the best-fit error type per sample
- Avoids error types that are structurally problematic (same avoid list as quota config)
- Supports --target-error-types to restrict to specific error types
- Supports --max-rounds override (default 5 for higher success rate)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import llm_client
import orchestrator
import qa_refactor_agent
from distribution_scheduler import (
    build_attack_request as build_profiled_attack_request,
    build_scheduler_config,
    load_error_type_profiles,
)

WORKSPACE_ROOT = Path(__file__).parent.parent
SERVER_PACKAGE_195_DIR = WORKSPACE_ROOT / "source_datasets" / "server_package_195"
SERVER_PACKAGE_195_QA_CSV = SERVER_PACKAGE_195_DIR / "ChartQA_CoVis_195_QA_with_images.csv"
SERVER_PACKAGE_195_METADATA_CSV = SERVER_PACKAGE_195_DIR / "ChartQA_CoVis_195_Questions_Metadata.csv"
DEFINITIONS_MD = WORKSPACE_ROOT / "datasets" / "error_type_generation_definitions.md"
DEFAULT_OUTPUT_DIR = WORKSPACE_ROOT / "generated_datasets" / "sp195_uncapped"

# Error types to avoid (structurally unreliable or deprecated)
AVOID_ERROR_TYPES = {
    "plottingerror",
    "inconsistentvaluelabels",
    "inconsistentgrouping",
    "Cherry_Picking",
    "Missing_Data",
    "narrative_framing",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def ensure_output_dirs(output_dir: Path) -> None:
    for subdir in (
        "charts",
        "logs",
        "successful",
        "successful_soft",
        "failed",
        "successful_only/charts",
        "successful_only/json",
        "successful_reviewed",
    ):
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)


def load_csv_rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_options(options_str: str, correct_str: str, correct_letter: str | None = None) -> tuple[dict, str]:
    opts = [o.strip() for o in options_str.split(";")]
    labels = ["A", "B", "C", "D"]
    options_dict = {labels[i]: opts[i] for i in range(min(len(opts), len(labels)))}
    if correct_letter:
        correct_letter = correct_letter.strip().upper()
        if correct_letter in options_dict:
            return options_dict, correct_letter
    gold = None
    correct_clean = correct_str.strip()
    for key, val in options_dict.items():
        if val.strip().lower() == correct_clean.lower():
            gold = key
            break
    if gold is None:
        for key, val in options_dict.items():
            if correct_clean.lower() in val.strip().lower():
                gold = key
                break
    if gold is None:
        gold = "A"
    return options_dict, gold


def normalize_chart_type(raw: str) -> str:
    mapping = {
        "h_bar": "bar_chart",
        "v_bar": "bar_chart",
        "line": "line_chart",
        "pie": "pie_or_donut_chart",
    }
    return mapping.get((raw or "").strip().lower(), "multi_series_chart")


def build_samples(question_rows: list[dict], metadata_map: dict[str, dict]) -> list[dict]:
    samples = []
    for row in question_rows:
        image_rel = row.get("image_path", "").strip()
        if not image_rel:
            continue
        chart_path = SERVER_PACKAGE_195_DIR / image_rel
        if not chart_path.exists():
            continue
        options_dict, gold_key = parse_options(
            row.get("options", ""),
            row.get("correct", ""),
            row.get("correct_letter"),
        )
        chart_filename = Path(image_rel).stem
        sample_id = f"SP195_{chart_filename}"
        meta = metadata_map.get(str(row.get("id", "")).strip(), {})
        samples.append({
            "sample_id": sample_id,
            "source_chart_path": str(chart_path),
            "question": row["question"],
            "options": options_dict,
            "gold_answer": gold_key,
            "vis": chart_filename,
            "raw_correct": row.get("correct", ""),
            "question_id": str(row.get("id", "")).strip(),
            "chart_type": normalize_chart_type(row.get("chart_type", "")),
            "task": row.get("task", "") or meta.get("task", ""),
            "difficulty": row.get("difficulty", "") or meta.get("difficulty", ""),
            "discrimination": meta.get("discrimination", ""),
            "source_dataset": "server_package_195",
            "source_chart_id": row.get("chart_id", ""),
            "annotation_path": str(SERVER_PACKAGE_195_DIR / row["annotation_path"]) if row.get("annotation_path") else "",
            "table_path": str(SERVER_PACKAGE_195_DIR / row["table_path"]) if row.get("table_path") else "",
        })
    return samples


def interleave_by_key(samples: list[dict], key: str) -> list[dict]:
    buckets: dict[str, deque] = defaultdict(deque)
    order: list[str] = []
    for s in samples:
        k = str(s.get(key, "") or "")
        if k not in buckets:
            order.append(k)
        buckets[k].append(s)
    result: list[dict] = []
    added = True
    while added:
        added = False
        for k in order:
            if buckets[k]:
                result.append(buckets[k].popleft())
                added = True
    return result


def write_success_dataset_array(output_dir: Path) -> None:
    json_dir = output_dir / "successful_only" / "json"
    rows = []
    if json_dir.exists():
        for path in sorted(json_dir.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    out = output_dir / "successful_only" / "generated_misleading_dataset.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote %d success records to %s", len(rows), out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Uncapped adversarial generation for server_package_195.")
    p.add_argument("--output-dir", type=str, default=None)
    p.add_argument("--max-samples", type=int, default=None, help="Cap total candidates processed.")
    p.add_argument("--start-offset", type=int, default=0)
    p.add_argument("--vis-ids", type=str, default=None, help="Comma-separated chart IDs to restrict to.")
    p.add_argument(
        "--target-error-types", type=str, default=None,
        help="Comma-separated error types to target. If omitted, all non-avoided types are eligible.",
    )
    p.add_argument("--max-rounds", type=int, default=5, help="Adversarial rounds per sample (default 5).")
    p.add_argument(
        "--task-mode-override", type=str, default=None,
        choices=["strict_answerable", "abstention_aware", "scope_reasoning"],
    )
    p.add_argument("--disable-qa-refactor", action="store_true")
    p.add_argument("--profile-path", type=str, default=None)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    ensure_output_dirs(output_dir)

    client = llm_client.make_client()
    try:
        judge_client = llm_client.make_judge_client()
    except Exception:
        judge_client = client

    definitions_text = DEFINITIONS_MD.read_text(encoding="utf-8")
    profiles = load_error_type_profiles(args.profile_path)

    target_error_types: list[str] | None = None
    if args.target_error_types:
        target_error_types = [t.strip() for t in args.target_error_types.split(",") if t.strip()]

    # Build a scheduler config with a large floor so every error type stays eligible
    # (we don't want the scheduler to stop because a quota is "met")
    scheduler_config = build_scheduler_config(
        profiles=profiles,
        current_dataset_json=None,
        target_error_types=target_error_types,
        target_count_per_type=9999,
        floor_per_error_type=9999 if not target_error_types else None,
        task_mode_override=args.task_mode_override,
    )

    # Load and prepare samples
    question_rows = load_csv_rows(SERVER_PACKAGE_195_QA_CSV)
    metadata_rows = load_csv_rows(SERVER_PACKAGE_195_METADATA_CSV)
    metadata_map = {str(r["id"]).strip(): r for r in metadata_rows}
    samples = build_samples(question_rows, metadata_map)

    if args.vis_ids:
        allowed = {v.strip() for v in args.vis_ids.split(",") if v.strip()}
        samples = [s for s in samples if s["vis"] in allowed]

    # Interleave by chart_type then by vis for diversity
    samples = interleave_by_key(samples, "chart_type")
    samples = interleave_by_key(samples, "vis")

    if args.start_offset:
        samples = samples[args.start_offset:]
    if args.max_samples is not None:
        samples = samples[:args.max_samples]

    logger.info("Processing %d candidate samples (uncapped, no per-source limit).", len(samples))

    success_counts_by_error: dict[str, int] = defaultdict(int)
    success_counts_by_source: dict[str, int] = defaultdict(int)
    attempt_counts_by_error: dict[str, int] = defaultdict(int)
    failed_counts_by_error: dict[str, int] = defaultdict(int)
    judge_verdicts: dict[str, int] = defaultdict(int)
    batch_results: list[dict] = []

    for sample in samples:
        # Build attack request via profiled scheduler — picks best error type for this sample
        attack_request = build_profiled_attack_request(
            sample,
            profiles=profiles,
            scheduler_config=scheduler_config,
            success_counts_by_error=success_counts_by_error,
            attempt_counts_by_error=attempt_counts_by_error,
            failed_counts_by_error=failed_counts_by_error,
            legacy_disallowed_error_types=list(AVOID_ERROR_TYPES),
        )

        if not attack_request.get("target_error_type"):
            logger.info("[%s] Skipping: no compatible error type found.", sample["sample_id"])
            batch_results.append({
                "sample_id": sample["sample_id"],
                "eligible_for_attack": False,
                "final_success": False,
                "why_succeeded_or_failed": "no compatible error type",
            })
            continue

        try:
            sample_to_run = qa_refactor_agent.prepare_sample(
                client=client,
                sample=sample,
                attack_request=attack_request,
                enable_refactor=not args.disable_qa_refactor,
            )
        except Exception as exc:
            target_et = attack_request.get("target_error_type")
            logger.warning("[%s] QA refactor failed (%s): %s", sample["sample_id"], target_et, exc)
            if target_et:
                attempt_counts_by_error[target_et] += 1
                failed_counts_by_error[target_et] += 1
            batch_results.append({
                "sample_id": sample["sample_id"],
                "eligible_for_attack": False,
                "final_success": False,
                "dominant_error_type": target_et,
                "why_succeeded_or_failed": f"QA refactor failed: {exc}",
            })
            continue

        logger.info(
            "[%s] target=%s | score=%s | reason=%s",
            sample["sample_id"],
            sample_to_run["attack_preferences"].get("target_error_type"),
            sample_to_run["attack_preferences"].get("selection_score"),
            sample_to_run["attack_preferences"].get("selection_reason"),
        )

        result = orchestrator.run_sample(
            client=client,
            sample=sample_to_run,
            output_dir=output_dir,
            definitions_text=definitions_text,
            max_rounds=args.max_rounds,
            judge_client=judge_client,
        )
        batch_results.append(result)

        scheduled_et = (sample_to_run.get("attack_preferences") or {}).get("target_error_type")
        if scheduled_et and result.get("eligible_for_attack"):
            attempt_counts_by_error[scheduled_et] += 1
            if not result.get("final_success"):
                failed_counts_by_error[scheduled_et] += 1

        if result.get("eligible_for_attack") and result.get("final_success"):
            error_type = result.get("dominant_error_type")
            source_vis = result.get("vis")
            verdict = (result.get("llm_judge_audit") or {}).get("verdict", "unreviewed")
            judge_verdicts[verdict] += 1
            if error_type:
                success_counts_by_error[error_type] += 1
            if source_vis:
                success_counts_by_source[source_vis] += 1

        # Save rolling summary after each sample
        total_success = sum(success_counts_by_error.values())
        summary = {
            "total_success": total_success,
            "success_counts_by_error": dict(success_counts_by_error),
            "success_counts_by_source": dict(success_counts_by_source),
            "attempt_counts_by_error": dict(attempt_counts_by_error),
            "failed_counts_by_error": dict(failed_counts_by_error),
            "judge_verdicts": dict(judge_verdicts),
            "processed_samples": len(batch_results),
        }
        (output_dir / "batch_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    (output_dir / "batch_results.json").write_text(
        json.dumps(batch_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_success_dataset_array(output_dir)

    total = sum(success_counts_by_error.values())
    logger.info(
        "Done. Total successes: %d / %d processed. By error type: %s",
        total,
        len(batch_results),
        dict(success_counts_by_error),
    )
    logger.info("Judge verdicts: %s", dict(judge_verdicts))


if __name__ == "__main__":
    main()
