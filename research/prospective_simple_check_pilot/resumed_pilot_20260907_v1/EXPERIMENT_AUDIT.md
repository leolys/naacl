# 实验完整性审查

日期：2026-09-07；审查者：fresh GPT-5.6-Sol ultra sub-agent；同系列、provisional。只有一次审查episode，因耗时在收尾时中断长调查，并要求按已核实证据返回，不要求改变结论或给PASS；原始请求与最终回复见 `.aris/traces/experiment-audit/2026-09-07_resume_v1/`。

以下为审查者原文；短文件名对应本段源码、live_panel_03或其evaluator目录，不代表审查了所有历史实验。段末处理说明是执行者记录，不是第二次审查。

结论：**WARN（same-family、provisional）**，非完整性 PASS。

- **A GT provenance—PASS**：在线仅投影 `public_task`（`panel.py:170-178,181-183`）；评分在结束后加载数据集 spec（`panel.py:298-305,334-347`），并按 `expected_action_id` 判定（`safe_shell.py:233-245`）。独立重算 96 行、16 个原 spec，0 不一致；未见 gold 键进入已查在线请求。
- **B normalization—PASS**：无按模型输出最大值归一化；恢复率明确为 `recovered/自然错误checkpoint数`（`panel.py:359-384`）。本轮自然错误为 0，报告保持 N/A。
- **C artifacts—PASS/WARN**：12 个自然 checkpoint 全正确；36 个确认提交=34 success+2 misleading failure，另 3 未提交、57 未运行。两次失败均是同一 `b046` 的 B2 核查后改坏，不是自然错误或两个独立任务（`CASE_TABLE.json:2481-2637,3088-3244`）。旧 9 条仅引用，新 27 条提交；未见 unit01–03 重建或重复 POST。恢复状态、像素、prompt 均等且完整 payload 相等（`resume_proof.json:4-35`；`reissued_request.json:3-6`）。
- **D executed code—WARN**：运行时五份源码与当前源码逐字节一致；但配置比较是非对称的，仅遍历新配置键，删除旧非忽略键可能漏检（`resume_panel.py:175-179`）。再次直接从多段来源接续还会覆写嵌套 `source_directory`（`:81-86`）；`NEXT_ACTION.md:7` 已承认需先补多段来源支持。
- **E scope/cost—WARN**：仅 3 个基础任务完整，不能泛化至计划 8 个任务或官方 GUI（`PILOT_REPORT.md:3-6`）。39 个完成响应均报告 Luna，权重未验证，不能称 Sol 排名（`:12-13`）。117 次尝试、281+212=493 transitions、API 上界 46.514392 美元均核对一致；实际账单仍未知。`CASE_NOTES.md:45` 的“74次真实调用”宜改为“调用尝试”，因 3 次 429 是否到达模型未知。
- **F 类型**：主实验为 **simulation_only 交互 + real_gt 离线评分**；单测/mock 为 simulation_only，非 human_eval、非模型生成 GT。

## 处理记录

已把CASE_NOTES中的“74次真实调用”改成“74次真实调用尝试”，明确429是否到达模型未知。未因此修改运行源码、原评分、manifest或旧结果。配置比较非对称和多段source_directory承接两项保留为下次接续前的代码修正任务；本次实际参数一致与已完成单元仅引用有独立工件核对。未继续推理或扩大面板。

