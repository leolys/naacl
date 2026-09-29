"""Explicit post-run interface diagnostic: replay existing zero-argument proposals, no API."""
import argparse
import copy
import json
from pathlib import Path

from PIL import Image, ImageChops

from adapter import BrowserTask, score_summary
from engine import Budget, dump


def normalize(proposal):
    """Repackage explicit, complete action fields; never infer a choice or submit."""
    result = copy.deepcopy(proposal)
    if isinstance(result.get("action"), str) and result["action"] in ("submit", "observe"):
        result["action"] = {"kind": result["action"]}
    elif result.get("action") == "select" and isinstance(result.get("option"), str):
        result["action"] = {"kind": "select", "option": result["option"]}
    elif (result.get("action") == "fill" and isinstance(result.get("field"), str)
          and isinstance(result.get("value"), str)):
        result["action"] = {"kind": "fill", "field": result["field"], "value": result["value"]}
    elif (result.get("action") == "check" and isinstance(result.get("field"), str)
          and isinstance(result.get("value"), bool)):
        result["action"] = {"kind": "check", "field": result["field"], "value": result["value"]}
    if not isinstance(result.get("action"), dict):
        raise ValueError("not an unambiguous supported action representation")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--data", default="data")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run, output = Path(args.run), Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((run / "config_snapshot.json").read_text(encoding="utf-8"))
    original_budget = json.loads((run / "budget.json").read_text(encoding="utf-8"))
    # Original runs, 21 engineering operations, and these replays share the advertised bound.
    config["max_browser_operations"] -= original_budget["browser_operations"] + 21
    config["max_request_attempts"] = 0
    budget = Budget(output, config)
    reports = []
    for folder in sorted(run.glob("case*")):
        trajectory_path = folder / "trajectory.json"
        if not trajectory_path.is_file():
            continue
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        if trajectory.get("error") != "ValueError: actor did not return a single action":
            continue
        actor_dir = sorted(folder.glob("step_*/actor"))[-1]
        old = json.loads((actor_dir / "parsed.json").read_text(encoding="utf-8"))
        if old.get("action") not in ("submit", "observe"):
            continue
        rec = {"source_run": folder.name, "source_proposal": str(actor_dir / "parsed.json"),
               "original_proposal": old, "status": "not_replayed", "api_attempts": 0}
        try:
            new = normalize(old)
            if old.get("action") not in ("submit", "observe"):
                raise ValueError("zero-model replay only covers explicit submit/observe; parameterized action continuation is separate")
            rec["normalized_proposal"] = new
            inputs = json.loads((actor_dir / "context.json").read_text(encoding="utf-8"))
            case_data = Path(args.data) / trajectory["case_alias"]
            with BrowserTask(case_data, output / folder.name,
                             config.get("browser_executable"), budget) as browser:
                for record in inputs["context"]["history"]:
                    if record["source"] == "deterministic_setup":
                        continue
                    receipt = browser.execute(record["action"], source=record["source"])
                    if not receipt["ok"]:
                        raise RuntimeError("replay of prior actual action failed")
                snap = browser.snapshot("restored_model_input")
                rec["state_equal"] = snap["state"] == inputs["context"]["state"]
                rec["history_equal"] = browser.history == inputs["context"]["history"]
                old_png = folder / "browser" / Path(inputs["images"][-1]["file"]).name
                old_image = Image.open(old_png).convert("RGB")
                new_image = Image.open(snap["screenshot"]).convert("RGB")
                rec["screenshot_pixels_equal"] = old_image.size == new_image.size and ImageChops.difference(old_image, new_image).getbbox() is None
                if not all(rec[k] for k in ("state_equal", "history_equal", "screenshot_pixels_equal")):
                    raise RuntimeError("cannot establish same input state; original proposal not executed")
                rec["execution"] = browser.execute(new["action"], source="saved_api_proposal_format_replay")
                rec["receipt"] = browser.receipt
                rec["status"] = "replayed"
            raw = json.loads((case_data / "offline" / "raw.json").read_text(encoding="utf-8"))
            rec["offline_score"] = score_summary(raw, rec.get("receipt"))
        except Exception as exc:
            rec["status"] = "not_supported"
            rec["error"] = type(exc).__name__ + ": " + str(exc)
        reports.append(rec)
        dump(output / "results.json", reports)
    dump(output / "results.json", reports)
    print(json.dumps({"candidates": len(reports), "operations": budget.operations,
                      "replayed": sum(r["status"] == "replayed" for r in reports)}))


if __name__ == "__main__":
    main()
