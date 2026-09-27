# V7 GUI投影与V6静态工程续接：代码审查

2026-09-26。离线审阅run_isolated.py、ISOLATION_ADDENDUM.md、test_isolated.py、两个真实pub001 checkpoint以及已有静态资产。未调用模型、SSH或ARIS，未修改冻结实现或旧工件。

## 结论

当前固定面板没有未关闭的执行blocking，可以开始。需要将同一输出目录中的**V7 GUI执行上下文隔离**与**V6静态首次工程续接**分别报告，不能将后者称作新的去历史迁移实验。

## value删键的实际审查

审查者递归枚举了两个真实checkpoint中所有待删除字段。两arm的value字段仅为：

- primary_action当前控件值：option_2或option_0；
- 各option提交token：空串、option_0、option_1、option_2。

其余删除项是页面临时URL、当前selected_text及各option的selected布尔状态。**固定pub001没有任务数值、阈值或业务政策存放在被删除的value键中**。完整state.text、字段标签、可选项文字/顺序、disabled属性和公开goal仍保留；top-level options也未改。

因此该投影在本面板没有发现删除业务规则的问题。但递归删除任何名为value的键不是一般无损变换：其他任务的只读事实、阈值或表格值可能也叫value。代码/协议不能据此声称可直接推广到任意任务。

## 阶段权限与真实执行

- hypothesis请求只传goal/options/hypothesis_option/search_question及投影state；不传history、pending、旧链。省略这些字段不等于声称真实历史为空。
- IsolatedChartAPI先用原上下文获取且校验与V5相同的完整原图，再投影候选请求，避免删除url后无法检查来源；没有引入裁剪或人工图例框。
- 使用同一V6契约替换和原假设schema/参数。核验仍走原上下文，actor仍看到实时完整页面和真实历史；没有答案筛链、直接改选或自动提交。
- 对两个静态例，main实际构造的是contract.ContractAPI，不是IsolatedAPI。它们保持原公开输入，复用既有initial，分支名为contract_hypotheses，注明V6续接。

## 归档守卫修复与预算

- main只允许对应记录的静态输入守卫失败继续，并检查不存在已完成静态模型产物；拒绝blocked模型账本，核对父源码版本与原checkpoint来源。
- 两个静态例在任何新推理之前统一验证prepared原字节manifest、源/归档图像哈希及解析后公共JSON对象相等，分别记录源字节和派生归档字节哈希；不修改旧manifest或回写旧结果。
- 已独立证明本轮两例差异恰为末尾单LF，故该修复是工程续接，不是放宽真实任务语义。JSON对象比较不应被宣传为适用于任意未审计工件的万能完整性校验。
- 继承原67次请求/66操作账本，仍按100/300硬限额计全部新尝试和重放；正常理论≤24次新请求不是独立追加额度。若重试耗尽余额，记录未运行部分，不重置目录重新开始。

## 离线回归

指定当前六个test文件执行pytest：**40 passed，退出码0**。新增测试包含：投影保留公开文字并不修改输入对象；真实prepare_transfer.save_json→base.dump→validate_derived_context链路；改变JSON语义会被拒绝；两个真实静态资产通过校验。

这弥补了此前只mock同一字节JSON而未覆盖归档序列化差异的测试缺口。它不等于真实服务、浏览器或研究效果已经通过。

## 运行后必须保留的边界

V7同时删除多种执行状态信息，不能只归因history一个变量。即使生成更多对象，也应分别评价结构交付、O是否忠实、B是否循环、不同解释、核验及实际提交。先前V5已在没有结构化新链时纠正，不能把后续成功全部归因反问补链。

全部早期失败、V6静态未运行状态和本轮工程续接来源都应保留；固定面板结束后交付审阅，不自动扩任务或追加下一种变体。
