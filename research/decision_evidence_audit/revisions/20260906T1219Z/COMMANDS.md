# GPU 0 授权后的真实阶段二 smoke

用户本轮授权：第 0 张卡，优先沿用已有 Qwen；对应上一条提出的最新代码 2×2×4 smoke。仅此轮，不启动阶段三/四或全量评测。

工作目录：`/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。
新 run：`stage2_live_smoke_20260906T1219Z`。旧 run 和原始数据不修改。

## 本地环境复用

复用既有 conda 环境，不安装依赖、不下载权重、不新增环境 contract/hash。
第 0 张物理 GPU：`GPU-27247398-541e-87a3-9bcf-04e95cadf94a`，H100 80GB；启动前显存 3 MiB，无计算进程。其他 GPU 有任务，不触碰。
沙箱内 nvidia-smi 无驱动访问；工具授权后的只读检查成功，不是主机驱动故障。
8045 端口空闲，无既有 Qwen server 进程。服务仅监听回环，实验后释放本轮启动的进程。
模型：`/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct`，4 个 shard 已定位。

独立 agent-follows-doc 验证只执行下面的 kernel witness（无模型推理、无浏览器、无下载）：

```bash
CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch, transformers, importlib.metadata as m; torch.manual_seed(12345); x=torch.randn(8,8,device="cuda"); print("WITNESS", tuple((x@x).shape), torch.cuda.get_device_name(), torch.cuda.device_count()); print("VERSIONS", torch.__version__, transformers.__version__, m.version("qwen-vl-utils"), m.version("accelerate"))'
```

## 服务命令

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python web_agent_benchmark/evaluation/qwen3_vl_server.py --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520
```

## 测试与模型运行

下面浏览器环境适用于 tests 和 runner：

```bash
export PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers
export LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu
export PYTHONDONTWRITEBYTECODE=1
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest discover -s research/decision_evidence_audit/tests -v
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T1219Z/browser_controls /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.runner --mode live-local --tasks env001,env025 --run-id stage2_live_smoke_20260906T1219Z --local-model-url http://127.0.0.1:8045 --local-model-name Qwen3-VL-8B-Instruct --max-model-calls 140 --max-browser-transitions 700 --prefix-max-model-calls 12 --max-output-tokens 1024 --temperature 0 --top-p 1 --seed 12345 --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.validate_run research/decision_evidence_audit/runs/stage2_live_smoke_20260906T1219Z --require-complete-submission
```

总授权仍为 160 次调用、800 次浏览器动作尝试；保守预留 20/100 给浏览器控制，故主 runner 为 140/700。双图 witness 在 runner 内计账。失败/重试不得免费重跑；独立审查不调用在线被测模型。实际结果在运行结束后补充，不能把上述命令存在当成执行完成。

## 实际完成记录

上述服务、unit、browser、runner、validator 均实际执行（控制/运行命令加 set -o pipefail，stdout/stderr 经 tee 写本目录新日志）。unit_tests.log 为36发现/33通过/3跳过；browser_tests.log 为3通过、无失败重跑。runner退出0；validation.strict.json为valid=true。真实41调用/96动作，浏览器控制14 mock/53动作，全轮55/149；没有第二组smoke。运行时间见run_manifest.json。

```bash
curl --noproxy '*' --max-time 3 -sS http://127.0.0.1:8045/health
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/decision_evidence_audit/revisions/20260906T1219Z/summarize_run.py
```

离线聚合命令先生成analysis.json；补充成功crop/失败分发独立计数后再次执行生成analysis.final.json，不覆盖初稿。该脚本只读已完成工件，零模型/浏览器调用。最新原始run没有被聚合脚本修改。

本轮模型PID263435、工具终端session94526；smoke退出后核对准确进程，向此所属终端发送Ctrl-C，服务会话退出130（人工停止，非smoke失败）。随后nvidia-smi与ss复核GPU0回到3 MiB、8045无listener；输出保存在gpu_released.csv和port_released.txt。其他卡不动。

本轮首次文档补丁因STAGE_REPORT标题上下文不匹配而整体拒绝，检查四文件未变后修正patch；没有影响代码、模型运行或预算。没有在线实现修复或重新采样。

最终只读复核：重新执行聚合脚本并将解析后的JSON与analysis.final.json比较完全一致；55≤160、149≤800、16单元断言通过。服务日志41条POST /complete与41请求/41响应一致；原始服务器回执16条与16个unit提交一致。没有新增推理、浏览器动作或数据改写。
