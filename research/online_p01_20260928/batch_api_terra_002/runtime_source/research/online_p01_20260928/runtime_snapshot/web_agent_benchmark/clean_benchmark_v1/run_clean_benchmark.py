#!/usr/bin/env python3
"""Run the four clean benchmark shell apps for agent-facing review."""

from __future__ import annotations

import signal
import argparse
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIR = REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1"
PYTHON = sys.executable

APPS = [
    {
        "name": "public39",
        "url": "http://127.0.0.1:8126/",
        "cmd": [
            PYTHON,
            "web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py",
            "--tasks",
            "web_agent_benchmark/clean_benchmark_v1/public39_tasks.jsonl",
            "--output",
            "web_agent_benchmark/clean_benchmark_v1/submissions/public39_submissions.jsonl",
            "--summary",
            "web_agent_benchmark/clean_benchmark_v1/public39_shell_summary.md",
            "--port",
            "8126",
        ],
    },
    {
        "name": "business47",
        "url": "http://127.0.0.1:8116/",
        "cmd": [
            PYTHON,
            "web_agent_benchmark/business_shell/business_shell_app.py",
            "--tasks",
            "web_agent_benchmark/clean_benchmark_v1/business47_tasks.jsonl",
            "--submissions",
            "web_agent_benchmark/clean_benchmark_v1/submissions/business47_submissions.jsonl",
            "--summary",
            "web_agent_benchmark/clean_benchmark_v1/business47_shell_summary.md",
            "--port",
            "8116",
        ],
    },
    {
        "name": "environment35",
        "url": "http://127.0.0.1:8133/",
        "cmd": [
            PYTHON,
            "web_agent_benchmark/environment_energy_shell/environment_shell_app.py",
            "--tasks",
            "web_agent_benchmark/clean_benchmark_v1/environment35_tasks.jsonl",
            "--output",
            "web_agent_benchmark/clean_benchmark_v1/submissions/environment35_submissions.jsonl",
            "--port",
            "8133",
        ],
    },
    {
        "name": "health19",
        "url": "http://127.0.0.1:8137/",
        "cmd": [
            PYTHON,
            "web_agent_benchmark/health_shell/health_shell_app.py",
            "--tasks",
            "web_agent_benchmark/clean_benchmark_v1/health19_tasks.jsonl",
            "--output",
            "web_agent_benchmark/clean_benchmark_v1/submissions/health19_submissions.jsonl",
            "--port",
            "8137",
        ],
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the clean benchmark shell apps.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface for all clean shell apps.")
    parser.add_argument(
        "--review-ui",
        action="store_true",
        help="Show clean/misleading chart comparison and action labels for human review.",
    )
    args = parser.parse_args()

    missing = [
        CLEAN_DIR / name
        for name in ["public39_tasks.jsonl", "business47_tasks.jsonl", "environment35_tasks.jsonl", "health19_tasks.jsonl"]
        if not (CLEAN_DIR / name).exists()
    ]
    if missing:
        print("Clean benchmark files are missing. Build them first with:")
        print("  python web_agent_benchmark/official_benchmark_v1/build_clean_benchmark.py")
        for path in missing:
            print(f"  missing: {path}")
        return 2

    (CLEAN_DIR / "submissions").mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for app in APPS:
            cmd = app["cmd"] + ["--host", args.host]
            if args.review_ui:
                cmd.append("--review-ui")
            process = subprocess.Popen(cmd, cwd=REPO_ROOT)
            processes.append(process)
            print(f"Started {app['name']}: {app['url']}")
        print("")
        print(f"Unified index: {CLEAN_DIR / 'index.html'}")
        print("Press Ctrl+C to stop all clean benchmark servers.")
        while True:
            for process, app in zip(processes, APPS):
                if process.poll() is not None:
                    raise RuntimeError(f"{app['name']} exited with code {process.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping clean benchmark servers...")
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
