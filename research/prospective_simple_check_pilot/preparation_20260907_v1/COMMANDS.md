# 本轮执行记录

工作目录：`/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。

## 离线准备

读取新执行单、内网 API 文档、AGENTS、experiment-plan 及其公共引用；查看既有源码和任务 metadata。只读现有配置，不使用文档中的 key。

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.prepare --output research/prospective_simple_check_pilot/preparation_20260907_v1
```

退出 0：8 入选、52 保守排除、32 计划前缀、96 计划配置；真实调用/浏览器 transition 均为 0。输出目录必须不存在；再运行应换新准备目录，不覆盖本轮 manifest。

准备期原图查看均来自 task row 的 `chart_asset.figure_path`，没有读 source.csv 或 source.html 取答案。首次手工假设 clean 图片仍是 jpeg 导致一次找不到文件；随后按原 row 路径找到 png，未修改资产。系统 Python 缺 PIL 的一次只读导入失败，切换为已有 eval 环境，不安装依赖。

## 单元测试

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation -v
```

15 项通过。然后复用原核心测试：

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.decision_evidence_audit.tests.test_core -v 2>&1 | tee research/prospective_simple_check_pilot/preparation_20260907_v1/unit_test.log
```

日志末尾 `Ran 53 tests in 11.311s / OK`。测试中只有 FakeSession，无内网/付费 API 请求。

## 实际浏览器、非图表 mock

第一次在沙箱内执行同一命令（输出 `mock_browser_01`），未进入任务，账本 0/0。最终仅对已核对命令行的本轮 PID 439783 执行 TERM；退出 143。沙箱内 TERM 曾因进程隔离返回不存在，之后沙箱外精确 PID 停止成功。未删除工件，没有停止任何 GPU/其他作业。

第二次增加 20 秒 browser launch timeout，用工具申请并获准沙箱外本地 CPU 检查，总命令再限 90 秒：

```bash
timeout 90s env PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.mock_browser --output research/prospective_simple_check_pilot/preparation_20260907_v1/mock_browser_02 --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
```

退出 0。20 mock calls、56 实际 transition、8 次 localhost POST；4 流程＋5 分支断言通过，工件 `mock_browser_02/result.json`。只使用临时公开 Route A/B 任务和空白图片，没有使用 8 个新任务进行 agent 测试。

## 未执行

未 GET 内网模型列表，未 POST 真实 API，未启动或复用 Qwen 服务，未下载权重，未改代理/SSH，未使用 GPU。没有新的真实自然 checkpoint 或视觉恢复结果。
