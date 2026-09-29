#!/usr/bin/env python3
"""Poll Claude Opus 4.6 route health and repair remaining official agent errors."""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import http.client
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import monitor_opus46_official_full_repair as merge_utils


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_RUNNER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_claude_opus46_uuid_checkpoint.py"
DEFAULT_MODEL_KEY = "claude_opus_4_6_aime_responses"
DEFAULT_MODEL_SLUG = "claude_opus_4_6_aime_responses_temp0_top_p1_seed12345"
DEFAULT_BASE_OFFICIAL_DIR = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "claude_opus_4_6_aime_responses_official_full140_20260521"
    / DEFAULT_MODEL_SLUG
    / "official"
)
DEFAULT_REPAIR_BATCH_ROOT = (
    REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_opus_4_6_aime_responses_official_repair_batches_20260521"
)
DEFAULT_REPAIR_OUTPUT_ROOT = (
    REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_opus_4_6_aime_responses_official_repair_checkpoint_20260521"
)
DEFAULT_MERGED_OFFICIAL_DIR = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "claude_opus_4_6_aime_responses_official_full140_20260521_agent_error_repaired"
    / DEFAULT_MODEL_SLUG
    / "official"
)
DEFAULT_TARGETS_PATH = (
    REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_opus_4_6_aime_responses_official_repair_targets_20260521.jsonl"
)
DEFAULT_LOG = (
    REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_opus_4_6_aime_responses_official_full140_20260521_logs" / "watch_opus46_repair.log"
)
DEFAULT_RUN_LOG = (
    REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_opus_4_6_aime_responses_official_full140_20260521_logs" / "watch_opus46_repair_runs.log"
)


class TunnelHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, connect_host: str, connect_port: int, timeout: float) -> None:
        super().__init__(host, port=443, timeout=timeout, context=ssl._create_unverified_context())
        self._connect_host = connect_host
        self._connect_port = connect_port

    def connect(self) -> None:
        raw = socket.create_connection((self._connect_host, self._connect_port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str, path: Path) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return merge_utils.read_jsonl(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    merge_utils.write_jsonl(path, rows)


def api_keys_from_env() -> list[str]:
    values: list[str] = []
    for name in ["AIME_LITELLM_API_KEY", "AIME_LITELLM_API_KEYS"]:
        raw = os.environ.get(name, "")
        values.extend(item.strip() for item in raw.split(",") if item.strip())
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def request(
    *,
    api_key: str,
    endpoint: str,
    payload: dict[str, Any],
    host: str,
    tunnel_host: str,
    tunnel_port: int,
    timeout_sec: float,
) -> tuple[int | None, str]:
    conn = TunnelHTTPSConnection(host, connect_host=tunnel_host, connect_port=tunnel_port, timeout=timeout_sec)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        conn.request("POST", endpoint, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", errors="replace")
        return resp.status, data
    finally:
        conn.close()


def preflight(args: argparse.Namespace, api_keys: list[str]) -> tuple[str, str] | None:
    checks = [
        (
            "responses",
            f"{args.aime_path_prefix}/responses",
            {"model": args.aime_model, "input": "只回答 OK", "max_output_tokens": 32},
        ),
        (
            "chat_completions",
            f"{args.aime_path_prefix}/chat/completions",
            {"model": args.aime_model, "messages": [{"role": "user", "content": "只回答 OK"}], "max_tokens": 32},
        ),
    ]
    for key_index, api_key in enumerate(api_keys, start=1):
        for style, endpoint, payload in checks:
            try:
                status, body = request(
                    api_key=api_key,
                    endpoint=endpoint,
                    payload=payload,
                    host=args.aime_host,
                    tunnel_host=args.tunnel_host,
                    tunnel_port=args.tunnel_port,
                    timeout_sec=args.preflight_timeout_sec,
                )
            except Exception as exc:  # noqa: BLE001 - log and continue polling.
                log(f"preflight key#{key_index} style={style} exception={exc!r}", args.log_path)
                continue
            snippet = body.replace("\n", " ")[:500]
            log(f"preflight key#{key_index} style={style} status={status} body={snippet}", args.log_path)
            if status == 200:
                return api_key, style
    return None


def remaining_targets(args: argparse.Namespace, expected: list[tuple[str, str]]) -> list[dict[str, Any]]:
    base_rows = merge_utils.read_rows_from_run_dir(args.base_official_dir)
    repair_rows = merge_utils.read_rows_from_run_dir(args.repair_output_root / args.model_slug / "official")
    return merge_utils.remaining_agent_error_targets(expected=expected, base_rows=base_rows, repair_rows=repair_rows)


def merge_current(args: argparse.Namespace, expected: list[tuple[str, str]]) -> Counter[str]:
    base_rows = merge_utils.read_rows_from_run_dir(args.base_official_dir)
    repair_rows = merge_utils.read_rows_from_run_dir(args.repair_output_root / args.model_slug / "official")
    merge_utils.merge_rows(
        expected=expected,
        base_rows=base_rows,
        repair_rows=repair_rows,
        output_dir=args.merged_official_dir,
        model_slug=args.model_slug,
    )
    merged = read_jsonl(args.merged_official_dir / "runs.jsonl")
    return Counter(str(row.get("outcome")) for row in merged)


def run_checkpoint(args: argparse.Namespace, *, api_key: str, api_style: str) -> int:
    cmd = [
        sys.executable,
        str(CHECKPOINT_RUNNER),
        "--benchmark",
        "official",
        "--model-key",
        args.model_key,
        "--model-slug",
        args.model_slug,
        "--batch-root",
        str(args.repair_batch_root),
        "--output-root",
        str(args.repair_output_root),
        "--targets-file",
        str(args.targets_path),
        "--cooldown-sec",
        str(args.repair_cooldown_sec),
        "--retry-passes",
        str(args.repair_retry_passes),
        "--retry-cooldown-sec",
        str(args.repair_retry_cooldown_sec),
        "--task-timeout-sec",
        str(args.repair_task_timeout_sec),
        "--port-offset",
        str(args.repair_port_offset),
        "--max-steps",
        str(args.max_steps),
        "--aime-request-delay-sec",
        str(args.aime_request_delay_sec),
        "--aime-max-retries",
        str(args.aime_max_retries),
        "--aime-read-timeout-sec",
        str(args.aime_read_timeout_sec),
        "--aime-base-url",
        f"https://127.0.0.1:{args.tunnel_port}{args.aime_path_prefix}",
        "--aime-host-header",
        args.aime_host,
        "--aime-api-style",
        api_style,
        "--aime-verify-ssl",
        "false",
    ]
    env = os.environ.copy()
    env["AIME_LITELLM_API_KEY"] = api_key
    env.pop("AIME_LITELLM_API_KEYS", None)
    args.run_log.parent.mkdir(parents=True, exist_ok=True)
    with args.run_log.open("a", encoding="utf-8") as fh:
        fh.write(f"[{utc_now()}] RUN style={api_style} cmd={' '.join(cmd)}\n")
        process = subprocess.run(cmd, cwd=REPO_ROOT, env=env, stdout=fh, stderr=fh, text=True)
        fh.write(f"[{utc_now()}] EXIT rc={process.returncode}\n")
        return int(process.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-key", default=DEFAULT_MODEL_KEY)
    parser.add_argument("--model-slug", default=DEFAULT_MODEL_SLUG)
    parser.add_argument("--base-official-dir", type=Path, default=DEFAULT_BASE_OFFICIAL_DIR)
    parser.add_argument("--repair-batch-root", type=Path, default=DEFAULT_REPAIR_BATCH_ROOT)
    parser.add_argument("--repair-output-root", type=Path, default=DEFAULT_REPAIR_OUTPUT_ROOT)
    parser.add_argument("--merged-official-dir", type=Path, default=DEFAULT_MERGED_OFFICIAL_DIR)
    parser.add_argument("--targets-path", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--run-log", type=Path, default=DEFAULT_RUN_LOG)
    parser.add_argument("--aime-model", default="claude-opus-4-6")
    parser.add_argument("--aime-host", default="aimemodeldev.myhexin.com")
    parser.add_argument("--aime-path-prefix", default="/litellm/v1")
    parser.add_argument("--tunnel-host", default="127.0.0.1")
    parser.add_argument("--tunnel-port", type=int, default=18444)
    parser.add_argument("--poll-sec", type=float, default=600.0)
    parser.add_argument("--preflight-timeout-sec", type=float, default=80.0)
    parser.add_argument("--repair-cooldown-sec", type=float, default=30.0)
    parser.add_argument("--repair-retry-passes", type=int, default=0)
    parser.add_argument("--repair-retry-cooldown-sec", type=float, default=120.0)
    parser.add_argument("--repair-task-timeout-sec", type=int, default=900)
    parser.add_argument("--repair-port-offset", type=int, default=22000)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2.0)
    parser.add_argument("--aime-max-retries", type=int, default=2)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300.0)
    parser.add_argument("--max-cycles", type=int, default=0, help="0 means run until all remaining targets are repaired.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keys = api_keys_from_env()
    if not keys:
        raise RuntimeError("Set AIME_LITELLM_API_KEY or AIME_LITELLM_API_KEYS in the environment.")
    expected = merge_utils.load_expected_tasks()
    cycle = 0
    while True:
        targets = remaining_targets(args, expected)
        write_jsonl(args.targets_path, targets)
        counts = merge_current(args, expected)
        log(f"cycle={cycle} remaining_targets={len(targets)} merged_outcomes={dict(counts)}", args.log_path)
        if not targets:
            log("all remaining Opus 4.6 agent-error targets are repaired; exiting", args.log_path)
            return 0
        if args.max_cycles > 0 and cycle >= args.max_cycles:
            log(f"max cycles reached: {args.max_cycles}; exiting", args.log_path)
            return 2
        result = preflight(args, keys)
        if result is None:
            log(f"Opus 4.6 not available; sleeping {args.poll_sec}s", args.log_path)
            time.sleep(args.poll_sec)
            cycle += 1
            continue
        api_key, api_style = result
        log(f"Opus 4.6 preflight succeeded; starting repair style={api_style}", args.log_path)
        rc = run_checkpoint(args, api_key=api_key, api_style=api_style)
        log(f"checkpoint repair finished rc={rc}", args.log_path)
        cycle += 1


if __name__ == "__main__":
    raise SystemExit(main())
