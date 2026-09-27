# 已执行工程验证（不是效果结论）

## 最终稳定工件与展示验收

- `checks/FINAL_LOCAL_TESTS.xml`：18 passed、1 skipped（Windows无Linux flock；远端开跑前已实测跨进程锁）。
- `captures/final_001`：稳定ZIP SHA、CRC及14328文件SHA核对通过；不使用progress_001。
- `analysis/final_001/INTEGRITY.json`：840结果归属、2232主阶段实际请求、2236总账本事件通过，响应唯一且无孤立响应，图像/公开上下文/版本与worker串用0、缺失证据0。
- `analysis/final_001/SUPPLEMENTAL.json`：306封存文件保持；capture与本地manifest/schedule/config/protocol字节相同；全部请求在原截止前、HTTP200、attempt1，原标签哈希保持。
- `checks/FINAL_RESOURCE_CHECK.json`：只读验收0/2/3三个自有副本正常退出，守卡仅在实际空卡恢复，原GPU7服务身份/环境/监听/health保持。
- `qa_final_002/QA.json`：140任务逐条切换、140张图解码、每条6张版本卡；25种版本×筛选组合、24/116/140面板计数、精确搜索、前后导航均通过。JS错误0、外网请求0、缺图0；桌面和手机无页面横向溢出，宽表仅容器内横向滚动。已实际看过桌面、样本和手机截图。HTML SHA256 `ffd96604043c7f080250f191b850e4371f9e84f46c690abd2e5ab8a201771206`。
- 第一版QA也通过自动检查，但截图发现手机配置名过度折行；保留`review_final_001`/`qa_final_001`，第二版只改显示，不改变模型结果。
- 原审查者独立复算和语义抽查见`FINAL_ADVERSARIAL_REVIEW.md`；这些工程检查不认证全部O/B语义正确，也不等于网页提交测试。

以下为开跑与早期检查的原记录。

- 本地：`PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，使用`research/competing_rules_20260923/.venv/Scripts/python.exe -m pytest test_full.py test_analysis.py -q -p no:cacheprovider --junitxml=checks/LOCAL_TESTS_001.xml`：18 passed，1 skipped（Windows上的Linux flock测试）。
- 内容：140输入哈希/提示原文/schema一致；840排程唯一且同任务同worker、顺序轮转；在线公开字段白名单；独占写不覆盖；四worker账本隔离；已知临时HTTP计数重试；未知传输与内容失败不重试；崩溃窗口从原响应结算而不重发；预算上限；null/失败与正确状态转移、未知用量不冒充0。
- 远端尝试`python -m pytest`报告现有环境没有pytest；未安装/修改环境，没有把它记成被测模型失败。
- 替代远端必要实测：运行`checks/remote_offline_check.py`，8项检查通过：全封存字节、840排程、140公开输入、同worker跨进程互斥、不同worker可并行、锁释放可复用、真实监听socket归属、错误owner拒绝。0模型请求/0安装。原回执在capture `checks/REMOTE_OFFLINE_RESULT.json`。
- 新服务：4组API PID/start_ticks/argv/env/监听socket/health/models检查成功；随后4次真实非图表单图结构控制通过，计入总账本。不能由此推断图表能力。
- 首个运行中capture核对ZIP SHA和所有成员SHA通过；正式汇总拒绝其中实时文件枚举与较晚账本的不同步。保留`captures/progress_001`，不作为最终统计，也不据此改运行器。结束后稳定capture必须重新严格评分、审计和展示QA。
- 对抗审查见`ADVERSARIAL_REVIEW.md`及`OFFLINE_REPORT_REVIEW.md`。开启模型前的3项资源及3项生命周期问题已修；离线逐请求归属、响应唯一/全集、图片/上下文、原评分哈希检查在`integrity_audit.py`，须在正式完整工件上执行后才能声称通过。
