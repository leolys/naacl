# env008 Phase-3 独立实现红队审查

审查日期：2026-08-31  
审查对象：Phase-3 frozen 50-cell implementation、model-free Firefox calibration；尚未审查 formal 模型结果  
审查角色：独立对抗 sub-agent；未修改 runner、controller、scorer、renderer 或 tests

## Launch verdict

**GO，可启动 formal。** 当前 live source 没有剩余 P0/P1 launch blocker。这个 GO 只表示实现与模型无关校准足以开始真实运行，不表示任何方法有效，也不提前认可之后的 `execution_complete` 或任务结论。正式 run 的 raw calls、真实 model-input receipts、UI transactions、submission/scorer join 仍须在结果审查中从磁盘重算。

放行所依据的 calibration 是：

`runs/phase3_calibration/20260831T144906Z_6db2f55e/summary.json`

它与 live `PROTOCOL_VERSION=env008-phase3-50cell-v3` 一致，50/50 cells 完成、0 cell errors、0 check failures、`execution_complete=true`。较早的 `20260831T141346Z_ba50f6c4` 是 v2，不能作为 v3 formal gate；runner 本身也会拒绝它。

## 审查范围与独立复算

只读检查了：

- `env008_phase3_protocol.py`
- `env008_role_counterfactual.py`
- `premise_controller.py`
- `run_env008_phase3.py`
- `model_server.py`、`agent_runtime.py`、共享 action parser
- Phase-3 tests、role assets/manifest、v3 calibration 的 50 个 intervention 和 136 张 PNG

独立复算结果：

- frozen matrix 为 50 个唯一 condition：M 8、A 6、R 24、C 12；这是一个开发样本上的条件格，不是 50 个 IID tasks；
- v3 calibration 共 190 个文件、136 张 PNG、50 个 intervention；50/50 handoff PNG 的磁盘 SHA 与 intervention 一致；
- 74/74 evaluator setup UI transactions 全局唯一：38 个 M/A/R cell 各 1 条 inherited selection，12 个 C cell 各 3 条 `selection → browser_back → selection`；
- M 每个 arm 的四个 handoff PNG 与去标识 app snapshot 相同；三个非空 memory entry 均为 30 checkpoint tokens、stored form 32 tokens、实际 prompt segment 42 tokens；
- A 每个 arm 的三个方法 handoff PNG 与 app snapshot 相同；F3 contradiction 在 1280×960 Firefox 像素中完整可见、未直接显示正确 entity；
- R 每个 config×arm 的两方法 handoff PNG 与 action mapping 相同；六个 config 的 R/X/P/C 与冻结表逐项一致；
- R 六对 1000×750 official/clean assets 均由对应 source rows 重渲染一致，pair diff bbox 均为 `(112,84,921,628)`、110,529 个不同像素、allowed mask 外为 0；r0/r1 correct=Solar，r2/r3 correct=Hydroelectric，r4/r5 correct=Wind；
- C 的四个 `arm × final entity` 组内，三种 history 的 handoff PNG 和 app snapshot 相同；两个 populated history 都为 2 frames/2 actions，末帧 raw PNG、末 action、click annotation 和预期 448-input digest 相同，较早 action 为 `WAIT` 对 `PRESS_BACK`；
- 全测试独立运行 172/172 通过，另有 2 个既有 loopback/sandbox skip。

## 七项 protocol NO-GO 的处置

| gate | verdict | 对抗结论 |
|---|---|---|
| 1. memory 真正入模且 ownership 清楚 | GO | memory prime 只允许 fresh reset-empty state；receipt 保存 exact entry/stored bytes。step receipt 把 stored-memory SHA/length 与实际 question 中唯一 `<MEMORY>` segment 连接。intervention 明示 evaluator-owned、非 agent-generated。 |
| 2. controller 不得读 evaluator truth | GO | model-call 与 stage-control dataflow 只使用 task instruction、current screenshot、同一 controller 自己抽出的 target，以及动作是否真实发生；函数另收的 cell/run/method metadata 只写 artifact，不进入 prompt 或分支。canonical case、CSV、expected entity、scorer、role、DOM、token→entity map 均不在 policy dataflow。 |
| 3. A 初始输入/checkpoint/budget 可比 | GO，有限定 | 同一 managed model object、官方 checkpoint、system prompt、generation config、viewport、4-call/4-action cap；每 arm 三方法起始像素一致。不同 prompt/state machine 是被测 method treatment，不是 same-compute control。 |
| 4. R truth/render/action/scorer 绑定 | GO | 六个 config、三种 role、X/P/C mapping、role-neutral action IDs、source rows、asset、mask、layout 与 scorer 均被独立连接；正确 entity 不再 hardcode Solar。 |
| 5. C current pixels 与 shared tail | GO | 同 final/arm 的三个 current states byte-identical；两个 populated fixtures 等长并共享最后 raw/model frame、click action与 annotation。fixture setup 不进入 model behavior，正式 cell 严格一 call。 |
| 6. 不把 cells 当样本/不筛格 | GO | protocol 固定 50 格和内容地址顺序，`n_base_case=1`、synthetic/reportable=false、in-case development 限制已写入 frozen protocol。 |
| 7. scorer/validator/role truth 不入 browser/prompt | GO | model-visible projection 是 whitelist；R 页面与 action labels 不含 role词；controller target 只能来自模型 evidence。scorer 仅在真实 submission receipt 后由 outer runner 调用，结果不反馈模型。 |

## 先前攻击与修复复核

### Action parser

先前 controller 可以接受没有最终 `<ACTION>:` 的 action prose，且可能与官方 parser 对多 action 文本的解释不同。现在 native 与 controller 共用 strict final-field parser；controller 还必须与服务端真实调用的官方 `GUI_Reflection.parse_action_output` 在 action type 和 parameters 上完全一致。以下攻击现在均被拒绝：

- 只有 `CLICK[[...]]`、没有 `<ACTION>:`；
- final field 内含两个 action；
- prose 中较早出现 `PRESS_BACK`，final field 为 CLICK，而官方 parser 返回 PRESS_BACK。

parser disagreement 会使 cell invalid，不能被计成方法失败或恢复成功。

### Condition-key 与外部服务泄漏

发往模型服务的 task ID 已改为 `phase3task_<random 32 hex>`，memory/history fixture ID 也为随机 opaque ID。`cell_key`、R config、method、arm 不再进入模型服务 identity。formal 明确禁止 `--agent-url`，只允许 runner 启动并核 health 的本地 audited GUI-Reflection service。

### Controller truth boundary 与归因

token→visible-entity mapping 已移出 `_controller_run`。整条 policy trajectory 结束后，outer evaluator 才生成 `controller_binding_audit`，并明确标记 `used_as_model_input=false`、`used_for_controller_stage_control=false`。因此：

- scorer true 且 UI 完成链成立可记 `task_level_recovery`；
- proposed controller 只有在模型 evidence target、实际 selection 与 submission entity 后验一致时，才记 `method_attributable_full_recovery`；
- 若 target=A、点击/提交=B，即使 B 偶然正确，也不能归因于声明的 premise→action dependency。

### R manifest 自证攻击

manifest 不再只信自报 `role_config_id`、vector、asset SHA 或 expected entity。loader 会从 frozen `ROLE_CONFIGS` 重建所需 R/X/P/C，重读 source CSV，检查 rows/value/bar/color/order，重渲染 official/clean/mask 并逐像素比资产；scorer 再从 variant source 的 printed values 独立求 argmax。篡改 X vector、source row order或color的定向测试均会失败。

## 非阻断限制与结果审查必查项

这些问题不制造当前 launch 的假阳性，但限制可声称内容：

1. **Controller 是显式辅助 method bundle。** evidence prompt 明确规定在数值标签与几何冲突时优先 printed values，并强制三阶段 evidence/reversal、target binding、submission check。成功只能归因于“同 checkpoint + 此 inference-time prompt/state machine”，不能称 GUI-Reflection 自主发现了该规则，也不能称 same prompt 或 same compute。

2. **重试策略并不相同。** native/current-only 可在 4-call cap 内继续处理 WAIT/非进展动作；controller stage mismatch 为 fail-fast，成功路径最多 3 calls。这个差异在结果前已冻结且不偏向事后保留成功格，所以不是 launch blocker；但禁止声称共享 retry policy，必须同时报告 calls/tokens/latency，并将差异视为 method bundle 的一部分。

3. **Structured evidence 不是视觉真实性证明。** parser 检查 JSON shape、唯一 numeric argmax，不从 CSV/DOM校正模型 evidence，也不自动验证它列全了可见类别或数字逐字来自截图。这样避免 oracle fallback，但也意味着后验 action binding 只能证明“模型声明的 target 与动作一致”，不能证明模型真实读取了全部图表证据。正式结果需逐 raw response/截图人工核 evidence records；不一致应保留为模型/方法失败，而不是 evaluator 修正。

4. **Formal 自动 paired checks 不是完整复核。** 当前 checks 会核 step-0 pixels/model image、M prompt treatment、C shared tail、R method pair、预算和 opaque task receipts；它不会自动重放每条 controller question 与 frozen template，也未把 native/system-prompt equality、current-only 每次 reset、submission→scorer exact join 全部浓缩为一个 gate。managed code path静态上正确，但结果审查仍须从 raw steps/receipts逐项复算，不能只信 summary。

5. **R 是 synthetic in-case OA。** 六页支持 pairwise-balanced main-shortcut诊断，不支持高阶 interaction、自然样本成功率或 benchmark generalization。role renderer 在当前环境能从 source 逐像素重建，但其跨环境 font/Pillow provenance 不如 D1 的双字体哈希绑定完整；本轮保存的实际 screenshots/receipts仍是行为解释的像素权威。

6. **C 的 empty 对比含 presence+length bundle，Solar/Wind 又含 entity/coordinate bundle。** C 只能报告同 final entity 的一次性 completion history差异；不能单靠 C 证明一般 correctness verification，也不能把 evaluator-built revision chain计为模型 recovery。

7. **Same-process scorer 边界。** scorer 与 runner 在同一进程，但不在 model/controller输入边界；只有真实 UI submission 后调用。结果审查必须确认无 submission 的格没有 scorer row；`TASK_COMPLETE`、no submission、correct provisional selection 都不是 success。

8. **Calibration 不是 model-call证据。** v3 calibration只证明页面、fixture、renderer和pairing。actual checkpoint input/history/memory/question receipts、opaque task join、controller reset-empty receipts及 raw outputs 必须等 formal 结束后验证。

## 允许与禁止的结果措辞

若 formal artifacts 通过后续独立审查，允许逐 condition 描述：

- evaluator-seeded M1/M2/M3 memory 相对 empty 对 observable Back、rebind、submission 的差异；
- 同一 GUI-Reflection checkpoint 下三个预注册 inference/state method bundles 的行为差异与额外调用成本；
- 六个 synthetic role counterfactual 中选择是否随 correct/misleading role、entity、chart/card position或color变化；
- current pixels相同条件下，三种 evaluator-owned history 对严格一次动作 Confirm 的差异；
- 只有真实 `effective reversal → correct rebind → submission → scorer true` 才称 task-level recovery。

禁止：

- 把 50 cells 写成 50 个独立样本、success rate或 held-out generalization；
- 把 current-only 写成未训练 reflection 的普通模型，或把 A 当训练消融；
- 把 evaluator memory/history/inherited choice写成模型自己生成的反思或错误；
- 仅凭 controller JSON/action一致就称其视觉 premise 已被正确读取和撤销；
- 把 Back、Solar provisional、TASK_COMPLETE、no-submission、scorer absence或 `execution_complete` 等同成功；
- 把 explicit printed-value policy 的成功表述成原始 GUI-Reflection 本身已经解决误导可视化。

## Final pre-run condition

应使用上述 v3 calibration summary、默认 audited repo/checkpoint与 managed local service启动；不得传 `--agent-url`，不得在看到任何 formal output 后更改 prompt、matrix、renderer或 controller。若 launch 后代码/asset发生变化，应停止并重新确认 calibration 的适用性，而不是继续把旧 gate 当 current-build 证据。
