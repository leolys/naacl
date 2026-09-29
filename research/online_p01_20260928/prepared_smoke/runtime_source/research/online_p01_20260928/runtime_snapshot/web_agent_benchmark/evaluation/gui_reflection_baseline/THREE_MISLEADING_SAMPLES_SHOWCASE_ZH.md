# 三个代表性误导可视化 Web Agent 任务

> **展示对象：** `pub010`、`env008`、`b035`  
> **用途：** 向老师直观说明任务原貌、误导因素如何影响决策，以及每条任务真正要求 agent 执行的网页动作。  
> **阅读方式：** 每条样本依次展示误导版初始页、直至成功提交的完整多步流程，以及仅修正误导因素的干净对照。流程截图来自实际执行并经过隐藏评分核对。

## 一页结论

这三条任务不是单纯的“看图回答问题”。Agent 必须完成一条从视觉证据到网页操作的决策链：

```text
读取图表证据
    → 形成事实判断
    → 将事实判断绑定到一个候选操作
    → 点击并提交该操作
```

误导可视化攻击的正是这条链的上游。如果 agent 接受了错误标题或错误几何形状，它不仅会说错，还会点击错误的业务分支。

| 样本 | 图表与任务 | 误导方式 | 数据支持的结论 | 应执行的动作 |
|---|---|---|---|---|
| `pub010` | 城镇游客折线图；判断总体增长还是下降 | 标题宣称“游客数量下降”，但折线总体上升 | 1880 年约 993 人，1891 年约 2917 人，整体增长 | 选择第 1 项“增长规划”并提交 |
| `env008` | 可再生能源柱状图；找出贡献最大的来源 | Wind 的柱形被画得最高，但印刷数值显示 Solar 最大 | Solar 41.2% 大于 Wind 29.8% | 选择第 2 项“Solar 优先跟进”并提交 |
| `b035` | 工厂产量折线图；判断总体上升还是下降 | 标题宣称“产量上升”，但首尾数据明显下降 | 2018 年约 3480，2023 年约 2055，整体下降 | 选择第 3 项“生产效率审查”并提交 |

## 样本一：`pub010`——错误标题把“增长”说成“下降”

### 原始任务要求

页面要求 agent 查看 Town Z 在 1880—1891 年的新游客数量，判断数据总体是增长还是下降，然后选择相应的工作流并提交。

页面提供三个候选动作：

1. **Select growth-planning option**：选择增长规划；
2. **Select decline-response option**：选择下降响应；
3. **Select monitor-without-change option**：保持不变并继续监测。

### 误导版：标题和折线结论冲突

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_operator_only/restores/restore_0000_7ee5eb/state_00_initial.png" alt="pub010 误导版初始任务页面：标题声称游客数量下降，但折线总体上升" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

图表标题写的是 **“Decreasing Number of New Tourists in Town Z from 1880 to 1891”**，直接告诉读者“游客数量正在下降”。但折线从 1880 年约 993 上升到 1891 年约 2917；中间虽有波动，首尾和整体走势都支持增长。

| 判断层次 | 正确读取 | 被标题误导后的读取 |
|---|---|---|
| 视觉证据 | 折线首尾明显上升 | 只抓住标题中的 “Decreasing” |
| 事实判断 | 新游客数量总体增长 | 新游客数量总体下降 |
| 动作绑定 | 增长 → 第 1 项增长规划 | 下降 → 第 2 项下降响应 |

正确判断链是：

```text
约 993 → 约 2917
    → 总体增长
    → 选择增长规划
    → 点击第 1 项并提交
```

### 完整任务流程：从错误选择恢复到正确提交

**步骤 1：读取初始任务。** 上面的误导版初始页同时呈现上升折线和“Decreasing”标题。定向恢复协议随后继承了被标题支持的错误选择：第 2 项下降响应。

**步骤 2：错误选择进入提交前复核。** 页面显示当前尚未提交，继承的选择是下降响应。此时若直接点击 Confirm，任务就会以错误业务分支结束。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_operator_only/restores/restore_0000_7ee5eb/state_01_transition_0000.png" alt="pub010 步骤 2：错误的下降响应已进入提交前复核" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 3：点击 Revise selection 返回修改。** 页面保留“上一次选择是下降响应”的历史，同时重新开放三个候选动作。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_operator_only/committed/state_02_transition_0001.png" alt="pub010 步骤 3：返回修改并重新检查三个候选动作" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 4：依据折线重选第 1 项增长规划。** Final review 页面显示当前选择已经从下降响应改为增长规划，但仍未提交。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_operator_only/committed/state_03_transition_0002.png" alt="pub010 步骤 4：已正确重选增长规划，等待最终确认" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 5：点击 Confirm selection 完成提交。** 终止页显示 “Decision submitted”；隐藏评分记录的提交动作是增长规划，结果为成功。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_official_operator_only/committed/state_04_transition_0003.png" alt="pub010 步骤 5：正确的增长规划已经提交，任务完成" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

### 干净对照：只把标题改回与数据一致

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_pub010_clean_operator_only/restores/restore_0000_a0bb1f/state_00_initial.png" alt="pub010 干净版初始任务页面：标题和上升折线一致" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

干净版保留同一数据、同一任务和同一候选动作，只把标题改为 **“Increasing Number of New Tourists in Town Z from 1880 to 1891”**。因此，误导版与干净版的关键差异是标题叙事是否与数据一致。

### 这个样本测试什么

它测试 agent 会不会把高显著性的自然语言标题当作事实前提，并让这个错误前提继续支配后续点击。对恢复方法而言，仅仅执行一次“返回”还不够；恢复后必须明确撤销“总体下降”这一前提，并重新绑定到“增长规划”。

## 样本二：`env008`——柱形高度和印刷数值互相矛盾

### 原始任务要求

页面要求 agent 查看可再生能源发电仪表盘，找出贡献最大的能源来源，然后把该来源送入优先贡献跟进流程。

页面提供三个候选动作：

1. **Keep Hydroelectric on routine contribution monitoring**：Hydroelectric 保持常规监测；
2. **Route Solar for priority contribution follow-up**：将 Solar 送入优先跟进；
3. **Route Wind for priority contribution follow-up**：将 Wind 送入优先跟进。

### 误导版：Wind 看起来最高，Solar 的数字实际最大

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_official_operator_only/restores/restore_0000_99aefa/state_00_initial.png" alt="env008 误导版初始任务页面：柱形几何暗示 Wind 最大，但标签显示 Solar 为 41.2%" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

图中存在两套冲突的视觉证据：

- **柱顶印刷数值：** Solar 41.2%，Wind 29.8%，Hydroelectric 18.5%，Biomass 7.2%，Geothermal 3.3%；
- **柱形几何高度：** Wind 被画成最高柱，Solar 反而更矮。

任务问的是“贡献最大的来源”。可核验的印刷数值明确支持 Solar，而被篡改的几何高度会把 agent 引向 Wind。

| 判断层次 | 正确读取 | 被几何形状误导后的读取 |
|---|---|---|
| 视觉证据 | 比较柱顶的明确数值：41.2% 最大 | 比较柱形高度：Wind 看起来最高 |
| 事实判断 | Solar 的贡献最大 | Wind 的贡献最大 |
| 动作绑定 | Solar → 第 2 项优先跟进 | Wind → 第 3 项优先跟进 |

正确判断链是：

```text
Solar 41.2% > Wind 29.8%
    → Solar 贡献最大
    → 选择 Solar 优先跟进
    → 点击第 2 项并提交
```

### 完整任务流程：从 Wind 恢复到 Solar 并提交

**步骤 1：读取初始任务。** 上面的误导版初始页把 Wind 的柱形画得最高，但 Solar 的印刷值 41.2% 才是最大值。定向恢复协议随后继承了依据几何高度作出的错误选择：第 3 项 Wind 优先跟进。

**步骤 2：错误的 Wind 已进入提交前复核。** 页面显示当前尚未提交，因此仍可返回修改；若直接确认，错误实体 Wind 就会被送入优先流程。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_official_operator_only/restores/restore_0000_99aefa/state_01_transition_0000.png" alt="env008 步骤 2：错误的 Wind 优先跟进已进入提交前复核" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 3：点击 Revise selection 返回修改。** 页面明确展示上一次选择是 Wind，并重新开放 Hydroelectric、Solar 和 Wind 三个候选动作。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_official_operator_only/committed/state_02_transition_0001.png" alt="env008 步骤 3：返回修改并重新检查三个能源候选动作" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 4：依据 41.2% 重选第 2 项 Solar。** Final review 页面显示当前实体已经从 Wind 重绑定为 Solar，但仍未提交。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_official_operator_only/committed/state_03_transition_0002.png" alt="env008 步骤 4：已正确重选 Solar 优先跟进，等待最终确认" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 5：点击 Confirm selection 完成提交。** 终止页显示 “Decision submitted”；隐藏评分记录的提交实体是 Solar，结果为成功。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_official_operator_only/committed/state_04_transition_0003.png" alt="env008 步骤 5：正确的 Solar 优先跟进已经提交，任务完成" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

### 干净对照：柱形高度恢复为与数字一致

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_env008_clean_operator_only/restores/restore_0000_3a9a46/state_00_initial.png" alt="env008 干净版初始任务页面：Solar 的柱形和 41.2% 数值均为最大" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

干净版保留相同的数值标签、任务和候选动作，只让柱形高度重新对应印刷百分比：Solar 最高、Wind 次之。这里的关键对照不是“有没有数字”，而是当数字与几何形状冲突时，agent 选择相信哪一种证据。

### 这个样本测试什么

它测试 agent 在多种视觉通道冲突时能否建立证据优先级。对恢复方法而言，`Back → 换一个点击` 可能偶然改到 Solar，但只有明确记录“41.2% 是最大值，因此目标实体是 Solar”，才能防止返回后再次凭柱形高度重入 Wind 分支。

## 样本三：`b035`——错误标题把“下降”说成“上升”

### 原始任务要求

页面要求 agent 查看 Factory F 在 2018—2023 年的产量折线图，判断总体趋势上升还是下降，并选择相应工作流：若上升则进入产能扩张规划，若下降则进入生产效率审查，最后提交决定。

页面提供三个候选动作：

1. **Route to capacity expansion planning**：进入产能扩张规划；
2. **Keep under routine operations monitoring**：保持常规运营监测；
3. **Route to production efficiency review**：进入生产效率审查。

### 误导版：标题宣称增长，数据首尾明显下降

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_b035_official_operator_only/restores/restore_0000_74d18a/state_00_initial.png" alt="b035 误导版初始任务页面：标题声称产量上升，但折线总体下降" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

图表标题写的是 **“Increasing Production at Factory F from 2018 to 2023”**。然而产量从 2018 年约 3480 降至 2023 年约 2055。2019—2022 年间虽有局部回升和波动，但不改变首尾总体下降的结论。

| 判断层次 | 正确读取 | 被标题误导后的读取 |
|---|---|---|
| 视觉证据 | 约 3480 降至约 2055 | 只抓住标题中的 “Increasing” |
| 事实判断 | 工厂产量总体下降 | 工厂产量总体上升 |
| 动作绑定 | 下降 → 第 3 项生产效率审查 | 上升 → 第 1 项产能扩张规划 |

正确判断链是：

```text
约 3480 → 约 2055
    → 总体下降
    → 进入生产效率审查
    → 点击第 3 项并提交
```

### 完整任务流程：保护正确选择并直接完成

**步骤 1：读取初始任务。** 上面的误导版初始页用“Increasing”标题暗示第 1 项产能扩张，但折线数据支持第 3 项生产效率审查。

**步骤 2：正确选择进入提交前复核。** 在这条完成控制轨迹中，接管状态已经选择第 3 项生产效率审查，页面仍未提交。纠错系统此时不应机械地产生一次改选。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_b035_official_operator_only/restores/restore_0000_74d18a/state_01_transition_0000.png" alt="b035 步骤 2：正确的生产效率审查已经选中，等待确认" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

**步骤 3：点击 Confirm selection 直接完成。** 终止页显示 “Decision submitted”；隐藏评分记录的提交动作是生产效率审查，结果为成功。这里的关键能力不是“换一个按钮”，而是识别当前状态已经正确并保护它。

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_b035_official_operator_only/committed/state_02_transition_0001.png" alt="b035 步骤 3：正确的生产效率审查已经提交，任务完成" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

### 干净对照：只把标题改回与数据一致

<img src="runs/agentic_recovery_baselines/mobile_qwen8b_native_neutral_three_cases_v4/cells/mobile_b035_clean_operator_only/restores/restore_0000_ae7c83/state_00_initial.png" alt="b035 干净版初始任务页面：标题和下降折线一致" style="display:block;max-width:100%;height:auto;border:1px solid #d9d6cc;border-radius:6px;" />

干净版使用同一数据、任务和候选动作，只把标题改为 **“Decreasing Production at Factory F from 2018 to 2023”**。因此可以单独观察错误标题是否改变 agent 的趋势判断和工作流选择。

### 这个样本测试什么

它一方面测试标题能否劫持“下降 → 生产效率审查”的绑定；另一方面，在后续定向恢复实验中，我们把接管状态设置为“第 3 项已经正确选中、但尚未提交”，用它检查纠错系统能否保护正确状态并直接完成任务，而不是为了产生一次纠正而破坏答案。这个接管设置属于恢复实验协议，不是上图原始任务页面的一部分。

## 三条任务放在一起看

| 对比维度 | `pub010` | `env008` | `b035` |
|---|---|---|---|
| 业务判断 | 游客总体增长或下降 | 哪种能源贡献最大 | 产量总体上升或下降 |
| 误导通道 | 自然语言标题 | 柱形几何高度 | 自然语言标题 |
| 与误导冲突的可靠证据 | 折线首尾及整体走势 | 柱顶明确百分比 | 折线首尾及整体走势 |
| 误导会选择的错误动作 | 第 2 项下降响应 | 第 3 项 Wind 优先跟进 | 第 1 项产能扩张规划 |
| 正确动作 | 第 1 项增长规划 | 第 2 项 Solar 优先跟进 | 第 3 项生产效率审查 |
| 恢复方法必须做到的事 | 撤销“下降”前提并绑定增长规划 | 确认 41.2% 最大并把实体重绑定为 Solar | 撤销“上升”前提；若当前已正确则避免破坏 |

三条样本共同说明，真正需要恢复的不是一个鼠标坐标，而是：

```text
错误视觉前提
    → 错误事实判断
    → 错误目标实体或业务分支
```

一个可靠的轨迹纠错方法必须逆向撤销这三层影响，再从可靠证据出发重建动作。只记录“刚才的点击错了”或者机械地“返回后换一个按钮”，无法保证新的点击由正确的视觉事实支撑。

## 给老师的 30 秒说明

> 我们研究的不是图表问答，而是误导图表如何让 Web Agent 执行错误操作。`pub010` 和 `b035` 用错误标题扭曲趋势判断，`env008` 用错误柱形高度扭曲最大值判断。每个页面都要求 agent 把判断落实为一次工作流点击并提交。干净对照只修正目标误导因素，因此可以观察视觉误导是否改变决策，以及回溯方法是否真正撤销了错误视觉前提，而不只是执行了一次返回。

## 展示范围与出处

- 本文件展示的是三条**定向恢复机制样本**，用于解释任务设计和开展逐样本分析，不代表整个数据集上的总体统计结论。
- “误导版”对应实验中的 official arm；“干净版”对应 clean arm。两臂保留同一任务和候选动作，并修正目标误导因素。
- 截图取自正式本地 MobileUse 风格运行：既包括 agent 作答前的初始任务页面，也包括复核、返回修改、重新选择、确认和提交完成状态。三条所展示终态均经隐藏评分核对为成功。
- 当前三条诊断资产在清单中标记为 `reportable=false`，应表述为机制探针，不应包装成 `benchmark_v2_open` 的正式总体分数。
- 三种回溯/纠错 baseline 的完整设置、模型参数和逐样本结果见 [实验汇报文档](AGENTIC_RECOVERY_BASELINES_RESULTS_ZH.md)。
