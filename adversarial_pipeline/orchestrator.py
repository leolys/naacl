"""
Orchestrator — drives the adversarial loop for one VLAT sample.

Protocol (up to max_rounds rounds):

  Step 0:  Forward Agent analyses the clean source chart.

  Round N (1..max_rounds):
    1. Reverse Agent inspects the latest Forward trace and generates an
       attacked chart (matplotlib code).
    2. Forward Agent analyses the attacked chart.
    3. If Forward Agent answers incorrectly → SUCCESS, stop.
    4. If still correct → Forward Agent explains why; pass explanation
       back to Reverse Agent in the next round.

Outputs:
  - outputs/logs/{sample_id}.jsonl  — one JSON line per round
  - outputs/successful/{sample_id}.json  — on success
  - outputs/failed/{sample_id}.json      — after all rounds fail

Public API:
    run_sample(client, sample, output_dir, definitions_text, max_rounds=3) -> dict
"""

import json
import logging
import os
import signal
import shutil
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

import chart_operators
import forward_agent
import llm_judge
import reverse_agent
import validator
import vlm_validator

logger = logging.getLogger(__name__)

TRANSIENT_RETRIES = int(os.environ.get("LLM_TRANSIENT_RETRIES", "4"))
TRANSIENT_BACKOFF_SEC = float(os.environ.get("LLM_TRANSIENT_BACKOFF_SEC", "3"))
MAX_SERVICE_RESTARTS_PER_ROUND = int(os.environ.get("MAX_SERVICE_RESTARTS_PER_ROUND", "2"))
LLM_STAGE_TIMEOUT_SEC = int(os.environ.get("LLM_STAGE_TIMEOUT_SEC", "150"))
MIN_ROUNDS_BEFORE_EARLY_STOP = int(os.environ.get("MIN_ROUNDS_BEFORE_EARLY_STOP", "3"))
EARLY_STOP_STAGNATION_STREAK = int(os.environ.get("EARLY_STOP_STAGNATION_STREAK", "2"))

LAYER_CODE_TO_NAME = {
    "L1": "VisualPerceptionLayer",
    "L2": "SemanticMappingLayer",
    "L3": "VisualReasoningLayer",
    "L4": "CognitiveLogicLayer",
}

LAYER_CODE_TO_NUM = {
    "L1": 1,
    "L2": 2,
    "L3": 3,
    "L4": 4,
}

HARD_FLIP_ONLY = "hard_flip_only"
FLIP_OR_CONFIDENCE_DROP = "flip_or_confidence_drop"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _make_round_record(
    round_id: int,
    chart_path: str,
    forward_trace: dict | None = None,
    attack_plan: dict | None = None,
    matplotlib_code: str | None = None,
    attack_outcome: dict | None = None,
    failure_explanation: dict | None = None,
) -> dict:
    return {
        "round_id": round_id,
        "current_chart_path": chart_path,
        "forward_trace": forward_trace,
        "attack_plan": attack_plan,
        "matplotlib_code": matplotlib_code,
        "attack_outcome": attack_outcome,
        "failure_explanation": failure_explanation,
    }


def _confidence_rank(value: str | None) -> int:
    table = {"low": 1, "medium": 2, "high": 3}
    return table.get(str(value or "").strip().lower(), 0)


def _success_policy(state: dict) -> str:
    profile = state.get("error_profile") or {}
    return str(profile.get("forward_effect_policy") or HARD_FLIP_ONLY)


def _assess_attack_effect(
    *,
    clean_trace: dict,
    attacked_trace: dict,
    gold_answer: str,
    success_policy: str,
    min_confidence_drop: int = 1,
) -> dict:
    predicted = attacked_trace.get("predicted_answer", "")
    clean_conf = clean_trace.get("confidence")
    attacked_conf = attacked_trace.get("confidence")
    confidence_drop = max(0, _confidence_rank(clean_conf) - _confidence_rank(attacked_conf))
    hard_success = predicted != gold_answer
    soft_success = (
        not hard_success
        and success_policy == FLIP_OR_CONFIDENCE_DROP
        and predicted == gold_answer
        and confidence_drop >= min_confidence_drop
    )
    effective_success = hard_success or soft_success
    success_type = "hard_success" if hard_success else ("soft_success" if soft_success else None)
    return {
        "success_policy": success_policy,
        "hard_success": hard_success,
        "soft_success": soft_success,
        "effective_success": effective_success,
        "success_type": success_type,
        "clean_confidence": clean_conf,
        "final_confidence": attacked_conf,
        "confidence_drop": confidence_drop,
    }


def _is_stagnant_transition(prev_round: dict, curr_round: dict) -> bool:
    prev_trace = prev_round.get("forward_trace") or {}
    curr_trace = curr_round.get("forward_trace") or {}
    prev_plan = prev_round.get("attack_plan") or {}
    curr_plan = curr_round.get("attack_plan") or {}

    if not prev_trace or not curr_trace:
        return False

    same_answer = prev_trace.get("predicted_answer") == curr_trace.get("predicted_answer")
    same_or_higher_confidence = _confidence_rank(curr_trace.get("confidence")) >= _confidence_rank(
        prev_trace.get("confidence")
    )
    same_error_type = prev_plan.get("target_error_type") == curr_plan.get("target_error_type")
    same_target_stage = prev_plan.get("target_stage") == curr_plan.get("target_stage")

    return same_answer and same_or_higher_confidence and same_error_type and same_target_stage


def _early_stop_reason(rounds: list[dict], max_rounds: int) -> str | None:
    if max_rounds <= MIN_ROUNDS_BEFORE_EARLY_STOP:
        return None
    if len(rounds) < max(MIN_ROUNDS_BEFORE_EARLY_STOP, EARLY_STOP_STAGNATION_STREAK + 1):
        return None

    recent = rounds[-(EARLY_STOP_STAGNATION_STREAK + 1) :]
    stagnant_pairs = [
        _is_stagnant_transition(recent[idx], recent[idx + 1])
        for idx in range(len(recent) - 1)
    ]
    if not all(stagnant_pairs):
        return None

    last_trace = recent[-1].get("forward_trace") or {}
    last_plan = recent[-1].get("attack_plan") or {}
    return (
        "Early-stopped due to no progress across the last "
        f"{EARLY_STOP_STAGNATION_STREAK + 1} rounds: Forward Agent kept answer "
        f"'{last_trace.get('predicted_answer')}' with non-improving confidence "
        f"while the attack stayed on {last_plan.get('target_error_type')} / {last_plan.get('target_stage')}."
    )


def _export_success_artifacts(output_dir: Path, state: dict, success_round: dict) -> None:
    success_root = output_dir / "successful_only"
    charts_dir = success_root / "charts"
    json_dir = success_root / "json"
    charts_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    sample_id = state["sample_id"]
    attack_plan = success_round.get("attack_plan") or {}
    final_chart_path = Path(success_round["current_chart_path"])
    exported_chart_path = charts_dir / f"{sample_id}{final_chart_path.suffix or '.png'}"
    shutil.copy2(final_chart_path, exported_chart_path)

    layer_code = attack_plan.get("target_original_layer")
    compact_record = {
        "sample_id": sample_id,
        "vis": state.get("vis", ""),
        "source_chart_path": state.get("source_chart_path"),
        "image_path": str(exported_chart_path.relative_to(output_dir)),
        "question": state.get("attack_question"),
        "option_A": state.get("attack_options", {}).get("A"),
        "option_B": state.get("attack_options", {}).get("B"),
        "option_C": state.get("attack_options", {}).get("C"),
        "option_D": state.get("attack_options", {}).get("D"),
        "correct_answer": state.get("attack_gold_answer"),
        "misleading_answer": (
            state.get("final_forward_answer")
            if state.get("success_type") == "hard_success"
            else None
        ),
        "model_final_answer": state.get("final_forward_answer"),
        "layer": LAYER_CODE_TO_NAME.get(layer_code, "GeneratedLayer"),
        "layer_num": LAYER_CODE_TO_NUM.get(layer_code),
        "category": "AgentGenerated",
        "error_type": attack_plan.get("target_error_type"),
        "attacked_stage": attack_plan.get("target_stage"),
        "cognitive_type": "Cognitive Hijacking",
        "dropped": "no",
        "qa_file": "generated_by_adversarial_pipeline",
        "global_id": None,
        "task_mode": state.get("task_mode", "strict_answerable"),
        "qa_refactor": state.get("qa_refactor"),
        "success_type": state.get("success_type"),
        "success_policy": state.get("success_policy"),
        "clean_forward_confidence": (state.get("clean_forward_trace") or {}).get("confidence"),
        "final_forward_confidence": state.get("final_forward_confidence"),
        "confidence_drop": state.get("confidence_drop", 0),
    }

    _write_json(json_dir / f"{sample_id}.json", compact_record)
    _append_jsonl(success_root / "successful_samples.jsonl", compact_record)
    return compact_record


def _export_reviewed_success_artifacts(
    output_dir: Path,
    compact_record: dict,
    chart_path: str | Path,
    judge_result: dict | None,
) -> None:
    verdict = (judge_result or {}).get("verdict", "unreviewed")
    bucket = (judge_result or {}).get("suggested_bucket")
    if not bucket:
        bucket = {
            "valid": "valid_success",
            "borderline": "borderline_success",
            "invalid": "invalid_success",
        }.get(verdict, "unreviewed_success")

    root = output_dir / "successful_reviewed" / bucket
    charts_dir = root / "charts"
    json_dir = root / "json"
    charts_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    sample_id = compact_record["sample_id"]
    chart_src = Path(chart_path)
    chart_dst = charts_dir / f"{sample_id}{chart_src.suffix or '.png'}"
    shutil.copy2(chart_src, chart_dst)

    reviewed_record = dict(compact_record)
    reviewed_record["image_path"] = str(chart_dst.relative_to(output_dir))
    reviewed_record["llm_judge"] = judge_result

    _write_json(json_dir / f"{sample_id}.json", reviewed_record)
    _append_jsonl(root / "samples.jsonl", reviewed_record)


def _maybe_llm_judge_success(
    client,
    state: dict,
    success_round: dict,
    judge_client=None,
) -> dict | None:
    if os.environ.get("ENABLE_LLM_JUDGE_VALIDATOR", "true").lower() != "true":
        return None
    # Use dedicated judge client if provided; otherwise fall back to primary client.
    effective_judge_client = judge_client if judge_client is not None else client
    try:
        result, transient_judge_error = _call_with_transient_retries(
            state["sample_id"],
            "LLM judge audit",
            llm_judge.audit_success,
            effective_judge_client,
            original_chart_path=state["source_chart_path"],
            attacked_chart_path=success_round["current_chart_path"],
            question=state["attack_question"],
            options=state["attack_options"],
            gold_answer=state["attack_gold_answer"],
            attack_plan=success_round.get("attack_plan") or {},
            task_mode=state.get("task_mode", "strict_answerable"),
            error_profile=state.get("error_profile"),
        )
        if transient_judge_error is not None:
            raise transient_judge_error
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] LLM judge audit failed: %s", state["sample_id"], exc)
        return {
            "verdict": "unreviewed",
            "recoverable_by_careful_reader": False,
            "structure_preserved": False,
            "main_issue": f"LLM judge failed: {exc}",
            "reasoning": "Audit did not complete.",
            "suggested_bucket": "unreviewed_success",
        }


def _is_transient_llm_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = [
        "503",
        "service_unavailable",
        "temporarily unavailable",
        "connection error",
        "connection prematurely closed",
        "before response",
        "unexpected eof while reading",
        "ssleoferror",
        "remote end closed connection without response",
        "ssl handshake",
        "do_handshake",
        "timeout",
        "timed out",
        "read timeout",
        "rate limit",
        "server error",
        "internal server error",
    ]
    return any(marker in text for marker in markers)


@contextmanager
def _stage_timeout(sample_id: str, stage_label: str, timeout_sec: int):
    if timeout_sec <= 0:
        yield
        return

    def _handle_alarm(signum, frame):  # noqa: ARG001
        raise TimeoutError(
            f"{stage_label} exceeded hard stage timeout of {timeout_sec}s "
            f"for sample {sample_id}"
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _handle_alarm)
    signal.alarm(timeout_sec)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def _call_with_transient_retries(sample_id: str, stage_label: str, func, *args, **kwargs):
    """
    Retry transient LLM failures with exponential backoff.

    Returns:
        (result, exhausted_transient_error)
    Raises:
        the original exception for non-transient failures.
    """
    delay = TRANSIENT_BACKOFF_SEC
    last_exc: Exception | None = None

    for attempt in range(1, TRANSIENT_RETRIES + 1):
        try:
            with _stage_timeout(sample_id, stage_label, LLM_STAGE_TIMEOUT_SEC):
                return func(*args, **kwargs), None
        except Exception as exc:  # noqa: BLE001
            if not _is_transient_llm_error(exc):
                raise
            last_exc = exc
            if attempt == TRANSIENT_RETRIES:
                break
            logger.warning(
                "[%s] %s transient failure (%d/%d): %s. Sleeping %.1fs before retry.",
                sample_id,
                stage_label,
                attempt,
                TRANSIENT_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)
            delay *= 2

    assert last_exc is not None
    return None, last_exc


# ---------------------------------------------------------------------------
# Source data loading helpers
# ---------------------------------------------------------------------------

def _load_source_data_table(sample: dict) -> str | None:
    """Load the CSV data table for a sample, if available."""
    table_path = sample.get("table_path")
    if not table_path or not Path(table_path).exists():
        return None
    try:
        content = Path(table_path).read_text(encoding="utf-8-sig").strip()
        # Truncate very large tables to avoid blowing up the prompt
        lines = content.split("\n")
        if len(lines) > 60:
            content = "\n".join(lines[:60]) + f"\n... ({len(lines) - 60} more rows truncated)"
        return content
    except Exception:
        return None


def _load_source_annotation(sample: dict) -> dict | None:
    """Load the chart annotation JSON for a sample, if available."""
    annotation_path = sample.get("annotation_path")
    if not annotation_path or not Path(annotation_path).exists():
        return None
    try:
        return json.loads(Path(annotation_path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _try_programmatic_operator(
    *,
    error_type: str | None,
    error_profile: dict | None,
    source_chart_path: str,
    source_annotation: dict | None,
    output_path: str,
    round_num: int,
) -> bool:
    """
    Try to generate the attacked chart using a deterministic PIL operator
    instead of the LLM Reverse Agent.

    Only used when:
      1. The profile specifies data_fidelity_policy = exact_marks_required
      2. An annotation is available (provides bboxes for the regions to erase)
      3. It is round 1 (later rounds use the previously-generated chart, which
         may already be modified, so the operator would paint over the wrong image)

    Returns True if the operator succeeded and the file was written.
    """
    if round_num != 1:
        return False
    if not error_type:
        return False
    profile = error_profile or {}
    if profile.get("data_fidelity_policy") != "exact_marks_required":
        return False
    if source_annotation is None:
        return False

    succeeded = chart_operators.apply_operator(
        error_type=error_type,
        src=source_chart_path,
        annotation=source_annotation,
        output_path=output_path,
    )
    if succeeded:
        logger.info(
            "Programmatic operator '%s' produced attacked chart at %s",
            error_type,
            output_path,
        )
    return succeeded


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_sample(
    client,
    sample: dict,
    output_dir: str | Path,
    definitions_text: str,
    max_rounds: int = 3,
    judge_client=None,
) -> dict:
    """
    Run the adversarial loop for one VLAT sample.

    Args:
        client:           OpenAI-compatible client
        sample:           dict with keys:
                            sample_id, source_chart_path, question,
                            options ({"A":...,"B":...}), gold_answer, vis
        output_dir:       base output directory (must contain charts/, logs/,
                          successful/, failed/ subdirs)
        definitions_text: contents of error_type_generation_definitions.md
        max_rounds:       maximum adversarial rounds (default 3)

    Returns:
        SampleState dict with full round history and final summary.
    """
    output_dir = Path(output_dir)
    sample_id = sample["sample_id"]
    clean_eval = sample.get("clean_eval") or {
        "question": sample["question"],
        "options": sample["options"],
        "gold_answer": sample["gold_answer"],
    }
    attack_eval = sample.get("attack_eval") or clean_eval
    clean_question = clean_eval["question"]
    clean_options = clean_eval["options"]
    clean_gold_answer = clean_eval["gold_answer"]
    attack_question = attack_eval["question"]
    attack_options = attack_eval["options"]
    attack_gold_answer = attack_eval["gold_answer"]
    source_chart_path = sample["source_chart_path"]
    attack_preferences = sample.get("attack_preferences")
    task_mode = sample.get("task_mode", "strict_answerable")
    error_profile = sample.get("error_profile")
    qa_refactor = sample.get("qa_refactor")
    source_chart_type = sample.get("chart_type")

    # Load source data table content if available
    source_data_table = _load_source_data_table(sample)
    source_annotation = _load_source_annotation(sample)

    log_path = output_dir / "logs" / f"{sample_id}.jsonl"

    # ------------------------------------------------------------------
    # Build the state envelope
    # ------------------------------------------------------------------
    state = {
        "sample_id": sample_id,
        "source_chart_path": source_chart_path,
        "question": attack_question,
        "options": attack_options,
        "gold_answer": attack_gold_answer,
        "clean_question": clean_question,
        "clean_options": clean_options,
        "clean_gold_answer": clean_gold_answer,
        "attack_question": attack_question,
        "attack_options": attack_options,
        "attack_gold_answer": attack_gold_answer,
        "vis": sample.get("vis", ""),
        "chart_type": source_chart_type,
        "task_mode": task_mode,
        "error_profile": error_profile,
        "qa_refactor": qa_refactor,
        "clean_forward_trace": None,
        "clean_forward_answer": None,
        "clean_forward_correct": None,
        "eligible_for_attack": None,
        "rounds": [],
        "final_success": False,
        "success_type": None,
        "success_policy": _success_policy(sample),
        "confidence_drop": 0,
        "final_round": 0,
        "dominant_error_type": None,
        "attacked_stage": None,
        "final_forward_answer": None,
        "final_forward_confidence": None,
        "why_succeeded_or_failed": None,
    }

    # ------------------------------------------------------------------
    # Step 0: Forward Agent analyses the clean source chart
    # ------------------------------------------------------------------
    logger.info("[%s] Step 0: Forward Agent on clean chart.", sample_id)
    try:
        clean_trace, clean_error = _call_with_transient_retries(
            sample_id,
            "Clean chart forward pass",
            forward_agent.analyze,
            client,
            source_chart_path,
            clean_question,
            clean_options,
            clean_gold_answer,
        )
        if clean_error is not None:
            raise clean_error
    except Exception as exc:
        logger.error("[%s] Forward Agent failed on clean chart: %s", sample_id, exc)
        state["why_succeeded_or_failed"] = f"Forward Agent failed on clean chart: {exc}"
        _write_json(output_dir / "failed" / f"{sample_id}.json", state)
        return state

    state["clean_forward_trace"] = clean_trace
    logger.info(
        "[%s] Clean chart answer: %s (gold: %s, confidence: %s)",
        sample_id,
        clean_trace.get("predicted_answer"),
        clean_gold_answer,
        clean_trace.get("confidence"),
    )
    state["clean_forward_answer"] = clean_trace.get("predicted_answer")
    state["clean_forward_correct"] = clean_trace.get("predicted_answer") == clean_gold_answer
    state["eligible_for_attack"] = state["clean_forward_correct"]

    if not state["clean_forward_correct"]:
        logger.warning(
            "[%s] Clean chart was already answered incorrectly (%s != %s). "
            "Skipping adversarial rounds because success would not be attributable to the attack.",
            sample_id,
            state["clean_forward_answer"],
            clean_gold_answer,
        )
        state["final_success"] = False
        state["final_round"] = 0
        state["final_forward_answer"] = state["clean_forward_answer"]
        state["why_succeeded_or_failed"] = (
            "Skipped adversarial rounds because the Forward Agent was already wrong "
            f"on the clean chart ({state['clean_forward_answer']} != {clean_gold_answer})."
        )
        _write_json(output_dir / "failed" / f"{sample_id}.json", state)
        return state

    # The trace the Reverse Agent will read in round N
    current_forward_trace = clean_trace
    prev_failure_explanation: dict | None = None
    prev_attack_plan: dict | None = None
    current_chart_reference_path = source_chart_path
    last_attacked_chart_path: str | None = None

    # ------------------------------------------------------------------
    # Adversarial rounds
    # ------------------------------------------------------------------
    round_num = 1
    while round_num <= max_rounds:
        logger.info("[%s] === Round %d / %d ===", sample_id, round_num, max_rounds)

        attacked_chart_path = str(
            output_dir / "charts" / f"{sample_id}_round{round_num}.png"
        )
        last_attacked_chart_path = attacked_chart_path
        service_restarts = 0

        # ----------------------------------------------------------------
        # Fast path: programmatic PIL operator (no LLM call)
        # Only for exact_marks_required profiles in round 1 with annotation.
        # ----------------------------------------------------------------
        _scheduled_error_type = (
            (attack_preferences or {}).get("target_error_type")
            or (error_profile or {}).get("error_type")
        )
        _prog_op_used = _try_programmatic_operator(
            error_type=_scheduled_error_type,
            error_profile=error_profile,
            source_chart_path=source_chart_path,
            source_annotation=source_annotation,
            output_path=attacked_chart_path,
            round_num=round_num,
        )
        if _prog_op_used:
            # Build a synthetic attack_plan so the rest of the pipeline works normally
            _prog_attack_plan = {
                "target_stage": "Stage 2",
                "target_original_layer": (error_profile or {}).get("layer_code", "L2"),
                "target_error_type": _scheduled_error_type,
                "task_mode": task_mode or "strict_answerable",
                "target_wrong_option": None,
                "tactic_family": "programmatic_operator",
                "beam_score": "N/A",
                "mark_change_type": "programmatic_erase",
                "scope_change": "none",
                "protected_channels_respected": ["primary_mark_geometry"],
                "data_fidelity_explanation": "PIL programmatic operator; source image marks unchanged.",
                "attack_rationale": (
                    f"Applied deterministic '{_scheduled_error_type}' operator: "
                    "painted over the relevant chart region using annotation bboxes."
                ),
                "chart_edit_summary": f"Programmatic {_scheduled_error_type} via chart_operators.py",
                "self_check": {
                    "dominant_mechanism_only": True,
                    "still_answerable": True,
                    "faithful_to_metadata": True,
                    "misleading_not_factually_broken": True,
                },
            }
            logger.info(
                "[%s] R%d using programmatic operator '%s' (skipping LLM Reverse Agent).",
                sample_id, round_num, _scheduled_error_type,
            )

            # VLM semantic check — verify the operator produced a valid chart
            _prog_vlm = vlm_validator.check_image(
                client=judge_client or client,
                attacked_chart_path=attacked_chart_path,
                error_type=_scheduled_error_type,
                source_chart_path=source_chart_path,
            )
            if not _prog_vlm.passed:
                logger.info(
                    "[%s] R%d VLM semantic check failed for programmatic operator: %s",
                    sample_id, round_num, _prog_vlm.reason,
                )
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    attack_plan=_prog_attack_plan,
                    matplotlib_code=None,
                    attack_outcome={
                        "succeeded": False,
                        "failure_reason": f"VLM semantic check failed: {_prog_vlm.reason}",
                    },
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                round_num += 1
                continue

            # Jump directly to Forward Agent evaluation
            _prog_forward_trace: dict | None = None
            _prog_forward_error: str | None = None
            try:
                _prog_forward_trace, _prog_transient_err = _call_with_transient_retries(
                    sample_id,
                    f"R{round_num} Forward Agent (programmatic)",
                    forward_agent.analyze,
                    client,
                    attacked_chart_path,
                    attack_question,
                    attack_options,
                    attack_gold_answer,
                )
                if _prog_transient_err is not None:
                    raise _prog_transient_err
            except Exception as exc:
                _prog_forward_error = traceback.format_exc()
                logger.error("[%s] R%d Forward Agent failed on programmatic chart: %s", sample_id, round_num, exc)

            if _prog_forward_error or _prog_forward_trace is None:
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    attack_plan=_prog_attack_plan,
                    matplotlib_code=None,
                    attack_outcome={"succeeded": False, "failure_reason": f"Forward Agent error: {_prog_forward_error}"},
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                round_num += 1
                continue

            _prog_predicted = _prog_forward_trace.get("predicted_answer", "")
            _prog_effect = _assess_attack_effect(
                clean_trace=clean_trace,
                attacked_trace=_prog_forward_trace,
                gold_answer=attack_gold_answer,
                success_policy=state["success_policy"],
            )
            _prog_attack_plan["target_wrong_option"] = _prog_predicted if _prog_effect["hard_success"] else None

            if _prog_effect["effective_success"]:
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    forward_trace=_prog_forward_trace,
                    attack_plan=_prog_attack_plan,
                    matplotlib_code=None,
                    attack_outcome={
                        "succeeded": True,
                        "failure_reason": None,
                        "success_type": _prog_effect["success_type"],
                        "confidence_drop": _prog_effect["confidence_drop"],
                    },
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                state["final_success"] = True
                state["success_type"] = _prog_effect["success_type"]
                state["final_round"] = round_num
                state["dominant_error_type"] = _scheduled_error_type
                state["attacked_stage"] = _prog_attack_plan["target_stage"]
                state["final_forward_answer"] = _prog_predicted
                state["final_forward_confidence"] = _prog_effect["final_confidence"]
                state["confidence_drop"] = _prog_effect["confidence_drop"]
                state["why_succeeded_or_failed"] = (
                    f"Round {round_num} programmatic hard-success. "
                    f"Operator '{_scheduled_error_type}' caused answer '{_prog_predicted}' (gold '{attack_gold_answer}')."
                )
                judge_result = _maybe_llm_judge_success(client, state, round_record, judge_client=judge_client)
                state["llm_judge_audit"] = judge_result
                _write_json(output_dir / "successful" / f"{sample_id}.json", state)
                compact_record = _export_success_artifacts(output_dir, state, round_record)
                _export_reviewed_success_artifacts(
                    output_dir, compact_record, round_record["current_chart_path"], judge_result
                )
                logger.info("[%s] PROGRAMMATIC SUCCESS at round %d. Wrong answer: %s", sample_id, round_num, _prog_predicted)
                return state
            else:
                # Programmatic operator did not fool the Forward Agent — fall through to LLM
                logger.info(
                    "[%s] R%d Programmatic operator did not fool Forward Agent (%s). Falling back to LLM.",
                    sample_id, round_num, _prog_predicted,
                )
                # Use the programmatic image as the new reference for the LLM
                current_chart_reference_path = attacked_chart_path
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    forward_trace=_prog_forward_trace,
                    attack_plan=_prog_attack_plan,
                    attack_outcome={"succeeded": False, "failure_reason": "Programmatic operator did not flip answer."},
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                round_num += 1
                continue

        # ----------------------------------------------------------------
        # Reverse Agent: plan and generate attack
        # ----------------------------------------------------------------
        while True:
            attack_plan: dict | None = None
            matplotlib_code: str | None = None
            reverse_error: str | None = None

            try:
                result, transient_reverse_error = _call_with_transient_retries(
                    sample_id,
                    f"R{round_num} Reverse Agent",
                    reverse_agent.generate_attack,
                    client=client,
                    forward_trace=current_forward_trace,
                    question=attack_question,
                    options=attack_options,
                    gold_answer=attack_gold_answer,
                    output_chart_path=attacked_chart_path,
                    round_num=round_num,
                    definitions_text=definitions_text,
                    failure_explanation=prev_failure_explanation,
                    prev_attack_plan=prev_attack_plan,
                    attack_preferences=attack_preferences,
                    task_mode=task_mode,
                    error_profile=error_profile,
                    reference_chart_path=current_chart_reference_path,
                    source_data_table=source_data_table,
                    source_annotation=source_annotation,
                )
                if transient_reverse_error is not None:
                    raise transient_reverse_error
                attack_plan, matplotlib_code = result
                logger.info(
                    "[%s] R%d Reverse Agent chose: %s (target %s → wrong-option %s via %s)",
                    sample_id,
                    round_num,
                    attack_plan.get("target_error_type"),
                    attack_plan.get("target_stage"),
                    attack_plan.get("target_wrong_option") or attack_plan.get("expected_wrong_option"),
                    attack_plan.get("tactic_family"),
                )
            except Exception as exc:
                reverse_error = traceback.format_exc()
                if _is_transient_llm_error(exc) and service_restarts < MAX_SERVICE_RESTARTS_PER_ROUND:
                    service_restarts += 1
                    sleep_s = TRANSIENT_BACKOFF_SEC * (2**service_restarts)
                    logger.warning(
                        "[%s] R%d Reverse Agent exhausted transient retries. "
                        "Restarting same round without consuming budget (%d/%d). Sleeping %.1fs.",
                        sample_id,
                        round_num,
                        service_restarts,
                        MAX_SERVICE_RESTARTS_PER_ROUND,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
                    continue
                logger.error(
                    "[%s] R%d Reverse Agent failed: %s", sample_id, round_num, exc
                )

            if reverse_error or attack_plan is None:
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    attack_plan=attack_plan,
                    matplotlib_code=matplotlib_code,
                    attack_outcome={"succeeded": False, "failure_reason": reverse_error},
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                round_num += 1
                break

            # ----------------------------------------------------------------
            # VLM semantic validation: verify the generated chart looks valid
            # ----------------------------------------------------------------
            if Path(attacked_chart_path).exists():
                _vlm_check = vlm_validator.check_image(
                    client=judge_client or client,
                    attacked_chart_path=attacked_chart_path,
                    error_type=attack_plan.get("target_error_type", ""),
                    source_chart_path=current_chart_reference_path,
                )
                if not _vlm_check.passed:
                    logger.info(
                        "[%s] R%d VLM semantic check rejected LLM-generated chart: %s",
                        sample_id, round_num, _vlm_check.reason,
                    )
                    round_record = _make_round_record(
                        round_id=round_num,
                        chart_path=attacked_chart_path,
                        attack_plan=attack_plan,
                        matplotlib_code=matplotlib_code,
                        attack_outcome={
                            "succeeded": False,
                            "failure_reason": f"VLM semantic check: {_vlm_check.reason}",
                        },
                    )
                    state["rounds"].append(round_record)
                    _write_jsonl(log_path, round_record)
                    prev_failure_explanation = {
                        "why_attack_failed": f"VLM semantic check rejected the chart: {_vlm_check.reason}",
                        "robust_stage": current_forward_trace.get("susceptible_stage", "Stage 1"),
                        "detected_misleading_cue": "The generated chart did not visually instantiate the intended mechanism.",
                        "decisive_corrective_evidence": _vlm_check.reason,
                        "suggested_more_dangerous_attack": (
                            "Ensure the misleading mechanism is visually prominent and data marks remain visible."
                        ),
                    }
                    prev_attack_plan = attack_plan
                    round_num += 1
                    break

            # ----------------------------------------------------------------
            # Policy validation: reject factually broken or metadata-breaking attacks
            # ----------------------------------------------------------------
            validation = validator.validate_attack_plan(
                attack_plan,
                matplotlib_code,
                question=attack_question,
                options=attack_options,
                gold_answer=attack_gold_answer,
                task_mode=task_mode,
                error_profile=error_profile,
                prev_attack_plan=prev_attack_plan,
                source_chart_path=current_chart_reference_path,
                source_chart_type=source_chart_type,
            )
            if not validation.is_valid:
                logger.info(
                    "[%s] R%d Attack rejected by validator: %s",
                    sample_id,
                    round_num,
                    validation.reason,
                )
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    attack_plan=attack_plan,
                    matplotlib_code=matplotlib_code,
                    attack_outcome={
                        "succeeded": False,
                        "failure_reason": f"Invalid attack: {validation.reason}",
                    },
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                prev_failure_explanation = {
                    "why_attack_failed": validation.reason,
                    "robust_stage": current_forward_trace.get("susceptible_stage", "Stage 1"),
                    "detected_misleading_cue": "Validator rejected the attack before evaluation.",
                    "decisive_corrective_evidence": "The proposed manipulation violated the strict misleading-but-recoverable policy.",
                    "suggested_more_dangerous_attack": (
                        "Use a recoverable distortion that preserves data and metadata fidelity."
                    ),
                }
                prev_attack_plan = attack_plan
                round_num += 1
                break

            # ----------------------------------------------------------------
            # Forward Agent: analyse the attacked chart
            # ----------------------------------------------------------------
            forward_trace_attacked: dict | None = None
            forward_error: str | None = None

            try:
                forward_trace_attacked, transient_forward_error = _call_with_transient_retries(
                    sample_id,
                    f"R{round_num} Forward Agent on attacked chart",
                    forward_agent.analyze,
                    client,
                    attacked_chart_path,
                    attack_question,
                    attack_options,
                    attack_gold_answer,
                )
                if transient_forward_error is not None:
                    raise transient_forward_error
                logger.info(
                    "[%s] R%d Forward Agent answered: %s (gold: %s, confidence: %s)",
                    sample_id,
                    round_num,
                    forward_trace_attacked.get("predicted_answer"),
                    attack_gold_answer,
                    forward_trace_attacked.get("confidence"),
                )
            except Exception as exc:
                forward_error = traceback.format_exc()
                if _is_transient_llm_error(exc) and service_restarts < MAX_SERVICE_RESTARTS_PER_ROUND:
                    service_restarts += 1
                    sleep_s = TRANSIENT_BACKOFF_SEC * (2**service_restarts)
                    logger.warning(
                        "[%s] R%d Forward Agent exhausted transient retries. "
                        "Restarting same round without consuming budget (%d/%d). Sleeping %.1fs.",
                        sample_id,
                        round_num,
                        service_restarts,
                        MAX_SERVICE_RESTARTS_PER_ROUND,
                        sleep_s,
                    )
                    time.sleep(sleep_s)
                    continue
                logger.error(
                    "[%s] R%d Forward Agent failed on attacked chart: %s",
                    sample_id,
                    round_num,
                    exc,
                )

            if forward_error or forward_trace_attacked is None:
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    attack_plan=attack_plan,
                    matplotlib_code=matplotlib_code,
                    attack_outcome={
                        "succeeded": False,
                        "failure_reason": f"Forward Agent error: {forward_error}",
                    },
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)
                round_num += 1
                break

            predicted = forward_trace_attacked.get("predicted_answer", "")
            attack_effect = _assess_attack_effect(
                clean_trace=clean_trace,
                attacked_trace=forward_trace_attacked,
                gold_answer=attack_gold_answer,
                success_policy=state["success_policy"],
            )
            attack_succeeded = attack_effect["effective_success"]

            # ----------------------------------------------------------------
            # Evaluate success
            # ----------------------------------------------------------------
            if attack_succeeded:
                attack_outcome = {
                    "succeeded": True,
                    "failure_reason": None,
                    "success_type": attack_effect["success_type"],
                    "confidence_drop": attack_effect["confidence_drop"],
                    "clean_confidence": attack_effect["clean_confidence"],
                    "final_confidence": attack_effect["final_confidence"],
                }
                round_record = _make_round_record(
                    round_id=round_num,
                    chart_path=attacked_chart_path,
                    forward_trace=forward_trace_attacked,
                    attack_plan=attack_plan,
                    matplotlib_code=matplotlib_code,
                    attack_outcome=attack_outcome,
                )
                state["rounds"].append(round_record)
                _write_jsonl(log_path, round_record)

                # Fill final summary
                state["final_success"] = True
                state["success_type"] = attack_effect["success_type"]
                state["final_round"] = round_num
                state["dominant_error_type"] = attack_plan.get("target_error_type")
                state["attacked_stage"] = attack_plan.get("target_stage")
                state["final_forward_answer"] = predicted
                state["final_forward_confidence"] = attack_effect["final_confidence"]
                state["confidence_drop"] = attack_effect["confidence_drop"]

                if attack_effect["hard_success"]:
                    state["why_succeeded_or_failed"] = (
                        f"Round {round_num} hard-succeeded. "
                        f"Forward Agent chose '{predicted}' instead of gold '{attack_gold_answer}'. "
                        f"Attack: {attack_plan.get('target_error_type')} on {attack_plan.get('target_stage')}."
                    )
                    judge_result = _maybe_llm_judge_success(client, state, round_record, judge_client=judge_client)
                    state["llm_judge_audit"] = judge_result
                    _write_json(output_dir / "successful" / f"{sample_id}.json", state)
                else:
                    state["why_succeeded_or_failed"] = (
                        f"Round {round_num} soft-succeeded. "
                        f"Forward Agent stayed on gold '{attack_gold_answer}' but confidence dropped "
                        f"from '{attack_effect['clean_confidence']}' to '{attack_effect['final_confidence']}'. "
                        f"Attack: {attack_plan.get('target_error_type')} on {attack_plan.get('target_stage')}."
                    )
                    state["llm_judge_audit"] = None
                    soft_dir = output_dir / "successful_soft"
                    soft_dir.mkdir(parents=True, exist_ok=True)
                    _write_json(soft_dir / f"{sample_id}.json", state)

                compact_record = _export_success_artifacts(output_dir, state, round_record)
                if attack_effect["hard_success"]:
                    _export_reviewed_success_artifacts(
                        output_dir,
                        compact_record,
                        round_record["current_chart_path"],
                        state.get("llm_judge_audit"),
                    )
                    logger.info(
                        "[%s] HARD SUCCESS at round %d. Wrong answer: %s", sample_id, round_num, predicted
                    )
                else:
                    logger.info(
                        "[%s] SOFT SUCCESS at round %d. Confidence dropped %s -> %s.",
                        sample_id,
                        round_num,
                        attack_effect["clean_confidence"],
                        attack_effect["final_confidence"],
                    )
                return state

            # ----------------------------------------------------------------
            # Attack failed — get failure explanation for next round
            # ----------------------------------------------------------------
            logger.info(
                "[%s] R%d Attack failed. Forward Agent still correct (%s). "
                "Requesting failure explanation.",
                sample_id,
                round_num,
                predicted,
            )

            failure_explanation: dict | None = None
            try:
                failure_explanation, transient_explain_error = _call_with_transient_retries(
                    sample_id,
                    f"R{round_num} Failure explanation",
                    forward_agent.explain_failure,
                    client,
                    attacked_chart_path,
                    attack_question,
                    attack_options,
                    attack_gold_answer,
                    forward_trace_attacked,
                )
                if transient_explain_error is not None:
                    raise transient_explain_error
            except Exception as exc:
                logger.warning(
                    "[%s] R%d Could not get failure explanation: %s",
                    sample_id,
                    round_num,
                    exc,
                )

            attack_outcome = {
                "succeeded": False,
                "failure_reason": (
                    failure_explanation.get("why_attack_failed", "Unknown")
                    if failure_explanation
                    else "Could not obtain failure explanation"
                ),
            }
            round_record = _make_round_record(
                round_id=round_num,
                chart_path=attacked_chart_path,
                forward_trace=forward_trace_attacked,
                attack_plan=attack_plan,
                matplotlib_code=matplotlib_code,
                attack_outcome=attack_outcome,
                failure_explanation=failure_explanation,
            )
            state["rounds"].append(round_record)
            _write_jsonl(log_path, round_record)

            early_stop_reason = _early_stop_reason(state["rounds"], max_rounds=max_rounds)
            if early_stop_reason is not None and round_num < max_rounds:
                state["final_success"] = False
                state["final_round"] = round_num
                state["dominant_error_type"] = attack_plan.get("target_error_type")
                state["attacked_stage"] = attack_plan.get("target_stage")
                state["final_forward_answer"] = predicted
                state["final_forward_confidence"] = forward_trace_attacked.get("confidence")
                state["why_succeeded_or_failed"] = early_stop_reason
                _write_json(output_dir / "failed" / f"{sample_id}.json", state)
                logger.info(
                    "[%s] EARLY STOP after round %d / %d. Final answer: %s",
                    sample_id,
                    round_num,
                    max_rounds,
                    predicted,
                )
                return state

            # Update for the next round
            current_forward_trace = forward_trace_attacked
            prev_failure_explanation = failure_explanation
            prev_attack_plan = attack_plan
            current_chart_reference_path = attacked_chart_path
            round_num += 1
            break

    # ------------------------------------------------------------------
    # All rounds exhausted without success
    # ------------------------------------------------------------------
    last_forward = state["rounds"][-1].get("forward_trace") if state["rounds"] else None
    final_answer = last_forward.get("predicted_answer") if last_forward else None

    last_round_plan = state["rounds"][-1].get("attack_plan") if state["rounds"] else None

    state["final_success"] = False
    state["final_round"] = min(round_num - 1, max_rounds)
    state["dominant_error_type"] = (
        last_round_plan.get("target_error_type") if last_round_plan else None
    )
    state["attacked_stage"] = (
        last_round_plan.get("target_stage") if last_round_plan else None
    )
    state["final_forward_answer"] = final_answer
    state["final_forward_confidence"] = last_forward.get("confidence") if last_forward else None
    state["why_succeeded_or_failed"] = (
        f"Failed after {max_rounds} rounds. "
        f"Forward Agent did not reach the configured success policy '{state['success_policy']}' "
        f"and ended on answer ({final_answer} = gold {attack_gold_answer}) with confidence "
        f"'{state['final_forward_confidence']}'. "
        f"Last attack: {state['dominant_error_type']} on {state['attacked_stage']}."
    )

    _write_json(output_dir / "failed" / f"{sample_id}.json", state)
    logger.info(
        "[%s] FAILED after %d rounds. Forward Agent final answer: %s",
        sample_id,
        max_rounds,
        final_answer,
    )
    return state
