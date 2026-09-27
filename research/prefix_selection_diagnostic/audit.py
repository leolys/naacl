"""Offline, request-level audit and time/action-only first-selection sampling."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from runtime import load_runtime, resolve_path


def read(path):
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def pixels_equal(left, right):
    with Image.open(resolve_path(left)) as a, Image.open(resolve_path(right)) as b:
        return a.size == b.size and a.convert("RGBA").tobytes() == b.convert("RGBA").tobytes()


def pairs_equal(a, b, root):
    aa, bb = a["image_artifacts"], b["image_artifacts"]
    return {
        "system_equal": a["system_prompt"] == b["system_prompt"],
        "user_text_equal": a["user_prompt"] == b["user_prompt"],
        "current_selection_equal": a["public_context"]["current_selection"] == b["public_context"]["current_selection"],
        "public_state_equal": a["public_context"]["state"] == b["public_context"]["state"],
        "all_image_pixels_equal": len(aa) == len(bb) and all(
            pixels_equal(root / x, root / y) for x, y in zip(aa, bb)),
        "image_count": [len(aa), len(bb)],
    }


def build_audit(source_run, output):
    source_run, output = resolve_path(source_run).resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rt = load_runtime(source_run)
    timeline, comparisons, sources, consistency = [], [], [], []
    mappings = rt.runner.read_jsonl(source_run / "evaluator/prefixes.jsonl")
    for mapping in mappings:
        prefix_id = mapping["prefix_id"]
        directory = source_run / "online/prefixes" / prefix_id
        result = read(directory / "prefix_result.json")
        paths = sorted((directory / "requests").glob("*.json"))
        requests = [read(path) for path in paths]
        receipts = result["executor_receipts"]
        receipt_cursor = 1  # The first real receipt is initial task-page navigation.
        first = None
        for step, (path, request) in enumerate(zip(paths, requests)):
            response = read(directory / "responses" / path.name)
            action = rt.runner._extract_action(response.get("text", ""))
            state = request["public_context"]["state"]
            executed = None
            if receipt_cursor < len(receipts) and receipts[receipt_cursor]["action"] == action:
                executed = receipts[receipt_cursor]
                receipt_cursor += 1
            selections = state.get("selects", [])
            flags_consistent = all(
                [opt["text"] for opt in s["options"] if opt["selected"]] == [s["selected_text"]]
                for s in selections)
            current = rt.core.current_selection(state)
            expected_prompt = rt.runner.prefix_prompt(request["public_context"]["user_goal"], state)
            check = dict(prefix_id=prefix_id, step=step,
                         prompt_exactly_runtime_current_page=(expected_prompt == (request["system_prompt"], request["user_prompt"])),
                         flags_consistent=flags_consistent,
                         current_selection_consistent=current == request["public_context"]["current_selection"],
                         chosen_option_still_available=(not current or current in rt.core.visible_options(state)),
                         all_visible_options_consistent=rt.core.visible_options(state) == request["public_context"]["visible_options"],
                         submit_button_visible=any(x["text"] == "Submit Form" and x["type"] == "submit" for x in state["buttons"]))
            consistency.append(check)
            next_selection = requests[step + 1]["public_context"]["current_selection"] if step + 1 < len(requests) else None
            # A final post-action selection is supported by executor's selected-text postcondition;
            # it is NOT claimed to appear in the final pre-action screenshot.
            post_selection = next_selection
            post_basis = "next_actual_request_s_t_plus_1" if next_selection is not None else "not_observed"
            if post_selection is None and executed and executed["executed"] and action["action"] == "select_option":
                post_selection, post_basis = action["option_text"], "executor_success_with_selection_postcondition"
            entry = dict(prefix_id=prefix_id, step=step, request_path=str(path),
                         response_path=str(directory / "responses" / path.name),
                         request=request, response=response, screenshot_timing="s_t BEFORE a_t",
                         selection_before=current, proposed_action=action, execution_receipt=executed,
                         selection_after=post_selection, selection_after_basis=post_basis)
            timeline.append(entry)
            primary = next((s for s in selections if s["name"] == "primary_action"), None)
            if (first is None and executed and executed["executed"] and primary
                    and action["action"] == "select_option" and action.get("option_text")
                    and action.get("select_name") in (primary["name"], primary["label"])
                    and action["option_text"] in rt.core.visible_options(state)):
                if step + 1 >= len(requests) or next_selection != action["option_text"]:
                    raise ValueError(f"no actual post-selection request for {prefix_id}")
                after_request = requests[step + 1]
                first = dict(prefix_id=prefix_id, task_slug=mapping["task_slug"], condition=mapping["condition"],
                             task_alias=state["url_path"].split("/")[2], selection_step=step,
                             source_action_request=str(path), source_state_request=str(paths[step + 1]),
                             source_run=str(source_run), request_after_selection=after_request,
                             replay_receipts=receipts[:receipt_cursor],
                             observed_screenshots=[{"kind": rt.runner.screenshot_kind(r["public_context"]["state"]["url_path"]),
                                                    "path": r["image_artifacts"][0]} for r in requests[:step + 2]],
                             selection_rule="first executed, nonempty primary selector action in chronological order; no scorer used")
                sources.append(first)
        if first is None:
            raise ValueError(f"first executed selection unavailable: {prefix_id}")
        for step in range(3, len(requests) - 2):
            comparisons.append(dict(prefix_id=prefix_id, steps=[step, step + 2],
                                    requests=[str(paths[step]), str(paths[step + 2])],
                                    **pairs_equal(requests[step], requests[step + 2], source_run)))
    rt.core.write_json(output / "REQUEST_TIMELINE.json", timeline)
    rt.core.write_json(output / "TWO_STEP_COMPARISONS.json", comparisons)
    rt.core.write_json(output / "PUBLIC_FIELD_CONSISTENCY.json", consistency)
    rt.core.write_json(output / "FIRST_SELECTION_SOURCES.json", sources)
    (output / "PREFIX_INPUT_AUDIT.md").write_text(render_audit(source_run, timeline, comparisons, consistency, rt), encoding="utf-8")
    print(json.dumps({"requests": len(timeline), "two_step_pairs": len(comparisons),
                      "identical_pairs": sum(all(x[k] for k in ("system_equal", "user_text_equal", "current_selection_equal", "public_state_equal", "all_image_pixels_equal")) for x in comparisons),
                      "first_selection_states": len(sources)}, indent=2))


def render_audit(root, timeline, comparisons, checks, rt):
    lines = ["# PREFIX_INPUT_AUDIT", "", f"参考真实运行：`{root.name}`。只读运行时源：`{rt.snapshot}`。", "",
             "## 直接核验", "",
             f"逐项核对 {len(timeline)} 个前缀完整请求和响应；请求、图像路径、执行回执与 s_t / a_t / s_(t+1) 对齐保存在 REQUEST_TIMELINE.json。",
             "public_context 是归档与边界检查对象，不会自动作为第三条消息传给模型。真实推理收到 system_prompt、user_prompt 与 image_artifacts 指向的图片。",
             "运行时 models.py 的 LocalQwenServiceBackend.complete 直接传这三者；runner.generate_checkpoint 每步只调用 prefix_prompt(goal,state)。model_context/executed_prefix 虽被保存，却没有附入前缀消息。", "",
             "已继续核对快照 llm_client.py:1566–1591 与 qwen3_vl_server.py:102–137：HTTP 携带 system_prompt、user_text、image_paths 和解码配置；服务逐请求新建两条 messages。user content 依次为固定文本 Panel 1:、解码成 RGB 的当前图片、归档 user_prompt。原前缀只有一图。文件路径用于服务端读图，不作为模型文本；没有自动加历史。这里的‘完整请求’包含归档字段及这层已核实的固定服务包装，并非声称另存了原始 token tensor。", "",
             f"所有请求均可由旧运行时当前页模板逐字重建：{all(c['prompt_exactly_runtime_current_page'] for c in checks)}。因此实际前缀没有动作历史、此前回执或此前截图。",
             f"selected_text 与 selected flags 一致：{all(c['flags_consistent'] for c in checks)}；current_selection 一致：{all(c['current_selection_consistent'] for c in checks)}；已选选项未被过滤：{all(c['chosen_option_still_available'] for c in checks)}；选项列表一致：{all(c['all_visible_options_consistent'] for c in checks)}。",
             "原始 raw_browser_state 过滤隐藏/禁用 option，不过滤 selected option；visible_options 仅排除空项/占位项，不排除当前选择。没有发现可直接证实的公开字段投影错误。本轮不修改旧投影代码。", "",
             "## Figure 10 与流程提示差异", "",
             "paper_0707/main.aux 的 fig:benchmark-agent-prompt 编号为 10；已人工查看 figures/prompts/benchmark_agent_prompt.png，且与 web_agent_benchmark/evaluation/run_public39.py:397–404 对照。原版存在：", "",
             '> "If the needed form option is already selected and the Submit Form button is visible, click Submit Form next."', "",
             "它还说明：所需选项尚未选中则修改；不要重复选择已选中的所需项。它不是‘必须换选项’，也不是不顾目标的无条件提交。旧诊断前缀删掉了这段普通流程能力提示，仅留下 Complete and submit。旧前缀同样没有‘必须换选项’提示，故不能把交替改选归因为代码命令换选。",
             "本轮 H0 保持旧当前页提示原文；H1 只增加最多四个真实动作及公开回执。不同时恢复流程条款，以保持单因素对照；缺失条款是基线协议差异的事实，是否导致循环仍待单独实验，不能由本面板确定。", "",
             "## 相隔两步的实际输入", "",
             "从首次选择后的 s_3 起比较 t 与 t+2：system/user 文本逐字比较、完整公开状态比较、每张图片解码为 RGBA 后逐像素比较（尺寸和顺序也比较），不以 token 数作证。", "",
             "| 前缀 | 比较对数 | 文本相同 | 所有图像像素相同 | 全部语义输入相同 |", "|---|---:|---:|---:|---:|"]
    for prefix in sorted({x["prefix_id"] for x in timeline}):
        pp = [x for x in comparisons if x["prefix_id"] == prefix]
        same = sum(all(x[k] for k in ("system_equal", "user_text_equal", "public_state_equal", "all_image_pixels_equal")) for x in pp)
        lines.append(f"| {prefix} | {len(pp)} | {sum(x['user_text_equal'] and x['system_equal'] for x in pp)} | {sum(x['all_image_pixels_equal'] for x in pp)} | {same} |")
    lines += ["", "无两步比较对的前缀在 s_3 就提议提交，不是缺失记录。闭环中重复相同公开输入是直接观察；‘遗忘’或内部信念变化只是未验证解释。", "", "## 时间线", "",
              "截图都是模型动作前的 s_t，不是响应 a_t，也不是执行后的 s_(t+1)。下面的末步动作成功有执行器选中项后置检查支持；不存在末步动作后的旧截图时不伪造。", "",
              "| 前缀/step | 输入当前选择 | 模型动作 | 执行后选择 | 证据 |", "|---|---|---|---|---|"]
    for x in timeline:
        a = x["proposed_action"]
        desc = a.get("option_text") or a.get("text") or a["action"]
        lines.append(f"| {x['prefix_id']}/{x['step']} | {x['selection_before'] or '空'} | {desc} | {x['selection_after'] or '未记录/终止提议'} | {x['selection_after_basis']} |")
    lines += ["", "## 分母与边界", "",
              "旧运行：6 条自然前缀、3 个实际 before-submit checkpoint，均按数据集评分正确；12 条实际提交是三状态的四策略分支，不是 12 个独立任务。错误 checkpoint=0；错误状态恢复率=N/A。原 24 配置记录不等于 24 条已执行核查轨迹。B3 的三条实际核查均直接决定、未 crop。",
              "本轮六个首选状态以时间和成功选择动作取样，不读取 gold 决定触发。env008 保持原 gold，另标 evidence_conflict；误导图中 Wind 的柱高及纵轴读数也是可见线索，不称完全无支持，不向模型写入‘必须相信打印标签’。",
              "本审计未证明循环的单一机制，也没有重新判定原图表无效。"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_audit(args.source_run, args.output)
