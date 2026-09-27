# 阶段一：本地资产、数据流与权限审计

## 最新状态：2026-09-07 12:22 UTC，四条已真实运行

GPU0共享许可已明确适用于本对话后续进程。本轮四条均已尝试：b011两臂反复改选、8调用内未提出提交；env027两臂正确选择并由B0原样真实提交。24次真实模型调用/36浏览器动作，加既有mock后累计28/40调用事件、45/160动作。没有补跑或扩大实验，自己的Qwen服务已释放。

当前自然错误的提交前checkpoint为0；不以b011中途选错冒充提交前错误。49项回归与212项工件检查通过，但新fresh子Agent因额度错误未执行，独立审查ERROR/unavailable。此前未运行/资源阻塞说明与旧检查、旧mock审查均为历史，不覆盖当前结果；父目录before-live副本保留原预算/summary。

[真实运行报告](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/STAGE_REPORT.md) · [逐样本轨迹](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/CASE_REPORT.md) · [当前停止点](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/NEXT_ACTION.md) · [实际命令](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/COMMANDS.md)。不要重跑已存在live_attempt的四单元。以下原文保留为历史记录。


## 当前补充：2026-09-07 四条自然轨迹的资源与工程检查

沿用已有Qwen权重/环境与release主路由适配，未安装或下载。两次只读主机查询GPU0被PID87116占用50569MiB/81559MiB，8045无服务，进程归属在当前命名空间不可见；本轮模型调用已获授权，但没有本轮与该新任务共用GPU的明确安排，因此0真实推理、0GPU服务启动。只执行一个单独标注的mock浏览器控制，4调用事件/9动作。

新增natural_prefix.py与6项测试，原runner/core/models/policies/safe_shell不改；48项回归通过。请求截图目录已在实际执行前中性化，完整原准备版本保留。模型每步只收到当前图/状态而非完整历史；实际Qwen处理图像尺寸仍未知。详见[本轮审计](runs/natural_prefix_20260907T0932Z/LOCAL_AUDIT.md)。

## 当前补充：2026-09-07 七候选网页资格，未使用模型/GPU

实际沿用benchmark_v2_open release spec、原图与既有safe-shell，7任务×2条件完成14次真实提交，98次浏览器transition。没有调用Qwen或启动/停止GPU服务。原runner/core/safe_shell/任务/图片/旧结果未改；仅新增资格脚本、4项测试及独立run工件，之后修复离线来源记录的field_id键。原运行记录保留并附更正侧文件。

额外只读调用原shell选项/评分函数，识别b012原runtime六项与release三项差异；并确认不能仅凭raw required字段判定三个legacy任务在原runtime会配套字段失败。实际流程与版本限制见[本轮审计](runs/web_qualification_20260907T0801Z/LOCAL_AUDIT.md)，下文设备与授权状态属于历史轮次。

## 当前补充：2026-09-07 共享授权后已执行

冻结24单元已在用户批准共用的GPU0完成；实际模型BF16 Qwen3-VL-8B，自己服务已关闭，未触碰其他任务。累计25调用/140动作。最新设备、权限和源码记录见[本轮审计](runs/frozen_panel_20260907T015908Z/live_20260907T0307Z/LOCAL_AUDIT.md)；以下历史显存/运行状态不代表当前。


## 最新核验：20260906T1342Z，B3修复后重跑

已沿用用户授权的物理GPU0和现有Qwen3-VL-8B-Instruct，重新完成唯一16单元真实smoke。启动前GPU UUID/显存/进程/端口原始查询、独立CUDA witness、health、实际server/client副本均保存在 `revisions/20260906T1342Z/`，不下载、不安装、不触碰其他卡。结束后自启服务关闭，GPU0回到3 MiB、8045无监听。数据、原runner、safe-shell与scorer未修改；只修B3接口/计数及相应测试。

本轮33个benchmark请求与6个真实合成控制请求均实际调用Qwen，不再有模型未运行的资源阻塞。在线隔离、恢复、真实POST工程检查通过，但两组真实小控制各失败一项：分别为公开规则反转、reason与option_label矛盾。不能把它们当作全部通过或研究残余难题已确认。env001规则阈值歧义仍在；env025正确终局伴随错误参考线理由仍需区分。

完整范围、模型、逐样本与限制见 [最新报告](revisions/20260906T1342Z/STAGE_REPORT.md)。以下时间性描述均为历史，不覆盖本节。

## 最新资源核验：20260906T1219Z，用户授权 GPU 0 后

本轮已复用现有 Qwen3-VL-8B-Instruct 权重与 qwen3_vl 环境，成功启动回环服务并完成真实模型 smoke；不再是“无已授权可用服务”。第 0 张物理卡是 H100 80GB，启动前 3 MiB，无计算任务；其他 GPU 未使用。模型加载、独立 CUDA witness、双图真实推理均成功，无安装、下载或付费 API。实验结束后仅关闭本轮自启服务，GPU 0 回到 3 MiB，8045 释放。详见 [本轮报告](revisions/20260906T1219Z/STAGE_REPORT.md) 和同目录 health.json、ENVIRONMENT_WITNESS.md、gpu_released.csv。

数据/在线投影/safe shell/scorer 继续用本地既有版本，没有根据本轮结果改原数据或在线实现。此前正文与旧“未运行”记录保留为历史，不适用于这次获授权运行。

## 本次增量审计：2026-09-06，16:30 开始（北京时间）

本节对应用户最新执行指令；分隔线以下是进入本次前已有的历史正文，原样保留，不应把其中“本轮”视为本次新运行。

- 当前根目录为 `/mnt/data/lys/CognitiveHijacking_CognitiveDenial`；已先完整读取执行单与适用 AGENTS.md。代码和报告改动限于本研究目录，另按审查技能记录 `.aris/traces/`；修改前源文件与四份报告备份在 `revisions/20260906T0830Z/original/`。未覆盖旧 runs、数据、原 runner 或其他用户修改。Git 可用但无可验证 HEAD，rg 可用；旧文档所称“Git/rg 不存在”不适用于当前机器。
- 重新执行 release 自带校验及新增只读清单脚本：140 official + 140 clean + 40 real-world，320 实例、180 case、797 资产，缺失 0；配对主键齐全，所审非图表字段完全相同的仅 114 对。最新机器证据为 `revisions/20260906T0830Z/local_assets_verified.json`；初稿 `local_assets.json` 的图类型字段误用了 chart_type，保留但作废，以读取真实 plot_type 的 verified 版为准。
- 原环境入口复核：`web_agent_benchmark/evaluation/run_environment35.py` 与 `environment_energy_shell/environment_shell_app.py`。原表单可显示 mechanism/readiness、companion correct_value，原 prompt 要求已选后立即提交。因此保留既有白名单 safe_shell 适配，而非直接调用原 runner；这不是原 benchmark 页面/布局的逐像素复现。
- 本次实际链路：release spec → public_task_projection（公开标签排序）→ task/dashboard/form → 截图与可见控件 → ScriptedMockBackend → 第一次提交提议 checkpoint → 新浏览器 context 重放同一前缀 → B0/B2/B3/B4 → 同一 executor → 真实 POST → confirmation → 离线 score_receipt。当前状态和历史 dashboard 均有截图；form 内仍显示图表；finish 不会执行 POST。评分器是适配层终局评分，不冒充完整原生 benchmark scorer。
- 当前默认 Python 缺 Flask/Pillow/Playwright；已验证并复用 `/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python`。已装 Playwright 1.59.0、Flask 3.1.3、Pillow 12.2.0、requests 2.33.1。浏览器与解包动态库在 `/tmp/decision_evidence_pw_browsers`、`/tmp/decision_evidence_pw_runtime`，无新安装或下载。
- 只读检查本机 listener 与进程，既有 8045 服务不存在，curl /health 为 connection refused。真实模型结果：**未运行**。没有重启模型、外部付费 API、读取密钥内容或使用 GPU。旧 07:30 UTC 的 Qwen run 只作为历史工件，不计为本次新结果。

候选任务的在线可核验性（运行结束后查看本次实际 dashboard 截图；没有据此产生被测 Agent 输出）：

| 开发任务 | 当前可见证据和限制 | 资格说明 |
|---|---|---|
| env001，折线/尺度 | 截图提供 2005–2014 年点值/坐标；误导图压缩变化外观，clean 图跨度更明显。目标用 large enough/ordinary，没有公开数值阈值，clean 纵轴单位也较弱 | 仅工程开发；不能把分歧直接归因于观察选择，正式语义诊断前需明确规则或更换有清晰规则的开发任务；不改原数据 |
| env025，柱图/注释 | 用户规则明确以图中展示的月总数为依据。三个柱值关系与 Average 线可交叉核对；两个条件都能看到全部三个柱及坐标 | 可作开发用可见平均关系诊断；不需要或允许读取全年隐藏数据。两个 arm 的排版、图内占比不同，应作为图像质量差异报告 |

在线模型只收白名单文本/控件、它实际观察的截图及截图裁剪；条件、pair/gold、原 CSV/HTML 源数据、人工框都不送入模型。隐藏字段交换已覆盖页面字节、四策略请求和分支结果不变、终局评分可变。扫描只证明已覆盖路径；白名单进程隔离不是操作系统级恶意代码沙箱。

---

审计日期：2026-09-06（Asia/Shanghai）  
执行范围：`Codex_MisVis_Direction1_Research_Brief.md` 的阶段一，以及阶段二实现所需的最小接口核验。

## 结论摘要

本轮可复用的主要数据面是 `web_agent_benchmark/benchmark_v2_open/`，但它的 manifest 状态是 `open_release_candidate`，许可证仍待项目所有者确认。它确有 140 个 synthetic pair、40 个 real-world case 和完整的便携资产；不过本轮逐字段核验发现，140 对中只有 114 对满足所审字段的“只改图表、任务/动作/评分不变”。因此后续配对实验不能把 140 全部直接视为强 chart-only pair。

原四类 runner、shell、模型客户端、scorer 和测试均已定位。原 shell/runner 不适合直接承担本轮在线隔离：页面会暴露机制/readiness 或部分 `correct_value`，middleware 还能改写 `finish`/重复动作；旧 paired supervisor 还可能清理同名输出并自动启动 GPU 服务。因此本轮没有改写它们，而是在 `research/decision_evidence_audit/` 增加一个单任务、安全白名单的薄适配层。

本机审计时没有正在监听且可确认已获本轮授权的本地模型服务。历史 endpoint、已有权重、旧成功日志和一个无法确认所有权的 GPU 进程均不构成本轮授权；真实模型 smoke 因而未运行。

## 证据等级

本文统一区分：

- E0：执行单/论文中的记载，未由本轮独立核验。
- E1：旧 manifest、旧报告或旧 run 的记载。
- E2：本轮直接读取代码、JSONL 和资产所得静态事实。
- E3：本轮 deterministic/injected test。
- E4：本轮脚本 mock + 真浏览器/HTTP 的集成 smoke。
- E5：真实模型 smoke；本轮缺失。
- E6：pilot；本轮未运行。
- E7：研究假设证据；本轮没有。

除非另有说明，下面的资产与代码结论为 E2。

## 数据版本和入口

| 本地路径 | 身份与规模 | 可复用性/风险 |
|---|---|---|
| `web_agent_benchmark/benchmark_v2_open/` | `release_version=2026-07-07`，`status=open_release_candidate`；140 official + 140 clean + 40 real-world；180 case、320 task instance、797 个引用资产 | 本轮主数据面；相对路径便携。不是已经确认许可证的正式公开版。 |
| `web_agent_benchmark/official_benchmark_v1/` | 2026-05-11 的 140-task official 来源 | task 中仍有机器绝对路径；open release 是其便携封装。 |
| `web_agent_benchmark/clean_benchmark_v1/` | 2026-05-16 的 140-task clean 来源 | 语义与 open clean 对齐；含旧 clean runner。 |
| `misvisagentbench-demo/` | 12 pair + 8 real-world，32 instances、72 assets | 仅 demo；其中也包含已知非强配对案例，不能替代全量。 |
| `web_agent_benchmark/benchmark_v2/` | 只有 `pub011` 的专项版本 | 名称近似但不是 140-pair release。 |
| `clean_datasets/` | 配对构造工作区，含图、部分 CSV/HTML 和构造材料 | 不是在线任务真源；不得把其中 raw data 提供给 Agent。 |
| `review_all_for_clean_pair/` | 2026-05-12 的 reviewer bundle | 相对当前 task files 已陈旧。 |
| `baseline/MisleadingChartQA-main/`、`baseline/visDeception-main/` | 数据构造源池 | 不是可直接执行的 benchmark。 |

Open release 的关键入口：

- task specs：`web_agent_benchmark/benchmark_v2_open/splits/{official140,clean140}/{public39,business47,environment35,health19}_tasks.jsonl`
- real-world specs：`web_agent_benchmark/benchmark_v2_open/splits/real_world40/tasks.jsonl`
- task index：`web_agent_benchmark/benchmark_v2_open/metadata/all_tasks_index.jsonl`
- asset index：`web_agent_benchmark/benchmark_v2_open/metadata/asset_manifest.jsonl`
- release validator：`web_agent_benchmark/benchmark_v2_open/scripts/validate_release.py`
- release manifest：`web_agent_benchmark/benchmark_v2_open/benchmark_manifest.json`

Release validator 实际输出为：

```text
Benchmark v2 Open validation passed
official140=140 clean140=140 real_world40=40
task_instances=320 case_uids=180
asset_manifest_rows=797 unique_assets=797
```

Demo validator 实际输出为：

```text
MisVisAgentBench demo validation passed
paired_pairs=12 real_world=8 instances=32
assets=72
```

这两个 validator 会检查其声明的 ID/文件/arm 内 action 自洽项，但不会证明所有跨 arm 非图表字段不变，也不会补上 open asset manifest 中为空的 SHA-256。

## 配对与任务质量

对 140 个 official/clean pair 比较任务、目标、图表说明、ground truth、intermediate decision、主动作、伴随动作、action space、expected/misleading IDs、fallback scoring 和 completion action：

- 114/140 对在这些非图表字段上相同。
- 26/140 对存在差异：`b017`–`b034`、`health006`–`health013`。
- 差异计数：`ground_truth` 26、`primary_action` 26、`action_space` 26、`workflow_instruction` 22、`intermediate_decision` 22、`expected_action_id` 22、`chart_reference` 4。
- 这 26 对正好覆盖全部 cherry-picking case，所以强 chart-only 114 子集中没有 cherry-picking。

旧 `web_agent_benchmark/evaluation/gui_reflection_baseline/task_sets/manifest.json` 也记录：

| 派生集合 | 数量 |
|---|---:|
| full140 | 140 |
| chart_only114 | 114 |
| readiness95 | 95 |
| strict_review94 | 94 |
| smoke17 | 17 |

其他质量 caveat：

- 当前 task rows 的 readiness 实际是 63 `formal_scored_task`、19 `image_only_draft`、58 缺失/legacy；旧 official manifest 写成 62/20/58。
- `pub008` 的 `action_space[].scoring_outcome` 为 null。
- 19 个 draft 中有 12 行使用 draft/待确认角色。
- strict94 没有 dual-axis；readiness95 中唯一 dual-encoding `env032` 又因 `gt_uncertain` 被 strict 集排除。阶段三不能为了凑类别隐瞒这一覆盖缺口。

### 正确动作位置侧信道及修复

本轮发现 official140 和 clean140 都是 140/140 行将 `expected_action_id` 放在原始 `action_space[0]`。这会让“永远选第一项”在不看图时得到满分，是明确的信息边界失败场景。

阶段二 safe shell 因此使用只依赖公开 label 的大小写无关字典序，且只接受 label 集相同的强配对任务。它不读取 gold；提交后 evaluator 再按唯一 label 映回 raw action。对 chart-only114，排序后的正确位置为 index 0/1/2 = 22/60/32，两个 arm 完全一致。该改动是必要协议适配，不是原 runner 的字节级复现。

## 资产核验

| Split | Figure | CSV | HTML | Figure 格式 |
|---|---:|---:|---:|---|
| official140 | 140 | 120 | 97 | 120 JPEG + 20 PNG |
| clean140 | 140 | 120 | 140 | 140 PNG |
| real_world40 | 40 | 0 | 0 | 21 JPG + 17 PNG + 1 GIF + 1 WebP |

- 797 个 manifest 引用文件全部存在，引用集合与 manifest 一致。
- 320 张图均能由 Pillow 解码；240 个 CSV 均可解析且非空；237 个 HTML 均非空。
- 没有独立 SVG。`svg_playwright` 是部分 clean 图的渲染方式，交付资产仍是 PNG。
- 只有 120/140 个 pair 有 CSV；不能假定每项都有原始数值表。
- CSV/HTML 即使存在也属于离线权限，B4 只从在线已见图像自行提取。
- 140 对中只有 25 对 source figure 像素尺寸相同，115 对不同；裁剪预算只能基于实际浏览器截图，不能免费裁 evaluator 原始高清图。
- 两个 smoke pair 的 source 尺寸也不同：env001 为 3420×2784 / 1385×1036，env025 为 1200×900 / 1120×908（official / clean）。
- Open release asset manifest 的 `sha256` 值全部为空；“本轮文件存在/解码检查通过”和“已有加密摘要验证”必须区分，后者不存在。

Plot 分布是 line 53、bar 32、scatter 28、choropleth 15、pie 8、stacked bar 3、area 1。Misleader 分布是 annotations 34、cherry-picking 26、unconventional scale directions 19、inappropriate scale functions 17、visual disproportion 15、inappropriate scale range 12、dual encoding 12、dual-axis 2，以及三个各 1 的小类。

## 网页、runner、scorer 与完整数据流

原始执行入口：

- `web_agent_benchmark/evaluation/run_public39.py`
- `web_agent_benchmark/evaluation/run_business47.py`
- `web_agent_benchmark/evaluation/run_environment35.py`
- `web_agent_benchmark/evaluation/run_health19.py`
- `web_agent_benchmark/evaluation/run_official_benchmark140.py`
- `web_agent_benchmark/clean_benchmark_v1/run_clean_benchmark.py`
- paired supervisor：`web_agent_benchmark/evaluation/run_pair_benchmarks.py`

对应 shell 位于 `public_benchmark/`、`business_shell/`、`environment_energy_shell/` 和 `health_shell/`。本轮追踪到的原流程为：

```text
raw task JSON
  -> shell 将 chart 与 task/dashboard/form 页面渲染
  -> runner 截图并构造可见状态
  -> 模型提出 browser action
  -> policy middleware
  -> browser executor
  -> 真正的 form POST
  -> server receipt / 隐藏 evaluator
  -> confirmation
```

关键行为：

- 最薄的 before-submit 插点在 middleware 之后、`execute_browser_action` 之前。
- 原模型通常提出 `click_button("Submit Form")`；executor 也接受 `submit_form`。
- `finish` 只退出 agent loop，不等于业务 POST。
- 真正 POST 后页面跳至 confirmation；隐藏 evaluator 结果不应再进入模型回合。
- 原 form 中图表仍可见。
- Browser Back 不是业务撤销，也不可靠恢复 `<select>` 的 DOM 状态；本轮使用新 page + 真实动作前缀重放。
- 原 middleware 可能把 `finish`/重复动作改写成提交，不能用于本轮中性 B0–B4。
- 原 prompt 有“信息足够后不要反复 dashboard”的倾向，与通用主动视觉核验冲突；阶段二使用统一的中性 prompt。
- 原 environment/health 页面会显示 mechanism/readiness；部分 shell 会渲染 companion `correct_value`。因此没有直接把 raw task object 交给新 controller/shell。

阶段二适配后的流为：

```text
offline raw task + chart path
  -> public-field allowlist + opaque task alias + neutral label sort
  -> agent-safe task/dashboard/form
  -> screenshot + allowlisted DOM state
  -> RecordedModel request
  -> first visible semantic-submit proposal
  -> checkpoint（尚无 POST）
  -> fresh page + physical prefix replay + state/screenshot equality
  -> B0/B2/B3/B4
  -> shared executor（含 selection postcondition）
  -> real HTTP POST + public receipt + confirmation
  -> separate offline score_receipt(raw task, receipt)
```

这里的“真实提交”指 agent-safe shell 上发生真实 HTTP POST、写入 receipt 并到达 confirmation，不等于在原 benchmark shell 上生成的官方分数。B0 也应准确称为“新中性协议下的零额外核查参考”。

## 在线与离线权限

在线 allowlist 在 `manifests/online_manifest.json`；离线字段和任务映射在 `manifests/researcher_manifest.json`。

| 在线 Agent 可见 | 仅离线 researcher/evaluator |
|---|---|
| user goal、page title、chart reference、可见 option labels、可见 DOM 文本/控件、去 host 的 URL path、已实际观察的截图/允许 crop、自己的历史输出 | raw task/case/pair/condition ID、mechanism、ground truth、expected/misleading action IDs、role/scoring、另一 arm、CSV/HTML/raw source data、source path、terminal score |

实现采用白名单重建，而不是黑名单删字段：

- model request helper 对嵌套 key 再做 forbidden-key 检查；
- URL 只保留 path，不保留 host/port；控件只保留 label/text/selected 状态，不保留 opaque value token；
- 图像先由当前浏览器截图保存到不含 condition/task slug 的 `online/` 别名路径；
- scorer object 不进入 Flask app 或 controller；只有 POST 完成后由 runner 离线调用；
- evaluator 的 unit map、pair identity 与 score 写在 `evaluator/`，不回流在线分支。

测试与工件扫描未发现所检查的 hidden key、task-specific hidden string、condition/source path 或图像 metadata 泄漏。这是覆盖范围内的 E3/E4 结论，不是“全系统无泄漏”的证明。

## 两个阶段二开发任务的在线可核验性

任务来自 `environment35_tasks.jsonl`，选择依据是 formal readiness、强 pair invariant、不同 plot/mechanism 类型和公开可见证据；没有依据方法输出或 gold 位置筛选。

| Alias | Raw slug | 类型（离线） | 在线可见依据与限制 |
|---|---|---|---|
| dev01 | env001 | line；inappropriate scale functions | 两 arm 的期间趋势和数值在图上可见；无 raw CSV 输入。目标中的 “large enough” 没有显式数值阈值，仍有轻度任务规则模糊性。 |
| dev02 | env025 | bar；misleading annotations | January 与三个月柱高关系可见，可从可见关系核对相对平均；隐藏的精确平均值和 CSV 不可提供给模型。 |

两项只足以作为开发 smoke，不足以判断真实模型是否能读图，也不代表机制类别覆盖。

## 模型服务、权限和安全

定位到的模型相关入口包括：

- `adversarial_pipeline/llm_client.py`
- `web_agent_benchmark/evaluation/qwen3_vl_server.py`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/agent_runtime.py`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/model_server.py`
- `web_agent_benchmark/evaluation/gui_reflection_baseline/run_agentic_recovery_baselines.py`

审计时：

- TCP listener 列表为空，已知 loopback 端口健康探针没有可用服务；
- 模型 endpoint/credential 环境变量未形成一套可用且本轮授权的配置；
- 历史 Qwen3-VL-8B 服务已停止；权重存在不等于获准启动 GPU；
- 历史 Kimi/AIME/远端结果不构成本轮付费或网络调用授权；
- `run_pair_benchmarks.py` 的部分 preset 会在服务缺失时自动占用 GPU 4–7，因此本轮未调用它；
- 一个无法确认所有权且无 listener 的 VLLM EngineCore 进程未被使用或终止。

安全发现：项目 `.claude/settings.json` 含明文 AIME credential literal，审计时权限为 0644。本轮没有读取其值、没有复制到报告、也没有使用。建议所有者轮换该凭据，将其移出仓库型配置并收紧文件权限。

## 测试入口与历史结果边界

现有 GUI baseline 回归入口：

```bash
python -m unittest discover \
  -s web_agent_benchmark/evaluation/gui_reflection_baseline/tests \
  -t . -v
```

本轮实际结果：186 tests，OK，2 skipped。它证明旧测试覆盖项没有在本轮静态环境中回归，不证明新协议或研究假设成立。

2026-09-01 的 3-task/6-state/42-cell GUI reflection 工件属于 evaluator-owned takeover 探针，SRC/ExACT/MobileUse 名称也不是三个官方系统的完整复现；本轮只借鉴工程结构，不并入新 smoke/pilot。

## 明确缺失或未知

- 没有本轮可确认授权且正在运行的真实视觉模型服务；E5 为“未运行”。
- Git 可执行文件缺失，`.git` 是 unborn HEAD/no objects；无法声称 clean worktree 或给出 commit。每个新 run 改用运行时 source fingerprint。
- `rg` 不存在，检索回退到 `find`/`grep`。
- 少数旧 delegation report 路径无读取权限；它们不是已定位核心 benchmark 根，但全工作区穷尽性带此限制。
- Safe-shell scorer 已覆盖当前单选任务与真实 receipt，但尚未证明等价于所有原 shell 的全部 companion-action/scoring 语义。
- B1、B5、stage-three runner、12-task split、pilot 和候选视觉选择机制均未实现/未运行。
