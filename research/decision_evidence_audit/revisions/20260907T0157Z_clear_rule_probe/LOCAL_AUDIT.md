# 本轮增量本地审计

工作区：`/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。未提交文件很多；使用 `git -c safe.directory=... status --short` 读取，未改全局 Git 配置，未提交、清理或覆盖旧结果。保留 AGENTS.md。

本轮修改 `research/decision_evidence_audit/runner.py` 和 `validate_run.py`，新增 `tests/test_clear_rule_probe.py`、`case_report.py`。不改变策略、在线客户端、图表、原始任务或评分映射。

## 资产与原有授权

- 发布数据：`web_agent_benchmark/benchmark_v2_open/splits/{official140,clean140}/`，三个家族 public39/environment35/business47。读取任务表中的实际 figure_path，不用旧机器的 benchmark_v2 路径猜测。
- Agent-safe 本地网页：现有 `safe_shell.py`；原样使用任务/仪表盘/表单/POST/确认页。只含主要路由决策，不冒称原始完整多字段工作流。
- 模型客户端：现有 loopback `LocalQwenServiceBackend`，不使用任何新服务、API key 或外部 API。
- 已有模型：`/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct`；初始只检查、不载入。用户追加共用许可后已载入该权重完成真实运行，没有下载。
- 模型 Python：`/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python`。
- 评测 Python：`/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python`。
- 浏览器：`/tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell`，运行库 `/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu`。

## 信息权限与恢复

所有在线任务仍经过公开字段 allowlist；图表条件和原始 slug 只写到 evaluator，页面使用 dev01/dev02/dev03；公开标签排序不依赖答案。核查者看不到另一图表条件、gold、原数据、隐藏标签或评测者选框。新任务家族不引入新信息入口。

首次提出 Submit Form 时暂停，未产生 POST；四个分支各自重放之前动作，比较恢复状态/截图，然后只执行一次业务提交，核对服务器回执及确认页。未修改原有信息保护、预算、恢复和源文件变化检测。

## 并发工作区变动

第一次 mock 于 02:01:04–02:02:05 UTC 执行。开始快照与结束快照唯一新增差异为 `research/decision_evidence_audit/frozen_panel.py`（不是本轮创建；文件时间 02:02:02 UTC）。已完成 pub010 两条件的 8 条提交后，原有 RuntimeSourceChanged 检查中止剩余 16 条；工件完整保留，不能把它作为通过的全量检查。另有异常清理时 event loop 已关闭的错误被保留，未隐藏。

随后复制该次已保存的 runtime_source_snapshot 到本轮 `execution_source/`，补拷原客户端和服务器源文件，作为执行目录；不修改旧快照，不撤销检测，不碰新出现的文件。第二次从这个独立目录执行同一代码。它只是复用已有源快照以避免并发文件改动，不是新增评测策略或挑选模型结果。

## GPU 占用

初始 GPU 0 上未知 PID 42504 占约 21 GB，同时跨 GPU 1–3。稍后改为未知 PID 56053，占约 14.8 GB，仍跨四卡。进程不在本地 /proc 可见范围，localhost:8045 没有服务。未终止占用者，未尝试其他 GPU，已询问是否属于用户且可共用。最终状态与真实执行结果见 STAGE_REPORT.md。

后续用户明确给出共用 GPU 0 许可；本轮服务绑定 CUDA_VISIBLE_DEVICES=0，日志显示只看到一张 GPU。完成真实运行后只对本轮 TTY 发送 Ctrl-C，服务退出码 130 是主动关闭，不是推理失败；8045 无监听，已有 PID 56053 仍使用 GPU，未被打断。

## 审查后修复与最终执行源

隔离目录在 revisions 之下暴露出旧 source_fingerprint 按绝对路径排除文件的错误。v1 mock 的源码覆盖缺口保留，不能追认通过。随后改为相对 PACKAGE_ROOT 排除运行工件，并给 validator 增加实际执行模块覆盖和同一 task/condition 共用 prefix 的普通一致性检查。最终执行源为 `execution_source_v3/`；最终 mock 和真实 run 都使用此版本，真实 run 保存 33 个源/数据/依赖文件。

结束后只对根目录 case_report.py 补充失败前缀的离线截图/响应展示；没有修改实际运行源、提示词或已有运行记录。生成的真实 HTML 明确记录 offline_reporter_path。
