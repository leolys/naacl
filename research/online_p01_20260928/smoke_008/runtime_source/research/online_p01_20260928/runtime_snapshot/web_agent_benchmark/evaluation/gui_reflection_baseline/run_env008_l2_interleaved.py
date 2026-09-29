#!/usr/bin/env python3
"""Run the predeclared interleaved env008 L2 F1/F3_pre mechanism panel."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from .agent_runtime import AgentClient, HttpAgentClient, ManagedAgentServer
from .run_inherited_error_pilot import (
    CONTRAST_ID,
    CURRENT_ONLY_CONDITION,
    NATIVE4_CONDITION,
    base_fields_for_cell,
    build_registry,
    condition_records,
    derive_layout_case,
    retry_current_check_reasons,
    retry_current_cross_cell_checks,
    validate_interventions,
)
from .run_targeted_recovery_pilot import (
    EXPECTED_MODEL_PATH,
    EXPECTED_OFFICIAL_REPO,
    RENDERER_BUILD_ID,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    build_browser_factory,
    cross_cell_checks,
    execution_complete,
    load_authoritative_case,
    run_cell,
    verify_health,
    write_json,
)
from .run_travel_pair import verify_agent_service
from .targeted_recovery import (
    F1_CHECKLIST,
    F3_PRE_REATTEMPT_CONTRADICTION,
    STANDARDIZED_MISTAKE,
    analyze_recovery_quartet,
)
from .targeted_recovery_layout import layout_algorithm
from .targeted_recovery_scorer import CanonicalSubmissionScorer
from .targeted_recovery_validator import CanonicalOutcomeValidator


LAYOUT_ID = "cyclic_shift_2"

# Adjacent pairs and within-pair direction are predeclared in the sample spec.
CELL_PLAN = (
    ("official_native_f1", "official", NATIVE4_CONDITION, F1_CHECKLIST),
    (
        "official_native_f3_pre",
        "official",
        NATIVE4_CONDITION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    ),
    ("clean_current_f1", "clean", CURRENT_ONLY_CONDITION, F1_CHECKLIST),
    (
        "clean_current_f3_pre",
        "clean",
        CURRENT_ONLY_CONDITION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    ),
    (
        "official_current_f3_pre",
        "official",
        CURRENT_ONLY_CONDITION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    ),
    ("official_current_f1", "official", CURRENT_ONLY_CONDITION, F1_CHECKLIST),
    (
        "clean_native_f3_pre",
        "clean",
        NATIVE4_CONDITION,
        F3_PRE_REATTEMPT_CONTRADICTION,
    ),
    ("clean_native_f1", "clean", NATIVE4_CONDITION, F1_CHECKLIST),
)


def _quartet_key(arm: str, condition: str) -> str:
    role = "candidate" if condition == NATIVE4_CONDITION else "reference"
    return f"{role}_{arm}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default="smoke17")
    parser.add_argument("--slug", default="env008")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--agent-url")
    parser.add_argument("--official-repo", type=Path, default=EXPECTED_OFFICIAL_REPO)
    parser.add_argument("--model-path", type=Path, default=EXPECTED_MODEL_PATH)
    parser.add_argument(
        "--agent-python", default="/tmp/gui-reflection-model-env/bin/python"
    )
    parser.add_argument("--agent-port", type=int, default=38109)
    parser.add_argument("--agent-startup-timeout", type=float, default=900.0)
    parser.add_argument("--agent-request-timeout", type=float, default=300.0)
    parser.add_argument(
        "--browser-backend",
        choices=("playwright", "selenium-firefox"),
        default="selenium-firefox",
    )
    parser.add_argument("--browser-executable")
    parser.add_argument(
        "--firefox-binary",
        default="/tmp/gui-reflection-firefox/usr/lib/firefox/firefox",
    )
    parser.add_argument(
        "--geckodriver",
        default="/tmp/gui-reflection-firefox/usr/bin/geckodriver",
    )
    parser.add_argument(
        "--firefox-library-path",
        default=(
            "/tmp/gui-reflection-firefox/usr/lib/x86_64-linux-gnu:"
            "/tmp/gui-reflection-firefox/usr/lib/firefox"
        ),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--action-wait-ms", type=int, default=700)
    parser.add_argument("--long-press-ms", type=int, default=800)
    args = parser.parse_args(argv)
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.official_repo.resolve() != EXPECTED_OFFICIAL_REPO:
        raise SystemExit("interleaved panel requires the audited official repository")
    if args.model_path.resolve() != EXPECTED_MODEL_PATH:
        raise SystemExit("interleaved panel requires the audited GUI-Reflection SFT")

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    panel_id = f"{run_stamp}_{uuid.uuid4().hex[:8]}"
    run_dir = (args.output_root / panel_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    canonical_case = load_authoritative_case(task_set=args.task_set, slug=args.slug)
    case = derive_layout_case(canonical_case, LAYOUT_ID)
    registry = build_registry(case, LAYOUT_ID)
    scorer = CanonicalSubmissionScorer(
        task_set=args.task_set, slug=args.slug, layout_id=LAYOUT_ID
    )
    validator = CanonicalOutcomeValidator(
        task_set=args.task_set, slug=args.slug, layout_id=LAYOUT_ID
    )
    trial_id = f"trial:{case['pair_group_id']}:F1-F3-pre:{panel_id}"
    write_json(run_dir / "canonical_case.json", canonical_case)
    write_json(run_dir / "derived_layout_case.json", case)
    write_json(run_dir / "conditions.json", condition_records(LAYOUT_ID))
    write_json(
        run_dir / "run_manifest.json",
        {
            "panel_id": panel_id,
            "trial_id": trial_id,
            "task_set": args.task_set,
            "slug": args.slug,
            "layout_id": LAYOUT_ID,
            "layout_algorithm": layout_algorithm(LAYOUT_ID),
            "recovery_branch": STANDARDIZED_MISTAKE,
            "evidence_levels": [F1_CHECKLIST, F3_PRE_REATTEMPT_CONTRADICTION],
            "cell_order": [key for key, _arm, _condition, _level in CELL_PLAN],
            "pairing_rule": {
                "official_native": "F1_then_F3_pre",
                "clean_current": "F1_then_F3_pre",
                "official_current": "F3_pre_then_F1",
                "clean_native": "F3_pre_then_F1",
            },
            "reset_before_each_agent_handoff": True,
            "contrast_id": CONTRAST_ID,
            "renderer_build_id": RENDERER_BUILD_ID,
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "max_steps": args.max_steps,
            "browser_backend": args.browser_backend,
        },
    )

    managed_agent: ManagedAgentServer | None = None
    try:
        if args.agent_url:
            client: AgentClient = HttpAgentClient(
                args.agent_url, args.agent_request_timeout
            )
        else:
            managed_agent = ManagedAgentServer(
                official_repo=args.official_repo,
                model_path=args.model_path,
                port=args.agent_port,
                log_path=run_dir / "model_server.log",
                python_executable=args.agent_python,
                temporal_len=4,
                startup_timeout_seconds=args.agent_startup_timeout,
                request_timeout_seconds=args.agent_request_timeout,
            )
            client = managed_agent.start()
        health = verify_agent_service(client)  # type: ignore[arg-type]
        verify_health(
            health, official_repo=args.official_repo, model_path=args.model_path
        )
        write_json(run_dir / "agent_health.json", health)
        browser_factory = build_browser_factory(args)
        results_by_level: dict[str, dict[str, dict[str, Any]]] = {
            F1_CHECKLIST: {},
            F3_PRE_REATTEMPT_CONTRADICTION: {},
        }
        quartet_inputs: dict[str, dict[str, dict[str, Any]]] = {
            F1_CHECKLIST: {},
            F3_PRE_REATTEMPT_CONTRADICTION: {},
        }

        for key, arm, condition, evidence_level in CELL_PLAN:
            quartet_key = _quartet_key(arm, condition)
            run_id = (
                f"run:{case['pair_group_id']}:{evidence_level}:"
                f"{panel_id}:{quartet_key}"
            )
            base = base_fields_for_cell(
                case=case,
                trial_id=trial_id,
                run_id=run_id,
                arm=arm,
                condition=condition,
                evidence_level=evidence_level,
                layout_id=LAYOUT_ID,
            )
            result = run_cell(
                case=case,
                registry=registry,
                base_fields=base,
                agent=client,
                scorer=scorer,
                browser_factory=browser_factory,
                cell_dir=run_dir / "cells" / key,
                max_steps=args.max_steps,
                outcome_validator=(
                    validator
                    if evidence_level == F3_PRE_REATTEMPT_CONTRADICTION
                    else None
                ),
                layout_id=LAYOUT_ID,
            )
            results_by_level[evidence_level][quartet_key] = result
            events = [
                json.loads(line)
                for line in Path(result["events_path"])
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            quartet_inputs[evidence_level][quartet_key] = {
                "base_fields": base,
                "events": events,
            }

        blocks: dict[str, Any] = {}
        overall_complete = True
        for evidence_level in (F1_CHECKLIST, F3_PRE_REATTEMPT_CONTRADICTION):
            level_results = results_by_level[evidence_level]
            checks = cross_cell_checks(level_results)
            complete, reasons = execution_complete(level_results, checks)
            retry_checks = retry_current_cross_cell_checks(level_results)
            retry_reasons = retry_current_check_reasons(retry_checks)
            intervention_reasons = validate_interventions(
                level_results,
                evidence_level=evidence_level,
                layout_id=LAYOUT_ID,
            )
            reasons.extend(retry_reasons)
            reasons.extend(intervention_reasons)
            complete = complete and not retry_reasons and not intervention_reasons
            quartet_error: str | None = None
            quartet: dict[str, Any] | None = None
            try:
                quartet = analyze_recovery_quartet(
                    quartet_inputs[evidence_level],
                    contrast_id=CONTRAST_ID,
                    registry=registry,
                ).to_dict()
            except Exception as exc:
                quartet_error = repr(exc)
            if quartet_error is not None:
                complete = False
                reasons.append(f"quartet_error:{quartet_error}")
            blocks[evidence_level] = {
                "execution_complete": complete,
                "execution_incomplete_reasons": reasons,
                "intervention_validation_reasons": intervention_reasons,
                "cross_cell_checks": checks,
                "retry_current_cross_cell_checks": retry_checks,
                "retry_current_validation_reasons": retry_reasons,
                "cell_results": level_results,
                "quartet": quartet,
                "quartet_error": quartet_error,
            }
            overall_complete = overall_complete and complete

        summary = {
            "record_type": "env008_l2_f1_f3_pre_interleaved_panel",
            "panel_id": panel_id,
            "trial_id": trial_id,
            "pair_group_id": case["pair_group_id"],
            "layout_id": LAYOUT_ID,
            "cell_order": [key for key, _arm, _condition, _level in CELL_PLAN],
            "execution_complete": overall_complete,
            "blocks": blocks,
            "interpretation_limits": [
                "F1 and F3_pre are parallel mechanism probes, not a causal ladder",
                "the inherited Wind choice is evaluator-owned, not model initial behavior",
                "history contrast does not identify reflection-training causality",
            ],
        }
        write_json(run_dir / "summary.json", summary)
        print(str(run_dir))
        print(
            json.dumps(
                {
                    "execution_complete": overall_complete,
                    "blocks": {
                        level: {
                            "execution_complete": row["execution_complete"],
                            "reasons": row["execution_incomplete_reasons"],
                        }
                        for level, row in blocks.items()
                    },
                },
                sort_keys=True,
            )
        )
        return 0 if overall_complete else 2
    except Exception as exc:
        write_json(
            run_dir / "failure.json",
            {"error": repr(exc), "type": type(exc).__name__},
        )
        raise
    finally:
        if managed_agent is not None:
            managed_agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
