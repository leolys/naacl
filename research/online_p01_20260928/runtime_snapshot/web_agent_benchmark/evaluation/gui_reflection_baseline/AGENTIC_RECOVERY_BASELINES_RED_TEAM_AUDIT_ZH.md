# 三类 Agent 恢复基线：对抗审查记录

日期：2026-09-01  
审查范围：`src_qwen8b_native_neutral_three_cases_v3`、`exact_qwen8b_native_neutral_three_cases_v3`、`mobile_qwen8b_native_neutral_three_cases_v4`。

## 总判定

三组正式实验共 42 个 cell，机械执行与工件完整性均无阻断。审查只认可方法内部、逐任务的因果比较，不认可跨方法总成功率排名。

## 通用检查

| 检查项 | 结论 |
|---|---|
| cell 完整性 | 42/42 completed，0 failed |
| 模型调用与成本 | 282 calls、854,562 tokens，与三份 aggregate 相加一致 |
| 图像 | 共 802 张模型输入图；原始尺寸均 1280×960；请求与服务回执数量、顺序、尺寸、协议一致 |
| 多图协议 | `2.0-native-multi-image`；1/2/16 图 preflight 通过 |
| 提示泄漏 | 未发现 hidden truth、arm、scorer、canonical action 等 runner-only 信息 |
| 恢复 | fresh initial 状态可复现；重复前缀与 cached node 匹配 |
| 最终评分 | 每格仅在 fresh final replay 完整提交后调用一次 canonical scorer |

## Speculative Rollback Correction 风格

- 6/6 cell 完整；33 calls、58,004 tokens、44 transitions，其中 21 replay。
- 51 张输入图的协议与尺寸一致。
- 4 个真实错误格的检测和首错定位均为 4/4。
- 2 个正确控制只有 1/2 被正确接受；`b035` 误导标题格发生 false reject。
- `pub010` 误导格中，teacher corrector 已选对 growth，student continuation 又改成 neutral 并未提交，构成“纠正正确但不持久”的干净机制例。
- `env008` 两臂在 teacher review 前已经由 student 自主成功，不能归因为 teacher recovery。
- reviewer 审查的是已执行 GUI 动作和状态；`K=3` 表示 operator proposal 预算，未执行的非法 proposal 不在 executed action history 中。

## ExACT 风格

- 12/12 cell 完整；125 calls、571,178 tokens、416 transitions，其中 415 replay。
- 551 张输入图的协议、尺寸和候选顺序一致。
- 六个 task×arm pair 的 contrast/highest `search_tree.json` 逐字段完全相同。
- 两模式的 value call 数、prompt、逐帧 SHA、raw/parsed output 和 metadata 完全相同。
- 每格都探索 3 个可见实体，正确提交路径都存在；“没搜到正确路径”为 0/6。
- highest-value 6/6 成功，但 value 并不完美，存在全 0 tie 和未提交候选高分。
- contrast 在 4/6 改 leaf，四次全部把成功改成失败；另外 2/6 保持 `env008` 的 Solar 正确候选。
- 因此可把四个回归直接归因于新增 contrast selection，而不是搜索随机性、截图裁缩或树差异。

## MobileUse 风格

- 24/24 cell 完整、提交且成功；124 calls、225,380 tokens、160 transitions，其中 104 replay。
- 200 张输入图一致：68 个 operator 单图调用、42 个 Action 双图调用、8 个 Trajectory 四图调用，Global 为 4 个三图和 2 个双图调用。
- 每个 task×arm 的四种模式最终物理 prefix 完全相同。
- operator-only 与 action-reflector 的 operator prompt、截图和 raw output 在 reflector 介入前逐项一致；trajectory 与 full 的共有调用也一致，full 只多 Global。
- Action 共 42 次，全部接受，0 rollback、0 semantic concern。
- Trajectory 共 8 次，全部置 `needs_correction=true`；`b035` 首步提交后未触发 Trajectory。
- Global 共 6 次，全部 allow，0 block、0 corrective action。
- 三层 reflector 的边际成功贡献为 0；完整模式 token 是 operator-only 的约 4.37 倍。
- `pub010` 误导格的 Trajectory 被错误标题诱导，产生“改回 decline”的有害反馈；后续 proposal 确实尝试执行，但被 one-reversal UI 与共享 executor 零执行。成功不能归因于 reflection。

## 被排除的 run

以下工件只保留为工程审计，不进入正式结果：

- 低分辨率 contact sheet 版本；
- 提示词显式暗示图表冲突或偏好标签/数值的版本；
- 把不可见 choose 转换成 finish 的旧 Mobile 版本；
- 中断或含 executor 异常的 `mobile_qwen8b_native_neutral_three_cases_v3`；
- 所有单格 smoke。

## 允许与不允许的论文表述

允许：

- “在 4 个真实继承错误格上，SRC 风格 reviewer 4/4 检测并定位首错，但一次纠正未必持久。”
- “在 6 个固定格中，ExACT 风格搜索找到正确路径；额外 contrast 4 次覆盖正确候选并造成 4 次回归。”
- “MobileUse 风格 reflector 没有产生 outcome 增益，且 `pub010` 暴露有害轨迹反思，只是被界面护栏遮蔽。”

不允许：

- 把三个 adapter 称为官方方法复现或官方 checkpoint 结果；
- 把不同预算的三种方法按总成功率排名；
- 把 42 controller cell 当成 42 个独立任务；
- 把任意正确 alias 的出现当作视觉前提恢复；
- 声称误导可视化专门导致 ExACT 或 Mobile 最终失败；两者的 official/clean 二元结果在各任务内相同；
- 把 Mobile 24/24 写成三层 reflector 解决了任务。
