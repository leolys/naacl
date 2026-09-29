# Expanded targeted-recovery：独立结果红队审计

日期：2026-09-01  
对象：`matched_annotation_v1`、expanded natural/inherited runs、五个 clean-only screens，以及 `EXPANDED_TARGETED_RECOVERY_RESULTS.md`。本审计从 raw steps/events/screenshots/intervention/validator/scorer 重算，不以 summary 的结论字段为真值。

## Verdict

- **有效性：CONDITIONAL VALID。**正式纳入的 16 个完整 run（54 cells）未发现 P0 artifact-integrity 异常；可作为受控、逐 case 的 diagnostic evidence。
- **发布状态：NO-GO for released benchmark aggregate。**所有 matched/inherited quartet 仍自报 `reportable=false` 和静态 `*_pending` blockers；3 个 asset manifest 也为 `reportable=false`，derived cases 仍为 `manual_evidence_pending`。这不推翻 raw 行为，但禁止称为 publication-ready benchmark score。
- **方法归因：CONDITIONAL。**natural F0 没有出现纠错成功；positive reversal/rebinding 只出现在 evaluator-owned inherited F3。应归因于“GUI-Reflection checkpoint 在显式外部 contradiction 下的 capacity”，不能归因 GUI-Reflection workflow 自身发现或修复错误。

## P0 / P1 / P2

### P0：有效 runs 中未发现；以下目录必须硬排除

1. `runs/expanded_inherited_f3/pub010/L0/20260831T181307Z_c4471293/`：只有 `ABORTED_PREEXECUTION.json`，`model_called=false`。
2. `runs/expanded_inherited_f3/pub010/L0/20260831T181504Z_514b8646/`：4 个行为 cells 机械自洽，但 top summary `execution_complete=false`；已有 `SUPERSEDED_VALIDITY_SEMANTICS.json`，正式 L0 只用 replacement `20260831T181935Z_0fe8c65d`。不得重复计数。
3. `runs/expanded_stage1_calibration/pub005/20260831T174336Z_4842b12a/`：只有两个 partial official cells，无完整 quartet/top summary/receipts；`ABORTED_P0_PAIRING.json` 明确 pair 与 evidence 不充分。不得作行为结论。
4. `b038` 与五个 clean-screen case 未通过准入时，缺少 inherited/official 后续 run 是 protocol stop，不得把“未运行”编码成 0 recovery。

### P1：写论文前必须收紧

1. **静态 reportability 不一致。**raw receipt 链已存在，但 `RecoveryQuartet.publication_blockers` 仍固定列出 registry/browser/receipt/history 等 pending 项。结果报告已披露此点；在 schema 状态没有一致化前，只能称 controlled diagnostic。
2. **聚合键风险。**有效 operational `pair_group_id`/`task_instance_id` 都带 `:asset_variant:matched_annotation_v1`（轮换再带 layout suffix），但 `task_id`、slug 和 `canonical_pair_group_id` 沿用 canonical。按 task ID、slug 或宽目录 `rglob(summary.json)` 会混 canonical/superseded；必须用完整 variant identity 和显式 allowlist。
3. **F3 归因。**F3 明示“当前 inherited selection 与独立 outcome 冲突”，最后又显示新选择 consistent。它不泄露正确按钮，但属于二元 correctness oracle；positive result 不是无提示 premise revision，也不是 natural recovery。
4. **措辞强度。**`b035` 只能写“checkpoint 在 externally supplied F3 下完成 semantic recovery”；“native history helps Confirm”在这里只是一个 clean cell 的对应差异。`pub010` 只能写“三个确定性 layout 中未使用 contradiction 撤销 misleading-title premise”，不能写绝对“不能”。
5. **scorer/validator independence。**它们对模型隐藏且与 model actions 分离，但由同一实验进程的 canonical stores 生成；“independent”只能指 model-independent，不代表独立服务或独立人工裁决。

### P2：解释边界

- `pub010/b035/b038` 是同一 title-vs-line family，不是三个独立 misleader 类型；layout/history 是 repeated cells。
- clean title 本身写出正确趋势，official title写出相反趋势。这是预声明 title-cue intervention，不是意外泄漏，但只识别 title-cue resistance，不代表一般图表数据读取。
- enriched/adaptive selection、单 checkpoint、确定性单轨迹不支持 prevalence、显著性或总体 recovery rate。
- timeout 只表示在 8-step budget 内未提交，不能表述成模型永远不会 Confirm/恢复。

## 机械复算

正式 allowlist 共 16 runs：11 个 matched/inherited runs（44 cells）加 5 个 clean-only runs（10 cells）。独立复算得到：

| evidence | count | anomaly |
|---|---:|---:|
| cells / raw steps / events | 54 / 199 / 191 | 0 |
| PNG | 223（199 step + 24 intervention） | 0 |
| evaluator interventions | 24 | 0 |
| validator records | 26 | 0 |
| actual submissions / scorer records | 34 / 34 | 0 |
| request IDs / response IDs | 199 / 199，均唯一 | 0 |
| transaction IDs | 91，跨 cell/step 无复用 | 0 |

199/199 step PNG 和 24/24 intervention PNG 的磁盘 SHA 与 receipt 一致。24/24 inherited handoff 均为 `task_step=0`、empty action/history/memory，且 intervention 标为 evaluator-owned、`normalized_as_agent_selection=false`。26/26 validator 的 pair/task/arm/layout/token-position/action/contradiction 全匹配；34/34 submission 均可 join UI transaction、submission event、scorer event，success 与 expected action 一致。所有 timeout 都耗尽 max steps 且无 submission/scorer。

同一 checkpoint 与 generation config 覆盖全部 54 cells：`craigwu/GUI_Reflection_8b_SFT@720d6239d18215417a80ac49f444a6145e073e9c`、deterministic decoding、`compact-recovery-v4`。仓库正式 unittest 入口独立复跑为 177 tests OK、2 skipped。

## Matched assets

三个 manifest 的 canonical CSV、HTML title、font、canvas 与 assets 均重新读取并在内存重画；6/6 chart PNG 与重画结果逐像素相同。

| case | rows | net change | diff pixels | diff bbox | outside mask |
|---|---:|---:|---:|---|---:|
| `pub010` | 12 | +1924 | 8,494 | `[98,24,901,46]` | 0 |
| `b035` | 6 | -1425 | 7,527 | `[164,24,836,46]` | 0 |
| `b038` | 4 | +533 | 6,239 | `[199,24,803,46]` | 0 |

三对均为 1000×750 PNG、同 renderer/font/axes/data line；official-clean CSV 逐字节相同。自然 run 的网页首帧 official-clean 差异也只落在 chart title：pub010 三布局 bbox 相同，同 arm workflow-on/off 的首帧和首次 raw response 10/10 pair 相同。未发现模型可见的 canonical action ID、role、ground truth、pair/task identity 或 asset path 泄漏。

## 逐 case 核验

### `pub010`

**Natural L0/L1/L2（12 cells）**：clean single/F0 6/6 正确提交；official single/F0 6/6 真实提交 decline trap。correct 与 trap 都轮遍 position 0/1/2。三个 official F0 都消费 review 后直接 Confirm，0 effective Back、0 correct rebind。因此它证明 matched title-only natural susceptibility 和 clean competence，**不证明 natural recovery**。

**Inherited F0 L0（4 cells）**：四格均为 evaluator 注入 decline；0 Back、0 rebind。native4 两臂提交错误，current-only 两臂 timeout。

**Inherited F3 L0/L1/L2（12 cells）**：

| arm / history | Back | correct rebind | correct submit |
|---|---:|---:|---:|
| clean native4 | 3/3 | 3/3 | 3/3 |
| clean current-only | 3/3 | 3/3 | 0/3 |
| official native4 | 0/3 | 0/3 | 0/3 |
| official current-only | 0/3 | 0/3 | 0/3 |

clean current-only 在 final review timeout；official native4 直接 Confirm inherited wrong；official current-only 留在 review timeout。允许结论是：同一 explicit contradiction 可被执行，但 misleading title 在三个布局中稳定阻止 premise/action revision；history 只改变 clean completion。不能把 evaluator 初错计成模型错误或 natural recovery。

### `b035`

Natural matched：clean 2/2 正确提交；official 2/2 提交 neutral routine-monitoring，而非预声明 capacity trap。因此可称 title intervention 扰乱 action binding，不能称 exact natural trap susceptibility/recovery。

Inherited F0：0/4 Back、0/4 rebind；一个错误提交、两个 timeout、一个 `TASK_COMPLETE` 无提交。Inherited F3：4/4 effective Back、4/4 correct rebind，但只有 clean native4 1/4 最终正确提交；official native4 在 correct final review 发 `TASK_COMPLETE`，两格 current-only timeout。它是“semantic recovery ≠ end-to-end recovery”的有效正例，但 semantic recovery 依赖外部 F3。

### `b038`

Matched natural 4/4 都有真实 submission，但 0/4 success：clean 两格选择 neutral manual review，official 两格选择 stable-title trap。canonical release Stage-1 的 clean 2/2 success 没有在 same-render intervention 下复现。按预声明规则停止 inherited F3 是正确的；`b038` 只能作为 renderer sensitivity / clean-competence failure，不得择优引用 canonical G1 后再声称 controlled recovery eligibility。

### 五个 clean-only screens

五个 top summaries 都只有 `candidate_clean/reference_clean`，共 10/10 clean cells；没有 official cell/file/event/render path，且 `official_arm_not_run=true`。决策符合预声明规则：

- `b008`：2 timeout、无 selection；reject。
- `env003`：两格 Hydroelectric trap，仅 single-attempt 错误提交；reject。
- `pub012`：两格 NY trap，仅 single-attempt 错误提交；reject。
- `pub009`：两格 neutral Thu-only，均错误提交；reject。
- `env025`：2 `TASK_COMPLETE`、无 selection/submission；reject。

这些是 clean capability-floor evidence，不是 misleading-chart recovery failure，也不能因未跑 official 而计为 official 失败。

## 对主结果报告的核验

`EXPANDED_TARGETED_RECOVERY_RESULTS.md` 的资产数字、pub010 三布局计数、b035 分层、b038 matched failure、五例 clean-only 决策以及 aborted/superseded 隔离均受 raw artifacts 支持。没有发现数值 P0。

论文引用时应将以下概括收紧：

- “GUI-Reflection can achieve semantic recovery” → “the GUI-Reflection checkpoint, after evaluator-owned F3 contradiction, executed semantic recovery in b035”。
- “native trajectory history helps” → “native4 coincided with Confirm in one b035 clean cell and three pub010 clean layouts”；不是跨 case causal estimate。
- “cannot invalidate/use contradiction” → “did not do so in the tested deterministic cells/layouts”。
- central claim 的 positive 部分必须带 “with explicit external contradiction feedback”；natural F0 本身没有 recovery success。

## 允许 / 禁止表述

允许：

- matched title-only manipulation caused stable clean/official divergence in `pub010` across three card positions；neutral F0 did not repair it。
- under evaluator-owned F3, the checkpoint showed 10 effective Back + correct-rebind trajectories across `pub010` clean and all `b035` cells, but only 4 became correct submissions。
- `b035` demonstrates a semantic-to-completion gap；`b038` and five screens establish clean-competence/renderer boundaries。
- results are case-level, controlled diagnostics with raw receipt support。

禁止：

- GUI-Reflection generally solves—or never helps—misleading charts；或报告 enriched panel recovery rate/显著性。
- 把 inherited selection、F3 correctness oracle 或 final “consistent” feedback冒充模型自主错误发现。
- 把 Back、correct rebind、Confirm、hidden-scorer success 合成一个未分层的 recovery。
- 把 timeout 写成永久能力缺失，把 missing/not-run cells 写成失败。
- 混入 preexecution、superseded L0、pub005 partial，或按 task ID/slug 把 canonical 和 matched variants 合并。
- 把 same-process hidden scorer/validator 称为外部独立裁决，或把这些 `reportable=false` diagnostics 称 released benchmark aggregate。

## 正式 allowlist

- `runs/expanded_matched_title/pub010/{L0/20260831T180601Z_4786f584,L1/20260831T180848Z_5e1aa625,L2/20260831T181037Z_87780597}`
- `runs/expanded_matched_title/b035/L0/20260831T183321Z_0524ce46`
- `runs/expanded_matched_title/b038/L0/20260831T183125Z_f13b1f85`
- `runs/expanded_inherited_f0/pub010/L0/20260831T183846Z_ab6dd2c5`
- `runs/expanded_inherited_f0/b035/L0/20260831T184157Z_fa5164ce`
- `runs/expanded_inherited_f3/pub010/{L0/20260831T181935Z_0fe8c65d,L1/20260831T184526Z_d81fe641,L2/20260831T184839Z_21345732}`
- `runs/expanded_inherited_f3/b035/L0/20260831T183521Z_ba17e32f`
- `runs/expanded_clean_screen/{b008/20260831T182251Z_9f49514c,env003/20260831T182504Z_95948e70,pub012/20260831T182633Z_97921909,pub009/20260831T182754Z_cd7b7045,env025/20260831T182919Z_fdff14ab}`
