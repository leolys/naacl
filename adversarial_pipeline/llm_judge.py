"""
Optional LLM-based second-layer validator for successful attacked charts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import llm_client


_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "judge_system.txt").read_text()


def _load_mode_prompt(task_mode: str | None) -> str:
    mode = (task_mode or "strict_answerable").strip().lower()
    if mode == "abstention_aware":
        return (_PROMPTS_DIR / "judge_system_abstention_aware.txt").read_text()
    if mode == "scope_reasoning":
        return (_PROMPTS_DIR / "judge_system_scope_reasoning.txt").read_text()
    return _load_system_prompt()


def _options_text(options: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in options.items())


def _extract_json(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"No JSON object found in LLM judge response: {text[:400]}")


def audit_success(
    client,
    *,
    original_chart_path: str,
    attacked_chart_path: str,
    question: str,
    options: dict,
    gold_answer: str,
    attack_plan: dict,
    task_mode: str | None = None,
    error_profile: dict | None = None,
) -> dict:
    system_prompt = _load_mode_prompt(task_mode)
    user_text = (
        "Audit this attacked chart sample.\n\n"
        "You will receive two images in order:\n"
        "1. the original clean chart\n"
        "2. the attacked chart\n\n"
        f"Question: {question}\n\n"
        f"Options:\n{_options_text(options)}\n\n"
        f"Gold answer: {gold_answer}\n\n"
        f"Task mode: {task_mode or 'strict_answerable'}\n\n"
        "Attack metadata:\n"
        f"{json.dumps(attack_plan, indent=2)}\n\n"
        "Error-type profile:\n"
        f"{json.dumps(error_profile or {}, indent=2)}\n\n"
        "Return ONLY the required JSON object."
    )

    raw = llm_client.complete_multivision(
        client=client,
        system_prompt=system_prompt,
        user_text=user_text,
        image_paths=[original_chart_path, attacked_chart_path],
        max_output_tokens=1200,
    )
    result = _extract_json(raw)
    fidelity_policy = str((error_profile or {}).get("data_fidelity_policy", "")).strip().lower()
    if fidelity_policy == "exact_marks_required":
        if result.get("invalid_due_to_data_drift") is True or result.get("data_marks_preserved") is False:
            result["verdict"] = "invalid"
            result.setdefault(
                "main_issue",
                "Underlying data marks drifted even though the profile required exact mark preservation.",
            )
            result.setdefault(
                "reasoning",
                "Profiles with exact mark preservation must keep the original data geometry unchanged.",
            )
    violated_profile_policies = result.get("violated_profile_policies")
    if isinstance(violated_profile_policies, list) and violated_profile_policies:
        result["verdict"] = "invalid"
        result.setdefault(
            "main_issue",
            "The attacked chart appears to violate one or more profile-level mark/scope constraints.",
        )
        result.setdefault(
            "reasoning",
            "Profile-level mark-policy constraints are treated as hard audit rules for benchmark validity.",
        )
    verdict = result.get("verdict", "invalid")
    if verdict not in {"valid", "borderline", "invalid"}:
        result["verdict"] = "invalid"
    bucket_map = {
        "valid": "valid_success",
        "borderline": "borderline_success",
        "invalid": "invalid_success",
    }
    result["suggested_bucket"] = bucket_map[result["verdict"]]
    return result
