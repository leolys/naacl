# B3 接口修复与再次执行（本轮授权）

用户同意“修，然后再执行”；范围仍为阶段二，GPU 0、现有 Qwen3-VL-8B、2开发任务×2条件×4配置，共一组16单元。总上限160调用/800浏览器动作，所有控制、失败、重试计入。主grid预留120调用/650动作；剩余40/150给控制，不作免费追加grid。

环境复用上一轮已验证的既有conda/本地权重，不重建、不下载、不新增环境hash/contract。启动前重新保存GPU UUID/占用、进程和端口原始查询。仅自启回环服务，完成后关闭本轮进程。

## 修复范围

仅通用B3核查阶段提示、格式解析/错误反馈、观察与决策计数，以及对应控制/离线验证。保留目标、当前选择、全部许可历史和图像工具，不添加样本名/答案/机制提示。不把点击提交或嵌套decision悄悄当成合法核查。

任何重试都使用原3次模型调用上限；格式错误不会虚构crop或消耗观察次数，但仍消耗模型调用。每次合法观察分发计观察预算（包括工具失败）；成功crop另计。两次观察后/最后一个模型回合只允许决策，不增加回合。

下面是供独立agent原样执行的唯一环境witness（无模型推理、无浏览器；stdout保存到本目录）：

```bash
CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch, transformers; torch.manual_seed(12345); x=torch.randn(8,8,device="cuda"); print("WITNESS", tuple((x@x).shape), torch.cuda.get_device_name(), torch.cuda.device_count(), torch.__version__, transformers.__version__)'
```

真实执行命令与结果将在下方补充，命令计划不等于运行完成。原始数据/旧runs不改，编辑前源码副本在original/。

## 已执行：启动、测试、两次小控制、唯一16单元grid

以下命令均从项目根目录运行；日志使用 `set -o pipefail` 与 `2>&1 | tee` 保存到本目录。模型/浏览器在已批准的主机执行面运行，普通沙箱的设备或localhost隔离不视为模型故障。

```bash
CUDA_VISIBLE_DEVICES=GPU-27247398-541e-87a3-9bcf-04e95cadf94a HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python web_agent_benchmark/evaluation/qwen3_vl_server.py --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520
```

服务日志 `service.log`、健康响应 `health.json`；原始启动前检查 `gpu_preflight.csv`、`gpu_processes_preflight.csv`、`port_preflight.txt`。本轮服务终端session5312。

测试和runner复用下列环境（不修改系统配置）：

```bash
export PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers
export LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu
export PYTHONDONTWRITEBYTECODE=1
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest discover -s research/decision_evidence_audit/tests -v
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 DECISION_EVIDENCE_TEST_OUTPUT=research/decision_evidence_audit/revisions/20260906T1342Z/browser_controls /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.b3_controls --output research/decision_evidence_audit/revisions/20260906T1342Z/live_controls --local-model-url http://127.0.0.1:8045
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.b3_controls --output research/decision_evidence_audit/revisions/20260906T1342Z/live_controls_retry1 --local-model-url http://127.0.0.1:8045
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.runner --mode live-local --tasks env001,env025 --run-id stage2_live_smoke_20260906T1342Z --local-model-url http://127.0.0.1:8045 --local-model-name Qwen3-VL-8B-Instruct --max-model-calls 120 --max-browser-transitions 650 --prefix-max-model-calls 12 --max-output-tokens 1024 --temperature 0 --top-p 1 --seed 12345 --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
```

执行时序：第一次unit通过 → browser通过 → validator计数测试通过 → 第一组live control退出1 → 保留 `pre_control_retry/policies.py`，仅将原始目标重复写在通用提示首尾并强调当前选择不是证据 → 最终unit通过 → 第二组live control退出1 → 不再调参或重试 → 唯一grid。浏览器测试在第二次通用提示文字调整前，最终unit与grid在调整后；执行器与解析器没有夹在中间改动。

unit三份日志 `unit_tests.log`、`unit_tests_with_validator.log`、`unit_tests_final.log` 都是38发现、35通过、3按入口跳过。browser日志为3/3通过、15 mock调用/59动作。两组真实小控制各3真实推理+2脚本工具请求，均共5预算调用/0动作，**均有一个失败，不能合并挑出成功结果宣称全通过**。

main grid前累计25计数调用（6真实、4注入、15mock）、59动作；120/650主grid上限保证全轮最多145/709，不超过用户160/800。无HTTP的单元函数替身不当作模型实验；浏览器控制中的mock backend则保守计入。

只读汇总/严格核验命令（不消耗模型或浏览器预算）：

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.decision_evidence_audit.validate_run research/decision_evidence_audit/runs/stage2_live_smoke_20260906T1342Z --require-complete-submission
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/decision_evidence_audit/revisions/20260906T1342Z/summarize_run.py
```

上述汇总以实际完成产物为准，结果及最终资源释放记录见本目录STAGE_REPORT.md。

## 最终完成与释放

唯一runner session86204退出0；严格validator退出0，analysis.json已生成。33真实smoke调用/96动作，加两组控制与浏览器mock后全轮58调用/155动作（其中真实推理39）。service.log的39条POST /complete与真实推理数量一致。

完成后向本轮自启服务终端session5312发送Ctrl-C，退出130是主动关闭，不是实验失败。随后执行下面只读查询，分别存 `gpu_released.csv`、`port_released.txt`，GPU0为3 MiB、8045无listener；其他GPU占用与启动前一致。

```bash
nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total --format=csv,noheader
ss -ltnp '( sport = :8045 )'
```

没有第二组grid，没有停止其他用户进程。旧run、原始数据、AGENTS.md均保留。Git只读查询需单次 `git -c safe.directory=/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial status --short`；未修改global Git配置。

最终只读重算也实际执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import json, pathlib, subprocess, sys; p=pathlib.Path("research/decision_evidence_audit/revisions/20260906T1342Z"); a=json.loads(subprocess.check_output([sys.executable,str(p/"summarize_run.py")])); assert a == json.loads((p/"analysis.json").read_text()); assert a["accounting"]["all_counted_calls"] == 58 <= 160; assert a["accounting"]["all_browser_transitions"] == 155 <= 800; assert a["configured_units"] == len(a["units"]) == 16; assert all(json.loads(u["records"][-2]["response"])["option_label"] == u["recommended_option"] for u in a["units"] if u["strategy"] == "B3"); print("OFFLINE_RECHECK_OK analysis exact; 16 units; 58/160 calls; 155/800 transitions; all 4 B3 raw labels match recommendations")'
```

退出0、stdout为 `OFFLINE_RECHECK_OK analysis exact; 16 units; 58/160 calls; 155/800 transitions; all 4 B3 raw labels match recommendations`。这是额外只读工件复核，不宣称通用validator独立验证了所有字符串/回复一致性，也不额外调用被测模型。
