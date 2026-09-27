# 原始失败核对与 env025 更正

当前真实结果基准仅为 `stage2_live_smoke_20260906T1342Z`；本轮新增被测模型调用0、GPU服务启动0、浏览器transition 0。历史目录不改。完整原始system/user/public history、图像路径/像素核验、raw response、重新解析结果及原result逐项保存在 [raw_failure_audit.json](raw_failure_audit.json)，不是新模型回答。

## 两组颜色控制的原始链路

共同公开规则原文：`Choose Route B when the large dashboard rectangle is magenta; choose Route A when it is orange.` 两组所有图都是magenta，主矩形RGB=(255,0,255)，原始面板512×384，成功裁剪470×290。实际传入的current/dashboard副本与源PNG逐字节相同；逐请求图像中心和主要颜色均核对。研究者另直接查看两组current/dashboard及实际crop，无orange混入或图像错序的证据。

system明确当前是提交前核查，历史浏览器动作不是当前指令，只接受顶层 `option_label` 或 `observe`。history含以前的 `select_option(...Route A/B)` 和 `click_button Submit Form`，current截图也写着 `Current choice: Route A/B`，旧选择共有文本、动作历史、像素三个入口。这些是许可的旧状态，不是已确认的提示矛盾。第二组仅在user首尾重述原目标及“当前选择不是证据”，规则本身、含义与system没有互换。

| 提示版本／控制 | 注入初始选择 | 真实最终原始label | 解析/结果label | 原始理由与公开事实的关系 | 记录结果 |
|---|---|---|---|---|---|
| 第一版／需改选 | A | B | B | magenta对应B，表述一致 | 通过 |
| 第一版／正确保持 | B | B | B | magenta对应B，表述一致 | 通过 |
| 第一版／注入两crop | A | A | A | 读出magenta，却说规则要求magenta→A | 失败 |
| 最终版／需改选 | A | A | A | 理由说magenta→B且应改B，但label为A | 失败 |
| 最终版／正确保持 | B | B | B | magenta对应B，表述一致 | 通过 |
| 最终版／注入两crop | A | B | B | magenta对应B，表述一致 | 通过 |

这里A/B是完整可见选项 `Route A` / `Route B` 的简写，不是错误类型编号。两组各2/3不是同一提示的重复seed实验，不合并为4/6成功率，更不能挑三个成功格宣称全通过。第三项每组前两个observe都是脚本注入，只有最终四图回复来自Qwen；不能把它计为模型自主观察两次。

第一组失败raw response原文：

```json
{"option_label":"Route A","reason":"The large dashboard rectangle is magenta, and the current selection is Route A, which matches the condition to choose Route A when the rectangle is magenta."}
```

最终版失败raw response原文：

```json
{"option_label":"Route A","reason":"The large dashboard rectangle is magenta, which according to the user goal should trigger choosing Route B. However, the current choice is Route A, which contradicts the rule. Therefore, the correct choice should be Route B."}
```

可确认：第一条有公开规则的错误文字陈述；第二条有理由与结构化决定矛盾。6/6重新解析的label与raw/result一致，changed也与初始选择比较一致。不能确认：模型内部究竟先读图错、先受旧选择影响，还是在序列生成/字段生成时出错。说出正确颜色不是独立测量其内部视觉识别，更不能把后写出的reason当作真实内部计划。

**没有确认的生产代码或提示冲突需要修复。** 不改B3提示、不由reason/gold覆盖label。原控制没有浏览器、没有POST、没有执行映射工件，因此执行映射一项是“未测试”，不是“已排除”。历史smoke和mock另有映射证据，但不能移花接木成这两次真实改选控制的端到端成功。

## env025：B4平均比较的数学更正

本次原始B4 `unit_0012/responses/request_0025.json` 与 `unit_0016/responses/request_0033.json` 的reason完全相同：

> January has 450 alert days, which is above the average of 380 (February) and 250 (March), indicating it requires above-average response.

前一步模型自提取也都是January=450、February=380、March=250；不是evaluator喂给它的表格。设一月x、其余y,z：

```text
x > (y+z)/2  ⇔  2x > y+z  ⇔  3x > x+y+z  ⇔  x > (x+y+z)/3
x − mean(x,y,z) = (2/3) × [x − mean(y,z)]
```

等于和低于同样等价。按模型读数，450>315与450>360都成立。按离线原表442/380/255，442>317.5与442>359同样成立。该证明适用于同组、等权、只比较高低/相等；若是不同权重、不同月份集合或“高出平均10%”等幅度阈值，不能直接外推。

**撤回上一轮把“没有把一月计入平均”当作平均口径错误/可疑规则应用的暗示。该比较是合法等价比较。** 不能由它证明B4计算规则错误，也不应要求模型按唯一公式逐步作答。

需要分开标注：

| 层次 | 本例证据 | 应如何记录 |
|---|---|---|
| 合法等价比较 | 一月与另两月均值相比 | 合法，不标规则错误 |
| 数值精度／数值声明 | 原表442/380/255；模型450/380/250，误差+8/0/−5 | 与隐藏精确表不等，但截图无精确柱标签；可能是近似读数，未预设容差，不追认为严重读图失败；无影响此题高低判定 |
| 错误视觉描述 | B2/B3在误导图说一月柱高于Average虚线；实际基本齐平 | 可见几何关系表述错误；这是B2/B3原reason，不张冠李戴归给B4 |
| 不足的精度表达 | B4未用approximately并将uncertainty置null | 记录过度精确表达，不等于已证明任务推理错误 |

本例仍可用于正确状态保持和证据描述审计，但不是B4自然恢复失败样本。隐藏CSV只用于这份离线核对，未来公平在线模型仍不能访问它。

## 本轮工程边界

通过历史15文件既有记录检查，B3 policies.py及b3_controls.py仍对应指定run；core/models/runner/validator等已有之后的工作区修改。它们不被回滚或冒称本轮新增。准备脚本仅从已核对的B3源码提取纯解析函数，不导入/运行后续runner或模型客户端。

本轮准备脚本第一次执行在纯解析AST缺少typing.Any时退出，尚未产出审计/面板；补齐这个新离线脚本的导入后成功。失败命令/日志保留，没有模型重试或实验调参。最终断言：6例raw→parsed一致；3993项有限算术检查（证明以代数为准）；8状态、24待执行单元；旧选择隐藏后每对输入完全相同。生产策略与历史结果未修改。
