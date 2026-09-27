"""Generic action-conclusion-only questioning variants for a bounded diagnostic.

V1 receives the historical QUESTIONS_NEW string from the caller unchanged.
V2 changes the search instruction while using exactly the same public context
projection. Neither variant generates a truth verdict or chooses an action.
V3 is a design note only and has no executable request path.

This is intentionally ACTION-conclusion-only, not a lossless representation of
arbitrary C claims. A claim may already contain observations or justification.
Therefore the online projection keeps only an exact public option label and
never forwards the original claim, chain ID, duplicate count, O, B, or notes.
Null-option relational candidates are unsupported here rather than rewritten.
"""

from copy import deepcopy


PUBLIC_FIELDS = ("goal", "state", "history", "options", "pending_proposal")


class ProjectionUnsupported(ValueError):
    """Cannot construct the authorized action-only representation without guessing."""


def build_action_conclusion_context(context):
    """Deep-copy the fixed public actor context plus deduplicated option labels.

    state MUST already be the audited public DOM projection and history actual
    public action/receipt history; this function cannot sanitize a raw task or
    scorer object smuggled into those fields. Unknown top-level fields are not
    forwarded. initial_chains must contain self-contained {C: ...} records from
    the existing initial generator.

    Deduplication is exact, case-sensitive option-label equality in first-seen
    order. Distinct original claims for the same action intentionally collapse:
    this intervention exposes actions, NOT their particular propositions or
    arguments. It does not infer semantic equivalence between different labels.
    Duplicate multiplicity is not sent to the model as a source of authority.
    A null option or a nonpublic label aborts projection; the caller must record
    unsupported and stop this strategy, not have Codex rewrite the conclusion.
    """
    if not isinstance(context, dict):
        raise ProjectionUnsupported("context must be a public context object")
    missing = [key for key in PUBLIC_FIELDS if key not in context]
    if missing:
        raise ProjectionUnsupported("missing audited public fields: " + ", ".join(missing))
    options = context["options"]
    if not isinstance(options, list) or any(not isinstance(option, str) for option in options):
        raise ProjectionUnsupported("options must be exact public option-label strings")
    chains = context.get("initial_chains")
    if not isinstance(chains, list):
        raise ProjectionUnsupported("initial_chains must be the original candidate list")
    conclusions, seen = [], set()
    for chain in chains:
        candidate = chain.get("C") if isinstance(chain, dict) else None
        if not isinstance(candidate, dict):
            raise ProjectionUnsupported("initial candidate lacks a C object")
        option = candidate.get("option_label")
        if option is None:
            raise ProjectionUnsupported("null-option relational candidate: action-only projection unsupported")
        if not isinstance(option, str) or option not in options:
            raise ProjectionUnsupported("candidate option_label is not an exact public option")
        if option not in seen:
            conclusions.append({"option_label": option})
            seen.add(option)
    projected = {key: deepcopy(context[key]) for key in PUBLIC_FIELDS}
    projected["existing_conclusions"] = conclusions
    return projected


V2_OPTIONS_QUESTIONS = """Search for additional concrete task-action conclusions
that the supplied complete page image might support. This is candidate
discovery, not verification, criticism of previous arguments, or action
execution. Existing conclusions are only exact public action labels used to
avoid duplicating the represented choices. They are not correct answers and
provide no observations, rules, justifications, or voting weights.

Use each public option in turn as a tentative search hypothesis: could choosing
this option satisfy the public task under a reading motivated by something
locatable in the image? Re-observe the complete image for the visual cue or
mapping that might make that hypothesis worth exploring. Consider every public
option, including the currently selected one, without presuming that any option
is correct, that the current one is wrong, or that alternatives must be found.
This option-wise search changes where you look for a possible conclusion; it
does not license fabricated evidence or a rule that merely assumes its answer.

Return at most two questions about materially unrepresented action conclusions.
For each, name the exact public option/concrete task-action conclusion and the
visible location or cue to re-examine for its candidate basis. Ask whether that
reading can form an O-B-C candidate; do not answer by evaluating the old chains,
asking only which encoding is authoritative, or declaring one option a winner.
Do not treat an unverified reading assumption as established truth. Unclear
priority alone need not prevent exploring an explicit conditional reading.
Later stages articulate candidates and separately check them.

Do not require one question per option. If no further image-grounded action
conclusion is apparent, or all possibilities you found are already represented,
return questions=[] and briefly state the inspection scope and limitation.
Do not force opposition, support for every option, or a fixed question count.
Do not invent marks, entities, values, public policies, time requirements, or
uniqueness rules. Do not import hidden answers, underlying data, another chart
version, or previous verdicts. Neither printed labels nor customary geometry
has automatic precedence. Use only the provided image and explicit public
goal, state, actual history, options, and pending proposal; the pending proposal
is not an answer key. Return concise checkable questions, not a reasoning trace.

Return only JSON with unique question IDs such as q1 and q2:
{"questions":[{"id":"q1","question":"Could [exact public action / concrete C]
follow under a reading motivated by [locatable image cue]? Can that reading
form an O-B-C candidate?"}],"summary":"what was inspected and remaining limits"}.
Questions are search hypotheses, not observations, verified facts, action
instructions, or proof of complete explanation coverage.
"""


V3_DESIGN_PROPOSAL = """Design only; not an implemented or authorized call path.
An independent search could receive the same full image and only the audited
public goal/state/history/options. It would receive no prior chain, conclusion,
question, verifier verdict, or pending choice used as an explanation reference.
It could propose at most three concrete action conclusions with locatable
visible search cues, explicitly as hypotheses rather than truth judgments.
The caller would then compare exact public option labels against the existing
action-conclusion set offline, retaining differences without consulting gold.
Semantic proposition matching and arbitrary relational conclusions are not
defined by this proposal. If all labels are already covered, no new option
would be claimed. This changes the available context more than V1/V2 and must
be separately frozen and labeled before any execution. No implementation,
API request, JSON schema, or recovery claim for V3 is provided here.
"""


def make_strategy_request(strategy, base_questions_new, context):
    """Return {system, context}; caller supplies unchanged image and output schema.

    V1's system string is byte-for-byte/equality identical to the historical
    prompt supplied by the caller. Do not append a new instruction to V1.
    Both variants share the same action-only context projection. Calling V2
    builds data only; execution/authorization remains the runner's concern.
    """
    if strategy not in ("V1", "V2"):
        raise ValueError("only V1 and V2 are implemented; V3 remains a proposal")
    if not isinstance(base_questions_new, str) or not base_questions_new:
        raise ValueError("the original QUESTIONS_NEW prompt must be supplied")
    projected = build_action_conclusion_context(context)
    return {
        "system": base_questions_new if strategy == "V1" else V2_OPTIONS_QUESTIONS,
        "context": projected,
    }
