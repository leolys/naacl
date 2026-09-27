# 公开输入的提示性条件与候选来源限定

全量冻结运行中对抗审阅发现：b003的公开目标与图表使用说明已经明确要求按 **labeled rating share（标注份额）** 决定。其策略表还有 `Decision metric: mislabeled_value / labeled rating share`。同类字段也在b006、b008中。它们来自原runtime-aligned公开页面投影，本轮没有添加、删除或重写。

这有两层含义：

- 明确指定标注份额时，按标注值比较有公开任务依据，不能一律批评为无根据的标签优先。b003几何读法的任务条件被反驳，可作为该条件下的局部核验例。
- `mislabeled_value` 是有提示性的命名；这些样本不能用来证明模型在毫无来源提示时自主发现了图形与标注的优先关系。即使去掉这个名称，现有任务文字仍明确指定标注值。

之前较窄的关键词检查没有覆盖 `mislabeled`，不能将无命中描述为“所有140条没有任何提示”。本次补充只读扫描覆盖mislabeled/mislead/decept/distort/truncat/reverse/invert，记录到PUBLIC_INPUT_AUDIT.json；词汇扫描本身也不是完整语义泄漏审计。

保持原样完成当前140应用，保留全部分母，不在看过结果后改变这3条或排除它们以修改总结果。这三条只是已核对的文本字段提示，不能据此声称其余137条都没有提示性内容。

## 图内已有的提示：pub019

pub019原图底部印有 `Clean choropleth: same US map base; darker color means higher true value.`，图例也为深色High、浅色Low。主审与对抗均逐图查看确认；它不是本轮新增提示，也不是只存在于旧候选的假设。原task文本本身未含这句话，候选O/B引用的是图内已有内容。

本轮图像SHA256为 `7060b380dce4d231030d6501313ae0f08fcbc95e20aff1b6b6677f3ee15c8ff4`，与原official140任务指定资产、旧runtime-aligned准备图相同（见ORIGINAL_LABEL_ALIGNMENT_v2.json中full_pub019）。因此更准确的面板名称是“official140原指定单图条件”，而非断言每张图都实际含反向色标等误导。家族metadata不证明图面机制。仍保留原任务、标签和本次接口失败，不自动清洗或改分；本轮也没有对所有图做完整OCR式提示审计。

另一项已知限定：原候选B全文和conditions保留，其中可能包含旧行动或“什么选项更合适”。本轮只移除了独立C字段及旧核验，并非严格结论盲审。核验的指令要求不评价旧行动，不代表模型事实上完全遵守。

全量中136任务使用旧Terra候选，4任务无有效旧链只补生成一次Qwen候选。旧Terra建议只是跨模型历史参照，不能由它与新Qwen选项的差值估计核验因果收益。
