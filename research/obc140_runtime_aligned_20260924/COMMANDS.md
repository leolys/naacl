# 本轮执行入口与命令记录

工作目录：`D:/ths_Viswork`。解释器：`research/competing_rules_20260923/.venv/Scripts/python.exe`。以下不包含密钥；密钥仅在实际执行进程的环境变量中提供。

## 已完成的运行前步骤

```powershell
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/prepare.py
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/runner.py prepare
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& research/competing_rules_20260923/.venv/Scripts/python.exe -m pytest research/obc140_runtime_aligned_20260924/tests -q --junitxml=research/obc140_runtime_aligned_20260924/offline_tests_final_pre_live.xml
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/runner.py mock --output research/obc140_runtime_aligned_20260924/mock_post_review
```

最终运行前回归 170 项通过；mock 是合成结构数据，不是真模型结果。早期测试失败和修复后的测试回执分开保留，没有覆盖成一次全绿历史。

## 真实请求

```powershell
# MODEL_API_KEY 只通过进程环境变量提供，此处不记录其值。
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/runner.py live --sanity --confirm-budget 20 450
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/check_live_requests.py --sanity
# 仅在三条实际请求审查通过后继续；同一预算账本，不重发终态失败。
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/runner.py live --resume --confirm-budget 20 450
```

第一条真实运行固定 b001、pub003、env008，已完成 9 次请求。后续实际完成状态以 `run/summary.json`、逐次 attempt 回执和最终报告为准；上述完整续跑命令是本轮批准的执行入口，不凭命令列表宣称执行完成。

## 离线汇总和展示入口

```powershell
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/check_live_requests.py
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/native_zh.py status
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/finalize.py
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/make_view.py --browser-check
```

本文件记录入口，不代替相应命令的结果回执。最终执行检查的实际输出另存 JSON/XML；中文由本地 Codex 翻译，不调用 APIYI 翻译服务。

## 全量结束后的实际检查

真实队列已结束，140 条均已处理，共 416 次请求尝试，估算 12.121808 美元；不是实际账单。未对无效或失败结果做质量重试，没有剩余待运行任务。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& research/competing_rules_20260923/.venv/Scripts/python.exe -m pytest research/obc140_runtime_aligned_20260924/tests -q --junitxml=research/obc140_runtime_aligned_20260924/offline_tests_final_delivery.xml
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/check_live_requests.py
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/native_zh.py status
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/make_view.py --browser-check
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/check_note_isolation.py
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/finalize.py
```

实际结果：172 项测试通过；416 个真实请求与冻结输入／源码一致；140 条中文齐全、待译 0；140 条离线显示通过、无脚本错误和外部网络请求；新旧人工笔记隔离通过；846 个原来源／旧工件未改动。以上均是工程检查，不是答案正确率。

## 交付归档入口

```powershell
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/archive_render_review.py --final
& research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_runtime_aligned_20260924/package_artifacts.py
```

最终独立展示审查见 `OBC140_TERRA_ZH_REVIEW.html.review.json`；归档结果以 `PACKAGE_CHECK.json` 为准。打包会拒绝覆盖已有同名 ZIP。上述入口本身不表示其已经成功，须结合这些回执查看。交付后不自动续跑 API。

首次打包在创建 ZIP 前被密钥样式扫描停止。检查确认是普通英文 `task-...` 中的词尾 `sk-...` 被误识别；扫描器补充 token 起始边界，并检查仍会拦截独立 key／Bearer 样式。没有移除或改写任何模型内容，也没有因该离线问题重发模型请求。
