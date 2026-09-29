# GUI-Reflection × Misleading Visualization 实验协议

## 研究问题

本实验区分两个问题：

1. **端到端鲁棒性**：官方 GUI-Reflection checkpoint 在 misleading 图表上的任务成功率，是否接近同任务的 clean 图表条件？
2. **条件轨迹恢复**：当策略已经进入图表诱导的错误分支并看见其后状态后，它能否退出、避免重入、转向正确分支并最终正确提交？

二者不能互相替代。端到端成功可能只是模型一开始没有受骗；从错误页 Back 也可能只是局部导航，而没有撤销“图表 → 判断 → 分支”的视觉前提。

## 1. 官方 baseline 的实际边界

依据 [NeurIPS 2025 论文](https://papers.nips.cc/paper_files/paper/2025/hash/937ae0e83eb08d2cb8627fe1def8c751-Abstract-Conference.html)、[官方仓库](https://github.com/penghao-wu/GUI_Reflection) 和 [官方 8B SFT checkpoint](https://huggingface.co/craigwu/GUI_Reflection_8b_SFT)：

- 推理入口是 `GUI_Reflection_Agent.step(image, task_goal)`；每个任务先 `reset()`。
- 策略读取当前截图，并在 agent 内部维护最近截图、完整文本动作历史和 memory bank。官方默认实验可使用最近 4 张历史截图。
- 输出是一个原子 GUI 动作；点击坐标位于 0–999 规范化空间，再按真实截图尺寸缩放。
- 本项目适配时只向模型传 PNG 与 task goal。不得传 HTML、DOM 文本、accessibility tree、selector、element box 或 `select_option(...)` 之类语义动作。
- `Action Verification`、`Action Reversal`、`Mistake-Informed Reattempt` 是论文的数据构造/训练与任务类型，不是 runtime 中三个可独立打开的反思模块。运行时只有统一策略的下一步动作预测；模型是否输出 `PRESS_BACK` 必须由轨迹观察，不能由方法名称推定。
- 公开材料中可直接定位的是 `GUI_Reflection_8b_SFT`；仓库把该 agent 用作最终推理入口，但公开模型页没有明确列出一个另行打包、名称独立的 online-tuned final checkpoint。结果中必须如实写实际加载的 checkpoint 名称，不能把 SFT 路径自动描述成未公开的另一训练阶段。

官方工作主要在移动 GUI/截图坐标域训练，本项目的桌面 Web、原生 `<select>` 和长页面属于域迁移。若出现坐标 grounding、弹出控件或滚动失败，必须单列为执行/grounding 失败，不能把执行器换成 DOM helper 后仍称为同一 baseline。

## 2. 双轨设计

### 轨道 A：正式 paired 端到端评测

任务集合按下表分层报告，不能把不同分母拼成一个数：

| 集合 | N 对 | 规则 | 用途 |
|---|---:|---|---|
| `chart_only114` | 114 | official/clean 的任务、工作流、动作空间、ground truth/scoring 字段完全相同 | 最宽的 chart-only 敏感性分析 |
| `readiness95` | 95 | 在 114 对上排除任一臂为 `image_only_draft` 的 19 对 | 主要可执行集 |
| `strict_review94` | 94 | 在 95 对上再排除 source review 含 `gt_uncertain` 的 `env032` | 最保守主结果 |
| `smoke17` | 17 | readiness95 每个 `(scenario, misleader_type)` 取字典序最小 slug | 工程 smoke；不是统计主结果 |

机器可读规则与来源位于 [`build_task_sets.py`](build_task_sets.py) 和 [`task_sets/manifest.json`](task_sets/manifest.json)。`full140` 只作 exploratory sensitivity，因为其中 26 对并非只差图表。

每对任务的执行约束：

- 同一官方 SFT checkpoint、相同 generation 设置、固定 1280×960 viewport、device scale factor 1；
- primary 使用官方历史长度 4；如做 `temporal_len=0` 消融，必须另表报告，不能混入 primary；
- official 与 clean 两臂使用相同页面清理；仅对称隐藏壳层 `.chips` 元数据，不修改图表、任务文字或动作选项；
- 每个 task 必须独立 `reset()`，使用新的浏览器 session；
- 两臂顺序做平衡/交错记录，以降低 GPU 负载与时间漂移造成的顺序偏差；
- success 只读壳的隐藏提交评分，不以模型自行输出 `TASK_COMPLETE` 代替；
- 保存每一步实际送入模型的截图、raw output、parsed action、规范化/像素坐标、执行后 URL、提交结果和错误类别。

端到端主要指标为：

- `SR_misleading`、`SR_clean` 及 paired `SR_clean - SR_misleading`；
- directed vulnerability：clean 成功且 matched misleading 走指定 trap action 的比例；
- clean regression：misleading 成功而 clean 失败的比例；
- grounding failure、unsupported action、navigation blocked、timeout、agent/model error 各自的率；
- 按 scenario 与 misleader type 的原始计数和区间估计。

### 轨道 B：travel 可逆分支的条件恢复诊断

使用 [`travel_choose_confirm_review_sample`](../../../travel_choose_confirm_review_sample) 的 paired 页面：misleading 与 clean 入口只替换 dashboard 图；IL 是图表诱导 trap，KS 是正确州，最终正确目的地为 `KS:johnson`。评分依据见 [`sample_summary_zh.md`](../../../travel_choose_confirm_review_sample/sample_summary_zh.md)。

必须把以下两种条件分开：

#### Natural

从 dashboard 前的正常任务入口开始，所有动作均由官方 GUI-Reflection 生成并实际执行。只有发生 `Tstrong` 的运行，才进入“已看到自己误入后的状态”的条件恢复分母。没有自然 `Tstrong` 时，可以报告模型避免了 trap，但不能据此声称它具备错误后的恢复能力。

#### Forced-state

重置后把浏览器初始化到 IL trap 页，让模型从该截图开始继续任务，并在记录中标记外部 intervention。它只测“身处错误状态时能否逃离并完成”，不测模型是否识别了自己先前动作的错误。

不得通过覆盖模型输出、伪造其 action history，或让 runner 把模型原本的非 IL 动作偷偷改成 IL，来构造所谓 forced self-error。官方 `step(image, goal)` 没有受支持的外部历史注入接口；那样做会造成内部历史与真实页面不一致。Natural 与 forced-state 的分母、指标和结论必须分表，不能合并。

## 3. 事件定义

事件按实际页面转移和“真正送进模型的截图”定义，不能只用 URL 是否重复代替：

| 记号 | 定义 |
|---|---|
| `Tweak` | 首次从 neutral/dashboard 进入 IL trap 分支；动作已经执行，但模型未必看过到达后的截图 |
| `Tstrong` | IL trap 分支截图确实作为下一次 `step()` 输入被模型消费 |
| `B` | `Tstrong` 后模型输出并执行 `PRESS_BACK` |
| `X` | 已进入 trap 后，从 IL trap 分支转移到非 trap 页面；`B` 与 `X` 分记，因为 Back 可能无效，其他动作也可能退出 |
| `C` | `X` 后首次进入正确 KS 分支 |
| `T2` | `X` 后再次进入 IL trap 分支，即重入 |
| `S` | 隐藏 evaluator 记录最终 `outcome=success` |

成功的强恢复轨迹是 `Tstrong → (B ∧ X，同一转移) → C → S`，且在 `X` 后、`S` 前没有 `T2`。如果只有 `Tweak` 后立即结束，模型没有观察到错误后的页面，不能算验证了反思。若模型以其他动作退出 trap、稍后才任意按一次 Back，或 `B` 后又进入 IL，都不能因“曾按 Back”就计为强恢复。

条件恢复至少报告：

- `P(Tweak)` 与 `P(Tstrong)`；
- `P(B | Tstrong)`；
- `P(X | Tstrong)`；
- `P(T2 | X)`；
- `P(C | X)`；
- `P(S | Tstrong)`；
- strong stable recovery 的原始计数/分母；
- 从 `Tstrong` 到 `X`、`C`、`S` 的动作步数；
- no-op Back、grounding error、timeout、review-only/no submission 的独立计数。

Natural 的 initial trap rate 可以比较 misleading 与 clean；forced-state 不存在自然 `Tweak`，其首帧记为 intervention + `Tstrong`，只能报告条件逃离/完成率。

## 4. 允许与不允许的结论

| 观察 | 允许结论 | 不允许结论 |
|---|---|---|
| strict94 上 misleading/clean 差距小 | 该 checkpoint 在这组可评分 chart-only 任务上端到端较稳健 | 它一定使用了 Action Reversal 或显式撤销了视觉前提 |
| Natural 中出现无 `T2` 的 `Tstrong→X→C→S` | 该策略在观察到自身 trap 后表现出行为级稳定恢复 | 已证明内部存在因果图或 premise-retraction 表示 |
| 只出现 `B`，随后 `T2` | 局部返回动作不足以阻止重入 | 模型完全没有任何反思能力 |
| forced-state 成功 | 从错误状态出发，策略有导航逃离与完成能力 | 模型纠正了自己先前的错误动作 |
| 失败由坐标、弹窗、timeout 导致 | baseline 在该 Web 适配上的执行失败 | 误导图表导致了认知失败 |
| `benchmark_v2/` 单样本成功 | adapter smoke 可连通 | GUI-Reflection 抵抗了误导图表 |

最终论文表述应使用“行为级恢复/重入”而非根据 thought 文本宣称内部机制。raw thought 可供定性审查，但不作为成功评分依据。

## 5. 执行顺序

1. 先在 travel misleading/clean 各跑少量 Natural trajectory，确认官方模型确实能操作桌面 Web；
2. 单列 forced-state 诊断，检查 Back/退出/重入事件定义；
3. 跑 `smoke17` 工程覆盖；注意它基于 readiness95，包含 metadata 冲突的 `env032`，因此 strict smoke 应另从 strict94 的 16 个可用 strata 取样；
4. 跑 strict94 主结果；
5. 将 readiness95、chart_only114、full140 依次作为敏感性分析；
6. `real_world40` 最后单独运行并单独报告，不计算 paired clean 差。
