"""
Optional QA refactor agent for non-strict task modes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import llm_client
from task_modes import (
    ABSTENTION_AWARE,
    SCOPE_REASONING,
    STRICT_ANSWERABLE,
    looks_like_exact_lookup,
    normalize_task_mode,
)


_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "qa_refactor_system.txt").read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"No JSON object found in QA refactor response: {text[:400]}")


def needs_qa_refactor(task_mode: str, error_profile: dict[str, Any] | None) -> bool:
    profile = error_profile or {}
    mode = normalize_task_mode(task_mode)
    if profile.get("qa_refactor_policy") == "required":
        return True
    return mode in {ABSTENTION_AWARE, SCOPE_REASONING}


_CAUTIOUS_SCOPE_PATTERNS = [
    r"\bdoes not justify\b",
    r"\bdoes not support\b",
    r"\bnot enough evidence\b",
    r"\binsufficient evidence\b",
    r"\bcannot conclude\b",
    r"\bcannot determine\b",
    r"\bcannot generalize\b",
    r"\bshould not generalize\b",
    r"\bonly supports\b",
    r"\bonly shows\b",
    r"\bonly the shown\b",
    r"\bonly the visible\b",
    r"\bvisible subset\b",
    r"\bshown subset\b",
    r"\bshown period\b",
    r"\bvisible period\b",
    r"\bvisible (?:data|evidence|period)\b",
    r"\bshown (?:data|evidence|period)\b",
    r"\bbased on (?:the )?(?:visible|shown)\b",
    r"\bbest supported by the (?:visible|shown)\b",
]

_OVERGENERALIZED_SCOPE_PATTERNS = [
    r"\bthroughout\b",
    r"\ball year\b",
    r"\brest of the year\b",
    r"\boverall\b",
    r"\balways\b",
    r"\bcontinued\b",
    r"\blong[- ]term\b",
    r"\byear[- ]round\b",
    r"\bwe can conclude\b",
    r"\bthis proves\b",
    r"\bgeneralize\b",
    r"\ballows us to predict\b",
    r"\bindicates that .* will\b",
    r"\bby december\b",
    r"\bfor the year\b",
    r"\bother years\b",
    r"\bmost other years\b",
]


def _looks_like_cautious_scope_option(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(re.search(pattern, lowered) for pattern in _CAUTIOUS_SCOPE_PATTERNS)


def _looks_like_overgeneralized_scope_option(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return any(re.search(pattern, lowered) for pattern in _OVERGENERALIZED_SCOPE_PATTERNS)


def _build_refactor_guidance(task_mode: str, error_profile: dict[str, Any]) -> str:
    profile = error_profile or {}
    error_type = profile.get("error_type", "unknown")
    notes: list[str] = []

    if task_mode == ABSTENTION_AWARE:
        notes.append(
            "Keep the question natural. Do not explicitly mention that data are missing or that the right answer is abstention."
        )
        notes.append(
            "Use one abstention option and three plausible distractors based on nearby values, interpolation, or tempting approximate readings."
        )
    if task_mode == SCOPE_REASONING:
        notes.append(
            "Prefer asking which conclusion is best supported, unsupported, or overgeneralized by the visible evidence."
        )
        notes.append(
            "Include one cautious option that stays tightly bounded to the visible evidence or explicitly refuses a broader conclusion."
        )
    if error_type == "Missing_Data":
        notes.append(
            "Missing_Data questions should reward noticing missing support without adding overt disclosure text in the wording."
        )
    if error_type == "Cherry_Picking":
        notes.append(
            "For Cherry_Picking, the correct option should usually be the cautious evidence-bounded interpretation; the visually tempting broader claim should be a distractor."
        )
        notes.append(
            "A good Cherry_Picking gold option often contains phrases like 'only the shown period', 'does not justify a long-term conclusion', or 'cannot generalize beyond the visible subset'."
        )
        notes.append(
            "A good Cherry_Picking distractor often contains phrases like 'overall trend', 'long-term trend', 'throughout the year', or 'year-round'."
        )
    if error_type == "narrative_framing":
        notes.append(
            "For Narrative Framing, let the title/caption bias tempt a stronger claim, but make the correct option the one grounded in the visible chart evidence."
        )
        notes.append(
            "A good Narrative Framing gold option often says the chart only supports the visible evidence, not the stronger framed claim."
        )
        notes.append(
            "A good Narrative Framing distractor often repeats the title/caption bias as if it were fully justified by the chart."
        )
    if error_type == "Concealed_Uncertainty":
        notes.append(
            "For Concealed_Uncertainty, prefer a correct option that preserves appropriate uncertainty instead of an overconfident summary."
        )

    profile_refactor_notes = profile.get("refactor_notes")
    if profile_refactor_notes:
        notes.append(str(profile_refactor_notes))

    if not notes:
        return "No extra refactor guidance."
    return "\n".join(f"- {note}" for note in notes)


def _build_retry_feedback(
    *,
    last_error: str,
    prepared: dict[str, Any],
) -> str:
    error_type = (prepared.get("error_profile") or {}).get("error_type")
    task_mode = prepared.get("task_mode")
    extra: list[str] = [last_error]

    if task_mode == SCOPE_REASONING and error_type in {"Cherry_Picking", "narrative_framing"}:
        extra.append(
            "Use a scope-reasoning question stem such as 'Which conclusion is best supported by the visible chart evidence?' or 'Which statement is most justified by the plotted data?'"
        )
        extra.append(
            "Make the gold option explicitly cautious. It should contain wording like 'only the shown data/period', 'does not justify a broader conclusion', or 'cannot generalize'."
        )
        extra.append(
            "Include at least one distractor that is clearly broader and more tempting, using wording like 'overall', 'long-term', 'throughout the year', or 'year-round'."
        )
    elif task_mode == SCOPE_REASONING and error_type == "Concealed_Uncertainty":
        extra.append(
            "Make the gold option preserve uncertainty or hedging, and make a distractor overconfident or too definitive."
        )

    return "\n".join(f"- {item}" for item in extra)


_ANCHOR_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "average",
    "chart",
    "data",
    "depicted",
    "displayed",
    "does",
    "figure",
    "for",
    "graph",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "shown",
    "show",
    "the",
    "their",
    "there",
    "these",
    "this",
    "those",
    "to",
    "trend",
    "value",
    "values",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}


def _extract_key_nouns(text: str) -> set[str]:
    """Extract candidate anchor tokens while skipping question words and generic chart terms."""
    if not text:
        return set()
    raw_tokens = re.findall(r"\b[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)?\b", text)
    nouns: set[str] = set()
    for token in raw_tokens:
        lowered = token.lower()
        if lowered in _ANCHOR_STOPWORDS:
            continue
        if token.isdigit() or re.fullmatch(r"\d+(?:\.\d+)?", token):
            nouns.add(lowered)
            continue
        if len(lowered) <= 1:
            continue
        nouns.add(lowered)
    return nouns


def _validate_anchor(
    original_question: str,
    refactored_question: str,
    original_options: dict[str, Any] | None = None,
    refactored_options: dict[str, Any] | None = None,
) -> str | None:
    """
    Check that the refactored question stays anchored to the same subject as
    the original.  We do this by verifying that at least one of the original
    question's key entity tokens appears in the refactored question or options.
    """
    orig_nouns = _extract_key_nouns(original_question)
    # Also consider entity names from original answer options
    for opt_text in (original_options or {}).values():
        orig_nouns |= _extract_key_nouns(str(opt_text))

    if not orig_nouns:
        return None  # Can't validate — no key entities found

    refact_text = refactored_question + " " + " ".join(str(v) for v in (refactored_options or {}).values())
    refact_nouns = _extract_key_nouns(refact_text)

    overlap = orig_nouns & refact_nouns
    if not overlap:
        return (
            "Refactored QA appears to have drifted from the original subject. "
            "The question and options share no key entity tokens with the original. "
            f"Original key tokens: {sorted(orig_nouns)[:8]}. "
            "Ensure the refactored question is still about the same entities."
        )
    return None


def _validate_refactor_result(
    *,
    original_sample: dict[str, Any],
    prepared: dict[str, Any],
    result: dict[str, Any],
) -> str | None:
    options = result.get("options") or {}
    if set(options.keys()) != {"A", "B", "C", "D"}:
        return "QA refactor must return exactly A/B/C/D options."

    gold_answer = result.get("gold_answer")
    if gold_answer not in options:
        return "QA refactor gold_answer must be one of A/B/C/D."

    # Anchor check: refactored question must share key entities with original
    anchor_error = _validate_anchor(
        original_question=original_sample.get("question", ""),
        refactored_question=result.get("question", ""),
        original_options=original_sample.get("options", {}),
        refactored_options=options,
    )
    if anchor_error:
        return anchor_error

    task_mode = prepared["task_mode"]
    error_type = (prepared.get("error_profile") or {}).get("error_type")
    original_exact_lookup = looks_like_exact_lookup(
        original_sample.get("question"),
        original_sample.get("options"),
    )

    if task_mode == SCOPE_REASONING and error_type in {
        "Cherry_Picking",
        "narrative_framing",
        "Concealed_Uncertainty",
    }:
        gold_text = str(options[gold_answer])
        requires_cautious_gold = error_type in {"Cherry_Picking", "narrative_framing"} or original_exact_lookup
        if requires_cautious_gold and not _looks_like_cautious_scope_option(gold_text):
            return (
                f"{error_type} scope_reasoning refactor should make the gold answer a cautious, "
                "evidence-limited statement rather than the tempting overgeneralization."
            )
        if requires_cautious_gold and _looks_like_overgeneralized_scope_option(gold_text):
            return (
                f"{error_type} scope_reasoning gold answer should not smuggle in unseen time spans, "
                "other-year comparisons, or end-of-year claims."
            )
        if error_type == "Cherry_Picking":
            distractors = [text for key, text in options.items() if key != gold_answer]
            if not any(_looks_like_overgeneralized_scope_option(text) for text in distractors):
                return (
                    "Cherry_Picking scope_reasoning refactor should include at least one broader, "
                    "tempting overgeneralized distractor."
                )

    return None


def prepare_sample(
    client,
    sample: dict[str, Any],
    attack_request: dict[str, Any],
    *,
    enable_refactor: bool = True,
) -> dict[str, Any]:
    prepared = dict(sample)
    original_payload = {
        "question": sample["question"],
        "options": sample["options"],
        "gold_answer": sample["gold_answer"],
    }
    prepared["clean_eval"] = dict(original_payload)
    prepared["attack_eval"] = dict(original_payload)
    prepared["task_mode"] = normalize_task_mode(attack_request.get("task_mode"))
    prepared["error_profile"] = attack_request.get("error_profile") or {}
    prepared["attack_preferences"] = attack_request
    exact_lookup = looks_like_exact_lookup(sample.get("question"), sample.get("options"))
    exact_lookup_policy = prepared["error_profile"].get("exact_lookup_policy", "allow")
    requires_refactor = needs_qa_refactor(prepared["task_mode"], prepared["error_profile"])
    if exact_lookup and exact_lookup_policy in {"requires_refactor", "abstention_preferred"}:
        requires_refactor = True
    prepared["qa_refactor"] = {
        "applied": False,
        "required": requires_refactor,
        "reason": None,
    }

    if not enable_refactor or not prepared["qa_refactor"]["required"]:
        return prepared

    retry_feedback: str | None = None
    last_error: str | None = None
    result: dict[str, Any] | None = None
    for attempt in range(4):
        user_text = (
            "Refactor this QA pair so it matches the requested misleading-visualization task mode.\n\n"
            f"Original question: {sample['question']}\n"
            f"Original options: {json.dumps(sample['options'], ensure_ascii=False)}\n"
            f"Original gold answer: {sample['gold_answer']}\n\n"
            "Requested attack metadata:\n"
            f"{json.dumps(attack_request, ensure_ascii=False, indent=2)}\n\n"
            "Additional refactor guidance:\n"
            f"{_build_refactor_guidance(prepared['task_mode'], prepared['error_profile'])}\n\n"
        )
        if retry_feedback:
            user_text += (
                "Your previous rewrite did not satisfy a hard policy constraint.\n"
                f"Fix this issue in the new rewrite:\n{retry_feedback}\n\n"
            )
        if attempt >= 2 and prepared["task_mode"] == SCOPE_REASONING:
            user_text += (
                "Hard lexical requirement for this retry:\n"
                "- The gold option must be explicitly cautious and evidence-bounded.\n"
                "- At least one distractor must be clearly broader or overgeneralized than the gold.\n\n"
            )
        user_text += (
            "Return ONLY JSON with keys: question, options, gold_answer, reason.\n"
            "Keep exactly four options A-D."
        )

        raw = llm_client.complete_vision(
            client=client,
            system_prompt=_load_system_prompt(),
            user_text=user_text,
            image_path=sample["source_chart_path"],
            max_output_tokens=1200,
        )
        result = _extract_json(raw)
        last_error = _validate_refactor_result(
            original_sample=sample,
            prepared=prepared,
            result=result,
        )
        if last_error is None:
            break
        retry_feedback = _build_retry_feedback(last_error=last_error, prepared=prepared)

    if result is None or last_error is not None:
        raise ValueError(last_error or "QA refactor failed to produce a valid result.")

    prepared["attack_eval"] = {
        "question": result["question"],
        "options": result["options"],
        "gold_answer": result["gold_answer"],
    }
    prepared["qa_refactor"] = {
        "applied": True,
        "required": True,
        "reason": result.get("reason"),
    }
    return prepared
