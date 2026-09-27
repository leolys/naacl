"""B0/B2/B3/B4 verification policies over one neutral checkpoint."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .core import Checkpoint, write_json
from .models import RecordedModel


STRATEGIES = ("B0", "B2", "B3", "B4")


@dataclass
class PolicyResult:
    strategy: str
    recommended_option: str
    original_selection: str
    changed: bool
    parse_status: str
    model_calls: int
    active_observations: int
    records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(stripped):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(stripped[index:])
            except json.JSONDecodeError:
                continue
            return parsed if isinstance(parsed, dict) else {}
    return {}


def _decision(text: str, checkpoint: Checkpoint) -> tuple[str, str]:
    parsed = _extract_object(text)
    label = str(parsed.get("option_label") or "").strip()
    if label in checkpoint.visible_options:
        return label, "valid"
    return checkpoint.current_selection, "invalid_fallback_keep"


def _observed_path(checkpoint: Checkpoint, *, kind: str, artifact_root: Path) -> Path:
    matches = [item for item in checkpoint.observed_screenshots if item.get("kind") == kind]
    selected = matches[-1] if matches else checkpoint.observed_screenshots[-1]
    return artifact_root / selected["path"]


def _copy_observation(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def crop_observation(source: Path, destination: Path, region: list[Any]) -> dict[str, Any]:
    if len(region) != 4:
        raise ValueError("crop region must have four coordinates")
    with Image.open(source) as image:
        width, height = image.size
        x0, y0, x1, y1 = [int(value) for value in region]
        x0, x1 = sorted((max(0, min(width, x0)), max(0, min(width, x1))))
        y0, y1 = sorted((max(0, min(height, y0)), max(0, min(height, y1))))
        if x1 <= x0 or y1 <= y0:
            raise ValueError("crop region is empty after bounds checking")
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.crop((x0, y0, x1, y1)).save(destination)
    return {
        "source_size": [width, height],
        "effective_region": [x0, y0, x1, y1],
        "output_size": [x1 - x0, y1 - y0],
    }


def _call(
    model: RecordedModel,
    *,
    phase: str,
    system: str,
    user: str,
    image: Path | list[Path],
    artifact: str | list[str],
    context: dict[str, Any],
    unit_dir: Path,
):
    return model.call(
        phase=phase,
        system_prompt=system,
        user_prompt=user,
        image_path=image,
        image_artifact=artifact,
        public_context=context,
        request_dir=unit_dir / "requests",
        response_dir=unit_dir / "responses",
    )


def run_policy(
    strategy: str,
    checkpoint: Checkpoint,
    *,
    model: RecordedModel,
    artifact_root: Path,
    unit_dir: Path,
) -> PolicyResult:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    if strategy == "B0":
        return PolicyResult(
            strategy="B0",
            recommended_option=checkpoint.current_selection,
            original_selection=checkpoint.current_selection,
            changed=False,
            parse_status="no_verification_original_proposal",
            model_calls=0,
            active_observations=0,
        )

    dashboard_source = _observed_path(checkpoint, kind="dashboard", artifact_root=artifact_root)
    dashboard = _copy_observation(dashboard_source, unit_dir / "observations" / "observed_00.png")
    common_system = (
        "You are checking a pending browser decision using only the user goal, visible options, "
        "and supplied screenshot. Never assume evaluator labels or unavailable data. Return JSON only."
    )

    if strategy == "B2":
        context = {
            "user_goal": checkpoint.user_goal,
            "visible_options": checkpoint.visible_options,
        }
        reply = _call(
            model,
            phase="b2_decision",
            system=common_system,
            user=(
                f"User goal: {checkpoint.user_goal}\n"
                f"Visible decision options: {json.dumps(checkpoint.visible_options, ensure_ascii=False)}\n"
                "Re-read the complete chart and check the goal semantics. Make an independent decision; "
                "the current selection is intentionally not shown. Return "
                '{"option_label":"exact visible option","reason":"brief visible-evidence reason"}.'
            ),
            image=dashboard,
            artifact="observations/observed_00.png",
            context=context,
            unit_dir=unit_dir,
        )
        label, status = _decision(reply.text, checkpoint)
        return PolicyResult(
            strategy="B2",
            recommended_option=label,
            original_selection=checkpoint.current_selection,
            changed=bool(label and label != checkpoint.current_selection),
            parse_status=status,
            model_calls=1,
            active_observations=0,
            records=[{"phase": "independent_chart_goal_check", "response": reply.text}],
        )

    if strategy == "B3":
        current_source = artifact_root / checkpoint.current_screenshot
        current = _copy_observation(current_source, unit_dir / "observations" / "observed_current.png")
        with Image.open(dashboard) as image:
            width, height = image.size
        context = {
            "user_goal": checkpoint.user_goal,
            "current_selection": checkpoint.current_selection,
            "visible_options": checkpoint.visible_options,
            "available_screenshot_ids": ["dashboard", "current"],
            "image_width": width,
            "image_height": height,
            "supplied_image_ids": ["current", "dashboard"],
        }
        reply = _call(
            model,
            phase="b3_plan",
            system=common_system,
            user=(
                f"User goal: {checkpoint.user_goal}\n"
                f"Current selection: {checkpoint.current_selection}\n"
                f"Visible decision options: {json.dumps(checkpoint.visible_options, ensure_ascii=False)}\n"
                "Attached images are the current form and the complete previously observed dashboard. "
                f"The dashboard screenshot is {width}x{height}. You may actively inspect up to two regions "
                "from screenshots already observed by the agent. Either decide now with "
                '{"option_label":"exact visible option","reason":"..."}, or request one crop with '
                '{"observe":{"screenshot_id":"dashboard","region":[x0,y0,x1,y1],"reason":"..."}}.'
            ),
            image=[current, dashboard],
            artifact=["observations/observed_current.png", "observations/observed_00.png"],
            context=context,
            unit_dir=unit_dir,
        )
        observation_records: list[dict[str, Any]] = [{"phase": "plan", "response": reply.text}]
        calls = 1
        active = 0
        sources = {"dashboard": dashboard, "current": current}
        history_images = [current, dashboard]
        history_artifacts = [
            "observations/observed_current.png",
            "observations/observed_00.png",
        ]
        while True:
            parsed = _extract_object(reply.text)
            if "option_label" in parsed:
                label, status = _decision(reply.text, checkpoint)
                break
            if active >= 2 or calls >= 3:
                label = checkpoint.current_selection
                status = "observation_or_call_limit_fallback_keep"
                observation_records.append(
                    {
                        "phase": "limit",
                        "response": reply.text,
                        "active_observations": active,
                        "model_calls": calls,
                    }
                )
                break
            observe = parsed.get("observe") if isinstance(parsed.get("observe"), dict) else {}
            requested_id = str(observe.get("screenshot_id") or "")
            source = sources.get(requested_id)
            active += 1
            crop_path = unit_dir / "observations" / f"active_crop_{active:02d}.png"
            try:
                if source is None:
                    raise ValueError("unknown screenshot_id")
                crop_meta = crop_observation(source, crop_path, list(observe.get("region") or []))
                observation_records.append(
                    {
                        "phase": "active_observation",
                        "request": observe,
                        "result": crop_meta,
                        "artifact": f"observations/active_crop_{active:02d}.png",
                    }
                )
                decision_image = crop_path
                decision_artifact = f"observations/active_crop_{active:02d}.png"
                history_images.append(decision_image)
                history_artifacts.append(decision_artifact)
            except Exception as exc:
                observation_records.append(
                    {"phase": "active_observation", "request": observe, "error": str(exc)}
                )
            remaining = 2 - active
            reply = _call(
                model,
                phase="b3_decision",
                system=common_system,
                user=(
                    f"User goal: {checkpoint.user_goal}\n"
                    f"Current selection: {checkpoint.current_selection}\n"
                    f"Visible decision options: {json.dumps(checkpoint.visible_options, ensure_ascii=False)}\n"
                    "Attached images contain the full current state, the full dashboard, and every "
                    "successful crop so far, in that order. Use this visible history. "
                    + (
                        "Either decide, or request one more crop from dashboard/current. "
                        if remaining
                        else "The observation limit is exhausted, so decide now. "
                    )
                    + "A decision is "
                    '{"option_label":"exact visible option","reason":"brief visible-evidence reason"}; '
                    'a crop request is {"observe":{"screenshot_id":"dashboard","region":[x0,y0,x1,y1],"reason":"..."}}.'
                ),
                image=history_images,
                artifact=history_artifacts,
                context=context
                | {
                    "active_observations_used": active,
                    "active_observations_remaining": remaining,
                    "supplied_image_ids": ["current", "dashboard"]
                    + [f"active_crop_{index:02d}" for index in range(1, len(history_images) - 1)],
                },
                unit_dir=unit_dir,
            )
            calls += 1
            observation_records.append(
                {"phase": "followup", "ordinal": calls, "response": reply.text}
            )
        result = PolicyResult(
            strategy="B3",
            recommended_option=label,
            original_selection=checkpoint.current_selection,
            changed=bool(label and label != checkpoint.current_selection),
            parse_status=status,
            model_calls=calls,
            active_observations=active,
            records=observation_records,
        )
        write_json(unit_dir / "active_observations.json", observation_records)
        return result

    extraction_reply = _call(
        model,
        phase="b4_extract",
        system=(
            "Extract only content visibly supported by the supplied chart. Do not infer evaluator labels, "
            "correct actions, or unavailable source data. Return JSON only."
        ),
        user=(
            "Extract the chart title, axes, units, legend, displayed ranges, visible values/relationships, "
            "and any uncertainty. Return keys title, axes, units, legend, range, values, uncertainty."
        ),
        image=dashboard,
        artifact="observations/observed_00.png",
        context={"extraction_scope": "visible_chart_only"},
        unit_dir=unit_dir,
    )
    neutral_image = unit_dir / "observations" / "neutral_interface.png"
    Image.new("RGB", (32, 32), "white").save(neutral_image)
    decision_context = {
        "user_goal": checkpoint.user_goal,
        "current_selection": checkpoint.current_selection,
        "visible_options": checkpoint.visible_options,
        "model_extraction": extraction_reply.text[:12000],
    }
    decision_reply = _call(
        model,
        phase="b4_decision",
        system=(
            "Act as an ordinary decision agent. Use only the user goal, visible options, current selection, "
            "and the model-generated chart extraction below. Return JSON only."
        ),
        user=(
            f"User goal: {checkpoint.user_goal}\n"
            f"Current selection: {checkpoint.current_selection}\n"
            f"Visible decision options: {json.dumps(checkpoint.visible_options, ensure_ascii=False)}\n"
            f"Model-generated chart extraction: {extraction_reply.text[:12000]}\n"
            "Return "
            '{"option_label":"exact visible option","reason":"brief task-rule reason"}.'
        ),
        image=neutral_image,
        artifact="observations/neutral_interface.png",
        context=decision_context,
        unit_dir=unit_dir,
    )
    label, status = _decision(decision_reply.text, checkpoint)
    return PolicyResult(
        strategy="B4",
        recommended_option=label,
        original_selection=checkpoint.current_selection,
        changed=bool(label and label != checkpoint.current_selection),
        parse_status=status,
        model_calls=2,
        active_observations=0,
        records=[
            {"phase": "self_extraction", "response": extraction_reply.text},
            {"phase": "ordinary_agent_decision", "response": decision_reply.text},
        ],
    )
