"""
Forward Agent — reads a chart image and answers a multiple-choice question
using explicit staged reasoning that maps to the 4 benchmark layers.

Public API:
    analyze(client, chart_path, question, options, gold_answer) -> dict
    explain_failure(client, chart_path, question, options, gold_answer, trace) -> dict
"""

import json
import re
from pathlib import Path

import llm_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    return (_PROMPTS_DIR / "forward_system.txt").read_text()


def _options_text(options: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in options.items())


def extract_json(text: str) -> dict:
    """
    Extract the first JSON object from a Claude response.
    Handles:
      - bare JSON
      - JSON wrapped in ```json ... ``` fences
      - JSON wrapped in ``` ... ``` fences
    """
    # Try ```json ... ``` fence first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Try bare JSON object (first { to matching })
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(
        f"No JSON object found in Forward Agent response.\n"
        f"Response excerpt: {text[:300]}"
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def analyze(
    client,
    chart_path: str,
    question: str,
    options: dict,
    gold_answer: str,  # noqa: ARG001  (passed for context but not used in prompt)
) -> dict:
    """
    Have the Forward Agent analyze a chart image and return a ForwardTrace dict.

    Args:
        client:       OpenAI client instance
        chart_path:   path to the PNG to analyse
        question:     benchmark question string
        options:      dict of {"A": "...", "B": "...", ...}
        gold_answer:  the correct answer key (not sent to the agent)

    Returns:
        ForwardTrace dict with fields:
            stage_1_visual_readout, stage_2_mapping, stage_3_reasoning,
            stage_4_final_decision, predicted_answer, confidence,
            susceptible_stage, susceptible_original_layer, why_susceptible
    """
    system_prompt = _load_system_prompt()

    user_text = (
        "Please analyze this chart and answer the following multiple-choice question.\n\n"
        f"Question: {question}\n\n"
        f"Options:\n{_options_text(options)}\n\n"
        "Important: output ONLY a valid JSON object with the exact keys specified in "
        "your instructions. Do not include any prose before or after the JSON."
    )

    raw = llm_client.complete_vision(
        client=client,
        system_prompt=system_prompt,
        user_text=user_text,
        image_path=chart_path,
        max_output_tokens=2048,
    )
    return extract_json(raw)


def explain_failure(
    client,
    chart_path: str,
    question: str,
    options: dict,
    gold_answer: str,
    trace: dict,
) -> dict:
    """
    After the Forward Agent answered correctly on the attacked chart, ask it to
    explain why the attack failed.

    Returns a FailureExplanation dict with fields:
        why_attack_failed, robust_stage, detected_misleading_cue,
        decisive_corrective_evidence, suggested_more_dangerous_attack
    """
    system_prompt = _load_system_prompt()

    user_text = (
        f"Question: {question}\n\n"
        f"Options:\n{_options_text(options)}\n\n"
        f"Your previous analysis of this chart:\n{json.dumps(trace, indent=2)}\n\n"
        "You answered the attacked chart correctly "
        f"(your answer {trace.get('predicted_answer')} matches the gold answer {gold_answer}).\n\n"
        "Explain why the attack failed to fool you.\n\n"
        "Focus on:\n"
        "- which stage remained robust,\n"
        "- what misleading cue you noticed,\n"
        "- why you still trusted the correct evidence,\n"
        "- what kind of stronger manipulation would have been more dangerous.\n\n"
        "Output ONLY a valid JSON object with exactly these keys:\n"
        "{\n"
        '  "why_attack_failed": "...",\n'
        '  "robust_stage": "<Stage 1|Stage 2|Stage 3|Stage 4>",\n'
        '  "detected_misleading_cue": "...",\n'
        '  "decisive_corrective_evidence": "...",\n'
        '  "suggested_more_dangerous_attack": "..."\n'
        "}"
    )

    raw = llm_client.complete_vision(
        client=client,
        system_prompt=system_prompt,
        user_text=user_text,
        image_path=chart_path,
        max_output_tokens=1024,
    )
    return extract_json(raw)
