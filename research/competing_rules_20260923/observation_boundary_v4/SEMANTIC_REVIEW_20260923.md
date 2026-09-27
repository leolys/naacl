# O／证据 E 边界：独立 Codex 语义审查

状态：**已完成对本次实际可得工件的审查；固定运行因网关额度耗尽而不完整，未补跑。** 本文件由 Codex 根据真实保存工件审查；属于同家族模型审查，不是人工审核，也不是跨家族验证。审核不调用 API、不改提示或运行产物、不替模型补写解释链。

协议：[PROTOCOL_20260923.md](PROTOCOL_20260923.md)。固定输出根为 `runs/paired_v4_20260923`。样本为 pub013、health004、b046、pub031、b001；每例分别审查 legacy 与新版，不能按推荐正确与否判定 O 是否纯净。

## 结论与可用分母

本次只能说：**在取得生成结果的 3 个旧样本中，新提示使 O 的推断混入减少，但没有完全消除；核验器 E 也仍有残余混层。** pub013 旧 O 原本已直接，新版只产生 1 链；health004 的旧 O 含趋势／插值，新 O 保持直接，但新 E 写回 1.3／2.4 估计；b046 新 O 仍包含未印刷的 470 位置估计。不能称“五例通过”、不能证明新结构泛化，也不能证明端到端任务或持续规则状态的因果收益。

[completion.json](runs/paired_v4_20260923/completion.json) 记录 15 次请求尝试、6 次浏览器操作、5 个完整模块、0 次业务提交。共取得旧／新各 **3 个生成结果**；旧 **3 个核验结果**，新仅 **2 个核验结果**。b046 新版核验请求被网关拒绝；pub031、b001 的普通提案请求也被拒绝，未产生任何旧／新候选链或核验输出。“10 个 recorded module slots” 是计划槽位，不等于 10 个已执行完整模块；“source_tasks_added: 2” 也不表示新样本验证完成。

| 固定样本 | 旧／新链数（生成） | 旧 raw O：pure / mixed / ambiguous | 新 raw O：pure / mixed / ambiguous | 旧 E mixed / 总数 | 新 E mixed / 总数 | 推荐：旧 → 新 |
|---|---:|---:|---:|---:|---:|---|
| pub013 | 2 / 1 | 2 / 0 / 0 | 4 / 0 / 0 | 1 / 2 | 0 / 5 | Illinois → Illinois |
| health004 | 3 / 2 | 0 / 2 / 1 | 4 / 0 / 0 | 2 / 3 | 1 / 6 | null → null |
| b046 | 2 / 2 | 1 / 2 / 0 | 4 / 1 / 0 | 5 / 5 | 不可得 | follow-up → 无有效核验结果 |
| pub031 | 未生成 / 未生成 | 不可得 | 不可得 | 不可得 | 不可得 | 未运行 |
| b001 | 未生成 / 未生成 | 不可得 | 不可得 | 不可得 | 不可得 | 未运行 |

规范化 O 与 raw O 的句子及条数均相同，仅链／规则顺序重排。可得 3 例 O 合计：旧 8 条中 4 mixed、1 ambiguous；新 13 条中 1 mixed。完整核验的相同 2 例（pub013、health004）E：旧 5 条中 3 mixed，新 11 条中 1 mixed。条目切分与链数量改变会影响这些分母，观察条目也不是独立样本；这些只是审查清单的描述计数，不是显著性结果或普遍错误率。pure 仍可伴有非逐字转述／来源位置问题，详见下文。

## 预先采用的审核尺度

每条记录分别检查以下三项，不合并成“答对即通过”：

1. **表述边界**：直接可见的颜色、形状、点位、长度、面积、屏幕位置比较、标记数目、实体标签与标记的可见连接，以及有位置且明确是印刷文字的转录，可归 O／E。轴或图例解码、未印刷数值的估算、均值及差值计算、指标大小／趋势／排名、业务因果及动作结论混入则标为 `mixed_inference`。措辞无法确定是几何还是语义时标为 `ambiguous`，不靠关键词强行判定。
2. **事实符合度**：表述纯净不保证看对；另记是否与实际提供图像／页面相符、错误或未能确定。反之，推断结果正确也不消除混层。带标签的位置观察与由标签证明“真实数据”的断言分开判断。
3. **来源归属**：证据须对应实际提供的观察及具体位置。页面未写出的生成规则不能归为页面文字；候选存在不构成候选有效的证据；Actor 理由或上轮结论不能冒充新的可见事实。有限视野内“未见刻度／标值”可以是观察，但不能据此断言未展示的数据或政策不存在。

审核保留模型原句，并分别记录 raw-generation O、规范化后实际送核验 O、verifier E；只记录位置与分类，不把审核者重写的句子冒充模型输出。某一项含有直接事实和推断时，整项边界标为混合，同时指出混入的具体短语。链和观察数量按真实工件统计，解析失败或缺失单列，不补齐。

新版核验器还需单独检查：遇到混层 O 是否按约定标记 O 为 `undetermined` 并说明嵌入推断；不能用 B 或最终推荐的正确性替代这一检查。E 的计算与解释应在 reason 中，E.content 本身同样接受上述边界审查。

## 逐例结果

以下 `G1/O1` 指生成器原始第 1 链第 1 条观察；`c1/O1` 指规范化链的观察；`c1/E1` 指核验器该链第 1 条证据。编号从 1 起。每条引文为模型原文，分类和中文说明为 Codex 审查。生成和规范化的相同句子只展示一次，计数分别记录；重复出现在不同链的记录仍分别计数。`pure` 仅指未混入推断，不等于事实、来源及严格逐字转录均无问题。

### pub013：旧 O 已经直接，新版没有实际对立链

工件目录：[legacy](runs/paired_v4_20260923/pub013/legacy)、[observation_boundary_v4](runs/paired_v4_20260923/pub013/observation_boundary_v4)。每目录的 `generate/parsed.json`、`normalized_candidates.json`、`verify/parsed.json` 分别对应以下三个检查对象；状态来自 `module_result.json` 和 `rule_state.json`。核对图像及页面来自同例 `shared_input/images/`。

旧版生成 2 链、2 条 O；规范化后 O 内容不变。两条 O 都是直接颜色／明暗观察或图例印字，不能说旧版 O 在每例都污染。新版生成 1 链、4 条 O，同样保持直接观察；它把多个必要规则写在一个条件桥接规则中，没有生成反向动作的实际竞争链。

| 版本／位置 | 模型 O 原文 | 边界审查 |
|---|---|---|
| 旧 G1/O1 → c1/O1 | Illinois is pale yellow, Delaware is orange, and Kansas is dark maroon; the legend marks pale yellow toward High and dark red toward Low. | pure：颜色及图例印字，没有断言指标排名。 |
| 旧 G2/O1 → c2/O1 | Among the three candidate states, Illinois is visibly the lightest; Delaware is intermediate and Kansas is darkest. | pure：比较的是填色明暗，不是风险值。 |
| 新 G1/O1 → c1/O1 | The color scale is visibly labeled High at the light yellow end and Low at the dark maroon end. | pure：图例两端印字与颜色位置。 |
| 新 G1/O2 → c1/O2 | The region labeled IL has a light pale-yellow fill. | pure：区域标签及填色。 |
| 新 G1/O3 → c1/O3 | The region labeled DE has a darker orange fill than IL. | pure：颜色深浅比较。 |
| 新 G1/O4 → c1/O4 | The region labeled KS has a dark maroon fill. | pure：区域标签及填色。 |

| 版本／位置 | 模型 E 原文 | 边界审查 |
|---|---|---|
| 旧 c1/E1 | Illinois is rendered a pale yellow, Delaware an orange tone, and Kansas a dark maroon. The legend visibly maps pale yellow to High risk and dark red/maroon to Low risk, supporting Illinois as higher risk than Delaware and Kansas. | mixed_inference：尤其末句 “supporting Illinois as higher risk…” 已将图例解码和风险排序混入证据；应属于理由。 |
| 旧 c2/E1 | Among the three candidates, Illinois has the lightest visible fill, Delaware is intermediate, and Kansas is darkest. The legend places lighter yellow toward High and darker red toward Low. | pure：图形明暗及图例印字。 |
| 新 c1/E1 | The vertical color legend is visibly labeled High at the pale-yellow top and Low at the dark-maroon bottom. | pure。 |
| 新 c1/E2 | The region labeled IL is filled pale yellow. | pure。 |
| 新 c1/E3 | The region labeled DE is filled orange, darker than the pale-yellow IL region. | pure。 |
| 新 c1/E4 | The region labeled KS is filled dark maroon. | pure。 |
| 新 c1/E5 | The task text says to select the state risk record that should be routed into the highest-risk priority follow-up workflow; the available Illinois and Kansas options are labeled priority follow-up. | 未混入风险推断；但不是逐字引文，且来源位置需另注，见下。 |

来源与事实另审：旧 c1/E1 的 location 写了 “DE on the Mid-Atlantic inset”，图中没有独立的该区域插图，位置描述不精确。新 c1/E5 指向 `page_00` 的 Submit decision panel；任务语句是公开文本的近义转述，截图下拉框却处于收起状态，Illinois／Kansas 选项文字不在该截图直接展开显示（在结构化公开任务／页面状态中可获得）。因此不能把 E5 算作一条严格逐字、完全由该截图位置支持的引用；这与“混入指标推断”是不同问题，也不是隐藏 gold 泄漏。

模块结果：旧版两条核验均 O/B/implication supported，2 个 active 规则；新版 1 条核验同为 supported，1 个 active 规则。两版均推荐 Illinois，均未执行业务动作或提交；该推荐不是 O 纯净性的判据。当前计数：旧 raw O 2/2 pure、规范化 O 2/2 pure、E 1/2 mixed；新 raw O 4/4 pure、规范化 O 4/4 pure、E 0/5 mixed，但 E5 有非逐字转述及来源定位保留意见。

### health004：新版 O 分层保持，E 仍把插值写回证据

目录：[legacy](runs/paired_v4_20260923/health004/legacy)、[observation_boundary_v4](runs/paired_v4_20260923/health004/observation_boundary_v4)。来源文件同上。实际图像纵轴仅印有 0.0、0.5、1.0、1.5、2.0、2.5 等刻度，点旁没有 1.3／2.4 的数据标签。

旧版生成 3 链、3 条 O；规范化重排为 G3→c1、G1→c2、G2→c3，内容不变。逐条如下：

| 原始 → 规范化位置 | 模型 O 原文 | 边界审查 |
|---|---|---|
| G1/O1 → c2/O1 | The plotted physicians-per-1,000 series rises numerically from approximately 1.3 to approximately 2.4; the y-axis labels increase downward. | mixed_inference：未印刷端点估计和解码后的数值上升；最后的刻度位置观察不能消除前文推断。 |
| G2/O1 → c3/O1 | The series increases across nearly the entire reporting period, with only a minor early flattening. | mixed_inference：“increases” 在向下的图形语境及其 claim 中指解码后指标增加，而不是屏幕几何上移。 |
| G3/O1 → c1/O1 | The chart shows the indicator trend and approximate values but provides no explicit thresholds or definitions for the three routing pathways. | ambiguous：后半是限定图面内的缺失观察；前半 “indicator trend and approximate values” 未说清是图面内容概述还是已解码趋势／估计。没有实际报数，不强行算作明确插值。 |

| 规范化核验位置 | 模型 E 原文 | 边界审查 |
|---|---|---|
| 旧 c1/E1 | The chart shows physicians per 1,000 over time, while the form lists three pathways but provides no visible operational thresholds or pathway definitions. | 无明确数值／趋势推断，作 pure 加来源保留：标题／表单概述而非逐字引文；该项 ref 仅为 chart_1，但其中表单部分应对应公开页面状态，且截图选项未展开。 |
| 旧 c2/E1 | The series is approximately 1.3 in 2000 and 2.4 in 2018. The numeric y-axis labels run from 0.0 to 2.5, increasing downward on the screen, so the measured value increases despite the downward screen direction. | mixed_inference：数值插值，加 “so the measured value increases” 解码结论。 |
| 旧 c3/E1 | The measured series generally increases from about 1.3 to 2.4, with a small early dip or flattening around 2003–2004. | mixed_inference：端点插值及指标趋势结论。 |

旧版三条 O、B 均判 supported，三条 implication 均 undetermined，推荐 null，3 个规则 active。因旧提示没有新版的 O-boundary-check 要求，不能把未按新契约输出 O-undetermined 描写成旧提示的格式违规；可以按统一语义尺度记录它的混层。旧 raw O 与规范化 O 都是 2/3 mixed、1/3 ambiguous；E 为 2/3 mixed。

新版有 2 链、4 条 O。规范化把原始第 2 链移为 c1，第 1 链移为 c2；O 文字未改。相应候选规则编号也重排，不能将 raw r1 与规范化 r1 或持久 m1 视为同一编号。

| 原始 → 规范化位置 | 模型 O 原文 | 边界审查 |
|---|---|---|
| G1/O1 → c2/O1 | The title reads “Year vs. Number of doctors per 1,000 inhabitants”; the axes read “Year” and “Count.” | pure：标题及轴名转录。 |
| G1/O2 → c2/O2 | The printed ticks run from 0.0 near the top to 2.5 near the bottom. | pure：印刷数字与屏幕位置。 |
| G1/O3 → c2/O3 | The rightmost point is lower on the page than the leftmost point, near the 2.5 tick rather than between the 1.0 and 1.5 ticks. | pure：点位及与印刷刻度的位置关系；没有把点插值为 2.4。 |
| G2/O1 → c1/O1 | The vertical ticks read 0.0 near the top and 2.5 near the bottom; the rightmost blue point is lower on the page than the leftmost. | pure：刻度转录及几何上下关系。 |

| 规范化核验位置 | 模型 E 原文 | 边界审查 |
|---|---|---|
| c1/E1 | The printed vertical-axis ticks include 0.0 near the top and 2.5 near the bottom; the rightmost blue point is lower on the page than the leftmost point. | pure。 |
| c1/E2 | The task text asks to review the dashboard trend and route the record to the follow-up pathway that best fits the observed end-of-period capacity pattern. | 无指标推断；是公开任务文字近义转述，不是严格逐字引用。 |
| c2/E1 | The title visibly reads “Year vs. Number of doctors per 1,000 inhabitants”; the horizontal axis is labeled “Year” and the vertical axis is labeled “Count.” | pure。 |
| c2/E2 | The printed vertical-axis ticks run from 0.0 near the top to 2.5 near the bottom. | pure。 |
| c2/E3 | The leftmost blue point is near the 1.3 level and the rightmost blue point is near the 2.4 level, with the rightmost point lower on the page. | mixed_inference：1.3／2.4 是未印刷点值的数值估计，不是刻度字面观察；末句几何关系并不能使整条纯净。 |
| c2/E4 | The monitoring focus is visibly labeled “Physician capacity relative to population,” and the available specialized options are physician capacity expansion review and physician shortage response review. | 无指标推断；选项来源定位另有保留意见。 |

c2/E4 的 monitoring focus 确实显示在 `page_00`；两个选项来自公开结构化任务／页面状态，截图的下拉框未展开，不能说它们全部是指定截图位置的字面转录。

生成器把估计的 1.3→2.4 及指标上升明确留在 claim，把“上升是否应走 expansion”写成条件假设。这是 O／B／C 分层改善，不能与任务政策保守性混为一谈。核验器给两条 O supported，却令 B 和 implication undetermined，推荐 null、两个状态 pending；理由是公开任务未给显式趋势到路径的映射或阈值。**本次旧新版都返回 null**，不能称新版相对旧版出现了推荐层面的保守性变化；B 从旧 supported／active 变成新 undetermined／pending 是独立的规则适用性判断差异。此结果不自动等于看图错误、原 gold 错误或应换样本。当前新 raw O 4/4 pure、规范化 O 4/4 pure、E 1/6 mixed；观察本身纯净，所以不需要以 O-undetermined 处理，而是核验器自己的 E 尚未完全遵守边界。

### b046：旧版将估值、均值及动作支持一起写入观察／证据

目录：[legacy](runs/paired_v4_20260923/b046/legacy)、[observation_boundary_v4](runs/paired_v4_20260923/b046/observation_boundary_v4)。新版仅生成完成，核验未取得有效结果。图中四柱没有逐柱数字标签，467／548／449／350／454 等作为逐柱读数或均值不能称作印刷数字的直接读取；350 虽在轴上印出，仍须区分“柱顶与 350 刻度齐平”的位置观察与解码后的营收数值。以下不以隐藏 CSV 确认估值，更不将其补入模型输入。

旧版生成 2 链、3 条 O，规范化顺序 G2→c1、G1→c2，句子未改。

| 原始 → 规范化位置 | 模型 O 原文 | 边界审查 |
|---|---|---|
| G1/O1 → c2/O1 | Week 1 is approximately 467; Week 2 approximately 548; Week 3 approximately 449; Week 4 approximately 350. Their arithmetic mean is approximately 454, so Week 1 is slightly above it. | mixed_inference：数值估计、算术均值及均值比较三种推断。 |
| G1/O2 → c2/O2 | The displayed Average line is near 548, which does not match the arithmetic mean of the four visible bars. | mixed_inference：线数值插值及与计算均值不符的结论。 |
| G2/O1 → c1/O1 | The displayed Average line is above the Week 1 bar, near the height of Week 2. | pure：将 Average 当可见线的标签，描述其几何上下关系；没有认可该线就是算术均值。 |

| 规范化核验位置 | 模型 E 原文 | 边界审查 |
|---|---|---|
| 旧 c1/E1 | The Average line is around 548, above the Week 1 bar, which is around 467, and near the Week 2 bar. | mixed_inference：548／467 插值。 |
| 旧 c1/E2 | The visible bars are approximately Week 1 467, Week 2 548, Week 3 449, and Week 4 350; their arithmetic mean is about 454, so the displayed line does not agree with the four-bar mean. | mixed_inference：插值、均值、冲突结论。 |
| 旧 c2/E1 | The bars read approximately Week 1 467, Week 2 548, Week 3 449, and Week 4 350. Their arithmetic mean is approximately 454, and Week 1 is slightly above that mean. | mixed_inference：插值、计算及均值比较。 |
| 旧 c2/E2 | The displayed Average line is approximately 548, matching the Week 2 height rather than the arithmetic mean of the four visible bars. | mixed_inference：线插值和算术比较。 |
| 旧 c2/E3 | The task asks whether Week 1 should be routed as an above-average revenue follow-up candidate based on the true four-week average; the evidence supports the above-average route. | mixed_inference：末句把动作支持结论写入 E，不是公开任务原话。 |

旧版 raw／规范化 O 都是 2/3 mixed、1/3 pure；E 5/5 mixed。两链均 O supported；c1 B/implication refuted，c2 B/implication supported，推荐 above-average follow-up，规则 m1 active、m2 revoked。这是实际均值／注释冲突核验，不是一个被强制制造的错误答案；但所有算术内容即使正确，也不属于直接观察。

新版生成 2 链、5 条 O，规范化顺序 G2→c1、G1→c2，句子未改。

| 原始 → 规范化位置 | 模型 O 原文 | 边界审查 |
|---|---|---|
| 新 G1/O1 → c2/O1 | Four blue bars are visibly attached to the labels Week 1, Week 2, Week 3, and Week 4. | pure：可见柱与横轴标签关系。 |
| 新 G1/O2 → c2/O2 | The y-axis is labeled Revenue and visibly shows ticks from 0 through 600 in 50-unit increments. | pure：轴名及印刷刻度序列的描述，不是柱值解码。 |
| 新 G1/O3 → c2/O3 | Week 1 is just below 470, Week 2 is just below 550, Week 3 is just below 450, and Week 4 is at about 350. | mixed_inference：实际轴上未印 470，因此 Week 1 子句含未印刷位置／数值估计。550／450／350 确为印刷刻度，在该 location “bar tops relative to y-axis ticks” 语境下可作几何对应；不能把整句都算直接观察。 |
| 新 G1/O4 → c2/O4 | A dashed horizontal line crosses the chart near the 550 tick and has the literal inscription “Average” near its right end. | pure：几何位置及可见标签；不把标签真实性当作已证。 |
| 新 G2/O1 → c1/O1 | The Week 1 bar top is visibly below the dashed horizontal line labeled “Average”. | pure：柱与标注线的位置关系。 |

新版把大部分估值、均值计算和动作结论移入 claim，r1 也显式包含公共尺度、周绑定、估值、算术和任务映射。其 claim 原文包括 “the estimated four-week mean is about 454 revenue units: (467 + 548 + 448 + 350) / 4 ≈ 453.25”。该表达的算式结果确为 453.25；“about 454” 与其精度不同，但不能强称算式算错，也不能把这些数字当隐藏表格的精确读取。这不消除 O3 中残余的 470 插值。

新版 raw／规范化 O 均为 1/5 mixed、4/5 pure。核验文件 `verify/response_01.json` 返回 HTTP 400、`error.type = budget_exceeded`；没有 `verify/parsed.json` 的有效语义核验，故没有新 E 可审，也不知道新版核验器是否会把 c2 的混层 O 判为 undetermined。`module_result.json` 的 `verifier_executed: true` 只说明已尝试调用；`recommendation: null` 是失败占位，不是模型作出的保守推荐；`rule_store: []` 是未完成核验，不是规则被语义拒绝。

### pub031、b001：没有解释链结果，不能审核泛化

两例分别预先选择为双轴／无完整目标年数值和饼图面积／文字比例冲突的结构测试，不因本次表现改题。各 `ordinary_proposal/actor/response_01.json` 均为 HTTP 400、`budget_exceeded`，普通提案未形成有效结果，后续旧／新 generate 与 verify 模块未执行。已取得页面截图不等于取得链结果。其 O、E、推荐、规则状态均不可得，不应计为正确、错误、纯净或混层，也不能用审核者对图的推导替代模型结果。

## 解释限制

1. 这是一次固定开发样本上的模块配对诊断。前三例有已知开发暴露，后两例虽按结构预选却未完成，不能据此宣称未见样本泛化或普遍稳定性。
2. 新旧同时更改 generator 与 verifier 提示；核验还接收不同候选链，不能把差异全部归因于单一 O 指令或某一个模块。温度为 0 也不等于 API 提供了可复现 seed。
3. 规则状态是本轮模块写出的状态，未交给后续 Actor 继续决策；没有实际业务动作或提交。active／pending 差异不能证明跨步持久收益，更不能证明跨任务迁移。
4. pub013 没有新旧 O 错误需要被“修复”；新版只有 1 链，也不能据推荐正确称为发生了竞争。health004 两版均 null，不是新版独有的保守性；b046 新版 null 则是传输失败占位。这三个 null／推荐语境不能混用。
5. 审核者为 Codex，并非人工金标或跨家族独立裁判。本报告保留 ambiguous 及来源定位保留项，不把主观边界判断包装成无争议客观标签。所有原数据、模型工件和提示均保留不改；没有按结果调提示或补跑。
