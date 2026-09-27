"""Read-only local inventory. Output is evaluator-owned, never model input."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image

from .core import write_json
from .runner import RELEASE_ROOT, REPOSITORY_ROOT, pair_invariant_differences, read_jsonl, utc_now


def audit() -> dict:
    conditions = {}
    for condition in ("official140", "clean140"):
        rows = [row for path in sorted((RELEASE_ROOT / "splits" / condition).glob("*_tasks.jsonl"))
                for row in read_jsonl(path)]
        conditions[condition] = {row["pair_group_id"]: row for row in rows}
    left, right = conditions["official140"], conditions["clean140"]
    differences = {
        pair: pair_invariant_differences(left[pair], right[pair])
        for pair in sorted(left.keys() & right.keys())
    }
    assets = read_jsonl(RELEASE_ROOT / "metadata" / "asset_manifest.jsonl")
    missing = [row["release_path"] for row in assets
               if not (REPOSITORY_ROOT / row["release_path"]).is_file()]
    formats = {}
    for condition, tasks in conditions.items():
        count = Counter()
        for task in tasks.values():
            path = REPOSITORY_ROOT / task["chart_asset"]["figure_path"]
            with Image.open(path) as image:
                count[image.format] += 1
        formats[condition] = dict(count)
    return {
        "audited_at": utc_now(), "repository_root": str(REPOSITORY_ROOT),
        "release_root": str(RELEASE_ROOT), "online_access": False,
        "release_manifest": json.loads((RELEASE_ROOT / "benchmark_manifest.json").read_text()),
        "counts": {name: len(tasks) for name, tasks in conditions.items()},
        "pair_keys_equal": left.keys() == right.keys(),
        "strict_non_chart_equal_pairs": sum(not fields for fields in differences.values()),
        "non_chart_differences": {pair: fields for pair, fields in differences.items() if fields},
        "official_chart_types": dict(Counter(str(row.get("plot_type")) for row in left.values())),
        "official_mechanisms": dict(Counter(str(row.get("misleader_type")) for row in left.values())),
        "asset_count": len(assets), "missing_assets": missing,
        "asset_suffixes": dict(Counter(Path(row["release_path"]).suffix.lower() for row in assets)),
        "decoded_figure_formats": formats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit()
    write_json(args.output, result)
    print(json.dumps({key: result[key] for key in
                      ("counts", "pair_keys_equal", "strict_non_chart_equal_pairs", "asset_count", "missing_assets")}, indent=2))


if __name__ == "__main__":
    main()
