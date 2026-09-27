#!/usr/bin/env python3
"""Evaluate CUGA Default vs CUGA Playbook on a frozen paired task set."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import socket
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CUGA_ROOT = REPO_ROOT / "external_tools" / "cuga-agent"
CUGA_SRC = CUGA_ROOT / "src"
EXPERIMENT_DIR = Path(__file__).resolve().parent / "cuga_policy_system"
DEFAULT_MANIFEST = EXPERIMENT_DIR / "miniset_16.jsonl"
DEFAULT_PLAYBOOK = EXPERIMENT_DIR / "chart_verification_playbook.md"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_miniset_20260710"
)
DEFAULT_CHROMIUM = Path("/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome")

SCENARIOS: dict[str, dict[str, Any]] = {
    "public39": {
        "module": "web_agent_benchmark.evaluation.run_public39",
        "tasks": "public39_tasks.jsonl",
        "ports": {"official": 47226, "clean": 47326},
    },
    "business47": {
        "module": "web_agent_benchmark.evaluation.run_business47",
        "tasks": "business47_tasks.jsonl",
        "ports": {"official": 47216, "clean": 47316},
    },
    "environment35": {
        "module": "web_agent_benchmark.evaluation.run_environment35",
        "tasks": "environment35_tasks.jsonl",
        "ports": {"official": 47233, "clean": 47333},
    },
    "health19": {
        "module": "web_agent_benchmark.evaluation.run_health19",
        "tasks": "health19_tasks.jsonl",
        "ports": {"official": 47237, "clean": 47337},
    },
}

BENCHMARK_DIRS = {
    "official": REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1",
    "clean": REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def task_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return str(row["condition"]), str(row["benchmark"]), str(row["scenario"]), str(row["slug"])


def configure_cuga(args: argparse.Namespace) -> None:
    if not CUGA_SRC.exists():
        raise RuntimeError(f"CUGA source is missing: {CUGA_SRC}")
    sys.path.insert(0, str(CUGA_SRC))
    os.environ.setdefault(
        "AGENT_SETTING_CONFIG",
        str(CUGA_ROOT / "src" / "cuga" / "configurations" / "models" / "settings.litellm.toml"),
    )
    os.environ["MODEL_NAME"] = args.model
    os.environ.setdefault("CUGA_DISABLE_SSL", "false")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


async def reset_policy(condition: str, policy_db: Path, playbook_path: Path) -> dict[str, Any]:
    from cuga.backend.cuga_graph.policy.configurable import PolicyConfigurable
    from cuga.backend.cuga_graph.policy.folder_loader import parse_markdown_with_frontmatter, create_playbook_from_markdown
    from cuga.backend.cuga_graph.policy.storage import PolicyStorage
    from cuga.backend.storage.policy import LocalPolicyStore

    async def keyword_only_embedding(_: str) -> list[float]:
        return [0.0] * 8

    backend = LocalPolicyStore(str(policy_db), "cuga_policies")
    storage = PolicyStorage(
        collection_name="cuga_policies",
        backend=backend,
        embedding_dim=8,
    )
    storage._embedding_function = keyword_only_embedding
    storage._embedding_initialized = True
    policy_system = PolicyConfigurable(storage=storage, embedding_function=keyword_only_embedding)
    PolicyConfigurable._instance = policy_system
    PolicyConfigurable._initialized = False
    await policy_system.initialize(embedding_dim=8)
    existing = await policy_system.storage.list_policies(enabled_only=False)
    for policy in existing:
        await policy_system.storage.delete_policy(policy.id)
    configured: list[str] = []
    if condition == "playbook":
        frontmatter, content = parse_markdown_with_frontmatter(str(playbook_path))
        policy = create_playbook_from_markdown(str(playbook_path), frontmatter, content)
        await policy_system.storage.add_policy(policy)
        configured.append(policy.id)
    await policy_system.initialize()
    return {"policy_system": policy_system, "configured_policy_ids": configured}


async def enact_policy_guidance(
    policy_system: Any,
    base_goal: str,
    thread_id: str,
) -> tuple[str, dict[str, Any]]:
    from cuga.backend.cuga_graph.policy.enactment import PolicyEnactment
    from cuga.backend.cuga_graph.policy.models import PolicyType

    config = {
        "configurable": {
            "policy_system": policy_system,
            "thread_id": thread_id,
        }
    }
    state = SimpleNamespace(goal=base_goal)
    command, metadata = await PolicyEnactment.check_and_enact(
        state,
        config,
        policy_types=[PolicyType.PLAYBOOK],
    )
    if command is not None:
        raise RuntimeError("A playbook unexpectedly returned a blocking policy command")
    metadata = metadata or {}
    guidance = str(metadata.get("playbook_guidance") or "").strip()
    record = {
        "matched": bool(metadata.get("policy_matched")),
        "policy_id": metadata.get("policy_id"),
        "policy_name": metadata.get("policy_name"),
        "policy_type": metadata.get("policy_type"),
        "policy_confidence": metadata.get("policy_confidence"),
        "policy_reasoning": metadata.get("policy_reasoning"),
        "guidance": guidance,
        "guidance_sha256": hashlib.sha256(guidance.encode("utf-8")).hexdigest() if guidance else None,
    }
    if not guidance:
        return base_goal, record
    enriched_goal = (
        f"{base_goal}\n\n"
        "CUGA policy-system guidance for this task:\n"
        f"{guidance}"
    )
    return enriched_goal, record


def find_task(benchmark: str, scenario: str, slug: str) -> dict[str, Any]:
    path = BENCHMARK_DIRS[benchmark] / SCENARIOS[scenario]["tasks"]
    slug_field = "official_slug"
    for row in read_jsonl(path):
        if str(row.get(slug_field)) == slug:
            return row
    raise KeyError(f"Task not found: {benchmark}/{scenario}/{slug}")


def new_submissions(path: Path, offset: int, task_id: str) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    return [row for row in rows[offset:] if str(row.get("task_id")) == task_id]


def serialize_steps(raw_steps: list[Any], run_dir: Path) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    image_dir = run_dir / "steps"
    for index, step in enumerate(raw_steps):
        data = step.model_dump(mode="json")
        image_uri = data.pop("image_before", "")
        if isinstance(image_uri, str) and image_uri.startswith("data:image/"):
            header, _, payload = image_uri.partition(",")
            image_bytes = base64.b64decode(payload)
            digest = hashlib.sha256(image_bytes).hexdigest()
            suffix = ".png" if "image/png" in header else ".jpg"
            image_path = image_dir / f"{index:03d}_{digest[:12]}{suffix}"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            if not image_path.exists():
                image_path.write_bytes(image_bytes)
            data["image_before_path"] = str(image_path.relative_to(REPO_ROOT))
            data["image_before_sha256"] = digest
        elif image_uri:
            data["image_before"] = image_uri
        serialized.append(data)
    return serialized


async def run_one(
    *,
    args: argparse.Namespace,
    condition: str,
    benchmark: str,
    selected: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    import importlib

    from cuga.backend.activity_tracker.tracker import ActivityTracker
    from cuga.backend.browser_env.browser.gym_env_async import BrowserEnvGymAsync
    from cuga.backend.browser_env.browser.open_ended_async import OpenEndedTaskAsync
    from cuga.backend.cuga_graph.utils.controller import AgentRunner
    from cuga.config import settings

    scenario = str(selected["scenario"])
    slug = str(selected["slug"])
    task = find_task(benchmark, scenario, slug)
    module = importlib.import_module(SCENARIOS[scenario]["module"])
    task_file = BENCHMARK_DIRS[benchmark] / SCENARIOS[scenario]["tasks"]
    run_dir = output_root / condition / benchmark / scenario / slug
    run_dir.mkdir(parents=True, exist_ok=True)
    submissions = output_root / condition / benchmark / "submissions" / f"{scenario}.jsonl"
    base_url = f"http://127.0.0.1:{reserve_local_port()}"
    offset = len(read_jsonl(submissions))
    base_goal = (
        f"Complete the current {scenario} benchmark task in the browser. "
        "Use the visible dashboard as evidence, choose the requested option in the form, and submit it."
    )
    policy_db = output_root / "policy_storage" / condition / "cuga_policies.db"
    policy_db.parent.mkdir(parents=True, exist_ok=True)
    thread_id = f"{condition}-{benchmark}-{scenario}-{slug}"
    goal = base_goal
    policy_setup: dict[str, Any] = {"configured_policy_ids": []}
    policy_enactment: dict[str, Any] = {"matched": False}
    server = None
    runner = None
    row: dict[str, Any]
    try:
        server = module.ensure_server(
            base_url,
            start_server=True,
            tasks_file=task_file,
            submissions_path=submissions,
        )
        policy_setup = await reset_policy(condition, policy_db, args.playbook)
        goal, policy_enactment = await enact_policy_guidance(
            policy_setup["policy_system"],
            base_goal,
            thread_id,
        )
        settings.advanced_features.mode = "web"
        settings.advanced_features.use_vision = True
        settings.advanced_features.lite_mode = False
        settings.evaluation.max_steps = args.max_steps
        tracker = ActivityTracker()
        tracker.reset(goal, task_id=f"{condition}_{benchmark}_{scenario}_{slug}")
        runner = AgentRunner(browser_enabled=True, thread_id=thread_id)
        runner.env = BrowserEnvGymAsync(
            OpenEndedTaskAsync,
            headless=not args.headed,
            interface_mode="browser_only",
            feedback=[],
            timeout=15000,
            viewport={"width": 1440, "height": 1100},
            pw_chromium_kwargs={"executable_path": str(args.chromium_executable)},
            task_kwargs={"start_url": f"{base_url}/task/{slug}", "goal": goal},
            tags_to_mark="all",
            enable_nocodeui_pu=False,
        )
        runner.obs, runner.info = await runner.env.reset()
        await runner.env.page.screenshot(path=str(run_dir / "start.png"), full_page=True)
        result = await asyncio.wait_for(
            runner.run_task_generic(eval_mode=False, goal=goal),
            timeout=args.task_timeout_sec,
        )
        await runner.env.page.screenshot(path=str(run_dir / "final.png"), full_page=True)
        submitted = new_submissions(submissions, offset, str(task.get("task_id")))
        submission = submitted[-1] if submitted else {}
        evaluation = submission.get("evaluation_hidden_from_agent", {})
        outcome = evaluation.get("outcome", "agent_timeout")
        error_attribution = evaluation.get("error_attribution", "no_submission")
        steps = serialize_steps(list(result.steps or []), run_dir)
        row = {
            "timestamp": utc_now(),
            "agent": "CUGA",
            "cuga_version": "0.3.0",
            "model": args.model,
            "condition": condition,
            "benchmark": benchmark,
            "base_url": base_url,
            "scenario": scenario,
            "slug": slug,
            "task_id": task.get("task_id"),
            "case_id": task.get("case_id"),
            "misleader_type": task.get("misleader_type"),
            "outcome": outcome,
            "error_attribution": error_attribution,
            "submission": submission,
            "cuga_answer": result.answer,
            "cuga_action_count": result.number_of_actions,
            "cuga_steps": steps,
            "configured_policy_ids": policy_setup["configured_policy_ids"],
            "policy_enactment": policy_enactment,
            "base_goal": base_goal,
            "agent_goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            "playbook_sha256": hashlib.sha256(args.playbook.read_bytes()).hexdigest(),
            "run_dir": display_path(run_dir),
        }
    except Exception as exc:
        row = {
            "timestamp": utc_now(),
            "agent": "CUGA",
            "cuga_version": "0.3.0",
            "model": args.model,
            "condition": condition,
            "benchmark": benchmark,
            "base_url": base_url,
            "scenario": scenario,
            "slug": slug,
            "task_id": task.get("task_id"),
            "case_id": task.get("case_id"),
            "misleader_type": task.get("misleader_type"),
            "outcome": "agent_error",
            "error_attribution": "cuga_runner_exception",
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
            "configured_policy_ids": policy_setup["configured_policy_ids"],
            "policy_enactment": policy_enactment,
            "base_goal": base_goal,
            "agent_goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            "playbook_sha256": hashlib.sha256(args.playbook.read_bytes()).hexdigest(),
            "run_dir": display_path(run_dir),
        }
    finally:
        if runner is not None and runner.env is not None:
            try:
                await runner.env.close()
            except Exception:
                pass
        if server is not None:
            server.stop()
    (run_dir / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def summarize(rows: list[dict[str, Any]], output_root: Path, manifest_rows: int) -> None:
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    by_key = {task_key(row): row for row in rows}
    for row in rows:
        grouped[(str(row["condition"]), str(row["benchmark"]))][str(row.get("outcome"))] += 1
    scope_label = "Full140" if manifest_rows == 140 else f"{manifest_rows}-case Set"
    lines = [
        f"# CUGA Policy-System {scope_label} Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Rows: `{len(rows)}`",
        "",
        "## Split Results",
        "",
        "| Condition | Split | N | Success | Success rate | Misleading failure | Agent error | Avg actions |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, benchmark in sorted(grouped):
        subset = [
            row
            for row in rows
            if row.get("condition") == condition and row.get("benchmark") == benchmark
        ]
        counts = grouped[(condition, benchmark)]
        n = len(subset)
        success = counts["success"]
        actions = [int(row.get("cuga_action_count") or 0) for row in subset]
        average_actions = sum(actions) / n if n else 0.0
        lines.append(
            f"| {condition} | {benchmark} | {n} | {success} | "
            f"{(100.0 * success / n if n else 0.0):.1f}% | {counts['misleading_failure']} | "
            f"{counts['agent_error']} | {average_actions:.2f} |"
        )

    lines.extend([
        "",
        "## Paired Robustness",
        "",
        "| Condition | Paired N | Official success | Clean success | Clean - official | Official misleading / clean success | Clean regression | Both failed |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    case_keys = {(str(row["scenario"]), str(row["slug"])) for row in rows}
    for condition in ("default", "playbook"):
        pairs = []
        for scenario, slug in sorted(case_keys):
            official = by_key.get((condition, "official", scenario, slug))
            clean = by_key.get((condition, "clean", scenario, slug))
            if official and clean:
                pairs.append((official, clean))
        n = len(pairs)
        official_success = sum(official.get("outcome") == "success" for official, _ in pairs)
        clean_success = sum(clean.get("outcome") == "success" for _, clean in pairs)
        directed = sum(
            official.get("outcome") == "misleading_failure" and clean.get("outcome") == "success"
            for official, clean in pairs
        )
        clean_regression = sum(
            official.get("outcome") == "success" and clean.get("outcome") != "success"
            for official, clean in pairs
        )
        both_failed = sum(
            official.get("outcome") != "success" and clean.get("outcome") != "success"
            for official, clean in pairs
        )
        official_rate = 100.0 * official_success / n if n else 0.0
        clean_rate = 100.0 * clean_success / n if n else 0.0
        lines.append(
            f"| {condition} | {n} | {official_success} ({official_rate:.1f}%) | "
            f"{clean_success} ({clean_rate:.1f}%) | {clean_rate - official_rate:+.1f} pp | "
            f"{directed} | {clean_regression} | {both_failed} |"
        )

    lines.extend(["", "## Policy Effects", ""])
    for benchmark in ("official", "clean"):
        eligible = recoveries = regressions = comparable = 0
        for scenario, slug in sorted(case_keys):
            default = by_key.get(("default", benchmark, scenario, slug))
            policy = by_key.get(("playbook", benchmark, scenario, slug))
            if not default or not policy:
                continue
            comparable += 1
            if default.get("outcome") != "success":
                eligible += 1
                recoveries += int(policy.get("outcome") == "success")
            regressions += int(default.get("outcome") == "success" and policy.get("outcome") != "success")
        lines.append(
            f"- `{benchmark}`: recoveries `{recoveries}/{eligible}`, regressions `{regressions}`, comparable `{comparable}`."
        )

    playbook_rows = [row for row in rows if row.get("condition") == "playbook"]
    matched = sum(bool(row.get("policy_enactment", {}).get("matched")) for row in playbook_rows)
    default_matches = sum(
        bool(row.get("policy_enactment", {}).get("matched"))
        for row in rows
        if row.get("condition") == "default"
    )
    lines.extend([
        "",
        "## Policy Audit",
        "",
        f"- Playbook matches: `{matched}/{len(playbook_rows)}`.",
        f"- Unexpected default-policy matches: `{default_matches}`.",
        "- Paired metrics include only cases with both clean and official rows for the same condition.",
    ])
    (output_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def async_main(args: argparse.Namespace) -> int:
    args.output_root = args.output_root.resolve()
    args.manifest = args.manifest.resolve()
    args.playbook = args.playbook.resolve()
    args.chromium_executable = args.chromium_executable.resolve()
    if args.seed_runs_from is not None:
        args.seed_runs_from = args.seed_runs_from.resolve()
    configure_cuga(args)
    manifest = read_jsonl(args.manifest)
    if args.limit:
        manifest = manifest[: args.limit]
    conditions = [item.strip() for item in args.conditions.split(",") if item.strip()]
    benchmarks = [item.strip() for item in args.benchmarks.split(",") if item.strip()]
    unknown_conditions = set(conditions) - {"default", "playbook"}
    unknown_benchmarks = set(benchmarks) - {"official", "clean"}
    if unknown_conditions or unknown_benchmarks:
        raise ValueError(f"Unknown conditions={unknown_conditions}, benchmarks={unknown_benchmarks}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    run_config = {
        "generated_at": utc_now(),
        "agent": "CUGA",
        "cuga_version": "0.3.0",
        "model": args.model,
        "conditions": conditions,
        "benchmarks": benchmarks,
        "manifest": str(args.manifest.relative_to(REPO_ROOT)),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "manifest_rows": len(manifest),
        "playbook": str(args.playbook.relative_to(REPO_ROOT)),
        "playbook_sha256": hashlib.sha256(args.playbook.read_bytes()).hexdigest(),
        "max_internal_graph_steps": args.max_steps,
        "task_timeout_sec": args.task_timeout_sec,
        "headless": not args.headed,
        "viewport": {"width": 1440, "height": 1100},
        "execution_order": "case-interleaved; condition and split order reversed on odd case indices",
        "seed_runs_from": (
            str(args.seed_runs_from.relative_to(REPO_ROOT))
            if args.seed_runs_from is not None and args.seed_runs_from.is_relative_to(REPO_ROOT)
            else str(args.seed_runs_from) if args.seed_runs_from is not None else None
        ),
        "seed_runs_sha256": (
            hashlib.sha256(args.seed_runs_from.read_bytes()).hexdigest()
            if args.seed_runs_from is not None
            else None
        ),
        "credentials_persisted": False,
    }
    (args.output_root / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    runs_path = args.output_root / "runs.jsonl"
    existing = read_jsonl(runs_path)
    if args.seed_runs_from is not None:
        if not args.seed_runs_from.exists():
            raise FileNotFoundError(f"Seed runs file does not exist: {args.seed_runs_from}")
        allowed_keys = {
            (condition, benchmark, str(selected["scenario"]), str(selected["slug"]))
            for selected in manifest
            for condition in conditions
            for benchmark in benchmarks
        }
        existing_by_key = {task_key(row): row for row in existing}
        imported = 0
        for seed_row in read_jsonl(args.seed_runs_from):
            key = task_key(seed_row)
            if key not in allowed_keys or key in existing_by_key:
                continue
            if seed_row.get("agent") != "CUGA" or seed_row.get("model") != args.model:
                raise ValueError(
                    f"Incompatible seed row for {'/'.join(key)}: "
                    f"agent={seed_row.get('agent')!r}, model={seed_row.get('model')!r}"
                )
            existing_by_key[key] = seed_row
            imported += 1
        existing = list(existing_by_key.values())
        write_jsonl(runs_path, existing)
        print(f"[cuga] imported {imported} checkpoint rows from {args.seed_runs_from}")
    completed = {task_key(row) for row in existing if row.get("outcome") != "agent_error"}
    rows = list(existing)
    summarize(rows, args.output_root, len(manifest))
    if args.prepare_only:
        print(
            f"[cuga] prepare-only complete: {len(rows)}/{len(manifest) * len(conditions) * len(benchmarks)} rows"
        )
        return 0
    for case_index, selected in enumerate(manifest):
        condition_order = conditions if case_index % 2 == 0 else list(reversed(conditions))
        benchmark_order = benchmarks if case_index % 2 == 0 else list(reversed(benchmarks))
        for condition in condition_order:
            for benchmark in benchmark_order:
                key = (condition, benchmark, str(selected["scenario"]), str(selected["slug"]))
                if key in completed and not args.force:
                    print(f"[cuga] skip completed: {'/'.join(key)}")
                    continue
                print(f"[cuga] run: {'/'.join(key)}")
                row = await run_one(
                    args=args,
                    condition=condition,
                    benchmark=benchmark,
                    selected=selected,
                    output_root=args.output_root,
                )
                rows = [old for old in rows if task_key(old) != key]
                rows.append(row)
                write_jsonl(runs_path, rows)
                write_jsonl(args.output_root / "failures.jsonl", [r for r in rows if r.get("outcome") != "success"])
                summarize(rows, args.output_root, len(manifest))
                print(f"[cuga] result: {row.get('outcome')} ({row.get('error_attribution')})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--conditions", default="default,playbook")
    parser.add_argument("--benchmarks", default="official,clean")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--chromium-executable", type=Path, default=DEFAULT_CHROMIUM)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=55,
        help="CUGA internal graph-step budget (browser actions are recorded separately).",
    )
    parser.add_argument("--task-timeout-sec", type=int, default=900)
    parser.add_argument(
        "--seed-runs-from",
        type=Path,
        help="Import compatible checkpoint rows before running missing tasks.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Import checkpoints and write metadata/summary without running tasks.",
    )
    args = parser.parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
