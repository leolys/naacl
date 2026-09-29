#!/usr/bin/env python3
"""Build a self-contained review bundle for the official 140-task benchmark."""

from __future__ import annotations

import csv
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_DIR = REPO_ROOT / "web_agent_benchmark" / "official_benchmark_v1"
OUT_DIR = REPO_ROOT / "review_all_for_clean_pair"

SCENARIO_TASK_FILES = [
    ("public39", "public39_tasks.jsonl"),
    ("business47", "business47_tasks.jsonl"),
    ("environment35", "environment35_tasks.jsonl"),
    ("health19", "health19_tasks.jsonl"),
]


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("._")
    return value[:120] or "item"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_csv_rows(path: Path | None) -> list[dict[str, str]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def copy_file(src: Path, dest: Path, copied: list[dict[str, str]], file_type: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    copied.append(
        {
            "type": file_type,
            "source_path": str(src),
            "local_path": str(dest.relative_to(OUT_DIR)),
        }
    )


def copy_tree(src: Path, dest: Path, copied: list[dict[str, str]], file_type: str) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    copied.append(
        {
            "type": file_type,
            "source_path": str(src),
            "local_path": str(dest.relative_to(OUT_DIR)),
        }
    )


def prepare_output() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in ["assets", "data"]:
        target = OUT_DIR / name
        if target.exists():
            shutil.rmtree(target)
    for name in ["index.html", "README.md"]:
        target = OUT_DIR / name
        if target.exists():
            target.unlink()


def collect_tasks(copied: list[dict[str, str]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()

    for scenario, filename in SCENARIO_TASK_FILES:
        source_file = OFFICIAL_DIR / filename
        for scenario_index, task in enumerate(read_jsonl(source_file), start=1):
            global_index = len(tasks) + 1
            slug = task.get("official_slug") or f"{scenario}_{scenario_index:03d}"
            task_id = task.get("task_id") or slug
            if task_id in seen_task_ids:
                raise ValueError(f"Duplicate task_id: {task_id}")
            seen_task_ids.add(task_id)

            task_dir_name = f"{global_index:03d}_{safe_name(slug)}"
            task_asset_dir = OUT_DIR / "assets" / task_dir_name
            chart_asset = task.get("chart_asset") or {}
            local_chart_asset: dict[str, str | None] = {
                "figure_path": None,
                "csv_path": None,
                "html_path": None,
            }
            original_chart_asset: dict[str, str | None] = {
                "figure_path": chart_asset.get("figure_path"),
                "csv_path": chart_asset.get("csv_path"),
                "html_path": chart_asset.get("html_path"),
            }

            figure_path = chart_asset.get("figure_path")
            if figure_path:
                src = Path(figure_path)
                ext = src.suffix or ".img"
                dest = task_asset_dir / f"figure{ext}"
                copy_file(src, dest, copied, "task_figure")
                local_chart_asset["figure_path"] = str(dest.relative_to(OUT_DIR))

            csv_path = chart_asset.get("csv_path")
            csv_rows: list[dict[str, str]] = []
            if csv_path:
                src = Path(csv_path)
                dest = task_asset_dir / "data.csv"
                copy_file(src, dest, copied, "task_csv")
                local_chart_asset["csv_path"] = str(dest.relative_to(OUT_DIR))
                csv_rows = read_csv_rows(src)

            html_path = chart_asset.get("html_path")
            if html_path:
                src = Path(html_path)
                dest = task_asset_dir / "source.html"
                copy_file(src, dest, copied, "task_source_html")
                local_chart_asset["html_path"] = str(dest.relative_to(OUT_DIR))

            task_copy = json.loads(json.dumps(task, ensure_ascii=False))
            task_copy["review_bundle"] = {
                "global_index": global_index,
                "asset_dir": str(task_asset_dir.relative_to(OUT_DIR)),
                "local_chart_asset": local_chart_asset,
                "original_chart_asset": original_chart_asset,
                "csv_rows": csv_rows,
            }
            tasks.append(task_copy)

    if len(tasks) != 140:
        raise ValueError(f"Expected 140 tasks, found {len(tasks)}")
    return tasks


def copy_reference_data(copied: list[dict[str, str]]) -> None:
    data_dir = OUT_DIR / "data"
    official_copy_dir = data_dir / "official_benchmark_v1"
    official_copy_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(OFFICIAL_DIR.iterdir()):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md"}:
            copy_file(path, official_copy_dir / path.name, copied, "official_top_level_data")

    eval_records = OFFICIAL_DIR / "evaluation_records"
    if eval_records.exists():
        copy_tree(eval_records, official_copy_dir / "evaluation_records", copied, "official_evaluation_records")

    evaluation_dir = REPO_ROOT / "web_agent_benchmark" / "evaluation"
    evaluation_refs_dir = data_dir / "evaluation_refs"
    evaluation_refs_dir.mkdir(parents=True, exist_ok=True)
    referenced_names = [
        "official_benchmark140_gpt54_runs.jsonl",
        "official_benchmark140_gpt54_summary.md",
        "official_benchmark140_gpt54_failures.jsonl",
        "public39_gpt54_runs.jsonl",
        "public39_gpt54_summary.md",
        "public39_gpt54_failures.jsonl",
        "business47_llm_full_runs.jsonl",
        "business47_llm_full_summary.md",
        "business47_llm_full_failures.jsonl",
        "environment35_gpt54_runs.jsonl",
        "environment35_gpt54_summary.md",
        "environment35_gpt54_failures.jsonl",
        "health19_gpt54_runs.jsonl",
        "health19_gpt54_summary.md",
        "health19_gpt54_failures.jsonl",
    ]
    for name in referenced_names:
        src = evaluation_dir / name
        if src.exists():
            copy_file(src, evaluation_refs_dir / name, copied, "evaluation_reference_data")


def write_tasks_data(tasks: list[dict[str, Any]], copied: list[dict[str, str]]) -> None:
    data_dir = OUT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "bundle_name": "review_all_for_clean_pair",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_official_dir": str(OFFICIAL_DIR),
        "task_count": len(tasks),
        "scenario_counts": {
            scenario: sum(1 for task in tasks if task.get("official_scenario") == scenario)
            for scenario, _ in SCENARIO_TASK_FILES
        },
        "asset_counts": {
            "figures": sum(1 for item in copied if item["type"] == "task_figure"),
            "csv": sum(1 for item in copied if item["type"] == "task_csv"),
            "source_html": sum(1 for item in copied if item["type"] == "task_source_html"),
        },
    }

    (data_dir / "all_tasks.json").write_text(
        json.dumps({"meta": meta, "tasks": tasks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (data_dir / "all_tasks.jsonl").open("w", encoding="utf-8") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    js = (
        "window.REVIEW_BUNDLE_META = "
        + json.dumps(meta, ensure_ascii=False, indent=2)
        + ";\nwindow.REVIEW_TASKS = "
        + json.dumps(tasks, ensure_ascii=False, indent=2)
        + ";\n"
    )
    (data_dir / "tasks.js").write_text(js, encoding="utf-8")

    (data_dir / "source_path_manifest.json").write_text(
        json.dumps({"meta": meta, "copied_files": copied}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_readme() -> None:
    readme = """# Review bundle for clean-pair work

This folder is self-contained. Open `index.html` in a browser to review the
140 official benchmark tasks one by one.

Contents:

- `index.html`: offline static reviewer.
- `assets/`: per-task chart figures, CSV files, and source HTML files.
- `data/tasks.js`: embedded task data used by the reviewer.
- `data/all_tasks.json` and `data/all_tasks.jsonl`: normalized task records.
- `data/official_benchmark_v1/`: copied benchmark manifest, registry, task JSONL files, docs, and evaluation records.
- `data/evaluation_refs/`: official run/summary/failure files referenced by the manifest.
- `data/source_path_manifest.json`: mapping from original source paths to local bundle paths.

The reviewer stores progress and notes in browser localStorage for the local
copy of this folder. The Export button in the page can emit a JSON progress
snapshot when needed.
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")


def write_index_html() -> None:
    html = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Official Benchmark 140 Review</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --surface: #ffffff;
      --surface-2: #eef1f5;
      --text: #17202a;
      --muted: #596675;
      --line: #d9dee7;
      --accent: #176b87;
      --accent-2: #2d8f6f;
      --warn: #a45f13;
      --bad: #a73535;
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); }
    button, input, select, textarea { font: inherit; }
    button {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 6px;
      padding: 8px 11px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); color: var(--accent); }
    button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
    button.done { background: #e8f5ef; border-color: #9cccb7; color: #146342; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .shell { display: grid; grid-template-columns: 330px minmax(0, 1fr); min-height: 100vh; }
    aside {
      border-right: 1px solid var(--line);
      background: var(--surface);
      height: 100vh;
      position: sticky;
      top: 0;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .side-head { padding: 18px 18px 12px; border-bottom: 1px solid var(--line); }
    h1 { font-size: 18px; margin: 0 0 6px; letter-spacing: 0; }
    .subtle { color: var(--muted); font-size: 13px; line-height: 1.45; }
    .filters { padding: 12px 18px; display: grid; gap: 8px; border-bottom: 1px solid var(--line); }
    .filters input, .filters select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--text);
    }
    .stats { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .list { overflow: auto; padding: 8px; }
    .task-row {
      width: 100%;
      text-align: left;
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr);
      gap: 8px;
      padding: 9px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      margin-bottom: 4px;
    }
    .task-row.active { background: #eaf3f4; border-color: #b8d5db; }
    .task-row.reviewed .row-title::after { content: " reviewed"; color: var(--accent-2); font-size: 11px; }
    .row-num { color: var(--muted); font-family: var(--mono); font-size: 12px; padding-top: 2px; }
    .row-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
    .row-meta { color: var(--muted); font-size: 12px; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    main { min-width: 0; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 5;
      background: rgba(246,247,249,0.95);
      border-bottom: 1px solid var(--line);
      padding: 12px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .nav-actions { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .content {
      padding: 22px;
      display: grid;
      grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
      gap: 18px;
      align-items: start;
    }
    section {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }
    h2 { font-size: 15px; margin: 0 0 12px; letter-spacing: 0; }
    h3 { font-size: 13px; margin: 18px 0 8px; color: var(--muted); letter-spacing: 0; text-transform: uppercase; }
    .chart-wrap { background: #fff; border: 1px solid var(--line); border-radius: 6px; overflow: auto; }
    .chart-wrap img { display: block; width: 100%; height: auto; max-height: 72vh; object-fit: contain; background: #fff; }
    .link-row { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0 0; font-size: 13px; }
    .kv { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 8px 12px; font-size: 13px; }
    .kv .key { color: var(--muted); }
    .text-block {
      border-left: 3px solid var(--line);
      padding-left: 10px;
      color: #26313c;
      line-height: 1.48;
      font-size: 14px;
      white-space: pre-wrap;
    }
    .answer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .answer { border: 1px solid var(--line); border-radius: 6px; padding: 10px; }
    .answer strong { display: block; margin-bottom: 4px; }
    .answer.correct { border-color: #9cccb7; background: #f0faf5; }
    .answer.trap { border-color: #e0ba83; background: #fff7e9; }
    .actions { display: grid; gap: 8px; }
    .action { border: 1px solid var(--line); border-radius: 6px; padding: 9px; font-size: 13px; }
    .action.correct { border-color: #9cccb7; }
    .action.misleading_trap { border-color: #e0ba83; }
    .table-wrap { max-height: 280px; overflow: auto; border: 1px solid var(--line); border-radius: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
    th { position: sticky; top: 0; background: var(--surface-2); z-index: 1; }
    code, pre { font-family: var(--mono); }
    details { border: 1px solid var(--line); border-radius: 6px; padding: 10px; background: #fbfcfd; }
    summary { cursor: pointer; color: var(--accent); }
    pre { overflow: auto; max-height: 360px; font-size: 12px; white-space: pre-wrap; }
    textarea { min-height: 90px; resize: vertical; }
    .empty { color: var(--muted); padding: 20px; text-align: center; }
    @media (max-width: 1100px) {
      .shell { grid-template-columns: 1fr; }
      aside { position: relative; height: auto; max-height: 48vh; }
      .content { grid-template-columns: 1fr; }
    }
    @media (max-width: 680px) {
      .topbar { align-items: stretch; flex-direction: column; }
      .content { padding: 14px; }
      .kv, .answer-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <div class="side-head">
        <h1>Official Benchmark 140 Review</h1>
        <div class="subtle">Offline reviewer for clean-pair preparation.</div>
        <div class="stats" id="stats"></div>
      </div>
      <div class="filters">
        <input id="search" type="search" placeholder="Search task, case, entity, trap">
        <select id="scenarioFilter">
          <option value="">All scenarios</option>
        </select>
        <select id="statusFilter">
          <option value="">All review states</option>
          <option value="open">Not reviewed</option>
          <option value="reviewed">Reviewed</option>
        </select>
      </div>
      <div class="list" id="taskList"></div>
    </aside>
    <main>
      <div class="topbar">
        <div>
          <div id="taskTitle" style="font-weight:700"></div>
          <div class="subtle" id="taskSubtitle"></div>
        </div>
        <div class="nav-actions">
          <button id="prevBtn">&lt; Prev</button>
          <button id="markBtn" class="primary">Mark reviewed</button>
          <button id="nextBtn">Next &gt;</button>
          <button id="exportBtn">Export notes</button>
        </div>
      </div>
      <div class="content" id="content"></div>
    </main>
  </div>
  <script src="data/tasks.js"></script>
  <script>
    const tasks = window.REVIEW_TASKS || [];
    const meta = window.REVIEW_BUNDLE_META || {};
    const progressKey = "review_all_for_clean_pair_progress_v1";
    let progress = loadProgress();
    let filtered = tasks.slice();
    let currentIndex = 0;

    const els = {
      stats: document.getElementById("stats"),
      search: document.getElementById("search"),
      scenarioFilter: document.getElementById("scenarioFilter"),
      statusFilter: document.getElementById("statusFilter"),
      taskList: document.getElementById("taskList"),
      taskTitle: document.getElementById("taskTitle"),
      taskSubtitle: document.getElementById("taskSubtitle"),
      content: document.getElementById("content"),
      prevBtn: document.getElementById("prevBtn"),
      nextBtn: document.getElementById("nextBtn"),
      markBtn: document.getElementById("markBtn"),
      exportBtn: document.getElementById("exportBtn")
    };

    function loadProgress() {
      try { return JSON.parse(localStorage.getItem(progressKey) || "{}"); }
      catch { return {}; }
    }
    function saveProgress() {
      localStorage.setItem(progressKey, JSON.stringify(progress));
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[ch]));
    }
    function getTaskKey(task) {
      return task.task_id || task.official_slug;
    }
    function reviewed(task) {
      return !!progress[getTaskKey(task)]?.reviewed;
    }
    function noteFor(task) {
      return progress[getTaskKey(task)]?.note || "";
    }
    function setNote(task, note) {
      const key = getTaskKey(task);
      progress[key] = progress[key] || {};
      progress[key].note = note;
      progress[key].updated_at = new Date().toISOString();
      saveProgress();
    }
    function scenarioLabel(value) {
      return value || "unspecified";
    }
    function firstActionByRole(task, role) {
      return (task.action_space || []).find(item => item.role === role);
    }
    function searchableText(task) {
      return [
        task.official_slug, task.task_id, task.case_id, task.official_scenario,
        task.workflow_instruction, task.misleader_type, task.plot_type,
        task.ground_truth?.ground_truth_entity,
        task.intermediate_decision?.correct_value,
        task.intermediate_decision?.misleading_value,
        task.misleading_context?.expected_visual_trap
      ].filter(Boolean).join(" ").toLowerCase();
    }
    function initFilters() {
      const scenarios = [...new Set(tasks.map(task => task.official_scenario).filter(Boolean))];
      for (const scenario of scenarios) {
        const option = document.createElement("option");
        option.value = scenario;
        option.textContent = scenario;
        els.scenarioFilter.appendChild(option);
      }
    }
    function applyFilters() {
      const query = els.search.value.trim().toLowerCase();
      const scenario = els.scenarioFilter.value;
      const status = els.statusFilter.value;
      filtered = tasks.filter(task => {
        if (scenario && task.official_scenario !== scenario) return false;
        if (status === "reviewed" && !reviewed(task)) return false;
        if (status === "open" && reviewed(task)) return false;
        if (query && !searchableText(task).includes(query)) return false;
        return true;
      });
      if (filtered.length && !filtered.includes(tasks[currentIndex])) {
        currentIndex = tasks.indexOf(filtered[0]);
      }
      renderList();
      renderCurrent();
    }
    function renderStats() {
      const reviewedCount = tasks.filter(reviewed).length;
      const scenarioCounts = meta.scenario_counts || {};
      els.stats.innerHTML = [
        `<span class="pill">${tasks.length} tasks</span>`,
        `<span class="pill">${reviewedCount} reviewed</span>`,
        ...Object.entries(scenarioCounts).map(([name, count]) => `<span class="pill">${escapeHtml(name)} ${count}</span>`)
      ].join("");
    }
    function renderList() {
      if (!filtered.length) {
        els.taskList.innerHTML = `<div class="empty">No matching tasks</div>`;
        return;
      }
      els.taskList.innerHTML = filtered.map(task => {
        const active = tasks[currentIndex] === task ? " active" : "";
        const isReviewed = reviewed(task) ? " reviewed" : "";
        const idx = task.review_bundle?.global_index || "";
        const title = `${task.official_slug || ""} ${task.ground_truth?.ground_truth_entity || task.case_id || ""}`;
        const metaLine = `${scenarioLabel(task.official_scenario)} · ${task.plot_type || ""} · ${task.misleader_type || ""}`;
        return `<button class="task-row${active}${isReviewed}" data-task-key="${escapeHtml(getTaskKey(task))}">
          <span class="row-num">${String(idx).padStart(3, "0")}</span>
          <span>
            <span class="row-title">${escapeHtml(title)}</span>
            <span class="row-meta">${escapeHtml(metaLine)}</span>
          </span>
        </button>`;
      }).join("");
    }
    function linkOrMuted(path, label) {
      return path ? `<a href="${escapeHtml(path)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>` : `<span class="subtle">${escapeHtml(label)} unavailable</span>`;
    }
    function renderKv(rows) {
      return `<div class="kv">${rows.map(([key, value]) => `<div class="key">${escapeHtml(key)}</div><div>${value}</div>`).join("")}</div>`;
    }
    function renderActions(task) {
      return `<div class="actions">${(task.action_space || []).map(action => `
        <div class="action ${escapeHtml(action.role || "")}">
          <strong>${escapeHtml(action.role || "action")}</strong>: ${escapeHtml(action.label || action.action_id)}
          ${action.scoring_outcome ? `<div class="subtle">Outcome: ${escapeHtml(action.scoring_outcome)}</div>` : ""}
          ${action.rationale ? `<div class="subtle">${escapeHtml(action.rationale)}</div>` : ""}
        </div>`).join("") || `<div class="subtle">No actions listed.</div>`}</div>`;
    }
    function renderCsv(task) {
      const rows = task.review_bundle?.csv_rows || [];
      if (!rows.length) return `<div class="subtle">No CSV rows available for this task.</div>`;
      const headers = Object.keys(rows[0]);
      return `<div class="table-wrap"><table>
        <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(row => `<tr>${headers.map(h => `<td>${escapeHtml(row[h])}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>`;
    }
    function renderCurrent() {
      if (!filtered.length) {
        els.taskTitle.textContent = "No matching tasks";
        els.taskSubtitle.textContent = "Adjust the filters to continue reviewing.";
        els.content.innerHTML = `<section><div class="empty">No matching tasks</div></section>`;
        els.prevBtn.disabled = true;
        els.nextBtn.disabled = true;
        els.markBtn.disabled = true;
        renderStats();
        return;
      }
      els.markBtn.disabled = false;
      const task = tasks[currentIndex];
      if (!task) return;
      const filteredPosition = filtered.indexOf(task);
      const local = task.review_bundle?.local_chart_asset || {};
      const idx = task.review_bundle?.global_index || currentIndex + 1;
      const correctAction = firstActionByRole(task, "correct");
      const trapAction = firstActionByRole(task, "misleading_trap");
      els.taskTitle.textContent = `${String(idx).padStart(3, "0")} / ${tasks.length} · ${task.official_slug || task.task_id}`;
      els.taskSubtitle.textContent = `${scenarioLabel(task.official_scenario)} · ${task.plot_type || "unknown plot"} · ${task.case_id || ""}`;
      els.markBtn.textContent = reviewed(task) ? "Reviewed" : "Mark reviewed";
      els.markBtn.classList.toggle("done", reviewed(task));
      els.prevBtn.disabled = filteredPosition <= 0;
      els.nextBtn.disabled = filteredPosition >= filtered.length - 1;

      const infoRows = [
        ["Task id", `<code>${escapeHtml(task.task_id)}</code>`],
        ["Case id", `<code>${escapeHtml(task.case_id)}</code>`],
        ["Scenario", escapeHtml(task.official_scenario || task.scenario || "")],
        ["Readiness", escapeHtml(task.task_readiness || task.scoring_status || "not specified")],
        ["Misleader", escapeHtml(task.misleader_type || "")],
        ["Plot type", escapeHtml(task.plot_type || "")],
        ["Reasoning", escapeHtml(task.reasoning_operation || "")],
        ["Source", escapeHtml(task.source_dataset || "official task file")]
      ];

      els.content.innerHTML = `
        <section>
          <h2>Chart Asset</h2>
          <div class="chart-wrap">
            ${local.figure_path ? `<img src="${escapeHtml(local.figure_path)}" alt="Task chart">` : `<div class="empty">No figure</div>`}
          </div>
          <div class="link-row">
            ${linkOrMuted(local.figure_path, "Open figure")}
            ${linkOrMuted(local.csv_path, "Open CSV")}
            ${linkOrMuted(local.html_path, "Open source HTML")}
          </div>
          <h3>CSV Data</h3>
          ${renderCsv(task)}
          <h3>Review Notes</h3>
          <textarea id="noteBox" placeholder="Notes for clean-pair creation">${escapeHtml(noteFor(task))}</textarea>
        </section>
        <section>
          <h2>Task Summary</h2>
          ${renderKv(infoRows)}
          <h3>Workflow Instruction</h3>
          <div class="text-block">${escapeHtml(task.workflow_instruction || "")}</div>
          <h3>Decision Pair</h3>
          <div class="answer-grid">
            <div class="answer correct">
              <strong>Correct</strong>
              ${escapeHtml(task.intermediate_decision?.correct_value || task.ground_truth?.ground_truth_entity || "")}
              <div class="subtle">${escapeHtml(correctAction?.label || task.primary_action?.correct_action_label || "")}</div>
            </div>
            <div class="answer trap">
              <strong>Misleading trap</strong>
              ${escapeHtml(task.intermediate_decision?.misleading_value || task.misleading_context?.misleading_target || "")}
              <div class="subtle">${escapeHtml(trapAction?.label || task.misleading_context?.expected_visual_trap || "")}</div>
            </div>
          </div>
          <h3>Ground Truth</h3>
          <div class="text-block">${escapeHtml(task.ground_truth?.ground_truth_computation || "")}</div>
          <h3>Visual Trap</h3>
          <div class="text-block">${escapeHtml(task.misleading_context?.expected_visual_trap || task.misleading_context?.misleading_mechanism || "")}</div>
          <h3>Action Space</h3>
          ${renderActions(task)}
          <h3>Full Task JSON</h3>
          <details>
            <summary>Show raw normalized task record</summary>
            <pre>${escapeHtml(JSON.stringify(task, null, 2))}</pre>
          </details>
        </section>
      `;
      const noteBox = document.getElementById("noteBox");
      noteBox.addEventListener("input", () => setNote(task, noteBox.value));
      renderStats();
      renderList();
    }
    function move(delta) {
      if (!filtered.length) return;
      const task = tasks[currentIndex];
      const position = Math.max(0, filtered.indexOf(task));
      const nextPosition = Math.max(0, Math.min(filtered.length - 1, position + delta));
      currentIndex = tasks.indexOf(filtered[nextPosition]);
      renderCurrent();
    }
    function exportNotes() {
      const payload = {
        exported_at: new Date().toISOString(),
        bundle: meta,
        progress
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "review_progress.json";
      a.click();
      URL.revokeObjectURL(url);
    }

    initFilters();
    renderStats();
    applyFilters();
    els.search.addEventListener("input", applyFilters);
    els.scenarioFilter.addEventListener("change", applyFilters);
    els.statusFilter.addEventListener("change", applyFilters);
    els.taskList.addEventListener("click", event => {
      const row = event.target.closest(".task-row");
      if (!row) return;
      const key = row.dataset.taskKey;
      const task = tasks.find(item => getTaskKey(item) === key);
      if (task) {
        currentIndex = tasks.indexOf(task);
        renderCurrent();
      }
    });
    els.prevBtn.addEventListener("click", () => move(-1));
    els.nextBtn.addEventListener("click", () => move(1));
    els.markBtn.addEventListener("click", () => {
      const task = tasks[currentIndex];
      const key = getTaskKey(task);
      progress[key] = progress[key] || {};
      progress[key].reviewed = !progress[key].reviewed;
      progress[key].updated_at = new Date().toISOString();
      saveProgress();
      renderCurrent();
    });
    els.exportBtn.addEventListener("click", exportNotes);
    document.addEventListener("keydown", event => {
      if (event.target.matches("input, textarea, select")) return;
      if (event.key === "ArrowLeft") move(-1);
      if (event.key === "ArrowRight") move(1);
      if (event.key.toLowerCase() === "r") els.markBtn.click();
    });
  </script>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    copied: list[dict[str, str]] = []
    prepare_output()
    copy_reference_data(copied)
    tasks = collect_tasks(copied)
    write_tasks_data(tasks, copied)
    write_index_html()
    write_readme()

    missing = []
    for task in tasks:
        local = task["review_bundle"]["local_chart_asset"]
        if not local.get("figure_path"):
            missing.append((task.get("official_slug"), "figure"))
    if missing:
        raise ValueError(f"Missing required local figures: {missing[:5]}")

    print(f"Wrote {OUT_DIR}")
    print(f"Tasks: {len(tasks)}")
    print(f"Figures copied: {sum(1 for item in copied if item['type'] == 'task_figure')}")
    print(f"CSV files copied: {sum(1 for item in copied if item['type'] == 'task_csv')}")
    print(f"Source HTML files copied: {sum(1 for item in copied if item['type'] == 'task_source_html')}")


if __name__ == "__main__":
    main()
