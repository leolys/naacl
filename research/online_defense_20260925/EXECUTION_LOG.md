# 执行记录

- 新建 online_defense_20260925，未修改旧运行、原始任务或图表。
- 12 个接口单元测试通过，3 条继承 Flask/itsdangerous 弃用警告。
- 首次离线入口发现 Python 通用模块名 runner 被旧目录遮蔽；恢复新实验目录导入优先级，未消耗模型调用。
- 280 条原任务条件的 GET/公开投影审计已执行；独立工件 asset_check_v1。
- 首次脚本化原浏览器控制发现空 select 的占位文字被显示成非空 value，导致控制误以为必填上下文已填写。保留 browser_check_v1；新投影区分 value/selected_text，并返回浏览器真实校验消息。不改原页面/评分。已发生 5 个浏览器操作计入共享 live_budget.json。
- 以上为启动前记录：当时真实模型尚未运行。工程修复不算模型反思/纠错效果。

## 已执行的后续步骤

- `browser_check_v2`：3 条真实浏览器控制通过，包含原表单真实 POST；合并首个失败控制共 26 次浏览器操作。没有模型调用。
- `prepare_runtime.py`：只读回收两个原缺失资产，建立隔离副本，`asset_check_v2` 的 280 个原页面/图表入口全部可用。旧快照不改。
- `batch_preflight.py`：280 个原 HTTP 表单提交/确认页控制通过，0 模型、0 实际浏览器操作，离线 HTTP 操作另记。
- `runner.py --mode live --output .../live_v1`：固定 12 条完整执行到各自终止条件，94 次 API 请求尝试；5/6 普通分支和 1/6 方法分支真实提交且原评分成功。原结果不替换。
- v1 继承提示中的“公开原文”与精确 JSON 标量类型要求不一致，经审查建立 `prompts_v2.py`。只改类型表述，不改校验、图表或判断逻辑。
- `schema_debug.py`：一次独立 b002 原图接口联调，共用原账本；实际终态以其 `summary.json` 为准，不混入原 12 条结果。
- 回归命令：`python -m pytest --import-mode=importlib research/online_defense_20260925/tests research/explanation_completion_20260925/tests -q`。`offline_tests_v6.xml`：81 通过、3 条继承弃用告警。早期 v4 同名测试收集失败也保留。
- 批量入口审查发现 override 可改费率/预留值；已按通用白名单修复并增加测试。审查通过不构成新的运行授权。
