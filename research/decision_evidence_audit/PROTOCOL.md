# 决策相关视觉核验协议（阶段二冻结说明）

## 最新状态：2026-09-07 12:22 UTC，四条已真实运行

GPU0共享许可已明确适用于本对话后续进程。本轮四条均已尝试：b011两臂反复改选、8调用内未提出提交；env027两臂正确选择并由B0原样真实提交。24次真实模型调用/36浏览器动作，加既有mock后累计28/40调用事件、45/160动作。没有补跑或扩大实验，自己的Qwen服务已释放。

当前自然错误的提交前checkpoint为0；不以b011中途选错冒充提交前错误。49项回归与212项工件检查通过，但新fresh子Agent因额度错误未执行，独立审查ERROR/unavailable。此前未运行/资源阻塞说明与旧检查、旧mock审查均为历史，不覆盖当前结果；父目录before-live副本保留原预算/summary。

[真实运行报告](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/STAGE_REPORT.md) · [逐样本轨迹](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/CASE_REPORT.md) · [当前停止点](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/NEXT_ACTION.md) · [实际命令](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/COMMANDS.md)。不要重跑已存在live_attempt的四单元。以下原文保留为历史记录。


## 当前补充：2026-09-07 四条自然轨迹，仅原样提交

本轮只授权b011/env027×两图表条件的4条自然前缀+B0；总40调用事件/160浏览器transition，每前缀最多8次模型调用，不运行其他策略。首次公开业务提交提议同样拦截，不看隐藏对错；按原runner保存并恢复状态，再执行原提议。请求目录中性化，图片/提示/公开规则不改，禁止以reason/gold替换选项。当前已用4个mock事件/9动作，真实四条均未运行，资源安排另见当前报告。

模型输入沿用当前图/状态单步接口，不宣称完整历史记忆；没有自然理由时不补造。协议全文见[本轮PROTOCOL](runs/natural_prefix_20260907T0932Z/PROTOCOL.md)。未启动核查比较、自然错误特权诊断、pilot或新机制；下文为历史协议。

## 当前补充：2026-09-07 七候选网页资格协议

本轮仅7个既有候选×两图表条件，预算0被测模型调用/112浏览器transition，实际0/98。所有实例使用相同公开计划规则：逐项选择3个公开选项，按公开顺序轮换确定最终提交；不看gold、不运行Agent、不以终局得分筛资格。网页显示、配对、选项映射与真实回执分开审查，完整保留14行。没有新增baseline/hash/冻结contract或原图修改。

[本轮协议](runs/web_qualification_20260907T0801Z/PROTOCOL.md) · [资格与局限](runs/web_qualification_20260907T0801Z/QUALIFICATION_TABLE.md)。检查范围为当前release主路由safe-shell适配，原runtime函数对照只读执行，不代表原portal完整运行；后续自然模型轨迹另需明确执行单。以下为历史协议。

## 当前补充：2026-09-07 冻结颜色面板一次真实执行

本轮只执行预定8状态×3条件，不重跑旧grid、不开发机制。预算80调用/200动作，实际25/140；旧选择投影、文本事实特权边界、真实POST与冻结来源见[本轮协议](runs/frozen_panel_20260907T015908Z/live_20260907T0307Z/PROTOCOL.md)。下文不同历史轮次预算和授权状态不替代本轮。


## 最新B3接口修正：20260906T1342Z

标题中的“冻结”是历史文件名描述；本轮依用户授权增量修正接口，旧run和修改前源码保存，不新增冻结contract或hash体系。研究底线、样本、策略范围与160调用/800动作上限不变。

B3当前核查必须输出顶层option_label或observe，不执行浏览器动作、不接受嵌套decision。它仍收到目标、当前选择、可见选项、既有公开动作/模型历史、current/dashboard和累计crop。格式错误给明确反馈并计模型调用，不虚构观察；合法分发含工具失败计2次观察上限，成功crop另计。最多3模型调用；没有强制裁剪、隐藏答案、样本专用规则或从reason替模型改答案。B0/B2/B4不变。

新metrics区分 invalid_outputs / observation_requests / dispatched_observations / successful_crops / tool_errors / rejected_observations / accepted_decisions；旧active_observations的空分发不能与新成功观察混用。唯一grid中B3为4合法决定、0请求/分发/crop、0改选，不代表主动选择观察已充分测到。

合成控制初始选择及部分crop请求是显式注入，不是自然benchmark轨迹；两次控制均有失败，最终prompt的改选控制出现reason说B而label为A。grid继续仅作为带此警告的工程/诊断smoke，不宣称正控制合格、语义可靠或方法能力边界。严格validator只管工件/一致性，不能覆盖语义失败。

全轮实际39真实推理+19注入/mock=58调用、155动作；其中唯一grid33/96。16单元均保留，无免费重跑。服务已释放，阶段三/四未启动。[详细协议执行与偏差说明](revisions/20260906T1342Z/STAGE_REPORT.md)。

## 最新运行说明：20260906T1219Z

用户授权 GPU 0 后，按当前在线实现完成唯一一组 2×2×4 真实 Qwen3-VL-8B smoke。没有修改策略、数据、解码或在线协议；主 runner ceiling 140/700，为浏览器控制预留预算；实际全轮含控制为 55 调用（41 真、14 mock）、149 浏览器动作，未超过160/800。

新增必须明确的解释限制：`completed_chain_smoke` 与严格 validator 通过只说明完整提交/记录链路，不代表策略语义接口合格。本轮 B3 四单元均回退保留；旧 `active_observations` 包括无 observe 对象引发的失败分发。原记录8，不是8次成功 crop；成功 crop=0，接受的核查决定=0。不得将其计为通用主动视觉核验已经充分测到。自然改选=0；修订 POST 证据来自注入控制。[逐任务工件报告](revisions/20260906T1219Z/STAGE_REPORT.md) 记录详情。阶段三/四仍未开始。

## 本次协议增量（20260906T0830Z）

底线与瓶颈不变：无执行报错的待提交决策核验，以及有限重观察下找到区分行动的视觉依据。只完成阶段一、二；不开发候选机制。以下历史正文保留，本节覆盖与当前实现有关的变化。

- 同一公开语义提交触发一次，不看答案或条件。B0 无额外核查；B2 独立看完整历史 dashboard + 目标 + 选项；B3 看目标、当前选项、完整 current/dashboard，自选最多两次截图区域；B4 用同一 backend 自提取图表，再由普通决策步骤使用提取结果。B0 不是等算力对照。
- B2 若从未观察过 dashboard，不以含当前选择的 form 截图冒充独立核验：记录 `independent_chart_observation_unavailable_keep`，不调用、不改选，照常执行原提交并保留终局结果。这是“未实际核查”，不是核验成功。当前开发 workflow 的四个前缀均有 dashboard。
- 审查后 B3/B4 同样不再将任意最后截图冒充 dashboard；缺该观察时记录 `chart_observation_unavailable_keep`，按未实际核查保留选择。当前实现仅支持已审计的 dashboard 工作流，不能声称已覆盖任意网页的图表发现。
- `online_manifest.json` 是权限的文档清单，不是 runner 读取的运行时配置。真实边界由 `core.py` 的 task/browser 白名单投影及 `policies.py` 显式请求构造实现；`assert_online_payload` 是附加的禁止键检查，不是整个 payload 的完整白名单验证器。历史正文对 manifest 可执行作用的说法在此纠正。
- 所有策略、自然前缀和重放共用严格选项执行器：精确 name/id 优先，否则精确匹配唯一可见 label；重复/未知/禁用控件、重复/不存在/禁用选项拒绝。不模糊匹配，不按任务名、gold 或机制补答案。最多两次物理尝试；提交最多一次；实际选中文字作为后置检查。
- 当前公开 DOM 提取排除隐藏/禁用控件，隐藏文本交换不应改变模型输入或提交触发。B3 请求还包含可见动作前缀、之前的 Agent 响应和最近一次裁剪坐标/反馈；保留完整当前图、dashboard与成功裁剪图。失败反馈不暴露本地文件路径。这仍是受限截图工具，不代表任意网页工具或完整GUI系统复现。
- 原提议终局状态明确记为 executed、execution_not_confirmed 或 cancelled_for_visible_revision；修订动作与实际 POST 分开。修改后的动作仍用原提交控件，但已取消旧选择对应的 pending proposal。
- 本次只有一个 16-unit mock grid；smoke 子账本上限下调为 120 调用/650 transition，给控制与失败重试预留额度，整体仍不得超过用户 160/800。Mock 没有模型参数量、token 或视觉推理能力，不能把其终局正确/错误计数当基线性能。
- 图像工具仅对已观察截图裁剪，不读取原始高清图另造证据；B3 的后续调用继续带完整图与成功裁剪。当前只开放已实现的 dashboard/current 裁剪，不宣称任意网页搜索。真实本地多图传输本次未运行。
- 当前 safe_shell 为独立的中性提交诊断页面；原 runner 未修改，布局与 companion 字段不逐项复现。B0 的“不变”指该协议内原提议和执行轨迹不被核查改变，不是旧论文系统整体行为不变。

分母包括全部启动的 task-condition 前缀及配置单元；未到 checkpoint、未核查、非法决策保留选择、执行失败和未提交都应单列。成功仅按真实服务器回执映射到原 task 的离线答案；clean 不等于当前正确，scorer 的 misleading_failure 标签也不是因果证明。

---

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

在线模型请求由代码中的公开字段投影和浏览器观察构造；`manifests/online_manifest.json` 仅记录其中的 task/browser 权限，不由 runner 加载，也未完整枚举策略上下文字段。Researcher/evaluator 清单和 `evaluator/` 输出独立保存。此处按本次独立审查纠正原有表述，历史原文见 original 备份。

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
