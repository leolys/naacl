#!/usr/bin/env python3
"""Resume CUGA v2 Full140 and finalize analysis after technical failures clear."""

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
DEFAULT_PLAYBOOK = EVALUATION_ROOT / "cuga_policy_system" / "chart_verification_playbook_v2.md"
DEFAULT_OUTPUT = (
    REPO_ROOT
    / "web_agent_benchmark"
    / "pair_evaluation_records"
    / "cuga_policy_system_v2_guarded_full140_gpt54_20260711"
)
CONTROL = "default_v2_control"
POLICY = "playbook_v2_guarded"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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
    guard_errors = [
        row_key(row)
        for row in rows
        if bool((row.get("guard_summary") or {}).get("has_guard_error"))
    ]
    policy_rows = [row for row in rows if row.get("condition") == POLICY]
    default_rows = [row for row in rows if row.get("condition") == CONTROL]
    return {
        "timestamp": utc_now(),
        "row_count": len(rows),
        "unique_key_count": len(unique_keys),
        "expected_rows": expected_rows,
        "agent_error_count": len(agent_errors),
        "guard_error_count": len(guard_errors),
        "agent_error_keys": ["/".join(key) for key in agent_errors],
        "guard_error_keys": ["/".join(key) for key in guard_errors],
        "policy_rows": len(policy_rows),
        "policy_matches": sum(
            bool((row.get("policy_enactment") or {}).get("matched")) for row in policy_rows
        ),
        "default_rows": len(default_rows),
        "unexpected_default_matches": sum(
            bool((row.get("policy_enactment") or {}).get("matched")) for row in default_rows
        ),
        "guard_call_limit_violations": sum(
            int((row.get("guard_summary") or {}).get("guard_call_count") or 0) > 2
            for row in policy_rows
        ),
        "guard_block_limit_violations": sum(
            int((row.get("guard_summary") or {}).get("guard_block_count") or 0) > 1
            for row in policy_rows
        ),
        "complete": len(rows) == expected_rows and len(unique_keys) == expected_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--task-timeout-sec", type=int, default=600)
    parser.add_argument("--max-steps", type=int, default=55)
    parser.add_argument("--max-passes", type=int, default=5)
    parser.add_argument("--retry-delay-sec", type=int, default=30)
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_BASE_URL"):
        raise RuntimeError("OPENAI_API_KEY and OPENAI_BASE_URL must be set")
    manifest = read_jsonl(args.manifest.resolve())
    if len(manifest) != 140:
        raise RuntimeError(f"expected a 140-case manifest, found {len(manifest)}")
    expected_rows = len(manifest) * 4
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    status_path = output_root / "supervisor_status.json"
    runner = EVALUATION_ROOT / "run_cuga_policy_system_v2_guarded.py"
    analyzer = EVALUATION_ROOT / "analyze_cuga_policy_system_v2_guarded.py"

    history: list[dict[str, Any]] = []
    for pass_index in range(1, args.max_passes + 1):
        before = inspect_output(output_root, expected_rows)
        print(
            f"[cuga-v2-supervisor] pass {pass_index}/{args.max_passes}: "
            f"rows={before['row_count']}/{expected_rows}, "
            f"agent_errors={before['agent_error_count']}, "
            f"guard_errors={before['guard_error_count']}",
            flush=True,
        )
        command = [
            sys.executable,
            "-u",
            str(runner),
            "--manifest",
            str(args.manifest.resolve()),
            "--playbook",
            str(args.playbook.resolve()),
            "--output-root",
            str(output_root),
            "--task-timeout-sec",
            str(args.task_timeout_sec),
            "--max-steps",
            str(args.max_steps),
        ]
        started_at = utc_now()
        result = subprocess.run(command, cwd=REPO_ROOT, check=False)
        after = inspect_output(output_root, expected_rows)
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
            json.dumps({"history": history, "latest": after}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        if (
            after["complete"]
            and after["agent_error_count"] == 0
            and after["guard_error_count"] == 0
            and after["policy_matches"] == 280
            and after["unexpected_default_matches"] == 0
            and after["guard_call_limit_violations"] == 0
            and after["guard_block_limit_violations"] == 0
        ):
            analysis = subprocess.run(
                [
                    sys.executable,
                    str(analyzer),
                    "--root",
                    str(output_root),
                    "--expected-cases",
                    "140",
                ],
                cwd=REPO_ROOT,
                check=False,
            )
            if analysis.returncode != 0:
                raise RuntimeError(f"CUGA v2 analysis failed with return code {analysis.returncode}")
            print("[cuga-v2-supervisor] Full140 complete and analysis generated", flush=True)
            return 0
        if result.returncode != 0:
            print(
                f"[cuga-v2-supervisor] runner returned {result.returncode}; "
                "the next pass will only be attempted after the fixed delay",
                flush=True,
            )
        if pass_index < args.max_passes:
            time.sleep(args.retry_delay_sec)

    latest = inspect_output(output_root, expected_rows)
    print(
        f"[cuga-v2-supervisor] incomplete after {args.max_passes} passes: "
        f"rows={latest['row_count']}/{expected_rows}, "
        f"agent_errors={latest['agent_error_count']}, "
        f"guard_errors={latest['guard_error_count']}",
        flush=True,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
