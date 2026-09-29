#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = REPO_ROOT / "web_agent_benchmark" / "tasks" / "benchmark_tasks.jsonl"
DEFAULT_ANNOTATIONS = (
    REPO_ROOT / "web_agent_benchmark" / "tasks" / "task_action_space_review_annotations.json"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_annotations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"updated_at": None, "annotations": {}}
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj.setdefault("annotations", {})
    return obj


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def csv_preview(path: Path, limit: int = 60) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for idx, row in enumerate(reader):
            if idx >= limit:
                break
            rows.append({str(k): str(v) for k, v in row.items() if k is not None})
        return {"headers": list(reader.fieldnames or []), "rows": rows}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_app(tasks_path: Path, annotations_path: Path) -> Flask:
    app = Flask(__name__)
    tasks = load_jsonl(tasks_path)
    task_by_id = {task["task_id"]: task for task in tasks}

    @app.get("/")
    def index() -> Response:
        return Response(INDEX_HTML, mimetype="text/html")

    @app.get("/api/tasks")
    def api_tasks() -> Response:
        annotations = load_annotations(annotations_path)["annotations"]
        compact = []
        for idx, task in enumerate(tasks):
            ann = annotations.get(task["task_id"], {})
            compact.append(
                {
                    "index": idx,
                    "task_id": task["task_id"],
                    "case_id": task["case_id"],
                    "scenario": task.get("scenario", ""),
                    "misleader_type": task.get("misleader_type", ""),
                    "reasoning_operation": task.get("reasoning_operation", ""),
                    "expected_action_id": task.get("expected_action_id", ""),
                    "status": ann.get("status", "unreviewed"),
                    "issue_type": ann.get("issue_type", ""),
                }
            )
        return jsonify({"tasks": compact})

    @app.get("/api/task/<int:index>")
    def api_task(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        annotations = load_annotations(annotations_path)["annotations"]
        task = dict(tasks[index])
        task["index"] = index
        task["annotation"] = annotations.get(task["task_id"], {})
        task["image_url"] = f"/image/{index}?t={int(time.time())}"
        task["csv_preview_url"] = f"/api/task/{index}/csv"
        return jsonify(task)

    @app.get("/api/task/<int:index>/csv")
    def api_task_csv(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        return jsonify(csv_preview(Path(tasks[index]["chart_asset"]["csv_path"])))

    @app.get("/image/<int:index>")
    def image(index: int) -> Response:
        if index < 0 or index >= len(tasks):
            return jsonify({"error": "task index out of range"}), 404
        path = Path(tasks[index]["chart_asset"]["figure_path"])
        if not path.exists():
            return jsonify({"error": f"missing image: {path}"}), 404
        return send_file(path)

    @app.post("/api/annotation")
    def api_annotation() -> Response:
        payload = request.get_json(force=True)
        task_id = payload.get("task_id")
        if task_id not in task_by_id:
            return jsonify({"error": "unknown task_id"}), 404
        status = payload.get("status", "unreviewed")
        if status not in {"suitable", "needs_rewrite", "unsuitable", "unreviewed"}:
            return jsonify({"error": "invalid status"}), 400
        issue_type = payload.get("issue_type", "")
        allowed_issues = {
            "",
            "correct_action_wrong",
            "misleading_action_not_aligned",
            "companion_action_wrong",
            "workflow_leaks_answer",
            "action_space_incomplete",
            "scoring_unclear",
        }
        if issue_type not in allowed_issues:
            return jsonify({"error": "invalid issue_type"}), 400
        obj = load_annotations(annotations_path)
        obj["annotations"][task_id] = {
            "task_id": task_id,
            "case_id": task_by_id[task_id]["case_id"],
            "status": status,
            "issue_type": issue_type,
            "notes": payload.get("notes", ""),
            "updated_at": utc_now(),
        }
        obj["updated_at"] = utc_now()
        atomic_write_json(annotations_path, obj)
        return jsonify({"ok": True, "annotation": obj["annotations"][task_id]})

    return app


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task Action Space Review</title>
  <style>
    :root { --bg:#f6f6f3; --panel:#fff; --line:#d9dedb; --text:#202124; --muted:#626a73; --ok:#176b3a; --bad:#a33b2f; --warn:#8a6400; --accent:#176b5f; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--text); }
    .app { display:grid; grid-template-columns: 360px 1fr; height:100vh; }
    aside { border-right:1px solid var(--line); background:var(--panel); display:flex; flex-direction:column; min-width:0; }
    header { padding:14px 16px; border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:18px; }
    .sub { color:var(--muted); font-size:12px; margin-top:4px; }
    .filters { padding:12px; display:grid; gap:8px; border-bottom:1px solid var(--line); }
    input, select, textarea { width:100%; border:1px solid var(--line); border-radius:6px; padding:8px; font:inherit; background:#fff; }
    .list { overflow:auto; padding:8px; }
    .item { padding:9px; border:1px solid transparent; border-radius:6px; cursor:pointer; }
    .item:hover, .item.active { background:#edf3f0; border-color:#bdd7ce; }
    .case { font-size:11px; color:var(--muted); overflow-wrap:anywhere; }
    .pill { display:inline-block; padding:2px 6px; border:1px solid var(--line); border-radius:999px; font-size:11px; margin-top:4px; }
    .status-suitable { color:var(--ok); border-color:#acd5bd; }
    .status-unsuitable { color:var(--bad); border-color:#ddb6ae; }
    .status-needs_rewrite { color:var(--warn); border-color:#e0cd91; }
    main { overflow:auto; padding:18px; }
    .grid { display:grid; grid-template-columns:minmax(360px, 0.9fr) minmax(480px, 1.1fr); gap:14px; align-items:start; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
    h2 { margin:0 0 10px; font-size:15px; }
    img { width:100%; max-height:560px; object-fit:contain; background:#fff; border:1px solid var(--line); border-radius:6px; }
    dl { display:grid; grid-template-columns:150px 1fr; gap:6px 10px; font-size:13px; }
    dt { color:var(--muted); }
    dd { margin:0; overflow-wrap:anywhere; }
    pre { white-space:pre-wrap; overflow:auto; background:#f7f8f6; border:1px solid var(--line); border-radius:6px; padding:10px; font-size:12px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th, td { border-bottom:1px solid var(--line); text-align:left; padding:7px; vertical-align:top; }
    .role-correct { color:var(--ok); font-weight:700; }
    .role-misleading_trap { color:var(--bad); font-weight:700; }
    .role-neutral_or_irrelevant { color:var(--warn); font-weight:700; }
    .buttons { display:flex; gap:8px; flex-wrap:wrap; margin:10px 0; }
    button { border:1px solid var(--line); background:#fff; border-radius:6px; padding:8px 10px; cursor:pointer; }
    button.selected { outline:2px solid var(--accent); }
    button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  </style>
</head>
<body>
<div class="app">
  <aside>
    <header><h1>Task Action Space Review</h1><div class="sub" id="counts">Loading...</div></header>
    <section class="filters">
      <input id="query" placeholder="Search task, case, operation">
      <select id="statusFilter"><option value="">All statuses</option><option>unreviewed</option><option>suitable</option><option>needs_rewrite</option><option>unsuitable</option></select>
    </section>
    <section class="list" id="taskList"></section>
  </aside>
  <main>
    <div id="empty">Select a task.</div>
    <div id="detail" style="display:none">
      <header class="panel" style="margin-bottom:14px">
        <h1 id="heading"></h1><div class="sub" id="sub"></div>
      </header>
      <div class="grid">
        <section class="panel"><h2>Chart</h2><img id="chart"><h2>Metadata</h2><dl id="meta"></dl></section>
        <section class="panel"><h2>Workflow</h2><pre id="workflow"></pre><h2>Ground Truth</h2><pre id="gt"></pre><h2>Misleading Context</h2><pre id="mislead"></pre></section>
      </div>
      <div class="grid" style="margin-top:14px">
        <section class="panel"><h2>Action Chain</h2><h3>Intermediate Decision</h3><pre id="decision"></pre><h3>Primary Action</h3><pre id="primary"></pre><h3>Companion Actions</h3><table id="companions"></table><h3>Completion Action</h3><pre id="completion"></pre></section>
        <section class="panel"><h2>Action Space</h2><table id="actions"></table><h2>Fallback Scoring</h2><pre id="fallback"></pre></section>
      </div>
      <section class="panel" style="margin-top:14px">
        <h2>Review</h2>
        <div class="buttons" id="statusBtns">
          <button data-status="suitable">Suitable</button><button data-status="needs_rewrite">Needs rewrite</button><button data-status="unsuitable">Unsuitable</button><button data-status="unreviewed">Unreviewed</button>
        </div>
        <select id="issueType"><option value="">No issue type</option><option>correct_action_wrong</option><option>misleading_action_not_aligned</option><option>companion_action_wrong</option><option>workflow_leaks_answer</option><option>action_space_incomplete</option><option>scoring_unclear</option></select>
        <textarea id="notes" rows="3" placeholder="Notes"></textarea>
        <div class="buttons"><button class="primary" id="saveBtn">Save Review</button></div>
      </section>
    </div>
  </main>
</div>
<script>
let tasks=[], current=null, currentTask=null;
async function loadTasks(){ const r=await fetch('/api/tasks'); tasks=(await r.json()).tasks; renderList(); }
function renderList(){
  const q=document.getElementById('query').value.toLowerCase();
  const sf=document.getElementById('statusFilter').value;
  const list=document.getElementById('taskList'); list.innerHTML='';
  const shown=tasks.filter(t=>(!sf||t.status===sf)&&JSON.stringify(t).toLowerCase().includes(q));
  document.getElementById('counts').textContent=`${shown.length}/${tasks.length} tasks`;
  shown.forEach(t=>{ const d=document.createElement('div'); d.className='item'+(current===t.index?' active':''); d.onclick=()=>openTask(t.index); d.innerHTML=`<div><b>#${t.index+1}</b> ${t.reasoning_operation}</div><div class="case">${t.case_id}</div><span class="pill status-${t.status}">${t.status}</span>`; list.appendChild(d); });
}
function table(el, headers, rows){
  el.innerHTML='<thead><tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(c=>`<td>${c??''}</td>`).join('')+'</tr>').join('')+'</tbody>';
}
async function openTask(index){
  current=index; const r=await fetch(`/api/task/${index}`); currentTask=await r.json();
  document.getElementById('empty').style.display='none'; document.getElementById('detail').style.display='block';
  document.getElementById('heading').textContent=currentTask.task_id;
  document.getElementById('sub').textContent=currentTask.case_id;
  document.getElementById('chart').src=currentTask.image_url;
  const meta=document.getElementById('meta'); meta.innerHTML='';
  ['scenario','misleader_type','plot_type','reasoning_operation','expected_action_id'].forEach(k=>{meta.innerHTML+=`<dt>${k}</dt><dd>${currentTask[k]??''}</dd>`});
  document.getElementById('workflow').textContent=currentTask.workflow_instruction||'';
  document.getElementById('gt').textContent=JSON.stringify(currentTask.ground_truth,null,2);
  document.getElementById('mislead').textContent=JSON.stringify(currentTask.misleading_context,null,2);
  document.getElementById('decision').textContent=JSON.stringify(currentTask.intermediate_decision,null,2);
  document.getElementById('primary').textContent=JSON.stringify(currentTask.primary_action,null,2);
  document.getElementById('completion').textContent=JSON.stringify(currentTask.completion_action,null,2);
  document.getElementById('fallback').textContent=JSON.stringify(currentTask.fallback_scoring,null,2);
  table(document.getElementById('companions'), ['field','label','correct value','type','rationale'], (currentTask.companion_actions||[]).map(c=>[c.field_id,c.field_label,c.correct_value,c.input_type,c.rationale]));
  table(document.getElementById('actions'), ['role','action_id','label','outcome','rationale'], (currentTask.action_space||[]).map(a=>[`<span class="role-${a.role}">${a.role}</span>`,a.action_id,a.label,a.scoring_outcome,a.rationale]));
  const ann=currentTask.annotation||{}; document.getElementById('issueType').value=ann.issue_type||''; document.getElementById('notes').value=ann.notes||'';
  document.querySelectorAll('#statusBtns button').forEach(b=>b.classList.toggle('selected', b.dataset.status===(ann.status||'unreviewed')));
  renderList();
}
document.getElementById('query').oninput=renderList; document.getElementById('statusFilter').onchange=renderList;
document.querySelectorAll('#statusBtns button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#statusBtns button').forEach(x=>x.classList.remove('selected')); b.classList.add('selected');});
document.getElementById('saveBtn').onclick=async()=>{
  const selected=document.querySelector('#statusBtns button.selected');
  const payload={task_id:currentTask.task_id,status:selected?selected.dataset.status:'unreviewed',issue_type:document.getElementById('issueType').value,notes:document.getElementById('notes').value};
  const r=await fetch('/api/annotation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!r.ok){ alert(await r.text()); return; }
  const idx=tasks.findIndex(t=>t.task_id===payload.task_id); tasks[idx].status=payload.status; tasks[idx].issue_type=payload.issue_type; await openTask(current);
};
loadTasks();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8014)
    args = parser.parse_args()
    app = make_app(Path(args.tasks), Path(args.annotations))
    print(f"Task Action Space Review UI: http://{args.host}:{args.port}")
    print(f"Tasks: {args.tasks}")
    print(f"Annotations: {args.annotations}")
    app.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
