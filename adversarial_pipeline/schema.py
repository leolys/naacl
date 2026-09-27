"""
State schema for the adversarial benchmark-construction pipeline.

Follows the shared state schema defined in:
  paper/agentic_benchmark_optimization_prompts.md

All dicts are typed as TypedDict for documentation; runtime usage is plain dict.
"""

from typing import TypedDict, Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# Forward Agent outputs
# ---------------------------------------------------------------------------

class ForwardTrace(TypedDict):
    """Output of Forward Agent after analyzing one chart."""
    stage_1_visual_readout: str
    stage_2_mapping: str
    stage_3_reasoning: str
    stage_4_final_decision: str
    predicted_answer: str             # "A" | "B" | "C" | "D"
    confidence: str                   # "low" | "medium" | "high"
    susceptible_stage: str            # "Stage 1" | "Stage 2" | "Stage 3" | "Stage 4" | "none"
    susceptible_original_layer: str   # "L1" | "L2" | "L3" | "L4" | "none"
    why_susceptible: str


class FailureExplanation(TypedDict):
    """Output of Forward Agent after explaining why an attack failed."""
    why_attack_failed: str
    robust_stage: str                  # "Stage 1" | "Stage 2" | "Stage 3" | "Stage 4"
    detected_misleading_cue: str
    decisive_corrective_evidence: str
    suggested_more_dangerous_attack: str


# ---------------------------------------------------------------------------
# Reverse Agent outputs
# ---------------------------------------------------------------------------

class SelfCheck(TypedDict):
    dominant_mechanism_only: bool
    still_answerable: bool
    faithful_to_metadata: bool
    misleading_not_factually_broken: bool
    possible_secondary_errors: List[str]


class AttackPlan(TypedDict):
    """Output of Reverse Agent: the attack plan JSON."""
    target_stage: str               # "Stage 1" | "Stage 2" | "Stage 3" | "Stage 4"
    target_original_layer: str      # "L1" | "L2" | "L3" | "L4"
    target_error_type: str          # taxonomy label, e.g. "truncatedaxis"
    task_mode: Optional[str]        # "strict_answerable" | "abstention_aware" | "scope_reasoning"
    attack_rationale: str
    category_match_explanation: Optional[str]
    expected_wrong_option: str      # "A" | "B" | "C" | "D"
    chart_edit_summary: str
    implementation_plan: List[str]
    self_check: SelfCheck
    # Optional retry fields (present in rounds > 1)
    revision_mode: Optional[str]            # "strengthen_same_stage" | "shift_stage"
    why_previous_attack_failed: Optional[str]
    why_new_attack_should_work: Optional[str]


class AttackOutcome(TypedDict):
    succeeded: bool
    failure_reason: Optional[str]   # populated if succeeded == False
    success_type: Optional[str]
    confidence_drop: Optional[int]
    clean_confidence: Optional[str]
    final_confidence: Optional[str]


# ---------------------------------------------------------------------------
# Per-round record
# ---------------------------------------------------------------------------

class RoundRecord(TypedDict):
    round_id: int                          # 1 | 2 | 3
    current_chart_path: str               # path to the attacked chart PNG
    forward_trace: Optional[ForwardTrace]  # Forward Agent's analysis of attacked chart
    attack_plan: Optional[AttackPlan]      # Reverse Agent's attack plan
    matplotlib_code: Optional[str]         # code used to generate attacked chart
    attack_outcome: Optional[AttackOutcome]
    failure_explanation: Optional[FailureExplanation]  # only if attack failed


# ---------------------------------------------------------------------------
# Sample-level state (the outer envelope for one sample)
# ---------------------------------------------------------------------------

class SampleState(TypedDict):
    sample_id: str                    # e.g. "VLAT_a_q1"
    source_chart_path: str            # path to clean source PNG
    question: str
    options: Dict[str, str]           # {"A": "...", "B": "...", "C": "...", "D": "..."}
    gold_answer: str                  # "A" | "B" | "C" | "D"
    clean_question: str
    clean_options: Dict[str, str]
    clean_gold_answer: str
    attack_question: str
    attack_options: Dict[str, str]
    attack_gold_answer: str
    vis: str                          # "VLAT_a" | "VLAT_b" | ...
    task_mode: str                    # active task mode for attacked-chart evaluation
    error_profile: Optional[Dict[str, Any]]
    qa_refactor: Optional[Dict[str, Any]]
    clean_forward_trace: Optional[ForwardTrace]  # Forward trace on the clean chart
    clean_forward_answer: Optional[str]
    clean_forward_correct: Optional[bool]
    eligible_for_attack: Optional[bool]
    rounds: List[RoundRecord]
    # Final summary fields
    final_success: bool
    success_type: Optional[str]
    success_policy: Optional[str]
    confidence_drop: Optional[int]
    final_round: int                  # round at which success occurred, or max_rounds
    dominant_error_type: Optional[str]
    attacked_stage: Optional[str]
    final_forward_answer: Optional[str]
    final_forward_confidence: Optional[str]
    why_succeeded_or_failed: Optional[str]


# ---------------------------------------------------------------------------
# Layer mapping constants (for documentation / validation)
# ---------------------------------------------------------------------------

BENCHMARK_LAYERS = {
    "L1": "Visual Perception",
    "L2": "Semantic Mapping",
    "L3": "Visual Reasoning",
    "L4": "Cognitive Logic",
}

OPERATIONAL_STAGES = {
    "Stage 1": "Visual Readout",
    "Stage 2": "Symbol-to-Meaning Mapping",
    "Stage 3": "Quantitative/Relational Reasoning",
    "Stage 4": "Final Interpretation and Narrative Check",
}

STAGE_TO_LAYER = {
    "Stage 1": "L1",
    "Stage 2": "L2",
    "Stage 3": "L3",
    "Stage 4": "L4",
}
