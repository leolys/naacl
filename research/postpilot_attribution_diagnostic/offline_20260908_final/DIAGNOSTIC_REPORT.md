# Post-pilot attribution：离线部分已完成，三条件真实诊断未运行

本文件是固定八任务面板结束后的归因核对，不是旧96条的补跑或新的实验结果。当前工作区未找到用户指定的 `Codex_PostPilot_Attribution_Diagnostic.md`；已请求实际路径/上传。未自行猜选四任务，未启动被测模型、GPU服务或浏览器。详细准备边界见 [PREPARATION_STATUS.md](PREPARATION_STATUS.md)。

## 1. 标签与审核应如何解释

16个原 task×arm spec、32个checkpoint和96条分支的原评分已机械对齐；16个spec的全部7个公开投影字段也与旧manifest完全一致，见 [PUBLIC_PROJECTION_ALIGNMENT.json](PUBLIC_PROJECTION_ALIGNMENT.json)。本轮没有修改任何图表、公开任务、gold或旧score。

**八题均找到了可按原 case_id 对齐的正向历史审核记录**，不是仅有 draft/legacy 字段。health001、health005、env035均存在 `approved_for_shell`，同时记录 `gt_uncertain`。应把这两个事实一起保留；不得把draft等同于未审核，也不能自动把“允许进入网页任务”解释成每个数值/gold已获独立确认。

项目所有者在此前执行要求中明确声明原图经过审核，本轮尊重这一声明，不重新否定图表、不删除任务。历史记录未保存审核者身份或确切覆盖范围时，记为“该记录未注明”，不推断没有人工审核。Codex的证据读取和本轮同家族代理审查均不是人工确认。

|任务|公开证据与业务规则（保留原任务解释）|原期望决策|找到的原审核记录与覆盖边界|
|---|---|---|---|
|b010|市场份额标签与柱高冲突；任务原文要求以真实份额选择推广品牌|Apple|2026-05-01 suitable；后有工作流筛选、业务路由说明。不是由legacy字段判为未审核。|
|b046|四周数值决定实际均值，再判断Week1；图上Average线可与之冲突|高于平均收入跟进|2026-05-02 suitable；业务路由说明明确区分误导平均线与above-average跟进。公开读数可为约数，原隐藏CSV均值453不在线提供。|
|health001|倒置纵轴下按死亡负担而非屏幕高点选年份|2018|2026-05-08 approved_for_shell，同时保留gt_uncertain；2017/2018接近是原离线证据限定，不撤销已有审核。|
|env035|倒置纵轴下辨认最高每桶价格年份|1980|2026-05-07 approved_for_shell，同时保留gt_uncertain；原spec的GPT-5.4图像草稿提示也是独立的来源字段。|
|health005|结合倒序日期和纵轴读检测量变化；原对照也保留倒序日期|上升容量规划|2026-05-08 approved_for_shell，同时保留gt_uncertain；原gold明确晚6月至晚11月上升。|
|pub013|把州位置/颜色与浅色为高值的图例关联|Illinois|2026-05-06 approved_for_shell，issues为空；原spec标记formal/scorable。|
|b014|Product C与25,000阈值比较，再区分普通复核、正常计划、critical升级|普通低需求复核|2026-05-01 suitable；已有业务路由修订说明明确保留“普通复核/过度升级”的区分。不能仅因读取阈值正确就忽略动作映射。|
|env005|标签百分比与饼图面积可不一致；选择最大来源|Nuclear|2026-05-01 suitable及05-07 approved_for_shell，issues为空；原spec标记formal/scorable。|

可逐项追溯：[RAW_SPEC_ALIGNMENT.json](RAW_SPEC_ALIGNMENT.json)保存公开任务、原标签、两图资产与原spec行号；[REVIEW_RECORDS.json](REVIEW_RECORDS.json)保存17条历史记录的原字段、来源和行号。17条中包括下游复制/筛选记录，**不计为17次独立人工审核**。`selected_cases_workflow_ready`的静态筛选说明不升格人工确认；文件名manual也不是作者身份证据。独立审查的来源限定见 EXPERIMENT_AUDIT.md。

另有可明确识别的机器审核：business_task_visual_grounding_review.jsonl第10/14/46行分别记录b010/b014/b046，字段为llm_model=gpt-5.4、llm_called=true，不能列入人工确认。b014的这份历史审核建议修订路由，与当前任务版本的对应须保留时间/版本限定。

本地归档CSV可用于离线核对b010、b046、b014、pub013、env005的标签来源，**不是本轮在线模型获准访问的公开证据**。截图、公开任务与原始表格来源是不同的信息层，不能把离线读到数值算作在线模型看到了数值表。三道image-only题的clean/source.html第15行虽写使用official CSV，其对应目录实际只有figure.png和source.html；HTML后面的ground_truth复述也不是独立表格或人工确认。本轮不修改这些历史文件，只记录来源限定。

## 2. 结果转移分层

以下“正确/错误”均沿用原评分，不改变任何历史审核结论。完整分模型×图表条件表见 [TRANSITION_REPORT.md](TRANSITION_REPORT.md)，推荐—执行—提交三层逐行记录见 [TRANSITION_LAYERS.json](TRANSITION_LAYERS.json)。

|原自然checkpoint到最终提交|不核查|独立全图语义核查|通用主动视觉核验|
|---|---:|---:|---:|
|正确保持|26|22|26|
|正确改错|0|4|0|
|错误改对|0|1|1|
|保持原来的错误选项|6|3|5|
|改成另一个错误选项|0|2|0|
|未确认提交|0|0|0|

分母各32共享checkpoint；两核查都修复同一个pub013 API状态。全图核查另改坏b046的Qwen两条件、health005误导API、pub013误导Qwen，共4个状态；b014的Qwen两条件则从一个错误动作改成另一错误动作。

64个核查分支的推荐、落实选项和最终提交一致；actor没有在核查后再次改选。该短续跑的保持不代表长程稳定。普通前缀另有3次自行改对、3次改坏，来自health005的两个API前缀和pub013的误导API前缀；这是选择事件数，不是新增独立错误checkpoint。具体序列在 [EXISTING_CHECKPOINT_INDEX.json](EXISTING_CHECKPOINT_INDEX.json) 和 [PREFIX_SELECTION_TRANSITIONS.json](PREFIX_SELECTION_TRANSITIONS.json)。

## 3. B2/B3实际输入并不等价

对32个状态读取了真实保存的首轮核查request，而不是只读策略函数或response；完整请求及图像路径在 [B2_B3_ACTUAL_INPUTS.json](B2_B3_ACTUAL_INPUTS.json)。

|输入因素|独立全图语义核查 B2|通用主动视觉核验 B3|
|---|---|---|
|首轮图像|1张已观察过的图表页|当前表单页、图表页，共2张，按此顺序|
|共享图表的实际像素|与同状态B3的图表页一致|32/32逐像素一致；不是按路径、大小或token数判断|
|图像尺寸|1440×1100|两张均1440×1100；表单内图表还以不同布局/尺度出现|
|当前选项|不提供|文本提供；表单截图也显示选项|
|执行历史|不提供|实际输入为最近4条动作及公开回执，32/32一致|
|此前模型自由文本回复|不提供|也不提供；H_base删除了原策略字段prior_agent_responses|
|目标与选项顺序|原目标、原选项|与B2一致，32/32通过|
|核查角色与措辞|独立重新判断|核查已有待提交选择，可保持/更改；目标重复强调，含工具输出格式|
|工具与调用预算|无工具，1次核查|最多2次裁剪/3次核查；不强制使用|

关键实现：[h_base.py](../../prospective_simple_check_pilot/h_base.py)中的VerifierModel会替换原策略的历史字段；不能将基础policies.py中本来存在的字段当成模型真正收到的字段。本轮早期开发输出 `offline_20260908_v1` 的简要历史计数字段读取了旧字段名，仅用于开发保留；其完整请求正确，**本final目录的计数已按实际字段修正**，不改旧实验工件。

比较证明共享图表输入一致，不证明API服务内部图像预处理一致；上游未报告的处理记为未知。B3多出的表单截图同时暴露当前选项和另一种图表呈现，所以单纯删除文字历史仍不足以得到“等图独立”条件。

## 4. API路由记录

历史完整成本范围149次API尝试：143次completed、4次HTTP失败、1次传输/响应失败、1次身份检查未接受。143次completed中，62次报告gpt-5.6-luna，80次报告mirror-gpt-5.6-luna，1次未报告路由；这是路由字符串，不是权重身份验证。

最终32条前缀及其策略目录中可直接关联的API成功response为134条：53条luna、80条mirror-luna、1条未报告。它们不等于149次物理尝试；差异含早期控制、失败与重试。所有条目的路径和状态见 [API_WIRE_INVENTORY.json](API_WIRE_INVENTORY.json)；任务/阶段对应见 [API_ROUTE_BY_RESPONSE.json](API_ROUTE_BY_RESPONSE.json)。

16个API checkpoint中，B2/B3核查响应的已报告路由在同状态内一致；部分整条轨迹的前缀/actor阶段混用两个路由。不能由此认定它们权重相同，也不能声称已验证的Sol模型能力。一个未报告路由的成功响应为旧unit02前缀request_0011；不补写身份。

内网费用豁免不变，旧reservation字段不当成实际消费。失败的上游token消耗未知，不补零。

## 5. 当前可以回答的三个问题

1. **B3少改坏主要能否由上下文解释？尚不能归因。** 旧结果中的4个优势都来自少改坏；实际输入确实含上下文差异，但图像数量/布局、提示措辞和工具权限同时变化。上下文解释是待检验假设，不是直接结论。
2. **工具是否提供额外作用？旧面板没有证明。** 只有pub013 API用过一次裁剪，而不裁剪的独立全图核查在同一状态也恢复。裁剪未覆盖Illinois/Kansas/完整图例，不能将成功归因于该裁剪；其余31个主动分支未裁剪。
3. **剩余问题是否确属视觉证据定位或解读？需要分开。** env035的轴方向、health005的日期/轴顺序、pub013的图例关联与视觉解读有关；b014已陈述阈值关系却对应错业务动作，不能归为纯视觉定位。现有理由不能证明模型内部注意位置；简单核查的残余错误不自动证明新观察选择器必要。

这些是旧工件的直接观察与有条件解释。预定的等图三条件诊断**未运行**，不以旧结果冒充新归因实验。

## 6. 执行与停止状态

- 本轮新被测模型请求尝试：0；新浏览器操作：0；未启停任何GPU作业。
- 已执行离线图像像素比较、32个checkpoint及96条评分复核、149条API账本盘点；4项普通单元测试通过。
- 本轮另有1个只读同家族审查代理，不是被测模型轨迹或人工评审。
- 独立审查总体WARN，见 [EXPERIMENT_AUDIT.md](EXPERIMENT_AUDIT.md)。代理在收口答复中明确未再次逐字段复核最终汇总JSON和最终代码；不将此称为完整实现验收。其原文的CSV权限、记录复制来源和一处文件路径已在审查文件前言明确校正，原回复保留不改。
- 代码与命令见 [COMMANDS.md](COMMANDS.md)。工程测试只覆盖上述离线整理功能，不证明研究假设。
- 当前停止于缺少执行单文件；未选择四任务、未运行三条件、未扩140对、未开发新机制。
