#!/usr/bin/env python3
"""Run the frozen env008 phase-2 GUI-Reflection mechanism panel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
import uuid

from PIL import Image, ImageChops, ImageDraw

from .actions import ActionParseError, ParsedAction
from .agent_runtime import (
    AgentClient,
    AgentRuntimeError,
    FixtureHistoryFrame,
    HttpAgentClient,
    ManagedAgentServer,
)
from .browser_executor import (
    BrowserExecutionError,
    UnsupportedWebAction,
)
from .build_targeted_recovery_cases import (
    model_visible_projection,
    model_visible_review_projection,
)
from .env008_phase2_protocol import (
    PHASE_ID,
    Q1,
    Q2,
    Q3,
    Q4,
    UI_BUILD_ID,
    Phase2CellSpec,
    direct_behavior_summary,
    phase2_cells,
)
from .formal_path_policy import NavigationBlocked, REPO_ROOT
from .phase2_history_fixture import (
    BOLD_FONT,
    REGULAR_FONT,
    build_proposition_frame,
    diff_audit,
    official_history_input_sha256,
)
from .run_targeted_recovery_pilot import (
    CHECKPOINT_ID,
    EXPECTED_MODEL_PATH,
    EXPECTED_OFFICIAL_REPO,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    _evaluator_choice_coordinate,
    _execution_dict,
    _wait_for_initial_chart,
    action_agreement,
    build_browser_factory,
    load_authoritative_case,
    parse_final_action,
    utc_now,
    verify_health,
    write_json,
)
from .run_travel_pair import verify_agent_service
from .targeted_recovery import (
    F3_PRE_REATTEMPT_CONTRADICTION,
    FEEDBACK_RETRY,
)
from .targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    PHASE2_BRANCH_INVALIDATION,
    PHASE2_BRANCH_NEUTRAL_CONTROL,
    TargetedPathPolicy,
)
from .targeted_recovery_layout import derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator


BRANCH_REVIEW_FEEDBACK_MASK = (850, 445, 1240, 555)
BRANCH_RETRY_FEEDBACK_MASK = (850, 348, 1240, 458)
BRANCH_REVIEW_PREVIOUS_LABEL_MASK = (850, 350, 1235, 435)
BRANCH_RETRY_PREVIOUS_LABEL_MASK = (920, 225, 1235, 300)


def append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _entity_maps(case: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    runner = case["runner_only"]
    action_ids = {
        "Solar": str(runner["expected_action_id"]),
        "Wind": str(runner["misleading_action_ids"][0]),
        "Hydroelectric": str(runner["neutral_action_ids"][0]),
    }
    raw_token_map = runner["choice_token_to_action_id"]
    token_pairs = (
        raw_token_map.items() if isinstance(raw_token_map, Mapping) else raw_token_map
    )
    token_to_action = {
        str(token): str(action_id) for token, action_id in token_pairs
    }
    action_to_token = {action_id: token for token, action_id in token_to_action.items()}
    entity_to_token = {
        entity: action_to_token[action_id] for entity, action_id in action_ids.items()
    }
    return action_ids, entity_to_token


def _projection(case: Mapping[str, Any], spec: Phase2CellSpec) -> dict[str, Any]:
    if spec.feedback_spec_id in {
        PHASE2_BRANCH_INVALIDATION,
        PHASE2_BRANCH_NEUTRAL_CONTROL,
    }:
        return {
            **model_visible_projection(dict(case), spec.arm),
            "review": {"feedback_spec_id": spec.feedback_spec_id},
        }
    return model_visible_review_projection(
        dict(case), spec.arm, evidence_level=spec.feedback_spec_id
    )


def _normalized_click_action(x: int, y: int) -> str:
    nx = next(value for value in range(1001) if value * VIEWPORT_WIDTH // 1000 == x)
    ny = next(value for value in range(1001) if value * VIEWPORT_HEIGHT // 1000 == y)
    return f"CLICK[[{nx}, {ny}]]"


def _click(x: int, y: int, raw: str) -> ParsedAction:
    return ParsedAction("CLICK", (x, y), raw)


def _feedback_leak_audit(app: CompactRecoveryApp, token: str) -> dict[str, Any]:
    html = app._review_feedback_html(token, retry=False)  # noqa: SLF001
    folded = html.casefold()
    forbidden = (
        "solar",
        "wind",
        "hydro",
        "41.2",
        "29.8",
        "18.5",
        "choice_",
        "correct",
        "misleading",
        "control_position",
        "expected_action_id",
    )
    return {
        "scoped_feedback_html": html,
        "forbidden_fragments": [value for value in forbidden if value in folded],
        "passed": not any(value in folded for value in forbidden),
    }


def _enrich_receipt(
    receipt: Mapping[str, Any],
    *,
    token_to_entity: Mapping[str, str],
) -> dict[str, Any]:
    row = dict(receipt)
    token = row.get("choice_token")
    if isinstance(token, str) and token in token_to_entity:
        row["selected_entity"] = token_to_entity[token]
    return row


def _setup_intervention(
    *,
    app: CompactRecoveryApp,
    browser: Any,
    case: Mapping[str, Any],
    spec: Phase2CellSpec,
    cell_dir: Path,
    run_id: str,
    action_ids: Mapping[str, str],
    entity_to_token: Mapping[str, str],
    validator: CanonicalOutcomeValidator | None,
) -> tuple[dict[str, Any], bytes | None, tuple[int, int] | None]:
    screenshots = cell_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    display_tokens = [
        str(card["choice_token"]) for card in case["model_visible_shared"]["action_cards"]
    ]
    token_to_entity = {token: entity for entity, token in entity_to_token.items()}
    before = browser.screenshot()
    before_path = screenshots / "evaluator_before_setup.png"
    before_path.write_bytes(before.png)
    receipt_offset = app.receipt_count()
    h1_png: bytes | None = before.png if spec.probe_id == Q2 else None
    h1_annotation: tuple[int, int] | None = None
    setup_executions: list[dict[str, Any]] = []

    def choose(entity: str, label: str) -> None:
        nonlocal h1_annotation
        token = entity_to_token[entity]
        position = display_tokens.index(token)
        x, y = _evaluator_choice_coordinate(position)
        execution = browser.execute(_click(x, y, label))
        setup_executions.append(_execution_dict(execution))
        if spec.probe_id == Q2:
            h1_annotation = (x, y)

    if spec.probe_id == Q3:
        initial = "Wind" if spec.inherited_entity == "Solar" else "Hydroelectric"
        choose(initial, f"EVALUATOR_COMPLETION_SETUP_{initial.upper()}")
        revise = browser.execute(_click(985, 884, "EVALUATOR_COMPLETION_REVISE"))
        setup_executions.append(_execution_dict(revise))
        choose(
            spec.inherited_entity,
            f"EVALUATOR_COMPLETION_FINAL_{spec.inherited_entity.upper()}",
        )
        expected_state = "final_review"
        source = "evaluator_completion_fixture"
        semantics = "completion_only_final_review"
    else:
        choose(spec.inherited_entity, "EVALUATOR_INHERITED_SELECTION")
        expected_state = "review"
        source = (
            "evaluator_trajectory_fixture"
            if spec.probe_id == Q2
            else "evaluator_previous_item_fixture"
            if spec.probe_id == Q4
            else "evaluator_f3_fixture"
            if spec.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION
            else "evaluator_inherited_wind_fixture"
        )
        semantics = (
            "external_proposition_and_inherited_wind_action"
            if spec.probe_id == Q2
            else "previous_item_branch_probe"
            if spec.probe_id == Q4
            else "binary_outcome_signal_on_inherited_wind"
            if spec.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION
            else "neutral_recheck_on_inherited_wind"
        )

    outcome_record: dict[str, Any] | None = None
    if validator is not None:
        token = entity_to_token[spec.inherited_entity]
        position = display_tokens.index(token)
        record = validator.validate(
            pair_group_id=str(case["pair_group_id"]),
            task_instance_id=str(case["arms"][spec.arm]["task_instance_id"]),
            arm=spec.arm,
            choice_token=token,
            control_position=position,
        )
        outcome_record = record.to_dict()
        app.set_outcome_feedback(
            record_id=record.outcome_record_id,
            choice_token=token,
            contradiction=record.contradiction,
        )
        browser.reload()

    snapshot = app.snapshot()
    setup_receipts = [
        _enrich_receipt(row, token_to_entity=token_to_entity)
        for row in app.receipts_since(receipt_offset)
    ]
    if (
        snapshot["visible_state"] != expected_state
        or snapshot["current_choice_token"] != entity_to_token[spec.inherited_entity]
        or snapshot["submitted"] is not False
    ):
        raise ValueError("evaluator setup did not establish the declared handoff state")
    expected_kinds = (
        ["selection", "revision", "selection"]
        if spec.probe_id == Q3
        else ["selection"]
    )
    if [row.get("kind") for row in setup_receipts] != expected_kinds:
        raise ValueError("evaluator setup UI transactions are incomplete")
    if spec.probe_id == Q3:
        initial_entity = "Wind" if spec.inherited_entity == "Solar" else "Hydroelectric"
        if (
            setup_receipts[0].get("selected_entity") != initial_entity
            or setup_receipts[0].get("from_state") != "initial_decision"
            or setup_receipts[1].get("from_state") != "review"
            or setup_receipts[1].get("to_state") != "retry_decision"
            or setup_receipts[2].get("selected_entity") != spec.inherited_entity
            or setup_receipts[2].get("from_state") != "retry_decision"
            or snapshot.get("selection_count") != 2
            or snapshot.get("reversal_count") != 1
            or not setup_executions[0]["from_url"].endswith("/decision")
            or not setup_executions[0]["to_url"].endswith("/review")
            or not setup_executions[1]["from_url"].endswith("/review")
            or not setup_executions[1]["to_url"].endswith("/decision")
            or not setup_executions[2]["from_url"].endswith("/decision")
            or not setup_executions[2]["to_url"].endswith("/review")
        ):
            raise ValueError("completion fixture chain does not join to final review")
    elif (
        setup_receipts[0].get("selected_entity") != spec.inherited_entity
        or setup_receipts[0].get("from_state") != "initial_decision"
        or snapshot.get("selection_count") != 1
        or snapshot.get("reversal_count") != 0
    ):
        raise ValueError("inherited handoff receipt does not join the declared action")

    recovery_eligible = bool(
        spec.probe_id in {Q1, Q2}
        or (spec.probe_id == Q4 and spec.inherited_entity == "Wind")
    )

    intervention = {
        "record_type": "env008_phase2_intervention",
        "intervention_id": f"intervention:{uuid.uuid4().hex}",
        "phase_id": PHASE_ID,
        "probe_id": spec.probe_id,
        "cell_key": spec.key,
        "condition_id": spec.key,
        "run_id": run_id,
        "pair_group_id": case["pair_group_id"],
        "task_instance_id": case["arms"][spec.arm]["task_instance_id"],
        "history_mode": spec.history_mode,
        "feedback_spec_id": spec.feedback_spec_id,
        "source": source,
        "intervention_semantics": semantics,
        "normalized_as_agent_reasoning": False,
        "normalized_as_agent_selection": False,
        "arm": spec.arm,
        "layout_id": spec.layout_id,
        "inherited_entity": spec.inherited_entity,
        "inherited_action_id": action_ids[spec.inherited_entity],
        "inherited_route_action_id": (
            action_ids["Wind"] if spec.probe_id == Q2 else None
        ),
        "completion_target_action_id": (
            action_ids[spec.inherited_entity] if spec.probe_id == Q3 else None
        ),
        "inherited_previous_action_id": (
            action_ids[spec.inherited_entity] if spec.probe_id == Q4 else None
        ),
        "inherited_previous_role": (
            "misleading" if spec.probe_id == Q4 and spec.inherited_entity == "Wind"
            else "neutral_or_irrelevant"
            if spec.probe_id == Q4
            else None
        ),
        "recorded_proposition_entity": spec.proposition_entity,
        "history_fixture_ownership": (
            "evaluator_trajectory_fixture" if spec.probe_id == Q2 else None
        ),
        "recovery_eligible": recovery_eligible,
        "pre_setup_screenshot_path": str(before_path.resolve()),
        "pre_setup_screenshot_sha256": sha256_bytes(before.png),
        "setup_executions": setup_executions,
        "setup_ui_receipts": setup_receipts,
        "outcome_validation": outcome_record,
        "post_setup_snapshot": snapshot,
    }
    return intervention, h1_png, h1_annotation


def _run_cell(
    *,
    spec: Phase2CellSpec,
    canonical_case: Mapping[str, Any],
    agent: AgentClient,
    browser_factory: Any,
    run_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    case = derive_layout_case(canonical_case, layout_id=spec.layout_id)
    action_ids, entity_to_token = _entity_maps(case)
    token_to_entity = {token: entity for entity, token in entity_to_token.items()}
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
    cell_dir = run_dir / "cells" / spec.key
    screenshots = cell_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    raw_path = cell_dir / "steps.jsonl"
    intervention_path = cell_dir / "intervention.json"
    scorer_path = cell_dir / "scorer_records.jsonl"
    agent_session_id = f"{PHASE_ID}|{run_id}"
    browser = None
    agent_reset_count = 0
    model_ui_receipts: list[dict[str, Any]] = []
    raw_steps: list[dict[str, Any]] = []
    scorer_rows: list[dict[str, Any]] = []
    fixture_receipt: dict[str, Any] | None = None
    status = "timeout"
    error: str | None = None
    first_screenshot_sha256: str | None = None
    first_action_raw: str | None = None
    parser_disagreements: list[int] = []
    intervention: dict[str, Any] | None = None
    submission_success: bool | None = None

    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            intervention, h1_png, h1_annotation = _setup_intervention(
                app=app,
                browser=browser,
                case=case,
                spec=spec,
                cell_dir=cell_dir,
                run_id=run_id,
                action_ids=action_ids,
                entity_to_token=entity_to_token,
                validator=validator,
            )
            model_receipt_offset = app.receipt_count()
            agent.reset(agent_session_id)
            agent_reset_count += 1

            if spec.probe_id == Q2:
                if not isinstance(agent, HttpAgentClient):
                    raise AgentRuntimeError("Q2 requires the receipt-owning HTTP client")
                if h1_png is None or h1_annotation is None:
                    raise ValueError("Q2 setup omitted the actual Wind decision frame")
                h0_png = build_proposition_frame(h1_png, str(spec.proposition_entity))
                h0_path = screenshots / "fixture_h0_proposition.png"
                h1_path = screenshots / "fixture_h1_wind_decision.png"
                h0_path.write_bytes(h0_png)
                h1_path.write_bytes(h1_png)
                fixture_actions = [
                    "PRESS_ENTER",
                    _normalized_click_action(*h1_annotation),
                ]
                fixture_descriptions = [
                    "Continue from the recorded source proposition.",
                    "Select the Wind routing option for provisional review.",
                ]
                fixture_id = (
                    f"fixture:{PHASE_ID}:{spec.arm}:{spec.proposition_entity}:"
                    f"{spec.history_mode}:{uuid.uuid4().hex}"
                )
                fixture_receipt = agent.prime_history_fixture(
                    fixture_id=fixture_id,
                    task_id=agent_session_id,
                    frames=[
                        FixtureHistoryFrame(
                            h0_png, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, None
                        ),
                        FixtureHistoryFrame(
                            h1_png,
                            VIEWPORT_WIDTH,
                            VIEWPORT_HEIGHT,
                            h1_annotation,
                        ),
                    ],
                    actions=fixture_actions,
                    action_descriptions=fixture_descriptions,
                )
                intervention["history_fixture"] = {
                    "receipt": fixture_receipt,
                    "h0_path": str(h0_path.resolve()),
                    "h1_path": str(h1_path.resolve()),
                    "actions": fixture_actions,
                    "action_descriptions": fixture_descriptions,
                    "expected_model_call_history_sha256": [
                        official_history_input_sha256(h0_png),
                        official_history_input_sha256(h1_png, h1_annotation),
                    ],
                }
                if spec.history_mode == "current_only":
                    agent.reset(agent_session_id)
                    agent_reset_count += 1

            leak_audit = _feedback_leak_audit(
                app, entity_to_token[spec.inherited_entity]
            )
            intervention["feedback_leak_audit"] = leak_audit
            write_json(intervention_path, intervention)

            for step_index in range(spec.max_steps):
                if spec.history_mode == "current_only" and step_index > 0:
                    agent.reset(agent_session_id)
                    agent_reset_count += 1
                frame = browser.screenshot()
                input_snapshot = app.snapshot()
                input_state = str(input_snapshot["visible_state"])
                screenshot_path = screenshots / f"step_{step_index:02d}.png"
                screenshot_path.write_bytes(frame.png)
                screenshot_sha = sha256_bytes(frame.png)
                if step_index == 0:
                    first_screenshot_sha256 = screenshot_sha
                step_result = agent.step(
                    frame.png,
                    str(projection["workflow_instruction"]),
                    agent_session_id,
                    frame.width,
                    frame.height,
                )
                if step_index == 0:
                    first_action_raw = step_result.action_raw
                receipt = step_result.receipt
                if not isinstance(receipt, dict):
                    raise AgentRuntimeError("phase-2 step has no service-owned receipt")
                if step_index == 0:
                    if spec.probe_id == Q2 and spec.history_mode == "native4":
                        fixture = intervention["history_fixture"]
                        if (
                            receipt.get("task_step_index") != 2
                            or receipt.get("history_image_count_before") != 2
                            or receipt.get("action_count_before") != 2
                            or receipt.get("history_image_sha256_before")
                            != fixture_receipt["history_rgb_sha256"]
                            or receipt.get("history_image_annotations_before")
                            != fixture_receipt["history_image_annotations"]
                            or receipt.get("action_history_sha256_before")
                            != fixture_receipt["action_history_sha256"]
                            or receipt.get("memory_empty_before") is not True
                            or receipt.get("model_call_input_image_sha256", [])[:2]
                            != fixture["expected_model_call_history_sha256"]
                        ):
                            raise AgentRuntimeError(
                                "Q2 native handoff does not match the exact fixture input"
                            )
                    else:
                        if (
                            receipt.get("task_step_index") != 0
                            or receipt.get("history_image_count_before") != 0
                            or receipt.get("action_count_before") != 0
                            or receipt.get("memory_empty_before") is not True
                        ):
                            raise AgentRuntimeError(
                                "phase-2 empty handoff retained model state"
                            )

                try:
                    final_action = parse_final_action(
                        step_result.action_raw, frame.width, frame.height
                    )
                    final_error = None
                except ActionParseError as exc:
                    final_action = None
                    final_error = str(exc)
                agrees = action_agreement(step_result.action, final_action)
                if not agrees:
                    parser_disagreements.append(step_index)

                raw_offset = app.receipt_count()
                execution = None
                execution_error = None
                back_error = None
                try:
                    execution = browser.execute(step_result.action)
                except (
                    UnsupportedWebAction,
                    NavigationBlocked,
                    BrowserExecutionError,
                ) as exc:
                    execution_error = str(exc)
                if (
                    execution is not None
                    and step_result.action.action_type == "PRESS_BACK"
                    and input_state == "review"
                    and execution.to_url.endswith("/decision")
                ):
                    try:
                        app.mark_browser_back("review", "retry_decision")
                    except ValueError as exc:
                        back_error = str(exc)
                ui_receipts = [
                    _enrich_receipt(row, token_to_entity=token_to_entity)
                    for row in app.receipts_since(raw_offset)
                ]
                model_ui_receipts.extend(ui_receipts)

                for ui in ui_receipts:
                    if ui.get("kind") != "submission":
                        continue
                    submission_id = f"submission:{run_id}:{ui['transaction_id']}"
                    score = scorer.score(
                        submission_id=submission_id,
                        pair_group_id=str(case["pair_group_id"]),
                        task_instance_id=str(case["arms"][spec.arm]["task_instance_id"]),
                        arm=spec.arm,
                        choice_token=str(ui["choice_token"]),
                        control_position=int(ui["control_position"]),
                    ).to_dict()
                    scorer_rows.append(score)
                    append_jsonl(scorer_path, score)
                    submission_success = bool(score["success"])

                row = {
                    "record_type": "env008_phase2_raw_step",
                    "phase_id": PHASE_ID,
                    "probe_id": spec.probe_id,
                    "cell_key": spec.key,
                    "run_id": run_id,
                    "step": step_index,
                    "input_state": input_state,
                    "input_snapshot": input_snapshot,
                    "screenshot_path": str(screenshot_path.resolve()),
                    "screenshot_sha256": screenshot_sha,
                    "model_receipt": receipt,
                    "action_raw": step_result.action_raw,
                    "action_description": step_result.action_description,
                    "official_action_parsed": step_result.action.as_dict(),
                    "final_action_parsed": (
                        final_action.as_dict() if final_action is not None else None
                    ),
                    "final_action_parse_error": final_error,
                    "parser_agreement": agrees,
                    "execution": (
                        _execution_dict(execution) if execution is not None else None
                    ),
                    "execution_error": execution_error,
                    "back_transition_error": back_error,
                    "ui_receipts": ui_receipts,
                    "post_action_snapshot": app.snapshot(),
                }
                raw_steps.append(row)
                append_jsonl(raw_path, row)

                if not agrees:
                    status = "parser_censored"
                    break
                if execution_error is not None or back_error is not None:
                    status = "invalid_run"
                    error = execution_error or back_error
                    break
                if execution is not None and execution.blocked_requests:
                    status = "invalid_run"
                    error = "navigation containment violation"
                    break
                if scorer_rows:
                    status = "submitted"
                    break
                if execution is not None and execution.terminal == "TASK_COMPLETE":
                    status = "agent_complete_without_submission"
                    break
                if execution is not None and execution.terminal == "TASK_IMPOSSIBLE":
                    status = "agent_impossible"
                    break
            else:
                status = "one_step_incomplete" if spec.probe_id == Q3 else "timeout"

            if app.receipt_count() < model_receipt_offset:
                raise ValueError("UI receipt stream moved backwards")
    except Exception as exc:
        status = "runner_error"
        error = repr(exc)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                if error is None:
                    status = "runner_error"
                    error = f"browser_close_failed:{exc!r}"
        if intervention is not None:
            write_json(intervention_path, intervention)

    behavior = direct_behavior_summary(
        spec=spec,
        action_ids_by_entity=action_ids,
        model_ui_receipts=model_ui_receipts,
        raw_steps=raw_steps,
        submission_success=submission_success,
    )
    summary = {
        "record_type": "env008_phase2_cell_summary",
        "phase_id": PHASE_ID,
        "probe_id": spec.probe_id,
        "cell_key": spec.key,
        "run_id": run_id,
        "reportable": False,
        "spec": spec.to_dict(),
        "pair_group_id": case["pair_group_id"],
        "task_instance_id": case["arms"][spec.arm]["task_instance_id"],
        "checkpoint_id": CHECKPOINT_ID,
        "ui_build_id": UI_BUILD_ID,
        "action_ids_by_entity": action_ids,
        "display_tokens": [
            str(card["choice_token"])
            for card in case["model_visible_shared"]["action_cards"]
        ],
        "status": status,
        "error": error,
        "agent_reset_count": agent_reset_count,
        "first_screenshot_sha256": first_screenshot_sha256,
        "first_action_raw": first_action_raw,
        "parser_disagreement_steps": parser_disagreements,
        "intervention_path": (
            str(intervention_path.resolve()) if intervention is not None else None
        ),
        "raw_steps_path": str(raw_path.resolve()),
        "scorer_records_path": (
            str(scorer_path.resolve()) if scorer_rows else None
        ),
        "model_ui_receipts": model_ui_receipts,
        "scorer_records": scorer_rows,
        "behavior": behavior,
    }
    write_json(cell_dir / "summary.json", summary)
    return summary


def _image_diff_with_mask(
    left_path: str, right_path: str, mask_bbox: tuple[int, int, int, int]
) -> dict[str, Any]:
    with Image.open(left_path).convert("RGB") as left, Image.open(right_path).convert(
        "RGB"
    ) as right:
        diff = ImageChops.difference(left, right)
        bbox = diff.getbbox()
        outside = diff.copy()
        mask = Image.new("L", left.size, 0)
        ImageDraw.Draw(mask).rectangle(mask_bbox, fill=255)
        outside.paste((0, 0, 0), mask=mask)
        outside_bbox = outside.getbbox()
    return {
        "diff_bbox": list(bbox) if bbox is not None else [],
        "mask_bbox": list(mask_bbox),
        "outside_mask_bbox": list(outside_bbox) if outside_bbox is not None else [],
        "within_mask": outside_bbox is None,
    }


def _load_intervention(result: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(Path(str(result["intervention_path"])).read_text(encoding="utf-8"))


def _load_steps(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(result["raw_steps_path"]))
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def paired_checks(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks: dict[str, Any] = {"q1": {}, "q2": {}, "q3": {}, "q4": {}}
    by_key = {str(key): value for key, value in results.items()}

    for layout in ("canonical", "cyclic_shift_1", "cyclic_shift_2"):
        for arm in ("official", "clean"):
            f0 = by_key[f"q1_{layout}_{arm}_f0"]
            f3 = by_key[f"q1_{layout}_{arm}_f3"]
            f0_intervention = _load_intervention(f0)
            f3_intervention = _load_intervention(f3)
            f0_setup = f0_intervention["setup_ui_receipts"]
            f3_setup = f3_intervention["setup_ui_receipts"]
            checks["q1"][f"{layout}_{arm}"] = {
                "same_display_tokens": f0["display_tokens"] == f3["display_tokens"],
                "same_chart_sha256": (
                    f0_intervention["post_setup_snapshot"]["chart_sha256"]
                    == f3_intervention["post_setup_snapshot"]["chart_sha256"]
                ),
                "same_wind_token_position": bool(
                    len(f0_setup) == 1
                    and len(f3_setup) == 1
                    and f0_setup[0].get("selected_entity") == "Wind"
                    and f3_setup[0].get("selected_entity") == "Wind"
                    and f0_setup[0].get("choice_token") == f3_setup[0].get("choice_token")
                    and f0_setup[0].get("control_position")
                    == f3_setup[0].get("control_position")
                ),
                "f0_identity_is_neutral": bool(
                    f0_intervention.get("source")
                    == "evaluator_inherited_wind_fixture"
                    and f0_intervention.get("intervention_semantics")
                    == "neutral_recheck_on_inherited_wind"
                    and f0_intervention.get("outcome_validation") is None
                ),
                "f3_identity_is_binary_validator": bool(
                    f3_intervention.get("source") == "evaluator_f3_fixture"
                    and f3_intervention.get("intervention_semantics")
                    == "binary_outcome_signal_on_inherited_wind"
                    and isinstance(f3_intervention.get("outcome_validation"), Mapping)
                    and f3_intervention["outcome_validation"].get("contradiction") is True
                ),
            }
            checks["q1"][f"{layout}_{arm}"]["passed"] = all(
                checks["q1"][f"{layout}_{arm}"].values()
            )

    for arm in ("official", "clean"):
        for history in ("native4", "current_only"):
            group = {
                entity: by_key[f"q2_p_{entity.lower()}_{arm}_{history}"]
                for entity in ("Solar", "Wind", "Hydroelectric")
            }
            interventions = {entity: _load_intervention(row) for entity, row in group.items()}
            steps = {entity: _load_steps(row) for entity, row in group.items()}
            current_shas = {row["first_screenshot_sha256"] for row in group.values()}
            h1_shas = {
                entity: sha256_bytes(
                    Path(interventions[entity]["history_fixture"]["h1_path"]).read_bytes()
                )
                for entity in group
            }
            action_digests = {
                interventions[entity]["history_fixture"]["receipt"][
                    "action_history_sha256"
                ]
                for entity in group
            }
            first_receipts = {
                entity: steps[entity][0]["model_receipt"] for entity in group
            }
            fixture_receipt_join = all(
                first_receipts[entity]["action_history_sha256_before"]
                == interventions[entity]["history_fixture"]["receipt"][
                    "action_history_sha256"
                ]
                and first_receipts[entity]["history_image_sha256_before"]
                == interventions[entity]["history_fixture"]["receipt"][
                    "history_rgb_sha256"
                ]
                for entity in group
            ) if history == "native4" else all(
                first_receipts[entity]["history_image_sha256_before"] == []
                for entity in group
            )
            if history == "native4":
                h0_model_hashes = {
                    entity: first_receipts[entity]["model_call_input_image_sha256"][0]
                    for entity in group
                }
                h1_model_hashes = {
                    first_receipts[entity]["model_call_input_image_sha256"][1]
                    for entity in group
                }
                current_model_hashes = {
                    first_receipts[entity]["model_call_input_image_sha256"][2]
                    for entity in group
                }
                annotations = {
                    json.dumps(
                        first_receipts[entity]["history_image_annotations_before"],
                        sort_keys=True,
                    )
                    for entity in group
                }
                history_receipts_valid = bool(
                    len(h0_model_hashes) == 3
                    and len(h1_model_hashes) == 1
                    and len(current_model_hashes) == 1
                    and len(annotations) == 1
                    and all(
                        first_receipts[entity]["history_image_count_before"] == 2
                        for entity in group
                    )
                )
            else:
                h0_model_hashes = {}
                h1_model_hashes = {
                    first_receipts[entity]["model_call_input_image_sha256"][0]
                    for entity in group
                }
                current_model_hashes = set(h1_model_hashes)
                annotations = {
                    json.dumps(
                        first_receipts[entity]["history_image_annotations_before"],
                        sort_keys=True,
                    )
                    for entity in group
                }
                history_receipts_valid = bool(
                    len(current_model_hashes) == 1
                    and annotations == {"[]"}
                    and all(
                        first_receipts[entity]["history_image_count_before"] == 0
                        and first_receipts[entity]["action_count_before"] == 0
                        and first_receipts[entity]["memory_empty_before"] is True
                        for entity in group
                    )
                )
            raw_responses = {row["first_action_raw"] for row in group.values()}
            h0_paths = {
                entity: interventions[entity]["history_fixture"]["h0_path"]
                for entity in group
            }
            pair_diffs = {
                "solar_vs_wind": diff_audit(
                    Path(h0_paths["Solar"]).read_bytes(),
                    Path(h0_paths["Wind"]).read_bytes(),
                ),
                "solar_vs_hydro": diff_audit(
                    Path(h0_paths["Solar"]).read_bytes(),
                    Path(h0_paths["Hydroelectric"]).read_bytes(),
                ),
                "wind_vs_hydro": diff_audit(
                    Path(h0_paths["Wind"]).read_bytes(),
                    Path(h0_paths["Hydroelectric"]).read_bytes(),
                ),
            }
            checks["q2"][f"{arm}_{history}"] = {
                "current_review_pixel_identical": len(current_shas) == 1,
                "h1_raw_pixel_identical": len(set(h1_shas.values())) == 1,
                "fixture_action_history_identical": len(action_digests) == 1,
                "actual_model_input_history_valid": history_receipts_valid,
                "fixture_receipt_exact_join": fixture_receipt_join,
                "h0_model_hashes": h0_model_hashes,
                "h1_model_hashes": list(h1_model_hashes),
                "current_model_hashes": list(current_model_hashes),
                "annotations": list(annotations),
                "current_only_raw_response_identical": (
                    len(raw_responses) == 1 if history == "current_only" else None
                ),
                "h0_pair_diff_audits": pair_diffs,
                "passed": bool(
                    len(current_shas) == 1
                    and len(set(h1_shas.values())) == 1
                    and len(action_digests) == 1
                    and history_receipts_valid
                    and fixture_receipt_join
                    and all(
                        audit["raw_diff_within_mask"]
                        and audit["model_448_diff_within_mask"]
                        for audit in pair_diffs.values()
                    )
                    and (history != "current_only" or len(raw_responses) == 1)
                ),
            }

    for arm in ("official", "clean"):
        native = by_key[f"q3_final_solar_{arm}_native4"]
        current = by_key[f"q3_final_solar_{arm}_current_only"]
        native_steps = _load_steps(native)
        current_steps = _load_steps(current)
        native_intervention = _load_intervention(native)
        current_intervention = _load_intervention(current)
        checks["q3"][arm] = {
            "first_screenshot_identical": (
                native["first_screenshot_sha256"] == current["first_screenshot_sha256"]
            ),
            "first_raw_response_identical": (
                native["first_action_raw"] == current["first_action_raw"]
            ),
            "both_empty_history": all(
                rows[0]["model_receipt"]["history_image_count_before"] == 0
                and rows[0]["model_receipt"]["action_count_before"] == 0
                and rows[0]["model_receipt"]["memory_empty_before"] is True
                for rows in (native_steps, current_steps)
            ),
            "both_are_completion_only_final_solar": all(
                intervention.get("source") == "evaluator_completion_fixture"
                and intervention.get("intervention_semantics")
                == "completion_only_final_review"
                and intervention.get("recovery_eligible") is False
                and intervention.get("completion_target_action_id")
                == row["action_ids_by_entity"]["Solar"]
                and intervention["post_setup_snapshot"].get("visible_state")
                == "final_review"
                and intervention["post_setup_snapshot"].get("selection_count") == 2
                and intervention["post_setup_snapshot"].get("reversal_count") == 1
                and steps[0].get("input_state") == "final_review"
                for intervention, row, steps in (
                    (native_intervention, native, native_steps),
                    (current_intervention, current, current_steps),
                )
            ),
        }
        checks["q3"][arm]["passed"] = all(checks["q3"][arm].values())
        negative = by_key[f"q3_final_wind_{arm}_native4"]
        negative_steps = _load_steps(negative)
        negative_intervention = _load_intervention(negative)
        checks["q3"][f"wind_negative_{arm}"] = {
            "one_model_action": len(negative_steps) == 1,
            "empty_handoff_history": bool(
                negative_steps
                and negative_steps[0]["model_receipt"]["history_image_count_before"] == 0
                and negative_steps[0]["model_receipt"]["action_count_before"] == 0
            ),
            "completion_fixture_not_recovery": bool(
                negative_intervention.get("source")
                == "evaluator_completion_fixture"
                and negative_intervention.get("recovery_eligible") is False
                and negative_intervention.get("completion_target_action_id")
                == negative["action_ids_by_entity"]["Wind"]
                and negative_intervention["post_setup_snapshot"].get("visible_state")
                == "final_review"
            ),
        }
        checks["q3"][f"wind_negative_{arm}"]["passed"] = all(
            checks["q3"][f"wind_negative_{arm}"].values()
        )

    for previous in ("Wind", "Hydroelectric"):
        for arm in ("official", "clean"):
            control = by_key[f"q4_prev_{previous.lower()}_{arm}_f0"]
            treatment = by_key[f"q4_prev_{previous.lower()}_{arm}_invalidation"]
            control_intervention = _load_intervention(control)
            treatment_intervention = _load_intervention(treatment)
            control_steps = _load_steps(control)
            treatment_steps = _load_steps(treatment)
            review_diff = _image_diff_with_mask(
                control_steps[0]["screenshot_path"],
                treatment_steps[0]["screenshot_path"],
                BRANCH_REVIEW_FEEDBACK_MASK,
            )
            control_retry = next(
                (row for row in control_steps if row["input_state"] == "retry_decision"),
                None,
            )
            treatment_retry = next(
                (row for row in treatment_steps if row["input_state"] == "retry_decision"),
                None,
            )
            retry_diff = (
                _image_diff_with_mask(
                    control_retry["screenshot_path"],
                    treatment_retry["screenshot_path"],
                    BRANCH_RETRY_FEEDBACK_MASK,
                )
                if control_retry is not None and treatment_retry is not None
                else None
            )
            retry_pair_available = (
                control_retry is not None and treatment_retry is not None
            )
            checks["q4"][f"{previous.lower()}_{arm}"] = {
                "same_display_tokens": control["display_tokens"]
                == treatment["display_tokens"],
                "same_chart_sha256": (
                    control_intervention["post_setup_snapshot"]["chart_sha256"]
                    == treatment_intervention["post_setup_snapshot"]["chart_sha256"]
                ),
                "previous_identity_and_role_valid": all(
                    intervention.get("inherited_previous_action_id")
                    == row["action_ids_by_entity"][previous]
                    and intervention.get("inherited_previous_role")
                    == ("misleading" if previous == "Wind" else "neutral_or_irrelevant")
                    and intervention.get("recovery_eligible")
                    is (previous == "Wind")
                    for intervention, row in (
                        (control_intervention, control),
                        (treatment_intervention, treatment),
                    )
                ),
                "review_diff": review_diff,
                "retry_diff": retry_diff,
                "retry_pair_available": retry_pair_available,
                "retry_pair_missing_is_behavioral": not retry_pair_available,
                "passed": bool(
                    control["display_tokens"] == treatment["display_tokens"]
                    and control_intervention["post_setup_snapshot"]["chart_sha256"]
                    == treatment_intervention["post_setup_snapshot"]["chart_sha256"]
                    and all(
                        intervention.get("inherited_previous_action_id")
                        == row["action_ids_by_entity"][previous]
                        and intervention.get("inherited_previous_role")
                        == (
                            "misleading"
                            if previous == "Wind"
                            else "neutral_or_irrelevant"
                        )
                        and intervention.get("recovery_eligible")
                        is (previous == "Wind")
                        for intervention, row in (
                            (control_intervention, control),
                            (treatment_intervention, treatment),
                        )
                    )
                    and bool(review_diff["diff_bbox"])
                    and review_diff["within_mask"]
                    and (
                        retry_diff is None
                        or (bool(retry_diff["diff_bbox"]) and retry_diff["within_mask"])
                    )
                ),
            }
    for feedback_name, suffix in (
        (PHASE2_BRANCH_NEUTRAL_CONTROL, "f0"),
        (PHASE2_BRANCH_INVALIDATION, "invalidation"),
    ):
        for arm in ("official", "clean"):
            wind = by_key[f"q4_prev_wind_{arm}_{suffix}"]
            hydro = by_key[f"q4_prev_hydroelectric_{arm}_{suffix}"]
            wind_steps = _load_steps(wind)
            hydro_steps = _load_steps(hydro)
            review_diff = _image_diff_with_mask(
                wind_steps[0]["screenshot_path"],
                hydro_steps[0]["screenshot_path"],
                BRANCH_REVIEW_PREVIOUS_LABEL_MASK,
            )
            wind_retry = next(
                (row for row in wind_steps if row["input_state"] == "retry_decision"),
                None,
            )
            hydro_retry = next(
                (row for row in hydro_steps if row["input_state"] == "retry_decision"),
                None,
            )
            retry_diff = (
                _image_diff_with_mask(
                    wind_retry["screenshot_path"],
                    hydro_retry["screenshot_path"],
                    BRANCH_RETRY_PREVIOUS_LABEL_MASK,
                )
                if wind_retry is not None and hydro_retry is not None
                else None
            )
            key = f"previous_label_parity_{feedback_name}_{arm}"
            checks["q4"][key] = {
                "same_display_tokens": wind["display_tokens"] == hydro["display_tokens"],
                "same_chart_sha256": (
                    _load_intervention(wind)["post_setup_snapshot"]["chart_sha256"]
                    == _load_intervention(hydro)["post_setup_snapshot"]["chart_sha256"]
                ),
                "review_previous_label_diff": review_diff,
                "retry_previous_label_diff": retry_diff,
                "retry_pair_missing_is_behavioral": retry_diff is None,
                "passed": bool(
                    wind["display_tokens"] == hydro["display_tokens"]
                    and _load_intervention(wind)["post_setup_snapshot"]["chart_sha256"]
                    == _load_intervention(hydro)["post_setup_snapshot"]["chart_sha256"]
                    and bool(review_diff["diff_bbox"])
                    and review_diff["within_mask"]
                    and (
                        retry_diff is None
                        or (
                            bool(retry_diff["diff_bbox"])
                            and retry_diff["within_mask"]
                        )
                    )
                ),
            }
    return checks


def paired_check_failures(checks: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for probe, rows in checks.items():
        for key, row in rows.items():
            if not isinstance(row, Mapping) or row.get("passed") is not True:
                failures.append(f"{probe}:{key}")
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path, default=EXPECTED_OFFICIAL_REPO)
    parser.add_argument("--model-path", type=Path, default=EXPECTED_MODEL_PATH)
    parser.add_argument(
        "--agent-python", default="/tmp/gui-reflection-model-env/bin/python"
    )
    parser.add_argument("--agent-port", type=int, default=38108)
    parser.add_argument("--agent-startup-timeout", type=float, default=900.0)
    parser.add_argument("--agent-request-timeout", type=float, default=300.0)
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
    parser.add_argument("--action-wait-ms", type=int, default=700)
    parser.add_argument("--long-press-ms", type=int, default=800)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.official_repo.resolve() != EXPECTED_OFFICIAL_REPO:
        raise SystemExit("phase 2 requires the audited official GUI-Reflection repo")
    if args.model_path.resolve() != EXPECTED_MODEL_PATH:
        raise SystemExit("phase 2 requires the audited GUI-Reflection SFT checkpoint")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (args.output_root / panel_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    cells = phase2_cells()
    canonical_case = load_authoritative_case(task_set="smoke17", slug="env008")
    write_json(run_dir / "canonical_case.json", canonical_case)
    write_json(
        run_dir / "frozen_protocol.json",
        {
            "record_type": "env008_phase2_frozen_protocol",
            "phase_id": PHASE_ID,
            "panel_id": panel_id,
            "reportable": False,
            "cell_count": len(cells),
            "cell_order": [cell.to_dict() for cell in cells],
            "checkpoint_id": CHECKPOINT_ID,
            "ui_build_id": UI_BUILD_ID,
            "fixture_fonts": {
                "regular": str(REGULAR_FONT),
                "bold": str(BOLD_FONT),
            },
            "interpretation_limits": [
                "single deterministic case; no success-rate or significance claim",
                "external proposition records are evaluator-owned, not latent beliefs",
                "completion fixtures are evaluator-owned and recovery_eligible=false",
                "branch invalidation is an explicit answer-neutral action constraint",
                "model-call image receipts bind the GUI-agent-to-Model PIL sequence, not final InternVL tensors",
            ],
        },
    )

    managed: ManagedAgentServer | None = None
    try:
        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            managed = ManagedAgentServer(
                official_repo=args.official_repo,
                model_path=args.model_path,
                port=args.agent_port,
                log_path=run_dir / "model_server.log",
                python_executable=args.agent_python,
                temporal_len=4,
                allow_fixture_prime=True,
                startup_timeout_seconds=args.agent_startup_timeout,
                request_timeout_seconds=args.agent_request_timeout,
            )
            client = managed.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        verify_health(health, official_repo=args.official_repo, model_path=args.model_path)
        if (
            health.get("fixture_history_prime_enabled") is not True
            or health.get("model_call_input_receipts") is not True
        ):
            raise AgentRuntimeError(
                "phase-2 model service lacks fixture/model-input receipt capabilities"
            )
        write_json(run_dir / "agent_health.json", health)
        browser_factory = build_browser_factory(args)
        results: dict[str, dict[str, Any]] = {}
        for index, spec in enumerate(cells):
            run_id = f"run:{PHASE_ID}:{panel_id}:{index:02d}:{spec.key}"
            results[spec.key] = _run_cell(
                spec=spec,
                canonical_case=canonical_case,
                agent=client,
                browser_factory=browser_factory,
                run_dir=run_dir,
                run_id=run_id,
            )
            write_json(run_dir / "partial_results.json", results)

        checks = paired_checks(results)
        check_failures = paired_check_failures(checks)
        interventions = {
            key: _load_intervention(row) for key, row in results.items()
        }
        intervention_ids = [
            value.get("intervention_id") for value in interventions.values()
        ]
        intervention_identity_failures = [
            key
            for key, row in results.items()
            if interventions[key].get("run_id") != row.get("run_id")
            or interventions[key].get("cell_key") != key
            or interventions[key].get("pair_group_id") != row.get("pair_group_id")
            or interventions[key].get("task_instance_id")
            != row.get("task_instance_id")
            or not isinstance(interventions[key].get("intervention_id"), str)
        ]
        if len(intervention_ids) != len(set(intervention_ids)):
            intervention_identity_failures.append("duplicate_intervention_id")
        invalid_cells = [
            key
            for key, row in results.items()
            if row.get("status") in {"runner_error", "invalid_run", "parser_censored"}
            or row.get("parser_disagreement_steps")
            or _load_intervention(row)["feedback_leak_audit"]["passed"] is not True
        ]
        summary = {
            "record_type": "env008_phase2_panel_summary",
            "phase_id": PHASE_ID,
            "panel_id": panel_id,
            "reportable": False,
            "cell_count": len(results),
            "cell_order": [cell.key for cell in cells],
            "cell_results": results,
            "paired_checks": checks,
            "paired_check_failures": check_failures,
            "intervention_identity_failures": intervention_identity_failures,
            "invalid_cells": invalid_cells,
            "execution_complete": bool(
                len(results) == len(cells)
                and not invalid_cells
                and not check_failures
                and not intervention_identity_failures
            ),
            "interpretation_limits": [
                "execution_complete is artifact validity, not task success",
                "Q1 measures a visible binary wrong signal, not autonomous discovery",
                "Q2 manipulates evaluator-owned visible proposition history, not belief",
                "Q3 direct Confirm is completion success, not trajectory recovery",
                "Q4 branch exit is distinct from Solar rebinding and full completion",
                "Q2 processed-image receipts stop at the GUI-agent-to-Model PIL call boundary",
            ],
        }
        write_json(run_dir / "summary.json", summary)
        print(str(run_dir))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["execution_complete"] else 2
    except Exception as exc:
        write_json(
            run_dir / "fatal_error.json",
            {"timestamp": utc_now(), "error": repr(exc)},
        )
        print(str(run_dir))
        raise
    finally:
        if managed is not None:
            managed.close()


if __name__ == "__main__":
    raise SystemExit(main())
