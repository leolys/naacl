# MisVis 决策证据核验：远程 GPU 续跑交接

> **2026-09-06 完成标记：** 本文件第 10–12 节所述的 stage-two live-local 执行清单已经在当前服务器按用户授权完成；原步骤保留作审计记录，不得凭同一授权再次执行。结果工件为 `runs/stage2_live_smoke_20260906T073005Z/`：16 units 全部落盘，8 条链路完成，env025 因通用 select label/name 映射失败而有 8 个 `not_run_no_checkpoint`；模型服务已关闭。当前权威状态见 `STAGE_REPORT.md` 和 `NEXT_ACTION.md`。Stage-three pilot 仍未启动、未获授权。

交接日期：2026-09-06（Asia/Shanghai）  
交接用途：把本对话中已经完成的阶段一/二工作、安全边界和下一步执行条件交给另一台有空闲 GPU 的服务器上的 Codex。  
安全说明：本文件已脱敏。用户曾在对话中提供 AIME bearer token；**该 token 不在本文件中，也不得写入代码、命令行日志、run manifest 或实验工件**。如需使用，只从进程环境变量读取，并建议用户轮换已在对话中暴露的 token。

## 1. 给新 Codex 的起始指令

请先完整读取以下文件，然后再执行任何命令：

1. 仓库根目录 `AGENTS.md`
2. `Codex_MisVis_Direction1_Research_Brief.md`
3. `research/decision_evidence_audit/LOCAL_AUDIT.md`
4. `research/decision_evidence_audit/PROTOCOL.md`
5. `research/decision_evidence_audit/STAGE_REPORT.md`
6. `research/decision_evidence_audit/NEXT_ACTION.md`
7. 本交接文件

继续遵守以下边界：

- 底线问题：在没有执行报错时，发现并修正缺少可见证据支持的待提交决策。
- 必须解决的瓶颈：用有限重观察预算找到足以区分不同行动的视觉依据。
- 不要把方向改回前提账本、长程回滚、技能进化或大型多 Agent 框架。
- 当前先检验普通重读、目标语义核查和通用主动视觉核验是否已经足够；没有明确残余问题，不开发新的候选机制。
- 不向被测模型提供隐藏正确选项、另一 arm、误导机制标签、evaluator bbox、原始 CSV/HTML 或终局评分。
- 写代码的 Codex可以离线审计 gold，但不得看着 gold 产生被测 action。
- 不覆盖原始数据、旧实验结果、用户未提交修改或 `AGENTS.md`。
- 下一步仍只是一个重新获批的 live-model stage-two smoke；未经用户另行批准，不启动 stage-three pilot、140-pair 全量评测或新机制开发。

## 2. 当前阶段状态

阶段一和阶段二工程工作已经完成，并已在阶段二停止。

当前研究结论：

```text
hypothesis_status = not_evaluated
```

原因：单元测试、injected control 和 scripted mock 只能证明工程链路，不能证明 B2/B3/B4 的视觉能力。真实视觉模型 smoke 尚未运行。

已有四份正式交付：

- `research/decision_evidence_audit/LOCAL_AUDIT.md`
- `research/decision_evidence_audit/PROTOCOL.md`
- `research/decision_evidence_audit/STAGE_REPORT.md`
- `research/decision_evidence_audit/NEXT_ACTION.md`

阶段二适配层当前 executable source/tests/manifests 共 13 个文件，tree fingerprint 为：

```text
f02f729f1bae58ac9c90bb0c8e03783f78b49fbfdc8953e28fbdfd1eea8ecb71
```

该 fingerprint 是 provenance 信息，不是长期发布 gate。当前机器没有 Git executable，且 `.git` 是 unborn HEAD/no objects，不能声称 clean worktree 或提供 commit。

## 3. 已确认的数据与协议事实

主数据面：

```text
web_agent_benchmark/benchmark_v2_open/
```

- release manifest：`release_version=2026-07-07`、`status=open_release_candidate`。
- 140 official + 140 clean + 40 real-world；320 task instances；797 个引用资产。
- 140 个 synthetic pair 中只有 114 对满足本轮所审字段的强 chart-only 条件。
- 26 个非强配对：`b017`–`b034`、`health006`–`health013`。
- 全部 cherry-picking case 都落在这 26 对中，不能混入严格 chart-only pilot。
- official/clean 的 raw task 都是 140/140 把 expected action 放在原始 `action_space[0]`，存在严重 gold-position side channel。
- 当前 safe shell 已改为只按公开 label 的 `(casefold(label), label)` 排序；评分在提交后按唯一 visible label 映回 raw action ID。

阶段二开发任务固定为：

```text
env001
env025
```

二者是已核验的强 pair，分别提供 line/bar 类型的开发覆盖；它们不是正式 holdout，也不足以支撑研究结论。

## 4. 当前代码结构

所有新增代码在：

```text
research/decision_evidence_audit/
```

关键文件：

- `core.py`：public projection、nested hidden-key guard、预算 ledger、中性 before-submit hook、checkpoint。
- `safe_shell.py`：只接收 public task/chart 的本地网页；真实 HTTP POST receipt；独立 offline scorer。
- `models.py`：调用前记账、request/response/error 工件、scripted mock、已运行 loopback Qwen 服务客户端、有序多图。
- `policies.py`：B0/B2/B3/B4。
- `runner.py`：固定 development split、2×2×4 schedule、自然前缀、物理 replay、共享 executor、不可逆 submit 单次尝试、失败分母保留、offline score。
- `validate_run.py`：grid、budget、replay、receipt、score、在线隔离、图像边界和 provenance 校验。
- `tests/`：deterministic tests 与 opt-in Playwright/HTTP integration test。

原 benchmark runner、shell、task data 和旧结果均未修改。没有直接复用原 shell，是因为部分页面会暴露 mechanism/readiness/`correct_value`，原 middleware 也可能改写 `finish` 或重复动作。

## 5. before-submit 与四个配置

Hook 在 Agent 第一次提出可解析到当前可见 submit 控件的业务提交动作后、executor 真正执行前触发。它不读取 condition、gold、scorer、mechanism 或当前选择是否正确；空选择和任意选项同样触发。

每个 task-condition 只自然运行一次得到 checkpoint，随后新建 page 并物理重放同一可见动作前缀。公开 DOM canonical JSON 与 full-page screenshot SHA-256 必须同时相等，才允许分叉：

| 配置 | 行为 | 核验调用 | 主动观察 |
|---|---|---:|---:|
| B0 | 原样继续并提交 | 0 | 0 |
| B2 | 完整重读图表与 goal，首次独立判断不显示 current selection | 1 | 0 |
| B3 | 通用主动视觉核验，可从已观察 screenshot 请求 crop | 1–3 | 0–2 |
| B4 | 同一模型先从图像提取内容，再由普通决策回合选择 | 2 | 0 |

B3 每回合显式携带 `current + dashboard + all successful crops`，因此真实模型服务必须支持有序多图，典型输入图数为 2→3→4。

“真实提交”是向 agent-safe 本地网页发生真实 HTTP POST、生成 server receipt 并观察 confirmation；它不是外部业务系统提交，也不是原 benchmark shell 的官方分数。

## 6. 已完成测试

数据 validator：

```bash
python web_agent_benchmark/benchmark_v2_open/scripts/validate_release.py
python misvisagentbench-demo/scripts/validate_demo.py
```

结果分别为：140/140/40、320 instances、797 assets；以及 12 pairs、8 real-world、32 instances、72 assets，均通过。

原 GUI baseline 回归：

```bash
python -m unittest discover \
  -s web_agent_benchmark/evaluation/gui_reflection_baseline/tests \
  -t . -v
```

结果：186 tests，OK，2 skipped。

当前适配层：

```bash
python -m py_compile \
  research/decision_evidence_audit/*.py \
  research/decision_evidence_audit/tests/*.py

python -m unittest discover \
  -s research/decision_evidence_audit/tests \
  -t . -v
```

最后结果：25 tests，OK，1 skipped；即 24 个 deterministic tests 实际执行通过。

真浏览器/HTTP 集成测试：

```bash
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
python -m unittest \
  research.decision_evidence_audit.tests.test_browser_integration -v
```

最后结果：1 test，OK。若新 Codex 的沙箱禁止 loopback bind，需要按其权限流程批准临时本机监听；不要把这个权限扩大为外网监听。

测试已经覆盖：neutral hook、B0 no-op、B2 change/no-change、B3 2 crops/3 calls/累计多图、hidden projection、label sort、selection no-op retry、不可逆 submit 不重试、真实 POST、状态恢复、空选择失败、prefix/backend failure、browser-start failure、post-commit close/confirmation failure、duplicate receipt、shell health cleanup、partial-run validation。

## 7. 旧 16-unit mock 工件及解释限制

已有工程演练：

```text
research/decision_evidence_audit/runs/stage2_mock_smoke_20260906T0206Z/
```

原命令：

```bash
python -m research.decision_evidence_audit.runner \
  --mode mock \
  --tasks env001,env025 \
  --run-id stage2_mock_smoke_20260906T0206Z \
  --max-model-calls 160 \
  --max-browser-transitions 800 \
  --prefix-max-model-calls 12
```

记录：16/16 units、4/4 checkpoints、16/16 replay state/screenshot equal、16/16 POST/receipt/confirmation、36 model calls、96 browser transitions。当前严格 validator 为 `valid=true`，隔离扫描未发现所检查范围内的泄漏。

但该 run 是**修复前历史工件**：当时 raw gold 全在第一项，scripted mock 也固定选择第一项，所以 16/16 success 完全不可作研究解释。其运行时 12 个 source files 中已有 9 个与当前源码不同，且当时没有记录后来新增的 validator。不得把它冒充当前代码或真实模型结果。

用户原先给出的总上限是最多 16 个 smoke units。旧 mock 已经用完这 16 units，因此新的 live 2×2×4 grid 需要用户明确重新授权 unit ceiling；只看 160-call/800-transition 尚有余量不能绕过 unit ceiling。

## 8. 模型选择结论

首次 live stage-two smoke 的首选：

```text
Qwen3-VL-8B-Instruct
```

当前机器核验到的权重位置：

```text
/mnt/data/datasets/open_source_models/Qwen3-VL-8B-Instruct
```

静态事实：

- `Qwen3VLForConditionalGeneration` / `qwen3_vl`，BF16。
- 4/4 safetensors shard 存在，索引声明总权重 `17,534,247,392` bytes（约 16.33 GiB；目录约 17 GB）。
- 本地 revision 记录为 `1610d9f98460d59272cd9963efdf92f0cd3c8dc9`。
- 现有服务 `web_agent_benchmark/evaluation/qwen3_vl_server.py` 原生支持 `/health`、`/complete` 和有序多图。
- 当前客户端 `research/decision_evidence_audit/models.py` 已匹配该协议，不会自动启动或下载模型。
- 粗略建议至少 32 GiB 空闲显存，40/48 GiB 更稳；正式启动前以目标服务器实测为准。

当前机器曾定位到专用环境：

```text
/mnt/data/code_generation/liyisheng/8H100conda/envs/qwen3_vl
```

其中历史静态版本包括 Transformers 4.57.1、qwen-vl-utils 0.0.14、Torch 2.8.0、Accelerate 1.11.0。**不要假设另一台服务器也有相同绝对路径或可用 CUDA；必须重新定位和验证。**

备选：

- `Qwen3-VL-4B-Instruct`：约 8.3 GB，但 server CLI 需小改且模型更弱。
- `Qwen3-vl-32-instruct`：约 63 GB、14/14 shard，现有 dense server 可兼容，但通常需要独占 80 GB 卡或多卡；不适合只为链路 smoke 增加资源。
- `Qwen3-VL-30B-A3B-Instruct`：约 58 GB，MoE；当前 server 硬编码 dense class，不能原样复用。
- `Qwen3.5-9B`：权重完整但当前环境/服务缺对应实现，需要升级或新 server，不作为首次 smoke。

原机器的 8 张 H100 在最后一次只读检查时均有未知归属的高负载任务（约 87%–90% utilization，42–70 GiB 已占用），所以没有启动模型、抢占 GPU、终止进程或下载依赖。

## 9. AIME 网关状态

用户明确允许考虑 AIME 上的开源视觉模型，但本次从原机器无法到达网关：

- 经配置代理连接时，CONNECT 阶段返回 HTTP 403，未到达目标服务。
- 清除代理并强制直连时，内网域名无法 DNS 解析。
- 只尝试了零推理 models-list 探针；没有调用 completion/messages。
- bearer credential 仅驻留探针进程内，未打印、未落盘。

仓库中的旧说明 `docs/multimodal_litellm_api.md` 曾记录 `qwen3.6-plus`、`dashscope/qwen3.5-397b-a17b` 等可读图，但这是历史记录，不是本轮取得的当前 `/models` 响应。模糊 alias 不能自动证明当前版本、开源身份或多图能力。

若新服务器能访问 AIME，先只获取脱敏 `/models` 列表，并确认精确 open-weight multimodal model ID。正式接入前还需新增一个专用 AIME backend，因为当前 stage-two runner 只支持 `mock/live-local`：

- API key 只读环境变量；不得进入 CLI、manifest 或工件。
- 只允许预期 HTTPS host，启用 TLS 验证，拒绝 redirect；`requests.Session.trust_env=False`，除非用户明确批准唯一代理，不继承 ambient proxy。
- Backend 初始化时把 key 读入进程内存后，应从环境删除，或给 Playwright/浏览器显式传入移除该变量的环境；不得让 bearer 被浏览器或其他子进程继承。
- 自动 retry 必须为 0；每个 HTTP attempt 都要在预算中计数。
- 必须保留 B3 的 2/3/4 张有序多图输入。
- manifest 明确 `remote_data_egress=true`；外发内容只能是公开 goal、visible options 和 agent 已观察截图。
- Open release manifest 仍是 `open_release_candidate`，第三方资产许可证尚待确认；即使 AIME 是内部网关，也需用户确认允许把这些截图发送到该服务。
- 首选精确版本的 `Qwen3-VL-32B-Instruct` 或等价 open-weight multimodal Instruct 模型；闭源 Claude 不作为主 backbone，只能另行批准做敏感性面板。

## 10. 新服务器上的最小执行顺序

### 10.1 先确认授权，不要直接开跑

需要用户明确给出：

1. 目标服务器/工作目录；
2. 可用且归属明确的 GPU ID；
3. 是否允许启动 `Qwen3-VL-8B-Instruct` 服务；
4. 新的 live smoke unit ceiling（完整 grid 为 16 units）；
5. model-call/browser-transition ceiling；建议仍不超过 160/800，并把所有 witness、失败和重试计入总账；
6. 若要走 AIME，确认该服务器允许向内部网关外发图表截图，并以环境变量方式提供 credential。

### 10.2 环境与 GPU preflight

使用项目本地 `run-experiment` skill，并读取目标服务器已有 `.aris/compute/` ledger（若存在）。先只读运行：

```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
  --format=csv,noheader
nvidia-smi --query-compute-apps=gpu_uuid,pid,process_name,used_memory \
  --format=csv,noheader
```

不要仅因“剩余显存似乎够”就与未知任务共享 GPU。按当前执行约定，空闲卡应接近 `<500 MiB` used，并确认所有权。

启动前还要检查目标端口和进程归属；若 8045 已有未知 listener，不得终止或仅凭其 `/health ok=true` 复用，应选择新的获准端口或请所有者确认。

重新核验：

- repo/data/weight/env/browser 的实际路径；
- 4 个 weight shard 与 index/config 是否存在；
- Python env 中 `torch`、`transformers`、`accelerate`、`qwen_vl_utils` 是否可导入；
- `torch.cuda.is_available()`、device count 和目标卡名称；
- Playwright 与 Chromium 是否已经安装。不得未经授权下载 browser、模型或依赖。

在声明环境 ready 前，按 `run-experiment` skill 做 seeded CUDA kernel witness；若新建或重建环境，按该 skill 记录声明式环境 spec/ledger 并做 fresh-agent follows-doc 核验。

### 10.3 启动本地服务

以下只是模板；必须替换为目标服务器已核验的绝对路径和获准 GPU：

```bash
CUDA_VISIBLE_DEVICES=<approved_gpu> \
<verified_qwen_env>/bin/python \
  web_agent_benchmark/evaluation/qwen3_vl_server.py \
  --host 127.0.0.1 \
  --port 8045 \
  --model-path <verified_Qwen3-VL-8B-Instruct_path> \
  --model-size 8b
```

长运行应使用独立 `screen`/等价后台会话并用 `tee` 保存日志。记录 PID、GPU、启动命令、模型路径、环境版本和日志路径；不要绑定 `0.0.0.0`。

先做零推理健康检查：

```bash
curl --noproxy '*' -sS http://127.0.0.1:8045/health | jq
```

必须人工确认：`ok=true`、模型路径/大小符合预期、`native_multi_image=true`、server protocol 为当前多图版本。当前客户端只自动检查 `ok/status`，不会自动拒绝错误 model path 或旧 protocol；因此这项人工核验不能省略。健康检查失败时保留日志，不盲目重复启动。

### 10.4 当前源码回归与多图 witness

先运行第 6 节的 py_compile、24 个 deterministic tests 和 opt-in browser test。

当前 runner 尚未提供独立 witness 入口或跨进程总账。先增加并测试一个可审计的 runner 内 preflight witness；若坚持独立运行，则必须单独落账，并把其实际 HTTP attempts 从随后传给 runner 的获批 ceiling 中扣除。不得一边额外调用 witness，一边仍把完整 ceiling 交给 runner。

在用户批准的总 model-call ceiling 内做一次 seeded 双图正控制，确认：

- server 确实收到 2 张图；
- 返回的 `input_image_count=2`；
- 响应能区分两张不含答案文件名的合成图；
- 该次 HTTP attempt 单独计入总预算并保存脱敏工件。

不要用真实 task 的 gold、另一 arm 或文件名提示完成 witness。失败不得免费重试。

### 10.5 运行新的 live-local 16-unit smoke

只有用户重新批准 16 units 后执行：

```bash
python -m research.decision_evidence_audit.runner \
  --mode live-local \
  --tasks env001,env025 \
  --run-id <new-unique-run-id> \
  --local-model-url http://127.0.0.1:8045 \
  --local-model-name Qwen3-VL-8B-Instruct \
  --max-model-calls <approved-model-call-ceiling> \
  --max-browser-transitions <approved-browser-transition-ceiling> \
  --prefix-max-model-calls 12
```

runner 会拒绝非 loopback URL、split 外或重复 task、超过 160/800 的 ceiling，以及不健康 endpoint。它不会自动启动模型。

不要根据 env001/env025 的结果换模型、改 prompt 或选择“表现最好”的 endpoint；这两个任务只是 chain smoke。

### 10.6 验证、报告和停止

```bash
python -m research.decision_evidence_audit.validate_run \
  research/decision_evidence_audit/runs/<new-unique-run-id> \
  --write \
  --require-complete-submission
```

报告至少包括：

- exact model path/revision、环境版本、GPU、seed/decoding；
- model calls、HTTP attempts、image counts/tokens、browser transitions；
- 所有失败/重试/重放；
- 16 个 unit 的 checkpoint/replay/POST/receipt/confirmation/score；
- isolation validator 与 source fingerprint；
- 明确标记 `engineering chain smoke`，不得把 16 units 当作方法有效性结论。

完成后停止并只终止本轮自己启动、PID 已记录的服务。不要自动进入 stage-three pilot。

## 11. 需要新 Codex特别警惕的事项

- 不要覆盖历史 run；每次使用新的 run ID。
- 不要复用旧 run 的 16/16 success 作为能力证据。
- 不要让模型看到 raw task object；在线输入必须从 public allowlist 构造。
- 不要把 API key 放进命令参数或错误回显。
- 不要把模型 backend 的内部 retry 当成一次调用；本协议要求每次真实 attempt 计预算。
- 不要使用 Browser Back 恢复状态；必须 fresh page + physical replay。
- final submit 不可逆，只尝试一次；若 receipt 已产生但 ack 失败，不得重复 POST。
- clean condition 不自动等于当前选择正确，official condition 也不自动等于当前选择错误。
- 测试通过只证明工程链路，不等于研究假设成立。

## 12. 新 Codex完成 live smoke 后应返回

1. 目标服务器与 GPU preflight 证据；
2. 实际模型、权重 revision、环境和服务启动命令；
3. 双图 witness 结果及预算计数；
4. 16-unit 实际命令、退出状态与运行时长；
5. validator 完整结果；
6. 每配置的调用/观察/修改/提交/outcome 汇总；
7. 失败和未完成单元，不能从分母删除；
8. 更新后的 `STAGE_REPORT.md` 和 `NEXT_ACTION.md`；
9. 明确回答是否仍停在 stage two；默认答案必须是“是”。
