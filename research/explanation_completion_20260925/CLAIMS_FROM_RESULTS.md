## RESULT-TO-CLAIM 判定

- `claim_supported: yes`，仅限纠正后的窄工程主张。
- `semantic_gain: partial`
- `review_independence: same-family`
- `acceptance_status: provisional`
- `confidence: high`（工程事实）/ `medium`（语义判断）
- `integrity_status: unavailable`（无正式 `EXPERIMENT_AUDIT`；现有 `WIRE_AUDIT` 为 PASS）

### what_results_support

- 三个固定开发样本均完整跑通 questions → supplement → verification → rule save/reload。
- 独立核算确认：9 个真实 HTTP 200 请求、每项 `attempt=1`，即 0 retry；128,131 input tokens、9,342 output tokens，按冻结公式正好为估算 `$0.4324315`，不是实际账单。
- b002 的两条竞争初始链均保留；流程允许 refinement、support-gap、未解决及零新增。
- 三例规则状态保存后重载内容一致；refinement 均 `applied_to_original=false`。
- 语义上：
  - b001 的标签—扇区面积冲突真实，refinement 有实际证据增量，但部分复述原条件。
  - b002 的“当前证据不足以在 Edge/Firefox 间确定选择”成立。
  - pub013 的 IL/DE/KS 选项内排序成立；灰色州无图例定义也是有效范围提醒。

### what_results_dont_support

- 不支持反问优于普通重读、因果收益、泛化、完整性或方法优越性。
- 不支持实际动作、业务提交或持久规则已被 actor 使用；三例均明确 `actual_actor_use=not_run`、`cross_step_effectiveness=not_tested`。
- `active` 只表示 B 层规则状态，不能冒充 C/动作确认。尤其 b001 的 implication 仍为 `undetermined`。
- b002 的新增 support-gap 基本是既有两条条件链的显式汇总，不宜称为新的事实发现。
- pub013 不支持“IL 是全图唯一最高风险州”；多个非灰州颜色接近，且灰色含义未知。

### 关键语义限制

- **b002 存在 B/applicability 混淆**：两条“若标签权威/若柱高权威”的条件逻辑本身可成立；当前图未证明哪个前提适用，应主要落在 applicability/implication，而不是把 B 判为 `undetermined`。
- **pub013 范围需统一**：可选动作只有 IL/KS/DE，不等于指标文字天然限定为三州。全图讨论可作为 scope qualification，但只能说“未见明显高于 IL 的非灰州，可能并列且受图像精度限制”；灰州只是未知，不能当反例。
- `EVIDENCE_PRECHECK` 只证明字符串存在，不证明语义主张正确。

### missing_evidence

若要提出更强主张，仍缺：

- 等信息、等预算的无反问对照；
- 预注册的更大未见样本与独立人工/跨家族语义裁决；
- 分离“条件规则成立”与“当前实例适用”的核验字段；
- actor 实际读取规则后的行为测试；
- 若坚持 pub013 全图主张，需要明确的比较范围、灰色/no-data 语义及并列处理。

### suggested_claim_revision

“在三个固定开发样本上，系统以 9 次无重试请求跑通了保留完整初始解释集合、反问、补充/细化、分维核验及作用域规则保存—重载流程。输出显式化了若干真实条件和范围缺口，但其语义判断仍为同族模型的暂定候选；结果不证明反问的因果优势、解释完备性、未见泛化、动作正确性或规则的下游采用。”

### next_experiments_needed

当前三例工程目标已闭合，**无需追加实验**。只有要升级语义或因果主张时，才需要：

1. 先修正 B/applicability 分层并做独立盲审；
2. 再做等预算无反问对照和未见样本评估；
3. 若声明持久规则有效，再做带日志的 actor 消费测试。
