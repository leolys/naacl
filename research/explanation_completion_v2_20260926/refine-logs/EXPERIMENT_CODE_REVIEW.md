# 对抗代码审查

审查路由：same-family / provisional。所有回复原文均留存，不把工程通过作为模型效果。一次实际阻断修复：独立核验上下文剥离 claim_kind。

## 提示预审

提示层预审（只读；research-review 本地分支，review_independence=same-family，acceptance_status=provisional）：目前未见 BLOCKING。总体已做到：保留各链具体自然语言 C；明确 conditional_inference 是在该链显式 O/B 前提下检验，B_applicability 单独判断当前图适用性；反问/补齐不强制冲突、新链或纠错；明确缺证≠否定、竞争链≠本链无 C，且标签/惯常几何均无自动优先。3 个 NON-BLOCKING 待代码联审：1) COMMON 允许新链输出 proposal_relation，但 GENERATOR/SUPPLEMENT 的 JSON 示例均未列此字段，可能造成 schema/parser 漂移；应二选一对齐。2) claim_kind='challenges_support' 仍同时覆盖“推出负结论”和“仅缺乏支持”；文字虽区分，但枚举本身过载，须确认 workflow/core 不据此自动转成 refutes/否定。3) SUPPLEMENT 的“Only add it if grounded in visible or public information”与“final applicability checked later”略有张力；原稿 3.2.2 允许反向解释先作待核验条件假设，故 grounded 应只约束 O/公开动机，不能先要求 B 已适用。另：GENERATOR 已定义但不在 PROMPTS 映射内，后续确认未被旁路调用即可。等完成版重点审 conditional valid 是否误激活 pending/refuted 规则、新旧隔离、mock 标识与零 API。

## 联审阻断记录

完成版联审发现 1 个可小修的真实 BLOCKING（正好进入唯一修复回合）：`workflow.build_context('verification')` 在 workflow.py:118-124 只剥离 `question_ids/relationship/proposal_relation`，却保留了候选生成器的 `claim_kind`。对 supplemental chain，它可能直接是 `challenges_support`/`undetermined`，属于候选角色/倾向标签，与注释“No preference/role metadata”和计划“不给独立核验器偏好提示”不符，也让过载的 `challenges_support` 有机会在核验端重新诱发“缺支持→否定”。具体自然语言 `claim` 与 `option_label` 足以核验 C；建议 verification context 同时 `pop('claim_kind', None)`，并扩展现有 `test_verifier_omits_proposal_and_questioner_assessments` 断言该字段未发送。其余关键路径目前通过：状态只聚合 B_applicability；valid conditional 不激活 pending/refuted B；C 原文保留；relation 不从 option 推断；真实三例仅 prepared_not_sent/not_run；Route fixture 全程 offline_fixture；无 API 客户端。独立复跑 34 passed。NON-BLOCKING：core.py:111-115 对 incomplete 只要求 missing_premises 非空，未强制 premise_ids 含本链/本规则，弱于提示通则但 target_id 可恢复链/规则，不建议为此扩大改动。修完上述一处后我复核并给最终 PASS/结论。review_independence=same-family；acceptance_status 暂为 provisional。

## 修复复核

修复复核结论：工程 PASS，无剩余 BLOCKING。workflow.py:120 已在 verification 投影中剥离 claim_kind，test_workflow.py:60 覆盖每条链均不携带该字段；mock_route_demo_final/verification/input_context.json 实查无 claim_kind/DO_NOT_SEND。独立重跑新旧联合测试（`--import-mode=importlib`）为 68 passed、3 条继承依赖 warning；tests/offline_receipt_final.xml 也记录 errors=0/failures=0/tests=68。
关键边界核验通过：① 每链 C 原文保留，未统一 yes/no；② conditional_inference 与 B_applicability 分离，valid 不会激活 pending/refuted 规则；③ claim_kind/option 差异均无运行时自动否定或 relation 推断；④ 规则状态只聚合 B_applicability，细化不回写原规则；⑤ 真实 b001/b002/pub013 仅 prepared_not_sent、v2_model_results=not_run、0 requests/0 GPU/0 business；⑥ Route A/B 仅 offline_fixture，B 均 undetermined、两规则 pending；⑦ 无客户端/live入口，旧工件未覆盖，prepared_final/mock_route_demo_final 为修复后新快照。
NON-BLOCKING/范围说明：incomplete 允许 premise_ids 不含本链/规则，弱于提示通则，但 target_id 与 chain.rule_id 可恢复归属，未造成跨链借用或状态误激活，不建议继续扩张本轮。README/CORRECTION_ZH 仍举旧目录名 prepared_v2/mock_route_demo；最终交付应明确以 prepared_final/mock_route_demo_final 和 offline_receipt_final.xml 为准，旧目录是保留的前序快照。这是交付指向提醒，不是逻辑阻断。
评审标识：review_independence=same-family；acceptance_status=provisional。此 PASS 仅表示协议结构、离线编排和隔离回归通过；本轮 0 被测 API，因此不构成模型语义效果、图表理解能力或防御增益的证据。

## 最终回复

最终审查：工程 PASS，无剩余 BLOCKING。

- 修复已验证：独立核验输入不再携带 `claim_kind` 等候选角色/偏好字段。
- 新旧联合测试独立复跑：68 passed；3 条既有依赖警告。
- `conditional_inference=valid` 不会激活 `B_applicability` 待定或被反驳的规则。
- 每链具体 C 保持原文；缺证、推导无效均不会自动生成反命题。
- 真实三例仅准备输入：0 API、0 GPU、0 业务操作，真实新版结果为 `not_run`。
- Route A/B 结果明确标记为 `offline_fixture`，不属于语义或视觉能力证据。
- 修复后交付应以 `prepared_final`、`mock_route_demo_final` 和 `tests/offline_receipt_final.xml` 为准；旧目录是保留的前序快照。

评审标识：`review_independence=same-family`，`acceptance_status=provisional`。该 PASS 仅覆盖协议结构、离线实现、隔离与回归；不证明模型语义效果或防御增益。
