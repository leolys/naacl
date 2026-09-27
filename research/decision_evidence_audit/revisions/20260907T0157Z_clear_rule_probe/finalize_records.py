"""Offline session accounting and artifact checks; performs no inference or browsing."""

import json
import argparse
from html.parser import HTMLParser
from pathlib import Path


REVISION = Path(__file__).resolve().parent
PACKAGE = REVISION.parents[1]
RUN_NAMES = (
    "clear_rule_mock_20260907T0200Z",
    "clear_rule_mock_isolated_20260907T0206Z",
    "clear_rule_mock_reviewed_20260907T0220Z",
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class ViewerAudit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = 0
        self.external_dependencies = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img":
            self.images += 1
        if tag in {"img", "script", "link", "iframe"}:
            for attr in ("src", "href"):
                value = attrs.get(attr, "")
                if value and not value.startswith("data:"):
                    self.external_dependencies.append(value)


def main():
    args_parser = argparse.ArgumentParser(description=__doc__)
    args_parser.add_argument("--live-run", type=Path)
    args = args_parser.parse_args()
    rows = []
    runs = [PACKAGE / "runs" / name for name in RUN_NAMES]
    if args.live_run:
        runs.append(args.live_run.resolve())
    for run in runs:
        manifest = read(run / "run_manifest.json")
        budget = read(run / "budget.json")
        rows.append({
            "artifact": str(run), "kind": manifest["model_mode"],
            "real_model_calls": budget["model_calls"] if manifest["model_mode"] == "live-local" else 0,
            "mock_backend_calls": budget["model_calls"] if manifest["model_mode"] == "mock" else 0,
            "browser_transitions": budget["browser_transitions"],
            "configured_units_including_retained_unexecuted": manifest["configured_units"],
            "completed_submission_chains": manifest["completed_chain_units"],
        })
    control_path = REVISION / "browser_controls" / "test_checkpoint_replay_true_revision_submit_b0_and_illegal_control" / "control_budgets.json"
    control = read(control_path)
    rows.append({
        "artifact": str(control_path), "kind": "synthetic_positive_control",
        "real_model_calls": control["real_model_calls"],
        "mock_backend_calls": control["mock_calls"],
        "browser_transitions": control["browser_transitions"],
    })
    totals = {key: sum(row[key] for row in rows) for key in (
        "real_model_calls", "mock_backend_calls", "browser_transitions",
    )}
    assert totals["real_model_calls"] <= 160
    assert totals["browser_transitions"] <= 800
    viewer = REVISION / "reviewed_case_view" / "CASE_VIEWER.html"
    parser = ViewerAudit()
    text = viewer.read_text(encoding="utf-8")
    parser.feed(text)
    assert parser.images > 0 and not parser.external_dependencies
    assert "脚本 mock：不是自然错误，不是模型效果" in text
    assert "原本错误且未纠正" not in text
    summary = read(REVISION / "reviewed_case_view" / "CASE_SUMMARY.json")
    assert summary["natural_wrong_checkpoints"] is None
    assert summary["trajectory_counts"] == {}
    payload = {
        "actual_run_rows": rows, "totals": totals,
        "real_model_experiment_status": read(args.live_run / "run_manifest.json")["real_model_smoke_status"] if args.live_run else "not_run",
        "natural_error_recovery_result": read(REVISION / "live_case_view" / "CASE_SUMMARY.json") if args.live_run else None,
        "unit_tests": {"latest_discovered": 49, "passed": 46, "skipped_opt_in_browser_tests": 3},
        "browser_control_test": {"passed": 1, "real_model_calls": 0},
        "report_tests_passed": 2,
        "viewer": {"path": str(viewer), "embedded_images": parser.images,
                   "external_dependencies": parser.external_dependencies, "bytes": viewer.stat().st_size},
        "note": "Unit-test fake backend/MagicMock calls are not actual inference or browser transitions. Browser control sub-ledgers are included exactly once via their aggregate.",
    }
    destination = REVISION / "SESSION_ACCOUNTING.json"
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
