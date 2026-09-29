#!/usr/bin/env python3
"""Calibrate or run the frozen 50-cell env008 Phase-3 mechanism panel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import uuid

from PIL import Image

from .actions import ActionParseError, ParsedAction
from .agent_runtime import (
    AgentClient,
    AgentRuntimeError,
    FixtureHistoryFrame,
    HttpAgentClient,
    ManagedAgentServer,
)
from .browser_executor import BrowserExecutionError, UnsupportedWebAction
from .build_targeted_recovery_cases import model_visible_review_projection
from .env008_phase3_protocol import (
    BLOCK_COMPLETION,
    BLOCK_MEMORY,
    BLOCK_METHOD,
    BLOCK_ROLE,
    MEMORY_TEXTS,
    METHOD_CURRENT_ONLY,
    METHOD_OFFICIAL,
    METHOD_PREMISE,
    PHASE_ID,
    PROTOCOL_VERSION,
    UI_BUILD_ID,
    Phase3CellSpec,
    memory_protocol_audit,
    phase3_cells,
)
from .env008_role_counterfactual import (
    ASSET_VARIANT_ID,
    RoleCounterfactualScorer,
    balance_audit,
    bind_role_case,
    load_manifest,
)
from .formal_path_policy import NavigationBlocked, REPO_ROOT
from .phase2_history_fixture import official_history_input_sha256
from .premise_controller import (
    PremiseControllerError,
    evidence_prompt,
    final_prompt,
    frozen_prompt_manifest,
    locate_prompt,
    parse_evidence_dependency,
    parse_stage_action,
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
    TargetedPathPolicy,
)
from .targeted_recovery_layout import derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator


ROLE_MANIFEST_PATH = (
    REPO_ROOT
    / "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
    "env008_role_counterfactual_v1/manifest.json"
)
ENTITIES = ("Solar", "Wind", "Hydroelectric")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(value), ensure_ascii=False, sort_keys=True) + "\n")


def _click(x: int, y: int, raw: str) -> ParsedAction:
    return ParsedAction("CLICK", (x, y), raw)


def _normalized_click_action(x: int, y: int) -> str:
    nx = next(value for value in range(1001) if value * VIEWPORT_WIDTH // 1000 == x)
    ny = next(value for value in range(1001) if value * VIEWPORT_HEIGHT // 1000 == y)
    return f"CLICK[[{nx}, {ny}]]"


def _entity_maps(
    case: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    cards = list(case["model_visible_shared"]["action_cards"])
    entity_to_token: dict[str, str] = {}
    for card in cards:
        label = str(card["label"])
        matches = [entity for entity in ENTITIES if entity in label]
        if len(matches) != 1:
            raise ValueError("each visible action card must name exactly one entity")
        entity_to_token[matches[0]] = str(card["choice_token"])
    if set(entity_to_token) != set(ENTITIES):
        raise ValueError("visible action cards do not cover the three entities")
    token_to_entity = {token: entity for entity, token in entity_to_token.items()}
    raw_map = case["runner_only"]["choice_token_to_action_id"]
    pairs = raw_map.items() if isinstance(raw_map, Mapping) else raw_map
    token_to_action = {str(token): str(action) for token, action in pairs}
    action_ids = {
        entity: token_to_action[token] for entity, token in entity_to_token.items()
    }
    return action_ids, entity_to_token, token_to_entity


def _case_for_spec(
    canonical_case: Mapping[str, Any], spec: Phase3CellSpec
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if spec.block_id == BLOCK_ROLE:
        if spec.role_config_id is None:
            raise ValueError("role cell omitted role_config_id")
        case, variant = bind_role_case(
            canonical_case,
            manifest_path=ROLE_MANIFEST_PATH,
            role_config_id=spec.role_config_id,
            layout_id=spec.layout_id,
        )
        return case, variant
    return derive_layout_case(canonical_case, layout_id=spec.layout_id), None


def _scorer_for_spec(
    canonical_case: Mapping[str, Any], spec: Phase3CellSpec
) -> Any:
    if spec.block_id == BLOCK_ROLE:
        if spec.role_config_id is None:
            raise ValueError("role scorer omitted role_config_id")
        return RoleCounterfactualScorer(
            canonical_case,
            manifest_path=ROLE_MANIFEST_PATH,
            role_config_id=spec.role_config_id,
            layout_id=spec.layout_id,
        )
    return CanonicalSubmissionScorer(
        task_set="smoke17", slug="env008", layout_id=spec.layout_id
    )


def _expected_entity(scorer: Any, action_ids: Mapping[str, str]) -> str:
    expected = str(scorer.expected_action_id)
    matches = [entity for entity, action in action_ids.items() if action == expected]
    if len(matches) != 1:
        raise ValueError("hidden scorer expected action does not bind one entity")
    return matches[0]


def _projection(case: Mapping[str, Any], spec: Phase3CellSpec) -> dict[str, Any]:
    return model_visible_review_projection(
        dict(case), spec.arm, evidence_level=spec.feedback_spec_id
    )


def _enrich_receipts(
    receipts: Sequence[Mapping[str, Any]], token_to_entity: Mapping[str, str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in receipts:
        row = dict(value)
        token = row.get("choice_token")
        if isinstance(token, str) and token in token_to_entity:
            row["selected_entity"] = token_to_entity[token]
        rows.append(row)
    return rows


def _score_submission(
    scorer: Any,
    *,
    submission_id: str,
    case: Mapping[str, Any],
    spec: Phase3CellSpec,
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    result = scorer.score(
        submission_id=submission_id,
        pair_group_id=str(case["pair_group_id"]),
        task_instance_id=str(case["arms"][spec.arm]["task_instance_id"]),
        arm=spec.arm,
        choice_token=str(receipt["choice_token"]),
        control_position=int(receipt["control_position"]),
    )
    return result if isinstance(result, dict) else result.to_dict()


def _choose_entity(
    *,
    browser: Any,
    case: Mapping[str, Any],
    entity_to_token: Mapping[str, str],
    entity: str,
    raw: str,
) -> tuple[dict[str, Any], tuple[int, int]]:
    display_tokens = [
        str(card["choice_token"])
        for card in case["model_visible_shared"]["action_cards"]
    ]
    token = entity_to_token[entity]
    position = display_tokens.index(token)
    coordinate = _evaluator_choice_coordinate(position)
    execution = browser.execute(_click(*coordinate, raw))
    return _execution_dict(execution), coordinate


def _setup_cell(
    *,
    app: CompactRecoveryApp,
    browser: Any,
    case: Mapping[str, Any],
    spec: Phase3CellSpec,
    cell_dir: Path,
    entity_to_token: Mapping[str, str],
    token_to_entity: Mapping[str, str],
) -> tuple[dict[str, Any], list[FixtureHistoryFrame], list[str], list[str]]:
    screenshots = cell_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    receipt_offset = app.receipt_count()
    setup_executions: list[dict[str, Any]] = []
    before = browser.screenshot()
    (screenshots / "evaluator_before_setup.png").write_bytes(before.png)
    history_frames: list[FixtureHistoryFrame] = []
    history_actions: list[str] = []
    history_descriptions: list[str] = []
    history_paths: list[str] = []
    outcome_record: dict[str, Any] | None = None

    if spec.block_id != BLOCK_COMPLETION:
        execution, _coordinate = _choose_entity(
            browser=browser,
            case=case,
            entity_to_token=entity_to_token,
            entity=spec.inherited_entity,
            raw="EVALUATOR_INHERITED_SELECTION",
        )
        setup_executions.append(execution)
        if spec.feedback_spec_id == F3_PRE_REATTEMPT_CONTRADICTION:
            validator = CanonicalOutcomeValidator(
                task_set="smoke17", slug="env008", layout_id=spec.layout_id
            )
            token = entity_to_token[spec.inherited_entity]
            position = [
                str(card["choice_token"])
                for card in case["model_visible_shared"]["action_cards"]
            ].index(token)
            record = validator.validate(
                pair_group_id=str(case["pair_group_id"]),
                task_instance_id=str(case["arms"][spec.arm]["task_instance_id"]),
                arm=spec.arm,
                choice_token=token,
                control_position=position,
            )
            outcome_record = record.to_dict()
            if outcome_record["contradiction"] is not True:
                raise ValueError("F3 setup did not validate the inherited choice as wrong")
            app.set_outcome_feedback(
                record_id=record.outcome_record_id,
                choice_token=token,
                contradiction=True,
            )
            browser.reload()
        expected_state = "review"
        setup_source = "evaluator_inherited_choice_fixture"
    else:
        final_entity = spec.completion_final_entity
        if final_entity not in {"Solar", "Wind"}:
            raise ValueError("completion cell has invalid final entity")
        prior_entity = "Wind" if final_entity == "Solar" else "Hydroelectric"
        execution, _prior_coordinate = _choose_entity(
            browser=browser,
            case=case,
            entity_to_token=entity_to_token,
            entity=prior_entity,
            raw=f"EVALUATOR_COMPLETION_PRIOR_{prior_entity.upper()}",
        )
        setup_executions.append(execution)
        review_frame = browser.screenshot()
        review_path = screenshots / "fixture_other_entity_review.png"
        review_path.write_bytes(review_frame.png)

        back = browser.execute(ParsedAction("PRESS_BACK", (), "EVALUATOR_COMPLETION_BACK"))
        setup_executions.append(_execution_dict(back))
        if not back.to_url.endswith("/decision"):
            raise ValueError("completion evaluator Back did not return to decision")
        app.mark_browser_back("review", "retry_decision")

        retry_before_wait = browser.screenshot()
        retry_wait_path = screenshots / "fixture_retry_before_wait.png"
        retry_wait_path.write_bytes(retry_before_wait.png)
        wait_execution = browser.execute(
            ParsedAction("WAIT", (), "EVALUATOR_COMPLETION_NEUTRAL_WAIT")
        )
        setup_executions.append(_execution_dict(wait_execution))
        retry_click = browser.screenshot()
        retry_click_path = screenshots / "fixture_retry_before_click.png"
        retry_click_path.write_bytes(retry_click.png)
        if retry_before_wait.png != retry_click.png:
            raise ValueError("neutral WAIT changed the retry screenshot")

        execution, final_coordinate = _choose_entity(
            browser=browser,
            case=case,
            entity_to_token=entity_to_token,
            entity=final_entity,
            raw=f"EVALUATOR_COMPLETION_FINAL_{final_entity.upper()}",
        )
        setup_executions.append(execution)
        final_click_action = _normalized_click_action(*final_coordinate)
        if spec.completion_history == "H2_recent_selection":
            history_frames = [
                FixtureHistoryFrame(
                    retry_before_wait.png,
                    retry_before_wait.width,
                    retry_before_wait.height,
                    None,
                ),
                FixtureHistoryFrame(
                    retry_click.png,
                    retry_click.width,
                    retry_click.height,
                    final_coordinate,
                ),
            ]
            history_actions = ["WAIT", final_click_action]
            history_descriptions = [
                "Wait on the retry decision while preserving the visible state.",
                f"Select the {final_entity} routing card for final review.",
            ]
            history_paths = [str(retry_wait_path.resolve()), str(retry_click_path.resolve())]
        elif spec.completion_history == "H2_revision_chain":
            history_frames = [
                FixtureHistoryFrame(
                    review_frame.png,
                    review_frame.width,
                    review_frame.height,
                    None,
                ),
                FixtureHistoryFrame(
                    retry_click.png,
                    retry_click.width,
                    retry_click.height,
                    final_coordinate,
                ),
            ]
            history_actions = ["PRESS_BACK", final_click_action]
            history_descriptions = [
                f"Reject the provisional {prior_entity} review and return to the decision.",
                f"Select the {final_entity} routing card for final review.",
            ]
            history_paths = [str(review_path.resolve()), str(retry_click_path.resolve())]
        elif spec.completion_history != "H0_empty":
            raise ValueError("completion history condition is unsupported")
        expected_state = "final_review"
        setup_source = "evaluator_completion_history_fixture"

    snapshot = app.snapshot()
    setup_receipts = _enrich_receipts(
        app.receipts_since(receipt_offset), token_to_entity
    )
    if (
        snapshot.get("visible_state") != expected_state
        or snapshot.get("current_choice_token")
        != entity_to_token[spec.inherited_entity]
        or snapshot.get("submitted") is not False
    ):
        raise ValueError("evaluator setup did not reach its declared handoff")
    expected_kinds = (
        ["selection", "browser_back", "selection"]
        if spec.block_id == BLOCK_COMPLETION
        else ["selection"]
    )
    if [row.get("kind") for row in setup_receipts] != expected_kinds:
        raise ValueError("evaluator setup UI receipt chain is incomplete")
    handoff = browser.screenshot()
    handoff_path = screenshots / "handoff_current.png"
    handoff_path.write_bytes(handoff.png)
    intervention = {
        "record_type": "env008_phase3_intervention",
        "intervention_id": f"intervention:{uuid.uuid4().hex}",
        "phase_id": PHASE_ID,
        "cell_key": spec.key,
        "block_id": spec.block_id,
        "source": setup_source,
        "normalized_as_agent_reasoning": False,
        "normalized_as_agent_selection": False,
        "recovery_eligible": spec.block_id != BLOCK_COMPLETION,
        "spec": spec.to_dict(),
        "pair_group_id": case["pair_group_id"],
        "task_instance_id": case["arms"][spec.arm]["task_instance_id"],
        "setup_executions": setup_executions,
        "setup_ui_receipts": setup_receipts,
        "outcome_validation": outcome_record,
        "post_setup_snapshot": snapshot,
        "handoff_current_path": str(handoff_path.resolve()),
        "handoff_current_sha256": _sha256_bytes(handoff.png),
        "history_fixture_design": {
            "ownership": (
                "evaluator_completion_history_fixture"
                if spec.block_id == BLOCK_COMPLETION
                else None
            ),
            "normalized_as_agent_selection": False,
            "recovery_eligible": False if spec.block_id == BLOCK_COMPLETION else None,
            "frame_paths": history_paths,
            "actions": history_actions,
            "action_descriptions": history_descriptions,
            "expected_model_call_history_sha256": [
                official_history_input_sha256(
                    frame.screenshot_png, frame.annotation
                )
                for frame in history_frames
            ],
        },
    }
    return intervention, history_frames, history_actions, history_descriptions


def _build_app_bundle(
    canonical_case: Mapping[str, Any], spec: Phase3CellSpec
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
    dict[str, Any],
    CompactRecoveryApp,
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    case, variant = _case_for_spec(canonical_case, spec)
    projection = _projection(case, spec)
    action_ids, entity_to_token, token_to_entity = _entity_maps(case)
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
    return (
        case,
        variant,
        projection,
        app,
        action_ids,
        entity_to_token,
        token_to_entity,
    )


def _execute_action(
    *,
    browser: Any,
    app: CompactRecoveryApp,
    action: ParsedAction,
    input_state: str,
) -> tuple[Any | None, str | None, str | None]:
    try:
        execution = browser.execute(action)
    except UnsupportedWebAction as exc:
        return None, f"unsupported_model_action:{exc}", None
    except (NavigationBlocked, BrowserExecutionError) as exc:
        return None, f"browser_execution_error:{exc}", None
    back_error = None
    if (
        action.action_type == "PRESS_BACK"
        and input_state == "review"
        and execution.to_url.endswith("/decision")
    ):
        try:
            app.mark_browser_back("review", "retry_decision")
        except ValueError as exc:
            back_error = str(exc)
    return execution, None, back_error


def _baseline_run(
    *,
    spec: Phase3CellSpec,
    agent: AgentClient,
    app: CompactRecoveryApp,
    browser: Any,
    case: Mapping[str, Any],
    projection: Mapping[str, Any],
    scorer: Any,
    token_to_entity: Mapping[str, str],
    intervention: dict[str, Any],
    history_frames: Sequence[FixtureHistoryFrame],
    history_actions: Sequence[str],
    history_descriptions: Sequence[str],
    cell_dir: Path,
    run_id: str,
    agent_session_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str, str | None, int]:
    if not isinstance(agent, HttpAgentClient):
        raise AgentRuntimeError("Phase-3 requires the receipt-owning HTTP client")
    screenshots = cell_dir / "screenshots"
    raw_path = cell_dir / "steps.jsonl"
    scorer_path = cell_dir / "scorer_records.jsonl"
    agent.reset(agent_session_id)
    reset_count = 1
    memory_receipt: dict[str, Any] | None = None
    history_receipt: dict[str, Any] | None = None
    if spec.block_id == BLOCK_MEMORY and spec.memory_condition != "M0_empty":
        memory_content = MEMORY_TEXTS.get(str(spec.memory_condition))
        if not isinstance(memory_content, str):
            raise ValueError("nonempty memory condition has no frozen content")
        memory_receipt = agent.prime_memory_fixture(
            fixture_id=f"memfixture_{uuid.uuid4().hex}",
            task_id=agent_session_id,
            memory_content=memory_content,
        )
        intervention["memory_fixture"] = {
            "source": "evaluator_memory_fixture",
            "normalized_as_agent_memory": False,
            "normalized_as_agent_reasoning": False,
            "exact_entry": memory_content,
            "receipt": memory_receipt,
        }
    else:
        intervention["memory_fixture"] = None
    if history_frames:
        history_receipt = agent.prime_history_fixture(
            fixture_id=f"histfixture_{uuid.uuid4().hex}",
            task_id=agent_session_id,
            frames=history_frames,
            actions=history_actions,
            action_descriptions=history_descriptions,
        )
        intervention["history_fixture_design"]["receipt"] = history_receipt

    raw_steps: list[dict[str, Any]] = []
    model_ui_receipts: list[dict[str, Any]] = []
    scorer_rows: list[dict[str, Any]] = []
    status = "timeout"
    error: str | None = None
    for step_index in range(spec.max_backbone_calls):
        if spec.method_id == METHOD_CURRENT_ONLY and step_index > 0:
            agent.reset(agent_session_id)
            reset_count += 1
        frame = browser.screenshot()
        input_snapshot = app.snapshot()
        input_state = str(input_snapshot["visible_state"])
        screenshot_path = screenshots / f"step_{step_index:02d}.png"
        screenshot_path.write_bytes(frame.png)
        result = agent.step(
            frame.png,
            str(projection["workflow_instruction"]),
            agent_session_id,
            frame.width,
            frame.height,
        )
        receipt = result.receipt
        if not isinstance(receipt, dict):
            raise AgentRuntimeError("Phase-3 official step omitted service receipt")
        if step_index == 0:
            if history_receipt is not None:
                expected_history = intervention["history_fixture_design"][
                    "expected_model_call_history_sha256"
                ]
                if (
                    receipt.get("task_step_index") != len(history_frames)
                    or receipt.get("history_image_count_before") != len(history_frames)
                    or receipt.get("action_count_before") != len(history_frames)
                    or receipt.get("history_image_sha256_before")
                    != history_receipt["history_rgb_sha256"]
                    or receipt.get("history_image_annotations_before")
                    != history_receipt["history_image_annotations"]
                    or receipt.get("action_history_sha256_before")
                    != history_receipt["action_history_sha256"]
                    or receipt.get("model_call_input_image_sha256", [])[:-1]
                    != expected_history
                    or receipt.get("memory_empty_before") is not True
                ):
                    raise AgentRuntimeError("completion history did not bind model input")
            else:
                if (
                    receipt.get("task_step_index") != 0
                    or receipt.get("history_image_count_before") != 0
                    or receipt.get("action_count_before") != 0
                ):
                    raise AgentRuntimeError("fresh Phase-3 handoff retained trajectory state")
            if memory_receipt is not None:
                if (
                    receipt.get("memory_text_sha256_before")
                    != memory_receipt["stored_memory_sha256"]
                    or receipt.get("memory_text_length_before")
                    != memory_receipt["stored_memory_length"]
                    or receipt.get("memory_empty_before") is not False
                    or receipt.get("model_call_memory_segment_occurrences") != 1
                ):
                    raise AgentRuntimeError("memory fixture did not bind model prompt")
            elif receipt.get("memory_empty_before") is not True:
                raise AgentRuntimeError("empty-memory condition retained memory")

        try:
            final_action = parse_final_action(result.action_raw, frame.width, frame.height)
            final_error = None
        except ActionParseError as exc:
            final_action = None
            final_error = str(exc)
        agrees = action_agreement(result.action, final_action)
        ui_offset = app.receipt_count()
        execution, execution_error, back_error = _execute_action(
            browser=browser,
            app=app,
            action=result.action,
            input_state=input_state,
        )
        ui_rows = _enrich_receipts(app.receipts_since(ui_offset), token_to_entity)
        model_ui_receipts.extend(ui_rows)
        for ui in ui_rows:
            if ui.get("kind") != "submission":
                continue
            score = _score_submission(
                scorer,
                submission_id=f"submission:{run_id}:{ui['transaction_id']}",
                case=case,
                spec=spec,
                receipt=ui,
            )
            scorer_rows.append(score)
            _append_jsonl(scorer_path, score)
        row = {
            "record_type": "env008_phase3_raw_step",
            "phase_id": PHASE_ID,
            "cell_key": spec.key,
            "block_id": spec.block_id,
            "method_id": spec.method_id,
            "run_id": run_id,
            "step": step_index,
            "input_state": input_state,
            "input_snapshot": input_snapshot,
            "screenshot_path": str(screenshot_path.resolve()),
            "screenshot_sha256": _sha256_bytes(frame.png),
            "model_receipt": receipt,
            "action_raw": result.action_raw,
            "action_description": result.action_description,
            "official_action_parsed": result.action.as_dict(),
            "final_action_parsed": final_action.as_dict() if final_action else None,
            "final_action_parse_error": final_error,
            "parser_agreement": agrees,
            "execution": _execution_dict(execution) if execution is not None else None,
            "execution_error": execution_error,
            "back_transition_error": back_error,
            "ui_receipts": ui_rows,
            "post_action_snapshot": app.snapshot(),
        }
        raw_steps.append(row)
        _append_jsonl(raw_path, row)
        if not agrees:
            status = "parser_censored"
            error = final_error or "official/final parser disagreement"
            break
        if execution_error is not None:
            if execution_error.startswith("unsupported_model_action"):
                status = "unsupported_model_action"
            else:
                status = "invalid_run"
                error = execution_error
            break
        if back_error is not None:
            status = "invalid_run"
            error = back_error
            break
        if execution is not None and execution.blocked_requests:
            status = "invalid_run"
            error = "navigation containment violation"
            break
        if scorer_rows:
            status = "submitted"
            break
        if execution is not None and execution.terminal:
            status = (
                "agent_complete_without_submission"
                if execution.terminal == "TASK_COMPLETE"
                else "agent_impossible"
            )
            break
    else:
        status = "one_action_incomplete" if spec.block_id == BLOCK_COMPLETION else "timeout"
    return raw_steps, model_ui_receipts, scorer_rows, status, error, reset_count


def _controller_run(
    *,
    cell_key: str,
    block_id: str,
    method_id: str,
    max_backbone_calls: int,
    agent: AgentClient,
    app: CompactRecoveryApp,
    browser: Any,
    task_instruction: str,
    cell_dir: Path,
    run_id: str,
    agent_session_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str, str | None, int]:
    if not isinstance(agent, HttpAgentClient):
        raise AgentRuntimeError("premise controller requires receipt-owning HTTP client")
    screenshots = cell_dir / "screenshots"
    raw_path = cell_dir / "steps.jsonl"
    agent.reset(agent_session_id)
    raw_steps: list[dict[str, Any]] = []
    model_ui_receipts: list[dict[str, Any]] = []
    scorer_rows: list[dict[str, Any]] = []
    instruction = task_instruction
    dependency = None
    status = "controller_output_failure"
    error: str | None = None
    stages: list[tuple[str, Any]] = [("evidence_and_reversal", None)]
    stage_index = 0
    while stages and stage_index < max_backbone_calls:
        stage_id, target = stages.pop(0)
        frame = browser.screenshot()
        input_snapshot = app.snapshot()
        input_state = str(input_snapshot["visible_state"])
        if stage_id == "evidence_and_reversal":
            question = evidence_prompt(instruction)
        elif stage_id == "target_action_binding":
            question = locate_prompt(instruction, str(target))
        elif stage_id == "submission_check":
            question = final_prompt(instruction, str(target))
        else:
            raise AssertionError("unknown controller stage")
        screenshot_path = screenshots / f"controller_{stage_index:02d}_{stage_id}.png"
        screenshot_path.write_bytes(frame.png)
        call = agent.controller_call(
            screenshot_png=frame.png,
            question=question,
            stage_id=stage_id,
            task_id=agent_session_id,
            viewport_width=frame.width,
            viewport_height=frame.height,
        )
        parse_error = None
        action: ParsedAction | None = None
        try:
            if stage_id == "evidence_and_reversal":
                dependency = parse_evidence_dependency(call.output_raw)
            action = parse_stage_action(
                call.output_raw,
                call.official_action_parsed,
                frame.width,
                frame.height,
            )
        except PremiseControllerError as exc:
            parse_error = str(exc)
        execution = None
        execution_error = None
        back_error = None
        ui_rows: list[dict[str, Any]] = []
        if action is not None:
            ui_offset = app.receipt_count()
            execution, execution_error, back_error = _execute_action(
                browser=browser, app=app, action=action, input_state=input_state
            )
            ui_rows = [dict(row) for row in app.receipts_since(ui_offset)]
            model_ui_receipts.extend(ui_rows)
        selections = [row for row in ui_rows if row.get("kind") == "selection"]
        submissions = [row for row in ui_rows if row.get("kind") == "submission"]
        target_entity = str(target) if target is not None else None
        row = {
            "record_type": "env008_phase3_controller_call",
            "phase_id": PHASE_ID,
            "cell_key": cell_key,
            "block_id": block_id,
            "method_id": method_id,
            "run_id": run_id,
            "step": stage_index,
            "controller_stage": stage_id,
            "input_state": input_state,
            "input_snapshot": input_snapshot,
            "screenshot_path": str(screenshot_path.resolve()),
            "screenshot_sha256": _sha256_bytes(frame.png),
            "controller_question": question,
            "controller_receipt": call.receipt,
            "action_raw": call.output_raw,
            "action_description": f"premise controller stage {stage_id}",
            "official_parser_payload": call.official_action_parsed,
            "official_action_parsed": action.as_dict() if action else None,
            "controller_parse_error": parse_error,
            "premise_dependency": dependency.to_dict() if dependency else None,
            "dependency_target_entity": target_entity,
            "selected_choice_token_observed": (
                selections[0].get("choice_token") if len(selections) == 1 else None
            ),
            "submitted_choice_token_observed": (
                submissions[0].get("choice_token") if len(submissions) == 1 else None
            ),
            "posthoc_entity_binding_not_available_inside_policy": True,
            "execution": _execution_dict(execution) if execution is not None else None,
            "execution_error": execution_error,
            "back_transition_error": back_error,
            "ui_receipts": ui_rows,
            "post_action_snapshot": app.snapshot(),
        }
        raw_steps.append(row)
        _append_jsonl(raw_path, row)
        stage_index += 1
        if parse_error is not None:
            status = "controller_output_failure"
            error = parse_error
            break
        if execution_error is not None:
            status = (
                "unsupported_model_action"
                if execution_error.startswith("unsupported_model_action")
                else "invalid_run"
            )
            error = None if status == "unsupported_model_action" else execution_error
            break
        if back_error is not None:
            status = "invalid_run"
            error = back_error
            break
        if execution is not None and execution.blocked_requests:
            status = "invalid_run"
            error = "navigation containment violation"
            break
        if execution is not None and execution.terminal:
            status = "agent_complete_without_submission"
            break
        if stage_id == "evidence_and_reversal":
            if (
                action is None
                or action.action_type != "PRESS_BACK"
                or dependency is None
                or submissions
            ):
                status = "controller_stage_mismatch"
                break
            stages.append(("target_action_binding", dependency.selected_entity))
        elif stage_id == "target_action_binding":
            if (
                action is None
                or action.action_type != "CLICK"
                or len(selections) != 1
                or submissions
            ):
                status = "controller_stage_mismatch"
                break
            stages.append(("submission_check", str(target)))
        else:
            if (
                action is not None
                and action.action_type == "CLICK"
                and len(submissions) == 1
            ):
                status = "submitted"
            else:
                status = "controller_no_submission"
            break
    return raw_steps, model_ui_receipts, scorer_rows, status, error, 1


def _posthoc_controller_binding_audit(
    raw_steps: Sequence[Mapping[str, Any]],
    token_to_entity: Mapping[str, str],
) -> dict[str, Any]:
    """Audit premise-to-action binding after the full policy trajectory ends.

    The visible-card token/entity map is evaluator instrumentation.  It is never
    supplied to a model call and never controls whether another controller stage
    runs; this audit is only used to separate task success from method-attributable
    dependency-chain success in the saved result.
    """

    target_rows = [
        row for row in raw_steps if row.get("controller_stage") == "target_action_binding"
    ]
    submission_rows = [
        row for row in raw_steps if row.get("controller_stage") == "submission_check"
    ]
    target_row = target_rows[0] if len(target_rows) == 1 else None
    submission_row = submission_rows[0] if len(submission_rows) == 1 else None
    target_entity = (
        str(target_row.get("dependency_target_entity"))
        if target_row is not None
        and isinstance(target_row.get("dependency_target_entity"), str)
        else None
    )

    def observed(
        row: Mapping[str, Any] | None, kind: str
    ) -> tuple[str | None, str | None, int]:
        receipts = row.get("ui_receipts", []) if row is not None else []
        matches = [
            receipt
            for receipt in receipts
            if isinstance(receipt, Mapping) and receipt.get("kind") == kind
        ]
        token = (
            str(matches[0].get("choice_token"))
            if len(matches) == 1 and isinstance(matches[0].get("choice_token"), str)
            else None
        )
        return token, token_to_entity.get(token) if token is not None else None, len(matches)

    selected_token, selected_entity, selection_count = observed(target_row, "selection")
    submitted_token, submitted_entity, submission_count = observed(
        submission_row, "submission"
    )
    action_consistent = bool(
        target_entity is not None
        and selected_entity is not None
        and target_entity.strip().casefold() == selected_entity.strip().casefold()
        and selection_count == 1
    )
    submission_consistent = bool(
        target_entity is not None
        and submitted_entity is not None
        and target_entity.strip().casefold() == submitted_entity.strip().casefold()
        and submission_count == 1
    )
    return {
        "record_type": "env008_phase3_posthoc_controller_binding_audit",
        "source": "evaluator_visible_card_label_binding",
        "used_as_model_input": False,
        "used_for_controller_stage_control": False,
        "computed_after_policy_trajectory": True,
        "target_entity_from_model_evidence": target_entity,
        "selected_choice_token": selected_token,
        "selected_entity_from_visible_card_label": selected_entity,
        "submitted_choice_token": submitted_token,
        "submitted_entity_from_visible_card_label": submitted_entity,
        "target_action_binding_consistent": action_consistent,
        "target_submission_binding_consistent": submission_consistent,
        "controller_chain_consistent": bool(
            action_consistent and submission_consistent
        ),
    }


def _behavior_summary(
    *,
    spec: Phase3CellSpec,
    expected_entity: str,
    action_ids: Mapping[str, str],
    ui_receipts: Sequence[Mapping[str, Any]],
    raw_steps: Sequence[Mapping[str, Any]],
    scorer_rows: Sequence[Mapping[str, Any]],
    controller_binding_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selections = [row for row in ui_receipts if row.get("kind") == "selection"]
    reversals = [
        row for row in ui_receipts if row.get("kind") in {"revision", "browser_back"}
    ]
    submissions = [row for row in ui_receipts if row.get("kind") == "submission"]
    retry = [row for row in selections if row.get("from_state") == "retry_decision"]
    first_retry_entity = retry[0].get("selected_entity") if retry else None
    success = bool(scorer_rows and scorer_rows[-1].get("success") is True)
    first_action_type = None
    if raw_steps:
        parsed = raw_steps[0].get("official_action_parsed")
        if isinstance(parsed, Mapping):
            first_action_type = parsed.get("action_type")
    effective_reversal = any(
        row.get("from_state") == "review" and row.get("to_state") == "retry_decision"
        for row in reversals
    )
    controller_chain_consistent = None
    if spec.method_id == METHOD_PREMISE:
        controller_chain_consistent = bool(
            controller_binding_audit is not None
            and controller_binding_audit.get("controller_chain_consistent") is True
        )
    task_level_recovery = bool(
        spec.block_id != BLOCK_COMPLETION
        and effective_reversal
        and first_retry_entity == expected_entity
        and submissions
        and success
    )
    method_attributable_recovery = bool(
        task_level_recovery
        and (
            spec.method_id != METHOD_PREMISE
            or controller_chain_consistent is True
        )
    )
    return {
        "first_action_type": first_action_type,
        "effective_reversal": effective_reversal,
        "first_retry_entity": first_retry_entity,
        "exit_inherited_branch": bool(
            first_retry_entity is not None
            and first_retry_entity != spec.inherited_entity
        ),
        "correct_entity_rebinding": first_retry_entity == expected_entity,
        "first_retry_action_id": (
            action_ids.get(str(first_retry_entity))
            if first_retry_entity is not None
            else None
        ),
        "submission_observed": bool(submissions),
        "submission_success": success if submissions else None,
        "task_level_recovery": task_level_recovery,
        "controller_dependency_target_entity": (
            controller_binding_audit.get("target_entity_from_model_evidence")
            if controller_binding_audit is not None
            else None
        ),
        "controller_action_bound_entity": (
            controller_binding_audit.get("selected_entity_from_visible_card_label")
            if controller_binding_audit is not None
            else None
        ),
        "controller_submission_bound_entity": (
            controller_binding_audit.get("submitted_entity_from_visible_card_label")
            if controller_binding_audit is not None
            else None
        ),
        "controller_chain_consistent": controller_chain_consistent,
        "method_attributable_full_recovery": method_attributable_recovery,
        "full_recovery": method_attributable_recovery,
        "direct_completion": bool(
            spec.block_id == BLOCK_COMPLETION
            and len(raw_steps) == 1
            and first_action_type == "CLICK"
            and submissions
            and success
        ),
        "model_selection_count": len(selections),
        "model_reversal_count": len(reversals),
        "model_submission_count": len(submissions),
    }


def _run_cell(
    *,
    spec: Phase3CellSpec,
    canonical_case: Mapping[str, Any],
    agent: AgentClient,
    browser_factory: Any,
    run_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    (
        case,
        variant,
        projection,
        app,
        action_ids,
        entity_to_token,
        token_to_entity,
    ) = _build_app_bundle(canonical_case, spec)
    scorer = _scorer_for_spec(canonical_case, spec)
    expected = _expected_entity(scorer, action_ids)
    cell_dir = run_dir / "cells" / spec.key
    cell_dir.mkdir(parents=True, exist_ok=True)
    intervention_path = cell_dir / "intervention.json"
    browser = None
    raw_steps: list[dict[str, Any]] = []
    model_ui_receipts: list[dict[str, Any]] = []
    scorer_rows: list[dict[str, Any]] = []
    intervention: dict[str, Any] | None = None
    controller_binding_audit: dict[str, Any] | None = None
    controller_binding_audit_path: Path | None = None
    status = "runner_error"
    error: str | None = None
    reset_count = 0
    agent_session_id = f"phase3task_{uuid.uuid4().hex}"
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            (
                intervention,
                history_frames,
                history_actions,
                history_descriptions,
            ) = _setup_cell(
                app=app,
                browser=browser,
                case=case,
                spec=spec,
                cell_dir=cell_dir,
                entity_to_token=entity_to_token,
                token_to_entity=token_to_entity,
            )
            intervention["run_id"] = run_id
            intervention["expected_entity_hidden_scorer"] = expected
            intervention["controller_input_excludes_intervention_record"] = True
            intervention["agent_service_task_id"] = agent_session_id
            intervention["agent_service_task_id_is_opaque"] = True
            if spec.method_id == METHOD_PREMISE:
                (
                    raw_steps,
                    model_ui_receipts,
                    scorer_rows,
                    status,
                    error,
                    reset_count,
                ) = _controller_run(
                    cell_key=spec.key,
                    block_id=spec.block_id,
                    method_id=spec.method_id,
                    max_backbone_calls=spec.max_backbone_calls,
                    agent=agent,
                    app=app,
                    browser=browser,
                    task_instruction=str(projection["workflow_instruction"]),
                    cell_dir=cell_dir,
                    run_id=run_id,
                    agent_session_id=agent_session_id,
                )
                intervention["controller_dependency"] = next(
                    (
                        row.get("premise_dependency")
                        for row in reversed(raw_steps)
                        if row.get("premise_dependency") is not None
                    ),
                    None,
                )
                intervention["controller_call_count"] = len(raw_steps)
                intervention["controller_ui_action_count"] = sum(
                    row.get("official_action_parsed") is not None
                    for row in raw_steps
                )
                # Hidden truth/scoring is deliberately outside the controller
                # policy call boundary and occurs only after a real submission.
                model_ui_receipts = _enrich_receipts(
                    model_ui_receipts, token_to_entity
                )
                controller_binding_audit = _posthoc_controller_binding_audit(
                    raw_steps, token_to_entity
                )
                controller_binding_audit_path = (
                    cell_dir / "controller_binding_audit.json"
                )
                write_json(controller_binding_audit_path, controller_binding_audit)
                intervention["controller_posthoc_binding_audit"] = {
                    "path": str(controller_binding_audit_path.resolve()),
                    "used_as_model_input": False,
                    "used_for_controller_stage_control": False,
                }
                scorer_path = cell_dir / "scorer_records.jsonl"
                for ui in model_ui_receipts:
                    if ui.get("kind") != "submission":
                        continue
                    score = _score_submission(
                        scorer,
                        submission_id=f"submission:{run_id}:{ui['transaction_id']}",
                        case=case,
                        spec=spec,
                        receipt=ui,
                    )
                    scorer_rows.append(score)
                    _append_jsonl(scorer_path, score)
            else:
                (
                    raw_steps,
                    model_ui_receipts,
                    scorer_rows,
                    status,
                    error,
                    reset_count,
                ) = _baseline_run(
                    spec=spec,
                    agent=agent,
                    app=app,
                    browser=browser,
                    case=case,
                    projection=projection,
                    scorer=scorer,
                    token_to_entity=token_to_entity,
                    intervention=intervention,
                    history_frames=history_frames,
                    history_actions=history_actions,
                    history_descriptions=history_descriptions,
                    cell_dir=cell_dir,
                    run_id=run_id,
                    agent_session_id=agent_session_id,
                )
    except Exception as exc:
        status = "runner_error"
        error = repr(exc)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                status = "runner_error"
                error = error or f"browser_close_failed:{exc!r}"
        if intervention is not None:
            write_json(intervention_path, intervention)

    behavior = _behavior_summary(
        spec=spec,
        expected_entity=expected,
        action_ids=action_ids,
        ui_receipts=model_ui_receipts,
        raw_steps=raw_steps,
        scorer_rows=scorer_rows,
        controller_binding_audit=controller_binding_audit,
    )
    first = raw_steps[0] if raw_steps else None
    first_receipt = None
    if first is not None:
        first_receipt = first.get("model_receipt") or first.get("controller_receipt")
    token_counts = []
    latencies = []
    for row in raw_steps:
        receipt = row.get("model_receipt") or row.get("controller_receipt")
        if not isinstance(receipt, Mapping):
            continue
        count = receipt.get("model_call_output_token_count")
        if count is None:
            count = receipt.get("output_token_count")
        if isinstance(count, int) and not isinstance(count, bool):
            token_counts.append(count)
        latency = receipt.get("latency_ms")
        if isinstance(latency, int) and not isinstance(latency, bool):
            latencies.append(latency)
    summary = {
        "record_type": "env008_phase3_cell_summary",
        "phase_id": PHASE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "cell_key": spec.key,
        "block_id": spec.block_id,
        "reportable": False,
        "synthetic_counterfactual": spec.block_id == BLOCK_ROLE,
        "spec": spec.to_dict(),
        "pair_group_id": case["pair_group_id"],
        "task_instance_id": case["arms"][spec.arm]["task_instance_id"],
        "checkpoint_id": CHECKPOINT_ID,
        "ui_build_id": UI_BUILD_ID,
        "variant_record": variant,
        "action_ids_by_entity": action_ids,
        "expected_entity_hidden_scorer": expected,
        "status": status,
        "error": error,
        "agent_reset_count": reset_count,
        "agent_service_task_id": agent_session_id,
        "agent_service_task_id_is_opaque": bool(
            agent_session_id.startswith("phase3task_")
            and len(agent_session_id) == len("phase3task_") + 32
        ),
        "backbone_call_count": len(raw_steps),
        "ui_action_count": sum(
            isinstance(row.get("official_action_parsed"), Mapping)
            for row in raw_steps
        ),
        "output_token_count_sum": sum(token_counts) if token_counts else None,
        "controller_latency_ms_sum": sum(latencies) if latencies else None,
        "controller_binding_audit": controller_binding_audit,
        "controller_binding_audit_path": (
            str(controller_binding_audit_path.resolve())
            if controller_binding_audit_path is not None
            else None
        ),
        "first_screenshot_sha256": first.get("screenshot_sha256") if first else None,
        "first_action_raw": first.get("action_raw") if first else None,
        "first_model_receipt": first_receipt,
        "intervention_path": (
            str(intervention_path.resolve()) if intervention is not None else None
        ),
        "raw_steps_path": str((cell_dir / "steps.jsonl").resolve()),
        "scorer_records_path": (
            str((cell_dir / "scorer_records.jsonl").resolve())
            if scorer_rows
            else None
        ),
        "model_ui_receipts": model_ui_receipts,
        "scorer_records": scorer_rows,
        "behavior": behavior,
    }
    write_json(cell_dir / "summary.json", summary)
    return summary


def _load_json(path_value: str | Path) -> dict[str, Any]:
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def _load_steps(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(row["raw_steps_path"]))
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _tokenizer_memory_audit(model_path: Path) -> dict[str, Any]:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        model_path, trust_remote_code=True, use_fast=True, local_files_only=True
    )
    counts: dict[str, dict[str, int]] = {}
    for key, content in MEMORY_TEXTS.items():
        if content is None:
            continue
        stored = "['{}']".format(content)
        segment = f"<MEMORY> (stored memory content): {stored}\n"
        counts[key] = {
            "entry": len(tokenizer(content, add_special_tokens=False)["input_ids"]),
            "stored": len(tokenizer(stored, add_special_tokens=False)["input_ids"]),
            "prompt_segment": len(
                tokenizer(segment, add_special_tokens=False)["input_ids"]
            ),
        }
    return {
        "checkpoint": str(model_path.resolve()),
        "counts": counts,
        "entry_counts_equal": len({row["entry"] for row in counts.values()}) == 1,
        "stored_counts_equal": len({row["stored"] for row in counts.values()}) == 1,
        "prompt_segment_counts_equal": len(
            {row["prompt_segment"] for row in counts.values()}
        )
        == 1,
        "passed": bool(
            {row["entry"] for row in counts.values()} == {30}
            and len({row["stored"] for row in counts.values()}) == 1
            and len({row["prompt_segment"] for row in counts.values()}) == 1
        ),
    }


def _controller_static_audit() -> dict[str, Any]:
    manifest = frozen_prompt_manifest()
    joined = "\n".join(manifest["templates"].values()).casefold()
    forbidden_visible = (
        "solar",
        "wind",
        "hydroelectric",
        "41.2",
        "29.8",
        "18.5",
        "choice_",
    )
    leaks = [value for value in forbidden_visible if value in joined]
    return {
        "prompt_manifest": manifest,
        "visible_answer_fragments": leaks,
        "controller_module_import_boundary": (
            "stdlib plus actions parser only; no case/CSV/scorer/DOM module import"
        ),
        "passed": not leaks,
    }


def _calibrate_cell(
    *,
    spec: Phase3CellSpec,
    canonical_case: Mapping[str, Any],
    browser_factory: Any,
    run_dir: Path,
) -> dict[str, Any]:
    (
        case,
        variant,
        _projection_value,
        app,
        action_ids,
        entity_to_token,
        token_to_entity,
    ) = _build_app_bundle(canonical_case, spec)
    cell_dir = run_dir / "cells" / spec.key
    cell_dir.mkdir(parents=True, exist_ok=True)
    browser = None
    try:
        with ManagedCompactRecoveryServer(app) as server:
            browser = browser_factory(TargetedPathPolicy.from_start_url(server.start_url))
            browser.start(server.start_url)
            _wait_for_initial_chart(app)
            intervention, frames, actions, descriptions = _setup_cell(
                app=app,
                browser=browser,
                case=case,
                spec=spec,
                cell_dir=cell_dir,
                entity_to_token=entity_to_token,
                token_to_entity=token_to_entity,
            )
            intervention["calibration_only"] = True
            write_json(cell_dir / "intervention.json", intervention)
            return {
                "cell_key": spec.key,
                "spec": spec.to_dict(),
                "status": "calibrated",
                "pair_group_id": case["pair_group_id"],
                "task_instance_id": case["arms"][spec.arm]["task_instance_id"],
                "action_ids_by_entity": action_ids,
                "variant_id": variant.get("variant_id") if variant else None,
                "intervention_path": str((cell_dir / "intervention.json").resolve()),
                "handoff_current_sha256": intervention["handoff_current_sha256"],
                "post_setup_snapshot": intervention["post_setup_snapshot"],
                "history_frame_sha256": [
                    _sha256_bytes(frame.screenshot_png) for frame in frames
                ],
                "history_annotations": [
                    list(frame.annotation) if frame.annotation is not None else None
                    for frame in frames
                ],
                "history_actions": list(actions),
                "history_descriptions": list(descriptions),
                "expected_model_call_history_sha256": intervention[
                    "history_fixture_design"
                ]["expected_model_call_history_sha256"],
            }
    finally:
        if browser is not None:
            browser.close()


def _calibration_checks(
    rows: Mapping[str, Mapping[str, Any]],
    *,
    model_path: Path,
) -> dict[str, Any]:
    cells = phase3_cells()
    checks: dict[str, Any] = {
        "memory_static": memory_protocol_audit(),
        "memory_tokenizer": _tokenizer_memory_audit(model_path),
        "controller_static": _controller_static_audit(),
        "role_orthogonal_array": balance_audit(),
        "role_manifest_validated": {
            "passed": load_manifest(ROLE_MANIFEST_PATH).get("variant_count") == 6
        },
        "M": {},
        "A": {},
        "R": {},
        "C": {},
    }
    for arm in ("official", "clean"):
        m = [rows[cell.key] for cell in cells if cell.block_id == BLOCK_MEMORY and cell.arm == arm]
        checks["M"][arm] = {
            "same_handoff_current": len({row["handoff_current_sha256"] for row in m}) == 1,
            "same_app_snapshot": len(
                {
                    json.dumps(
                        _snapshot_without_ids(row["post_setup_snapshot"]),
                        sort_keys=True,
                    )
                    for row in m
                }
            )
            == 1,
        }
        checks["M"][arm]["passed"] = all(checks["M"][arm].values())
        a = [rows[cell.key] for cell in cells if cell.block_id == BLOCK_METHOD and cell.arm == arm]
        checks["A"][arm] = {
            "three_methods_present": len(a) == 3,
            "same_handoff_current": len({row["handoff_current_sha256"] for row in a}) == 1,
            "same_app_snapshot": len(
                {
                    json.dumps(
                        _snapshot_without_ids(row["post_setup_snapshot"]),
                        sort_keys=True,
                    )
                    for row in a
                }
            )
            == 1,
        }
        checks["A"][arm]["passed"] = all(checks["A"][arm].values())
        for final_entity in ("Solar", "Wind"):
            c = [
                rows[cell.key]
                for cell in cells
                if cell.block_id == BLOCK_COMPLETION
                and cell.arm == arm
                and cell.completion_final_entity == final_entity
            ]
            by_history = {row["spec"]["completion_history"]: row for row in c}
            recent = by_history["H2_recent_selection"]
            revision = by_history["H2_revision_chain"]
            checks["C"][f"{arm}_{final_entity}"] = {
                "three_histories_present": len(c) == 3,
                "same_handoff_current": len(
                    {row["handoff_current_sha256"] for row in c}
                )
                == 1,
                "same_app_snapshot": len(
                    {
                        json.dumps(
                            _snapshot_without_ids(row["post_setup_snapshot"]),
                            sort_keys=True,
                        )
                        for row in c
                    }
                )
                == 1,
                "populated_equal_length": len(recent["history_actions"])
                == len(revision["history_actions"])
                == 2,
                "shared_last_raw_frame": recent["history_frame_sha256"][-1]
                == revision["history_frame_sha256"][-1],
                "shared_last_action": recent["history_actions"][-1]
                == revision["history_actions"][-1],
                "shared_last_annotation": recent["history_annotations"][-1]
                == revision["history_annotations"][-1],
                "shared_last_model_hash": recent[
                    "expected_model_call_history_sha256"
                ][-1]
                == revision["expected_model_call_history_sha256"][-1],
                "early_semantics_differ": recent["history_actions"][0] == "WAIT"
                and revision["history_actions"][0] == "PRESS_BACK",
            }
            checks["C"][f"{arm}_{final_entity}"]["passed"] = all(
                checks["C"][f"{arm}_{final_entity}"].values()
            )
    for config_id in ("r0", "r1", "r2", "r3", "r4", "r5"):
        for arm in ("official", "clean"):
            group = [
                rows[cell.key]
                for cell in cells
                if cell.block_id == BLOCK_ROLE
                and cell.role_config_id == config_id
                and cell.arm == arm
            ]
            checks["R"][f"{config_id}_{arm}"] = {
                "two_methods_present": len(group) == 2,
                "same_handoff_current": len(
                    {row["handoff_current_sha256"] for row in group}
                )
                == 1,
                "same_action_mapping": len(
                    {json.dumps(row["action_ids_by_entity"], sort_keys=True) for row in group}
                )
                == 1,
            }
            checks["R"][f"{config_id}_{arm}"]["passed"] = all(
                checks["R"][f"{config_id}_{arm}"].values()
            )
    return checks


def _flatten_check_failures(checks: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    for key, value in checks.items():
        if isinstance(value, Mapping) and "passed" in value:
            if value.get("passed") is not True:
                failures.append(key)
        elif isinstance(value, Mapping):
            for subkey, subvalue in value.items():
                if not isinstance(subvalue, Mapping) or subvalue.get("passed") is not True:
                    failures.append(f"{key}:{subkey}")
    return failures


def _first_model_current_hash(row: Mapping[str, Any]) -> str | None:
    receipt = row.get("first_model_receipt")
    if not isinstance(receipt, Mapping):
        return None
    values = receipt.get("model_call_input_image_sha256")
    return str(values[-1]) if isinstance(values, list) and values else None


def _formal_checks(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    cells = phase3_cells()
    task_ids = [str(row.get("agent_service_task_id", "")) for row in results.values()]
    service_boundary = {
        "opaque_unique_task_ids": bool(
            len(task_ids) == len(set(task_ids))
            and all(
                value.startswith("phase3task_")
                and len(value) == len("phase3task_") + 32
                and all(character in "0123456789abcdef" for character in value[-32:])
                for value in task_ids
            )
        ),
        "all_receipts_bind_opaque_task_id": all(
            all(
                isinstance(
                    step.get("model_receipt") or step.get("controller_receipt"),
                    Mapping,
                )
                and (
                    step.get("model_receipt") or step.get("controller_receipt")
                ).get("task_id")
                == row.get("agent_service_task_id")
                for step in _load_steps(row)
            )
            for row in results.values()
        ),
    }
    service_boundary["passed"] = all(service_boundary.values())
    checks: dict[str, Any] = {
        "service_boundary": service_boundary,
        "M": {},
        "A": {},
        "R": {},
        "C": {},
        "budgets": {},
    }
    for arm in ("official", "clean"):
        m_specs = [cell for cell in cells if cell.block_id == BLOCK_MEMORY and cell.arm == arm]
        m_rows = [results[cell.key] for cell in m_specs]
        nonempty = [
            results[cell.key]
            for cell in m_specs
            if cell.memory_condition != "M0_empty"
        ]
        checks["M"][arm] = {
            "four_levels_present": len(m_rows) == 4,
            "same_first_current_png": len(
                {row["first_screenshot_sha256"] for row in m_rows}
            )
            == 1,
            "same_actual_current_model_image": len(
                {_first_model_current_hash(row) for row in m_rows}
            )
            == 1,
            "nonempty_full_question_tokens_equal": len(
                {
                    row["first_model_receipt"].get(
                        "model_call_question_token_count"
                    )
                    for row in nonempty
                }
            )
            == 1,
            "all_step0_empty_history": all(
                row["first_model_receipt"].get("history_image_count_before") == 0
                and row["first_model_receipt"].get("action_count_before") == 0
                for row in m_rows
            ),
            "memory_polarity_valid": all(
                row["first_model_receipt"].get("memory_empty_before")
                is (row["spec"]["memory_condition"] == "M0_empty")
                for row in m_rows
            ),
            "memory_prompt_bound_once": all(
                row["first_model_receipt"].get(
                    "model_call_memory_segment_occurrences"
                )
                == 1
                for row in m_rows
            ),
        }
        checks["M"][arm]["passed"] = all(checks["M"][arm].values())

        a_specs = [cell for cell in cells if cell.block_id == BLOCK_METHOD and cell.arm == arm]
        by_method = {cell.method_id: results[cell.key] for cell in a_specs}
        current = by_method[METHOD_CURRENT_ONLY]
        official = by_method[METHOD_OFFICIAL]
        controller = by_method[METHOD_PREMISE]
        checks["A"][arm] = {
            "three_methods_present": len(by_method) == 3,
            "same_first_current_png": len(
                {row["first_screenshot_sha256"] for row in by_method.values()}
            )
            == 1,
            "same_actual_current_model_image": len(
                {_first_model_current_hash(row) for row in by_method.values()}
            )
            == 1,
            "current_native_first_raw_equal": current["first_action_raw"]
            == official["first_action_raw"],
            "current_native_generation_equal": current["first_model_receipt"].get(
                "generation_config"
            )
            == official["first_model_receipt"].get("generation_config"),
            "controller_same_checkpoint_source": controller[
                "first_model_receipt"
            ].get("source")
            == "premise_aware_controller_v1_same_checkpoint",
        }
        checks["A"][arm]["passed"] = all(checks["A"][arm].values())

        for final_entity in ("Solar", "Wind"):
            c_specs = [
                cell
                for cell in cells
                if cell.block_id == BLOCK_COMPLETION
                and cell.arm == arm
                and cell.completion_final_entity == final_entity
            ]
            c_rows = {cell.completion_history: results[cell.key] for cell in c_specs}
            recent = c_rows["H2_recent_selection"]
            revision = c_rows["H2_revision_chain"]
            empty = c_rows["H0_empty"]
            recent_intervention = _load_json(recent["intervention_path"])
            revision_intervention = _load_json(revision["intervention_path"])
            checks["C"][f"{arm}_{final_entity}"] = {
                "same_first_current_png": len(
                    {row["first_screenshot_sha256"] for row in c_rows.values()}
                )
                == 1,
                "same_actual_current_model_image": len(
                    {_first_model_current_hash(row) for row in c_rows.values()}
                )
                == 1,
                "empty_history_zero": empty["first_model_receipt"].get(
                    "history_image_count_before"
                )
                == 0,
                "populated_history_two": recent["first_model_receipt"].get(
                    "history_image_count_before"
                )
                == revision["first_model_receipt"].get(
                    "history_image_count_before"
                )
                == 2,
                "shared_last_history_rgb": recent["first_model_receipt"][
                    "history_image_sha256_before"
                ][-1]
                == revision["first_model_receipt"]["history_image_sha256_before"][-1],
                "shared_last_model_input": recent["first_model_receipt"][
                    "model_call_input_image_sha256"
                ][-2]
                == revision["first_model_receipt"]["model_call_input_image_sha256"][-2],
                "shared_last_annotation": recent["first_model_receipt"][
                    "history_image_annotations_before"
                ][-1]
                == revision["first_model_receipt"][
                    "history_image_annotations_before"
                ][-1],
                "fixture_ownership_explicit": recent_intervention[
                    "history_fixture_design"
                ]["ownership"]
                == revision_intervention["history_fixture_design"]["ownership"]
                == "evaluator_completion_history_fixture",
                "strict_one_model_action": all(
                    row["backbone_call_count"] == 1 for row in c_rows.values()
                ),
            }
            checks["C"][f"{arm}_{final_entity}"]["passed"] = all(
                checks["C"][f"{arm}_{final_entity}"].values()
            )

    for config_id in ("r0", "r1", "r2", "r3", "r4", "r5"):
        for arm in ("official", "clean"):
            specs = [
                cell
                for cell in cells
                if cell.block_id == BLOCK_ROLE
                and cell.role_config_id == config_id
                and cell.arm == arm
            ]
            group = [results[cell.key] for cell in specs]
            checks["R"][f"{config_id}_{arm}"] = {
                "two_methods_present": len(group) == 2,
                "same_first_current_png": len(
                    {row["first_screenshot_sha256"] for row in group}
                )
                == 1,
                "same_actual_current_model_image": len(
                    {_first_model_current_hash(row) for row in group}
                )
                == 1,
                "role_neutral_action_ids": all(
                    all(
                        not action.startswith(("correct_", "misleading_", "neutral_"))
                        for action in row["action_ids_by_entity"].values()
                    )
                    for row in group
                ),
            }
            checks["R"][f"{config_id}_{arm}"]["passed"] = all(
                checks["R"][f"{config_id}_{arm}"].values()
            )

    for key, row in results.items():
        spec = row["spec"]
        checks["budgets"][key] = {
            "backbone_within_cap": row["backbone_call_count"]
            <= spec["max_backbone_calls"],
            "ui_actions_within_cap": row["ui_action_count"] <= spec["max_ui_actions"],
            "passed": row["backbone_call_count"] <= spec["max_backbone_calls"]
            and row["ui_action_count"] <= spec["max_ui_actions"],
        }
    return checks


def _snapshot_without_ids(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"outcome_record_id"}
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("calibration", "formal"), required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--calibration-summary", type=Path)
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path, default=EXPECTED_OFFICIAL_REPO)
    parser.add_argument("--model-path", type=Path, default=EXPECTED_MODEL_PATH)
    parser.add_argument(
        "--agent-python", default="/tmp/gui-reflection-model-env/bin/python"
    )
    parser.add_argument("--agent-port", type=int, default=38109)
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


def _new_run_dir(output_root: Path, label: str) -> tuple[str, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (output_root / label / panel_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    return panel_id, run_dir


def _write_frozen_protocol(
    run_dir: Path,
    *,
    panel_id: str,
    mode: str,
    cells: Sequence[Phase3CellSpec],
    token_audit: Mapping[str, Any],
    calibration_summary: Path | None,
) -> None:
    write_json(
        run_dir / "frozen_protocol.json",
        {
            "record_type": "env008_phase3_frozen_protocol",
            "phase_id": PHASE_ID,
            "protocol_version": PROTOCOL_VERSION,
            "panel_id": panel_id,
            "mode": mode,
            "reportable": False,
            "n_base_case": 1,
            "n_counterfactual_configs": 6,
            "n_cells": len(cells),
            "cell_order_algorithm": "ascending sha256(PROTOCOL_VERSION + '|' + cell_key)",
            "cell_order": [cell.to_dict() for cell in cells],
            "memory_entries": MEMORY_TEXTS,
            "memory_tokenizer_audit": dict(token_audit),
            "controller": frozen_prompt_manifest(),
            "role_manifest_path": str(ROLE_MANIFEST_PATH.resolve()),
            "role_manifest_asset_variant_id": ASSET_VARIANT_ID,
            "checkpoint_id": CHECKPOINT_ID,
            "ui_build_id": UI_BUILD_ID,
            "calibration_summary": (
                str(calibration_summary.resolve()) if calibration_summary else None
            ),
            "interpretation_limits": [
                "50 cells are within one development case, not IID samples",
                "memory is evaluator-seeded assistance, not autonomous model memory",
                "current-only is a same-checkpoint inference ablation, not a training control",
                "premise controller is an inference-time method bundle with different prompts",
                "six role configs are synthetic pairwise-orthogonal main-shortcut diagnostics",
                "completion fixtures are evaluator-owned and recovery_eligible=false",
                "Phase 3 is in-case development validation, not held-out generalization",
            ],
        },
    )


def _run_calibration(args: argparse.Namespace) -> int:
    cells = phase3_cells()
    panel_id, run_dir = _new_run_dir(args.output_root, "phase3_calibration")
    canonical_case = load_authoritative_case(task_set="smoke17", slug="env008")
    write_json(run_dir / "canonical_case.json", canonical_case)
    token_audit = _tokenizer_memory_audit(args.model_path)
    _write_frozen_protocol(
        run_dir,
        panel_id=panel_id,
        mode="calibration",
        cells=cells,
        token_audit=token_audit,
        calibration_summary=None,
    )
    browser_factory = build_browser_factory(args)
    rows: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for spec in cells:
        try:
            rows[spec.key] = _calibrate_cell(
                spec=spec,
                canonical_case=canonical_case,
                browser_factory=browser_factory,
                run_dir=run_dir,
            )
        except Exception as exc:
            errors[spec.key] = repr(exc)
        write_json(run_dir / "partial_calibration.json", {"rows": rows, "errors": errors})
    checks = _calibration_checks(rows, model_path=args.model_path) if not errors else {}
    failures = _flatten_check_failures(checks) if checks else ["cell_errors"]
    summary = {
        "record_type": "env008_phase3_calibration_summary",
        "phase_id": PHASE_ID,
        "protocol_version": PROTOCOL_VERSION,
        "panel_id": panel_id,
        "reportable": False,
        "cell_count": len(rows),
        "cell_order": [cell.key for cell in cells],
        "cell_errors": errors,
        "checks": checks,
        "check_failures": failures,
        "execution_complete": len(rows) == len(cells) and not errors and not failures,
    }
    write_json(run_dir / "summary.json", summary)
    print(str(run_dir))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["execution_complete"] else 2


def _validate_calibration_gate(path: Path) -> dict[str, Any]:
    summary = _load_json(path.resolve())
    if (
        summary.get("record_type") != "env008_phase3_calibration_summary"
        or summary.get("phase_id") != PHASE_ID
        or summary.get("protocol_version") != PROTOCOL_VERSION
        or summary.get("execution_complete") is not True
        or summary.get("cell_count") != 50
        or summary.get("cell_order") != [cell.key for cell in phase3_cells()]
    ):
        raise SystemExit("formal Phase-3 requires a complete matching calibration summary")
    return summary


def _run_formal(args: argparse.Namespace) -> int:
    if args.calibration_summary is None:
        raise SystemExit("--calibration-summary is required for formal Phase-3")
    calibration = _validate_calibration_gate(args.calibration_summary)
    cells = phase3_cells()
    panel_id, run_dir = _new_run_dir(args.output_root, "phase3_formal")
    canonical_case = load_authoritative_case(task_set="smoke17", slug="env008")
    write_json(run_dir / "canonical_case.json", canonical_case)
    token_audit = _tokenizer_memory_audit(args.model_path)
    _write_frozen_protocol(
        run_dir,
        panel_id=panel_id,
        mode="formal",
        cells=cells,
        token_audit=token_audit,
        calibration_summary=args.calibration_summary,
    )
    write_json(run_dir / "calibration_gate_receipt.json", calibration)
    if args.agent_url:
        raise SystemExit(
            "formal Phase-3 forbids external agent URLs and requires the audited "
            "managed local GUI-Reflection service"
        )
    managed: ManagedAgentServer | None = None
    try:
        managed = ManagedAgentServer(
            official_repo=args.official_repo,
            model_path=args.model_path,
            port=args.agent_port,
            log_path=run_dir / "model_server.log",
            python_executable=args.agent_python,
            temporal_len=4,
            allow_fixture_prime=True,
            allow_memory_prime=True,
            allow_controller_call=True,
            startup_timeout_seconds=args.agent_startup_timeout,
            request_timeout_seconds=args.agent_request_timeout,
        )
        client: AgentClient = managed.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        verify_health(health, official_repo=args.official_repo, model_path=args.model_path)
        if not all(
            health.get(field) is True
            for field in (
                "fixture_history_prime_enabled",
                "fixture_memory_prime_enabled",
                "controller_call_enabled",
                "model_call_input_receipts",
                "model_call_prompt_receipts",
            )
        ):
            raise AgentRuntimeError("Phase-3 service lacks a frozen protocol capability")
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
        checks = _formal_checks(results)
        check_failures = _flatten_check_failures(checks)
        invalid_cells = [
            key
            for key, row in results.items()
            if row.get("status") in {"runner_error", "invalid_run", "parser_censored"}
        ]
        intervention_ids = []
        intervention_identity_failures = []
        for key, row in results.items():
            intervention = _load_json(row["intervention_path"])
            intervention_ids.append(intervention.get("intervention_id"))
            if (
                intervention.get("cell_key") != key
                or intervention.get("run_id") != row.get("run_id")
                or intervention.get("pair_group_id") != row.get("pair_group_id")
                or intervention.get("task_instance_id") != row.get("task_instance_id")
            ):
                intervention_identity_failures.append(key)
        if len(intervention_ids) != len(set(intervention_ids)):
            intervention_identity_failures.append("duplicate_intervention_id")
        summary = {
            "record_type": "env008_phase3_panel_summary",
            "phase_id": PHASE_ID,
            "protocol_version": PROTOCOL_VERSION,
            "panel_id": panel_id,
            "reportable": False,
            "n_base_case": 1,
            "n_counterfactual_configs": 6,
            "cell_count": len(results),
            "cell_order": [cell.key for cell in cells],
            "cell_results": results,
            "paired_checks": checks,
            "paired_check_failures": check_failures,
            "invalid_cells": invalid_cells,
            "intervention_identity_failures": intervention_identity_failures,
            "execution_complete": bool(
                len(results) == len(cells)
                and not invalid_cells
                and not check_failures
                and not intervention_identity_failures
            ),
            "execution_complete_is_artifact_validity_not_task_success": True,
        }
        write_json(run_dir / "summary.json", summary)
        print(str(run_dir))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if summary["execution_complete"] else 2
    except Exception as exc:
        write_json(run_dir / "fatal_error.json", {"timestamp": utc_now(), "error": repr(exc)})
        print(str(run_dir))
        raise
    finally:
        if managed is not None:
            managed.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.official_repo.resolve() != EXPECTED_OFFICIAL_REPO:
        raise SystemExit("Phase-3 requires the audited official GUI-Reflection repo")
    if args.model_path.resolve() != EXPECTED_MODEL_PATH:
        raise SystemExit("Phase-3 requires the audited GUI-Reflection SFT checkpoint")
    if args.mode == "calibration":
        return _run_calibration(args)
    return _run_formal(args)


if __name__ == "__main__":
    raise SystemExit(main())
