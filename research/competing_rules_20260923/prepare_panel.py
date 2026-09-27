# -*- coding: utf-8 -*-
"""Prepare reproducible, OFFLINE inventory/configuration; never run experiments.

The output is evaluator-side research metadata, not an agent input package.
This utility only reads the existing snapshot and writes its three named outputs.
Use --check to validate the prepared artifacts without modifying any file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
INVENTORY = WORKSPACE / ".aris/dataset_inventory_20260918"
HISTORY = WORKSPACE / ".aris/multimodel_20260916"
DEMO_IDS = ("pub013", "health004", "b046")
DOMAINS = ("business47", "public39", "environment35", "health19")
CONDITIONS = ("official140", "clean140")
PAIR_INVARIANTS = (
    "task_id", "case_id", "workflow_instruction", "chart_reference",
    "ground_truth", "intermediate_decision", "primary_action", "companion_actions",
    "action_space", "expected_action_id", "misleading_action_ids", "fallback_scoring",
    "completion_action",
)
OWNED_OUTPUTS = ("panel140_manifest.json", "configs/panel140_draft.json",
                 "DATASET_ADAPTATION_20260923.md")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def source_info(path):
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def snapshot_path(relative):
    path = (INVENTORY / relative.replace("\\", "/")).resolve()
    if INVENTORY.resolve() not in path.parents or not path.is_file():
        raise ValueError("Missing or out-of-snapshot source: " + str(path))
    return path


def read_task_rows():
    rows, sources = {}, []
    for condition in CONDITIONS:
        for domain in DOMAINS:
            path = INVENTORY / "raw/splits" / condition / (domain + "_tasks.jsonl")
            sources.append(source_info(path))
            for line_number, raw in enumerate(path.read_bytes().splitlines(), 1):
                if not raw.strip():
                    continue
                value = json.loads(raw)
                slug = value.get("task_slug") or value["official_slug"]
                key = (condition, slug)
                if key in rows:
                    raise ValueError("Duplicate task: " + str(key))
                rows[key] = (value, {
                    "spec_path": str(path), "spec_line_number": line_number,
                    "record_sha256_excluding_line_ending": hashlib.sha256(raw).hexdigest(),
                })
    return rows, sources


def old_exposure():
    """Use historical attempted cases, never select based on their outcomes."""
    evidence = HISTORY / "delivery/ALL_CASES.json"
    protocol = HISTORY / "source/multi_model_simple_check/PROTOCOL.md"
    if not evidence.is_file():
        return set(), [], "historical_case_record_unavailable"
    rows = json.loads(evidence.read_text(encoding="utf-8-sig"))
    task_ids = {row["task_slug"] for row in rows if row.get("task_slug")}
    sources = [source_info(evidence)]
    if protocol.is_file():
        sources.append(source_info(protocol))
    return task_ids, sources, "historical_attempt_records_available"


def compile_artifacts():
    catalog_path = INVENTORY / "TASK_CATALOG.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    if len(catalog) != 140 or len({row["slug"] for row in catalog}) != 140:
        raise ValueError("Expected exactly 140 unique catalog tasks")
    specs, spec_sources = read_task_rows()
    if len(specs) != 280:
        raise ValueError("Expected exactly 280 paired task records")
    old_ids, exposure_sources, exposure_status = old_exposure()
    slugs = {row["slug"] for row in catalog}
    if not old_ids.issubset(slugs) or not set(DEMO_IDS).issubset(slugs):
        raise ValueError("Exposure IDs are not within the 140-task snapshot")
    known_dev = old_ids | set(DEMO_IDS)
    provenance = [source_info(catalog_path),
                  source_info(INVENTORY / "DATASET_140_AUDIT.md"),
                  source_info(INVENTORY / "LINEAGE.md")] + spec_sources + exposure_sources
    families, parents, images = defaultdict(list), defaultdict(list), defaultdict(list)
    rows = []
    for entry in catalog:
        slug = entry["slug"]
        original = specs[("official140", slug)][0]
        clean = specs[("clean140", slug)][0]
        changed = [key for key in PAIR_INVARIANTS if original.get(key) != clean.get(key)]
        pair_assets = {}
        for condition, spec, relative, expected in (
            ("official140", original, entry["assets"]["figure_path"]["path"],
             entry["assets"]["figure_path"]["sha256"]),
            ("clean140", clean, entry["clean_image_path"], entry["clean_figure_sha256"]),
        ):
            path = snapshot_path(relative)
            digest = sha256(path)
            if digest != expected:
                raise ValueError("Image differs from audited catalog: " + str(path))
            pair_assets[condition] = {
                "original_release_path": spec["chart_asset"]["figure_path"],
                "snapshot_relative_path": relative,
                "snapshot_absolute_path": str(path),
                "sha256": digest, "bytes": path.stat().st_size,
                "task_instance_id": spec.get("task_instance_id"),
                "original_readiness": spec.get("task_readiness"),
                "original_scoring_status": spec.get("scoring_status"),
                "original_action_option_count": len(spec.get("action_space", [])),
                **specs[(condition, slug)][1],
            }
        family = entry["core_task_family"]
        parent = entry["source_parent_code"]
        families[family].append(slug)
        parents[parent].append(slug)
        images[pair_assets["official140"]["sha256"]].append(slug)
        sources = []
        if slug in old_ids:
            sources.append("historical_eight_task_attempt_records")
        if slug in DEMO_IDS:
            sources.append("predeclared_20260923_development_demo")
        flags = []
        mechanism = entry["audited_mechanism"]
        if mechanism in {"选择性呈现时间区间", "选择性呈现样本／子群"}:
            flags.append("visible_scope_may_not_support_full_task_population_or_period")
        if mechanism == "几何编码与标注数值不一致":
            flags.append("conflicting_visible_cues_do_not_hardcode_preferred_channel")
        if slug == "pub005":
            flags.append("coarse_bins_do_not_determine_within_bin_strict_rank")
        if slug == "pub019":
            flags.append("published_asset_does_not_show_registered_reversed_color_mechanism")
        if slug in {"env004", "b011"}:
            flags.append("registered_mechanism_does_not_necessarily_flip_requested_choice")
        if slug == "b046":
            flags.append("original_bars_have_no_printed_exact_values_use_visual_estimates_only")
        if slug == "health004":
            flags.append("image_only_source_preserve_legacy_review_metadata")
        rows.append({
            "task_slug": slug, "domain": entry["domain"], "case_id": entry["case_id"],
            "pair_group_id": original.get("pair_group_id"),
            "original_mechanism": entry["original_mechanism"],
            "original_plot": entry["original_plot"],
            "audited_mechanism": mechanism,
            "core_task_family": family, "reasoning_family": entry["reasoning_family"],
            "lineage": {key: entry.get(key) for key in (
                "source_dataset", "source_group", "source_parent_code", "explicit_rewrite",
                "recorded_parent_case_id", "rewrite_source_record")},
            "pair_assets": pair_assets, "pair_semantic_invariants_equal": not changed,
            "pair_changed_semantic_fields": changed,
            "pair_comparison_status": "strict_fields_equal" if not changed else "original_pair_has_semantic_changes",
            "pair_workflow_equal": original.get("workflow_instruction") == clean.get("workflow_instruction"),
            "pair_public_option_labels_equal": [item["label"] for item in original["action_space"]]
                == [item["label"] for item in clean["action_space"]],
            "pair_expected_action_id_equal": original.get("expected_action_id") == clean.get("expected_action_id"),
            "scoring_policy": "use_each_condition_original_spec_without_overwriting_either_gold",
            "original_readiness": original.get("task_readiness"),
            "original_scoring_status": original.get("scoring_status"),
            "historical_review_records": entry.get("review_records", []),
            "audit_note": entry.get("audit_note", ""),
            "analyst_review": entry.get("analyst_review"),
            "exposure": {"status": "known_dev" if slug in known_dev else "unknown",
                         "sources": sources, "held_out_assignment": None},
            "evidence_limit_flags": flags,
            "native_persistence_eligibility": "not_established_by_inventory_requires_trajectory_audit",
        })
    for row in rows:
        relatives = parents[row["lineage"]["source_parent_code"]]
        row["lineage"]["same_parent_task_ids"] = relatives
        row["lineage"]["known_dev_relative_ids"] = sorted(set(relatives) & known_dev)
    summary = {
        "base_task_count": 140, "paired_task_instance_count": 280,
        "original_image_count_by_sha256": len(images),
        "original_label_count": len({row["original_mechanism"] for row in rows}),
        "audited_mechanism_labels_including_asset_exception": len({row["audited_mechanism"] for row in rows}),
        "core_task_family_count": len(families), "source_parent_code_count": len(parents),
        "explicit_rewrite_count": sum(bool(row["lineage"]["explicit_rewrite"]) for row in rows),
        "exposure_counts": dict(Counter(row["exposure"]["status"] for row in rows)),
        "domain_counts": dict(Counter(row["domain"] for row in rows)),
        "verified_original_and_clean_image_hash_count": 280,
        "paired_semantic_invariant_checks_passed": sum(row["pair_semantic_invariants_equal"] for row in rows),
        "pairs_with_changed_semantic_fields": sum(not row["pair_semantic_invariants_equal"] for row in rows),
        "pairs_with_changed_public_option_labels": sum(not row["pair_public_option_labels_equal"] for row in rows),
        "pairs_with_changed_expected_action_id": sum(not row["pair_expected_action_id_equal"] for row in rows),
    }
    manifest = {
        "schema_version": "1.0", "prepared_date": "2026-09-23",
        "status": "prepared_notrun", "role": "offline_evaluator_metadata_never_agent_input",
        "originals_modified": False, "gold_modified": False, "api_calls_by_preparation": 0,
        "source_snapshot": str(INVENTORY), "provenance": provenance,
        "summary": summary, "historical_exposure_status": exposure_status,
        "historical_known_dev_ids": sorted(old_ids), "fixed_demo_task_ids": list(DEMO_IDS),
        "pair_semantic_invariant_fields": list(PAIR_INVARIANTS),
        "pair_differences": {row["task_slug"]: row["pair_changed_semantic_fields"]
                             for row in rows if row["pair_changed_semantic_fields"]},
        "groups": {
            "core_task_family": dict(sorted(families.items())),
            "source_parent_code": dict(sorted(parents.items())),
            "identical_original_images": {key: value for key, value in images.items() if len(value) > 1},
        },
        "split_policy": {
            "status": "recommended_not_assigned",
            "known_dev_eligible_for_unseen_test": False,
            "unknown_means_unseen": False,
            "minimum_grouping": "Connected components of same parent and identical image; keep each pair together.",
            "strict_generalization_track": "Hold out complete core task families; report separately from within-family results.",
            "exposure_incomplete": True,
            "no_random_instance_split": True,
        },
        "tasks": rows,
    }
    config = make_config(summary, old_ids)
    report = make_report(summary, old_ids)
    return dict(zip(OWNED_OUTPUTS, (json_text(manifest), json_text(config), report)))


def make_config(summary, old_ids):
    methods = [
        ("ordinary", None, None, "Unmodified ordinary actor baseline; report its lower cost separately."),
        ("C0S0", False, False, "Equal-budget ordinary full-chart recheck; ordinary unchanged execution history."),
        ("C1S0", True, False, "Competing explanations and shared verifier; no dedicated persistent rule store."),
        ("C0S1", False, True, "Equal-budget ordinary recheck feeds the same scoped rule-state interface."),
        ("C1S1", True, True, "Competing explanations with scoped, versioned persistent rule state."),
        ("C1_flat_memory", True, False, "Equal factual content and matched token allocation in ordinary text memory; no status/version/scope governance."),
    ]
    return {
        "schema_version": "1.0", "status": "prepared_notrun", "enabled": False,
        "implementation_status": "panel_orchestration_and_ablation_arms_not_implemented",
        "launch_entrypoint": None, "network_enabled": False, "api_enabled": False,
        "gpu_jobs_enabled": False, "full_panel_authorized": False,
        "wandb": False, "manifest": "../panel140_manifest.json",
        "proposed_runtime": {
            "model_requested": "gpt-5.6-sol",
            "endpoint": "https://aimemodeldev.myhexin.com/litellm/v1/chat/completions",
            "auth_env_var": "MODEL_API_KEY",
            "credentials_in_config": False,
            "optional_proxy": "http://127.0.0.1:7897",
            "proxy_policy": "Optional current local proxy; validate availability before any future run.",
            "temperature": 0,
            "max_tokens": 2200,
            "timeout_seconds": 120,
            "max_attempts_per_call": 3,
            "retry_policy": "At most 3 total attempts including the first; transient transport errors only, no answer-quality retry.",
            "max_actor_calls_per_trajectory": 7,
            "api_seed_parameter": "not_supported_do_not_send",
            "record_requested_and_returned_model_ids": True,
        },
        "replication_plan": {
            "status": "proposed_disabled",
            "initial_replicate_ids": ["replicate_01"],
            "replicate_id_is_api_seed": False,
            "temperature_zero_does_not_guarantee_identical_outputs": True,
            "optional_extension": {
                "enabled": False, "target_total_replicates": 3,
                "additional_replicate_ids": ["replicate_02", "replicate_03"],
                "all_six_methods_trajectories_at_three_replicates": 5040,
                "status": "separate_future_confirmation_required",
                "budget": "not_approved_or_inherited_from_initial_replicate",
                "auto_start": False,
            },
        },
        "proposed_global_budget": {
            "status": "budget_proposed_requires_confirmation",
            "scope": "all six methods, both image conditions, 140 tasks, replicate_01; 1680 planned trajectories",
            "max_request_attempts": 20000,
            "max_browser_operations": 20000,
            "count_failed_requests_and_retries": True,
            "count_replay_and_failed_browser_attempts": True,
            "on_exhaustion": "stop_dispatch_and_record_unfinished_trajectories_no_auto_extension",
            "enforcement_implementation_status": "not_implemented_panel_orchestrator_required",
            "guarantees_all_planned_trajectories_complete": False,
            "is_current_demo_budget": False,
            "grants_permission_to_launch": False,
            "currency_cost_ceiling": "not_quoted_gateway_pricing_not_validated",
        },
        "scope": {"base_task_count": 140, "chart_conditions": list(CONDITIONS),
                  "exclude_real_world40": True, "replace_tasks_after_results": False},
        "methods": [{"id": name, "competition": competition, "persistent_rule_state": state,
                     "description": description, "status": "planned_not_implemented", "enabled": False}
                    for name, competition, state, description in methods],
        "factorial_contrasts": ["C1S0 - C0S0", "C1S1 - C0S1", "C0S1 - C0S0",
                                 "C1S1 - C1S0", "C1S1 - C1_flat_memory"],
        "controls": {
            "same_frozen_model_across_modules_and_arms": True,
            "same_chart_and_full_visible_evidence_access": True,
            "same_visual_verifier_and_arithmetic_tool": True,
            "same_unmodified_execution_history_across_state_arms": True,
            "state_off_does_not_mean_erasing_history": True,
            "match_review_call_and_token_budget_across_factorial_arms": True,
            "memory_control_matches_facts_and_token_budget": True,
            "neutral_option_aliases_and_precommitted_permutation": True,
            "same_permutation_across_methods_within_condition": True,
            "same_pair_permutation_when_original_option_sets_match": True,
            "different_original_option_sets": "precommit each original condition separately; never rewrite options",
            "gold_feedback_allowed_online": False,
            "csv_source_and_full_specs_allowed_online": False,
            "pair_images_allowed_together_online": False,
        },
        "bounded_method_draft": {"K_additional_competing_chains": 2,
                                 "L_additional_verification_rounds": 1,
                                 "unresolved_outcome": "stop_decision_and_record_reason",
                                 "rule_statuses": ["pending", "active", "disputed", "revoked"],
                                 "rule_scope": "task/chart/encoding/series/metric/range",
                                 "task_to_task_rule_transfer": False},
        "execution_requirements_unresolved": {
            "proposed_parameters_and_global_budget_confirmation": "required_before_full_panel_not_requested_by_preparation",
            "panel_orchestration_and_ablation_implementation": "not_implemented",
            "model_call_schema_and_budget_matching_validation": "required_before_run",
            "native_followup_decision_eligibility_audit": "required_for_persistence_claims",
            "original_companion_and_submission_scoring_coverage": "required_before_full_panel",
        },
        "planned_size_per_model_per_replicate_id": {
            "factorial_four_arms_trajectories": 1120,
            "equal_information_memory_trajectories": 280,
            "ordinary_baseline_trajectories": 280,
            "all_six_methods_trajectories": 1680,
            "note": "Planning arithmetic only; no 140-panel trajectory has been launched by this preparation.",
        },
        "reporting": {
            "native_outcomes": ["original_primary_action", "original_companion_fields", "actual_submission",
                                "original_terminal_score", "unresolved", "runtime_failure"],
            "paired_changes": ["wrong_to_correct", "correct_to_wrong", "correct_to_correct", "wrong_to_wrong"],
            "aggregations": ["task_instance", "core_task_family", "source_parent_group", "exposure_status"],
            "costs": ["all_api_attempts", "input_output_tokens", "elapsed_time", "browser_operations"],
            "persistence": "Only naturally eligible later chart-dependent judgments; no eligible denominator means N/A.",
            "derived_probes": "Separate optional protocol, never merged with native140 scores.",
            "clean_vs_official": "Stratify strict-field-equal versus changed-semantics pairs; latter are not chart-only causal contrasts.",
            "scoring": "Preserve and apply each condition original gold/options/companions/completion requirements.",
        },
        "exposure": {"known_dev_ids": sorted(set(old_ids) | set(DEMO_IDS)),
                     "other_task_status": "unknown", "split_assignment": "not_assigned"},
        "this_turn_demo_scope": {"task_ids": list(DEMO_IDS), "chart_conditions": list(CONDITIONS),
                                 "methods": ["ordinary", "full"], "planned_trajectories": 12,
                                 "configuration": "demo.json",
                                 "results_source": "separate_demo_artifacts_only_not_this_config"},
    }


def make_report(summary, old_ids):
    return f"""# 140 对任务适配与离线实验配置（2026-09-23）

状态：**prepared_notrun**。本文件、`panel140_manifest.json` 与 `configs/panel140_draft.json` 是离线准备结果；未启动 140 面板，未调用 API，未安装依赖、改图、改任务、改 gold 或改历史审核。实际三例演示由独立 `demo.json` 管理，其结果不能从本清单推断。

## 数据和可核验清单

源快照：`{INVENTORY}`。清单保存原 release 路径、本地快照路径、逐图 SHA256、原 JSONL 路径/行号/记录哈希，并引用审计目录与历史开发证据的文件哈希。原始字段与审计字段并存，未重写正式标签。

- {summary['base_task_count']} 个基础任务，official140 / clean140 共 {summary['paired_task_instance_count']} 个条件实例；不含真实网页 40 题。
- 逐一核验 {summary['verified_original_and_clean_image_hash_count']} 张图的现存字节哈希与既有目录一致。{summary['paired_semantic_invariant_checks_passed']} 对所查任务/行动/评分字段完全一致，另 {summary['pairs_with_changed_semantic_fields']} 对存在字段差异，逐项列入 `pair_differences`。
- {summary['pairs_with_changed_public_option_labels']} 对的公开选项文本不同，其中 {summary['pairs_with_changed_expected_action_id']} 对的原期望 action ID 也不同；不能把“存在字段变化”全部等同于“gold 被翻转”。
- {summary['original_image_count_by_sha256']} 份不同 official 图片、{summary['original_label_count']} 个原机制标签、{summary['core_task_family_count']} 个核心题型、{summary['source_parent_code_count']} 个父图代码；{summary['explicit_rewrite_count']} 条显式改写。父图数不等于独立生成器或独立研究问题数。
- 原审计将实物划为 14 个工作机制子类，另列 pub019 资产例外；清单保存的标签数量包括此例外。

原审核状态和已保存选入记录同时保留。本次元数据校验不构成新的人工审核。pub019 不删除，不伪装成有效的反向色标对照；pub005 粗分箱、截取时间窗、子群推广与视觉信号冲突分别保留证据限制。

**配对不总是只换图片。** 例如 b017 的 official 任务要求根据精选子群判断是否应请求完整数据；clean 发布任务改为根据全店图选择批准或拒绝，选项由三项改为两项，原 gold 也随之改变。这是原发布记录的差异，本轮没有合并或改正它。每个条件使用各自原 spec 评分；140 对整体不能声称纯图表变化的因果对照。比较同一条件下不同防御组仍可进行；跨 official/clean 的比较须按字段一致与存在差异分层，字段一致本身也不能保证所有视觉证据仅有单一变化。

## 开发接触与划分

历史八题证据来自已存在的 `ALL_CASES.json` 实际尝试记录及其协议，任务为：{', '.join(sorted(old_ids))}。本次预先固定三题为 pub013、health004、b046，均为开发演示。两者并集 {summary['exposure_counts'].get('known_dev', 0)} 题标为 `known_dev`；其余 {summary['exposure_counts'].get('unknown', 0)} 题标为 `unknown`，不称“未见测试”。父图关联到已知开发题的风险另记，不据此声称其他任务已运行或完全未接触。

清单没有分配 train/dev/test。后续最小约束是：配对条件同组、同父图及相同图片形成的连通组不跨划分；pub011/pub023 必须同组。若声称新题型泛化，应另设整组核心题型留出的轨道，并与同题型新实例成绩分别报告。先复核完整接触历史，再冻结划分；不能按本次表现移入/移出题目。

## 方法接入与在线信息边界

接入点为观察入口、图表相关动作执行前、后续推理读取入口。完整链条是当前 O∧B⇒C 的显式记录、至多 K 条实质不同竞争解释、整图核验 O/B/推导、带 scope 和版本的规则状态更新、行动重新推导。当前动作正确时允许 KEEP；证据不足允许 UNRESOLVED。规则撤销不自动证明动作错误，撤销记录也不能作为当前事实。

运行模型只能接收公开任务、实际观察到的完整原图、公开选项与允许的历史。中性选项别名按预先固定顺序映射回原 action ID；同一条件的实验组共享顺序，配对原选项不同则分别预定，不能擅自对齐或补删选项。原 `correct_` / `misleading_` ID、评分角色、完整 spec、CSV、HTML、审计推断及配对图片均不进入在线提示。本清单本身也不能作为 agent 输入。

pub013 的图例映射、health004 的纵轴刻度、b046 的均值线分别形成三种机制。b046 原图无柱值标签，精确原始柱值和真实均值仅可用于离线评分，在线应估读并记录不确定性。不得在提示里提供题目专属正确规则或强迫基线先犯错。

## 已准备、尚未实现的全量比较

| 配置 | 竞争解释 | 专门规则状态 | 用途 |
|---|---|---|---|
| ordinary | 无 | 无 | 普通执行基线，单独报告较低调用成本 |
| C0S0 | 等预算普通复核 | 无 | 因子对照基础 |
| C1S0 | 有 | 无 | 检查竞争解释贡献 |
| C0S1 | 等预算普通复核 | 有 | 检查状态接口贡献 |
| C1S1 | 有 | 有 | 完整组合 |
| C1_flat_memory | 有 | 等信息普通文本记忆 | 区分规则治理与重复提供相同信息 |

以上六组均 `enabled: false`、`planned_not_implemented`；没有面板启动入口。配置保留相同图像、冻结模型、视觉核验与算术接口、原执行历史及等预算要求。关闭状态不能通过删除历史制造劣势。消融逻辑、等信息匹配和全量调度仍须实现和验证，具体参数已经给出草案，未授权启动。

| 后续全量运行的参数草案 | 值 |
|---|---|
| 请求模型 | `gpt-5.6-sol`，保存请求及实际返回模型标识 |
| 接口 | `https://aimemodeldev.myhexin.com/litellm/v1/chat/completions` |
| 鉴权 | 只引用环境变量 `MODEL_API_KEY`；配置不含密钥 |
| 可选当前代理 | `http://127.0.0.1:7897`，后续运行前检查可用性 |
| 温度／单次最大输出 | `temperature=0`／`max_tokens=2200` |
| 超时／传输尝试 | 120 秒／每次调用最多 3 次总尝试（含首次），仅重试暂时传输故障 |
| 每轨迹 actor 调用上限 | 7 次；不因答案不理想重试 |
| 竞争解释／追加核验 | K=2 条额外候选／L=1 次额外核验 |
| 首轮重复标识 | `replicate_01`，不是 API seed；接口未支持 seed，不发送该参数 |
| 首轮六组共同硬上限草案 | 20,000 次请求尝试、20,000 次浏览器操作 |

全局上限的状态为 `budget_proposed_requires_confirmation`，只用于后续 140 面板预算讨论，不是当前演示预算，也不授予运行许可。所有失败和重试计入请求尝试，回放及失败操作计入浏览器操作；达到任一上限即停发，保留未完成项，不自动扩额。调度器尚未实现这些限制，且上限不保证 1,680 条轨迹全部完成。网关单价未核验，因此没有虚构货币费用上限。

按一个模型和一个 `replicate_id` 计算：四组因子对照 1,120 条、等信息记忆 280 条、普通基线 280 条，共 1,680 条计划轨迹；这是规划算术，不是本轮执行量。温度为零不保证确定性，`replicate_id` 只标识独立重复记录。后续可另行确认扩至总共 3 次重复（新增 `replicate_02`、`replicate_03`，共 5,040 条），其预算不继承本次草案，不自动启动。本轮独立演示计划仅 3 题 × 2 图条件 × ordinary/full = 12 条，不能据此声称已做四组消融；实际 `demo.json` 未由本准备脚本修改。

## 原生工作流与持久性结论

原生任务通常围绕一个主要图表选择完成导航、填写、提交。模型调用多次、跨页面或再按一次提交，均不自动构成第二次图表语义判断。清单因此把所有任务的持久性资格标为“需要实际轨迹审计”，不凭 spec 编造跨步骤回退率。

可以展示规则写入、按上下文读取、后续动作引用版本的接口证据。要声称防止回退，须在后续真实图表判断的机会中比较状态开/关；没有符合条件的分母时报告 N/A。人为新增问题、改变范围、遮挡图或插入旧规则挑战须单列派生诊断，不更改原图/gold，不计为原生 140 结果。

正式结果同时报告原行动正确性、必要伴随字段、真实提交、未解决和运行故障；分开统计纠错与过度纠正，记录全部尝试、token、耗时和动作成本。按实例、核心题型、父图组和接触状态分别汇总，不能把 140 当作 140 个独立题型，也不能以三题结果计算总体结论。

## 复核

使用 `D:\\anaconda\\python.exe prepare_panel.py --check` 验证清单/配置与当前源文件一致；无参数只重新生成本脚本拥有的三个准备工件。脚本无网络、API、GPU 或浏览器入口。
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate existing outputs without writing")
    args = parser.parse_args()
    artifacts = compile_artifacts()
    for name, content in artifacts.items():
        path = HERE / name
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise SystemExit("Prepared artifact missing/stale: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
    print(json_text({"status": "checked" if args.check else "prepared_notrun",
                     "base_tasks": 140, "images_verified": 280, "api_calls": 0,
                     "outputs": list(artifacts)}))


if __name__ == "__main__":
    main()
