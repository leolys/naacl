# 阶段一/二执行报告

报告日期：2026-09-06（Asia/Shanghai）  
停止点：阶段二真实本地模型 smoke 已执行并以 incomplete chain 停止；自启模型服务已关闭；未启动阶段三 pilot、140-pair 全量评测或阶段四机制。

## 1. 结果分层

| 层级 | 状态 | 本轮证据 |
|---|---|---|
| 本地资产/入口审计 | 完成 | 直接检查 release、task rows、assets、shell、runner、scorer、模型配置和测试入口 |
| before-submit/B0/B2/B3/B4 接口 | 已实现 | 当前 source + deterministic/unit tests |
| 信息隔离/重放/真 POST 工程链路 | 部分真实验证 | env001 两个条件的 8 units 完成严格重放与真提交；env025 两个前缀未到 checkpoint，8 units 原样留在分母 |
| 获批的 16-unit live-local grid | **已尝试、链路不完整** | 16/16 终局工件；2/4 checkpoints，8/16 completed chains，另外 8 个为 `not_run_no_checkpoint` |
| 真实模型链路 | **已运行** | GPU 0 上本地 Qwen3-VL-8B-Instruct；41/160 calls、95/800 browser transitions；服务随后关闭 |
| Stage-three pilot | 未运行 | 未获批准；split 尚未 materialize |
| “简单基线是否足够” | **未评估** | 只有一个 base task 到达 checkpoint，且 smoke 不是研究比较 |
| 新观察选择机制是否需要/有效 | **未评估** | 阶段四未启动 |

本轮安全结论只有：本地 learned-model、多图请求、浏览器、提交前分叉、严格重放、真实 HTTP 提交、失败保留和离线评分能够连成链路；同时暴露出一个阻断 env025 前缀的通用 tool-schema/字段映射问题。该 smoke 不支持 B2/B3/B4 方法效果或新机制必要性的研究结论。

## 2. 实际代码与配置改动

所有新增内容都位于 `research/decision_evidence_audit/`；未改原 task data、chart assets、旧 runner、旧实验结果或 `AGENTS.md`。

| 文件 | 作用 |
|---|---|
| `core.py` | 在线公开字段投影、隐藏 key guard、neutral option sort、预算 ledger、公开 browser state、首次 submit hook、checkpoint |
| `safe_shell.py` | 只接收 public task + 当前 chart 的 agent-safe task/dashboard/form；真实 POST receipt；独立 label-based offline scorer；表单控件使用确定性直角边框 |
| `models.py` | 调用前记账/请求记录、响应/异常记录、脚本 mock、loopback Qwen client、多图输入及服务协议/像素/加载元数据 |
| `policies.py` | B0/B2/B3/B4；B2 独立首判；B3 最多两次 crop/三次调用且累计多图；B4 图像自提取 |
| `runner.py` | 固定 development split 与 2×2×4 限制、自然前缀、before-submit 分叉、物理 replay、共享 executor、严格截图 SHA、确定性 Chromium 参数、单调用有序双图 witness、失败分母 finalizer、offline scoring |
| `validate_run.py` | 普通失败保留模式和严格 complete-smoke 模式；grid/预算/receipt/replay、提交与终局评分一致性、online keys/hidden inputs/image boundary、witness 和运行时 provenance 审计；只豁免可逐字追溯到同 unit 先前 B4 extraction 响应的模型历史 |
| `tests/test_core.py` | projection/hook/baselines/crop/budget/retry/path/排序/提交边界/witness/模型历史审计/清理/失败终局等 deterministic tests |
| `tests/test_browser_integration.py` | 真浏览器、真 HTTP POST、重放、B0、可见像素改选与正确不改、非法空提交、prefix backend failure |
| `manifests/online_manifest.json` | 在线白名单与中性排序声明 |
| `manifests/researcher_manifest.json` | 离线 release/开发 task/隐藏字段/协议适配映射 |
| `manifests/split_manifest.json` | 仅 materialize 两个 stage-two development pair；holdout 为空 |

live run 当时 executable source/tests/manifests 的 tree fingerprint（13 files）为：

```text
a7197316760cc000c4445c5ab3512d191baceb4422f97aa510f60566c58109e7
```

live run 后修改了 `validate_run.py` 及其 `tests/test_core.py` 测试，用于修正 B4 模型历史的审计归类；最终浏览器复核又在 `safe_shell.py` 将 select/textarea 圆角改为直角，以消除已复现的 7-pixel、最大通道差 1 的边框抗锯齿漂移。没有改变 runner、模型、策略、manifest 或既有 run 的 online/receipt/score 工件。当前 13-file tree fingerprint 为 `dd022753252c5e2fa850fc407953a71493acbef454e4edd94807c41b31b9a406`。Git executable 缺失且 `.git` 是 unborn HEAD/no objects，故不能提供 commit、clean-worktree 声明或完整 repository diff。这些 fingerprint 只覆盖本适配层的 `.py/.json/.jsonl`，不建立长期发布 gate。

## 3. 实际执行命令与结果

### 3.1 数据 validator

```bash
python web_agent_benchmark/benchmark_v2_open/scripts/validate_release.py
python misvisagentbench-demo/scripts/validate_demo.py
```

结果：open release validator 通过（140/140/40、320 instances、797 assets）；demo validator 通过（12 pairs、8 real-world、32 instances、72 assets）。这些 validator 不覆盖本轮发现的 26 个非强配对问题。

### 3.2 原 GUI baseline 回归

```bash
python -m unittest discover \
  -s web_agent_benchmark/evaluation/gui_reflection_baseline/tests \
  -t . -v
```

结果：`Ran 186 tests in 6.233s`，`OK (skipped=2)`。

### 3.3 新适配层静态/单元测试

```bash
python -m py_compile \
  research/decision_evidence_audit/*.py \
  research/decision_evidence_audit/tests/*.py

python -m unittest discover \
  -s research/decision_evidence_audit/tests \
  -t . -v
```

最终复核结果：py_compile 通过；`Ran 28 tests`，`OK (skipped=1)`。唯一 skip 是默认关闭的 Playwright 集成测试，因此实际执行 27 个 deterministic tests。

覆盖项包括：

- hidden label/gold 互换不改变 public projection 或 HTML，但 offline score 可改变；
- nested evaluator key 被 online request guard 拒绝；
- 所有 current selection 状态同样触发，`finish`/普通按钮/无可见 submit 不触发；
- B0 零调用/no-op；B2 首判不含 current selection；
- B3 可走 2 次 crop、3 次调用，收到图像数为 2→3→4；
- crop 保留注入的 axis/legend 像素；
- 可逆 click 失败和 selection silent no-op 都被检测、计数并重试；
- final submit 可显式禁止重试；
- path containment 要求 task path boundary；
- gold-first raw order 被公开 label sort 隔离；
- 健康检查失败会关闭 session 和临时 shell；非法/重复 development task 在创建 run 目录前拒绝；
- POST 后 page-close 异常不覆盖 receipt/result，缺失 confirmation 与重复 receipt 分别保留为 ack/duplicate failure；
- checkpoint 后的明确 early unit failure 不需要伪造 replay 成功证据；
- 注入 browser-startup failure 后仍保留 4 prefixes、16 units、score exclusions、0/0 budget 和 manifest，普通 validator 通过。
- live-local 必须先用同一 backend、同一 budget ledger 做恰好一次有序双图 witness；图像数或内容不符时在 episode 前失败；
- B4 decision 中的字符串只有在逐字来自同 unit 的先前成功 extraction 响应时才归为允许的模型历史，缺少该响应仍判 hidden-input leak。

### 3.4 真浏览器 injected controls

```bash
RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
python -m unittest \
  research.decision_evidence_audit.tests.test_browser_integration -v
```

最终复核结果：首次沙箱内执行因禁止监听回环端口而报 `PermissionError`；按权限流程批准本机回环监听后，最终 `Ran 1 test in 19.705s`，`OK`。Chromium 147 的复核曾在公开 state 完全相同时，于 textarea 左下圆角产生 7 个像素、最大通道差 1 的漂移；`--disable-gpu` 单独不足以稳定消除。Safe shell 将 select/textarea 的纯装饰圆角改为直角后，同一 checkpoint 连续 8 次为 8/8 SHA 完全一致，完整 browser test 随后通过。图表、布局语义和严格 screenshot SHA 门槛均未放宽。

一个 test method 内实际核验：

- hook capture 时 server receipt 仍为 0；
- fresh page 物理重放与 checkpoint state/screenshot 一致；
- B0 真 POST 原选择；
- 明确的 magenta/orange 可见像素规则驱动 B2 从 Route A 改为 Route B，旧 submit proposal 标 cancelled，实际 POST 为 Route B；
- 同一可见规则下已为 Route B 时 B2 不改坏，并真 POST；
- 空选择的非法控制仍真实提交为空并得到 `completion_failure`，没有被修成成功；
- prefix model exception 被计 1 call，保存错误 response 和 `prefix_result.json`，无 POST。

这是 injected deterministic visual control，不是 learned model 的图表语义能力证据。

### 3.5 16-unit 本地真实模型 smoke

工件：`runs/stage2_live_smoke_20260906T073005Z/`；服务日志：`service_logs/qwen3vl_20260906T073005Z.log`。

#### 环境与启动前证据

- 当前主机为 `interactive-vaga86sg7eby-6cd57f4bff-pkrzw`；`.aris/compute/` 不存在，因此没有可用的环境账本。
- 经主机侧只读核验，获批的 GPU 0 是空闲 NVIDIA H100 80GB HBM3；其他 GPU 的既有进程未触碰。固定 `CUDA_VISIBLE_DEVICES=0` 后，seed `20260906` 的 CUDA kernel witness 成功。
- 使用 `/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct` 的四个 safetensor shards，index 报告总大小 17,534,247,392 bytes。交接文件记录 revision `1610d9f98460d59272cd9963efdf92f0cd3c8dc9`；当前主机只可读到 `.mv` 的 `Revision:master`，精确 revision marker 权限不足，故本轮不能独立复核该 commit。
- 模型环境：Python 3.10.18、torch 2.8.0+cu128、transformers 4.57.1、accelerate 1.11.0、qwen-vl-utils 0.0.14。服务健康信息确认 `model_size=8b`、`max_pixels=1003520`、`native_multi_image=true`、协议 `2.0-native-multi-image`，加载 17.336 秒。
- 浏览器使用 Playwright 1.59.0；经用户许可，将 Chromium/headless shell 147.0.7727.15 下载到 `/tmp/decision_evidence_pw_browsers`，并只在 `/tmp/decision_evidence_pw_runtime` 解包所缺动态库，没有系统安装。
- fresh-agent follows-doc witness 的原命令在普通沙箱因 CUDA Error 304 失败；同一原命令在获批主机执行面通过，sentinel 为 `WITNESS (8, 8) NVIDIA H100 80GB HBM3 True -29.691481`。该差异归因于沙箱设备隔离，不计作目标环境失败。

服务只监听 `127.0.0.1:8045`。实际 smoke 命令为：

```bash
env \
  PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers \
  LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu \
  /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.runner \
  --mode live-local \
  --tasks env001,env025 \
  --run-id stage2_live_smoke_20260906T073005Z \
  --local-model-url http://127.0.0.1:8045 \
  --local-model-name Qwen3-VL-8B-Instruct \
  --max-model-calls 160 \
  --max-browser-transitions 800 \
  --prefix-max-model-calls 12 \
  --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell \
  --max-output-tokens 1024 \
  --temperature 0 --top-p 1 --seed 12345
```

run 从 `2026-09-06T07:41:41Z` 到 `07:46:40Z`，进程 exit code 为 0，manifest 状态为 `completed`，但语义状态为 `attempted_incomplete_chain_smoke`。

#### 同预算双图 witness

episode 前使用同一 Qwen backend 和同一 `BudgetLedger` 做一次有序双图调用：`panel_01.png` 是红色三角形，`panel_02.png` 是蓝色圆形。服务确认收到 2 张 512×384 图，返回：

```json
{"panel_1":{"color":"red","shape":"triangle"},"panel_2":{"color":"blue","shape":"circle"}}
```

witness 消耗 1 个模型调用、501 prompt tokens、26 completion tokens，耗时 2.286 秒。它证明本轮协议确实按顺序接收两张图，不证明后续任务判断正确。

#### 完整计数

| 项目 | 实际 |
|---|---:|
| Configured/finalized units | 16/16 |
| Before-submit checkpoints | 2/4 task-conditions |
| Completed chains / submitted units | 8/16 |
| Replay public state SHA / screenshot SHA | 8/8 / 8/8 |
| 真 POST / server receipt / confirmation | 8/8 / 8/8 |
| Model calls / HTTP attempts / successful responses | 41 / 41 / 41 |
| Automatic model retries | 0 |
| Browser transition attempts | 95（55 成功执行，40 失败） |
| Token usage | prompt 54,270；completion 2,237；total 56,507 |
| Model inference time sum | 55.163 秒 |
| Image inputs | 44（38 次单图请求，3 次双图请求） |

模型调用分解：witness 1、自然前缀 32、B2 2、B3 2、B4 extraction 2、B4 decision 2。B3 的两个已运行 unit 都直接判断，没有请求 crop，所以本轮没有三图或四图策略调用。

#### 逐 task-condition/config 结果

| Task | Condition | B0 | B2 | B3 | B4 |
|---|---|---|---|---|---|
| env001 | official140 | success | **misleading_failure** | success | success |
| env001 | clean140 | success | success | success | success |
| env025 | official140 | `not_run_no_checkpoint` | `not_run_no_checkpoint` | `not_run_no_checkpoint` | `not_run_no_checkpoint` |
| env025 | clean140 | `not_run_no_checkpoint` | `not_run_no_checkpoint` | `not_run_no_checkpoint` | `not_run_no_checkpoint` |

env001 的两个自然前缀各用 4 次调用到达 checkpoint，8 个分叉均严格重放、单次提交且无重复 receipt/ack failure。B2 在 official140 中把原本正确的“substantial-change follow-up”改为 routine monitoring，产生唯一一个 `misleading_failure`；clean140 没有改坏。由于只覆盖一个到达 checkpoint 的 base task，这个观察不能外推为 B2 的方法结论。

env025 的两个自然前缀各用满 12 次调用仍未到 checkpoint。模型每次都选择了语义上正确的 option label，却把可见字段标题 `January alert-load routing decision` 写入 `select_name`；实际公开 DOM state 已给出机器字段名 `primary_action`。Executor 按既定 schema 查找 `name/id`，每个高层动作的两次 5 秒尝试均超时：每个 condition 10 个 `action_failure`、20 个失败 transition，最终为 `prefix_model_call_limit`。因此对应 8 units 以 `no_before_submit_checkpoint` 留在分母，没有伪造 replay 或提交。

这是当前首要的执行/tool-schema 映射阻塞，不是观察选择机制证据。按照预先约束，本轮没有根据 env001/env025 修改 prompt、切模型或重跑；获批的 16 units 已全部消耗。

#### 校验与停止

- 普通失败保留校验 `evaluator/validation.json`：`valid=true`、errors 为空；16 units、41 calls、95 transitions、8 receipts 全部对账。
- 完整提交严格校验 `evaluator/validation.strict.json`：`valid=false`，错误仅为 env025 的 2 个 clean-checkpoint 缺失和 8 个 unit 未提交，符合 incomplete-chain 事实。
- 信息隔离：115 个 online JSON、60 个 image metadata、41 个 model request、44 个 image references；forbidden online keys、hidden input values、image-boundary hits 均为 0。两处 `Global Temperature Change` 可逐字追溯到同 unit 先前的 B4 extraction 响应，属于允许的模型自身历史。修复前的首份严格校验保存在 `evaluator/validation.initial_strict.json`，未覆盖。
- 当前 validator 给出 provenance warning，因为 live run 后修正了 validator/相应测试，并对 safe-shell 控件做了纯装饰渲染稳定化；run-time fingerprint 和当前 fingerprint 均已保留。
- 任务结束后向本轮自建 tmux 服务发送定向 Ctrl-C；已确认 session/PID 消失、8045 端口释放、GPU 0 回到约 3 MiB。未终止任何他人进程。

### 3.6 16-unit 脚本 mock 工程演练（历史）

实际命令：

```bash
python -m research.decision_evidence_audit.runner \
  --mode mock \
  --tasks env001,env025 \
  --run-id stage2_mock_smoke_20260906T0206Z \
  --max-model-calls 160 \
  --max-browser-transitions 800 \
  --prefix-max-model-calls 12
```

工件：`runs/stage2_mock_smoke_20260906T0206Z/`。

该 run 是**修复前工程演练**：它发生在发现/修复 raw gold-first option order、B3 累计多图、真实 selection postcondition、时间字段和完整失败 finalizer 之前。目录名中的 `Z` 也误用了本地时刻；manifest 的 `started_at` 实际在 receipts 之后，不能把这些字段当可靠开始时间。原工件未覆盖写，保留用于审计。

原 run 生成 198 个文件；本轮随后只新增 `evaluator/validation.json`，当前共 199 个文件。

#### 逐 task-condition/config 结果

表格单元为 `offline outcome；policy calls/active ops；改选`：

| Task | Condition | B0 | B2 | B3 | B4 |
|---|---|---|---|---|---|
| env001 | official140 | success；0/0；否 | success；1/0；否 | success；2/1；否 | success；2/0；否 |
| env001 | clean140 | success；0/0；否 | success；1/0；否 | success；2/1；否 | success；2/0；否 |
| env025 | official140 | success；0/0；否 | success；1/0；否 | success；2/1；否 | success；2/0；否 |
| env025 | clean140 | success；0/0；否 | success；1/0；否 | success；2/1；否 | success；2/0；否 |

**这 16/16 success 完全不可作研究解释。** 当时 safe shell 沿用 raw action order，而两个 synthetic arm 的 140/140 task 都把 gold 放在第一项；scripted mock 也固定选第一可见项。所有策略均未改选，因而结果只是位置侧信道 + mock 规则。

#### 工程链路计数

| 项目 | 实际 |
|---|---:|
| Configured/completed units | 16/16 |
| Checkpoints | 4/4 |
| Capture 前/后 receipts | 每个 prefix 均 0/0 |
| Replay public state equality | 16/16 |
| Replay screenshot equality | 16/16 |
| 真 POST / server receipt / confirmation | 16/16 / 16/16 / 16/16 |
| Request/response pairs | 36/36，全部 `ok=true`、mock 标记 |
| Model calls | 36/160 |
| Browser transitions | 96/800 |
| Failed retries | 0 |
| Revision actions | 0 |
| B3 active crops | 4；每次 1440×880，占当时 1440×1100 screenshot 的 80% |

调用分解：自然前缀 16，B2 4，B3 8，B4 8，B0 0。Transition 分解：4 个自然前缀共 16；16 个 replay+submit 共 80。两个开发 pair 的所审 non-chart difference 均为空。

严格 post-hoc validator 命令：

```bash
python -m research.decision_evidence_audit.validate_run \
  research/decision_evidence_audit/runs/stage2_mock_smoke_20260906T0206Z \
  --write \
  --require-complete-submission
```

结果：结构/链路 `valid=true`、errors 为空；扫描 116 个 online JSON、72 个 online image metadata、36 个 model input requests 和 36 个 request image references，所检查的 forbidden keys、task-specific hidden strings、condition/source paths、image metadata 和跨 prefix/unit image reference 均为 0 命中。

Validator 同时给出 provenance warning：run 记录的 12 个 source files 中，当前有 9 个 hash 不同；当前还新增了当时未记录的 `validate_run.py`。因此该 run 只能代表它自己记录的旧代码，不能冒充当前最终实现的完整 smoke。

### 3.7 为什么当时没有重跑第二个 mock grid

首轮授权是**最多 16 个 mock smoke 运行单元**，不仅是 160 calls/800 transitions；所以修复后没有自行追加第二个 mock grid。之后用户另行明确批准了新的 16-unit live-local smoke 及 160/800 ceiling，才执行 §3.5。两次运行的授权和预算彼此独立，没有把后一次结果追写进历史 mock 工件。

## 4. 当前实现相对首轮 mock 工件的修复

首轮 mock 后，基于协议审计而不是 learned-model outcome 调参，完成：

1. raw gold-first 顺序改为 public-label-only 排序；chart-only114 的正确位置变为 22/60/32，而非 114/0/0。
2. Offline scorer 按唯一 visible label 映回 raw action，不再把新 token index 错当 raw index。
3. B3 支持最多两次主动观察，并在每回合显式携带 current+dashboard+累计 crops 的多图历史。
4. `submit_form` 只有当前 DOM 确有可见 submit 时触发 hook。
5. Executor 验证 selection postcondition；可逆失败重试计数。
6. 不可逆 final submit 只尝试一次；POST 已落 receipt 而 acknowledgement 失败时不重复提交。
7. Prefix/model/runtime failure 和 browser startup failure保留整个 planned grid、budget、exclusion 和 manifest。
8. Run manifest 分开记录 `started_at/completed_at`，且任何 smoke 都固定 `research_interpretation_allowed=false`。
9. 删除 prompt 中暗示存在另一 condition 的泛化措辞。
10. 提交后 page-close 异常不再覆盖成功 return；已有单 receipt 可由失败 finalizer 恢复并离线评分。
11. 重复 POST 单独记录实际 receipt 数并排除评分；已 commit 但缺 confirmation 的状态不再记为完整提交链路。
12. Shell health failure 会清理 session/server；非法 endpoint/task/重复 task 在创建 run 目录前拒绝，避免孤儿目录。
13. Validator 区分 checkpoint 后的早期 replay failure，并要求已提交状态有非空终局评分。
14. live-local 在 episode 前用同一 backend 和总预算执行一次有序双图 witness，失败即停止且不吞掉调用计数。
15. Chromium 固定 `--no-sandbox --disable-gpu` 并保留严格 screenshot SHA；最终复核证明该参数本身仍不足以消除所有圆角抗锯齿漂移，后续由第 17 项处理。
16. live run 后，validator 将 B4 decision 中可精确追溯到同 unit 先前成功 extraction 响应的文本归为模型自身历史；无可追溯响应仍判泄漏，并有正反测试。
17. 最终浏览器复核将 safe shell 的 select/textarea 装饰圆角归零；这是针对已定位的 7-pixel 栅格漂移，不是容差比较。focused replay 8/8、完整 opt-in test 1/1 通过。

第 1–15 项已进入 live run 的 runtime fingerprint。第 16 项只改变 post-hoc 审计归类，第 17 项只改变后续 safe-shell 控件装饰；二者都不改变既有请求、决策或结果。首份 validator 输出已另名保留；没有把修复追写进旧 manifest 或覆盖原始 online artifacts。

## 5. 真实模型结果的解释边界

真实本地 Qwen3-VL-8B-Instruct 链路已尝试，但不是完成的 16-unit chain smoke，更不是 stage-three pilot。env001 提供 8 个完成链路的工程样本；env025 的 8 个策略单元没有 checkpoint，不能用于策略效果比较。B2 的一次 damage、B3 的零 crop 和其余成功只能逐轨迹陈述，不能估计总体成功率、错误修复率、false-positive damage 或任何方法优劣。

本轮没有调用 AIME 或其他付费/远端 API，没有读取旧明文凭据，没有训练或下载模型权重，也没有占用/终止其他 GPU 服务。唯一网络下载是经批准取得 Playwright Chromium 运行包和缺失的公开系统库包。

## 6. 剩余阻塞与局限

- 第一阻塞是自然 Agent action schema 的字段映射歧义：模型把公开 select label 当成 `select_name`，而 executor 只按 DOM `name/id` 解析。必须先做与 task outcome 无关的通用接口修正和控制测试；不得把它包装成视觉机制改进。
- 本次 16-unit live budget 已使用；修正后如需再次证明 2×2×4 完整链路，必须由用户批准新的 units/calls/transitions，不能自动重跑。
- Safe shell/label scorer 覆盖当前单选开发任务，但尚未证明等价于所有原 shell 的 companion-action/scoring 语义。
- 两 arm source 尺寸普遍不匹配；真实模型结果需按实际 screenshot/image cost 报告。
- 26 个 cherry-picking pair 不是强 chart-only；严格子集又缺 dual-axis/dual-encoding 覆盖。
- 原生双图接口已经由真实模型 witness 与 B3/B4 请求实跑；但 B3 在两个可运行 unit 中没有主动 crop，因此累计 3/4 图的 learned-model 路径仍只有 deterministic 覆盖。
- 当前源码与 live runtime fingerprint 的差异是 post-hoc validator/测试修正及上述 safe-shell 圆角稳定化；任何未来运行仍应记录自己的 runtime fingerprint。
- 模型权重精确 revision 只能引用交接记录，当前主机没有权限独立读取 exact marker。
- B1、可核验的 B5、stage-three runner、12-task split、pilot 和 candidate 均未实现/未运行。
- Open release 许可证/第三方资产权限尚待项目所有者确认。
- 项目明文 credential 需要所有者轮换/迁出；本轮没有改变该配置。

## 7. 最终研究判断

`hypothesis_status = not_evaluated`。

测试与 live smoke 只说明所覆盖的工程链路，并定位了一个执行接口阻塞。不能从单个到达 checkpoint 的 base task、脚本 mock、旧 GUI takeover 结果或 deterministic control 推断 B2/B3/B4 的视觉能力；也不能据此决定开发新的决策相关视觉观察选择机制。Stage-three 仍明确未启动。
