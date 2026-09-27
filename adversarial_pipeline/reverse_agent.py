"""
Reverse Agent — inspects the Forward Agent's reasoning trace and generates a
misleading chart variant (as executable matplotlib code) targeting the weakest
reasoning stage.

Public API:
    generate_attack(client, forward_trace, question, options, gold_answer,
                    output_chart_path, round_num, definitions_text,
                    failure_explanation=None, prev_attack_plan=None) -> (dict, str)
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import llm_client
import validator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_TACTIC_LIBRARY_PATH = Path(__file__).parent / "reverse_tactic_library.json"
logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "reverse_system.txt").read_text()


def _load_retry_addon() -> str:
    return (_PROMPTS_DIR / "reverse_retry_addon.txt").read_text()


def _load_tactic_library() -> dict[str, Any]:
    return json.loads(_TACTIC_LIBRARY_PATH.read_text(encoding="utf-8"))


def _options_text(options: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in options.items())


def _relevant_tactics(
    *,
    attack_preferences: dict | None,
    task_mode: str | None,
    error_profile: dict | None,
) -> list[dict[str, Any]]:
    library = _load_tactic_library().get("tactics", [])
    error_type = (
        (attack_preferences or {}).get("target_error_type")
        or (error_profile or {}).get("error_type")
    )
    chart_type = (attack_preferences or {}).get("chart_type")
    mode = (task_mode or "strict_answerable").strip().lower()

    relevant: list[dict[str, Any]] = []
    for tactic in library:
        if error_type and tactic.get("error_type") != error_type:
            continue
        task_modes = tactic.get("task_modes") or []
        if task_modes and mode not in task_modes:
            continue
        chart_types = tactic.get("chart_types") or []
        if chart_type and chart_types and chart_type not in chart_types:
            continue
        relevant.append(tactic)
    return relevant


def _data_fidelity_policy(error_profile: dict[str, Any] | None) -> str:
    return str((error_profile or {}).get("data_fidelity_policy", "")).strip().lower()


def _requires_exact_mark_preservation(error_profile: dict[str, Any] | None) -> bool:
    return _data_fidelity_policy(error_profile) == "exact_marks_required"


def _normalize_attack_plan_fields(attack_plan: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(attack_plan)
    target_wrong = normalized.get("target_wrong_option") or normalized.get("expected_wrong_option")
    if target_wrong:
        normalized["target_wrong_option"] = target_wrong
        normalized.setdefault("expected_wrong_option", target_wrong)
    return normalized


def _validate_attack_plan_fields(
    *,
    attack_plan: dict[str, Any],
    options: dict[str, str],
    gold_answer: str,
    attack_preferences: dict | None,
    task_mode: str | None,
    error_profile: dict | None,
    prev_attack_plan: dict | None,
) -> None:
    error_type = attack_plan.get("target_error_type")
    target_wrong = attack_plan.get("target_wrong_option")
    if target_wrong not in options:
        raise ValueError("Reverse Agent must return target_wrong_option as one of A/B/C/D.")
    if target_wrong == gold_answer:
        raise ValueError("Reverse Agent target_wrong_option must not equal the gold answer.")

    option_analysis = attack_plan.get("option_confusability_analysis")
    if not isinstance(option_analysis, dict):
        raise ValueError("Reverse Agent must return option_confusability_analysis as a JSON object.")
    if not option_analysis.get("target_wrong_option_reason"):
        raise ValueError("Reverse Agent must explain why the chosen wrong option is visually tempting.")
    if not option_analysis.get("gold_option_resistance"):
        raise ValueError("Reverse Agent must explain why the gold option should become less direct.")

    allowed_mark_changes = list((error_profile or {}).get("allowed_mark_changes") or [])
    if allowed_mark_changes:
        mark_change_type = attack_plan.get("mark_change_type")
        if not mark_change_type:
            raise ValueError("Reverse Agent must return mark_change_type from the profile's allowed_mark_changes.")
        if mark_change_type not in allowed_mark_changes:
            raise ValueError(
                f"Reverse Agent mark_change_type '{mark_change_type}' is not allowed for '{error_type}'."
            )

    allowed_scope_changes = list((error_profile or {}).get("allowed_scope_changes") or [])
    if allowed_scope_changes:
        scope_change = attack_plan.get("scope_change")
        if not scope_change:
            raise ValueError("Reverse Agent must return scope_change from the profile's allowed_scope_changes.")
        if scope_change not in allowed_scope_changes:
            raise ValueError(
                f"Reverse Agent scope_change '{scope_change}' is not allowed for '{error_type}'."
            )

    protected_channels = list((error_profile or {}).get("protected_channels") or [])
    if protected_channels:
        respected = attack_plan.get("protected_channels_respected")
        if not isinstance(respected, list) or not respected:
            raise ValueError("Reverse Agent must return protected_channels_respected as a non-empty list.")
        fidelity_explanation = str(attack_plan.get("data_fidelity_explanation", "")).strip()
        if not fidelity_explanation:
            raise ValueError("Reverse Agent must explain how profile-protected channels remain faithful.")

    if error_type in {"Cherry_Picking", "Missing_Data"}:
        tactic_family = attack_plan.get("tactic_family")
        if not tactic_family:
            raise ValueError(f"Reverse Agent must return tactic_family for {error_type}.")
        if not attack_plan.get("corrective_evidence_to_break"):
            raise ValueError(f"Reverse Agent must identify corrective_evidence_to_break for {error_type}.")
        if not attack_plan.get("how_this_revision_breaks_it"):
            raise ValueError(f"Reverse Agent must explain how_this_revision_breaks_it for {error_type}.")

        relevant_tactics = _relevant_tactics(
            attack_preferences=attack_preferences,
            task_mode=task_mode,
            error_profile=error_profile,
        )
        allowed_families = {item.get("tactic_family") for item in relevant_tactics}
        if allowed_families and tactic_family not in allowed_families:
            raise ValueError(
                f"Reverse Agent tactic_family '{tactic_family}' is not in the tactic library for {error_type}."
            )

        prev = prev_attack_plan or {}
        if prev:
            prev_wrong = prev.get("target_wrong_option") or prev.get("expected_wrong_option")
            same_family = prev.get("tactic_family") == tactic_family
            same_wrong = prev_wrong == target_wrong
            same_stage = prev.get("target_stage") == attack_plan.get("target_stage")
            if same_family and same_wrong and same_stage:
                raise ValueError(
                    "Reverse Agent repeated the same tactic_family, target_wrong_option, and target_stage on retry."
                )


def _profile_beam_width(error_profile: dict[str, Any] | None) -> int:
    try:
        return max(1, int((error_profile or {}).get("reverse_beam_width_hint", 1)))
    except Exception:
        return 1


def _combined_failure_text(failure_explanation: dict[str, Any] | None) -> str:
    if not failure_explanation:
        return ""
    parts = [
        str(failure_explanation.get("why_attack_failed", "")),
        str(failure_explanation.get("detected_misleading_cue", "")),
        str(failure_explanation.get("decisive_corrective_evidence", "")),
        str(failure_explanation.get("suggested_more_dangerous_attack", "")),
    ]
    return " ".join(part for part in parts if part).lower()


def _seed_penalty_from_failure(
    *,
    tactic_family: str,
    target_wrong_option: str,
    failure_explanation: dict[str, Any] | None,
    prev_attack_plan: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    penalty = 0.0
    reasons: list[str] = []
    failure_text = _combined_failure_text(failure_explanation)
    prev = prev_attack_plan or {}

    if prev.get("tactic_family") == tactic_family:
        penalty -= 1.5
        reasons.append("same_tactic_penalty")
    prev_wrong = prev.get("target_wrong_option") or prev.get("expected_wrong_option")
    if prev_wrong == target_wrong_option:
        penalty -= 0.5
        reasons.append("same_wrong_option_penalty")

    if any(key in failure_text for key in ["x-axis labels", "country labels", "mapping", "no visible country labels"]):
        if tactic_family == "omit_reference_mapping":
            penalty -= 3.0
            reasons.append("mapping_failure_penalty")

    if any(key in failure_text for key in ["japan is absent", "japan was absent", "not listed", "country list", "not included among"]):
        if tactic_family == "omit_disambiguating_category":
            penalty -= 2.5
            reasons.append("absence_too_obvious_penalty")

    if any(key in failure_text for key in ["only three months", "limited x-axis coverage", "subset too obvious", "only march", "only apr"]):
        if tactic_family == "selective_time_window":
            penalty -= 2.5
            reasons.append("obvious_window_penalty")
        if tactic_family == "partial_year_frame":
            penalty += 1.5
            reasons.append("partial_frame_bonus")

    return penalty, reasons


def _build_candidate_seeds(
    *,
    options: dict[str, str],
    gold_answer: str,
    attack_preferences: dict | None,
    task_mode: str | None,
    error_profile: dict | None,
    prev_attack_plan: dict | None,
    failure_explanation: dict | None,
) -> list[dict[str, Any]]:
    tactics = _relevant_tactics(
        attack_preferences=attack_preferences,
        task_mode=task_mode,
        error_profile=error_profile,
    )
    wrong_options = [label for label in options.keys() if label != gold_answer]
    if not tactics or not wrong_options:
        return []

    seeds: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    # First pass: diversify tactics first.
    for idx, tactic in enumerate(tactics):
        wrong_option = wrong_options[idx % len(wrong_options)]
        combo = (tactic["tactic_family"], wrong_option)
        if combo in seen:
            continue
        seen.add(combo)
        seeds.append(
            {
                "tactic_family": tactic["tactic_family"],
                "target_wrong_option": wrong_option,
                "seed_base_score": 10.0 - idx,
                "seed_reason": [f"diverse_tactic={tactic['tactic_family']}"],
            }
        )

    # Second pass: fill remaining tactic-option combinations.
    for tactic in tactics:
        for wrong_option in wrong_options:
            combo = (tactic["tactic_family"], wrong_option)
            if combo in seen:
                continue
            seen.add(combo)
            seeds.append(
                {
                    "tactic_family": tactic["tactic_family"],
                    "target_wrong_option": wrong_option,
                    "seed_base_score": 5.0,
                    "seed_reason": [f"combo={tactic['tactic_family']}:{wrong_option}"],
                }
            )

    for seed in seeds:
        penalty, reasons = _seed_penalty_from_failure(
            tactic_family=seed["tactic_family"],
            target_wrong_option=seed["target_wrong_option"],
            failure_explanation=failure_explanation,
            prev_attack_plan=prev_attack_plan,
        )
        seed["seed_base_score"] += penalty
        seed["seed_reason"].extend(reasons)

    seeds.sort(
        key=lambda item: (
            -item["seed_base_score"],
            item["tactic_family"],
            item["target_wrong_option"],
        )
    )
    return seeds


def extract_json_block(text: str) -> dict:
    """
    Extract the first JSON object from a ```json ... ``` fenced block.
    Falls back to the first bare { ... } object.
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Try generic ``` fence
    m = re.search(r"```\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare JSON object
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        # Find the last closing brace that might belong to the JSON
        # Use a simple bracket balancing approach
        start = text.find("{")
        if start != -1:
            depth = 0
            for i, ch in enumerate(text[start:], start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
    raise ValueError(
        f"No JSON object found in Reverse Agent response.\n"
        f"Response excerpt: {text[:400]}"
    )


def extract_python_block(text: str) -> str:
    """
    Extract the Python code from a ```python ... ``` fenced block.
    Falls back to any ``` ... ``` block that is not JSON.
    """
    # Prefer explicit ```python
    m = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # Find all ``` blocks and return the one that looks most like Python
    blocks = re.findall(r"```(?:\w*)?\s*(.*?)\s*```", text, re.DOTALL)
    for block in blocks:
        stripped = block.strip()
        # Skip if it looks like JSON
        if stripped.startswith("{"):
            continue
        if "import" in stripped or "plt." in stripped or "matplotlib" in stripped:
            return stripped

    # Last resort: return anything after the JSON block
    # Split on the last ``` that closed the JSON block
    parts = re.split(r"```json.*?```", text, flags=re.DOTALL)
    if len(parts) > 1:
        remainder = parts[-1]
        m = re.search(r"```(?:python)?\s*(.*?)\s*```", remainder, re.DOTALL)
        if m:
            return m.group(1).strip()

    raise ValueError(
        f"No Python code block found in Reverse Agent response.\n"
        f"Response excerpt: {text[:400]}"
    )


def execute_chart_code(
    code: str,
    output_path: str,
    timeout: int = 90,
    reference_chart_path: str | None = None,
) -> None:
    """
    Execute matplotlib code in an isolated subprocess.
    Injects `OUTPUT_PATH` and, when available, `REFERENCE_CHART_PATH` /
    `SOURCE_CHART_PATH` so the code can save to the right file and edit the
    current reference chart directly.

    Raises RuntimeError if the subprocess exits with a non-zero return code.
    """
    injected = f"OUTPUT_PATH = {repr(output_path)}\n"
    if reference_chart_path is not None:
        injected += (
            f"REFERENCE_CHART_PATH = {repr(reference_chart_path)}\n"
            "SOURCE_CHART_PATH = REFERENCE_CHART_PATH\n"
        )
    injected += "\n" + code

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(injected)
        tmp_path = fh.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Chart generation code exited with code {result.returncode}.\n"
                f"stderr:\n{result.stderr}\n"
                f"stdout:\n{result.stdout}"
            )
    finally:
        os.unlink(tmp_path)


def _build_attack_prompt(
    forward_trace: dict,
    question: str,
    options: dict,
    gold_answer: str,
    definitions_text: str,
    round_num: int,
    failure_explanation: dict | None,
    prev_attack_plan: dict | None,
    attack_preferences: dict | None,
    task_mode: str | None,
    error_profile: dict | None,
    reference_chart_path: str | None = None,
    forced_tactic_family: str | None = None,
    forced_target_wrong_option: str | None = None,
    seed_reason: list[str] | None = None,
    source_data_table: str | None = None,
    source_annotation: dict | None = None,
) -> str:
    """Construct the full user message for the Reverse Agent."""
    exact_marks_required = _requires_exact_mark_preservation(error_profile)
    tactic_guidance = _relevant_tactics(
        attack_preferences=attack_preferences,
        task_mode=task_mode,
        error_profile=error_profile,
    )

    lines = [
        "## Forward Agent Reasoning Trace",
        "",
        f"Question: {question}",
        "",
        f"Options:\n{_options_text(options)}",
        "",
        f"Gold (correct) answer: {gold_answer}",
        "",
        "Forward Agent's staged reasoning:",
        "```json",
        json.dumps(forward_trace, indent=2),
        "```",
        "",
        "## VLAT Error-Type Taxonomy",
        "",
        definitions_text,
        "",
    ]

    # Source data table and annotation — ground truth for the chart
    if source_data_table:
        lines += [
            "## Source Data Table (Ground Truth)",
            "",
            "The following CSV data is the actual data behind the chart.",
            "Use this data to define values inline in your matplotlib code",
            "instead of approximating from the Forward Agent's visual readout.",
            "This ensures your generated chart accurately represents the source data.",
            "",
            "```csv",
            source_data_table,
            "```",
            "",
        ]

    if source_annotation:
        # Extract key annotation info (title, axis labels) without the full bboxes
        annotation_summary = {}
        general = source_annotation.get("general_figure_info", {})
        if general.get("title", {}).get("text"):
            annotation_summary["title"] = general["title"]["text"]
        x_axis = general.get("x_axis", {})
        y_axis = general.get("y_axis", {})
        if x_axis.get("label", {}).get("text"):
            annotation_summary["x_axis_label"] = x_axis["label"]["text"]
        if y_axis.get("label", {}).get("text"):
            annotation_summary["y_axis_label"] = y_axis["label"]["text"]
        x_labels = x_axis.get("major_labels", {}).get("values")
        if x_labels:
            annotation_summary["x_tick_labels"] = x_labels
        y_labels = y_axis.get("major_labels", {}).get("values")
        if y_labels:
            annotation_summary["y_tick_labels"] = y_labels

        if annotation_summary:
            lines += [
                "## Chart Annotation Metadata",
                "",
                "Structural metadata extracted from the original chart annotation:",
                "",
                "```json",
                json.dumps(annotation_summary, indent=2, ensure_ascii=False),
                "```",
                "",
            ]

    if attack_preferences:
        lines += [
            "## Scheduler Guidance",
            "",
            "The scheduler has provided target-category guidance for this sample.",
            "When target_error_type is provided, treat it as a hard target unless the sample structure makes it impossible.",
            "Do not mention this guidance in the final chart; only use it to choose a better attack.",
            "",
            "```json",
            json.dumps(attack_preferences, indent=2),
            "```",
            "",
        ]

    if task_mode or error_profile:
        lines += [
            "## Task-Mode and Error-Profile Constraints",
            "",
            f"Requested task_mode: {task_mode or 'strict_answerable'}",
            "",
            "```json",
            json.dumps(error_profile or {}, indent=2),
            "```",
            "",
            "Your generated attack must match the requested error type profile and task mode.",
            "",
        ]

    if reference_chart_path and exact_marks_required:
        lines += [
            "## Reference Chart Image",
            "",
            "A reference chart image is attached after this text prompt.",
            "Because the current profile requires exact mark preservation, your code must edit that attached chart image directly.",
            "At execution time, the same file will be available as SOURCE_CHART_PATH / REFERENCE_CHART_PATH.",
            "Do not redraw the core points, bars, lines, or slices from scratch.",
            "",
        ]

    if tactic_guidance:
        lines += [
            "## Tactic Library Guidance",
            "",
            "Use one tactic_family from the library below. Prefer a tactic that makes one specific wrong option visually tempting while weakening the corrective evidence that previously saved the model.",
            "",
            "```json",
            json.dumps(tactic_guidance, indent=2),
            "```",
            "",
        ]

    if forced_tactic_family or forced_target_wrong_option:
        lines += [
            "## Beam Search Seed Constraints",
            "",
            "For this candidate, treat the following as hard constraints.",
            "If you cannot satisfy them cleanly, fail this candidate rather than silently drifting.",
            f"- forced tactic_family: {forced_tactic_family or 'N/A'}",
            f"- forced target_wrong_option: {forced_target_wrong_option or 'N/A'}",
        ]
        if seed_reason:
            lines += [f"- seed rationale: {'; '.join(seed_reason)}"]
        lines += ["",]

    # Retry instructions (rounds 2 and 3)
    if round_num > 1 and failure_explanation is not None:
        retry_template = _load_retry_addon()
        retry_block = retry_template.format(
            round_num=round_num,
            failure_explanation=json.dumps(failure_explanation, indent=2),
            prev_attack_plan=json.dumps(prev_attack_plan, indent=2)
            if prev_attack_plan
            else "N/A",
        )
        lines.append(retry_block)
        lines.append("")

    lines += [
        "## Your Task",
        "",
        "1. Study the Forward Agent's trace above and identify the most vulnerable reasoning stage.",
        "2. Decide which wrong answer option is most realistically temptable for this sample.",
        "3. Choose one dominant VLAT error type and one tactic_family that target that option.",
        "4. Explicitly identify the corrective evidence that saved the Forward Agent last time and explain how you will break it.",
        "5. Output your attack plan as a ```json ... ``` block.",
        "6. Then output self-contained Python matplotlib code as a ```python ... ``` block.",
        "",
        "The Python code MUST:",
        "- Import matplotlib.pyplot as plt and any needed standard library.",
        "- Save the chart with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')",
        "- NOT call plt.show().",
        "- NOT define OUTPUT_PATH (it will be injected automatically).",
        "- Add 2-4 inline comments marking where the misleading mechanism is applied.",
        "",
        "Reminder: the chart must remain answerable and must not be factually broken.",
        "Do not leave the gold answer as the visually most obvious option if the requested tactic can plausibly make a distractor more tempting.",
    ]
    if exact_marks_required:
        lines[lines.index("- Save the chart with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')"):lines.index("- Save the chart with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')")] = [
            "- Load the reference chart image from SOURCE_CHART_PATH / REFERENCE_CHART_PATH and edit it directly.",
            "- Preserve the original data marks/geometry exactly.",
            "- Do NOT redraw points, bars, lines, or pie slices from scratch.",
            "- Do NOT synthesize a new dataset or rely on Stage 1 text to recreate coordinates.",
            "- Apply the misleading mechanism only to allowed reference elements such as ticks, titles, legends, labels, or units.",
        ]
    else:
        data_source_instructions = []
        if source_data_table:
            data_source_instructions = [
                "- Define all data values inline using the Source Data Table provided above.",
                "- The Source Data Table is ground truth — use it instead of the Forward Agent's visual readout for exact values.",
                "- Apply the misleading mechanism you described.",
            ]
        else:
            data_source_instructions = [
                "- Define all data values inline (no external files).",
                "- Use the data values reported in the Forward Agent's Stage 1 Visual Readout.",
                "- Apply the misleading mechanism you described.",
            ]
        lines[lines.index("- Save the chart with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')"):lines.index("- Save the chart with: plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches='tight')")] = data_source_instructions

    return "\n".join(lines)


def _generate_candidate(
    *,
    client,
    system_prompt: str,
    forward_trace: dict,
    question: str,
    options: dict,
    gold_answer: str,
    definitions_text: str,
    round_num: int,
    failure_explanation: dict | None,
    prev_attack_plan: dict | None,
    attack_preferences: dict | None,
    task_mode: str | None,
    error_profile: dict | None,
    reference_chart_path: str | None,
    forced_tactic_family: str | None,
    forced_target_wrong_option: str | None,
    seed_reason: list[str] | None,
    source_data_table: str | None = None,
    source_annotation: dict | None = None,
) -> dict[str, Any]:
    user_prompt = _build_attack_prompt(
        forward_trace=forward_trace,
        question=question,
        options=options,
        gold_answer=gold_answer,
        definitions_text=definitions_text,
        round_num=round_num,
        failure_explanation=failure_explanation,
        prev_attack_plan=prev_attack_plan,
        attack_preferences=attack_preferences,
        task_mode=task_mode,
        error_profile=error_profile,
        reference_chart_path=reference_chart_path,
        forced_tactic_family=forced_tactic_family,
        forced_target_wrong_option=forced_target_wrong_option,
        seed_reason=seed_reason,
        source_data_table=source_data_table,
        source_annotation=source_annotation,
    )
    if reference_chart_path and _requires_exact_mark_preservation(error_profile):
        raw = llm_client.complete_vision(
            client=client,
            system_prompt=system_prompt,
            user_text=user_prompt,
            image_path=reference_chart_path,
            max_output_tokens=4096,
        )
    else:
        raw = llm_client.complete_text(
            client=client,
            system_prompt=system_prompt,
            user_text=user_prompt,
            max_output_tokens=4096,
        )

    attack_plan = _normalize_attack_plan_fields(extract_json_block(raw))
    matplotlib_code = extract_python_block(raw)
    hard_target = (attack_preferences or {}).get("target_error_type")
    if hard_target and attack_plan.get("target_error_type") != hard_target:
        raise ValueError(
            f"Reverse Agent returned error type '{attack_plan.get('target_error_type')}' "
            f"but scheduler requested '{hard_target}'."
        )
    requested_task_mode = (task_mode or "strict_answerable").strip().lower()
    returned_task_mode = str(attack_plan.get("task_mode", requested_task_mode)).strip().lower()
    if returned_task_mode != requested_task_mode:
        raise ValueError(
            f"Reverse Agent returned task_mode '{returned_task_mode}' "
            f"but scheduler requested '{requested_task_mode}'."
        )
    if forced_tactic_family and attack_plan.get("tactic_family") != forced_tactic_family:
        raise ValueError(
            f"Reverse Agent returned tactic_family '{attack_plan.get('tactic_family')}' "
            f"but beam search required '{forced_tactic_family}'."
        )
    returned_wrong = attack_plan.get("target_wrong_option") or attack_plan.get("expected_wrong_option")
    if forced_target_wrong_option and returned_wrong != forced_target_wrong_option:
        raise ValueError(
            f"Reverse Agent returned target_wrong_option '{returned_wrong}' "
            f"but beam search required '{forced_target_wrong_option}'."
        )
    attack_plan.setdefault("task_mode", requested_task_mode)
    _validate_attack_plan_fields(
        attack_plan=attack_plan,
        options=options,
        gold_answer=gold_answer,
        attack_preferences=attack_preferences,
        task_mode=task_mode,
        error_profile=error_profile,
        prev_attack_plan=prev_attack_plan,
    )

    self_check = attack_plan.get("self_check", {})
    if not self_check.get("still_answerable", True):
        raise ValueError(
            "Reverse Agent self-check: still_answerable == false. "
            "Rejecting this attack as it would make the chart unanswerable."
        )

    validation = validator.validate_attack_plan(
        attack_plan,
        matplotlib_code,
        question=question,
        options=options,
        gold_answer=gold_answer,
        task_mode=task_mode,
        error_profile=error_profile,
        prev_attack_plan=prev_attack_plan,
        source_chart_path=reference_chart_path,
        source_chart_type=(attack_preferences or {}).get("chart_type"),
    )
    if not validation.is_valid:
        raise ValueError(f"Reverse candidate rejected by validator: {validation.reason}")

    model_beam_score = attack_plan.get("beam_score", 0)
    try:
        model_beam_score = float(model_beam_score)
    except Exception:
        model_beam_score = 0.0

    return {
        "attack_plan": attack_plan,
        "matplotlib_code": matplotlib_code,
        "model_beam_score": model_beam_score,
    }


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def generate_attack(
    client,
    forward_trace: dict,
    question: str,
    options: dict,
    gold_answer: str,
    output_chart_path: str,
    round_num: int,
    definitions_text: str,
    failure_explanation: dict | None = None,
    prev_attack_plan: dict | None = None,
    attack_preferences: dict | None = None,
    task_mode: str | None = None,
    error_profile: dict | None = None,
    reference_chart_path: str | None = None,
    source_data_table: str | None = None,
    source_annotation: dict | None = None,
) -> tuple[dict, str]:
    """
    Have the Reverse Agent plan and generate a misleading chart.

    Args:
        client:              OpenAI client instance
        forward_trace:       ForwardTrace dict from the Forward Agent
        question:            benchmark question string
        options:             {"A": "...", "B": "...", ...}
        gold_answer:         correct answer key, e.g. "B"
        output_chart_path:   where to save the generated PNG
        reference_chart_path: current chart image to preserve/edit for this round
        round_num:           current round number (1, 2, or 3)
        definitions_text:    contents of error_type_generation_definitions.md
        failure_explanation: FailureExplanation dict from previous round (if any)
        prev_attack_plan:    AttackPlan dict from previous round (if any)
        source_data_table:   CSV content of the source data table (if available)
        source_annotation:   chart annotation dict (if available)

    Returns:
        (attack_plan, matplotlib_code) tuple
        Side-effect: generates and saves the PNG at output_chart_path
    """
    system_prompt = _load_system_prompt()
    beam_width = _profile_beam_width(error_profile)
    candidate_seeds = _build_candidate_seeds(
        options=options,
        gold_answer=gold_answer,
        attack_preferences=attack_preferences,
        task_mode=task_mode,
        error_profile=error_profile,
        prev_attack_plan=prev_attack_plan,
        failure_explanation=failure_explanation,
    )

    if beam_width <= 1 or not candidate_seeds:
        candidate_seeds = [
            {
                "tactic_family": None,
                "target_wrong_option": None,
                "seed_base_score": 0.0,
                "seed_reason": ["single_candidate_mode"],
            }
        ]
    else:
        candidate_seeds = candidate_seeds[:beam_width]

    logger.info(
        "Reverse beam search: trying %d candidate(s) for %s",
        len(candidate_seeds),
        (attack_preferences or {}).get("target_error_type") or (error_profile or {}).get("error_type"),
    )

    valid_candidates: list[dict[str, Any]] = []
    candidate_errors: list[str] = []
    for idx, seed in enumerate(candidate_seeds, start=1):
        try:
            candidate = _generate_candidate(
                client=client,
                system_prompt=system_prompt,
                forward_trace=forward_trace,
                question=question,
                options=options,
                gold_answer=gold_answer,
                definitions_text=definitions_text,
                round_num=round_num,
                failure_explanation=failure_explanation,
                prev_attack_plan=prev_attack_plan,
                attack_preferences=attack_preferences,
                task_mode=task_mode,
                error_profile=error_profile,
                reference_chart_path=reference_chart_path,
                forced_tactic_family=seed.get("tactic_family"),
                forced_target_wrong_option=seed.get("target_wrong_option"),
                seed_reason=seed.get("seed_reason"),
                source_data_table=source_data_table,
                source_annotation=source_annotation,
            )
            total_score = float(seed.get("seed_base_score", 0.0)) + float(candidate.get("model_beam_score", 0.0))
            candidate["total_score"] = total_score
            candidate["seed_rank"] = idx
            candidate["seed"] = seed
            valid_candidates.append(candidate)
        except Exception as exc:
            candidate_errors.append(
                f"seed#{idx} tactic={seed.get('tactic_family')} wrong={seed.get('target_wrong_option')}: {exc}"
            )

    if not valid_candidates:
        raise ValueError(
            "Reverse beam search failed to produce any valid candidate. "
            + " | ".join(candidate_errors[:6])
        )

    valid_candidates.sort(key=lambda item: (-item["total_score"], item["seed_rank"]))

    execution_errors: list[str] = []
    for candidate in valid_candidates:
        try:
            execute_chart_code(
                candidate["matplotlib_code"],
                output_chart_path,
                reference_chart_path=reference_chart_path,
            )
            chosen_plan = dict(candidate["attack_plan"])
            chosen_plan["beam_search_metadata"] = {
                "beam_width": len(candidate_seeds),
                "candidate_count": len(valid_candidates),
                "chosen_seed_rank": candidate["seed_rank"],
                "chosen_total_score": candidate["total_score"],
                "considered_candidates": [
                    {
                        "seed_rank": item["seed_rank"],
                        "tactic_family": (item["attack_plan"] or {}).get("tactic_family"),
                        "target_wrong_option": (item["attack_plan"] or {}).get("target_wrong_option"),
                        "total_score": item["total_score"],
                    }
                    for item in valid_candidates
                ],
            }
            return chosen_plan, candidate["matplotlib_code"]
        except Exception as exc:
            execution_errors.append(
                f"seed#{candidate['seed_rank']} tactic={(candidate['attack_plan'] or {}).get('tactic_family')}: {exc}"
            )

    raise RuntimeError(
        "Reverse beam search produced valid plans but all candidate chart executions failed. "
        + " | ".join(execution_errors[:6])
    )
