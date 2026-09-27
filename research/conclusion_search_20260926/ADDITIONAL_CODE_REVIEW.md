# V5 与静态迁移实现审查

2026-09-26，普通离线sub-agent代码审查。审阅run_additional.py、test_additional.py、CHART_ADDENDUM.md、TRANSFER_PROTOCOL.md及两例public_context/manifest；没有API、SSH或ARIS调用，没有修改实现或旧结果。

## 发现及修复状态

1. **缓存跨arm复用风险：已关闭。** 初版缓存只按公开chart URL索引；两个顺序创建的临时服务器若恰好重用端口，URL可以相同而图条件不同。现已改为“输出观察目录的绝对路径＋URL”联合键，并有相同端口不同arm的mock回归，避免将误导图缓存交给正常图。
2. **V5 prior输入与父面板绑定：已关闭。** 父源码哈希锁不能替代旧checkpoint/initial/截图输入哈希。当前assert_checkpoint_source已在chart阶段启动锁/模型请求前逐arm比较--prior-run的checkpoint/initial/image哈希与父run_live_001的reuse_provenance，确保V5与V4同状态、同初始集合。已直接阅读确认。
3. **迁移输入manifest断言：已关闭。** 当前transfer_case在任何模型请求前核对public_context.json与chart.png的manifest哈希，不再只复制manifest。已直接阅读确认。

## 已确认的实现

- chart URL仅从合法localhost当前task form地址生成，固定转成同task/chart；拒绝其他task、query、fragment、外站，HTTP禁止redirect。
- FullChartAPI仅override hypothesis/verify的image，actor仍走原实时完整页面；公开state/history/选项及系统提示不变。图表获取保守计为一次browser operation。
- 原图bytes与MIME保留，JPEG/其他可解码图转换为RGB PNG，不resize/crop；比较解码RGB字节与尺寸。该断言是RGB解码等价，不声称JPEG压缩字节相同或服务视觉token相同。
- 追加阶段必须精确依赖已完成的父run目录，拒绝blocked父账本；deepcopy整个父账本后追加，不编辑父账本。100/300上限与关键模型参数再次核对；父源码依赖逐文件hash锁定。
- 所有新输出独占目录/阶段锁，未见付费或其他模型fallback路径。网络未知停止与重试上限沿用已测试基类。
- 迁移例固定b002/pub013；状态为静态、空history、空current selection、pending=null，不继承旧actor或旧链。两个实际public_context只有公开任务、可选项及规则，没有评分、旧提议、解释或机制标签。
- 迁移initial重新生成；V1与V4共享该initial。核验schema容量单独从5扩到6，保留全部候选并验证ID精确覆盖，不修改基类schema、不丢链。
- 迁移不启动actor、不提交业务操作。报告不能将静态候选新增称作纠错提交成功。

## 测试记录

先用unittest执行类测试：26项通过。随后指定当前四个测试文件执行pytest，含pytest函数测试：**33 passed**。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& 'D:\anaconda\python.exe' -m pytest `
  'D:\ths_Viswork\research\conclusion_search_20260926\test_additional.py' `
  'D:\ths_Viswork\research\conclusion_search_20260926\test_prepare_transfer.py' `
  'D:\ths_Viswork\research\conclusion_search_20260926\test_run_search.py' `
  'D:\ths_Viswork\research\conclusion_search_20260926\test_search_strategies.py' -q
```

最初递归整个实验目录时，pytest同时收集旧run/runtime_source内同名测试，引发collection import mismatch；未删除缓存/旧文件，改为精确当前测试入口后通过。该失败是测试收集范围问题，不是模型/浏览器实验失败，未消耗模型预算。

## 非图表正控制建议

六个逐选项请求连正常图原正确项也全部为空，值得加一个不带图表的明确公开规则控制，以区分“接口能否生成基本候选”与图面解读问题。可固定可见数字和两个行动的显式阈值规则，分别测试符合规则与不符合规则的两个假设，各一次相同hypothesis提示/schema/参数。

正控制最多2次正常模型请求，失败/重试继续计入100总账；无图表能力结论、无真实任务gold输入、不据控制反应偷偷改已冻结提示。控制若出现空链，应记录，不反复修改到PASS。

实施复核：positive_control已固定公开可见数字7和阈值5的Route A/B规则，使用原hypothesis生成器分别调用两次，预期结果只写离线result，不进上下文。页面set_content记一次browser操作；控制LocalAPI与V5共享同一ledger。控制的语义结果不gate随后V5；服务/预算停止仍全局停止。它发生在V5两arm之前，不是取得成功后才补写的控制。

## 结论边界

两项输入哈希绑定均已落实，当前实现没有未关闭执行blocking，可以启动固定追加阶段。即便链路通过，仍需运行后核对实际图像payload、阶段来源、每次真实提交和累计成本；代码审查不能预先证明V5或迁移会发现合理候选。
