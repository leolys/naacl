#!/usr/bin/env python3
"""Run Benchmark v2 Open evaluations.

This wrapper lets new experiments target `web_agent_benchmark/benchmark_v2_open`
directly while reusing the existing official/clean scenario runners and the
Real-World40 runner.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_agent_benchmark.evaluation import run_pair_benchmarks as pair_runner  # noqa: E402


RELEASE_ROOT = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2_open"
RECORD_ROOT = REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records"
REAL_WORLD_PORT = 28447
REAL_WORLD_DRYRUN_TASKS = "rw001,rw020,rw040"
REAL_WORLD_FULL_TASKS = "all"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def parse_splits(raw: str) -> set[str]:
    if raw == "all":
        return {"official140", "clean140", "real_world40"}
    if raw == "paired":
        return {"official140", "clean140"}
    mapping = {
        "official": "official140",
        "official140": "official140",
        "clean": "clean140",
        "clean140": "clean140",
        "real_world": "real_world40",
        "real_world40": "real_world40",
    }
    splits: set[str] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if item not in mapping:
            raise RuntimeError(f"Unknown split: {item}")
        splits.add(mapping[item])
    if not splits:
        raise RuntimeError("No splits selected")
    return splits


def namespace_for_pair_helpers(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        record_slug_suffix=args.record_slug_suffix,
        model_max_output_tokens=args.model_max_output_tokens,
        aime_base_url=args.aime_base_url,
        aime_model=args.aime_model,
        aime_host_header=args.aime_host_header,
        aime_verify_ssl=args.aime_verify_ssl,
        aime_api_style=args.aime_api_style,
        aime_max_retries=args.aime_max_retries,
        aime_request_delay_sec=args.aime_request_delay_sec,
        aime_read_timeout_sec=args.aime_read_timeout_sec,
        aime_extra_body_json=args.aime_extra_body_json,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=args.seed,
        experiment_variant=args.experiment_variant,
        thinking_budget_supported=args.thinking_budget_supported,
        extra_system_prompt=args.extra_system_prompt,
    )


def record_slug_for(model_key: str, args: argparse.Namespace) -> str:
    helper_args = namespace_for_pair_helpers(args)
    return pair_runner.record_slug_for(model_key, helper_args)


def model_metadata_for(model_key: str, args: argparse.Namespace) -> dict[str, Any]:
    helper_args = namespace_for_pair_helpers(args)
    return pair_runner.model_metadata_for(model_key, helper_args)


def effective_model_env(model_key: str, args: argparse.Namespace) -> dict[str, str]:
    helper_args = namespace_for_pair_helpers(args)
    return pair_runner.effective_model_env(model_key, helper_args)


def effective_max_output_tokens(model_key: str, args: argparse.Namespace) -> int:
    helper_args = namespace_for_pair_helpers(args)
    return pair_runner.effective_max_output_tokens(model_key, helper_args)


def append_common_pair_args(cmd: list[str], args: argparse.Namespace) -> None:
    cmd.extend(
        [
            "--profile",
            args.profile,
            "--temperature",
            str(args.temperature),
            "--top-p",
            str(args.top_p),
            "--seed",
            str(args.seed),
            "--max-steps",
            str(args.max_steps),
            "--port-offset",
            str(args.port_offset),
            "--record-root",
            str(args.record_root),
            "--official-root",
            str(args.release_root / "splits" / "official140"),
            "--clean-root",
            str(args.release_root / "splits" / "clean140"),
        ]
    )
    optional_pairs = [
        ("--model-max-output-tokens", args.model_max_output_tokens),
        ("--aime-max-retries", args.aime_max_retries),
        ("--aime-request-delay-sec", args.aime_request_delay_sec),
        ("--aime-read-timeout-sec", args.aime_read_timeout_sec),
        ("--aime-extra-body-json", args.aime_extra_body_json),
        ("--aime-base-url", args.aime_base_url),
        ("--aime-model", args.aime_model),
        ("--aime-host-header", args.aime_host_header),
        ("--aime-verify-ssl", args.aime_verify_ssl),
        ("--aime-api-style", args.aime_api_style),
        ("--experiment-variant", args.experiment_variant),
        ("--thinking-budget-supported", args.thinking_budget_supported),
        ("--extra-system-prompt", args.extra_system_prompt),
        ("--record-slug-suffix", args.record_slug_suffix),
        ("--scenarios", args.scenarios),
        ("--task-overrides", args.task_overrides),
    ]
    for flag, value in optional_pairs:
        if value not in (None, ""):
            cmd.extend([flag, str(value)])


def run_paired_splits(args: argparse.Namespace, splits: set[str]) -> None:
    selected = sorted(splits & {"official140", "clean140"})
    if not selected:
        return
    if selected == ["clean140", "official140"]:
        benchmark = "both"
    elif selected == ["official140"]:
        benchmark = "official"
    elif selected == ["clean140"]:
        benchmark = "clean"
    else:
        raise RuntimeError(f"Unexpected paired split selection: {selected}")
    cmd = [
        sys.executable,
        str(REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_pair_benchmarks.py"),
        "--benchmark",
        benchmark,
        "--models",
        args.models,
    ]
    append_common_pair_args(cmd, args)
    if args.dry_run:
        print("[benchmark_v2_open] paired command:")
        print(" ".join(cmd))
        return
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Paired split evaluation failed with exit code {completed.returncode}")


def selected_action_from_submission(submission: dict[str, Any]) -> tuple[str, str]:
    return str(submission.get("selected_action_id", "")), str(submission.get("selected_action_label", ""))


def enrich_real_world_row(
    row: dict[str, Any],
    *,
    model_key: str,
    model_metadata: dict[str, Any],
    record_dir: Path,
) -> dict[str, Any]:
    payload = dict(row)
    payload["benchmark_version"] = "benchmark_v2_open_real_world40"
    payload["benchmark"] = "real_world40"
    payload["split"] = "real_world40"
    payload["scenario"] = "real_world40"
    payload["model_key"] = model_key
    payload["model_metadata"] = model_metadata
    submission = payload.get("submission") or {}
    selected_id, selected_label = selected_action_from_submission(submission)
    payload.setdefault("selected_action_id", selected_id)
    payload.setdefault("selected_action_label", selected_label)
    payload["record_dir"] = display_path(record_dir)
    return payload


def summarize_real_world_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row.get("outcome", "unknown") for row in rows)
    by_misleader: dict[str, Counter[str]] = {}
    for row in rows:
        key = str(row.get("misleader_type") or "")
        by_misleader.setdefault(key, Counter())[row.get("outcome", "unknown")] += 1
    return {
        "task_count": len(rows),
        "success_count": counts.get("success", 0),
        "success_rate": counts.get("success", 0) / len(rows) if rows else 0.0,
        "outcome_counts": dict(counts),
        "by_misleader": {key: dict(counter) for key, counter in sorted(by_misleader.items())},
    }


def write_real_world_summary(path: Path, rows: list[dict[str, Any]], *, model_key: str, profile: str) -> None:
    summary = summarize_real_world_rows(rows)
    lines = [
        f"# {model_key} Real-World40 Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        "- Benchmark: `real_world40`",
        f"- Profile: `{profile}`",
        f"- Total tasks: `{summary['task_count']}`",
        f"- Success count: `{summary['success_count']}`",
        f"- Success rate: `{summary['success_rate']:.2%}`",
        f"- Outcome distribution: `{summary['outcome_counts']}`",
        "",
        "## By Misleader Type",
        "",
        "| Misleader Type | Outcomes |",
        "|---|---|",
    ]
    for key, counter in summary["by_misleader"].items():
        lines.append(f"| {key} | `{counter}` |")
    lines.extend(
        [
            "",
            "## Task-Level Results",
            "",
            "| Slug | Task ID | Outcome | Error Attribution | Selected Action |",
            "|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('slug','')} | {row.get('task_id','')} | {row.get('outcome','')} | "
            f"{row.get('error_attribution','')} | {row.get('selected_action_label','')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_real_world_readme(record_dir: Path, *, model_key: str, profile: str, args: argparse.Namespace) -> None:
    (record_dir / "README.md").write_text(
        f"# {model_key} Real-World40 Evaluation Record\n\n"
        "This directory contains a Benchmark v2 Open Real-World40 browser-agent run.\n\n"
        f"- Generated at: `{utc_now()}`\n"
        "- Benchmark: `real_world40`\n"
        f"- Profile: `{profile}`\n"
        f"- Tasks file: `{display_path(args.release_root / 'splits' / 'real_world40' / 'tasks.jsonl')}`\n"
        f"- Runs: `runs.jsonl`\n"
        f"- Summary: `summary.md`\n"
        f"- Failures: `failures.jsonl`\n"
        f"- Transient failures: `transient_failures.jsonl`\n"
        f"- Screenshots: `screenshots/<slug>/step_XX.png`\n",
        encoding="utf-8",
    )


def run_real_world_model(model_key: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    record_slug = record_slug_for(model_key, args)
    record_dir = args.record_root / record_slug / "real_world40"
    record_dir.mkdir(parents=True, exist_ok=True)
    for filename in ["runs.jsonl", "summary.md", "failures.jsonl", "transient_failures.jsonl", "run_config.json"]:
        path = record_dir / filename
        if path.exists():
            path.unlink()
    submissions = record_dir / "submissions" / "real_world40.jsonl"
    screenshots = record_dir / "screenshots"
    if submissions.exists():
        submissions.unlink()
    if screenshots.exists():
        import shutil

        shutil.rmtree(screenshots)

    tasks = args.real_world_tasks or (REAL_WORLD_DRYRUN_TASKS if args.profile == "dryrun" else REAL_WORLD_FULL_TASKS)
    model_metadata = model_metadata_for(model_key, args)
    mode = args.real_world_mode
    cmd = [
        sys.executable,
        str(REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_real_world40.py"),
        "--mode",
        mode,
        "--tasks",
        tasks,
        "--tasks-file",
        str(args.release_root / "splits" / "real_world40" / "tasks.jsonl"),
        "--base-url",
        f"http://127.0.0.1:{args.real_world_port + args.port_offset}",
        "--submissions",
        str(submissions),
        "--runs-out",
        str(record_dir / "runs.jsonl"),
        "--summary-out",
        str(record_dir / "summary.md"),
        "--failures-out",
        str(record_dir / "failures.jsonl"),
        "--screenshot-dir",
        str(screenshots),
        "--max-steps",
        str(args.max_steps),
        "--max-output-tokens",
        str(effective_max_output_tokens(model_key, args)),
        "--temperature",
        str(args.temperature),
        "--top-p",
        str(args.top_p),
        "--seed",
        str(args.seed),
        "--hide-form-dashboard-link",
    ]
    if args.extra_system_prompt:
        cmd.extend(["--extra-system-prompt", args.extra_system_prompt])
    if args.dry_run:
        print(f"[benchmark_v2_open] real_world40 command for {model_key}:")
        print(" ".join(cmd))
        return []

    env = os.environ.copy()
    env.update(effective_model_env(model_key, args))
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, text=True, capture_output=True)
    (record_dir / "stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (record_dir / "stderr.log").write_text(completed.stderr or "", encoding="utf-8")
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    rows = read_jsonl(record_dir / "runs.jsonl")
    if completed.returncode != 0 and not rows:
        raise RuntimeError(f"{model_key}/real_world40 failed before writing rows. See {record_dir / 'stderr.log'}")
    rows = [
        enrich_real_world_row(
            row,
            model_key=model_key,
            model_metadata=model_metadata,
            record_dir=record_dir,
        )
        for row in rows
    ]
    write_jsonl(record_dir / "runs.jsonl", rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    transient = [row for row in failures if pair_runner.is_transient_model_failure(row)]
    write_jsonl(record_dir / "failures.jsonl", failures)
    write_jsonl(record_dir / "transient_failures.jsonl", transient)
    write_real_world_summary(record_dir / "summary.md", rows, model_key=model_key, profile=args.profile)
    run_config = {
        "generated_at": utc_now(),
        "benchmark": "real_world40",
        "benchmark_version": "benchmark_v2_open_real_world40",
        "profile": args.profile,
        "model_key": model_key,
        "model_metadata": model_metadata,
        "max_steps": args.max_steps,
        "decoding_config": {"temperature": args.temperature, "top_p": args.top_p, "seed": args.seed},
        "tasks_file": display_path(args.release_root / "splits" / "real_world40" / "tasks.jsonl"),
        "tasks": tasks,
        "real_world_mode": mode,
        "extra_system_prompt": args.extra_system_prompt,
        "record_slug_suffix": args.record_slug_suffix,
    }
    (record_dir / "run_config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_real_world_readme(record_dir, model_key=model_key, profile=args.profile, args=args)
    print(f"[benchmark_v2_open] wrote {record_dir / 'runs.jsonl'}")
    return rows


def run_real_world_split(args: argparse.Namespace, splits: set[str]) -> None:
    if "real_world40" not in splits:
        return
    for model_key in pair_runner.model_choices(args.models):
        run_real_world_model(model_key, args)


def load_model_rows(record_root: Path, model_key: str, args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    record_slug = record_slug_for(model_key, args)
    base = record_root / record_slug
    return {
        "official": read_jsonl(base / "official" / "runs.jsonl"),
        "clean": read_jsonl(base / "clean" / "runs.jsonl"),
        "real_world40": read_jsonl(base / "real_world40" / "runs.jsonl"),
    }


def pair_category(official: dict[str, Any] | None, clean: dict[str, Any] | None) -> str:
    official_success = bool(official and official.get("outcome") == "success")
    clean_success = bool(clean and clean.get("outcome") == "success")
    if official_success and clean_success:
        return "official_success_clean_success"
    if (not official_success) and clean_success:
        return "official_misleading_clean_success"
    if official_success and not clean_success:
        return "clean_regression"
    return "both_failed"


def paired_counts(official_rows: list[dict[str, Any]], clean_rows: list[dict[str, Any]]) -> Counter[str]:
    official_by_slug = {str(row.get("slug")): row for row in official_rows}
    clean_by_slug = {str(row.get("slug")): row for row in clean_rows}
    counts: Counter[str] = Counter()
    for slug in sorted(set(official_by_slug) | set(clean_by_slug)):
        counts[pair_category(official_by_slug.get(slug), clean_by_slug.get(slug))] += 1
    return counts


def success_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("outcome") == "success")


def fmt_rate(success: int, total: int) -> str:
    return f"{success}/{total} ({(success / total if total else 0):.2%})"


def write_open_summary(args: argparse.Namespace) -> None:
    models = pair_runner.model_choices(args.models)
    summary_rows: list[dict[str, Any]] = []
    for model_key in models:
        rows_by_split = load_model_rows(args.record_root, model_key, args)
        official = rows_by_split["official"]
        clean = rows_by_split["clean"]
        real_world = rows_by_split["real_world40"]
        pair_counts = paired_counts(official, clean) if official or clean else Counter()
        summary_rows.append(
            {
                "model_key": model_key,
                "record_slug": record_slug_for(model_key, args),
                "official_tasks": len(official),
                "official_success": success_count(official),
                "clean_tasks": len(clean),
                "clean_success": success_count(clean),
                "real_world40_tasks": len(real_world),
                "real_world40_success": success_count(real_world),
                "pair_categories": dict(pair_counts),
                "agent_error_count": sum(
                    1
                    for row in official + clean + real_world
                    if row.get("outcome") == "agent_error"
                ),
            }
        )
    write_jsonl(args.record_root / "benchmark_v2_open_model_summary.jsonl", summary_rows)
    lines = [
        "# Benchmark v2 Open Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Release root: `{display_path(args.release_root)}`",
        f"- Record root: `{display_path(args.record_root)}`",
        f"- Models: `{', '.join(models)}`",
        "",
        "| Model | Official140 Success | Clean140 Success | Clean - Official | Official Misleading -> Clean Success | Clean Regression | Real-World40 Success | Agent Error Count |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        official_tasks = int(row["official_tasks"])
        clean_tasks = int(row["clean_tasks"])
        real_tasks = int(row["real_world40_tasks"])
        official_success = int(row["official_success"])
        clean_success = int(row["clean_success"])
        real_success = int(row["real_world40_success"])
        diff = (
            (clean_success / clean_tasks) - (official_success / official_tasks)
            if official_tasks and clean_tasks
            else 0.0
        )
        pair_counts = Counter(row["pair_categories"])
        lines.append(
            f"| {row['model_key']} | {fmt_rate(official_success, official_tasks)} | "
            f"{fmt_rate(clean_success, clean_tasks)} | {diff:+.2%} | "
            f"{pair_counts.get('official_misleading_clean_success', 0)} | "
            f"{pair_counts.get('clean_regression', 0)} | "
            f"{fmt_rate(real_success, real_tasks)} | {row['agent_error_count']} |"
        )
    (args.record_root / "benchmark_v2_open_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_release(args: argparse.Namespace) -> None:
    cmd = [sys.executable, str(args.release_root / "scripts" / "validate_release.py")]
    completed = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Release validation failed with exit code {completed.returncode}")


def run(args: argparse.Namespace) -> int:
    args.release_root = args.release_root.resolve()
    args.record_root = args.record_root or (
        RECORD_ROOT / f"benchmark_v2_open_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    args.record_root = args.record_root.resolve()
    splits = parse_splits(args.splits)
    if not args.skip_release_validation and not args.dry_run:
        validate_release(args)
    args.record_root.mkdir(parents=True, exist_ok=True)
    run_paired_splits(args, splits)
    run_real_world_split(args, splits)
    if not args.dry_run:
        write_open_summary(args)
        print(f"[benchmark_v2_open] wrote {args.record_root / 'benchmark_v2_open_summary.md'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, default=RELEASE_ROOT)
    parser.add_argument("--record-root", type=Path)
    parser.add_argument(
        "--splits",
        default="all",
        help="all, paired, official140, clean140, real_world40, or comma-separated aliases.",
    )
    parser.add_argument("--models", default="gpt54")
    parser.add_argument("--profile", choices=["dryrun", "full"], default="dryrun")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", dest="top_p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--model-max-output-tokens", type=int)
    parser.add_argument("--aime-max-retries", type=int)
    parser.add_argument("--aime-request-delay-sec", type=float)
    parser.add_argument("--aime-read-timeout-sec", type=float)
    parser.add_argument("--aime-extra-body-json")
    parser.add_argument("--aime-base-url")
    parser.add_argument("--aime-model")
    parser.add_argument("--aime-host-header")
    parser.add_argument("--aime-verify-ssl", choices=["true", "false"])
    parser.add_argument("--aime-api-style", choices=["chat_completions", "responses"])
    parser.add_argument("--experiment-variant")
    parser.add_argument("--thinking-budget-supported", choices=["true", "false", "unknown"])
    parser.add_argument("--scenarios")
    parser.add_argument("--task-overrides")
    parser.add_argument("--extra-system-prompt")
    parser.add_argument("--record-slug-suffix", default="")
    parser.add_argument("--port-offset", type=int, default=0)
    parser.add_argument("--real-world-port", type=int, default=REAL_WORLD_PORT)
    parser.add_argument("--real-world-tasks", help="Override Real-World40 tasks, e.g. rw001,rw040.")
    parser.add_argument(
        "--real-world-mode",
        choices=["mock_correct", "mock_misleading", "llm_agent"],
        default="llm_agent",
    )
    parser.add_argument("--skip-release-validation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
