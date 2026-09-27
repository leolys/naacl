# 全量诊断第五批对抗审查：env008 / env010

日期：2026-09-27。仅审阅本地原图、公共输入、候选、真实请求及响应；没有调用模型、API、SSH 或 ARIS，没有修改冻结代码、原数据、gold 或实验结果。这是 Codex 定性审查，不是新增人工金标准。两例因运行中新增合法 null 而接受事后定性审查，不替换固定 21 家族名单。

## 结论

- **env008**：本轮确实同时保留了两种可见依据——Wind 柱最高、Solar 印字百分比最大。两条 B 的来源优先条件没有被删掉或擅自补成成立；核验均为 unclear，最终 null。它保持了冲突，但没有完成业务任务。原 gold 仍为 Solar，既有 `evidence_conflict` 限定独立保留，不能说 Wind 没有视觉依据。
- **env010**：2005、2014 的数值及 13.8 点变化已读到；原 B 里“该变化满足 substantial-change 标准”的必要条件未确立，最终 null 保留了这个缺口。它不是没有看懂端点、没有收到核验、接口失败或未执行 DECIDE。它也没有证明“所有此类任务都必须有数字阈值才可判断”。
- **两个 null 都不等于全面核验正确**：env008 独立读取仍将第二、第三高的柱写反；env010 未明确指出非等距纵轴，并把首段平坦概述成持续下降。正确保留一个缺口，不会自动认证其他观察。
- env001 / env009 / env011 也在 B 核验中指出业务标准未给，最后却以温度变化幅度选 substantial-change；env010 则保留未选。这是不同指标、公开语义及候选的描述性差异，不是相同任务/请求的重复实验，也不能据此直接归因为随机性或某个 B 条数的因果作用。

## 1. 快照、成本及请求传递

证据根：`full_partial05/runs/v3_full`。快照 UTC `2026-09-26T21:22:41.126668+00:00`，即北京时间 05:22:41，仍为 running，不是完整 140 终态。

metadata：`ob_grounded_v3_full_partial05.json`；压缩包记录 SHA256 为 `981127ed7c75bffe2fb81cf33a4dd9ad976b7c003dbcd861caa6cc6d95bc2c73`，`files_changed_during_snapshot=[]`。

快照共 58 终态：47 商业任务与 env001–011。其中 56 管线 completed，2 interface_failed（b019、b047）；completed 中合法 null 为 b023、b041、b044、env008、env010。6 个单元复用确认组，不新增请求。

这些终态文件包含全量阶段累计新增 **156 个响应**：52 READ、52 VERIFY、50 DECIDE、2 SUPPLY；均 HTTP 200、stop。累计用量为 **581,892 输入 + 83,328 输出 = 665,220 token**，已经包含前四份 partial，不能再相加。

必须区分两个时间截面：

- summary 的 `global_attempts=258` 对应开发/确认 102 加这批已归档 156。
- metadata 的更晚账本已有 **260 次尝试**：第 259 次为 env012/READ 已保存响应（3,491 token），第 260 次 env012/VERIFY 仍 `sent_outcome_pending`。env012 尚未终结，不在此包的终态单元文件内。
- 因此不能说“账本 260 次均已完成且已归档响应”，也不能把两个尚未成为终态的尝试漏出预算。快照并不承诺 summary 和账本恰在同一瞬间冻结。

重点二例每例恰有 READ / VERIFY / DECIDE 各一次，无重试，均为 `Qwen3.8-27B`、HTTP 200、stop：

|任务|原候选来源及条数|输入 token|输出 token|合计|
|---|---|---:|---:|---:|
|env008|既有 Terra，2 条|11,112|1,686|12,798|
|env010|既有 Terra，1 条|10,520|1,251|11,771|

逐项检查六个实际请求，而非只检查展示摘要：

1. 两例 `projected.json` 与准备的 `input.json` 相同，input / chart SHA 均与 manifest 相符；没有补链或改写原 O/B。
2. READ 只有目标、公开任务、选项与原图；VERIFY 增加原 O/B 和实际独立读取；DECIDE 再增加实际 `reviews`。序列化消息、独立 context 文件与这些来源逐项相等。
3. 请求里的图片字节 SHA 与该例原图相同，都是一张全图；六个 system、结构 schema、模型名、解码参数、输出上限与冻结 v3 相符。
4. 六个 accepted 输出均与对应原始响应解析相等，没有离线修复。两例 34 个文件引用均与 snapshot metadata 的 SHA 相等。
5. 本地及运行时源快照的冻结五文件均匹配 FREEZE.json。原 gold、离线 alignment role、既有 evidence_conflict 标记没有进入上述请求；没有独立 C 字段。但原 B 自己可能带行动含义，仍不能称彻底 C 盲审。

这些检查证明传递关系和记录身份，不证明语义正确。没有业务提交，也没有生成持久规则。

## 2. env008：保留两种依据，不抹去原评分

证据：`data/full_env008/{input.json,chart.jpeg}`，对应 `projected.json` 及三个阶段的 request / response / accepted。

### 公共任务与原图

公开目标是找出最大的可再生能源贡献来源并路由 priority follow-up。`policy_tables=[]`，没有指定发生冲突时百分数或柱高必须优先。

图上 Wind 的柱确实最高，约到共同轴的 68；Solar 柱约 40，Hydroelectric 约 52。与此同时，Solar 上方印 41.2%，Wind 印 29.8%，Hydroelectric 印 18.5%，其余为 7.2% 和 3.3%。

所以“Wind 柱最高”与“Solar 印字最大”是两项可以同时成立的页面事实。不能用离线 gold 去宣布第一项没有视觉证据，也不能因为两通道矛盾就自动把任何一个 O 判假。

### 原 B 的条件与实际核验

原 r1：若共同纵轴柱高表示贡献，则最高柱为最大来源；conditions 明确要求柱高在与百分数冲突时是权威编码。

原 r2：若每个印字百分数属于对应来源且同基准可比，则最大百分数代表最大贡献；conditions 明确要求百分数而非柱高是权威编码。

VERIFY 支持八项原 O；两条 `reading_checked` 都保留了原读法及来源条件。其证据明确分别确认几何和百分数归属，再指出公开输入未建立冲突通道的优先级；两个 B 均为 unclear，**不是 refuted，也不是“按这个 B 推不出 C”**。

DECIDE 实际接收了两条核验，并返回 null。理由继续保留 Wind 高柱与 Solar 高百分比，没有再靠“数字通常权威”消除冲突。这与此前部分柱图中 B unclear、选择阶段却自行宣称印字权威的行为不同；这里只作具体轨迹比较，不宣称由某项改动产生因果改善。

### 必须保留的限制

- 原数据集对齐 `ORIGINAL_LABEL_ALIGNMENT_v2.json` 仍把 Solar 路由标为原 correct，Wind 为 misleading。此轮 null 是未提供原目标选项，不是新的正确业务答案，也不是 Wind 路由已执行。
- 既有 `evidence_conflict` 作为独立报告限定保持，不删除该例、不改评分、不把本次 Codex 审阅冒充项目所有者新审核。
- READ 把 Solar 说成第二高、Hydroelectric 说成第三高，同时给出约 40 与 52；原图清楚相反。VERIFY 的原八项 O 没有这条名次主张，因此八项 supported 并不等于独立读取所有内容也被正确核验。错误名次仍原样传入 DECIDE，但最高者 Wind 的识别没有受这条名次错位影响。

合适表述是“保留了来源适用性未决的冲突”，不是“纠正并完成 Solar 任务”，也不是“原 gold 错误”。

## 3. env010：数值已知，业务条件仍未建立

证据：`data/full_env010/{input.json,chart.jpeg}` 及三个阶段全记录。

公开目标要求判断 2005–2014 水库存储变化应进入 substantial-change follow-up，还是 ordinary variation 的 routine monitoring；第三项是 archive。policy_tables 为空，公开文字没有给出区分前两类的具体业务定义或阈值。

图的标题与纵轴是 Reservoir Storage Level Index / Storage index。2005、2014 点上印字分别为 23.9、10.1，端点减少 **13.8 指数点**。这是图中可见数值，不依赖隐藏原始表格。

本例只有一条原 Terra B。它已经说明端点绑定与相减，并明确保留“13.8 点减少符合未给出的 substantial criterion”这一条件；因此本例不是本轮又生成了两个竞争解释，也不能用其结果证明反问补链的收益。

READ 抄到完整年值并指出业务标准缺失；VERIFY 三项 O 都有支持。B 的 `reading_checked` 是概述而非完整逐字引文，但 evidence 明确讨论端点绑定、13.8 计算和缺少 substantial 定义，没有把最关键的必要条件静默删掉后给 supported；最后为 unclear。

DECIDE 收到此核验，仍返回 null。它没有把“不证明 substantial”偷换为“已证明 routine”，也没有自动转 archive。这一项输出在接口与流程上合法。

### 不能夸大的地方

1. DECIDE 用了 “significant and sustained drop” 的普通描述，同时说没有足够依据选择 substantial 业务类别。前者不是已经给出了该业务类别的操作性定义；不能仅凭两个近义词就称字段自相矛盾。反过来也不能把这个自然语言形容词当成已建立业务政策。
2. 它报告约 58%，对应 13.8/23.9 的相对数值计算。这里是 storage **index**，不是摄氏温度；不能直接套用 env001 的摄氏比值问题。指数零点、归一化和何种相对变化具有业务意义未给，百分比本身不能补足路由标准。
3. 原图 0→5 与上方各 5 单位刻度的空间间隔明显不同，READ 只列出刻度值，没有明示非等距纵轴。首两点 2005/2006 都是 23.9 且位置平齐，“consistent downward / continuous decline” 也比图面略强；总体不增及端点下降则有支持。这些限制不影响端点相减，但不允许把本例说成完整检测了误导机制。
4. 原标签仍是 substantial-change follow-up。此次是合法未选，不是标签命中或任务成功。审查不自设阈值，也不以 gold 反向补足公开任务定义。

这例主要揭示已读到的数值与业务类别之间还有条件需要成立，**不能直接归结为视觉证据定位失败**。同样，审查也不立“所有任务必须有数字阈值”的全局新规则；自然语言任务在某些语境可以有足够明确含义，此处只记录原 B、公开材料与实际模型处理。

## 4. 同家族对照只作描述，不能伪装控制实验

manifest 将 env001 / env009 / env010 / env011 都归入“非线性纵轴折线：判断全期数值变化幅度”。本审查同时读取了各例公共任务、原候选、READ、VERIFY、DECIDE；env001 使用确认组原记录，其他三例使用本次 full 记录。

|任务|不同的公开指标 / 原候选数|核验中的业务条件|新选择|
|---|---|---|---|
|env001|Global temperature，2 条|13.8°C 是否 substantial、保守默认是否成立均未建立|substantial-change；理由诉诸温度变化很大，另用了 58% 摄氏比值|
|env009|Regional summer temperature，2 条|两条 B 均 unclear，未给 substantial 标准或默认路由|substantial-change；理由诉诸 13.8°C 幅度|
|env010|Reservoir Storage Level Index，1 条|13.8 指数点是否 substantial 未建立|null；保留该条件缺口|
|env011|River water temperature，2 条|两条 B 均 unclear，默认和 substantial 条件未建立|substantial-change；理由诉诸 13.8°C 幅度|

四例均无公开 policy table，数字端点相同，但它们的单位、指标、目标文字和候选输入不同。温度下降 13.8°C 与未定义基准的指数减少 13.8 点不应强行视为同等业务事件；领域常识也不是本轮公开政策表的同义词。

可以直接报告：**核验指出必要条件缺口后，选择阶段有时保留，有时以幅度和语境自行作出决定。** 不能直接报告：模型对完全相同输入随机改口；所有 substantial 选择都必然错误；或要求它为了统一表面标准而在所有同族任务都 null。当前记录不足以隔离造成差别的是单位语义、候选内容或随机生成。

## 5. WORKED_EXAMPLES.md 措辞复核

额外只读复核当前 `WORKED_EXAMPLES.md`，并重新对照 health005 的原 VERIFY / DECIDE；其余重点以本次及前四批已核对的原图、原请求为依据。

- b003：保留公开任务明确要求 labeled rating-share 及原有 `mislabeled_value` 提示，不误称核验器自己证明了印字优先。独立读取错误另记，口径合适。
- env008：保留两种真实视觉依据、原 gold / evidence_conflict 和 Solar/Hydroelectric 排序错误，不把 null 等于成功，符合本次原记录。
- health005：原 B 指出右侧 June→左侧 November；实际 VERIFY 与 DECIDE 都把 Nov→Jun 的左→右误叫 chronological，最后选择下降。文中“沿用这个错误”有对应文字支持，但它不是单独估计“核验导致下降”的因果效应。
- b036：明确核验并未建议必须选 growth，只提出阈值及标题权威缺口；没有虚构已确定的正确纠正建议。
- b044：明确当前三月算术均值是一个条件式离线读法，同时允许虚线指其他总体但缺定义；所写近似区间未冒充精确原始数据或 gold 更正。

未发现必须阻塞展示的实质歪曲。全文“更易审阅”宜理解为这里的离线表达评价，不是受控测得的可解释性优势；末段已明确不等于可靠全量核验器、人工准确率或真实任务完成率。

本批结论不触发任何重跑或新机制。继续保留全部分母、冻结版本和失败原文；待全量最终归档后才汇总最终覆盖与成本。
