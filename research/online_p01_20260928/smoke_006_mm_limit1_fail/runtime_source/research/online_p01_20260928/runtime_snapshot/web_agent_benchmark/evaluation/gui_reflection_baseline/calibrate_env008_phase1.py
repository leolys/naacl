#!/usr/bin/env python3
"""Model-free, real-browser calibration for the env008 phase-1 layouts.

The calibration deliberately uses only fixed screen coordinates and the
evaluator-owned canonical scorer.  It proves that each role-blind layout admits
Wind -> Revise -> Solar -> Confirm, rejects a submitted Wind choice, and keeps
the workflow-on/off initial screenshots pixel-identical within an arm.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .actions import ParsedAction
from .build_targeted_recovery_cases import (
    model_visible_projection,
    model_visible_review_projection,
)
from .formal_path_policy import REPO_ROOT
from .run_targeted_recovery_pilot import (
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    _evaluator_choice_coordinate,
    _wait_for_initial_chart,
    build_browser_factory,
    load_authoritative_case,
    write_json,
)
from .targeted_recovery import (
    F0_NEUTRAL_RECHECK,
    FEEDBACK_RETRY,
    OUTCOME_FEEDBACK_LEVELS,
    SINGLE_ATTEMPT,
)
from .targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    TargetedPathPolicy,
)
from .targeted_recovery_layout import LAYOUT_IDS, derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _click(x: int, y: int, label: str) -> ParsedAction:
    return ParsedAction("CLICK", (x, y), f"CALIBRATION_{label}")


def _token_for_action(case: Mapping[str, Any], action_id: str) -> str:
    matches = [
        token
        for token, mapped_action in case["runner_only"][
            "choice_token_to_action_id"
        ].items()
        if mapped_action == action_id
    ]
    if len(matches) != 1:
        raise ValueError(f"action {action_id!r} does not resolve to one token")
    return str(matches[0])


def _position_for_token(case: Mapping[str, Any], token: str) -> int:
    tokens = tuple(
        str(card["choice_token"])
        for card in case["model_visible_shared"]["action_cards"]
    )
    if tokens.count(token) != 1:
        raise ValueError(f"token {token!r} does not have one visible position")
    return tokens.index(token)


def _capture(browser: Any, path: Path) -> dict[str, Any]:
    frame = browser.screenshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(frame.png)
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(frame.png),
        "width": frame.width,
        "height": frame.height,
        "url": frame.url,
    }


def _submission_receipt(app: CompactRecoveryApp) -> Mapping[str, Any]:
    receipts = [row for row in app.receipts_since(0) if row.get("kind") == "submission"]
    if len(receipts) != 1:
        raise ValueError("calibration expected exactly one submission receipt")
    return receipts[0]


def _score_submission(
    *,
    scorer: CanonicalSubmissionScorer,
    case: Mapping[str, Any],
    arm: str,
    receipt: Mapping[str, Any],
    submission_id: str,
) -> dict[str, Any]:
    record = scorer.score(
        submission_id=submission_id,
        pair_group_id=str(case["pair_group_id"]),
        task_instance_id=str(case["arms"][arm]["task_instance_id"]),
        arm=arm,
        choice_token=str(receipt["choice_token"]),
        control_position=int(receipt["control_position"]),
    )
    return record.to_dict()


def _make_app(
    *,
    case: Mapping[str, Any],
    arm: str,
    workflow_mode: str,
    evidence_level: str = F0_NEUTRAL_RECHECK,
    evidence_record_id: str | None = None,
    registry: Any = None,
) -> CompactRecoveryApp:
    if workflow_mode == FEEDBACK_RETRY:
        projection = model_visible_review_projection(
            dict(case),
            arm,
            evidence_level=evidence_level,
            evidence_record_id=evidence_record_id,
            registry=registry,
        )
    else:
        projection = model_visible_projection(dict(case), arm)
    return CompactRecoveryApp(
        visible_case=projection,
        repository_root=REPO_ROOT,
        chart_path=(REPO_ROOT / str(projection["chart_path"])).resolve(),
        workflow_mode=workflow_mode,
        inherited_selection=workflow_mode == FEEDBACK_RETRY,
        outcome_feedback_enabled=evidence_level in OUTCOME_FEEDBACK_LEVELS,
    )


def _initial_frame(
    *,
    case: Mapping[str, Any],
    arm: str,
    workflow_mode: str,
    browser_factory: Any,
    path: Path,
) -> dict[str, Any]:
    app = _make_app(case=case, arm=arm, workflow_mode=workflow_mode)
    browser = None
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            frame = _capture(browser, path)
            snapshot = app.snapshot()
    finally:
        if browser is not None:
            browser.close()
    if snapshot["visible_state"] != "initial_decision":
        raise ValueError("initial parity capture left the initial decision state")
    return {"frame": frame, "snapshot": snapshot}


def _recovery_path(
    *,
    case: Mapping[str, Any],
    arm: str,
    scorer: CanonicalSubmissionScorer,
    browser_factory: Any,
    directory: Path,
) -> dict[str, Any]:
    app = _make_app(case=case, arm=arm, workflow_mode=FEEDBACK_RETRY)
    wind_action_id = str(case["runner_only"]["misleading_action_ids"][0])
    solar_action_id = str(case["runner_only"]["expected_action_id"])
    wind_token = _token_for_action(case, wind_action_id)
    solar_token = _token_for_action(case, solar_action_id)
    wind_position = _position_for_token(case, wind_token)
    solar_position = _position_for_token(case, solar_token)
    browser = None
    snapshots: list[dict[str, Any]] = []
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            initial = _capture(browser, directory / "00_initial.png")
            snapshots.append(app.snapshot())

            browser.execute(
                _click(*_evaluator_choice_coordinate(wind_position), "SELECT_WIND")
            )
            review = _capture(browser, directory / "01_wind_review.png")
            snapshots.append(app.snapshot())

            browser.execute(_click(985, 884, "REVISE"))
            retry = _capture(browser, directory / "02_retry.png")
            snapshots.append(app.snapshot())

            browser.execute(
                _click(*_evaluator_choice_coordinate(solar_position), "SELECT_SOLAR")
            )
            final_review = _capture(browser, directory / "03_solar_final_review.png")
            snapshots.append(app.snapshot())

            browser.execute(_click(985, 884, "CONFIRM_SOLAR"))
            done = _capture(browser, directory / "04_done.png")
            snapshots.append(app.snapshot())
    finally:
        if browser is not None:
            browser.close()

    expected_states = (
        "initial_decision",
        "review",
        "retry_decision",
        "final_review",
        "submitted",
    )
    observed_states = tuple(str(row["visible_state"]) for row in snapshots)
    receipt = _submission_receipt(app)
    score = _score_submission(
        scorer=scorer,
        case=case,
        arm=arm,
        receipt=receipt,
        submission_id=f"calibration:{case['pair_group_id']}:{arm}:solar",
    )
    passed = bool(
        observed_states == expected_states
        and receipt["choice_token"] == solar_token
        and receipt["control_position"] == solar_position
        and score["selected_action_id"] == solar_action_id
        and score["success"] is True
    )
    return {
        "passed": passed,
        "wind_token": wind_token,
        "wind_position": wind_position,
        "solar_token": solar_token,
        "solar_position": solar_position,
        "observed_states": list(observed_states),
        "expected_states": list(expected_states),
        "initial_frame": initial,
        "review_frame": review,
        "retry_frame": retry,
        "final_review_frame": final_review,
        "done_frame": done,
        "receipts": app.receipts_since(0),
        "scorer_record": score,
    }


def _wrong_submission_path(
    *,
    case: Mapping[str, Any],
    arm: str,
    scorer: CanonicalSubmissionScorer,
    browser_factory: Any,
    directory: Path,
) -> dict[str, Any]:
    app = _make_app(case=case, arm=arm, workflow_mode=FEEDBACK_RETRY)
    wind_action_id = str(case["runner_only"]["misleading_action_ids"][0])
    wind_token = _token_for_action(case, wind_action_id)
    wind_position = _position_for_token(case, wind_token)
    browser = None
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            browser.execute(
                _click(*_evaluator_choice_coordinate(wind_position), "SELECT_WIND")
            )
            review = _capture(browser, directory / "00_wind_review.png")
            browser.execute(_click(985, 788, "CONFIRM_WIND"))
            done = _capture(browser, directory / "01_done.png")
    finally:
        if browser is not None:
            browser.close()
    receipt = _submission_receipt(app)
    score = _score_submission(
        scorer=scorer,
        case=case,
        arm=arm,
        receipt=receipt,
        submission_id=f"calibration:{case['pair_group_id']}:{arm}:wind",
    )
    return {
        "passed": bool(
            receipt["choice_token"] == wind_token
            and receipt["control_position"] == wind_position
            and score["selected_action_id"] == wind_action_id
            and score["success"] is False
            and app.snapshot()["visible_state"] == "submitted"
        ),
        "review_frame": review,
        "done_frame": done,
        "receipts": app.receipts_since(0),
        "scorer_record": score,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default="smoke17")
    parser.add_argument("--slug", default="env008")
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
        "--geckodriver",
        default="/tmp/gui-reflection-firefox/usr/bin/geckodriver",
    )
    parser.add_argument(
        "--firefox-library-path",
        default=(
            "/tmp/gui-reflection-firefox/usr/lib/x86_64-linux-gnu:"
            "/tmp/gui-reflection-firefox/usr/lib/firefox"
        ),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--action-wait-ms", type=int, default=250)
    parser.add_argument("--long-press-ms", type=int, default=800)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    canonical_case = load_authoritative_case(task_set=args.task_set, slug=args.slug)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root.resolve() / f"env008_phase1_calibration_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=False)
    browser_factory = build_browser_factory(args)
    layouts: dict[str, Any] = {}

    for layout_id in LAYOUT_IDS:
        case = derive_layout_case(canonical_case, layout_id=layout_id)
        scorer = CanonicalSubmissionScorer(
            task_set=args.task_set, slug=args.slug, layout_id=layout_id
        )
        arms: dict[str, Any] = {}
        for arm in ("official", "clean"):
            arm_dir = output_dir / layout_id / arm
            recovery = _recovery_path(
                case=case,
                arm=arm,
                scorer=scorer,
                browser_factory=browser_factory,
                directory=arm_dir / "recovery",
            )
            off_initial = _initial_frame(
                case=case,
                arm=arm,
                workflow_mode=SINGLE_ATTEMPT,
                browser_factory=browser_factory,
                path=arm_dir / "workflow_off_initial.png",
            )
            wrong = _wrong_submission_path(
                case=case,
                arm=arm,
                scorer=scorer,
                browser_factory=browser_factory,
                directory=arm_dir / "wrong_submission",
            )
            initial_pixel_identical = (
                recovery["initial_frame"]["sha256"]
                == off_initial["frame"]["sha256"]
            )
            arms[arm] = {
                "passed": bool(
                    recovery["passed"]
                    and wrong["passed"]
                    and initial_pixel_identical
                ),
                "initial_workflow_on_off_pixel_identical": initial_pixel_identical,
                "recovery": recovery,
                "workflow_off_initial": off_initial,
                "wrong_submission": wrong,
            }
        layouts[layout_id] = {
            "display_order": list(case["runner_only"]["display_order"]),
            "display_tokens": [
                str(card["choice_token"])
                for card in case["model_visible_shared"]["action_cards"]
            ],
            "passed": all(row["passed"] for row in arms.values()),
            "arms": arms,
        }

    report = {
        "record_type": "env008_phase1_model_free_calibration",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "task_set": args.task_set,
        "slug": args.slug,
        "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
        "coordinate_only": True,
        "passed": all(row["passed"] for row in layouts.values()),
        "layouts": layouts,
    }
    write_json(output_dir / "calibration_report.json", report)
    print(json.dumps({"output_dir": str(output_dir), "passed": report["passed"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
