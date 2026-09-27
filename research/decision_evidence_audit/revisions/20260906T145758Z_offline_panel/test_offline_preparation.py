"""Read-only tests for prepared artifacts; no model, browser, runner imports."""
import json
import unittest
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(path):
    return json.loads(path.read_text())


class OfflinePreparationTests(unittest.TestCase):
    def test_historical_rules_and_raw_labels(self):
        audit = read(HERE / "raw_failure_audit.json")
        rule = "Choose Route B when the large dashboard rectangle is magenta; choose Route A when it is orange."
        system = audit["cases"][0]["exchanges"][0]["request"]["system_prompt"]
        self.assertEqual(len(audit["cases"]), 6)
        for case in audit["cases"]:
            policy = case["recorded_result"]["policy"]
            self.assertEqual(case["exchanges"][-1]["parsed"]["option_label"], policy["recommended_option"])
            for exchange in case["exchanges"]:
                req = exchange["request"]
                self.assertEqual(req["system_prompt"], system)
                self.assertEqual(req["public_context"]["user_goal"], rule)
                self.assertIn(json.dumps(req["public_context"], ensure_ascii=False), req["user_prompt"])
                self.assertTrue(all(im["center_rgb"] == [255, 0, 255] for im in exchange["images"]))
                vision = exchange["response"].get("metadata", {}).get("vision_input")
                if vision:
                    self.assertEqual(vision["image_count"], len(exchange["images"]))
                    self.assertEqual(vision["original_image_sizes"], [im["size"] for im in exchange["images"]])

    def test_panel_factors_and_counts(self):
        panel = read(HERE / "control_panel.json")
        self.assertEqual(len(panel["units"]), 24)
        states = panel["states"]
        factors = {(s["fixture_color"], s["public_mapping"]["magenta"], s["initial_correct"]) for s in states}
        self.assertEqual(len(factors), 8)
        self.assertEqual(sum(s["visible_options"][0] == "Route A" for s in states), 4)
        self.assertEqual(sum(s["expected_option_offline_only"] == s["visible_options"][0] for s in states), 4)
        self.assertEqual(sum(s["initial_selection"] == s["visible_options"][0] for s in states), 4)
        self.assertTrue(all(u["status"] == "not_run_awaiting_explicit_authorization" for u in panel["units"]))
        order = panel["execution_state_order"]
        self.assertEqual(set(order), {s["state_id"] for s in states})
        scheduled = [next(s for s in states if s["state_id"] == state_id) for state_id in order]
        self.assertTrue(all(a["fixture_color"] != b["fixture_color"] for a, b in zip(scheduled, scheduled[1:])))
        for block in (scheduled[:4], scheduled[4:]):
            self.assertEqual(sum(s["initial_correct"] for s in block), 2)
            self.assertEqual(sum(s["public_mapping"]["magenta"] == "Route A" for s in block), 2)

    def test_selection_blinding_and_pixel_parity(self):
        online = read(HERE / "panel_online_requests.json")
        hidden = [u["model_payload"] for u in online if u["mode"] == "independent_hidden_selection"]
        for index in range(0, 8, 2):
            self.assertEqual(hidden[index], hidden[index + 1])
        for state_id in {u["state_id"] for u in online}:
            payloads = [u["model_payload"] for u in online if u["state_id"] == state_id]
            self.assertEqual(len(payloads), 3)
            self.assertTrue(all(p["image_artifacts"] == payloads[0]["image_artifacts"] for p in payloads))
            self.assertTrue(all(p["public_context"]["visible_options"] == payloads[0]["public_context"]["visible_options"] for p in payloads))
            for path in payloads[0]["image_artifacts"]:
                with Image.open(HERE / path) as image:
                    self.assertEqual(image.size, (512, 384))

    def test_no_evaluator_keys_in_online_projection(self):
        for row in read(HERE / "panel_online_requests.json"):
            data = row["model_payload"]
            for key in ("initial_correct", "expected_option_offline_only", "public_mapping", "fixture_color"):
                self.assertNotIn(key, json.dumps(data))
            context = data["public_context"]
            if row["mode"] == "independent_hidden_selection":
                self.assertEqual(context["current_selection"], "")
                self.assertEqual(context["visible_action_prefix"], [])
            if row["mode"] == "B3_with_text_color_fact":
                self.assertNotIn("Route", context["diagnostic_color_fact"])

    def test_b4_final_reasons_match_across_arms(self):
        rows = read(HERE / "raw_failure_audit.json")["env025_b4"]
        self.assertEqual(rows[0]["responses"][-1]["text"], rows[1]["responses"][-1]["text"])
        self.assertIn("average of 380 (February) and 250 (March)", rows[0]["responses"][-1]["text"])

    def test_split_asset_level_not_runnable_claim(self):
        split = read(HERE / "asset_review/proposed_split.json")
        self.assertEqual(len(split["asset_reviewed_primary_candidates"]), 7)
        self.assertEqual(split["actual_shell_render_and_submission_validated"], [])
        self.assertFalse(split["selection_uses_method_outputs"])
        self.assertFalse(set(split["new_development_candidates"]) & set(split["new_diagnostic_candidates"]))
        groups = [set(g["members"]) for g in split["groups"]]
        self.assertTrue(all(not a & b for i, a in enumerate(groups) for b in groups[i + 1:]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
