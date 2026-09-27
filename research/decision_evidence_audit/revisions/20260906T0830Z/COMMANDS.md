# 本次实际执行与工件索引

所有命令从项目根目录执行。以下 PY 和两个浏览器环境变量仅为复现方便归并；实际使用相同绝对路径逐条执行。复现需使用新的输出目录，不能覆盖这里的日志或已有 run。

```bash
PY=/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python
export PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers
export LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu
```

## 只读环境和资产检查

```bash
git -c safe.directory=/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial status --short
git -c safe.directory=/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial rev-parse --verify HEAD
ss -ltnp
pgrep -af 'qwen3_vl_server|vllm.entrypoints|llama-server'
curl --noproxy '*' --max-time 3 -sS http://127.0.0.1:8045/health
"$PY" web_agent_benchmark/benchmark_v2_open/scripts/validate_release.py
"$PY" -m research.decision_evidence_audit.audit_assets --output research/decision_evidence_audit/revisions/20260906T0830Z/local_assets_verified.json
```

Git 有可执行文件、无可验证 HEAD；工作区已有内容均为未跟踪，原样保留。首次 sandbox 的 ss 因 netlink 权限失败，随后按权限流程只读复核；8045 connection refused，模型进程查询无匹配。没有启动服务、下载依赖或模型、终止他人进程。release 校验日志见 release_validation.log，资产终稿见 local_assets_verified.json；local_assets.json 是图类型字段取错的初稿，不使用其中图类型统计。

## 测试

```bash
"$PY" -m unittest discover -s research/decision_evidence_audit/tests -v
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T0830Z/browser_controls \
"$PY" -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
# 修复后使用新目录 browser_controls_retry1，保留首轮日志与截图：
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T0830Z/browser_controls_retry1 \
"$PY" -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
"$PY" -m unittest discover -s web_agent_benchmark/evaluation/gui_reflection_baseline/tests -t . -v
```

结果：unit_tests.log 为31个发现/29通过/2按入口跳过；browser_tests.log 为首轮2失败，browser_tests_retry1.log 为2通过；existing_regression_retry1.log 为186个发现/184通过/2跳过。旧测试首命令未带 -t .，existing_regression.log 保留了15个包相对导入错误；命令修正后通过，旧测试代码未变。

浏览器需要临时回环 HTTP listener 和进程执行权限；通过工具授权执行，没有外网访问。浏览器工件保留请求、响应、截图、真实 POST 回执和 control_budgets.json。注入夹具的 DOM 设置不是被测 Agent 的浏览器动作；agent navigate/select/click 的尝试、重试和重放全部计数。

## 唯一新 smoke

```bash
"$PY" -m research.decision_evidence_audit.runner \
  --mode mock --tasks env001,env025 \
  --run-id stage2_mock_smoke_20260906T0837Z \
  --max-model-calls 120 --max-browser-transitions 650 \
  --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
"$PY" -m research.decision_evidence_audit.validate_run \
  research/decision_evidence_audit/runs/stage2_mock_smoke_20260906T0837Z \
  --require-complete-submission
```

smoke.log 和 smoke_validation.log 保留完整输出。没有第二组 smoke，没有新真实模型推理。运行后新增 validator 的 B2 无独立截图0调用分支；来源校验保留了该项差异警告。原运行 fingerprint 不作修改。

## 预算复核

| 范围 | Mock backend 调用 | Agent 浏览器动作尝试 |
|---|---:|---:|
| 唯一16单元 smoke | 36 | 96 |
| 首次失败浏览器控制 | 4 | 27 |
| 修复后浏览器控制 | 14 | 52 |
| 独立隐藏 DOM 控制 | 0 | 1 |
| 最终三项浏览器回归 | 14 | 53 |
| 最终合计 | 68 | 229 |

真实模型调用为0。首轮主控制 ledger 在断言失败前没有落盘：4条 prefix 请求、4条 prefix executor receipt、4条 B0 replay receipt，以及原序列直接执行5步，共4/13；另一个首轮控制完整 ledger 为0/14，合计4/27。成功轮 ledger 完整为14/37+0/15。对应证据文件路径见 session_accounting.json。单元测试的无 HTTP stub 函数调用不是模型服务请求或真实浏览器动作；审查 Codex 也不是在线被测 Agent。

## 本次结束

真实模型状态见 real_smoke_status.json；退出前健康检查日志为 local_model_check_final.log（pgrep 使用 [q]wen/[v]llm/[l]lama 避免匹配检查命令本身；前一份 local_service_check.log 的两条 bash 自匹配不是模型服务）。只有当前阶段二工程结论；不据 mock score 推断方法好坏。阶段三/四、140对全量评测均未启动。独立 same-family/provisional 审查另存 EXPERIMENT_AUDIT.md/json。

## 独立审查后的增量（没有新模型或浏览器运行）

相同 unittest 命令最后一次输出保存为 unit_tests_post_review.log：34个发现、32通过、2跳过。相同严格 validate_run 命令输出另存 validation_post_review.json：对原16单元复核 valid=true。新增离线校验实际重算数据集终局类别并核对动作/选择/服务器回执，不改原分数；分类因果文字、无图分支和文档修正使当前代码与原 fingerprint 存在明确记录的差异。pre_review/ 为该次修改前源码。

审查者另披露其子审查执行过 compileall（无模型/浏览器调用），可能刷新生成型 __pycache__；未修改源代码、数据或运行工件。该操作超出给审查者的只读范围，保留披露，不删除缓存掩盖。

## 最终可见 DOM/B3 回归

```bash
"$PY" -m unittest discover -s research/decision_evidence_audit/tests -v
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T0830Z/hidden_dom_control \
"$PY" -m unittest research.decision_evidence_audit.tests.test_browser_integration.BrowserIntegrationTests.test_hidden_dom_swap_cannot_enter_public_state_or_trigger_submit -v
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T0830Z/browser_controls_final \
"$PY" -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
"$PY" -m research.decision_evidence_audit.validate_run \
  research/decision_evidence_audit/runs/stage2_mock_smoke_20260906T0837Z --require-complete-submission
```

日志分别为 unit_tests_visibility.log（36发现/33通过/3跳过）、hidden_dom_browser_test.log（1通过）、browser_tests_final.log（3通过）、validation_visibility_revision.json（valid=true，来源差异保留）。此前还有一次同样校验命令带 `--write`，生成原run的 evaluator/validation.json，stdout 为 smoke_validation_final.log；后续校验仅写本次 revisions，不再覆盖该文件。
