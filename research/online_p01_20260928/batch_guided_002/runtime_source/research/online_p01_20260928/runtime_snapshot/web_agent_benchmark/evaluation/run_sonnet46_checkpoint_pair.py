#!/usr/bin/env python3
"""Run Sonnet 4.6 official and clean checkpoints with endpoint preflight."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_RUNNER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "run_claude_opus46_uuid_checkpoint.py"
PAIR_MERGER = REPO_ROOT / "web_agent_benchmark" / "evaluation" / "merge_sonnet46_checkpoint_pair.py"
MODEL_KEY = "claude_sonnet_4_6_aime_responses"
MODEL_SLUG = "claude_sonnet_4_6_aime_responses_temp0_top_p1_seed12345"
DEFAULT_BASE_URL = "https://127.0.0.1:18444/litellm/v1"
DEFAULT_HOST_HEADER = "aimemodeldev.myhexin.com"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def request_body(api_style: str) -> bytes:
    if api_style == "responses":
        payload: dict[str, Any] = {
            "model": "claude-sonnet-4-6",
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "只回答 OK"}]}],
            "max_output_tokens": 32,
        }
    else:
        payload = {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "只回答 OK"}],
            "max_tokens": 32,
        }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def public_endpoint_url(*, base_url: str, host_header: str, api_style: str) -> tuple[str, str]:
    path = "/responses" if api_style == "responses" else "/chat/completions"
    match = re.match(r"^https://127\.0\.0\.1:(\d+)(/.*)$", base_url.rstrip("/"))
    if not match:
        return base_url.rstrip("/") + path, ""
    port, base_path = match.groups()
    return f"https://{host_header}{base_path}{path}", f"{host_header}:443:127.0.0.1:{port}"


def probe_style(*, api_style: str, base_url: str, host_header: str, timeout: int) -> tuple[int | None, str]:
    url, connect_to = public_endpoint_url(base_url=base_url, host_header=host_header, api_style=api_style)
    command = [
        "curl",
        "--noproxy",
        "*",
        "--connect-timeout",
        "10",
        "--max-time",
        str(timeout),
        "-sS",
        "-o",
        "-",
        "-w",
        "\n%{http_code}",
        url,
        "-H",
        "Authorization: Bearer " + os.environ["AIME_LITELLM_API_KEY"],
        "-H",
        "Content-Type: application/json",
        "-d",
        request_body(api_style).decode("utf-8"),
    ]
    if connect_to:
        command[1:1] = ["--connect-to", connect_to]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout + 5)
    except Exception as exc:
        return None, repr(exc)
    output = completed.stdout or completed.stderr or ""
    body, _, code_text = output.rpartition("\n")
    try:
        code = int(code_text.strip())
    except ValueError:
        code = None
    return code, body[:500]


def choose_api_style(args: argparse.Namespace, log_path: Path) -> str:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, args.preflight_attempts + 1):
        timestamp = utc_now()
        responses_code, responses_body = probe_style(
            api_style="responses",
            base_url=args.aime_base_url,
            host_header=args.aime_host_header,
            timeout=args.preflight_timeout_sec,
        )
        if responses_code == 200:
            log_path.write_text(
                f"[{timestamp}] attempt={attempt} selected=responses responses=200\n",
                encoding="utf-8",
            )
            return "responses"
        chat_code, chat_body = probe_style(
            api_style="chat_completions",
            base_url=args.aime_base_url,
            host_header=args.aime_host_header,
            timeout=args.preflight_timeout_sec,
        )
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(
                f"[{timestamp}] attempt={attempt} responses={responses_code} "
                f"chat={chat_code} responses_body={responses_body[:240]!r} "
                f"chat_body={chat_body[:240]!r}\n"
            )
        if chat_code == 200:
            return "chat_completions"
        time.sleep(args.preflight_sleep_sec)
    raise RuntimeError("Neither /responses nor /chat/completions recovered during preflight.")


def checkpoint_command(args: argparse.Namespace, *, benchmark: str, api_style: str) -> list[str]:
    return [
        sys.executable,
        str(CHECKPOINT_RUNNER),
        "--benchmark",
        benchmark,
        "--model-key",
        MODEL_KEY,
        "--model-slug",
        MODEL_SLUG,
        "--batch-root",
        str(args.record_root / f"claude_sonnet_4_6_aime_responses_{benchmark}_checkpoint_batches_20260521"),
        "--output-root",
        str(args.record_root / f"claude_sonnet_4_6_aime_responses_{benchmark}_checkpoint_full140_20260521"),
        "--cooldown-sec",
        str(args.cooldown_sec),
        "--retry-passes",
        str(args.retry_passes),
        "--retry-cooldown-sec",
        str(args.retry_cooldown_sec),
        "--task-timeout-sec",
        str(args.task_timeout_sec),
        "--port-offset",
        str(args.port_offset),
        "--max-steps",
        str(args.max_steps),
        "--aime-request-delay-sec",
        str(args.aime_request_delay_sec),
        "--aime-max-retries",
        str(args.aime_max_retries),
        "--aime-read-timeout-sec",
        str(args.aime_read_timeout_sec),
        "--aime-base-url",
        args.aime_base_url,
        "--aime-host-header",
        args.aime_host_header,
        "--aime-api-style",
        api_style,
        "--aime-verify-ssl",
        "false",
        "--preflight-before-task",
        "--aime-preflight-model",
        "claude-sonnet-4-6",
        "--preflight-attempts",
        str(args.preflight_attempts),
        "--preflight-sleep-sec",
        str(args.preflight_sleep_sec),
        "--preflight-timeout-sec",
        str(args.preflight_timeout_sec),
        "--transient-agent-error-cooldown-sec",
        str(args.transient_agent_error_cooldown_sec),
    ]


def run_command(command: list[str], *, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
            log.flush()
        return process.wait()


def agent_error_count(args: argparse.Namespace, benchmark: str) -> int:
    path = (
        args.record_root
        / f"claude_sonnet_4_6_aime_responses_{benchmark}_checkpoint_full140_20260521"
        / "agent_error_targets.jsonl"
    )
    return len(read_jsonl(path))


def merge_pair(args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        str(PAIR_MERGER),
        "--official-root",
        str(args.record_root / "claude_sonnet_4_6_aime_responses_official_checkpoint_full140_20260521"),
        "--clean-root",
        str(args.record_root / "claude_sonnet_4_6_aime_responses_clean_checkpoint_full140_20260521"),
        "--output-root",
        str(args.record_root / "claude_sonnet_4_6_aime_responses_full140_checkpoint_repaired_20260521"),
    ]
    return run_command(command, log_path=args.log_root / "merge.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-root", type=Path, default=REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records")
    parser.add_argument("--log-root", type=Path, default=REPO_ROOT / "web_agent_benchmark" / "pair_evaluation_records" / "claude_sonnet_4_6_aime_responses_loop_logs_20260521")
    parser.add_argument("--aime-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--aime-host-header", default=DEFAULT_HOST_HEADER)
    parser.add_argument("--benchmarks", default="official,clean")
    parser.add_argument("--port-offset", type=int, default=20000)
    parser.add_argument("--retry-passes", type=int, default=4)
    parser.add_argument("--cooldown-sec", type=float, default=10.0)
    parser.add_argument("--retry-cooldown-sec", type=float, default=60.0)
    parser.add_argument("--task-timeout-sec", type=int, default=900)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--aime-request-delay-sec", type=float, default=2.0)
    parser.add_argument("--aime-max-retries", type=int, default=2)
    parser.add_argument("--aime-read-timeout-sec", type=float, default=300.0)
    parser.add_argument("--preflight-attempts", type=int, default=60)
    parser.add_argument("--preflight-sleep-sec", type=float, default=60.0)
    parser.add_argument("--preflight-timeout-sec", type=int, default=60)
    parser.add_argument("--transient-agent-error-cooldown-sec", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.environ.get("AIME_LITELLM_API_KEY"):
        raise RuntimeError("AIME_LITELLM_API_KEY is not set.")
    args.record_root = args.record_root.resolve()
    args.log_root = args.log_root.resolve()
    benchmarks = [item.strip() for item in args.benchmarks.split(",") if item.strip()]
    for benchmark in benchmarks:
        style = choose_api_style(args, args.log_root / f"{benchmark}_preflight.log")
        command = checkpoint_command(args, benchmark=benchmark, api_style=style)
        rc = run_command(command, log_path=args.log_root / f"{benchmark}_checkpoint.log")
        if rc != 0:
            return rc
        while agent_error_count(args, benchmark) > 0:
            style = choose_api_style(args, args.log_root / f"{benchmark}_retry_preflight.log")
            command = checkpoint_command(args, benchmark=benchmark, api_style=style)
            rc = run_command(command, log_path=args.log_root / f"{benchmark}_checkpoint_retry.log")
            if rc != 0:
                return rc
    if set(benchmarks) == {"official", "clean"}:
        return merge_pair(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
