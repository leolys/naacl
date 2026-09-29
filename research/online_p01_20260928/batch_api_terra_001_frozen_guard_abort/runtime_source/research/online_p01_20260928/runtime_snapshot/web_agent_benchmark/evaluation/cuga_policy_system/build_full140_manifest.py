#!/usr/bin/env python3
"""Build the frozen 140-case CUGA manifest from paired benchmark task files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
OFFICIAL_ROOT = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
CLEAN_ROOT = REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "full140.jsonl"
SCENARIOS = {
    "public39": ("public39_tasks.jsonl", 39),
    "business47": ("business47_tasks.jsonl", 47),
    "environment35": ("environment35_tasks.jsonl", 35),
    "health19": ("health19_tasks.jsonl", 19),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    manifest: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for scenario, (filename, expected_count) in SCENARIOS.items():
        official_rows = read_jsonl(OFFICIAL_ROOT / filename)
        clean_rows = read_jsonl(CLEAN_ROOT / filename)
        if len(official_rows) != expected_count or len(clean_rows) != expected_count:
            raise ValueError(
                f"Unexpected {scenario} counts: official={len(official_rows)}, "
                f"clean={len(clean_rows)}, expected={expected_count}"
            )
        clean_by_slug = {str(row["official_slug"]): row for row in clean_rows}
        for official in official_rows:
            slug = str(official["official_slug"])
            key = (scenario, slug)
            if key in seen:
                raise ValueError(f"Duplicate manifest key: {scenario}/{slug}")
            seen.add(key)
            clean = clean_by_slug.get(slug)
            if clean is None:
                raise ValueError(f"Missing clean pair: {scenario}/{slug}")
            if clean.get("case_id") != official.get("case_id"):
                raise ValueError(f"Pair case_id mismatch: {scenario}/{slug}")
            manifest.append(
                {
                    "selection_rule": "all 140 paired synthetic benchmark cases in canonical scenario/task order",
                    "scenario": scenario,
                    "slug": slug,
                    "misleader_type": official.get("misleader_type"),
                    "case_id": official.get("case_id"),
                }
            )

    if len(manifest) != 140:
        raise ValueError(f"Expected 140 manifest rows, found {len(manifest)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest)
    args.output.write_text(payload, encoding="utf-8")
    print(f"Wrote {len(manifest)} paired cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
