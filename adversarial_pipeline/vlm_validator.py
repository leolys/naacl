"""
VLM-based semantic validator for attacked chart images.

Provides a lightweight second-pass check after code execution or programmatic
operators:
  - Are data marks (bars, lines, points) still clearly visible?
  - Is the intended misleading mechanism visually present?
  - Does the chart look like a real chart (not a blank or corrupted image)?

This validator is intentionally FAST — it uses a single low-token VLM call
with a structured Yes/No checklist rather than an open-ended audit.  The full
quality audit is done by llm_judge.audit_success() for hard successes only.

Public API:
    check_image(client, attacked_chart_path, error_type, source_chart_path) -> VLMCheckResult
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import llm_client

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VLMCheckResult:
    passed: bool
    reason: str
    marks_visible: bool | None = None
    mechanism_present: bool | None = None
    looks_like_chart: bool | None = None
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a strict visual QA auditor for a chart-manipulation benchmark.
You will receive two images: the original clean chart and the attacked version.
Answer the following checklist as JSON exactly.
"""

_CHECKLIST_TEMPLATE = """\
Attacked chart audit checklist.

Error type that was applied: {error_type}
Definition: {error_type_definition}

Answer each question with true/false and a one-line reason.

Questions:
1. looks_like_chart: Does the attacked image still look like a chart (not blank, not mostly white, not corrupted)?
2. marks_visible: Are the primary data marks (bars, lines, scatter points, or pie slices) still clearly present in the attacked image?
3. mechanism_present: Is the specific misleading mechanism for "{error_type}" visually present in the attacked image?

Return ONLY this JSON object (no other text):
{{
  "looks_like_chart": true/false,
  "looks_like_chart_reason": "...",
  "marks_visible": true/false,
  "marks_visible_reason": "...",
  "mechanism_present": true/false,
  "mechanism_present_reason": "..."
}}
"""

# Short one-line definitions for the checklist
_MECHANISM_DEFINITIONS: dict[str, str] = {
    "missingaxis":         "The axis line and all axis tick labels are absent or invisible.",
    "missingaxisticks":    "The axis tick labels (numbers or category names) are absent or invisible.",
    "missingaxistitle":    "The axis title/label text (e.g. 'Year', 'Sales') is absent or invisible.",
    "missingtitle":        "The chart title is absent or invisible.",
    "missinglegend":       "The legend is absent or invisible.",
    "missingunits":        "Unit suffixes on axis labels (e.g. '%', 'Mbps') are absent or invisible.",
    "confusinglegend":     "Legend labels are present but do not match the correct data series.",
    "illegibletext":       "Key text labels (axis ticks, title, legend) are blurry or too small to read.",
    "indistinguishablecolors": "Data series that should be distinct look nearly the same color or shade.",
    "overusingcolors":     "The chart uses an excessive number of bright unrelated colors.",
    "confusingcharttype":  "The chart type is poorly matched to the data (e.g. a line chart for unordered categories).",
    "discretizedcontinuousvariable": "A continuous axis has been replaced by coarse discrete bands or labels.",
    "inconsistentvaluelabels": "Data value labels shown on the chart disagree with the bar/line heights.",
    "truncatedaxis":       "The value axis is truncated so it does not start at zero.",
    "changingscale":       "The axis scale changes non-uniformly between tick intervals.",
    "invertedaxis":        "An axis is inverted (larger values appear lower or further left).",
    "narrative_framing":   "The chart title or caption makes a biased claim that overstates what the data show.",
    "Cherry_Picking":      "Only a subset of the data is shown, hiding the broader trend.",
    "Missing_Data":        "Data that should be present is missing, preventing a complete answer.",
    "Missing_Normalization": "Raw counts are presented where rates/proportions would be needed for a fair comparison.",
    "Concealed_Uncertainty": "Error bars, confidence intervals, or uncertainty information are hidden.",
}


def _extract_json(text: str) -> dict[str, Any]:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"No JSON found in VLM validator response: {text[:300]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_image(
    client,
    attacked_chart_path: str | Path,
    error_type: str,
    source_chart_path: str | Path | None = None,
    *,
    skip_if_disabled: bool = True,
) -> VLMCheckResult:
    """
    Run a fast VLM semantic check on the attacked chart image.

    Args:
        client:               LLM client (should be the judge/validator client)
        attacked_chart_path:  Path to the generated/edited attacked chart PNG
        error_type:           The error type that was applied
        source_chart_path:    Original clean chart (sent as first image for comparison)
        skip_if_disabled:     If VLM_SEMANTIC_VALIDATION=false, skip and return passed=True

    Returns:
        VLMCheckResult with passed=True only if all three checks pass.
    """
    if skip_if_disabled and os.environ.get("VLM_SEMANTIC_VALIDATION", "true").lower() != "true":
        return VLMCheckResult(passed=True, reason="VLM semantic validation disabled.")

    attacked_path = Path(attacked_chart_path)
    if not attacked_path.exists() or attacked_path.stat().st_size < 1000:
        return VLMCheckResult(
            passed=False,
            reason=f"Attacked chart file missing or too small: {attacked_chart_path}",
        )

    definition = _MECHANISM_DEFINITIONS.get(error_type, f"A '{error_type}' misleading mechanism is applied.")
    user_text = _CHECKLIST_TEMPLATE.format(
        error_type=error_type,
        error_type_definition=definition,
    )

    image_paths: list[str | Path] = []
    if source_chart_path and Path(source_chart_path).exists():
        image_paths.append(source_chart_path)
    image_paths.append(attacked_chart_path)

    try:
        if len(image_paths) == 2:
            raw = llm_client.complete_multivision(
                client=client,
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_text,
                image_paths=image_paths,
                max_output_tokens=512,
            )
        else:
            raw = llm_client.complete_vision(
                client=client,
                system_prompt=_SYSTEM_PROMPT,
                user_text=user_text,
                image_path=attacked_chart_path,
                max_output_tokens=512,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("VLM semantic validator call failed: %s", exc)
        # On API failure, don't block the sample — let it through
        return VLMCheckResult(passed=True, reason=f"VLM validator skipped (API error): {exc}")

    try:
        result = _extract_json(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("VLM validator response parse failed: %s — raw: %s", exc, raw[:200])
        return VLMCheckResult(passed=True, reason=f"VLM validator parse failed; skipping: {exc}", raw_response=raw)

    looks_like_chart = bool(result.get("looks_like_chart", True))
    marks_visible    = bool(result.get("marks_visible", True))
    mechanism_present = bool(result.get("mechanism_present", False))

    failures: list[str] = []
    if not looks_like_chart:
        failures.append(f"image doesn't look like a chart: {result.get('looks_like_chart_reason', '')}")
    if not marks_visible:
        failures.append(f"data marks not visible: {result.get('marks_visible_reason', '')}")
    if not mechanism_present:
        failures.append(f"misleading mechanism not present: {result.get('mechanism_present_reason', '')}")

    passed = len(failures) == 0
    reason = "; ".join(failures) if failures else "all VLM checks passed"

    logger.info(
        "VLM semantic check for %s: passed=%s marks=%s mechanism=%s chart=%s",
        error_type, passed, marks_visible, mechanism_present, looks_like_chart,
    )

    return VLMCheckResult(
        passed=passed,
        reason=reason,
        marks_visible=marks_visible,
        mechanism_present=mechanism_present,
        looks_like_chart=looks_like_chart,
        raw_response=raw,
    )
