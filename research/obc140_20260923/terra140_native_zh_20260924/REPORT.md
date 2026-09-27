# 140 条解释材料交付报告

这是原图上的静态提案—解释生成—核验材料，不是网页多步任务执行或防御有效率评测。

## 实际完成状态

- 固定任务：140；领域分布：商业 47 条、环境 35 条、健康 19 条、公共事务 39 条。
- 生成完成：135；核验结构校验完成：99；现有文本的原生中文映射齐备：140 条任务。最后一项不代表缺失的模型阶段已补全。
- 可阅览的原始解释链：140 条任务（含结构校验未接受、但已返回可读草稿的任务）；不把这项等同于校验通过。
- 英文复用：b001、pub013 两条；新请求尝试：409（上限 450）。
- APIYI 翻译请求：0；浏览器业务操作：0；GPU：未使用。
- 规范化后多条解释指向不同选项：82 条；规范化解释链数量分布：{2: 81, 1: 34, 0: 5, 3: 20}。未强行补写竞争链。
- 已接受核验中的选择变化：保留原提案 42，建议不同选项 1，未给出推荐 56。改变不等于纠错，没有使用 gold 给变化定性。
- 新账本保守估算：$11.569135；这是估算，不是账户实际扣款。
- 重试尝试：0；HTTP 成功响应：409；模型返回名称分布：{"gpt-5.6-terra": 409}。名称来自网关声明，不证明实际内部权重；HTTP 成功不等于内容校验成功。

## 如何看

直接打开 OBC140_TERRA_ZH_REVIEW.html，无需项目、服务器或网络。左侧筛选任务；点击原图放大；切换中文／英文；展开逐链核验、规则状态与原始 JSON。人工笔记可导出。

O 是可见事实，B 是解释规则，C 是结论；这只是字段设计目标，不保证每条模型输出都遵守。单链、多链同选项和不同选项竞争在页面分别提醒。

规则 active 不等于整链成立或行动被接受：还要查看 implication 与 recommendation。health010 的固定审查明确记录了规则保留、行动蕴含却被反驳且推荐为空的情况。

英文模型记录保持原样。中文仅为独立阅览层，重复原文复用同一译文；译文不改正原回答。公开任务引用与图像引用分开标示，来源绑定不是内容真实性认证。

run 中 translation=not_run 表示没有执行 API 翻译阶段；本轮原生中文侧车的完成状态在 review_data_zh.json 单独计算，两者不是同一个计数。

沿用预先固定的格式处理：生成阶段只在 finish_reason=stop 时允许补末尾 JSON 闭合符；规范化候选最多按原生成顺序保留三条。原始响应及处理日志均保留，不是语义纠错；length 截断不补完。格式修补工件 0 份（含复用来源如有），触发候选上限的任务 0 条。

## 失败与证据限制

失败阶段：[{"task": "b008", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b010", "phase": "verification", "status": "failed", "error": "model_request_or_parse_failed"}, {"task": "b011", "phase": "generation", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b015", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b016", "phase": "generation", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b017", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b021", "phase": "generation", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b022", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b027", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b035", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b036", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b040", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b043", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "b045", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env001", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env002", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env003", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env005", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env009", "phase": "generation", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env010", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env012", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env013", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env016", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "env024", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "health004", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "health006", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "health007", "phase": "verification", "status": "failed", "error": "model_request_or_parse_failed"}, {"task": "health012", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "health013", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "health014", "phase": "generation", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub003", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub007", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub009", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub012", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub014", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub017", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub018", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub021", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub031", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub034", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}, {"task": "pub036", "phase": "verification", "status": "invalid", "error": "structural_validation_failed"}]

详细故障见 failure_audit.json。达到长度上限、引用路径格式不符、字面规则过滤与真正的视觉理解错误是不同事件。b011 的字面拒绝归因见 FAILURE_INTERPRETATION.md；其原始条件式解释保留，不提升为已核验规则。

接口／输出失败原因分布：{"task citation field unavailable: user goal": 5, "output_length_limit": 1, "rule contains an action label instead of an interpretation": 2, "unobserved evidence source": 9, "candidate observations lack chart provenance": 3, "task citation field unavailable: user goal and option labels": 3, "task citation field unavailable: routing criterion and option labels": 2, "task citation field unavailable: routing criterion field": 2, "task citation field unavailable: routing_criterion companion field": 2, "task citation field unavailable: routing criterion and options": 1, "task citation field unavailable: user_goal and option labels": 2, "task citation field unavailable: user goal and review window": 1, "invalid_json_on_normal_stop": 1, "task citation field unavailable: option list": 1, "task citation field unavailable: chart_reference and option labels": 1, "task citation must locate one nonempty public text field": 1, "task citation field unavailable: user goal and options": 1, "task citation field unavailable: user goal and option list": 1, "task citation field unavailable: user goal and chart reference": 1, "task citation field unavailable: user_goal and routing_criterion": 1}。

b001 的几何副链核验有“接近”被过强解释为“并非较小”的已知疑点，已保留提示。其他逐例疑点以 semantic_review.json / SEMANTIC_REVIEW.md 的实际审核范围为准；未审核不等于无问题。

没有按隐藏答案修改输出，没有注入错误、强制答案或质量重采样。本材料不能证明解释都正确、错误提案恢复率，或长期规则保持能力。复用的两个开发例不算新的独立样本。

## 费用口径

运行限额使用全部输入×$2.5/百万＋输出×$12/百万的保守代理价，不扣缓存优惠。没有有效用量的尝试保留 $0.20 预留。此代理价不是供应商已确认的扣款上界。

有 409 次请求的用量别名出现零值／非零值等不一致。沿用既有规则取唯一非零值而不是累加别名；未解决的不同正值冲突 0 项，用量规范化错误 0 次。每个原字段与解析过程都留在 cost_summary.json，不把这项处理说成账单核实。

按返回用量及已归档公开标价的两种情景小计：{"regular_no_write_premium_usd": 9.872648, "returned_write_plus_25pct_usd": 11.5644695}；缺失费用尝试：0。

第二情景仅假设缓存写入额外加价 25%，不是已核实的 APIYI 费率。详情见 cost_summary.json；旧复用请求费用不并入新账本。

## 可追溯工件

- PLAN.md / config.json：固定范围与配置。
- run/runtime.json / runtime_source：执行源快照；run/tasks：完整请求、响应和英文记录。
- translations/inbox / outbox：原生译文的逐字符串输入输出。
- review_data_zh.json：双语阅览数据；run 中的原模型记录不受翻译影响。
- PREDEPLOY_REVIEW.md：同家族独立上下文代码审查，不是跨模型确认。
- offline_tests.xml / browser_check.json：工程检查，不代表研究假设成立。

本轮离线回归计数：{"tests": 56, "failures": 0, "errors": 0, "skipped": 0}。

本批处理结束后不自动追加任务或开发新机制。
