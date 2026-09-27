# 固定实现范围

只在本目录新增代码，旧代码只读导入；所有在线文本来自 prompts_v2.py，不在 runner 注入任务定制指导。

数据：manifest.json 固定五基础任务六条件。原 arm 的 public.json 和 chart 为旧 prepared 原文件。用旧 proposal/round_001/validated.json 的 proposal.action.option 与旧 generation/round_001/validated.json 的 generated.chains ORIGINAL 顺序选择第一条相同 option_label 的链。只继承该链和其规则；保留来源索引；不把其余链、旧核验、score、gold 读入在线 context。若 generated 结构不在该文件，读取同阶段 parsed.json，不从 record 中依答案选择。选择规则不可按结果改变。Clean 独立调用 SEED，完全不读取另一 arm 的 proposal/chain，只共用相同公开任务。

每例 stages seed(仅clean)→questions→competitors→verification；一轮各一次。全panel共享 EstimatedBudget，复用 BudgetedPanelAPI 原实际请求回执与重试账本。19正常调用；<=24attempts，<=3estimatedUSD。失败阶段不重采样；普通实例结构失败记录后可处理下一例，ServiceStop/unknown request outcome 则停止panel。不得静默恢复/重复旧request。--prepare 无网络；--live 明确凭证环境，输出目录不存在才运行。

复用老b001的 questions validator 与共通字段paths/公开字段守卫，但 QUESTIONER多 visual_inventory(0–8条) 与 current_bridge 非空字段。不要靠词语黑名单去判语义正确。candidate结构参考prompts_v2；0–2条、每个question response覆盖/依赖一致、公开option、完整rule、非空claim/difference/discriminator，claim_kind支持行动、反驳支持、未确定；后两者必须nulloption。observations保留局部chart引用；空alternative合法。不将 exact duplicate 计新候选，但语义重复仍由审查报告，不靠程序冒充语义核验。

新schema独立规范化：只规范rule IDs和chain IDs并排序，保留claim_kind、option_label可能null；来源映射只入sidecar。Verifier context仅common +normalized +public_task_text_paths；不传questioner摘要/来源/base_proposal。可复用 citation_adapter 和 RuleStore，但 null非行动链不得当作全局优胜选项，负面挑战也不得自动激活替代action。保存raw recommendation与保守validated recommendation的区别，程序不得凭null抹去真实verdict后声称模型改变。明确RuleStore是原简化状态快照，无跨步有效性实证。

审查修正（live前）：支持缺口规则可以陈述必要充分性条件，不要求另一种映射。discriminator.alternative_reading 对 challenges_support / underdetermined 可以 JSON null，对 supports_action 仍必须非空；observable_check 始终非空。不要用程序判断语义新颖性。

每例result包含完整inputs、questions、competitors、normalized、provenance、verification_raw/validated、rule_state、status/failure、API费用来源；另有全panel summary/budget。runtime源与config/prompt/manifest固定记录，原资产不变，fullwire请求不含secret。

测试必须阻断网络：正确真实question传递、clean不读另一arm、unknownrefs、nullchallenge合法/推荐不能null执行、0竞争合法、最多2、raw完整保留、privatefield拒绝、无质量retry、全局预算/成本、oldoriginalinput未修改、不同task相同prompt。测试与真实结果分开。
