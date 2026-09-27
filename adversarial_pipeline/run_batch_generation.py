"""
Batch runner for quota-aware adversarial dataset generation.

Reads:
- adversarial_pipeline/generation_quota_config.json
- source_datasets/VLAT/VLAT Questions.csv
- source_datasets/VLAT/VLAT Questions Metadata.csv

Runs the existing orchestrator sequentially while:
- enforcing clean-chart correctness before counting success
- respecting per-source-chart success caps
- passing quota-aware attack preferences to the Reverse Agent
- tracking layer/error-type progress against the quota table
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import llm_client
import orchestrator
import qa_refactor_agent
from distribution_scheduler import (
    build_attack_request as build_profiled_attack_request,
    build_scheduler_config,
    compute_remaining_targets as compute_profiled_remaining_targets,
    load_distribution_target_config,
    load_error_type_profiles,
)


WORKSPACE_ROOT = Path(__file__).parent.parent
VLAT_DIR = WORKSPACE_ROOT / "source_datasets" / "VLAT"
SERVER_PACKAGE_195_DIR = WORKSPACE_ROOT / "source_datasets" / "server_package_195"
GENERATED_DATASETS_DIR = WORKSPACE_ROOT / "generated_datasets"
IMAGES_DIR = VLAT_DIR / "Images"
QUESTIONS_CSV = VLAT_DIR / "VLAT Questions.csv"
METADATA_CSV = VLAT_DIR / "VLAT Questions Metadata.csv"
SERVER_PACKAGE_195_QA_CSV = SERVER_PACKAGE_195_DIR / "ChartQA_CoVis_195_QA_with_images.csv"
SERVER_PACKAGE_195_METADATA_CSV = SERVER_PACKAGE_195_DIR / "ChartQA_CoVis_195_Questions_Metadata.csv"
DEFINITIONS_MD = WORKSPACE_ROOT / "datasets" / "error_type_generation_definitions.md"
QUOTA_CONFIG_JSON = Path(__file__).parent / "generation_quota_config.json"
DEFAULT_VLAT_OUTPUT_DIR = Path(__file__).parent / "batch_outputs"
DEFAULT_SERVER_PACKAGE_195_OUTPUT_DIR = GENERATED_DATASETS_DIR / "server_package_195_misleading" / "batch_outputs"
DEFAULT_CURRENT_DATASET_JSON = WORKSPACE_ROOT / "datasets" / "VLAT_comprehensive_dataset_structured_fixed.json"


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
    ):
        (output_dir / subdir).mkdir(parents=True, exist_ok=True)


def write_success_dataset_array(output_dir: Path) -> Path:
    json_dir = output_dir / "successful_only" / "json"
    rows = []
    if json_dir.exists():
        for path in sorted(json_dir.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    out_path = output_dir / "successful_only" / "generated_misleading_dataset.json"
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


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


def normalize_chart_type(raw_vis_type: str) -> str:
    text = (raw_vis_type or "").strip().lower()
    mapping = {
        "line chart": "line_chart",
        "bar chart": "bar_chart",
        "stacked bar chart": "stacked_bar_chart",
        "pie chart": "pie_or_donut_chart",
        "donut chart": "pie_or_donut_chart",
        "scatterplot": "multi_series_chart",
        "scatter plot": "multi_series_chart",
        "multi-line chart": "multi_series_chart",
    }
    return mapping.get(text, "multi_series_chart")


def normalize_chart_type_server_package_195(raw_chart_type: str) -> str:
    text = (raw_chart_type or "").strip().lower()
    mapping = {
        "h_bar": "bar_chart",
        "v_bar": "bar_chart",
        "line": "line_chart",
        "pie": "pie_or_donut_chart",
    }
    return mapping.get(text, "multi_series_chart")


def build_metadata_map(rows: list[dict]) -> dict[str, dict]:
    return {str(r["id"]).strip(): r for r in rows}


def build_samples(question_rows: list[dict], metadata_map: dict[str, dict]) -> list[dict]:
    samples = []
    for row in question_rows:
        if row.get("dropped", "no").lower() == "yes":
            continue
        vis_id = row["vis"]
        chart_path = IMAGES_DIR / f"{vis_id}.png"
        if not chart_path.exists():
            continue

        options_dict, gold_key = parse_options(row["options"], row["correct"])
        item_id = row.get("item") or f"q{row.get('id', 'x')}"
        sample_id = f"{vis_id}_{item_id}"
        meta = metadata_map.get(str(row.get("id", "")).strip(), {})

        # Look for optional VLAT data table and annotation files
        vlat_table_path = VLAT_DIR / "tables" / f"{vis_id}.csv"
        vlat_annotation_path = VLAT_DIR / "annotations" / f"{vis_id}.json"

        samples.append(
            {
                "sample_id": sample_id,
                "source_chart_path": str(chart_path),
                "question": row["question"],
                "options": options_dict,
                "gold_answer": gold_key,
                "vis": vis_id,
                "raw_correct": row["correct"],
                "question_id": str(row.get("id", "")).strip(),
                "chart_type": normalize_chart_type(meta.get("vis", "")),
                "task": meta.get("task", ""),
                "difficulty": meta.get("difficulty", ""),
                "discrimination": meta.get("discrimination", ""),
                "table_path": str(vlat_table_path) if vlat_table_path.exists() else "",
                "annotation_path": str(vlat_annotation_path) if vlat_annotation_path.exists() else "",
            }
        )
    return samples


def build_samples_server_package_195(question_rows: list[dict], metadata_map: dict[str, dict]) -> list[dict]:
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
        samples.append(
            {
                "sample_id": sample_id,
                "source_chart_path": str(chart_path),
                "question": row["question"],
                "options": options_dict,
                "gold_answer": gold_key,
                "vis": chart_filename,
                "raw_correct": row.get("correct", ""),
                "question_id": str(row.get("id", "")).strip(),
                "chart_type": normalize_chart_type_server_package_195(row.get("chart_type", "")),
                "task": row.get("task", "") or meta.get("task", ""),
                "difficulty": row.get("difficulty", "") or meta.get("difficulty", ""),
                "discrimination": meta.get("discrimination", ""),
                "source_dataset": "server_package_195",
                "source_chart_id": row.get("chart_id", ""),
                "annotation_path": str(SERVER_PACKAGE_195_DIR / row["annotation_path"]) if row.get("annotation_path") else "",
                "table_path": str(SERVER_PACKAGE_195_DIR / row["table_path"]) if row.get("table_path") else "",
            }
        )
    return samples


def load_quota_config() -> dict:
    return json.loads(QUOTA_CONFIG_JSON.read_text(encoding="utf-8"))


def build_error_type_to_layer(quota_config: dict) -> dict[str, str]:
    mapping = {}
    for layer_id, layer_info in quota_config["layer_targets"].items():
        for error_type in layer_info["error_type_targets"]:
            mapping[error_type] = layer_id
    return mapping


def compute_remaining_targets(quota_config: dict, success_counts_by_error: dict[str, int]) -> dict[str, int]:
    remaining = {}
    for layer_info in quota_config["layer_targets"].values():
        for error_type, target in layer_info["error_type_targets"].items():
            remaining[error_type] = max(0, target - success_counts_by_error[error_type])
    return remaining


def build_attack_preferences(
    sample: dict,
    quota_config: dict,
    remaining_by_error: dict[str, int],
    error_type_to_layer: dict[str, str],
    excluded_error_types: set[str] | None = None,
) -> dict:
    excluded_error_types = excluded_error_types or set()
    chart_type = sample.get("chart_type", "multi_series_chart")
    chart_type_prefs = quota_config.get("source_chart_type_preferences", {}).get(chart_type, [])
    preferred_error_types = [
        e for e in chart_type_prefs
        if remaining_by_error.get(e, 0) > 0 and e not in excluded_error_types
    ]

    if not preferred_error_types:
        preferred_error_types = [
            e
            for e, rem in sorted(remaining_by_error.items(), key=lambda kv: (-kv[1], kv[0]))
            if rem > 0 and e not in excluded_error_types
        ][:6]

    preferred_layers = []
    for error_type in preferred_error_types:
        layer = error_type_to_layer.get(error_type)
        if layer and layer not in preferred_layers:
            preferred_layers.append(layer)

    return {
        "chart_type": chart_type,
        "task": sample.get("task", ""),
        "difficulty": sample.get("difficulty", ""),
        "preferred_layers": preferred_layers,
        "preferred_error_types": preferred_error_types[:6],
        "disallowed_error_types": quota_config["global_generation_policy"]["avoid_error_types"],
        "already_attempted_error_types": sorted(excluded_error_types),
        "scheduler_note": (
            "Prefer attacks from preferred_error_types that still have remaining quota. "
            "If the current sample structure makes one clearly inappropriate, choose another "
            "validator-safe option from the preferred list before falling back."
        ),
        "quota_remaining_snapshot": {e: remaining_by_error[e] for e in preferred_error_types[:6]},
    }


def interleave_samples_by_vis(samples: list[dict]) -> list[dict]:
    """Round-robin samples across distinct source charts for more even coverage."""
    buckets: dict[str, deque[dict]] = defaultdict(deque)
    vis_order: list[str] = []

    for sample in samples:
        vis = sample["vis"]
        if vis not in buckets:
            vis_order.append(vis)
        buckets[vis].append(sample)

    interleaved: list[dict] = []
    added = True
    while added:
        added = False
        for vis in vis_order:
            if buckets[vis]:
                interleaved.append(buckets[vis].popleft())
                added = True
    return interleaved


def interleave_samples_by_key(samples: list[dict], key: str) -> list[dict]:
    buckets: dict[str, deque[dict]] = defaultdict(deque)
    key_order: list[str] = []

    for sample in samples:
        bucket_key = str(sample.get(key, "") or "")
        if bucket_key not in buckets:
            key_order.append(bucket_key)
        buckets[bucket_key].append(sample)

    interleaved: list[dict] = []
    added = True
    while added:
        added = False
        for bucket_key in key_order:
            if buckets[bucket_key]:
                interleaved.append(buckets[bucket_key].popleft())
                added = True
    return interleaved


def _make_client():
    try:
        return llm_client.make_client()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create LLM client: %s", exc)
        raise SystemExit(1)


def _make_judge_client():
    """
    Create a separate client for the LLM Judge.

    Configure with JUDGE_LLM_BACKEND / JUDGE_LLM_MODEL env vars to use
    a different model than the Forward/Reverse agents.  Falls back to the
    primary client config if those vars are unset.
    """
    try:
        return llm_client.make_judge_client()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create separate judge client (%s); falling back to primary client.", exc)
        return _make_client()


def compute_precision_metrics(
    judge_verdicts: dict[str, int],
    judge_verdicts_by_error: dict[str, dict[str, int]] | None = None,
) -> dict:
    """Compute precision metrics from LLM judge verdicts."""
    total_reviewed = sum(judge_verdicts.values()) - judge_verdicts.get("unreviewed", 0)
    valid_count = judge_verdicts.get("valid", 0)
    borderline_count = judge_verdicts.get("borderline", 0)
    invalid_count = judge_verdicts.get("invalid", 0)

    precision_strict = valid_count / total_reviewed if total_reviewed > 0 else None
    precision_lenient = (valid_count + borderline_count) / total_reviewed if total_reviewed > 0 else None

    per_error = {}
    for error_type, verdicts in (judge_verdicts_by_error or {}).items():
        et_total = sum(verdicts.values()) - verdicts.get("unreviewed", 0)
        et_valid = verdicts.get("valid", 0)
        per_error[error_type] = {
            "valid": et_valid,
            "borderline": verdicts.get("borderline", 0),
            "invalid": verdicts.get("invalid", 0),
            "unreviewed": verdicts.get("unreviewed", 0),
            "precision": et_valid / et_total if et_total > 0 else None,
        }

    return {
        "total_judge_reviewed": total_reviewed,
        "judge_valid": valid_count,
        "judge_borderline": borderline_count,
        "judge_invalid": invalid_count,
        "judge_unreviewed": judge_verdicts.get("unreviewed", 0),
        "precision_strict": round(precision_strict, 4) if precision_strict is not None else None,
        "precision_lenient": round(precision_lenient, 4) if precision_lenient is not None else None,
        "precision_by_error_type": per_error,
    }


def save_batch_summary(path: Path, summary: dict) -> None:
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quota-aware batch adversarial generation.")
    parser.add_argument(
        "--source_dataset",
        type=str,
        default="vlat",
        choices=["vlat", "server_package_195"],
        help="Which source chart dataset to load.",
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        default=None,
        help="Only process the first N candidate samples after filtering. Useful for dry-runs.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=None,
        help="Directory for batch outputs.",
    )
    parser.add_argument(
        "--start_offset",
        type=int,
        default=0,
        help="Skip the first N candidate samples after filtering/interleaving. Useful for sequential batch runs.",
    )
    parser.add_argument(
        "--vis_ids",
        type=str,
        default=None,
        help="Comma-separated source chart ids to keep, e.g. 'VLAT_a,VLAT_b'.",
    )
    parser.add_argument(
        "--scheduler_mode",
        type=str,
        default="legacy_quota",
        choices=["legacy_quota", "profiled"],
        help="Use the old quota runner or the new profile-driven scheduler.",
    )
    parser.add_argument(
        "--profile_path",
        type=str,
        default=None,
        help="Optional path to error_type_profiles.json.",
    )
    parser.add_argument(
        "--target_config",
        type=str,
        default=None,
        help="Optional distribution target config JSON for profiled scheduling.",
    )
    parser.add_argument(
        "--current_dataset_json",
        type=str,
        default=str(DEFAULT_CURRENT_DATASET_JSON),
        help="Current active dataset JSON used to estimate distribution deficits.",
    )
    parser.add_argument(
        "--target_error_types",
        type=str,
        default=None,
        help="Comma-separated taxonomy categories to target explicitly in profiled mode.",
    )
    parser.add_argument(
        "--target_count_per_type",
        type=int,
        default=None,
        help="When target_error_types are given, treat this as the desired minimum count per type.",
    )
    parser.add_argument(
        "--floor_per_error_type",
        type=int,
        default=None,
        help="In profiled mode, balance toward this minimum count per error type.",
    )
    parser.add_argument(
        "--task_mode_override",
        type=str,
        default=None,
        choices=["strict_answerable", "abstention_aware", "scope_reasoning"],
        help="Force one task mode for all generated samples in profiled mode.",
    )
    parser.add_argument(
        "--disable_qa_refactor",
        action="store_true",
        help="Disable the optional QA refactor agent even when a profile requests it.",
    )
    parser.add_argument(
        "--max_rounds",
        type=int,
        default=None,
        help="Override adversarial rounds per sample. If omitted in profiled mode, use error profile hints when available.",
    )
    return parser.parse_args()


def _resolve_max_rounds(
    *,
    args: argparse.Namespace,
    sample_to_run: dict,
) -> int:
    if args.max_rounds is not None:
        return max(1, int(args.max_rounds))
    if args.scheduler_mode == "profiled":
        profile = sample_to_run.get("error_profile") or {}
        hint = profile.get("max_rounds_hint")
        if hint is not None:
            return max(1, int(hint))
    return 3


def main() -> None:
    args = parse_args()
    client = _make_client()
    judge_client = _make_judge_client()
    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif args.source_dataset == "server_package_195":
        output_dir = DEFAULT_SERVER_PACKAGE_195_OUTPUT_DIR
    else:
        output_dir = DEFAULT_VLAT_OUTPUT_DIR
    ensure_output_dirs(output_dir)

    quota_config = load_quota_config()
    error_type_to_layer = build_error_type_to_layer(quota_config)
    definitions_text = DEFINITIONS_MD.read_text(encoding="utf-8")
    profiles = load_error_type_profiles(args.profile_path) if args.scheduler_mode == "profiled" else {}
    target_config = load_distribution_target_config(args.target_config) if args.scheduler_mode == "profiled" else None
    target_error_types = (
        [item.strip() for item in args.target_error_types.split(",") if item.strip()]
        if args.target_error_types
        else None
    )
    scheduler_config = (
        build_scheduler_config(
            profiles=profiles,
            current_dataset_json=args.current_dataset_json,
            target_config=target_config,
            target_error_types=target_error_types,
            target_count_per_type=args.target_count_per_type,
            floor_per_error_type=args.floor_per_error_type,
            task_mode_override=args.task_mode_override,
        )
        if args.scheduler_mode == "profiled"
        else None
    )

    profiled_target_total = 0
    if args.scheduler_mode == "profiled" and scheduler_config and scheduler_config.target_counts:
        profiled_target_total = sum(
            max(0, scheduler_config.target_counts.get(error_type, 0) - scheduler_config.current_counts.get(error_type, 0))
            for error_type in scheduler_config.target_counts
        )

    if args.source_dataset == "server_package_195":
        question_rows = load_csv_rows(SERVER_PACKAGE_195_QA_CSV)
        metadata_rows = load_csv_rows(SERVER_PACKAGE_195_METADATA_CSV)
        metadata_map = build_metadata_map(metadata_rows)
        samples = build_samples_server_package_195(question_rows, metadata_map)
    else:
        question_rows = load_csv_rows(QUESTIONS_CSV)
        metadata_rows = load_csv_rows(METADATA_CSV)
        metadata_map = build_metadata_map(metadata_rows)
        samples = build_samples(question_rows, metadata_map)
    if args.vis_ids:
        allowed_vis = {v.strip() for v in args.vis_ids.split(",") if v.strip()}
        samples = [s for s in samples if s["vis"] in allowed_vis]
    if args.source_dataset == "server_package_195":
        samples = interleave_samples_by_key(samples, "chart_type")
    samples = interleave_samples_by_vis(samples)
    if args.start_offset:
        samples = samples[args.start_offset :]
    if args.max_samples is not None:
        samples = samples[: args.max_samples]

    success_cap_per_source = quota_config["success_definition"]["same_source_chart_max_successes"]
    target_total = profiled_target_total if args.scheduler_mode == "profiled" else quota_config["target_successful_samples_total"]

    success_counts_by_error: dict[str, int] = defaultdict(int)
    success_counts_by_layer: dict[str, int] = defaultdict(int)
    success_counts_by_source: dict[str, int] = defaultdict(int)
    hard_success_counts_by_error: dict[str, int] = defaultdict(int)
    soft_success_counts_by_error: dict[str, int] = defaultdict(int)
    attempt_counts_by_error: dict[str, int] = defaultdict(int)
    failed_counts_by_error: dict[str, int] = defaultdict(int)

    # Precision tracking from LLM judge verdicts
    judge_verdicts: dict[str, int] = defaultdict(int)  # valid/borderline/invalid/unreviewed
    judge_verdicts_by_error: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    batch_results = []

    logger.info("Loaded %d candidate samples for quota-aware batch generation.", len(samples))

    for sample in samples:
        current_total_success = sum(success_counts_by_error.values())
        if target_total > 0 and current_total_success >= target_total:
            break

        if success_counts_by_source[sample["vis"]] >= success_cap_per_source:
            logger.info(
                "[%s] Skipping: source chart already reached success cap (%d).",
                sample["sample_id"],
                success_cap_per_source,
            )
            continue

        remaining_by_error = compute_remaining_targets(quota_config, success_counts_by_error)
        if max(remaining_by_error.values(), default=0) <= 0:
            if args.scheduler_mode == "legacy_quota":
                break

        if args.scheduler_mode == "profiled" and scheduler_config and scheduler_config.target_counts:
            profiled_remaining = compute_profiled_remaining_targets(
                scheduler_config,
                success_counts_by_error,
            )
            if max(profiled_remaining.values(), default=0) <= 0:
                break

        if args.scheduler_mode == "profiled":
            attack_request = build_profiled_attack_request(
                sample,
                profiles=profiles,
                scheduler_config=scheduler_config,
                success_counts_by_error=success_counts_by_error,
                attempt_counts_by_error=attempt_counts_by_error,
                failed_counts_by_error=failed_counts_by_error,
                legacy_disallowed_error_types=quota_config["global_generation_policy"]["avoid_error_types"],
            )
            if not attack_request.get("target_error_type"):
                logger.info("[%s] Skipping: no compatible target error type from scheduler.", sample["sample_id"])
                continue
            try:
                prepared_sample = qa_refactor_agent.prepare_sample(
                    client=client,
                    sample=sample,
                    attack_request=attack_request,
                    enable_refactor=not args.disable_qa_refactor,
                )
            except Exception as exc:  # noqa: BLE001
                target_error = attack_request.get("target_error_type")
                logger.warning(
                    "[%s] Skipping after QA refactor failure for target %s: %s",
                    sample["sample_id"],
                    target_error,
                    exc,
                )
                if target_error:
                    attempt_counts_by_error[target_error] += 1
                    failed_counts_by_error[target_error] += 1
                batch_results.append(
                    {
                        "sample_id": sample["sample_id"],
                        "eligible_for_attack": False,
                        "final_success": False,
                        "dominant_error_type": target_error,
                        "why_succeeded_or_failed": f"QA refactor failed: {exc}",
                    }
                )
                summary = {
                    "target_total": target_total,
                    "current_total_success": sum(success_counts_by_error.values()),
                    "hard_total_success": sum(hard_success_counts_by_error.values()),
                    "soft_total_success": sum(soft_success_counts_by_error.values()),
                    "success_counts_by_error": dict(success_counts_by_error),
                    "hard_success_counts_by_error": dict(hard_success_counts_by_error),
                    "soft_success_counts_by_error": dict(soft_success_counts_by_error),
                    "success_counts_by_layer": dict(success_counts_by_layer),
                    "success_counts_by_source": dict(success_counts_by_source),
                    "attempt_counts_by_error": dict(attempt_counts_by_error) if args.scheduler_mode == "profiled" else None,
                    "failed_counts_by_error": dict(failed_counts_by_error) if args.scheduler_mode == "profiled" else None,
                    "processed_samples": len(batch_results),
                    "max_samples": args.max_samples,
                    "start_offset": args.start_offset,
                    "vis_ids": args.vis_ids,
                    "scheduler_mode": args.scheduler_mode,
                    "profiled_target_total": profiled_target_total if args.scheduler_mode == "profiled" else None,
                }
                save_batch_summary(output_dir / "batch_summary.json", summary)
                continue
            sample_to_run = prepared_sample
        else:
            sample["attack_preferences"] = build_attack_preferences(
                sample,
                quota_config,
                remaining_by_error,
                error_type_to_layer,
            )
            sample_to_run = sample

        logger.info(
            "[%s] Running sample with target errors: %s | selected=%s | score=%s | reason=%s",
            sample["sample_id"],
            ", ".join(sample_to_run["attack_preferences"]["preferred_error_types"]),
            sample_to_run["attack_preferences"].get("target_error_type"),
            sample_to_run["attack_preferences"].get("selection_score"),
            sample_to_run["attack_preferences"].get("selection_reason"),
        )
        effective_max_rounds = _resolve_max_rounds(args=args, sample_to_run=sample_to_run)
        logger.info(
            "[%s] Effective max_rounds=%d (override=%s profile_hint=%s)",
            sample["sample_id"],
            effective_max_rounds,
            args.max_rounds,
            (sample_to_run.get("error_profile") or {}).get("max_rounds_hint"),
        )

        result = orchestrator.run_sample(
            client=client,
            sample=sample_to_run,
            output_dir=output_dir,
            definitions_text=definitions_text,
            max_rounds=effective_max_rounds,
            judge_client=judge_client,
        )
        batch_results.append(result)

        if args.scheduler_mode == "profiled":
            scheduled_error_type = (sample_to_run.get("attack_preferences") or {}).get("target_error_type")
            if scheduled_error_type and result.get("eligible_for_attack"):
                attempt_counts_by_error[scheduled_error_type] += 1
                if not result.get("final_success"):
                    failed_counts_by_error[scheduled_error_type] += 1

        if result.get("eligible_for_attack") and result.get("final_success"):
            # Track LLM judge precision metrics
            judge_audit = result.get("llm_judge_audit") or {}
            verdict = judge_audit.get("verdict", "unreviewed")
            judge_verdicts[verdict] += 1
            scheduled_et = result.get("dominant_error_type") or "unknown"
            judge_verdicts_by_error[scheduled_et][verdict] += 1

            error_type = result.get("dominant_error_type")
            layer = result.get("attacked_stage")
            source_vis = result.get("vis")
            success_type = result.get("success_type")
            if error_type:
                success_counts_by_error[error_type] += 1
                if success_type == "hard_success":
                    hard_success_counts_by_error[error_type] += 1
                elif success_type == "soft_success":
                    soft_success_counts_by_error[error_type] += 1
                if args.scheduler_mode == "profiled":
                    mapped_layer = (profiles.get(error_type) or {}).get("layer_code")
                else:
                    mapped_layer = error_type_to_layer.get(error_type)
                if mapped_layer:
                    success_counts_by_layer[mapped_layer] += 1
            if source_vis:
                success_counts_by_source[source_vis] += 1

        summary = {
            "source_dataset": args.source_dataset,
            "target_total": target_total,
            "current_total_success": sum(success_counts_by_error.values()),
            "hard_total_success": sum(hard_success_counts_by_error.values()),
            "soft_total_success": sum(soft_success_counts_by_error.values()),
            "success_counts_by_error": dict(success_counts_by_error),
            "hard_success_counts_by_error": dict(hard_success_counts_by_error),
            "soft_success_counts_by_error": dict(soft_success_counts_by_error),
            "success_counts_by_layer": dict(success_counts_by_layer),
            "success_counts_by_source": dict(success_counts_by_source),
            "attempt_counts_by_error": dict(attempt_counts_by_error) if args.scheduler_mode == "profiled" else None,
            "failed_counts_by_error": dict(failed_counts_by_error) if args.scheduler_mode == "profiled" else None,
            "processed_samples": len(batch_results),
            "max_samples": args.max_samples,
            "start_offset": args.start_offset,
            "vis_ids": args.vis_ids,
            "scheduler_mode": args.scheduler_mode,
            "profiled_target_total": profiled_target_total if args.scheduler_mode == "profiled" else None,
            "max_rounds_override": args.max_rounds,
        }
        save_batch_summary(output_dir / "batch_summary.json", summary)

    precision = compute_precision_metrics(dict(judge_verdicts), dict(judge_verdicts_by_error))

    final_summary = {
        "source_dataset": args.source_dataset,
        "quota_config_path": str(QUOTA_CONFIG_JSON),
        "target_total": target_total,
        "current_total_success": sum(success_counts_by_error.values()),
        "hard_total_success": sum(hard_success_counts_by_error.values()),
        "soft_total_success": sum(soft_success_counts_by_error.values()),
        "success_counts_by_error": dict(success_counts_by_error),
        "hard_success_counts_by_error": dict(hard_success_counts_by_error),
        "soft_success_counts_by_error": dict(soft_success_counts_by_error),
        "success_counts_by_layer": dict(success_counts_by_layer),
        "success_counts_by_source": dict(success_counts_by_source),
        "attempt_counts_by_error": dict(attempt_counts_by_error) if args.scheduler_mode == "profiled" else None,
        "failed_counts_by_error": dict(failed_counts_by_error) if args.scheduler_mode == "profiled" else None,
        "precision_metrics": precision,
        "processed_samples": len(batch_results),
        "max_samples": args.max_samples,
        "start_offset": args.start_offset,
        "vis_ids": args.vis_ids,
        "scheduler_mode": args.scheduler_mode,
        "profiled_target_total": profiled_target_total if args.scheduler_mode == "profiled" else None,
        "target_error_types": target_error_types,
        "task_mode_override": args.task_mode_override,
        "max_rounds_override": args.max_rounds,
        "results_file": str(output_dir / "batch_results.json"),
    }
    save_batch_summary(output_dir / "batch_summary.json", final_summary)
    save_batch_summary(output_dir / "batch_results.json", batch_results)
    dataset_array_path = write_success_dataset_array(output_dir)

    logger.info(
        "Batch generation finished. Effective eligible samples: %d (hard=%d soft=%d)",
        final_summary["current_total_success"],
        final_summary["hard_total_success"],
        final_summary["soft_total_success"],
    )
    if precision["precision_strict"] is not None:
        logger.info(
            "LLM Judge precision: strict=%.1f%% lenient=%.1f%% (reviewed=%d valid=%d borderline=%d invalid=%d)",
            precision["precision_strict"] * 100,
            precision["precision_lenient"] * 100,
            precision["total_judge_reviewed"],
            precision["judge_valid"],
            precision["judge_borderline"],
            precision["judge_invalid"],
        )
    logger.info("Batch summary saved to %s", output_dir / "batch_summary.json")
    logger.info("Successful dataset array saved to %s", dataset_array_path)


if __name__ == "__main__":
    main()
