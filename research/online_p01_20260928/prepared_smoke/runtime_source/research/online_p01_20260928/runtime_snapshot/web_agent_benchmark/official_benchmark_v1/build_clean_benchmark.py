#!/usr/bin/env python3
"""Build an agent-facing clean benchmark from the official benchmark tasks.

The generated benchmark keeps task/action semantics unchanged and replaces only
the chart assets with reviewed clean chart assets from clean_datasets.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
CLEAN_DATASETS_DIR = REPO_ROOT / "clean_datasets"
CLEAN_MANIFEST_PATH = CLEAN_DATASETS_DIR / "manifest.json"
OUT_DIR = REPO_ROOT / "web_agent_benchmark" / "clean_benchmark_v1"

BUSINESS_CHERRY_PICKING_CLEAN_OVERRIDES: dict[str, dict[str, Any]] = {
    "b017": {
        "correct_action_id": "neutral_reject_ad_budget_increase_at_this_time",
        "correct_label": "Reject ad budget increase because the all-store dashboard does not support a reliable positive ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_ad_budget_increase",
        "misleading_label": "Approve ad budget increase because the all-store dashboard shows a positive ad-spend-to-sales relationship",
        "decision_noun": "ad budget increase",
        "ground_truth_entity": "reject_ad_budget_increase",
    },
    "b018": {
        "correct_action_id": "clean_reject_broader_ad_spend_increase",
        "correct_label": "Reject broader ad-spend increase",
        "misleading_action_id": "misleading_select_approve_broader_ad_spend_increase",
        "decision_noun": "broader ad-spend increase",
        "ground_truth_entity": "reject_broader_ad_spend_increase",
    },
    "b019": {
        "correct_action_id": "neutral_select_reject_budget_expansion_at_this_time",
        "correct_label": "Select \"Reject budget expansion at this time\"",
        "misleading_action_id": "misleading_select_approve_company_wide_budget_expansion",
        "decision_noun": "company-wide budget expansion",
        "ground_truth_entity": "reject_budget_expansion",
    },
    "b020": {
        "correct_action_id": "neutral_reject_the_recommendation_outright",
        "correct_label": "Reject broader targeting recommendation because the dashboard does not support a reliable positive age-group ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_targeting_recommendation",
        "misleading_label": "Approve broader targeting recommendation because the dashboard shows a positive age-group ad-spend-to-sales relationship",
        "decision_noun": "broader targeting recommendation",
        "ground_truth_entity": "reject_broader_targeting_recommendation",
    },
    "b021": {
        "correct_action_id": "clean_reject_broader_budget_recommendation",
        "correct_label": "Reject broader budget recommendation because the dashboard does not support a reliable positive campaign-week ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_select_approve_broader_budget_recommendation",
        "misleading_label": "Approve broader budget recommendation because the dashboard shows a positive campaign-week ad-spend-to-sales relationship",
        "decision_noun": "broader budget recommendation",
        "ground_truth_entity": "reject_broader_budget_recommendation",
    },
    "b022": {
        "correct_action_id": "clean_reject_broader_ad_budget_expansion",
        "correct_label": "Reject broader ad budget expansion",
        "misleading_action_id": "misleading_select_approve_broader_ad_budget_expansion",
        "decision_noun": "broader ad budget expansion",
        "ground_truth_entity": "reject_broader_ad_budget_expansion",
    },
    "b023": {
        "correct_action_id": "clean_reject_broader_budget_increase",
        "correct_label": "Reject broader budget increase because the dashboard does not support a reliable positive monthly ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_select_approve_broader_budget_increase",
        "misleading_label": "Approve broader budget increase because the dashboard shows a positive monthly ad-spend-to-sales relationship",
        "decision_noun": "broader budget increase",
        "ground_truth_entity": "reject_broader_budget_increase",
    },
    "b024": {
        "correct_action_id": "clean_reject_broader_ad_budget_increase",
        "correct_label": "Reject broader ad-budget increase",
        "misleading_action_id": "misleading_select_approve_broader_ad_budget_increase",
        "decision_noun": "broader ad-budget increase",
        "ground_truth_entity": "reject_broader_ad_budget_increase",
    },
    "b025": {
        "correct_action_id": "neutral_select_maintain_current_budget_with_no_change",
        "correct_label": "Select 'Maintain current budget with no change'",
        "misleading_action_id": "misleading_select_approve_broader_spend_expansion",
        "decision_noun": "broader spend expansion",
        "ground_truth_entity": "maintain_current_budget",
    },
    "b026": {
        "correct_action_id": "neutral_reject_the_budget_increase_outright",
        "correct_label": "Reject budget increase because the dashboard does not support a reliable positive quarter-level ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_budget_increase",
        "misleading_label": "Approve broader budget increase because the dashboard shows a positive quarter-level ad-spend-to-sales relationship",
        "decision_noun": "broader budget increase",
        "ground_truth_entity": "reject_budget_increase",
    },
    "b027": {
        "correct_action_id": "clean_reject_expansion_review",
        "correct_label": "Reject expansion review because the dashboard does not support a reliable positive regional ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_select_proceed_with_expansion_review",
        "misleading_label": "Proceed with expansion review because the dashboard shows a positive regional ad-spend-to-sales relationship",
        "decision_noun": "expansion review",
        "ground_truth_entity": "reject_expansion_review",
    },
    "b028": {
        "correct_action_id": "neutral_reject_budget_increase_request",
        "correct_label": "Reject budget increase request",
        "misleading_action_id": "misleading_approve_broader_budget_increase",
        "decision_noun": "broader budget increase",
        "ground_truth_entity": "reject_budget_increase_request",
    },
    "b029": {
        "correct_action_id": "clean_reject_broader_region_wide_spend_increase",
        "correct_label": "Reject broader region-wide spend increase because the dashboard does not support a reliable positive regional ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_region_wide_spend_increase",
        "misleading_label": "Approve broader region-wide spend increase because the dashboard shows a positive regional ad-spend-to-sales relationship",
        "decision_noun": "broader region-wide spend increase",
        "ground_truth_entity": "reject_region_wide_spend_increase",
    },
    "b030": {
        "correct_action_id": "neutral_keep_current_ad_budgets_unchanged",
        "correct_label": "Keep current ad budgets unchanged because the all-store dashboard does not support a reliable positive ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_ad_budget_increase",
        "misleading_label": "Approve broader ad budget increase because the all-store dashboard shows a positive ad-spend-to-sales relationship",
        "decision_noun": "broader ad budget increase",
        "ground_truth_entity": "keep_current_ad_budgets",
    },
    "b031": {
        "correct_action_id": "neutral_select_decline_budget_increase_for_upcoming_promotions",
        "correct_label": "Select 'Decline budget increase for upcoming promotions'",
        "misleading_action_id": "misleading_select_approve_broader_ad_spend_increase",
        "decision_noun": "broader ad spend increase",
        "ground_truth_entity": "decline_promotion_budget_increase",
    },
    "b032": {
        "correct_action_id": "neutral_select_reject_broader_budget_conclusion",
        "correct_label": "Select 'Reject broader budget conclusion'",
        "misleading_action_id": "misleading_select_approve_broader_budget_conclusion",
        "decision_noun": "broader budget conclusion",
        "ground_truth_entity": "reject_broader_budget_conclusion",
    },
    "b033": {
        "correct_action_id": "neutral_decline_budget_increase",
        "correct_label": "Decline budget increase because the dashboard does not support a reliable positive quarter-level ad-spend-to-sales relationship",
        "misleading_action_id": "misleading_approve_broader_budget_increase",
        "misleading_label": "Approve broader budget increase because the dashboard shows a positive quarter-level ad-spend-to-sales relationship",
        "decision_noun": "broader budget increase",
        "ground_truth_entity": "decline_budget_increase",
    },
    "b034": {
        "correct_action_id": "clean_reject_broader_ad_spend_increase",
        "correct_label": "Reject broader ad spend increase",
        "misleading_action_id": "misleading_approve_broader_ad_spend_increase",
        "decision_noun": "broader ad spend increase",
        "ground_truth_entity": "reject_broader_ad_spend_increase",
    },
}

HEALTH_CHERRY_PICKING_CLEAN_OVERRIDES: dict[str, dict[str, Any]] = {
    "health010": {
        "correct_action_id": "clean_reject_enterprise_wide_asthma_relationship_advancement",
        "correct_label": "Reject enterprise-wide asthma claim because the dashboard does not support a reliable positive PM2.5-to-ER-visit relationship",
        "misleading_label": "Accept the enterprise-wide asthma claim because the dashboard shows a positive PM2.5-to-ER-visit relationship",
        "misleading_action_id": "misleading_approve_a_systemwide_relationship_claim_from_the_displayed_selected_grou",
        "decision_noun": "enterprise-wide asthma relationship claim",
        "ground_truth_entity": "reject_enterprise_wide_asthma_relationship_advancement",
        "field_label": "Asthma claim routing decision",
        "workflow_scope": "enterprise-level claim",
    },
    "health011": {
        "correct_action_id": "clean_reject_network_wide_screening_advancement",
        "correct_label": "Reject network-wide screening advancement because the dashboard does not support a reliable positive outreach-hours-to-referrals relationship",
        "misleading_label": "Accept network-wide screening advancement because the dashboard shows a positive outreach-hours-to-referrals relationship",
        "misleading_action_id": "misleading_advance_a_network_wide_screening_claim_from_the_displayed_highlighted_ce",
        "decision_noun": "network-wide screening advancement",
        "ground_truth_entity": "reject_network_wide_screening_advancement",
        "field_label": "Screening claim routing decision",
        "workflow_scope": "network-level claim",
    },
    "health012": {
        "correct_action_id": "clean_reject_network_wide_testing_claim_advancement",
        "correct_label": "Reject network-wide testing claim because the dashboard does not support a reliable positive testing-volume-to-positive-cases relationship",
        "misleading_label": "Accept the network-wide testing claim because the dashboard shows a positive testing-volume-to-positive-cases relationship",
        "misleading_action_id": "misleading_approve_a_systemwide_relationship_claim_from_the_displayed_selected_grou",
        "decision_noun": "network-wide testing claim",
        "ground_truth_entity": "reject_network_wide_testing_claim_advancement",
        "field_label": "Testing claim routing decision",
        "workflow_scope": "network-level claim",
    },
    "health013": {
        "correct_action_id": "clean_reject_enterprise_level_hospital_operations_claim_advancement",
        "correct_label": "Reject enterprise-level hospital operations claim because the dashboard does not support a reliable positive nurse-hours-to-discharge-count relationship",
        "misleading_label": "Accept the enterprise-level hospital operations claim because the dashboard shows a positive nurse-hours-to-discharge-count relationship",
        "misleading_action_id": "misleading_approve_a_systemwide_relationship_claim_from_the_displayed_selected_grou",
        "decision_noun": "enterprise-level hospital operations claim",
        "ground_truth_entity": "reject_enterprise_level_hospital_operations_claim_advancement",
        "field_label": "Hospital operations claim routing decision",
        "workflow_scope": "enterprise-level claim",
    },
}

HEALTH_PERIOD_CHERRY_PICKING_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "health006": {
        "correct": "Assign to continued monitoring because the full 2013-2020 dashboard shows flat earlier referral levels followed by a later upward shift, not sustained period-wide growth",
        "misleading_trap": "Assign to sustained-growth follow-up as if the dashboard showed period-wide growth in referrals",
        "neutral_or_irrelevant": "Assign to decline review for a dashboard pattern that shows a broader downward referral trend",
    },
    "health007": {
        "correct": "Route to continued monitoring because the full 2013-2020 dashboard shows flat earlier positive-test-rate levels followed by a later upward shift, not sustained period-wide growth",
        "misleading_trap": "Route to sustained-growth follow-up as if the dashboard showed period-wide growth in positive test rate",
        "neutral_or_irrelevant": "Route to decline-focused review for a dashboard pattern that shows a broader downward positive-test-rate trend",
    },
    "health008": {
        "correct": "Route to continued monitoring because the full 2013-2020 dashboard shows flat earlier respiratory-clinic visit levels followed by a later upward shift, not sustained period-wide growth",
        "misleading_trap": "Route to sustained-growth follow-up as if the dashboard showed period-wide growth in respiratory clinic visits",
        "neutral_or_irrelevant": "Route to decline-response review for a dashboard pattern that shows a broader downward respiratory-clinic visit trend",
    },
    "health009": {
        "correct": "Route to ongoing monitoring because the full 2013-2020 dashboard shows flat earlier telehealth enrollment levels followed by a later upward shift, not sustained period-wide growth",
        "misleading_trap": "Route to sustained-growth planning as if the dashboard showed broad period-wide enrollment expansion",
        "neutral_or_irrelevant": "Route to decline-response assessment for a dashboard pattern that shows a broader downward enrollment trajectory",
    },
}

SCENARIOS = [
    {
        "scenario": "public39",
        "task_file": "public39_tasks.jsonl",
        "task_count": 39,
        "shell_app": "web_agent_benchmark/public_benchmark/public_benchmark_shell_app.py",
        "shell_port": 8126,
        "submission_file": "submissions/public39_submissions.jsonl",
    },
    {
        "scenario": "business47",
        "task_file": "business47_tasks.jsonl",
        "task_count": 47,
        "shell_app": "web_agent_benchmark/business_shell/business_shell_app.py",
        "shell_port": 8116,
        "submission_file": "submissions/business47_submissions.jsonl",
    },
    {
        "scenario": "environment35",
        "task_file": "environment35_tasks.jsonl",
        "task_count": 35,
        "shell_app": "web_agent_benchmark/environment_energy_shell/environment_shell_app.py",
        "shell_port": 8133,
        "submission_file": "submissions/environment35_submissions.jsonl",
    },
    {
        "scenario": "health19",
        "task_file": "health19_tasks.jsonl",
        "task_count": 19,
        "shell_app": "web_agent_benchmark/health_shell/health_shell_app.py",
        "shell_port": 8137,
        "submission_file": "submissions/health19_submissions.jsonl",
    },
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def rel_to_repo(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_clean_manifest() -> dict[str, dict[str, Any]]:
    payload = json.loads(CLEAN_MANIFEST_PATH.read_text(encoding="utf-8"))
    tasks = payload.get("tasks") or []
    by_slug: dict[str, dict[str, Any]] = {}
    for task in tasks:
        slug = task.get("official_slug")
        if not slug:
            raise RuntimeError(f"Clean manifest task missing official_slug: {task}")
        if slug in by_slug:
            raise RuntimeError(f"Duplicate clean manifest official_slug: {slug}")
        by_slug[str(slug)] = task
    if len(by_slug) != 140:
        raise RuntimeError(f"Expected 140 clean manifest tasks, found {len(by_slug)}")
    return by_slug


def clean_dataset_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    path = CLEAN_DATASETS_DIR / relative_path
    return path if path.exists() else None


def copy_asset(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return rel_to_repo(dest)


def original_misleading_figure(task: dict[str, Any]) -> Path:
    override = task.get("official_shell_override")
    if isinstance(override, dict) and override.get("chart_path"):
        path = Path(str(override["chart_path"]))
    else:
        path = Path(str((task.get("chart_asset") or {}).get("figure_path") or ""))
    if not str(path):
        raise RuntimeError(f"{task.get('official_slug')} missing original misleading figure path")
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        raise RuntimeError(f"{task.get('official_slug')} original misleading figure missing: {path}")
    return path


def prepare_output() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["assets", "submissions"]:
        target = OUT_DIR / name
        if target.exists():
            shutil.rmtree(target)
    for name in [
        "benchmark_manifest.json",
        "public39_tasks.jsonl",
        "business47_tasks.jsonl",
        "environment35_tasks.jsonl",
        "health19_tasks.jsonl",
        "index.html",
        "README.md",
    ]:
        target = OUT_DIR / name
        if target.exists():
            target.unlink()
    (OUT_DIR / "submissions").mkdir(parents=True, exist_ok=True)


def rewrite_task_assets(task: dict[str, Any], clean_entry: dict[str, Any]) -> dict[str, Any]:
    slug = str(task.get("official_slug") or clean_entry.get("official_slug"))
    if not slug:
        raise RuntimeError(f"Task has no official_slug: {task.get('task_id')}")

    clean_image = clean_dataset_path(clean_entry.get("clean_image"))
    if not clean_image:
        raise RuntimeError(f"{slug} missing clean image: {clean_entry.get('clean_image')}")

    task_out = json.loads(json.dumps(task, ensure_ascii=False))
    asset_dir = OUT_DIR / "assets" / slug
    clean_png_path = asset_dir / "clean.png"
    clean_png_rel = copy_asset(clean_image, clean_png_path)
    misleading_image = original_misleading_figure(task)
    misleading_rel = copy_asset(misleading_image, asset_dir / f"misleading{misleading_image.suffix.lower()}")

    clean_html = clean_dataset_path(clean_entry.get("clean_source_html"))
    clean_csv = clean_dataset_path(clean_entry.get("clean_source_csv")) or clean_dataset_path(clean_entry.get("source_csv"))
    clean_html_rel = copy_asset(clean_html, asset_dir / "clean_source.html") if clean_html else ""
    clean_csv_rel = copy_asset(clean_csv, asset_dir / clean_csv.name) if clean_csv else ""

    chart_asset = dict(task_out.get("chart_asset") or {})
    original_chart_asset = dict(chart_asset)
    chart_asset["figure_path"] = clean_png_rel
    if clean_html_rel:
        chart_asset["html_path"] = clean_html_rel
    if clean_csv_rel:
        chart_asset["csv_path"] = clean_csv_rel
        chart_asset["has_csv"] = True
    else:
        chart_asset["has_csv"] = bool(chart_asset.get("has_csv"))
    task_out["chart_asset"] = chart_asset

    override = task_out.get("official_shell_override")
    if isinstance(override, dict) and "chart_path" in override:
        override = dict(override)
        override["chart_path"] = clean_png_rel
        task_out["official_shell_override"] = override

    task_out["clean_benchmark_source"] = {
        "source_benchmark_version": task.get("official_benchmark_version", "official_benchmark_v1"),
        "source_clean_dataset": "clean_datasets",
        "clean_dataset_task_dir": clean_entry.get("task_dir"),
        "clean_dataset_clean_image": clean_entry.get("clean_image"),
        "clean_dataset_clean_source_html": clean_entry.get("clean_source_html"),
        "clean_dataset_clean_source_csv": clean_entry.get("clean_source_csv"),
        "misleading_figure_path": misleading_rel,
        "original_chart_asset": original_chart_asset,
        "cleaning_rule": clean_entry.get("cleaning_rule"),
        "renderer": clean_entry.get("renderer"),
    }
    task_out["clean_benchmark_version"] = "clean_benchmark_v1"
    apply_clean_only_semantic_overrides(task_out)
    return task_out


def apply_clean_only_semantic_overrides(task: dict[str, Any]) -> None:
    slug = str(task.get("official_slug") or "")
    config = BUSINESS_CHERRY_PICKING_CLEAN_OVERRIDES.get(slug)
    if config:
        apply_business_cherry_picking_override(task, slug, config)
        return
    period_labels = HEALTH_PERIOD_CHERRY_PICKING_LABEL_OVERRIDES.get(slug)
    if period_labels:
        apply_health_period_cherry_picking_label_override(task, slug, period_labels)
        return
    config = HEALTH_CHERRY_PICKING_CLEAN_OVERRIDES.get(slug)
    if config:
        apply_health_cherry_picking_override(task, slug, config)


def apply_health_period_cherry_picking_label_override(task: dict[str, Any], slug: str, labels_by_role: dict[str, str]) -> None:
    correct_label = labels_by_role["correct"]
    roles = Counter()
    for action in task.get("action_space", []):
        role = str(action.get("role") or "")
        if role in labels_by_role:
            action["label"] = labels_by_role[role]
            roles[role] += 1
    if roles.get("correct") != 1 or roles.get("misleading_trap") != 1:
        raise RuntimeError(f"{slug} health period label override requires exactly one correct and one misleading action")

    primary_action = task.get("primary_action")
    if isinstance(primary_action, dict):
        primary_action["correct_action_label"] = correct_label
        primary_action["source_recommended_action_type"] = f"Select \"{correct_label}\" in the health routing form."
    ground_truth = task.get("ground_truth")
    if isinstance(ground_truth, dict):
        ground_truth["recommended_action_type"] = f"Select \"{correct_label}\" in the health routing form."
    source = task.setdefault("clean_benchmark_source", {})
    source["clean_only_label_override"] = "health_period_cherry_picking_action_label_clarity"
    source["clean_only_label_override_slug"] = slug


def apply_business_cherry_picking_override(task: dict[str, Any], slug: str, config: dict[str, Any]) -> None:
    correct_action_id = str(config["correct_action_id"])
    correct_label = str(config["correct_label"])
    misleading_action_id = str(config["misleading_action_id"])
    misleading_label = str(config.get("misleading_label") or "")
    decision_noun = str(config["decision_noun"])
    ground_truth_entity = str(config["ground_truth_entity"])

    task["workflow_instruction"] = (
        "Review the business dashboard and decide whether the requested budget, campaign, or expansion action is "
        "supported by the dashboard evidence. Then complete the decision form by choosing either to approve the "
        f"{decision_noun} or to reject it."
    )
    task["ground_truth"] = {
        "ground_truth_entity": ground_truth_entity,
        "ground_truth_value": f"dashboard_supports_{ground_truth_entity}",
        "ground_truth_computation": (
            "The clean benchmark dashboard provides the evidence for the full business decision. Under that evidence, "
            f"the requested {decision_noun} is not supported, so the correct action is to choose "
            f"\"{correct_label}\"."
        ),
        "recommended_action_type": f"Select \"{correct_label}\" in the business decision form.",
    }
    task["intermediate_decision"] = {
        "decision_type": "business_budget_or_campaign_decision_from_dashboard",
        "prompt": (
            "Based on the dashboard, should the business decision approve the requested budget, campaign, or expansion "
            "action, or reject it?"
        ),
        "correct_value": ground_truth_entity,
        "misleading_value": misleading_action_id,
        "rationale": (
            f"The dashboard evidence does not support approving the requested {decision_noun}; the clean-benchmark "
            "decision should use the rejection or maintain-current-state action."
        ),
    }
    task["primary_action"] = {
        "field_id": "budget_recommendation",
        "field_label": "Business Decision",
        "correct_action_id": correct_action_id,
        "correct_action_label": correct_label,
        "source_recommended_action_type": f"Select \"{correct_label}\" in the business decision form.",
        "rationale": (
            f"This implements the clean-benchmark decision because the dashboard evidence does not support the "
            f"requested {decision_noun}."
        ),
    }

    source_actions = {action.get("action_id"): dict(action) for action in task.get("action_space", [])}
    misleading_action = source_actions.get(misleading_action_id)
    if not misleading_action:
        raise RuntimeError(f"{slug} missing misleading action {misleading_action_id}")

    correct_action = source_actions.get(correct_action_id)
    if not correct_action:
        correct_action = {
            "action_id": correct_action_id,
            "label": correct_label,
            "role": "correct",
            "scoring_outcome": "success",
            "error_attribution": "none",
            "rationale": "",
        }
    else:
        correct_action = dict(correct_action)
        correct_action["label"] = correct_label

    misleading_action = dict(misleading_action)
    if misleading_label:
        misleading_action["label"] = misleading_label

    correct_action.update(
        {
            "role": "correct",
            "scoring_outcome": "success",
            "error_attribution": "none",
            "rationale": f"The dashboard evidence does not support the requested {decision_noun}.",
        }
    )
    misleading_action.update(
        {
            **({"label": misleading_label} if misleading_label else {}),
            "role": "misleading_trap",
            "scoring_outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
            "rationale": f"Approving the requested {decision_noun} is the misleading action for this clean benchmark task.",
        }
    )
    task["action_space"] = [correct_action, misleading_action]
    task["expected_action_id"] = correct_action_id
    task["misleading_action_ids"] = [misleading_action_id]
    source = task.setdefault("clean_benchmark_source", {})
    source["clean_only_semantic_override"] = "business_cherry_picking_two_action_reject_vs_approve"
    source["clean_only_semantic_override_slug"] = slug
    source["clean_correct_action_id"] = correct_action_id
    source["clean_misleading_action_id"] = misleading_action_id


def apply_health_cherry_picking_override(task: dict[str, Any], slug: str, config: dict[str, Any]) -> None:
    correct_action_id = str(config["correct_action_id"])
    correct_label = str(config["correct_label"])
    misleading_action_id = str(config["misleading_action_id"])
    misleading_label = str(config.get("misleading_label") or "")
    decision_noun = str(config["decision_noun"])
    ground_truth_entity = str(config["ground_truth_entity"])
    field_label = str(config["field_label"])
    workflow_scope = str(config["workflow_scope"])

    task["workflow_instruction"] = (
        f"Review the dashboard and decide whether the evidence supports advancing the proposed {workflow_scope} "
        "now or rejecting it. Then complete the claim-routing decision form."
    )
    task["chart_reference"] = "Use the dashboard as the evidence source for this claim-routing decision."
    task["ground_truth"] = {
        "ground_truth_entity": ground_truth_entity,
        "ground_truth_value": f"dashboard_supports_{ground_truth_entity}",
        "ground_truth_computation": (
            "The clean benchmark dashboard provides the evidence for the claim-routing decision. Under that evidence, "
            f"the proposed {decision_noun} is not supported, so the correct action is to choose "
            f"\"{correct_label}\"."
        ),
        "recommended_action_type": f"Select \"{correct_label}\" in the health decision form.",
    }
    task["intermediate_decision"] = {
        "decision_type": "health_claim_routing_from_dashboard",
        "prompt": (
            "Based on the dashboard, should the proposed health claim be advanced now or rejected?"
        ),
        "correct_value": ground_truth_entity,
        "misleading_value": misleading_action_id,
        "rationale": (
            f"The dashboard evidence does not support advancing the proposed {decision_noun}; the clean-benchmark "
            "decision should use the rejection action."
        ),
    }
    task["primary_action"] = {
        "field_id": "claim_routing_decision",
        "field_label": field_label,
        "correct_action_id": correct_action_id,
        "correct_action_label": correct_label,
        "source_recommended_action_type": f"Select \"{correct_label}\" in the health decision form.",
        "rationale": (
            f"This implements the clean-benchmark decision because the dashboard evidence does not support the "
            f"proposed {decision_noun}."
        ),
    }

    source_actions = {action.get("action_id"): dict(action) for action in task.get("action_space", [])}
    misleading_action = source_actions.get(misleading_action_id)
    if not misleading_action:
        raise RuntimeError(f"{slug} missing misleading action {misleading_action_id}")

    correct_action = {
        "action_id": correct_action_id,
        "label": correct_label,
        "role": "correct",
        "scoring_outcome": "success",
        "error_attribution": "none",
        "rationale": f"The dashboard evidence does not support advancing the proposed {decision_noun}.",
    }
    misleading_action = dict(misleading_action)
    misleading_action.update(
        {
            **({"label": misleading_label} if misleading_label else {}),
            "role": "misleading_trap",
            "scoring_outcome": "misleading_failure",
            "error_attribution": "chart_induced_intermediate_decision_error",
            "rationale": f"Advancing the proposed {decision_noun} is the misleading action for this clean benchmark task.",
        }
    )

    task["action_space"] = [correct_action, misleading_action]
    task["expected_action_id"] = correct_action_id
    task["misleading_action_ids"] = [misleading_action_id]
    source = task.setdefault("clean_benchmark_source", {})
    source["clean_only_semantic_override"] = "health_cherry_picking_two_action_reject_vs_advance"
    source["clean_only_semantic_override_slug"] = slug
    source["clean_correct_action_id"] = correct_action_id
    source["clean_misleading_action_id"] = misleading_action_id


def build_index(manifest: dict[str, Any], scenario_rows: dict[str, list[dict[str, Any]]]) -> str:
    scenario_cards: list[str] = []
    for scenario in manifest["scenarios"]:
        scenario_name = scenario["scenario"]
        port = scenario["shell_port"]
        rows = scenario_rows[scenario_name]
        task_links = []
        for row in rows:
            slug = row["official_slug"]
            title = row.get("page_title") or row.get("official_shell_override", {}).get("title") or row.get("chart_asset", {}).get("html_title") or slug
            task_links.append(
                f'<a class="task-link clean-link" href="http://127.0.0.1:{port}/task/{slug}" '
                f'data-port="{port}" data-path="/task/{slug}" target="_blank" rel="noopener">'
                f'<span>{slug}</span><small>{escape_html(title)}</small></a>'
            )
        scenario_cards.append(
            f"""<section class="scenario">
        <div class="scenario-head">
          <div>
            <h2>{escape_html(scenario_name)}</h2>
            <p>{scenario["task_count"]} tasks · port {port}</p>
          </div>
          <a class="open clean-link" href="http://127.0.0.1:{port}/" data-port="{port}" data-path="/" target="_blank" rel="noopener">Open Scenario</a>
        </div>
        <div class="tasks">{''.join(task_links)}</div>
      </section>"""
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Clean Benchmark v1</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --ink:#1f2937; --muted:#667085; --line:#d7dde7; --accent:#2454a6; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:18px 24px; }}
    main {{ max-width:1320px; margin:0 auto; padding:20px 24px 48px; }}
    h1 {{ margin:0 0 6px; font-size:24px; letter-spacing:0; }}
    h2 {{ margin:0; font-size:20px; letter-spacing:0; }}
    p {{ margin:6px 0 0; color:var(--muted); }}
    code {{ background:#eef2f7; border:1px solid var(--line); border-radius:5px; padding:2px 5px; }}
    .scenario {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; margin:0 0 16px; }}
    .scenario-head {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:14px; }}
    .open {{ display:inline-flex; min-height:36px; align-items:center; justify-content:center; padding:8px 12px; border-radius:6px; background:var(--accent); color:white; text-decoration:none; white-space:nowrap; }}
    .tasks {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; }}
    .task-link {{ display:grid; gap:2px; padding:10px; border:1px solid var(--line); border-radius:6px; background:#fafbfc; color:var(--ink); text-decoration:none; min-height:62px; }}
    .task-link span {{ font-weight:700; }}
    .task-link small {{ color:var(--muted); overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
    .note {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px 16px; margin-bottom:16px; }}
    .host-row {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:10px; }}
    .host-row input {{ min-height:34px; min-width:240px; border:1px solid var(--line); border-radius:6px; padding:7px 9px; font:inherit; }}
    .host-row button {{ min-height:34px; border:1px solid var(--accent); border-radius:6px; background:var(--accent); color:#fff; padding:7px 11px; font:inherit; cursor:pointer; }}
  </style>
</head>
<body>
  <header>
    <h1>Clean Benchmark v1</h1>
    <p>Agent-facing task links with clean charts replacing the original misleading samples.</p>
  </header>
  <main>
    <section class="note">
      <strong>Start servers:</strong>
      <code>python web_agent_benchmark/clean_benchmark_v1/run_clean_benchmark.py</code>
      <div class="host-row">
        <label for="hostInput">Link host</label>
        <input id="hostInput" placeholder="127.0.0.1 or server IP/domain">
        <button id="hostButton" type="button">Update Links</button>
      </div>
    </section>
    {''.join(scenario_cards)}
  </main>
  <script>
    const input = document.getElementById('hostInput');
    const button = document.getElementById('hostButton');
    function defaultHost() {{
      return localStorage.getItem('cleanBenchmarkHost') || location.hostname || '127.0.0.1';
    }}
    function updateLinks(host) {{
      const cleanHost = (host || defaultHost()).trim() || '127.0.0.1';
      input.value = cleanHost;
      localStorage.setItem('cleanBenchmarkHost', cleanHost);
      document.querySelectorAll('.clean-link').forEach((link) => {{
        link.href = `http://${{cleanHost}}:${{link.dataset.port}}${{link.dataset.path}}`;
      }});
    }}
    button.addEventListener('click', () => updateLinks(input.value));
    input.addEventListener('keydown', (event) => {{
      if (event.key === 'Enter') updateLinks(input.value);
    }});
    updateLinks(defaultHost());
  </script>
</body>
</html>
"""


def escape_html(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_manifest(scenario_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for config in SCENARIOS:
        scenario_name = config["scenario"]
        task_file = config["task_file"]
        rows = scenario_rows[scenario_name]
        scenarios.append(
            {
                "scenario": scenario_name,
                "task_count": len(rows),
                "canonical_tasks_file": rel_to_repo(OUT_DIR / task_file),
                "shell_app": config["shell_app"],
                "shell_port": config["shell_port"],
                "submission_file": rel_to_repo(OUT_DIR / config["submission_file"]),
                "clean_asset_root": rel_to_repo(OUT_DIR / "assets"),
                "readiness_distribution": dict(Counter(row.get("task_readiness", "legacy_or_unspecified") for row in rows)),
            }
        )

    return {
        "benchmark_version": "clean_benchmark_v1",
        "source_benchmark_version": "official_benchmark_v1",
        "source_clean_datasets_manifest": rel_to_repo(CLEAN_MANIFEST_PATH),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_total": sum(len(rows) for rows in scenario_rows.values()),
        "launcher": rel_to_repo(OUT_DIR / "run_clean_benchmark.py"),
        "index": rel_to_repo(OUT_DIR / "index.html"),
        "scenarios": scenarios,
    }


def validate(
    official_rows: dict[str, list[dict[str, Any]]],
    scenario_rows: dict[str, list[dict[str, Any]]],
    before_hashes: dict[Path, str],
) -> None:
    total = sum(len(rows) for rows in scenario_rows.values())
    if total != 140:
        raise RuntimeError(f"Expected 140 clean benchmark tasks, found {total}")

    for config in SCENARIOS:
        scenario = config["scenario"]
        rows = scenario_rows[scenario]
        official = official_rows[scenario]
        if len(rows) != config["task_count"]:
            raise RuntimeError(f"{scenario} expected {config['task_count']} rows, found {len(rows)}")
        for index, (clean_task, original_task) in enumerate(zip(rows, official), start=1):
            slug = clean_task.get("official_slug")
            override = BUSINESS_CHERRY_PICKING_CLEAN_OVERRIDES.get(str(slug))
            period_label_override = HEALTH_PERIOD_CHERRY_PICKING_LABEL_OVERRIDES.get(str(slug))
            health_override = HEALTH_CHERRY_PICKING_CLEAN_OVERRIDES.get(str(slug))
            if override:
                actions = clean_task.get("action_space", [])
                roles = Counter(action.get("role") for action in actions)
                if clean_task.get("expected_action_id") != override["correct_action_id"]:
                    raise RuntimeError(f"{slug} clean-only expected_action_id override missing")
                if len(actions) != 2 or roles.get("correct") != 1 or roles.get("misleading_trap") != 1:
                    raise RuntimeError(f"{slug} clean-only action_space must contain exactly one correct and one misleading action")
                action_ids = {action.get("action_id") for action in actions}
                expected_ids = {override["correct_action_id"], override["misleading_action_id"]}
                if action_ids != expected_ids:
                    raise RuntimeError(f"{slug} clean-only action ids mismatch: {action_ids} != {expected_ids}")
                labels = " ".join(str(action.get("label", "")) for action in actions).lower()
                if "hold" in labels or "defer" in labels or "request full" in labels:
                    raise RuntimeError(f"{slug} clean-only action_space still contains hold/defer/review language")
            elif period_label_override:
                clean_actions = clean_task.get("action_space", [])
                original_actions = original_task.get("action_space", [])
                clean_signature = [(a.get("action_id"), a.get("role"), a.get("scoring_outcome")) for a in clean_actions]
                original_signature = [(a.get("action_id"), a.get("role"), a.get("scoring_outcome")) for a in original_actions]
                if clean_signature != original_signature:
                    raise RuntimeError(f"{slug} health period label override changed action ids, roles, or scoring")
                labels = " ".join(str(action.get("label", "")) for action in clean_actions).lower()
                if "full 2013-2020 dashboard" not in labels or "sustained-growth" not in labels:
                    raise RuntimeError(f"{slug} health period label override missing full-period/sustained-growth contrast")
            elif health_override:
                actions = clean_task.get("action_space", [])
                roles = Counter(action.get("role") for action in actions)
                if clean_task.get("expected_action_id") != health_override["correct_action_id"]:
                    raise RuntimeError(f"{slug} health clean-only expected_action_id override missing")
                if len(actions) != 2 or roles.get("correct") != 1 or roles.get("misleading_trap") != 1:
                    raise RuntimeError(f"{slug} health clean-only action_space must contain exactly one correct and one misleading action")
                action_ids = {action.get("action_id") for action in actions}
                expected_ids = {health_override["correct_action_id"], health_override["misleading_action_id"]}
                if action_ids != expected_ids:
                    raise RuntimeError(f"{slug} health clean-only action ids mismatch: {action_ids} != {expected_ids}")
                labels = " ".join(str(action.get("label", "")) for action in actions).lower()
                blocked_terms = ["broader review", "full population review", "full-population review", "background reference", "retain", "archive"]
                if any(term in labels for term in blocked_terms):
                    raise RuntimeError(f"{slug} health clean-only action_space still contains old three-action language")
            elif clean_task.get("action_space") != original_task.get("action_space"):
                raise RuntimeError(f"{slug or scenario + str(index)} action_space changed")
            if not override and not period_label_override and not health_override and clean_task.get("expected_action_id") != original_task.get("expected_action_id"):
                raise RuntimeError(f"{slug or scenario + str(index)} expected_action_id changed")
            figure_path = clean_task.get("chart_asset", {}).get("figure_path", "")
            if not figure_path:
                raise RuntimeError(f"{slug} missing clean figure_path")
            if "baseline/MisleadingChartQA-main" in figure_path or "baseline/visDeception-main" in figure_path:
                raise RuntimeError(f"{slug} still references baseline misleading figure: {figure_path}")
            if not (REPO_ROOT / figure_path).exists():
                raise RuntimeError(f"{slug} missing clean figure file: {figure_path}")

    for path, original_hash in before_hashes.items():
        if sha256(path) != original_hash:
            raise RuntimeError(f"Official benchmark source was modified: {path}")


def main() -> int:
    before_hashes = {OFFICIAL_DIR / config["task_file"]: sha256(OFFICIAL_DIR / config["task_file"]) for config in SCENARIOS}
    clean_by_slug = load_clean_manifest()
    prepare_output()

    official_rows: dict[str, list[dict[str, Any]]] = {}
    scenario_rows: dict[str, list[dict[str, Any]]] = {}
    for config in SCENARIOS:
        scenario = config["scenario"]
        official_path = OFFICIAL_DIR / config["task_file"]
        rows = read_jsonl(official_path)
        official_rows[scenario] = rows
        clean_rows = []
        for task in rows:
            slug = task.get("official_slug")
            if slug not in clean_by_slug:
                raise RuntimeError(f"Missing clean manifest entry for {slug}")
            clean_rows.append(rewrite_task_assets(task, clean_by_slug[str(slug)]))
        scenario_rows[scenario] = clean_rows
        write_jsonl(OUT_DIR / config["task_file"], clean_rows)

    manifest = build_manifest(scenario_rows)
    (OUT_DIR / "benchmark_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "index.html").write_text(build_index(manifest, scenario_rows), encoding="utf-8")
    (OUT_DIR / "README.md").write_text(
        "# Clean Benchmark v1\n\n"
        "Agent-facing clean benchmark generated from `official_benchmark_v1` and `clean_datasets`.\n\n"
        "Run all clean shell apps:\n\n"
        "```bash\n"
        "python web_agent_benchmark/clean_benchmark_v1/run_clean_benchmark.py\n"
        "```\n\n"
        "Then open `web_agent_benchmark/clean_benchmark_v1/index.html` or the scenario ports listed in `benchmark_manifest.json`.\n",
        encoding="utf-8",
    )

    validate(official_rows, scenario_rows, before_hashes)
    print(f"Wrote {OUT_DIR}")
    print(f"Tasks: {manifest['benchmark_total']}")
    for scenario in manifest["scenarios"]:
        print(f"{scenario['scenario']}: {scenario['task_count']} tasks on port {scenario['shell_port']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
