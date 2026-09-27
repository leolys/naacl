# 合作者接手说明

## 材料对应关系

| 目录 | 用途与边界 |
|---|---|
| `web_agent_benchmark/benchmark_v2_open` | 原140对数据的移交子集。保留原任务行与必要资产，不含Real-World40。 |
| `web_agent_benchmark/*_shell`、`public_benchmark`、`evaluation` | 网页环境、动作执行、真实提交与评分、模型适配器及测试。 |
| `evaluation/gui_reflection_baseline` | 已有GUI-Reflection与SRC/ExACT/MobileUse风格的控制器适配、诊断与证据；不是声称完全复现各上游系统。 |
| `research/decision_evidence_audit`、`prefix_selection_diagnostic` | before-submit与首个选择后的开发诊断。触发点、共享状态、自然前缀与回顾性续跑不能混称。 |
| `research/prospective_simple_check_pilot`、`multi_model_simple_check`、`postpilot_attribution_diagnostic` | 固定八任务及后续模型/离线归因记录；具体已运行与未运行以真实日志和报告为准。 |
| `research/competing_rules_20260923`、`obc140_*` | 初始解释链生成、公开输入修复、140条候选与展示；旧含提示输入和修复后的输入保留分界。 |
| `counterquestion_*`、`explanation_completion_*` | 反问补齐与候选结论生成的发展记录，不为每例强制制造冲突。 |
| `alternative_conclusion_*`、`conclusion_search_*`、`candidate_registration_*`、`proposal_completion_*`、`conditional_expansion_*` | 从另一个可能结论寻找解释、保留条件式读法并交给后续核验。 |
| `ob_only_verification_*`、`ob_grounded_*`、`ob_refinement_*` | 观察O与解释规则B的分工、可见依据核验、v3–v7的开发与局限。 |
| `ob_full_comparison_20260927` | 已完成的全140单图六方案描述性比较；优先从REPORT及VERSION_GUIDE阅读。 |
| `paper/current` | 用户提供的新工作引言/方法草稿，不是本次移交新增的研究证据。 |
| `paper_0707` | 原benchmark论文相关正文、图表与文献；未纳入审稿意见、rebuttal或内部讨论。 |

表中简写的研究目录均位于 `research/`；GUI基线目录位于 `web_agent_benchmark/`。

## 当前需要理解的结论

v5在本固定已知面板上有最高的原标签相合数96/140，不等于方法已稳定可靠。参照和时间顺序核验有真实改善案例，但遗漏B必要条件、将无阈值当默认常规行动、没有将已见参照转为查询点区间仍会发生。请同时看pub001/health005的改善、env001/pub035的退化及pub008/env032的残余。

140任务中包含变式扩展，21个家族分组不等于21种独立机制。原开发24与其余116需分层；116也不能称为完全未见集。环境领域v5低于普通方案，应保留这一点。

## 如何看完整证据

Release分包采用仓库相对路径。解包到一个工作副本根目录即可补齐历史路径；不要扁平化，不要将不同版本输出复制为同名结果。只读阅览可直接打开分包里的独立HTML。

最新终版展示在Release中另存为独立附件 `OB_FULL_COMPARISON_REVIEW.html`；其原相对路径为 `research/ob_full_comparison_20260927/review_final_002/OB_FULL_COMPARISON_REVIEW.html`。直接下载HTML即可，无需为阅览取回所有原始记录。界面为中文，实际模型响应保留英语。记录中有结构通过、语义判断、最终选择等不同层级，不能把结构通过视为正确。

旧评测脚本可能引用被明确排除的硬件审计、旧绝对路径或非移交分区。本次提供的新移交检查验证导出副本与分包，绝不改写旧评分或给旧实验追写新版本身份。需要在线重跑时，应另建输出目录，重新设置模型接口、预算和硬件权限。

## 排除与安全

未移交：Real-World40、额外恢复扩展包、已停止的早期证据修订/回滚方向、审稿/rebuttal/内部讨论、大量候选池、重复压缩备份、无关项目、凭证、账户配置、ARIS安装、权重、环境目录、缓存、守卡与第三方作业资料。

历史科研报告中的资源收尾说明不是运行脚本，也不构成再次占用某张GPU的许可。账号协作通过仓库邀请完成，不分享项目所有者PAT。公开发布前须另行核实许可证。
