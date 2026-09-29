# REBUILD：在线实验缺失件的测试锚定重建（online_p01_20260928）

原 `research/online_defense_20260925` 导出时有三个有意省略的旧路径（AGENTS.md 声明），
P0-1 在线实验需要它们。本目录按仓库纪律重建，**全部行为以冻结测试为锚**：

## 缺失件与重建方式

| 缺失件 | 重建方式 | 锚 |
|---|---|---|
| `explanation_completion_20260925/core.py`（解释补全核心：import_initial / validate_questions / apply_supplement / validate_verification / build_rule_state / save+load_state / read_rules / public_leaf_paths / _evidence(+_list)） | 本目录 `core.py` 从零重建 | `explanation_completion_20260925/tests/test_core.py`（242 行，24 例）+ `online_defense_20260925/tests/test_method.py`、`test_scalar_contract.py`（含 v2 类型化标量引用）+ `METHOD_REVISED_ZH.md`、`METHOD_INTERFACE_V2_ADDENDUM.md` |
| `.aris/task_flows_20260924/snapshot` + `RUNTIME_TASKS.json` | `rebuild_snapshot.py`：从仓库正源 `web_agent_benchmark/` 逐字节复制镜像（含四 shell 包、splits、assets），RUNTIME_TASKS.json 280 行由 splits 重建（slug/arm/domain/spec） | 两件运行时恢复资产按 20260925 `asset_recovery` 的 sha256 逐一核验；`original_env.make_original` 路径契约 |
| `runtime_snapshot/`（隔离运行时镜像） | 由重建的 snapshot 复制 + 同两件资产核验 | `prepare_runtime.py` 契约（本目录内以 rebuild_snapshot.py --runtime 完成同等动作） |

不修改任何旧实验目录；`explanation_completion_20260925/`、`online_defense_20260925/` 保持原样。
runner/method/prompts/original_env/batch_main/deps 为原文件的复制；deps.py 唯一改动 =
core 载入路径指向本目录重建版。

## 已声明的协议差异（相对 20260925 pilot）

1. 端点/模型：本地 vLLM `Qwen3.8-27B`（127.0.0.1:8058）替代付费网关；估算费率置 0
   （本地服务无 API 成本，真实成本为 GPU 时间，按 token/请求留账）。
2. 超时 120s→600s（本地 27B 长核验生成需要）。
3. 浏览器：Playwright 安装的 Chromium（原 Windows Edge 路径不可用）。
4. 接口 `typed_scalars_v2`（prompts_v2 引用规则 + 重建 core 的类型化标量核验）。
5. 预算以请求数/浏览器操作数计（1600/2400），估算 USD 仅作记录。

## 测试

```
python3 -m pytest tests -q        # 离线；0 模型请求
```

通过标准：v1 core 24 例 + method/runner/batch/scalar 全部通过。
工程测试通过不等于研究效果；在线效果结论只来自授权后的真实轨迹。
