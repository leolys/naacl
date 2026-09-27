# 请求可靠性代码复核（一次，有界）

审查者：已有 `/root/panel_stop_audit` sub-agent；复用上下文、同系列代理、只读工程复核，不是独立外部研究审查，不给研究结论评级。禁止它调用推理、API 或 GPU，禁止修改文件或扩大任务。没有为获得 PASS 再发起第二轮。

## 发给审查者的任务

沿用本项目此前要求的对抗审查，做一次有界、只读的代码复核（不是新研究结论审查）。只检查新增 transport retry 的可靠性边界，禁止推理/API/GPU调用、修改文件或扩展任务。直接读 research/prospective_simple_check_pilot 下 api_backend.py、panel.py、test_api_retry.py、harness.py，以及 retry_reliability_20260907_v1/README.md、RETRY_POLICY.json、unit_tests.log；browser_probe_01/result.json 若存在也读取。检查每次重试是否计费/计数、是否保持同一消息和图像、仅临时运输错误重试、Retry-After与预算停止、是否会重复业务提交或悄悄换模型，以及有效回复是否被重采样挑结果。请只返回具体错误/风险、证据行号和工程覆盖盲点；最多800字，不检查其他实验或论文，不新建门禁，缺证据写未知。只需这一轮，不追求PASS。

## 返回意见（保留原意和原审查行号）

1. `429/5xx` 是否永久仅靠少量精确 `error.type/code` 判断；非标准字段、字符串错误或其他供应商额度码会被当作临时故障重试，最多四次。api_backend.py:97,129,367；test_api_retry.py:135 只覆盖 insufficient_quota。
2. 失败后先等待、下一轮才检查预算，已知没有余额仍会空等 10–60 秒。api_backend.py:301,321；unit_tests.log:21。首次派发前金额检查失败时 `last=None`，停止原因泛化为 non_retryable_failure：api_backend.py:340。
3. transport 不按内容质量重采样，但 harness.py:60,73 对 invalid 动作仍会发下一次逻辑请求，因此“不挑结果”不能泛化到完整 actor 循环。
4. 单测验证同一 Python payload 和图像 data URL；实际 HTTP body 字节一致性、网关是否路由同一权重未知。api_backend.py:295,375。
5. 审查读取时 browser_probe_01/result.json 不存在，不能确认恰好一次业务提交的浏览器证据；仅能看到 harness.py:146 的 max_attempts=1 和 91 项单元/mock 测试。

## 主代理处理与证据时间差

- 接受第 1、3、4 项为明确边界，写入 README。不猜测网关未公开的错误格式，不新增模型兜底，不改变原 actor 对 invalid 的处理。请求相同不等于已验证内部模型相同。
- 第 2 项做最小修正：金额/接口调用预留不足在等待前检查；首次派发前的预算失败也正确标为 budget_exhausted_before_another_dispatch。追加 1 项针对首请求无余额的测试，并增强已有金额不足测试对空等待的断言。共享模型 callback 仍在派发前检查，该项可能空等但不会超额发送，明确记录而不扩展预算框架。
- 第 5 项是读取时序限制，不是浏览器失败。主代理随后拿到 browser_probe_01 退出码 0 和 result.json；修正后在新目录 browser_probe_02 再跑一次，亦退出码 0，每次 2 次模拟请求、1 次实际 localhost POST、5 次 transition。这不是审查者后来亲自验证的结论，不能倒写为审查已确认。
- 最终单元测试 92 项通过，见 unit_tests_after_review.log；最终浏览器源码副本见 browser_probe_02/executed_sources。未启动真实模型实验。本文件不替代原研究面板的 EXPERIMENT_AUDIT，不修改其结论。
