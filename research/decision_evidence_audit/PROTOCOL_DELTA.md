# Stage 2.5 协议增量

本文件只记录相对 `PROTOCOL.md` 的增量与澄清，不把 safe-shell 适配描述成原 benchmark runner 或某篇 GUI Agent 方法的完整复现。

## 1. 研究问题保持不变

底线问题仍是：Agent 没有执行报错、正准备提交一个业务决策时，能否发现该决策缺少可见证据支持，并在有限重观察预算内修正。

本轮继续只比较：

- B0：保存的提交提议原样继续，不增加核查调用；
- B2：重看完整 dashboard，并独立核对目标语义与可见选项；
- B3：通用主动视觉核验，最多 3 次核查模型调用、最多 2 次合法观察分发；
- B4：同一模型先从已见图像提取内容，再由普通 Agent 按目标决策。

没有加入前提账本、长程回滚、技能进化、多 Agent 框架或决策相关观察选择器。

## 2. before-submit 与共同执行器

hook 的中性触发条件不变：第一次出现匹配页面可见 submit control 的 `submit_form`/submit-button proposal，并且该动作尚未交给 executor。触发不读取图表 condition、gold、当前选项是否正确或 evaluator outcome。

checkpoint 保存公开 browser state、当前选择、已观察截图、公开动作前缀、模型自身历史及 pending proposal。每个分支在 fresh page 中物理重放相同前缀；revision 由同一个 `BrowserExecutor` 执行 selection postcondition，随后 pending submit 只尝试一次。server receipt 与 confirmation 是提交证据，`finish` 不是提交。

B0 是“当前中性协议下零额外核查参考”，不是旧 runner 的逐字节复现。B2–B4 均固定使用 dashboard/当前截图流和相同执行器，不能把 generic GUI grounding 的改选能力混入策略名称。

## 3. raw JSON、页面渲染和模型输入的区分

| 原 task 字段/来源 | safe shell 页面 | 实际模型请求 |
|---|---|---|
| `page_title` | 保留为页面标题 | 通过可见页面截图/状态出现 |
| `workflow_instruction` | 保留为 `user_goal` | 明文目标；B2–B4 都可见 |
| `chart_reference` | 保留；为空时仅用中性 `Review the chart.` | 明文图表说明，不补隐藏规则 |
| `primary_action.field_label` | 保留为 select label | 可见控件文本 |
| `action_space[].label` | 全部保留，但按公开 label 大小写无关字典序排序 | 可见选项文本；不含 opaque value token |
| `chart_asset.figure_path` | 只用于本地 `/chart` 返回图像 | 只送模型实际浏览器截图/允许 crop；不送源路径 |
| task/case/pair/condition ID | 用 opaque `task_alias` 代替 | 不发送；URL 只留 path |
| action ID、role、scoring outcome、expected/misleading IDs、ground truth | 不渲染 | 不发送；终止后离线评分 |
| misleader type、readiness、generation metadata | 不渲染 | 不发送 |
| CSV、HTML、原始表格 | 不渲染 | 不发送；B4 只能从已见图像提取 |
| companion actions/correct values | 不渲染 | 不发送 |
| 另一 arm | 单次 shell 不持有 | 不发送 |
| `Decision note` | safe shell 新增的中性可见控件 | 可见但非 evaluator 证据；不改变主决策评分 |

因此 `correct_value` 这个字段名本身不等于在线泄漏；泄漏判断取决于它是否被渲染或进入 request。当前白名单重建使它不跨过在线边界。

## 4. safe shell 的有效身份

当前 shell 的有效身份是：复用本地任务目标、图表和可见选项的 neutral main-decision diagnostic。它保留 `task -> dashboard -> form -> POST -> confirmation` 的核心语义和真正本地 HTTP 提交，但不保留原网页视觉布局、全部 companion fields、原 middleware、通用多站点动作空间或原 benchmark scorer integration。

移除字段如果破坏公开规则，就应排除任务而不是在 prompt 中偷偷补齐。`TASK_ELIGIBILITY.csv` 已逐项记录保留/移除内容；本轮候选中 `pub010`、`b035`、`b012`、`b013`、`b015` 的 `chart_reference` 为空，但 workflow 本身给出完整规则，所以中性 fallback 不破坏任务。

## 5. task pair 资格

release 身份：`benchmark_v2_open`，`release_version=2026-07-07`，`status=open_release_candidate`。

对 140 对的 14 个任务/动作/评分字段比较：

| 类别 | 数量 | 任务 | 处理 |
|---|---:|---|---|
| 所审字段相同 | 114 | 见 `pair_field_differences.csv` 中空 diff | 可进入 chart-only 候选池，仍需可见规则和截图质量审查 |
| 可见目标/选项和评分语义同时改变 | 22 | `b017`–`b034`、`health010`–`health013` | `pair_confounded`，不用于强配对因果比较 |
| 可见 option wording 改变，action IDs/roles/outcomes 保持 | 4 | `health006`–`health009` | 仍为 `pair_confounded`；措辞变化可直接影响模型 |
| 只有 action ID 改名 | 0 | — | 本轮未发现 |
| 只有无关离线 metadata/explanation 改变 | 0 | — | 本轮未发现 |

完整逐对导出在 `revisions/20260906T144628Z/offline_audit/pair_field_differences.csv`。这份检查说明 26 对不能自动保留，但不证明 2026-05 的论文主实验实际使用了这些 2026-07 task rows。版本对应关系保持 `pending`，不得推断“论文 140 对全部受影响”。

## 6. 候选任务审查

候选在查看历史 model-run outputs 之前固定为当前 2 项开发任务和 12 个新增任务：`env001`、`env025`、`pub010`、`env008`、`b035`、`pub020`、`pub023`、`pub024`、`b012`、`b013`、`b015`、`env006`、`env021`、`env026`。

每个 task/arm 都实际渲染 dashboard：28 张截图、固定 viewport 1440×1100、图表 CSS box 1194×720。人工查看确认当前缩放下轴、标签或数值关系可读；实际源尺寸和 rendered geometry 在 `candidate_renders/render_audit.json`。资格结论：

- 13 项为 `eligible_primary_decision_probe`；
- `env001` 为 `engineering_only`，因为“large enough”没有公开阈值；
- `env025` 虽规则合格，但最新 live checkpoint 两 arm 已自然正确，主要用于 correct-state preservation 和理由支持性；
- 三个主要近重复族必须同组：趋势标题族 `pub010/pub024/b035`，月均标注族 `env025/pub023/env026`，商品阈值族 `b012/b013/b015`；largest-category 项也需要按源图/模板继续分组。

这只是候选资格表，不是已 materialize 的 pilot split。

## 7. 选项顺序

现阶段公开 label 排序消除了 raw task 中 140/140 gold-first 的直接侧信道，但 chart-only114 的正确选项位置仍为第 1/2/3 位 = 22/60/32。该分布必须报告，不能称平衡。

正式 pilot 的预注册方案是使用与 gold 无关的固定外部 seed，对每个 task 的公开 label 集做确定性排列；同一 task 的两 arm、所有方法共享同一排列。seed 和 task slug 可以决定排列，但实现不得读取正确位置、正确 label 或输出表现来平衡。还应加 position-only/no-image diagnostic。本轮没有实现或运行这项 pilot 改动。

## 8. integrity-v2

新 run 的最低完整性记录为：

1. run 创建后、任何 episode 前保存 `evaluator/run_start.json` 和空 `budget.json`；
2. 每次计费后更新 budget，失败也计入；
3. 保存实际执行配置及其摘要；
4. 保存适配器源码、测试、manifests、selected task specs/figures；live 模式还保存本地 client/server 源码；
5. prefix/unit 边界检查 runtime source identity，变化即停并保留剩余分母；
6. replay 保存 `restored_state`，validator 从文件重算原/恢复 state digest 和 screenshot hash；
7. 每个 request 必须有同 ID response，且明确 `ok=true` 或携带 error type/message 的 `ok=false`；request IDs 与 budget events 对齐。

`stage25_mock_integrity_20260906T145414Z` 验证了该格式：16/16 state 和 image 可重算，36/36 request-response 配对，23/23 snapshot 文件匹配，预算 132 events/133 writes。旧 run 缺失字段只报告历史限制，不反向改写。

## 9. 当前真实 smoke 的固定协议与实际执行

用户随后明确授权在 GPU 0 启动已有 Qwen3-VL-8B 权重。唯一一次 fresh 16-unit grid `stage25_live_smoke_20260906T1515Z` 已按以下固定协议执行：

- tasks：`env001,env025`；
- conditions：`official140,clean140`；
- configs：B0/B2/B3/B4；
- concurrency：1；
- hard ceiling：160 model calls、800 browser transitions，witness、失败、replay、核查全部计入；
- backbone/解码/图像预算在 run_start 固定；
- exact current source/config 运行，中途修改即停止，不补跑拼接；
- env001 仅工程链，不做语义效果比较；
- 保留所有失败、checkpoint、submission、revision receipt、token/image/call 成本。

主 grid 实际结果为 4/4 checkpoint、16/16 replay/POST/confirmation、33 model calls、96 browser transitions；运行中源码未变，严格 validator 为零错误零警告。B3 的四个输出均为合法直接决定，但 0 自主 crop、0 revision；没有为了触发工具而改任务 prompt 或追加重跑。双图传输 witness 已在主 grid ledger 中计 1 次调用。

执行单要求的小型 true-backend crop feedback/cumulative multi-image control 随后只运行一次并单列：其 ledger 计 5 次调用事件，其中 2 次是注入的合法 observe、3 次是真实 Qwen completion，浏览器 transition 为 0。注入路径 2/2 crop 成功，最终真实调用确认收到 4 张累计图并输出正确 Route B；正确初选保持控制通过；自然改选控制失败，因为 reason 说应选 Route B 而顶层 `option_label` 仍为 Route A。套件 2/3 通过、exit 1，失败原样保留且未重试。它只验证工具/传输，不构成自主 crop 或 benchmark recovery。

合并主 grid 与单列控制，本次授权实际使用 38/160 个计费调用事件（其中 36 次真实模型 HTTP completion）、96/800 browser transitions。

模型服务在实验后关闭，GPU 0 已释放。本次授权与 16-unit ceiling 已用完，不凭剩余 call/transition 额度启动第二组 grid。

## 10. 后续因果诊断仅为计划

若以后出现无歧义的错误 checkpoint，预注册诊断顺序可以是：完整重读、固定 task-independent matched crop、oracle-region diagnostic、给定正确视觉事实、给定正确 action。该顺序用于定位是视觉定位、事实读取、规则绑定还是执行问题；oracle 区域/正确事实/正确 action 只能作为离线诊断，不得进入主方法输入。

本轮没有实现这些诊断，也没有开发新的观察选择机制。
