# 本次命令与结果

工作目录 `/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。

## 1. 用户授权的只读模型列表

```bash
python scripts/test_intranet_model_api.py --list-models --proxy http://127.0.0.1:18891 --timeout 20
```

经工具网络权限审核执行，密钥通过 `getpass` 的掩码终端输入，未放入命令、脚本、环境配置文件或归档。HTTP 200，工具报告 61 条，0 生成调用；结果为工具输出而非原始 HTTP 归档。仅查询一次。

## 2. 单元与必要原核心回归

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_panel -v
```

初次 8 项通过。补上局部额度/全局停止分离测试后：

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel -v 2>&1 | tee research/prospective_simple_check_pilot/api_preparation_20260907_v2/unit_test.log
```

25 项通过。加入原 `research.decision_evidence_audit.tests.test_core` 的回归命令输出存 `regression_test.log`，63 项通过。最后增加 token 缺项记账、失败核验尝试、已提交但未确认完成测试后：

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_preparation research.prospective_simple_check_pilot.test_panel research.decision_evidence_audit.tests.test_core -v 2>&1 | tee research/prospective_simple_check_pilot/api_preparation_20260907_v2/regression_final.log
```

退出 0，66 项通过，1.042 秒。另解析 10 个模块语法、核对列表转存数为 60、实际提交 JSONL 总数为 20，均通过。`git diff --check` 退出 0，但这些研究文件当前是 untracked，不能据此声称 Git 已审查其全部新增内容。一次报告文本补丁因上下文未匹配被拒绝，随后以准确完整段落应用成功；未影响代码或任何实验工件。

## 3. 非图表脚本后端，实际浏览器

```bash
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu timeout 120 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.test_panel --browser /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell --output research/prospective_simple_check_pilot/api_preparation_20260907_v2/mock_panel_01
```

因本机临时 HTTP 服务和浏览器需要沙箱外权限，明确申请 CPU-only 本地工程测试后执行。Chromium 使用 `--disable-gpu`。退出 0，48 mock calls、124 transition、20 localhost POST；0 API 生成、0 GPU 推理。未重跑或使用预选 8 个图表任务。

## 4. 零网络的准备状态检查

```bash
set -o pipefail
env PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.prospective_simple_check_pilot.panel --config research/prospective_simple_check_pilot/api_preparation_20260907_v2/MODEL_CONFIG.json | tee research/prospective_simple_check_pilot/api_preparation_20260907_v2/READINESS.json
```

退出 0，报告尚未满足的授权、金额/费用依据、固定配置和运行中本地服务等项；32 计划前缀、96 计划配置，0 网络、0 模型调用。该命令不会读取文档中的密钥或自动启动任何服务。

## 尚未执行

正式调用入口为同一 `panel` 模块的 `--execute --output 新目录 --browser 已有浏览器`，配合经过明确授权的当轮配置与安全注入的 MODEL_API_KEY。当前配置故意不具备执行授权。不要直接把 `authorized` 改成 true 来绕过用户金额/资源确认；也不要把官方标价填作未证实的内网计费依据。

没有 API POST，没有启动/复用 Qwen，没有 GPU 监测或其他作业启停，没有新样本选择或提示校准。编写和读取新工程文件之外，旧 manifest、score、图像均未改写。
