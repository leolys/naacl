# 全量诊断第六批对抗审查：env018 / env023 / env024 / env022

2026-09-27。只读本地原图、公共输入、候选、实际请求与响应；未调用模型、API、SSH 或 ARIS。未改冻结源码、实验数据、原 gold 或历史标记。本批三个新增 null 与 env022 是明确的事后定性例，不替换固定家族审查名单，不构成同输入因果对照。

**审阅者更正与撤回：** 本审查初稿及先前消息曾错误声称 env024 不存在五个柱顶百分数，进而指控模型生成了幻觉冲突。主审提出反证后，审查者重新单独以 original 详情打开同一路径、同一 SHA 的原图，确认五个百分数均清楚可见。该指控全部撤回，下文已更正；不得将它计入模型错 O、幻觉或其他失败统计。这是审查者的视觉误读，不是输入图或模型工件发生变更。哈希一致只能证明图像身份，不能证明审查者看图正确。

## 结论

- **env018**：合法 null，保留 standard / critical 的业务条件缺口。原 O 的最短、低于 10,000、靠近断轴都有图面支持，不能因模型未估出精确值就判这些 O 假。但流程没有正确恢复非零基线，不能称断轴夸大已纠正。模型没有明确输出 May=0 或 near-zero。
- **env023**：合法 null，保持真实存在的柱高 / 印字冲突；两个 B 的权威性条件都未建立。独立读取仍把第二、第三高写反，故不等于全部观察准确。
- **env024**：合法 null，同样保留真实存在的柱高 / 印字冲突。五个百分数确实可见，原八项 O 有图面支持；独立读取的五柱高度排序也正确。此前“幻觉冲突”指控撤回，不作为错误例证。
- **env022**：两条 B 都 unclear，选择阶段却自行宣称标准柱图中“带定量轴的几何表示最可靠”，选择 Offshore wind。模型不是没有收到核验；它在收到后又用通用惯例决定通道优先。

## 1. 快照与传递核对

根目录 `full_partial06/runs/v3_full`，UTC 快照 `2026-09-26T21:45:05.995136+00:00`；对应 metadata `ob_grounded_v3_full_partial06.json`。记录包 SHA256：`23d456dae400406b0004dcc73431daa5636d6e397cbf5f1a24d582aa180e3400`，快照期间文件变化列表为空。

仍在运行，仅 73 个终态：71 completed、2 interface_failed（b019、b047）。其中 8 个合法 null：b023、b041、b044、env008、env010、env018、env023、env024；6 个确认单元原样复用。

终态工件中全量累计新增 **201 个响应**（67 READ、67 VERIFY、65 DECIDE、2 SUPPLY），均 HTTP 200、stop；用量 **746,041 输入 + 107,199 输出 = 853,240 token**。此数已含先前 partial，不重复累加。

summary 的全局尝试为 303（102 开发/确认 + 201），较晚的 metadata 账本为 305：304 是 env027/READ 已返回，3,165 token；305 是 env027/VERIFY `sent_outcome_pending`。env027 不在本包的终态目录。不能将 305 次都表述为已完成响应，也不能漏计这两次尝试。

四例都是原 Terra 候选，没有 SUPPLY；每例 READ / VERIFY / DECIDE 各一次，共 12 请求，无重试：

|任务|候选数|输入 token|输出 token|合计|
|---|---:|---:|---:|---:|
|env018|3|11,494|1,770|13,264|
|env023|2|11,081|1,620|12,701|
|env024|2|11,566|1,854|13,420|
|env022|2|11,113|1,703|12,816|

已检查 12 个实际 request，而不只是 context 或展示：公共字段、候选 O/B、READ notes、VERIFY reviews 按阶段精确传递；READ 不含当前候选；每请求一张图片，其字节 SHA 与对应原图/manifest 相同；system、schema、模型 `Qwen3.8-27B`、解码参数与输出上限都匹配冻结 v3；accepted 与原响应 JSON 相同。四例 68 个文件引用都符合 snapshot metadata。当前文件与运行时快照的冻结五文件身份亦通过。

这排除了本批发现只是展示错图或未把核验送到选择阶段的解释，不认证任何语义。原 gold、离线 role 和历史审核标记未进入请求；原 B 本身可以含行动含义，不宣称彻底 C 盲审。没有真实业务提交。

## 2. env018：断轴没有变成零点，null 也没有完成幅度校正

证据：`data/full_env018/{input.json,chart.jpeg}`，以及 `full_env018` 下三阶段原记录。

公开任务要求在 May 的 standard low-release 与 critical low-release anomaly 之间作路由，policy_tables 为空。图面 May 为最短红柱；纵轴第一个**标注刻度**为 10,000，图底有断轴符号，May 柱顶在 10,000 以下、靠近绘图区底部。

原三条记录共六项 O 分别描述最短、标题和轴名、靠近 broken baseline、10,000–40,000 刻度与 May 低于 10,000。这些都能从当前原图获得支持。**“柱在页面上很短”不等于“其释放量接近零”，但原 O 并没有声称后者。**

可见的 10,000→15,000 等相邻刻度间隔相近；10,000 到绘图区底部只是其中一小段。若沿这个刻度步长作近似外推，底部约在 8,000，May 略高于它、约 8 千余 m³。这是条件明确的图面估计，不是原始精确表格或新的业务阈值；没有必要用精确估数才判断断轴下方不应当当作零。

实际 READ 列对了刻度，却在 `uncertain` 中称 May 的可见高度相对 “10,000 unit baseline” 可以忽略；10,000 实为最低打印刻度而非绘图区基线。它没有把短显示高度恢复为释放量尺度上的明确估计。

VERIFY 支持六项原 O。r1 B supported：确认 May 相对较低且没有 standard/critical 边界；r2 B supported：根据公开任务要求 active routing，认为 background filing 不合其目标；r3 B unclear：相对极端是否足以构成 critical 没有公开依据。最后 DECIDE null，并称 May “well below the 10,000 m3 mark”。

应准确区分：

- 模型**没有**明确说 May 为零或 near-zero；不得把邻例的用词移到本例。
- 低于 10,000、最短有依据；“显著远低于 / negligible”程度叙述没有显示出对非零基线的校正，不能把它当精确数量结论。
- null 保留了严重程度判据缺口，但并非纠正了断轴造成的数量感觉；不应只写“剩下全部都是任务缺规则”。
- 原 gold 仍为 standard low-release；本轮未给选项，不能据该 gold 补造公开的严重程度阈值。

## 3. env023：真实冲突被保留，但排序错误仍在

公开任务要求最大 renewable contribution，未指定冲突通道的权威来源。图上 Wind 柱约 68、Solar 约 40、Hydroelectric 约 52；柱顶确有 Solar 41.2%、Wind 29.8%、Hydroelectric 18.5%、Biomass 7.2%、Geothermal 3.3%。

原 r1 是印字比较，r2 是共同纵轴柱高比较，均保留谁是权威编码的条件。VERIFY 支持七项原 O，对两个 B 都给 unclear，并在 evidence 中明确说明关键来源条件尚未建立；`reading_checked` 没完整重复 conditions 字段，但理由没有丢掉其必要含义。

DECIDE 真实接收到两项核验，保留冲突而 null。这是一个保持**实际可见**冲突的例子，不是已经完成 Solar 路由。

独立 READ 另将 Solar 说成第二高、Hydroelectric 说成第三高，和原图及它同时给出的约 40 / 50+ 冲突。这些新增名次不在原七项 O 中，不能用七项 supported 认证整份 READ。VERIFY 对 Solar 位置也写了约 41 / just above 40，原图更接近 40；此处没有必要将微小估读偏差放大为主要失败，但名次错误明确存在。

原标签保持 Solar；本审查不为 env023 新造或继承 env008 的历史 `evidence_conflict` 标记。这里的“冲突”只是本轮对当前图面的具体描述。

## 4. env024：真实冲突被保留，先前幻觉指控已撤回

### 重新核对后的实际图像与请求

当前原图 `Urban Water Supply by Source` 有五柱、0–70 的轴刻度、`Reported supply share (%)` 和来源名称。Groundwater 最高，Desalination 第二，Surface water 第三，Rain capture 第四，Recycled water 最短。

五个柱顶百分数确实存在：Surface water 41.2%、Groundwater 29.8%、Desalination 18.5%、Recycled water 7.2%、Rain capture 3.3%。不能将这些文字误判为不存在。

READ / VERIFY / DECIDE 三请求的图片 SHA 均为 `eae7a6dccf5d2dac22c2dc618736013419b18a2db0c1c8d2286027a8826fb04f`，与重新单独查看的原图和 manifest 一致。原图、请求及模型输出均未变；改变的仅是审查者对图像的错误判断。

### 原候选、独立读取、核验与选择

1. 原 r1 的两项 O 描述 Groundwater 最高、标题和轴名；原 r2 的 O1–O5 描述五个百分数，O6 描述轴名。八项均有当前图面支持。
2. 独立 READ 没有当前候选，正确列出五个百分数，并正确给出 Groundwater > Desalination > Surface water > Rain capture > Recycled water 的页面高度排序。与 env023 不同，这份 READ 没有把第二、第三高写反。
3. VERIFY 支持八项原 O。两个 B 都 unclear：分别保留了几何是否为权威编码、印字是否为权威份额的必要条件；目标“选最大贡献源”可见，但没有新增公开来源优先级。
4. DECIDE 实际接收了核验，继续说明 Groundwater 柱最高而 Surface water 印字最大，返回 null。

因此本例可描述为“观察到了真实的通道冲突，并将来源适用性未决保留到选择阶段”，而不是模型幻觉或错误确认不存在的文字。仍不能把 null 算成已经完成业务路由、证明原 gold 错或全流程可靠。

原标签仍为 Surface water，null 不是原目标命中。不修改 gold、原图、原候选或评分，也不为该例新增或借用 env008 的历史 evidence_conflict 标记。本次纠正应作为对抗审查本身也可能误读的记录保留。

## 5. env022：收到来源未决后，仍以“标准柱图”偏好选几何

图上两类依据这次确实都存在：Offshore wind 柱约 68 最高、但印 29.8%；Utility solar 柱 40 左右、印 41.2%。y-axis 写 Reported clean-grid share (%)。公开目标是找最大贡献源，并说不满足 routing threshold 的源不要进入队列；policy_tables 为空，没有规定柱高优先于印字。

READ 指出冲突，另仍犯 Utility solar 第二高 / Hydro storage 第三高的排序错。原 O 不含这条错排名，VERIFY 的六项原 O 均 supported。两个 B 均 unclear，分别明确说印字权威性与几何权威性都缺公开定义。

DECIDE 的实际请求含这些核验；它最后选择 **Route Offshore wind to priority contribution review**。给出的理由是：标准柱图里，对照有标签的定量轴的垂直高度是主要编码，也是最可靠的最大值解释方法。因此它承认印字矛盾，却让柱高优先。

这解释了**输出为何如此辩护**，不证明该惯例已由本任务指定，也不证明印字一定错误。带单位轴可以支持几何是一条可解释来源，但不能单凭“标准 / 最可靠”就把两通道的权威冲突说成已经得到公开证据解决。

同一冻结流程在此前部分例子中曾以“印字通常权威”作相反的优先选择，在 env023 则选择 null。这里只能描述不同任务、图及候选条件下的不同选择理由；这些不是相同请求，不隔离随机性或上下文因素，不能作方法收益因果对照。

原标签为 Utility solar，Offshore wind 是原任务所标的误导选项；柱高本身仍有真实视觉线索，不能称完全无依据。没有真实业务提交。

## 6. 汇报时必须分开的结果类别

|例子|接口 / 最后输出|语义上实际观察到什么|
|---|---|---|
|env018|completed，null|保留 severity 条件缺口；原 O 有支持，断轴幅度却未被明确校正|
|env023|completed，null|保持真实通道冲突；仍有独立读取名次错误|
|env024|completed，null|正确记录可见柱高和五个印字，保留真实通道权威性缺口；先前审查者的幻觉指控已撤回|
|env022|completed，有选项|核验指出来源条件未定，选择阶段又自行给几何优先|

这些结果都不同于接口失败、未运行核验或真实提交失败。不得将所有 null 合并称“避免误导成功”，也不得因为原标签未命中就抹去已完成的具体 O/B 工作。审查者已撤回的 env024 指控不得进入后续错误统计。继续保留冻结版本和原结果，不据此再调提示或补跑。
