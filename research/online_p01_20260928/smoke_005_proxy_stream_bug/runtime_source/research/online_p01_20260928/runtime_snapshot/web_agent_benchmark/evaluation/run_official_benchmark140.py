#!/usr/bin/env python3
"""Run or aggregate the official 140-task benchmark across all four scenarios."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "web_agent_benchmark" / "evaluation"

SCENARIOS: dict[str, dict[str, Any]] = {
    "public39": {
        "scenario": "public39",
        "task_count": 39,
        "shell_port": 8026,
        "shell_app": REPO_ROOT / "web_agent_benchmark" / "public_benchmark" / "public_benchmark_shell_app.py",
        "runner": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_public39.py",
        "viewer_app": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "public39_trace_viewer_app.py",
        "viewer_port": 8027,
        "dryrun_tasks": "pub001,pub020,pub039",
        "full_tasks": "pub001-pub039",
        "official_runs": EVAL_DIR / "public39_gpt54_runs.jsonl",
        "official_summary": EVAL_DIR / "public39_gpt54_summary.md",
        "official_failures": EVAL_DIR / "public39_gpt54_failures.jsonl",
        "official_dryrun_runs": EVAL_DIR / "public39_gpt54_dryrun_runs.jsonl",
        "submissions": REPO_ROOT / "web_agent_benchmark" / "public_benchmark" / "submissions.jsonl",
    },
    "business47": {
        "scenario": "business47",
        "task_count": 47,
        "shell_port": 8016,
        "shell_app": REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_shell_app.py",
        "runner": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_business47.py",
        "viewer_app": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "trace_viewer_app.py",
        "viewer_port": 8017,
        "dryrun_tasks": "b001,b024,b047",
        "full_tasks": "b001-b047",
        "official_runs": EVAL_DIR / "business47_llm_full_runs.jsonl",
        "official_summary": EVAL_DIR / "business47_llm_full_summary.md",
        "official_failures": EVAL_DIR / "business47_llm_full_failures.jsonl",
        "official_dryrun_runs": EVAL_DIR / "business47_llm_dryrun_runs.jsonl",
        "submissions": REPO_ROOT / "web_agent_benchmark" / "business_shell" / "submissions.jsonl",
    },
    "environment35": {
        "scenario": "environment35",
        "task_count": 35,
        "shell_port": 8033,
        "shell_app": REPO_ROOT / "web_agent_benchmark" / "environment_energy_shell" / "environment_shell_app.py",
        "runner": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_environment35.py",
        "viewer_app": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "environment35_trace_viewer_app.py",
        "viewer_port": 8034,
        "dryrun_tasks": "env001,env017,env035",
        "full_tasks": "env001-env035",
        "official_runs": EVAL_DIR / "environment35_gpt54_runs.jsonl",
        "official_summary": EVAL_DIR / "environment35_gpt54_summary.md",
        "official_failures": EVAL_DIR / "environment35_gpt54_failures.jsonl",
        "official_dryrun_runs": EVAL_DIR / "environment35_gpt54_dryrun_runs.jsonl",
        "submissions": REPO_ROOT / "web_agent_benchmark" / "environment_energy_shell" / "submissions.jsonl",
    },
    "health19": {
        "scenario": "health19",
        "task_count": 19,
        "shell_port": 8037,
        "shell_app": REPO_ROOT / "web_agent_benchmark" / "health_shell" / "health_shell_app.py",
        "runner": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_health19.py",
        "viewer_app": REPO_ROOT / "web_agent_benchmark" / "evaluation" / "health19_trace_viewer_app.py",
        "viewer_port": 8038,
        "dryrun_tasks": "health001,health010,health019",
        "full_tasks": "health001-health019",
        "official_runs": EVAL_DIR / "health19_gpt54_runs.jsonl",
        "official_summary": EVAL_DIR / "health19_gpt54_summary.md",
        "official_failures": EVAL_DIR / "health19_gpt54_failures.jsonl",
        "official_dryrun_runs": EVAL_DIR / "health19_gpt54_dryrun_runs.jsonl",
        "submissions": REPO_ROOT / "web_agent_benchmark" / "health_shell" / "submissions.jsonl",
    },
}

DEFAULT_ORDER = ["public39", "business47", "environment35", "health19"]
QWEN_PYTHON = Path(
    "/mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python"
)
QWEN_MODEL_PATHS = {
    "8b": Path("/mnt/data/datasets/open_source_models/Qwen3-VL-8B-Instruct"),
    "32b": Path("/mnt/data/datasets/open_source_models/Qwen3-vl-32-instruct"),
}
QWEN_DEFAULT_PORTS = {"8b": 8045, "32b": 8046}
QWEN_CUDA_VISIBLE_DEVICES = "4,5,6"
LLAMA32_PYTHON = Path(
    "/mnt/data/code_generation/liyisheng/8H100conda/envs/internvl/bin/python"
)
LLAMA32_MODEL_PATHS = {
    "11b": Path("/mnt/data/datasets/open_source_models/llama3.2_vision_11B"),
    "90b": Path("/mnt/data/datasets/open_source_models/Llama-3.2-90B-Vision"),
}
LLAMA32_DEFAULT_PORTS = {"11b": 8047, "90b": 8048}
LLAMA32_CUDA_VISIBLE_DEVICES = "4,5,6"
KIMIK2_BASE_URL = "http://10.240.24.60:8000/v1/chat/completions"
KIMIK2_MODEL = "kimik26"


class QwenServerHandle:
    def __init__(self, process: subprocess.Popen[str] | None = None) -> None:
        self.process = process

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Llama32ServerHandle:
    def __init__(self, process: subprocess.Popen[str] | None = None) -> None:
        self.process = process

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def is_transient_model_failure(row: dict[str, Any]) -> bool:
    if row.get("outcome") == "success":
        return False
    haystack_parts = [
        str(row.get("exception", "")),
        str(row.get("error_attribution", "")),
        json.dumps(row.get("trace", []), ensure_ascii=False),
    ]
    haystack = " ".join(haystack_parts).lower()
    markers = [
        "kimi k2.6 request failed",
        "transient http",
        "http 429",
        "http 502",
        "http 503",
        "http 504",
        "connection error",
        "timed out",
        "empty response",
        "empty final content",
        "llm_action_generation_error",
    ]
    return any(marker in haystack for marker in markers)


def output_paths(mode: str, profile: str) -> tuple[Path, Path, Path]:
    mode_tag = "gpt54" if mode == "llm_agent" else mode
    prefix = f"official_benchmark140_{mode_tag}"
    if profile == "dryrun":
        prefix += "_dryrun"
    return (
        EVAL_DIR / f"{prefix}_runs.jsonl",
        EVAL_DIR / f"{prefix}_summary.md",
        EVAL_DIR / f"{prefix}_failures.jsonl",
    )


def decoding_config_from_args(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if args.temperature is not None:
        config["temperature"] = args.temperature
    if args.top_p is not None:
        config["top_p"] = args.top_p
    if args.seed is not None:
        config["seed"] = args.seed
    return config


def qwen_server_url(args: argparse.Namespace) -> str:
    if args.qwen_server_url:
        return args.qwen_server_url.rstrip("/")
    port = QWEN_DEFAULT_PORTS[args.qwen_model_size]
    return f"http://127.0.0.1:{port}"


def qwen_model_path(args: argparse.Namespace) -> Path:
    return args.qwen_model_path or QWEN_MODEL_PATHS[args.qwen_model_size]


def qwen_health_ok(server_url: str, *, model_path: Path | None = None) -> bool:
    import requests

    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{server_url.rstrip('/')}/health", timeout=2)
        if response.status_code != 200:
            return False
        data = response.json()
        if not data.get("ok"):
            return False
        if model_path and str(model_path) != data.get("model_path"):
            return False
        return True
    except Exception:
        return False


def llama32_server_url(args: argparse.Namespace) -> str:
    if args.llama32_server_url:
        return args.llama32_server_url.rstrip("/")
    port = LLAMA32_DEFAULT_PORTS[args.llama32_model_size]
    return f"http://127.0.0.1:{port}"


def llama32_model_path(args: argparse.Namespace) -> Path:
    return args.llama32_model_path or LLAMA32_MODEL_PATHS[args.llama32_model_size]


def llama32_health_ok(server_url: str, *, model_path: Path | None = None) -> bool:
    import requests

    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(f"{server_url.rstrip('/')}/health", timeout=2)
        if response.status_code != 200:
            return False
        data = response.json()
        if not data.get("ok"):
            return False
        if model_path and str(model_path) != data.get("model_path"):
            return False
        return True
    except Exception:
        return False


def ensure_llama32_server(args: argparse.Namespace) -> Llama32ServerHandle:
    if args.mode != "llm_agent" or args.agent_backend != "llama32_vision_http":
        return Llama32ServerHandle()
    model_path = llama32_model_path(args)
    server_url = llama32_server_url(args)
    if llama32_health_ok(server_url, model_path=model_path):
        print(f"[official_benchmark140] Reusing Llama-3.2 Vision server at {server_url}")
        return Llama32ServerHandle()
    if args.no_start_llama32_server:
        raise RuntimeError(f"Llama-3.2 Vision server is not reachable at {server_url}/health")
    if not LLAMA32_PYTHON.exists():
        raise RuntimeError(f"Llama-3.2 Vision Python does not exist: {LLAMA32_PYTHON}")
    if not model_path.exists():
        raise RuntimeError(f"Llama-3.2 Vision model path does not exist: {model_path}")

    port = int(server_url.rsplit(":", 1)[-1])
    log_dir = EVAL_DIR / "llama32_vision_server_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.llama32_model_size}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_fh = log_path.open("w", encoding="utf-8")
    cmd = [
        str(LLAMA32_PYTHON),
        str(EVAL_DIR / "llama32_vision_server.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model-path",
        str(model_path),
        "--model-size",
        args.llama32_model_size,
    ]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = args.llama32_cuda_visible_devices
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    print(
        f"[official_benchmark140] Starting Llama-3.2 Vision {args.llama32_model_size} "
        f"server at {server_url}"
    )
    print(f"[official_benchmark140] Llama server log: {log_path}")
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_fh.close()
    deadline = time.time() + args.llama32_start_timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Llama-3.2 Vision server exited with code {process.returncode}. "
                f"See log: {log_path}"
            )
        if llama32_health_ok(server_url, model_path=model_path):
            print(f"[official_benchmark140] Llama-3.2 Vision server ready: {server_url}")
            return Llama32ServerHandle(process)
        time.sleep(5)
    process.terminate()
    raise RuntimeError(
        f"Llama-3.2 Vision server did not become ready within "
        f"{args.llama32_start_timeout}s. Log: {log_path}"
    )


def ensure_qwen_server(args: argparse.Namespace) -> QwenServerHandle:
    if args.mode != "llm_agent" or args.agent_backend != "qwen3_vl_http":
        return QwenServerHandle()
    model_path = qwen_model_path(args)
    server_url = qwen_server_url(args)
    if qwen_health_ok(server_url, model_path=model_path):
        print(f"[official_benchmark140] Reusing Qwen3-VL server at {server_url}")
        return QwenServerHandle()
    if args.no_start_qwen_server:
        raise RuntimeError(f"Qwen3-VL server is not reachable at {server_url}/health")
    if not QWEN_PYTHON.exists():
        raise RuntimeError(f"Qwen Python does not exist: {QWEN_PYTHON}")
    if not model_path.exists():
        raise RuntimeError(f"Qwen model path does not exist: {model_path}")

    port = int(server_url.rsplit(":", 1)[-1])
    log_dir = EVAL_DIR / "qwen3_vl_server_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{args.qwen_model_size}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_fh = log_path.open("w", encoding="utf-8")
    cmd = [
        str(QWEN_PYTHON),
        str(EVAL_DIR / "qwen3_vl_server.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model-path",
        str(model_path),
        "--model-size",
        args.qwen_model_size,
        "--max-pixels",
        str(args.qwen_max_pixels),
    ]
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = args.qwen_cuda_visible_devices
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    print(f"[official_benchmark140] Starting Qwen3-VL {args.qwen_model_size} server at {server_url}")
    print(f"[official_benchmark140] Qwen server log: {log_path}")
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_fh.close()
    deadline = time.time() + args.qwen_start_timeout
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Qwen server exited with code {process.returncode}. See log: {log_path}"
            )
        if qwen_health_ok(server_url, model_path=model_path):
            print(f"[official_benchmark140] Qwen3-VL server ready: {server_url}")
            return QwenServerHandle(process)
        time.sleep(5)
    process.terminate()
    raise RuntimeError(f"Qwen server did not become ready within {args.qwen_start_timeout}s. Log: {log_path}")


def parse_scenarios(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_ORDER)
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in requested if item not in SCENARIOS]
    if unknown:
        raise RuntimeError(f"Unknown scenarios: {', '.join(unknown)}")
    return [name for name in DEFAULT_ORDER if name in requested]


def parse_task_overrides(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    overrides: dict[str, str] = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise RuntimeError(f"Invalid task override chunk: {chunk}")
        scenario_name, task_spec = chunk.split("=", 1)
        scenario_name = scenario_name.strip()
        task_spec = task_spec.strip()
        if scenario_name not in SCENARIOS:
            raise RuntimeError(f"Unknown task override scenario: {scenario_name}")
        if not task_spec:
            raise RuntimeError(f"Empty task override for {scenario_name}")
        overrides[scenario_name] = task_spec
    return overrides


def tasks_for(scenario_name: str, profile: str, overrides: dict[str, str] | None = None) -> str:
    if overrides and scenario_name in overrides:
        return overrides[scenario_name]
    meta = SCENARIOS[scenario_name]
    return meta["dryrun_tasks"] if profile == "dryrun" else meta["full_tasks"]


def expand_task_spec(task_spec: str) -> list[str]:
    slugs: list[str] = []
    for part in task_spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" not in part:
            slugs.append(part)
            continue
        start, end = part.split("-", 1)
        prefix = "".join(ch for ch in start if not ch.isdigit())
        start_i = int("".join(ch for ch in start if ch.isdigit()))
        end_i = int("".join(ch for ch in end if ch.isdigit()))
        for idx in range(start_i, end_i + 1):
            slugs.append(f"{prefix}{idx:03d}")
    return slugs


def aggregate_rows(
    scenario_name: str,
    rows: list[dict[str, Any]],
    *,
    source_runner: Path,
    source_runs_file: Path,
    model_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    aggregated: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["scenario"] = scenario_name
        payload["scenario_slug"] = scenario_name
        payload["source_runner"] = str(source_runner.relative_to(REPO_ROOT))
        payload["source_runs_file"] = str(source_runs_file.relative_to(REPO_ROOT))
        if model_metadata:
            payload.update(model_metadata)
        aggregated.append(payload)
    return aggregated


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    outcome_counts = Counter(row.get("outcome", "unknown") for row in rows)
    success_count = outcome_counts.get("success", 0)
    scenario_counts = Counter(row.get("scenario", "unknown") for row in rows)
    by_scenario: dict[str, dict[str, Any]] = {}
    for scenario_name in DEFAULT_ORDER:
        scenario_rows = [row for row in rows if row.get("scenario") == scenario_name]
        if not scenario_rows:
            continue
        counts = Counter(row.get("outcome", "unknown") for row in scenario_rows)
        task_count = len(scenario_rows)
        by_scenario[scenario_name] = {
            "task_count": task_count,
            "success_count": counts.get("success", 0),
            "misleading_failure_count": counts.get("misleading_failure", 0),
            "other_failure_count": task_count - counts.get("success", 0) - counts.get("misleading_failure", 0),
            "success_rate": (counts.get("success", 0) / task_count) if task_count else 0.0,
            "outcome_counts": dict(counts),
        }
    return {
        "task_count": len(rows),
        "success_count": success_count,
        "success_rate": (success_count / len(rows)) if rows else 0.0,
        "outcome_counts": dict(outcome_counts),
        "by_scenario": by_scenario,
    }


def write_summary(path: Path, rows: list[dict[str, Any]], *, mode: str, profile: str, scenarios: list[str]) -> None:
    summary = summarize_rows(rows)
    lines = [
        "# Official Benchmark 140 Evaluation Summary",
        "",
        f"- Generated at: `{utc_now()}`",
        f"- Mode: `{mode}`",
        f"- Profile: `{profile}`",
        f"- Scenarios: `{', '.join(scenarios)}`",
        f"- Total tasks: `{summary['task_count']}`",
        f"- Success count: `{summary['success_count']}`",
        f"- Success rate: `{summary['success_rate']:.2%}`",
        f"- Outcome distribution: `{summary['outcome_counts']}`",
        "",
        "## By Scenario",
        "",
        "| Scenario | Task Count | Success | Misleading Failure | Other Failures | Success Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scenario_name in scenarios:
        row = summary["by_scenario"].get(scenario_name)
        if not row:
            continue
        lines.append(
            f"| {scenario_name} | {row['task_count']} | {row['success_count']} | "
            f"{row['misleading_failure_count']} | {row['other_failure_count']} | {row['success_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Task-Level Results",
            "",
            "| Scenario | Slug | Task ID | Outcome | Error Attribution | Selected Action |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.get('scenario','')} | {row.get('slug','')} | {row.get('task_id','')} | "
            f"{row.get('outcome','')} | {row.get('error_attribution','')} | {row.get('selected_action_label','')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scenario(
    scenario_name: str,
    *,
    mode: str,
    profile: str,
    max_steps: int,
    max_output_tokens: int,
    headed: bool,
    start_server: bool,
    temp_root: Path,
    decoding_config: dict[str, Any],
    agent_backend: str,
    model_metadata: dict[str, Any],
    qwen_server_url_value: str | None,
    llama32_server_url_value: str | None,
    task_overrides: dict[str, str],
) -> list[dict[str, Any]]:
    meta = SCENARIOS[scenario_name]
    task_spec = tasks_for(scenario_name, profile, task_overrides)
    expected_slugs = expand_task_spec(task_spec)
    scenario_dir = temp_root / scenario_name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    runs_out = scenario_dir / "runs.jsonl"
    summary_out = scenario_dir / "summary.md"
    failures_out = scenario_dir / "failures.jsonl"
    cmd = [
        sys.executable,
        str(meta["runner"]),
        "--mode",
        mode,
        "--tasks",
        task_spec,
        "--base-url",
        f"http://127.0.0.1:{meta['shell_port']}",
        "--submissions",
        str(meta["submissions"]),
        "--runs-out",
        str(runs_out),
        "--summary-out",
        str(summary_out),
        "--failures-out",
        str(failures_out),
        "--max-steps",
        str(max_steps),
        "--max-output-tokens",
        str(max_output_tokens),
    ]
    if "temperature" in decoding_config:
        cmd.extend(["--temperature", str(decoding_config["temperature"])])
    if "top_p" in decoding_config:
        cmd.extend(["--top-p", str(decoding_config["top_p"])])
    if "seed" in decoding_config:
        cmd.extend(["--seed", str(decoding_config["seed"])])
    if headed:
        cmd.append("--headed")
    if not start_server:
        cmd.append("--no-start-server")
    env = os.environ.copy()
    if agent_backend == "qwen3_vl_http":
        env["LLM_BACKEND"] = "qwen3_vl_http"
        if qwen_server_url_value:
            env["QWEN3_VL_SERVER_URL"] = qwen_server_url_value
        if model_metadata.get("model_path"):
            env["QWEN3_VL_MODEL_PATH"] = str(model_metadata["model_path"])
        if model_metadata.get("agent_model_size"):
            env["QWEN3_VL_MODEL_SIZE"] = str(model_metadata["agent_model_size"])
        env["QWEN3_VL_MODEL"] = str(model_metadata.get("agent_model_name") or "qwen3_vl")
    elif agent_backend == "llama32_vision_http":
        env["LLM_BACKEND"] = "llama32_vision_http"
        if llama32_server_url_value:
            env["LLAMA32_VISION_SERVER_URL"] = llama32_server_url_value
        if model_metadata.get("model_path"):
            env["LLAMA32_VISION_MODEL_PATH"] = str(model_metadata["model_path"])
        if model_metadata.get("agent_model_size"):
            env["LLAMA32_VISION_MODEL_SIZE"] = str(model_metadata["agent_model_size"])
        env["LLAMA32_VISION_MODEL"] = str(
            model_metadata.get("agent_model_name") or "llama3_2_vision"
        )
    elif agent_backend == "kimik2_http":
        env["LLM_BACKEND"] = "kimik2_http"
        env["KIMIK2_BASE_URL"] = str(model_metadata.get("kimik2_base_url") or KIMIK2_BASE_URL)
        env["KIMIK2_MODEL"] = str(model_metadata.get("agent_model_id") or KIMIK2_MODEL)
        env["KIMIK2_ENABLE_THINKING"] = "true"
        env.setdefault("KIMIK2_MAX_RETRIES", "5")
        env.setdefault("KIMIK2_REQUEST_DELAY_SEC", "2")
        env.setdefault("KIMIK2_HTTP_READ_TIMEOUT_SEC", "900")
    else:
        env.setdefault("LLM_BACKEND", "hexin_openai")
        env.setdefault("HEXIN_MODEL", "gpt-5.4")
    completed = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    scenario_rows = read_jsonl(runs_out)
    existing_by_slug = {row.get("slug"): row for row in scenario_rows if row.get("slug")}
    missing_slugs = [slug for slug in expected_slugs if slug not in existing_by_slug]
    if completed.returncode != 0:
        for slug in missing_slugs:
            scenario_rows.append(
                {
                    "slug": slug,
                    "task_id": "",
                    "outcome": "agent_error",
                    "error_attribution": "scenario_runner_exception",
                    "submission": {},
                    "trace": [],
                    "exception": f"Scenario runner exited with code {completed.returncode}",
                }
            )
            if decoding_config:
                scenario_rows[-1]["decoding_config"] = decoding_config
            if model_metadata:
                scenario_rows[-1].update(model_metadata)
    elif missing_slugs:
        for slug in missing_slugs:
            scenario_rows.append(
                {
                    "slug": slug,
                    "task_id": "",
                    "outcome": "agent_error",
                    "error_attribution": "missing_scenario_row",
                    "submission": {},
                    "trace": [],
                    "exception": "Scenario runner completed without writing a row for this task.",
                }
            )
            if decoding_config:
                scenario_rows[-1]["decoding_config"] = decoding_config
            if model_metadata:
                scenario_rows[-1].update(model_metadata)
    if completed.returncode != 0 and not scenario_rows:
        raise RuntimeError(f"{scenario_name} runner failed before writing any rows.")
    return aggregate_rows(
        scenario_name,
        scenario_rows,
        source_runner=meta["runner"],
        source_runs_file=runs_out,
        model_metadata=model_metadata,
    )


def aggregate_existing_full_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario_name in DEFAULT_ORDER:
        meta = SCENARIOS[scenario_name]
        rows.extend(
            aggregate_rows(
                scenario_name,
                read_jsonl(meta["official_runs"]),
                source_runner=meta["runner"],
                source_runs_file=meta["official_runs"],
            )
        )
    return rows


def run(args: argparse.Namespace) -> int:
    scenarios = parse_scenarios(args.scenarios)
    task_overrides = parse_task_overrides(args.task_overrides)
    decoding_config = decoding_config_from_args(args)
    model_metadata: dict[str, Any] = {}
    qwen_server_url_value: str | None = None
    llama32_server_url_value: str | None = None
    if args.mode == "llm_agent" and args.agent_backend == "qwen3_vl_http":
        model_path = qwen_model_path(args)
        qwen_server_url_value = qwen_server_url(args)
        model_metadata = {
            "agent_backend": "qwen3_vl_http",
            "agent_model_family": "qwen3_vl",
            "agent_model_size": args.qwen_model_size,
            "agent_model_name": f"Qwen3-VL-{args.qwen_model_size.upper()}-Instruct",
            "model_path": str(model_path),
            "qwen_server_url": qwen_server_url_value,
            "generation_config": {
                "do_sample": False,
                **({"temperature": args.temperature} if args.temperature is not None else {}),
                **({"top_p": args.top_p} if args.top_p is not None else {}),
                **({"seed": args.seed} if args.seed is not None else {}),
            },
        }
    if args.mode == "llm_agent" and args.agent_backend == "llama32_vision_http":
        model_path = llama32_model_path(args)
        llama32_server_url_value = llama32_server_url(args)
        model_metadata = {
            "agent_backend": "llama32_vision_http",
            "agent_model_family": "llama3_2_vision",
            "agent_model_size": args.llama32_model_size,
            "agent_model_name": f"Llama-3.2-Vision-{args.llama32_model_size.upper()}",
            "model_path": str(model_path),
            "llama32_server_url": llama32_server_url_value,
            "generation_config": {
                "do_sample": False,
                **({"temperature": args.temperature} if args.temperature is not None else {}),
                **({"top_p": args.top_p} if args.top_p is not None else {}),
                **({"seed": args.seed} if args.seed is not None else {}),
            },
        }
    if args.mode == "llm_agent" and args.agent_backend == "kimik2_http":
        model_metadata = {
            "agent_backend": "kimik2_http",
            "agent_model_family": "kimik2",
            "agent_model_name": "Kimi-K2.6",
            "agent_model_id": KIMIK2_MODEL,
            "kimik2_base_url": KIMIK2_BASE_URL,
            "generation_config": {
                "thinking": True,
                **({"temperature": args.temperature} if args.temperature is not None else {}),
                **({"top_p": args.top_p} if args.top_p is not None else {}),
                **({"seed": args.seed} if args.seed is not None else {}),
            },
            "retry_config": {
                "max_retries": int(os.environ.get("KIMIK2_MAX_RETRIES", "5")),
                "request_delay_sec": float(os.environ.get("KIMIK2_REQUEST_DELAY_SEC", "2")),
                "read_timeout_sec": float(os.environ.get("KIMIK2_HTTP_READ_TIMEOUT_SEC", "900")),
                "trust_env_proxy": False,
            },
        }
    if args.record_dir:
        args.record_dir.mkdir(parents=True, exist_ok=True)
        runs_out = args.record_dir / "runs.jsonl"
        summary_out = args.record_dir / "summary.md"
        failures_out = args.record_dir / "failures.jsonl"
    else:
        runs_out, summary_out, failures_out = output_paths(args.mode, args.profile)
    temp_root = EVAL_DIR / "_official_benchmark140_tmp"
    if temp_root.exists():
        shutil.rmtree(temp_root)
    temp_root.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    qwen_server = ensure_qwen_server(args)
    llama32_server = ensure_llama32_server(args)
    try:
        for scenario_name in scenarios:
            print(
                f"[official_benchmark140] Running {scenario_name} "
                f"({tasks_for(scenario_name, args.profile, task_overrides)})"
            )
            rows.extend(
                run_scenario(
                    scenario_name,
                    mode=args.mode,
                    profile=args.profile,
                    max_steps=args.max_steps,
                    max_output_tokens=args.max_output_tokens,
                    headed=args.headed,
                    start_server=not args.no_start_server,
                    temp_root=temp_root,
                    decoding_config=decoding_config,
                    agent_backend=args.agent_backend,
                    model_metadata=model_metadata,
                    qwen_server_url_value=qwen_server_url_value,
                    llama32_server_url_value=llama32_server_url_value,
                    task_overrides=task_overrides,
                )
            )
    finally:
        qwen_server.stop()
        llama32_server.stop()
        if not args.keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)
    write_jsonl(runs_out, rows)
    failures = [row for row in rows if row.get("outcome") != "success"]
    write_jsonl(failures_out, failures)
    transient_failures = [row for row in failures if is_transient_model_failure(row)]
    transient_failures_out = failures_out.with_name(
        failures_out.stem.replace("_failures", "") + "_transient_failures.jsonl"
    )
    write_jsonl(transient_failures_out, transient_failures)
    write_summary(summary_out, rows, mode=args.mode, profile=args.profile, scenarios=scenarios)
    if args.record_dir:
        record_model_backend = args.agent_backend
        record_model = (
            model_metadata.get("agent_model_name")
            if model_metadata
            else os.environ.get("HEXIN_MODEL", "gpt-5.4")
        )
        config = {
            "generated_at": utc_now(),
            "mode": args.mode,
            "profile": args.profile,
            "scenarios": scenarios,
            "task_overrides": task_overrides,
            "model_backend": record_model_backend,
            "model": record_model,
            "decoding_config": decoding_config,
            "agent_backend": args.agent_backend,
            "model_metadata": model_metadata,
            "max_steps": args.max_steps,
            "max_output_tokens": args.max_output_tokens,
            "runs": str(runs_out),
            "summary": str(summary_out),
            "failures": str(failures_out),
            "transient_failures": str(transient_failures_out),
        }
        (args.record_dir / "run_config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        record_title = f"{record_model} Full-140 Evaluation Record"
        (args.record_dir / "README.md").write_text(
            f"# {record_title}\n\n"
            "This directory contains one official benchmark_v1 evaluation run.\n\n"
            f"- Mode: `{args.mode}`\n"
            f"- Profile: `{args.profile}`\n"
            f"- Scenarios: `{', '.join(scenarios)}`\n"
            f"- Task overrides: `{task_overrides}`\n"
            f"- Agent backend: `{args.agent_backend}`\n"
            f"- Model metadata: `{model_metadata}`\n"
            f"- Decoding config: `{decoding_config}`\n"
            f"- Runs: `runs.jsonl`\n"
            f"- Summary: `summary.md`\n"
            f"- Failures: `failures.jsonl`\n"
            f"- Transient failures: `{transient_failures_out.name}`\n",
            encoding="utf-8",
        )
    print(f"Wrote runs: {runs_out}")
    print(f"Wrote summary: {summary_out}")
    print(f"Wrote failures: {failures_out}")
    print(f"Wrote transient failures: {transient_failures_out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock_correct", "mock_misleading", "llm_agent"], required=True)
    parser.add_argument("--profile", choices=["dryrun", "full"], default="full")
    parser.add_argument(
        "--agent-backend",
        choices=["hexin_openai", "qwen3_vl_http", "llama32_vision_http", "kimik2_http"],
        default="hexin_openai",
    )
    parser.add_argument("--scenarios", help="Optional comma-separated subset, e.g. public39,health19")
    parser.add_argument(
        "--task-overrides",
        help="Optional semicolon-separated scenario task specs, e.g. public39=pub021,pub030;health19=health010",
    )
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-p", dest="top_p", type=float)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--record-dir", type=Path)
    parser.add_argument("--qwen-model-size", choices=["8b", "32b"], default="8b")
    parser.add_argument("--qwen-model-path", type=Path)
    parser.add_argument("--qwen-server-url")
    parser.add_argument("--qwen-cuda-visible-devices", default=QWEN_CUDA_VISIBLE_DEVICES)
    parser.add_argument("--qwen-max-pixels", type=int, default=1280 * 28 * 28)
    parser.add_argument("--qwen-start-timeout", type=int, default=1800)
    parser.add_argument("--no-start-qwen-server", action="store_true")
    parser.add_argument("--llama32-model-size", choices=["11b", "90b"], default="11b")
    parser.add_argument("--llama32-model-path", type=Path)
    parser.add_argument("--llama32-server-url")
    parser.add_argument("--llama32-cuda-visible-devices", default=LLAMA32_CUDA_VISIBLE_DEVICES)
    parser.add_argument("--llama32-start-timeout", type=int, default=3600)
    parser.add_argument("--no-start-llama32-server", action="store_true")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-start-server", action="store_true")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary per-scenario outputs.")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
