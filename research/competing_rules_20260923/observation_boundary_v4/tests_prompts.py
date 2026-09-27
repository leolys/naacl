import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import GENERATOR, VERIFIER, RuleStore, defense_prompts, verify
from prompts_observation_v4 import OBSERVATION_CONTRACT


def test_legacy_is_exact_and_new_profile_is_explicit():
    assert defense_prompts({}) == (GENERATOR, VERIFIER)
    assert defense_prompts({"defense_prompt_profile": "legacy"}) == (GENERATOR, VERIFIER)
    pair = defense_prompts({"defense_prompt_profile": "observation_boundary_v4"})
    assert pair[0] != GENERATOR and pair[1] != VERIFIER
    assert all(OBSERVATION_CONTRACT in prompt for prompt in pair)
    with pytest.raises(ValueError):
        defense_prompts({"defense_prompt_profile": "misspelled"})


def test_no_concrete_case_names_or_preferred_options_in_prompts():
    combined = "\n".join(defense_prompts({"defense_prompt_profile": "observation_boundary_v4"})).lower()
    for token in ("pub013", "health004", "b046", "pub031", "b001", "illinois", "kansas", "delaware",
                  "week 1", "capacity expansion", "married couple", "single women"):
        assert token not in combined
    # This checks literal specialization only, not semantic observation quality.


def test_live_verify_entry_uses_both_selected_prompts(tmp_path):
    seen = []

    class FakeAPI:
        def call(self, folder, phase, system, context, images):
            seen.append((phase, system))
            if phase == "generate":
                return {"rules": [{"id": "r", "text": "Position is interpreted using the visible axis",
                         "component": "axis", "conditions": "same axis"}],
                        "chains": [{"rule_id": "r", "option_label": "Route A", "claim": "route fits",
                         "observations": [{"ref": "chart_1", "location": "axis", "content": "A mark is above another mark"}]}]}
            return {"checks": [{"chain_id": "c1", "O": "supported", "B": "supported", "implication": "supported",
                     "evidence": [{"ref": "chart_1", "location": "axis", "content": "printed ticks"}],
                     "reason": "synthetic structural fixture, not visual evaluation"}],
                    "recommendation": "Route A", "unresolved_reason": ""}

    config = {"defense_prompt_profile": "observation_boundary_v4", "competitors": 2}
    result = verify(FakeAPI(), tmp_path, {"primary_field_label": "Metric"},
                    {"options": ["Route A"], "current_selection": ""}, [], [("chart_1", "mock-image-not-read")],
                    {"action": {"kind": "select", "option": "Route A"}}, RuleStore(), config)
    assert [item[1] for item in seen] == list(defense_prompts(config))
    assert result["recommendation"] == "Route A"
    assert json.loads((tmp_path / "rule_state.json").read_text())[0]["version"] == 1


def test_additional_verification_uses_same_profile():
    source = (ROOT / "run_demo.py").read_text(encoding="utf-8")
    assert '"additional_check", defense_prompts(config)[1]' in source
