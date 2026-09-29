#!/usr/bin/env python3
"""Model-free Firefox calibration for every unique env008 phase-2 UI state."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .actions import ParsedAction
from .env008_phase2_protocol import Q1, Q2, Q3, Q4, Phase2CellSpec, phase2_cells
from .phase2_history_fixture import build_proposition_frame, diff_audit
from .run_env008_phase2 import (
    _click,
    _entity_maps,
    _feedback_leak_audit,
    _projection,
    _setup_intervention,
)
from .run_targeted_recovery_pilot import (
    _evaluator_choice_coordinate,
    _wait_for_initial_chart,
    build_browser_factory,
    load_authoritative_case,
    write_json,
)
from .targeted_recovery import F3_PRE_REATTEMPT_CONTRADICTION, FEEDBACK_RETRY
from .targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    PHASE2_BRANCH_INVALIDATION,
    TargetedPathPolicy,
)
from .targeted_recovery_layout import derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator
from .formal_path_policy import REPO_ROOT


def _capture(browser: Any, path: Path) -> dict[str, Any]:
    frame = browser.screenshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(frame.png)
    return {"path": str(path.resolve()), "url": frame.url}


def _feedback_choice_coordinate(position: int) -> tuple[int, int]:
    if position not in {0, 1, 2}:
        raise ValueError("phase-2 feedback calibration expects three cards")
    return 985, 613 + 109 * position


def _unique_specs() -> list[Phase2CellSpec]:
    selected: list[Phase2CellSpec] = []
    seen: set[tuple[Any, ...]] = set()
    for spec in phase2_cells():
        if spec.probe_id == Q2:
            identity = (Q2, spec.arm)
        else:
            identity = (
                spec.probe_id,
                spec.layout_id,
                spec.arm,
                spec.feedback_spec_id,
                spec.inherited_entity,
            )
        if identity not in seen:
            seen.add(identity)
            selected.append(spec)
    return selected


def _calibrate(
    *,
    spec: Phase2CellSpec,
    canonical_case: dict[str, Any],
    browser_factory: Any,
    directory: Path,
) -> dict[str, Any]:
    case = derive_layout_case(canonical_case, layout_id=spec.layout_id)
    action_ids, entity_to_token = _entity_maps(case)
    display_tokens = [
        str(card["choice_token"]) for card in case["model_visible_shared"]["action_cards"]
    ]
    projection = _projection(case, spec)
    app = CompactRecoveryApp(
        visible_case=projection,
        repository_root=REPO_ROOT,
        chart_path=(REPO_ROOT / str(projection["chart_path"])).resolve(),
        workflow_mode=FEEDBACK_RETRY,
        inherited_selection=True,
        outcome_feedback_enabled=(
            spec.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION
        ),
    )
    validator = (
        CanonicalOutcomeValidator(
            task_set="smoke17", slug="env008", layout_id=spec.layout_id
        )
        if spec.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION
        else None
    )
    scorer = CanonicalSubmissionScorer(
        task_set="smoke17", slug="env008", layout_id=spec.layout_id
    )
    browser = None
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            intervention, h1_png, _annotation = _setup_intervention(
                app=app,
                browser=browser,
                case=case,
                spec=spec,
                cell_dir=directory,
                run_id=f"calibration:{spec.key}",
                action_ids=action_ids,
                entity_to_token=entity_to_token,
                validator=validator,
            )
            handoff = _capture(browser, directory / "handoff.png")
            leak = _feedback_leak_audit(app, entity_to_token[spec.inherited_entity])
            fixture_diffs: dict[str, Any] | None = None
            if spec.probe_id == Q2:
                assert h1_png is not None
                frames = {
                    entity: build_proposition_frame(h1_png, entity)
                    for entity in ("Solar", "Wind", "Hydroelectric")
                }
                for entity, png in frames.items():
                    (directory / f"fixture_{entity.lower()}.png").write_bytes(png)
                fixture_diffs = {
                    "solar_wind": diff_audit(frames["Solar"], frames["Wind"]),
                    "solar_hydro": diff_audit(
                        frames["Solar"], frames["Hydroelectric"]
                    ),
                    "wind_hydro": diff_audit(
                        frames["Wind"], frames["Hydroelectric"]
                    ),
                }

            if spec.probe_id == Q3:
                browser.execute(_click(985, 884, "CALIBRATION_CONFIRM_FINAL"))
                done = _capture(browser, directory / "done.png")
                receipts = app.receipts_since(0)
                expected_success = spec.inherited_entity == "Solar"
            else:
                back = browser.execute(
                    ParsedAction("PRESS_BACK", (), "CALIBRATION_BROWSER_BACK")
                )
                back_receipt = app.mark_browser_back("review", "retry_decision")
                retry = _capture(browser, directory / "retry.png")
                # In the invalidation treatment deliberately reselect the previous
                # card.  A real server receipt proves that the UI did not disable it.
                retry_entity = (
                    spec.inherited_entity
                    if spec.probe_id == Q4
                    and spec.feedback_spec_id == PHASE2_BRANCH_INVALIDATION
                    else "Solar"
                )
                position = display_tokens.index(entity_to_token[retry_entity])
                coordinate = (
                    _feedback_choice_coordinate(position)
                    if app._review_feedback_html(  # noqa: SLF001
                        entity_to_token[spec.inherited_entity], retry=True
                    )
                    else _evaluator_choice_coordinate(position)
                )
                browser.execute(
                    _click(*coordinate, f"CALIBRATION_RETRY_{retry_entity.upper()}")
                )
                final = _capture(browser, directory / "final_review.png")
                browser.execute(_click(985, 884, "CALIBRATION_CONFIRM_RETRY"))
                done = _capture(browser, directory / "done.png")
                receipts = app.receipts_since(0)
                expected_success = retry_entity == "Solar"
                if (
                    back.from_url.endswith("/review") is False
                    or back.to_url.endswith("/decision") is False
                    or back_receipt.get("kind") != "browser_back"
                ):
                    raise ValueError("calibration Back did not produce a real transition")

            submissions = [row for row in receipts if row.get("kind") == "submission"]
            score = None
            if len(submissions) == 1:
                submission = submissions[0]
                score = scorer.score(
                    submission_id=f"phase2-calibration:{spec.key}",
                    pair_group_id=str(case["pair_group_id"]),
                    task_instance_id=str(case["arms"][spec.arm]["task_instance_id"]),
                    arm=spec.arm,
                    choice_token=str(submission["choice_token"]),
                    control_position=int(submission["control_position"]),
                ).to_dict()
            fixture_passed = bool(
                fixture_diffs is None
                or all(
                    value["raw_diff_within_mask"]
                    and value["model_448_diff_within_mask"]
                    for value in fixture_diffs.values()
                )
            )
            passed = bool(
                leak["passed"]
                and fixture_passed
                and score is not None
                and score["success"] is expected_success
                and app.snapshot()["visible_state"] == "submitted"
                and (
                    spec.probe_id != Q4
                    or spec.feedback_spec_id != PHASE2_BRANCH_INVALIDATION
                    or any(
                        row.get("kind") == "selection"
                        and row.get("from_state") == "retry_decision"
                        and row.get("choice_token")
                        == entity_to_token[spec.inherited_entity]
                        for row in receipts
                    )
                )
            )
            return {
                "passed": passed,
                "spec": spec.to_dict(),
                "intervention": intervention,
                "handoff": handoff,
                "retry": retry if spec.probe_id != Q3 else None,
                "final_review": final if spec.probe_id != Q3 else handoff,
                "done": done,
                "feedback_leak_audit": leak,
                "fixture_diff_audits": fixture_diffs,
                "receipts": receipts,
                "scorer_record": score,
                "expected_scorer_success": expected_success,
            }
    finally:
        if browser is not None:
            browser.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument(
        "--browser-backend",
        choices=("playwright", "selenium-firefox"),
        default="selenium-firefox",
    )
    parser.add_argument("--browser-executable")
    parser.add_argument(
        "--firefox-binary",
        default="/tmp/gui-reflection-firefox/usr/lib/firefox/firefox",
    )
    parser.add_argument(
        "--geckodriver", default="/tmp/gui-reflection-firefox/usr/bin/geckodriver"
    )
    parser.add_argument(
        "--firefox-library-path",
        default=(
            "/tmp/gui-reflection-firefox/usr/lib/x86_64-linux-gnu:"
            "/tmp/gui-reflection-firefox/usr/lib/firefox"
        ),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--action-wait-ms", type=int, default=150)
    parser.add_argument("--long-press-ms", type=int, default=800)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = (args.output_root / f"env008_phase2_calibration_{stamp}").resolve()
    root.mkdir(parents=True, exist_ok=False)
    canonical_case = load_authoritative_case(task_set="smoke17", slug="env008")
    factory = build_browser_factory(args)
    results: dict[str, Any] = {}
    for index, spec in enumerate(_unique_specs()):
        key = f"{index:02d}_{spec.key}"
        results[key] = _calibrate(
            spec=spec,
            canonical_case=canonical_case,
            browser_factory=factory,
            directory=root / "cells" / key,
        )
    report = {
        "record_type": "env008_phase2_model_free_calibration",
        "cell_count": len(results),
        "all_passed": all(row["passed"] for row in results.values()),
        "results": results,
    }
    write_json(root / "report.json", report)
    print(str(root))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
