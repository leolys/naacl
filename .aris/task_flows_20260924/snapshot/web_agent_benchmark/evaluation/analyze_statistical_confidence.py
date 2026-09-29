#!/usr/bin/env python3
"""Statistical confidence analysis for paired clean/misleading benchmark runs.

This script does not rerun any model. It estimates sampling uncertainty from
existing paired benchmark records using task-pair bootstrap, exact McNemar tests,
and Holm-Bonferroni correction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
DEFAULT_INPUT_ROOT = DEFAULT_RECORD_ROOT / "final_selected_merged_20260523_kimi_full140_replaced"
DEFAULT_OUTPUT_ROOT = DEFAULT_RECORD_ROOT / "statistical_confidence_final_selected_kimi_full140_replaced_20260525"
METRICS = ["Acc_cle", "Acc_mis", "PAD", "PRA", "AFR_c", "MSR_c", "DFR", "SI", "DI"]
MECHANISM_METRICS = ["Acc_cle", "Acc_mis", "PAD", "PRA", "AFR_c", "MSR_c"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    return ordered[idx]


def fmt_pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def fmt_pp(value: float) -> str:
    return f"{100.0 * value:.2f} pp"


def fmt_p_value(value: float) -> str:
    if value == 0.0:
        return "<1e-300"
    if value < 1e-4:
        return f"{value:.2e}"
    return f"{value:.4f}"


def action_kind(action: dict[str, Any]) -> str:
    kind = str(action.get("action") or "")
    if kind == "select_option" and str(action.get("select_name") or "") == "primary_action":
        return "select_primary_action"
    return kind or "none"


def primary_action_diagnostics(row: dict[str, Any], *, max_steps: int) -> dict[str, int | bool]:
    trace = row.get("trace") or []
    primary_options: list[str] = []
    primary_steps = 0
    for step in trace:
        action = step.get("action") or {}
        if action_kind(action) == "select_primary_action":
            primary_steps += 1
            primary_options.append(str(action.get("option_text") or action.get("value") or ""))
    switch_count = sum(1 for prev, cur in zip(primary_options, primary_options[1:]) if prev != cur)
    hit_max_steps = bool(row.get("outcome") != "success" and len(trace) >= max_steps)
    return {
        "step_count": len(trace),
        "primary_action_reselect_count": max(0, primary_steps - 1),
        "primary_action_switch_count": switch_count,
        "decision_related_hit_max_steps": bool(hit_max_steps and switch_count > 0),
    }


def decision_instability(row: dict[str, Any], *, baseline_steps: int, max_steps: int) -> int:
    diagnostics = primary_action_diagnostics(row, max_steps=max_steps)
    return int(
        max(0, int(diagnostics["step_count"]) - baseline_steps)
        + int(diagnostics["primary_action_reselect_count"])
        + 2 * int(diagnostics["primary_action_switch_count"])
        + (3 if diagnostics["decision_related_hit_max_steps"] else 0)
    )


def pair_task_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("scenario")), str(row.get("slug"))


def load_pairs(input_root: Path, *, max_steps: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    paired_results = read_jsonl(input_root / "paired_results.jsonl")
    if len(paired_results) != 1540:
        raise RuntimeError(f"{input_root / 'paired_results.jsonl'} expected 1540 rows, found {len(paired_results)}")

    manifest_path = input_root / "merge_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Missing merge manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    included = manifest.get("included") or []
    if len(included) != 11:
        raise RuntimeError(f"Expected 11 models in merge manifest, found {len(included)}")

    all_pairs: list[dict[str, Any]] = []
    for entry in included:
        model_key = str(entry["model_key"])
        model_slug = str(entry["model_slug"])
        official_rows = read_jsonl(input_root / model_slug / "official" / "runs.jsonl")
        clean_rows = read_jsonl(input_root / model_slug / "clean" / "runs.jsonl")
        if len(official_rows) != 140 or len(clean_rows) != 140:
            raise RuntimeError(f"{model_slug} expected 140/140 rows, found {len(official_rows)}/{len(clean_rows)}")
        official_by_task = {pair_task_key(row): row for row in official_rows}
        clean_by_task = {pair_task_key(row): row for row in clean_rows}
        if len(official_by_task) != 140 or len(clean_by_task) != 140:
            raise RuntimeError(f"{model_slug} has duplicate task keys")
        if set(official_by_task) != set(clean_by_task):
            raise RuntimeError(f"{model_slug} official and clean task keys do not match")
        for scenario, slug in sorted(official_by_task):
            official = official_by_task[(scenario, slug)]
            clean = clean_by_task[(scenario, slug)]
            official_steps = len(official.get("trace") or [])
            clean_steps = len(clean.get("trace") or [])
            baseline_steps = min(official_steps, clean_steps)
            all_pairs.append(
                {
                    "model_key": model_key,
                    "model_slug": model_slug,
                    "scenario": scenario,
                    "slug": slug,
                    "task_key": f"{scenario}/{slug}",
                    "misleader_type": official.get("misleader_type") or clean.get("misleader_type") or "unknown",
                    "clean_success": clean.get("outcome") == "success",
                    "mis_success": official.get("outcome") == "success",
                    "mis_outcome": official.get("outcome"),
                    "clean_outcome": clean.get("outcome"),
                    "step_delta": official_steps - clean_steps,
                    "di_delta": decision_instability(official, baseline_steps=baseline_steps, max_steps=max_steps)
                    - decision_instability(clean, baseline_steps=baseline_steps, max_steps=max_steps),
                }
            )

    task_count = len({pair["task_key"] for pair in all_pairs})
    if len(all_pairs) != 1540 or task_count != 140:
        raise RuntimeError(f"Expected 1540 model-task pairs and 140 tasks, found {len(all_pairs)} and {task_count}")
    return all_pairs, included


def compute_metrics(pairs: list[dict[str, Any]]) -> dict[str, float | int]:
    total = len(pairs)
    clean_success = sum(1 for pair in pairs if pair["clean_success"])
    mis_success = sum(1 for pair in pairs if pair["mis_success"])
    both_success = sum(1 for pair in pairs if pair["clean_success"] and pair["mis_success"])
    clean_only_failure = sum(1 for pair in pairs if pair["clean_success"] and not pair["mis_success"])
    clean_to_mechanism = sum(
        1 for pair in pairs if pair["clean_success"] and pair["mis_outcome"] == "misleading_failure"
    )
    return {
        "n": total,
        "clean_success_count": clean_success,
        "mis_success_count": mis_success,
        "both_success_count": both_success,
        "clean_only_failure_count": clean_only_failure,
        "mechanism_aligned_count": clean_to_mechanism,
        "Acc_cle": clean_success / total if total else float("nan"),
        "Acc_mis": mis_success / total if total else float("nan"),
        "PAD": (clean_success - mis_success) / total if total else float("nan"),
        "PRA": both_success / total if total else float("nan"),
        "AFR_c": clean_only_failure / clean_success if clean_success else float("nan"),
        "MSR_c": clean_to_mechanism / clean_success if clean_success else float("nan"),
        "DFR": clean_to_mechanism / clean_only_failure if clean_only_failure else float("nan"),
        "SI": sum(float(pair["step_delta"]) for pair in pairs) / total if total else float("nan"),
        "DI": sum(float(pair["di_delta"]) for pair in pairs) / total if total else float("nan"),
    }


def bootstrap_by_task(
    pairs: list[dict[str, Any]],
    *,
    iters: int,
    rng: random.Random,
    metrics: list[str],
) -> dict[str, tuple[float, float]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_task[str(pair["task_key"])].append(pair)
    task_keys = sorted(by_task)
    samples: dict[str, list[float]] = {metric: [] for metric in metrics}
    for _ in range(iters):
        sampled_pairs: list[dict[str, Any]] = []
        for task_key in rng.choices(task_keys, k=len(task_keys)):
            sampled_pairs.extend(by_task[task_key])
        estimates = compute_metrics(sampled_pairs)
        for metric in metrics:
            value = float(estimates[metric])
            if not math.isnan(value):
                samples[metric].append(value)
    alpha = 0.05
    return {metric: (quantile(values, alpha / 2), quantile(values, 1 - alpha / 2)) for metric, values in samples.items()}


def bootstrap_by_model_task(
    pairs: list[dict[str, Any]],
    *,
    iters: int,
    rng: random.Random,
    metrics: list[str],
) -> dict[str, tuple[float, float]]:
    by_task: dict[str, dict[str, Any]] = {str(pair["task_key"]): pair for pair in pairs}
    task_keys = sorted(by_task)
    samples: dict[str, list[float]] = {metric: [] for metric in metrics}
    for _ in range(iters):
        sampled_pairs = [by_task[task_key] for task_key in rng.choices(task_keys, k=len(task_keys))]
        estimates = compute_metrics(sampled_pairs)
        for metric in metrics:
            value = float(estimates[metric])
            if not math.isnan(value):
                samples[metric].append(value)
    alpha = 0.05
    return {metric: (quantile(values, alpha / 2), quantile(values, 1 - alpha / 2)) for metric, values in samples.items()}


def exact_mcnemar_p(clean_only_success: int, misleading_only_success: int) -> float:
    n = clean_only_success + misleading_only_success
    if n == 0:
        return 1.0
    k = min(clean_only_success, misleading_only_success)
    logs = [
        math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) - n * math.log(2)
        for i in range(k + 1)
    ]
    max_log = max(logs)
    log_tail = max_log + math.log(sum(math.exp(value - max_log) for value in logs))
    return min(1.0, 2.0 * math.exp(log_tail))


def holm_bonferroni(rows: list[dict[str, Any]], *, alpha: float = 0.05) -> None:
    ordered = sorted(rows, key=lambda row: float(row["p_value"]))
    m = len(ordered)
    running_max = 0.0
    for rank, row in enumerate(ordered, start=1):
        adjusted = min(1.0, float(row["p_value"]) * (m - rank + 1))
        running_max = max(running_max, adjusted)
        row["holm_adjusted_p_value"] = running_max
        row["holm_reject_alpha_0_05"] = running_max <= alpha


def metric_row(
    *,
    group_type: str,
    group_name: str,
    metric: str,
    estimates: dict[str, float | int],
    ci: dict[str, tuple[float, float]],
    exploratory: bool = False,
) -> dict[str, Any]:
    low, high = ci.get(metric, (float("nan"), float("nan")))
    return {
        "group_type": group_type,
        "group_name": group_name,
        "metric": metric,
        "estimate": estimates[metric],
        "ci_low": low,
        "ci_high": high,
        "confidence_level": 0.95,
        "n_pairs": estimates["n"],
        "clean_success_count": estimates["clean_success_count"],
        "mis_success_count": estimates["mis_success_count"],
        "both_success_count": estimates["both_success_count"],
        "clean_only_failure_count": estimates["clean_only_failure_count"],
        "mechanism_aligned_count": estimates["mechanism_aligned_count"],
        "exploratory": exploratory,
    }


def write_overall_summary(
    path: Path,
    *,
    input_root: Path,
    estimates: dict[str, float | int],
    ci: dict[str, tuple[float, float]],
    overall_mcnemar: dict[str, Any],
    model_tests: list[dict[str, Any]],
    iters: int,
    seed: int,
) -> None:
    metric_labels = {
        "Acc_cle": "Clean accuracy",
        "Acc_mis": "Misleading accuracy",
        "PAD": "Paired accuracy drop",
        "PRA": "Paired robust accuracy",
        "AFR_c": "Conditional attributable failure rate",
        "MSR_c": "Conditional mechanism-aligned failure rate",
        "DFR": "Directed failure ratio",
        "SI": "Step inflation",
        "DI": "Decision instability delta",
    }
    lines = [
        "# Statistical Confidence Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Source root: `{input_root}`",
        f"- Bootstrap iterations: `{iters}`",
        f"- Seed: `{seed}`",
        "- CI method: percentile bootstrap over paired task clusters.",
        "- McNemar test: exact two-sided paired test on clean vs misleading success.",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Estimate | 95% CI | Count Basis |",
        "|---|---:|---:|---|",
    ]
    for metric in METRICS:
        low, high = ci[metric]
        estimate = float(estimates[metric])
        if metric in {"SI", "DI"}:
            estimate_text = f"{estimate:.2f}"
            ci_text = f"[{low:.2f}, {high:.2f}]"
        elif metric == "PAD":
            estimate_text = fmt_pp(estimate)
            ci_text = f"[{fmt_pp(low)}, {fmt_pp(high)}]"
        else:
            estimate_text = fmt_pct(estimate)
            ci_text = f"[{fmt_pct(low)}, {fmt_pct(high)}]"
        lines.append(f"| {metric_labels[metric]} (`{metric}`) | {estimate_text} | {ci_text} | `{int(estimates['n'])}` model-task pairs |")

    lines.extend(
        [
            "",
            "## McNemar Tests",
            "",
            f"- Overall clean-only success count: `{overall_mcnemar['clean_only_success']}`",
            f"- Overall misleading-only success count: `{overall_mcnemar['misleading_only_success']}`",
            f"- Overall exact McNemar p-value: `{fmt_p_value(float(overall_mcnemar['p_value']))}`",
            f"- Per-model tests significant after Holm-Bonferroni correction: `{sum(1 for row in model_tests if row['holm_reject_alpha_0_05'])}/{len(model_tests)}`",
            "",
            "## Paper-Ready Method Paragraph",
            "",
            "We estimate uncertainty using a paired task-cluster bootstrap over the 140 task pairs. "
            "In each bootstrap replicate, we resample task pairs with replacement and retain all model outcomes "
            "associated with each sampled task, preserving both the clean--misleading pairing and the cross-model "
            f"task correlation. We report percentile 95% confidence intervals over {iters:,} replicates. "
            "For clean-vs-misleading success comparisons, we use exact paired McNemar tests and apply "
            "Holm-Bonferroni correction across the eleven model-level tests.",
            "",
            "## Paper-Ready Result Paragraph",
            "",
            f"Across all 1,540 model-task pairs, clean accuracy is {fmt_pct(float(estimates['Acc_cle']))} "
            f"(95% CI {fmt_pct(ci['Acc_cle'][0])}--{fmt_pct(ci['Acc_cle'][1])}), while misleading accuracy is "
            f"{fmt_pct(float(estimates['Acc_mis']))} (95% CI {fmt_pct(ci['Acc_mis'][0])}--{fmt_pct(ci['Acc_mis'][1])}). "
            f"The paired accuracy drop is {fmt_pp(float(estimates['PAD']))} "
            f"(95% CI {fmt_pp(ci['PAD'][0])}--{fmt_pp(ci['PAD'][1])}). "
            f"Paired robust accuracy is {fmt_pct(float(estimates['PRA']))} "
            f"(95% CI {fmt_pct(ci['PRA'][0])}--{fmt_pct(ci['PRA'][1])}). "
            f"The exact paired McNemar test is highly significant (clean-only successes={overall_mcnemar['clean_only_success']}, "
            f"misleading-only successes={overall_mcnemar['misleading_only_success']}, "
            f"p={fmt_p_value(float(overall_mcnemar['p_value']))}); all eleven model-level clean-vs-misleading drops "
            "remain significant after Holm-Bonferroni correction.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Statistical Confidence Analysis",
                "",
                "This directory contains statistical uncertainty estimates for existing paired benchmark results. "
                "No model was rerun. The analysis treats the 140 paired tasks as the sampling unit and uses "
                "bootstrap resampling to estimate benchmark task-sampling uncertainty.",
                "",
                "## Why Not Repeat Model Runs",
                "",
                "The evaluation uses deterministic decoding settings, and the main uncertainty question for the paper is "
                "whether the 140 paired tasks are sufficient to support the reported benchmark-level conclusions. "
                "Repeating all model calls would mostly measure backend/runtime instability and would be costly. "
                "Paired task bootstrap directly targets the uncertainty induced by the benchmark task sample.",
                "",
                "## Files",
                "",
                "- `overall_confidence_summary.md`: headline CIs, McNemar test, and paper-ready text.",
                "- `model_metric_ci.csv`: per-model metric estimates and percentile bootstrap CIs.",
                "- `model_mcnemar_tests.csv`: exact paired McNemar tests with Holm-Bonferroni correction.",
                "- `mechanism_metric_ci.csv`: exploratory mechanism-level metric CIs.",
                "- `bootstrap_samples_config.json`: reproducibility metadata.",
                "",
                "## Interpretation",
                "",
                "The overall bootstrap resamples task pairs and keeps all model outcomes for each sampled task. "
                "This preserves the clean--misleading pairing and the fact that all models are evaluated on the same tasks. "
                "Mechanism-level intervals are exploratory and should be used as uncertainty descriptions rather than "
                "confirmatory claims unless a separate multiple-comparison procedure is applied.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--bootstrap-iters", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--max-steps", type=int, default=10)
    args = parser.parse_args()
    if args.confidence != 0.95:
        raise RuntimeError("Only percentile 95% CI is currently implemented.")

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    pairs, included = load_pairs(input_root, max_steps=args.max_steps)
    output_root.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    overall_estimates = compute_metrics(pairs)
    overall_ci = bootstrap_by_task(pairs, iters=args.bootstrap_iters, rng=rng, metrics=METRICS)

    model_rows: list[dict[str, Any]] = []
    model_tests: list[dict[str, Any]] = []
    pairs_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    slug_by_model: dict[str, str] = {}
    for pair in pairs:
        pairs_by_model[str(pair["model_key"])].append(pair)
        slug_by_model[str(pair["model_key"])] = str(pair["model_slug"])

    for model_key in sorted(pairs_by_model):
        group = pairs_by_model[model_key]
        estimates = compute_metrics(group)
        ci = bootstrap_by_model_task(group, iters=args.bootstrap_iters, rng=rng, metrics=METRICS)
        for metric in METRICS:
            row = metric_row(
                group_type="model",
                group_name=model_key,
                metric=metric,
                estimates=estimates,
                ci=ci,
            )
            row["model_slug"] = slug_by_model[model_key]
            model_rows.append(row)
        clean_only = sum(1 for pair in group if pair["clean_success"] and not pair["mis_success"])
        misleading_only = sum(1 for pair in group if pair["mis_success"] and not pair["clean_success"])
        model_tests.append(
            {
                "model_key": model_key,
                "model_slug": slug_by_model[model_key],
                "clean_only_success": clean_only,
                "misleading_only_success": misleading_only,
                "discordant_total": clean_only + misleading_only,
                "p_value": exact_mcnemar_p(clean_only, misleading_only),
            }
        )
    holm_bonferroni(model_tests)

    mechanism_rows: list[dict[str, Any]] = []
    pairs_by_mechanism: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        pairs_by_mechanism[str(pair["misleader_type"])].append(pair)
    for mechanism, group in sorted(pairs_by_mechanism.items()):
        estimates = compute_metrics(group)
        ci = bootstrap_by_task(group, iters=args.bootstrap_iters, rng=rng, metrics=MECHANISM_METRICS)
        mechanism_task_count = len({pair["task_key"] for pair in group})
        for metric in MECHANISM_METRICS:
            row = metric_row(
                group_type="mechanism",
                group_name=mechanism,
                metric=metric,
                estimates=estimates,
                ci=ci,
                exploratory=True,
            )
            row["mechanism_task_pairs"] = mechanism_task_count
            mechanism_rows.append(row)

    model_fieldnames = [
        "group_type",
        "group_name",
        "model_slug",
        "metric",
        "estimate",
        "ci_low",
        "ci_high",
        "confidence_level",
        "n_pairs",
        "clean_success_count",
        "mis_success_count",
        "both_success_count",
        "clean_only_failure_count",
        "mechanism_aligned_count",
        "exploratory",
    ]
    write_csv(output_root / "model_metric_ci.csv", model_rows, model_fieldnames)
    write_csv(
        output_root / "model_mcnemar_tests.csv",
        model_tests,
        [
            "model_key",
            "model_slug",
            "clean_only_success",
            "misleading_only_success",
            "discordant_total",
            "p_value",
            "holm_adjusted_p_value",
            "holm_reject_alpha_0_05",
        ],
    )
    mechanism_fieldnames = [
        "group_type",
        "group_name",
        "mechanism_task_pairs",
        "metric",
        "estimate",
        "ci_low",
        "ci_high",
        "confidence_level",
        "n_pairs",
        "clean_success_count",
        "mis_success_count",
        "both_success_count",
        "clean_only_failure_count",
        "mechanism_aligned_count",
        "exploratory",
    ]
    write_csv(output_root / "mechanism_metric_ci.csv", mechanism_rows, mechanism_fieldnames)

    overall_mcnemar = {
        "clean_only_success": int(overall_estimates["clean_only_failure_count"]),
        "misleading_only_success": sum(1 for pair in pairs if pair["mis_success"] and not pair["clean_success"]),
    }
    overall_mcnemar["p_value"] = exact_mcnemar_p(
        overall_mcnemar["clean_only_success"], overall_mcnemar["misleading_only_success"]
    )
    write_overall_summary(
        output_root / "overall_confidence_summary.md",
        input_root=input_root,
        estimates=overall_estimates,
        ci=overall_ci,
        overall_mcnemar=overall_mcnemar,
        model_tests=model_tests,
        iters=args.bootstrap_iters,
        seed=args.seed,
    )
    write_readme(output_root / "README.md")
    config = {
        "generated_at": utc_now(),
        "input_root": str(input_root),
        "output_root": str(output_root),
        "bootstrap_iters": args.bootstrap_iters,
        "seed": args.seed,
        "confidence": args.confidence,
        "ci_method": "percentile_bootstrap",
        "overall_bootstrap_unit": "paired_task_cluster_with_all_model_outcomes",
        "per_model_bootstrap_unit": "paired_task",
        "mechanism_bootstrap_unit": "paired_task_within_misleader_type",
        "model_count": len(included),
        "task_pair_count": len({pair["task_key"] for pair in pairs}),
        "model_task_pair_count": len(pairs),
        "metrics": METRICS,
        "mechanism_metrics": MECHANISM_METRICS,
    }
    (output_root / "bootstrap_samples_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote statistical confidence analysis to {output_root}")
    print(f"Models: {len(included)}")
    print(f"Task pairs: {len({pair['task_key'] for pair in pairs})}")
    print(f"Model-task pairs: {len(pairs)}")
    print(
        "Overall PAD: "
        f"{overall_estimates['PAD']:.6f} "
        f"[{overall_ci['PAD'][0]:.6f}, {overall_ci['PAD'][1]:.6f}]"
    )
    print(
        "Overall McNemar clean-only/misleading-only/p: "
        f"{overall_mcnemar['clean_only_success']}/"
        f"{overall_mcnemar['misleading_only_success']}/"
        f"{overall_mcnemar['p_value']:.3e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
