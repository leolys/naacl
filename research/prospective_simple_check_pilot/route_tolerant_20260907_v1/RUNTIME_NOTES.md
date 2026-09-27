# 运行后记录勘误（不回写旧工件）

审查指出的两处记录问题：

1. `live_panel_02/runtime.json` 的 git_head 为字面字符串 `HEAD`，**不是有效提交 ID**。保存函数只读取 `git rev-parse HEAD` 的 stdout，未检查退出状态。此次不能据该字段宣称 Git 提交身份或 clean worktree；版本依据是运行时保存的 `executed_sources/`，以及实际快照之间的 SOURCE_CHANGES.patch。旧 runtime.json 原样保留。本轮不补写 commit/hash，不据当前代码伪造旧版本身份。
2. `MODEL_CONFIG_scheduler_fix.json` 的 `cost_planning.note` 仍写旧余额 `$49.9772`，是说明文字未同步。实际字段 `M_strong.money_cap_usd` 为 `$49.824904`；`live_panel_02/pre_panel_cost_estimate.json` 记录的比较上限也是 `$49.824904`，执行使用的数值并未采用旧说明。本说明纠正文字歧义，不覆盖原配置快照、不释放费用预留。

这两处不能用“测试通过”抹去。它们不改变已记录的 3 个正确 checkpoint、9 次真实提交、HTTP 429 或预算累计，但限制了可声称的版本身份精度。原数据集标签的来源由已有 spec 提供，本轮没有独立重标注或外部验证；结果仅按原评分口径报告。
