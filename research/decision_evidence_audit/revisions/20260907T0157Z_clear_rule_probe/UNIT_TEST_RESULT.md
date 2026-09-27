# 单元测试执行记录

实际命令（工作目录为项目根）：

```bash
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest discover -s research/decision_evidence_audit/tests -p 'test_*.py' -v
```

实际终端结果：退出码 0；`Ran 45 tests in 0.736s`；`OK (skipped=3)`。42 项通过，3 项 opt-in 浏览器集成测试未在这次命令中开启。此处是终端结果记录，不冒充逐行重定向的日志；后续报告测试和浏览器正控制另有原始日志。

新增 4 项均通过：默认开发范围不变且新 profile 必须显式选择；三个数据家族与配对不变式/隐藏字段变异隔离；拒绝未知 slug/条件；浏览器启动失败时 24 单元与 6 前缀均保留且零模型/浏览器调用。

原有测试涵盖：中性首次提交拦截、无关按钮不拦截、B0 零核查调用、隐藏信息变异不改变策略请求、B2 无独立图表不替换成带选择表单、B3 裁剪和调用上限、失败计费、真实回执一致性检测、重复提交/未确认区分、恢复状态与截图重算、服务多图传输检查（此处使用测试 backend）。

这批测试没有真实模型请求、没有启动浏览器。测试内的 fake backend 和 MagicMock transition 不属于真实模型/GPU/浏览器消耗，不作为自然错误、纠正能力或工程 POST 成功的证据。
