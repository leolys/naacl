# 本轮实际命令

工作目录：项目根目录。沿用本地环境，无安装/下载；凭据从用户指定的已有 API 使用文档读入进程内存，不在命令中放密钥字面值，不打印密钥或另写密钥文件。已有用户文档是否含明文凭据与本轮输出是否泄露是两回事，本轮不改该文档。

## 回归

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_api_retry research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core -v 2>&1 | tee /tmp/misvis_resume_unit_tests_20260907.log
```

93项通过，0.854秒，退出0；日志副本 unit_tests.log。

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.test_resume --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/mock_resume_01 2>&1 | tee /tmp/misvis_resume_browser_20260907.log
```

退出0，33次模拟调用、78实际transition、12本地POST，0真实模型/API。日志副本 mock_resume_01.log；没有改动既有真实结果。

## 既有GPU0服务

```bash
nvidia-smi -i 0 --query-gpu=index,memory.used,memory.total --format=csv,noheader
ss -ltnp '( sport = :8045 or sport = :18891 or sport = :18892 )'
```

受限沙箱第一次无法访问驱动/netlink，提升权限后只读检查成功；启动前 GPU0 为 58491/81559 MiB，8045无监听，原代理18891已有监听。该沙箱访问失败不是GPU故障。

```bash
set -o pipefail
env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch,runpy; torch.cuda.set_per_process_memory_fraction(0.25,0); print("ALLOCATOR_MEMORY_FRACTION",0.25,flush=True); runpy.run_path("web_agent_benchmark/evaluation/qwen3_vl_server.py",run_name="__main__")' --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520 2>&1 | tee research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/qwen_server.log
```

本轮服务PID84468，加载12.368秒；/health返回8b、max_pixels1003520、native_multi_image=true、server_protocol_version2.0。启动后GPU0为75778/81559 MiB。服务启动不是一次模型生成，也不是新环境建立。

## 明确接续同一面板

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import os,re,runpy; from pathlib import Path; candidates=set(re.findall(r"sk-[A-Za-z0-9_-]{20,}",Path("docs/intranet_model_api_usage.md").read_text())); assert len(candidates)==1,"Expected exactly one configured credential; no inference started"; os.environ["MODEL_API_KEY"]=candidates.pop(); del candidates; runpy.run_module("research.prospective_simple_check_pilot.resume_panel",run_name="__main__")' --source research/prospective_simple_check_pilot/route_tolerant_20260907_v1/live_panel_02 --config research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/MODEL_CONFIG.json --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/live_panel_03 2>&1 | tee research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/live_panel_03.log
```

22:47 CST启动。完整源拷贝在live_panel_03/executed_sources；新Git字段若没有有效提交则为null，不再把命令失败的字面HEAD当版本。旧runtime.json保持原样。

结束状态、每次尝试回执及费用以 live_panel_03 的工件和 PILOT_REPORT.md 为准；程序退出0也可能表示已正确保存停止工件，不代表96配置完成。

## 离线报告与收尾

调度退出0，stopped=true，stop.json为BudgetExceeded。之后才运行：

```bash
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/report_results.py --run research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/live_panel_03
```

退出0，生成PILOT_REPORT、CASE_LAYERS、CUMULATIVE_COSTS。本目录report_results.py是独立的事后汇总代码，不冒称旧运行时reporter；实际评分由新段executed_sources中的panel.py/safe_shell.py在在线结束后执行。

```bash
ps -p 84468 -o pid,ppid,args
readlink /proc/84468/cwd
ss -ltnp '( sport = :8045 )'
kill -TERM 84468
nvidia-smi -i 0 --query-gpu=index,memory.used,memory.total --format=csv,noheader
ss -ltnp '( sport = :8045 )'
```

先核对PID、cwd、监听归属，再仅停止自有服务；服务退出143。GPU0回到58491/81559 MiB，8045无监听；其他作业保留。
