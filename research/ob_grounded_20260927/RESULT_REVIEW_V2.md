# v2 完整开发面板：独立对抗复审

结论：**接口完成度提高，个别职责错误改善，但视觉核验仍不可靠，且存在可定位的退化。** 可以按已审的通用 v3 做最后一版固定开发测试；不能把 v2 最终选项正确、HTTP 200 或结构校验通过，写成解释链核验可靠或任务纠错成功。

审查只读本地冻结输入、实际请求/响应、源图和 v1/v2 工件；未调用模型、API、SSH、GPU 或 ARIS，未修改模型输出，未查看确认组结果。审查判断不是项目所有者的人工确认，也不重定数据集 gold。

## 运行、身份与输入复核

独立复算 `runs/v2_dev` 的全部请求：22 次尝试 = 8 次 READ + 7 次 VERIFY + 7 次 DECIDE，全部 HTTP 200，0 次重试。7 个完整单元；`coverage/pub013` 的 READ 输出达到 1,500 token，`finish_reason=length`，JSON 字符串截断，后续 VERIFY/DECIDE 均未运行。失败必须保留；它不是核验语义反驳，也不是未被挑选的样本。

- 响应模型名全部为 `Qwen3.8-27B`；请求使用冻结的 temperature 0.7、top_p 0.8、top_k 20、seed 12345、关闭思考配置。
- 本轮输入 85,976 token，输出 18,921 token，合计 104,897 token。summary 的 `global_attempts=42` 含 v1 的 20 次，不能当成本轮次数。
- 22 个 system、schema、公共上下文、O/B、读取笔记、核验记录，均按 v2 冻结源码重建并与真实请求对上；22 张请求图像的字节哈希与 manifest 一致；5 份 runtime_source 哈希一致。
- 21 份 accepted 对象等于对应原响应 JSON；截断 READ 没有 accepted，也没有被手工补全。
- READ 只见公开任务/选项与同一全图，不见候选 O/B/C。VERIFY/DECIDE 见完整原 O/B，未另传 C、gold、旧核验结果或样本机制标签。O/B 本身仍可含行动结论，所以不能称真正的 C 盲审。
- 本轮是静态核验及重新选择；业务提交数为 0，没有浏览器任务完成结果或持久规则生成。

### 相同请求不等于相同响应

四个图输入各自的两个 READ 请求文件均字节完全相同。尤其 b002 两份 SHA256 都是 `51fcfeacfd2e123d5ef06018da69333370593e0a8086c4b09d524da64b446f49`：registration 错称 Edge 更高，coverage 却读出 Firefox 约 85、Edge 约 78。固定 seed 没有令本次服务输出完全确定；现有记录不能进一步定位后端原因。

这是预先固定的两条 pipeline 分支产生的重复读取，不是按质量重试。READ 不接收两来源的候选，不能把两次读取差异归因于候选 O/B。8 个单元也不是 8 个独立基础任务：仍是 3 个基础任务、4 张图、两种候选来源。

## 八单元结果

表中 ME/Edge/IL 只是公开选项的缩写，不是核验准确率。

| 单元 | 终态／重新选择 | 相对 v1 的主要观察 |
|---|---|---|
| registration/pub001 误导 | 完成；ME | 错误颜色—图例绑定仍被反驳；最低优先条件从 unclear 变为按惯例 refuted，证据门槛未修好 |
| registration/pub001 正常 | 完成；ME | 全部 20 条 O 获 supported，包括 AK 等同 ME 最深色的错误断言 |
| registration/b002 | 完成；Edge | 不再空读取，但把正确的 Firefox 较高反驳为错误；新增完成不等于新增可靠性 |
| registration/pub013 | 完成；IL | r3 能抽离旧 KS 行动评价读法；DE 仍错读为栗色并被核验支持 |
| coverage/pub001 误导 | 完成；ME | 混合 O 的错误图例绑定仍能反驳；看不到 dropdown 却判 refuted，缺证据与反证又混淆 |
| coverage/pub001 正常 | 完成；ME | v1 曾识别 AK 并非同最深色，v2 又支持该错误；整句只核对部分内容的问题也回归 |
| coverage/b002 | 完成；Edge | READ 正确分开标签与柱高，O 中“Firefox 第二高”被反驳；DECIDE 仍无依据宣布标签为主要真值来源 |
| coverage/pub013 | READ 截断失败；未选择 | 不是已执行核验失败；原图/任务保留，不能以另一来源成功填补 |

## 具体语义证据

### 1. b002：读图错与自行确立来源优先，不能靠最终选项掩盖

原图的蓝色 Firefox 柱顶高于绿色 Edge，分别约 85 与 78；印字则分别为 23% 与 87%。`dev_registration_b002/read/accepted.json` 错称 Edge 最高；随后 `verify/accepted.json` 的 r3.B.visual_decoding 以“绿色 Edge 明显更高”为反证，错误反驳原来的几何读法。这不是 B 假设真的被视觉证据否定，而是核验器读反了可见高低。

`dev_coverage_b002/read/accepted.json` 则读对几何，并在核验 r3/O3 时反驳“Firefox 第二高”。这是具体局部进展；但同份 B 的 visual_decoding 理由又把“labels and heights”合称支持 Edge 最高，未保持前面已分开的依据。

两次 DECIDE 均选 Edge。coverage 的最终理由明确说印字是 “primary source of truth”，并把柱高冲突推测成常见图表错误或缩放问题。公开任务要求最大 market_share、以 dashboard values 为依据，但没有宣布印字天然优先于几何。因此选项即便与原评分相合，也不能为这一来源优先规则背书。

### 2. `reading_checked` 有帮助，但不是忠实性证明

26 条实际核验记录的 reading_checked 均可在原 B 文本与原条件按序串接后找到原文片段；未发现这一字段直接新造更合理规则。这个检查只证明摘录来源，不证明必要条件完整或职责分离。

最明确改善是 `registration/pub013` 的 r3：v1 因原 B 夹带选择 KS 而将任务适用性判 unclear；v2 摘出 High=高、Low=低的读法，不再因为 KS 不符合该读法而否定它。这是局部职责改善，不是重新证明所有条件。

残余例子：registration/b002 r3 仍摘入“Firefox 最高”的结论；coverage/b002 r3 仍摘入“因此应将 Firefox 加入队列”；registration/pub001 正常 r3 仍含“ME 是正确选择”。字段存在不意味着已将行动评价排除。pub013 r4 只引用首句，后续原假设没有完整重述；不能凭原文片段相等就宣称条件覆盖完成。

### 3. 地图：邻区/色阶错误仍会被二次确认

pub013 的 DE 是邻近深红 MD 的小区域，图上并非 KS 的深栗色。v2 registration 的独立 READ 仍把 DE 记作与 KS 等色；随后 r3/O4 支持“DE 深栗色”。r1/O5 的“medium red”也被反驳，但反证仍是假定 DE 深栗色：不能因其否定原句就把该核验计为可靠。最终 IL 选择没有消除这一观察错误。

pub001 正常图中，AK 是明显亮于 ME 的红色；v1 coverage 曾反驳“AK 与 ME 同最深色”，v2 coverage 的 r1/O5、r2/O4 又支持它。其他 ID/AL/MN 与 ME 被归为相同最深色也过度概括。相同图案上的局部退化应保留，不只展示读对图例的部分。

coverage/pub001 正常 r4/O3 还声称图例标着整张图标题。v2 的支持理由只核对 High/Low 与 0/100，跳过了错误的标题位置部分；v1 曾反驳此项。整句支持门槛没有稳定执行。

### 4. 假设、惯例与反证边界仍不稳定

pub001 的公开 page_text 只要求加入 Priority hazard review，没有明确规定最高或最低。v2 多次承认最高优先是 reasonable/typical，仍写 supported；最低优先则因 counter-intuitive/不符合 standard usage 写 refuted。这混淆了“更自然的解释”和“有公开证据确认/否定”。无需强求所有读法都 supported，也不能把更多 unclear 自动算改进；应看具体必要条件是否已有依据。

pub013 的标题 Risk Index、High/Low 与“highest-risk”任务确实为正向解释提供更多语义依据。此处不能机械要求正反两读法都 unclear；但仍需区分文字定义与惯例，不能只靠“standard”替代证据说明。

coverage/pub001 误导 r1/O5 关于当前 dropdown 的事实在静态图上不可见；v2 因图里没有表单就判 refuted。缺少这个界面的截图只证明当前输入不足，不证明旧界面状态相反。registration 同项写 unclear，进一步显示边界不稳定。

## 对最后一版开发的决定

值得做一次预先固定的通用 v3：分开描述外观与印字、限制无关全国枚举、将 B 两个容易互相代替的轴收敛为对读法及必要条件的单一证据判断。这针对已记录的职责与观察失败，不是要求输出某个实体，也不保证会改善。

v3 必须保留全部固定八单元、旧结果、截断和成本；不能再按是否达到理想选项开启第四版。它同时改变 prompt、读取 schema 和输出规模、B 判定结构，不能从版本差异声称某一条提示的因果效应。确认组须在冻结后运行且不驱动本轮修改。

本阶段可以说“流程基本可执行、局部读法评价改善，仍有稳定性和视觉事实问题”；不能说“已可靠核验 O/B”“已证明能生成可靠持久规则”“已实现真实任务纠错”或“适用于 140 任务已经证实”。
