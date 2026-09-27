"""Post-run cost reconciliation and full response traces; never called by the actor."""
import argparse
import json
from collections import Counter
from pathlib import Path

from audit import read, pixels_equal, resolve_path
from report import label


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run, out = resolve_path(args.run).resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = read(run / "evaluator/chart_results.json")
    controls = read(run / "evaluator/controls.json")
    manifest, ledger = read(run / "run_manifest.json"), read(run / "budget.json")
    assert manifest["mode"] == "live-local" and manifest["status"] == "panel_finished"
    totals, phases, configs, image_counts = Counter(), Counter(), Counter(), Counter()
    requests, responses = [], []
    for request_path in sorted((run / "online").rglob("requests/*.json")):
        request = read(request_path)
        response_path = request_path.parent.parent / "responses" / request_path.name
        response = read(response_path)
        requests.append(request)
        responses.append(response)
        phases[request["phase"]] += 1
        if response["ok"]:
            m = response["metadata"]
            totals.update(m.get("usage") or {})
            configs[json.dumps(m.get("generation_config"), sort_keys=True)] += 1
            image_counts[(m.get("vision_input") or {}).get("image_count", 0)] += 1
    summary = dict(model_calls=ledger["model_calls"], request_count=len(requests), response_count=len(responses),
                   failed_model_responses=sum(not r["ok"] for r in responses),
                   usage=dict(totals), model_call_phases=dict(phases),
                   generation_config_counts=dict(configs), image_count_distribution=dict(image_counts),
                   total_images=sum(k*v for k,v in image_counts.items()),
                   browser_transitions=ledger["browser_transitions"],
                   transition_phases=dict(Counter(e["phase"] for e in ledger["events"] if e["kind"] == "browser_transition")),
                   control_branches=len(controls), chart_branches=len(rows), by_method={}, controls=[])
    for control in controls:
        summary["controls"].append({k: control[k] for k in ("control_id", "context_mode", "initial_selection", "explicit_target", "status", "final_selection", "correctly_completed", "model_calls", "browser_transitions")})
    for method in ("H0", "H1", "A2", "A3", "A4"):
        rr = [r for r in rows if r["method"] == method]
        summary["by_method"][method] = dict(states=len(rr), model_calls=sum(r["model_calls"] for r in rr),
            actor_calls=sum(r.get("actor_calls", 0) for r in rr),
            verification_calls=sum(r.get("verification", {}).get("model_calls", 0) for r in rr),
            active_observations=sum(r.get("verification", {}).get("active_observations", 0) for r in rr),
            submitted=sum(r["submitted"] for r in rr),
            correctly_submitted=sum(r["evaluation"]["score"]["outcome"] == "success" for r in rr),
            incorrect_proposals=sum(r["evaluation"]["checkpoint_selection_correct"] is False for r in rr),
            no_hook=sum(not r["checkpoint_reached"] for r in rr),
            timeouts=sum(r["status"] == "actor_call_limit" for r in rr),
            executed_verifications=sum(r["verification_executed"] for r in rr),
            incorrect_immediate_post_verification=sum(r["verification_executed"] and r["evaluation"]["immediate_selection_correct"] is False for r in rr),
            next_action_changed=sum(r["next_action_changed_selection"] for r in rr),
            event_counts=dict(sum((Counter(r["evaluation"]["event_counts"]) for r in rr), Counter())))
    summary["request_ids_unique"] = len({r["request_id"] for r in requests}) == len(requests)
    summary["ledger_matches_archives"] = len(requests) == len(responses) == ledger["model_calls"]
    summary["all_requested_images_accounted"] = all(not response["ok"] or len(request["image_artifacts"]) == response["metadata"]["vision_input"]["image_count"] for request, response in zip(requests, responses))
    summary["new_execution_source_unchanged"] = {p.name: p.read_bytes() == (run / "implementation" / p.name).read_bytes()
        for p in (Path(__file__).parent / "diagnostic.py", Path(__file__).parent / "runtime.py")}
    # Direct comparison of the first H0 call with its source; no token-count proxy.
    sources = read(run.parent / "audit/FIRST_SELECTION_SOURCES.json")
    summary["h0_initial_request_matches_source"] = []
    for source in sources:
        directory = run / "online" / source["prefix_id"] / "H0"
        request = read(sorted((directory / "requests").glob("*.json"))[0])
        old = source["request_after_selection"]
        summary["h0_initial_request_matches_source"].append(dict(prefix_id=source["prefix_id"],
            exact_text=request["system_prompt"] == old["system_prompt"] and request["user_prompt"] == old["user_prompt"],
            current_selection=request["public_context"]["current_selection"] == old["public_context"]["current_selection"],
            pixels=pixels_equal(directory / request["image_artifacts"][0], resolve_path(source["source_run"]) / old["image_artifacts"][0])))
    (out / "LIVE_SUMMARY.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    lines = ["# 逐状态真实响应与执行轨迹", "", "H1 在首选后核验比较中复用为 A0。核验与 actor 响应均原样保留，不补写模型理由。所有截图标记动作前/后；解释见 CASE_ANALYSIS.md。"]
    for row in rows:
        lines += ["", f"## {row['task_slug']} / {row['condition']} / {row['method']}", "",
                  f"继承选择：{label(row['initial_selection'])}；核验后立即：{label(row['immediate_selection'])}；最终：{label(row['final_selection'])}。",
                  f"结束：{row['status']}；实际提交：{row['submitted']}；离线原评分：{row['evaluation']['score']['outcome']}。",
                  f"调用 {row['model_calls']}，浏览器动作（含重放）{row['browser_transitions']}。"]
        for record in row.get("verification", {}).get("records", []):
            if "response" in record:
                lines += ["", f"核验阶段 {record['phase']}：", "", "```text", record["response"], "```"]
        for step in row["timeline"]:
            before = next((s["selected_text"] for s in step["state_before"]["selects"]), "无选择器")
            lines += ["", f"actor 第 {step['step']+1} 步；输入选择：{label(before)}。", "",
                f"[完整请求]({run}/online/{row['prefix_id']}/{row['method']}/requests/{step['request_id']}.json) · [动作前截图]({step['screenshot_before']})",
                "", "```text", step.get("response", "无响应"), "```", "",
                "执行回执：`" + json.dumps(step.get("receipt", {"error": step.get("error", "no browser action")}), ensure_ascii=False) + "`"]
    (out / "CASE_TRACES.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
