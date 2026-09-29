#!/usr/bin/env python3
"""Resume CUGA Full140 passes and finalize analysis after complete coverage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = REPO_ROOT / "web_agent_benchmark" / "evaluation"
DEFAULT_MANIFEST = EVALUATION_ROOT / "cuga_policy_system" / "full140.jsonl"
DEFAULT_SEED = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_miniset_16paired_20260710"
    / "runs.jsonl"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_full140_gpt54_20260711"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("condition")),
        str(row.get("benchmark")),
        str(row.get("scenario")),
        str(row.get("slug")),
    )


def inspect_output(output_root: Path, expected_rows: int) -> dict[str, Any]:
    rows = read_jsonl(output_root / "runs.jsonl")
    unique_keys = {row_key(row) for row in rows}
    agent_errors = [row_key(row) for row in rows if row.get("outcome") == "agent_error"]
    return {
        "timestamp": utc_now(),
        "row_count": len(rows),
        "unique_key_count": len(unique_keys),
        "expected_rows": expected_rows,
        "agent_error_count": len(agent_errors),
        "agent_error_keys": ["/".join(key) for key in agent_errors],
        "complete": len(rows) == expected_rows and len(unique_keys) == expected_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seed-runs-from", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--task-timeout-sec", type=int, default=600)
    parser.add_argument("--max-passes", type=int, default=5)
    parser.add_argument("--retry-delay-sec", type=int, default=30)
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_BASE_URL"):
        raise RuntimeError("OPENAI_API_KEY and OPENAI_BASE_URL must be set in the process environment")

    manifest = read_jsonl(args.manifest.resolve())
    expected_rows = len(manifest) * 4
    if len(manifest) != 140:
        raise RuntimeError(f"Expected a 140-case manifest, found {len(manifest)}")

    args.output_root = args.output_root.resolve()
    args.output_root.mkdir(parents=True, exist_ok=True)
    status_path = args.output_root / "supervisor_status.json"
    runner = EVALUATION_ROOT / "run_cuga_policy_system_miniset.py"
    analyzer = EVALUATION_ROOT / "analyze_cuga_policy_system_miniset.py"

    history: list[dict[str, Any]] = []
    for pass_index in range(1, args.max_passes + 1):
        before = inspect_output(args.output_root, expected_rows)
        print(
            f"[supervisor] pass {pass_index}/{args.max_passes}: "
            f"before={before['row_count']}/{expected_rows}, agent_errors={before['agent_error_count']}",
            flush=True,
        )
        command = [
            sys.executable,
            "-u",
            str(runner),
            "--manifest",
            str(args.manifest.resolve()),
            "--seed-runs-from",
            str(args.seed_runs_from.resolve()),
            "--output-root",
            str(args.output_root),
            "--task-timeout-sec",
            str(args.task_timeout_sec),
        ]
        started_at = utc_now()
        result = subprocess.run(command, cwd=REPO_ROOT, check=False)
        after = inspect_output(args.output_root, expected_rows)
        history.append(
            {
                "pass": pass_index,
                "started_at": started_at,
                "finished_at": utc_now(),
                "return_code": result.returncode,
                "before": before,
                "after": after,
            }
        )
        status_path.write_text(
            json.dumps({"history": history, "latest": after}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"[supervisor] pass {pass_index} finished: rc={result.returncode}, "
            f"rows={after['row_count']}/{expected_rows}, agent_errors={after['agent_error_count']}",
            flush=True,
        )
        if after["complete"] and after["agent_error_count"] == 0:
            analysis = subprocess.run(
                [sys.executable, str(analyzer), "--root", str(args.output_root)],
                cwd=REPO_ROOT,
                check=False,
            )
            if analysis.returncode != 0:
                raise RuntimeError(f"Full140 analysis failed with return code {analysis.returncode}")
            print("[supervisor] Full140 complete and analysis generated", flush=True)
            return 0
        if pass_index < args.max_passes:
            time.sleep(args.retry_delay_sec)

    latest = inspect_output(args.output_root, expected_rows)
    print(
        f"[supervisor] incomplete after {args.max_passes} passes: "
        f"rows={latest['row_count']}/{expected_rows}, agent_errors={latest['agent_error_count']}",
        flush=True,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
