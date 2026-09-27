"""Offline manifest builder. Reads metadata/public rules; never reads model outcomes."""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from research.decision_evidence_audit.core import public_task_projection, write_json
from research.decision_evidence_audit.runner import PAIR_INVARIANT_FIELDS, REPOSITORY_ROOT, RELEASE_ROOT
from .api_backend import ApiConfig
from .h_base import PROTOCOL_VERSION

SEED = 20260907
# Purposive, rule/coverage-based selection; the seed randomizes order, not eligibility.
# These decisions preceded every new backbone call. No performance files are read here.
SELECTED = ["b010", "b014", "b046", "env005", "env035", "health001", "health005", "pub013"]
NOTES = {
    "b010": dict(template="category_max_bar", overlap=["b002", "env008"],
        rule="最大份额品牌→选择该品牌，原指令已明确 true share 与 bar height 的区别。",
        visible_witness="Apple 30%、Others 25%、Huawei 23%；误导柱高则 Huawei 最高。",
        limits="标签与柱高冲突；保留原指令中的防误读提示，不是新增防御。", conflict=True),
    "b014": dict(template="product_numeric_threshold", overlap=["b012", "b013", "b015"],
        rule="Product C 低于 25,000→普通低需求复核；否则正常计划，不能把普通阈值扩写为紧急。",
        visible_witness="C 的柱顶约 24,000；误导轴从约 18,000 起，clean 从零起。",
        limits="与旧 pop-up 阈值工作流同模板，不是模板外泛化。", conflict=False),
    "b046": dict(template="four_week_mean_comparison", overlap=["env025", "pub011"],
        rule="Week 1 高于四周平均→above-average follow-up，否则 normal monitoring；manual audit 是独立动作。",
        visible_witness="四柱约 467、548、448、351，平均约 454；Week 1 高于实际平均但低于误导 Average 线。",
        limits="约数用于离线人工可见核对，不在线供给；均值判定工作流与旧三月平均任务相近。", conflict=True),
    "env005": dict(template="energy_mix_max_pie", overlap=["env003", "env004", "env006"],
        rule="最大能源消费来源→对应 priority source monitoring。",
        visible_witness="Nuclear 40%、Hydroelectric 25%、Renewables 20%、Fossil Fuels 15%；误导面积排序不同。",
        limits="相同能源混合模板，与旧能源饼图属于模板内扩展，不宣称其为新问题族。", conflict=True),
    "env035": dict(template="inverted_axis_peak_year", overlap=[],
        rule="最高每桶价格年份→该年 escalation review。",
        visible_witness="1976—1995 年；误导 y 轴向下增大；1980 约 38，在倒轴图中最低，clean 图中最高。",
        limits="原 image_only_draft 保留；只有主决策可见证据核对，不升格官方资格。", conflict=False),
    "health001": dict(template="inverted_axis_peak_year", overlap=[],
        rule="年度最高死亡负担→该年 peak-burden follow-up。",
        visible_witness="2006—2018 年，y 轴方向决定值的大小；2018 最末点与 2017 很接近。",
        limits="原 image_only_draft 保留；2017/2018 区别细小，应记录读取不确定性；可用动作是 2018/2010/方法复核。", conflict=False),
    "health005": dict(template="two_axis_order_time_trend", overlap=[],
        rule="实际日历顺序的检测量上升/下降→rising-volume capacity / declining-volume outreach。",
        visible_witness="横轴左 Nov 20、右 Jun 26；日历正序为右到左；6 月约 0.4M 到 11 月约 1.24M。倒 y 轴需另行读刻度。",
        limits="原 image_only_draft 保留；两臂横轴都逆时间排列，不能把屏幕左到右等同时间先后。clean 中间点重构不完全同形，只支持当前端到端趋势判定。", conflict=False),
    "pub013": dict(template="state_extreme_reversed_legend", overlap=["pub001", "pub002", "pub012"],
        rule="最高风险州→对应 priority follow-up。",
        visible_witness="误导图例浅色=高值、深红=低值，须关联 IL/KS/DE 州名与图例；clean 图例方向相反。",
        limits="原 clean 图内有 Clean choropleth 说明，不删除或伪造；这是可见制图条件线索。地图模板在旧面板出现过。", conflict=False),
}
NOT_SELECTED = {
    "pub021": "本轮离线看图发现两臂图内实体名称/标题不同（Service Design vs Design）；不改图，暂不纳入严格语义配对主面板。",
    "env029": "公开规则未量化波动稳定与小幅下降的分界；暂不纳入唯一行动判定组，不改原 gold。",
    "pub034": "原图缺少 y 轴刻度，目标年非直接标注；跨轴外推需额外假设，暂不纳入该 8 例主面板。",
    "b043": "Promotion follow-up 与四周均值关系未在公开规则中明确方向；改选原本明确 above-average 的 b046，不补规则。",
}


def load_pairs():
    return {arm: {r["task_slug"]: r for p in sorted((RELEASE_ROOT / "splits" / arm).glob("*_tasks.jsonl"))
                   for r in map(json.loads, p.read_text().splitlines())}
            for arm in ("official140", "clean140")}


def source_group(row):
    case = row["case_id"]
    # Dataset rewrite IDs explicitly preserve their source chart in segment 2.
    if case.startswith(("environment_rewrite/", "health_rewrite/")):
        return case.split("/")[1]
    return case.split("/")[-1]


def prior_exclusions(pairs):
    excluded = {}
    def add(slug, why):
        if slug in pairs["official140"]:
            excluded.setdefault(slug, []).append(why)
    for slug in ("pub010", "env008", "b035", "env001", "env025"):
        add(slug, "执行单明确排除")
    root = REPOSITORY_ROOT / "web_agent_benchmark/evaluation/gui_reflection_baseline"
    manifests = sorted((root / "runs").rglob("run_manifest.json"))
    names = {"slug", "task_slug", "slugs", "task_slugs", "case_slug", "case_slugs", "task_ids", "tasks"}
    def inspect(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in names:
                    for slug in re.findall(r"\b(?:pub|env|health|b)\d{3}\b", str(child)):
                        add(slug, str(path.relative_to(REPOSITORY_ROOT)))
                elif isinstance(child, (dict, list)):
                    inspect(child, path)
        elif isinstance(value, list):
            for child in value:
                inspect(child, path)
    for path in manifests:
        inspect(json.loads(path.read_text()), path)
    # Conservative exclusions: planned smoke tasks and prior offline eligibility
    # work are excluded even where a live run is not established.
    smoke = root / "task_sets/smoke17.jsonl"
    for row in map(json.loads, smoke.read_text().splitlines()):
        add(row["slug"], "旧 smoke17 计划集合；保守排除，不等同全部已真实运行")
    eligibility = REPOSITORY_ROOT / "research/decision_evidence_audit/TASK_ELIGIBILITY.csv"
    with eligibility.open() as f:
        for row in csv.DictReader(f):
            add(row["task_slug"], "旧离线任务资格分析；保守排除")
    recent = REPOSITORY_ROOT / "research/decision_evidence_audit/runs/web_qualification_20260907T0801Z/run_manifest.json"
    for slug in json.loads(recent.read_text())["candidates"]:
        add(slug, "20260907 网页资格诊断；0 模型调用，仍保守排除")
    old_sources = {source_group(pairs["official140"][slug]) for slug in excluded}
    for slug, row in pairs["official140"].items():
        if source_group(row) in old_sources and slug not in excluded:
            add(slug, "与已用/保守排除任务同原图来源；不得仅改实体、数字、标题冒充独立留出")
    return dict(sorted(excluded.items())), dict(gui_run_manifests=len(manifests),
        sources=[str(smoke.relative_to(REPOSITORY_ROOT)), str(eligibility.relative_to(REPOSITORY_ROOT)),
                 str(recent.relative_to(REPOSITORY_ROOT))],
        scope="本研究 GUI-Reflection/agentic recovery/decision evidence 记录；原论文全量模型评测不当作本轮方法调参使用。无缺失日志完备性保证。")


def build_manifest():
    pairs = load_pairs()
    excluded, audit = prior_exclusions(pairs)
    order = sorted(SELECTED)
    random.Random(SEED).shuffle(order)
    rows, schedule, positions = [], [], Counter()
    for i, slug in enumerate(order):
        if slug in excluded:
            raise ValueError(f"Preselected task has prior-use evidence: {slug}")
        a, b = pairs["official140"][slug], pairs["clean140"][slug]
        differences = [k for k in PAIR_INVARIANT_FIELDS if a.get(k) != b.get(k)]
        if differences:
            raise ValueError(f"Selected pair has non-chart changes: {slug}: {differences}")
        public = public_task_projection(a, task_alias=f"case{i + 1:02d}")
        correct_label = next(x["label"] for x in a["action_space"] if x["action_id"] == a["expected_action_id"])
        pos = public["option_labels"].index(correct_label) + 1
        positions[pos] += 1
        assets = {}
        for arm, raw in (("official140", a), ("clean140", b)):
            path = REPOSITORY_ROOT / raw["chart_asset"]["figure_path"]
            with Image.open(path) as im:
                assets[arm] = dict(path=str(path.relative_to(REPOSITORY_ROOT)), size=list(im.size), format=im.format)
        rows.append(dict(task_slug=slug, pair_group_id=a["pair_group_id"],
            task_alias=public["task_alias"], family=a["official_scenario"], source_case_id=a["case_id"],
            original_source_group=source_group(a), original_readiness=a.get("task_readiness", "legacy_unspecified"),
            original_scoring_status=a.get("scoring_status", "legacy_unspecified"),
            offline_mechanism=a["misleader_type"], plot_type=a["plot_type"], assets=assets,
            public_task=public, offline_expected_option_position=pos,
            invariant_fields_checked=list(PAIR_INVARIANT_FIELDS), non_chart_differences=differences,
            evidence_audit=NOTES[slug], qualification="prospective_primary_decision_only_with_recorded_caveats"))
        models = ["M_small", "M_strong"] if i % 2 == 0 else ["M_strong", "M_small"]
        arms = ["official140", "clean140"] if i % 2 == 0 else ["clean140", "official140"]
        for arm in arms:
            for model in models:
                strategies = ["B0", "B2", "B3"]
                rotate = len(schedule) % 3
                strategies = strategies[rotate:] + strategies[:rotate]
                schedule.append(dict(ordinal=len(schedule) + 1, task_slug=slug, task_alias=public["task_alias"],
                                     arm=arm, model=model, strategies=strategies, status="not_run"))
    return dict(protocol=PROTOCOL_VERSION, status="prepared_not_authorized_not_run", seed=SEED,
        sampling="目的性资格/覆盖预选；seed 仅随机化预选 8 个任务的运行顺序，非随机总体样本。",
        template_generalization="不声称模板外泛化。8 个原记录/来源组，多个工作流及生成模板与旧开发组重叠。",
        rows=rows, case_interleaved_order=schedule, exclusions=excluded, prior_use_audit=audit,
        considered_but_not_selected=NOT_SELECTED, base_tasks=8, natural_prefixes_planned=32,
        strategy_records_planned=96, models_started=0,
        offline_correct_option_position_distribution=dict(sorted(positions.items())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = build_manifest()
    write_json(args.output / "TASK_MANIFEST.json", manifest)
    config = dict(status="prepared_not_authorized", protocol=PROTOCOL_VERSION,
        M_small=dict(model="Qwen3-VL-8B-Instruct", authorized=False, server_url=None,
            weights="/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct",
            precision="bfloat16", max_output_tokens=1024, do_sample=False, temperature=0.0,
            top_p=1.0, seed=12345, max_pixels=1003520, native_multi_image=True,
            runtime_versions=dict(transformers="4.57.1", torch="2.8.0", qwen_vl_utils="0.0.14"),
            runtime_status="previously audited configuration; reverify running service after authorization",
            gpu_permission="new GPU0 shared-use permission required; no autostart"),
        M_strong=asdict(ApiConfig()),
        budgets=dict(approved=False, local_model_calls=400, api_model_calls=400,
                     browser_transitions=4000, concurrency=1, prefix_calls=12, prefix_transitions=20,
                     B2_check_calls=1, B3_check_calls=3, B3_crops=2, continuation_calls=4),
        api_missing=ApiConfig().missing(check_credential=False),
        credentials="MODEL_API_KEY only; not read from documentation or local key files; do not paste in chat")
    write_json(args.output / "MODEL_CONFIG.json", config)
    fields = ["ordinal", "task_slug", "arm", "model", "strategy", "prefix_status", "checkpoint_selection",
              "verifier_recommendation", "executor_selection", "actor_final_submission", "score", "model_calls", "browser_transitions"]
    with (args.output / "CASE_TABLE.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for unit in manifest["case_interleaved_order"]:
            for strategy in unit["strategies"]:
                writer.writerow({k: unit[k] for k in ("ordinal", "task_slug", "arm", "model")} |
                                dict(strategy=strategy, prefix_status="not_run_awaiting_authorization"))
    print(json.dumps(dict(output=str(args.output), selected=[r["task_slug"] for r in manifest["rows"]],
                         exclusions=len(manifest["exclusions"]), planned_prefixes=32, planned_records=96,
                         real_model_calls=0, browser_transitions=0), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
