# 实际执行命令

工作目录为项目根目录；未调用真实模型、付费 API 或 GPU。Python / Chromium 沿用已有环境，不安装或下载。下列 `tee` 保存测试程序输出；第二次控制使用新目录，第一次结果不覆盖。

## 单元测试

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_api_retry research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core -v 2>&1 | tee research/prospective_simple_check_pilot/retry_reliability_20260907_v1/unit_tests_after_review.log
```

退出码 0；92 tests / 1.259s / OK。审查前同一模块列表执行过一次，输出至 unit_tests.log：91 tests / 7.689s / OK。两轮均为单元/mock，等待依赖被替换，不访问网关。

## 浏览器正控制（最终源版本）

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.test_api_retry --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/retry_reliability_20260907_v1/browser_probe_02 2>&1 | tee research/prospective_simple_check_pilot/retry_reliability_20260907_v1/browser_probe_02.log
```

退出码 0；5 actual_browser_transitions / 2 mock_model_call_attempts / 1 actual_localhost_submissions / 0 real_model_calls。审查前使用 browser_probe_01 目录和对应同名日志执行一次，结果相同；每次都是独立的非图表工程控制，不是正式实验轨迹的重跑。

## 无网络准备检查

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.panel --config research/prospective_simple_check_pilot/route_tolerant_20260907_v1/live_panel_02/MODEL_CONFIG.json --retry-policy research/prospective_simple_check_pilot/retry_reliability_20260907_v1/RETRY_POLICY.json
```

退出码 0；只读已存在 config，不修改它。输出 local_readiness_only、missing credential_environment:MODEL_API_KEY、32 planned prefixes、96 planned strategy_records、0 real_model_calls / 0 network_requests。32/96 仅为原 manifest 计划数，非本轮已执行结果。没有添加 `--execute`，没有以此命令重跑旧面板。
