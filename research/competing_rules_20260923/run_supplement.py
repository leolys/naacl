"""One fixed, separately reported format-repair check; not a replacement panel."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
from pathlib import Path

from engine import API, Budget, dump
from run_demo import one_run, offline_evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/health004_supplement.json")
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if (config["case_aliases"] != ["case03", "case04"]
            or config["task_ids"] != ["health004"]
            or config["systems"] != ["competing_persistent"]
            or config["max_request_attempts"] > 40 or config["max_browser_operations"] > 40):
        raise ValueError("This supplement is fixed to two health004 full-method trajectories, capped at 40/40")
    data, output = Path(args.data), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "config_snapshot.json", config)
    dump(output / "scope.json", {
        "kind": "post_format_fix_engineering_supplement",
        "v2_rows_replaced": False, "independent_new_tasks": 0,
        "prior_request_attempts": 73, "prior_browser_operations": 141,
        "prior_browser_includes_engineering_tests": 21,
        "cumulative_ceiling": {"request_attempts": 150, "browser_operations": 300}})
    sources = list(Path(__file__).parent.glob("*.py"))
    dump(output / "runtime.json", {"python": sys.version, "platform": platform.platform(),
        "packages": {p: importlib.metadata.version(p) for p in ("requests", "Pillow", "Flask", "playwright")},
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}})
    (output / "runtime_source").mkdir()
    for path in sources:
        shutil.copy2(path, output / "runtime_source" / path.name)
    budget = Budget(output, config)
    api = API(config, budget)
    results = []
    for alias in config["case_aliases"]:
        print("START", alias, "supplement", flush=True)
        result = one_run(api, budget, config, data / alias, "competing_persistent", output / (alias + "_competing_persistent"))
        results.append(result)
        print("END", alias, result["status"], "attempts", budget.attempts, flush=True)
    offline_evaluate(data, output, results)
    print("DONE", len(results), "separate supplement trajectories; requests", budget.attempts,
          "browser operations", budget.operations, flush=True)


if __name__ == "__main__":
    main()
