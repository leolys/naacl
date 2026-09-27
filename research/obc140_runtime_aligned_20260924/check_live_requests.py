"""Offline check of archived actual requests, distinct from semantic validity."""
import argparse
import base64
import hashlib
import json
from collections import Counter

import runner
from prepare import HERE, read, digest


def check(sanity=False):
    runtime = read(HERE / "run/runtime.json")
    config = read(HERE / "config.json")
    assert read(HERE / "run/config_snapshot.json") == config
    runner.check_config(config)
    for relative, expected in runtime["source_sha256"].items():
        assert digest(HERE.parent / relative) == expected, relative
        assert digest(HERE / "run/runtime_source" / relative) == expected, relative
    catalog = read(HERE / "prepared/catalog.json")
    aliases = set(runner.MOCK_SLUGS) if sanity else {e["task_slug"] for e in catalog["tasks"]}
    paths = sorted((HERE / "run/tasks").glob("*/*/round_*/request.json"))
    actual_slugs, models, verified, errors = set(), Counter(), [], []
    for path in paths:
        slug, phase = path.parents[2].name, path.parents[1].name
        actual_slugs.add(slug)
        if slug not in aliases:
            raise ValueError("Unexpected task actually requested: " + slug)
        record = read(path.parents[2] / "record.json")
        public = read(HERE / "prepared/tasks" / slug / "public.json")
        assert record["public_task"] == public
        request = read(path)
        prompt, context, images = runner.parent.phase_input(phase, record)
        assert request["model"] == "gpt-5.6-terra"
        assert request["temperature"] == 0
        assert request["max_tokens"] == runner.core.read(HERE / "config.json")["phase_max_tokens"][phase]
        assert len(request["messages"]) == 2
        assert request["messages"][0] == {"role": "system", "content": prompt}
        content = request["messages"][1]["content"]
        assert request["messages"][1]["role"] == "user" and len(content) == 3
        assert json.loads(content[0]["text"]) == context
        assert context["task"] == public and context["history"] == [] and context["state"]["current_selection"] == ""
        runner.assert_public(context)
        assert content[1] == {"type": "text", "text": "Observation chart_1"}
        chart = base64.b64decode(content[2]["image_url"]["url"].split(",", 1)[1], validate=True)
        assert hashlib.sha256(chart).hexdigest() == digest(images[0][1])
        assert record["provenance"]["old_results_reused"] is False
        for response_path in sorted(path.parent.glob("response_*.json")):
            body = read(response_path)
            models[str(body.get("model"))] += 1
        verified.append({"task": slug, "phase": phase, "request_file": str(path), "status": record["status"][phase]})
        if record["status"][phase] == "invalid":
            try:
                runner.citation_adapter.validate_stage(phase, record[phase + "_invalid_raw"], record, read(HERE / "config.json"))
            except Exception as error:
                errors.append({"task": slug, "phase": phase, "invalid_reason": str(error),
                               "record_unchanged": True})
    budget = read(HERE / "run/budget.json")
    attempts = list((HERE / "run/tasks").glob("*/*/round_*/attempt_*.json"))
    assert budget["request_attempts"] == len(attempts) == len(budget["events"])
    if sanity:
        assert actual_slugs == aliases and len(paths) == 9
    result = {"engineering_status": "PASS", "scope": "archived wire input fidelity only, not semantic correctness",
        "frozen_source_files_checked": len(runtime["source_sha256"]), "config_snapshot_matches": True,
        "actual_tasks": sorted(actual_slugs), "request_files_checked": len(paths),
        "attempts": len(attempts), "response_models": dict(models), "stages": verified,
        "preserved_invalid_stages": errors, "model_calls_by_this_check": 0,
        "estimated_ledger_usd": budget["estimated_ledger_usd"]}
    output = HERE / ("sanity_request_checks.json" if sanity else "all_request_checks.json")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: result[k] for k in ("engineering_status", "actual_tasks", "request_files_checked", "attempts", "response_models", "preserved_invalid_stages", "estimated_ledger_usd")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanity", action="store_true")
    args = parser.parse_args()
    print(json.dumps(check(args.sanity), ensure_ascii=False))
