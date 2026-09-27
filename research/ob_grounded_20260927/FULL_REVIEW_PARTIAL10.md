# 全量冻结版离线对抗审查：partial10

日期：2026-09-27。仅阅读本地工件，不调用模型、API、SSH或ARIS，不修改图、任务、原标签、原响应或冻结五文件。审查 pub021（最后一个固定家族代表、新增合法null）以及 pub015、pub019（新增接口失败）；未额外挑选其他新任务作语义例证。

## 1. 快照与范围

快照 `full_partial10/runs/v3_full`，UTC 2026-09-26 22:47:46；压缩包SHA256重新计算相符：`a40a004309e0b056f518c0d6b77cba7500875b3bddd8d98ac39d3ed5d6d9152f`。metadata记录采集中无文件变动。全量仍在运行，不是最终140结果。

summary有122个终态：116 completed，包括104个非空选项与**12个合法null**；6个接口失败。相对partial09，新增null是pub021，并非仍只有11个。11项复用确认组，保持原分母和失败记录。

固定21家族代表现在全部完成逐例离线审阅。这里的“覆盖21/21”仅指预定代表的审查覆盖，不是21例核验全对、全140人工准确率或新的人类确认。pub015、pub019是因接口失败追加的诊断，不替换名单，不用于无偏错误率估计。

## 2. 实际请求、图片和版本

三个单元共7次请求，均为单次HTTP 200、完整JSON、finish_reason=stop，无重试。返回模型名均为Qwen3.8-27B。

| 单元 | READ／VERIFY／DECIDE | 输入tokens | 输出tokens | 总tokens |
|---|---|---:|---:|---:|
| pub021 | 各1次，最终null | 11,220 | 1,652 | 12,872 |
| pub015 | 1／1／未运行 | 6,573 | 1,391 | 7,964 |
| pub019 | 1／1／未运行 | 4,814 | 795 | 5,609 |
| 合计 | 7次 | 22,607 | 3,838 | 26,445 |

逐项核对结果：

- 原 `data/full_*/input.json` 与 `projected.json` 一致。完整公开目标、选项、companion fields、policy_tables与page_instructions均已阅读。
- 每次实际user消息中的JSON与 `context.json` 一致；每次只有一张图，内嵌图字节与原图完全一致。
- VERIFY中的records等于原O/B，independent_visual_notes等于READ原输出；pub021 DECIDE中的ob_checks等于VERIFY原reviews。原始调用确实传递这些信息，不是只存日志。
- READ没有原O/B；VERIFY和DECIDE没有单列候选C或隐藏原正确标签字段。B中的候选/读法文字依原样保留，不能因此宣称严格C盲审。
- 所有存在的accepted均与原模型输出解析一致；两个失败VERIFY没有accepted、没有DECIDE。
- 实际system prompt逐字等于冻结v3对应阶段；快照source_hashes及当前五文件均与FREEZE相同。温度0.7、top_p0.8、top_k20、seed12345、enable_thinking=false；输出上限READ1500、VERIFY3600、DECIDE700。

三张图均单独以原分辨率输出复查。图片SHA与离线原任务资产对齐记录相符：

| 图 | SHA256 |
|---|---|
| pub021 | `c6d134682b8fee232a51fbc368362186d4f512b2557b1eb818473c634393a3fe` |
| pub015 | `851387d6a12d4d3a713225f0e9a01504fddf920e786d2ada74a3e4d30b801485` |
| pub019 | `7060b380dce4d231030d6501313ae0f08fcbc95e20aff1b6b6677f3ee15c8ff4` |

该检查确认工件身份和传递，不证明视觉判断或B状态为真。

## 3. pub021：真实冲突保留了，但“两个B均有权威”没有得到证实

### 公开任务和原O

公开任务明确要求最低反馈份额类别，候选是Service Design、Other的低覆盖跟进，以及Support Access的常规监测。它没有指定“按印字”或“按点高”优先。

原图有两套不一致信息：

- 点位置大致为Service Quality60、Service Cost50、Service Design49、Support Access35、Service Delivery50、Other22，Other在页面最低。
- 六个百分数印字为52%、51%、12%、17%、42%、41%，其中Service Design的12%最小。

原标题和Value轴真实存在；两组原O共9条对这些核心可见事实的描述有据，VERIFY均supported在此并非仅因结构齐全。

READ仍有一处独立几何错误：它称Service Delivery“高于Support Access、低于Service Design”，然而Service Delivery约50，页面稍高于Service Design约49。这个局部次序误读不改变本例最低点Other，但不能因最后null就省略。READ的printed_facts未列Other41%，但其uncertain明确写出41%与约22的冲突，故不能说模型输入完全遗失该印字。

### B必要条件被弱化成“是图的一部分”

原r1.B的必要条件是：**尽管与百分数不一致，仍将点高作为权威的反馈份额编码**。r2.B则要求：**百分数而非点高是权威反馈份额**。

VERIFY在reading_checked中都提到authoritative，但支持理由没有建立这个条件：

- r1根据Other最低、任务要求最低份额，以及Value轴是主要图形编码，就把B判supported。
- r2根据印字存在、印字属于dashboard的数据展示，也把B判supported。

“能形成一种读法”与“这套读法在冲突下应获优先”不是同一件事。公开任务要求使用整张dashboard，不能同时为两种互相冲突的权威性主张提供决定性证据。此处不是要求回到O+B⇒C核定，而是原B自己的必要条件没有被完整落实。无需硬判其中一条必错，应该把来源优先未建立这个缺口保留下来。

### 后续选择

DECIDE确实收到上述两条supported核验，却没有把它们当投票或真值证书；它重新指出两套编码指向不同类别、没有依据决定哪套权威，返回null。因而最终保留了真实冲突，未武断改选；但不能说这反过来证明两个B支持判定是正确的。

原正确标签仍为Service Design。本报告不据gold为在线模型添加“印字必优先”，也不修改评分。null是合法未选择，不是业务完成、成功恢复或接口失败。

## 4. pub015：完整五条观察被ID大小写拒绝

### 失败机制

实际VERIFY请求record ID为`r1`，含5条O；raw返回`R1`，索引1至5齐全且B完整，finish_reason=stop。`failure.json`记录`ValueError: record coverage`、`no_quality_retry: true`。这是标识不一致触发严格接口拒绝，不是漏观察、不完整JSON、输出长度截断或网络报错。没有accepted、没有DECIDE，不能修ID后重新记成完成。

### 图面与原始响应

单独原图可见标题、MO很浅黄、MS深酒红、DE小区域深红，以及浅黄High/100—深色Low/0图例；这5条原O的关键描述有据。注意本图DE确实深红，不能套用此前pub013的另一张地图颜色。

READ另称地图标签包括CA，但本图California是灰色无CA文字；这是候选之外的附加印字误读，不影响此处5条原O覆盖的事实。raw B的颜色映射有明确图例依据，且公开目标明确最高发病率，不需要凭红色日常直觉重定方向。

原B同时有限定：只在列出的三个候选中比较，未证明MO在全国每一州中唯一最高。raw reading_checked保留了候选范围，却进一步直接说MO高于MS和DE并指向选项；这一内容越过了纯读法适用性的职责边界，不宜称其完全遵守“不评价哪个选项赢”的要求。更重要的是，没有后续真正的选择步骤，不能据raw理由推定任务会完成。

## 5. pub019：原图确有明示读法说明，接口仍拒绝

### 失败机制

同样是请求`r1`、输出`R1`；原4条O及索引1至4齐全，B完整、正常结束，因record coverage拒绝。没有DECIDE，不是合法null，不能把raw核验当最终行动。

### “Clean／true value”字样的准确来源

该图下方确实打印：

> Clean choropleth: same US map base; darker color means higher true value.

这是本轮收到的**原图内可见文字**。公开task JSON没有这句；旧候选O3引用图内文字，B/conditions据此提出颜色解释；READ和raw VERIFY也读到了它。图片字节与离线原任务资产SHA一致，并非本轮在prompt中临时加的policy，也不是仅仅由旧候选自称出来的真值。

因此应披露：当前official140输入中，至少这张具体资产含有“Clean choropleth”“true value”这类明示描述。不能据这一张图把全库概括成完全没有引导措辞，也不能反过来在本轮改图、删样本或抹去文字。图内的线性颜色方向说明是在线可见证据；它不是隐藏gold字段。

### O/B语义

原图CA深酒红、TN浅黄，DE显著浅于CA；右侧图例确为深色High、浅色Low。原4条O的核心内容可见，B关于颜色方向的条件有图内caption和图例共同支持，不应一律要求额外政策才能使用。

保留原响应额外细节的问题：READ和raw O1理由把CA与Alaska说成同样最深，目视CA比Alaska更深，至少不能不加限定把二者当同色；原O1仅说CA非常深，不需要这个额外全图比较才能成立。READ又把Low底端称为20，图中20是底端上方的一个刻度，不等于最底边的数值。两点均不改变明示的深高浅低方向，但提醒“核心读法可用”不等于所有补充观察精确。

原标签CA不改；无DECIDE和提交，不计业务成功，也不借原标签替代颜色审阅。

## 6. 成本及最终口径边界

本快照全量归档330份新响应，总1,336,698 tokens（输入1,163,235，输出173,463）。summary累计432次尝试；metadata账本433次，432次已保存响应，另pub022 READ在途。已知账本总用量1,779,925 tokens，包含开发、确认与全量，不能把在途请求漏计或将其当完成。

6个接口失败仍保留：b019为O索引覆盖问题；b047、pub003、pub006、pub015、pub019为record coverage。这里仅新增定位后两者，pub006仍是确认组失败复用，不新增调用。12个null包括pub021，全部仍是已运行DECIDE但未选择，而不是未运行核验。

**结论：固定21家族的预定审阅范围已完成，但模型还存在可见事实附加误读、把存在性误当来源权威、以及格式ID错误。pub021最终保持冲突是局部正面表现，不能抵消其B核验缺口；pub015/pub019的raw内容有可用观察，也不能抵消真实接口拒绝。** 全量未结束，不提前给完整140结论，不修复旧失败或追加质量重跑。
