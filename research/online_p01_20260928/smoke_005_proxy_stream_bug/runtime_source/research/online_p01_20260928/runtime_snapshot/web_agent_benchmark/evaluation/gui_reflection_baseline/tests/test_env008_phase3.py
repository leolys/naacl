from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import unittest

from ..env008_phase3_protocol import (
    BLOCK_COMPLETION,
    BLOCK_MEMORY,
    BLOCK_METHOD,
    BLOCK_ROLE,
    MEMORY_TEXTS,
    METHOD_CURRENT_ONLY,
    METHOD_OFFICIAL,
    METHOD_PREMISE,
    ROLE_CONFIGS,
    memory_protocol_audit,
    phase3_cells,
)
from ..env008_role_counterfactual import (
    ENTITY_TO_ACTION_ID,
    RoleCounterfactualScorer,
    _role_map,
    _validate_variant_semantics,
    _variant_rows,
    balance_audit,
    bind_role_case,
)
from ..env008_phase3_protocol import LAYOUT_BY_CARD_VECTOR
from ..premise_controller import (
    PremiseControllerError,
    evidence_prompt,
    frozen_prompt_manifest,
    parse_evidence_dependency,
    parse_stage_action,
)
from ..run_env008_phase3 import (
    _behavior_summary,
    _posthoc_controller_binding_audit,
)
from ..targeted_recovery import F3_PRE_REATTEMPT_CONTRADICTION


ROOT = Path(__file__).resolve().parents[4]
CANONICAL = ROOT / (
    "web_agent_benchmark/evaluation/gui_reflection_baseline/runs/phase2_formal/"
    "20260831T095625Z_797a0392/canonical_case.json"
)
MANIFEST = ROOT / (
    "web_agent_benchmark/evaluation/gui_reflection_baseline/assets/"
    "env008_role_counterfactual_v1/manifest.json"
)


class Env008Phase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))

    def test_frozen_matrix_has_50_with_core_block_counts(self) -> None:
        cells = phase3_cells()
        self.assertEqual(len(cells), 50)
        self.assertEqual(len({cell.key for cell in cells}), 50)
        self.assertEqual(
            Counter(cell.block_id for cell in cells),
            {
                BLOCK_MEMORY: 8,
                BLOCK_METHOD: 6,
                BLOCK_ROLE: 24,
                BLOCK_COMPLETION: 12,
            },
        )
        method_cells = [cell for cell in cells if cell.block_id == BLOCK_METHOD]
        self.assertEqual({cell.feedback_spec_id for cell in method_cells}, {F3_PRE_REATTEMPT_CONTRADICTION})
        self.assertEqual(
            {cell.method_id for cell in method_cells},
            {METHOD_CURRENT_ONLY, METHOD_OFFICIAL, METHOD_PREMISE},
        )

    def test_memory_entries_are_balanced_and_answer_nonrevealing(self) -> None:
        audit = memory_protocol_audit()
        self.assertTrue(audit["passed"])
        nonempty = [value for value in MEMORY_TEXTS.values() if value is not None]
        self.assertEqual(len(nonempty), 3)
        self.assertTrue(all(value.count("Wind") == 1 for value in nonempty))
        self.assertTrue(all("Solar" not in value for value in nonempty))

    def test_role_orthogonal_array_is_pairwise_balanced(self) -> None:
        audit = balance_audit()
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["row_count"], 18)
        self.assertEqual(len(audit["pair_counts"]), 10)
        for counts in audit["pair_counts"].values():
            self.assertEqual(len(counts), 9)
            self.assertEqual(set(counts.values()), {2})
        self.assertTrue(audit["heuristic_sequences_distinct"])

    def test_role_case_uses_visible_and_hidden_role_neutral_actions(self) -> None:
        config = next(row for row in ROLE_CONFIGS if row["config_id"] == "r2")
        case, _record = bind_role_case(
            self.canonical,
            manifest_path=MANIFEST,
            role_config_id="r2",
            layout_id="cyclic_shift_2",
        )
        labels = [card["label"] for card in case["model_visible_shared"]["action_cards"]]
        self.assertTrue(all(label.startswith("Route ") for label in labels))
        action_ids = case["runner_only"]["choice_token_to_action_id"]
        self.assertEqual(set(action_ids.values()), set(ENTITY_TO_ACTION_ID.values()))
        self.assertTrue(
            all(
                not value.startswith(("correct_", "misleading_", "neutral_"))
                for value in action_ids.values()
            )
        )
        self.assertEqual(config["R"], "120")

    def test_role_scorer_recomputes_non_solar_truth_from_variant_source(self) -> None:
        scorer = RoleCounterfactualScorer(
            self.canonical,
            manifest_path=MANIFEST,
            role_config_id="r2",
            layout_id="cyclic_shift_2",
        )
        self.assertEqual(scorer.expected_entity, "Hydroelectric")
        case = scorer.case
        token = "choice_2"
        display = [
            card["choice_token"] for card in case["model_visible_shared"]["action_cards"]
        ]
        result = scorer.score(
            submission_id="test",
            pair_group_id=case["pair_group_id"],
            task_instance_id=case["arms"]["official"]["task_instance_id"],
            arm="official",
            choice_token=token,
            control_position=display.index(token),
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["expected_entity_recomputed"], "Hydroelectric")

    def test_role_manifest_semantics_bind_each_frozen_vector(self) -> None:
        config = next(row for row in ROLE_CONFIGS if row["config_id"] == "r2")
        roles = _role_map(config)
        record = {
            "variant_id": "r2",
            "role_config_id": "r2",
            "vectors": {name: config[name] for name in ("R", "X", "P", "C")},
            "layout_id": LAYOUT_BY_CARD_VECTOR[config["P"]],
            "roles_by_entity_declaration": roles,
            "correct_entity_declaration": next(
                entity for entity, role in roles.items() if role == "correct"
            ),
            "misleading_entity_declaration": next(
                entity for entity, role in roles.items() if role == "misleading"
            ),
            "neutral_entity_declaration": next(
                entity
                for entity, role in roles.items()
                if role == "neutral_or_irrelevant"
            ),
        }
        rows = _variant_rows(config)
        _validate_variant_semantics(record, config, rows)
        bad_record = json.loads(json.dumps(record))
        bad_record["vectors"]["X"] = "210"
        with self.assertRaises(ValueError):
            _validate_variant_semantics(bad_record, config, rows)
        bad_rows = json.loads(json.dumps(rows))
        bad_rows[0], bad_rows[1] = bad_rows[1], bad_rows[0]
        with self.assertRaises(ValueError):
            _validate_variant_semantics(record, config, bad_rows)
        bad_rows = json.loads(json.dumps(rows))
        bad_rows[0]["color"] = "#000000"
        with self.assertRaises(ValueError):
            _validate_variant_semantics(record, config, bad_rows)

    def test_completion_histories_are_equal_length_by_spec(self) -> None:
        cells = [cell for cell in phase3_cells() if cell.block_id == BLOCK_COMPLETION]
        self.assertEqual(
            {cell.completion_history for cell in cells},
            {"H0_empty", "H2_recent_selection", "H2_revision_chain"},
        )
        self.assertTrue(all(cell.max_backbone_calls == 1 for cell in cells))

    def test_controller_argmax_is_generic_and_model_evidence_owned(self) -> None:
        raw = (
            'EVIDENCE_JSON: {"records":['
            '{"entity":"Alpha","printed_value":"12.0%","unit":"%","evidence_region":"left label"},'
            '{"entity":"Beta","printed_value":19.5,"unit":"%","evidence_region":"middle label"}]}'
            "\n<ACTION>: PRESS_BACK"
        )
        dependency = parse_evidence_dependency(raw)
        self.assertEqual(dependency.selected_entity, "Beta")
        self.assertEqual(dependency.operation, "argmax(extracted.printed_value)")
        self.assertEqual(len(dependency.dependency_sha256), 64)
        with self.assertRaises(PremiseControllerError):
            parse_evidence_dependency(
                'EVIDENCE_JSON: {"records":['
                '{"entity":"A","printed_value":2,"unit":"%","evidence_region":"x"},'
                '{"entity":"B","printed_value":2,"unit":"%","evidence_region":"y"}]}'
            )

    def test_controller_frozen_templates_contain_no_env008_answer(self) -> None:
        manifest = frozen_prompt_manifest()
        text = "\n".join(manifest["templates"].values())
        for fragment in ("Solar", "Wind", "Hydroelectric", "41.2", "29.8", "18.5"):
            self.assertNotIn(fragment, text)
        prompt = evidence_prompt("Route the source with the largest reported contribution.")
        self.assertEqual(prompt.count("<image>"), 1)

    def test_controller_action_requires_strict_field_and_official_agreement(self) -> None:
        raw = "<THOUGHT>: revise\n<ACTION>: PRESS_BACK"
        action = parse_stage_action(
            raw,
            {"action_type": "PRESS_BACK", "parameters": []},
            1280,
            960,
        )
        self.assertEqual(action.action_type, "PRESS_BACK")
        invalid = (
            ("I should PRESS_BACK.", {"action_type": "PRESS_BACK", "parameters": []}),
            (
                "<ACTION>: PRESS_BACK CLICK[[500, 500]]",
                {"action_type": "PRESS_BACK", "parameters": []},
            ),
            (
                "I considered PRESS_BACK.\n<ACTION>: CLICK[[500, 500]]",
                {"action_type": "PRESS_BACK", "parameters": []},
            ),
        )
        for output, official in invalid:
            with self.subTest(output=output), self.assertRaises(PremiseControllerError):
                parse_stage_action(output, official, 1280, 960)

    def test_controller_binding_is_posthoc_and_gates_method_attribution(self) -> None:
        raw_steps = [
            {
                "controller_stage": "evidence_and_reversal",
                "official_action_parsed": {"action_type": "PRESS_BACK"},
                "ui_receipts": [
                    {
                        "kind": "browser_back",
                        "from_state": "review",
                        "to_state": "retry_decision",
                    }
                ],
            },
            {
                "controller_stage": "target_action_binding",
                "dependency_target_entity": "Wind",
                "ui_receipts": [
                    {
                        "kind": "selection",
                        "choice_token": "choice_0",
                        "from_state": "retry_decision",
                    }
                ],
            },
            {
                "controller_stage": "submission_check",
                "dependency_target_entity": "Wind",
                "ui_receipts": [
                    {"kind": "submission", "choice_token": "choice_0"}
                ],
            },
        ]
        audit = _posthoc_controller_binding_audit(
            raw_steps, {"choice_0": "Solar", "choice_1": "Wind"}
        )
        self.assertIs(audit["used_for_controller_stage_control"], False)
        self.assertIs(audit["controller_chain_consistent"], False)
        spec = next(
            cell
            for cell in phase3_cells()
            if cell.block_id == BLOCK_METHOD and cell.method_id == METHOD_PREMISE
        )
        ui = [
            {
                "kind": "browser_back",
                "from_state": "review",
                "to_state": "retry_decision",
            },
            {
                "kind": "selection",
                "from_state": "retry_decision",
                "selected_entity": "Solar",
            },
            {"kind": "submission", "selected_entity": "Solar"},
        ]
        behavior = _behavior_summary(
            spec=spec,
            expected_entity="Solar",
            action_ids={"Solar": "route_solar_priority"},
            ui_receipts=ui,
            raw_steps=raw_steps,
            scorer_rows=[{"success": True}],
            controller_binding_audit=audit,
        )
        self.assertIs(behavior["task_level_recovery"], True)
        self.assertIs(behavior["controller_chain_consistent"], False)
        self.assertIs(behavior["full_recovery"], False)


if __name__ == "__main__":
    unittest.main()
