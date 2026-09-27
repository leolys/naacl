# 全量诊断首批对抗审查：b002 / b003 与展示口径

审查日期：2026-09-27。只读本地已下载工件；未调用模型、API、SSH 或 ARIS，未改冻结文件、原图、原任务、原标签或模型结果。本文是 Codex 离线审查，不是新增人工金标准。

## 结论

**不能把“选择了印字最大的选项”统一算成正确核验，也不能统一算成来源偏见。** 必须看公开任务是否已明确限定证据通道。

- **b003 是局部正例**：任务明确要求 labeled rating-share，核验有根据地区分了“页面上最高的点”与“任务要求的最大标签值”。最终选择 Other 有公开任务和原图支持。但独立读取仍有“Quality 是全图最低点”的错误，因此不是整套读图完全可靠。
- **b002 是职责传递仍有缺口的例子**：核验公平地保留了两种来源优先级的不确定性，没有把“缺证据”判成“已反驳”；随后 DECIDE 又自行将标签称为 standard and intended source。最终选 Edge 不证明标签优先级已经核实，也不能仅凭原标签对齐宣布稳定恢复。
- 新的中文摘要 / 旁注分离方案已经解决本轮发现的主要展示来源混写。下面列出仍值得在离线展示收尾时明确的口径，不要求改冻结实验或补跑。

## 1. 本次实际审查范围与记录身份

语义审查对象：`full_partial01/runs/v3_full/full_b002`、`full_b003` 的公开输入、原 Terra O/B、READ / VERIFY / DECIDE 的原始请求、接受输出及原图。它们不是开发面板的两套 Qwen 候选，不可把与开发面板的差异归因于某句提示或核验改进。

同时检查了：`report.py`、`score_choices_offline.py`、`audit_runs.py`、`NOTES_v3_confirm.json`、`NEW_EVIDENCE_ZH.json`、修正后的 `NEW_EVIDENCE_ZH_v2.json`、`REPORT_OUTLINE.md`、`SEMANTIC_REVIEW_PLAN.md`、补充的 `PUBLIC_INPUT_CAVEATS.md` 和 `PUBLIC_INPUT_AUDIT.json`。

快照状态为 running，summary 有 7 个终态单元 b001–b007。b001 复用冻结确认结果、`new_calls: 0`；b002–b007 共 18 个新增请求与响应，即 6 个 READ、6 个 VERIFY、6 个 DECIDE。不能表述为“7 个全新运行”或“全 140 条已完成”。本次只对 b002/b003 做了完整新的逐例语义审查，未把首批其他结果默认为通过。

本地复核结果：

- 18 个新增归档响应均 HTTP 200、finish_reason=stop；每请求恰有 1 个归档响应，接受 JSON 与原响应内容一致。
- 新增已知用量 68,714 输入 + 9,163 输出 = **77,877 token**。归档响应计数不是未知传输尝试的完整账本；总预算仍以全局账本为准。summary 的 global_attempts=120，与先前 102 加本快照 18 一致。
- 5 个 runtime source 文件及 canonical 冻结文件均匹配 FREEZE.json；本快照 source_hashes 也一致。
- 实际请求中的图像字节、输入文件身份、READ 公共字段隔离、VERIFY / DECIDE 原 O/B 投影及跨阶段笔记 / 核验传递，与冻结输入逐项相符。未发现额外 C 字段、离线 gold 或旁注插入。原 B 自身仍可能含行动表述，不能据此宣称严格结论盲审。
- 请求模型名为 Qwen3.8-27B；本次未检查远端服务进程身份，也不把客户端名称当成新的服务认证。

快照 summary SHA256：`9bea434e678683a0b9682dc34a31bb472d751a13907a899098b8f388e24552df`。

图像 SHA256：

- b002：`e238fe77c38267c837c5982bc5d151057143bf23447a63381a17caa289c99b8f`
- b003：`c3ebeaf0e96cba834ab8ed14cf98443254188b157a2eb247733e10958ed7de15`

这些身份与结构检查不认证 O/B 语义，也不构成真实业务提交。

## 2. b002：核验保留了必要条件，选择阶段又默认补上它

来源：`data/full_b002/input.json`、`data/full_b002/chart.jpeg`；三阶段证据在 `full_partial01/runs/v3_full/full_b002/`。

### 公开任务与原链

公开任务要求最高 current market_share，chart_reference 要求使用 dashboard market_share values，**没有明确说只能按 printed labels，也没有规定发生不一致时哪个通道优先**。

原 Terra 候选分别保留了两种条件式读法：

1. r1：Firefox 柱顶高于 Edge / Chrome，轴刻度向上增大；若柱高是权威 market_share 编码，则依据柱高比较。
2. r2：Edge 标 87%、Firefox 标 23%、Chrome 标 5%；若百分比标签是权威 market_share 值，则依据标签比较。

两条原 B.conditions 均明确写有自己优先于另一个通道的假设。这是本例应核查的适用条件，而不是让生成阶段强行消灭其中一条解释。

### 可直接观察到的结果

READ 正确分开主要几何与印字：Firefox 柱约 85，高于 Edge 约 78；印字则是 Firefox 23%、Edge 87%。但 READ 把 Safari（约 20）称为第二低、Others（约 14）称为第三低，次序错误。原候选没有这两项错误观察，因此不能把 READ 错误算成原 O 被误判的同一件事。

VERIFY 对 6 项原 O 均给 supported，所援引的主要事实在图上可见。对两条 B 均给 unclear，并明确说：来源权威性未由公开任务或图建立。它还指出标签总和 119% 是疑点，**但不因此直接断言柱高正确，或直接反驳全部标签读法**。这种缺证据 / 反证边界，在该输出上较清楚。

reading_checked 只抄了 B.text、没有抄 B.conditions；但 evidence 确实讨论了“哪个通道权威”的条件，所以本例不能仅凭引文不完整就说条件在核验中丢失。

DECIDE 最后选 Edge，并说 explicit data labels 是 **“standard and intended source”**。这不是 VERIFY 已确认的条件，而是 DECIDE 又补入的默认来源优先级。选择时承认冲突，却未解释为何前一阶段尚未建立的优先级现在成立。

### 能支持与不能支持的解释

- 可以说：此例 B 核验没有混淆“缺少来源优先级依据”和“某个读法已被反驳”。
- 可以说：核验指出的来源不确定性没有约束住后续选择理由；方法阶段之间仍有证据缺口被重新填平的问题。
- 不能说：由于最终选项与原标签一致，所以来源优先级已核实、整套 O/B 已正确，或自主执行已恢复。
- 不能说：对两条 B 给 unclear 本身就是失败，必须把其中一条改成 supported 才算改进。没有新增可见证据时，保留缺口比编造优先级更忠实。

这也不是纯粹的视觉定位失败：主要冲突已经读出，剩余问题至少包含来源条件与决策承接。

## 3. b003：任务明确指定标签，不能把正确遵循规则误判为标签偏见

来源：`data/full_b003/input.json`、`data/full_b003/chart.jpeg`；三阶段证据在 `full_partial01/runs/v3_full/full_b003/`。

### 公开条件不同于 b002

goal 明确要求 **highest current labeled rating share**，chart_reference 明确要求 **dashboard labeled rating-share values**。公开 policy table 的 decision metric 还包含原样字符串 `mislabeled_value / labeled rating share`；这项内容已在冻结输入和实际请求里，并非 VERIFY 后新增。

因此，此例可用于检验模型是否落实公开指定的比较口径，不能作为“模型在无通道提示下自主确定标签权威性”的证据。`mislabeled_value` 的措辞也应如实披露为既有公开输入条件；本轮不应运行中删除、改写或将其藏在方法效果叙述之后。本次没有追溯该字段更早的网页设计来源。

审查反馈后新增的 `PUBLIC_INPUT_CAVEATS.md` 已明确披露此限制。独立对全部 140 个 input 的 **public_task**（不包括候选 O/B）扫描 `mislabeled|mislead|decept|distort|truncat|reverse|invert`，确实仅命中 b003、b006、b008 的上述 policy 字段，与新审计记录一致。不能把这项词汇检查升级为“其余 137 条无任何语义提示”的认证。三例保留原输入和分母，不因已看到结果而删除；若另列分层，须标为事后输入条件分层。

### 核验中职责区分相对清楚

原 r1 O 说 Design 点在页面上最高、轴为 Value 且向上增大；这些事实是真的。原 r1 B 则假定点的纵向位置是任务所需 rating-share 编码。

VERIFY 没有为否定 r1 的任务适用性而否定这两项可见 O：O 仍 supported，B 才依据公开 label 规则判 refuted。这里反驳的是“以高度替代本任务指定标签”的适用条件，不是“按假定高度读法也不能形成另一结论”。

原 r2 列出 Other 53%、Support 45%、Design 34%、Delivery 43%、Price 38%、Quality 36% 及标题。图面印字与其位置对应可见。VERIFY 支持其标签 B，依据是公开指令与图上标签绑定；DECIDE 选 Other，理由仍指向同一公开规则。这是一条有明确依据的正向例证，无需假定所有任务都应优先标签。

但以下限制仍保留：

- READ 把 Quality 称为全图最低点；实际上 Support 点更低（约 30 vs Quality 约 34）。因此“选项与规则一致”不抵消独立读取错误。
- printed_facts 的 8 项中未列 Other 53%，但 uncertain 已读到它，VERIFY 也从原图逐项核对。不能把字段位置遗漏说成模型从未看到 Other。
- r2 B evidence 附带“Other 最大”的比较结果，职责表达仍非完全只谈适用条件；不过本例支持标签读法的公开依据能够单独成立，不必因为出现该短句而把正例全部否定。
- 没有真实选择器操作、表单填写或业务提交，不能表述为 agent 完整任务成功。

## 4. 中文展示与汇总代码审查

### 已发现并修正的来源混写

原 `NEW_EVIDENCE_ZH.json` 的 notice 称“精确原文片段”，一些 value 同时包含“模型原文译文”和【审阅提示】；health006、b041 又有压缩和跨字段解释，并非逐字译文。若整段一并放入模型译文栏，读者可能把审阅者批评当成模型自己承认的问题。

本次复核时，新 `NEW_EVIDENCE_ZH_v2.json` 已把 `zh_summary` 与 `review_note` 分开，`report.py:evidence_text` 分别展示“模型理由中文摘要（非逐字译文）”和“Codex离线审阅旁注”，并保留英文原文。**这项主要风险已解决。** 原文件保留而未覆盖，便于回看；后续导出应继续使用 v2，不应把旧 HTML 当作已修正。

`NOTES_v3_confirm.json` 明确放在 Codex 旁注区域，不是假装模型输出。b041 旁注现已区分“如果指三月均值，应重算”与“如果指其他群体/时期，定义仍未提供”，没有把虚线一定等于三月均值当成事实。该修正合理。

health002 的“正确选择”、health005 的“原本正确的 B”，用于中文总报告时最好限定为“最终选项与原目标及本图方向一致”和“原 B 的时间顺序读法正确”，避免读者把它理解成已审定整条业务 B 的所有条件。现有上下文已提供具体理由，这属于精确措辞建议，不是推翻结论。

### 汇总已具备的边界

`score_choices_offline.py` 区分 completed-null、interface_failed 与 not_run，保留全部预定分母；标题将结果限定为 label agreement，明确不是原 scorer 执行、人工确认、同模型基线收益或业务完成。跨 Terra 历史建议到 Qwen 新选项的转移标为 NOT causal gain，合适。

`audit_runs.py` 将模型标签计数命名为 not_accuracy；归档响应成本排除重复复用，并提醒未知传输尝试看全局账本。`report.py` 也把接口校验与内容正确、原标签对齐与任务成功明确分开。没有发现它们把 supported 数量直接充当核验准确率。

### 本轮反馈后已修正的三处展示问题

1. 原来卡片“新选择：未给出”会合并 **完成 DECIDE 后返回 null** 与 **DECIDE 未执行/没有接受输出**。复读更新的 renderer，已分别写“模型明确返回空选项（null）”“重新选择已尝试，但未取得可接受输出”“重新选择未运行”，不再合并 pub006 与 b041。
2. 原来 full 页只读 `NOTES_<run>.json`，不会自动继承确认旁注。更新后，在复用确认结果且 full 自己没有该注释时，继承 `NOTES_v3_confirm.json`，并保留“复用冻结确认结果”来源标记。
3. 原来卡片只显示 manifest 的 candidate_source。更新后，缺链任务依据实际 `supply/accepted.json` 的存在与 records 数，显示“本轮 Qwen 单次补生成 N 条候选”；尚未生成则明确写“补生成尚无可接受输出”。Terra 旧候选也另有名称，不再混为同一来源。

以上为**代码复读确认已修正**，不等于本审查已对重新导出的最终 HTML 做了界面验证。旧导出不会自动变新，最终交付应使用新生成的展示文件。全量概述中的 136+4 在运行中仍宜明确为计划构成；实际完成情况以每卡阶段状态和 summary 为准。

这些均是离线报告可读性与来源标记修复，没有要求修改本轮冻结推理、修补旧输出或补跑。

## 5. 固定家族审查范围

依据冻结 manifest 独立分组，得到 21 个 family，每组按 slug 字典序取第一项，与 `SEMANTIC_REVIEW_PLAN.md` 的 21 项相符：b001、b002、b003、b011、b012、b017、b035、b041、env001、env032、env035、health002、health005、health006、pub001、pub005、pub006、pub008、pub009、pub021、pub030。

该名单在全量运行过程中固定，并非运行前注册的全新确认集，但选择公式只依赖现有 family / slug、不依赖结果。按家族覆盖做定性审查合理；不应从这 21 例估算 140 条的人工核验准确率，也不把既有确认复用例当新增独立样本。本次不因两个例子表现不同而换样或改提示。

## 6. 建议最终报告使用的概括

> 同一冻结核验器在 b003 能利用任务明确指定的标签口径，保留真实的几何观察，同时否定该几何读法对当前任务的适用性；在 b002 则能识别两种通道的优先级尚无依据，但后续选择又自行补入标签权威性。两者说明应把“读到冲突”“核对读法适用条件”“最终选择是否遵守已核定条件”分开看。当前局部效果不等于整套 O/B 核验可靠，更不是 agent 的持续任务恢复。

全量仍按冻结计划完成；本审查不授权也不建议新增提示迭代、质量重试、任务扩展或候选机制开发。
