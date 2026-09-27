"""
Mode-aware attack validator for the adversarial benchmark-construction pipeline.

This validator no longer treats the whole pipeline as a single
`strict_answerable` benchmark. Instead it checks each proposed attack against:
- the requested task mode
- the selected error-type profile
- lightweight static code heuristics

The goal is still conservative validation, but the policy is now category-aware
instead of globally blocking broad families such as Missing_Data or
Cherry_Picking.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from task_modes import (
    ABSTENTION_AWARE,
    SCOPE_REASONING,
    STRICT_ANSWERABLE,
    looks_like_exact_lookup,
    normalize_task_mode,
    options_have_abstention,
)


DEPRECATED_ERROR_TYPES = {
    "plottingerror",
}

STRICT_REFERENCE_SYSTEM_RISKS = {
    "missingaxis",
    "missingaxisticks",
    "missingaxistitle",
    "missingunits",
}

STRUCTURE_RELAXED_POLICIES = {
    "subset_allowed",
    "omission_allowed",
}

EXACT_MARKS_REQUIRED_POLICIES = {
    "exact_marks_required",
}

CODE_HEURISTIC_PATTERNS = [
    (
        "value_override_after_copy",
        "explicit value override after copying a true data array",
        re.compile(
            r"(true_[a-zA-Z_][a-zA-Z0-9_]*\s*=.*?\n.*?copy\(\).*?\n.*?\[[^\]]+\]\s*=)",
            re.DOTALL,
        ),
    ),
    (
        "render_data_split",
        "render/display data separated from true data",
        re.compile(r"\b(display_|plot_)(prices|values|speeds|data)\b", re.IGNORECASE),
    ),
    (
        "plottingerror_comment",
        "comment explicitly referring to plotting error",
        re.compile(r"plottingerror|rendered .* instead of .*true value", re.IGNORECASE),
    ),
    (
        "explicit_omission",
        "explicit selective omission of marks/series/categories",
        re.compile(
            r"only the .* (bars|lines|series|categories) are drawn|visible_values\s*=|if\s+\w+\s+in\s+visible_values",
            re.IGNORECASE,
        ),
    ),
    (
        "omission_comment",
        "comment acknowledging omitted chart elements",
        re.compile(r"omit(?:ted)?|only .*visible|subset of (bars|series|categories)", re.IGNORECASE),
    ),
]

EXPLICIT_DISCLOSURE_STRING_PATTERN = re.compile(
    r"""["'](?:data unavailable|not available|n/?a|no data|cannot be determined(?: exactly)?|cannot determine|missing data)["']""",
    re.IGNORECASE,
)
REFERENCE_IMAGE_TOKEN_PATTERN = re.compile(r"\b(?:SOURCE_CHART_PATH|REFERENCE_CHART_PATH)\b")
MARK_REGENERATION_PATTERN = re.compile(
    r"\b(?:plt|ax)\.(?:scatter|plot|bar|barh|hist|pie|fill_between|stackplot)\s*\(",
    re.IGNORECASE,
)
INLINE_ARRAY_PATTERN = re.compile(r"\b(?:np|numpy)\.array\s*\(\s*\[", re.IGNORECASE)
INLINE_NUMERIC_LIST_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:np\.array\(\s*)?\[\s*[-+]?\d",
    re.IGNORECASE | re.MULTILINE,
)
STAGE_READOUT_RECONSTRUCTION_PATTERN = re.compile(
    r"(stage\s*1|visual readout|forward agent'?s visual readout|provided visual readout|prompt'?s visual readout)",
    re.IGNORECASE,
)
MANUAL_ENTITY_BAND_ASSIGNMENT_PATTERN = re.compile(
    r'["\'](?:low|medium|high|very high|very low|elite|fast|slow)["\']\s*:\s*\{\s*["\'](?:cities|items|labels)["\']\s*:',
    re.IGNORECASE,
)
SCATTER_CALL_PATTERN = re.compile(r"\b(?:plt|ax)\.scatter\s*\(", re.IGNORECASE)
BUBBLE_SIZE_CHANNEL_PATTERN = re.compile(r"^\s*(?:ridership|size|sizes)\s*=", re.IGNORECASE | re.MULTILINE)
TWIN_AXIS_PATTERN = re.compile(r"\b(?:ax\d*\s*=\s*ax\.twin[xy]\(\)|twinx\(\)|twiny\(\))", re.IGNORECASE)
AXIS_LIMIT_CALL_PATTERN = re.compile(
    r"\b(?:ax|plt)\.(?:set_xlim|set_ylim|xlim|ylim)\s*\(",
    re.IGNORECASE,
)
EXPLICIT_TICK_CONFIG_PATTERN = re.compile(
    r"\b(?:ax\.set_xticks|ax\.set_yticks|plt\.xticks|plt\.yticks)\s*\(",
    re.IGNORECASE,
)
EXPLICIT_TICKLABEL_CONFIG_PATTERN = re.compile(
    r"\b(?:ax\.set_xticklabels|ax\.set_yticklabels)\s*\(",
    re.IGNORECASE,
)
TRANSFORM_FUNCTION_PATTERN = re.compile(
    r"def\s+\w*(?:transform|scale)\w*\s*\(|(?:piecewise|non-linear|nonlinear|changing scale|transform)\b",
    re.IGNORECASE,
)
SUBSETTING_EVIDENCE_PATTERN = re.compile(
    r"\b(?:visible_idx|visible_months|visible_values|subset|selected_|shown_|months_full|prices_full|legend_indices|display_labels|_full\b)\b",
    re.IGNORECASE,
)
BLANK_LABEL_PATTERN = re.compile(r'display_labels\s*=\s*\[[^\]]*["\']\s*["\']', re.IGNORECASE | re.DOTALL)
NORMALIZATION_SIGNAL_PATTERN = re.compile(
    r"\b(?:normalized|normalised|per[_ ]capita|per[_ ]person|ratio|share|percent(?:age)? of total|residual|z[- ]?score|standardi[sz]ed|monthly_pattern|cross-year mean)\b",
    re.IGNORECASE,
)
ANNOTATION_OR_CALLOUT_PATTERN = re.compile(r"\b(?:annotate|text|suptitle)\s*\(", re.IGNORECASE)
UNCERTAINTY_SIGNAL_PATTERN = re.compile(
    r"\b(?:errorbar|fill_between|confidence|uncertainty|stderr|std|variance|band)\b",
    re.IGNORECASE,
)
PIE_CALL_PATTERN = re.compile(r"\b(?:plt|ax)\.pie\s*\(", re.IGNORECASE)
BAR_CALL_PATTERN = re.compile(r"\b(?:plt|ax)\.(?:bar|barh)\s*\(", re.IGNORECASE)
LINE_CALL_PATTERN = re.compile(r"\b(?:plt|ax)\.plot\s*\(", re.IGNORECASE)
STACK_OR_FILL_PATTERN = re.compile(r"\b(?:plt|ax)\.(?:stackplot|fill_between)\s*\(", re.IGNORECASE)
THREE_D_PATTERN = re.compile(
    r"\b(?:projection\s*=\s*['\"]3d['\"]|Axes3D|mpl_toolkits\.mplot3d|bar3d|Poly3DCollection)\b",
    re.IGNORECASE,
)
PIE_DEPTH_PATTERN = re.compile(r"\bshadow\s*=\s*True\b|\bexplode\s*=", re.IGNORECASE)
AREA_PATCH_PATTERN = re.compile(
    r"\b(?:Circle|Ellipse|Wedge|RegularPolygon|PathPatch|AnnotationBbox|OffsetImage)\s*\(",
    re.IGNORECASE,
)
AREA_SIZE_CHANNEL_PATTERN = re.compile(
    r"\b(?:s|sizes|markersize|ms)\s*=",
    re.IGNORECASE,
)
ICONIC_MARK_PATTERN = re.compile(
    r"\b(?:OffsetImage|AnnotationBbox|imshow|Image\.open|icon|pictogram|marker\s*=)\b",
    re.IGNORECASE,
)
ALPHA_VALUE_PATTERN = re.compile(r"\balpha\s*=\s*([01](?:\.\d+)?)", re.IGNORECASE)
LEGEND_CALL_PATTERN = re.compile(r"\b(?:ax|plt)\.legend\s*\(|\blegend\s*\(", re.IGNORECASE)
LEGEND_CONFUSION_PATTERN = re.compile(
    r"\bbbox_to_anchor\b|\bhandles\s*=|\blegend_handles\b|\blegend_labels\b|\bLine2D\s*\(|\bmarkerscale\s*=|\bhandlelength\s*=|\bcolumnspacing\s*=|\blabelspacing\s*=|\bhandler_map\s*=",
    re.IGNORECASE,
)
NUMERIC_TEXT_LITERAL_PATTERN = re.compile(r"['\"][^'\"]*\d+(?:\.\d+)?[^'\"]*['\"]")
SUMMARY_LABEL_PATTERN = re.compile(r"\b(?:average|avg|mean|median|total|sum)\b", re.IGNORECASE)
POLAR_LAYOUT_PATTERN = re.compile(r"\b(?:polar\s*=\s*True|projection\s*=\s*['\"]polar['\"])\b", re.IGNORECASE)
RADAR_SIGNAL_PATTERN = re.compile(r"\btheta_offset\b|\btheta_direction\b|\bset_theta_offset\b|\bset_theta_direction\b", re.IGNORECASE)
CURVE_DISTORTION_PATTERN = re.compile(
    r"\b(?:sin|cos|bezier|spline|interp1d|interpolate|curve)\b",
    re.IGNORECASE,
)
INVERT_AXIS_CALL_PATTERN = re.compile(r"\b(?:ax|plt)\.invert_[xy]axis\s*\(", re.IGNORECASE)
FIGSIZE_PATTERN = re.compile(
    r"figsize\s*=\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*\)",
    re.IGNORECASE,
)
X_LIMIT_VALUE_PATTERN = re.compile(
    r"\b(?:set_xlim|xlim)\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*\)",
    re.IGNORECASE,
)
Y_LIMIT_VALUE_PATTERN = re.compile(
    r"\b(?:set_ylim|ylim)\s*\(\s*([-+]?\d*\.?\d+)\s*,\s*([-+]?\d*\.?\d+)\s*\)",
    re.IGNORECASE,
)
TEXT_OR_REFERENCE_ONLY_MARK_CHANGE_TYPES = {
    "reference_system_removal_only",
    "title_caption_text_only",
    "reference_text_only",
    "in_chart_label_text_only",
    "legend_binding_presentation_only",
    "color_discriminability_only",
    "color_mapping_only",
    "text_readability_only",
    "chart_level_framing_only",
}
SCOPE_RELAXING_MARK_CHANGE_TYPES = {
    "subset_selection_only",
    "context_omission_only",
    "normalization_context_omission_only",
}

_TACTIC_LIBRARY_PATH = Path(__file__).parent / "reverse_tactic_library.json"


@dataclass
class ValidationResult:
    is_valid: bool
    reason: str


def _load_tactic_library() -> dict[str, Any]:
    return json.loads(_TACTIC_LIBRARY_PATH.read_text(encoding="utf-8"))


def _merged_profile(attack_plan: dict[str, Any], error_profile: dict[str, Any] | None) -> dict[str, Any]:
    profile = dict(error_profile or {})
    if "error_type" not in profile and attack_plan.get("target_error_type"):
        profile["error_type"] = attack_plan.get("target_error_type")
    return profile


def _profile_error_type(profile: dict[str, Any], attack_plan: dict[str, Any]) -> str | None:
    return profile.get("error_type") or attack_plan.get("target_error_type")


def _is_exact_lookup(question: str | None, options: dict[str, str] | None) -> bool:
    return looks_like_exact_lookup(question, options)


def _skip_heuristic_for_structure(heuristic_code: str, structure_policy: str) -> bool:
    if structure_policy not in STRUCTURE_RELAXED_POLICIES:
        return False
    return heuristic_code in {
        "render_data_split",
        "explicit_omission",
        "omission_comment",
    }


def _validate_task_mode_and_profile(
    *,
    attack_plan: dict[str, Any],
    task_mode: str,
    error_profile: dict[str, Any],
    question: str | None,
    options: dict[str, str] | None,
) -> ValidationResult | None:
    error_type = attack_plan.get("target_error_type")
    profile_error_type = _profile_error_type(error_profile, attack_plan)
    if error_type != profile_error_type:
        return ValidationResult(
            False,
            f"Attack/profile mismatch: attack_plan targets '{error_type}' but profile targets '{profile_error_type}'.",
        )

    if error_type in DEPRECATED_ERROR_TYPES:
        return ValidationResult(
            False,
            f"Invalid attack: error type '{error_type}' is deprecated in the active taxonomy.",
        )

    allowed_task_modes = error_profile.get("allowed_task_modes") or []
    if allowed_task_modes and task_mode not in allowed_task_modes:
        return ValidationResult(
            False,
            f"Invalid attack: task mode '{task_mode}' is not allowed for error type '{error_type}'.",
        )

    exact_lookup = _is_exact_lookup(question, options)
    exact_lookup_policy = error_profile.get("exact_lookup_policy", "allow")
    qa_refactor_policy = error_profile.get("qa_refactor_policy", "none")
    structure_policy = error_profile.get("structure_policy", "preserve")

    if task_mode == ABSTENTION_AWARE:
        if not options_have_abstention(options):
            return ValidationResult(
                False,
                "Invalid abstention-aware attack: options do not contain an explicit abstention choice.",
            )
        if not error_profile.get("supports_abstention_option", False):
            return ValidationResult(
                False,
                f"Invalid attack: error type '{error_type}' is not configured for abstention-aware evaluation.",
            )

    if task_mode == STRICT_ANSWERABLE and exact_lookup:
        if error_type in STRICT_REFERENCE_SYSTEM_RISKS:
            return ValidationResult(
                False,
                f"Invalid strict attack for exact-lookup question: '{error_type}' removes too much numeric reference context.",
            )
        if exact_lookup_policy in {"disallow", "requires_refactor", "abstention_preferred"}:
            return ValidationResult(
                False,
                f"Invalid strict attack: profile for '{error_type}' requires QA refactor or abstention for exact-lookup questions.",
            )
        if structure_policy in STRUCTURE_RELAXED_POLICIES:
            return ValidationResult(
                False,
                f"Invalid strict exact-lookup attack: structure policy '{structure_policy}' would undercut direct value recovery.",
            )

    if task_mode == SCOPE_REASONING and exact_lookup and qa_refactor_policy == "required":
        return ValidationResult(
            False,
            f"Invalid scope-reasoning attack: question still looks like exact lookup even though '{error_type}' requires QA refactor.",
        )

    if task_mode == ABSTENTION_AWARE and exact_lookup and qa_refactor_policy == "required" and not options_have_abstention(options):
        return ValidationResult(
            False,
            f"Invalid abstention-aware attack: '{error_type}' requires refactored abstention options for exact-lookup questions.",
        )

    return None


def _validate_self_check(
    attack_plan: dict[str, Any],
    *,
    task_mode: str,
) -> ValidationResult | None:
    self_check = attack_plan.get("self_check") or {}

    if not self_check.get("dominant_mechanism_only", False):
        return ValidationResult(False, "Reverse Agent self-check failed: dominant_mechanism_only is false.")
    if not self_check.get("still_answerable", False):
        return ValidationResult(
            False,
            f"Reverse Agent self-check failed: still_answerable is false under task mode '{task_mode}'.",
        )
    if not self_check.get("faithful_to_metadata", False):
        return ValidationResult(False, "Reverse Agent self-check failed: faithful_to_metadata is false.")
    if not self_check.get("misleading_not_factually_broken", False):
        return ValidationResult(
            False,
            "Reverse Agent self-check failed: misleading_not_factually_broken is false.",
        )
    return None


def _validate_anti_triviality(
    *,
    matplotlib_code: str,
    task_mode: str,
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    if task_mode != ABSTENTION_AWARE:
        return None
    if error_profile.get("text_policy", "neutral_only") != "neutral_only":
        return None
    if EXPLICIT_DISCLOSURE_STRING_PATTERN.search(matplotlib_code or ""):
        return ValidationResult(
            False,
            "Invalid abstention-aware attack: chart code contains overly explicit disclosure text about missingness or indeterminacy.",
        )
    return None


def _validate_option_aware_fields(
    *,
    attack_plan: dict[str, Any],
    options: dict[str, str] | None,
    gold_answer: str | None,
) -> ValidationResult | None:
    target_wrong = attack_plan.get("target_wrong_option") or attack_plan.get("expected_wrong_option")
    if not target_wrong:
        return ValidationResult(False, "Invalid attack: target_wrong_option is missing.")
    if options and target_wrong not in options:
        return ValidationResult(False, "Invalid attack: target_wrong_option must be one of the current options.")
    if gold_answer and target_wrong == gold_answer:
        return ValidationResult(False, "Invalid attack: target_wrong_option must differ from the gold answer.")

    option_analysis = attack_plan.get("option_confusability_analysis")
    if not isinstance(option_analysis, dict):
        return ValidationResult(False, "Invalid attack: option_confusability_analysis is missing or malformed.")
    if not option_analysis.get("target_wrong_option_reason"):
        return ValidationResult(False, "Invalid attack: missing target_wrong_option_reason.")
    if not option_analysis.get("gold_option_resistance"):
        return ValidationResult(False, "Invalid attack: missing gold_option_resistance explanation.")
    return None


def _validate_data_fidelity_policy(
    *,
    matplotlib_code: str,
    error_profile: dict[str, Any],
    source_chart_path: str | None,
) -> ValidationResult | None:
    policy = str(error_profile.get("data_fidelity_policy", "")).strip().lower()
    if policy not in EXACT_MARKS_REQUIRED_POLICIES:
        return None
    if not source_chart_path:
        return ValidationResult(
            False,
            "Invalid exact-mark-preservation attack: source/reference chart path is missing.",
        )
    if not REFERENCE_IMAGE_TOKEN_PATTERN.search(matplotlib_code or ""):
        return ValidationResult(
            False,
            "Invalid exact-mark-preservation attack: code must load SOURCE_CHART_PATH/REFERENCE_CHART_PATH and edit the reference chart directly.",
        )
    if MARK_REGENERATION_PATTERN.search(matplotlib_code or ""):
        return ValidationResult(
            False,
            "Invalid exact-mark-preservation attack: code redraws core marks from scratch instead of editing the reference chart.",
        )
    if INLINE_ARRAY_PATTERN.search(matplotlib_code or ""):
        return ValidationResult(
            False,
            "Invalid exact-mark-preservation attack: code defines new numeric data arrays, which suggests regenerated chart geometry.",
        )
    return None


def _listify_profile_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _count_numeric_array_assignments(matplotlib_code: str) -> int:
    if not matplotlib_code:
        return 0
    return len(INLINE_NUMERIC_LIST_ASSIGNMENT_PATTERN.findall(matplotlib_code))


def _count_pattern(matplotlib_code: str, pattern: re.Pattern[str]) -> int:
    if not matplotlib_code:
        return 0
    return len(pattern.findall(matplotlib_code))


def _extract_alpha_values(matplotlib_code: str) -> list[float]:
    values: list[float] = []
    for raw in ALPHA_VALUE_PATTERN.findall(matplotlib_code or ""):
        try:
            values.append(float(raw))
        except Exception:
            continue
    return values


def _extract_figsize(matplotlib_code: str) -> tuple[float, float] | None:
    match = FIGSIZE_PATTERN.search(matplotlib_code or "")
    if not match:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except Exception:
        return None


def _extract_axis_limits(matplotlib_code: str) -> dict[str, list[tuple[float, float]]]:
    limits: dict[str, list[tuple[float, float]]] = {"x": [], "y": []}
    for lo, hi in X_LIMIT_VALUE_PATTERN.findall(matplotlib_code or ""):
        try:
            limits["x"].append((float(lo), float(hi)))
        except Exception:
            continue
    for lo, hi in Y_LIMIT_VALUE_PATTERN.findall(matplotlib_code or ""):
        try:
            limits["y"].append((float(lo), float(hi)))
        except Exception:
            continue
    return limits


def _numeric_constant(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _numeric_constant(node.operand)
        if inner is None:
            return None
        return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _numeric_sequence_from_expr(node: ast.AST) -> list[float] | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[float] = []
        for elt in node.elts:
            num = _numeric_constant(elt)
            if num is None:
                return None
            values.append(num)
        return values
    if isinstance(node, ast.Call) and node.args:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name == "array":
            return _numeric_sequence_from_expr(node.args[0])
    return None


def _extract_numeric_series(matplotlib_code: str) -> dict[str, list[float]]:
    if not matplotlib_code:
        return {}
    try:
        tree = ast.parse(matplotlib_code)
    except Exception:
        return {}
    series: dict[str, list[float]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        seq = _numeric_sequence_from_expr(node.value)
        if not seq or len(seq) < 2:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                series[target.id] = seq
    return series


def _is_axis_position_series(name: str) -> bool:
    lowered = (name or "").lower()
    return any(
        token in lowered
        for token in (
            "x",
            "month",
            "months",
            "year",
            "years",
            "idx",
            "index",
            "indices",
            "angle",
            "angles",
            "theta",
            "position",
            "positions",
        )
    )


def _has_extended_axis_padding(matplotlib_code: str) -> bool:
    series = _extract_numeric_series(matplotlib_code)
    limits = _extract_axis_limits(matplotlib_code)
    candidates = [vals for name, vals in series.items() if len(vals) >= 3 and not _is_axis_position_series(name)]
    if not candidates:
        candidates = [vals for vals in series.values() if len(vals) >= 3]
    for vals in candidates:
        data_min = min(vals)
        data_max = max(vals)
        data_span = data_max - data_min
        if data_span <= 0:
            continue
        for lo, hi in limits.get("y", []) + limits.get("x", []):
            if hi <= lo:
                continue
            axis_span = hi - lo
            if lo <= data_min and hi >= data_max and axis_span >= data_span * 2.5:
                padding_lo = data_min - lo
                padding_hi = hi - data_max
                if (
                    padding_lo >= 0.5 * data_span
                    or padding_hi >= 0.5 * data_span
                    or (padding_lo + padding_hi) >= 1.0 * data_span
                ):
                    return True
    return False


def _has_reversed_axis(matplotlib_code: str) -> bool:
    if INVERT_AXIS_CALL_PATTERN.search(matplotlib_code or ""):
        return True
    limits = _extract_axis_limits(matplotlib_code)
    return any(lo > hi for lo, hi in limits.get("x", []) + limits.get("y", []))


def _non_position_series_ranges(matplotlib_code: str) -> list[tuple[str, float]]:
    ranges: list[tuple[str, float]] = []
    for name, vals in _extract_numeric_series(matplotlib_code).items():
        if len(vals) < 3 or _is_axis_position_series(name):
            continue
        span = max(vals) - min(vals)
        if span > 0:
            ranges.append((name, span))
    return ranges


def _looks_like_stage1_geometry_reconstruction(matplotlib_code: str) -> bool:
    code = matplotlib_code or ""
    return bool(
        MARK_REGENERATION_PATTERN.search(code)
        and STAGE_READOUT_RECONSTRUCTION_PATTERN.search(code)
        and _count_numeric_array_assignments(code) >= 2
    )


def _infer_attack_chart_families(matplotlib_code: str) -> set[str]:
    code = matplotlib_code or ""
    families: set[str] = set()
    if PIE_CALL_PATTERN.search(code):
        families.add("pie_or_donut_chart")
    if BAR_CALL_PATTERN.search(code):
        families.add("bar_chart")
    if STACK_OR_FILL_PATTERN.search(code):
        families.add("multi_series_chart")
    if LINE_CALL_PATTERN.search(code):
        families.add("line_chart")
    if SCATTER_CALL_PATTERN.search(code):
        families.add("multi_series_chart")
    return families


def _has_area_encoding_evidence(matplotlib_code: str) -> bool:
    code = matplotlib_code or ""
    scatter_with_size = bool(SCATTER_CALL_PATTERN.search(code) and AREA_SIZE_CHANNEL_PATTERN.search(code))
    plot_with_marker_size = bool(LINE_CALL_PATTERN.search(code) and AREA_SIZE_CHANNEL_PATTERN.search(code))
    return any(
        (
            scatter_with_size,
            plot_with_marker_size,
            PIE_CALL_PATTERN.search(code),
            AREA_PATCH_PATTERN.search(code),
            ICONIC_MARK_PATTERN.search(code),
        )
    )


def _validate_mark_policy_fields(
    *,
    attack_plan: dict[str, Any],
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    allowed_mark_changes = _listify_profile_field(error_profile.get("allowed_mark_changes"))
    if allowed_mark_changes:
        mark_change_type = str(attack_plan.get("mark_change_type", "")).strip()
        if mark_change_type and mark_change_type not in allowed_mark_changes:
            return ValidationResult(
                False,
                f"Invalid attack: mark_change_type '{mark_change_type}' is not allowed by the profile.",
            )

    allowed_scope_changes = _listify_profile_field(error_profile.get("allowed_scope_changes"))
    if allowed_scope_changes:
        scope_change = str(attack_plan.get("scope_change", "")).strip()
        if scope_change and scope_change not in allowed_scope_changes:
            return ValidationResult(
                False,
                f"Invalid attack: scope_change '{scope_change}' is not allowed by the profile.",
            )

    protected_channels = _listify_profile_field(error_profile.get("protected_channels"))
    respected = attack_plan.get("protected_channels_respected")
    if respected is not None and not isinstance(respected, list):
        return ValidationResult(
            False,
            "Invalid attack: protected_channels_respected must be a JSON list when provided.",
        )
    if protected_channels and respected == []:
        return ValidationResult(
            False,
            "Invalid attack: protected_channels_respected is empty even though the profile declares protected channels.",
        )

    if attack_plan.get("data_fidelity_explanation") is not None:
        fidelity_explanation = str(attack_plan.get("data_fidelity_explanation", "")).strip()
        if not fidelity_explanation:
            return ValidationResult(
                False,
                "Invalid attack: data_fidelity_explanation is empty.",
            )

    return None


def _validate_profile_specific_mark_policy(
    *,
    attack_plan: dict[str, Any],
    matplotlib_code: str,
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    error_type = _profile_error_type(error_profile, attack_plan)
    invalid_if = set(_listify_profile_field(error_profile.get("invalid_if")))
    protected_channels = set(_listify_profile_field(error_profile.get("protected_channels")))

    if error_type == "discretizedcontinuousvariable":
        if "relabels_discrete_bands_inconsistently_with_original_order" in invalid_if:
            if MANUAL_ENTITY_BAND_ASSIGNMENT_PATTERN.search(matplotlib_code or ""):
                return ValidationResult(
                    False,
                    "Invalid discretizedcontinuousvariable attack: code manually assigns entities into named bands, which risks violating original order fidelity.",
                )

        if (
            "changes_non_target_channels" in invalid_if
            and "non_target_channels" in protected_channels
            and SCATTER_CALL_PATTERN.search(matplotlib_code or "")
            and STAGE_READOUT_RECONSTRUCTION_PATTERN.search(matplotlib_code or "")
            and _count_numeric_array_assignments(matplotlib_code or "") >= 2
        ):
            return ValidationResult(
                False,
                "Invalid discretizedcontinuousvariable attack: scatter/bubble chart is reconstructed from Stage-1 readout across multiple numeric channels, so non-target channels cannot be trusted to remain faithful.",
            )

        if (
            "changes_non_target_channels" in invalid_if
            and "non_target_channels" in protected_channels
            and SCATTER_CALL_PATTERN.search(matplotlib_code or "")
            and BUBBLE_SIZE_CHANNEL_PATTERN.search(matplotlib_code or "")
            and _count_numeric_array_assignments(matplotlib_code or "") >= 3
        ):
            return ValidationResult(
                False,
                "Invalid discretizedcontinuousvariable attack: bubble/scatter code manually redefines secondary quantitative channels, which exceeds the allowed encoding-only transformation.",
            )

    return None


def _validate_second_batch_specializations(
    *,
    attack_plan: dict[str, Any],
    matplotlib_code: str,
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    error_type = _profile_error_type(error_profile, attack_plan)
    code = matplotlib_code or ""
    stage1_reconstruction = _looks_like_stage1_geometry_reconstruction(code)
    protected_channels = set(_listify_profile_field(error_profile.get("protected_channels")))

    if error_type == "dualaxis":
        if not TWIN_AXIS_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid dualaxis attack: code does not create a real secondary axis.",
            )

    if error_type == "truncatedaxis":
        if not AXIS_LIMIT_CALL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid truncatedaxis attack: code does not explicitly narrow the visible axis range.",
            )

    if error_type == "changingscale":
        if not (TRANSFORM_FUNCTION_PATTERN.search(code) or (EXPLICIT_TICK_CONFIG_PATTERN.search(code) and EXPLICIT_TICKLABEL_CONFIG_PATTERN.search(code))):
            return ValidationResult(
                False,
                "Invalid changingscale attack: code does not show an explicit non-linear/piecewise scale manipulation.",
            )

    if error_type == "inconsistentticklabels":
        if not (EXPLICIT_TICK_CONFIG_PATTERN.search(code) and EXPLICIT_TICKLABEL_CONFIG_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid inconsistentticklabels attack: code does not explicitly redefine tick positions and labels.",
            )

    if error_type == "Cherry_Picking":
        if not SUBSETTING_EVIDENCE_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid Cherry_Picking attack: code does not show clear evidence of selective subsetting/windowing.",
            )

    if error_type == "Missing_Data":
        if not (SUBSETTING_EVIDENCE_PATTERN.search(code) or BLANK_LABEL_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid Missing_Data attack: code does not show a concrete missingness mechanism such as omitted labels, missing categories, or truncated visible scope.",
            )

    if error_type == "Missing_Normalization":
        if NORMALIZATION_SIGNAL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid Missing_Normalization attack: code appears to introduce explicit normalization/aggregation cues instead of withholding them.",
            )
        if (
            stage1_reconstruction
            and SCATTER_CALL_PATTERN.search(code)
            and ("raw_values" in protected_channels or "primary_mark_geometry" in protected_channels)
        ):
            return ValidationResult(
                False,
                "Invalid Missing_Normalization attack: scatter/bubble chart is reconstructed from Stage-1 readout, so raw-value fidelity cannot be trusted.",
            )

    if error_type == "narrative_framing":
        if stage1_reconstruction and "primary_mark_geometry" in protected_channels:
            return ValidationResult(
                False,
                "Invalid narrative_framing attack: chart-level framing should not reconstruct new chart geometry from Stage-1 readout.",
            )
        if not ANNOTATION_OR_CALLOUT_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid narrative_framing attack: code does not add any chart-level framing annotation/callout beyond ordinary chart drawing.",
            )

    if error_type == "Concealed_Uncertainty":
        if stage1_reconstruction and "primary_mark_geometry" in protected_channels:
            return ValidationResult(
                False,
                "Invalid Concealed_Uncertainty attack: uncertainty suppression should not reconstruct new chart geometry from Stage-1 readout.",
            )
        if not (UNCERTAINTY_SIGNAL_PATTERN.search(code) or REFERENCE_IMAGE_TOKEN_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid Concealed_Uncertainty attack: code does not provide evidence of uncertainty-band/errorbar manipulation.",
            )

    return None


def _validate_third_batch_specializations(
    *,
    attack_plan: dict[str, Any],
    matplotlib_code: str,
    error_profile: dict[str, Any],
    source_chart_type: str | None,
) -> ValidationResult | None:
    error_type = _profile_error_type(error_profile, attack_plan)
    code = matplotlib_code or ""
    stage1_reconstruction = _looks_like_stage1_geometry_reconstruction(code)
    protected_channels = set(_listify_profile_field(error_profile.get("protected_channels")))
    attack_families = _infer_attack_chart_families(code)

    if error_type == "confusingcharttype":
        if not attack_families:
            return ValidationResult(
                False,
                "Invalid confusingcharttype attack: code does not provide clear evidence of an actual chart-type remapping.",
            )
        if source_chart_type and attack_families == {source_chart_type}:
            return ValidationResult(
                False,
                f"Invalid confusingcharttype attack: inferred attack chart family still matches source_chart_type='{source_chart_type}'.",
            )
        if REFERENCE_IMAGE_TOKEN_PATTERN.search(code) and not MARK_REGENERATION_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid confusingcharttype attack: reference-only editing does not establish a genuine chart-type remapping.",
            )

    if error_type == "overplotting":
        line_calls = _count_pattern(code, LINE_CALL_PATTERN)
        scatter_calls = _count_pattern(code, SCATTER_CALL_PATTERN)
        alpha_values = _extract_alpha_values(code)
        if (
            stage1_reconstruction
            and ("raw_values" in protected_channels or "primary_mark_geometry" in protected_channels)
        ):
            return ValidationResult(
                False,
                "Invalid overplotting attack: code reconstructs chart geometry from Stage-1 readout, so raw-value fidelity cannot be trusted.",
            )
        if not (scatter_calls >= 1 or line_calls >= 2 or STACK_OR_FILL_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid overplotting attack: code does not show enough overlapping marks or multi-series crowding to support an overplotting mechanism.",
            )
        if alpha_values and max(alpha_values) < 0.55:
            return ValidationResult(
                False,
                "Invalid overplotting attack: marks are made too transparent, which mitigates rather than creates heavy overplotting.",
            )

    if error_type == "3d":
        if source_chart_type == "bar_chart":
            if not (THREE_D_PATTERN.search(code) or re.search(r"\bbar3d\s*\(", code, re.IGNORECASE)):
                return ValidationResult(
                    False,
                    "Invalid 3d attack: bar-chart source lacks explicit 3D bar or perspective-rendering evidence.",
                )
        elif source_chart_type == "pie_or_donut_chart" or PIE_CALL_PATTERN.search(code):
            if not (PIE_CALL_PATTERN.search(code) and (THREE_D_PATTERN.search(code) or PIE_DEPTH_PATTERN.search(code))):
                return ValidationResult(
                    False,
                    "Invalid 3d attack: pie/donut source lacks clear 3D depth or perspective cues.",
                )
        elif not THREE_D_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid 3d attack: code does not contain clear 3D rendering evidence.",
            )
        if _has_area_encoding_evidence(code) and not THREE_D_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid 3d attack: code looks more like area/icon encoding than perspective-based 3D distortion.",
            )

    if error_type == "areaencoding":
        if not _has_area_encoding_evidence(code):
            return ValidationResult(
                False,
                "Invalid areaencoding attack: code does not show clear area-based or pictorial/icon size encoding evidence.",
            )
        if THREE_D_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid areaencoding attack: code introduces explicit 3D perspective cues, which drifts into the 3d category.",
            )
        if source_chart_type == "bar_chart" and BAR_CALL_PATTERN.search(code) and not (
            AREA_PATCH_PATTERN.search(code)
            or ICONIC_MARK_PATTERN.search(code)
            or PIE_CALL_PATTERN.search(code)
            or (SCATTER_CALL_PATTERN.search(code) and AREA_SIZE_CHANNEL_PATTERN.search(code))
        ):
            return ValidationResult(
                False,
                "Invalid areaencoding attack: standard bar rendering is still length-coded and does not establish a genuine area/pictorial encoding transformation.",
            )

    return None


def _validate_fourth_batch_specializations(
    *,
    attack_plan: dict[str, Any],
    matplotlib_code: str,
    error_profile: dict[str, Any],
    source_chart_type: str | None,
) -> ValidationResult | None:
    error_type = _profile_error_type(error_profile, attack_plan)
    code = matplotlib_code or ""
    stage1_reconstruction = _looks_like_stage1_geometry_reconstruction(code)
    protected_channels = set(_listify_profile_field(error_profile.get("protected_channels")))

    if error_type == "confusinglegend":
        if not LEGEND_CALL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid confusinglegend attack: code does not create any legend, which drifts into missinglegend.",
            )
        if not LEGEND_CONFUSION_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid confusinglegend attack: legend exists, but code does not show a concrete ambiguity mechanism such as remapped handles, displaced placement, or weakened legend-key binding.",
            )

    if error_type == "inconsistentvaluelabels":
        if not ANNOTATION_OR_CALLOUT_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid inconsistentvaluelabels attack: code does not add in-chart annotations or numeric guide labels.",
            )
        if not (NUMERIC_TEXT_LITERAL_PATTERN.search(code) or SUMMARY_LABEL_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid inconsistentvaluelabels attack: annotation text does not contain numeric or summary-style value labels.",
            )
        if stage1_reconstruction and "primary_mark_geometry" in protected_channels:
            return ValidationResult(
                False,
                "Invalid inconsistentvaluelabels attack: in-chart label manipulation should not reconstruct new chart geometry from Stage-1 readout.",
            )

    if error_type == "dataindifferentmagnitudes":
        if TWIN_AXIS_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid dataindifferentmagnitudes attack: code creates a second axis, which drifts into dualaxis.",
            )
        ranges = sorted((span for _, span in _non_position_series_ranges(code)), reverse=True)
        if len(ranges) < 2:
            return ValidationResult(
                False,
                "Invalid dataindifferentmagnitudes attack: code does not expose at least two non-positional quantitative series on the same axis.",
            )
        small = max(ranges[-1], 1e-9)
        if ranges[0] / small < 8.0:
            return ValidationResult(
                False,
                "Invalid dataindifferentmagnitudes attack: quantitative series do not show a strong enough same-axis magnitude disparity.",
            )

    if error_type == "inappropriateaspectratio":
        figsize = _extract_figsize(code)
        if not figsize:
            return ValidationResult(
                False,
                "Invalid inappropriateaspectratio attack: code does not set an explicit figure aspect ratio.",
            )
        width, height = figsize
        ratio = width / height if height else 0.0
        if not (ratio >= 1.8 or ratio <= 0.6):
            return ValidationResult(
                False,
                "Invalid inappropriateaspectratio attack: figure shape is not extreme enough to plausibly amplify or flatten perceived slope.",
            )
        if not LINE_CALL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid inappropriateaspectratio attack: code does not contain a line-based chart where aspect ratio would materially affect slope perception.",
            )

    if error_type == "misusingcircularlayout":
        if not (PIE_CALL_PATTERN.search(code) or POLAR_LAYOUT_PATTERN.search(code) or RADAR_SIGNAL_PATTERN.search(code)):
            return ValidationResult(
                False,
                "Invalid misusingcircularlayout attack: code does not provide clear pie/donut/polar/radar layout evidence.",
            )
        if THREE_D_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid misusingcircularlayout attack: code introduces explicit 3D cues, which drifts into 3d.",
            )

    if error_type == "sineillusion":
        if not LINE_CALL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid sineillusion attack: code does not contain a line-based chart.",
            )
        if not CURVE_DISTORTION_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid sineillusion attack: code does not show sinusoidal/curvilinear interpolation or wave-like curve construction.",
            )

    if error_type == "invertedaxis":
        if not _has_reversed_axis(code):
            return ValidationResult(
                False,
                "Invalid invertedaxis attack: code does not explicitly invert an axis or reverse axis limits.",
            )

    if error_type == "extendedaxis":
        if not AXIS_LIMIT_CALL_PATTERN.search(code):
            return ValidationResult(
                False,
                "Invalid extendedaxis attack: code does not explicitly expand axis limits.",
            )
        if _has_reversed_axis(code):
            return ValidationResult(
                False,
                "Invalid extendedaxis attack: axis reversal is present, which drifts toward invertedaxis.",
            )
        if not _has_extended_axis_padding(code):
            return ValidationResult(
                False,
                "Invalid extendedaxis attack: axis limits do not show clear excess empty range relative to the plotted data.",
            )

    return None


def _validate_mark_policy_family(
    *,
    attack_plan: dict[str, Any],
    matplotlib_code: str,
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    mark_change_type = str(attack_plan.get("mark_change_type", "")).strip()
    scope_change = str(attack_plan.get("scope_change", "")).strip()
    structure_policy = str(error_profile.get("structure_policy", "preserve")).strip().lower()
    text_policy = str(error_profile.get("text_policy", "neutral_only")).strip().lower()
    protected_channels = set(_listify_profile_field(error_profile.get("protected_channels")))
    invalid_if = set(_listify_profile_field(error_profile.get("invalid_if")))
    allowed_scope_changes = set(_listify_profile_field(error_profile.get("allowed_scope_changes")))

    if not mark_change_type:
        return None

    code = matplotlib_code or ""
    stage1_reconstruction = _looks_like_stage1_geometry_reconstruction(code)

    if mark_change_type in TEXT_OR_REFERENCE_ONLY_MARK_CHANGE_TYPES:
        if (
            stage1_reconstruction
            and ("primary_mark_geometry" in protected_channels or "non_target_channels" in protected_channels)
            and "changes_primary_geometry_without_profile_permission" in invalid_if
        ):
            return ValidationResult(
                False,
                f"Invalid attack: mark_change_type '{mark_change_type}' should preserve the original chart geometry, but the code appears to reconstruct marks from Stage-1 readout.",
            )

    if mark_change_type == "in_chart_label_text_only" and text_policy != "in_chart_numeric_conflict_allowed":
        return ValidationResult(
            False,
            "Invalid attack: in_chart_label_text_only is not allowed unless the profile permits in-chart numeric conflict.",
        )

    if mark_change_type == "chart_level_framing_only" and text_policy != "chart_level_bias_allowed":
        return ValidationResult(
            False,
            "Invalid attack: chart_level_framing_only is not allowed unless the profile permits chart-level bias.",
        )

    if mark_change_type == "subset_selection_only" and structure_policy != "subset_allowed":
        return ValidationResult(
            False,
            "Invalid attack: subset_selection_only requires structure_policy=subset_allowed.",
        )

    if mark_change_type == "context_omission_only" and structure_policy != "omission_allowed":
        return ValidationResult(
            False,
            "Invalid attack: context_omission_only requires structure_policy=omission_allowed.",
        )

    if mark_change_type == "normalization_context_omission_only" and structure_policy not in {"preserve", "omission_allowed"}:
        return ValidationResult(
            False,
            "Invalid attack: normalization_context_omission_only is incompatible with the current structure policy.",
        )

    if (
        mark_change_type not in SCOPE_RELAXING_MARK_CHANGE_TYPES
        and scope_change
        and scope_change != "none"
        and scope_change not in allowed_scope_changes
        and "changes_scope_without_profile_permission" in invalid_if
    ):
        return ValidationResult(
            False,
            f"Invalid attack: mark_change_type '{mark_change_type}' is not supposed to change scope, but scope_change='{scope_change}'.",
        )

    return None


def _validate_tactic_family(
    *,
    attack_plan: dict[str, Any],
    task_mode: str,
    error_profile: dict[str, Any],
) -> ValidationResult | None:
    error_type = _profile_error_type(error_profile, attack_plan)
    if error_type not in {"Cherry_Picking", "Missing_Data"}:
        return None

    tactic_family = attack_plan.get("tactic_family")
    if not tactic_family:
        return ValidationResult(False, f"Invalid attack: tactic_family is required for {error_type}.")
    if not attack_plan.get("corrective_evidence_to_break"):
        return ValidationResult(False, f"Invalid attack: corrective_evidence_to_break is required for {error_type}.")
    if not attack_plan.get("how_this_revision_breaks_it"):
        return ValidationResult(False, f"Invalid attack: how_this_revision_breaks_it is required for {error_type}.")

    library = _load_tactic_library().get("tactics", [])
    allowed = {
        item.get("tactic_family")
        for item in library
        if item.get("error_type") == error_type and task_mode in (item.get("task_modes") or [])
    }
    if allowed and tactic_family not in allowed:
        return ValidationResult(
            False,
            f"Invalid attack: tactic_family '{tactic_family}' is not allowed for {error_type} under {task_mode}.",
        )
    return None


def _validate_retry_diversity(
    *,
    attack_plan: dict[str, Any],
    prev_attack_plan: dict[str, Any] | None,
) -> ValidationResult | None:
    if not prev_attack_plan:
        return None
    error_type = attack_plan.get("target_error_type")
    if error_type not in {"Cherry_Picking", "Missing_Data"}:
        return None

    prev_wrong = prev_attack_plan.get("target_wrong_option") or prev_attack_plan.get("expected_wrong_option")
    curr_wrong = attack_plan.get("target_wrong_option") or attack_plan.get("expected_wrong_option")
    same_family = prev_attack_plan.get("tactic_family") == attack_plan.get("tactic_family")
    same_wrong = prev_wrong == curr_wrong
    same_stage = prev_attack_plan.get("target_stage") == attack_plan.get("target_stage")
    if same_family and same_wrong and same_stage:
        return ValidationResult(
            False,
            "Invalid retry: repeated the same tactic_family, target_wrong_option, and target_stage.",
        )
    return None


def validate_attack_plan(
    attack_plan: dict,
    matplotlib_code: str,
    *,
    question: str | None = None,
    options: dict | None = None,
    gold_answer: str | None = None,
    task_mode: str | None = None,
    error_profile: dict[str, Any] | None = None,
    prev_attack_plan: dict[str, Any] | None = None,
    source_chart_path: str | None = None,
    source_chart_type: str | None = None,
) -> ValidationResult:
    """
    Validate an attack plan before the attacked chart is accepted by the loop.

    The validator is conservative but mode-aware:
    - `strict_answerable` requires direct recoverability of the benchmark answer
    - `abstention_aware` allows the correct answer to be "cannot infer"
    - `scope_reasoning` allows scope/framing/subsetting attacks when the profile permits them
    """
    if not attack_plan:
        return ValidationResult(False, "Missing attack plan.")

    mode = normalize_task_mode(task_mode)
    profile = _merged_profile(attack_plan, error_profile)

    profile_validation = _validate_task_mode_and_profile(
        attack_plan=attack_plan,
        task_mode=mode,
        error_profile=profile,
        question=question,
        options=options,
    )
    if profile_validation is not None:
        return profile_validation

    self_check_validation = _validate_self_check(attack_plan, task_mode=mode)
    if self_check_validation is not None:
        return self_check_validation

    option_aware_validation = _validate_option_aware_fields(
        attack_plan=attack_plan,
        options=options,
        gold_answer=gold_answer,
    )
    if option_aware_validation is not None:
        return option_aware_validation

    mark_policy_field_validation = _validate_mark_policy_fields(
        attack_plan=attack_plan,
        error_profile=profile,
    )
    if mark_policy_field_validation is not None:
        return mark_policy_field_validation

    data_fidelity_validation = _validate_data_fidelity_policy(
        matplotlib_code=matplotlib_code,
        error_profile=profile,
        source_chart_path=source_chart_path,
    )
    if data_fidelity_validation is not None:
        return data_fidelity_validation

    profile_specific_mark_policy_validation = _validate_profile_specific_mark_policy(
        attack_plan=attack_plan,
        matplotlib_code=matplotlib_code,
        error_profile=profile,
    )
    if profile_specific_mark_policy_validation is not None:
        return profile_specific_mark_policy_validation

    mark_policy_family_validation = _validate_mark_policy_family(
        attack_plan=attack_plan,
        matplotlib_code=matplotlib_code,
        error_profile=profile,
    )
    if mark_policy_family_validation is not None:
        return mark_policy_family_validation

    second_batch_specialization_validation = _validate_second_batch_specializations(
        attack_plan=attack_plan,
        matplotlib_code=matplotlib_code,
        error_profile=profile,
    )
    if second_batch_specialization_validation is not None:
        return second_batch_specialization_validation

    third_batch_specialization_validation = _validate_third_batch_specializations(
        attack_plan=attack_plan,
        matplotlib_code=matplotlib_code,
        error_profile=profile,
        source_chart_type=source_chart_type,
    )
    if third_batch_specialization_validation is not None:
        return third_batch_specialization_validation

    fourth_batch_specialization_validation = _validate_fourth_batch_specializations(
        attack_plan=attack_plan,
        matplotlib_code=matplotlib_code,
        error_profile=profile,
        source_chart_type=source_chart_type,
    )
    if fourth_batch_specialization_validation is not None:
        return fourth_batch_specialization_validation

    tactic_validation = _validate_tactic_family(
        attack_plan=attack_plan,
        task_mode=mode,
        error_profile=profile,
    )
    if tactic_validation is not None:
        return tactic_validation

    retry_validation = _validate_retry_diversity(
        attack_plan=attack_plan,
        prev_attack_plan=prev_attack_plan,
    )
    if retry_validation is not None:
        return retry_validation

    anti_triviality_validation = _validate_anti_triviality(
        matplotlib_code=matplotlib_code,
        task_mode=mode,
        error_profile=profile,
    )
    if anti_triviality_validation is not None:
        return anti_triviality_validation

    structure_policy = profile.get("structure_policy", "preserve")
    if matplotlib_code:
        for heuristic_code, description, pattern in CODE_HEURISTIC_PATTERNS:
            if not pattern.search(matplotlib_code):
                continue
            if _skip_heuristic_for_structure(heuristic_code, structure_policy):
                continue
            return ValidationResult(
                False,
                f"Invalid attack by static code heuristic: detected {description}.",
            )

    return ValidationResult(True, f"Attack passed {mode} validation.")
