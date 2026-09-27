# 执行与核对命令

工作目录：`D:/ths_Viswork`。凭据只通过进程环境传入，本文不记录密钥。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe -m pytest research/obc140_20260923/terra140_native_zh_20260924/test_batch.py research/obc140_20260923/terra140_native_zh_20260924/test_native.py research/obc140_20260923/tests_panel.py research/obc140_20260923/tests_catalog.py research/obc140_20260923/tests_viewer.py -q --junitxml=research/obc140_20260923/terra140_native_zh_20260924/offline_tests.xml
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/batch_runner.py --prepare-only
# 下面两个命令需要已获授权的 MODEL_API_KEY 进程环境变量。
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/batch_runner.py --resume --limit 1
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/batch_runner.py --resume
# 以下完全离线；prepare 只分配翻译输入，实际中文由 Codex 写入 outbox。
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/native_zh.py prepare
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/native_zh.py status
& D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_20260923/terra140_native_zh_20260924/make_view.py --browser-check
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/finalize_summary.py
```

命令列出预定顺序；真实完成状态以 run/run_state.json、budget.json、测试结果和最终报告为准。不可凭本文件声称所有命令已成功执行。遇未知请求结果、服务或预算阻塞，不使用这些命令绕过停止条件。

## 收尾命令（全部不调用 API）

队列和原生翻译结束后，按以下顺序收尾。原生翻译输入准备在本轮实际由 `translation_watch.py` 单进程执行，不应再同时启动另一个 prepare 写入者。

```powershell
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/collect_semantic_notes.py
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/audit_failures.py
& D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe research/obc140_20260923/terra140_native_zh_20260924/make_view.py --browser-check
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/finalize_summary.py
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/verify_delivery.py
& D:/anaconda/python.exe research/obc140_20260923/terra140_native_zh_20260924/package_delivery.py
```

已存在的归档不会覆盖；不要为重打包删除旧归档，应另行版本化。展示用浏览器点击只检查本地材料，不是被测 Agent 的网页任务操作。
