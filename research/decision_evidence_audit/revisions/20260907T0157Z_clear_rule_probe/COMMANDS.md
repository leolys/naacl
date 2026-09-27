# 实际执行命令与退出状态

以下路径均为本机路径。实际记录日志与各运行目录保留；没有调用外部 API。变量只是缩短复现命令，不使用 HOME/CODEX_HOME。

```bash
PROBE_REPO=/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial
PROBE_REV="$PROBE_REPO/research/decision_evidence_audit/revisions/20260907T0157Z_clear_rule_probe"
PROBE_EVAL=/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python
PROBE_MODEL=/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python
export PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers
export LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1
```

## 测试

初次在项目根执行：

```bash
"$PROBE_EVAL" -m unittest discover -s research/decision_evidence_audit/tests -p 'test_*.py' -v
```

45 项、42 通过、3 跳过，退出 0。修复相对路径检查后在 execution_source_v2 用同一命令：46 项、43 通过、3 跳过，退出 0，日志 final_unit_tests.log。完整审查修复后：

```bash
cd "$PROBE_REV/execution_source_v3"
"$PROBE_EVAL" -m unittest discover -s research/decision_evidence_audit/tests -p 'test_*.py' -v
```

49 项、46 通过、3 跳过，退出 0，日志 review_fix_unit_tests.log。

已有浏览器正控制在 execution_source（v1）中单独执行一次：

```bash
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 DECISION_EVIDENCE_TEST_OUTPUT="$PROBE_REV/browser_controls" \
"$PROBE_EVAL" -m unittest research.decision_evidence_audit.tests.test_browser_integration.BrowserIntegrationTests.test_checkpoint_replay_true_revision_submit_b0_and_illegal_control -v
```

退出 0，1 项通过；脚本 15 次调用、43 transitions。v1/v3 的 core、policies、safe_shell、浏览器执行器相同；本测试不是执行源覆盖的验证。离线 `PYTHONPATH=. "$PROBE_EVAL" "$PROBE_REV/test_case_report.py"` 两项通过、退出 0。

## 三次工程尝试

统一 runner 参数：`--mode mock --profile clear-rule-probe --tasks pub010,env008,b035 --output-root "$PROBE_REPO/research/decision_evidence_audit/runs" --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell`。

| 工作目录 | run-id | 限额（mock 调用/transition） | 实际状态 |
|---|---|---|---|
| 项目根 | clear_rule_mock_20260907T0200Z | 80/180 | 进程退出 0，但 manifest 保留 source-change 错误，只有 8 条提交 |
| execution_source | clear_rule_mock_isolated_20260907T0206Z | 80/180 | 24 条提交，旧来源记录遗漏执行代码；原验证结果不可当作来源通过证明 |
| execution_source_v3 | clear_rule_mock_reviewed_20260907T0220Z | 60/180 | 完整 24 条提交；修复后验证通过 |

第三次实际入口：

```bash
cd "$PROBE_REV/execution_source_v3"
"$PROBE_EVAL" -m research.decision_evidence_audit.runner --mode mock --profile clear-rule-probe \
  --tasks pub010,env008,b035 --output-root "$PROBE_REPO/research/decision_evidence_audit/runs" \
  --run-id clear_rule_mock_reviewed_20260907T0220Z --max-model-calls 60 --max-browser-transitions 180 \
  --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
```

## 已获共用许可后的真实服务和运行

服务在独立 TTY 启动，stdout/stderr 经 tee 保存至 qwen3_vl_server.log：

```bash
cd "$PROBE_REV/execution_source_v3"
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$PROBE_MODEL" -u web_agent_benchmark/evaluation/qwen3_vl_server.py \
  --host 127.0.0.1 --port 8045 \
  --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b
```

权重加载成功，native multi-image 服务可用后执行一次：

```bash
"$PROBE_EVAL" -u -m research.decision_evidence_audit.runner \
  --mode live-local --profile clear-rule-probe --tasks pub010,env008,b035 \
  --output-root "$PROBE_REPO/research/decision_evidence_audit/runs" \
  --run-id clear_rule_live_20260907T0222Z --max-model-calls 140 --max-browser-transitions 380 \
  --prefix-max-model-calls 12 --local-model-url http://127.0.0.1:8045 --local-model-name qwen3_vl \
  --max-output-tokens 1024 --temperature 0 --top-p 1 --seed 12345 \
  --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
```

退出 0，但 manifest 明确为 attempted_incomplete_chain_smoke：3 个 checkpoint、12 条提交、其余 12 分支未运行。61 次推理、111 transitions。执行结束后对自己启动的 TTY 发送 Ctrl-C，服务正常释放资源（退出 130）。

## 验证、展示与总账

```bash
# 最终 mock 使用 --require-complete-submission；真实运行不加该参数，保留未到 checkpoint 的前缀。
"$PROBE_EVAL" -m research.decision_evidence_audit.validate_run \
  "$PROBE_REPO/research/decision_evidence_audit/runs/clear_rule_mock_reviewed_20260907T0220Z" --write --require-complete-submission
"$PROBE_EVAL" -m research.decision_evidence_audit.validate_run \
  "$PROBE_REPO/research/decision_evidence_audit/runs/clear_rule_live_20260907T0222Z" --write

# 离线真实展示用结束后补充失败前缀展示的根目录 reporter；不改执行源。
cd "$PROBE_REPO"
"$PROBE_EVAL" -m research.decision_evidence_audit.case_report \
  research/decision_evidence_audit/runs/clear_rule_live_20260907T0222Z \
  --output-dir research/decision_evidence_audit/revisions/20260907T0157Z_clear_rule_probe/live_case_view
"$PROBE_EVAL" "$PROBE_REV/finalize_records.py" \
  --live-run research/decision_evidence_audit/runs/clear_rule_live_20260907T0222Z
```

上述验证/展示/总账均退出 0。工件禁止覆盖，复现须使用新的 run-id/output-dir。查看模型响应/预算/截图不额外调用模型；任何真实重跑都需重新分配剩余预算。
