"""Reuse the established offline viewer, populated ONLY with this new run."""
import argparse
import copy
import importlib.util
from pathlib import Path
import sys

import native_zh
from prepare import HERE, OLD, read, digest

sys.path.insert(0, str(OLD))
import panel_core as core
import run_panel as parent

_path = OLD / "terra140_native_zh_20260924/make_view.py"
_spec = importlib.util.spec_from_file_location("established_offline_view", _path)
view = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(view)
view.HERE = HERE
view.native_zh = native_zh


def compose(destination=None):
    translated, warnings, origins = native_zh.load_translations()
    comparison = read(HERE / "prepared/input_comparison.json")
    comparisons = {row["task_slug"]: row for row in comparison["tasks"]}
    state = core.read(HERE / "run/run_state.json", {})
    budget = core.read(HERE / "run/budget.json", {"request_attempts": 0})
    tasks = []
    for original in native_zh.records():
        task = copy.deepcopy(original)
        strings = native_zh.items(task)
        missing = [row["key"] for row in strings if native_zh.sid(row["text"]) not in translated]
        task["translation_items"] = strings
        task["translations"] = {"items": {row["key"]: translated[native_zh.sid(row["text"]) ]
            for row in strings if native_zh.sid(row["text"]) in translated}}
        task["status"]["translation"] = "not_run" if missing else "completed"
        record_path = HERE / "run/tasks" / task["task_slug"] / "record.json"
        task["native_translation_provenance"] = {"producer": "codex-native", "apiyi_translation_calls": 0,
            "source_record_sha256": digest(record_path) if record_path.is_file() else None,
            "missing_keys": missing, "complete_keys": len(task["translations"]["items"]),
            "source_files": sorted({origins[native_zh.sid(row["text"])] for row in strings
                                     if native_zh.sid(row["text"]) in origins}),
            "reuse_scope": "only exact-string Chinese translations; no previous model answers reused"}
        view.add_state_labels(task)
        case = comparisons[task["task_slug"]]
        task["review_flags"] = [
            "新协议：任务文字来自原网页实际公开内容；所有旧 OBC 模型解释均未复用。",
            "这是静态图表解释与核验，不是网页执行或最终提交；原网页已有的业务规则保持不变。",
            "三个页面的公开说明汇总为静态上下文；没有伪造 Agent 已浏览页面的动作历史。"]
        if case["advisory_flags"]:
            task["review_flags"].append("原网页仍有标注数值等证据指导（可能含 mislabeled_value）；本条不能归入严格无提示子集。未擅自改写原网页规则。")
        chains = (task.get("normalized") or {}).get("chains", [])
        if task["status"]["generation"] == "completed" and len(chains) < 2:
            task["review_flags"].append("只有一条解释链，未强行补写竞争解释。")
        elif len(chains) > 1 and len({row.get("option_label") for row in chains}) < 2:
            task["review_flags"].append("多条解释指向相同选项，不算不同行动的竞争解释。")
        if task.get("error"):
            task["review_flags"].append("保留的接口或核验失败不是已证明的视觉错误；请查看原始回答。")
        task["offline_metadata"] = {"input_protocol": "runtime_dom_public_v1",
            "changed_fields_from_previous": case["changed_fields"],
            "runtime_advisory_flags": case["advisory_flags"],
            "raw_spec_based_old_chains_reused": False}
        tasks.append(task)
    status = state.get("status", "prepared_not_run")
    if status == "completed_with_terminal_records":
        status = "completed" if all(all(t["status"][p] == "completed" for p in ("proposal", "generation", "verification")) for t in tasks) else "finished_with_terminal_failures"
    summary = {"total_tasks": len(tasks), "request_attempts": budget["request_attempts"],
        "generated": sum(t["status"]["generation"] == "completed" for t in tasks),
        "verified": sum(t["status"]["verification"] == "completed" for t in tasks),
        "translated": sum(t["status"]["translation"] == "completed" for t in tasks),
        "run_status": status, "blocked_reason": state.get("blocked_reason"),
        "apiyi_translation_calls": 0, "browser_operations": 0, "old_model_results_reused": 0,
        "scope": "new runtime-aligned static explanations; not defense efficacy or GUI completion"}
    result = {"schema_version": "obc140_review_v1", "generated_at": parent.now(),
        "title": "140 条原网页对齐任务 · 新版 OBC 中文阅览", "summary": summary,
        "field_labels": {**view.LABELS, "policy_tables": "原网页公开业务规则表",
                         "page_instructions": "原网页三个页面的公开说明", "readonly": "只读"},
        "tasks": tasks, "protocol": read(HERE / "config.json"), "translation_warnings": warnings}
    core.dump(destination or HERE / "review_data_zh.json", result)
    return result


view.compose = compose


def isolate_note_storage():
    """Never silently inherit human labels from the old spec-projected run."""
    template = (OLD / "viewer_template.html").read_text(encoding="utf-8")
    old = 'const storageKey = "obc140-notes-v1:" +'
    if template.count(old) != 1:
        raise ValueError("Inspect note namespace before rendering")
    template = template.replace(old, 'const storageKey = "obc140-runtime-dom-v1-20260924-notes:" +')
    path = HERE / "viewer_base_runtime.html"
    path.write_text(template, encoding="utf-8")
    view.render_viewer.TEMPLATE_PATH = path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser-check", action="store_true")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    isolate_note_storage()
    view.make(browser_check=args.browser_check, preview=args.preview)
