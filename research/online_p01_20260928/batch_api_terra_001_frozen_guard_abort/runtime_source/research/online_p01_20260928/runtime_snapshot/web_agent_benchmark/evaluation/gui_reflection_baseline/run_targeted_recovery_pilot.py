#!/usr/bin/env python3
"""Run the real GUI-Reflection SFT on one compact targeted-recovery quartet.

This is an exploratory natural-track pilot.  It compares the same checkpoint
with and without a visible review/retry workflow on both canonical chart arms.
It does not claim to be an R+/R- reflection-training contrast.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterable, Mapping
import uuid

from .actions import (
    ActionParseError,
    ParsedAction,
    parse_official_action,
    parse_strict_final_action,
)
from .agent_runtime import (
    AgentClient,
    AgentRuntimeError,
    HttpAgentClient,
    ManagedAgentServer,
)
from .browser_executor import (
    BrowserExecutionError,
    BrowserExecutor,
    PlaywrightExecutor,
    SeleniumFirefoxExecutor,
    UnsupportedWebAction,
)
from .build_targeted_recovery_cases import (
    build_targeted_recovery_cases,
    model_visible_projection,
    model_visible_review_projection,
)
from .asset_variants import apply_asset_variant_case
from .formal_path_policy import REPO_ROOT
from .path_policy import NavigationBlocked
from .run_formal_task import append_jsonl, load_task_set_entries
from .run_travel_pair import verify_agent_service
from .targeted_recovery import (
    CURRENT_VISIBLE_RETRY,
    F0_NEUTRAL_RECHECK,
    F2_AUDITED_VALUES,
    F3_OUTCOME_CONTRADICTION,
    F3_PRE_REATTEMPT_CONTRADICTION,
    FEEDBACK_RETRY,
    NATURAL_RECOVERY,
    SINGLE_ATTEMPT,
    STANDARDIZED_MISTAKE,
    WORKFLOW_CONTRAST,
    TargetedRecoveryRegistry,
    analyze_recovery_quartet,
    analyze_run,
    derive_run_from_events,
)
from .targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    TargetedPathPolicy,
)
from .targeted_recovery_scorer import (
    CanonicalSubmissionScorer,
    ScorerRecord,
)
from .targeted_recovery_validator import (
    CanonicalOutcomeValidator,
    OutcomeValidationRecord,
)
from .targeted_recovery_layout import (
    LAYOUT_IDS,
    derive_layout_case,
    layout_algorithm,
    layout_offset,
)


RENDERER_BUILD_ID = "compact-recovery-v4"
CHECKPOINT_ID = (
    "craigwu/GUI_Reflection_8b_SFT@"
    "720d6239d18215417a80ac49f444a6145e073e9c"
)
WORKFLOW_ON = "gui_reflection_sft_native4_workflow_on_f0"
WORKFLOW_OFF = "gui_reflection_sft_native4_single_attempt"
CONTRAST_ID = "workflow:gui-reflection-sft-native4:on-vs-off"
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 960
# Fixed CSS geometry of the chart viewport.  Arm differences outside this box
# indicate that the paired render changed more than the canonical chart asset.
CHART_PIXEL_BOUNDS = (40, 230, 800, 920)
EXPECTED_OFFICIAL_REPO = Path(
    "/mnt/data/lys/gui_reflection_assets/GUI_Reflection"
).resolve()
EXPECTED_MODEL_PATH = Path(
    "/mnt/data/lys/gui_reflection_assets/GUI_Reflection_8b_SFT"
).resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def history_rgb_sha256(png: bytes) -> str:
    from PIL import Image

    with Image.open(BytesIO(png)).convert("RGB") as image:
        digest = hashlib.sha256()
        digest.update(b"gui-reflection-history-rgb-v1\0")
        digest.update(image.width.to_bytes(8, "big"))
        digest.update(image.height.to_bytes(8, "big"))
        digest.update(image.tobytes())
        return digest.hexdigest()


def action_history_sha256(actions: list[str], descriptions: list[str]) -> str:
    payload = json.dumps(
        {"actions": actions, "action_descriptions": descriptions},
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_authoritative_case(
    *, task_set: str | Path, slug: str
) -> dict[str, Any]:
    """Rebuild one case from canonical task pointers, never a self-reported case."""

    entries = [
        entry
        for entry in load_task_set_entries(task_set)
        if entry.get("slug") == slug
    ]
    if len(entries) != 1:
        raise ValueError(f"expected one canonical task-set entry for {slug!r}")
    cases = build_targeted_recovery_cases(entries, repo_root=REPO_ROOT)
    if len(cases) != 1:
        raise ValueError("canonical targeted case builder did not return one case")
    return cases[0]


def condition_records(layout_id: str = "canonical") -> list[dict[str, Any]]:
    shared = {
        "checkpoint_id": CHECKPOINT_ID,
        "checkpoint_stage": "sft",
        "reflection_training_status": "gui_reflection_sft",
        "history_mode": "native4",
        "renderer_build_id": RENDERER_BUILD_ID,
        "viewport_width": VIEWPORT_WIDTH,
        "viewport_height": VIEWPORT_HEIGHT,
        "ui_variant": f"compact_recovery_v4_{layout_id}",
    }
    return [
        {
            "condition_id": WORKFLOW_ON,
            **shared,
            "workflow_mode": FEEDBACK_RETRY,
        },
        {
            "condition_id": WORKFLOW_OFF,
            **shared,
            "workflow_mode": SINGLE_ATTEMPT,
        },
    ]


def build_registry(
    case: Mapping[str, Any], layout_id: str = "canonical"
) -> TargetedRecoveryRegistry:
    return TargetedRecoveryRegistry(
        repository_root=REPO_ROOT,
        cases=[case],
        conditions=condition_records(layout_id),
        contrasts=[
            {
                "contrast_id": CONTRAST_ID,
                "contrast_axis": WORKFLOW_CONTRAST,
                "candidate_condition": WORKFLOW_ON,
                "reference_condition": WORKFLOW_OFF,
            }
        ],
    )


def base_fields_for_cell(
    *,
    pair_group_id: str,
    trial_id: str,
    run_id: str,
    arm: str,
    condition: str,
) -> dict[str, Any]:
    workflow_on = condition == WORKFLOW_ON
    return {
        "run_id": run_id,
        "trial_id": trial_id,
        "pair_group_id": pair_group_id,
        "condition": condition,
        "arm": arm,
        "recovery_branch": NATURAL_RECOVERY,
        "evidence_level": F0_NEUTRAL_RECHECK if workflow_on else None,
        "evidence_record_id": None,
        "review_regime": "neutral_recheck" if workflow_on else "not_applicable",
        "retry_presentation": CURRENT_VISIBLE_RETRY,
        "training_recipe_match_id": None,
    }


def event_identity(bound: Mapping[str, Any]) -> dict[str, str]:
    return {
        field: str(bound[field])
        for field in (
            "run_id",
            "trial_id",
            "pair_group_id",
            "task_instance_id",
            "arm",
            "condition",
        )
    }


class EventCollector:
    def __init__(self, bound: Mapping[str, Any]) -> None:
        self.bound = dict(bound)
        self.events: list[dict[str, Any]] = []
        self.identity = event_identity(bound)
        self.token_map = dict(bound["choice_token_to_action_id"])
        self.display_tokens = list(bound["display_tokens"])
        self.observed_states: set[str] = set()

    def add(self, event_type: str, source: str, **fields: Any) -> dict[str, Any]:
        row = {
            "event_index": len(self.events),
            "event_type": event_type,
            "source": source,
            **self.identity,
            **fields,
        }
        self.events.append(row)
        return row

    def censor(self, reason: str) -> None:
        self.add("interface_censor", "runner", reason=reason)

    def _provisional_fields(self, token: str | None) -> dict[str, Any]:
        if token is None:
            return {
                "rendered_provisional_action_id": None,
                "rendered_provisional_choice_token": None,
                "rendered_provisional_control_position": None,
            }
        if token not in self.token_map:
            raise ValueError("renderer snapshot has a non-canonical choice token")
        return {
            "rendered_provisional_action_id": self.token_map[token],
            "rendered_provisional_choice_token": token,
            "rendered_provisional_control_position": self.display_tokens.index(token),
        }

    def render_identity(self) -> dict[str, Any]:
        return {
            "rendered_task_instance_id": self.bound["task_instance_id"],
            "rendered_chart_path": self.bound["chart_path"],
            "rendered_ui_variant": self.bound["ui_variant"],
            "renderer_build_id": self.bound["renderer_build_id"],
            "viewport_width": self.bound["viewport_width"],
            "viewport_height": self.bound["viewport_height"],
        }

    def observation(
        self,
        *,
        state: str,
        screenshot_path: Path,
        model_step_id: str,
        provisional_token: str | None,
        outcome_record_id: str | None = None,
        outcome_contradiction: bool | None = None,
    ) -> None:
        if state in self.observed_states:
            raise ValueError(f"normalized trace cannot observe {state!r} twice")
        self.add(
            "screenshot_observation",
            "runner",
            observed_state=state,
            artifact_path=str(screenshot_path.resolve()),
            model_step_id=model_step_id,
            feedback_spec_id=self.bound["evidence_level"],
            rendered_evidence_record_id=(
                self.bound["evidence_record_id"]
                if self.bound["evidence_level"] == F2_AUDITED_VALUES
                else None
            ),
            rendered_outcome_record_id=outcome_record_id,
            rendered_outcome_contradiction=outcome_contradiction,
            **self._provisional_fields(provisional_token),
            **self.render_identity(),
        )
        self.observed_states.add(state)

    def selection(
        self,
        *,
        receipt: Mapping[str, Any],
        input_state: str,
        input_snapshot: Mapping[str, Any],
        screenshot_path: Path,
        model_step_id: str,
        model_response_id: str,
        execution_receipt_id: str,
    ) -> None:
        token = str(receipt["choice_token"])
        position = int(receipt["control_position"])
        action_id = self.token_map[token]
        initial = input_state == "initial_decision"
        if not initial and input_state != "retry_decision":
            raise ValueError("selection input is not a decision state")
        self.add(
            "ui_selection",
            "runner",
            action_id=action_id,
            choice_token=token,
            control_position=position,
            decision_state=input_state,
            input_artifact_path=str(screenshot_path.resolve()),
            input_model_step_id=model_step_id,
            rendered_retry_presentation=(
                None if initial else self.bound["retry_presentation"]
            ),
            rendered_feedback_spec_id=(
                None if initial else self.bound["evidence_level"]
            ),
            rendered_evidence_record_id=(
                self.bound["evidence_record_id"]
                if not initial
                and self.bound["evidence_level"] == F2_AUDITED_VALUES
                else None
            ),
            rendered_outcome_record_id=(
                None if initial else input_snapshot.get("outcome_record_id")
            ),
            rendered_outcome_contradiction=(
                None if initial else input_snapshot.get("outcome_contradiction")
            ),
            **self._provisional_fields(
                None if initial else input_snapshot.get("current_choice_token")
            ),
            rendered_display_tokens=list(self.display_tokens),
            model_response_id=model_response_id,
            execution_receipt_id=execution_receipt_id,
            caused_by_model_step_id=model_step_id,
            **self.render_identity(),
        )

    def outcome_validation(self, record: OutcomeValidationRecord) -> None:
        self.add(
            "outcome_validation",
            "validator",
            provisional_action_id=record.provisional_action_id,
            provisional_choice_token=record.provisional_choice_token,
            provisional_control_position=record.provisional_control_position,
            outcome_record_id=record.outcome_record_id,
            contradiction=record.contradiction,
        )

    def reversal(
        self,
        *,
        action_type: str,
        receipt: Mapping[str, Any],
        model_step_id: str,
        model_response_id: str,
        execution_receipt_id: str,
    ) -> None:
        self.add(
            "ui_reversal",
            "runner",
            action_type=action_type,
            from_state=str(receipt["from_state"]),
            to_state=str(receipt["to_state"]),
            model_response_id=model_response_id,
            execution_receipt_id=execution_receipt_id,
            caused_by_model_step_id=model_step_id,
        )

    def submission(
        self,
        *,
        receipt: Mapping[str, Any],
        model_step_id: str,
        model_response_id: str,
        execution_receipt_id: str,
    ) -> dict[str, Any]:
        token = str(receipt["choice_token"])
        position = int(receipt["control_position"])
        action_id = self.token_map[token]
        submission_id = f"submission:{self.bound['run_id']}:{receipt['transaction_id']}"
        self.add(
            "submission",
            "runner",
            submitted_action_id=action_id,
            submitted_choice_token=token,
            submitted_control_position=position,
            submission_id=submission_id,
            model_response_id=model_response_id,
            execution_receipt_id=execution_receipt_id,
            caused_by_model_step_id=model_step_id,
        )
        return {
            "submission_id": submission_id,
            "choice_token": token,
            "control_position": position,
            "selected_action_id": action_id,
        }

    def scorer_result(self, record: ScorerRecord) -> None:
        self.add(
            "scorer_result",
            "scorer",
            submission_id=record.submission_id,
            scorer_record_id=record.scorer_record_id,
            success=record.success,
        )


def parse_final_action(
    raw: str, viewport_width: int, viewport_height: int
) -> ParsedAction:
    return parse_strict_final_action(raw, viewport_width, viewport_height)


def action_agreement(official: ParsedAction, final: ParsedAction | None) -> bool:
    return bool(
        final is not None
        and official.action_type == final.action_type
        and official.parameters == final.parameters
    )


def _execution_dict(execution: Any) -> dict[str, Any]:
    return {
        "from_url": execution.from_url,
        "to_url": execution.to_url,
        "terminal": execution.terminal,
        "executed_coordinates": (
            list(execution.executed_coordinates)
            if execution.executed_coordinates is not None
            else None
        ),
        "blocked_requests": list(execution.blocked_requests),
    }


def _wait_for_initial_chart(app: CompactRecoveryApp, timeout_seconds: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if app.snapshot()["chart_delivery_count"] >= 1:
            time.sleep(0.1)
            return
        time.sleep(0.01)
    raise BrowserExecutionError("initial chart asset was not delivered before screenshot")


def _evaluator_choice_coordinate(control_position: int) -> tuple[int, int]:
    """Return the fixed-layout center of one visible routing card."""

    if control_position not in {0, 1, 2}:
        raise ValueError("compact evaluator intervention expects exactly three cards")
    return 985, 368 + 129 * control_position


def run_cell(
    *,
    case: Mapping[str, Any],
    registry: TargetedRecoveryRegistry,
    base_fields: Mapping[str, Any],
    agent: AgentClient,
    scorer: CanonicalSubmissionScorer,
    browser_factory: Any,
    cell_dir: Path,
    max_steps: int,
    outcome_validator: CanonicalOutcomeValidator | None = None,
    layout_id: str = "canonical",
) -> dict[str, Any]:
    bound = registry.bind_base_fields(base_fields)
    standardized = bound["recovery_branch"] == STANDARDIZED_MISTAKE
    outcome_feedback = bound["evidence_level"] in {
        F3_OUTCOME_CONTRADICTION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    }
    if outcome_feedback != (outcome_validator is not None):
        raise ValueError(
            "outcome-feedback cells require one canonical outcome validator"
        )
    if bound["workflow_mode"] == FEEDBACK_RETRY:
        projection = model_visible_review_projection(
            dict(case),
            str(bound["arm"]),
            evidence_level=str(bound["evidence_level"]),
            evidence_record_id=bound.get("evidence_record_id"),
            registry=registry,
        )
    else:
        projection = model_visible_projection(dict(case), str(bound["arm"]))
    chart_path = (REPO_ROOT / str(projection["chart_path"])).resolve()
    app = CompactRecoveryApp(
        visible_case=projection,
        repository_root=REPO_ROOT,
        chart_path=chart_path,
        workflow_mode=str(bound["workflow_mode"]),
        inherited_selection=standardized,
        outcome_feedback_enabled=outcome_feedback,
    )
    collector = EventCollector(bound)
    screenshots_dir = cell_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    raw_steps_path = cell_dir / "steps.jsonl"
    events_path = cell_dir / "events.jsonl"
    scorer_records_path = cell_dir / "scorer_records.jsonl"
    validator_records_path = cell_dir / "validator_records.jsonl"
    intervention_path = cell_dir / "intervention.json"
    browser: BrowserExecutor | None = None
    status = "timeout"
    error: str | None = None
    selected_action_id: str | None = None
    raw_scorer_success: bool | None = None
    first_screenshot_path: str | None = None
    first_screenshot_sha256: str | None = None
    first_action_raw: str | None = None
    parser_disagreement_steps: list[int] = []
    steps_completed = 0
    last_unrecorded_observation: dict[str, Any] | None = None
    agent_session_id = f"{bound['task_instance_id']}|{bound['run_id']}"
    sent_history_hashes: list[str] = []
    expected_actions: list[str] = []
    expected_action_descriptions: list[str] = []
    agent_reset_count = 0
    intervention_record: dict[str, Any] | None = None

    try:
        if not standardized:
            agent.reset(agent_session_id)
            agent_reset_count += 1
        with ManagedCompactRecoveryServer(app) as server:
            start_url = server.start_url
            policy = TargetedPathPolicy.from_start_url(start_url)
            browser = browser_factory(policy)
            browser.start(start_url)
            _wait_for_initial_chart(app)
            if standardized:
                injected_action_id = str(bound["injected_mistake_action_id"])
                injected_tokens = [
                    token
                    for token, action_id in collector.token_map.items()
                    if action_id == injected_action_id
                ]
                if len(injected_tokens) != 1:
                    raise ValueError("injected mistake does not resolve to one visible token")
                injected_token = injected_tokens[0]
                injected_position = collector.display_tokens.index(injected_token)
                pre_frame = browser.screenshot()
                pre_path = screenshots_dir / "evaluator_before_injection.png"
                pre_path.write_bytes(pre_frame.png)
                receipt_offset = app.receipt_count()
                x, y = _evaluator_choice_coordinate(injected_position)
                evaluator_action = ParsedAction(
                    "CLICK", (x, y), "EVALUATOR_INTERVENTION_CLICK"
                )
                intervention_execution = browser.execute(evaluator_action)
                intervention_receipts = app.receipts_since(receipt_offset)
                if len(intervention_receipts) != 1:
                    raise ValueError("evaluator intervention must create one UI receipt")
                selection_receipt = intervention_receipts[0]
                if (
                    selection_receipt.get("kind") != "selection"
                    or selection_receipt.get("choice_token") != injected_token
                    or selection_receipt.get("control_position") != injected_position
                    or app.snapshot()["visible_state"] != "review"
                    or app.snapshot()["current_choice_token"] != injected_token
                    or not urlsplit_path(intervention_execution.from_url).endswith("/decision")
                    or not urlsplit_path(intervention_execution.to_url).endswith("/review")
                ):
                    raise ValueError("evaluator intervention did not establish Wind review state")
                initial_outcome: OutcomeValidationRecord | None = None
                if outcome_validator is not None:
                    initial_outcome = outcome_validator.validate(
                        pair_group_id=str(bound["pair_group_id"]),
                        task_instance_id=str(bound["task_instance_id"]),
                        arm=str(bound["arm"]),
                        choice_token=injected_token,
                        control_position=injected_position,
                    )
                    append_jsonl(validator_records_path, initial_outcome.to_dict())
                    collector.outcome_validation(initial_outcome)
                    app.set_outcome_feedback(
                        record_id=initial_outcome.outcome_record_id,
                        choice_token=injected_token,
                        contradiction=initial_outcome.contradiction,
                    )
                    browser.reload()
                post_setup = app.snapshot()
                intervention_record = {
                    "record_type": "targeted_standardized_mistake_intervention",
                    "source": "evaluator_intervention",
                    "timestamp": utc_now(),
                    "run_id": bound["run_id"],
                    "pair_group_id": bound["pair_group_id"],
                    "task_instance_id": bound["task_instance_id"],
                    "arm": bound["arm"],
                    "layout_id": layout_id,
                    "injected_action_id": injected_action_id,
                    "raw_choice_token": injected_token,
                    "raw_control_position": injected_position,
                    "pre_intervention_screenshot_path": str(pre_path.resolve()),
                    "pre_intervention_screenshot_sha256": sha256_bytes(pre_frame.png),
                    "evaluator_action": evaluator_action.as_dict(),
                    "browser_execution": _execution_dict(intervention_execution),
                    "ui_receipt": selection_receipt,
                    "post_setup_snapshot": post_setup,
                    "outcome_record_id": (
                        initial_outcome.outcome_record_id
                        if initial_outcome is not None
                        else None
                    ),
                    "normalized_as_agent_selection": False,
                    "handoff_model_receipt": None,
                }
                write_json(intervention_path, intervention_record)
                agent.reset(agent_session_id)
                agent_reset_count += 1
            for step_index in range(max_steps):
                if bound["history_mode"] == "current_only" and step_index > 0:
                    agent.reset(agent_session_id)
                    agent_reset_count += 1
                frame = browser.screenshot()
                input_snapshot = app.snapshot()
                input_state = str(input_snapshot["visible_state"])
                screenshot_path = screenshots_dir / f"step_{step_index:02d}.png"
                screenshot_path.write_bytes(frame.png)
                screenshot_sha = sha256_bytes(frame.png)
                if step_index == 0:
                    first_screenshot_path = str(screenshot_path.resolve())
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
                    raise AgentRuntimeError("targeted pilot requires service-owned step receipt")
                if receipt.get("screenshot_png_sha256") != screenshot_sha:
                    raise AgentRuntimeError("model receipt does not join the captured screenshot")
                if standardized and step_index == 0 and (
                    receipt.get("task_step_index") != 0
                    or receipt.get("action_count_before") != 0
                    or receipt.get("history_image_count_before") != 0
                    or receipt.get("history_image_sha256_before") != []
                    or receipt.get("memory_empty_before") is not True
                    or receipt.get("action_history_sha256_before")
                    != action_history_sha256([], [])
                ):
                    raise AgentRuntimeError(
                        "standardized handoff reset did not clear model state"
                    )
                expected_history = (
                    []
                    if bound["history_mode"] == "current_only"
                    else sent_history_hashes[-4:]
                )
                if receipt.get("history_image_sha256_before") != expected_history:
                    raise AgentRuntimeError(
                        "model receipt history images do not match this cell's sent sequence"
                    )
                if receipt.get("history_image_count_before") != len(expected_history):
                    raise AgentRuntimeError("model receipt history count is not native4")
                expected_action_digest = action_history_sha256(
                    [] if bound["history_mode"] == "current_only" else expected_actions,
                    []
                    if bound["history_mode"] == "current_only"
                    else expected_action_descriptions,
                )
                if receipt.get("action_history_sha256_before") != expected_action_digest:
                    raise AgentRuntimeError(
                        "model receipt action history does not match this cell's responses"
                    )
                model_step_id = f"{bound['run_id']}:{receipt['request_id']}"
                model_response_id = f"{bound['run_id']}:{receipt['response_id']}"
                if step_index == 0 and intervention_record is not None:
                    intervention_record["handoff_model_receipt"] = {
                        "request_id": receipt["request_id"],
                        "response_id": receipt["response_id"],
                        "task_step_index": receipt["task_step_index"],
                        "history_image_count_before": receipt[
                            "history_image_count_before"
                        ],
                        "history_image_sha256_before": receipt[
                            "history_image_sha256_before"
                        ],
                        "action_count_before": receipt["action_count_before"],
                        "action_history_sha256_before": receipt[
                            "action_history_sha256_before"
                        ],
                        "memory_empty_before": receipt["memory_empty_before"],
                        "screenshot_png_sha256": receipt["screenshot_png_sha256"],
                    }
                    write_json(intervention_path, intervention_record)

                try:
                    final_action = parse_final_action(
                        step_result.action_raw, frame.width, frame.height
                    )
                    final_parse_error = None
                except ActionParseError as exc:
                    final_action = None
                    final_parse_error = str(exc)
                parser_agrees = action_agreement(step_result.action, final_action)
                if not parser_agrees:
                    parser_disagreement_steps.append(step_index)
                sent_history_hashes.append(history_rgb_sha256(frame.png))
                if step_result.action.action_type == "MEMORIZE":
                    brief = step_result.action_description.lstrip("Memorize").strip()
                    expected_actions.append(f"MEMORIZE[summary: {brief}]")
                else:
                    expected_actions.append(
                        step_result.action_raw.split("<ACTION>:")[-1].strip()
                    )
                expected_action_descriptions.append(step_result.action_description)

                raw_offset = app.receipt_count()
                execution_error: str | None = None
                execution: Any = None
                try:
                    execution = browser.execute(step_result.action)
                    steps_completed = step_index + 1
                except (
                    UnsupportedWebAction,
                    NavigationBlocked,
                    BrowserExecutionError,
                ) as exc:
                    execution_error = str(exc)

                back_receipt_error: str | None = None
                if (
                    execution is not None
                    and step_result.action.action_type == "PRESS_BACK"
                    and input_state in {"review", "final_review"}
                    and urlsplit_path(execution.to_url).endswith("/decision")
                ):
                    post_navigation = app.snapshot()
                    rerendered = (
                        int(post_navigation["render_count"])
                        > int(input_snapshot["render_count"])
                        and post_navigation["visible_state"] == "retry_decision"
                    )
                    try:
                        app.mark_browser_back(input_state, "retry_decision")
                    except ValueError as exc:
                        back_receipt_error = str(exc)
                    if not rerendered:
                        back_receipt_error = (
                            (back_receipt_error + "; ") if back_receipt_error else ""
                        ) + "browser Back did not server-render current-visible retry"

                ui_receipts = app.receipts_since(raw_offset)
                structural_kinds = {str(row.get("kind")) for row in ui_receipts}
                action_type = step_result.action.action_type
                interaction_actions = {"CLICK", "LONG_PRESS", "PRESS_ENTER"}
                receipt_action_error: str | None = None
                if "browser_back" in structural_kinds and action_type != "PRESS_BACK":
                    receipt_action_error = "browser_back receipt was not caused by PRESS_BACK"
                if (
                    structural_kinds & {"selection", "revision", "submission"}
                    and action_type not in interaction_actions
                ):
                    receipt_action_error = (
                        f"UI receipt was caused by incompatible action {action_type}"
                    )
                selections = [
                    row for row in ui_receipts if row.get("kind") == "selection"
                ]
                submissions = [
                    row for row in ui_receipts if row.get("kind") == "submission"
                ]
                if bound["workflow_mode"] == SINGLE_ATTEMPT and selections:
                    if (
                        len(selections) != 1
                        or len(submissions) != 1
                        or selections[0].get("transaction_id")
                        != submissions[0].get("transaction_id")
                        or not submissions[0].get("atomic_with_selection")
                    ):
                        receipt_action_error = (
                            "single-attempt selection/submission is not one transaction"
                        )
                terminal_action = (
                    execution.terminal if execution is not None else None
                )
                record_observation = bool(
                    input_state in {"review", "final_review"}
                    and (
                        structural_kinds & {"revision", "browser_back", "submission"}
                        or terminal_action in {"TASK_COMPLETE", "TASK_IMPOSSIBLE"}
                        or step_index == max_steps - 1
                        or execution_error is not None
                    )
                )
                if input_state in {"review", "final_review"}:
                    last_unrecorded_observation = {
                        "state": input_state,
                        "screenshot_path": screenshot_path,
                        "model_step_id": model_step_id,
                        "provisional_token": input_snapshot.get(
                            "current_choice_token"
                        ),
                        "outcome_record_id": input_snapshot.get(
                            "outcome_record_id"
                        ),
                        "outcome_contradiction": input_snapshot.get(
                            "outcome_contradiction"
                        ),
                    }
                if record_observation and input_state not in collector.observed_states:
                    collector.observation(**last_unrecorded_observation)  # type: ignore[arg-type]
                    last_unrecorded_observation = None

                for ui_receipt in ui_receipts:
                    kind = ui_receipt.get("kind")
                    transaction_id = str(ui_receipt.get("transaction_id"))
                    execution_receipt_id = (
                        f"{bound['run_id']}:ui:{transaction_id}"
                    )
                    if kind == "selection":
                        collector.selection(
                            receipt=ui_receipt,
                            input_state=input_state,
                            input_snapshot=input_snapshot,
                            screenshot_path=screenshot_path,
                            model_step_id=model_step_id,
                            model_response_id=model_response_id,
                            execution_receipt_id=execution_receipt_id,
                        )
                        should_validate_retry = (
                            outcome_validator is not None
                            and (
                                bound["evidence_level"]
                                != F3_PRE_REATTEMPT_CONTRADICTION
                                or input_state == "initial_decision"
                            )
                        )
                        if should_validate_retry:
                            outcome_record = outcome_validator.validate(
                                pair_group_id=str(bound["pair_group_id"]),
                                task_instance_id=str(bound["task_instance_id"]),
                                arm=str(bound["arm"]),
                                choice_token=str(ui_receipt["choice_token"]),
                                control_position=int(ui_receipt["control_position"]),
                            )
                            append_jsonl(
                                validator_records_path, outcome_record.to_dict()
                            )
                            collector.outcome_validation(outcome_record)
                            app.set_outcome_feedback(
                                record_id=outcome_record.outcome_record_id,
                                choice_token=outcome_record.provisional_choice_token,
                                contradiction=outcome_record.contradiction,
                            )
                            browser.reload()
                    elif kind in {"revision", "browser_back"}:
                        collector.reversal(
                            action_type=(
                                "REVISE_SELECTION"
                                if kind == "revision"
                                else "PRESS_BACK"
                            ),
                            receipt=ui_receipt,
                            model_step_id=model_step_id,
                            model_response_id=model_response_id,
                            execution_receipt_id=execution_receipt_id,
                        )
                    elif kind == "submission":
                        claim = collector.submission(
                            receipt=ui_receipt,
                            model_step_id=model_step_id,
                            model_response_id=model_response_id,
                            execution_receipt_id=execution_receipt_id,
                        )
                        scorer_record = scorer.score(
                            submission_id=claim["submission_id"],
                            pair_group_id=str(bound["pair_group_id"]),
                            task_instance_id=str(bound["task_instance_id"]),
                            arm=str(bound["arm"]),
                            choice_token=claim["choice_token"],
                            control_position=claim["control_position"],
                        )
                        append_jsonl(scorer_records_path, scorer_record.to_dict())
                        collector.scorer_result(scorer_record)
                        selected_action_id = scorer_record.selected_action_id
                        raw_scorer_success = scorer_record.success
                    else:
                        collector.censor(f"unknown_ui_receipt:{kind}")

                if not parser_agrees:
                    collector.censor(
                        f"official_parser_final_action_disagreement:step_{step_index}"
                    )
                if back_receipt_error:
                    collector.censor(
                        f"back_transition_unverifiable:step_{step_index}:{back_receipt_error}"
                    )
                if receipt_action_error:
                    collector.censor(
                        f"ui_receipt_action_mismatch:step_{step_index}:{receipt_action_error}"
                    )
                if execution_error:
                    collector.censor(
                        f"browser_execution_error:step_{step_index}:{execution_error}"
                    )

                raw_step = {
                    "record_type": "targeted_raw_step",
                    "timestamp": utc_now(),
                    "run_id": bound["run_id"],
                    "task_instance_id": bound["task_instance_id"],
                    "agent_session_id": agent_session_id,
                    "step": step_index,
                    "input_state": input_state,
                    "input_snapshot": input_snapshot,
                    "screenshot_path": str(screenshot_path.resolve()),
                    "screenshot_sha256": screenshot_sha,
                    "screenshot_size": [frame.width, frame.height],
                    "model_receipt": receipt,
                    "action_raw": step_result.action_raw,
                    "action_description": step_result.action_description,
                    "official_action_parsed": step_result.action.as_dict(),
                    "final_action_parsed": (
                        final_action.as_dict() if final_action is not None else None
                    ),
                    "final_action_parse_error": final_parse_error,
                    "parser_agreement": parser_agrees,
                    "execution": (
                        _execution_dict(execution) if execution is not None else None
                    ),
                    "execution_error": execution_error,
                    "ui_receipts": ui_receipts,
                    "ui_receipt_action_error": receipt_action_error,
                    "post_action_snapshot": app.snapshot(),
                }
                append_jsonl(raw_steps_path, raw_step)

                if not parser_agrees:
                    status = "parser_censored"
                    error = f"official parser disagreed with final ACTION at step {step_index}"
                    break
                if receipt_action_error is not None:
                    status = "invalid_run"
                    error = receipt_action_error
                    break
                if execution is not None and execution.blocked_requests:
                    collector.censor(
                        f"navigation_containment_violation:step_{step_index}"
                    )
                    status = "invalid_run"
                    error = "browser blocked one or more out-of-policy requests"
                    break
                if selected_action_id is not None:
                    status = "submitted"
                    break
                if execution_error is not None:
                    status = "invalid_run"
                    error = execution_error
                    break
                if back_receipt_error is not None:
                    status = "invalid_run"
                    error = back_receipt_error
                    break
                if terminal_action == "TASK_COMPLETE":
                    status = "agent_complete_without_submission"
                    break
                if terminal_action == "TASK_IMPOSSIBLE":
                    status = "agent_impossible"
                    break
            else:
                status = "timeout"
    except Exception as exc:
        status = "runner_error"
        error = repr(exc)
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception as exc:
                if error is None:
                    error = f"browser close failed: {exc!r}"
                    status = "runner_error"
        if intervention_record is not None:
            write_json(intervention_path, intervention_record)

    if last_unrecorded_observation is not None:
        state = str(last_unrecorded_observation["state"])
        if state not in collector.observed_states:
            try:
                collector.observation(**last_unrecorded_observation)
            except Exception as exc:
                collector.censor(f"late_review_observation_failed:{exc}")
    if not collector.events:
        collector.censor(f"no_structural_event:{status}")
    for event in collector.events:
        append_jsonl(events_path, event)

    analysis_error: str | None = None
    run_record: dict[str, Any] | None = None
    analysis_record: dict[str, Any] | None = None
    try:
        run_record = derive_run_from_events(bound, collector.events).to_dict()
        analysis_record = analyze_run(
            base_fields, collector.events, registry=registry
        ).to_dict()
    except Exception as exc:
        analysis_error = repr(exc)
        status = "invalid_trace"
        if error is None:
            error = analysis_error

    result = {
        "record_type": "targeted_cell_summary",
        "timestamp": utc_now(),
        "run_id": bound["run_id"],
        "trial_id": bound["trial_id"],
        "pair_group_id": bound["pair_group_id"],
        "task_id": bound["task_id"],
        "task_instance_id": bound["task_instance_id"],
        "arm": bound["arm"],
        "condition": bound["condition"],
        "workflow_mode": bound["workflow_mode"],
        "status": status,
        "steps_completed": steps_completed,
        "agent_reset_count": agent_reset_count,
        "history_mode": bound["history_mode"],
        "recovery_branch": bound["recovery_branch"],
        "injected_mistake_action_id": bound.get("injected_mistake_action_id"),
        "evidence_level": bound["evidence_level"],
        "layout_id": layout_id,
        "intervention_path": (
            str(intervention_path.resolve()) if intervention_record is not None else None
        ),
        "validator_records_path": (
            str(validator_records_path.resolve())
            if validator_records_path.exists()
            else None
        ),
        "selected_action_id": selected_action_id,
        "submission_success": (
            raw_scorer_success
            if status == "submitted" and not parser_disagreement_steps
            else None
        ),
        "raw_scorer_success": raw_scorer_success,
        "first_screenshot_path": first_screenshot_path,
        "first_screenshot_sha256": first_screenshot_sha256,
        "first_action_raw": first_action_raw,
        "parser_disagreement_steps": parser_disagreement_steps,
        "chart_sha256": app.chart_sha256,
        "chart_delivery_count": app.snapshot()["chart_delivery_count"],
        "raw_steps_path": str(raw_steps_path.resolve()),
        "events_path": str(events_path.resolve()),
        "scorer_records_path": str(scorer_records_path.resolve()),
        "run_record": run_record,
        "analysis": analysis_record,
        "analysis_error": analysis_error,
        "error": error,
    }
    write_json(cell_dir / "summary.json", result)
    return result


def urlsplit_path(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path


def build_browser_factory(args: argparse.Namespace) -> Any:
    def factory(policy: TargetedPathPolicy) -> BrowserExecutor:
        common = {
            "viewport_width": VIEWPORT_WIDTH,
            "viewport_height": VIEWPORT_HEIGHT,
            "headed": args.headed,
            "action_wait_ms": args.action_wait_ms,
            "long_press_ms": args.long_press_ms,
        }
        if args.browser_backend == "playwright":
            return PlaywrightExecutor(
                policy, browser_executable=args.browser_executable, **common
            )
        return SeleniumFirefoxExecutor(
            policy,
            firefox_binary=args.firefox_binary,
            geckodriver=args.geckodriver,
            firefox_library_path=args.firefox_library_path,
            **common,
        )

    return factory


def _pixel_diff_bbox(path_a: str, path_b: str) -> list[int] | None:
    try:
        from PIL import Image, ImageChops

        with Image.open(path_a).convert("RGB") as image_a, Image.open(path_b).convert(
            "RGB"
        ) as image_b:
            if image_a.size != image_b.size:
                return None
            bbox = ImageChops.difference(image_a, image_b).getbbox()
            return list(bbox) if bbox is not None else []
    except Exception:
        return None


def cross_cell_checks(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    checks: dict[str, Any] = {"same_arm_initial": {}, "arm_diff_bbox": {}}
    for arm in ("official", "clean"):
        on = results[f"candidate_{arm}"]
        off = results[f"reference_{arm}"]
        on_sha = on.get("first_screenshot_sha256")
        off_sha = off.get("first_screenshot_sha256")
        on_raw = on.get("first_action_raw")
        off_raw = off.get("first_action_raw")
        checks["same_arm_initial"][arm] = {
            "screenshot_byte_identical": (
                isinstance(on_sha, str)
                and bool(on_sha)
                and isinstance(off_sha, str)
                and bool(off_sha)
                and on_sha == off_sha
            ),
            "first_raw_response_identical": (
                isinstance(on_raw, str)
                and bool(on_raw)
                and isinstance(off_raw, str)
                and bool(off_raw)
                and on_raw == off_raw
            ),
            "candidate_sha256": on_sha,
            "reference_sha256": off_sha,
        }
    for role in ("candidate", "reference"):
        official = results[f"{role}_official"].get("first_screenshot_path")
        clean = results[f"{role}_clean"].get("first_screenshot_path")
        bbox = (
            _pixel_diff_bbox(str(official), str(clean))
            if (
                isinstance(official, str)
                and Path(official).is_file()
                and isinstance(clean, str)
                and Path(clean).is_file()
            )
            else None
        )
        checks["arm_diff_bbox"][role] = bbox
        checks.setdefault("arm_diff_within_chart", {})[role] = bool(
            isinstance(bbox, list)
            and len(bbox) == 4
            and bbox[0] >= CHART_PIXEL_BOUNDS[0]
            and bbox[1] >= CHART_PIXEL_BOUNDS[1]
            and bbox[2] <= CHART_PIXEL_BOUNDS[2]
            and bbox[3] <= CHART_PIXEL_BOUNDS[3]
        )
    return checks


def execution_complete(
    results: Mapping[str, Mapping[str, Any]], checks: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    invalid_statuses = {"runner_error", "invalid_trace", "invalid_run", "parser_censored"}
    for key in (
        "candidate_official",
        "reference_official",
        "candidate_clean",
        "reference_clean",
    ):
        row = results.get(key)
        if not isinstance(row, Mapping):
            reasons.append(f"missing_cell:{key}")
            continue
        if row.get("status") in invalid_statuses:
            reasons.append(f"invalid_cell:{key}:{row.get('status')}")
        screenshot = row.get("first_screenshot_path")
        if not isinstance(screenshot, str) or not Path(screenshot).is_file():
            reasons.append(f"missing_first_screenshot:{key}")
        if not isinstance(row.get("first_action_raw"), str) or not row.get(
            "first_action_raw"
        ):
            reasons.append(f"missing_first_model_response:{key}")
    same_arm = checks.get("same_arm_initial")
    if not isinstance(same_arm, Mapping):
        reasons.append("missing_same_arm_initial_checks")
    else:
        for arm in ("official", "clean"):
            arm_check = same_arm.get(arm)
            if not isinstance(arm_check, Mapping) or not arm_check.get(
                "screenshot_byte_identical"
            ):
                reasons.append(f"workflow_initial_screenshot_mismatch:{arm}")
            if not isinstance(arm_check, Mapping) or not arm_check.get(
                "first_raw_response_identical"
            ):
                reasons.append(f"workflow_initial_response_mismatch:{arm}")
    arm_diff = checks.get("arm_diff_within_chart")
    if not isinstance(arm_diff, Mapping):
        reasons.append("missing_arm_diff_checks")
    else:
        for role in ("candidate", "reference"):
            if arm_diff.get(role) is not True:
                reasons.append(f"paired_render_diff_outside_chart:{role}")
    return not reasons, reasons


def verify_health(
    health: Mapping[str, Any], *, official_repo: Path, model_path: Path
) -> None:
    if health.get("implementation") != "official_GUI_Reflection_Agent":
        raise AgentRuntimeError("targeted pilot requires official GUI-Reflection")
    if Path(str(health.get("official_repo", ""))).resolve() != official_repo.resolve():
        raise AgentRuntimeError("agent service official_repo does not match pilot")
    if Path(str(health.get("model_path", ""))).resolve() != model_path.resolve():
        raise AgentRuntimeError("agent service model_path does not match pilot")
    if health.get("temporal_len") != 4:
        raise AgentRuntimeError("targeted pilot requires native temporal_len=4")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default="smoke17")
    parser.add_argument("--slug", default="env008")
    parser.add_argument("--layout-id", choices=LAYOUT_IDS, default="canonical")
    parser.add_argument(
        "--clean-only-screen",
        action="store_true",
        help="run only the two clean-arm competence cells before official-arm inspection",
    )
    parser.add_argument(
        "--asset-variant-manifest",
        type=Path,
        help="bind a validated, separately identified chart asset variant",
    )
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--agent-url")
    parser.add_argument(
        "--official-repo",
        type=Path,
        default=Path("/mnt/data/lys/gui_reflection_assets/GUI_Reflection"),
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path(
            "/mnt/data/lys/gui_reflection_assets/GUI_Reflection_8b_SFT"
        ),
    )
    parser.add_argument(
        "--agent-python", default="/tmp/gui-reflection-model-env/bin/python"
    )
    parser.add_argument("--agent-port", type=int, default=38092)
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
    parser.add_argument("--action-wait-ms", type=int, default=700)
    parser.add_argument("--long-press-ms", type=int, default=800)
    args = parser.parse_args(argv)
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    return args


def natural_cell_order(layout_id: str) -> tuple[tuple[str, str, str], ...]:
    base = (
        ("candidate_official", "official", WORKFLOW_ON),
        ("reference_official", "official", WORKFLOW_OFF),
        ("reference_clean", "clean", WORKFLOW_OFF),
        ("candidate_clean", "clean", WORKFLOW_ON),
    )
    return tuple(reversed(base)) if layout_offset(layout_id) % 2 else base


def clean_screen_checks(
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    candidate = results.get("candidate_clean", {})
    reference = results.get("reference_clean", {})
    candidate_sha = candidate.get("first_screenshot_sha256")
    reference_sha = reference.get("first_screenshot_sha256")
    candidate_raw = candidate.get("first_action_raw")
    reference_raw = reference.get("first_action_raw")
    return {
        "same_arm_initial": {
            "clean": {
                "screenshot_byte_identical": bool(
                    isinstance(candidate_sha, str)
                    and candidate_sha
                    and candidate_sha == reference_sha
                ),
                "first_raw_response_identical": bool(
                    isinstance(candidate_raw, str)
                    and candidate_raw
                    and candidate_raw == reference_raw
                ),
                "candidate_sha256": candidate_sha,
                "reference_sha256": reference_sha,
            }
        },
        "official_arm_not_run": "candidate_official" not in results
        and "reference_official" not in results,
    }


def clean_screen_execution_complete(
    results: Mapping[str, Mapping[str, Any]], checks: Mapping[str, Any]
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    invalid_statuses = {"runner_error", "invalid_trace", "invalid_run", "parser_censored"}
    if set(results) != {"candidate_clean", "reference_clean"}:
        reasons.append("clean_screen_cell_set_mismatch")
    for key in ("candidate_clean", "reference_clean"):
        row = results.get(key)
        if not isinstance(row, Mapping):
            reasons.append(f"missing_cell:{key}")
            continue
        if row.get("status") in invalid_statuses:
            reasons.append(f"invalid_cell:{key}:{row.get('status')}")
        screenshot = row.get("first_screenshot_path")
        if not isinstance(screenshot, str) or not Path(screenshot).is_file():
            reasons.append(f"missing_first_screenshot:{key}")
        if not isinstance(row.get("first_action_raw"), str) or not row.get(
            "first_action_raw"
        ):
            reasons.append(f"missing_first_model_response:{key}")
    clean_check = (checks.get("same_arm_initial") or {}).get("clean")
    if not isinstance(clean_check, Mapping) or not clean_check.get(
        "screenshot_byte_identical"
    ):
        reasons.append("workflow_initial_screenshot_mismatch:clean")
    if not isinstance(clean_check, Mapping) or not clean_check.get(
        "first_raw_response_identical"
    ):
        reasons.append("workflow_initial_response_mismatch:clean")
    if checks.get("official_arm_not_run") is not True:
        reasons.append("official_arm_present_in_clean_screen")
    return not reasons, reasons


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pilot_id = f"{run_stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (args.output_root / pilot_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    if args.official_repo.resolve() != EXPECTED_OFFICIAL_REPO:
        raise SystemExit(
            "registered checkpoint condition requires the audited official repo at "
            f"{EXPECTED_OFFICIAL_REPO}"
        )
    if args.model_path.resolve() != EXPECTED_MODEL_PATH:
        raise SystemExit(
            "registered checkpoint condition requires the audited model at "
            f"{EXPECTED_MODEL_PATH}"
        )
    canonical_case = load_authoritative_case(task_set=args.task_set, slug=args.slug)
    case = derive_layout_case(canonical_case, layout_id=args.layout_id)
    asset_variant_manifest: dict[str, Any] | None = None
    asset_variant_id: str | None = None
    if args.asset_variant_manifest is not None:
        manifest_path = args.asset_variant_manifest
        if not manifest_path.is_absolute():
            manifest_path = REPO_ROOT / manifest_path
        case, asset_variant_manifest = apply_asset_variant_case(
            case,
            manifest_path=manifest_path,
        )
        value = asset_variant_manifest.get("asset_variant_id")
        if not isinstance(value, str) or not value:
            raise SystemExit("asset variant manifest has no identity")
        asset_variant_id = value
    registry = build_registry(case, args.layout_id)
    scorer = CanonicalSubmissionScorer(
        task_set=args.task_set,
        slug=args.slug,
        layout_id=args.layout_id,
        asset_variant_id=asset_variant_id,
    )
    trial_id = f"trial:{case['pair_group_id']}:{pilot_id}"
    write_json(run_dir / "canonical_case.json", canonical_case)
    write_json(run_dir / "derived_layout_case.json", case)
    write_json(run_dir / "conditions.json", condition_records(args.layout_id))
    if asset_variant_manifest is not None:
        write_json(run_dir / "asset_variant_manifest.json", asset_variant_manifest)

    managed_agent: ManagedAgentServer | None = None
    try:
        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            managed_agent = ManagedAgentServer(
                official_repo=args.official_repo,
                model_path=args.model_path,
                port=args.agent_port,
                log_path=run_dir / "model_server.log",
                python_executable=args.agent_python,
                temporal_len=4,
                startup_timeout_seconds=args.agent_startup_timeout,
                request_timeout_seconds=args.agent_request_timeout,
            )
            client = managed_agent.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        verify_health(
            health,
            official_repo=args.official_repo,
            model_path=args.model_path,
        )
        write_json(run_dir / "agent_health.json", health)
        browser_factory = build_browser_factory(args)

        # Counterbalance the workflow order across chart arms while retaining a
        # single preregistered order in the run manifest.
        cell_order = natural_cell_order(args.layout_id)
        if args.clean_only_screen:
            cell_order = tuple(row for row in cell_order if row[1] == "clean")
        write_json(
            run_dir / "run_manifest.json",
            {
                "pilot_id": pilot_id,
                "trial_id": trial_id,
                "task_set": args.task_set,
                "slug": args.slug,
                "layout_id": args.layout_id,
                "layout_algorithm": layout_algorithm(args.layout_id),
                "cell_order": [key for key, _arm, _condition in cell_order],
                "contrast_id": CONTRAST_ID,
                "contrast_axis": WORKFLOW_CONTRAST,
                "checkpoint_id": CHECKPOINT_ID,
                "temporal_len": 4,
                "renderer_build_id": RENDERER_BUILD_ID,
                "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
                "max_steps": args.max_steps,
                "browser_backend": args.browser_backend,
                "natural_track": True,
                "clean_only_screen": args.clean_only_screen,
                "asset_variant_id": (
                    asset_variant_id
                ),
                "asset_variant_scope": (
                    asset_variant_manifest.get("scope")
                    if asset_variant_manifest is not None
                    else None
                ),
            },
        )
        results: dict[str, dict[str, Any]] = {}
        quartet_cells: dict[str, dict[str, Any]] = {}
        for key, arm, condition in cell_order:
            run_id = f"run:{case['pair_group_id']}:{pilot_id}:{key}"
            base = base_fields_for_cell(
                pair_group_id=str(case["pair_group_id"]),
                trial_id=trial_id,
                run_id=run_id,
                arm=arm,
                condition=condition,
            )
            result = run_cell(
                case=case,
                registry=registry,
                base_fields=base,
                agent=client,
                scorer=scorer,
                browser_factory=browser_factory,
                cell_dir=run_dir / "cells" / key,
                max_steps=args.max_steps,
                layout_id=args.layout_id,
            )
            results[key] = result
            events = [
                json.loads(line)
                for line in Path(result["events_path"])
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            quartet_cells[key] = {"base_fields": base, "events": events}
            append_jsonl(run_dir / "cells.jsonl", result)

        quartet_error: str | None = None
        quartet_record: dict[str, Any] | None = None
        if args.clean_only_screen:
            checks = clean_screen_checks(results)
            complete, completion_reasons = clean_screen_execution_complete(
                results, checks
            )
        else:
            try:
                quartet_record = analyze_recovery_quartet(
                    quartet_cells,
                    contrast_id=CONTRAST_ID,
                    registry=registry,
                ).to_dict()
            except Exception as exc:
                quartet_error = repr(exc)
            checks = cross_cell_checks(results)
            complete, completion_reasons = execution_complete(results, checks)
        summary = {
            "pilot_id": pilot_id,
            "trial_id": trial_id,
            "pair_group_id": case["pair_group_id"],
            "layout_id": args.layout_id,
            "asset_variant_id": (
                asset_variant_id
            ),
            "clean_only_screen": args.clean_only_screen,
            "contrast": (
                "clean-arm competence screen; official arm not run"
                if args.clean_only_screen
                else "workflow assistance, not reflection-training R+/R-"
            ),
            "cell_results": results,
            "cross_cell_checks": checks,
            "execution_complete": complete,
            "execution_incomplete_reasons": completion_reasons,
            "quartet": quartet_record,
            "quartet_error": quartet_error,
            "interpretation_limits": [
                "layout is fixed before model execution and interpreted by action label",
                "natural first-choice correctness is prevention, not recovery",
                "one quartet is qualitative and not a population estimate",
                "workflow on/off does not identify reflection-training causality",
                *(
                    [
                        "clean-only screening establishes competence but cannot measure "
                        "official susceptibility or recovery"
                    ]
                    if args.clean_only_screen
                    else []
                ),
                *(
                    [
                        "matched-render D1 is an isolated rendering sensitivity, "
                        "not a canonical benchmark_v2 replication"
                    ]
                    if asset_variant_manifest is not None
                    else []
                ),
            ],
        }
        write_json(run_dir / "summary.json", summary)
        print(str(run_dir))
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0 if quartet_error is None and complete else 2
    except Exception as exc:
        write_json(
            run_dir / "fatal_error.json",
            {"timestamp": utc_now(), "error": repr(exc)},
        )
        print(f"targeted recovery pilot failed: {exc}", file=sys.stderr)
        print(str(run_dir), file=sys.stderr)
        return 2
    finally:
        if managed_agent is not None:
            managed_agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
