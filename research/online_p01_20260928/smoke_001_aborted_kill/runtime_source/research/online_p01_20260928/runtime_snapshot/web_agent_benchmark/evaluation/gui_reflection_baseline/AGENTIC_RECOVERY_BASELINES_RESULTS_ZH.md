# 深度回溯与分层纠错基线：定向恢复实验汇报

日期：2026-09-01  
用途：汇报 Speculative Rollback Correction 风格短分支回滚、ExACT 风格自主搜索回溯，以及 MobileUse 风格分层反思在误导可视化 Web Agent 样本上的实际作用位置。

## 一页结论

这轮结果不支持“现有回溯方法完全无效”，也不支持“加入反思就能解决误导图表”。更准确的结论是：

1. **短分支教师能发现错误，但一次纠正未必会被后续 agent 保持。**在 4 个继承错误格中，Speculative Rollback Correction 风格 reviewer 4/4 发现错误并定位到首个错误动作；但 `pub010` 误导标题格里，corrector 已重新选择正确的增长选项，student 随后又相信误导标题，把正确选择改成中性选项，最终没有提交。
2. **自主搜索能够解决这三个短分支样本，但后验反思可能把正确搜索结果改坏。**ExACT 风格搜索在 6 个任务×图表格中都探索到正确提交路径，直接选择最高价值候选时 6/6 成功；额外的多候选 contrast 反思改变了 4/6 个候选，4 次全部由成功变失败，最终只有 2/6 成功。
3. **MobileUse 风格的 24/24 成功不能归因于三层 reflector。**不使用 reflector 的同一 Qwen3-VL operator 已经 6/6 成功；动作、轨迹和完成 reflector 没有增加成功格，也没有产生一次新的物理纠错，却把总 token 从 19,712 增加到 86,188。`pub010` 误导标题上，轨迹 reflector 还明确要求把正确增长选项改回下降，只因一次撤销界面和共享 executor 护栏才没有真正执行。
4. **真正尚未稳定解决的不是 Back 本身，而是纠正后的视觉前提、实体和动作如何保持绑定。**搜索可能找到正确分支，reviewer 可能说出正确答案，operator 也可能已经选对；后续 reflector 或 student 仍会因误导标题、完成页面或实体 grounding 幻觉覆盖它。

因此，下一研究点不应笼统命名为“更深回溯”，而应聚焦：**显式视觉前提撤销、证据仲裁、纠正后实体—动作绑定持久化，以及不会破坏正确状态的完成验证。**

## 1. 本轮究竟跑了多少数据

### 1.1 统计单位

这轮只包含 **3 个语义不同的基础任务**。每个任务有误导图表和匹配干净图表两个 arm，共 6 个可见任务状态；不同方法和组件配置重复运行这些状态，形成 **42 个 controller cell**。42 不是独立样本量，不能据此计算总体泛化准确率。

| 方法探针 | 基础任务 | 图表 arm | 方法内部配置 | 正式 cell 数 |
|---|---:|---:|---:|---:|
| Speculative Rollback Correction 风格短分支教师回滚 | 3 | 2 | 1 | 6 |
| ExACT 风格枚举搜索 | 3 | 2 | 最高价值、额外 contrast 两种选择模式 | 12 |
| MobileUse 风格分层反思 | 3 | 2 | 纯 operator、动作、动作+轨迹、完整三层 | 24 |
| **合计** | **3** | **6 个任务状态** | — | **42** |

三组正式 run 共完成：

- 42/42 cell 落盘，0 个运行异常；
- 282 次模型调用，854,562 tokens；
- 620 次真实浏览器 transition，其中 540 次是 reset-and-replay；
- 802 张模型输入图像，原始尺寸均为 1280×960；
- 所有 controller 只在 fresh final replay 后调用一次隐藏 scorer。

这些总量只说明工件规模。不同方法预算差异很大，不能把 42 格合成一个成功率，也不能用总成功率横向排名三种方法。

### 1.2 三个任务与误导类型

| 任务 | 可见数据与正确判断 | 误导图表 | 干净图表 | evaluator 接管状态 | 正确恢复目标 |
|---|---|---|---|---|---|
| 城镇游客趋势 `pub010` | 1880 到 1891 总体从约 993 上升到 2917，应选择增长规划 | 标题错误写成“游客数量下降” | 标题与上升数据一致 | 继承错误的下降响应，页面 position 2 | 返回后选择 position 1 的增长规划并确认 |
| 可再生能源贡献 `env008` | 印刷值 Solar 41.2% > Wind 29.8% > Hydroelectric 18.5%，应选择 Solar | 柱形几何把 Wind 画得像最大值 | 柱高与印刷值一致 | 继承错误的 Wind，页面 position 3 | 返回后选择 position 2 的 Solar 并确认 |
| 工厂产量 `b035` | 2018 到 2023 总体从约 3480 降到 2055，应进入生产效率审查 | 标题错误写成产量上升 | 标题与下降数据一致 | **继承选择已经正确**，只是尚未提交，页面 position 3 | 不破坏正确选择，直接确认 |

`pub010` 和 `env008` 是错误恢复格；`b035` 是完成控制格，用来测试纠错系统会不会“为了纠错而纠错”。三者使用匹配诊断资产和固定布局，属于 evaluator-owned takeover 机制探针，资产清单仍标记 `reportable=false`，不是 `benchmark_v2_open` 的正式总体分数。

## 2. Agent 背后的模型与实验参数

### 2.1 统一基础模型

本轮三种 controller 的所有角色都由同一份本地模型驱动，以隔离 controller 机制差异。

| 设置项 | 实际值 |
|---|---|
| 模型 | `Qwen3-VL-8B-Instruct` |
| 本地权重 | `/mnt/data/datasets/open_source_models/Qwen3-VL-8B-Instruct` |
| 规模标记 | 8B |
| 权重精度 | bfloat16 |
| 运行设备 | `CUDA_VISIBLE_DEVICES=6` 的本地 GPU |
| 解码 | greedy，`do_sample=false` |
| temperature | 0 |
| top-p | 1 |
| 每次调用 seed | 12345；服务在每次请求前重置 PyTorch/CUDA seed |
| 最大输出 | 700 tokens |
| 视觉输入 | 有序原生多图；每张图独立输入，不使用低分辨率 contact sheet |
| 原始浏览器截图 | 1280×960 |
| 图像处理器上限 | 每图 `max_pixels=1,003,520` |
| 多图协议 | `2.0-native-multi-image` |

Speculative Rollback Correction 风格实验中的 student、reviewer 和 corrector 都是同一个 8B 模型；这里的“teacher”只表示 controller 角色，**不是更强模型**。这有利于做 matched-backbone 机制比较，但不同于原论文的 teacher-assisted 数据收集设置。

### 2.2 公平性与信息隔离

所有 controller 只能看到：

- 当前截图；
- 方法所需的最近有序截图；
- 自己可见的动作历史；
- 中性任务说明和当前可见动作。

模型看不到 canonical action id、正确角色、official/clean 条件名、pair id、隐藏 scorer 或另一 arm 的图表。提示词机械扫描未发现 runner truth 泄漏。隐藏 scorer 只在选定最终前缀后，由全新应用、服务器和浏览器重新执行完整前缀，确认真实提交后调用。

每次恢复都不是内存状态跳转，而是：

```text
关闭旧浏览器与应用
    → 启动新实例
    → 从初始页物理重放可见前缀
    → 比较截图与规范化页面状态
    → 继续搜索或最终提交
```

1、2、16 张图的独立 preflight 全部通过；正式审查也逐调用核对了图像数量、顺序、尺寸、协议和 SHA。

### 2.3 三个 adapter 的准确身份

| adapter | 本轮实现 | 预算 | 明确不包含什么 |
|---|---|---|---|
| **Speculative Rollback Correction 风格 teacher-assisted short-branch collector probe** | student 最多提出 3 个动作；reviewer 检查已执行的 GUI 动作与状态并定位首个有害动作；fresh reset/replay；corrector 给一个纠正动作；student 继续 | 默认三步短分支 | 不是官方训练后 policy；reviewer 不看未执行的非法 proposal；teacher 不是更强模型 |
| **ExACT-inspired enumerative MCTS + single-call VLM value debate + optional post-hoc contrast probe** | 枚举可见分支、保存节点、VLM 给候选状态估值；比较直接取最高价值与额外多候选反思重排 | 每格最多 18 rollout，探索系数 1.2，contrast 最多比较 8 个候选/16 张图 | 不是官方 ExACT 的双 agent、judge、跨任务反思记忆或官方 GPT-4o 配置 |
| **MobileUse-style nested reflector controller** | 同一 operator 下逐层加入动作效果 reflector、最近轨迹 reflector、全局完成 reflector | 每格最多 6 个 operator proposal | 不是官方 MobileUse checkpoint 或完整系统；共享 executor 的合法动作反馈不是 reflector |

## 3. 总体结果

### 3.1 正式 run 与成本

| 正式 run | cells | 结果摘要 | 模型调用 | tokens | 浏览器 transitions | 其中 replay |
|---|---:|---|---:|---:|---:|---:|
| `src_qwen8b_native_neutral_three_cases_v3` | 6 | 5 提交且正确，1 未提交 | 33 | 58,004 | 44 | 21 |
| `exact_qwen8b_native_neutral_three_cases_v3` | 12 | 最高价值 6/6；contrast 2/6 | 125 | 571,178 | 416 | 415 |
| `mobile_qwen8b_native_neutral_three_cases_v4` | 24 | 四模式各 6/6 | 124 | 225,380 | 160 | 104 |

ExACT 的物理搜索预算远大于另外两种方法，因此不能把 6/6 与 5/6 直接解释成方法排名。

### 3.2 Speculative Rollback Correction 风格结果

| 任务与 arm | student 在 review 前的三步短分支 | teacher verdict | fresh corrector | 最终轨迹 | 严格因果解释 |
|---|---|---|---|---|---|
| `pub010` 误导 | Revise → growth；第 3 个 proposal 非法且未执行 | 正确拒绝 takeover，定位 index 0 | 再次选择 growth | growth → Revise → neutral；未提交 | teacher 局部纠正正确，但 student 没有保持纠正后的前提 |
| `pub010` 干净 | Revise → growth；尚未提交 | 正确拒绝 takeover，定位 index 0 | 再次选择 growth | growth → Confirm，成功 | 从未提交变为提交，但缺少 matched no-teacher continuation，不能宣称严格 teacher 增益 |
| `env008` 误导 | Revise → Solar → Confirm，已经成功 | 正确拒绝 takeover，定位 index 0 | 再次选择 Solar | Solar → Confirm，成功 | student 在 teacher 前已独立恢复，teacher 回滚并重做是冗余 |
| `env008` 干净 | Revise → Solar → Confirm，已经成功 | 正确拒绝 takeover，定位 index 0 | 再次选择 Solar | Solar → Confirm，成功 | 同上 |
| `b035` 误导 | 直接 Confirm 正确 inherited selection | **错误拒绝**正确轨迹 | 又选择同一个正确 position 3 | position 3 → Confirm，成功 | 成功是尽管 teacher 误判；错误标题诱导了 reviewer |
| `b035` 干净 | 直接 Confirm 正确 inherited selection | 正确接受 | 无 | position 3 → Confirm，成功 | 正确完成控制 |

应分开报告两个数字：

- 4 个真实继承错误格：错误检测 4/4，首错定位 4/4；
- 2 个本来正确的控制格：正确接受 1/2，即 1 次 false reject。

`b035` 误导格的 false reject 尤其关键。reviewer 的理由同时承认“折线总体下降”和“当前 position 3 对应下降后的生产效率审查”，这些证据都支持当前动作，却仍输出 REJECT。独立 corrector 恰好重新选回正确 position 3，掩盖了 teacher verdict 的错误。

### 3.3 ExACT 风格结果

| 任务与 arm | 最高价值选择 | 额外 contrast 选择 | contrast 是否改 leaf | 失败位置 |
|---|---|---|---:|---|
| `pub010` 误导 | decline → Revise → growth → Confirm，成功 | decline → Confirm，失败 | 是 | 完成页面压过增长实体绑定 |
| `pub010` 干净 | decline → Revise → growth → Confirm，成功 | decline → Confirm，失败 | 是 | 同样失败，说明不只由误导标题造成 |
| `env008` 误导 | Wind → Revise → Solar → Confirm，成功 | 保持同一候选，成功 | 否 | 印刷值 41.2% 足以支持 Solar |
| `env008` 干净 | Wind → Revise → Solar → Confirm，成功 | 保持同一候选，成功 | 否 | 同上 |
| `b035` 误导 | 直接 Confirm 正确 position 3，成功 | Revise → 错误 position 1 → Confirm，失败 | 是 | 对候选实体发生错误重绑定 |
| `b035` 干净 | 冗余 Revise → 仍选 position 3 → Confirm，成功 | Revise → 错误 position 1 → Confirm，失败 | 是 | 倒置了“下降→生产效率”的任务规则 |

六对 contrast/highest-value 的 `search_tree.json` 逐字段完全相同；value calls 的 system/user prompt、逐帧 SHA、raw output 和 parsed output 也完全相同。唯一新增变量是 contrast 选择。因此，在这 6 个固定格内可以做严格因果表述：

- 正确提交路径没搜到：0/6；每格都探索了 3 个可见实体；
- 最终最高价值选择失败：0/6；
- contrast 改变候选：4/6；
- 4 次改变全部把原本成功的候选变成失败，没有一次改善；
- 只有 `b035` 干净 contrast 需要下游 actor；它只是继续确认 contrast 已经选错的扩产选项，不是独立根因。

这不表示 value model 完美。`b035` 误导格给所有候选都打了 0 分，最终只是靠 visit/tie-break 选中正确 direct-confirm；`b035` 干净格还把一个未提交的 finish 分支与正确提交分支同时打成 1.0。最安全的结论是：**本轮近枚举搜索覆盖了正确路径，最高价值选择碰巧在 6 格保持成功，而额外反思稳定性更差。**

### 3.4 MobileUse 风格结果

| 模式 | 6 个任务状态成功 | calls | tokens | transitions | 实际新增纠错 |
|---|---:|---:|---:|---:|---|
| 纯 operator | 6/6 | 16 | 19,712 | 40 | 基础参照 |
| 加动作效果 reflector | 6/6 | 30 | 49,962 | 40 | 42 个动作检查分布在三个启用模式；全部接受，0 rollback、0 semantic concern |
| 再加轨迹/循环 reflector | 6/6 | 36 | 69,518 | 40 | 本模式与完整模式合计 8 次轨迹检查，全部写 `needs_correction=true`；没有新增物理恢复 |
| 再加全局完成 reflector | 6/6 | 42 | 86,188 | 40 | 6 次全部 allow，0 block、0 corrective action |

完整模式 token 是纯 operator 的约 4.37 倍，最终物理轨迹却在每个 task×arm 上完全相同：

- `pub010`：decline → Revise → growth → Confirm；
- `env008`：Wind → Revise → Solar → Confirm；
- `b035`：正确 position 3 → Confirm。

动作 reflector 和 global reflector 的真正纠错分支在本轮没有被触发。`b035` 首步 Confirm 后任务已经结束，所以轨迹 reflector 0 次调用；不能用 `b035` 的成功评价循环纠错。

共享 executor 一共拦截了 12 个当前不可见动作：纯 operator 2 次、动作模式 2 次、轨迹模式 4 次、完整模式 4 次。它们都消耗 operator proposal，但产生 0 个浏览器 transition，并向下一步返回当前可见 legal actions。这个护栏对所有模式一致，**不是 MobileUse reflector**。

## 4. 三个代表样本的误导前后与纠错作用位置

### 4.1 `pub010`：纠正可以发生，但会被标题或完成状态覆盖

误导图表的标题声称“游客数量下降”，折线却从约 993 总体上升到 2917。接管页继承 decline-response：

![pub010 误导标题与继承错误选择](runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_action_trajectory_reflectors/restores/restore_0000_612349/state_01_transition_0000.png)

#### 旧 GUI-Reflection checkpoint

- 自然决策：干净标题 6/6 正确提交；误导标题 6/6 提交下降响应。
- 显式告诉它当前选择与结果矛盾后：干净标题 6/6 返回并改选增长；误导标题 0/6 返回、0/6 改选增长。
- 作用边界：误导标题建立的旧视觉前提没有被矛盾信号覆盖。

#### 本轮 Speculative Rollback Correction 风格

```text
继承 decline
    → student 自己 Revise → growth
    → teacher 正确定位 takeover 错误
    → fresh corrector 再选 growth
    → continuation 再次相信“Decreasing”标题
    → Revise → neutral
    → 未提交
```

teacher 能做局部错误检测和正确重选，但纠正没有写入可持续的 belief/action binding。最终失败发生在 teacher 纠正以后。

#### 本轮 ExACT 风格

```text
同一搜索树
    ├─ 最高价值：decline → Revise → growth → Confirm    成功
    └─ contrast： decline → Confirm                     失败
```

contrast 的视觉结论退化为通用的 “Decision submitted”，把更短的已完成页面误当成更好的候选。干净标题上也发生同样失败，因此这是完成偏置，不是只由误导标题造成。

#### 本轮 MobileUse 风格

纯 operator 已经忽略标题、重新选择 growth。加入轨迹 reflector 后，reflector 反而只抓住 “Decreasing” 标题，明确反馈“重新选择 decline-response”。下一 operator 确实尝试 Revise，再尝试不可见的 choose；两次都被 one-reversal UI 和共享 executor 拦截，最终才 Confirm 正确 growth。

![pub010 已正确重绑定到 growth](runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_action_trajectory_reflectors/committed/state_03_transition_0002.png)

这格的正确说法是：**成功尽管 trajectory reflection 有害**。如果页面仍允许第二次 Revise，该有害意图可能真正破坏答案；本轮只能证明界面护栏挡住了它，不能证明一定会失败。

### 4.2 `env008`：这次 Qwen operator 能读印刷值，但 reflector 没有增加恢复

旧 GUI-Reflection 的关键 22 条最近历史轨迹中，21 条执行 Back，0 条正确提交；它经常返回后重新选择 Wind。这正是“完成局部导航撤销，但没有完成正确实体/action 重绑定”的原始例子。

本轮三种 agent adapter 的表现不同：

- Speculative Rollback Correction 风格：student 在 teacher 介入前已经 `Wind → Revise → Solar → Confirm`；teacher 的回滚与重做是冗余。
- ExACT 风格：误导和干净 arm 的两种选择模式全部保持 `Wind → Revise → Solar → Confirm`；搜索明确使用 Solar 41.2% 的印刷值。
- MobileUse 风格：纯 operator 已经完成同一恢复，三个 reflector 没有改变物理轨迹。

这说明本轮 Qwen3-VL-8B 在这个具体页面上能优先读取印刷值，误导柱形几何没有击穿它。不能把成功归因于 teacher、搜索或 Mobile reflector，也不能与旧 GUI-Reflection checkpoint 直接做模型能力比较，因为 backbone、动作接口和评测协议都不同。

轨迹 reflector 仍暴露了内部问题：它一边正确写“Solar 41.2% 最大”，一边声称 operator “反复选择 Wind、没有利用反馈”，但实际 operator 在继承一次 Wind 后已经选中 Solar。干净 arm 中，这种冗余反馈还额外诱发一次不可见 choose，增加了摩擦。

### 4.3 `b035`：正确状态也会被 reviewer 或 contrast 破坏

这个完成控制接管时已经选择正确的生产效率审查，只需 Confirm。

#### 旧 GUI-Reflection checkpoint

旧定向恢复条件从错误扩产选择开始：4/4 返回并改选生产效率审查，但只有 1/4 正确提交。它说明语义重绑定与最终完成是两个断点。

#### 本轮结果

- Speculative Rollback Correction 风格：干净标题 reviewer 正确 ACCEPT；误导标题 reviewer 错误 REJECT，虽然其理由本身已经承认总体下降和当前选项正确。corrector 又选回同一 position 3，结果才没有被破坏。
- ExACT 最高价值：误导标题直接 Confirm 成功；干净标题做了冗余 Revise 后选回同一 position 3，仍成功。
- ExACT contrast：两臂都把正确状态改成 position 1 并错误提交。误导 arm 发生候选实体标签幻觉；干净 arm 直接把“下降→生产效率”规则倒置成“下降→扩产”。
- MobileUse 风格：四模式都直接 Confirm。动作 reflector 只验证提交，轨迹 reflector没有触发；global 正确用下降数值放行，但没有改变动作。

`b035` 证明恢复系统还必须具有 **no-harm property**：在当前状态已经正确时，reviewer 或 reflector 应优先保护现有绑定，而不是默认产生一次“纠正”。

## 5. 误导 arm 与干净 arm 的差异究竟在哪里

| 方法与样本 | 干净 arm | 误导 arm | 能否归因于误导可视化 |
|---|---|---|---|
| Speculative Rollback Correction：`pub010` | corrector 后 Confirm 成功 | corrector 后 student 被标题重新诱导，改为 neutral 且未提交 | 有明确的标题相关 continuation 差异，但只有单格 |
| Speculative Rollback Correction：`env008` | student 在 teacher 前已成功 | student 在 teacher 前也已成功 | 本格没有显示误导几何影响 |
| Speculative Rollback Correction：`b035` | 正确 ACCEPT | 错误 REJECT，但 corrector 选回原正确项 | reviewer verdict 的标题诱导证据明确；最终二元结果被 corrector 掩盖 |
| ExACT：`pub010` | highest 成功、contrast 失败 | highest 成功、contrast 失败 | contrast 失败并非误导标题特有 |
| ExACT：`env008` | 两模式成功 | 两模式成功 | 本格没有显示误导几何影响 |
| ExACT：`b035` | highest 成功、contrast 失败 | highest 成功、contrast 失败 | 最终二元结果相同；内部 hallucination 形式不同 |
| MobileUse：全部任务 | 12/12 成功 | 12/12 成功 | 最终结果无 arm 差异；`pub010` 误导 arm 的 trajectory 内部被标题劫持 |

因此，这轮最强证据不是“误导图让所有深回溯失败”，而是：

> 正确恢复轨迹已经被 student 或搜索发现后，通用 reviewer/reflector 仍不能稳定保存从视觉证据到命题、实体和 action 的绑定；有时它会因误导标题或表面完成状态覆盖正确分支。

## 6. 与 GUI-Reflection 原实验如何合并理解

| 样本 | 旧 GUI-Reflection 的主要断点 | 本轮更深 agent adapter 的新增信息 |
|---|---|---|
| `pub010` | 误导标题下不返回或直接确认旧错误 | teacher 可定位错误，搜索可找到正确分支；但 student continuation 和 trajectory reflector 仍可被标题重新劫持 |
| `env008` | 21/22 返回，但 0 正确提交，常重入 Wind | 本轮 Qwen operator 自主读出 Solar 41.2 并成功；不能归因于 reflector，也说明需要在同一 backbone 上比较 controller |
| `b035` | 能返回并改选正确，但常不 Confirm | 本轮是“已经正确、只差提交”的控制；teacher/contrast 可能破坏它，Mobile operator 能直接完成 |

旧实验使用官方 `craigwu/GUI_Reflection_8b_SFT` checkpoint（InternVL/InternLM2.5-7B 架构），本轮使用 Qwen3-VL-8B-Instruct，并改变了动作空间和 takeover protocol。两批实验只能做机制互补，不能把成功率直接相减并声称某个 controller 提升了多少。

## 7. 下一篇论文应如何调整研究问题

### 7.1 不再使用的过强命题

这轮已经否定了两个过强叙述：

- “现有回溯搜索无法解决误导图表”：不成立。近枚举的最高价值搜索在 6 个固定格全部成功。
- “加入更多 reflection 会更稳”：不成立。ExACT contrast 4 次把成功改成失败；Mobile trajectory 也产生有害或自相矛盾反馈。

### 7.2 更有支撑的研究命题

建议把新方法定位为 **premise-aware recovery controller，视觉前提感知恢复控制器**：

```text
截图中的多个证据通道
标题 / 印刷数值 / 几何 / 图例
          ↓
显式前提账本
“旧判断是什么、由什么支持、哪条反证使它失效”
          ↓
回滚或搜索
只负责回到可修改状态并生成候选
          ↓
实体—动作绑定保护
新命题 → 目标实体 → 当前页面可见选项
          ↓
语义完成验证
先核对绑定，再允许 Confirm；不能只奖励“Decision submitted”
```

最小可验证的四个模块是：

1. **前提撤销记录**：明确保存“下降标题不再是可信依据”“Solar 的印刷值优先于失真柱高”，后续模块若要覆盖它必须给出新证据。
2. **证据仲裁**：把标题、数值、几何和图例作为可冲突的独立通道，而不是让同一个 VLM 用一句自由文本混合裁决。
3. **纠正后绑定不变量**：保存 `corrected claim → entity → visible action`；reviewer、value model 和 completion checker 都必须重新验证这条映射。
4. **no-harm 完成保护**：对 `b035` 这类当前已经正确的状态，若没有新的反证，禁止无理由回滚或改选。

### 7.3 下一轮最有价值的实验

第一阶段不需要立刻跑完整 140 项。建议先扩成约 12 个独立基础任务的机制面板：标题冲突、几何—数值冲突、图例反转、尺度/聚合误导各 3 个，并在每类加入：

- 错误深度 1、3、5 的 takeover；
- 至少一个“当前已经正确”的 no-harm 控制；
- 实体、按钮位置和颜色轮换；
- 搜索 only、搜索+通用 reflection、搜索+前提账本、完整方法四个消融；
- 逐格记录前提是否撤销、实体是否重绑定、是否提交，而不只看最终 success。

如果前提账本在这个面板上稳定改善，再扩大到 `benchmark_v2_open` 的自然错误与更多图表类型。这样能先证明机制，再谈总体统计。

## 8. 对抗审查、淘汰实验与边界

对抗审查子代理逐项核验了三组正式 run。结论是 42 格机械有效，无剩余代码级阻断：

- Speculative Rollback Correction：33 次调用、51 张图、44 transitions 与 aggregate 一致；4 个真实错误格和 2 个正确控制分开审查。
- ExACT：六对搜索树与 value calls 逐字段相同；551 张图顺序与候选 before→after 配对一致。
- MobileUse：200 张图、四种嵌套配置与调用关系一致；每个 task×arm 的最终物理 prefix 完全相同。
- 三组均为 prompt truth 泄漏 0，fresh restore/replay 一致，最终完整 prefix 后只调用一次 scorer。

以下旧 run 明确淘汰，不进入本文任何正式数字：

- 使用低分辨率 contact sheet、模型难以读取图表文字的旧 ExACT/Mobile/SRC run；
- 把 final-review 非法 choose 错误转换成 finish 的旧 Mobile supplement；
- prompt 显式提示“图表可能冲突、优先标签/数值”的旧版本；
- 因非法 revise 抛异常而中断的 `mobile_qwen8b_native_neutral_three_cases_v3`；
- 所有 smoke 只用于工程回归，不并入正式 42 格。

Mobile v4 在统一不可见动作处理后运行，因此其 runner SHA 与较早的 SRC/ExACT 正式 run 不同；两组较早 run 中已观察到的 final-review choose 本来就按零执行处理，其内部结论不受后来泛化补丁影响。不能声称三组使用完全相同的 runner source hash。

当前测试为 9/9 通过；1/2/16 图 preflight 通过。本轮正式有效范围只覆盖 Qwen 本地多图 backend，不能外推到未验证的非 Qwen backend。

## 9. 可复现实验入口与原始工件

### 9.1 核心代码

- [`run_agentic_recovery_baselines.py`](run_agentic_recovery_baselines.py)：三种 controller adapter、fresh restore/replay、统一 executor 和最终评分。
- [`qwen3_vl_server.py`](../qwen3_vl_server.py)：Qwen3-VL BF16 原生多图服务。
- [`llm_client.py`](../../../adversarial_pipeline/llm_client.py)：本地多图请求接口。
- [`test_agentic_recovery_baselines.py`](tests/test_agentic_recovery_baselines.py)：动作边界、提示泄漏与后验审计单测。
- [`MULTI_IMAGE_PREFLIGHT_20260901.json`](runs/agentic_recovery_baselines/MULTI_IMAGE_PREFLIGHT_20260901.json)：1/2/16 图服务 preflight。

### 9.2 正式结果目录

- [Speculative Rollback Correction 风格正式结果](runs/agentic_recovery_baselines/src_qwen8b_native_neutral_three_cases_v3/aggregate.json)
- [ExACT 风格正式结果](runs/agentic_recovery_baselines/exact_qwen8b_native_neutral_three_cases_v3/aggregate.json)
- [MobileUse 风格正式结果](runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/aggregate.json)

每个目录包含 `run_manifest.json`、`aggregate.json`、`results.json`，以及每格的 `summary.json`、`model_calls.json`、restore receipts 和截图。

### 9.3 方法来源

- Speculative Rollback Correction：[论文](https://arxiv.org/abs/2606.12485)，[官方仓库](https://github.com/LongkunHao/SRC_gui_agent)
- ExACT：[论文](https://arxiv.org/abs/2410.02052)，[官方仓库](https://github.com/microsoft/ExACT)
- MobileUse：[论文](https://arxiv.org/abs/2507.16853)，[官方仓库](https://github.com/MadeAgents/mobile-use)
- 本轮代码实现遵循已安装的 [Ponytail](https://github.com/dietrichgebert/ponytail) 最小实现原则；它不改变实验方法身份。

## 10. 给老师的两分钟汇报话术

我们用同一个 Qwen3-VL-8B，在三个代表任务的误导/干净配对上做了 42 个定向恢复 cell。短分支教师能 4/4 发现继承错误，但 `pub010` 中 teacher 选对后 student 又被误导标题带回错误判断；它还在一个本来正确的 `b035` 控制上 false reject。ExACT 风格搜索在 6 个格里都找到了正确提交路径，直接取最高价值时 6/6 成功；但额外 contrast 反思有 4 次覆盖正确候选，4 次都把成功变成失败。MobileUse 四模式表面上全部 6/6，不过纯 operator 已经 6/6，三层 reflector 没新增任何物理纠错，完整模式 token 成本是纯 operator 的 4.37 倍；在 `pub010` 误导标题上，轨迹 reflector 还试图把正确增长改回下降，只是被一次撤销界面挡住。

所以现有 agent 方法证明“搜索到替代分支”可以解决这些短样本，但没有稳定解决“纠正后的视觉前提如何持续绑定到正确实体和动作”。我们的下一研究点应是显式前提撤销、证据仲裁、绑定保护和 no-harm completion，而不是单纯再加一层 reflection。
