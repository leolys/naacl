#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks/benchmark_public_affairs_tasks.jsonl"
DEFAULT_ANNOTATIONS = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks/review_annotations.json"
DEFAULT_APPROVED = REPO_ROOT / "web_agent_benchmark/public_affairs_tasks/approved_for_shell_tasks.jsonl"

STATUSES = {"unreviewed", "approved_for_shell", "needs_rewrite", "reject", "needs_gt_confirmation"}
ISSUES = {
    "correct_action_wrong",
    "misleading_action_wrong",
    "workflow_leaks_hint",
    "action_space_not_parallel",
    "dual_axis_task_unclear",
    "gt_uncertain",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_annotations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"updated_at": None, "annotations": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("annotations", {})
    return payload


def save_annotations(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_preview(path_value: str | None, limit: int = 60) -> dict[str, Any]:
    if not path_value or not Path(path_value).exists():
        return {"no_csv": True, "message": "No CSV available for this task."}
    with Path(path_value).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append({str(k): str(v) for k, v in row.items() if k is not None})
        return {"headers": list(reader.fieldnames or []), "rows": rows}


def make_app(tasks_path: Path, annotations_path: Path, approved_path: Path) -> Flask:
    app = Flask(__name__)
    tasks = read_jsonl(tasks_path)
    by_id = {task["task_id"]: task for task in tasks}

    @app.get("/")
    def index() -> Response:
        return Response(INDEX_HTML, mimetype="text/html")

    @app.get("/health")
    def health() -> Response:
        ann = load_annotations(annotations_path)["annotations"]
        return jsonify({
            "ok": True,
            "tasks": len(tasks),
            "formal_scored": sum(t.get("task_readiness") == "formal_scored_task" for t in tasks),
            "image_only_draft": sum(t.get("task_readiness") == "image_only_draft" for t in tasks),
            "status_counts": {s: sum(1 for t in tasks if ann.get(t["task_id"], {}).get("status", "unreviewed") == s) for s in STATUSES},
        })

    @app.get("/api/tasks")
    def api_tasks() -> Response:
        ann = load_annotations(annotations_path)["annotations"]
        compact = []
        for idx, task in enumerate(tasks):
            a = ann.get(task["task_id"], {})
            compact.append({
                "index": idx,
                "task_id": task["task_id"],
                "case_id": task["case_id"],
                "source_dataset": task.get("source_dataset"),
                "task_readiness": task.get("task_readiness"),
                "scoring_status": task.get("scoring_status"),
                "misleader_type": task.get("misleader_type"),
                "plot_type": task.get("plot_type"),
                "status": a.get("status", "unreviewed"),
                "issues": a.get("issues", []),
            })
        return jsonify({"tasks": compact})

    @app.get("/api/task/<int:index>")
    def api_task(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        ann = load_annotations(annotations_path)["annotations"]
        task = dict(tasks[index])
        task["index"] = index
        task["image_url"] = f"/image/{index}"
        task["csv_preview_url"] = f"/api/task/{index}/csv"
        task["annotation"] = ann.get(task["task_id"], {})
        return jsonify(task)

    @app.get("/api/task/<int:index>/csv")
    def api_task_csv(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        task = tasks[index]
        if not task.get("chart_asset", {}).get("has_csv"):
            return jsonify({
                "no_csv": True,
                "message": "Image-only draft. Review OCR/classification instead of CSV.",
                "image_only_review_context": task.get("image_only_review_context", {}),
            })
        return jsonify(csv_preview(task.get("chart_asset", {}).get("csv_path")))

    @app.get("/image/<int:index>")
    def image(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        path = Path(tasks[index]["chart_asset"]["figure_path"])
        if not path.exists():
            return jsonify({"error": f"missing image {path}"}), 404
        return send_file(path)

    @app.post("/api/annotation")
    def api_annotation() -> Response:
        payload = request.get_json(force=True)
        task_id = payload.get("task_id")
        if task_id not in by_id:
            return jsonify({"error": "unknown task_id"}), 404
        status = payload.get("status", "unreviewed")
        if status not in STATUSES:
            return jsonify({"error": "invalid status"}), 400
        issues = payload.get("issues", [])
        if not isinstance(issues, list):
            return jsonify({"error": "invalid issues"}), 400
        filtered_issues = [issue for issue in issues if issue in ISSUES]
        ignored_issues = [issue for issue in issues if issue not in ISSUES]
        obj = load_annotations(annotations_path)
        obj["annotations"][task_id] = {
            "task_id": task_id,
            "case_id": by_id[task_id]["case_id"],
            "status": status,
            "issues": filtered_issues,
            "notes": payload.get("notes", ""),
            "updated_at": utc_now(),
        }
        obj["updated_at"] = utc_now()
        save_annotations(annotations_path, obj)
        return jsonify({
            "ok": True,
            "annotation": obj["annotations"][task_id],
            "ignored_issues": ignored_issues,
        })

    @app.post("/api/export_approved")
    def export_approved() -> Response:
        ann = load_annotations(annotations_path)["annotations"]
        approved = [task for task in tasks if ann.get(task["task_id"], {}).get("status") == "approved_for_shell"]
        write_jsonl(approved_path, approved)
        return jsonify({"ok": True, "approved": len(approved), "path": str(approved_path)})

    return app


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Public Affairs Task Review</title>
  <style>
    body{margin:0;font-family:Inter,system-ui,sans-serif;background:#f6f6f3;color:#202124}
    .app{display:grid;grid-template-columns:390px 1fr;height:100vh}
    aside{background:#fff;border-right:1px solid #d9dedb;overflow:auto}
    header{padding:14px 16px;border-bottom:1px solid #d9dedb}
    h1{font-size:18px;margin:0}.sub{font-size:12px;color:#68736d;margin-top:5px}
    .filters{padding:12px;display:grid;gap:8px;border-bottom:1px solid #d9dedb}
    input,select,textarea{font:inherit;border:1px solid #d9dedb;border-radius:6px;padding:8px;background:#fff}
    .item{padding:10px 12px;border-bottom:1px solid #edf0ed;cursor:pointer}
    .item.active,.item:hover{background:#e8f1ee}.case{font-size:11px;color:#68736d;overflow-wrap:anywhere}
    .tag{display:inline-block;border:1px solid #d9dedb;border-radius:999px;padding:2px 6px;font-size:11px;margin:4px 4px 0 0}
    .draft{color:#8a6100;border-color:#d4b36d}.ok{color:#176b3a;border-color:#8abb9d}.bad{color:#9d352d;border-color:#d99a94}
    main{overflow:auto;padding:16px}.grid{display:grid;grid-template-columns:minmax(380px,.9fr) minmax(520px,1.1fr);gap:14px}
    .panel{background:#fff;border:1px solid #d9dedb;border-radius:8px;padding:14px;margin-bottom:14px}
    h2{font-size:15px;margin:0 0 10px}img{width:100%;max-height:560px;object-fit:contain;border:1px solid #d9dedb;border-radius:6px;background:#fff}
    pre{white-space:pre-wrap;background:#f7f8f6;border:1px solid #d9dedb;border-radius:6px;padding:10px;font-size:12px;overflow:auto}
    table{width:100%;border-collapse:collapse;font-size:12px}td,th{border-bottom:1px solid #d9dedb;padding:6px;text-align:left;vertical-align:top}
    button{border:1px solid #d9dedb;background:#fff;border-radius:6px;padding:8px 10px;cursor:pointer}.primary{background:#176b5f;color:white;border-color:#176b5f}
    .checks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;font-size:12px}
  </style>
</head>
<body>
<div class="app">
<aside>
<header><h1>Public Affairs Task Review</h1><div class="sub" id="counts">Loading...</div></header>
<div class="filters">
<input id="q" placeholder="Search">
<select id="status"><option value="">All statuses</option><option>unreviewed</option><option>approved_for_shell</option><option>needs_rewrite</option><option>reject</option><option>needs_gt_confirmation</option></select>
<select id="readiness"><option value="">All readiness</option><option>formal_scored_task</option><option>image_only_draft</option></select>
<button id="exportBtn">Export approved</button><div class="sub" id="exportMsg"></div>
</div>
<div id="list"></div>
</aside>
<main><div id="empty">Select a task.</div><div id="detail" style="display:none">
<div class="panel"><h1 id="heading"></h1><div class="sub" id="sub"></div></div>
<div class="grid">
<div><div class="panel"><h2>Chart</h2><img id="chart"></div><div class="panel"><h2>CSV / OCR</h2><div id="csv"></div></div></div>
<div>
<div class="panel"><h2>Workflow</h2><pre id="workflow"></pre></div>
<div class="panel"><h2>Actions</h2><pre id="actions"></pre></div>
<div class="panel"><h2>Ground Truth / Context</h2><pre id="gt"></pre></div>
<div class="panel"><h2>Annotation</h2>
<select id="annStatus"><option>unreviewed</option><option>approved_for_shell</option><option>needs_rewrite</option><option>reject</option><option>needs_gt_confirmation</option></select>
<div class="checks" id="issues"></div><textarea id="notes" style="width:100%;min-height:90px;margin-top:8px"></textarea>
<button class="primary" id="saveBtn">Save</button><span class="sub" id="saveMsg"></span></div>
</div></div></div></main></div>
<script>
const issueTypes=["correct_action_wrong","misleading_action_wrong","workflow_leaks_hint","action_space_not_parallel","dual_axis_task_unclear","gt_uncertain"];
let tasks=[],current=null;
const $=id=>document.getElementById(id);
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function load(){const r=await fetch('/api/tasks');tasks=(await r.json()).tasks;renderList();$('counts').textContent=`${tasks.length} tasks`;}
function filtered(){const q=$('q').value.toLowerCase(),s=$('status').value,rd=$('readiness').value;return tasks.filter(t=>(!q||(`${t.task_id} ${t.case_id} ${t.misleader_type}`).toLowerCase().includes(q))&&(!s||t.status===s)&&(!rd||t.task_readiness===rd))}
function renderList(){const rows=filtered();$('list').innerHTML=rows.map(t=>`<div class="item ${current===t.index?'active':''}" onclick="openTask(${t.index})"><b>${esc(t.task_id)}</b><div class="case">${esc(t.case_id)}</div><span class="tag ${t.task_readiness==='image_only_draft'?'draft':''}">${esc(t.task_readiness)}</span><span class="tag">${esc(t.status)}</span><span class="tag">${esc(t.misleader_type)}</span></div>`).join('')}
function renderIssues(selected){$('issues').innerHTML=issueTypes.map(i=>`<label><input type="checkbox" value="${i}" ${selected.includes(i)?'checked':''}> ${i}</label>`).join('')}
async function openTask(i){current=i;const t=await (await fetch(`/api/task/${i}`)).json();$('empty').style.display='none';$('detail').style.display='block';$('heading').textContent=t.task_id;$('sub').textContent=t.case_id;$('chart').src=t.image_url;$('workflow').textContent=t.workflow_instruction;$('actions').textContent=JSON.stringify({primary_action:t.primary_action, companion_actions:t.companion_actions, action_space:t.action_space, completion_action:t.completion_action, fallback_scoring:t.fallback_scoring},null,2);$('gt').textContent=JSON.stringify({task_readiness:t.task_readiness, scoring_status:t.scoring_status, ground_truth:t.ground_truth, misleading_context:t.misleading_context, intermediate_decision:t.intermediate_decision, image_only_review_context:t.image_only_review_context},null,2);const c=await (await fetch(t.csv_preview_url)).json();if(c.no_csv){$('csv').innerHTML=`<pre>${esc(JSON.stringify(c,null,2))}</pre>`}else{$('csv').innerHTML='<table><thead><tr>'+c.headers.map(h=>`<th>${esc(h)}</th>`).join('')+'</tr></thead><tbody>'+c.rows.map(r=>'<tr>'+c.headers.map(h=>`<td>${esc(r[h])}</td>`).join('')+'</tr>').join('')+'</tbody></table>'}const a=t.annotation||{};$('annStatus').value=a.status||'unreviewed';$('notes').value=a.notes||'';renderIssues(a.issues||[]);renderList()}
async function save(){if(current===null)return;const t=await (await fetch(`/api/task/${current}`)).json();const issues=[...$('issues').querySelectorAll('input:checked')].map(x=>x.value);const res=await fetch('/api/annotation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:t.task_id,status:$('annStatus').value,issues,notes:$('notes').value})});const body=await res.json().catch(()=>({error:'non-json response'}));$('saveMsg').textContent=(res.ok&&body.ok)?(body.ignored_issues&&body.ignored_issues.length?`saved; ignored ${body.ignored_issues.join(', ')}`:'saved'):`failed: ${body.error||res.status}`;if(res.ok&&body.ok){await load();await openTask(current)}}
async function exp(){const r=await (await fetch('/api/export_approved',{method:'POST'})).json();$('exportMsg').textContent=`approved ${r.approved||0}`;}
['q','status','readiness'].forEach(id=>$(id).oninput=renderList);$('saveBtn').onclick=save;$('exportBtn').onclick=exp;load();
</script>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--approved-out", type=Path, default=DEFAULT_APPROVED)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8024)
    args = parser.parse_args()
    make_app(args.tasks, args.annotations, args.approved_out).run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
