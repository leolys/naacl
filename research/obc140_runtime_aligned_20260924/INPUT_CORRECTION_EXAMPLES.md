# 为什么要重生成：三个具体输入差异

下面是输入文件的差异，不是模型效果比较。中文为阅读说明，实际请求保留英文。完整字段及来源见 `prepared/input_comparison.json` 和各任务 `provenance.json`。

| 样本 | 旧 OBC 输入确实包含的内容 | 原网页实际业务字段（本轮采用） |
|---|---|---|
| b001，手机市场份额预算分配 | 标题包含 “Visualization May Be Misleading”；目标要求使用 true values 而非 misleading slice sizes | 标题是 “EU Smartphone Market-Leader Promotion Allocation”；目标是查看欧洲手机市场份额看板，把高端零售推广预算分给当前份额最高的品牌 |
| b002，浏览器兼容性测试队列 | 目标要求找 highest true market_share，“rather than the tallest-looking bar” | 查看浏览器使用份额看板，把当前 market_share 最高的浏览器分配到优先兼容性测试队列；没有“不要看最高柱子”的额外说明 |
| pub003，州发病率详情路由 | 目标直接解释 reversed legend 和 lighter shading means higher incidence；完成标签还直接写 West Virginia | 目标是依据州发病率地图，将最高发病率州详情转入优先跟进；真实提交按钮只写 “Submit Form”，没有在按钮中指定州 |

这些旧文字不只是展示额外加的旁白：它们曾进入旧 OBC 模型请求。问题来自旧适配读取原始 spec，没有应用原网页已经存在的业务覆盖。因此本轮修复的是模型输入投影和相应展示，不是把旧答案换一个标题。

还同步恢复了原网页的选项顺序、可见伴随字段、业务规则表、页面说明和提交按钮。由于输入变化不止一项，新旧输出差异不能被单独解释成“去掉提示”的因果效果。

## 不能顺便抹掉的原始情况

- b003、b006、b008 的原网页业务规则本来就含有优先使用 labeled rating share 等指导，部分规则含 `mislabeled_value`。这轮保留它们，并明确标注，不把原始规则偷偷改成另一道题。
- environment/health 的 54 条原入口页可见机制 chip 属于本轮白名单未纳入的元数据。新模型输入是业务字段投影，不等于原网页所有可见文字，也没有改原网页。
- 图表自身的标题、图例、数值、形状及可能相互矛盾的线索完全保留。
- “未命中提示关键词”不等于经过人工确认完全中性；这些记录用于人工继续审阅。

本轮重新生成全部 140 条，保留旧版本供对照；新的解释、竞争解释与核验状态只能来自本轮实际返回。
