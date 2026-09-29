# GUI-Reflection baseline 对抗审查

审查日期：2026-08-30。该审查由独立子代理在实现过程中并行完成，目标不是提高被测模型得分，而是主动寻找会让复现实验得出错误结论的路径。主实现随后逐项复核并用测试或实机校准验证修复。

## 核心威胁与处理

| 风险 | 具体失败场景 | 审查结论与处理 |
|---|---|---|
| 答案泄漏 | 在 `benchmark_v2/` 单样本壳上测试；页面同时展示 clean/misleading 图、真实均值和 reviewer action labels，正确提交被误写成视觉前提撤销 | 该目录只允许做连通性展示，不进入性能分母。正式集合来自 `benchmark_v2_open/` |
| baseline 身份漂移 | 用本地普通 InternVL、API VLM、mock policy 或现有语义 agent 替代官方 checkpoint，却沿用 GUI-Reflection 名称 | model service 只导入官方 `GUI_Reflection_Agent`；没有真实本地权重时明确失败，不提供替代模型回退 |
| 动作接口漂移 | 将模型坐标预测改写成 DOM selector、可见文本点击或 `<select>` helper，掩盖 Web grounding 失败 | 模型只收 screenshot + goal；runner 只执行物理坐标、键盘、Back/Enter/Wait。DOM 仅用于双臂相同的 `.chips` 清理，不向模型泄漏内容或几何 |
| 跨条件/审查页泄漏 | travel agent 点击 `/` 或 `/review` 后读到 paired chart/正确路线；正式 agent 返回根任务列表后看到其他任务 | 路由按 condition/task/asset 收紧；root、review/admin、其他 slug、另一 arm 和跨域页面都会终止，且禁页不会进入下一张模型截图 |
| “曾按 Back”假装恢复 | 模型用其他动作离开 IL，稍后任意按过一次 Back，最终偶然到 KS；松散布尔值把它记作 Action Reversal | 强恢复要求模型真实看过 IL 反证截图，且 `PRESS_BACK` 本身完成 IL→非 trap 转移，之后不重入 IL，再进入 KS 并获隐藏评分成功 |
| URL 正确假装任务成功 | 访问 KS 后输出 `TASK_COMPLETE`，但没有提交或提交错误目的地 | URL recovery 只作分支信号；`full_ordered_recovery` 必须合并 sample server 的 `outcome=success` 与 `recovered_to_expected_route=true` |
| 把避免受骗当作纠错 | 模型从未进入 IL，却因最终成功被描述成“错误后反思成功” | Natural 轨迹的端到端成功与 `Tstrong` 条件恢复分开统计；只有 IL 截图确实送入下一次 `step()` 才进入错误后恢复分母 |
| paired 因果混淆 | 将 official/clean 中任务文本、动作空间或 GT 同时变化的 26 对解释成纯图表效应 | 主分析分层为 chart-only 114、readiness 95、strict-review 94；full140 只作探索性敏感性分析 |
| 可见元数据泄漏 | environment/health official 首页显示 `misleader_type`、`task_readiness`，clean 不同 | 两臂在每次截图前对称移除 `.chips`；正式 Firefox 校准确认 `env001` 实际移除 1 个 badge |
| 有争议 GT 混入主结果 | `env032` canonical row 标为 `formal_scored_task`，但 source review 仍为 `gt_uncertain` | readiness95 保留并披露；保守主集合 strict94 排除；smoke17 含该样本，不能代替 strict 主结果 |
| 移动→Web 域迁移误归因 | 原生 select、滚动、坐标或弹窗失败被写成认知纠错失败 | runner 单列 invalid action、grounding/browser error、navigation blocked、timeout、agent error；不得用 DOM helper 悄悄修复后仍宣称同一 baseline |
| harness 校准冒充模型数据 | 人工坐标脚本能走 IL→Back→KS，就被报告成 GUI-Reflection 有恢复能力 | 所有校准均标记 model-free；实际模型结果另列为 travel 2 条和 formal 34 个单元，且只按隐藏提交判成功 |
| 进程成功冒充任务成功 | runner exit 0 或模型输出 `TASK_COMPLETE`，就被计为完成 | formal 的 34 个单元全部检查 hidden submission；27 条 `TASK_COMPLETE` 因无提交均记为 completion failure |
| 零提交冒充鲁棒 | `directed_vulnerability=0`、clean-official gap 为 0pp，被解释成不受误导 | 两臂均为 0/17 success，34/34 无提交；这些统计量处于共同地板，不能估计图表效应 |
| 记录齐全冒充有效配对 | `complete_pair_count=17` 被表述成 17 个双臂均有效的 pair | 汇总器只检查两臂记录存在；official `pub008` 是 invalid run，因此是 17 个记录配对、16 个双臂有效 pair 加 1 个含 invalid 单元的 pair |
| endpoint 名字冒充可见 Search | 因内部 POST 路径叫 `/state-search`，就声称测量了重新点击 Search | travel 页面可见控件不是字面 Search；该样本只能作结构类比，不能报告 Search 重入 |

## 对抗样例的选择

标准 140 任务是 task→dashboard→form→terminal 的提交链，错误提交后只有隐藏 scorer，通常没有可见的“你错了”页面。因此它适合端到端 paired robustness，却不充分激活论文所讨论的错误后 reversal。

现有 `travel_choose_confirm_review_sample` 更适合机制诊断：misleading map 可诱导 IL，而 IL profile 随后清晰显示 risk index 96 / High；KS profile 显示 5 / Low。它提供延迟反证、真实浏览器 Back、可观察重入和隐藏最终评分，同时 misleading/clean 只替换 map。正式协议因此保留双轨：formal paired 端到端结果 + travel 条件恢复结果，不能用其中之一替代另一个。

## 已执行的反例校准

两条纯坐标、无模型轨迹证明测量链能区分关键失败模式：

1. `dashboard → IL → Back → dashboard → Enter`：Firefox 保留输入 `IL`，再次进入 IL；事件记录为 re-entry，不能算恢复。
2. `dashboard → IL → Back → dashboard → directory → KS → Johnson → submit`：隐藏 scorer 为 success，证明真实恢复路径和最终评分可合并；它仍只是人为 harness calibration。

新增测试还覆盖了一个专门反例：`IL → CLICK exit → unrelated Back → KS` 虽然包含 trap、Back、exit 和 KS 四个松散布尔值，但严格有序恢复必须为 false。

## 运行后的独立反方审计

官方代码和四个 SFT shard 已经完整本地化并逐分片校验；官方 wrapper 实际完成 266 次 model step，没有模型服务 400/500。反方审计随后不采信 runner 的 exit 0，而是逐个比对 `summary.json`、34 条 `runs.jsonl`、34 个 trace summary、252 张截图和 shell logs，确认：

- 34/34 `submission_observed=false`，没有 success，也没有可解释为“未受骗”的 `misleading_failure`；
- 252 张实际截图和 trace 声明全部是 `1280×960`；
- 7 次模型口述 `Submit Form` 都没有真实提交，页面仍在 `/form`，`reached_confirmation=false`；
- official `pub008` 的 containment violation 由模型点击真实的 `Back to Portal` 触发，隔离器按设计阻止根任务列表进入下一张截图，不是基础设施错误；
- official `env008` 的真实 URL 序列支持 `dashboard → Back → task → 同一 dashboard` 重入；模型在重入前后均把 misleading target `Wind` 当成最大源。clean 对照没有第二次 dashboard，但两臂都未提交，所以它只是一条定性机制证据。

尚未关闭的是**识别问题**而不是下载问题：clean smoke 也是 0/17，最终成功指标处于 Web grounding/completion 地板；现有 travel Natural 又没有自然进入 chart/trap。因此当前不能从最终成功率估计 GUI-Reflection 的图表纠错效应，也不能把 `env008` 单例升级为总体因果结论。直接运行 strict94 会扩大端到端失败样本，但不自动解决这个识别问题。
