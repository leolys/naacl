# 观察O与解释B的通用边界修订

用户指出的问题成立：旧提示只要求“reading”，没有要求读数、编码解读和业务结论分层。实际生成器把风险排序、数值趋势、插值及均值计算写进O，使B变成了对已经出现的答案再做说明。此文件说明通用修改；真实输出以本轮运行文件为准。

## 不是删除图例，而是不在观察阶段接受图例结论

| 层 | 应当记录 | 不应当混入 |
|---|---|---|
| 观察O | 区域颜色、点的位置、长度关系；文字/数字原样转录及其所在位置；实体与标记的可见绑定 | 已解读的风险大小、实际指标增减、未印刷的插值数值、计算得到的均值、业务推荐 |
| 解释规则B | 图例/坐标/尺度如何将视觉事实映射为数值或语义，必要的计算及业务条件；成立的范围与假设 | 把答案本身作为规则，或默认一个未说明的编码桥梁 |
| 结论C | 运用O和B得到的数值、排序或趋势，以及它为何支持某个任务动作 | 把自己的结论当成新的图内证据 |

“某色块旁印着High”可以是字面观察；“该颜色意味着真实风险更高”已经是解释。印刷值可以转录，但转录不是认定其准确。屏幕位置升降可以观察，业务指标升降需要坐标解释。未打印数值的估计和算术允许继续做，只是移入推导结果，不再伪装成直接可见事实。

## 实际提示修改

完整英文提示在 [prompts_observation_v4.py](../prompts_observation_v4.py)。关键约束原文：

> Keep O, B, and C separate; an already interpreted result is not an observation.

> Do not put decoded metric ranks, metric trends, unprinted numeric estimates, computed means/differences, causal or business implications, or recommended actions in O.

> A printed number may be transcribed, but is not thereby validated as true.

> Do not omit the encoding bridge by placing the decoded ordering in O and using a tautology such as 'choose the largest' as the whole B.

生成器还被要求：竞争解释可以共享同一组O，不通过修改O的含义来制造分歧；必要的映射规则应实际进入对应链，而不是生成一条未使用规则后在O中偷偷假定它。

核验器增加同样边界：若O混入推断，明确标记O未确定并指出混入内容，不悄悄改写；不能因为最终选项正确就认可O。证据E.content也保留原始事实，把解读放进reason。候选B、Actor依据或历史核验不是独立视觉证据，不能写成页面上出现的文字。

这仍依赖模型遵循提示，不是形式化语义保证。不能以字符串关键词检查代替逐条观察审查。

## 通用性与未改动部分

提示不包含五个测试样本的编号、实体名、具体答案、特定颜色映射或固定轴方向。没有“印刷标签必定正确”的全局规则。图像、公开任务、gold、动作执行器、规则状态结构、候选数量、输出token上限、Actor提示均未改变。

engine.defense_prompts选择新旧提示；已有配置不含profile时仍使用legacy。当前demo.json已显式选择observation_boundary_v4，但本轮没有重新运行完整12条或140对。额外核验入口也采用同一个profile，避免首轮新提示、复核又回旧提示。

旧提示、代码与demo配置保存在before_change；旧运行目录与旧ZIP未修改。配对诊断的原始响应不会被手工“清洗”为合格O。

## 本轮验证边界

五例均为原误导条件：地图、反向轴线图、均值参考线柱图、双轴线图、扇区／标签图。前3例重用已有真实输入，不冒充新自然前缀；后2例各获得一个普通Actor自然提案。每例比较旧生成＋旧核验和新生成＋新核验，生成和核验提示同时调整，不单独归因。

不执行建议、不提交业务表单、不测稳定恢复。模型原标签一致性只在全部模块停止后离线核对；观察是否纯净、观察事实是否正确、结论是否正确分别审查。原数据及人工审核记录保持不变。
