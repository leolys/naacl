# v1 部分开发结果：独立语义审查

状态：仅审查 `partial02/runs/v1_dev` 已归档的前 5 个单元；总面板仍在运行，不能作 8 单元或 140 条最终结论。没有调用模型/API/SSH/ARIS，也没有修改被测输入与响应。

本快照中 4 个单元完成读取—核验—选择；registration/b002 在读取阶段返回空 visible_facts，被既有 validator 拒绝，后续核验与选择未执行。快照 summary 的 global_attempts=13；最终成本须等待完整账本，不能用这个数代替全轮预算。

## 可观察的局部推进

1. **coverage/pub001 误导的混合 O 得到更完整核对。** 旧 O/B-only 对 r1/O2、O4 只确认 TX 深色、ME 浅色，忽略同句中的错误图例端点，给 supported；v1 两条均给 refuted，说明本次确实检查了整个主张中的映射部分。
2. **registration/pub001 误导部分 B 子项开始分开。** r1/r2 的视觉解码被反驳，但任务项单独讨论最高风险优先，不再只用“颜色读错”反驳任务目标。不过最高优先仍只是惯例推断，supported 的证据强度偏宽。
3. **pub001 最低优先假设有时改记 unclear。** coverage/r3 理由最终承认任务未定义 priority 方向，应记未确认，而不只是因惯例不赞同就直接反驳。
4. **pub013 逆向风险定义保留为尚未确认的条件。** registration/r1 task_applicability 为 unclear；这是相对于此前某些单元将“可能为 Safety Index”直接支持的更谨慎处理。但不能把任何 uncertain 增加都算进步，需要逐条理由支持。

以上变化均来自固定原 O/B 与同图上的实际输出；没有达到全部分工一致，也不能单独归因于新增读取而非同步改动的核验提示。

## 未改善或出现退化

### 独立读取不是视觉真值

registration/pub013 的 READ 在未看候选时已经将 DE 读成深红/栗色，VERIFY 随后也支持该假观察。可见“首次独立读取”不能保证修正视觉识别，更不能将两次一致当作独立验证。原图中 DE 并非 KS 的深栗色。

registration/pub001 正常的 READ 只谨慎说其他若干州也是深红、ME 最深或并列最深，没有确认 AK 与 ME 相同；VERIFY 仍把旧 O 中“AK、AL、ID、MN 都是与 ME 同样最深色”全部支持。至少 AK 明显更亮、更红。这说明后续仍可能沿候选文字确认错误关系，不能因最终选 ME 就认为 O 核验可靠。

### C 推导越界在 pub013 再次出现

registration/pub013 r3 的实际读法是 High=高风险、Low=低风险；原 B 后面还夹带候选想选择 KS。旧 O/B-only 该项虽在文字中讨论矛盾，最终仍支持标准读法；v1 task_applicability 因“KS 不符合 High=高风险，所以规则内部矛盾”给 unclear。

这不是对公开任务所需方向、指标或范围的单独评价，而是又把候选动作是否服从读法作为 B 判断的依据。比旧版该项分工退化；不能因标签从 refuted 改成 unclear 就自动视为更准确。

### B 两个维度仍会互相替代

coverage/pub001 误导 r1/r2 的 task_applicability 又因为视觉解码错误和 TX 结论不对而给 refuted。与 registration 同图的输出不同，说明分工不稳定。

coverage/r3 的 task 理由还有大量自问自答，先后讨论 unclear、refuted、业务常识和应选谁，最后才落到 unclear。虽然没有旧 inference 字段，理由仍会把工作扩展为再答题，而不是简短评价被检读法。

### “reasonable”仍被提升成 supported

registration/pub001 正常与误导多条 task 依据明确承认最高优先未在公开任务定义，只是 reasonable/logical/typical，却仍给 supported。最低优先在正常图仍仅因违背 standard interpretation 就给 refuted。新提示要求 concrete public support，但模型尚未稳定采用这一证据门槛。

这不等于“最高优先一定错误”；问题是判定的证据层级没有与本轮 supported/refuted/unclear 定义一致。

## registration/b002：接口失败，不伪装成核验失败

实际 HTTP 200，返回模型 Qwen3.8-27B，finish_reason=stop，输出 60 token。返回内容只有两条任务定义，`visible_facts=[]` 且 uncertain=[]。后续 validator 报 no visible facts。

因此记录应是“读取输出不满足既有非空接口，核验未执行”，不是服务没看到图、模型拒绝柱高路径，也不是被测核验判错。

若 v2 将现有客户端的非空约束同步进 JSON schema 的 minItems=1，这是接口契约对齐。不得把随后非空本身算视觉理解改善；是否读对仍要另外核对。v1 的失败不补写成成功，不替换样本。

## 第二版最小建议

本版已重复要求 ignore action suggestions，但实际仍受 B 内嵌 C 牵引。单纯再添加一句同义提醒未必足够。可以加入 **一个短的 B.reading_under_review** 作为受检对象记录，但须限定用途：

- 尽可能引用原 B 中读法、指标/方向/范围与必要条件的短片段；不自由改写为更合理的新规则，不丢条件词。
- 它是模型实际选择评价的对象，供人工审查，不替代原 B，不进入持久规则，也不作为硬筛选/代码自动纠正依据。
- 排除“最后选择哪个实体”的动作提议，不排除真正的实体绑定或比较范围条件。不能为了避开错误而只摘原 B 中最容易支持的一部分。
- 若仅为精简而不加字段，也可要求 evidence 开头先明确受检读法；但这种纯文字做法更难检查是否把对象换成动作。本审查倾向短字段，而非继续堆叠禁令。

其收益应评价为“是否更清楚且稳定地在评价读法”，不能把多输出一个看起来正确的短句当作读法真实性已解决。新增字段本身也有遗漏条件、选取有利片段的风险，必须保留原 B 对照。

另外，将 evidence 限定为简短依据、证据不足命名缺口，能够减少长篇再决策式自辩；不要增加单独推导状态或强迫必须支持/反驳。实体、样本、特定颜色或答案不可写进新 prompt。

最终是否采用 v2，仍应等待全部 8 个开发单元，不以当前局部改善选择性终止或更换失败样本。
