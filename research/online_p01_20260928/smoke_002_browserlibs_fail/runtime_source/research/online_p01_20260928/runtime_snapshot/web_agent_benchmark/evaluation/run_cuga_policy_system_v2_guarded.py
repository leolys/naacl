#!/usr/bin/env python3
"""Evaluate time-matched CUGA Default v2 vs Playbook v2 + PreSubmitGuard."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import sys
import time
import traceback
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALUATION_ROOT))

import run_cuga_policy_system_miniset as v1  # noqa: E402
from cuga_policy_system_v2_guard import (  # noqa: E402
    GUARD_SCHEMA_VERSION,
    GUARD_SYSTEM_PROMPT,
    GuardedPlaywrightToolImplProvider,
    VisibleEvidenceGuard,
)


EXPERIMENT_DIR = EVALUATION_ROOT / "cuga_policy_system"
DEFAULT_MANIFEST = EXPERIMENT_DIR / "v2_smoke_4.jsonl"
DEFAULT_PLAYBOOK = EXPERIMENT_DIR / "chart_verification_playbook_v2.md"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_v2_guarded_smoke_gpt54_20260711"
)
DEFAULT_CHROMIUM = Path("/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome")
DEFAULT_CONDITION = "default_v2_control"
POLICY_CONDITION = "playbook_v2_guarded"
FROZEN_PLAYBOOK_SHA256 = "06012867be220f82e344b09fd38a4cf2c044ce15103ac4cf5e6e4a6fbfe3d0ec"
PLAYBOOK_REVISION = "v2.2_candidate_scoped_completion"
REGISTRY_PORT = 48001
REGISTRY_URL = f"http://127.0.0.1:{REGISTRY_PORT}"
SHELL_PORTS = {
    "official": {
        "business47": 30116,
        "public39": 30126,
        "environment35": 30133,
        "health19": 30137,
    },
    "clean": {
        "business47": 30216,
        "public39": 30226,
        "environment35": 30233,
        "health19": 30237,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("condition")),
        str(row.get("benchmark")),
        str(row.get("scenario")),
        str(row.get("slug")),
    )


def row_has_guard_error(row: dict[str, Any]) -> bool:
    return bool((row.get("guard_summary") or {}).get("has_guard_error"))


def row_is_technical_failure(row: dict[str, Any]) -> bool:
    return row.get("outcome") == "agent_error" or row_has_guard_error(row)


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def wait_for_port_free(port: int, timeout_sec: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if port_is_free(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"shell port {port} did not become free within {timeout_sec:.1f}s")


def verify_registry() -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{REGISTRY_URL}/applications", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"registry returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"CUGA registry is not ready at {REGISTRY_URL}: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"CUGA registry returned an unexpected payload: {type(payload).__name__}")


def preflight_shell_ports() -> None:
    occupied = [
        port
        for benchmark_ports in SHELL_PORTS.values()
        for port in benchmark_ports.values()
        if not port_is_free(port)
    ]
    if occupied:
        raise RuntimeError(f"v2 shell ports are already occupied: {sorted(occupied)}")


def configure_cuga(args: argparse.Namespace) -> None:
    no_proxy_values = {
        value.strip()
        for name in ("NO_PROXY", "no_proxy")
        for value in os.environ.get(name, "").split(",")
        if value.strip()
    }
    no_proxy_values.update({"127.0.0.1", "localhost"})
    no_proxy = ",".join(sorted(no_proxy_values))
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy
    os.environ["DYNACONF_SERVER_PORTS__REGISTRY"] = str(REGISTRY_PORT)
    os.environ["DYNACONF_SERVER_PORTS__REGISTRY_HOST"] = REGISTRY_URL
    v1.configure_cuga(args)


async def configure_policy(
    condition: str,
    policy_db: Path,
    playbook_path: Path,
) -> dict[str, Any]:
    source_condition = "playbook" if condition == POLICY_CONDITION else "default"
    return await v1.reset_policy(source_condition, policy_db, playbook_path)


async def enact_policy_guidance_v2(
    policy_system: Any,
    base_goal: str,
    thread_id: str,
) -> tuple[str, dict[str, Any]]:
    """Use CUGA's type-specific matcher because its generic matcher omits AlwaysTrigger."""

    from cuga.backend.cuga_graph.policy.configurable import PolicyConfigurable
    from cuga.backend.cuga_graph.policy.enactment import PolicyEnactment
    from cuga.backend.cuga_graph.policy.models import PolicyType

    config = {
        "configurable": {
            "policy_system": policy_system,
            "thread_id": thread_id,
        }
    }
    state = SimpleNamespace(goal=base_goal)
    context = PolicyConfigurable.create_context_from_state(state, config)
    original_embedding = policy_system.agent.embedding_function
    policy_system.agent.embedding_function = None
    try:
        matches = await policy_system.match_policies_by_type(context, PolicyType.PLAYBOOK)
    finally:
        policy_system.agent.embedding_function = original_embedding
    if not matches:
        return base_goal, {
            "matched": False,
            "match_path": "cuga.match_policies_by_type",
        }
    policy_match = matches[0]
    command, metadata = await PolicyEnactment._enact_policy_action(
        state,
        policy_match,
        policy_system,
        context,
    )
    if command is not None:
        raise RuntimeError("A Playbook unexpectedly returned a blocking policy command")
    metadata = metadata or {}
    guidance = str(metadata.get("playbook_guidance") or "").strip()
    record = {
        "matched": bool(metadata.get("policy_matched")),
        "match_path": "cuga.match_policies_by_type",
        "policy_id": metadata.get("policy_id"),
        "policy_name": metadata.get("policy_name"),
        "policy_type": metadata.get("policy_type"),
        "policy_confidence": metadata.get("policy_confidence"),
        "policy_reasoning": metadata.get("policy_reasoning"),
        "guidance": guidance,
        "guidance_sha256": (
            hashlib.sha256(guidance.encode("utf-8")).hexdigest() if guidance else None
        ),
    }
    if not guidance:
        return base_goal, record
    return (
        f"{base_goal}\n\nCUGA policy-system guidance for this task:\n{guidance}",
        record,
    )


def summarize(rows: list[dict[str, Any]], output_root: Path, manifest_rows: int) -> None:
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    by_key = {task_key(row): row for row in rows}
    for row in rows:
        grouped[(str(row["condition"]), str(row["benchmark"]))][str(row.get("outcome"))] += 1

    lines = [
        "# CUGA Playbook v2 + Guard Experiment",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Manifest cases: `{manifest_rows}`",
        f"- Result rows: `{len(rows)}`",
        f"- Guard schema: `{GUARD_SCHEMA_VERSION}`",
        "- `official` is the internal identifier for the misleading-chart task version; `clean` is its non-misleading paired version.",
        "- Success and directed misleading-choice failure are mutually exclusive but not exhaustive outcomes. Other outcomes include irrelevant actions, incomplete workflows, timeouts, and agent errors.",
        "",
        "## Split Results",
        "",
        "| Condition | Task version | N | Correct completion | Correct completion rate | Directed misleading-choice failure | Agent error | Guard error | Timeout | Avg actions | Avg internal steps | Avg guard calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, benchmark in sorted(grouped):
        benchmark_label = (
            "Misleading-chart version" if benchmark == "official" else "Clean paired version"
        )
        subset = [
            row
            for row in rows
            if row.get("condition") == condition and row.get("benchmark") == benchmark
        ]
        counts = grouped[(condition, benchmark)]
        n = len(subset)
        success = counts["success"]
        actions = [int(row.get("cuga_action_count") or 0) for row in subset]
        internal_steps = [int(row.get("cuga_internal_step_count") or 0) for row in subset]
        guard_calls = [
            int((row.get("guard_summary") or {}).get("guard_call_count") or 0)
            for row in subset
        ]
        lines.append(
            f"| {condition} | {benchmark_label} | {n} | {success} | "
            f"{(100.0 * success / n if n else 0.0):.1f}% | {counts['misleading_failure']} | "
            f"{counts['agent_error']} | {sum(row_has_guard_error(row) for row in subset)} | "
            f"{counts['agent_timeout']} | {(sum(actions) / n if n else 0.0):.2f} | "
            f"{(sum(internal_steps) / n if n else 0.0):.2f} | "
            f"{(sum(guard_calls) / n if n else 0.0):.2f} |"
        )

    case_keys = {(str(row["scenario"]), str(row["slug"])) for row in rows}
    lines.extend(
        [
            "",
            "## Paired Robustness",
            "",
            "| Condition | Paired N | Misleading-chart task success | Clean-task success | Clean minus misleading-chart success | Paired directed vulnerability (clean success, misleading-chart directed failure) | Clean-task regression | Both failed |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for condition in (DEFAULT_CONDITION, POLICY_CONDITION):
        pairs = []
        for scenario, slug in sorted(case_keys):
            official = by_key.get((condition, "official", scenario, slug))
            clean = by_key.get((condition, "clean", scenario, slug))
            if official and clean:
                pairs.append((official, clean))
        n = len(pairs)
        official_success = sum(a.get("outcome") == "success" for a, _ in pairs)
        clean_success = sum(b.get("outcome") == "success" for _, b in pairs)
        directed = sum(
            a.get("outcome") == "misleading_failure" and b.get("outcome") == "success"
            for a, b in pairs
        )
        clean_regression = sum(
            a.get("outcome") == "success" and b.get("outcome") != "success"
            for a, b in pairs
        )
        both_failed = sum(
            a.get("outcome") != "success" and b.get("outcome") != "success"
            for a, b in pairs
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
        benchmark_label = (
            "Misleading-chart version" if benchmark == "official" else "Clean paired version"
        )
        recoveries = regressions = comparable = 0
        for scenario, slug in sorted(case_keys):
            default = by_key.get((DEFAULT_CONDITION, benchmark, scenario, slug))
            policy = by_key.get((POLICY_CONDITION, benchmark, scenario, slug))
            if not default or not policy:
                continue
            comparable += 1
            recoveries += int(
                default.get("outcome") != "success" and policy.get("outcome") == "success"
            )
            regressions += int(
                default.get("outcome") == "success" and policy.get("outcome") != "success"
            )
        lines.append(
            f"- {benchmark_label}: recoveries `{recoveries}`, regressions `{regressions}`, "
            f"comparable `{comparable}`."
        )

    policy_rows = [row for row in rows if row.get("condition") == POLICY_CONDITION]
    default_rows = [row for row in rows if row.get("condition") == DEFAULT_CONDITION]
    lines.extend(
        [
            "",
            "## Policy And Guard Audit",
            "",
            f"- Intended v2 Playbook matches: `{sum(bool((row.get('policy_enactment') or {}).get('matched')) for row in policy_rows)}/{len(policy_rows)}`.",
            f"- Unexpected Default matches: `{sum(bool((row.get('policy_enactment') or {}).get('matched')) for row in default_rows)}/{len(default_rows)}`.",
            f"- Guard calls: `{sum(int((row.get('guard_summary') or {}).get('guard_call_count') or 0) for row in policy_rows)}`.",
            f"- Guard blocks: `{sum(int((row.get('guard_summary') or {}).get('guard_block_count') or 0) for row in policy_rows)}`.",
            f"- Guard unresolved: `{sum(int((row.get('guard_summary') or {}).get('guard_unresolved_count') or 0) for row in policy_rows)}`.",
            f"- Guard errors: `{sum(row_has_guard_error(row) for row in policy_rows)}`.",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_compatible_output(args: argparse.Namespace, run_config: dict[str, Any]) -> None:
    config_path = args.output_root / "run_config.json"
    if config_path.exists():
        existing = json.loads(config_path.read_text(encoding="utf-8"))
        fields = (
            "model",
            "conditions",
            "benchmarks",
            "manifest_sha256",
            "playbook_sha256",
            "guard_schema_version",
            "shell_ports",
            "registry_url",
        )
        mismatches = [field for field in fields if existing.get(field) != run_config.get(field)]
        if mismatches:
            raise RuntimeError(f"output directory has incompatible run_config fields: {mismatches}")
        return
    allowed_preexisting = {"run.log", "registry.log", "supervisor_status.json"}
    unexpected = [path.name for path in args.output_root.iterdir() if path.name not in allowed_preexisting]
    if unexpected:
        raise RuntimeError(
            f"refusing to use non-empty output directory without compatible run_config: {unexpected}"
        )
    config_path.write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def run_one(
    *,
    args: argparse.Namespace,
    condition: str,
    benchmark: str,
    selected: dict[str, Any],
) -> dict[str, Any]:
    import importlib

    from cuga.backend.activity_tracker.tracker import ActivityTracker
    from cuga.backend.browser_env.browser.gym_env_async import BrowserEnvGymAsync
    from cuga.backend.browser_env.browser.open_ended_async import OpenEndedTaskAsync
    from cuga.backend.cuga_graph.utils.controller import AgentRunner
    from cuga.config import settings

    scenario = str(selected["scenario"])
    slug = str(selected["slug"])
    task = v1.find_task(benchmark, scenario, slug)
    module = importlib.import_module(v1.SCENARIOS[scenario]["module"])
    task_file = v1.BENCHMARK_DIRS[benchmark] / v1.SCENARIOS[scenario]["tasks"]
    run_dir = args.output_root / condition / benchmark / scenario / slug
    run_dir.mkdir(parents=True, exist_ok=True)
    submissions = args.output_root / condition / benchmark / "submissions" / f"{scenario}.jsonl"
    port = SHELL_PORTS[benchmark][scenario]
    wait_for_port_free(port)
    base_url = f"http://127.0.0.1:{port}"
    offset = len(v1.read_jsonl(submissions))
    base_goal = (
        f"Complete the current {scenario} benchmark task in the browser. "
        "Use the visible dashboard as evidence, choose the requested option in the form, and submit it."
    )
    policy_db = args.output_root / "policy_storage" / condition / "cuga_policies.db"
    policy_db.parent.mkdir(parents=True, exist_ok=True)
    thread_id = f"v2-{condition}-{benchmark}-{scenario}-{slug}"
    goal = base_goal
    policy_setup: dict[str, Any] = {"configured_policy_ids": []}
    policy_enactment: dict[str, Any] = {"matched": False}
    guard: VisibleEvidenceGuard | None = None
    server = None
    runner = None
    row: dict[str, Any]
    started = time.monotonic()
    try:
        server = module.ensure_server(
            base_url,
            start_server=True,
            tasks_file=task_file,
            submissions_path=submissions,
        )
        policy_setup = await configure_policy(condition, policy_db, args.playbook)
        goal, policy_enactment = await enact_policy_guidance_v2(
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
        provider = None
        if condition == POLICY_CONDITION:
            guard = VisibleEvidenceGuard(
                run_dir=run_dir,
                repo_root=REPO_ROOT,
                model=args.model,
            )
            provider = GuardedPlaywrightToolImplProvider(guard)
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
            tool_implementation_provider=provider,
        )
        runner.obs, runner.info = await runner.env.reset()
        await runner.env.page.screenshot(path=str(run_dir / "start.png"), full_page=True)
        result = await asyncio.wait_for(
            runner.run_task_generic(eval_mode=False, goal=goal),
            timeout=args.task_timeout_sec,
        )
        await runner.env.page.screenshot(path=str(run_dir / "final.png"), full_page=True)
        submitted = v1.new_submissions(submissions, offset, str(task.get("task_id")))
        submission = submitted[-1] if submitted else {}
        evaluation = submission.get("evaluation_hidden_from_agent", {})
        if evaluation:
            outcome = evaluation.get("outcome", "completion_failure")
            error_attribution = evaluation.get("error_attribution", "no_final_submission")
        elif str(result.answer or "").strip():
            outcome = "completion_failure"
            error_attribution = "no_final_submission"
        else:
            outcome = "agent_timeout"
            error_attribution = "internal_step_limit_without_final_answer"
        steps = v1.serialize_steps(list(result.steps or []), run_dir)
        row = {
            "timestamp": utc_now(),
            "agent": "CUGA",
            "cuga_version": "0.3.0",
            "experiment_version": "policy_playbook_v2_guarded",
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
            "cuga_internal_step_count": len(steps),
            "cuga_steps": steps,
            "configured_policy_ids": policy_setup["configured_policy_ids"],
            "policy_enactment": policy_enactment,
            "base_goal": base_goal,
            "agent_goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            "playbook_sha256": sha256_path(args.playbook),
            "guard_events": guard.events if guard is not None else [],
            "guard_summary": guard.summary() if guard is not None else {"enabled": False},
            "elapsed_sec": round(time.monotonic() - started, 3),
            "run_dir": v1.display_path(run_dir),
        }
    except Exception as exc:
        timed_out = isinstance(exc, asyncio.TimeoutError)
        row = {
            "timestamp": utc_now(),
            "agent": "CUGA",
            "cuga_version": "0.3.0",
            "experiment_version": "policy_playbook_v2_guarded",
            "model": args.model,
            "condition": condition,
            "benchmark": benchmark,
            "base_url": base_url,
            "scenario": scenario,
            "slug": slug,
            "task_id": task.get("task_id"),
            "case_id": task.get("case_id"),
            "misleader_type": task.get("misleader_type"),
            "outcome": "agent_timeout" if timed_out else "agent_error",
            "error_attribution": (
                "task_wall_clock_timeout" if timed_out else "cuga_v2_runner_exception"
            ),
            "exception": repr(exc),
            "traceback": traceback.format_exc(),
            "configured_policy_ids": policy_setup["configured_policy_ids"],
            "policy_enactment": policy_enactment,
            "base_goal": base_goal,
            "agent_goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
            "playbook_sha256": sha256_path(args.playbook),
            "guard_events": guard.events if guard is not None else [],
            "guard_summary": guard.summary() if guard is not None else {"enabled": False},
            "elapsed_sec": round(time.monotonic() - started, 3),
            "run_dir": v1.display_path(run_dir),
        }
    finally:
        if runner is not None and runner.env is not None:
            try:
                await runner.env.close()
            except Exception:
                pass
        if server is not None:
            server.stop()
            wait_for_port_free(port)
    (run_dir / "result.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return row


async def async_main(args: argparse.Namespace) -> int:
    args.output_root = args.output_root.resolve()
    args.manifest = args.manifest.resolve()
    args.playbook = args.playbook.resolve()
    args.chromium_executable = args.chromium_executable.resolve()
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_BASE_URL"):
        raise RuntimeError("OPENAI_API_KEY and OPENAI_BASE_URL must be set")
    if sha256_path(args.playbook) != FROZEN_PLAYBOOK_SHA256:
        raise RuntimeError(
            "frozen Playbook v2 hash mismatch: "
            f"expected {FROZEN_PLAYBOOK_SHA256}, got {sha256_path(args.playbook)}"
        )
    if not args.chromium_executable.exists():
        raise FileNotFoundError(f"Chromium executable is missing: {args.chromium_executable}")

    conditions = [item.strip() for item in args.conditions.split(",") if item.strip()]
    benchmarks = [item.strip() for item in args.benchmarks.split(",") if item.strip()]
    unknown_conditions = set(conditions) - {DEFAULT_CONDITION, POLICY_CONDITION}
    unknown_benchmarks = set(benchmarks) - {"official", "clean"}
    if unknown_conditions or unknown_benchmarks:
        raise ValueError(f"unknown conditions={unknown_conditions}, benchmarks={unknown_benchmarks}")
    manifest = v1.read_jsonl(args.manifest)
    if args.limit:
        manifest = manifest[: args.limit]
    for selected in manifest:
        if selected.get("scenario") not in SHELL_PORTS["official"]:
            raise ValueError(f"unknown scenario in manifest: {selected.get('scenario')}")

    configure_cuga(args)
    verify_registry()
    preflight_shell_ports()
    args.output_root.mkdir(parents=True, exist_ok=True)
    run_config = {
        "generated_at": utc_now(),
        "agent": "CUGA",
        "cuga_version": "0.3.0",
        "experiment_version": "policy_playbook_v2_guarded",
        "model": args.model,
        "conditions": conditions,
        "benchmarks": benchmarks,
        "manifest": v1.display_path(args.manifest),
        "manifest_sha256": sha256_path(args.manifest),
        "manifest_rows": len(manifest),
        "playbook": v1.display_path(args.playbook),
        "playbook_revision": PLAYBOOK_REVISION,
        "playbook_sha256": sha256_path(args.playbook),
        "frozen_playbook_sha256": FROZEN_PLAYBOOK_SHA256,
        "guard_schema_version": GUARD_SCHEMA_VERSION,
        "guard_system_prompt_sha256": hashlib.sha256(
            GUARD_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "guard_model": args.model,
        "guard_max_logical_calls_per_task": 2,
        "guard_retry_per_logical_call": 1,
        "guard_approval_confidence": 0.75,
        "guard_hidden_fields_allowed": False,
        "registry_url": REGISTRY_URL,
        "shell_ports": SHELL_PORTS,
        "max_internal_graph_steps": args.max_steps,
        "task_timeout_sec": args.task_timeout_sec,
        "headless": not args.headed,
        "viewport": {"width": 1440, "height": 1100},
        "execution_order": (
            "case-interleaved; condition and split order reversed on odd case indices"
        ),
        "credentials_persisted": False,
        "post_hoc_refinement_disclosure": (
            "Playbook v2 and Guard were designed after inspecting v1 aggregate and transition results."
        ),
    }
    ensure_compatible_output(args, run_config)
    runs_path = args.output_root / "runs.jsonl"
    rows = v1.read_jsonl(runs_path)
    completed = {task_key(row) for row in rows if not row_is_technical_failure(row)}
    summarize(rows, args.output_root, len(manifest))
    for case_index, selected in enumerate(manifest):
        condition_order = conditions if case_index % 2 == 0 else list(reversed(conditions))
        benchmark_order = benchmarks if case_index % 2 == 0 else list(reversed(benchmarks))
        for condition in condition_order:
            for benchmark in benchmark_order:
                key = (condition, benchmark, str(selected["scenario"]), str(selected["slug"]))
                if key in completed and not args.force:
                    print(f"[cuga-v2] skip completed: {'/'.join(key)}", flush=True)
                    continue
                print(f"[cuga-v2] run: {'/'.join(key)}", flush=True)
                row = await run_one(
                    args=args,
                    condition=condition,
                    benchmark=benchmark,
                    selected=selected,
                )
                rows = [old for old in rows if task_key(old) != key]
                rows.append(row)
                v1.write_jsonl(runs_path, rows)
                v1.write_jsonl(
                    args.output_root / "failures.jsonl",
                    [
                        item
                        for item in rows
                        if item.get("outcome") != "success" or row_has_guard_error(item)
                    ],
                )
                v1.write_jsonl(
                    args.output_root / "transient_failures.jsonl",
                    [item for item in rows if row_is_technical_failure(item)],
                )
                summarize(rows, args.output_root, len(manifest))
                print(
                    f"[cuga-v2] result: {row.get('outcome')} "
                    f"guard={row.get('guard_summary', {}).get('guard_final_state')}",
                    flush=True,
                )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--conditions", default=f"{DEFAULT_CONDITION},{POLICY_CONDITION}"
    )
    parser.add_argument("--benchmarks", default="official,clean")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument("--chromium-executable", type=Path, default=DEFAULT_CHROMIUM)
    parser.add_argument("--max-steps", type=int, default=55)
    parser.add_argument("--task-timeout-sec", type=int, default=600)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--force", action="store_true")
    return asyncio.run(async_main(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
