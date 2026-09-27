# b001 反问驱动小测试

本目录独立于旧 140 条输出。`PLAN.md` 是执行范围，`config.json` 是有界调用配置。

正常执行顺序为：继承旧公开输入／单链 → 模型提出三个反问 → 模型依据实际反问生成新候选或说明未形成替代 → 对新旧候选独立核验 → 记录规则状态。最多三个逻辑调用，不进行浏览器选择／提交。

## 工件

- `run/seed_input.json`：实际继承的公开任务、提案和单链，未包含旧核验结论。
- `run/counterquestions/round_001/`：反问请求、完整图像和原始响应。
- `run/competitors/round_001/`：实际接收反问的候选生成请求和原始响应。
- `run/verification/round_001/`：新旧候选的核验请求与结果。
- `run/result.json`：问题到候选的映射、规范化链、规则状态、阶段状态和成本。
- `run/budget.json`：含失败和重试的全量请求尝试账本，费用是估算。
- `run/runtime.json`、`run/runtime_source/`：实际执行源与原始输入来源。
- `prepared/`：运行前离线准备，不代表真实模型运行。
- `tests/`、`reviews/`：离线检查与同家族暂定审查，不是答案人工确认。
- `REPORT_ZH.md` 是中文说明；最终阅读入口是 `B001_COUNTERQUESTION_REVIEW_v2.html`，可独立离线打开。初版 `B001_COUNTERQUESTION_REVIEW.html` 因原尺寸图像越界已由 v2 改善，原版及初次检查保留作记录；这次只改显示尺寸与换行，不改原图字节或模型输出。

## 实际命令入口

解释器：`D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe`。

```powershell
# 默认只做离线准备；已存在目录不会覆盖。
& research/competing_rules_20260923/.venv/Scripts/python.exe research/counterquestion_b001_20260925/run_diagnostic.py --output research/counterquestion_b001_20260925/prepared
# 真调用前需本轮授权、审查和进程环境中的 MODEL_API_KEY；不在文件中保存密钥。
& research/competing_rules_20260923/.venv/Scripts/python.exe research/counterquestion_b001_20260925/run_diagnostic.py --live
```

这是已使用样本、继承给定解释状态的开发诊断，不能视为独立新任务、反问的因果消融或实际 GUI 成功率。即使产生不同选项，也不自动视为纠正了错误；即使结构通过，也不代表语义成立。中文仅为阅读说明，英文原响应保留。
