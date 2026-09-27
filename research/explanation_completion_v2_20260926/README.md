# 先看哪里

先读最终版 CORRECTION_FINAL_ZH.md 或由其生成的 CORRECTION_FINAL_ZH.html。它们说明具体 C、条件推导、当前规则适用性之间的区别，明确区分旧结果、协议修改和虚构接口测试。CORRECTION_ZH.md/html 是保留的前序说明。

新版本只在本目录实现。旧 explanation_completion_20260925 保持原样，不能把原三例结果视为已用新协议核验。

## 执行记录

工作目录：D:/ths_Viswork/research/explanation_completion_v2_20260926。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest tests -q --junitxml=tests/offline_receipt_01.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' workflow.py --prepare --output prepared_v2
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' offline_demo.py --output mock_route_demo
```

工作目录改为 D:/ths_Viswork 后的新旧联合测试：

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/explanation_completion_20260925/tests research/explanation_completion_v2_20260926/tests --import-mode=importlib -q --junitxml=research/explanation_completion_v2_20260926/tests/offline_receipt_combined.xml
```

以上实际完成：新测试 34，通过；新旧共 68，通过；3 条继承依赖 DeprecationWarning。prepare 为 0 请求；mock 为 3 个虚构阶段、0 请求。各输出拒绝覆盖；若仅做离线再现须用新子目录名。

本次未调用任何被测模型服务；config.json 的模型别名仅用于未来获授权后的请求预览。没有凭据、下载、远程/GPU或业务提交。实际 pipeline 仍需要未来独立授权和 provider 接入，不能把一个已有 API token 当作本轮新预算。

## 最终复核后目录

审查发现核验上下文仍携带生成器 claim_kind；最终 workflow.py 剥离该字段，增加回归断言。再次执行联合测试，结果 68 passed，回执为 tests/offline_receipt_final.xml；没有覆盖前序测试回执。

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' workflow.py --prepare --output prepared_final
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' offline_demo.py --output mock_route_demo_final
```

以上是实际执行且完成的最终准备/模拟命令；旧 prepared_v2 和 mock_route_demo 留作前序快照，不是最终接口。审查为同族暂定工程 PASS，非模型能力结论。
