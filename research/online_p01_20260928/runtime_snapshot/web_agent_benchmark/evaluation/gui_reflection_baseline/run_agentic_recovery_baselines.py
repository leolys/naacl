#!/usr/bin/env python3
"""Run targeted SRC-, ExACT-, and MobileUse-style recovery probes.

This is a controller-level matched-backbone adapter, not a claim of exact
reproduction of any upstream system.  Every controller sees screenshots and
its own visible action history only.  Canonical roles and the submission
scorer stay runner-side and are consulted only after a final browser commit.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback
from typing import Any, Iterable, Mapping, Sequence
from urllib.request import urlopen
import uuid

from adversarial_pipeline import llm_client

from .actions import ParsedAction
from .asset_variants import apply_asset_variant_case
from .browser_executor import SeleniumFirefoxExecutor
from .build_targeted_recovery_cases import model_visible_review_projection
from .formal_path_policy import REPO_ROOT
from .run_targeted_recovery_pilot import load_authoritative_case
from .targeted_recovery import F0_NEUTRAL_RECHECK, FEEDBACK_RETRY
from .targeted_recovery_app import (
    CompactRecoveryApp,
    ManagedCompactRecoveryServer,
    TargetedPathPolicy,
)
from .targeted_recovery_layout import derive_layout_case
from .targeted_recovery_scorer import CanonicalSubmissionScorer


VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 960
CHOICE_X = 985
CHOICE_Y0 = 368
CHOICE_Y_STEP = 129
REVIEW_CONFIRM = (1039, 787)
REVIEW_REVISE = (1039, 883)
FINAL_CONFIRM = (1039, 883)
EXACT_CANDIDATE_LIMIT = 8

METHOD_SRC = "src_style_teacher_assisted"
METHOD_EXACT = "exact_style_r_mcts"
METHOD_MOBILE = "mobileuse_style"
MOBILE_MODES = (
    "operator_only",
    "action_reflector",
    "action_trajectory_reflectors",
    "full_with_global_reflector",
)


@dataclass(frozen=True)
class TaskSpec:
    slug: str
    layout_id: str
    asset_manifest: str
    takeover_role: str
    correct_claim_aliases: tuple[str, ...]


TASK_SPECS = {
    "pub010": TaskSpec(
        "pub010",
        "cyclic_shift_1",
        "web_agent_benchmark/evaluation/gui_reflection_baseline/"
        "assets/matched_annotation_v1/pub010/manifest.json",
        "misleading",
        ("increase", "increasing", "grew", "growth", "rose", "rising"),
    ),
    "env008": TaskSpec(
        "env008",
        "cyclic_shift_2",
        "web_agent_benchmark/evaluation/gui_reflection_baseline/"
        "assets/env008_matched_render_v1/manifest.json",
        "misleading",
        ("solar",),
    ),
    "b035": TaskSpec(
        "b035",
        "canonical",
        "web_agent_benchmark/evaluation/gui_reflection_baseline/"
        "assets/matched_annotation_v1/b035/manifest.json",
        "correct",
        ("fall", "falling", "fell", "decrease", "decline", "declining"),
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def qwen_service_health(endpoint: str) -> dict[str, Any]:
    with urlopen(f"{endpoint.rstrip('/')}/health", timeout=10) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not value.get("ok"):
        raise RuntimeError(f"Qwen3-VL service is not ready: {value}")
    if (
        not value.get("native_multi_image")
        or value.get("server_protocol_version") != "2.0-native-multi-image"
    ):
        raise RuntimeError("Qwen3-VL service lacks native multi-image protocol v2")
    return value


def extract_json_object(text: str) -> dict[str, Any]:
    """Return the first decodable JSON object, tolerating fenced prose."""

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("model response contains no JSON object")


FORBIDDEN_PROMPT_TERMS = (
    "runner_only",
    "expected_action_id",
    "misleading_action_ids",
    "ground_truth",
    "source_references",
    "pair_group_id",
    "task_instance_id",
    "canonical action",
    "hidden scorer",
    "official arm",
    "clean arm",
)


def assert_prompt_safe(*parts: str) -> None:
    joined = "\n".join(parts).lower()
    leaked = [term for term in FORBIDDEN_PROMPT_TERMS if term in joined]
    if leaked:
        raise ValueError(f"model prompt contains runner-only terms: {leaked}")


def normalized_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Observable state used to prove fresh reset-and-replay equivalence."""

    keep = (
        "visible_state",
        "current_choice_token",
        "current_control_position",
        "selection_count",
        "reversal_count",
        "submitted",
        "chart_sha256",
    )
    return {name: snapshot.get(name) for name in keep}


def action_label(action: str) -> str:
    if action.startswith("choose:"):
        return f"click visible routing option {int(action.split(':', 1)[1]) + 1}"
    return {
        "revise": "click Revise selection",
        "confirm": "click Confirm selection",
        "finish": "declare the task complete without another browser click",
    }.get(action, action)


def visible_action_history(actions: Sequence[str]) -> str:
    if not actions:
        return "No action has been taken yet."
    return "\n".join(
        f"Action {index}: {action_label(action)}"
        for index, action in enumerate(actions)
    )


def legal_action_text(actions: Sequence[str]) -> str:
    return ", ".join(action_label(action) for action in actions)


class VisionJSONModel:
    """One matched vision backbone with complete call/cost receipts."""

    def __init__(
        self,
        *,
        output_dir: Path,
        backend: str,
        model: str,
        endpoint: str,
        model_path: str,
        model_size: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        seed: int,
    ) -> None:
        self.output_dir = output_dir
        if backend == "qwen3_vl_http":
            self.client = llm_client.LLMClient(
                backend=backend,
                model=model,
                qwen3_vl_server_url=endpoint,
                qwen3_vl_model_path=model_path,
                qwen3_vl_model_size=model_size,
            )
        elif backend == "kimik2_http":
            self.client = llm_client.LLMClient(
                backend=backend,
                model=model,
                kimik2_base_url=endpoint,
            )
        else:
            raise ValueError(f"unsupported experiment backend {backend!r}")
        self.backend = backend
        self.model = model
        self.endpoint = endpoint
        self.model_path = model_path
        self.model_size = model_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.seed = seed
        self.calls: list[dict[str, Any]] = []

    def ask(
        self,
        *,
        role: str,
        system: str,
        user: str,
        screenshots: Sequence[Path],
    ) -> dict[str, Any]:
        assert_prompt_safe(system, user)
        if not screenshots:
            raise ValueError("a vision call requires at least one screenshot")
        if self.backend != "qwen3_vl_http" and len(screenshots) != 1:
            raise ValueError(
                f"backend {self.backend!r} cannot preserve ordered multi-image input"
            )
        call_index = len(self.calls)
        input_paths = list(screenshots)
        model_input: Path | Sequence[Path] = (
            input_paths if self.backend == "qwen3_vl_http" else input_paths[0]
        )
        started = time.monotonic()
        raw = ""
        parsed: dict[str, Any] | None = None
        error: str | None = None
        try:
            raw = llm_client.complete_vision(
                self.client,
                system,
                user,
                model_input,
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
                top_p=self.top_p,
                seed=self.seed,
            )
            parsed = extract_json_object(raw)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        metadata = llm_client.get_last_response_metadata()
        record = {
            "call_index": call_index,
            "role": role,
            "backend": self.backend,
            "model": self.model,
            "model_path": self.model_path,
            "model_size": self.model_size,
            "endpoint_host": self.endpoint.split("/v1/", 1)[0],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "max_output_tokens": self.max_tokens,
            "system": system,
            "user": user,
            "input_packaging": (
                "native_ordered_images"
                if self.backend == "qwen3_vl_http"
                else "single_image"
            ),
            "input_image_count": len(input_paths),
            "input_screenshot_sha256": (
                sha256_bytes(input_paths[0].read_bytes())
                if len(input_paths) == 1
                else None
            ),
            "input_image_sha256": [
                sha256_bytes(path.read_bytes()) for path in input_paths
            ],
            "input_image_paths": [str(path.resolve()) for path in input_paths],
            "source_panel_sha256": [
                sha256_bytes(path.read_bytes()) for path in input_paths
            ],
            "raw": raw,
            "parsed": parsed,
            "metadata": metadata,
            "latency_seconds": time.monotonic() - started,
            "error": error,
        }
        self.calls.append(record)
        write_json(self.output_dir / "model_calls.json", self.calls)
        if error is not None or parsed is None:
            raise RuntimeError(error or "model JSON parse failed")
        return parsed

    def cost_summary(self) -> dict[str, Any]:
        by_role: dict[str, int] = {}
        prompt_tokens = completion_tokens = total_tokens = 0
        for call in self.calls:
            role = str(call["role"])
            by_role[role] = by_role.get(role, 0) + 1
            usage = (call.get("metadata") or {}).get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
        return {
            "calls_total": len(self.calls),
            "calls_by_role": by_role,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "model": self.model,
            "backend": self.backend,
            "model_path": self.model_path,
            "model_size": self.model_size,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
        }


@dataclass
class RestoreResult:
    prefix: tuple[str, ...]
    screenshot: Path
    screenshot_sha256: str
    snapshot: dict[str, Any]
    matched_cached_node: bool | None
    restore_id: str


class CompactBranchEnvironment:
    """Fresh-instance, coordinate-only branch execution and replay."""

    def __init__(
        self,
        *,
        case: Mapping[str, Any],
        arm: str,
        cell_dir: Path,
        firefox_binary: str,
        geckodriver: str,
        firefox_library_path: str,
        action_wait_ms: int,
    ) -> None:
        self.case = dict(case)
        self.arm = arm
        self.cell_dir = cell_dir
        self.visible_case = model_visible_review_projection(
            self.case,
            arm,
            evidence_level=F0_NEUTRAL_RECHECK,
        )
        self.firefox_binary = firefox_binary
        self.geckodriver = geckodriver
        self.firefox_library_path = firefox_library_path
        self.action_wait_ms = action_wait_ms
        self.app: CompactRecoveryApp | None = None
        self.server: ManagedCompactRecoveryServer | None = None
        self.browser: SeleniumFirefoxExecutor | None = None
        self.current_prefix: tuple[str, ...] = ()
        self.restore_count = 0
        self.transition_count = 0
        self.replay_transition_count = 0
        self.restore_receipts: list[dict[str, Any]] = []
        self.transition_receipts: list[dict[str, Any]] = []
        self.node_cache: dict[tuple[str, ...], tuple[str, dict[str, Any]]] = {}

        roles = self.case["runner_only"]["roles_by_action_id"]
        token_to_action = self.case["runner_only"]["choice_token_to_action_id"]
        desired_role = TASK_SPECS[str(self.case["slug"])].takeover_role
        matching = [
            token for token, action_id in token_to_action.items()
            if roles[action_id] == desired_role
        ]
        if len(matching) != 1:
            raise ValueError(
                f"expected one takeover token for role {desired_role!r}, got {matching}"
            )
        self.takeover_token = matching[0]
        display_position = next(
            index
            for index, card in enumerate(self.visible_case["action_cards"])
            if card["choice_token"] == self.takeover_token
        )
        self.takeover_action = f"choose:{display_position}"

    def close(self) -> None:
        if self.browser is not None:
            try:
                self.browser.close()
            finally:
                self.browser = None
        if self.server is not None:
            self.server.close()
            self.server = None
        self.app = None

    def _screenshot(self, directory: Path, name: str) -> Path:
        if self.browser is None:
            raise RuntimeError("browser is not running")
        frame = self.browser.screenshot()
        path = directory / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(frame.png)
        return path

    def _start(self, inherited: bool, restore_dir: Path) -> Path:
        chart_value = Path(str(self.visible_case["chart_path"]))
        chart_path = (
            chart_value.resolve()
            if chart_value.is_absolute()
            else (REPO_ROOT / chart_value).resolve()
        )
        self.app = CompactRecoveryApp(
            visible_case=self.visible_case,
            repository_root=REPO_ROOT,
            chart_path=chart_path,
            workflow_mode=FEEDBACK_RETRY,
            inherited_selection=inherited,
        )
        self.server = ManagedCompactRecoveryServer(self.app)
        start_url = self.server.start()
        policy = TargetedPathPolicy.from_start_url(start_url)
        self.browser = SeleniumFirefoxExecutor(
            policy,
            viewport_width=VIEWPORT_WIDTH,
            viewport_height=VIEWPORT_HEIGHT,
            firefox_binary=self.firefox_binary,
            geckodriver=self.geckodriver,
            firefox_library_path=self.firefox_library_path,
            action_wait_ms=self.action_wait_ms,
        )
        self.browser.start(start_url)
        deadline = time.monotonic() + 8
        while self.app.snapshot()["chart_delivery_count"] < 1:
            if time.monotonic() >= deadline:
                raise RuntimeError("chart did not load")
            time.sleep(0.02)
        return self._screenshot(restore_dir, "state_00_initial")

    def legal_actions(self) -> list[str]:
        if self.app is None:
            raise RuntimeError("environment is not restored")
        state = self.app.snapshot()["visible_state"]
        if state in {"initial_decision", "retry_decision"}:
            return [
                *(f"choose:{index}" for index in range(len(self.visible_case["action_cards"]))),
                "finish",
            ]
        if state == "review":
            return ["revise", "confirm", "finish"]
        if state == "final_review":
            return ["confirm", "finish"]
        return []

    def _parsed_action(self, action: str) -> ParsedAction | None:
        if self.app is None:
            raise RuntimeError("environment is not restored")
        state = str(self.app.snapshot()["visible_state"])
        if action.startswith("choose:"):
            position = int(action.split(":", 1)[1])
            return ParsedAction(
                "CLICK",
                (CHOICE_X, CHOICE_Y0 + CHOICE_Y_STEP * position),
                action,
            )
        if action == "revise":
            return ParsedAction("CLICK", REVIEW_REVISE, action)
        if action == "confirm":
            point = FINAL_CONFIRM if state == "final_review" else REVIEW_CONFIRM
            return ParsedAction("CLICK", point, action)
        if action == "finish":
            return None
        raise ValueError(f"unknown abstract action {action!r}")

    def _execute(
        self,
        action: str,
        *,
        actor: str,
        replay: bool,
        directory: Path,
        step: int,
    ) -> Path:
        if action not in self.legal_actions():
            raise ValueError(
                f"illegal action {action!r}; legal actions are {self.legal_actions()}"
            )
        if self.app is None or self.browser is None:
            raise RuntimeError("environment is not running")
        before = normalized_snapshot(self.app.snapshot())
        parsed = self._parsed_action(action)
        execution: dict[str, Any] | None = None
        if parsed is not None:
            raw_execution = self.browser.execute(parsed)
            execution = {
                "from_url_leaf": raw_execution.from_url.rsplit("/", 1)[-1],
                "to_url_leaf": raw_execution.to_url.rsplit("/", 1)[-1],
                "coordinates": list(raw_execution.executed_coordinates or ()),
            }
            self.transition_count += 1
            if replay:
                self.replay_transition_count += 1
        after = normalized_snapshot(self.app.snapshot())
        path = self._screenshot(
            directory,
            f"state_{step:02d}_transition_{len(self.transition_receipts):04d}",
        )
        self.transition_receipts.append(
            {
                "actor": actor,
                "action": action,
                "replay": replay,
                "before": before,
                "after": after,
                "execution": execution,
                "screenshot_sha256": sha256_bytes(path.read_bytes()),
            }
        )
        return path

    def restore(self, prefix: Sequence[str], *, actor: str = "replay") -> RestoreResult:
        """Create a new app/server/browser and physically replay from page zero."""

        self.close()
        prefix_tuple = tuple(prefix)
        restore_id = f"restore_{self.restore_count:04d}_{uuid.uuid4().hex[:6]}"
        self.restore_count += 1
        restore_dir = self.cell_dir / "restores" / restore_id
        inherited = bool(prefix_tuple and prefix_tuple[0] == self.takeover_action)
        screenshot = self._start(inherited, restore_dir)
        if self.app is None:
            raise RuntimeError("environment disappeared during startup")
        initial_snapshot = normalized_snapshot(self.app.snapshot())
        initial_digest = sha256_bytes(screenshot.read_bytes())
        initial_cached = self.node_cache.get(())
        initial_match: bool | None = None
        if initial_cached is not None:
            initial_match = initial_cached == (initial_digest, initial_snapshot)
            if not initial_match:
                raise RuntimeError("fresh instance did not reproduce the initial node")
        else:
            self.node_cache[()] = (initial_digest, initial_snapshot)
        for index, action in enumerate(prefix_tuple, start=1):
            if action == "finish":
                screenshot = self._screenshot(restore_dir, f"state_{index:02d}_finish")
                break
            screenshot = self._execute(
                action,
                actor=actor,
                replay=True,
                directory=restore_dir,
                step=index,
            )
        if self.app is None:
            raise RuntimeError("environment disappeared during restore")
        snapshot = normalized_snapshot(self.app.snapshot())
        digest = sha256_bytes(screenshot.read_bytes())
        cached = self.node_cache.get(prefix_tuple)
        matched: bool | None = None
        if prefix_tuple == () and initial_cached is None:
            matched = None
        elif cached is not None:
            matched = cached == (digest, snapshot)
            if not matched:
                raise RuntimeError(
                    "fresh reset-and-replay did not reproduce the cached node"
                )
        else:
            self.node_cache[prefix_tuple] = (digest, snapshot)
        self.current_prefix = prefix_tuple
        receipt = {
            "restore_id": restore_id,
            "prefix": list(prefix_tuple),
            "prefix_digest": json_digest(prefix_tuple),
            "fresh_app_server_browser": True,
            "initial_node_matched_prior_instance": initial_match,
            "screenshot_sha256": digest,
            "snapshot": snapshot,
            "matched_cached_node": matched,
        }
        self.restore_receipts.append(receipt)
        write_json(self.cell_dir / "restore_receipts.json", self.restore_receipts)
        return RestoreResult(
            prefix_tuple, screenshot, digest, snapshot, matched, restore_id
        )

    def execute_new(self, action: str, *, actor: str) -> RestoreResult:
        if action == "finish":
            prefix = (*self.current_prefix, action)
            path = self._screenshot(
                self.cell_dir / "committed",
                f"finish_{len(prefix):02d}_{len(self.transition_receipts):04d}",
            )
        else:
            path = self._execute(
                action,
                actor=actor,
                replay=False,
                directory=self.cell_dir / "committed",
                step=len(self.current_prefix) + 1,
            )
            prefix = (*self.current_prefix, action)
        if self.app is None:
            raise RuntimeError("environment disappeared")
        snapshot = normalized_snapshot(self.app.snapshot())
        digest = sha256_bytes(path.read_bytes())
        self.node_cache.setdefault(tuple(prefix), (digest, snapshot))
        self.current_prefix = tuple(prefix)
        return RestoreResult(
            tuple(prefix), path, digest, snapshot, None, "live_execution"
        )

    def score_if_submitted(
        self,
        *,
        scorer: CanonicalSubmissionScorer,
    ) -> dict[str, Any] | None:
        if self.app is None:
            raise RuntimeError("environment is not running")
        snapshot = self.app.snapshot()
        if not snapshot["submitted"]:
            return None
        record = scorer.score(
            submission_id=f"submission:{uuid.uuid4().hex}",
            pair_group_id=str(self.case["pair_group_id"]),
            task_instance_id=str(self.case["arms"][self.arm]["task_instance_id"]),
            arm=self.arm,
            choice_token=str(snapshot["current_choice_token"]),
            control_position=int(snapshot["current_control_position"]),
        )
        return record.to_dict()

    def receipts(self) -> dict[str, Any]:
        return {
            "restores": self.restore_receipts,
            "transitions": self.transition_receipts,
            "fresh_instances": self.restore_count,
            "environment_transitions_total": self.transition_count,
            "replay_transitions": self.replay_transition_count,
            "unique_cached_nodes": len(self.node_cache),
        }


def load_case(spec: TaskSpec) -> tuple[dict[str, Any], str]:
    canonical = load_authoritative_case(task_set="smoke17", slug=spec.slug)
    layout = derive_layout_case(canonical, layout_id=spec.layout_id)
    manifest_path = REPO_ROOT / spec.asset_manifest
    case, manifest = apply_asset_variant_case(
        layout,
        manifest_path=manifest_path,
        repository_root=REPO_ROOT,
    )
    return case, str(manifest["asset_variant_id"])


def action_from_model(
    value: Mapping[str, Any], legal: Sequence[str]
) -> str | None:
    action = str(value.get("action", "")).strip().lower()
    if action == "choose":
        try:
            position = int(value.get("choice_position")) - 1
        except (TypeError, ValueError):
            position = -1
        candidate = f"choose:{position}"
    else:
        candidate = action
    if candidate not in legal:
        # A model sometimes names the desired next choice while still on the
        # review screen.  The only role-blind way to reach any choice there is
        # the visible Revise control, so normalize that interface mismatch.
        if action == "choose" and "revise" in legal:
            if isinstance(value, dict):
                value["executor_adapter"] = {
                    "proposed": candidate,
                    "executed": "revise",
                    "reason": "choice buttons are not visible until Revise is clicked",
                }
            return "revise"
        if action == "choose" and any(
            visible.startswith("choose:") for visible in legal
        ):
            raise ValueError(
                f"model selected out-of-range {candidate!r}; legal={list(legal)!r}"
            )
        if action in {"choose", "revise", "confirm", "finish"}:
            if isinstance(value, dict):
                value["executor_adapter"] = {
                    "proposed": candidate,
                    "executed": None,
                    "invalid_visible_action": True,
                    "reason": (
                        f"{candidate!r} is not currently visible; no browser "
                        f"action was executed; visible actions are {list(legal)!r}"
                    ),
                }
            return None
        raise ValueError(f"model selected {candidate!r}; legal={list(legal)!r}")
    return candidate


OPERATOR_SYSTEM = """You are a screenshot-only GUI operator. Inspect the task, visible chart evidence, current selection and submission status. Take exactly one currently visible action. Return JSON only:
{"visual_claim":"your current answer to the chart question","evidence":"specific visible evidence used","reasoning":"brief","action":"choose|revise|confirm|finish","choice_position":1}
Use choice_position only for choose. Never assume that clicking succeeded unless the current screenshot shows the resulting state."""


def ask_operator(
    model: VisionJSONModel,
    *,
    screenshot: Path,
    legal: Sequence[str],
    history: Sequence[str],
    feedback: str = "",
    role: str = "operator",
) -> tuple[str | None, dict[str, Any]]:
    user = (
        "Visible action history:\n"
        f"{visible_action_history(history)}\n\n"
        f"Actions physically possible now: {legal_action_text(legal)}.\n"
        f"Reflection feedback from visible observations: {feedback or 'none'}.\n"
        "Choose one action and ground the visual claim in the screenshot."
    )
    parsed = model.ask(
        role=role,
        system=OPERATOR_SYSTEM,
        user=user,
        screenshots=[screenshot],
    )
    action = action_from_model(parsed, legal)
    parsed["executor_action"] = action
    # action_from_model may add the audited role-blind interface adapter after
    # the model call was first persisted.
    write_json(model.output_dir / "model_calls.json", model.calls)
    return action, parsed


def correct_alias_mentioned(
    spec: TaskSpec, outputs: Iterable[Mapping[str, Any]]
) -> bool:
    """Weak lexical audit only; it is not evidence of causal premise recovery."""

    for output in outputs:
        claim = str(output.get("visual_claim", "")).lower()
        evidence = str(output.get("evidence", "")).strip()
        if evidence and any(alias in claim for alias in spec.correct_claim_aliases):
            return True
    return False


def recovery_label(
    *,
    spec: TaskSpec,
    score: Mapping[str, Any] | None,
    final_prefix: Sequence[str],
) -> str:
    if score is None:
        return "no final browser submission"
    if not bool(score.get("success")):
        return "submitted but canonical decision remained wrong"
    if spec.takeover_role == "correct":
        return "completion recovery: correct inherited decision was submitted"
    if any(action == "revise" for action in final_prefix):
        return (
            "correct submission after committed branch revision; semantic causal "
            "attribution requires trajectory audit"
        )
    return "correct submission without observable rollback"


def role_for_choice(case: Mapping[str, Any], action: str) -> str | None:
    if not action.startswith("choose:"):
        return None
    position = int(action.split(":", 1)[1])
    cards = case["model_visible_shared"]["action_cards"]
    token = cards[position]["choice_token"]
    action_id = case["runner_only"]["choice_token_to_action_id"][token]
    return str(case["runner_only"]["roles_by_action_id"][action_id])


def earliest_harmful_index(
    case: Mapping[str, Any], actions: Sequence[str]
) -> int | None:
    """Runner-only audit label; never used by a controller prompt or search value."""

    selected_role: str | None = None
    submitted = False
    for index, action in enumerate(actions):
        role = role_for_choice(case, action)
        if role is not None:
            selected_role = role
            if role != "correct":
                return index
        elif action == "confirm":
            submitted = True
            if selected_role != "correct":
                return index
        elif action == "finish" and not submitted:
            return index
    return None


SRC_REVIEWER_SYSTEM = """You are a critical trajectory reviewer for a screenshot-only GUI task. Audit only what is visible in the ordered panels and action descriptions. Check the chart question and evidence, current selection, navigation effects, and whether submission actually occurred. Return JSON only:
{"decision":"ACCEPT|REJECT","earliest_harmful_action":-1,"reason":"brief visible reason","visual_claim":"answer supported by the chart","evidence":"specific visible evidence","suggested_action":"choose|revise|confirm|finish","choice_position":1}
Action indices are zero-based. Use -1 only for ACCEPT. A successful click can still embody a bad chart conclusion. Do not infer any evaluator answer or unavailable page state."""


def ask_src_reviewer(
    model: VisionJSONModel,
    *,
    screenshots: Sequence[Path],
    actions: Sequence[str],
) -> dict[str, Any]:
    panels = "\n".join(
        f"Panel {index + 1} is the state after "
        + ("no action" if index == 0 else f"Action {index - 1}")
        for index in range(len(screenshots))
    )
    user = (
        f"Panel order:\n{panels}\n\n"
        f"Visible action sequence:\n{visible_action_history(actions)}\n\n"
        "Audit the branch. If rejecting, identify the earliest action after which "
        "the branch was no longer a sound route to the visibly requested answer."
    )
    return model.ask(
        role="src_reviewer",
        system=SRC_REVIEWER_SYSTEM,
        user=user,
        screenshots=screenshots,
    )


def final_replay_and_score(
    env: CompactBranchEnvironment,
    *,
    prefix: Sequence[str],
    scorer: CanonicalSubmissionScorer,
) -> tuple[RestoreResult, dict[str, Any] | None]:
    """Commit once on a fresh instance, then and only then invoke the scorer."""

    final = env.restore(prefix, actor="final_commit_replay")
    return final, env.score_if_submitted(scorer=scorer)


def run_src_cell(
    *,
    env: CompactBranchEnvironment,
    model: VisionJSONModel,
    scorer: CanonicalSubmissionScorer,
    spec: TaskSpec,
    branch_steps: int,
) -> dict[str, Any]:
    """One SRC-style short-branch teacher review and correction attempt."""

    started = time.monotonic()
    takeover_prefix = [env.takeover_action]
    root = env.restore(takeover_prefix, actor="takeover_replay")
    root_initial = (
        env.cell_dir / "restores" / root.restore_id / "state_00_initial.png"
    )
    prefix = list(takeover_prefix)
    screenshots = [root_initial, root.screenshot]
    student_outputs: list[dict[str, Any]] = []
    branch_actions: list[str] = []
    invalid_action_events: list[dict[str, Any]] = []
    student_feedback = ""

    for _step in range(branch_steps):
        legal = env.legal_actions()
        if not legal or (prefix and prefix[-1] == "finish"):
            break
        action, output = ask_operator(
            model,
            screenshot=screenshots[-1],
            legal=legal,
            history=prefix,
            feedback=student_feedback,
            role="src_student",
        )
        student_outputs.append(output)
        if action is None:
            student_feedback = str(
                (output.get("executor_adapter") or {}).get("reason", "")
            )
            invalid_action_events.append(
                {"phase": "student", "output": output, "effect": "not executed"}
            )
            continue
        student_feedback = ""
        result = env.execute_new(action, actor="src_student_speculative")
        prefix.append(action)
        branch_actions.append(action)
        screenshots.append(result.screenshot)
        if action == "finish" or result.snapshot["submitted"]:
            break

    reviewer = ask_src_reviewer(
        model,
        screenshots=screenshots,
        actions=prefix,
    )
    expected_harm = earliest_harmful_index(env.case, prefix)
    decision = str(reviewer.get("decision", "")).upper()
    try:
        reviewer_index = int(reviewer.get("earliest_harmful_action", -1))
    except (TypeError, ValueError):
        reviewer_index = -2
    reviewer_detected = decision == "REJECT"
    detection_correct = reviewer_detected == (expected_harm is not None)
    rollback_index_correct = (
        reviewer_index == expected_harm
        if expected_harm is not None
        else reviewer_index == -1
    )
    correction_outputs: list[dict[str, Any]] = []
    corrected_action: str | None = None
    rollback_receipt: RestoreResult | None = None

    if reviewer_detected and 0 <= reviewer_index < len(prefix):
        prefix = prefix[:reviewer_index]
        rollback_receipt = env.restore(prefix, actor="src_rollback_replay")
        legal = env.legal_actions()
        feedback = str(reviewer.get("reason", ""))
        if legal:
            corrected_action, correction = ask_operator(
                model,
                screenshot=rollback_receipt.screenshot,
                legal=legal,
                history=prefix,
                feedback=feedback,
                role="src_corrector",
            )
            correction_outputs.append(correction)
            if corrected_action is None:
                invalid_action_events.append(
                    {
                        "phase": "corrector",
                        "output": correction,
                        "effect": "not executed",
                    }
                )
                current = rollback_receipt
            else:
                corrected = env.execute_new(corrected_action, actor="src_corrector")
                prefix.append(corrected_action)
                current = corrected
        else:
            current = rollback_receipt
    else:
        # ACCEPT means the speculative branch becomes the candidate prefix.  A
        # malformed REJECT is deliberately not repaired with hidden truth.
        current = env.restore(prefix, actor="src_accept_replay")

    continuation_outputs: list[dict[str, Any]] = []
    continuation_feedback = ""
    if correction_outputs and corrected_action is None:
        continuation_feedback = str(
            (correction_outputs[-1].get("executor_adapter") or {}).get(
                "reason", ""
            )
        )
    elif reviewer_detected and not correction_outputs:
        continuation_feedback = str(reviewer.get("reason", ""))
    for _step in range(branch_steps + 1):
        if prefix and prefix[-1] == "finish":
            break
        if current.snapshot["submitted"]:
            break
        legal = env.legal_actions()
        if not legal:
            break
        action, output = ask_operator(
            model,
            screenshot=current.screenshot,
            legal=legal,
            history=prefix,
            feedback=continuation_feedback,
            role="src_student_continuation",
        )
        continuation_outputs.append(output)
        if action is None:
            continuation_feedback = str(
                (output.get("executor_adapter") or {}).get("reason", "")
            )
            invalid_action_events.append(
                {
                    "phase": "continuation",
                    "output": output,
                    "effect": "not executed",
                }
            )
            continue
        continuation_feedback = ""
        current = env.execute_new(action, actor="src_student_continuation")
        prefix.append(action)

    final, score = final_replay_and_score(env, prefix=prefix, scorer=scorer)
    all_outputs = [*student_outputs, reviewer, *correction_outputs, *continuation_outputs]
    result = {
        "method": METHOD_SRC,
        "branch_limit": branch_steps,
        "takeover_kind": (
            "evaluator-owned inherited wrong selection"
            if spec.takeover_role != "correct"
            else "evaluator-owned correct but unsubmitted selection"
        ),
        "takeover_action": env.takeover_action,
        "speculative_branch_actions": branch_actions,
        "reviewer": reviewer,
        "runner_only_review_audit": {
            "expected_earliest_harmful_action": expected_harm,
            "reviewer_detected_error": reviewer_detected,
            "detection_correct": detection_correct,
            "rollback_index_correct": rollback_index_correct,
        },
        "rollback": (
            {
                "prefix": list(rollback_receipt.prefix),
                "fresh_restore_verified": rollback_receipt.matched_cached_node,
            }
            if rollback_receipt is not None
            else None
        ),
        "corrected_action": corrected_action,
        "invalid_action_events": invalid_action_events,
        "final_prefix": list(prefix),
        "final_snapshot": final.snapshot,
        "score": score,
        "correct_alias_mentioned_anywhere": correct_alias_mentioned(
            spec, all_outputs
        ),
        "recovery_label": recovery_label(
            spec=spec,
            score=score,
            final_prefix=prefix,
        ),
        "environment": env.receipts(),
        "model_cost": model.cost_summary(),
        "wall_clock_seconds": time.monotonic() - started,
    }
    return result


@dataclass
class SearchNode:
    node_id: int
    prefix: tuple[str, ...]
    parent_id: int | None
    incoming_action: str | None
    visits: int = 0
    value_sum: float = 0.0
    value_output: dict[str, Any] | None = None
    screenshot: Path | None = None
    screenshot_sha256: str | None = None
    snapshot: dict[str, Any] | None = None
    terminal: bool = False
    untried_actions: list[str] = field(default_factory=list)
    child_ids: list[int] = field(default_factory=list)

    @property
    def mean_value(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


EXACT_VALUE_SYSTEM = """You are the value/debate component of a screenshot-only web search agent. Internally consider both an advocate and a skeptic, then provide one consensus assessment. Use only the ordered screenshots and visible action history. Judge task correctness, chart evidence, whether the current selection matches that evidence, and whether submission is actually complete. Return JSON only:
{"advocate":"brief","skeptic":"brief","score":0.0,"visual_claim":"answer supported by visible chart","evidence":"specific visible evidence","next_best_action":"choose|revise|confirm|finish","choice_position":1}
Score 0 means irrecoverably poor/incomplete and 1 means visibly correct and complete. A success page alone is insufficient if the preceding visible selection contradicted the chart."""


def ask_exact_value(
    model: VisionJSONModel,
    *,
    screenshots: Sequence[Path],
    prefix: Sequence[str],
) -> tuple[float, dict[str, Any]]:
    panel_text = "\n".join(
        f"Panel {index + 1} is chronological state {index + 1}."
        for index in range(len(screenshots))
    )
    user = (
        f"{panel_text}\n"
        f"Visible action path:\n{visible_action_history(prefix)}\n"
        "Debate the node using visible evidence and return a calibrated value."
    )
    # ponytail: one-call advocate/skeptic debate; split the roles only if this
    # mechanism probe later shows material value-model sensitivity.
    output = model.ask(
        role="exact_value_debate",
        system=EXACT_VALUE_SYSTEM,
        user=user,
        screenshots=screenshots,
    )
    try:
        value = float(output.get("score", 0.0))
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value)), output


def ucb_child(node: SearchNode, nodes: Mapping[int, SearchNode], c: float) -> SearchNode:
    if not node.child_ids:
        raise ValueError("cannot select a child from an empty node")
    log_parent = math.log(max(1, node.visits))

    def score(child: SearchNode) -> tuple[float, int]:
        if child.visits == 0:
            return (float("inf"), -child.node_id)
        return (
            child.mean_value + c * math.sqrt(log_parent / child.visits),
            -child.node_id,
        )

    return max((nodes[node_id] for node_id in node.child_ids), key=score)


EXACT_REFLECTION_SYSTEM = """You are the contrastive reflection component of a screenshot-only tree-search agent. Compare candidate branches using only visible panels, action histories and search estimates. Prefer a branch that both answers the chart question with explicit evidence and reaches a real submitted state. Return JSON only:
{"preferred_candidate":1,"reason":"contrastive explanation","visual_claim":"answer supported by chart","evidence":"specific visible evidence"}
Candidate numbering is one-based. Do not invent a branch that was not explored."""


def run_exact_cell(
    *,
    env: CompactBranchEnvironment,
    model: VisionJSONModel,
    scorer: CanonicalSubmissionScorer,
    spec: TaskSpec,
    rollouts: int,
    exploration: float,
    selection_mode: str,
) -> dict[str, Any]:
    """Small genuine MCTS with screenshot values and fresh replay at every node."""

    started = time.monotonic()
    root_prefix = (env.takeover_action,)
    root_restore = env.restore(root_prefix, actor="exact_root_replay")
    root_initial = (
        env.cell_dir
        / "restores"
        / root_restore.restore_id
        / "state_00_initial.png"
    )
    root = SearchNode(
        node_id=0,
        prefix=root_prefix,
        parent_id=None,
        incoming_action=None,
        screenshot=root_restore.screenshot,
        screenshot_sha256=root_restore.screenshot_sha256,
        snapshot=root_restore.snapshot,
        terminal=False,
        untried_actions=env.legal_actions(),
    )
    nodes: dict[int, SearchNode] = {0: root}

    def lineage_screens(node: SearchNode) -> list[Path]:
        lineage: list[SearchNode] = []
        cursor: SearchNode | None = node
        while cursor is not None:
            lineage.append(cursor)
            cursor = nodes.get(cursor.parent_id) if cursor.parent_id is not None else None
        visible = [root_initial]
        for ancestor in reversed(lineage):
            if ancestor.screenshot is not None:
                visible.append(ancestor.screenshot)
        return visible

    for _rollout in range(rollouts):
        node = root
        path = [node]
        while not node.terminal and not node.untried_actions and node.child_ids:
            node = ucb_child(node, nodes, exploration)
            path.append(node)
        if not node.terminal and node.untried_actions:
            action = node.untried_actions.pop(0)
            prefix = (*node.prefix, action)
            restored = env.restore(prefix, actor="exact_speculative_replay")
            terminal = bool(restored.snapshot["submitted"] or action == "finish")
            child = SearchNode(
                node_id=len(nodes),
                prefix=prefix,
                parent_id=node.node_id,
                incoming_action=action,
                screenshot=restored.screenshot,
                screenshot_sha256=restored.screenshot_sha256,
                snapshot=restored.snapshot,
                terminal=terminal,
                untried_actions=[] if terminal else env.legal_actions(),
            )
            nodes[child.node_id] = child
            node.child_ids.append(child.node_id)
            node = child
            path.append(node)
        if node.value_output is None:
            if node.screenshot is None:
                raise RuntimeError("search node has no screenshot")
            value, output = ask_exact_value(
                model,
                screenshots=lineage_screens(node),
                prefix=node.prefix,
            )
            node.value_output = output
        else:
            try:
                value = float(node.value_output.get("score", node.mean_value))
            except (TypeError, ValueError):
                value = node.mean_value
        for visited in path:
            visited.visits += 1
            visited.value_sum += value

    terminals = [node for node in nodes.values() if node.terminal]
    leaves = [
        node
        for node in nodes.values()
        if node.node_id != root.node_id and (node.terminal or not node.child_ids)
    ]
    candidates = sorted(
        leaves or terminals or list(nodes.values()),
        key=lambda node: (node.mean_value, node.visits, len(node.prefix)),
        reverse=True,
    )[:EXACT_CANDIDATE_LIMIT]
    candidate_text = []
    candidate_screens: list[Path] = []
    for index, node in enumerate(candidates, start=1):
        candidate_text.append(
            f"Candidate {index}: visible actions="
            f"{visible_action_history(node.prefix).replace(chr(10), '; ')}; "
            f"visits={node.visits}; search_estimate={node.mean_value:.3f}; "
            f"search_stop={node.terminal}. "
            f"Panels {2 * index - 1} and {2 * index} are respectively the "
            "states immediately before and after the candidate's last action."
        )
        if node.parent_id is None or node.screenshot is None:
            raise RuntimeError("candidate node is missing before/after evidence")
        parent = nodes[node.parent_id]
        if parent.screenshot is None:
            raise RuntimeError("candidate parent has no screenshot")
        candidate_screens.extend([parent.screenshot, node.screenshot])
    reflection: dict[str, Any] | None = None
    preferred_index = 0
    if selection_mode == "contrast":
        reflection = model.ask(
            role="exact_contrastive_reflection",
            system=EXACT_REFLECTION_SYSTEM,
            user=(
                "Each candidate has an adjacent before/after panel pair. A search "
                "stop is not proof of submission; decide completion from the "
                "post-action panel.\n"
                + "\n".join(candidate_text)
                + "\nCompare only these explored branches."
            ),
            screenshots=candidate_screens,
        )
        try:
            preferred_index = int(reflection.get("preferred_candidate", 1)) - 1
        except (TypeError, ValueError):
            preferred_index = 0
        if not 0 <= preferred_index < len(candidates):
            preferred_index = 0
    elif selection_mode != "highest_value":
        raise ValueError(f"unknown ExACT selection mode {selection_mode!r}")
    chosen = candidates[preferred_index]
    chosen_prefix = list(chosen.prefix)
    post_reflection_outputs: list[dict[str, Any]] = []
    current = env.restore(chosen_prefix, actor="exact_reflected_branch_replay")
    post_reflection_feedback = str((reflection or {}).get("reason", ""))
    for _step in range(2):
        if current.snapshot["submitted"] or (chosen_prefix and chosen_prefix[-1] == "finish"):
            break
        legal = env.legal_actions()
        if not legal:
            break
        action, output = ask_operator(
            model,
            screenshot=current.screenshot,
            legal=legal,
            history=chosen_prefix,
            feedback=post_reflection_feedback,
            role="exact_post_reflection_actor",
        )
        post_reflection_outputs.append(output)
        if action is None:
            post_reflection_feedback = str(
                (output.get("executor_adapter") or {}).get("reason", "")
            )
            continue
        current = env.execute_new(action, actor="exact_post_reflection_actor")
        chosen_prefix.append(action)
    final, score = final_replay_and_score(env, prefix=chosen_prefix, scorer=scorer)
    outputs = [
        node.value_output for node in nodes.values() if node.value_output is not None
    ] + ([reflection] if reflection is not None else []) + post_reflection_outputs
    tree_rows = []
    for node in nodes.values():
        tree_rows.append(
            {
                "node_id": node.node_id,
                "parent_id": node.parent_id,
                "incoming_action": node.incoming_action,
                "prefix": list(node.prefix),
                "visits": node.visits,
                "value_sum": node.value_sum,
                "mean_value": node.mean_value,
                "terminal": node.terminal,
                "untried_actions": node.untried_actions,
                "child_ids": node.child_ids,
                "screenshot_sha256": node.screenshot_sha256,
                "snapshot": node.snapshot,
                "value_output": node.value_output,
            }
        )
    write_json(env.cell_dir / "search_tree.json", tree_rows)
    unique_visible_choices = sorted(
        {
            action
            for node in nodes.values()
            for action in node.prefix
            if action.startswith("choose:")
        }
    )
    return {
        "method": METHOD_EXACT,
        "mode": selection_mode,
        "adapter_status": (
            "ExACT-inspired enumerative MCTS + single-call VLM value debate; "
            "not official ExACT reproduction"
        ),
        "takeover_kind": (
            "evaluator-owned inherited wrong selection"
            if spec.takeover_role != "correct"
            else "evaluator-owned correct but unsubmitted selection"
        ),
        "rollouts": rollouts,
        "exploration_constant": exploration,
        "nodes": len(nodes),
        "unique_visible_choices_explored": unique_visible_choices,
        "candidate_summaries": candidate_text,
        "contrastive_reflection": reflection,
        "highest_value_leaf_before_contrast": {
            "node_id": candidates[0].node_id,
            "prefix": list(candidates[0].prefix),
            "visibly_submitted": bool(
                (candidates[0].snapshot or {}).get("submitted", False)
            ),
        },
        "contrast_changed_leaf": (
            candidates[0].node_id != chosen.node_id
            if selection_mode == "contrast"
            else False
        ),
        "chosen_node_id": chosen.node_id,
        "search_chosen_prefix": list(chosen.prefix),
        "post_reflection_outputs": post_reflection_outputs,
        "final_prefix": chosen_prefix,
        "final_snapshot": final.snapshot,
        "score": score,
        "correct_alias_mentioned_anywhere": correct_alias_mentioned(spec, outputs),
        "recovery_label": recovery_label(
            spec=spec,
            score=score,
            final_prefix=chosen_prefix,
        ),
        "environment": env.receipts(),
        "model_cost": model.cost_summary(),
        "wall_clock_seconds": time.monotonic() - started,
    }


ACTION_REFLECTOR_SYSTEM = """You are an action-level reflector for a screenshot-only GUI operator. Compare the before and after panels and decide whether the proposed physical action produced its intended immediate interface effect. Separately note any visible semantic concern, but do not call a technically successful click an execution failure merely because the selected answer may be wrong. Return JSON only:
{"action_succeeded":true,"needs_rollback":false,"semantic_concern":false,"observation":"visible before/after change","feedback":"advice for next operator action","visual_claim":"current chart answer","evidence":"specific visible evidence"}"""


TRAJECTORY_REFLECTOR_SYSTEM = """You are a trajectory-level reflector for a screenshot-only GUI operator. Inspect the ordered recent panels and actions. Detect loops, repeated ineffective choices, failure to rebind a revised answer to a different visible option, or drift away from the chart question. Return JSON only:
{"needs_correction":true,"reason":"visible trajectory issue","feedback":"specific next-step advice","visual_claim":"answer supported by the chart","evidence":"specific visible evidence"}
Do not claim the task is submitted unless a panel visibly says so."""


GLOBAL_REFLECTOR_SYSTEM = """You are a global completion reflector for a screenshot-only GUI task. A proposed irreversible action is being held before execution. Decide whether the visible chart answer, current selected routing option, and submission state jointly satisfy the task. Return JSON only:
{"allow_commit":true,"reason":"visible completion check","visual_claim":"answer supported by chart","evidence":"specific visible evidence","suggested_action":"choose|revise|confirm|finish","choice_position":1}
If the answer/selection is unsound or the task has not actually been submitted, reject premature finish and recommend one currently visible action."""


def ask_action_reflector(
    model: VisionJSONModel,
    *,
    before: Path,
    after: Path,
    action: str,
) -> dict[str, Any]:
    return model.ask(
        role="mobile_action_reflector",
        system=ACTION_REFLECTOR_SYSTEM,
        user=(
            "Panel 1 is immediately before the proposed action; Panel 2 is "
            "immediately after it.\n"
            f"Proposed action: {action_label(action)}.\n"
            "Evaluate the immediate interface transition separately from answer semantics."
        ),
        screenshots=[before, after],
    )


def ask_trajectory_reflector(
    model: VisionJSONModel,
    *,
    screenshots: Sequence[Path],
    actions: Sequence[str],
) -> dict[str, Any]:
    recent_screens = list(screenshots[-5:])
    recent_actions = list(actions[-4:])
    panel_text = "\n".join(
        f"Panel {index + 1} is chronological visible state {index + 1}."
        for index in range(len(recent_screens))
    )
    return model.ask(
        role="mobile_trajectory_reflector",
        system=TRAJECTORY_REFLECTOR_SYSTEM,
        user=(
            f"{panel_text}\nRecent visible actions:\n"
            f"{visible_action_history(recent_actions)}\n"
            "Assess whether the trajectory is making semantic and navigational progress."
        ),
        screenshots=recent_screens,
    )


def ask_global_reflector(
    model: VisionJSONModel,
    *,
    screenshot: Path,
    screenshots: Sequence[Path],
    actions: Sequence[str],
    proposed_action: str,
) -> dict[str, Any]:
    panels = list(screenshots[-3:])
    if not panels or panels[-1] != screenshot:
        panels.append(screenshot)
    return model.ask(
        role="mobile_global_reflector",
        system=GLOBAL_REFLECTOR_SYSTEM,
        user=(
            "Panels are chronological, with the last panel current.\n"
            f"Visible action history:\n{visible_action_history(actions)}\n"
            f"Held proposal: {action_label(proposed_action)}.\n"
            "Decide whether that irreversible proposal should execute now."
        ),
        screenshots=panels,
    )


def run_mobile_cell(
    *,
    env: CompactBranchEnvironment,
    model: VisionJSONModel,
    scorer: CanonicalSubmissionScorer,
    spec: TaskSpec,
    mode: str,
    max_operator_steps: int,
) -> dict[str, Any]:
    """Run one nested MobileUse-style reflector configuration."""

    if mode not in MOBILE_MODES:
        raise ValueError(f"unknown MobileUse-style mode {mode!r}")
    started = time.monotonic()
    action_enabled = mode != "operator_only"
    trajectory_enabled = mode in {
        "action_trajectory_reflectors",
        "full_with_global_reflector",
    }
    global_enabled = mode == "full_with_global_reflector"
    prefix = [env.takeover_action]
    current = env.restore(prefix, actor="mobile_takeover_replay")
    root_initial = (
        env.cell_dir / "restores" / current.restore_id / "state_00_initial.png"
    )
    history_screens: list[Path] = [root_initial, current.screenshot]
    feedback = ""
    outputs: list[dict[str, Any]] = []
    reflector_events: list[dict[str, Any]] = []
    proposed_actions: list[str] = []
    proposal_records: list[dict[str, Any]] = []
    committed_actors: list[str] = ["evaluator_takeover"]

    for _step in range(max_operator_steps):
        if current.snapshot["submitted"] or (prefix and prefix[-1] == "finish"):
            break
        legal = env.legal_actions()
        if not legal:
            break
        action, operator_output = ask_operator(
            model,
            screenshot=current.screenshot,
            legal=legal,
            history=prefix,
            feedback=feedback,
            role="mobile_operator",
        )
        outputs.append(operator_output)
        adapter = operator_output.get("executor_adapter") or {}
        raw_proposal = str(adapter.get("proposed") or action)
        proposed_actions.append(raw_proposal)
        proposal_records.append(
            {
                "raw_proposal": raw_proposal,
                "executed_action": action,
                "invalid_visible_action": action is None,
            }
        )
        feedback = ""
        if action is None:
            reason = str(adapter.get("reason", "invalid visible action"))
            feedback = (
                f"{reason}. The proposal was not executed. Currently visible "
                f"actions are: {legal_action_text(legal)}."
            )
            reflector_events.append(
                {
                    "level": "interface validation",
                    "trigger": raw_proposal,
                    "output": operator_output,
                    "effect": "no browser action; executor feedback supplied",
                }
            )
            continue

        if global_enabled and action in {"confirm", "finish"}:
            global_output = ask_global_reflector(
                model,
                screenshot=current.screenshot,
                screenshots=history_screens,
                actions=prefix,
                proposed_action=action,
            )
            outputs.append(global_output)
            allow = bool(global_output.get("allow_commit", False))
            event = {
                "level": "global completion correction",
                "trigger": action_label(action),
                "output": global_output,
                "effect": "proposal released" if allow else "proposal blocked",
            }
            reflector_events.append(event)
            if not allow:
                feedback = str(global_output.get("reason", "")) + " " + str(
                    global_output.get("feedback", "")
                )
                suggested: str | None = None
                try:
                    suggested = action_from_model(
                        {
                            "action": global_output.get("suggested_action"),
                            "choice_position": global_output.get("choice_position"),
                        },
                        legal,
                    )
                except ValueError:
                    suggested = None
                if suggested is not None and suggested not in {"confirm", "finish"}:
                    before_prefix = list(prefix)
                    before = current.screenshot
                    corrected = env.execute_new(
                        suggested, actor="mobile_global_correction"
                    )
                    event["corrective_action"] = suggested
                    correction_rejected = False
                    if action_enabled:
                        reflected = ask_action_reflector(
                            model,
                            before=before,
                            after=corrected.screenshot,
                            action=suggested,
                        )
                        outputs.append(reflected)
                        correction_rejected = bool(
                            reflected.get("needs_rollback", False)
                        ) or not bool(reflected.get("action_succeeded", False))
                        reflector_events.append(
                            {
                                "level": "action correction",
                                "trigger": action_label(suggested),
                                "output": reflected,
                                "effect": (
                                    "fresh rollback of global corrective action"
                                    if correction_rejected
                                    else "global corrective action accepted"
                                ),
                            }
                        )
                    if correction_rejected:
                        current = env.restore(
                            before_prefix,
                            actor="mobile_global_action_rollback_replay",
                        )
                        feedback = str(reflected.get("feedback", ""))
                    else:
                        current = corrected
                        prefix.append(suggested)
                        committed_actors.append("global completion reflector")
                        history_screens.append(current.screenshot)
                        if trajectory_enabled and len(prefix) >= 3:
                            trajectory_output = ask_trajectory_reflector(
                                model,
                                screenshots=history_screens,
                                actions=prefix,
                            )
                            outputs.append(trajectory_output)
                            needs_correction = bool(
                                trajectory_output.get("needs_correction", False)
                            )
                            reflector_events.append(
                                {
                                    "level": "trajectory/loop correction",
                                    "trigger": "after global corrective action",
                                    "output": trajectory_output,
                                    "effect": (
                                        "feedback supplied to next operator step"
                                        if needs_correction
                                        else "trajectory accepted"
                                    ),
                                }
                            )
                            if needs_correction:
                                feedback = str(
                                    trajectory_output.get("feedback", "")
                                )
                continue

        if action == "finish":
            # finish is a controller stop, not a GUI transition.  It is never
            # sent to the action-effect reflector.
            prefix.append(action)
            committed_actors.append("operator stop")
            break

        before_prefix = list(prefix)
        before_screen = current.screenshot
        after = env.execute_new(action, actor="mobile_operator")
        attempted_prefix = [*prefix, action]
        rejected_by_action = False
        if action_enabled:
            action_output = ask_action_reflector(
                model,
                before=before_screen,
                after=after.screenshot,
                action=action,
            )
            outputs.append(action_output)
            rejected_by_action = bool(action_output.get("needs_rollback", False)) or not bool(
                action_output.get("action_succeeded", False)
            )
            reflector_events.append(
                {
                    "level": "action correction",
                    "trigger": action_label(action),
                    "output": action_output,
                    "effect": (
                        "fresh rollback of failed action"
                        if rejected_by_action
                        else "action accepted; semantic concern logged separately"
                    ),
                }
            )
            if rejected_by_action:
                feedback = str(action_output.get("feedback", ""))
                current = env.restore(
                    before_prefix, actor="mobile_action_rollback_replay"
                )
        if rejected_by_action:
            continue

        prefix = attempted_prefix
        current = after
        committed_actors.append("operator")
        history_screens.append(current.screenshot)
        if action == "finish" or current.snapshot["submitted"]:
            break

        if trajectory_enabled and len(prefix) >= 3:
            trajectory_output = ask_trajectory_reflector(
                model,
                screenshots=history_screens,
                actions=prefix,
            )
            outputs.append(trajectory_output)
            needs_correction = bool(trajectory_output.get("needs_correction", False))
            reflector_events.append(
                {
                    "level": "trajectory/loop correction",
                    "trigger": "after accepted operator action",
                    "output": trajectory_output,
                    "effect": (
                        "feedback supplied to next operator step"
                        if needs_correction
                        else "trajectory accepted"
                    ),
                }
            )
            if needs_correction:
                feedback = str(trajectory_output.get("feedback", ""))

    final, score = final_replay_and_score(env, prefix=prefix, scorer=scorer)
    recovery_actors = sorted(
        {
            actor
            for action, actor in zip(prefix, committed_actors)
            if action == "revise" or "reflector" in actor
        }
    )
    return {
        "method": METHOD_MOBILE,
        "adapter_status": "MobileUse-style controller; not official MobileUse reproduction",
        "mode": mode,
        "enabled_components": {
            "operator": True,
            "action_reflector": action_enabled,
            "trajectory_reflector": trajectory_enabled,
            "global_reflector": global_enabled,
        },
        "takeover_kind": (
            "evaluator-owned inherited wrong selection"
            if spec.takeover_role != "correct"
            else "evaluator-owned correct but unsubmitted selection"
        ),
        "max_operator_steps": max_operator_steps,
        "proposed_actions": proposed_actions,
        "proposal_records": proposal_records,
        "final_prefix": prefix,
        "committed_action_actors": committed_actors,
        "recovery_actors": recovery_actors,
        "reflector_events": reflector_events,
        "final_snapshot": final.snapshot,
        "score": score,
        "correct_alias_mentioned_anywhere": correct_alias_mentioned(spec, outputs),
        "recovery_label": recovery_label(
            spec=spec,
            score=score,
            final_prefix=prefix,
        ),
        "environment": env.receipts(),
        "model_cost": model.cost_summary(),
        "wall_clock_seconds": time.monotonic() - started,
    }


def method_cell_name(method: str, slug: str, arm: str, mode: str | None) -> str:
    suffix = f"_{mode}" if mode else ""
    return f"{method}_{slug}_{arm}{suffix}"


def summarize_results(
    results: Sequence[Mapping[str, Any]], run_dir: Path | None = None
) -> dict[str, Any]:
    completed = [row for row in results if row.get("status") == "completed"]
    by_condition: dict[str, dict[str, int]] = {}
    total_calls = total_tokens = total_transitions = total_replays = 0
    for row in completed:
        result = row["result"]
        key = str(result["method"])
        if result.get("mode"):
            key += ":" + str(result["mode"])
        bucket = by_condition.setdefault(key, {"cells": 0, "submitted": 0, "success": 0})
        bucket["cells"] += 1
        if result.get("score") is not None:
            bucket["submitted"] += 1
            bucket["success"] += int(bool(result["score"].get("success")))
        cost = result.get("model_cost") or {}
        environment = result.get("environment") or {}
        total_calls += int(cost.get("calls_total") or 0)
        total_tokens += int(cost.get("total_tokens") or 0)
        total_transitions += int(environment.get("environment_transitions_total") or 0)
        total_replays += int(environment.get("replay_transitions") or 0)
    src_rows = [
        row["result"]
        for row in completed
        if row["result"].get("method") == METHOD_SRC
    ]
    completed_cost = {
        "model_calls": total_calls,
        "model_tokens": total_tokens,
        "all_physical_browser_transitions": total_transitions,
        "of_which_reset_replay_transitions": total_replays,
    }
    attempted_cost = dict(completed_cost)
    if run_dir is not None:
        attempted_calls = attempted_tokens = 0
        attempted_transitions = attempted_replays = 0
        for row in results:
            cell_dir = run_dir / "cells" / str(row["cell_name"])
            call_path = cell_dir / "model_calls.json"
            if call_path.is_file():
                calls = json.loads(call_path.read_text(encoding="utf-8"))
                attempted_calls += len(calls)
                for call in calls:
                    usage = (call.get("metadata") or {}).get("usage") or {}
                    attempted_tokens += int(usage.get("total_tokens") or 0)
            receipt_path = cell_dir / "environment_receipts_latest.json"
            if receipt_path.is_file():
                receipts = json.loads(receipt_path.read_text(encoding="utf-8"))
                attempted_transitions += int(
                    receipts.get("environment_transitions_total") or 0
                )
                attempted_replays += int(receipts.get("replay_transitions") or 0)
        attempted_cost = {
            "model_calls": attempted_calls,
            "model_tokens": attempted_tokens,
            "all_physical_browser_transitions": attempted_transitions,
            "of_which_reset_replay_transitions": attempted_replays,
        }
    return {
        "cells_requested": len(results),
        "cells_completed": len(completed),
        "cells_failed": len(results) - len(completed),
        "by_condition": by_condition,
        "src_reviewer": {
            "cells": len(src_rows),
            "detection_correct": sum(
                int(bool(row["runner_only_review_audit"]["detection_correct"]))
                for row in src_rows
            ),
            "rollback_index_correct": sum(
                int(bool(row["runner_only_review_audit"]["rollback_index_correct"]))
                for row in src_rows
            ),
        },
        "cost": {
            **attempted_cost,
            "attempted": attempted_cost,
            "completed_cells_only": completed_cost,
        },
    }


def run_cell_dispatch(
    *,
    method: str,
    spec: TaskSpec,
    arm: str,
    mode: str | None,
    case: Mapping[str, Any],
    asset_variant_id: str,
    cell_dir: Path,
    args: argparse.Namespace,
) -> dict[str, Any]:
    model = VisionJSONModel(
        output_dir=cell_dir,
        backend=args.backend,
        model=args.model,
        endpoint=args.endpoint,
        model_path=args.model_path,
        model_size=args.model_size,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=args.seed,
    )
    env = CompactBranchEnvironment(
        case=case,
        arm=arm,
        cell_dir=cell_dir,
        firefox_binary=args.firefox_binary,
        geckodriver=args.geckodriver,
        firefox_library_path=args.firefox_library_path,
        action_wait_ms=args.action_wait_ms,
    )
    scorer = CanonicalSubmissionScorer(
        task_set="smoke17",
        slug=spec.slug,
        layout_id=spec.layout_id,
        asset_variant_id=asset_variant_id,
    )
    try:
        if method == "src":
            return run_src_cell(
                env=env,
                model=model,
                scorer=scorer,
                spec=spec,
                branch_steps=args.src_branch_steps,
            )
        if method == "exact":
            if mode is None:
                raise ValueError("ExACT-inspired cell requires a selection mode")
            return run_exact_cell(
                env=env,
                model=model,
                scorer=scorer,
                spec=spec,
                rollouts=args.exact_rollouts,
                exploration=args.exact_exploration,
                selection_mode=mode,
            )
        if method == "mobile":
            if mode is None:
                raise ValueError("MobileUse-style cell requires a mode")
            return run_mobile_cell(
                env=env,
                model=model,
                scorer=scorer,
                spec=spec,
                mode=mode,
                max_operator_steps=args.mobile_max_steps,
            )
        raise ValueError(f"unknown method {method!r}")
    finally:
        write_json(cell_dir / "environment_receipts_latest.json", env.receipts())
        env.close()


def parse_csv_choices(value: str, allowed: Iterable[str], label: str) -> list[str]:
    choices = [item.strip() for item in value.split(",") if item.strip()]
    unknown = set(choices) - set(allowed)
    if not choices or unknown:
        raise argparse.ArgumentTypeError(
            f"{label} must be a comma-separated subset of {sorted(allowed)}; "
            f"unknown={sorted(unknown)}"
        )
    return choices


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", default="src,exact,mobile")
    parser.add_argument("--tasks", default="pub010,env008,b035")
    parser.add_argument("--arms", default="official,clean")
    parser.add_argument("--mobile-modes", default=",".join(MOBILE_MODES))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=(
            Path(__file__).resolve().parent
            / "runs"
            / "agentic_recovery_baselines"
        ),
    )
    parser.add_argument("--run-id")
    parser.add_argument(
        "--backend", choices=("qwen3_vl_http", "kimik2_http"), default="qwen3_vl_http"
    )
    parser.add_argument("--model", default="Qwen3-VL-8B-Instruct")
    parser.add_argument(
        "--endpoint", default="http://127.0.0.1:8045"
    )
    parser.add_argument(
        "--model-path",
        default="/mnt/data/datasets/open_source_models/Qwen3-VL-8B-Instruct",
    )
    parser.add_argument("--model-size", default="8b")
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--src-branch-steps", type=int, default=3)
    parser.add_argument("--exact-rollouts", type=int, default=12)
    parser.add_argument("--exact-exploration", type=float, default=1.2)
    parser.add_argument(
        "--exact-selection-modes", default="contrast,highest_value"
    )
    parser.add_argument("--mobile-max-steps", type=int, default=6)
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
    parser.add_argument("--action-wait-ms", type=int, default=350)
    args = parser.parse_args(argv)
    args.methods = parse_csv_choices(args.methods, ("src", "exact", "mobile"), "methods")
    args.tasks = parse_csv_choices(args.tasks, TASK_SPECS, "tasks")
    args.arms = parse_csv_choices(args.arms, ("official", "clean"), "arms")
    args.mobile_modes = parse_csv_choices(
        args.mobile_modes, MOBILE_MODES, "mobile modes"
    )
    args.exact_selection_modes = parse_csv_choices(
        args.exact_selection_modes,
        ("contrast", "highest_value"),
        "ExACT selection modes",
    )
    if args.src_branch_steps < 1 or args.exact_rollouts < 1 or args.mobile_max_steps < 1:
        parser.error("step and rollout limits must be positive")
    for path_name in ("firefox_binary", "geckodriver"):
        if not Path(getattr(args, path_name)).is_file():
            parser.error(f"{path_name} does not exist: {getattr(args, path_name)}")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.environ["KIMIK2_ENABLE_THINKING"] = "false"
    os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    run_id = args.run_id or (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_")
        + uuid.uuid4().hex[:8]
    )
    run_dir = (args.output_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    service_health = (
        qwen_service_health(args.endpoint)
        if args.backend == "qwen3_vl_http"
        else None
    )
    if service_health is not None:
        if str(service_health.get("model_path")) != str(args.model_path):
            raise RuntimeError(
                "Qwen service model path does not match requested checkpoint"
            )
        if str(service_health.get("model_size")) != str(args.model_size):
            raise RuntimeError(
                "Qwen service model size does not match requested checkpoint size"
            )
    case_cache = {slug: load_case(TASK_SPECS[slug]) for slug in args.tasks}
    requested_cells: list[tuple[str, str, str, str | None]] = []
    for method in args.methods:
        if method == "mobile":
            modes: Sequence[str | None] = args.mobile_modes
        elif method == "exact":
            modes = args.exact_selection_modes
        else:
            modes = (None,)
        for slug in args.tasks:
            for arm in args.arms:
                for mode in modes:
                    requested_cells.append((method, slug, arm, mode))

    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "benchmark": (
            "benchmark_v2_open paired official140/clean140 release-candidate cases; "
            "not the legacy benchmark_v2 directory"
        ),
        "task_set_pointer": "smoke17",
        "tasks": args.tasks,
        "arms": args.arms,
        "methods": args.methods,
        "mobile_modes": args.mobile_modes if "mobile" in args.methods else [],
        "exact_selection_modes": (
            args.exact_selection_modes if "exact" in args.methods else []
        ),
        "requested_cells": [
            {"method": method, "slug": slug, "arm": arm, "mode": mode}
            for method, slug, arm, mode in requested_cells
        ],
        "model": {
            "provider": args.backend,
            "checkpoint_name": args.model,
            "checkpoint_path": args.model_path,
            "checkpoint_size": args.model_size,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "seed": args.seed,
            "max_output_tokens": args.max_tokens,
            "thinking": False if args.backend == "kimik2_http" else "not applicable",
            "matched_backbone_across_roles": True,
            "teacher_is_not_a_stronger_model": True,
            "server_health": service_health,
            "vision_input_packaging": "native ordered images; no contact sheet",
            "operator_prompt": "neutral visible-chart-evidence prompt v2",
        },
        "browser": {
            "backend": "Selenium Firefox",
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "coordinate_only_task_actions": True,
            "fresh_app_server_browser_per_restore": True,
        },
        "protocol_scope": {
            "track": "evaluator-owned takeover mechanism probe",
            "natural_error_rate": False,
            "deep_horizon_claim": False,
            "scorer_visible_to_controllers": False,
            "scorer_invocation": "only after fresh final browser commit",
            "asset_variants": "matched diagnostic variants; non-reportable as canonical benchmark scores",
        },
        "implementation_receipts": {
            "runner_source_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "llm_client_source_sha256": sha256_bytes(
                Path(llm_client.__file__).read_bytes()
            ),
            "qwen_server_source_sha256": sha256_bytes(
                (REPO_ROOT / "web_agent_benchmark/evaluation/qwen3_vl_server.py").read_bytes()
            ),
        },
        "method_identity": {
            "src": "SRC-style teacher-assisted short-branch collector probe",
            "exact": (
                "ExACT-inspired enumerative MCTS + single-call VLM value debate "
                "+ optional post-hoc contrast probe"
            ),
            "mobile": "MobileUse-style nested reflector controller",
        },
        "limits": {
            "src_branch_steps": args.src_branch_steps,
            "exact_rollouts": args.exact_rollouts,
            "exact_exploration": args.exact_exploration,
            "exact_candidate_limit": EXACT_CANDIDATE_LIMIT,
            "exact_max_contrast_images": EXACT_CANDIDATE_LIMIT * 2,
            "mobile_max_operator_steps": args.mobile_max_steps,
        },
    }
    write_json(run_dir / "run_manifest.json", manifest)
    results: list[dict[str, Any]] = []
    for index, (method, slug, arm, mode) in enumerate(requested_cells, start=1):
        cell_name = method_cell_name(method, slug, arm, mode)
        cell_dir = run_dir / "cells" / cell_name
        cell_dir.mkdir(parents=True, exist_ok=False)
        case, asset_variant_id = case_cache[slug]
        cell_meta = {
            "cell_index": index,
            "cell_count": len(requested_cells),
            "cell_name": cell_name,
            "method": method,
            "slug": slug,
            "arm": arm,
            "mode": mode,
            "layout_id": TASK_SPECS[slug].layout_id,
            "asset_variant_id": asset_variant_id,
        }
        print(
            f"[{index}/{len(requested_cells)}] {cell_name}",
            flush=True,
        )
        try:
            result = run_cell_dispatch(
                method=method,
                spec=TASK_SPECS[slug],
                arm=arm,
                mode=mode,
                case=case,
                asset_variant_id=asset_variant_id,
                cell_dir=cell_dir,
                args=args,
            )
            row = {**cell_meta, "status": "completed", "result": result}
        except Exception as exc:
            row = {
                **cell_meta,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        results.append(row)
        write_json(cell_dir / "summary.json", row)
        write_json(run_dir / "results.json", results)
        write_json(run_dir / "aggregate.json", summarize_results(results, run_dir))
        print(f"  -> {row['status']}", flush=True)
    aggregate = summarize_results(results, run_dir)
    aggregate["run_id"] = run_id
    aggregate["finished_at"] = utc_now()
    write_json(run_dir / "aggregate.json", aggregate)
    print(json.dumps(aggregate, ensure_ascii=False, indent=2), flush=True)
    return 0 if aggregate["cells_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
