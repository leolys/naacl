# Terra 引用兼容验证工件索引

本轮仅两个已知开发任务，新鲜 API 请求共 8 次；旧响应离线重放共四份、0 次请求。批量未启动。

| 文件 | 内容 |
| --- | --- |
| VALIDATION_REPORT_20260924.md / .html | 结果、保留问题、预算估算与停止边界 |
| PLAN.md | 本轮授权范围及预先固定步骤 |
| citation_adapter.py | 通用任务引用来源分离，图像证据要求不变 |
| run_validation.py | 两任务、Terra、最多 8 次、新独立运行入口 |
| test_citation_adapter.py、tests_citations.xml | 90 项适配与边界单元测试 |
| tests_regression.xml | 含原管线的 118 项联合回归 |
| offline_replay.json | 四份已有核验的新旧校验对照，不是新模型结果 |
| run/config_snapshot.json、runtime.json、runtime_source/ | 实际运行配置和源快照 |
| run/catalog_snapshot.json | 本轮实际两任务清单 |
| run/tasks/b001、run/tasks/pub013 | 原始请求、响应、用量、解析、适配记录与中文 |
| run/budget.json、summary.json、run_state.json | 8 次请求及当前终态；不以目录数算完成量 |
| summarize_run.py、cost_and_comparability.json | 复用既有费用函数；缓存敏感性和真实输入差异 |
| make_view.py、view_provenance.json | 不改模型记录的离线展示，来源字段中性中文标签 |
| TERRA_CITATION_REVIEW.html | 内嵌原图、两任务完整中英解释及状态，单文件可携带 |
| TERRA_CITATION_VALIDATION.zip、PACKAGE_READ_ME.md | 可携带报告、阅览页、原始两任务记录与代码；不是独立推理环境 |
| browser_check.json、view_b001.png、view_pub013.png | 实际离线 Edge 验证，不是 GUI Agent 轨迹 |
| PREDEPLOY_REVIEW.md | 新鲜独立代码审查，同家族暂定通过 |
| POSTRUN_SEMANTIC_REVIEW.md | 原图、生成链、核验、中文逐项复核及语义问题 |
| ../../../.aris/traces/experiment-bridge/2026-09-24_terra_citations/ | 审查完整请求、答复和身份记录 |

## 实际执行与复核命令

工作目录为本目录；模型执行使用本地既有环境 `D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe`。密钥只存在调用进程环境，没有写入文件。测试与离线汇总使用 `D:\anaconda\python.exe`。

```text
python run_validation.py --offline-replay
# 测试时设置进程环境 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest ../tests_panel.py ../tests_viewer.py ../tests_catalog.py test_citation_adapter.py -q --junitxml=tests_regression.xml
# 独立审查通过后，串行执行；首例完成并检查后才执行第二例。
python run_validation.py --task b001
python run_validation.py --task pub013
python summarize_run.py
python make_view.py --browser-check
```

原客户端严格保留未知请求结果不自动重发、终态不重跑策略。`run/` 是新版本，不用于改写 `../apiyi_selection_20260924/runs/`。
