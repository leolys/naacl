# 决策相关视觉核验协议（阶段二冻结说明）

状态：阶段二工程协议已实现；一次真实本地模型 smoke 已尝试但链路不完整；阶段三 pilot、阶段四候选机制均未运行。  
研究问题：在没有执行报错时，能否在业务提交之前发现并修正缺少可见证据支持的决策？  
瓶颈：在有限重观察预算下，找到足以区分不同行动的视觉依据。

这里的“冻结”仅指同一个 run 内的配置不变，不建立永久 contract/baseline/gate。后续只有经审批的新 run 才能更新协议版本。

## 1. 本轮研究边界

阶段二只比较 B0、B2、B3、B4，并只运行两个开发基础任务的两个图表条件。B1 和 B5 留到阶段三；决策相关观察选择候选只在简单方案留下明确残余问题后进入阶段四。

以下内容不属于本协议：前提账本、长程回滚、技能进化、训练基础模型、大搜索树、人工看着 gold 接管 Agent、140-pair 全量评测，以及把历史 42-cell takeover 结果并入本轮。

## 2. 实验单位与开发 split

当前 `manifests/split_manifest.json` 只 materialize：

- development：env001、env025 两个 chart-only pair；
- diagnostic holdout：空；
- formal holdout：空。

阶段二 grid：

```text
2 base tasks × 2 chart conditions × 4 strategies = 16 units
```

一个 task-condition 先自然运行一次，保存一个 before-submit checkpoint，再物理重放同一可见动作前缀，分叉给四个策略。四个策略不重新采样前缀。

## 3. 中性 before-submit 触发

### 3.1 触发条件

默认每个 episode 只在第一次满足下列条件时触发：

1. 当前公开 DOM 中存在可见 `type=submit` 控件；
2. Agent 提出 `click_button`/兼容 `click_link`，且 visible label 精确解析到该 submit 控件；或提出 `submit_form`，并能解析到当前可见 submit 控件；
3. executor 尚未执行该 action。

`finish`、普通按钮、猜测的提交文字和没有可见 submit 控件的 `submit_form` 不触发。Hook 不读取 condition、gold、scorer、mechanism 或“当前是否正确”；空选择、任一已选项、任一 chart condition 使用同一规则。

该固定触发测量统一提交前核查能力，不代表 Agent 自主意识到自己犯错。

### 3.2 Checkpoint 内容

保存：

- 原始公开 user goal；
- visible options 和实际 current selection；
- 当前 allowlisted browser state；
- 当前截图；
- 此前实际观察过的 task/dashboard/form 截图；
- 已真实执行的公开动作前缀；
- 模型 request ID、公开响应、proposal 和 state digest；
- pending submit proposal，状态为 `pending`。

在 capture 后检查 server receipt 数没有变化。`pending proposal`、核验导致的 `cancelled_for_visible_revision`、revision action 和实际 submit receipt 分开记录。

### 3.3 恢复

每个 unit 新建 page，从 task URL 开始，用同一 executor 物理重放 checkpoint 的非提交动作；不使用 Browser Back，也不重新采样 Agent 前缀。重放后必须同时满足：

- allowlisted state 的 canonical JSON 完全相等；
- 当前 full-page screenshot SHA-256 完全相等。

任一不等即 `unsupported_replay_mismatch`，该 unit 不冒充恢复结果。

当前 Chromium/Playwright 启动参数固定为 `--no-sandbox --disable-gpu`，浏览器版本、可执行路径和启动参数写入每个 run manifest。最终复核发现 `--disable-gpu` 仍不足以消除 textarea 圆角处的 7-pixel、最大通道差 1 的栅格漂移，因此 safe shell 的 select/textarea 使用直角边框；该纯装饰稳定化在同一 checkpoint 的 8 次重放中得到 8/8 exact SHA。截图比较本身不设像素容差，也不对 chart 做归一化。

## 4. 四个阶段二配置

| 配置 | 输入和行为 | 额外模型调用 | 主动观察 |
|---|---|---:|---:|
| B0 原样继续 | 不核查、不改选，执行保存的原 submit proposal | 0 | 0 |
| B2 完整重读＋目标语义核查 | 独立查看完整 dashboard、goal 与 options；第一次判断刻意不展示 current selection，controller 再与 checkpoint 比较 | 1 | 0 |
| B3 通用主动视觉核验 | 获得 goal、current selection、options、完整 current/form、完整已见 dashboard；可自行决定立即判断或从 `dashboard/current` 请求 crop | 1–3 | 0–2 |
| B4 自行提取＋普通 Agent | 同一模型先只从完整可见图提取 title/axes/units/legend/range/values/uncertainty，再由普通决策回合只使用该提取、goal、options、current | 2 | 0 |

B3 每个后续回合显式重新携带有序多图历史：`current`、`dashboard`、所有成功 crop；不是假设 HTTP 模型有会话记忆。第二次 crop 后第三次调用必须决策；仍请求观察或输出非法 label 时 fail-open 保持原选择。

所有 crop 都来自该 Agent 已观察的浏览器截图副本，不读取 evaluator 的原始高清 figure，不读取 CSV/HTML，不声称 crop 能恢复不存在的像素。未来候选机制若进入阶段四，必须复用 B3 的这套多图/裁剪接口、图像质量、历史权限和调用上限；当前尚无候选实现，所以公平性只是一项后续约束，不是已验证结果。

B4 的 extraction 失败属于 B4 自身失败；不得用正确表格替换。第二回合收到一张中性 32×32 interface image，仅为满足当前 vision-client 接口，不携带额外证据。

## 5. 公开选项排序与评分

本地 raw task 的两个 synthetic arm 均为 140/140 把 expected action 放在 `action_space[0]`，若照原序渲染会形成 gold-position side channel。Safe shell 因此：

1. 只取公开、唯一、非空 label；
2. 按 `(label.casefold(), label)` 排序；
3. 两个强 pair 的 label 集相同，因此两 arm 得到同序；
4. 浏览器只提交 opaque `option_N`，server receipt 同时保存对应 visible label；
5. 终止后 evaluator 按唯一 label 映回 raw action ID 并评分。

排序不读取 gold。B0 是“该中性安全协议下不增加核查”，不是原 runner 页面字节级复现。

## 6. 统一执行器与终止语义

所有配置共享 `BrowserExecutor`：

- URL 必须是精确 `/task/<alias>` 或其子路径；
- 只执行 `click_link`、`click_button`/`submit_form`、`select_option`；
- 普通可逆动作最多尝试 2 次；每次尝试前先计 browser transition；
- `select_option` 后读取 `selectedOptions[0]`，label 未生效即失败并按同一上限重试；
- revision 通过正常 `select_option` action，不暗中替换 token；
- 非法 policy label 保持 checkpoint 选择，但仍执行真实提交，不能靠 abstain 提高分数；
- final submit 是不可逆边界，只尝试 1 次。若 POST receipt 已产生但 redirect/ack/confirmation 失败，记录 `submitted_acknowledgement_error`，不重复 POST；
- 若一次 unit 观察到多个新增 receipt，记录 `duplicate_submission_error` 和实际 receipt 数，保留证据但不选择其中一个评分；
- POST 后的 page-close/截图清理错误不得覆盖已确定的 commit 状态与 receipt。

只有 server receipt 新增恰好一行才算真实提交；随后另查 confirmation。`finish` 不算提交。Scorer 只在终止后读取 raw task 与 receipt，不给 online controller 返回任何结果。

## 7. 信息边界

在线模型请求只由 `manifests/online_manifest.json` 的公开字段和浏览器观察构造。Researcher/evaluator 使用独立的 `manifests/researcher_manifest.json` 和 `evaluator/` 输出。

在线允许：goal、page/chart reference、visible labels、公开 DOM state、去 host/port 的 path、已观察截图、模型自己的历史。禁止：expected/misleading IDs、ground truth、mechanism/condition、另一 arm、role/score、raw CSV/HTML、source path、evaluator bbox 和终局 score。

每个请求在调用前保存；嵌套 key 经过 forbidden-key 检查。请求图像只能引用所属 prefix/unit 目录，不能跨 unit 或跨 arm。模型输出可自行推断图上内容，所以 hidden-string 输入扫描只针对 request/prompt/context；所有 online JSON 仍做 forbidden-key 扫描，以发现 scorer 对象误混入。B4 decision 中若出现疑似隐藏字符串，只有它能逐字追溯到同 unit 先前成功的 extraction response 时才可归为允许的模型自身历史；否则仍报 leak。

写代码/离线审计可以读取 raw task 结构和终止后 score，但不得据此产生被测 action。阶段二 action 全部来自显式 model backend；mock backend 明确标记 `research_result=false`。

## 8. 预算与失败分母

阶段二 hard ceiling：

- model calls ≤ 160；
- browser transitions ≤ 800；
- 每个自然前缀 model calls ≤ 12；
- concurrency = 1；
- 每个核验 policy model calls ≤ 3、active observations ≤ 2。

`BudgetLedger` 在调用/transition 尝试前计数；model/backend/browser failure 不会从计数中删去。超过 hard ceiling 的下一次调用在发送前拒绝。

live-local 模式在任何 episode 前必须通过一次同 backend 的有序双图 witness：单次请求同时携带中性命名的红三角形和蓝圆形图片，并核对服务报告的图像数、顺序相关内容和协议元数据。该调用使用同一 `BudgetLedger`，计入 160-call 总上限；失败时不得继续 task episodes。它只验证多图传输，不是图表能力基准。

对已通过配置/资产 preflight 的 run：

- prefix model/browser exception 写入 `prefix_result.errors`；
- 未到 checkpoint 的四个 unit 都保留为 `not_run_no_checkpoint`，进入端到端分母并带 exclusion reason；
- unit error、replay mismatch、无 submit/confirmation 分别保存；
- shell/browser runtime failure 的未完成 grid 由顶层 finalizer 写成 retained error，并仍落 unit map、scores、budget 和 run manifest。

参数非法、development split/重复 task、pair invariant preflight 失败、未授权/不健康模型 endpoint 属于 run 启动拒绝，不当作已启动 episode；这些检查在创建 run 目录前完成，避免残缺且不可复用的目录。

## 9. 工件布局与校验

```text
runs/<run_id>/
  run_manifest.json
  budget.json
  online/
    preflight_witness/{images,requests,responses}
    prefixes/<opaque_prefix_id>/{checkpoint,prefix_result,requests,responses,screenshots}
    units/<opaque_unit_id>/{replay,result,requests,responses,observations,screenshots}
  server_receipts/
  evaluator/{unit_map,prefixes,scores,pair_invariant_audit,validation}
```

Online 目录不出现 raw slug/condition 的目录名。`validate_run.py` 普通模式允许完整记录的失败单元；`--require-complete-submission` 用于本轮要求所有 16 unit 完成的严格 smoke 检查。

由于本机无 Git executable 且 `.git` 无 commit，每个 run manifest 记录 executable source、tests 和 manifests 的运行时 SHA-256 tree fingerprint；它不是新增长期发布 gate。

## 10. 指标与解释限制

阶段二 smoke 只报告：witness、checkpoint 到达、capture 前后 receipt、replay state/screenshot、真实 POST/receipt/confirmation、policy calls/active ops/revisions/retries、budget、终局离线 outcome 与 exclusion。Mock outcome 只能验证 scorer/链路，不能比较方法能力。

2026-09-06 的真实模型 smoke 只有 env001 两个条件到达 checkpoint，env025 因 `select_name` 的公开 label/name 映射失败而留下 8 个 `not_run_no_checkpoint`。这首先是执行接口问题，必须在任何后续研究比较前排除。即使未来完整真实模型 smoke 通过，也仍只算链路检查；不能据 16 units 判断普通重读/B3 是否足够，更不能据此启动新机制。

阶段三经审批后才报告：所有启动轨迹为分母的端到端成功、checkpoint coverage、当前错误状态 detection/fix、当前正确状态 false positive/damage、final submission、调用/image/token/browser/replay cost，并按 base task 聚类给逐任务配对表。Clean 不自动等于当前正确，misleading 不自动等于当前错误。

## 11. 阶段三/四停止规则

- 若 B2 或 B3 已解决绝大多数诊断留出问题，优先停止复杂化并评估成本。
- 只有多个独立任务、至少两类非标题视觉问题在相同可访问证据下仍失败，且排除分辨率/crop/接口错误后，才筛查决策相关观察选择。
- 给定同一正确图表判断后仍大量执行失败，先修执行/映射。
- 候选与 B3 在同预算下无清楚优势、损害正确状态、靠不提交提高安全率，均停止扩展或收窄结论。
- 收益来自标题、raw data、固定布局、人工接管或更强 backbone，不能支持所声称的视觉选择机制。

阶段二在这里停止，不自动启动 pilot 或候选开发。
