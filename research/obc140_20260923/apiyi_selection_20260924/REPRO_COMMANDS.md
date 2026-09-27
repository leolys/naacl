# 本轮执行入口与复核

这是两个已知开发任务的模型选型，不是 140 任务完成报告。调用凭据仅由运行进程环境提供，不写入命令示例或文件。未经新的批量模型与费用确认，不调用原 140 执行入口。

工作目录：`D:\ths_Viswork\research\obc140_20260923\apiyi_selection_20260924`

实际 Python：`D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe`。以下用 `python` 简记该绝对路径，不使用 Windows Store Python。

## 实际选型请求顺序

```text
python run_selection.py --model gpt-5.6-sol --task b001 --stop-after proposal
# 检查原图、提案、用量后继续，已完成阶段不重复调用。
python run_selection.py --model gpt-5.6-sol --task b001
python run_selection.py --model gpt-5.6-sol --task pub013
python run_selection.py --model gpt-5.6-terra --task b001
python run_selection.py --model gpt-5.6-terra --task pub013
python run_selection.py --model gpt-5.4-mini --task b001
python run_selection.py --model gpt-5.4-mini --task pub013
```

配置、源代码快照及运行身份位于各模型 `runs/<model>/`；完整线上请求、原始响应、HTTP/用量回执位于 `tasks/<task>/<stage>/round_001/`。`record.json` 为各阶段解析结果；中文只存翻译层，英文没有被改写。

每模型预算 8 次，总计至多 24 次；失败不自动重试。目录中的 140 个原始任务槽位仅用于数据来源对齐，只有 `b001`、`pub013` 在调用范围内。

## 无模型调用的复核与展示

```text
python -m pytest ../tests_panel.py ../tests_viewer.py ../tests_catalog.py test_selection.py -q --junitxml=tests_pipeline.xml
python -m pytest test_usage.py -q --junitxml=tests_usage.xml
python analyze_usage.py
python export_pilot_views.py
python browser_check_pilot.py
```

以上均不调用模型。浏览器检查仅验证离线阅读界面，不执行原任务，也不是 GUI Agent 结果。完整执行结果以报告和测试回执为准；本文件列命令不等于声称每条均成功。

测试实际使用首选 `D:\anaconda\python.exe`，并在进程环境设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；不修改现有 Python 环境。第一次虚拟环境默认插件回归长时间无输出，已中断，未产生通过报告。上面的两次实际离线测试分别通过 32 项与 18 项。
