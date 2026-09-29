#!/usr/bin/env python3
"""Run benchmark_v2."""

from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = REPO_ROOT / "web_agent_benchmark" / "benchmark_v2"
PYTHON = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark_v2.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8146)
    args = parser.parse_args()

    tasks = BENCHMARK_DIR / "public_tasks.jsonl"
    if not tasks.exists():
        print("Benchmark v2 files are missing. Build them first with:")
        print("  python web_agent_benchmark/official_benchmark_v1/build_benchmark_v2.py")
        return 2

    (BENCHMARK_DIR / "submissions").mkdir(parents=True, exist_ok=True)
    cmd = [
        PYTHON,
        "web_agent_benchmark/benchmark_v2/benchmark_v2_public_app.py",
        "--tasks",
        "web_agent_benchmark/benchmark_v2/public_tasks.jsonl",
        "--output",
        "web_agent_benchmark/benchmark_v2/submissions/public_submissions.jsonl",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    process = subprocess.Popen(cmd, cwd=REPO_ROOT)
    try:
        print(f"Started benchmark_v2: http://127.0.0.1:{args.port}/")
        print(f"Index file: {BENCHMARK_DIR / 'index.html'}")
        print("Press Ctrl+C to stop benchmark_v2.")
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"benchmark_v2 exited with code {process.returncode}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping benchmark_v2...")
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
