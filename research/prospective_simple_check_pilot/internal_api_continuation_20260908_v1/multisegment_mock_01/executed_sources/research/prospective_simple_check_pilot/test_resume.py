"""Synthetic browser interruption/resume regression; not benchmark inference."""
import argparse
import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from research.decision_evidence_audit import core, models, runner
from . import panel
from .api_backend import IntranetApiBackend
from .mock_browser import RouteMock
from .resume_panel import PrefixResume, ReissueFirstRequest, carry_budget
from .test_api_retry import SequenceSession, failure, ok
from .test_panel import fixture_manifest
from .test_preparation import config


def unit_replies():
    return [ok(json.dumps(a)) for a in (
        dict(action="click_link", text="Open Dashboard"),
        dict(action="click_link", text="Open Form"),
        dict(action="select_option", select_name="primary_action", option_text="Route A"),
        dict(action="click_button", text="Submit Form"),
        dict(option_label="Route A", reason="Public synthetic task specifies Route A"),
        dict(action="click_button", text="Submit Form"),
        dict(option_label="Route A", reason="Public synthetic task specifies Route A"),
        dict(action="click_button", text="Submit Form"))]


def run(output, browser_path, multisegment=False):
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    panel.snapshot_sources(root)
    old, new = root / "interrupted", root / "continued"
    old.mkdir()
    new.mkdir()
    manifest = fixture_manifest()
    core.write_json(old / "TASK_MANIFEST.json", manifest)
    core.write_json(new / "TASK_MANIFEST.json", manifest)
    chart = root / "blank.png"
    Image.new("RGB", (300, 180), "white").save(chart)
    resolver = lambda row, arm: (row["public_task"], chart)
    prior = core.BudgetLedger(max_model_calls=100, max_browser_transitions=150)
    prior.bind_snapshot(old / "budget.json")
    views = {n: panel.ModelBudget(prior, n, 400) for n in panel.BACKBONES}
    cfg = config()
    cfg.money_cap_usd = "50"
    with patch.dict(os.environ, {"MODEL_API_KEY": "mock-only"}), runner.require_playwright()() as pw:
        br = pw.chromium.launch(headless=True, executable_path=str(browser_path), args=list(runner.BROWSER_LAUNCH_ARGS))
        try:
            failed_api = IntranetApiBackend(cfg, artifact_dir=old / "api_wire",
                session=SequenceSession([unit_replies()[0], failure()]))
            record = {n: models.RecordedModel(b, ledger=views[n]) for n, b in
                      dict(M_small=RouteMock(), M_strong=failed_api).items()}
            first = panel.execute_schedule(br, manifest, record, views, prior, old, resolve_public=resolver)
            failed_api.close()
            assert len(first["prefixes"]) == 2 and sum(r.get("submitted", False) for r in first["rows"]) == 3
            preserved = {str(p): p.read_bytes() for p in old.rglob("*") if p.is_file()}
            resume = PrefixResume(old, manifest)
            assert resume.completed_ordinals == {1} and resume.ordinal == 2
            assert resume.logical_completed == 1 and resume.prior_attempts == 1
            changed = copy.deepcopy(manifest)
            changed["rows"][0]["public_task"]["user_goal"] = "Different task"
            try:
                PrefixResume(old, changed)
            except ValueError:
                pass
            else:
                raise AssertionError("manifest drift accepted")
            ledger = core.BudgetLedger(max_model_calls=100, max_browser_transitions=150)
            carry_budget(ledger, old)
            ledger.bind_snapshot(new / "budget.json")
            views = {n: panel.ModelBudget(ledger, n, 400) for n in panel.BACKBONES}
            cfg.max_retries = 3
            cfg.max_calls = 8 if multisegment else 400
            session = SequenceSession(unit_replies()[1:] + ([failure()] if multisegment else unit_replies()))
            api = IntranetApiBackend(cfg, artifact_dir=new / "api_wire", session=session,
                retry_charge=views["M_strong"].charge_model, sleep=lambda seconds: None)
            guarded = ReissueFirstRequest(api, resume, new)
            record = {n: models.RecordedModel(b, ledger=views[n]) for n, b in
                      dict(M_small=RouteMock(), M_strong=guarded).items()}
            record["M_small"]._ordinal = 8
            record["M_strong"]._ordinal = 2
            result = panel.execute_schedule(br, manifest, record, views, ledger, new,
                                           resolve_public=resolver, resume=resume)
            api.close()
            if multisegment:
                assert (new / "stop.json").is_file()
                assert sum(r.get("submitted", False) for r in result["rows"]) == 9
                preserved.update({str(p): p.read_bytes() for p in new.rglob("*") if p.is_file()})
                third = root / "continued_again"
                third.mkdir()
                core.write_json(third / "TASK_MANIFEST.json", manifest)
                next_resume = PrefixResume(new, manifest)
                assert next_resume.ordinal == 4 and next_resume.prior_attempts == 1
                assert next_resume.rows()[0]["source_directory"] == str(old / "online/unit_01")
                assert next_resume.completed_prefixes()[0]["source_run"] == str(old)
                carry = core.BudgetLedger(max_model_calls=100, max_browser_transitions=150)
                carry_budget(carry, new)
                carry.bind_snapshot(third / "budget.json")
                views = {n: panel.ModelBudget(carry, n, 400) for n in panel.BACKBONES}
                cfg.max_calls = 400
                cfg.enforce_money_cap = False
                cfg.money_cap_usd = None
                cfg.money_limit_waiver_reference = "synthetic test-only owner authorization"
                third_api = IntranetApiBackend(cfg, artifact_dir=third / "api_wire",
                    session=SequenceSession(unit_replies()), retry_charge=views["M_strong"].charge_model)
                guarded = ReissueFirstRequest(third_api, next_resume, third)
                next_models = {n: models.RecordedModel(b, ledger=views[n]) for n, b in
                               dict(M_small=RouteMock(), M_strong=guarded).items()}
                for name, model in next_models.items():
                    model._ordinal = record[name]._ordinal
                result = panel.execute_schedule(br, manifest, next_models, views, carry, third,
                    resolve_public=resolver, resume=next_resume)
                third_api.close()
                assert not (third / "stop.json").exists()
                assert not (third / "online/unit_01").exists() and not (third / "online/unit_02").exists()
                assert json.loads((third / "reissued_request.json").read_text())["serialized_payload_and_image_bytes_equal"]
                ledger = carry
            else:
                assert not (new / "stop.json").exists()
            assert len(result["prefixes"]) == 4 and sum(r.get("submitted", False) for r in result["rows"]) == 12
            assert not (new / "online/unit_01").exists()
            assert all(Path(p).read_bytes() == value for p, value in preserved.items())
            proof = json.loads((new / "online/unit_02/prefix/resume_proof.json").read_text())
            assert proof["original_prompt_equal"] and proof["screenshot_pixels_equal"] and proof["public_state_equal"]
            reissued = json.loads((new / "reissued_request.json").read_text())
            assert reissued["serialized_payload_and_image_bytes_equal"]
            assert len(session.calls) == (8 if multisegment else 15)
            receipt_files = list(root.rglob("server_receipts.jsonl"))
            assert sum(runner.line_count(p) for p in receipt_files) == 12
            core.write_json(root / "result.json", dict(status="passed", scope="nonchart_scripted_resume_only",
                actual_browser_transitions=ledger.browser_transitions, mock_model_attempts=ledger.model_calls,
                actual_localhost_submissions=12, preserved_completed_units=1, reissued_unanswered_request=True,
                resumed_input_equal=True, old_artifacts_unchanged=True, multisegment=multisegment,
                real_api_calls=0, real_model_calls=0))
            print((root / "result.json").read_text())
        finally:
            br.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--multisegment", action="store_true")
    args = parser.parse_args()
    run(args.output, args.browser, args.multisegment)
