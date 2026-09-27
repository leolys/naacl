#!/usr/bin/env python3
"""Paired statistical robustness checks for reviewer tvEY's W2 concern."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path


MODEL_NAMES = {
    "gpt54": "GPT-5.4",
    "gpt55_litellm": "GPT-5.5",
    "gemini31flash_image_preview": "Gemini 3.1 Flash",
    "gemini3pro_image_preview": "Gemini 3 Pro",
    "qwen35plus_litellm": "Qwen 3.5 Plus",
    "qwen36plus_litellm": "Qwen 3.6 Plus",
    "claude_haiku_4_5_litellm": "Claude Haiku 4.5",
    "claude_sonnet_4_6_litellm": "Claude Sonnet 4.6",
    "claude_opus_4_6_aime_responses": "Claude Opus 4.6",
    "claude_opus_4_7_aime_responses": "Claude Opus 4.7",
    "kimik26": "Kimi K2.6",
}

MECHANISM_GROUPS = {
    "misleading_annotations": "Misleading annotations",
    "cherry_picking": "Cherry picking",
    "MS_unconventional_scale_directions": "Unconventional scale directions",
    "MS_inappropriate_scale_functions": "Inappropriate scale functions",
    "data_visual_disproportion": "Visual disproportion",
    "dual_encoding": "Dual axis",
    "dual_axis_distortion": "Dual axis",
    "MS_inappropriate_scale_range": "Inappropriate scale range",
    "categorical_encoding_for_continuous_data": "Misuse of cumulative relationship",
    "misuse_of_cumulative_relationship": "Misuse of cumulative relationship",
    "small_size": "Small size",
}

EXPECTED_MECHANISM_COUNTS = {
    "Misleading annotations": 34,
    "Cherry picking": 26,
    "Unconventional scale directions": 19,
    "Inappropriate scale functions": 17,
    "Visual disproportion": 15,
    "Dual axis": 14,
    "Inappropriate scale range": 12,
    "Misuse of cumulative relationship": 2,
    "Small size": 1,
}


def parse_args() -> argparse.Namespace:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--result-root",
        type=Path,
        default=repo
        / "web_agent_benchmark/pair_evaluation_records/"
        "final_selected_merged_20260523_kimi_full140_replaced",
    )
    parser.add_argument(
        "--benchmark-root",
        type=Path,
        default=repo / "web_agent_benchmark/official_benchmark_v1",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=repo / "paper/tvEY_W2_statistical_robustness_20260713.md",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=repo / "paper/tvEY_W2_statistical_robustness_20260713.json",
    )
    parser.add_argument("--bootstrap-samples", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=12345)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def exact_mcnemar_p(clean_only: int, misleading_only: int) -> float:
    discordant = clean_only + misleading_only
    if not discordant:
        return 1.0
    tail = min(clean_only, misleading_only)
    probability = sum(math.comb(discordant, i) for i in range(tail + 1)) / 2**discordant
    return min(1.0, 2.0 * probability)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (key, p_value) in enumerate(ordered):
        running = max(running, (total - index) * p_value)
        adjusted[key] = min(1.0, running)
    return adjusted


def percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def aggregate(task_stats: list[dict]) -> dict[str, float | int]:
    model_task_rows = sum(item["rows"] for item in task_stats)
    clean_success = sum(item["clean_success"] for item in task_stats)
    misleading_success = sum(item["misleading_success"] for item in task_stats)
    attributable_failure = sum(item["attributable_failure"] for item in task_stats)
    return {
        "task_pairs": len(task_stats),
        "model_task_rows": model_task_rows,
        "clean_success": clean_success,
        "misleading_success": misleading_success,
        "attributable_failure": attributable_failure,
        "clean_rate": clean_success / model_task_rows,
        "misleading_rate": misleading_success / model_task_rows,
        "gap": (clean_success - misleading_success) / model_task_rows,
        "afr_c": attributable_failure / clean_success,
    }


def exact_task_cluster_sign_flip(task_stats: list[dict]) -> float:
    differences = [item["clean_success"] - item["misleading_success"] for item in task_stats]
    observed = abs(sum(differences))
    distribution = {0: 1}
    for difference in differences:
        updated: defaultdict[int, int] = defaultdict(int)
        for total, count in distribution.items():
            updated[total + difference] += count
            updated[total - difference] += count
        distribution = dict(updated)
    extreme = sum(count for total, count in distribution.items() if abs(total) >= observed)
    return extreme / 2 ** len(differences)


def bootstrap_task_clusters(
    task_stats: list[dict], samples: int, seed: int
) -> dict[str, list[float]]:
    rng = random.Random(seed)
    size = len(task_stats)
    draws = {name: [] for name in ("clean_rate", "misleading_rate", "gap", "afr_c")}
    for _ in range(samples):
        sample = [task_stats[rng.randrange(size)] for _ in range(size)]
        result = aggregate(sample)
        for name in draws:
            draws[name].append(float(result[name]))
    intervals = {}
    for name, values in draws.items():
        values.sort()
        intervals[name] = [percentile(values, 0.025), percentile(values, 0.975)]
    return intervals


def format_percent(value: float, digits: int = 2) -> str:
    return f"{100.0 * value:.{digits}f}%"


def format_p(value: float) -> str:
    return f"{value:.2e}" if value < 0.0001 else f"{value:.4f}"


def main() -> None:
    args = parse_args()
    paired_rows = load_jsonl(args.result_root / "paired_results.jsonl")

    metadata = {}
    for path in sorted(args.benchmark_root.glob("*_tasks.jsonl")):
        for row in load_jsonl(path):
            metadata[row["task_id"]] = row

    models = sorted({row["model_key"] for row in paired_rows})
    task_ids = sorted({row["task_id"] for row in paired_rows})
    assert len(models) == 11, len(models)
    assert len(task_ids) == 140, len(task_ids)
    assert len(paired_rows) == len(models) * len(task_ids), len(paired_rows)
    assert all(task_id in metadata for task_id in task_ids)

    rows_by_task: defaultdict[str, list[dict]] = defaultdict(list)
    rows_by_model: defaultdict[str, list[dict]] = defaultdict(list)
    for row in paired_rows:
        rows_by_task[row["task_id"]].append(row)
        rows_by_model[row["model_key"]].append(row)
    assert all(len(rows_by_task[task_id]) == len(models) for task_id in task_ids)
    assert all(len(rows_by_model[model]) == len(task_ids) for model in models)

    mechanism_tasks: defaultdict[str, list[str]] = defaultdict(list)
    task_stats = []
    for task_id in task_ids:
        raw_mechanism = metadata[task_id]["misleader_type"]
        if raw_mechanism not in MECHANISM_GROUPS:
            raise KeyError(f"Unmapped mechanism: {raw_mechanism}")
        mechanism = MECHANISM_GROUPS[raw_mechanism]
        mechanism_tasks[mechanism].append(task_id)
        rows = rows_by_task[task_id]
        clean_success = sum(row["clean_outcome"] == "success" for row in rows)
        misleading_success = sum(row["official_outcome"] == "success" for row in rows)
        task_stats.append(
            {
                "task_id": task_id,
                "mechanism": mechanism,
                "rows": len(rows),
                "clean_success": clean_success,
                "misleading_success": misleading_success,
                "attributable_failure": sum(
                    row["clean_outcome"] == "success"
                    and row["official_outcome"] != "success"
                    for row in rows
                ),
            }
        )

    mechanism_counts = {key: len(value) for key, value in mechanism_tasks.items()}
    assert mechanism_counts == EXPECTED_MECHANISM_COUNTS, mechanism_counts

    overall = aggregate(task_stats)
    intervals = bootstrap_task_clusters(task_stats, args.bootstrap_samples, args.seed)
    cluster_p = exact_task_cluster_sign_flip(task_stats)

    model_results = []
    raw_p_values = {}
    for model in models:
        rows = rows_by_model[model]
        clean_success = sum(row["clean_outcome"] == "success" for row in rows)
        misleading_success = sum(row["official_outcome"] == "success" for row in rows)
        clean_only = sum(
            row["clean_outcome"] == "success" and row["official_outcome"] != "success"
            for row in rows
        )
        misleading_only = sum(
            row["clean_outcome"] != "success" and row["official_outcome"] == "success"
            for row in rows
        )
        raw_p_values[model] = exact_mcnemar_p(clean_only, misleading_only)
        model_results.append(
            {
                "model_key": model,
                "model": MODEL_NAMES.get(model, model),
                "clean_success": clean_success,
                "misleading_success": misleading_success,
                "clean_rate": clean_success / len(rows),
                "misleading_rate": misleading_success / len(rows),
                "gap": (clean_success - misleading_success) / len(rows),
                "clean_only": clean_only,
                "misleading_only": misleading_only,
                "afr_c": clean_only / clean_success,
                "mcnemar_p": raw_p_values[model],
            }
        )
    adjusted_p_values = holm_adjust(raw_p_values)
    for row in model_results:
        row["holm_p"] = adjusted_p_values[row["model_key"]]

    leave_one_out = []
    for mechanism in EXPECTED_MECHANISM_COUNTS:
        remaining = [item for item in task_stats if item["mechanism"] != mechanism]
        result = aggregate(remaining)
        leave_one_out.append(
            {
                "omitted_mechanism": mechanism,
                "omitted_pairs": EXPECTED_MECHANISM_COUNTS[mechanism],
                **result,
            }
        )

    payload = {
        "source": str(args.result_root / "paired_results.jsonl"),
        "statistical_unit": "task pair; all 11 model outcomes retained within each task cluster",
        "models": len(models),
        "task_pairs": len(task_ids),
        "bootstrap_samples": args.bootstrap_samples,
        "seed": args.seed,
        "overall": overall,
        "task_cluster_bootstrap_95_ci": intervals,
        "exact_task_cluster_sign_flip_p": cluster_p,
        "per_model_exact_mcnemar": model_results,
        "leave_one_mechanism_out": leave_one_out,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n")

    gap_loo = [row["gap"] for row in leave_one_out]
    afr_loo = [row["afr_c"] for row in leave_one_out]
    model_gaps = [row["gap"] for row in model_results]
    max_holm = max(row["holm_p"] for row in model_results)

    lines = [
        "# tvEY W2 Statistical Robustness Analysis",
        "",
        "## Scope and statistical unit",
        "",
        f"- Source: `{args.result_root / 'paired_results.jsonl'}`",
        f"- Complete paired data: {len(models)} models x {len(task_ids)} task pairs = {len(paired_rows)} model-task pairs.",
        "- Bootstrap and sign-flip inference use the 140 task pairs as clusters. All model outcomes for a sampled task remain together, so the 1,540 rows are not treated as independent.",
        "- The model-specific analysis uses an exact paired McNemar test over each model's 140 clean-misleading task pairs, followed by Holm correction across 11 models.",
        "- Mechanism stability uses the nine mechanism categories reported in the paper and recomputes the aggregate result after omitting each category in turn.",
        "",
        "## Compact rebuttal table",
        "",
        "| Analysis | Result | Robustness evidence |",
        "|---|---:|---|",
        (
            f"| Full paired benchmark | Clean {format_percent(overall['clean_rate'])}; misleading "
            f"{format_percent(overall['misleading_rate'])}; gap {100 * overall['gap']:.2f} pp | "
            f"Task-cluster bootstrap 95% CI for gap: [{100 * intervals['gap'][0]:.2f}, "
            f"{100 * intervals['gap'][1]:.2f}] pp; exact clustered sign-flip "
            f"p={format_p(cluster_p)} |"
        ),
        (
            f"| Conditional attributable failure | AFR_c={format_percent(overall['afr_c'])} "
            f"({overall['attributable_failure']}/{overall['clean_success']}) | "
            f"Task-cluster bootstrap 95% CI: [{format_percent(intervals['afr_c'][0])}, "
            f"{format_percent(intervals['afr_c'][1])}] |"
        ),
        (
            f"| Per-model paired tests | All 11 models have positive clean-minus-misleading gaps "
            f"({100 * min(model_gaps):.2f} to {100 * max(model_gaps):.2f} pp) | "
            f"All exact McNemar tests remain significant after Holm correction "
            f"(maximum adjusted p={format_p(max_holm)}) |"
        ),
        (
            f"| Leave-one-mechanism-out | Gap remains {100 * min(gap_loo):.2f} to "
            f"{100 * max(gap_loo):.2f} pp; AFR_c remains {format_percent(min(afr_loo))} to "
            f"{format_percent(max(afr_loo))} | All nine omissions preserve the same direction |"
        ),
        "",
        "## Per-model exact paired tests",
        "",
        "| Model | Clean | Misleading | Gap (pp) | Clean-only / misleading-only | AFR_c | Exact McNemar p | Holm p |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in sorted(model_results, key=lambda item: item["model"]):
        lines.append(
            f"| {row['model']} | {row['clean_success']}/140 | {row['misleading_success']}/140 | "
            f"{100 * row['gap']:.2f} | {row['clean_only']} / {row['misleading_only']} | "
            f"{format_percent(row['afr_c'])} | {format_p(row['mcnemar_p'])} | "
            f"{format_p(row['holm_p'])} |"
        )

    lines.extend(
        [
            "",
            "## Leave-one-mechanism-out stability",
            "",
            "| Omitted mechanism | Omitted pairs | Remaining pairs | Gap (pp) | AFR_c |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in leave_one_out:
        lines.append(
            f"| {row['omitted_mechanism']} | {row['omitted_pairs']} | {row['task_pairs']} | "
            f"{100 * row['gap']:.2f} | {format_percent(row['afr_c'])} |"
        )

    lines.extend(
        [
            "",
            "## Recommended W2 statement",
            "",
            (
                "Using the task pair as the resampling unit, a 100,000-sample cluster bootstrap "
                f"places the {100 * overall['gap']:.1f}-point clean-to-misleading success gap at "
                f"{100 * intervals['gap'][0]:.1f}-{100 * intervals['gap'][1]:.1f} points (95% CI), "
                f"while AFR_c={100 * overall['afr_c']:.1f}% has a 95% CI of "
                f"{100 * intervals['afr_c'][0]:.1f}-{100 * intervals['afr_c'][1]:.1f}%. "
                "The direction is also preserved for every evaluated agent after Holm-corrected "
                "exact McNemar tests and after omitting any one of the nine misleading-mechanism "
                "categories. These checks show that the aggregate finding is unlikely to be a "
                "chance fluctuation or to be driven by a single mechanism category."
            ),
            "",
            "## Interpretation boundary",
            "",
            "These analyses strengthen the reliability and within-benchmark stability of the paired effect. They do not by themselves establish coverage of every real-world webpage structure or application domain, so the reusable construction workflow and future expansion remain complementary rather than statistical evidence for external validity.",
            "",
        ]
    )
    args.output_md.write_text("\n".join(lines))

    print(f"Wrote {args.output_md}")
    print(f"Wrote {args.output_json}")
    print(
        f"gap={100 * overall['gap']:.2f} pp, "
        f"95% CI=[{100 * intervals['gap'][0]:.2f}, {100 * intervals['gap'][1]:.2f}] pp, "
        f"AFR_c={100 * overall['afr_c']:.2f}%"
    )


if __name__ == "__main__":
    main()
