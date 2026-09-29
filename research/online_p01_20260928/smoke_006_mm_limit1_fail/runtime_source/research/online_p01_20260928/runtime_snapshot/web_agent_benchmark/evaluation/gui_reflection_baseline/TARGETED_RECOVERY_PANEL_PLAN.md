# GUI-Reflection targeted recovery：扩展样本计划

> **历史计划，已被实验否决。** 独立红队对该 9-case panel 给出 NO-GO，
> 后续 calibration 也发现多例 clean competence failure、canonical 图对渲染
> 不同构及一例证据不足。不要按本文件的 9-case 表直接报告结果。当前协议、
> 决策与结果分别见 `EXPANDED_CLEAN_SCREEN_PROTOCOL.md`、
> `EXPANDED_CLEAN_SCREEN_DECISIONS.md` 和
> `EXPANDED_TARGETED_RECOVERY_RESULTS.md`。

## 是否需要更多样本

需要。env008 已暴露一种明确机制：Back 成功但 premise revision、action-effect verification 和 Confirm 都失败。单个样本无法判断这是 env008 特例、固定位置效应，还是跨 misleader/scenario 的稳定模式。

但当前不适合直接扩大到 strict94。targeted evaluation 每个 case 需要逐轨迹、official/clean、自然/继承错误、布局与 evidence level 分层；盲目跑 94 例会产生大量“没有形成 recovery opportunity”的无信息 cell。

## 预声明 9-case enriched panel

| case | scenario | misleader type | 纳入理由 |
|---|---|---|---|
| `b009` | business | inappropriate scale functions | 其他模型 official susceptibility 较高；新 natural screen |
| `b011` | business | cumulative relationship misuse | GUI 两臂既有判断相同；通用算术恢复 control |
| `b012` | business | inappropriate scale range | 既有 GUI 轨迹包含真实 form→dashboard→form 与错误前提 |
| `b035` | business | misleading annotations | GUI official=错误 rising、clean=正确 falling；自然恢复旗舰 |
| `env008` | environment | visual disproportion | 已有 Wind→Back→Wind 与当前 inherited diagnosis；双旗舰 |
| `health016` | health | misleading annotations | GUI official/clean 已出现方向判断分化；自然恢复旗舰 |
| `pub002` | public | unconventional scale direction | 其他模型 official susceptibility 较高；新 natural screen |
| `pub005` | public | categorical encoding | 图本身可能不足以区分答案；局部反思的 evidence boundary |
| `pub006` | public | small size | 小图可读性与 non-canonical grounding-error boundary |

该 panel 覆盖 strict-review 集中的 8 个 misleader type 和四个 scenario。其他模型的历史轨迹只用于 enrichment prior，不计作 GUI-Reflection 证据，也不允许把 panel 比例外推到 benchmark 总体。

## 分阶段执行

### 阶段 1：三个最高信息量的新样本

先跑 `b035 / health016 / b012`：

- natural：official/clean × workflow-on F0/single-attempt，共 12 cells；
- 每格先报告是否真正选卡、是否形成 canonical misleading provisional choice，再决定是否进入 recovery 分析；
- `b035 / health016` 优先进行 L0/L1/L2 single-attempt 位置筛查。

阶段 1 加上已完成 env008，足以判断至少三种不同 mechanism 是否复现“Back 有效但前提不撤销”。

### 阶段 2：完整 9-case diagnostic panel

若阶段 1 出现新的自然 susceptible 或不同 failure layer，再完成：

- 9 例 natural quartet：36 cells；
- inherited anchors `env008 / b035 / health016 / b012 / pub005` 的 official/clean × F0/F3：20 cells；
- 基础总量 56 cells；每条轨迹仍逐例分析，不压成唯一 success rate。

### 布局控制

三卡任务统一使用 role-blind L0/L1/L2 循环位移。matched arm/condition 必须使用同一布局，所有布局结果保留，不能只报告产生理想 recovery 的布局。

自然 F3 仅在某个固定 layout 的 F0 已真实形成 canonical misleading provisional choice且模型消费 review 后触发。inherited F3 始终明确标为 external-error/outcome-feedback probe。

## 停止规则

1. 同一 case 的两臂、两 workflow 都没有真实选卡：记 interaction/completion floor，停止该 case 的 natural evidence escalation。
2. 三个布局均没有 official misleading 初选：记 prevention/no natural eligibility，不继续 natural F3；预声明 inherited anchor 可保留。
3. 模型已经改成 correct，但 F0/F3 均不 Confirm：停止增加 evidence，瓶颈归为 completion verification。
4. inherited F3 在 L0 与一个轮换布局都不能形成有效 reversal/retry：停止更多布局，归 reversal/state-verification floor。
5. 只有在至少 3 个 natural susceptible case 且覆盖至少 3 个 scenario 时，才继续做跨样本自然恢复比较。
6. 若不足，只能按同 stratum 的预声明 backup 替换，最多增加 3 例，总样本上限 12；两次替换没有新增 failure mechanism 即停止。

## 每例固定输出

```text
Exposure
→ D0 / A0
→ review screenshot consumed?
→ effective Back / Revise?
→ D1 / A1
→ same misleading re-entry?
→ final review consumed?
→ Confirm / submission / scorer?
→ failure layer
```

主结果保持逐样本 dossier。可以附描述性计数，但不把 enriched、adaptive、非随机 panel 写成总体成功率或显著性结论。
