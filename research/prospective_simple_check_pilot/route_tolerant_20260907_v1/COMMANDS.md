# 本段执行命令

工作目录为项目根目录。承接旧段开销，不修改旧段记录。下列命令不含凭据值；API 密钥仅通过 getpass 掩码输入进入评测进程内存。

## 回归

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core -v 2>&1 | tee research/prospective_simple_check_pilot/route_tolerant_20260907_v1/prelaunch_tests.log
```

71 项通过，81.697 秒。新增测试涉及显式身份豁免、实际路由保留和旧控制预算承接；原严格身份检查仍是默认。测试使用 fixture/mock，并非真实模型效果结果。

## GPU0 已有权重服务

```bash
set -o pipefail
env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch,runpy; torch.cuda.set_per_process_memory_fraction(0.25,0); print("ALLOCATOR_MEMORY_FRACTION",0.25,flush=True); runpy.run_path("web_agent_benchmark/evaluation/qwen3_vl_server.py",run_name="__main__")' --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520 2>&1 | tee research/prospective_simple_check_pilot/route_tolerant_20260907_v1/qwen_server.log
```

本进程 PID 48804，11.79 秒完成加载。仅 GPU0；25% 是本进程 PyTorch allocator 上限，不是对其他共享作业的配额或干预。启动后等待 `/health` 验证，再执行面板。

## 真实控制与固定面板

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import getpass,os,runpy; os.environ["MODEL_API_KEY"]=getpass.getpass("API Key (hidden, memory only): "); runpy.run_module("research.prospective_simple_check_pilot.panel",run_name="__main__")' --config research/prospective_simple_check_pilot/route_tolerant_20260907_v1/MODEL_CONFIG.json --execute --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/route_tolerant_20260907_v1/live_panel_01 2>&1 | tee research/prospective_simple_check_pilot/route_tolerant_20260907_v1/live_panel_01.log
```

运行时源码位于 `live_panel_01/executed_sources/`。是否完成以工件中的 prefixes、rows、stop_reason 和真实提交回执为准，不能只看进程退出码。

## 调度修复、离线复现与同面板承接

从真实 manifest 读取首个 unit，调用 `dict(**u, status="starting", checkpoint_reached=False)`，离线退出 1：`TypeError: dict() got multiple values for keyword argument 'status'`。用 apply_patch 改为字典合并，保留旧源快照。复跑上述 unittest 命令，输出改为 `scheduler_fix_tests.log`：73 项通过，27.953 秒。

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.test_panel --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/route_tolerant_20260907_v1/scheduler_fix_browser_01 2>&1 | tee research/prospective_simple_check_pilot/route_tolerant_20260907_v1/scheduler_fix_browser_01.log
```

退出 0，48 次脚本 mock 调用、124 次实际浏览器 transition、20 次 localhost POST；0 次真实模型/API 生成。

确认 PID 48804 命令行、cwd、8045 监听均为本段服务后，`kill -TERM 48804`；退出 143。复查 GPU0 回到其他作业的 58491 MiB，8045 无监听。未干预其他进程。

使用上方完全相同 GPU0 服务命令重启，仅日志改为 `qwen_server_scheduler_fix.log`。新 PID 54800，8.865 秒加载成功，仍为 25% allocator cap。

使用上方完全相同 getpass 面板命令启动，仅将 `--config` 改为 `research/prospective_simple_check_pilot/route_tolerant_20260907_v1/MODEL_CONFIG_scheduler_fix.json`，`--output` 改为同目录 `live_panel_02`，tee 改为 `live_panel_02.log`。21:20 CST 开始；新快照在 `live_panel_02/executed_sources/`。所有已用预算承接，具体见 `SCHEDULER_FIX.md`。

面板因 HTTP 429 正常写出停止工件，进程退出 0；输出 `stopped=true`，不是整组实验完成。累计 live 43 模型调用尝试、107 transition、36 replay。没有重试。

再次用 `ps -p 54800 -o pid,ppid,args`、`readlink /proc/54800/cwd` 和 `ss -ltnp '( sport = :8045 )'` 核实本轮归属后执行 `kill -TERM 54800`。服务退出 143。`nvidia-smi -i 0 --query-gpu=index,memory.used,memory.total --format=csv,noheader` 回报 58491 / 81559 MiB（其他作业仍在），8045 无监听。

只读对比此前严格身份运行快照与本次实际运行快照的四个修改文件，用 apply_patch 保存 SOURCE_CHANGES.patch；没有改写旧源文件。凭据片段扫描本目录和本次审查 trace 无命中。完整归档请求不保存 Authorization 头，密钥未写入磁盘。
