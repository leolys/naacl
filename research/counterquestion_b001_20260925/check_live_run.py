"""Verify the archived three wire requests, never send requests or judge gold."""
import base64
import json
from pathlib import Path
import run_diagnostic as d

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"


def main():
    result = d.core.read(RUN / "result.json")
    seed = d.core.read(RUN / "seed_input.json")
    config = d.core.read(HERE / "config.json")
    common = d.core.common_context(seed["task"])
    expected = {
        "counterquestions": {**common, "base_arguments": seed["base_arguments"]},
        "competitors": {**common, "base_arguments": seed["base_arguments"], "counterquestions": result["counterquestions"]},
        "verification": {**common, "arguments": result["normalized"], "public_task_text_paths": d.text_paths(seed["task"])},
    }
    prompts = {"counterquestions": d.QUESTIONER, "competitors": d.COMPETITOR, "verification": d.VERIFICATION}
    for stage, ctx in expected.items():
        folder = RUN / stage / "round_001"
        wire = d.core.read(folder / "request.json")
        manifest = d.core.read(folder / "context.json")
        assert manifest["context"] == ctx
        assert json.loads(wire["messages"][1]["content"][0]["text"]) == ctx
        d.public_inputs.assert_public(ctx)
        assert wire["messages"][0]["content"] == prompts[stage]
        assert wire["model"] == config["model"] and wire["temperature"] == 0 and wire["max_tokens"] == 2600
        parts = wire["messages"][1]["content"]
        images = [p["image_url"]["url"] for p in parts if p["type"] == "image_url"]
        assert len(images) == 1 and base64.b64decode(images[0].split(",", 1)[1]) == (RUN / "chart.jpeg").read_bytes()
        assert result["stages"][stage]["status"] == "completed"
    runtime = d.core.read(RUN / "runtime.json")
    for path, value in runtime["source_sha256"].items():
        assert d.core.digest(path) == value
        frozen = RUN / "runtime_source" / Path(path).relative_to(d.RESEARCH)
        assert d.core.digest(frozen) == value
    assert all(d.core.digest(p) == h for p, h in runtime["seed_sha256"].items())
    attempts = list(RUN.glob("*/round_001/attempt_*.json"))
    budget = d.core.read(RUN / "budget.json")
    assert len(attempts) == budget["request_attempts"] == result["request_attempts"] == 3
    assert len(budget["events"]) == 3 and result["estimated_ledger_usd"] <= 1
    receipt = {"status": "PASS", "actual_requests_checked": 3,
               "same_full_chart_and_public_task": True, "actual_questions_delivered_to_generator": True,
               "verifier_origin_and_questioner_provenance_withheld": True,
               "no_gold_or_old_verifier_fields_in_online_context": True,
               "runtime_and_inherited_seed_unchanged": True,
               "scope": "wire/artifact consistency, not semantic correctness or causal efficacy"}
    d.core.dump(HERE / "live_wire_check.json", receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
