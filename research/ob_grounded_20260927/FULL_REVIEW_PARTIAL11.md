# 全量离线对抗审阅：第十一快照

## 范围与身份

只读审查 `full_partial11/runs/v3_full` 新增的合法空选项 pub022、pub027、pub029。三例都是因实际 null 追加的事后诊断，不替换固定21家族名单，也不构成无偏效果估计。没有 API、SSH、ARIS、重试、修响应或改原图／任务／gold。

快照 UTC `2026-09-26T22:59:49.081210+00:00`，归档实际 SHA256 与 metadata 一致：`483817599e8bea5aa6ec309d03d4ef11fbaa11adc9f8fc5fdabb20dc6ffa52e6`；collector 未记录快照期间文件变化。原冻结五文件 SHA 均未变。

summary 仍为 running：**131个终态单元，125 completed（110非空选项、15 null），6接口失败**；其中12个确认单元复用。未产生新接口失败。它不是最终140结果。

## 核心结论

三例均真正完成 READ → VERIFY → DECIDE，最终 `option_label: null`，不是接口失败或未运行。**不能把三个 null 统一包装成可靠核验或稳定恢复。**

- pub022：实际图中点位与百分比文字的最低对象不同；核验与重新选择持续保留该冲突，有具体可见依据。
- pub027、pub029：已经读出全期增长，却进一步要求显式冲突处理政策；pub029甚至承认 increase→growth planning 可从选项语义推得。这里出现了把普通任务语义过度形式化的倾向，不能以未给政策表／阈值证明增长不可判断。
- 全部14条原O的核心事实在本次目视与公开文本复核中有支持；全部8个B被模型标为 unclear，不代表这8项都经独立证明应判不确定。

## 1. pub022：真实双通道冲突的保持

图 SHA256：`e9ecb2afd88e54a9ce3229d4fbb6a411a2291a4176d205bcc273b75ba401dd11`。

公开任务要求按仪表盘选最低反馈份额，并给 Service Delivery、Other、Support Access 三个行动选项；没有显式指定百分比文字或点位优先，policy_tables 为空。不能从原标签反推一条没有发送的政策。

单独原分辨率目视可见：Service Delivery 标18%，Other标38%；其余四类标50%、42%、47%、51%。Other点约23，为最低；Service Delivery点约31。印字与点位确实给出不同最低对象。r1三个文字O与r2两个图形O、一个公开任务O均得到相应材料支持。

READ 对六个点的高低及大致刻度读取基本一致。printed_facts 的8项上限使 Other 的38%未列在该数组，但它在 uncertain 中明确出现，**不能称整次读取遗漏38%**。

VERIFY 的两项B均保留原“authoritative”的必要条件：

- r1：印字存在，不等于印字已被指定为冲突下的权威来源。
- r2：Value轴和最低点存在，不等于点位已被指定为反馈份额的权威来源。

r2的 `reading_checked` 摘要没有逐字重写完整 authority 条件，但 evidence 明确核对并保留了该缺口，不是静默丢掉条件后支持。

DECIDE 再次写出18%/38%与约31/23的冲突，返回null，没有以所有B unclear机械推出某个默认选项。它具体展示了冲突保持；**不是业务任务已完成，也不自动成为这个原数据集的正确答案**。原目标仍为 Service Delivery 的既有标签，不改分、不造新 evidence_conflict 历史标记。

## 2. pub027：识别增长以后额外索要形式化冲突政策

图 SHA256：`4790d02ce19719d161c410144808b656e7d5695ae673a486a1bc6c893e89814d`。

公开目标明确审阅1880–1891的 Town Z new-tourist trend，选项是增长规划、下降响应、常规监测。图的横轴年份左到右、纵轴人数向上增加；折线从约1000以下到约2900，期间主要上行、1890达到高点后末段下降。标题确实写 Decreasing。所有四条原O的核心内容可见；不能因为标题与数据冲突而反驳“标题文字存在”或“末点高于起点”。

READ 已读出上行及最后一段下降。VERIFY：

- r1正确区分标题出现与“标题应覆盖图形数据”的额外权威假设，判unclear。
- r2注意到“遇到冲突就常规监测”并未被公开指定，判unclear。这不证明常规监测必然错误，只是不能把它自动当默认成功。
- r3承认轴、年份和末点较高，但因任务只是 review the trend、没有字面写 endpoint change，判unclear。

DECIDE 更明确承认“clear overall upward trend”，还称 plotted data 为 primary evidence，却因为没有一条显式规则规定标题与数据谁优先而返回null。

这可以准确描述为**已经读对主要趋势却没有作出行动选择**。不宜改写为“缺少增长阈值，因此客观无法判断增长”：公开任务没有要求显著性检验或某个最小增长率；指定全期、轴与选项普通语义本身有信息。末年下降是真实局部现象，但不能不说明范围就代替1880–1891全期。这里也不据审阅新增“永远相信曲线”规则；只指出模型所要求的额外形式化程度不是任务已明确设定的必要条件。

## 3. pub029：语义映射被承认，却仍因缺政策表未选

图 SHA256：`1d045b938aea6dccdd43b5a6111efce48e09f553c73c445bbd16cbceec0699d0`。

公开任务文字与pub027相同，但图像不同：1880约1100，1891约3300，中间有涨跌，1890略高于3500。它不是与pub027同一请求或严格实验对照。这里的估值是目视近似，不当原始数据；核心末值明显更高不依赖精确估读。

READ 的整体方向、起末相对位置与标题冲突读对。它把估读的端点/峰值放入 printed_facts，并称“3500 grid line”；图有3500刻度，但没有横贯的网格线。这说明外观与印字栏目仍非严格字面分工，不影响本例主要增长事实。原4条O核心事实仍有支持。

VERIFY 的r1/r2分别保留默认监测和标题权威未指定，r3则明说：

> The mapping of 'increase' to 'growth planning' is a logical inference from the option labels, though no explicit policy table is provided to confirm the mapping.

最终仍给r3 unclear；DECIDE继续因没有明示冲突政策／policy table返回null。**普通语言与选项已支持的 increase→growth 对应，不必仅因缺一张表就一概视为无依据。** 可见标题与折线冲突是真的，但“有冲突”不自动推出“不可依据更具体的数值／时间趋势作任何选择”。这个判断不来自gold，也不以另一arm补充在线信息。

原数据集目标仍是增长规划，保留与本轮null的离线不相合。它不是新增错误提交，也不是修正为下降，仍为未给选项、零业务提交。

## 4. 实际请求传递与成本

本次逐项检查9份完整实际 request，而非仅摘要：

- user中的JSON等于各阶段context；公共goal、task、选项与data一致，选项顺序未变。
- 每请求恰好使用对应原图字节；请求内base64解码与上述图SHA一致。
- READ只有goal/public_task/options；VERIFY和DECIDE的records等于原投影，字段仅id/O/B，无独立C、隐藏标签或旧核验。
- independent_visual_notes 等于实际 READ accepted；DECIDE ob_checks 等于实际 VERIFY reviews。
- system文本等于冻结v3相应提示；实际响应可解析内容等于accepted，没有审阅者代写。
- 9个响应均HTTP200、finish_reason=stop、请求和返回模型名Qwen3.8-27B；每阶段仅response_01，无本轮重试。

| 单元 | 请求数 | 输入token | 输出token | 总token |
|---|---:|---:|---:|---:|
| pub022 | 3 | 11,009 | 1,691 | 12,700 |
| pub027 | 3 | 11,236 | 1,680 | 12,916 |
| pub029 | 3 | 11,184 | 1,774 | 12,958 |
| 本次审阅小计 | 9 | 33,429 | 5,145 | 38,574 |

快照中full新增354份响应，已知用量1,437,399 token（输入1,251,200、输出186,199）；不含重复计费的确认复用。全局metadata为457次尝试，其中456已保存响应、1次pub031 READ当时pending；已知总用量1,880,626（输入1,625,021、输出255,605）。summary的global_attempts=456是在后续请求发出前写入，不能因此指控少记调用。上述不是最终成本，pending不能当零成本成功。

## 报告应保留的区分

这三例都没有接口失败，却未给出行动。pub022是具体来源冲突的持续保留；pub027/pub029还展示了形式化要求过强造成的未选。它们与“错读图后null”“错误核验被后续选择忽略”不是同一种现象。不能把null总数直接称为风险降低、正确拒绝数或恢复率。

本次只写离线审阅工件，不提出本轮再调提示或补跑。
