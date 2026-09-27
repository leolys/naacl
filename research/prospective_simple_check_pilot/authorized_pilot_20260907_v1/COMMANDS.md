# 本轮实际命令

工作目录 `/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。以下省略凭据值；所有实际输入均使用掩码终端，密钥未写入项目、日志或命令参数。

## 资源、环境与 metadata

沙箱内 `nvidia-smi` 和 `ss` 无法访问驱动/网络状态；经工具权限审核后只读检查成功。GPU0 H100 80GB、3 MiB，8045 未启动、18891 监听。fresh agent 读 AGENTS 后按以下命令运行小型 witness，退出 0：

```bash
env CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch; torch.manual_seed(12345); x=torch.randn(8,8,device="cuda"); y=x@x; torch.cuda.synchronize(); print("WITNESS", tuple(y.shape), bool(torch.isfinite(y).all()), torch.cuda.get_device_name(0), torch.__version__); import importlib.metadata as m; print("VERSIONS", {p:m.version(p) for p in ("transformers","qwen-vl-utils")})'
```

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.gateway_metadata --output research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/gateway_metadata_01
```

掩码输入后，两个 GET 均 200，0 生成，退出 0。输出包含当前完整 ID 列表投影与仅针对 Sol 的四个部署的能力/价格字段，不存储网关上游凭据。

## 源码与测试

通过已有 `snapshot_sources` 保存修改前源文件至 `before_live_accounting_sources/`。然后以 apply_patch 补充可选的完整 usage 费用上界结算及其测试，未知成本不释放；加入正式任务前的控制成本场景估计。

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core -v 2>&1 | tee research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/prelaunch_tests.log
```

68 项通过，0.832 秒；仅原测试中的非失败 Pillow 弃用警告。

## GPU0 服务

```bash
set -o pipefail
env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python web_agent_benchmark/evaluation/qwen3_vl_server.py --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520 2>&1 | tee research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/qwen_server.log
```

已有四个 shard 成功加载，10.197 秒，PID 40510，CUDA 可见设备仅一个。未下载权重。模型服务只收到 `/health`，没有 `/complete`。

## 真实固定控制与计划面板入口

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import getpass,os,runpy; os.environ["MODEL_API_KEY"]=getpass.getpass("API Key (hidden, memory only): "); runpy.run_module("research.prospective_simple_check_pilot.panel",run_name="__main__")' --config research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/MODEL_CONFIG.json --execute --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/live_panel_01 2>&1 | tee research/prospective_simple_check_pilot/authorized_pilot_20260907_v1/live_panel_01.log
```

命令退出 0 仅表示停止工件已正常写完；输出 `stopped=true`，不代表实验通过。生成请求 1，Route 控制设置 transition 4。API 返回执行身份 Luna，`ApiStop`，未执行返回动作。固定控制、正式面板均未通过/未完成。

## 精确清理与复查

用 `ps -p 40510 -o pid,ppid,args`、`readlink /proc/40510/cwd`、`ss -ltnp '( sport = :8045 )'` 确认是本轮服务后执行 `kill -TERM 40510`。服务退出 143。之后只读复查：GPU0 3 MiB / 81559 MiB、利用率 0%；8045 无监听；PID 不存在。复查组合命令末尾 `ps` 因 PID 已不存在退出 1，这是清理成功的预期结果。

未删除任何工件或进程以外的数据；未改图、任务、gold 或旧运行。没有 API 重试、别名扫描、Qwen-only 面板或新机制开发。
