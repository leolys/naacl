# 本轮命令与执行记录

工作目录：`/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。以下命令已执行；最终分析和资源释放在结尾追加。无新环境、模型下载或密钥明文日志。run-experiment技能沿用已有环境及先前命令记录；用户共享GPU0授权优先于技能的独占空闲GPU建议，未新建hash或门禁。

## 单元及浏览器回归

先执行相同前四个测试模块：59 tests通过。随后包含现有核心信息隔离/预算/评分测试，留下完整日志：

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.prospective_simple_check_pilot.test_api_retry research.prospective_simple_check_pilot.test_money_waiver research.decision_evidence_audit.tests.test_core 2>&1 | tee research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/unit_tests.log
```

97 tests通过，3.023秒，退出0。模拟重试不调用网关，也不扣真实模型次数。

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.test_resume --multisegment --output research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/multisegment_mock_01 --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell
```

退出0，34次mock模型尝试、79次实际浏览器transition、12次真实localhost POST，0次真实模型/API调用。三段接续、无重复提交、旧文件内容不变、完整输入一致。工件：`multisegment_mock_01/result.json`及三个运行段。合计工程transition从212增至291。

## Qwen 原环境热复用

启动前只读核对：GPU0 58491/81559 MiB，原8045端口未监听，代理18891正常。未操作其他GPU作业。

```bash
set -o pipefail
env CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python -c 'import torch,runpy; torch.cuda.set_per_process_memory_fraction(0.25,0); print("ALLOCATOR_MEMORY_FRACTION",0.25,flush=True); runpy.run_path("web_agent_benchmark/evaluation/qwen3_vl_server.py",run_name="__main__")' --host 127.0.0.1 --port 8045 --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct --model-size 8b --max-pixels 1003520 2>&1 | tee research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/qwen_server.log
curl --noproxy '*' --max-time 5 -fsS http://127.0.0.1:8045/health
```

服务PID338266，加载15.266秒；health确认原权重、max_pixels1003520、native_multi_image=true。首次加载中健康检查connection refused，此后就绪；健康GET不计模型生成。未因此重启第二服务。

## 真实固定面板接续

凭据仅由用户指定的本地使用说明读入进程环境；不打印、不拷贝进结果。此次权重与图像配置通过原服务metadata核对；原已通过的流程控制不重新调用。

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import os,re,runpy; from pathlib import Path; candidates=set(re.findall(r"sk-[A-Za-z0-9_-]{20,}",Path("docs/intranet_model_api_usage.md").read_text())); assert len(candidates)==1,"Expected exactly one configured credential; no inference started"; os.environ["MODEL_API_KEY"]=candidates.pop(); del candidates; runpy.run_module("research.prospective_simple_check_pilot.resume_panel",run_name="__main__")' --source research/prospective_simple_check_pilot/resumed_pilot_20260907_v1/live_panel_03 --config research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/MODEL_CONFIG.json --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/live_panel_04 2>&1 | tee research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/live_panel_04.log
```

2026-09-08 09:01 UTC左右启动。`reissued_request.json`和`online/unit_13/prefix/resume_proof.json`记录旧request0059→新request0060：原公开状态、历史prompt、截图像素、完整wire含图像字节一致；旧2次失败计入本逻辑请求4次总额。后续进度与终止见运行日志、budget、progress和evaluator。

工程源修改：`api_backend.py`、`resume_panel.py`、`test_resume.py`，新增`test_money_waiver.py`。运行前副本位于`live_panel_04/executed_sources`；旧运行的源码副本保留。本目录离线report_results.py不属于在线执行器，无权调用模型或更改评分。

运行中另做只读逐字节比较：本段与上一段executed_sources中的prospective `h_base.py/harness.py/panel.py`、decision_evidence_audit `policies.py/runner.py/core.py/safe_shell.py/models.py`，8/8相同。`SOURCE_CHANGES.patch`由旧运行源码副本与当前改动比较得到；没有用Git HEAD推断未提交代码身份。本检查不是对未来任意工作区变化的自动保证，也不是图像在所有历史时点均未变化的证明。

审查指出的通用局限单独保留：mock是组件级回归，不覆盖生产CLI全部检查；同一前缀多次跨段中断尚不受充分支持；本次配置retry字段经人工核对相同，但通用比较允许显式retry调整；HTTP429没有被客户端接受的成功答复，非200完整响应体未保存，因此无法证明上游根本没有生成过内容。当前第13单元此前完成逻辑调用为0，没有用组件测试宣称任意多段恢复正确。

## 运行完成、离线分析、释放资源

2026-09-08 09:55:18 UTC附近调度退出0，stopped=false；累计真实调用尝试285、live transitions691（重放405），未发生全局停止。研究面板无新增模型替换或自动扩样。

```bash
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/report_results.py --run research/prospective_simple_check_pilot/internal_api_continuation_20260908_v1/live_panel_04
ps -p 338266 -o pid,ppid,etime,args
readlink /proc/338266/cwd
ss -ltnp '( sport = :8045 )'
kill -TERM 338266
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
ss -ltnp '( sport = :8045 )'
ps -p 338266 -o pid,stat
```

报告生成退出0（之后仅为本段文档措辞再生成，无模型/浏览器调用）。先核实PID338266是本项目原8045服务再关闭；关闭后8045未监听，PID消失，GPU0从运行中76994 MiB回到58491 MiB，其余三GPU始终58491 MiB。末次ps因进程已退出返回1是预期，不是实验错误。没有删除模型或旧实验文件。

离线报告使用analyze-results整理分模型、条件和相对B0差异，不做单种子显著性推断。experiment-audit由同系列新审查者给出provisional审查，原始提示/回复留在`.aris/traces/experiment-audit/2026-09-08_internal_continuation_v1`；审查不是被测Agent，也不计入研究模型调用尝试。

Reporter首次实际执行为2026-09-08 09:55 UTC之后、GPU关闭前；实际源码就是本目录report_results.py，不冒称在线executed_sources中的版本。10:11 UTC附近根据最终审查补充标签资格与百分比分母说明并再次执行同一命令，评分与模型结果不变，具体再生成时间见REPORT_GENERATION.json。

输入一致性表述限定：reissued_request中的完整payload比较是Python JSON结构/值相等，加public_context相等，其中包含完全相同的图像base64字符串；没有抓取socket层HTTP序列化字节作逐字节比较。不能将该字段名外推为网络层取证证明。
