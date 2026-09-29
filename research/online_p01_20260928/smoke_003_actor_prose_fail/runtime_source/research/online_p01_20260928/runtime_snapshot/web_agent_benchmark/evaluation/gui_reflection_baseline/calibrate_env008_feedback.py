#!/usr/bin/env python3
"""Real-Firefox calibration of env008 L2 F1/F3_pre feedback and Browser Back."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.request import ProxyHandler, build_opener

from .actions import ParsedAction
from .calibrate_env008_phase1 import (
    _capture,
    _click,
    _make_app,
    _position_for_token,
    _token_for_action,
)
from .run_targeted_recovery_pilot import (
    _evaluator_choice_coordinate,
    _wait_for_initial_chart,
    build_browser_factory,
    load_authoritative_case,
    write_json,
)
from .run_inherited_error_pilot import (
    approved_f2_record,
    build_registry as build_inherited_registry,
)
from .targeted_recovery import (
    F1_CHECKLIST,
    F2_AUDITED_VALUES,
    F3_PRE_REATTEMPT_CONTRADICTION,
    TargetedRecoveryRegistry,
)
from .targeted_recovery_app import ManagedCompactRecoveryServer, TargetedPathPolicy
from .targeted_recovery_layout import derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator


LAYOUT_ID = "cyclic_shift_2"
FORBIDDEN_ANSWER_FRAGMENTS = (
    "solar",
    "wind",
    "hydro",
    "41.2",
    "29.8",
    "18.5",
    "choice_",
    "correct action",
    "misleading action",
    "routing option 1",
    "routing option 2",
    "routing option 3",
)


class _FeedbackRegionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.regions: list[dict[str, Any]] = []
        self._depth = 0
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if self._current is None and "data-feedback-region" in attr_map:
            self._current = {
                "region": attr_map["data-feedback-region"],
                "attributes": [f"{name}={value or ''}" for name, value in attrs],
                "text_parts": [],
            }
            self._depth = 1
        elif self._current is not None:
            self._depth += 1
            self._current["attributes"].extend(
                f"{name}={value or ''}" for name, value in attrs
            )

    def handle_endtag(self, _tag: str) -> None:
        if self._current is None:
            return
        self._depth -= 1
        if self._depth == 0:
            self._current["text"] = " ".join(
                part.strip()
                for part in self._current.pop("text_parts")
                if part.strip()
            )
            self.regions.append(self._current)
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text_parts"].append(data)


def _read_page(url: str) -> str:
    opener = build_opener(ProxyHandler({}))
    with opener.open(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _evidence_retry_choice_coordinate(control_position: int) -> tuple[int, int]:
    if control_position not in {0, 1, 2}:
        raise ValueError("feedback calibration expects exactly three route cards")
    return 985, 613 + 109 * control_position


def _feedback_regions(html: str) -> list[dict[str, Any]]:
    parser = _FeedbackRegionParser()
    parser.feed(html)
    return parser.regions


def _leaks(regions: list[dict[str, Any]], evidence_level: str) -> list[str]:
    pieces: list[str] = []
    for region in regions:
        pieces.extend(
            [
                str(region.get("region", "")),
                str(region.get("text", "")),
                *[str(value) for value in region.get("attributes", [])],
            ]
        )
    scoped = " ".join(pieces).casefold()
    forbidden = (
        (
            "maximum",
            "correct",
            "choose solar",
            "choice_",
            "expected_action_id",
            "misleading",
            "control position",
            "reviewed_by",
            "record_id",
            "agent_cross_checked",
        )
        if evidence_level == F2_AUDITED_VALUES
        else FORBIDDEN_ANSWER_FRAGMENTS
    )
    return [term for term in forbidden if term in scoped]


def _calibrate_cell(
    *,
    case: Mapping[str, Any],
    arm: str,
    evidence_level: str,
    validator: CanonicalOutcomeValidator,
    scorer: CanonicalSubmissionScorer,
    registry: TargetedRecoveryRegistry,
    evidence_record_id: str | None,
    browser_factory: Any,
    directory: Path,
) -> dict[str, Any]:
    app = _make_app(
        case=case,
        arm=arm,
        workflow_mode="feedback_retry",
        evidence_level=evidence_level,
        evidence_record_id=evidence_record_id,
        registry=registry,
    )
    wind_action_id = str(case["runner_only"]["misleading_action_ids"][0])
    solar_action_id = str(case["runner_only"]["expected_action_id"])
    wind_token = _token_for_action(case, wind_action_id)
    solar_token = _token_for_action(case, solar_action_id)
    wind_position = _position_for_token(case, wind_token)
    solar_position = _position_for_token(case, solar_token)
    outcome_record: dict[str, Any] | None = None
    browser_back_receipt: dict[str, Any] | None = None
    browser = None
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            browser.execute(
                _click(*_evaluator_choice_coordinate(wind_position), "SELECT_WIND")
            )
            if evidence_level == F3_PRE_REATTEMPT_CONTRADICTION:
                record = validator.validate(
                    pair_group_id=str(case["pair_group_id"]),
                    task_instance_id=str(case["arms"][arm]["task_instance_id"]),
                    arm=arm,
                    choice_token=wind_token,
                    control_position=wind_position,
                )
                outcome_record = record.to_dict()
                app.set_outcome_feedback(
                    record_id=record.outcome_record_id,
                    choice_token=wind_token,
                    contradiction=record.contradiction,
                )
                browser.reload()
            review = _capture(browser, directory / "00_review.png")
            review_regions = _feedback_regions(_read_page(review["url"]))

            back_execution = browser.execute(
                ParsedAction("PRESS_BACK", (), "CALIBRATION_BROWSER_BACK")
            )
            browser_back_receipt = app.mark_browser_back("review", "retry_decision")
            retry = _capture(browser, directory / "01_retry.png")
            retry_regions = _feedback_regions(_read_page(retry["url"]))

            browser.execute(
                _click(
                    *_evidence_retry_choice_coordinate(solar_position),
                    "SELECT_SOLAR",
                )
            )
            final_review = _capture(browser, directory / "02_final_review.png")
            final_html = _read_page(final_review["url"])
            final_regions = _feedback_regions(final_html)
            final_snapshot = app.snapshot()
            browser.execute(_click(985, 884, "CONFIRM_SOLAR"))
            done = _capture(browser, directory / "03_done.png")
    finally:
        if browser is not None:
            browser.close()

    receipts = app.receipts_since(0)
    submission_receipts = [
        row for row in receipts if row.get("kind") == "submission"
    ]
    scorer_record: dict[str, Any] | None = None
    if len(submission_receipts) == 1:
        submission = submission_receipts[0]
        scorer_record = scorer.score(
            submission_id=(
                f"feedback-calibration:{case['pair_group_id']}:"
                f"{arm}:{evidence_level}"
            ),
            pair_group_id=str(case["pair_group_id"]),
            task_instance_id=str(case["arms"][arm]["task_instance_id"]),
            arm=arm,
            choice_token=str(submission["choice_token"]),
            control_position=int(submission["control_position"]),
        ).to_dict()
    expected_region = (
        "checklist"
        if evidence_level == F1_CHECKLIST
        else "reviewed-values"
        if evidence_level == F2_AUDITED_VALUES
        else "outcome"
    )
    review_region_names = [str(row["region"]) for row in review_regions]
    retry_region_names = [str(row["region"]) for row in retry_regions]
    final_forbidden_polarity = any(
        fragment in final_html.casefold()
        for fragment in (
            "independent outcome check",
            "does not agree",
            "conflicts with",
            "consistent with",
        )
    )
    f2_text_complete = evidence_level != F2_AUDITED_VALUES or (
        len(review_regions) == 1
        and len(retry_regions) == 1
        and all(
            fragment in str(review_regions[0].get("text", ""))
            and fragment in str(retry_regions[0].get("text", ""))
            for fragment in (
                "Solar — 41.2%",
                "Wind — 29.8%",
                "Hydroelectric — 18.5%",
                "Use these reviewed values together with the task instruction",
            )
        )
    )
    passed = bool(
        review_region_names == [expected_region]
        and retry_region_names == [expected_region]
        and not _leaks(review_regions, evidence_level)
        and not _leaks(retry_regions, evidence_level)
        and f2_text_complete
        and final_regions == []
        and not final_forbidden_polarity
        and final_snapshot["outcome_record_id"] is None
        and final_snapshot["outcome_choice_token"] is None
        and final_snapshot["outcome_contradiction"] is None
        and final_snapshot["visible_state"] == "final_review"
        and app.snapshot()["visible_state"] == "submitted"
        and browser_back_receipt.get("kind") == "browser_back"
        and back_execution.from_url.endswith("/review")
        and back_execution.to_url.endswith("/decision")
        and [row.get("kind") for row in receipts]
        == ["selection", "browser_back", "selection", "submission"]
        and receipts[2].get("choice_token") == solar_token
        and receipts[2].get("control_position") == solar_position
        and receipts[3].get("choice_token") == solar_token
        and receipts[3].get("control_position") == solar_position
        and scorer_record is not None
        and scorer_record["selected_action_id"] == solar_action_id
        and scorer_record["success"] is True
        and (
            evidence_level != F3_PRE_REATTEMPT_CONTRADICTION
            or (
                outcome_record is not None
                and outcome_record["contradiction"] is True
            )
        )
    )
    return {
        "passed": passed,
        "evidence_level": evidence_level,
        "review_frame": review,
        "retry_frame": retry,
        "final_review_frame": final_review,
        "done_frame": done,
        "review_regions": review_regions,
        "retry_regions": retry_regions,
        "final_regions": final_regions,
        "review_leaks": _leaks(review_regions, evidence_level),
        "retry_leaks": _leaks(retry_regions, evidence_level),
        "final_forbidden_polarity": final_forbidden_polarity,
        "f2_text_complete": f2_text_complete,
        "final_snapshot_before_confirm": final_snapshot,
        "browser_back_receipt": browser_back_receipt,
        "browser_back_execution": {
            "from_url": back_execution.from_url,
            "to_url": back_execution.to_url,
            "executed_coordinates": back_execution.executed_coordinates,
        },
        "outcome_record": outcome_record,
        "receipts": receipts,
        "scorer_record": scorer_record,
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
    case = derive_layout_case(canonical_case, layout_id=LAYOUT_ID)
    validator = CanonicalOutcomeValidator(
        task_set=args.task_set, slug=args.slug, layout_id=LAYOUT_ID
    )
    scorer = CanonicalSubmissionScorer(
        task_set=args.task_set, slug=args.slug, layout_id=LAYOUT_ID
    )
    registry = build_inherited_registry(case, LAYOUT_ID)
    f2_record = approved_f2_record(case, layout_id=LAYOUT_ID)
    browser_factory = build_browser_factory(args)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root.resolve() / f"env008_feedback_calibration_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=False)
    cells: dict[str, Any] = {}
    for arm in ("official", "clean"):
        for evidence_level in (
            F1_CHECKLIST,
            F2_AUDITED_VALUES,
            F3_PRE_REATTEMPT_CONTRADICTION,
        ):
            key = f"{arm}_{evidence_level}"
            cells[key] = _calibrate_cell(
                case=case,
                arm=arm,
                evidence_level=evidence_level,
                validator=validator,
                scorer=scorer,
                registry=registry,
                evidence_record_id=(
                    f2_record["record_id"]
                    if evidence_level == F2_AUDITED_VALUES
                    else None
                ),
                browser_factory=browser_factory,
                directory=output_dir / key,
            )
    final_page_identity = {}
    for arm in ("official", "clean"):
        final_hashes = {
            cells[f"{arm}_{level}"]["final_review_frame"]["sha256"]
            for level in (
                F1_CHECKLIST,
                F2_AUDITED_VALUES,
                F3_PRE_REATTEMPT_CONTRADICTION,
            )
        }
        final_page_identity[arm] = len(final_hashes) == 1
    report = {
        "record_type": "env008_l2_feedback_browser_calibration",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "layout_id": LAYOUT_ID,
        "coordinate_only_agent_actions": True,
        "evaluator_scoped_html_leakage_audit": True,
        "final_page_f1_f3_pre_pixel_identical": final_page_identity,
        "passed": all(row["passed"] for row in cells.values())
        and all(final_page_identity.values()),
        "cells": cells,
    }
    write_json(output_dir / "feedback_calibration_report.json", report)
    print(json.dumps({"output_dir": str(output_dir), "passed": report["passed"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
