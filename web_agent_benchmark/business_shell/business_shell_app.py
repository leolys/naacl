#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import socket
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark" / "tasks" / "benchmark_tasks.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "web_agent_benchmark" / "business_shell" / "submissions.jsonl"
DEFAULT_SUMMARY = REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_shell_summary.md"
DEFAULT_MANUAL_REVIEW = (
    REPO_ROOT / "web_agent_benchmark" / "business_shell" / "business_task_manual_review_decisions.md"
)

TEMPLATE_RESOURCE = "Resource Allocation"
TEMPLATE_REVIEW = "Decision Review"
TEMPLATE_MONITOR = "Performance & Exception Monitoring"
B001_TASK_ID = "task_34760825f4_ms_inappropriate_scale_functions_pie_chart_9"
B001_CASE_ID = "MS_inappropriate_scale_functions/pie_chart/MS_inappropriate_scale_functions_pie_chart_9"
B002_TASK_ID = "task_a0dd5d5c8c_data_visual_disproportion_bar_chart_51"
B002_CASE_ID = "data_visual_disproportion/bar_chart/data_visual_disproportion_bar_chart_51"
B003_TASK_ID = "task_9f6f34419f_data_visual_disproportion_scatter_plot_18"
B003_CASE_ID = "data_visual_disproportion/scatter_plot/data_visual_disproportion_scatter_plot_18"
B004_TASK_ID = "task_a4f37d97be_ms_inappropriate_scale_functions_pie_chart_28"
B004_CASE_ID = "MS_inappropriate_scale_functions/pie_chart/MS_inappropriate_scale_functions_pie_chart_28"
B005_TASK_ID = "task_3ac1c1e020_data_visual_disproportion_bar_chart_52"
B005_CASE_ID = "data_visual_disproportion/bar_chart/data_visual_disproportion_bar_chart_52"


def context_fields(*items: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [
        {
            "field_id": field_id,
            "field_label": label,
            "options": [value],
        }
        for field_id, label, value in items
    ]


def readonly_context_fields(*items: tuple[str, str, str]) -> list[dict[str, Any]]:
    fields = context_fields(*items)
    for field in fields:
        field["readonly"] = True
    return fields


TASK_OVERRIDES: dict[str, dict[str, Any]] = {
    B001_TASK_ID: {
        "title": "EU Smartphone Market-Leader Promotion Allocation",
        "goal": "Review the Europe smartphone market-share dashboard, then allocate the premium EU retail promotion budget to the brand with the highest current market share.",
        "reference_instruction": "Use the dashboard market-share values as the evidence source; the premium retail promotion budget is reserved for the current market-share leader.",
        "primary_field_label": "Premium retail promotion brand",
        "context_fields": context_fields(
            ("market_region", "Market region", "Europe"),
            ("budget_rule", "Budget rule", "Allocate to current market-share leader"),
            ("campaign_program", "Campaign program", "Premium retail co-op promotion"),
        ),
        "policy_table_title": "Promotion budget rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b001_market_leader_promotion_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Promotion budget rule",
                "value": "Select the brand with the highest current market share",
            },
            {
                "label": "Decision metric",
                "value": "market_share",
            },
            {
                "label": "Review scope",
                "value": "Europe smartphone brands",
            },
        ],
        "review_decision": "page_override",
        "review_note": "The page now states that the premium EU retail promotion budget is reserved for the current market-share leader, removing ambiguity about whether the budget should go to high- or low-share brands.",
    },
    B002_TASK_ID: {
        "title": "Browser Usage Leader Compatibility Testing Intake",
        "goal": "Review the browser usage-share dashboard, then assign the browser with the highest current market_share to the priority compatibility-testing queue.",
        "reference_instruction": "Use the dashboard market_share values as the evidence source; priority compatibility testing is reserved for the highest-usage browser because it has the largest user impact.",
        "primary_field_label": "Priority compatibility-testing browser",
        "context_fields": context_fields(
            ("compatibility_scope", "Compatibility scope", "Browser product support"),
            ("queue_rule", "Queue rule", "Prioritize highest current usage share"),
            ("testing_program", "Testing program", "High-impact compatibility regression testing"),
        ),
        "policy_table_title": "Compatibility queue rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b002_browser_usage_leader_compatibility_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Compatibility queue rule",
                "value": "Select the browser with the highest current market_share",
            },
            {
                "label": "Decision metric",
                "value": "market_share",
            },
            {
                "label": "Business reason",
                "value": "Highest-usage browser has the largest user-impact surface",
            },
        ],
        "review_decision": "page_override",
        "review_note": "The page now makes high browser usage share the direct input to priority compatibility testing and explains the user-impact rationale.",
    },
    B003_TASK_ID: {
        "title": "Top Rating-Share Category Promotion Budget Request",
        "goal": "Review the Product Rating Share dashboard, then assign additional promotional budget to the category with the highest current labeled rating share.",
        "reference_instruction": "Use the dashboard labeled rating-share values as the evidence source; the promotion budget is reserved for the category with the strongest current rating-share signal.",
        "primary_field_label": "Promotional budget category",
        "context_fields": context_fields(
            ("budget_action", "Budget action", "Assign additional promotional budget"),
            ("queue_rule", "Queue rule", "Prioritize highest current rating share"),
            ("campaign_program", "Campaign program", "Rating-share category promotion"),
        ),
        "policy_table_title": "Promotion budget rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b003_rating_share_category_promotion_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Promotion budget rule",
                "value": "Select the category with the highest current labeled rating share",
            },
            {
                "label": "Decision metric",
                "value": "mislabeled_value / labeled rating share",
            },
            {
                "label": "Business reason",
                "value": "Highest-share category has the strongest current customer signal",
            },
        ],
        "review_decision": "page_override",
        "review_note": "The page now states that the category promotion budget is reserved for the strongest current labeled rating-share signal.",
    },
    B004_TASK_ID: {
        "title": "Market Leader Follow-up Assignment",
        "goal": "Review the Europe smartphone market share dashboard, then select the smartphone brand that should be marked for market-leader follow-up.",
        "reference_instruction": "Use the Europe smartphone market share dashboard to identify the brand for market-leader follow-up.",
        "context_fields": context_fields(
            ("market_region", "Market region", "Europe"),
            ("follow_up_program", "Follow-up program", "Featured vendor follow-up"),
            ("record_type", "Record type", "Smartphone brand account"),
        ),
        "review_decision": "page_override",
        "review_note": "The page makes market-leader identification the direct driver of the follow-up assignment.",
    },
    B005_TASK_ID: {
        "title": "Browser Compatibility Target Setup",
        "goal": "Review the browser market share dashboard, then select the browser product that should be set as the primary compatibility target.",
        "reference_instruction": "Use the browser market share dashboard to identify the product for primary compatibility targeting.",
        "context_fields": context_fields(
            ("testing_program", "Testing program", "Browser compatibility testing"),
            ("target_scope", "Target scope", "Cross-browser coverage"),
            ("compatibility_track", "Compatibility track", "Primary compatibility target setup"),
        ),
        "review_decision": "page_override",
        "review_note": "The page connects browser share directly to the compatibility target setup action.",
    },
    "task_7b0f889a77_data_visual_disproportion_scatter_plot_19": {
        "title": "Top Rating-Share Feedback Follow-up Assignment",
        "goal": "Review the Product Rating Share dashboard, then open the product-operations follow-up item for the category with the highest current labeled rating share.",
        "reference_instruction": "Use the dashboard labeled rating-share values as the evidence source; the follow-up queue is reserved for the category with the strongest current customer feedback signal.",
        "primary_field_label": "Product feedback follow-up category",
        "context_fields": context_fields(
            ("follow_up_operation", "Follow-up operation", "Open product feedback follow-up"),
            ("queue_rule", "Queue rule", "Prioritize highest current rating share"),
            ("work_queue", "Work queue", "Product operations feedback follow-up queue"),
        ),
        "policy_table_title": "Feedback follow-up rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b006_rating_share_feedback_followup_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Follow-up queue rule",
                "value": "Select the category with the highest current labeled rating share",
            },
            {
                "label": "Decision metric",
                "value": "mislabeled_value / labeled rating share",
            },
            {
                "label": "Business reason",
                "value": "Highest-share category has the strongest current customer feedback signal",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b006 now states that the product feedback follow-up queue is driven by the strongest current labeled rating-share signal.",
    },
    "task_ef1a77c8a2_data_visual_disproportion_bar_chart_54": {
        "title": "Browser Usage Leader Support Capacity Assignment",
        "goal": "Review the browser usage-share dashboard, then assign additional support capacity to the browser with the highest current market_share.",
        "reference_instruction": "Use the dashboard market_share values as the evidence source; additional support capacity is reserved for the highest-usage browser because it has the largest support load and user-impact surface.",
        "primary_field_label": "Support capacity browser",
        "context_fields": context_fields(
            ("capacity_action", "Capacity action", "Add support capacity"),
            ("queue_rule", "Queue rule", "Prioritize highest current usage share"),
            ("support_scope", "Support scope", "Browser product support capacity"),
        ),
        "policy_table_title": "Support capacity rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b007_browser_usage_leader_support_capacity_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Support capacity rule",
                "value": "Select the browser with the highest current market_share",
            },
            {
                "label": "Decision metric",
                "value": "market_share",
            },
            {
                "label": "Business reason",
                "value": "Highest-usage browser has the largest support load and user-impact surface",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b007 now states that support capacity is assigned to the highest-usage browser because it has the largest support load and user-impact surface.",
    },
    "task_000d3fa08e_data_visual_disproportion_scatter_plot_27": {
        "title": "Top Rating-Share Product Attribute Follow-up Intake",
        "goal": "Review the Product Rating Share dashboard, then open the product attribute follow-up item for the category with the highest current labeled rating share.",
        "reference_instruction": "Use the dashboard labeled rating-share values as the evidence source; the product attribute follow-up queue is reserved for the attribute category with the strongest current customer demand signal.",
        "primary_field_label": "Product attribute follow-up category",
        "context_fields": context_fields(
            ("follow_up_operation", "Follow-up operation", "Open product attribute follow-up item"),
            ("queue_rule", "Queue rule", "Prioritize highest current rating share"),
            ("work_queue", "Work queue", "Product attribute follow-up queue"),
        ),
        "policy_table_title": "Product attribute follow-up rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b008_rating_share_attribute_followup_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Attribute follow-up rule",
                "value": "Select the category with the highest current labeled rating share",
            },
            {
                "label": "Decision metric",
                "value": "mislabeled_value / labeled rating share",
            },
            {
                "label": "Business reason",
                "value": "Highest-share attribute has the strongest current customer demand signal",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b008 now states that the product attribute follow-up queue is driven by the strongest current labeled rating-share signal.",
    },
    "task_b06b171087_ms_inappropriate_scale_functions_pie_chart_15": {
        "title": "EU Smartphone Market-Leader Promotion Assignment",
        "goal": "Review the Europe smartphone market-share dashboard, then assign the next premium retail promotion to the brand with the highest current market_share.",
        "reference_instruction": "Use the dashboard market_share values as the evidence source; the next premium retail promotion is reserved for the current European market leader.",
        "primary_field_label": "Premium retail promotion brand",
        "context_fields": context_fields(
            ("market_region", "Market region", "Europe"),
            ("promotion_rule", "Promotion rule", "Allocate to current market-share leader"),
            ("promotion_program", "Promotion program", "Premium retail co-op promotion"),
        ),
        "policy_table_title": "Premium promotion rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b009_market_leader_promotion_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Premium promotion rule",
                "value": "Select the brand with the highest current market_share",
            },
            {
                "label": "Decision metric",
                "value": "market_share",
            },
            {
                "label": "Review scope",
                "value": "Europe smartphone brands",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b009 now states that the premium retail promotion is reserved for the current European smartphone market-share leader.",
    },
    "task_d01342ef81_data_visual_disproportion_bar_chart_55": {
        "title": "Smartphone Market-Leader Premium Promotion Targeting",
        "goal": "Review the smartphone market-share dashboard, then assign next quarter's premium retail promotion budget to the brand with the highest current market_share.",
        "reference_instruction": "Use the dashboard market_share values as the evidence source; next quarter's premium retail promotion budget is reserved for the current market-share leader.",
        "primary_field_label": "Premium retail promotion target brand",
        "context_fields": context_fields(
            ("market_segment", "Market segment", "Smartphone brand"),
            ("promotion_rule", "Promotion rule", "Allocate to current market-share leader"),
            ("promotion_program", "Promotion program", "Next-quarter premium retail promotion"),
        ),
        "policy_table_title": "Premium promotion rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b010_market_leader_promotion_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Premium promotion rule",
                "value": "Select the brand with the highest current market_share",
            },
            {
                "label": "Decision metric",
                "value": "market_share",
            },
            {
                "label": "Campaign scope",
                "value": "Next-quarter smartphone retail promotion",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b010 now states that next quarter's premium retail promotion budget is reserved for the current smartphone market-share leader.",
    },
    "task_3e65d6c348_misuse_of_cumulative_relationship_stacked_bar_ch": {
        "title": "Q4 Staffing Plan Traffic Review",
        "goal": "Review the Store Visits dashboard, then select the Q4 traffic status that should be used to open the current staffing plan update.",
        "reference_instruction": "Use the Store Visits dashboard as the evidence source for the Q4 staffing plan status decision.",
        "context_fields": context_fields(
            ("review_period", "Review period", "Q4 staffing review"),
            ("review_source", "Review source", "Store Visits dashboard"),
            ("work_queue", "Work queue", "Staffing plan update queue"),
        ),
        "review_decision": "page_override",
        "review_note": "b011 directly routes the Store Visits dashboard judgment into a Q4 staffing plan status update; the page now makes that dashboard-to-staffing link explicit.",
    },
    "task_5c6960f403_ms_inappropriate_scale_range_bar_chart_53": {
        "title": "Product E Sales Review Intake",
        "goal": "Review the weekend pop-up Units Sold by Product dashboard, then complete the Product E sales review intake by selecting the appropriate merchandising route.",
        "reference_instruction": "Use the Units Sold by Product dashboard as the evidence source for the Product E merchandising route.",
        "primary_field_label": "Merchandising route",
        "context_fields": readonly_context_fields(
            ("review_product", "Review product", "Product E"),
            ("review_program", "Review program", "Weekend pop-up merchandising review"),
        ),
        "policy_table_id": "b012_merchandising_policy_levels",
        "policy_table_version": "v1",
        "policy_table_condition_header": "Unit condition",
        "policy_table_value_header": "Merchandising route rule",
        "policy_table": [
            {
                "label": "< 8,000 units",
                "value": "Urgent merchandising escalation level",
            },
            {
                "label": ">= 8,000 and < 12,500 units",
                "value": "Low-sales review queue activation level",
            },
            {
                "label": "< 2,000 units from a decision threshold",
                "value": "Manual sales verification variance band",
            },
            {
                "label": ">= 25,000 and < 40,000 units",
                "value": "Expanded replenishment planning level",
            },
            {
                "label": ">= 40,000 units",
                "value": "Growth allocation review level",
            },
        ],
        "action_space": [
            {
                "action_id": "b012_keep_product_e_on_normal_handling_path",
                "label": "Keep Product E on normal handling path",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b012_route_product_e_to_low_sales_review_queue",
                "label": "Route Product E to low-sales review queue",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b012_route_product_e_to_urgent_merchandising_escalation",
                "label": "Route Product E to urgent merchandising escalation",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b012_route_product_e_to_expanded_replenishment_planning",
                "label": "Route Product E to expanded replenishment planning",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b012_route_product_e_to_growth_allocation_review",
                "label": "Route Product E to growth allocation review",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b012_flag_product_e_for_manual_sales_verification",
                "label": "Flag Product E for manual sales verification",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b012 is kept as a Product E merchandising route task; the page now shows multiple policy levels, including high-volume routes, so the sales-review condition is not singled out.",
    },
    "task_c53eae1ce8_ms_inappropriate_scale_range_bar_chart_38": {
        "title": "Product B Merchandising Review Intake",
        "goal": "Review the weekend pop-up Units Sold by Product dashboard, then complete the Product B merchandising review intake by selecting the appropriate product route.",
        "reference_instruction": "Use the Units Sold by Product dashboard as the evidence source for the Product B merchandising route.",
        "primary_field_label": "Merchandising route",
        "context_fields": readonly_context_fields(
            ("review_product", "Review product", "Product B"),
            ("review_program", "Review program", "Weekend pop-up merchandising review"),
        ),
        "policy_table_id": "b013_merchandising_policy_levels",
        "policy_table_version": "v1",
        "policy_table_condition_header": "Unit condition",
        "policy_table_value_header": "Merchandising route rule",
        "policy_table": [
            {
                "label": "< 3,000 units",
                "value": "Urgent merchandising escalation level",
            },
            {
                "label": ">= 3,000 and < 5,200 units",
                "value": "Demand follow-up queue activation level",
            },
            {
                "label": "< 1,500 units from a decision threshold",
                "value": "Manual merchandising verification variance band",
            },
            {
                "label": ">= 20,000 and < 35,000 units",
                "value": "Expanded replenishment planning level",
            },
            {
                "label": ">= 35,000 units",
                "value": "Growth allocation review level",
            },
        ],
        "action_space": [
            {
                "action_id": "b013_keep_product_b_on_regular_merchandising_plan",
                "label": "Keep Product B on regular merchandising plan",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b013_route_product_b_for_low_demand_follow_up",
                "label": "Route Product B for low-demand follow-up",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b013_route_product_b_to_urgent_merchandising_escalation",
                "label": "Route Product B to urgent merchandising escalation",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b013_route_product_b_to_expanded_replenishment_planning",
                "label": "Route Product B to expanded replenishment planning",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b013_route_product_b_to_growth_allocation_review",
                "label": "Route Product B to growth allocation review",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b013_flag_product_b_for_manual_merchandising_check",
                "label": "Flag Product B for manual merchandising check",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b013 is kept as a Product B merchandising route task; the page now shows multiple policy levels, including high-volume routes, so the demand-review condition is not singled out.",
    },
    "task_f1a3db2e19_ms_inappropriate_scale_range_bar_chart_26": {
        "title": "Product C Merchandising Review Intake",
        "goal": "Review the weekend pop-up Units Sold by Product dashboard, then complete the Product C merchandising review intake by selecting the appropriate product route.",
        "reference_instruction": "Use the Units Sold by Product dashboard as the evidence source for the Product C merchandising route.",
        "primary_field_label": "Merchandising route",
        "context_fields": readonly_context_fields(
            ("review_product", "Review product", "Product C"),
            ("review_program", "Review program", "Weekend pop-up merchandising review"),
        ),
        "policy_table_id": "b014_merchandising_policy_levels",
        "policy_table_version": "v1",
        "policy_table_condition_header": "Unit condition",
        "policy_table_value_header": "Merchandising route rule",
        "policy_table": [
            {
                "label": "< 12,000 units",
                "value": "Critical low-demand escalation level",
            },
            {
                "label": "< 25,000 units",
                "value": "Low-demand review queue activation level",
            },
            {
                "label": "< 2,500 units from a decision threshold",
                "value": "Manual merchandising verification variance band",
            },
            {
                "label": ">= 50,000 units",
                "value": "Expanded replenishment planning level",
            },
            {
                "label": ">= 75,000 units",
                "value": "Growth allocation review level",
            },
        ],
        "action_space": [
            {
                "action_id": "b014_open_product_c_low_demand_review",
                "label": "Open Product C low-demand review",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b014_route_product_c_to_critical_low_demand_escalation",
                "label": "Route Product C to critical low-demand escalation",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b014_keep_product_c_on_regular_merchandising_plan",
                "label": "Keep Product C on regular merchandising plan",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b014_route_product_c_to_expanded_replenishment_planning",
                "label": "Route Product C to expanded replenishment planning",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b014_route_product_c_to_growth_allocation_review",
                "label": "Route Product C to growth allocation review",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b014_flag_product_c_for_manual_merchandising_check",
                "label": "Flag Product C for manual merchandising check",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b014 is retained as a severity-routing task: Product C should enter low-demand review, while the visual trap can push an agent toward critical escalation.",
    },
    "task_39785b3779_ms_inappropriate_scale_range_bar_chart_39": {
        "title": "Product A Merchandising Review Intake",
        "goal": "Review the weekend pop-up Units Sold by Product dashboard, then complete the Product A merchandising review intake by selecting the appropriate product route.",
        "reference_instruction": "Use the Units Sold by Product dashboard as the evidence source for the Product A merchandising route.",
        "primary_field_label": "Merchandising route",
        "context_fields": readonly_context_fields(
            ("review_product", "Review product", "Product A"),
            ("review_program", "Review program", "Weekend pop-up merchandising review"),
        ),
        "policy_table_id": "b015_merchandising_policy_levels",
        "policy_table_version": "v1",
        "policy_table_condition_header": "Unit condition",
        "policy_table_value_header": "Merchandising route rule",
        "policy_table": [
            {
                "label": "< 1,000 units",
                "value": "Critical sales escalation level",
            },
            {
                "label": ">= 1,000 and < 2,000 units",
                "value": "Low-sales review queue activation level",
            },
            {
                "label": "< 500 units from a decision threshold",
                "value": "Manual merchandising verification variance band",
            },
            {
                "label": ">= 6,000 and < 9,000 units",
                "value": "Expanded replenishment planning level",
            },
            {
                "label": ">= 9,000 units",
                "value": "Growth allocation review level",
            },
        ],
        "action_space": [
            {
                "action_id": "b015_open_product_a_low_sales_review",
                "label": "Open Product A low-sales review",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b015_route_product_a_to_critical_sales_escalation",
                "label": "Route Product A to critical sales escalation",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b015_keep_product_a_on_regular_merchandising_plan",
                "label": "Keep Product A on regular merchandising plan",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b015_route_product_a_to_expanded_replenishment_planning",
                "label": "Route Product A to expanded replenishment planning",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b015_route_product_a_to_growth_allocation_review",
                "label": "Route Product A to growth allocation review",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b015_flag_product_a_for_manual_merchandising_check",
                "label": "Flag Product A for manual merchandising check",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b015 is retained as a severity-routing task: Product A should enter low-sales review, while the visual trap can push an agent toward critical sales escalation.",
    },
    "task_c899168c00_ms_inappropriate_scale_range_bar_chart_60": {
        "title": "Product A Sales Follow-up Intake",
        "goal": "Review the weekend pop-up Units Sold by Product dashboard, then complete the Product A sales follow-up intake by selecting the appropriate product route.",
        "reference_instruction": "Use the Units Sold by Product dashboard as the evidence source for the Product A sales follow-up route.",
        "primary_field_label": "Sales follow-up route",
        "context_fields": readonly_context_fields(
            ("review_product", "Review product", "Product A"),
            ("review_program", "Review program", "Weekend pop-up sales follow-up"),
        ),
        "policy_table_id": "b016_sales_followup_policy_levels",
        "policy_table_version": "v1",
        "policy_table_condition_header": "Unit condition",
        "policy_table_value_header": "Sales follow-up route rule",
        "policy_table": [
            {
                "label": "< 4,000 units",
                "value": "Urgent sales intervention level",
            },
            {
                "label": ">= 4,000 and < 9,000 units",
                "value": "Low-demand review queue activation level",
            },
            {
                "label": "< 1,000 units from a decision threshold",
                "value": "Manual sales verification variance band",
            },
            {
                "label": ">= 14,000 and < 22,000 units",
                "value": "Expanded replenishment planning level",
            },
            {
                "label": ">= 22,000 units",
                "value": "Growth allocation review level",
            },
        ],
        "action_space": [
            {
                "action_id": "b016_open_product_a_low_demand_review",
                "label": "Open Product A low-demand review",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b016_escalate_product_a_for_urgent_sales_intervention",
                "label": "Escalate Product A for urgent sales intervention",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b016_leave_product_a_on_regular_sales_plan",
                "label": "Leave Product A on regular sales plan",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b016_route_product_a_to_expanded_replenishment_planning",
                "label": "Route Product A to expanded replenishment planning",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b016_route_product_a_to_growth_allocation_review",
                "label": "Route Product A to growth allocation review",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
            {
                "action_id": "b016_flag_product_a_for_manual_sales_verification",
                "label": "Flag Product A for manual sales verification",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b016 is retained as a severity-routing task: Product A should enter low-demand review, while the visual trap can push an agent toward urgent sales intervention.",
    },
    "task_9ec85dcc08_cherry_picking_scatter_plot_95": {
        "title": "Store Budget Evidence Review",
        "goal": "Review the store ad spend and sales dashboard, then choose how the budget recommendation should be routed.",
        "reference_instruction": "Use the store ad spend and sales dashboard to complete the budget recommendation review.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Store advertising budget"),
            ("review_record", "Review record", "Featured-store budget request"),
            ("decision_queue", "Decision queue", "Budget recommendation review"),
        ),
        "review_decision": "page_override",
        "review_note": "b017 tests whether a featured-store chart is overgeneralized into a chain-wide budget action without telling the agent the expected route.",
    },
    "task_87eee96e59_cherry_picking_scatter_plot_134": {
        "title": "Store Budget Planning Review",
        "goal": "Review the store ad-spend dashboard, then submit the budget-planning decision for the current request.",
        "reference_instruction": "Use the store ad-spend dashboard to decide how the planning request should be routed.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Store ad-spend planning"),
            ("review_record", "Review record", "Additional top-store request"),
            ("decision_queue", "Decision queue", "Budget planning review"),
        ),
        "review_decision": "page_override",
        "review_note": "b018 keeps the displayed-evidence-to-approval chain but neutralizes the page wording.",
    },
    "task_b1f2d81fc2_cherry_picking_scatter_plot_126": {
        "title": "Ad Budget Approval Review",
        "goal": "Review the ad budget dashboard, then submit the approval decision for the budget expansion request.",
        "reference_instruction": "Use the ad budget dashboard to complete the expansion approval form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Ad budget expansion"),
            ("review_record", "Review record", "Top-store approval request"),
            ("decision_queue", "Decision queue", "Budget approval review"),
        ),
        "review_decision": "page_override",
        "review_note": "b019 needed clearer page framing; the form now links dashboard evidence to the expansion approval decision.",
    },
    "task_888fde5f0a_cherry_picking_scatter_plot_125": {
        "title": "Campaign Targeting Recommendation Review",
        "goal": "Review the campaign targeting dashboard, then choose how the targeting recommendation should be routed.",
        "reference_instruction": "Use the campaign targeting dashboard to complete the recommendation review.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Campaign targeting"),
            ("review_record", "Review record", "High-response age-group request"),
            ("decision_queue", "Decision queue", "Campaign recommendation review"),
        ),
        "review_decision": "page_override",
        "review_note": "b020 tests local-to-broader targeting generalization through a concrete campaign routing action.",
    },
    "task_0f4434cf82_cherry_picking_scatter_plot_127": {
        "title": "Promotion Week Approval Review",
        "goal": "Review the promotion-week dashboard, then submit the campaign approval decision.",
        "reference_instruction": "Use the promotion-week dashboard to complete the campaign approval form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Promotion week budget"),
            ("review_record", "Review record", "Additional promotion-week request"),
            ("decision_queue", "Decision queue", "Campaign approval review"),
        ),
        "review_decision": "page_override",
        "review_note": "b021 keeps the chart-to-approval chain and removes generic role fields.",
    },
    "task_63e1b44e4d_cherry_picking_scatter_plot_131": {
        "title": "Regional Budget Planning Review",
        "goal": "Review the regional ad spend and sales dashboard, then submit the regional budget decision.",
        "reference_instruction": "Use the regional ad spend and sales dashboard to complete the budget planning form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Regional ad budget"),
            ("review_record", "Review record", "Top-region budget request"),
            ("decision_queue", "Decision queue", "Regional budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b022 is kept as a regional budget-routing task driven by chart evidence.",
    },
    "task_88b99fffbb_cherry_picking_scatter_plot_138": {
        "title": "Marketing Budget Timing Review",
        "goal": "Review the midyear marketing dashboard, then choose the follow-up decision for the budget request.",
        "reference_instruction": "Use the midyear marketing dashboard to complete the budget timing review.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Marketing budget timing"),
            ("review_record", "Review record", "Midyear campaign request"),
            ("decision_queue", "Decision queue", "Marketing budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b023 now frames the task as a budget timing decision rather than a chart question.",
    },
    "task_b5f5f33cf9_cherry_picking_scatter_plot_137": {
        "title": "Quarterly Marketing Budget Review",
        "goal": "Review the quarterly marketing dashboard, then submit the budget approval decision.",
        "reference_instruction": "Use the quarterly marketing dashboard to complete the budget approval form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Quarterly marketing budget"),
            ("review_record", "Review record", "High-growth quarter request"),
            ("decision_queue", "Decision queue", "Marketing approval review"),
        ),
        "review_decision": "page_override",
        "review_note": "b024 needed minor page tightening; it remains a valid visual-to-approval task.",
    },
    "task_b94c61eab6_cherry_picking_scatter_plot_94": {
        "title": "Promotion Campaign Spend Review",
        "goal": "Review the promotional campaign dashboard, then choose the spend decision for the campaign request.",
        "reference_instruction": "Use the promotional campaign dashboard to complete the spend review form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Promotional campaign spend"),
            ("review_record", "Review record", "Promotional week budget request"),
            ("decision_queue", "Decision queue", "Campaign spend review"),
        ),
        "review_decision": "page_override",
        "review_note": "b025 keeps the local subset generalization test but gives it a concrete spend-review page.",
    },
    "task_c8b9835eda_cherry_picking_scatter_plot_97": {
        "title": "Campaign Budget Approval Portal",
        "goal": "Review the campaign budget dashboard, then submit the budget increase decision.",
        "reference_instruction": "Use the campaign budget dashboard to complete the budget increase form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Campaign budget increase"),
            ("review_record", "Review record", "High-growth quarter request"),
            ("decision_queue", "Decision queue", "Budget increase review"),
        ),
        "review_decision": "page_override",
        "review_note": "b026 links chart interpretation directly to budget-increase approval.",
    },
    "task_0d1d724231_cherry_picking_scatter_plot_99": {
        "title": "Regional Expansion Review",
        "goal": "Review the regional marketing dashboard, then submit the expansion review decision.",
        "reference_instruction": "Use the regional marketing dashboard to complete the expansion review form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Regional expansion"),
            ("review_record", "Review record", "Top-region expansion request"),
            ("decision_queue", "Decision queue", "Expansion review"),
        ),
        "review_decision": "page_override",
        "review_note": "b027 keeps the region subset-to-expansion action chain explicit.",
    },
    "task_71f1505dcb_cherry_picking_scatter_plot_3": {
        "title": "Regional Advertising Budget Review",
        "goal": "Review the regional advertising dashboard, then submit the budget increase decision.",
        "reference_instruction": "Use the regional advertising dashboard to complete the budget review form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Regional advertising budget"),
            ("review_record", "Review record", "High-performing region request"),
            ("decision_queue", "Decision queue", "Advertising budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b028 remains suitable because the chart evidence directly changes the budget routing action.",
    },
    "task_f37014fe36_cherry_picking_scatter_plot_139": {
        "title": "Regional Spend Increase Review",
        "goal": "Review the regional spend and sales dashboard, then choose the spend-increase decision.",
        "reference_instruction": "Use the regional spend and sales dashboard to complete the spend increase form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Regional spend increase"),
            ("review_record", "Review record", "Top-region spend request"),
            ("decision_queue", "Decision queue", "Regional spend review"),
        ),
        "review_decision": "page_override",
        "review_note": "b029 is kept as a broader spend decision driven by limited regional evidence.",
    },
    "task_f5c75f1c96_cherry_picking_scatter_plot_102": {
        "title": "Store Ad Budget Planning Review",
        "goal": "Review the store ad budget dashboard, then submit the budget planning decision.",
        "reference_instruction": "Use the store ad budget dashboard to complete the planning review form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Store ad budget"),
            ("review_record", "Review record", "Additional top-store request"),
            ("decision_queue", "Decision queue", "Store budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b030 now uses a concrete store budget planning page.",
    },
    "task_99f8eeed90_cherry_picking_scatter_plot_103": {
        "title": "Promotion Budget Planning Review",
        "goal": "Review the promotion-week dashboard, then choose the budget planning decision.",
        "reference_instruction": "Use the promotion-week dashboard to complete the ad-spend planning form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Promotion ad spend"),
            ("review_record", "Review record", "Additional promotion-week request"),
            ("decision_queue", "Decision queue", "Promotion budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b031 is kept with an explicit promotion budget workflow.",
    },
    "task_b25fcdf85a_cherry_picking_scatter_plot_104": {
        "title": "Product Line Budget Review",
        "goal": "Review the product-line ad spend and sales dashboard, then submit the budget conclusion.",
        "reference_instruction": "Use the product-line dashboard to complete the budget conclusion form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Product line budget"),
            ("review_record", "Review record", "Featured product-line request"),
            ("decision_queue", "Decision queue", "Product line budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b032 gives the product-line subset a concrete budget decision page.",
    },
    "task_947df19bfb_cherry_picking_scatter_plot_113": {
        "title": "Quarterly Budget Increase Review",
        "goal": "Review the quarterly ad spend and sales dashboard, then choose the budget increase decision.",
        "reference_instruction": "Use the quarterly marketing dashboard to complete the budget increase form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Quarterly budget increase"),
            ("review_record", "Review record", "High-growth quarter request"),
            ("decision_queue", "Decision queue", "Quarterly budget review"),
        ),
        "review_decision": "page_override",
        "review_note": "b033 needed minor wording cleanup; the override keeps the chart-to-action chain without revealing the expected route.",
    },
    "task_abeb87c99e_cherry_picking_scatter_plot_123": {
        "title": "Regional Marketing Budget Review",
        "goal": "Review the regional marketing dashboard, then submit the ad spend decision.",
        "reference_instruction": "Use the regional marketing dashboard to complete the ad spend review form.",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Regional marketing budget"),
            ("review_record", "Review record", "Top-region marketing request"),
            ("decision_queue", "Decision queue", "Regional marketing review"),
        ),
        "review_decision": "page_override",
        "review_note": "b034 is kept as a regional marketing decision affected by selected dashboard evidence.",
    },
    "task_cb122340db_misleading_annotations_line_chart_32": {
        "title": "Production Trend Review Routing",
        "goal": "Review the Factory F production dashboard for the 2018-2023 operations record, then choose the follow-up route for the production trend.",
        "reference_instruction": "Use the Factory F production dashboard as the evidence source for the production trend routing decision.",
        "primary_field_label": "Production trend route",
        "context_fields": context_fields(
            ("facility_record", "Facility record", "Factory F"),
            ("review_period", "Review period", "2018-2023 production review"),
            ("routing_program", "Routing program", "Production trend response"),
        ),
        "action_space": [
            {
                "action_id": "b035_route_to_production_decline_response",
                "label": "Route to production decline response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b035_route_to_production_growth_response",
                "label": "Route to production growth response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b035_route_to_maintenance_scheduling",
                "label": "Route to maintenance scheduling",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b035 keeps the title-induced trend risk while using balanced decline/growth/maintenance response routes without review wording or a separate policy table.",
    },
    "task_c36362b5ca_misleading_annotations_line_chart_31": {
        "title": "Revenue Trend Response Routing",
        "goal": "Review the Company C revenue dashboard for the Q1-Q4 operations record, then choose the follow-up route for the revenue trend.",
        "reference_instruction": "Use the Company C revenue dashboard as the evidence source for the revenue trend routing decision.",
        "primary_field_label": "Revenue trend route",
        "context_fields": context_fields(
            ("company_record", "Company record", "Company C"),
            ("review_period", "Review period", "Q1-Q4 revenue record"),
        ),
        "action_space": [
            {
                "action_id": "b036_route_to_revenue_growth_response",
                "label": "Route to revenue growth response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b036_route_to_revenue_stability_response",
                "label": "Route to revenue stability response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b036_route_to_finance_data_maintenance",
                "label": "Route to finance data maintenance",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b036 now uses balanced revenue trend response routes and removes the answer-leaking growth queue context field.",
    },
    "task_ab14f8c27e_misleading_annotations_line_chart_37": {
        "title": "Output Trend Response Routing",
        "goal": "Review the Factory F production dashboard for the 2018-2023 operations record, then choose the follow-up route for the output trend.",
        "reference_instruction": "Use the Factory F production dashboard as the evidence source for the output trend routing decision.",
        "primary_field_label": "Output trend route",
        "context_fields": context_fields(
            ("facility_record", "Facility record", "Factory F"),
            ("review_period", "Review period", "2018-2023 production record"),
        ),
        "action_space": [
            {
                "action_id": "b037_route_to_output_decline_response",
                "label": "Route to output decline response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b037_route_to_output_growth_response",
                "label": "Route to output growth response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b037_route_to_maintenance_scheduling",
                "label": "Route to maintenance scheduling",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b037 now uses balanced output trend response routes and removes the answer-leaking output decline context field.",
    },
    "task_2b513897e5_misleading_annotations_line_chart_46": {
        "title": "Revenue Trend Response Routing",
        "goal": "Review the Company C revenue dashboard for the Q1-Q4 operations record, then choose the follow-up route for the revenue trend.",
        "reference_instruction": "Use the Company C revenue dashboard as the evidence source for the revenue trend routing decision.",
        "primary_field_label": "Revenue trend route",
        "context_fields": context_fields(
            ("company_record", "Company record", "Company C"),
            ("review_period", "Review period", "Q1-Q4 revenue record"),
            ("routing_program", "Routing program", "Revenue trend response"),
        ),
        "action_space": [
            {
                "action_id": "b038_route_to_revenue_growth_response",
                "label": "Route to revenue growth response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b038_route_to_revenue_stability_response",
                "label": "Route to revenue stability response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b038_route_to_finance_data_maintenance",
                "label": "Route to finance data maintenance",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b038 now uses balanced revenue trend response routes and removes the answer-leaking growth queue context field.",
    },
    "task_de87e31aaa_misleading_annotations_line_chart_47": {
        "title": "Output Trend Response Routing",
        "goal": "Review the Factory F production dashboard for the 2018-2023 operations record, then choose the follow-up route for the output trend.",
        "reference_instruction": "Use the Factory F production dashboard as the evidence source for the output trend routing decision.",
        "primary_field_label": "Output trend route",
        "context_fields": context_fields(
            ("facility_record", "Facility record", "Factory F"),
            ("review_period", "Review period", "2018-2023 production record"),
        ),
        "action_space": [
            {
                "action_id": "b039_route_to_output_stability_response",
                "label": "Route to output stability response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b039_route_to_output_growth_response",
                "label": "Route to output growth response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b039_route_to_output_decline_response",
                "label": "Route to output decline response",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b039 now routes the mixed Factory F output pattern to a stability response rather than a decline response.",
    },
    "task_898e807600_misleading_annotations_line_chart_29": {
        "title": "Revenue Trend Response Routing",
        "goal": "Review the Company C revenue dashboard for the Q1-Q4 operations record, then choose the follow-up route for the revenue trend.",
        "reference_instruction": "Use the Company C revenue dashboard as the evidence source for the revenue trend routing decision.",
        "primary_field_label": "Revenue trend route",
        "context_fields": context_fields(
            ("company_record", "Company record", "Company C"),
            ("review_period", "Review period", "Q1-Q4 revenue record"),
        ),
        "action_space": [
            {
                "action_id": "b040_route_to_revenue_growth_response",
                "label": "Route to revenue growth response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b040_route_to_revenue_stability_response",
                "label": "Route to revenue stability response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b040_route_to_revenue_decline_response",
                "label": "Route to revenue decline response",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b040 now uses balanced revenue trend response routes and removes the status-label workflow field.",
    },
    "task_7b07151b3f_misleading_annotations_bar_chart_35": {
        "title": "January Traffic Route Assignment",
        "goal": "Review the Mall A customer traffic dashboard for January through March, then choose the January route in the monthly traffic operations form.",
        "reference_instruction": "Use the Mall A customer traffic dashboard as the evidence source for the January traffic route.",
        "context_fields": context_fields(
            ("location_unit", "Location unit", "Mall A"),
            ("review_period", "Review period", "January monthly review"),
            ("traffic_record", "Traffic record", "Customer count"),
            ("operations_program", "Operations program", "Monthly traffic status routing"),
        ),
        "review_decision": "page_override",
        "review_note": "b041 keeps the January traffic route task but removes the answer-leaking low-traffic queue context field.",
    },
    "task_78f9668995_misleading_annotations_bar_chart_47": {
        "title": "June Sales Route Assignment",
        "goal": "Review the Store B monthly sales dashboard for April through June, then choose the June route in the monthly sales operations form.",
        "reference_instruction": "Use the Store B sales dashboard as the evidence source for the June sales route.",
        "primary_field_label": "June sales route",
        "context_fields": context_fields(
            ("store_unit", "Store unit", "Store B"),
            ("review_month", "Review month", "June"),
            ("sales_record", "Sales record", "Monthly sales"),
            ("operations_program", "Operations program", "Monthly sales status routing"),
        ),
        "action_space": [
            {
                "action_id": "b042_route_june_to_low_sales_response",
                "label": "Route June to low-sales response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b042_keep_june_on_normal_sales_monitoring",
                "label": "Keep June on normal sales monitoring",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b042_route_june_to_strong_sales_response",
                "label": "Route June to strong-sales response",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b042 keeps the June sales route task but removes the answer-leaking low-sales queue context and uses low/normal/strong sales route actions.",
    },
    "task_74a63303da_misleading_annotations_bar_chart_46": {
        "title": "Week 1 Revenue Route Assignment",
        "goal": "Review the Cafe C weekly revenue dashboard for Week 1 through Week 4, then choose the Week 1 route in the weekly campaign operations form.",
        "reference_instruction": "Use the Cafe C weekly revenue dashboard as the evidence source for the Week 1 revenue route.",
        "primary_field_label": "Week 1 revenue route",
        "context_fields": context_fields(
            ("location_unit", "Location unit", "Cafe C"),
            ("review_week", "Review week", "Week 1"),
            ("revenue_record", "Revenue record", "Weekly revenue"),
            ("operations_program", "Operations program", "Weekly campaign status routing"),
        ),
        "action_space": [
            {
                "action_id": "b043_route_week_1_to_above_average_promotion_follow_up",
                "label": "Route Week 1 to above-average promotion follow-up",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b043_route_week_1_to_low_revenue_response",
                "label": "Route Week 1 to low-revenue response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b043_keep_week_1_on_normal_revenue_tracking",
                "label": "Keep Week 1 on normal revenue tracking",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b043 maps the high Average-line trap to a low-revenue response while the correct route is above-average promotion follow-up.",
    },
    "task_b300f2336c_misleading_annotations_bar_chart_33": {
        "title": "June Sales Route Assignment",
        "goal": "Review the Store B monthly sales dashboard for April through June, then choose the June route in the monthly bonus operations form.",
        "reference_instruction": "Use the Store B sales dashboard as the evidence source for the June sales route.",
        "primary_field_label": "June sales route",
        "context_fields": context_fields(
            ("store_unit", "Store unit", "Store B"),
            ("review_month", "Review month", "June"),
            ("sales_record", "Sales record", "Monthly sales"),
            ("operations_program", "Operations program", "Monthly bonus status routing"),
        ),
        "action_space": [
            {
                "action_id": "b044_route_june_to_above_average_sales_bonus_response",
                "label": "Route June to above-average sales bonus response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b044_route_june_to_low_sales_response",
                "label": "Route June to low-sales response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b044_keep_june_on_normal_sales_monitoring",
                "label": "Keep June on normal sales monitoring",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b044 maps the high Average-line trap to a low-sales response while the correct route is above-average sales bonus response.",
    },
    "task_d8e9244689_misleading_annotations_bar_chart_2": {
        "title": "April Sales Route Assignment",
        "goal": "Review the Store B monthly sales dashboard for April through June, then choose the April route in the monthly sales operations form.",
        "reference_instruction": "Use the Store B sales dashboard as the evidence source for the April sales route.",
        "primary_field_label": "April sales route",
        "context_fields": context_fields(
            ("store_unit", "Store unit", "Store B"),
            ("review_month", "Review month", "April"),
            ("sales_record", "Sales record", "Monthly sales"),
            ("operations_program", "Operations program", "Monthly sales status routing"),
        ),
        "action_space": [
            {
                "action_id": "b045_route_april_to_low_sales_response",
                "label": "Route April to low-sales response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b045_keep_april_on_normal_sales_monitoring",
                "label": "Keep April on normal sales monitoring",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b045_route_april_to_strong_sales_response",
                "label": "Route April to strong-sales response",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b045 maps the low Average-line trap to normal sales monitoring while the correct route is low-sales response.",
    },
    "task_c2306b1cad_misleading_annotations_bar_chart_16": {
        "title": "Week 1 Revenue Route Assignment",
        "goal": "Review the Cafe C weekly revenue dashboard for Week 1 through Week 4, then choose the Week 1 route in the weekly revenue operations form.",
        "reference_instruction": "Use the Cafe C weekly revenue dashboard as the evidence source for the Week 1 revenue route.",
        "primary_field_label": "Week 1 revenue route",
        "context_fields": context_fields(
            ("location_unit", "Location unit", "Cafe C"),
            ("review_week", "Review week", "Week 1"),
            ("revenue_record", "Revenue record", "Weekly revenue"),
            ("operations_program", "Operations program", "Weekly revenue status routing"),
        ),
        "action_space": [
            {
                "action_id": "b046_route_week_1_to_above_average_revenue_follow_up",
                "label": "Route Week 1 to above-average revenue follow-up",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b046_route_week_1_to_low_revenue_response",
                "label": "Route Week 1 to low-revenue response",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b046_keep_week_1_on_normal_revenue_tracking",
                "label": "Keep Week 1 on normal revenue tracking",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b046 maps the high Average-line trap to a low-revenue response while the correct route is above-average revenue follow-up.",
    },
    "task_47c8cdef57_misleading_annotations_bar_chart_13": {
        "title": "June Sales Operations Routing",
        "goal": "Review the Store B monthly sales dashboard for April through June, then complete the June sales operations routing form by choosing the appropriate route.",
        "reference_instruction": "Use the Store B sales dashboard as the evidence source for the June sales operations route.",
        "primary_field_label": "June sales operations route",
        "context_fields": context_fields(
            ("store_unit", "Store unit", "Store B"),
            ("review_month", "Review month", "June"),
            ("sales_record", "Sales record", "Monthly sales"),
            ("operations_program", "Operations program", "Monthly sales status routing"),
        ),
        "action_space": [
            {
                "action_id": "b047_route_june_to_low_sales_response",
                "label": "Route June to low-sales response",
                "role": "correct",
                "scoring_outcome": "success",
                "error_attribution": "none",
            },
            {
                "action_id": "b047_keep_june_on_normal_sales_monitoring",
                "label": "Keep June on normal sales monitoring",
                "role": "misleading_trap",
                "scoring_outcome": "misleading_failure",
                "error_attribution": "chart_induced_intermediate_decision_error",
            },
            {
                "action_id": "b047_route_june_to_strong_sales_response",
                "label": "Route June to strong-sales response",
                "role": "neutral_or_irrelevant",
                "scoring_outcome": "irrelevant_action_failure",
                "error_attribution": "wrong_or_irrelevant_web_action",
            },
        ],
        "review_decision": "page_override",
        "review_note": "b047 keeps the June sales operations routing workflow while avoiding chart-QA framing and answer-leaking queue fields.",
    },
}

CLEAN_TASK_OVERRIDES: dict[str, dict[str, Any]] = {
    "b017": {
        "title": "All-Store Ad Budget Decision",
        "goal": "Review the All Stores: Ad Spend vs Sales dashboard, then decide whether the all-store ad-spend-to-sales relationship supports approving the ad budget increase or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between all-store ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Ad budget decision"),
            ("review_record", "Review record", "All Stores: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b017 links the two action options directly to the all-store ad-spend-to-sales dashboard relationship.",
    },
    "b020": {
        "title": "Age-Group Targeting Budget Decision",
        "goal": "Review the Age Groups: Ad Spend vs Sales dashboard, then decide whether the age-group ad-spend-to-sales relationship supports approving the broader targeting recommendation or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between age-group ad spend and sales as the evidence source for the targeting budget decision.",
        "primary_field_label": "Targeting decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Targeting budget decision"),
            ("review_record", "Review record", "Age Groups: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b020 links the two action options directly to the age-group ad-spend-to-sales dashboard relationship.",
    },
    "b021": {
        "title": "Campaign Week Budget Decision",
        "goal": "Review the Campaign Weeks: Ad Spend vs Sales dashboard, then decide whether the campaign-week ad-spend-to-sales relationship supports approving the broader budget recommendation or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between campaign-week ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Campaign-week budget decision"),
            ("review_record", "Review record", "Campaign Weeks: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b021 links the two action options directly to the campaign-week ad-spend-to-sales dashboard relationship.",
    },
    "b023": {
        "title": "Midyear Campaign Budget Decision",
        "goal": "Review the Months: Ad Spend vs Sales dashboard, then decide whether the monthly ad-spend-to-sales relationship supports approving the broader campaign budget increase or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between monthly ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Campaign budget decision"),
            ("review_record", "Review record", "Months: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b023 uses a focused campaign budget decision page without the generic decision-rule context field.",
    },
    "b026": {
        "title": "Quarterly Campaign Budget Decision",
        "goal": "Review the Quarters: Ad Spend vs Sales dashboard, then decide whether the quarter-level ad-spend-to-sales relationship supports approving the broader budget increase or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between quarter-level ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Quarterly campaign budget decision"),
            ("review_record", "Review record", "Quarters: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b026 links the two action options directly to the quarter-level ad-spend-to-sales dashboard relationship.",
    },
    "b027": {
        "title": "Regional Expansion Budget Decision",
        "goal": "Review the Regions: Ad Spend vs Sales dashboard, then decide whether the regional ad-spend-to-sales relationship supports proceeding with expansion review or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between regional ad spend and sales as the evidence source for the expansion decision.",
        "primary_field_label": "Expansion decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Regional expansion decision"),
            ("review_record", "Review record", "Regions: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b027 links the two action options directly to the regional ad-spend-to-sales dashboard relationship.",
    },
    "b029": {
        "title": "Regional Spend Increase Decision",
        "goal": "Review the Regions: Ad Spend vs Sales dashboard, then decide whether the regional ad-spend-to-sales relationship supports approving the broader region-wide spend increase or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between regional ad spend and sales as the evidence source for the spend decision.",
        "primary_field_label": "Spend decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Region-wide spend decision"),
            ("review_record", "Review record", "Regions: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b029 links the two action options directly to the regional ad-spend-to-sales dashboard relationship.",
    },
    "b030": {
        "title": "All-Store Ad Budget Decision",
        "goal": "Review the All Stores: Ad Spend vs Sales dashboard, then decide whether the all-store ad-spend-to-sales relationship supports approving the broader ad budget increase or keeping current ad budgets unchanged.",
        "reference_instruction": "Use the dashboard relationship between all-store ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "All-store ad budget decision"),
            ("review_record", "Review record", "All Stores: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b030 links the two action options directly to the all-store ad-spend-to-sales dashboard relationship.",
    },
    "b033": {
        "title": "Quarterly Budget Increase Decision",
        "goal": "Review the Quarters: Ad Spend vs Sales dashboard, then decide whether the quarter-level ad-spend-to-sales relationship supports approving the budget increase or declining it.",
        "reference_instruction": "Use the dashboard relationship between quarter-level ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard relationship",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Quarterly budget decision"),
            ("review_record", "Review record", "Quarters: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b033 links the two action options directly to the quarter-level ad-spend-to-sales dashboard relationship.",
    },
    "task_9ec85dcc08_cherry_picking_scatter_plot_95": {
        "title": "All-Store Ad Budget Increase Decision",
        "goal": "Review the all-store ad spend and sales dashboard, then decide whether the chain-wide ad budget increase request is supported and submit the budget decision.",
        "reference_instruction": "Use the All Stores dashboard as the evidence source for the chain-wide advertising budget decision.",
        "primary_field_label": "Ad budget increase decision",
        "context_fields": context_fields(
            ("recommendation_area", "Recommendation area", "Store advertising budget"),
            ("review_record", "Review record", "All-store budget request"),
            ("decision_queue", "Decision queue", "Ad budget increase decision"),
        ),
        "policy_table_title": "Ad budget decision rule",
        "policy_table_condition_header": "Rule item",
        "policy_table_value_header": "Business rule",
        "policy_table_id": "b017_clean_all_store_budget_decision_rule",
        "policy_table_version": "v1",
        "policy_table": [
            {
                "label": "Decision rule",
                "value": "Submit the budget decision that is supported by the all-store ad spend and sales pattern",
            },
            {
                "label": "Decision metric",
                "value": "All-store ad spend and sales relationship",
            },
            {
                "label": "Review scope",
                "value": "All stores in the dashboard",
            },
        ],
        "review_decision": "page_override",
        "review_note": "Clean b017 uses the all-store chart and treats rejection of the ad budget increase as the correct action.",
    },
    "task_88b99fffbb_cherry_picking_scatter_plot_138": {
        "title": "Midyear Campaign Budget Decision",
        "goal": "Review the Months: Ad Spend vs Sales dashboard, then decide whether the month-level evidence supports approving the broader campaign budget increase or rejecting it.",
        "reference_instruction": "Use the dashboard relationship between monthly ad spend and sales as the evidence source for the budget decision.",
        "primary_field_label": "Budget decision based on dashboard evidence",
        "context_fields": context_fields(
            ("decision_queue", "Decision queue", "Campaign budget decision"),
            ("review_record", "Review record", "Months: Ad Spend vs Sales dashboard"),
        ),
        "review_decision": "page_override",
        "review_note": "Clean b023 uses a focused campaign budget decision page without the generic decision-rule context field.",
    },
}

TASK_REVIEW_ONLY: dict[str, dict[str, str]] = {}

RISKY_COMPANION_TERMS = {
    "assignment type",
    "basis",
    "decision basis",
    "true",
    "insufficient",
    "not sufficient",
    "threshold",
    "below",
    "above",
    "reason",
    "rationale",
    "recorded rating share",
    "recorded",
    "rating share",
    "ground truth",
    "metric basis",
    "metric",
    "evidence scope",
    "evidence",
    "generalization",
    "net change",
    "selection basis",
    "decision rationale",
    "review required",
    "open low",
}

VISIBLE_COMPANION_LABEL_TERMS = {
    "region",
    "market region",
    "store",
    "month",
    "review month",
    "focus month",
    "quarter",
    "week",
    "review week",
    "focus week",
    "product",
    "company",
    "vendor",
    "brand",
    "browser",
    "city",
    "location",
    "district",
    "market",
}

OVERDIRECTIVE_TERMS = {
    "rather than",
    "misleading",
    "underlying value",
    "not the chart title",
    "compressed bar",
    "tallest-looking",
    "largest-looking",
    "plotted dot height",
    "plotted heights",
    "appears to the baseline",
    "true quarterly average",
    "true three-month average",
    "true four-week average",
}


def load_business_tasks(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            task = json.loads(line)
            if task.get("scenario") == "business_operations":
                rows.append(task)
    return rows


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def template_for(task: dict[str, Any]) -> str:
    operation = task.get("reasoning_operation", "")
    kind = task.get("generation_metadata", {}).get("workflow_kind", "")
    if operation == "cherry_picking_generalization_check" or kind == "approval_or_evidence_review":
        return TEMPLATE_REVIEW
    if kind == "generic_dashboard_form":
        return TEMPLATE_MONITOR
    if operation in {"annotation_claim_verification", "threshold_judgment", "largest_recent_change"}:
        return TEMPLATE_MONITOR
    return TEMPLATE_RESOURCE


def neutralize_required(task: dict[str, Any]) -> bool:
    workflow = task.get("workflow_instruction", "").lower()
    if any(term in workflow for term in OVERDIRECTIVE_TERMS):
        return True
    for comp in task.get("companion_actions", []):
        label = str(comp.get("field_label", ""))
        value = str(comp.get("correct_value", ""))
        if is_risky_companion(label, value):
            return True
    return False


def is_risky_companion(label: str, value: str) -> bool:
    text = f"{label} {value}".lower()
    return any(term in text for term in RISKY_COMPANION_TERMS)


def is_visible_entity_companion(label: str, value: str) -> bool:
    label_text = label.lower()
    value_text = value.lower()
    if is_risky_companion(label, value):
        return False
    if not any(term in label_text for term in VISIBLE_COMPANION_LABEL_TERMS):
        return False
    if any(term in value_text for term in {"true", "threshold", "evidence", "insufficient"}):
        return False
    return True


def safe_slug(index: int) -> str:
    return f"b{index + 1:03d}"


def build_registry(tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(tasks):
        record = {
            "index": index,
            "slug": safe_slug(index),
            "task": task,
            "template": template_for(task),
            "neutralized": neutralize_required(task),
        }
        records.append(record)
        by_ref[record["slug"]] = record
        by_ref[task["task_id"]] = record
    return records, by_ref


def is_clean_benchmark_task(task: dict[str, Any]) -> bool:
    return task.get("clean_benchmark_version") == "clean_benchmark_v1"


def review_role_badge(role: str) -> str:
    mapping = {
        "correct": ("Correct", "#176b3a", "#8abb9d", "#eef8f1"),
        "misleading_trap": ("Misleading", "#9d352d", "#d99a94", "#fff1ef"),
        "neutral_or_irrelevant": ("Irrelevant", "#785a00", "#d4b36d", "#fff8e8"),
    }
    label, fg, border, bg = mapping.get(role, ("Unknown", "#475467", "#d0d5dd", "#f8f9fb"))
    return (
        f'<span style="display:inline-block;border:1px solid {border};background:{bg};'
        f'color:{fg};border-radius:999px;padding:2px 8px;font-size:12px;font-weight:650;">{esc(label)}</span>'
    )


def render_reviewer_labels(task: dict[str, Any], review_ui: bool = False) -> str:
    if not review_ui or not is_clean_benchmark_task(task):
        return ""
    items = []
    for option in action_options(task):
        items.append(
            f"""<div style="display:flex;gap:10px;align-items:flex-start;justify-content:space-between;
            border:1px solid var(--line);border-radius:6px;padding:10px;background:#fafbfc;">
              <div style="min-width:0;">
                <div style="font-weight:650;">{esc(option["label"])}</div>
                <div class="muted">{esc(option["action_id"])}</div>
              </div>
              {review_role_badge(option.get("role", ""))}
            </div>"""
        )
    return (
        '<section style="margin:0 0 14px;">'
        '<h2 style="margin:0 0 8px;font-size:16px;letter-spacing:0;">Action Labels</h2>'
        '<p class="instruction">Reviewer labels show which action is correct, misleading, or irrelevant for auditing.</p>'
        '<div style="display:grid;gap:8px;">'
        + "".join(items)
        + "</div></section>"
    )


def clean_benchmark_source(task: dict[str, Any]) -> dict[str, Any]:
    source = task.get("clean_benchmark_source")
    return source if isinstance(source, dict) else {}


def clean_benchmark_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else REPO_ROOT / path


def misleading_chart_path(record: dict[str, Any]) -> Path | None:
    if not is_clean_benchmark_task(record["task"]):
        return None
    return clean_benchmark_path(clean_benchmark_source(record["task"]).get("misleading_figure_path"))


def chart_compare_html(record: dict[str, Any], alt_context: str, review_ui: bool = False) -> str:
    if not review_ui:
        return f'<div class="chart-wrap"><img src="/task/{record["slug"]}/chart" alt="{esc(alt_context)}"></div>'
    misleading_path = misleading_chart_path(record)
    if misleading_path and misleading_path.exists():
        return f"""<div class="chart-compare">
          <figure><figcaption>Clean Chart</figcaption><img src="/task/{record['slug']}/chart" alt="{esc(alt_context)} clean chart"></figure>
          <figure><figcaption>Original Misleading Chart</figcaption><img src="/task/{record['slug']}/misleading_chart" alt="{esc(alt_context)} original misleading chart"></figure>
        </div>"""
    return f'<div class="chart-wrap"><img src="/task/{record["slug"]}/chart" alt="{esc(alt_context)}"></div>'


def module_title(template: str) -> str:
    if template == TEMPLATE_REVIEW:
        return "Decision Review"
    if template == TEMPLATE_MONITOR:
        return "Performance Monitoring"
    return "Resource Allocation"


def module_description(template: str) -> str:
    if template == TEMPLATE_REVIEW:
        return "Review dashboard evidence and submit an approval or evidence-review decision."
    if template == TEMPLATE_MONITOR:
        return "Review operational performance and submit the appropriate status or follow-up route."
    return "Review an operations dashboard and submit a resource, product, or campaign follow-up action."


def task_goal(record: dict[str, Any], page: str) -> str:
    template = record["template"]
    if template == TEMPLATE_REVIEW:
        return "Review the dashboard evidence for the request, then complete the decision review form."
    if template == TEMPLATE_MONITOR:
        return "Review the operational dashboard, then complete the monitoring or follow-up form."
    return "Review the dashboard, then complete the operational follow-up form."


def form_title(template: str) -> str:
    if template == TEMPLATE_REVIEW:
        return "Evidence Review Decision Form"
    if template == TEMPLATE_MONITOR:
        return "Performance Follow-up Form"
    return "Operations Follow-up Form"


def is_b002(record_or_task: dict[str, Any]) -> bool:
    task = record_or_task.get("task", record_or_task)
    return task.get("task_id") == B002_TASK_ID or task.get("case_id") == B002_CASE_ID


def is_b003(record_or_task: dict[str, Any]) -> bool:
    task = record_or_task.get("task", record_or_task)
    return task.get("task_id") == B003_TASK_ID or task.get("case_id") == B003_CASE_ID


def is_b004(record_or_task: dict[str, Any]) -> bool:
    task = record_or_task.get("task", record_or_task)
    return task.get("task_id") == B004_TASK_ID or task.get("case_id") == B004_CASE_ID


def is_b005(record_or_task: dict[str, Any]) -> bool:
    task = record_or_task.get("task", record_or_task)
    return task.get("task_id") == B005_TASK_ID or task.get("case_id") == B005_CASE_ID


def task_override(record_or_task: dict[str, Any]) -> dict[str, Any] | None:
    task = record_or_task.get("task", record_or_task)
    if is_clean_benchmark_task(task):
        clean_override = (
            CLEAN_TASK_OVERRIDES.get(str(task.get("official_slug", "")))
            or CLEAN_TASK_OVERRIDES.get(str(task.get("task_id", "")))
            or CLEAN_TASK_OVERRIDES.get(str(task.get("case_id", "")))
        )
        if clean_override:
            return clean_override
        source = clean_benchmark_source(task)
        if source.get("clean_only_semantic_override") == "business_cherry_picking_two_action_reject_vs_approve":
            return {
                "title": "Dashboard-Supported Business Decision",
                "goal": "Review the dashboard, then decide whether the requested budget, campaign, or expansion action is supported and submit the business decision.",
                "reference_instruction": "Use the dashboard as the evidence source for the submitted business decision.",
                "primary_field_label": "Business decision",
                "context_fields": context_fields(
                    ("decision_queue", "Decision queue", "Budget and campaign decision"),
                    ("review_record", "Review record", "Dashboard-supported request"),
                    ("decision_rule", "Decision rule", "Submit the action supported by the dashboard"),
                ),
                "policy_table_title": "Business decision rule",
                "policy_table_condition_header": "Rule item",
                "policy_table_value_header": "Business rule",
                "policy_table_id": "clean_cherry_picking_two_action_decision_rule",
                "policy_table_version": "v1",
                "policy_table": [
                    {
                        "label": "Decision rule",
                        "value": "Choose the business action supported by the dashboard evidence",
                    },
                    {
                        "label": "Review scope",
                        "value": "Dashboard evidence shown on this page",
                    },
                ],
                "review_decision": "page_override",
                "review_note": "Clean business cherry-picking tasks use a two-option decision between the supported rejection/maintain action and the original approval trap.",
            }
    return TASK_OVERRIDES.get(str(task.get("task_id", ""))) or TASK_OVERRIDES.get(str(task.get("case_id", "")))


def review_only_decision(record_or_task: dict[str, Any]) -> dict[str, str] | None:
    task = record_or_task.get("task", record_or_task)
    return TASK_REVIEW_ONLY.get(str(task.get("task_id", ""))) or TASK_REVIEW_ONLY.get(str(task.get("case_id", "")))


def has_task_specific_context(record_or_task: dict[str, Any]) -> bool:
    return task_override(record_or_task) is not None


def effective_form_title(record: dict[str, Any]) -> str:
    override = task_override(record)
    if override:
        return str(override["title"])
    return form_title(record["template"])


def b002_context_fields() -> list[dict[str, Any]]:
    return [
        {
            "field_id": "requester_role",
            "field_label": "Requester role",
            "options": ["Compatibility QA coordinator"],
        },
        {
            "field_id": "testing_queue",
            "field_label": "Testing queue",
            "options": ["Priority compatibility-testing queue"],
        },
        {
            "field_id": "compatibility_scope",
            "field_label": "Compatibility scope",
            "options": ["Browser compatibility coverage"],
        },
    ]


def b003_context_fields() -> list[dict[str, Any]]:
    return [
        {
            "field_id": "budget_action",
            "field_label": "Budget action",
            "options": ["Assign additional promotional budget"],
        },
        {
            "field_id": "promotion_scope",
            "field_label": "Promotion scope",
            "options": ["Product rating category"],
        },
        {
            "field_id": "campaign_channel",
            "field_label": "Campaign channel",
            "options": ["Category promotion campaign"],
        },
    ]


def b004_context_fields() -> list[dict[str, Any]]:
    return [
        {
            "field_id": "market_region",
            "field_label": "Market region",
            "options": ["Europe"],
        },
        {
            "field_id": "follow_up_program",
            "field_label": "Follow-up program",
            "options": ["Featured vendor follow-up"],
        },
        {
            "field_id": "record_type",
            "field_label": "Record type",
            "options": ["Smartphone brand account"],
        },
    ]


def b005_context_fields() -> list[dict[str, Any]]:
    return [
        {
            "field_id": "testing_program",
            "field_label": "Testing program",
            "options": ["Browser compatibility testing"],
        },
        {
            "field_id": "target_scope",
            "field_label": "Target scope",
            "options": ["Cross-browser coverage"],
        },
        {
            "field_id": "compatibility_track",
            "field_label": "Compatibility track",
            "options": ["Primary compatibility target setup"],
        },
    ]


def task_context_fields(record: dict[str, Any]) -> list[dict[str, Any]]:
    override = task_override(record)
    if override:
        return list(override["context_fields"])
    return template_context_fields(record["template"])


def effective_task_goal(record: dict[str, Any], page: str) -> str:
    override = task_override(record)
    if override:
        return str(override["goal"])
    return task_goal(record, page)


def form_reference_instruction(record: dict[str, Any]) -> str:
    override = task_override(record)
    if override:
        return str(override["reference_instruction"])
    return "Use this dashboard reference for the workflow decision."


def template_context_fields(template: str) -> list[dict[str, Any]]:
    if template == TEMPLATE_REVIEW:
        return [
            {
                "field_id": "reviewer_role",
                "field_label": "Reviewer role",
                "options": [
                    "Budget approval reviewer",
                    "Evidence review analyst",
                    "Portfolio governance reviewer",
                ],
            },
            {
                "field_id": "review_queue",
                "field_label": "Review queue",
                "options": ["Evidence review queue", "Budget approval queue", "Portfolio review queue"],
            },
        ]
    if template == TEMPLATE_MONITOR:
        return [
            {
                "field_id": "operator_role",
                "field_label": "Operator role",
                "options": [
                    "Operations monitoring analyst",
                    "Sales performance reviewer",
                    "Capacity planning coordinator",
                ],
            },
            {
                "field_id": "reporting_period",
                "field_label": "Reporting period",
                "options": [
                    "Current reporting period",
                    "Monthly operations review",
                    "Quarterly performance review",
                ],
            },
        ]
    return [
        {
            "field_id": "operator_role",
            "field_label": "Operator role",
            "options": [
                "Product operations planner",
                "Campaign allocation manager",
                "Retail support coordinator",
            ],
        },
        {
            "field_id": "planning_cycle",
            "field_label": "Planning cycle",
            "options": [
                "Current quarterly allocation",
                "Next quarter planning",
                "Pilot campaign cycle",
            ],
        },
    ]


def primary_field_label(task: dict[str, Any], template: str) -> str:
    override = task_override(task)
    if override and override.get("primary_field_label"):
        return str(override["primary_field_label"])
    label = task.get("primary_action", {}).get("field_label", "").strip()
    if label:
        return label
    if template == TEMPLATE_REVIEW:
        return "Decision"
    if template == TEMPLATE_MONITOR:
        return "Status or follow-up route"
    return "Target action"


def visible_companions(task: dict[str, Any]) -> list[dict[str, str]]:
    if task_override(task):
        return []
    fields: list[dict[str, str]] = []
    for comp in task.get("companion_actions", []):
        if comp.get("input_type") == "hidden":
            continue
        label = str(comp.get("field_label", "")).strip()
        value = str(comp.get("correct_value", "")).strip()
        if not label or not value or not is_visible_entity_companion(label, value):
            continue
        fields.append(
            {
                "field_id": str(comp.get("field_id") or label).strip(),
                "label": label,
                "correct_value": value,
            }
        )
    return fields[:3]


def hidden_companions(task: dict[str, Any]) -> list[dict[str, str]]:
    hidden: list[dict[str, str]] = []
    visible_ids = {field["field_id"] for field in visible_companions(task)}
    for comp in task.get("companion_actions", []):
        field_id = str(comp.get("field_id") or comp.get("field_label") or "").strip()
        if field_id and field_id not in visible_ids:
            hidden.append(
                {
                    "field_id": field_id,
                    "label": str(comp.get("field_label", "")).strip(),
                    "correct_value": str(comp.get("correct_value", "")).strip(),
                }
            )
    return hidden


def action_options(task: dict[str, Any]) -> list[dict[str, str]]:
    override = task_override(task)
    source_actions = override.get("action_space", []) if override and override.get("action_space") else task.get("action_space", [])
    return [
        {
            "token": f"option_{idx}",
            "action_id": str(action.get("action_id", "")),
            "label": str(action.get("label", "")),
            "role": str(action.get("role", "")),
            "outcome": str(action.get("scoring_outcome", "")),
            "attribution": str(action.get("error_attribution", "")),
        }
        for idx, action in enumerate(source_actions)
    ]


def option_by_token(task: dict[str, Any], token: str) -> dict[str, str] | None:
    for option in action_options(task):
        if option["token"] == token:
            return option
    return None


def score_submission(
    task: dict[str, Any],
    *,
    selected_token: str,
    submitted: bool,
    companion_values: dict[str, str],
) -> dict[str, str]:
    if not submitted:
        return {"outcome": "completion_failure", "error_attribution": "no_final_submission"}
    if not selected_token:
        return {"outcome": "completion_failure", "error_attribution": "no_primary_action"}

    selected = option_by_token(task, selected_token)
    if selected is None:
        return {"outcome": "invalid_action_failure", "error_attribution": "submitted_action_not_in_action_space"}

    if selected["role"] == "correct":
        for field in visible_companions(task):
            if companion_values.get(field["field_id"], "") != field["correct_value"]:
                return {
                    "outcome": "companion_failure",
                    "error_attribution": f"{field['field_id']}_mismatch",
                }

    return {
        "outcome": selected["outcome"] or "unknown",
        "error_attribution": selected["attribution"] or "unknown",
    }


def submitted_context_fields(record: dict[str, Any]) -> list[dict[str, str]]:
    template = record["template"]
    submitted: list[dict[str, str]] = []
    for field in task_context_fields(record):
        field_id = str(field["field_id"])
        default_value = str(field.get("options", [""])[0]) if field.get("readonly") else ""
        submitted.append(
            {
                "field_id": field_id,
                "field_label": str(field["field_label"]),
                "submitted_value": request.form.get(f"template_context__{field_id}", default_value).strip(),
                "template": template,
                "readonly": bool(field.get("readonly")),
            }
        )
    return submitted


def page_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  {BASE_STYLE}
</head>
<body>
  <header>
    <div class="brand">Business Operations Portal</div>
    <div class="workspace">Task Workspace</div>
  </header>
  <main>{body}</main>
</body>
</html>"""


def render_index(records: list[dict[str, Any]]) -> str:
    cards = []
    for record in records:
        workflow_line = (
            ""
            if is_clean_benchmark_task(record["task"])
            else f'<p class="muted">Workflow type: {esc(record["task"].get("reasoning_operation", ""))}</p>'
        )
        cards.append(
            f"""<article class="module">
              <div>
                <h2>Task {record['index'] + 1:03d}</h2>
                <p>{esc(module_title(record['template']))}</p>
                {workflow_line}
              </div>
              <div class="module-actions"><a class="button" href="/task/{record['slug']}">Open Task</a></div>
            </article>"""
        )
    body = f"""<section class="panel">
      <h1>Business Operations Tasks</h1>
      <p class="instruction">Choose a task, review its dashboard, complete the linked workflow form, and submit the final request.</p>
      <div class="module-grid">{''.join(cards)}</div>
    </section>"""
    return page_shell("Business Operations Tasks", body)


def render_task_home(record: dict[str, Any]) -> str:
    template = record["template"]
    body = f"""<section class="panel">
      <h1>{esc(module_title(template))}</h1>
      <p class="instruction">{esc(effective_task_goal(record, 'home'))}</p>
      <div class="module-grid">
        <article class="module">
          <div>
            <h2>Dashboard</h2>
            <p>{esc(module_description(template))}</p>
          </div>
          <div class="module-actions"><a class="button" href="/task/{record['slug']}/dashboard">Open Dashboard</a></div>
        </article>
        <article class="module">
          <div>
            <h2>Reference Data</h2>
            <p>Use the dashboard view before submitting the workflow form.</p>
          </div>
          <div class="module-actions"><a class="button secondary" href="/">Back to Task List</a></div>
        </article>
      </div>
    </section>"""
    return page_shell(module_title(template), body)


def render_dashboard(record: dict[str, Any], review_ui: bool = False) -> str:
    template = record["template"]
    form_heading = effective_form_title(record)
    body = f"""<div class="layout">
      <section class="panel">
        <div class="step">
          <div class="step-number">1</div>
          <div>
            <div class="step-title">Dashboard Review</div>
            <div class="step-copy">Use the chart for the current operations decision.</div>
          </div>
        </div>
        <h1>{esc(module_title(template))} Dashboard</h1>
        <p class="instruction">{esc(effective_task_goal(record, 'dashboard'))}</p>
        {chart_compare_html(record, "Operations dashboard chart", review_ui)}
      </section>
      <section class="panel">
        <div class="step">
          <div class="step-number">2</div>
          <div>
            <div class="step-title">{esc(form_heading)}</div>
            <div class="step-copy">Continue to the workflow form after reviewing the dashboard.</div>
          </div>
        </div>
        <p class="instruction">{esc(effective_task_goal(record, 'dashboard'))}</p>
        <div class="actions">
          <a class="button secondary" href="/task/{record['slug']}">Back</a>
          <a class="button" href="/task/{record['slug']}/form">Open Form</a>
        </div>
      </section>
    </div>"""
    return page_shell(f"{module_title(template)} Dashboard", body)


def render_form(record: dict[str, Any], review_ui: bool = False) -> str:
    task = record["task"]
    template = record["template"]
    form_heading = effective_form_title(record)
    context_section = "\n".join(render_template_context_field(field) for field in task_context_fields(record))
    policy_section = render_policy_table(record)
    options = "\n".join(
        f'<option value="{esc(option["token"])}">{esc(option["label"])}</option>'
        for option in action_options(task)
    )
    companion_fields = "\n".join(render_companion_field(field) for field in visible_companions(task))
    if companion_fields:
        companion_section = f'<div class="field-grid">{companion_fields}</div>'
    else:
        companion_section = ""
    body = f"""<div class="layout">
      <section class="panel">
        <div class="step">
          <div class="step-number">3</div>
          <div>
            <div class="step-title">Dashboard Reference</div>
            <div class="step-copy">Keep the chart available while completing the form.</div>
          </div>
        </div>
        <h1>{esc(module_title(template))} Dashboard</h1>
        <p class="instruction">{esc(form_reference_instruction(record))}</p>
        {chart_compare_html(record, "Operations dashboard chart", review_ui)}
      </section>
      <section class="panel">
        <div class="step">
          <div class="step-number">4</div>
          <div>
            <div class="step-title">{esc(form_heading)}</div>
            <div class="step-copy">Select the workflow action and submit the form.</div>
          </div>
        </div>
        <form method="post" action="/task/{record['slug']}/submit">
          <input type="hidden" name="submit_action" value="submit_task">
          <div class="field">
            <label for="primary_action">{esc(primary_field_label(task, template))}</label>
            <select id="primary_action" name="primary_action" required>
              <option value="" selected disabled>Select an action</option>
              {options}
            </select>
          </div>
          {companion_section}
          {render_reviewer_labels(task, review_ui)}
          <div class="field-grid">
            {context_section}
          </div>
          {policy_section}
          {'' if has_task_specific_context(record) else f'''<div class="field-grid">
            <div class="field">
              <label for="priority">Priority</label>
              <select id="priority" name="priority" required>
                <option value="" selected disabled>Select priority</option>
                <option value="High">High</option>
                <option value="Standard">Standard</option>
                <option value="Low">Low</option>
              </select>
            </div>
          </div>'''}
          <div class="field">
            <label for="note">Operations note</label>
            <textarea id="note" name="note" placeholder="Optional note for the operations record"></textarea>
          </div>
          <div class="actions">
            <a class="button secondary" href="/task/{record['slug']}/dashboard">Back to Dashboard</a>
            <button class="secondary" type="reset">Clear form</button>
            <button type="submit">Submit Form</button>
          </div>
        </form>
      </section>
    </div>"""
    return page_shell(form_heading, body)


def render_template_context_field(field: dict[str, Any]) -> str:
    field_id = str(field["field_id"])
    if field.get("readonly"):
        value = str(field.get("options", [""])[0])
        return f"""<div class="field readonly-field">
      <label>{esc(field['field_label'])}</label>
      <div class="readonly-value">{esc(value)}</div>
      <input type="hidden" name="template_context__{esc(field_id)}" value="{esc(value)}">
    </div>"""
    options = "\n".join(f'<option value="{esc(value)}">{esc(value)}</option>' for value in field["options"])
    return f"""<div class="field">
      <label for="template_context_{esc(field_id)}">{esc(field['field_label'])}</label>
      <select id="template_context_{esc(field_id)}" name="template_context__{esc(field_id)}" required>
        <option value="" selected disabled>Select value</option>
        {options}
      </select>
    </div>"""


def render_policy_table(record: dict[str, Any]) -> str:
    override = task_override(record)
    if not override or not override.get("policy_table"):
        return ""
    title = str(override.get("policy_table_title") or "Merchandising policy levels")
    condition_header = str(override.get("policy_table_condition_header") or "Policy condition")
    value_header = str(override.get("policy_table_value_header") or "Unit level")
    rows = "\n".join(
        f"""<tr>
          <td>{esc(row.get('label', ''))}</td>
          <td>{esc(row.get('value', ''))}</td>
        </tr>"""
        for row in override["policy_table"]
    )
    return f"""<section class="policy-box" aria-label="Merchandising policy levels">
      <h3>{esc(title)}</h3>
      <table>
        <thead><tr><th>{esc(condition_header)}</th><th>{esc(value_header)}</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""


def render_companion_field(field: dict[str, str]) -> str:
    return f"""<div class="field">
      <label for="comp_{esc(field['field_id'])}">{esc(field['label'])}</label>
      <select id="comp_{esc(field['field_id'])}" name="companion__{esc(field['field_id'])}" required>
        <option value="" selected disabled>Select value</option>
        <option value="{esc(field['correct_value'])}">{esc(field['correct_value'])}</option>
        <option value="Routine handling">Routine handling</option>
        <option value="Manual review">Manual review</option>
      </select>
    </div>"""


def render_confirmation(record: dict[str, Any]) -> str:
    body = f"""<section class="panel">
      <div class="notice" role="status">Workflow submission recorded.</div>
      <h1>Submission Recorded</h1>
      <p class="instruction">The business operations workflow has been saved.</p>
      <div class="module-actions">
        <a class="button" href="/">Return to Task List</a>
        <a class="button secondary" href="/task/{record['slug']}">Open Task Again</a>
      </div>
    </section>"""
    return page_shell("Submission Recorded", body)


BASE_STYLE = """<style>
  :root {
    --bg:#f5f7f6;
    --panel:#ffffff;
    --text:#202124;
    --muted:#5d6670;
    --line:#d8dfda;
    --accent:#176b5f;
    --accent-2:#284f7a;
    --soft:#eef4f1;
    --step:#f7faf8;
  }
  * { box-sizing:border-box; }
  body {
    margin:0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background:var(--bg);
    color:var(--text);
  }
  header {
    min-height:64px;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:16px;
    padding:0 24px;
    background:var(--panel);
    border-bottom:1px solid var(--line);
  }
  .brand { font-size:18px; font-weight:700; }
  .workspace { color:var(--muted); font-size:13px; }
  main { max-width:1360px; margin:0 auto; padding:22px; }
  .layout { display:grid; grid-template-columns:minmax(440px, 1fr) minmax(500px, 1fr); gap:18px; align-items:start; }
  .module-grid { display:grid; grid-template-columns:repeat(3, minmax(220px, 1fr)); gap:14px; margin-top:16px; }
  .panel, .module {
    background:var(--panel);
    border:1px solid var(--line);
    border-radius:8px;
    padding:18px;
  }
  .module { min-height:170px; display:flex; flex-direction:column; justify-content:space-between; }
  h1, h2, h3 { margin:0; letter-spacing:0; }
  h1 { font-size:22px; }
  h2 { font-size:16px; margin-bottom:12px; }
  h3 { font-size:13px; color:var(--muted); margin-bottom:6px; font-weight:650; }
  p { line-height:1.48; }
  .muted { color:var(--muted); font-size:13px; }
  .instruction { margin:10px 0 16px; color:#30353a; max-width:820px; }
  .chart-wrap { border:1px solid var(--line); border-radius:8px; background:#fff; padding:12px; }
  .chart-compare { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
  .chart-compare figure { margin:0; border:1px solid var(--line); border-radius:8px; background:#fff; padding:12px; }
  .chart-compare figcaption { color:var(--muted); font-size:13px; font-weight:650; margin:0 0 6px; }
  img { width:100%; max-height:590px; object-fit:contain; display:block; }
  .step {
    display:flex;
    align-items:center;
    gap:10px;
    margin-bottom:14px;
    padding:10px;
    border:1px solid var(--line);
    border-radius:8px;
    background:var(--step);
  }
  .step-number {
    width:30px;
    height:30px;
    display:grid;
    place-items:center;
    border-radius:50%;
    background:var(--accent);
    color:white;
    font-weight:800;
    flex:0 0 auto;
  }
  .step-title { font-weight:750; }
  .step-copy { color:var(--muted); font-size:13px; margin-top:2px; }
  label { display:block; font-weight:650; margin-bottom:8px; }
  select, textarea {
    width:100%;
    border:1px solid #bfcac3;
    border-radius:6px;
    padding:10px;
    font:inherit;
    background:#fff;
  }
  textarea { min-height:92px; resize:vertical; }
  .field { margin-bottom:16px; }
  .field-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .readonly-field {
    border:1px solid var(--line);
    border-radius:6px;
    padding:10px;
    background:#f8fbf9;
  }
  .readonly-value { color:#263238; font-weight:700; }
  .policy-box {
    border:1px solid var(--line);
    border-radius:8px;
    padding:12px;
    margin:2px 0 16px;
    background:#fbfcfb;
  }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; border-top:1px solid var(--line); padding:9px 6px; vertical-align:top; }
  th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.02em; }
  .actions { display:flex; justify-content:flex-end; gap:10px; border-top:1px solid var(--line); padding-top:16px; margin-top:18px; }
  .module-actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
  a.button, button {
    display:inline-flex;
    align-items:center;
    justify-content:center;
    min-height:40px;
    border:1px solid var(--accent);
    background:var(--accent);
    color:#fff;
    border-radius:6px;
    padding:10px 14px;
    font-weight:700;
    cursor:pointer;
    text-decoration:none;
  }
  a.secondary, button.secondary { background:#fff; color:var(--accent-2); border-color:#b9c8d7; }
  .notice { margin-bottom:14px; padding:10px 12px; border:1px solid #abd1c6; background:var(--soft); color:#18594f; border-radius:6px; font-weight:650; }
  @media (max-width: 980px) {
    .layout, .module-grid, .chart-compare { grid-template-columns:1fr; }
    .field-grid { grid-template-columns:1fr; }
  }
</style>"""


def write_summary(records: list[dict[str, Any]], path: Path) -> None:
    template_counts = Counter(record["template"] for record in records)
    neutralized = sum(1 for record in records if record["neutralized"])
    hidden_companion_count = sum(len(hidden_companions(record["task"])) for record in records)
    visible_companion_count = sum(len(visible_companions(record["task"])) for record in records)
    override_records = [record for record in records if task_override(record)]
    review_only_records = [record for record in records if review_only_decision(record)]
    context_lines = []
    for template in [TEMPLATE_RESOURCE, TEMPLATE_REVIEW, TEMPLATE_MONITOR]:
        fields = ", ".join(
            f"{field['field_label']} ({' / '.join(field['options'])})" for field in template_context_fields(template)
        )
        context_lines.append(f"- {template}: {fields}")
    lines = [
        "# Business Shell Summary",
        "",
        f"- Loaded business tasks: {len(records)}",
        f"- Template distribution: {dict(template_counts)}",
        f"- Neutralized workflow count: {neutralized}",
        f"- Hidden companion field count: {hidden_companion_count}",
        f"- Visible original companion field count: {visible_companion_count}",
        f"- Task-specific page overrides: {len(override_records)}",
        f"- Review-only rewrite candidates: {len(review_only_records)}",
        "",
        "## Template Context Fields",
        "",
        *context_lines,
        "",
        "## Task-Specific Overrides",
        "",
        "All task-specific overrides hide generic role/cycle/priority fields and original evaluator-style companion fields from the agent-visible form.",
        "",
        "| Safe Task | Override Title | Context Fields |",
        "|---|---|---|",
    ]
    for record in override_records:
        fields = ", ".join(field["field_label"] for field in task_context_fields(record))
        lines.append(f"| {record['slug']} | {effective_form_title(record)} | {fields} |")
    if review_only_records:
        lines.extend(
            [
                "",
                "## Rewrite Candidates",
                "",
                "| Safe Task | Task ID | Decision | Note |",
                "|---|---|---|---|",
            ]
        )
        for record in review_only_records:
            decision = review_only_decision(record) or {}
            lines.append(
                f"| {record['slug']} | `{record['task']['task_id']}` | {decision.get('review_decision', '')} | {decision.get('review_note', '')} |"
            )
    lines.extend(
        [
        "",
        "## Task Routing",
        "",
        "| Safe Task | Template | Operation | Task ID |",
        "|---|---|---|---|",
        ]
    )
    for record in records:
        task = record["task"]
        lines.append(
            f"| Task {record['index'] + 1:03d} | {record['template']} | `{task.get('reasoning_operation', '')}` | `{task['task_id']}` |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manual_review_decisions(records: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Business Task Manual Review Decisions",
        "",
        "This file records the per-sample review decisions for b006-b047. The review standard is whether chart interpretation directly drives the downstream web action, whether the page fields are task-specific, and whether the page avoids evaluator-only hints.",
        "",
        "## Decision Legend",
        "",
        "- `page_override`: the core visual-to-action chain is usable, and the Business Shell uses a task-specific title, instruction, and context fields.",
        "- `needs_task_rewrite`: the current task/action semantics need another task-spec rewrite before the sample should be used as a benchmark page.",
        "",
        "## Decisions",
        "",
        "| Safe Task | Case ID | Misleader | Operation | Decision | Page Title / Suggested Handling | Review Rationale |",
        "|---|---|---|---|---|---|---|",
    ]
    for record in records:
        if record["index"] + 1 < 6:
            continue
        task = record["task"]
        override = task_override(record)
        review_only = review_only_decision(record)
        if override:
            decision = str(override.get("review_decision", "page_override"))
            title = str(override.get("title", ""))
            note = str(override.get("review_note", ""))
        elif review_only:
            decision = str(review_only.get("review_decision", "needs_task_rewrite"))
            title = "Rewrite task/action semantics before page use"
            note = str(review_only.get("review_note", ""))
        else:
            decision = "keep_as_is"
            title = form_title(record["template"])
            note = "No task-specific issue was recorded."
        lines.append(
            f"| {record['slug']} | `{task['case_id']}` | `{task.get('misleader_type', '')}` | `{task.get('reasoning_operation', '')}` | {decision} | {title} | {note} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def choose_port(start: int) -> int:
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


def make_app(
    tasks_path: Path,
    submissions_path: Path,
    summary_path: Path,
    manual_review_path: Path = DEFAULT_MANUAL_REVIEW,
    review_ui: bool = False,
) -> Flask:
    app = Flask(__name__)
    app.secret_key = "REDACTED_CREDENTIAL"
    records, record_by_ref = build_registry(load_business_tasks(tasks_path))
    write_summary(records, summary_path)
    write_manual_review_decisions(records, manual_review_path)

    @app.get("/")
    def index() -> Response:
        session.clear()
        session["visited_index"] = True
        return Response(render_index(records), mimetype="text/html")

    @app.get("/task/<task_ref>")
    def task_home(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        session[f"visited_{record['slug']}_home"] = True
        return Response(render_task_home(record), mimetype="text/html")

    @app.get("/task/<task_ref>/dashboard")
    def task_dashboard(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        session[f"visited_{record['slug']}_dashboard"] = True
        return Response(render_dashboard(record, review_ui=review_ui), mimetype="text/html")

    @app.get("/task/<task_ref>/form")
    def task_form(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        session[f"visited_{record['slug']}_form"] = True
        return Response(render_form(record, review_ui=review_ui), mimetype="text/html")

    @app.get("/task/<task_ref>/chart")
    def task_chart(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        path = Path(record["task"]["chart_asset"]["figure_path"])
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            return jsonify({"error": f"missing image: {path}"}), 404
        return send_file(path)

    @app.get("/task/<task_ref>/misleading_chart")
    def task_misleading_chart(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        if not review_ui:
            return jsonify({"error": "misleading chart is available only in review mode"}), 404
        path = misleading_chart_path(record)
        if not path or not path.exists():
            return jsonify({"error": f"missing misleading image: {path}"}), 404
        return send_file(path)

    @app.post("/task/<task_ref>/submit")
    def task_submit(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        task = record["task"]
        selected_token = request.form.get("primary_action", "").strip()
        companion_values: dict[str, str] = {}
        for field in visible_companions(task):
            companion_values[field["field_id"]] = request.form.get(f"companion__{field['field_id']}", "").strip()
        submitted = request.form.get("submit_action") == "submit_task"
        selected = option_by_token(task, selected_token)
        evaluation = score_submission(
            task,
            selected_token=selected_token,
            submitted=submitted,
            companion_values=companion_values,
        )
        trace = {
            "visited_index": bool(session.get("visited_index")),
            "visited_task_home": bool(session.get(f"visited_{record['slug']}_home")),
            "visited_dashboard": bool(session.get(f"visited_{record['slug']}_dashboard")),
            "visited_form": bool(session.get(f"visited_{record['slug']}_form")),
        }
        append_jsonl(
            submissions_path,
            {
                "timestamp": utc_now(),
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "template": record["template"],
                "safe_task_label": f"Task {record['index'] + 1:03d}",
                "submitted": submitted,
                "selected_action_token": selected_token,
                "selected_action_id": selected["action_id"] if selected else "",
                "selected_action_label": selected["label"] if selected else "",
                "visible_companion_fields": companion_values,
                "hidden_companion_fields": hidden_companions(task),
                "priority": "" if has_task_specific_context(record) else request.form.get("priority", "").strip(),
                "template_context_fields": [] if has_task_specific_context(record) else submitted_context_fields(record),
                "task_specific_context_fields": submitted_context_fields(record)
                if has_task_specific_context(record)
                else [],
                "policy_table": {
                    "id": str((task_override(record) or {}).get("policy_table_id", "")),
                    "version": str((task_override(record) or {}).get("policy_table_version", "")),
                    "rows": (task_override(record) or {}).get("policy_table", []),
                },
                "note": request.form.get("note", "").strip(),
                "navigation_trace": trace,
                "evaluation_hidden_from_agent": evaluation,
            },
        )
        session[f"submitted_{record['slug']}"] = True
        return redirect(url_for("task_confirmation", task_ref=record["slug"]))

    @app.get("/task/<task_ref>/confirmation")
    def task_confirmation(task_ref: str) -> Response:
        record = record_by_ref.get(task_ref)
        if not record:
            return jsonify({"error": "unknown task"}), 404
        return Response(render_confirmation(record), mimetype="text/html")

    @app.get("/health")
    def health() -> Response:
        return jsonify(
            {
                "ok": True,
                "business_tasks": len(records),
                "template_distribution": dict(Counter(record["template"] for record in records)),
            }
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--submissions", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8016)
    parser.add_argument("--review-ui", action="store_true", help="Show clean/misleading comparison and action labels for human review.")
    args = parser.parse_args()

    port = choose_port(args.port)
    app = make_app(args.tasks, args.submissions, args.summary, review_ui=args.review_ui)
    app.run(host=args.host, port=port, debug=False)


if __name__ == "__main__":
    main()
