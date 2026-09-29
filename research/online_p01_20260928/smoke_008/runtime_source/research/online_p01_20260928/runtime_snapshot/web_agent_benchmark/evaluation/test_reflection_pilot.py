#!/usr/bin/env python3

from __future__ import annotations

import fcntl
import json
import os
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from web_agent_benchmark.evaluation.reflection_cycle_metrics import (
    analyze_cycles,
    locate_cycles,
)
from web_agent_benchmark.evaluation.reflection_history import (
    HistoryRuntime,
    action_generation_attempt_limit,
    action_signature,
    assert_no_hidden_keys,
    estimate_tokens,
    empty_memory,
    internal_metadata_terms_in,
    output_contract_text,
    sanitize_visible_page_for_pilot,
    semantic_state,
    state_hash,
)
from web_agent_benchmark.evaluation.reflection_aime_identity_guard import (
    install_aime_identity_guard,
)
from web_agent_benchmark.evaluation.run_reflection_history_pilot import (
    CONCURRENCY_INCIDENT_FILENAME,
    MODEL_CONFIGS,
    RUNNER_LOCK_FILENAME,
    acquire_output_root_lock,
    build_gpt_model_scoped_smoke_manifest,
    build_manifest,
    build_smoke_manifest,
    build_sonnet_auxiliary_smoke_manifest,
    classify_effective_interface_error,
    classify_physical_agent_error_evidence,
    classify_stop_rule_interface_error,
    execute_cell,
    first_incomplete_scheduled_cell,
    fresh_attempt_dir,
    is_availability_error,
    is_retryable_interface_error,
    is_stop_rule_interface_error,
    interface_stop_rule_state,
    non_interface_failure_identity_errors,
    probe_deployment,
    prepare_review_provenance,
    prepare_runtime_config,
    prepare_scheduling_deviation,
    read_jsonl,
    reconcile_scheduling_finishes,
    review_provenance_spec,
    runtime_routes,
    run as run_pilot,
    run_process_group,
    scheduled_cells,
    scheduling_deviation_spec,
    sha256_file,
    validate_identity_evidence,
    validate_gpt_model_scoped_gate1,
    validate_selection,
)
from web_agent_benchmark.evaluation.audit_reflection_history_gpt_model_scoped_smoke import (
    audit as audit_gpt_model_scoped_smoke,
)
from web_agent_benchmark.evaluation.analyze_reflection_history_pilot import (
    apply_strict_fail_closed_policy,
    decision,
    schema_cell_diagnostics,
    schema_compliance_summary,
    usage,
    validate_analysis_inputs,
)
from web_agent_benchmark.evaluation.audit_reflection_history_checkpoint import (
    SECRET_PATTERN,
    audit as audit_checkpoint,
    scan_secrets,
)
from web_agent_benchmark.evaluation.audit_reflection_history_model_scoped_smoke import (
    audit as audit_model_scoped_smoke,
)
from web_agent_benchmark.evaluation.audit_reflection_history_stage import (
    SECRET_PATTERNS as STAGE_SECRET_PATTERNS,
    audit as audit_stage,
    audit_identity_events,
    interface_error_threshold,
    raw_action_semantics_match,
    secret_scan as stage_secret_scan,
    valid_frozen_action,
)
from web_agent_benchmark.evaluation.materialize_reflection_history_gpt64_recovery import (
    MATERIALIZATION_RELATIVE_PATH,
    materialize as materialize_gpt64_recovery,
    recovery_inventory,
    stable_prefix_audit as audit_recovery_prefix,
    verify_preserved_inventory,
)
from web_agent_benchmark.evaluation import (
    materialize_reflection_history_false_stop_recovery as false_stop_recovery,
)


def page_state(url: str, selected: str = "", text: str = "Dashboard 2024") -> dict:
    return {
        "url": url,
        "text": text,
        "elements": {
            "links": [{"text": "Open Form", "href": "/task/x/form?task_ref=x"}],
            "buttons": [{"text": "Submit Form", "type": "submit"}],
            "selects": [{
                "name": "primary_action",
                "value": selected.lower(),
                "selected_text": selected,
                "options": [
                    {"value": "a", "text": "A", "selected": selected == "A"},
                    {"value": "b", "text": "B", "selected": selected == "B"},
                ],
            }],
        },
    }


def trace_step(index: int, state_id: str, action_id: str, action: str = "click_link", text: str = "") -> dict:
    return {
        "step": index,
        "pilot_history": {
            "state_hash": state_id,
            "action_signature": action_id,
            "execution_status": "executed",
        },
        "action": {"action": action, "text": text},
    }


@contextmanager
def false_stop_recovery_fixture(
    *,
    invalid_identity: bool = False,
    partial_parent: bool = False,
):
    with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
        root = Path(temporary)
        cell_id = "false-stop-test-cell"
        attempt_relative = (
            Path("cells") / cell_id / "attempt_01"
        )
        attempt_dir = root / attempt_relative
        attempt_dir.mkdir(parents=True)
        (root / "gate_reviews").mkdir()
        cell = {
            "cell_id": cell_id,
            "benchmark": "official",
            "scenario": "public39",
            "slug": "pub032",
            "stratum": "high_oscillation",
            "model": "gpt54",
            "model_id": "gpt-5.4",
            "condition": "no_history",
            "repetition": 1,
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 12345,
            "max_steps": 10,
            "history_token_limit": 3000,
            "condition_order": 1,
        }
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "RECOVERY_CELL_ID",
                cell_id,
            )
        )
        stack.enter_context(
            patch.object(false_stop_recovery, "RECOVERY_SEQUENCE", 1)
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "RECOVERY_ATTEMPT_DIR",
                attempt_relative,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_COMPLETED_AFTER_RECOVERY",
                1,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_MISSING_AFTER_RECOVERY",
                0,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_HTTP_REQUEST_COUNT",
                1,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_INTERFACE_COUNTS",
                {"no_history": 0},
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "FORMAL_ROOT_RELATIVE_PATH",
                Path("test/formal-root"),
            )
        )

        manifest_path = root / "preregistered_cells.jsonl"
        manifest_path.write_text(
            json.dumps(cell) + "\n",
            encoding="utf-8",
        )
        (root / "runtime_routes.json").write_text(
            json.dumps({"test": True}),
            encoding="utf-8",
        )
        scheduling_path = root / "scheduling_deviation.json"
        scheduling_path.write_text(
            json.dumps({"test_schedule": True}),
            encoding="utf-8",
        )
        for name in (
            "runs.jsonl",
            "attempt_manifest.jsonl",
            "checkpoint_manifest.jsonl",
        ):
            (root / name).write_text("", encoding="utf-8")
        start = {
            "event_type": "cell_start",
            "cell_id": cell_id,
            "execution_sequence": 1,
            "started_at": "2026-07-28T00:00:00+00:00",
            "original_condition_order": 1,
            "model_queue": "gpt54",
            "scheduling_deviation_sha256": sha256_file(scheduling_path),
        }
        (root / "scheduling_execution_log.jsonl").write_text(
            json.dumps(start) + "\n",
            encoding="utf-8",
        )
        (root / "missing_cells.jsonl").write_text(
            json.dumps(cell) + "\n",
            encoding="utf-8",
        )
        (root / "run_progress.json").write_text(
            json.dumps({
                "expected_cells": 1,
                "completed_cells": 0,
                "missing_cells": 1,
                "outcome_counts": {},
            }),
            encoding="utf-8",
        )
        (root / "unrelated_preserved.txt").write_text(
            "immutable\n",
            encoding="utf-8",
        )

        deployment = false_stop_recovery.EXPECTED_DEPLOYMENT
        submission = {
            "slug": "pub032",
            "selected_action_id": "misleading-action",
        }
        action_metadata = {
            "identity_validated": True,
            "requested_deployment": deployment,
            "response_model": deployment,
        }
        raw_row = {
            "timestamp": "2026-07-28T00:00:01+00:00",
            "mode": "llm_agent",
            "slug": "pub032",
            "outcome": "misleading_failure",
            "error_attribution": (
                "chart_induced_intermediate_decision_error"
            ),
            "submission": submission,
            "trace": [{
                "action": {
                    "action": "click_link",
                    "text": "Open Form",
                    "_raw": (
                        '{"action":"click_link","text":"Open Form",'
                        '"memory_update":{}}'
                    ),
                    "_response_metadata": action_metadata,
                },
            }],
        }
        event = {
            "timestamp": "2026-07-28T00:00:01+00:00",
            "request_index": 1,
            "request_payload_sha256": "a" * 64,
            "hidden_prompt_terms_seen": [],
            "requested_deployment": deployment,
            "api_path": "/v1/chat/completions",
            "event_type": "http_request",
            "result": "success",
            "status_code": 200,
            "response_model": deployment,
            "identity_validated": True,
            "response_id": "test-response",
        }
        if invalid_identity:
            event.update({
                "result": "exception",
                "status_code": 503,
                "response_model": None,
                "identity_validated": False,
            })
        (attempt_dir / "runs.jsonl").write_text(
            json.dumps(raw_row) + "\n",
            encoding="utf-8",
        )
        (attempt_dir / "model_identity_events.jsonl").write_text(
            json.dumps(event) + "\n",
            encoding="utf-8",
        )
        (attempt_dir / "submissions.jsonl").write_text(
            json.dumps(submission) + "\n",
            encoding="utf-8",
        )
        if partial_parent:
            (attempt_dir / "attempt_status.json").write_text(
                json.dumps({"partial": True}),
                encoding="utf-8",
            )

        pause_hashes = {
            name: sha256_file(root / name)
            for name in false_stop_recovery.SNAPSHOT_FILES
        }
        deviation = {
            "pause_snapshot_hashes": pause_hashes,
        }
        deviation_path = (
            root / false_stop_recovery.DEVIATION_RELATIVE_PATH
        )
        deviation_path.write_text(
            json.dumps(deviation),
            encoding="utf-8",
        )
        raw_expected = {
            name: sha256_file(attempt_dir / name)
            for name in false_stop_recovery.EXPECTED_RAW_HASHES
        }
        raw_inventory = false_stop_recovery.immutable_cell_inventory(
            root
        )
        root_inventory = false_stop_recovery.immutable_root_inventory(
            root
        )
        auxiliary_hashes = {
            name: sha256_file(root / name)
            for name in false_stop_recovery.EXPECTED_AUXILIARY_PAUSE_HASHES
        }
        frozen_hashes = {
            name: sha256_file(root / name)
            for name in false_stop_recovery.EXPECTED_FROZEN_HASHES
        }
        reviewed_hashes = {
            "runner": "test-runner",
            "stage_auditor": "test-stage",
            "prior_materializer": "test-prior",
        }
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_DEVIATION_SHA256",
                sha256_file(deviation_path),
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_RAW_HASHES",
                raw_expected,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_RAW_ARTIFACT_COUNT",
                raw_inventory["artifact_count"],
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_RAW_TREE_SHA256",
                raw_inventory["tree_sha256"],
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_ROOT_ARTIFACT_COUNT",
                root_inventory["artifact_count"],
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_ROOT_TREE_SHA256",
                root_inventory["tree_sha256"],
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_AUXILIARY_PAUSE_HASHES",
                auxiliary_hashes,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_FROZEN_HASHES",
                frozen_hashes,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "EXPECTED_REVIEWED_CODE_HASHES",
                reviewed_hashes,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "reviewed_code_hashes",
                return_value=reviewed_hashes,
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "audit_cell",
                return_value=[],
            )
        )
        stack.enter_context(
            patch.object(
                false_stop_recovery,
                "stable_prefix_audit",
                return_value={
                    "approved": True,
                    "errors": [],
                    "expected_completed": 1,
                },
            )
        )
        yield root, cell, attempt_dir


class ReflectionPilotTests(unittest.TestCase):
    def test_pilot_ui_sanitization_removes_metadata_badges(self):
        class FakePage:
            expression = ""

            def evaluate(self, expression):
                self.expression = expression
                return 2

        page = FakePage()
        result = sanitize_visible_page_for_pilot(
            page,
            HistoryRuntime("no_history"),
        )
        self.assertEqual(result["removed_element_count"], 2)
        self.assertIn(".chips", page.expression)
        self.assertIsNone(sanitize_visible_page_for_pilot(page, None))

    def test_internal_metadata_scan_covers_dom_and_request_payloads(self):
        self.assertEqual(
            internal_metadata_terms_in(
                {"messages": [{"content": "formal_scored_task"}]}
            ),
            ["formal_scored_task"],
        )
        self.assertEqual(
            internal_metadata_terms_in("The visible chart uses two axes."),
            [],
        )

    def test_identity_guard_rejects_mismatched_raw_response_model(self):
        import adversarial_pipeline.llm_client as llm_client

        class Response:
            status_code = 200
            text = '{"id":"x","model":"wrong-deployment"}'
            headers = {}

            @staticmethod
            def json():
                return {
                    "id": "x",
                    "model": "wrong-deployment",
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": "OK"},
                    }],
                }

            @staticmethod
            def raise_for_status():
                return None

        original_post = llm_client.requests.post
        original_set_metadata = llm_client._set_last_response_metadata
        original_messages_payload = llm_client._aime_litellm_payload_for_messages
        original_max_retries = llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES
        original_marker = getattr(
            llm_client,
            "_reflection_identity_guard_installed",
            None,
        )
        try:
            llm_client.requests.post = lambda *args, **kwargs: Response()
            if hasattr(llm_client, "_reflection_identity_guard_installed"):
                delattr(llm_client, "_reflection_identity_guard_installed")
            with patch.dict(
                os.environ,
                {"AIME_LITELLM_STRICT_MODEL_IDENTITY": "true"},
                clear=False,
            ):
                install_aime_identity_guard()
                llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES = 0
                client = llm_client.LLMClient(
                    backend="aime_litellm",
                    model="expected-deployment",
                    aime_litellm_base_url="https://example/litellm/v1",
                    aime_litellm_api_key="test-only",
                )
                with self.assertRaisesRegex(
                    RuntimeError,
                    "model identity mismatch",
                ):
                    llm_client._aime_litellm_post(
                        client,
                        {
                            "model": "expected-deployment",
                            "messages": [{"role": "user", "content": "OK"}],
                            "max_tokens": 8,
                        },
                    )
        finally:
            llm_client.requests.post = original_post
            llm_client._set_last_response_metadata = original_set_metadata
            llm_client._aime_litellm_payload_for_messages = original_messages_payload
            llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES = original_max_retries
            if original_marker is None:
                if hasattr(llm_client, "_reflection_identity_guard_installed"):
                    delattr(llm_client, "_reflection_identity_guard_installed")
            else:
                llm_client._reflection_identity_guard_installed = original_marker

    def test_pilot_messages_payload_preserves_top_p_and_seed(self):
        import adversarial_pipeline.llm_client as llm_client

        original_messages_payload = llm_client._aime_litellm_payload_for_messages
        original_marker = getattr(
            llm_client,
            "_reflection_identity_guard_installed",
            None,
        )
        try:
            if hasattr(llm_client, "_reflection_identity_guard_installed"):
                delattr(llm_client, "_reflection_identity_guard_installed")
            with patch.dict(
                os.environ,
                {"AIME_LITELLM_STRICT_MODEL_IDENTITY": "true"},
                clear=False,
            ):
                install_aime_identity_guard()
                converted = llm_client._aime_litellm_payload_for_messages({
                    "model": "deployment",
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 16,
                    "temperature": 0,
                    "top_p": 1,
                    "seed": 12345,
                })
            self.assertEqual(converted["top_p"], 1)
            self.assertEqual(converted["seed"], 12345)
            self.assertNotIn("temperature", converted)
        finally:
            llm_client._aime_litellm_payload_for_messages = original_messages_payload
            if original_marker is None:
                if hasattr(llm_client, "_reflection_identity_guard_installed"):
                    delattr(llm_client, "_reflection_identity_guard_installed")
            else:
                llm_client._reflection_identity_guard_installed = original_marker

    def test_identity_guard_audits_exact_request_for_internal_metadata(self):
        import adversarial_pipeline.llm_client as llm_client

        class Response:
            status_code = 200
            text = '{"id":"x","model":"deployment"}'
            headers = {}

            @staticmethod
            def json():
                return {
                    "id": "x",
                    "model": "deployment",
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"content": "OK"},
                    }],
                }

            @staticmethod
            def raise_for_status():
                return None

        original_post = llm_client.requests.post
        original_set_metadata = llm_client._set_last_response_metadata
        original_messages_payload = llm_client._aime_litellm_payload_for_messages
        original_max_retries = llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES
        original_marker = getattr(
            llm_client,
            "_reflection_identity_guard_installed",
            None,
        )
        try:
            with tempfile.TemporaryDirectory() as temporary:
                log = Path(temporary) / "identity.jsonl"
                llm_client.requests.post = lambda *args, **kwargs: Response()
                if hasattr(llm_client, "_reflection_identity_guard_installed"):
                    delattr(llm_client, "_reflection_identity_guard_installed")
                with patch.dict(
                    os.environ,
                    {
                        "AIME_LITELLM_STRICT_MODEL_IDENTITY": "true",
                        "WEB_AGENT_MODEL_IDENTITY_LOG": str(log),
                    },
                    clear=False,
                ):
                    install_aime_identity_guard()
                    llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES = 0
                    client = llm_client.LLMClient(
                        backend="aime_litellm",
                        model="deployment",
                        aime_litellm_base_url="https://example/litellm/v1",
                        aime_litellm_api_key="test-only",
                    )
                    llm_client._aime_litellm_post(
                        client,
                        {
                            "model": "deployment",
                            "messages": [{
                                "role": "user",
                                "content": "expected_action_id must not leak",
                            }],
                            "max_tokens": 8,
                        },
                    )
                event = read_jsonl(log)[0]
                self.assertEqual(
                    event["hidden_prompt_terms_seen"],
                    ["expected_action_id"],
                )
        finally:
            llm_client.requests.post = original_post
            llm_client._set_last_response_metadata = original_set_metadata
            llm_client._aime_litellm_payload_for_messages = original_messages_payload
            llm_client.DEFAULT_AIME_LITELLM_MAX_RETRIES = original_max_retries
            if original_marker is None:
                if hasattr(llm_client, "_reflection_identity_guard_installed"):
                    delattr(llm_client, "_reflection_identity_guard_installed")
            else:
                llm_client._reflection_identity_guard_installed = original_marker

    def test_dates_are_preserved_as_evidence(self):
        semantic = semantic_state(page_state("http://x/task/x", text="2019 versus 2024"))
        self.assertIn("2019 versus 2024", semantic["text"])

    def test_dynamic_query_is_removed_but_task_query_is_preserved(self):
        first = page_state("http://x/task/x?task_ref=a&timestamp=1")
        second = page_state("http://y/task/x?task_ref=a&timestamp=2")
        third = page_state("http://x/task/x?task_ref=b&timestamp=1")
        self.assertEqual(state_hash(first), state_hash(second))
        self.assertNotEqual(state_hash(first), state_hash(third))

    def test_select_state_changes_hash(self):
        self.assertNotEqual(
            state_hash(page_state("http://x/task/x", selected="A")),
            state_hash(page_state("http://x/task/x", selected="B")),
        )

    def test_hidden_field_is_rejected_recursively(self):
        with self.assertRaises(ValueError):
            assert_no_hidden_keys({"safe": [{"expected_action_id": "x"}]})

    def test_all_conditions_share_common_guidance_and_schema(self):
        contract = output_contract_text()
        parsed = {
            "action": {"action": "click_link", "text": "Open Form"},
            "memory_update": {"current_hypothesis": "inspect"},
        }
        outputs = []
        for condition in ["no_history", "previous_step", "full_history", "structured_falsification"]:
            runtime = HistoryRuntime(condition)
            outputs.append(runtime.normalize_response(parsed))
            self.assertIn("avoid repeating", contract)
        self.assertTrue(all(output == outputs[0] for output in outputs))
        self.assertTrue(outputs[0][2])

    def test_pilot_uses_one_action_generation_attempt_per_step(self):
        self.assertEqual(
            action_generation_attempt_limit(HistoryRuntime("no_history")),
            1,
        )
        self.assertEqual(action_generation_attempt_limit(None), 3)

    def test_malformed_schema_is_flagged_equally(self):
        parsed = {"action": "click_link", "text": "Open Form"}
        for condition in ["no_history", "previous_step", "full_history", "structured_falsification"]:
            _, _, valid = HistoryRuntime(condition).normalize_response(parsed)
            self.assertFalse(valid)

    def test_condition_payload_shapes(self):
        action = {"action": "select_option", "select_name": "primary_action", "option_text": "A"}
        for condition, expected in [
            ("no_history", 0),
            ("previous_step", 1),
            ("full_history", 1),
            ("structured_falsification", 1),
        ]:
            runtime = HistoryRuntime(condition)
            runtime.record(
                step=0,
                state=page_state("http://x/task/x"),
                action=action,
                memory_update={"current_hypothesis": "A"},
                execution_status="executed",
            )
            prompt, metadata = runtime.history_payload()
            self.assertEqual(metadata["history_records_injected"], expected)
            self.assertEqual(bool(prompt), expected > 0)

    def test_full_history_token_limit_and_retained_steps(self):
        runtime = HistoryRuntime("full_history", token_limit=256)
        for index in range(8):
            runtime.record(
                step=index,
                state=page_state(f"http://x/task/x/{index}", text="evidence " * 100),
                action={"action": "click_link", "text": str(index)},
                memory_update={"current_hypothesis": "x" * 300},
                execution_status="executed",
            )
        _, metadata = runtime.history_payload()
        self.assertTrue(metadata["history_truncated"])
        self.assertLessEqual(metadata["history_tokens_estimated"], 256)
        self.assertNotIn(0, metadata["retained_step_ids"])

    def test_all_history_payloads_remain_valid_json_when_truncated(self):
        for condition in [
            "previous_step",
            "full_history",
            "structured_falsification",
        ]:
            runtime = HistoryRuntime(condition, token_limit=256)
            for index in range(3):
                runtime.record(
                    step=index,
                    state=page_state(
                        f"http://x/task/x/{index}",
                        text="2019 2020 evidence " * 500,
                    ),
                    action={"action": "click_link", "text": "Open Form"},
                    memory_update={
                        "current_hypothesis": "hypothesis " * 500,
                        "supporting_visible_evidence": ["evidence " * 500],
                    },
                    execution_status="executed",
                )
            prompt, metadata = runtime.history_payload()
            payload = prompt.split("\n")[-1]
            json.loads(payload)
            self.assertLessEqual(metadata["history_tokens_estimated"], 256)

    def test_action_signature_is_stable(self):
        action = {"option_text": "A", "action": "select_option", "select_name": "primary_action"}
        self.assertEqual(action_signature(action), action_signature(dict(reversed(list(action.items())))))

    def test_aa_abab_and_abcabc_cycles(self):
        aa = [trace_step(0, "A", "a"), trace_step(1, "A", "a")]
        abab = [
            trace_step(0, "A", "a"),
            trace_step(1, "B", "b"),
            trace_step(2, "A", "a"),
            trace_step(3, "B", "b"),
        ]
        abcabc = [
            trace_step(0, "A", "a"),
            trace_step(1, "B", "b"),
            trace_step(2, "C", "c"),
            trace_step(3, "A", "a"),
            trace_step(4, "B", "b"),
            trace_step(5, "C", "c"),
        ]
        self.assertEqual(locate_cycles(aa)[0], {"start": 0, "end": 1, "period": 1})
        self.assertEqual(locate_cycles(abab)[0], {"start": 0, "end": 3, "period": 2})
        self.assertEqual(locate_cycles(abcabc)[0], {"start": 0, "end": 5, "period": 3})

    def test_missing_history_does_not_shift_cycle_indices(self):
        trace = [
            trace_step(0, "A", "a"),
            {"step": 1, "action": {"action": "agent_error"}},
            trace_step(2, "A", "a"),
        ]
        self.assertEqual(locate_cycles(trace), [])

    def test_long_range_revisit_is_not_cycle(self):
        trace = [trace_step(index, str(index), str(index)) for index in range(8)]
        trace.append(trace_step(8, "A", "a"))
        trace[0] = trace_step(0, "A", "a")
        metrics = analyze_cycles({"trace": trace})
        self.assertFalse(metrics["state_action_cycle_incidence"])
        self.assertEqual(metrics["long_range_revisit_count"], 1)

    def test_return_button_is_not_submission(self):
        trace = [
            trace_step(0, "A", "a"),
            trace_step(1, "A", "a", action="click_button", text="No, return to form"),
        ]
        metrics = analyze_cycles({"trace": trace})
        self.assertIsNone(metrics["submission_step"])

    def test_harmful_submission_must_follow_cycle(self):
        trace = [
            trace_step(0, "A", "a"),
            trace_step(1, "A", "a"),
            trace_step(2, "B", "submit", action="click_button", text="Submit Form"),
        ]
        metrics = analyze_cycles({
            "trace": trace,
            "selected_action_id": "trap",
            "misleading_action_ids_for_analysis": ["trap"],
        })
        self.assertTrue(metrics["submitted_after_cycle"])
        self.assertTrue(metrics["harmful_submission_after_cycle"])

    def test_execution_failure_counts_as_trace_error(self):
        step = trace_step(0, "A", "a")
        step["pilot_history"]["execution_status"] = "failed"
        self.assertEqual(analyze_cycles({"trace": [step]})["trace_agent_error_count"], 1)

    def test_strict_schema_policy_blocks_warning_submission(self):
        step = trace_step(
            0,
            "A",
            "submit",
            action="submit_form",
            text="Submit Form",
        )
        step["pilot_history"]["schema_valid"] = False
        step["action"]["_raw"] = '{"action":"submit_form"}'
        step["submission"] = {"selected_action_id": "trap"}
        row = {
            "outcome": "misleading_failure",
            "selected_action_id": "trap",
            "submission": {"selected_action_id": "trap"},
            "trace": [step],
        }

        diagnostic = schema_cell_diagnostics(row, ["trap"])
        strict = diagnostic["strict_fail_closed"]

        self.assertTrue(diagnostic["schema_compliance_applicable"])
        self.assertFalse(diagnostic["schema_compliant_cell"])
        self.assertTrue(strict["schema_blocked"])
        self.assertEqual(strict["step_count"], 0)
        self.assertFalse(strict["task_success"])
        self.assertFalse(strict["harmful_submission"])
        self.assertTrue(strict["blocked_action_would_submit"])
        self.assertTrue(strict["blocked_action_would_be_harmful"])
        self.assertEqual(
            strict["blocked_submission_evidence"],
            "explicit_step_submission",
        )
        self.assertEqual(strict["model_request_count"], 1)

    def test_strict_schema_policy_excludes_warning_from_cycle_prefix(self):
        first = trace_step(0, "A", "a")
        first["pilot_history"]["schema_valid"] = True
        first["action"]["_raw"] = '{"action":"click_link"}'
        first["action"]["_response_metadata"] = {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
            },
        }
        warning = trace_step(99, "A", "a")
        warning["pilot_history"]["schema_valid"] = False
        warning["action"]["_raw"] = '{"action":"click_link"}'
        warning["action"]["_response_metadata"] = {
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 2,
                "total_tokens": 22,
            },
        }
        trailing = trace_step(2, "A", "a")
        trailing["pilot_history"]["schema_valid"] = True
        trailing["action"]["_raw"] = '{"action":"click_link"}'
        trailing["action"]["_response_metadata"] = {
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 3,
                "total_tokens": 33,
            },
        }
        row = {
            "outcome": "agent_timeout",
            "trace": [first, warning, trailing],
        }

        strict = schema_cell_diagnostics(row, [])["strict_fail_closed"]

        self.assertEqual(strict["step_count"], 1)
        self.assertFalse(strict["state_action_cycle_incidence"])
        self.assertEqual(strict["model_request_count"], 2)
        self.assertEqual(strict["blocked_step"], 1)
        self.assertEqual(strict["blocked_runner_step"], 99)
        self.assertEqual(strict["blocked_proposed_action"], {
            "action": "click_link",
        })
        self.assertEqual(strict["prompt_tokens"], 30)
        self.assertEqual(strict["completion_tokens"], 3)
        self.assertEqual(strict["total_tokens"], 33)

    def test_strict_schema_policy_preserves_prior_explicit_submission(self):
        submitted = trace_step(
            0,
            "A",
            "submit",
            action="submit_form",
            text="Submit Form",
        )
        submitted["pilot_history"]["schema_valid"] = True
        submitted["action"]["_raw"] = '{"action":"submit_form"}'
        submitted["submission"] = {"selected_action_id": "correct"}
        warning = trace_step(1, "B", "b")
        warning["pilot_history"]["schema_valid"] = False
        warning["action"]["_raw"] = '{"action":"click_link"}'
        row = {
            "outcome": "success",
            "selected_action_id": "correct",
            "submission": {"selected_action_id": "correct"},
            "trace": [submitted, warning],
        }

        strict = schema_cell_diagnostics(row, ["trap"])[
            "strict_fail_closed"
        ]

        self.assertEqual(strict["outcome"], "success")
        self.assertTrue(strict["task_success"])
        self.assertEqual(strict["selected_action_id"], "correct")
        self.assertFalse(strict["harmful_submission"])
        self.assertEqual(strict["step_count"], 1)

    def test_strict_schema_policy_preserves_prior_harmful_submission(self):
        submitted = trace_step(
            0,
            "A",
            "submit",
            action="submit_form",
            text="Submit Form",
        )
        submitted["pilot_history"]["schema_valid"] = True
        submitted["action"]["_raw"] = '{"action":"submit_form"}'
        submitted["submission"] = {"selected_action_id": "trap"}
        warning = trace_step(1, "B", "b")
        warning["pilot_history"]["schema_valid"] = False
        warning["action"]["_raw"] = '{"action":"click_link"}'
        row = {
            "outcome": "misleading_failure",
            "selected_action_id": "trap",
            "submission": {"selected_action_id": "trap"},
            "trace": [submitted, warning],
        }

        strict = schema_cell_diagnostics(row, ["trap"])[
            "strict_fail_closed"
        ]

        self.assertEqual(strict["outcome"], "misleading_failure")
        self.assertEqual(strict["selected_action_id"], "trap")
        self.assertTrue(strict["harmful_submission"])
        self.assertFalse(strict["task_success"])

    def test_schema_requires_auditable_raw_model_output(self):
        step = trace_step(7, "A", "a")
        step["pilot_history"]["schema_valid"] = False
        diagnostic = schema_cell_diagnostics(
            {"outcome": "agent_timeout", "trace": [step]},
            [],
        )
        self.assertFalse(diagnostic["schema_compliance_applicable"])
        self.assertIsNone(diagnostic["schema_compliant_cell"])
        self.assertEqual(diagnostic["schema_step_count"], 0)

    def test_strict_schema_policy_removes_downstream_interface_error(self):
        warning = trace_step(0, "A", "a")
        warning["pilot_history"]["schema_valid"] = False
        warning["action"]["_raw"] = '{"action":"click_link"}'
        downstream_error = {
            "step": 1,
            "action": {
                "action": "agent_error",
                "error": "HTTP 503 service unavailable",
            },
        }
        row = {
            "cell_id": "cell-a",
            "model": "gpt54",
            "benchmark": "official",
            "condition": "no_history",
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception": "HTTP 503 service unavailable",
            "trace": [warning, downstream_error],
        }
        diagnostic = schema_cell_diagnostics(row, [])
        metrics = {
            **row,
            **diagnostic,
            **analyze_cycles(row),
            "selected_action_id": "",
            "harmful_submission": False,
            "interface_error": True,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        strict = apply_strict_fail_closed_policy([metrics])[0]

        self.assertEqual(strict["outcome"], "schema_blocked")
        self.assertFalse(strict["interface_error"])
        self.assertEqual(
            strict["error_attribution"],
            "schema_parser_policy_block",
        )
        self.assertFalse(strict["agent_error"])
        self.assertEqual(strict["step_count"], 0)

    def test_compliant_schema_policy_preserves_decision_metrics(self):
        step = trace_step(
            0,
            "A",
            "submit",
            action="submit_form",
            text="Submit Form",
        )
        step["pilot_history"]["schema_valid"] = True
        step["action"]["_raw"] = '{"action":"submit_form"}'
        step["action"]["_response_metadata"] = {
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
            },
        }
        step["submission"] = {"selected_action_id": "correct"}
        row = {
            "cell_id": "cell-a",
            "model": "gpt54",
            "benchmark": "official",
            "condition": "no_history",
            "outcome": "success",
            "error_attribution": "none",
            "selected_action_id": "correct",
            "submission": {"selected_action_id": "correct"},
            "trace": [step],
        }
        diagnostic = schema_cell_diagnostics(row, ["trap"])
        metrics = {
            **row,
            **diagnostic,
            **analyze_cycles({
                **row,
                "misleading_action_ids_for_analysis": ["trap"],
            }),
            "harmful_submission": False,
            "interface_error": False,
            **usage(row),
        }

        strict = apply_strict_fail_closed_policy([metrics])[0]
        decision_keys = {
            "outcome",
            "error_attribution",
            "interface_error",
            "selected_action_id",
            "harmful_submission",
            "state_action_cycle_incidence",
            "state_action_recurrence_count",
            "long_range_revisit_count",
            "repeated_state_action_count",
            "abab_cycle_count",
            "navigation_cycle_count",
            "cycle_start_step",
            "cycle_end_step",
            "cycle_period",
            "escape_step",
            "steps_to_escape",
            "escaped_before_submission",
            "submission_step",
            "submitted_after_cycle",
            "harmful_submission_after_cycle",
            "trace_agent_error_count",
            "step_count",
            "task_success",
            "agent_error",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        }
        self.assertEqual(
            {key: strict[key] for key in decision_keys},
            {key: metrics[key] for key in decision_keys},
        )

    def test_schema_not_applicable_and_policy_preserves_cell_weights(self):
        no_audit = {
            "cell_id": "cell-a",
            "model": "gpt54",
            "benchmark": "official",
            "condition": "no_history",
            "outcome": "success",
            "trace": [],
        }
        diagnostic = schema_cell_diagnostics(no_audit, [])
        self.assertFalse(diagnostic["schema_compliance_applicable"])
        self.assertIsNone(diagnostic["schema_compliant_cell"])

        compliant_step = trace_step(0, "A", "a")
        compliant_step["pilot_history"]["schema_valid"] = True
        compliant_step["action"]["_raw"] = '{"action":"click_link"}'
        compliant = {
            **no_audit,
            "cell_id": "cell-b",
            "condition": "previous_step",
            "trace": [compliant_step],
            **schema_cell_diagnostics(
                {"outcome": "success", "trace": [compliant_step]},
                [],
            ),
            **analyze_cycles({"outcome": "success", "trace": [compliant_step]}),
            "harmful_submission": False,
            "interface_error": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        no_audit_metrics = {
            **no_audit,
            **diagnostic,
            **analyze_cycles(no_audit),
            "harmful_submission": False,
            "interface_error": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        rows = [no_audit_metrics, compliant]
        transformed = apply_strict_fail_closed_policy(rows)

        self.assertEqual(
            [row["cell_id"] for row in transformed],
            ["cell-a", "cell-b"],
        )
        self.assertEqual(len(transformed), len(rows))
        summary = schema_compliance_summary(rows)
        by_condition = {row["condition"]: row for row in summary}
        self.assertEqual(
            by_condition["no_history"]["not_applicable_cell_count"],
            1,
        )
        self.assertEqual(
            by_condition["previous_step"]["cell_compliance_rate"],
            1.0,
        )

    def test_schema_summary_reports_warning_na_and_truncation_rates(self):
        rows = [
            {
                "model": "gpt54",
                "benchmark": "official",
                "condition": "full_history",
                "schema_compliance_applicable": True,
                "schema_compliant_cell": False,
                "schema_step_count": 2,
                "schema_warning_step_count": 1,
                "history_truncation_count": 3,
                "strict_fail_closed": {"schema_blocked": True},
            },
            {
                "model": "gpt54",
                "benchmark": "official",
                "condition": "full_history",
                "schema_compliance_applicable": True,
                "schema_compliant_cell": True,
                "schema_step_count": 3,
                "schema_warning_step_count": 0,
                "history_truncation_count": 0,
                "strict_fail_closed": {"schema_blocked": False},
            },
            {
                "model": "gpt54",
                "benchmark": "official",
                "condition": "full_history",
                "schema_compliance_applicable": False,
                "schema_compliant_cell": None,
                "schema_step_count": 0,
                "schema_warning_step_count": 0,
                "history_truncation_count": 0,
                "strict_fail_closed": {"schema_blocked": False},
            },
        ]

        summary = schema_compliance_summary(rows)[0]

        self.assertEqual(summary["cell_count"], 3)
        self.assertEqual(summary["applicable_cell_count"], 2)
        self.assertEqual(summary["not_applicable_cell_count"], 1)
        self.assertEqual(summary["warning_cell_count"], 1)
        self.assertEqual(summary["warning_cell_rate"], 0.5)
        self.assertAlmostEqual(
            summary["warning_cell_rate_all_cells"],
            1 / 3,
        )
        self.assertEqual(summary["schema_step_count"], 5)
        self.assertEqual(summary["schema_warning_step_count"], 1)
        self.assertEqual(summary["schema_warning_step_rate"], 0.2)
        self.assertEqual(summary["history_truncation_cell_count"], 1)
        self.assertEqual(summary["history_truncation_step_count"], 3)

    def test_strict_schema_policy_preserves_all_512_cells_and_weights(self):
        metrics = []
        for cell in build_manifest():
            base = {
                "cell_id": cell["cell_id"],
                "model": cell["model"],
                "benchmark": cell["benchmark"],
                "condition": cell["condition"],
                "outcome": "success",
                "error_attribution": "none",
                "interface_error": False,
                "selected_action_id": "",
                "harmful_submission": False,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "trace": [],
            }
            metrics.append({
                **base,
                **schema_cell_diagnostics(base, []),
                **analyze_cycles(base),
            })

        transformed = apply_strict_fail_closed_policy(metrics)

        self.assertEqual(len(transformed), 512)
        self.assertEqual(
            [row["cell_id"] for row in transformed],
            [row["cell_id"] for row in metrics],
        )
        self.assertEqual(
            {
                key: sum(
                    (
                        row["model"],
                        row["benchmark"],
                        row["condition"],
                    ) == key
                    for row in transformed
                )
                for key in {
                    (
                        row["model"],
                        row["benchmark"],
                        row["condition"],
                    )
                    for row in transformed
                }
            },
            {
                key: sum(
                    (
                        row["model"],
                        row["benchmark"],
                        row["condition"],
                    ) == key
                    for row in metrics
                )
                for key in {
                    (
                        row["model"],
                        row["benchmark"],
                        row["condition"],
                    )
                    for row in metrics
                }
            },
        )

    def test_token_estimator_handles_chinese_and_ascii(self):
        self.assertGreaterEqual(estimate_tokens("证据状态"), 4)
        self.assertGreaterEqual(estimate_tokens("one two three"), 3)

    def test_checkpoint_secret_scan_avoids_task_flag_false_positive(self):
        self.assertIsNone(SECRET_PATTERN.search("--task-timeout-sec"))
        self.assertIsNone(SECRET_PATTERN.search("task-specific"))
        self.assertIsNotNone(
            SECRET_PATTERN.search("sk-" "exampleCredential123456")
        )
        self.assertIsNone(STAGE_SECRET_PATTERNS[0].search(b"task-specific"))
        self.assertIsNotNone(
            STAGE_SECRET_PATTERNS[0].search(
                b"sk-" b"exampleCredential123456"
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "safe.log").write_text(
                "--task-timeout-sec\ntask-specific\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_secrets(root), [])
            self.assertEqual(stage_secret_scan(root), ([], []))
            (root / "unsafe.log").write_text(
                "sk-" "exampleCredential123456\n",
                encoding="utf-8",
            )
            self.assertEqual(scan_secrets(root), ["unsafe.log"])
            self.assertEqual(stage_secret_scan(root), (["unsafe.log"], []))

    def test_action_semantics_audit_accepts_flat_shape_without_rewriting(self):
        flat = {
            "action": "click_link",
            "text": "Open Form",
            "_raw": (
                '{"action":"click_link","text":"Open Form",'
                '"memory_update":{}}'
            ),
        }
        self.assertTrue(valid_frozen_action(flat))
        self.assertTrue(raw_action_semantics_match(flat))
        changed = dict(flat)
        changed["text"] = "Open Dashboard"
        self.assertFalse(raw_action_semantics_match(changed))
        self.assertFalse(valid_frozen_action({"action": "click_link"}))

    @staticmethod
    def _write_rows(path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )

    def _build_checkpoint_fixture(
        self,
        root: Path,
        *,
        aborted_first_start: bool = False,
    ) -> tuple[list[dict], list[dict], str]:
        manifest = build_manifest()
        manifest_path = root / "preregistered_cells.jsonl"
        self._write_rows(manifest_path, manifest)
        (root / "preregistration.json").write_text(
            json.dumps({"manifest_sha256": sha256_file(manifest_path)}),
            encoding="utf-8",
        )
        schedule_path = root / "scheduling_deviation.json"
        schedule = {
            "created_at": "2026-07-27T13:17:35.381947+00:00",
            **scheduling_deviation_spec(
                manifest,
                manifest_sha256=sha256_file(manifest_path),
            ),
        }
        schedule_path.write_text(
            json.dumps(schedule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        schedule_sha = sha256_file(schedule_path)
        (root / "scheduling_deviation.sha256").write_text(
            f"{schedule_sha}  {schedule_path.name}\n",
            encoding="utf-8",
        )
        prepare_runtime_config(
            root,
            manifest_path=manifest_path,
            experiment_kind="formal_512_cell_pilot",
            scheduling_path=schedule_path,
        )
        prepare_review_provenance(root)
        (root / RUNNER_LOCK_FILENAME).write_text(
            json.dumps({
                "pid": 1,
                "acquired_at": "2026-07-27T00:00:00+00:00",
                "output_root": str(root.resolve()),
            }),
            encoding="utf-8",
        )
        rows: list[dict] = []
        attempt_statuses: list[dict] = []
        schedule_events: list[dict] = []
        frozen_schedule = scheduled_cells(manifest)
        if aborted_first_start:
            first = frozen_schedule[0]
            schedule_events.extend([
                {
                    "event_type": "cell_start",
                    "cell_id": first["cell_id"],
                    "execution_sequence": 1,
                    "started_at": "2026-07-27T00:00:00+00:00",
                    "original_condition_order": first["condition_order"],
                    "model_queue": first["model"],
                    "scheduling_deviation_sha256": schedule_sha,
                },
                {
                    "event_type": "cell_abort",
                    "cell_id": first["cell_id"],
                    "execution_sequence": 1,
                    "aborted_at": "2026-07-27T00:00:01+00:00",
                    "reason": "process_interruption_detected_at_resume",
                    "original_condition_order": first["condition_order"],
                    "model_queue": first["model"],
                },
            ])
        empty_hash = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        for sequence, cell in enumerate(frozen_schedule[:64], 1):
            execution_sequence = sequence + int(aborted_first_start)
            cell_id = cell["cell_id"]
            deployment = MODEL_CONFIGS[cell["model"]]["deployment_id"]
            attempt_dir = root / "cells" / cell_id / "attempt_01"
            screenshot = attempt_dir / "screenshots" / "step_00.png"
            screenshot.parent.mkdir(parents=True)
            screenshot.write_bytes(b"fixture")
            response_metadata = {
                "requested_deployment": deployment,
                "response_model": deployment,
                "identity_validated": True,
                "request_payload_sha256": "b" * 64,
                "hidden_prompt_terms_seen": [],
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
            history = {
                "condition": cell["condition"],
                "history_chars": 0,
                "history_tokens_estimated": 0,
                "history_records_available": 0,
                "history_records_injected": 0,
                "retained_step_ids": [],
                "history_truncated": False,
                "history_payload_sha256": empty_hash,
                "state_hash": "a" * 64,
                "action_signature": '{"action":"finish"}',
                "memory_update": empty_memory(),
                "schema_valid": True,
                "execution_status": "finish",
            }
            relative_attempt = str(attempt_dir.relative_to(root))
            row = {
                "outcome": "success",
                "error_attribution": "none",
                "trace": [{
                    "step": 0,
                    "screenshot": str(screenshot),
                    "page_text_excerpt": "fixture",
                    "pilot_hidden_terms_seen": [],
                    "pilot_ui_sanitization": {
                        "applied_before_screenshot_and_state_capture": True,
                        "removed_element_count": 1,
                    },
                    "action": {
                        "action": "finish",
                        "_raw": (
                            '{"action":{"action":"finish"},'
                            '"memory_update":{}}'
                        ),
                        "_response_metadata": response_metadata,
                    },
                    "pilot_history": history,
                }],
                "pilot_identity_audit": {
                    "valid": True,
                    "expected_deployment": deployment,
                    "identity_event_count": 1,
                    "traced_model_action_count": 1,
                    "errors": [],
                },
                "pilot_cell": cell,
                "pilot_attempt": 1,
                "pilot_attempt_dir": relative_attempt,
                "pilot_actual_http_request_count": 1,
                "pilot_scheduling": {
                    "execution_sequence": execution_sequence,
                    "started_at": "2026-07-27T00:00:00+00:00",
                    "original_condition_order": cell["condition_order"],
                    "model_queue": cell["model"],
                    "scheduling_deviation_sha256": schedule_sha,
                },
            }
            self._write_rows(
                attempt_dir / "model_identity_events.jsonl",
                [{
                    "event_type": "http_request",
                    "request_index": 1,
                    "result": "success",
                    "requested_deployment": deployment,
                    "response_model": deployment,
                    "identity_validated": True,
                    "request_payload_sha256": "b" * 64,
                    "hidden_prompt_terms_seen": [],
                }],
            )
            attempt_row = dict(row)
            attempt_row.pop("pilot_scheduling")
            (attempt_dir / "result.json").write_text(
                json.dumps(attempt_row),
                encoding="utf-8",
            )
            attempt_status = {
                "cell_id": cell_id,
                "attempt": 1,
                "attempt_dir": relative_attempt,
                "formal_attempt_consumed": True,
                "availability_aborted": False,
                "actual_http_request_count": 1,
                "outcome": "success",
            }
            (attempt_dir / "attempt_status.json").write_text(
                json.dumps(attempt_status),
                encoding="utf-8",
            )
            attempt_statuses.append(attempt_status)
            chosen = root / "cells" / cell_id / "chosen_result.json"
            chosen.write_text(json.dumps(row), encoding="utf-8")
            rows.append(row)
            schedule_events.extend([
                {
                    "event_type": "cell_start",
                    "cell_id": cell_id,
                    "execution_sequence": execution_sequence,
                    "started_at": "2026-07-27T00:00:00+00:00",
                    "original_condition_order": cell["condition_order"],
                    "model_queue": cell["model"],
                    "scheduling_deviation_sha256": schedule_sha,
                },
                {
                    "event_type": "cell_finish",
                    "cell_id": cell_id,
                    "execution_sequence": execution_sequence,
                    "finished_at": "2026-07-27T00:00:01+00:00",
                    "outcome": "success",
                    "chosen_attempt": 1,
                },
            ])
        self._write_rows(root / "runs.jsonl", rows)
        self._write_rows(root / "attempt_manifest.jsonl", attempt_statuses)
        self._write_rows(root / "scheduling_execution_log.jsonl", schedule_events)
        return manifest, rows, schedule_sha

    def _write_nonformal_smoke_fixture(
        self,
        root: Path,
        *,
        manifest_name: str,
        manifest: list[dict],
        selected: list[dict],
        experiment_kind: str,
    ) -> None:
        manifest_path = root / manifest_name
        self._write_rows(manifest_path, manifest)
        prepare_runtime_config(
            root,
            manifest_path=manifest_path,
            experiment_kind=experiment_kind,
        )
        rows: list[dict] = []
        statuses: list[dict] = []
        checkpoints: list[dict] = []
        for cell in selected:
            cell_id = cell["cell_id"]
            deployment = MODEL_CONFIGS[cell["model"]]["deployment_id"]
            attempt_dir = root / "cells" / cell_id / "attempt_01"
            screenshot = attempt_dir / "screenshots" / "step_00.png"
            screenshot.parent.mkdir(parents=True)
            screenshot.write_bytes(b"fixture")
            relative_attempt = str(attempt_dir.relative_to(root))
            row = {
                "outcome": "success",
                "error_attribution": "none",
                "trace": [{
                    "step": 0,
                    "screenshot": str(screenshot),
                    "page_text_excerpt": "fixture",
                    "pilot_hidden_terms_seen": [],
                    "pilot_ui_sanitization": {
                        "applied_before_screenshot_and_state_capture": True,
                        "removed_element_count": 1,
                    },
                    "action": {
                        "action": "finish",
                        "_raw": (
                            '{"action":{"action":"finish"},'
                            '"memory_update":{}}'
                        ),
                        "_response_metadata": {
                            "requested_deployment": deployment,
                            "response_model": deployment,
                            "identity_validated": True,
                            "request_payload_sha256": "b" * 64,
                            "hidden_prompt_terms_seen": [],
                        },
                    },
                    "pilot_history": {
                        "condition": cell["condition"],
                        "history_chars": 0,
                        "history_tokens_estimated": 0,
                        "history_records_available": 0,
                        "history_records_injected": 0,
                        "retained_step_ids": [],
                        "history_truncated": False,
                        "history_payload_sha256": (
                            "e3b0c44298fc1c149afbf4c8996fb924"
                            "27ae41e4649b934ca495991b7852b855"
                        ),
                        "state_hash": "a" * 64,
                        "action_signature": '{"action":"finish"}',
                        "memory_update": empty_memory(),
                        "schema_valid": True,
                        "execution_status": "finish",
                    },
                }],
                "pilot_identity_audit": {
                    "valid": True,
                    "expected_deployment": deployment,
                    "identity_event_count": 1,
                    "traced_model_action_count": 1,
                    "errors": [],
                },
                "pilot_cell": cell,
                "pilot_attempt": 1,
                "pilot_attempt_dir": relative_attempt,
                "pilot_actual_http_request_count": 1,
            }
            self._write_rows(
                attempt_dir / "model_identity_events.jsonl",
                [{
                    "event_type": "http_request",
                    "request_index": 1,
                    "result": "success",
                    "requested_deployment": deployment,
                    "response_model": deployment,
                    "identity_validated": True,
                    "request_payload_sha256": "b" * 64,
                    "hidden_prompt_terms_seen": [],
                }],
            )
            (attempt_dir / "result.json").write_text(
                json.dumps(row),
                encoding="utf-8",
            )
            status = {
                "cell_id": cell_id,
                "attempt": 1,
                "attempt_dir": relative_attempt,
                "formal_attempt_consumed": True,
                "availability_aborted": False,
                "actual_http_request_count": 1,
                "outcome": "success",
                "error_attribution": "none",
            }
            (attempt_dir / "attempt_status.json").write_text(
                json.dumps(status),
                encoding="utf-8",
            )
            statuses.append(status)
            checkpoints.append({
                "cell_id": cell_id,
                "condition_order": cell["condition_order"],
                "attempt_count": 1,
                "chosen_attempt": 1,
                "outcome": "success",
                "error_attribution": "none",
                "scheduling_execution_sequence": None,
            })
            chosen = root / "cells" / cell_id / "chosen_result.json"
            chosen.write_text(json.dumps(row), encoding="utf-8")
            rows.append(row)
        self._write_rows(root / "runs.jsonl", rows)
        self._write_rows(root / "attempt_manifest.jsonl", statuses)
        self._write_rows(root / "checkpoint_manifest.jsonl", checkpoints)

    def _build_model_scoped_smoke_fixture(
        self,
        certified_root: Path,
        auxiliary_root: Path,
    ) -> None:
        original = build_smoke_manifest()
        original_sonnet = [
            cell
            for cell in original
            if cell["model"] == "claude_sonnet_4_6_litellm"
        ]
        auxiliary = build_sonnet_auxiliary_smoke_manifest()
        self._write_nonformal_smoke_fixture(
            certified_root,
            manifest_name="instrumentation_smoke_cells.jsonl",
            manifest=original,
            selected=original_sonnet,
            experiment_kind="instrumentation_smoke_non_formal",
        )
        self._write_nonformal_smoke_fixture(
            auxiliary_root,
            manifest_name="sonnet_auxiliary_smoke_cells.jsonl",
            manifest=auxiliary,
            selected=auxiliary,
            experiment_kind="instrumentation_smoke_sonnet_auxiliary_non_formal",
        )

    def test_model_scoped_smoke_audit_is_closed_and_nonformal(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            certified = base / "certified"
            auxiliary = base / "auxiliary"
            self._build_model_scoped_smoke_fixture(certified, auxiliary)

            report = audit_model_scoped_smoke(certified, auxiliary)
            self.assertTrue(report["approved"], report["errors"])

            aux_rows = read_jsonl(auxiliary / "runs.jsonl")
            self._write_rows(auxiliary / "runs.jsonl", [*aux_rows, aux_rows[0]])
            report = audit_model_scoped_smoke(certified, auxiliary)
            self.assertFalse(report["approved"])
            self.assertIn("duplicate run", " ".join(report["errors"]))

            self._write_rows(auxiliary / "runs.jsonl", aux_rows)
            extra = json.loads(json.dumps(aux_rows[0]))
            extra["pilot_cell"] = next(
                cell for cell in build_smoke_manifest()
                if cell["model"] == "gpt54"
            )
            self._write_rows(auxiliary / "runs.jsonl", [*aux_rows, extra])
            report = audit_model_scoped_smoke(certified, auxiliary)
            self.assertFalse(report["approved"])
            self.assertIn("unknown cells", " ".join(report["errors"]))

            self._write_rows(auxiliary / "runs.jsonl", aux_rows)
            config_path = auxiliary / "pilot_run_config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["experiment_kind"] = "formal_512_cell_pilot"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            report = audit_model_scoped_smoke(certified, auxiliary)
            self.assertFalse(report["approved"])
            self.assertIn(
                "non-formal run configuration differs",
                " ".join(report["errors"]),
            )

            config_path.unlink()
            prepare_runtime_config(
                auxiliary,
                manifest_path=auxiliary / "sonnet_auxiliary_smoke_cells.jsonl",
                experiment_kind=(
                    "instrumentation_smoke_sonnet_auxiliary_non_formal"
                ),
            )
            (auxiliary / "scheduling_execution_log.jsonl").write_text(
                "",
                encoding="utf-8",
            )
            report = audit_model_scoped_smoke(certified, auxiliary)
            self.assertFalse(report["approved"])
            self.assertIn("formal scheduling artifacts", " ".join(report["errors"]))

    def test_gpt_model_scoped_smoke_audit_is_closed_and_nonformal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = build_gpt_model_scoped_smoke_manifest()
            self._write_nonformal_smoke_fixture(
                root,
                manifest_name="gpt_model_scoped_smoke_cells.jsonl",
                manifest=manifest,
                selected=manifest,
                experiment_kind=(
                    "instrumentation_smoke_gpt_model_scoped_non_formal"
                ),
            )

            report = audit_gpt_model_scoped_smoke(root)

            self.assertTrue(report["approved"], report["errors"])
            self.assertEqual(report["completed_cells"], 4)
            self.assertEqual(
                report["conditions"],
                [
                    "full_history",
                    "no_history",
                    "previous_step",
                    "structured_falsification",
                ],
            )
            self.assertEqual(
                report["split_counts"],
                {"official": 2, "clean": 2},
            )

            rows = read_jsonl(root / "runs.jsonl")
            rows[0]["pilot_cell"]["model"] = (
                "claude_sonnet_4_6_litellm"
            )
            self._write_rows(root / "runs.jsonl", rows)
            report = audit_gpt_model_scoped_smoke(root)
            self.assertFalse(report["approved"])

    def test_gpt_smoke_audit_rejects_broken_attempt_evidence(self):
        def build_fixture(root: Path) -> tuple[list[dict], dict]:
            manifest = build_gpt_model_scoped_smoke_manifest()
            self._write_nonformal_smoke_fixture(
                root,
                manifest_name="gpt_model_scoped_smoke_cells.jsonl",
                manifest=manifest,
                selected=manifest,
                experiment_kind=(
                    "instrumentation_smoke_gpt_model_scoped_non_formal"
                ),
            )
            return manifest, read_jsonl(root / "runs.jsonl")[0]

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)

            mismatch_root = base / "result_mismatch"
            _, row = build_fixture(mismatch_root)
            result_path = (
                mismatch_root / row["pilot_attempt_dir"] / "result.json"
            )
            attempt_result = json.loads(
                result_path.read_text(encoding="utf-8")
            )
            attempt_result["outcome"] = "agent_timeout"
            result_path.write_text(
                json.dumps(attempt_result),
                encoding="utf-8",
            )
            report = audit_gpt_model_scoped_smoke(mismatch_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "chosen result differs from consumed attempt result",
                " ".join(report["errors"]),
            )

            missing_status_root = base / "missing_status"
            _, row = build_fixture(missing_status_root)
            (
                missing_status_root
                / row["pilot_attempt_dir"]
                / "attempt_status.json"
            ).unlink()
            report = audit_gpt_model_scoped_smoke(missing_status_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "attempt directories do not exactly match status files",
                " ".join(report["errors"]),
            )

            zero_root = base / "zero_request"
            _, first = build_fixture(zero_root)
            rows = read_jsonl(zero_root / "runs.jsonl")
            rows[0]["pilot_actual_http_request_count"] = 0
            rows[0]["pilot_identity_audit"]["identity_event_count"] = 0
            cell_id = rows[0]["pilot_cell"]["cell_id"]
            relative = rows[0]["pilot_attempt_dir"]
            chosen = zero_root / "cells" / cell_id / "chosen_result.json"
            result = zero_root / relative / "result.json"
            chosen.write_text(json.dumps(rows[0]), encoding="utf-8")
            result.write_text(json.dumps(rows[0]), encoding="utf-8")
            self._write_rows(zero_root / "runs.jsonl", rows)
            statuses = read_jsonl(zero_root / "attempt_manifest.jsonl")
            statuses[0]["actual_http_request_count"] = 0
            self._write_rows(
                zero_root / "attempt_manifest.jsonl",
                statuses,
            )
            status_path = zero_root / relative / "attempt_status.json"
            status_path.write_text(
                json.dumps(statuses[0]),
                encoding="utf-8",
            )
            (zero_root / relative / "model_identity_events.jsonl").write_text(
                "",
                encoding="utf-8",
            )
            report = audit_gpt_model_scoped_smoke(zero_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "chosen attempt made zero HTTP requests",
                " ".join(report["errors"]),
            )

            event_root = base / "non_success_event"
            _, row = build_fixture(event_root)
            events_path = (
                event_root
                / row["pilot_attempt_dir"]
                / "model_identity_events.jsonl"
            )
            events = read_jsonl(events_path)
            events[0]["result"] = "transient_error"
            self._write_rows(events_path, events)
            report = audit_gpt_model_scoped_smoke(event_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "chosen attempt contains a non-success HTTP event",
                " ".join(report["errors"]),
            )

            def add_attempt(
                root: Path,
                *,
                directory_name: str,
                attempt: int,
                consumed: bool,
                inconsistent_status: bool = False,
            ) -> None:
                chosen_row = read_jsonl(root / "runs.jsonl")[0]
                old_dir = root / chosen_row["pilot_attempt_dir"]
                new_dir = old_dir.parent / directory_name
                shutil.copytree(old_dir, new_dir)
                relative = str(new_dir.relative_to(root))
                attempt_row = json.loads(json.dumps(chosen_row))
                attempt_row["pilot_attempt"] = attempt
                attempt_row["pilot_attempt_dir"] = relative
                if not consumed:
                    attempt_row["outcome"] = "agent_error"
                    attempt_row[
                        "error_attribution"
                    ] = "llm_action_generation_error"
                    attempt_row["exception"] = "HTTP 429 cooling down"
                (new_dir / "result.json").write_text(
                    json.dumps(attempt_row),
                    encoding="utf-8",
                )
                status = {
                    "cell_id": chosen_row["pilot_cell"]["cell_id"],
                    "attempt": attempt,
                    "attempt_dir": relative,
                    "formal_attempt_consumed": consumed,
                    "availability_aborted": not consumed,
                    "actual_http_request_count": 1,
                    "outcome": (
                        "success"
                        if inconsistent_status
                        else attempt_row["outcome"]
                    ),
                    "error_attribution": (
                        "none"
                        if inconsistent_status
                        else attempt_row["error_attribution"]
                    ),
                }
                (new_dir / "attempt_status.json").write_text(
                    json.dumps(status),
                    encoding="utf-8",
                )
                statuses = read_jsonl(root / "attempt_manifest.jsonl")
                self._write_rows(
                    root / "attempt_manifest.jsonl",
                    [*statuses, status],
                )

            duplicate_root = base / "duplicate_consumed"
            _, _ = build_fixture(duplicate_root)
            add_attempt(
                duplicate_root,
                directory_name="attempt_01_resume_01",
                attempt=1,
                consumed=True,
            )
            report = audit_gpt_model_scoped_smoke(duplicate_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "duplicate consumed attempt index",
                " ".join(report["errors"]),
            )

            extra_root = base / "extra_consumed"
            _, _ = build_fixture(extra_root)
            add_attempt(
                extra_root,
                directory_name="attempt_02",
                attempt=2,
                consumed=True,
            )
            report = audit_gpt_model_scoped_smoke(extra_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "chosen attempt is not the final consumed attempt",
                " ".join(report["errors"]),
            )

            inconsistent_root = base / "inconsistent_nonchosen"
            _, _ = build_fixture(inconsistent_root)
            add_attempt(
                inconsistent_root,
                directory_name="attempt_01_availability_abort_01",
                attempt=1,
                consumed=False,
                inconsistent_status=True,
            )
            report = audit_gpt_model_scoped_smoke(inconsistent_root)
            self.assertFalse(report["approved"])
            self.assertIn(
                "attempt outcome differs from status",
                " ".join(report["errors"]),
            )

    def test_gpt_gate1_validator_binds_audit_and_independent_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            smoke = base / "smoke"
            formal = base / "formal"
            manifest = build_gpt_model_scoped_smoke_manifest()
            self._write_nonformal_smoke_fixture(
                smoke,
                manifest_name="gpt_model_scoped_smoke_cells.jsonl",
                manifest=manifest,
                selected=manifest,
                experiment_kind=(
                    "instrumentation_smoke_gpt_model_scoped_non_formal"
                ),
            )
            audit = audit_gpt_model_scoped_smoke(smoke)
            audit_path = smoke / "model_scoped_gate1_audit.json"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            approval_dir = formal / "gate_reviews"
            approval_dir.mkdir(parents=True)
            approval = {
                "decision": "APPROVE GPT MODEL-SCOPED GATE 1",
                "reviewer_agent_id": (
                    "019fa390-af77-7312-9c16-7b611362f58a"
                ),
                "smoke_root": str(smoke),
                "audit_sha256": sha256_file(audit_path),
                "manifest_sha256": sha256_file(
                    smoke / "gpt_model_scoped_smoke_cells.jsonl"
                ),
            }
            (
                approval_dir / "gpt_model_scoped_gate1_approval.json"
            ).write_text(json.dumps(approval), encoding="utf-8")

            with patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT",
                smoke,
            ):
                errors = validate_gpt_model_scoped_gate1(formal)

            self.assertEqual(errors, [])
            event_path = next(
                smoke.glob("cells/*/attempt_*/model_identity_events.jsonl")
            )
            events = read_jsonl(event_path)
            events[0]["post_approval_tamper"] = True
            self._write_rows(event_path, events)
            with patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT",
                smoke,
            ):
                errors = validate_gpt_model_scoped_gate1(formal)
            self.assertIn(
                "GPT model-scoped audited artifact tree changed",
                errors,
            )
            events[0].pop("post_approval_tamper")
            self._write_rows(event_path, events)
            chosen_path = next(smoke.glob("cells/*/chosen_result.json"))
            chosen = json.loads(chosen_path.read_text(encoding="utf-8"))
            chosen["post_approval_tamper"] = True
            chosen_path.write_text(json.dumps(chosen), encoding="utf-8")
            with patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "DEFAULT_GPT_MODEL_SCOPED_SMOKE_OUTPUT_ROOT",
                smoke,
            ):
                errors = validate_gpt_model_scoped_gate1(formal)
            self.assertIn(
                "GPT model-scoped audited artifact tree changed",
                errors,
            )

    def test_formal_gpt_cell_is_rejected_without_gate1_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_gpt = next(
                cell
                for cell in scheduled_cells(build_manifest())
                if cell["model"] == "gpt54"
            )
            args = Namespace(
                output_root=root,
                instrumentation_smoke=False,
                sonnet_auxiliary_smoke=False,
                gpt_model_scoped_smoke=False,
                manifest_only=False,
                only_cell_id=None,
                availability_gate=True,
                availability_poll_sec=1,
                availability_max_wait_sec=1,
                task_timeout_sec=1,
                max_new_cells=1,
            )
            with patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "first_incomplete_scheduled_cell",
                return_value=first_gpt,
            ):
                result = run_pilot(args)

            self.assertEqual(result, 2)
            self.assertEqual(list((root / "cells").glob("*")), [])

    def test_same_process_crossing_into_gpt_rechecks_gate1(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ordered = scheduled_cells(build_manifest())
            first_sonnet = next(
                cell
                for cell in ordered
                if cell["model"] == "claude_sonnet_4_6_litellm"
            )
            args = Namespace(
                output_root=root,
                instrumentation_smoke=False,
                sonnet_auxiliary_smoke=False,
                gpt_model_scoped_smoke=False,
                manifest_only=False,
                only_cell_id=None,
                availability_gate=True,
                availability_poll_sec=1,
                availability_max_wait_sec=1,
                task_timeout_sec=1,
                max_new_cells=None,
            )

            def completed_sonnet(_, cell):
                return (
                    {"outcome": "success"}
                    if cell["model"] == "claude_sonnet_4_6_litellm"
                    else None
                )

            with patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "first_incomplete_scheduled_cell",
                return_value=first_sonnet,
            ), patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot.result_for_cell",
                side_effect=completed_sonnet,
            ), patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot.preflight",
                return_value=[],
            ), patch(
                "web_agent_benchmark.evaluation."
                "run_reflection_history_pilot."
                "validate_gpt_model_scoped_gate1",
                return_value=["independent approval missing"],
            ) as gate:
                result = run_pilot(args)

            self.assertEqual(result, 2)
            gate.assert_called_once_with(root.resolve())

    def test_checkpoint_audit_accepts_append_only_abort_then_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._build_checkpoint_fixture(
                root,
                aborted_first_start=True,
            )

            stage = audit_stage(root, 2)
            checkpoint = audit_checkpoint(root, expected_completed=64)

            self.assertTrue(
                stage["approved_by_automated_audit"],
                stage["errors"],
            )
            self.assertTrue(checkpoint["approved"], checkpoint["errors"])

    def _prepare_recovery_prefix_fixture(
        self,
        root: Path,
    ) -> tuple[list[dict], list[dict]]:
        manifest, rows, _ = self._build_checkpoint_fixture(root)
        expected = scheduled_cells(manifest)[:64]
        row_by_id = {
            row["pilot_cell"]["cell_id"]: row for row in rows
        }
        aggregate_rows = [
            row_by_id[cell["cell_id"]]
            for cell in manifest
            if cell["cell_id"] in row_by_id
        ]
        self._write_rows(root / "runs.jsonl", aggregate_rows)
        checkpoints = []
        for cell in expected:
            row = row_by_id[cell["cell_id"]]
            checkpoints.append({
                "timestamp": "2026-07-27T00:00:01+00:00",
                "cell_id": cell["cell_id"],
                "condition_order": cell["condition_order"],
                "attempt_count": 1,
                "chosen_attempt": row["pilot_attempt"],
                "outcome": row["outcome"],
                "error_attribution": row["error_attribution"],
                "scheduling_execution_sequence": row[
                    "pilot_scheduling"
                ]["execution_sequence"],
            })
        self._write_rows(root / "checkpoint_manifest.jsonl", checkpoints)
        return manifest, aggregate_rows

    def test_recovery_prefix_audit_rejects_reordered_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, rows = self._prepare_recovery_prefix_fixture(root)
            self._write_rows(root / "runs.jsonl", list(reversed(rows)))

            report = audit_recovery_prefix(root, expected_completed=64)

            self.assertFalse(report["approved"])
            self.assertIn("aggregate order", " ".join(report["errors"]))

    def test_recovery_prefix_audit_binds_chosen_result_and_checkpoint(self):
        for mutation in ("chosen", "result", "checkpoint"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, rows = self._prepare_recovery_prefix_fixture(root)
                row = rows[0]
                cell_id = row["pilot_cell"]["cell_id"]
                if mutation == "chosen":
                    path = root / "cells" / cell_id / "chosen_result.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["outcome"] = "misleading_failure"
                    path.write_text(json.dumps(value), encoding="utf-8")
                elif mutation == "result":
                    path = root / row["pilot_attempt_dir"] / "result.json"
                    value = json.loads(path.read_text(encoding="utf-8"))
                    value["outcome"] = "misleading_failure"
                    path.write_text(json.dumps(value), encoding="utf-8")
                else:
                    checkpoints = read_jsonl(root / "checkpoint_manifest.jsonl")
                    checkpoints[0]["outcome"] = "misleading_failure"
                    self._write_rows(
                        root / "checkpoint_manifest.jsonl",
                        checkpoints,
                    )

                report = audit_recovery_prefix(root, expected_completed=64)

                self.assertFalse(report["approved"])

    def test_recovery_prefix_audit_rejects_forged_status_and_identity(self):
        for mutation in ("status", "identity"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, rows = self._prepare_recovery_prefix_fixture(root)
                row = rows[0]
                attempt_dir = root / row["pilot_attempt_dir"]
                if mutation == "status":
                    path = attempt_dir / "attempt_status.json"
                    status = json.loads(path.read_text(encoding="utf-8"))
                    status["actual_http_request_count"] = 9
                    path.write_text(json.dumps(status), encoding="utf-8")
                    statuses = read_jsonl(root / "attempt_manifest.jsonl")
                    statuses[0]["actual_http_request_count"] = 9
                    self._write_rows(root / "attempt_manifest.jsonl", statuses)
                else:
                    path = attempt_dir / "model_identity_events.jsonl"
                    events = read_jsonl(path)
                    events[0]["response_model"] = "forged-deployment"
                    self._write_rows(path, events)

                report = audit_recovery_prefix(root, expected_completed=64)

                self.assertFalse(report["approved"])

    def test_recovery_prefix_audit_rejects_future_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, _ = self._prepare_recovery_prefix_fixture(root)
            future = scheduled_cells(manifest)[64]
            attempt = root / "cells" / future["cell_id"] / "attempt_01"
            attempt.mkdir(parents=True)
            (attempt / "attempt_status.json").write_text(
                "{}\n",
                encoding="utf-8",
            )

            report = audit_recovery_prefix(root, expected_completed=64)

            self.assertFalse(report["approved"])
            self.assertIn("outside", " ".join(report["errors"]))

    def test_recovery_inventory_detects_screenshot_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, rows = self._prepare_recovery_prefix_fixture(root)
            cell_id = rows[0]["pilot_cell"]["cell_id"]
            inventory = recovery_inventory(root, [cell_id])
            self.assertEqual(
                verify_preserved_inventory(root, inventory["artifacts"]),
                [],
            )
            screenshot = next((root / "cells" / cell_id).rglob("*.png"))
            screenshot.write_bytes(b"mutated")

            self.assertTrue(
                any(
                    "mutated preserved artifact" in error
                    for error in verify_preserved_inventory(
                        root,
                        inventory["artifacts"]
                    )
                )
            )

    def test_recovery_prefix_audit_rejects_duplicate_checkpoint_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_recovery_prefix_fixture(root)
            checkpoints = read_jsonl(root / "checkpoint_manifest.jsonl")
            self._write_rows(
                root / "checkpoint_manifest.jsonl",
                [*checkpoints, checkpoints[-1]],
            )

            report = audit_recovery_prefix(root, expected_completed=64)

            self.assertFalse(report["approved"])
            joined = " ".join(report["errors"])
            self.assertIn("duplicate", joined)

    def test_recovery_materializer_idempotent_branch_never_appends(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materialization = root / MATERIALIZATION_RELATIVE_PATH
            materialization.parent.mkdir(parents=True)
            expected = {
                "event": "gpt64_overrun_recovery_materialization",
                "no_model_request": True,
            }
            materialization.write_text(
                json.dumps(expected),
                encoding="utf-8",
            )
            sentinel = root / "attempt_manifest.jsonl"
            sentinel.write_text("sentinel\n", encoding="utf-8")
            with patch(
                "web_agent_benchmark.evaluation."
                "materialize_reflection_history_gpt64_recovery."
                "validate_existing_materialization"
            ) as validate:
                observed = materialize_gpt64_recovery(root)

            validate.assert_called_once_with(root, expected)
            self.assertEqual(observed, expected)
            self.assertEqual(
                sentinel.read_text(encoding="utf-8"),
                "sentinel\n",
            )

    def test_false_stop_materializer_exact_success_output(self):
        with false_stop_recovery_fixture() as (root, cell, attempt_dir):
            report = false_stop_recovery.materialize(root)

            self.assertTrue(report["no_model_request"])
            self.assertTrue(report["audit_approved"])
            self.assertEqual(report["progress"]["completed_cells"], 1)
            self.assertEqual(report["progress"]["missing_cells"], 0)
            self.assertFalse(
                report["interface_stop_state"]["triggered"]
            )
            status = json.loads(
                (attempt_dir / "attempt_status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIsNone(status["return_code"])
            self.assertIsNone(status["duration_sec"])
            self.assertIsNone(status["port"])
            self.assertEqual(
                status["cleanup_status"],
                "recovered_after_parent_interruption",
            )
            self.assertEqual(status["actual_http_request_count"], 1)
            self.assertEqual(
                len(read_jsonl(root / "runs.jsonl")),
                1,
            )
            self.assertEqual(
                len(read_jsonl(root / "attempt_manifest.jsonl")),
                1,
            )
            self.assertEqual(
                len(read_jsonl(root / "checkpoint_manifest.jsonl")),
                1,
            )
            events = read_jsonl(root / "scheduling_execution_log.jsonl")
            self.assertEqual(
                [event["event_type"] for event in events],
                ["cell_start", "cell_finish"],
            )
            chosen = json.loads(
                (
                    root
                    / "cells"
                    / cell["cell_id"]
                    / "chosen_result.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                chosen["pilot_scheduling"]["execution_sequence"],
                1,
            )

    def test_false_stop_materializer_rejects_root_inventory_mutation(self):
        with false_stop_recovery_fixture() as (root, _, _):
            (root / "unrelated_preserved.txt").write_text(
                "mutated\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "whole-root artifact tree changed",
            ):
                false_stop_recovery.materialize(root)

    def test_false_stop_materializer_rejects_invalid_identity_events(self):
        with false_stop_recovery_fixture(
            invalid_identity=True
        ) as (root, _, _):
            with self.assertRaisesRegex(
                RuntimeError,
                "identity event evidence is invalid",
            ):
                false_stop_recovery.materialize(root)

    def test_false_stop_materializer_rejects_partial_parent_artifacts(self):
        with false_stop_recovery_fixture(
            partial_parent=True
        ) as (root, _, _):
            with self.assertRaisesRegex(
                RuntimeError,
                "partially materialized",
            ):
                false_stop_recovery.materialize(root)

    def test_false_stop_materializer_rejects_lock_contention(self):
        with false_stop_recovery_fixture() as (root, _, _):
            lock = acquire_output_root_lock(root)
            self.assertIsNotNone(lock)
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Another pilot process holds",
                ):
                    false_stop_recovery.materialize_with_lock(root)
            finally:
                lock.close()

    def test_false_stop_materializer_rejects_report_inventory_tamper(self):
        with false_stop_recovery_fixture() as (root, _, _):
            false_stop_recovery.materialize(root)
            report_path = (
                root / false_stop_recovery.MATERIALIZATION_RELATIVE_PATH
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["preserved_root_artifact_inventory"] = (
                report["preserved_root_artifact_inventory"][1:]
            )
            report_path.write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                RuntimeError,
                "inventory count is invalid",
            ):
                false_stop_recovery.materialize(root)

    def test_false_stop_materializer_second_call_is_byte_identical(self):
        with false_stop_recovery_fixture() as (root, _, _):
            first = false_stop_recovery.materialize(root)
            before = {
                path.relative_to(root).as_posix(): sha256_file(path)
                for path in root.rglob("*")
                if path.is_file()
            }
            second = false_stop_recovery.materialize(root)
            after = {
                path.relative_to(root).as_posix(): sha256_file(path)
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(second, first)
            self.assertEqual(after, before)

    def test_checkpoint_audit_end_to_end_and_fail_closed_mutations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, rows, schedule_sha = self._build_checkpoint_fixture(root)
            report = audit_checkpoint(root, expected_completed=64)
            self.assertTrue(report["approved"], report["errors"])
            self.assertEqual(report["interface_error_count"], 0)

            broken_history = json.loads(json.dumps(rows))
            broken_history[0]["trace"][0]["pilot_history"].pop(
                "history_payload_sha256"
            )
            chosen = (
                root
                / "cells"
                / broken_history[0]["pilot_cell"]["cell_id"]
                / "chosen_result.json"
            )
            self._write_rows(root / "runs.jsonl", broken_history)
            chosen.write_text(json.dumps(broken_history[0]), encoding="utf-8")
            report = audit_checkpoint(root, expected_completed=64)
            self.assertFalse(report["approved"])
            self.assertIn(
                "history_payload_sha256",
                " ".join(report["errors"]),
            )

            self._write_rows(root / "runs.jsonl", rows)
            chosen.write_text(json.dumps(rows[0]), encoding="utf-8")
            extra_cell = scheduled_cells(manifest)[64]
            extra = (
                root
                / "cells"
                / extra_cell["cell_id"]
                / "chosen_result.json"
            )
            extra.parent.mkdir(parents=True)
            extra.write_text('{"outcome":"success"}', encoding="utf-8")
            report = audit_checkpoint(root, expected_completed=64)
            self.assertFalse(report["approved"])
            self.assertIn("chosen_result", " ".join(report["errors"]))
            extra.unlink()

            events = read_jsonl(root / "scheduling_execution_log.jsonl")
            events.append({
                "event_type": "cell_start",
                "cell_id": extra_cell["cell_id"],
                "execution_sequence": 65,
                "started_at": "2026-07-27T00:01:00+00:00",
                "original_condition_order": extra_cell["condition_order"],
                "model_queue": extra_cell["model"],
                "scheduling_deviation_sha256": schedule_sha,
            })
            self._write_rows(root / "scheduling_execution_log.jsonl", events)
            report = audit_checkpoint(root, expected_completed=64)
            self.assertFalse(report["approved"])
            joined = " ".join(report["errors"])
            self.assertIn("in-flight", joined)
            self.assertIn("beyond", joined)

    def test_usage_normalizes_chat_and_messages_token_names(self):
        row = {
            "trace": [
                {
                    "action": {
                        "_response_metadata": {
                            "usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 3,
                                "total_tokens": 13,
                            },
                        },
                    },
                },
                {
                    "action": {
                        "_response_metadata": {
                            "usage": {
                                "input_tokens": 20,
                                "output_tokens": 5,
                                "total_tokens": 25,
                            },
                        },
                    },
                },
            ],
        }
        self.assertEqual(
            usage(row),
            {
                "prompt_tokens": 30,
                "completion_tokens": 8,
                "total_tokens": 38,
            },
        )

    def test_preregistered_manifest_has_exact_matrix(self):
        manifest = build_manifest()
        self.assertEqual(len(manifest), 512)
        self.assertEqual(sum(row["benchmark"] == "official" for row in manifest), 384)
        self.assertEqual(sum(row["benchmark"] == "clean" for row in manifest), 128)
        self.assertEqual(len({row["cell_id"] for row in manifest}), 512)
        self.assertEqual(manifest, build_manifest())

    def test_availability_schedule_is_a_stable_model_partition(self):
        manifest = build_manifest()
        scheduled = scheduled_cells(manifest)
        self.assertEqual(len(scheduled), 512)
        self.assertEqual(
            [row["cell_id"] for row in scheduled[:256]],
            [
                row["cell_id"]
                for row in manifest
                if row["model"] == "claude_sonnet_4_6_litellm"
            ],
        )
        self.assertEqual(
            [row["cell_id"] for row in scheduled[256:]],
            [
                row["cell_id"]
                for row in manifest
                if row["model"] == "gpt54"
            ],
        )
        self.assertEqual(
            {row["cell_id"] for row in scheduled},
            {row["cell_id"] for row in manifest},
        )

    def test_scheduling_deviation_is_frozen_before_formal_results(self):
        manifest = build_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "preregistered_cells.jsonl"
            manifest_path.write_text(
                "".join(json.dumps(row) + "\n" for row in manifest),
                encoding="utf-8",
            )
            schedule_path = prepare_scheduling_deviation(
                root,
                cells=manifest,
                manifest_path=manifest_path,
            )
            first_hash = sha256_file(schedule_path)
            self.assertEqual(
                first_hash,
                "fa7325dcf6d3e276f615ef1cdacd1f94160c29d293a744ced2d9cab6c720520e",
            )
            self.assertEqual(
                prepare_scheduling_deviation(
                    root,
                    cells=manifest,
                    manifest_path=manifest_path,
                ),
                schedule_path,
            )
            self.assertEqual(sha256_file(schedule_path), first_hash)
            schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
            self.assertEqual(
                schedule["approval_marker"],
                "APPROVE AVAILABILITY-STRATIFIED SCHEDULING",
            )
            self.assertNotIn("sk-", json.dumps(schedule))
            prepare_runtime_config(
                root,
                manifest_path=manifest_path,
                experiment_kind="formal_512_cell_pilot",
                scheduling_path=schedule_path,
            )
            config = json.loads(
                (root / "pilot_run_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                config["scheduling_deviation_sha256"],
                first_hash,
            )

    def test_scheduling_deviation_spec_preserves_original_orders(self):
        manifest = build_manifest()
        spec = scheduling_deviation_spec(
            manifest,
            manifest_sha256="frozen-sha",
        )
        self.assertEqual(spec["cell_count"], 512)
        self.assertEqual(
            [queue["model"] for queue in spec["queues"]],
            ["claude_sonnet_4_6_litellm", "gpt54"],
        )
        for queue in spec["queues"]:
            self.assertEqual(
                queue["original_condition_orders"],
                sorted(queue["original_condition_orders"]),
            )

    def test_missing_schedule_finish_is_reconciled_append_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cell = {
                "cell_id": "scheduled-cell",
                "condition_order": 7,
                "model": "claude_sonnet_4_6_litellm",
            }
            chosen = root / "cells" / cell["cell_id"] / "chosen_result.json"
            chosen.parent.mkdir(parents=True)
            chosen.write_text(
                json.dumps({
                    "outcome": "success",
                    "pilot_attempt": 1,
                    "pilot_scheduling": {"execution_sequence": 3},
                }),
                encoding="utf-8",
            )
            log = root / "scheduling_execution_log.jsonl"
            log.write_text(
                json.dumps({
                    "event_type": "cell_start",
                    "cell_id": cell["cell_id"],
                    "execution_sequence": 3,
                }) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                reconcile_scheduling_finishes(root, [cell]),
                1,
            )
            self.assertEqual(
                reconcile_scheduling_finishes(root, [cell]),
                0,
            )
            events = read_jsonl(log)
            self.assertEqual(len(events), 2)
            self.assertTrue(events[1]["recovered_from_chosen_result"])

    def test_interrupted_schedule_start_is_reconciled_as_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cell = {
                "cell_id": "interrupted-cell",
                "condition_order": 9,
                "model": "claude_sonnet_4_6_litellm",
            }
            log = root / "scheduling_execution_log.jsonl"
            self._write_rows(log, [{
                "event_type": "cell_start",
                "cell_id": cell["cell_id"],
                "execution_sequence": 1,
                "original_condition_order": 9,
                "model_queue": cell["model"],
            }])
            self.assertEqual(
                reconcile_scheduling_finishes(root, [cell]),
                1,
            )
            self.assertEqual(
                reconcile_scheduling_finishes(root, [cell]),
                0,
            )
            events = read_jsonl(log)
            self.assertEqual(events[-1]["event_type"], "cell_abort")
            self.assertEqual(
                events[-1]["reason"],
                "process_interruption_detected_at_resume",
            )

    def test_formal_results_must_be_a_strict_schedule_prefix(self):
        cells = scheduled_cells(build_manifest())[:3]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(
                first_incomplete_scheduled_cell(root, cells)["cell_id"],
                cells[0]["cell_id"],
            )
            first = root / "cells" / cells[0]["cell_id"] / "chosen_result.json"
            first.parent.mkdir(parents=True)
            first.write_text('{"outcome":"success"}\n', encoding="utf-8")
            self.assertEqual(
                first_incomplete_scheduled_cell(root, cells)["cell_id"],
                cells[1]["cell_id"],
            )
            third = root / "cells" / cells[2]["cell_id"] / "chosen_result.json"
            third.parent.mkdir(parents=True)
            third.write_text('{"outcome":"success"}\n', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "strict prefix"):
                first_incomplete_scheduled_cell(root, cells)

    def test_quarantined_output_root_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incident = root / CONCURRENCY_INCIDENT_FILENAME
            incident.write_text(
                json.dumps({
                    "excluded_from_analysis": True,
                    "reason": "test concurrency incident",
                }),
                encoding="utf-8",
            )
            before = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }

            result = run_pilot(Namespace(
                output_root=root,
                instrumentation_smoke=False,
                sonnet_auxiliary_smoke=False,
            ))

            after = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(result, 2)
            self.assertEqual(after, before)
            self.assertNotIn(RUNNER_LOCK_FILENAME, after)

    def test_second_runner_lock_failure_leaves_output_tree_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_lock = acquire_output_root_lock(root)
            self.assertIsNotNone(first_lock)
            before = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            try:
                result = run_pilot(Namespace(
                    output_root=root,
                    instrumentation_smoke=False,
                    sonnet_auxiliary_smoke=False,
                ))
            finally:
                fcntl.flock(first_lock.fileno(), fcntl.LOCK_UN)
                first_lock.close()

            after = {
                str(path.relative_to(root)): path.read_bytes()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(result, 2)
            self.assertEqual(after, before)

    def test_review_provenance_is_frozen_and_rejects_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = prepare_review_provenance(root)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                review_provenance_spec(),
            )
            self.assertEqual(prepare_review_provenance(root), path)
            changed = review_provenance_spec()
            changed["reuse_from_quarantined_root"]["attempts"] = 1
            path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "provenance changed"):
                prepare_review_provenance(root)

    def test_formal_manifest_mode_cannot_disable_availability_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_pilot(Namespace(
                output_root=Path(temporary),
                instrumentation_smoke=False,
                manifest_only=True,
                only_cell_id=None,
                availability_gate=False,
                availability_poll_sec=1,
                availability_max_wait_sec=1,
                task_timeout_sec=1,
                max_new_cells=None,
            ))
        self.assertEqual(result, 2)

    def test_instrumentation_smoke_has_frozen_four_way_mapping(self):
        manifest = build_smoke_manifest()
        self.assertEqual(len(manifest), 4)
        self.assertEqual(
            {row["benchmark"] for row in manifest},
            {"official", "clean"},
        )
        self.assertEqual(
            {row["model"] for row in manifest},
            {"gpt54", "claude_sonnet_4_6_litellm"},
        )
        self.assertEqual(
            {row["condition"] for row in manifest},
            {
                "no_history",
                "previous_step",
                "full_history",
                "structured_falsification",
            },
        )
        self.assertTrue(all(not row["formal_experiment_cell"] for row in manifest))

    def test_sonnet_auxiliary_smoke_is_nonformal_and_not_gpt_evidence(self):
        manifest = build_sonnet_auxiliary_smoke_manifest()
        self.assertEqual(len(manifest), 2)
        self.assertEqual(
            {row["model"] for row in manifest},
            {"claude_sonnet_4_6_litellm"},
        )
        self.assertEqual(
            {row["condition"] for row in manifest},
            {"no_history", "full_history"},
        )
        self.assertTrue(all(not row["formal_experiment_cell"] for row in manifest))
        self.assertTrue(all(not row["counts_as_gpt_smoke"] for row in manifest))
        self.assertTrue(
            all(row["model_scoped_gate"] == "sonnet_only" for row in manifest)
        )

    def test_gpt_model_scoped_smoke_has_frozen_four_way_mapping(self):
        manifest = build_gpt_model_scoped_smoke_manifest()
        self.assertEqual(len(manifest), 4)
        self.assertEqual({row["model"] for row in manifest}, {"gpt54"})
        self.assertEqual(
            {row["condition"] for row in manifest},
            {
                "no_history",
                "previous_step",
                "full_history",
                "structured_falsification",
            },
        )
        self.assertEqual(
            sum(row["benchmark"] == "official" for row in manifest),
            2,
        )
        self.assertEqual(
            sum(row["benchmark"] == "clean" for row in manifest),
            2,
        )
        self.assertTrue(all(not row["formal_experiment_cell"] for row in manifest))
        self.assertTrue(all(row["counts_as_gpt_smoke"] for row in manifest))
        self.assertTrue(
            all(row["model_scoped_gate"] == "gpt_only" for row in manifest)
        )

    def test_runtime_routes_are_direct_deployments_without_credentials(self):
        routes = runtime_routes()
        serialized = json.dumps(routes)
        self.assertNotIn("sk-", serialized)
        self.assertTrue(routes["strict_response_model_identity"])
        self.assertEqual(routes["review_status"], "pending")
        self.assertEqual(
            routes["models"]["gpt54"]["api_style"],
            "chat_completions",
        )
        self.assertEqual(
            routes["models"]["claude_sonnet_4_6_litellm"]["api_style"],
            "messages",
        )
        for model in routes["models"].values():
            self.assertRegex(
                model["requested_deployment"],
                r"^[0-9a-f]{8}-[0-9a-f-]{27}$",
            )

    def test_identity_evidence_is_a_fail_closed_attempt_invariant(self):
        deployment = "4bb890af-7111-410c-9344-061eb678f4ec"
        row = {
            "trace": [{
                "action": {
                    "action": "click_link",
                    "_raw": "{}",
                    "_response_metadata": {
                        "requested_deployment": deployment,
                        "response_model": deployment,
                        "identity_validated": True,
                    },
                },
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "identity.jsonl"
            log.write_text(
                json.dumps({
                    "event_type": "http_request",
                    "result": "success",
                    "requested_deployment": deployment,
                    "response_model": deployment,
                    "identity_validated": True,
                }) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(validate_identity_evidence(
                row=row,
                identity_log=log,
                expected_deployment=deployment,
            )["valid"])
            row["trace"][0]["action"].pop("_response_metadata")
            result = validate_identity_evidence(
                row=row,
                identity_log=log,
                expected_deployment=deployment,
            )
            self.assertFalse(result["valid"])
            self.assertIn("lacks response metadata", " ".join(result["errors"]))

    def test_pre_model_runner_error_keeps_original_attribution(self):
        row = {
            "outcome": "agent_error",
            "error_attribution": "runner_exception",
            "exception": "BrowserType.launch: executable does not exist",
            "trace": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = validate_identity_evidence(
                row=row,
                identity_log=Path(temporary) / "missing.jsonl",
                expected_deployment="deployment",
            )
        self.assertTrue(result["valid"])
        self.assertEqual(
            result["applicability"],
            "not_applicable_before_first_model_request",
        )
        self.assertEqual(row["error_attribution"], "runner_exception")
        self.assertFalse(is_retryable_interface_error(row))

    def test_high_oscillation_selection_revalidates(self):
        self.assertEqual(validate_selection()["violations"], [])

    def test_only_transient_interface_errors_are_retryable(self):
        transient_messages = [
            "ReadTimeout: upstream HTTP 503",
            "AIME LiteLLM returned empty content",
            "AIME LiteLLM response has no choices",
            "Read timed out. (read timeout=300)",
            (
                "AIME LiteLLM model identity mismatch: "
                "requested='a' response_model='b'"
            ),
            "model identity audit failed: identity log is missing or empty",
        ]
        schema = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception": "JSONDecodeError: malformed action",
        }
        browser = {
            "outcome": "agent_error",
            "error_attribution": "runner_exception",
            "exception": "Element not found",
        }
        for message in transient_messages:
            self.assertTrue(is_retryable_interface_error({
                "outcome": "agent_error",
                "error_attribution": "llm_action_generation_error",
                "exception": message,
            }))
        self.assertFalse(is_retryable_interface_error(schema))
        self.assertFalse(is_retryable_interface_error(browser))

    def test_stop_rule_classifier_unwraps_identity_audit_failures(self):
        transport = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception": (
                "model identity audit failed: identity event 0 "
                "is not validated"
            ),
            "exception_before_identity_rejection": (
                "ReadTimeout: upstream read timed out"
            ),
            "pilot_identity_audit": {
                "valid": False,
                "errors": ["identity event 0 is not validated"],
            },
        }
        harness = {
            **transport,
            "exception_before_identity_rejection": (
                "Locator.select_option: Unexpected token while parsing "
                "CSS selector"
            ),
            "pilot_identity_audit": {
                "valid": False,
                "errors": [
                    "trace contains no auditable model-generated action"
                ],
            },
        }
        parser = {
            **transport,
            "exception_before_identity_rejection": (
                "RuntimeError: Unsupported browser action"
            ),
            "pilot_identity_audit": {
                "valid": False,
                "errors": [
                    "trace contains no auditable model-generated action"
                ],
            },
        }
        self.assertTrue(is_retryable_interface_error(harness))
        self.assertTrue(is_retryable_interface_error(parser))
        self.assertTrue(is_stop_rule_interface_error(transport))
        self.assertFalse(is_stop_rule_interface_error(harness))
        self.assertFalse(is_stop_rule_interface_error(parser))
        self.assertEqual(
            classify_stop_rule_interface_error(harness)["category"],
            "non_interface_harness",
        )
        self.assertEqual(
            classify_stop_rule_interface_error(parser)["category"],
            "non_interface_parser",
        )

    def test_formal_gpt_stop_rule_regression_sequences(self):
        root = (
            Path(__file__).resolve().parents[2]
            / "web_agent_benchmark"
            / "pair_evaluation_records"
            / "reflection_history_pilot_20260727_restart1"
        )
        if not (root / "runs.jsonl").is_file():
            self.skipTest("formal reflection pilot is not available")
        rows = [
            row
            for row in read_jsonl(root / "runs.jsonl")
            if int(
                (row.get("pilot_scheduling") or {}).get(
                    "execution_sequence"
                )
                or 0
            )
            >= 257
            and row.get("outcome") == "agent_error"
        ]
        by_sequence = {
            int(row["pilot_scheduling"]["execution_sequence"]): row
            for row in rows
        }
        expected_interface = {
            280,
            281,
            282,
            283,
            284,
            285,
            286,
            287,
            288,
            297,
            298,
        }
        observed_interface = {
            sequence
            for sequence, row in by_sequence.items()
            if is_stop_rule_interface_error(row)
        }
        self.assertEqual(observed_interface, expected_interface)
        observed_effective_interface = {
            sequence
            for sequence, row in by_sequence.items()
            if classify_effective_interface_error(
                output_root=root,
                row=row,
            )["is_interface_error"]
        }
        self.assertEqual(
            observed_effective_interface,
            expected_interface,
        )
        self.assertEqual(
            classify_effective_interface_error(
                output_root=root,
                row=by_sequence[356],
            )["category"],
            "non_interface_harness",
        )
        self.assertEqual(
            classify_effective_interface_error(
                output_root=root,
                row=by_sequence[415],
            )["category"],
            "non_interface_harness",
        )
        self.assertEqual(
            classify_effective_interface_error(
                output_root=root,
                row=by_sequence[485],
            )["category"],
            "non_interface_parser",
        )

    def test_unknown_http_and_identity_failures_use_physical_evidence(self):
        deployment = MODEL_CONFIGS["gpt54"]["deployment_id"]
        row = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception_before_identity_rejection": (
                "Provider rejected the request"
            ),
            "pilot_cell": {
                "cell_id": "physical-identity",
                "condition": "full_history",
                "model": "gpt54",
            },
            "pilot_attempt_dir": "cells/physical-identity/attempt_01",
            "pilot_actual_http_request_count": 1,
        }
        invalid_events = [
            {
                "event_type": "http_request",
                "result": "exception",
                "status_code": status_code,
                "requested_deployment": deployment,
                "response_model": None,
                "identity_validated": False,
            }
            for status_code in (401, 403, 404, 520)
        ] + [
            {
                "event_type": "http_request",
                "result": "success",
                "status_code": 200,
                "requested_deployment": deployment,
                "response_model": "wrong-deployment",
                "identity_validated": True,
            },
        ]
        for event in invalid_events:
            with self.subTest(event=event):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    event_path = (
                        root
                        / row["pilot_attempt_dir"]
                        / "model_identity_events.jsonl"
                    )
                    event_path.parent.mkdir(parents=True)
                    event_path.write_text(
                        json.dumps(event) + "\n",
                        encoding="utf-8",
                    )
                    errors = non_interface_failure_identity_errors(
                        output_root=root,
                        row=row,
                    )
                    self.assertEqual(errors, [])
                    physical = classify_physical_agent_error_evidence(
                        output_root=root,
                        row=row,
                    )
                    self.assertTrue(physical["is_interface_error"])
                    effective = classify_effective_interface_error(
                        output_root=root,
                        row=row,
                    )
                    self.assertTrue(effective["is_interface_error"])
                    self.assertEqual(
                        effective["category"],
                        "interface_physical_event",
                    )
                    state = interface_stop_rule_state(
                        [row],
                        [{"condition": "full_history"}],
                        output_root=root,
                    )
                    self.assertTrue(state["triggered"])
                    self.assertFalse(
                        state["classification_error_triggered"]
                    )
                    self.assertEqual(
                        state["failure_classification_counts"],
                        {"interface_physical_event": 1},
                    )

    def test_missing_physical_identity_evidence_stops_classification(self):
        row = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception_before_identity_rejection": (
                "Provider returned an unclassified failure"
            ),
            "pilot_cell": {
                "cell_id": "missing-physical",
                "condition": "full_history",
                "model": "gpt54",
            },
            "pilot_attempt_dir": "cells/missing-physical/attempt_01",
            "pilot_actual_http_request_count": 1,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            effective = classify_effective_interface_error(
                output_root=root,
                row=row,
            )
            self.assertEqual(
                effective["category"],
                "classification_error",
            )
            self.assertTrue(effective["classification_errors"])
            state = interface_stop_rule_state(
                [row],
                [{"condition": "full_history"}],
                output_root=root,
            )
            self.assertTrue(state["triggered"])
            self.assertTrue(state["classification_error_triggered"])

    def test_interface_stop_state_uses_evidence_classifier(self):
        cells = [
            {"condition": condition}
            for condition in (
                "no_history",
                "previous_step",
                "full_history",
                "structured_falsification",
            )
            for _ in range(128)
        ]
        transport = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception_before_identity_rejection": "ReadTimeout",
            "pilot_cell": {
                "condition": "full_history",
                "model": "gpt54",
            },
            "pilot_attempt_dir": "cells/test/attempt_01",
            "pilot_actual_http_request_count": 1,
            "pilot_scheduling": {"execution_sequence": 1},
        }
        parser = {
            **transport,
            "exception": "model identity audit failed",
            "exception_before_identity_rejection": (
                "Unsupported browser action"
            ),
        }
        deployment = MODEL_CONFIGS["gpt54"]["deployment_id"]
        event = {
            "event_type": "http_request",
            "result": "success",
            "status_code": 200,
            "requested_deployment": deployment,
            "response_model": deployment,
            "identity_validated": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event_path = (
                root
                / "cells"
                / "test"
                / "attempt_01"
                / "model_identity_events.jsonl"
            )
            event_path.parent.mkdir(parents=True)
            event_path.write_text(
                json.dumps(event) + "\n",
                encoding="utf-8",
            )
            state = interface_stop_rule_state(
                [dict(transport) for _ in range(6)] + [parser],
                cells,
                output_root=root,
            )
            self.assertFalse(state["triggered"])
            self.assertEqual(
                state["observed_interface_errors_by_condition"][
                    "full_history"
                ],
                6,
            )
            state = interface_stop_rule_state(
                [dict(transport) for _ in range(7)],
                cells,
                output_root=root,
            )
            self.assertTrue(state["triggered"])

    def test_cooldown_abort_does_not_consume_formal_attempt(self):
        cooldown = {
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception": "AIME LiteLLM transient HTTP 429: cooling down",
            "pilot_attempt": 1,
        }
        success = {
            "outcome": "success",
            "error_attribution": "none",
            "pilot_attempt": 1,
        }
        cell = {
            "cell_id": "availability-cell",
            "condition_order": 1,
            "model": "gpt54",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "web_agent_benchmark.evaluation.run_reflection_history_pilot.run_attempt",
                side_effect=[cooldown, success],
            ) as run_attempt_mock, patch(
                "web_agent_benchmark.evaluation.run_reflection_history_pilot.wait_for_deployment"
            ) as wait_mock:
                chosen = execute_cell(
                    output_root=root,
                    cell=cell,
                    task_timeout_sec=10,
                    availability_gate=True,
                    availability_poll_sec=1,
                    availability_max_wait_sec=60,
                )
            self.assertEqual(chosen["outcome"], "success")
            self.assertEqual(chosen["pilot_attempt"], 1)
            self.assertEqual(run_attempt_mock.call_count, 2)
            self.assertEqual(
                [
                    call.kwargs["availability_abort_index"]
                    for call in run_attempt_mock.call_args_list
                ],
                [0, 1],
            )
            wait_mock.assert_called_once()
            checkpoint = read_jsonl(root / "checkpoint_manifest.jsonl")[0]
            self.assertEqual(checkpoint["attempt_count"], 1)

    def test_availability_probe_fails_closed_on_identity_mismatch(self):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"model": "wrong-deployment"}

        with patch.dict(
            os.environ,
            {"AIME_LITELLM_API_KEY": "test-only"},
            clear=False,
        ), patch(
            "web_agent_benchmark.evaluation.run_reflection_history_pilot.requests.post",
            return_value=Response(),
        ):
            event = probe_deployment("gpt54")
        self.assertFalse(event["ready"])
        self.assertEqual(event["probe_state"], "fatal")
        self.assertEqual(event["error_category"], "model_identity_mismatch")
        self.assertTrue(is_availability_error({
            "outcome": "agent_error",
            "error_attribution": "llm_action_generation_error",
            "exception_before_identity_rejection": "HTTP 429 cooling down",
        }))
        self.assertFalse(is_availability_error({
            "outcome": "agent_error",
            "error_attribution": "runner_exception",
            "exception": "Element text happened to say cooling down",
            "trace": [{"error": "HTTP 429"}],
        }))

    def test_availability_probe_rejects_non_object_2xx(self):
        class Response:
            status_code = 200

            @staticmethod
            def json():
                return ["not", "an", "object"]

        with patch.dict(
            os.environ,
            {"AIME_LITELLM_API_KEY": "test-only"},
            clear=False,
        ), patch(
            "web_agent_benchmark.evaluation.run_reflection_history_pilot.requests.post",
            return_value=Response(),
        ):
            event = probe_deployment("gpt54")
        self.assertFalse(event["ready"])
        self.assertEqual(event["probe_state"], "fatal")
        self.assertEqual(event["error_category"], "invalid_json_shape_2xx")

    def test_partial_attempt_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            cell_dir = Path(temporary)
            partial = cell_dir / "attempt_01"
            partial.mkdir()
            (partial / "model_identity_events.jsonl").write_text(
                '{"partial":true}\n',
                encoding="utf-8",
            )
            resumed = fresh_attempt_dir(
                cell_dir,
                attempt=1,
                availability_abort_index=0,
            )
            self.assertEqual(resumed.name, "attempt_01_resume_01")
            resumed.mkdir()
            next_resume = fresh_attempt_dir(
                cell_dir,
                attempt=1,
                availability_abort_index=0,
            )
            self.assertEqual(next_resume.name, "attempt_01_resume_02")

    def test_infrastructure_threshold_prevents_effect_decision(self):
        manifest = [
            {"cell_id": f"{condition}-{index}", "condition": condition}
            for condition in [
                "no_history",
                "previous_step",
                "full_history",
                "structured_falsification",
            ]
            for index in range(20)
        ]
        rows = [
            {
                "cell_id": cell["cell_id"],
                "condition": cell["condition"],
                "interface_error": (
                    cell["condition"] == "previous_step"
                    and cell["cell_id"].endswith(("-0", "-1"))
                ),
                "agent_error": False,
            }
            for cell in manifest
        ]
        result = decision(rows, manifest)
        self.assertEqual(result["decision"], "infrastructure_invalid")
        self.assertFalse(result["effect_comparison_performed"])

    @staticmethod
    def _decision_block(
        *,
        structured_cycle: bool,
        structured_success: bool,
    ):
        manifest = [{"condition": condition} for condition in [
            "no_history",
            "previous_step",
            "full_history",
            "structured_falsification",
        ]]
        values = {
            "no_history": (True, False, True),
            "previous_step": (False, True, False),
            "full_history": (False, True, False),
            "structured_falsification": (
                structured_cycle,
                structured_success,
                structured_cycle,
            ),
        }
        rows = []
        for condition, (cycle, success, harmful) in values.items():
            rows.append({
                "model": "gpt54",
                "benchmark": "official",
                "scenario": "business47",
                "slug": "b010",
                "repetition": 1,
                "condition": condition,
                "interface_error": False,
                "state_action_cycle_incidence": cycle,
                "task_success": success,
                "harmful_submission": harmful,
            })
        return rows, manifest

    def test_harness_fix_requires_structured_to_be_close_to_previous_step(self):
        rows, manifest = self._decision_block(
            structured_cycle=False,
            structured_success=True,
        )
        self.assertEqual(decision(rows, manifest)["decision"], "harness_fix")

    def test_structured_regression_is_not_mislabeled_harness_fix(self):
        rows, manifest = self._decision_block(
            structured_cycle=True,
            structured_success=False,
        )
        self.assertEqual(decision(rows, manifest)["decision"], "no_go")

    def test_manifest_result_bijection_and_frozen_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cell = {
                "cell_id": "cell-a",
                "condition": "no_history",
                "model": "gpt54",
            }
            manifest_path = root / "preregistered_cells.jsonl"
            manifest_path.write_text(json.dumps(cell) + "\n", encoding="utf-8")
            (root / "preregistration.json").write_text(
                json.dumps({"manifest_sha256": sha256_file(manifest_path)}),
                encoding="utf-8",
            )
            routes_path = root / "runtime_routes.json"
            routes_path.write_text(
                json.dumps(runtime_routes()),
                encoding="utf-8",
            )
            (root / "pilot_run_config.json").write_text(
                json.dumps({
                    "runtime_routes_sha256": sha256_file(routes_path),
                }),
                encoding="utf-8",
            )
            row = {
                "pilot_cell": cell,
                "pilot_attempt": 1,
                "pilot_attempt_dir": "cells/cell-a/attempt_01",
                "pilot_identity_audit": {"valid": True},
            }
            chosen = root / "cells" / "cell-a" / "chosen_result.json"
            chosen.parent.mkdir(parents=True)
            chosen.write_text(json.dumps(row), encoding="utf-8")
            result = validate_analysis_inputs(
                root,
                [cell],
                [row],
                allow_incomplete=False,
            )
            self.assertEqual(result["missing_cell_count"], 0)
            with self.assertRaises(RuntimeError):
                validate_analysis_inputs(
                    root,
                    [cell],
                    [row, row],
                    allow_incomplete=False,
                )

    def test_stage_audit_rejects_status_stored_under_another_cell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = build_manifest()
            cell_a = manifest[0]
            cell_b = manifest[1]
            actual_dir = (
                root / "cells" / cell_a["cell_id"] / "attempt_01"
            )
            declared_dir = (
                Path("cells") / cell_b["cell_id"] / "attempt_01"
            )
            actual_dir.mkdir(parents=True)
            status = {
                "cell_id": cell_b["cell_id"],
                "attempt": 1,
                "attempt_dir": str(declared_dir),
                "formal_attempt_consumed": True,
                "availability_aborted": False,
                "actual_http_request_count": 0,
                "outcome": "agent_error",
            }
            (actual_dir / "attempt_status.json").write_text(
                json.dumps(status),
                encoding="utf-8",
            )
            (root / "attempt_manifest.jsonl").write_text(
                json.dumps(status) + "\n",
                encoding="utf-8",
            )

            report = audit_stage(root, 2)

            self.assertTrue(any(
                "not physically stored" in error
                for error in report["errors"]
            ))

    def test_stage_audit_rejects_chosen_unconsumed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = build_manifest()
            cell = manifest[0]
            relative_dir = (
                Path("cells") / cell["cell_id"] / "attempt_01"
            )
            attempt_dir = root / relative_dir
            attempt_dir.mkdir(parents=True)
            status = {
                "cell_id": cell["cell_id"],
                "attempt": 1,
                "attempt_dir": str(relative_dir),
                "formal_attempt_consumed": False,
                "availability_aborted": True,
                "actual_http_request_count": 0,
                "outcome": "agent_error",
            }
            row = {
                "pilot_cell": cell,
                "pilot_attempt": 1,
                "pilot_attempt_dir": str(relative_dir),
                "pilot_actual_http_request_count": 0,
                "pilot_identity_audit": {
                    "expected_deployment": MODEL_CONFIGS[
                        cell["model"]
                    ]["deployment_id"],
                    "valid": False,
                },
                "outcome": "agent_error",
                "error_attribution": "llm_action_generation_error",
                "trace": [],
            }
            (attempt_dir / "attempt_status.json").write_text(
                json.dumps(status),
                encoding="utf-8",
            )
            (attempt_dir / "result.json").write_text(
                json.dumps(row),
                encoding="utf-8",
            )
            chosen_path = (
                root / "cells" / cell["cell_id"] / "chosen_result.json"
            )
            chosen_path.write_text(json.dumps(row), encoding="utf-8")
            (root / "runs.jsonl").write_text(
                json.dumps(row) + "\n",
                encoding="utf-8",
            )
            (root / "attempt_manifest.jsonl").write_text(
                json.dumps(status) + "\n",
                encoding="utf-8",
            )

            report = audit_stage(root, 2)

            self.assertTrue(any(
                "chosen result points to unconsumed attempt" in error
                for error in report["errors"]
            ))

    def test_stage_audit_rejects_future_cell_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            future_cell_id = build_manifest()[-1]["cell_id"]
            chosen = (
                root / "cells" / future_cell_id / "chosen_result.json"
            )
            chosen.parent.mkdir(parents=True)
            chosen.write_text("{}\n", encoding="utf-8")
            attempt = chosen.parent / "attempt_01"
            attempt.mkdir()
            (attempt / "attempt_status.json").write_text(
                "{}\n",
                encoding="utf-8",
            )
            (attempt / "result.json").write_text("{}\n", encoding="utf-8")

            report = audit_stage(root, 2)

            self.assertTrue(any(
                "chosen_result files do not exactly match" in error
                for error in report["errors"]
            ))
            self.assertTrue(any(
                "outside the schedule prefix" in error
                for error in report["errors"]
            ))

    def test_identity_event_sequence_rejects_forged_events(self):
        deployment = "deployment-id"
        events = [
            {
                "event_type": "not_http",
                "request_index": 2,
                "result": "invented",
                "requested_deployment": deployment,
                "request_payload_sha256": "a" * 64,
                "hidden_prompt_terms_seen": [],
            },
        ]

        errors = audit_identity_events(
            events,
            expected_deployment=deployment,
        )

        self.assertTrue(any("invalid event_type" in error for error in errors))
        self.assertTrue(any("not contiguous" in error for error in errors))
        self.assertTrue(any("invalid result" in error for error in errors))

    def test_interface_error_threshold_is_enforced_per_condition(self):
        manifest = build_manifest()
        rows = [
            {
                "pilot_cell": {"condition": "no_history"},
                "outcome": "agent_error",
                "error_attribution": "llm_action_generation_error",
                "exception": "HTTP 503 service unavailable",
            }
            for _ in range(7)
        ]

        observed, allowed, errors = interface_error_threshold(rows, manifest)

        self.assertEqual(allowed["no_history"], 6)
        self.assertEqual(observed["no_history"], 7)
        self.assertTrue(any("no_history" in error for error in errors))

    def test_timeout_cleans_entire_process_group(self):
        command = [
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time;"
                "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
                "time.sleep(60)"
            ),
        ]
        return_code, _, _, timed_out, cleanup = run_process_group(
            command,
            cwd=Path("/tmp"),
            env={},
            timeout_sec=1,
        )
        self.assertEqual(return_code, 124)
        self.assertTrue(timed_out)
        self.assertIn(cleanup, {"terminated_process_group", "killed_process_group"})

    def test_all_four_runners_parse_shared_pilot_contract(self):
        from web_agent_benchmark.evaluation import (
            run_business47,
            run_environment35,
            run_health19,
            run_public39,
        )

        response = json_response = (
            '{"action":{"action":"click_link","text":"Open Form"},'
            '"memory_update":{"current_hypothesis":"inspect",'
            '"supporting_visible_evidence":[],"contradicting_visible_evidence":[],'
            '"tried_actions":[],"rejected_routes":[],"unresolved_question":"",'
            '"next_verification_target":"form"}}'
        )

        def fake_complete(*args, **kwargs):
            return response

        common = {
            "client": object(),
            "state": page_state("http://x/task/x"),
            "screenshot_path": Path("/tmp/not_read.png"),
            "task_goal": "Complete task",
            "misleader_type": "must_not_be_injected",
            "max_output_tokens": 1024,
            "decoding_config": {"temperature": 0.0, "top_p": 1.0, "seed": 12345},
            "history_runtime": HistoryRuntime("no_history"),
        }
        with patch("adversarial_pipeline.llm_client.complete_vision", fake_complete):
            public_action = run_public39.llm_next_action(**common)
            business_action = run_business47.llm_next_action(**common)
        environment_action = run_environment35.llm_next_action(
            **common,
            complete_vision_fn=fake_complete,
        )
        health_action = run_health19.llm_next_action(
            **common,
            complete_vision_fn=fake_complete,
        )
        for action in [
            public_action,
            business_action,
            environment_action,
            health_action,
        ]:
            self.assertEqual(action["action"], "click_link")
            self.assertTrue(action["_pilot_schema_valid"])
            self.assertEqual(
                action["_pilot_memory_update"]["current_hypothesis"],
                "inspect",
            )
            self.assertEqual(
                action["_pilot_history_input"]["history_records_injected"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
