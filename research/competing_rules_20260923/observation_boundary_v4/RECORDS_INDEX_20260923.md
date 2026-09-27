# 本轮记录入口

本目录展示固定五例的新旧提示**模块诊断**，不是新的执行轨迹或提交结果。运行根目录为 `runs/paired_v4_20260923/`。每个样本下面的 `shared_input` 是两臂共享的实际公开输入，`legacy`／`observation_boundary_v4` 是旧／新提示。

| 样本与原图类型 | 新版生成O/B/C | 新版核验输出 | 新版规则状态 | 两臂输入一致性证据 |
|---|---|---|---|---|
| pub013：地图颜色与图例 | [生成原文](runs/paired_v4_20260923/pub013/observation_boundary_v4/generate/parsed.json) | [核验原文](runs/paired_v4_20260923/pub013/observation_boundary_v4/verify/parsed.json) | [状态](runs/paired_v4_20260923/pub013/observation_boundary_v4/rule_state.json) | [配对](runs/paired_v4_20260923/pub013/paired_input_proof.json) |
| health004：反向纵轴折线图 | [生成原文](runs/paired_v4_20260923/health004/observation_boundary_v4/generate/parsed.json) | [核验原文](runs/paired_v4_20260923/health004/observation_boundary_v4/verify/parsed.json) | [状态](runs/paired_v4_20260923/health004/observation_boundary_v4/rule_state.json) | [配对](runs/paired_v4_20260923/health004/paired_input_proof.json) |
| b046：柱形与均值参考线 | [生成原文](runs/paired_v4_20260923/b046/observation_boundary_v4/generate/parsed.json) | 未获得：[额度拒绝回执](runs/paired_v4_20260923/b046/observation_boundary_v4/verify/response_01.json) | 未更新：[模块结果](runs/paired_v4_20260923/b046/observation_boundary_v4/module_result.json) | [生成输入配对](runs/paired_v4_20260923/b046/paired_input_proof.json) |
| pub031：双纵轴折线图 | 未运行：[前置Actor额度拒绝](runs/paired_v4_20260923/pub031/ordinary_proposal/actor/response_01.json) | 未运行 | 无 | 未形成配对 |
| b001：扇区面积与百分比标注 | 未运行：[前置Actor额度拒绝](runs/paired_v4_20260923/b001/ordinary_proposal/actor/response_01.json) | 未运行 | 无 | 未形成配对 |

若某阶段失败，其对应文件可能不存在，应先看样本的 `module_result.json`，不能以不存在的核验文件当成已运行失败的判断器。

## 每一层分别看什么

- `shared_input/public_input.json`：任务、真实公开历史、选择前状态及普通Actor提案；不是隐藏答案。
- `shared_input/images/`：实际输入图像。`provenance.offline.json` 记录来源；旧三例与原请求中base64图像逐字节核对。
- `generate/request.json`／`verify/request.json`：完整实际发送体，含当次system提示和图像base64；`context.json` 为同一输入的便读形式。
- `generate/response_*.json`／`parsed.json`：原始返回体／解析后的生成内容。没有手工改写O。
- `normalized_candidates.json`：实际送给核验器的候选。链会规范化排序，c1不一定是生成时第一条；按完整内容核对，不按行号猜来源。
- `verify/parsed.json`：模型核验原文；`validated_verification.json`：经过既有结构一致性校验后的结果。
- `rule_state.json`：本次核验生成的规则与证据状态。它没有被本轮后续Actor读取，不能证明持续纠错。
- `attempt_*.json`：各次尝试的HTTP状态、耗时、网关返回model和usage；失败及重试也保留。
- `module_result.json`：推荐、阶段完成情况、调用次数；`submitted=false`。
- `offline_results.json`：全部模块结束后才合入的原标签一致性，不是提交成功率。

同级 `legacy/` 保留本次旧提示的完整配对输出，早先三示例运行仍在项目根 `runs/`，两者不混同。
