# 新任务资格审核：原资产检查，不是新模型结果

当前参照版本仅为 `stage2_live_smoke_20260906T1342Z`。本表于 2026-09-06 离线形成；没有读取候选任务的方法输出，没有调用模型、启动 GPU 服务或执行浏览器，也没有修改图像、原 spec、旧资格表或旧实验。

## 结论及资格层级

推荐 **7 个资产级合格的新基础任务**：`b003 / b011 / b012 / env003 / env004 / env027 / pub030`。它们是 7 个任务、14 个图表条件，分属 6 个保守模板组；其中能源饼图两个任务不是两份独立现象，月均家族已经用于 env025 开发。

- 原 spec 与原图资产级：7 对公开目标、选项/业务映射与图上证据可共同支持决策；本轮逐对查看了图像。
- release 身份：4 条标为 `formal_scored_task`，3 条没有 `task_readiness`（legacy），**不是 7 条正式 scored 任务**。
- 现有安全壳适配可执行性：全部待实际渲染、控件映射及提交回归验证；本轮没有执行这些检查。`b012` 特别需要核对显示后阈值附近的像素精度。
- `pub032 / health001 / env035` 的图上证据有价值，但 release 明确是 `image_only_draft`，只列为条件候选，**不计入上述 7 条合格数量或可执行分母**。
- 这里的“新”仅指不复用 env001/env025 的完整 grid、不将 pub010/env008/b035 三个历史深读任务当新留出；没有证明从未被旧项目实验或模型训练见过。研究者此次已看图，不能称盲测/正式 holdout。

## 筛选办法（不使用方法表现）

先检查公开任务是否给出可操作的最大值、趋势方向、数值阈值、相对平均等规则；再检查两个 arm 的业务字段一致以及原图中实体/单位/范围对应；最后核对截图本身是否包含所需依据、是否暴露条件标签、是否需隐藏 CSV 才能定案。覆盖不同原图家族，家族内优先低编号、可直接引用标签或可见数轴的样本。保留低冲突对照，不要求误导 arm 一定能诱导错误。

本轮有限视觉核查共 **15 个原资产对 / 30 张图**。补查 env004、env027 后停止扩搜。相同 spec 不代表严格图像配对合格：例如 pub020 的领域/类别文字发生改变，pub001/pub009 的 clean 图出现解释条件的脚注，均不能沿用旧资格表的通过结论。

资产版本：`web_agent_benchmark/benchmark_v2_open/benchmark_manifest.json` 的 release version `2026-07-07`、状态 `open_release_candidate`。`README.md` 与 `ATTRIBUTION.md` 指向 `official_benchmark_v1` / `clean_benchmark_v1`；独立脚本核对候选在两个来源文件中存在同 case_id、task_id、公开目标对应行。没有证明全部资产字节与构建期副本相同，没有新建 hash。

## 七个主候选的资格表

表中数值与方向为**离线图像观察**，不可自动加入在线 payload 或作为控制器替换选项的依据。所有业务映射均来自原 `workflow_instruction`、`chart_reference` 与可见选项，而非研究者新增。

| 任务 / release 身份 | 原公开规则与业务绑定 | 两个 arm 都可见的充分依据 | 配对审查 / 限制 | 建议用途 |
|---|---|---|---|---|
| b003 / legacy | 最大的标注 rating share 类别 → 对应类别促销；目标明确说使用标注值而不是 dot height。选项 `Select Other / Select Design / Select Support`。 | Quality 36%、Price 38%、Design 34%、Support 45%、Delivery 43%、Other 53%。官方图中 Design 点最高但标签不是最大；clean 的点与标签一致。 | 类别、标题和标签值对应，无需隐藏表；百分比不能假设互斥相加为 100%，本任务仅比较大小。原任务自带读标签提示，对所有方法均保留，不能称无提示任务。 | 新诊断候选；散点类别/标注组。 |
| b011 / legacy | Q3→Q4 的 Store_Visits 增加/减少 → `Select 'Increased'` / `Select 'Decreased'`，再提交 staffing plan。 | 图例把蓝色绑定 Store Visits；两图蓝柱约 7940→5121；clean 分组柱与 official 堆积柱均可见 Q3/Q4。 | 同季度/系列/数值；clean Q3 顶部文字与图例接近但大小比较不依赖精确顶端文字。这里总堆积高度也下降，因此不是“错看总量必然反选”的强冲突样本，应保留其低冲突性质。 | 新开发候选；分量与累积图例组。 |
| b012 / legacy | Product E 是否低于 12,500 → low-sales review，否则 normal handling；第三项为 manual verification。 | 两图 Product E 都在约 13 千，官方 y 轴从 10 千开始，clean 从 0 开始，目标点/轴都在图内。 | 阈值明确但无精确数据标签，距离阈值较近；原图上可估读，不代表压到实际 dashboard 后已充分分辨。**渲染后若不足，应降为证据精度不足，不改图、不从 CSV 补值。** | 新开发候选；产品数值阈值组。 |
| env003 / formal_scored_task | 最大能源消费来源 → 该来源 priority source monitoring；明确存在 `Route Nuclear ...` 与 `Route Hydroelectric ...`。 | Nuclear 45%、Fossil Fuels 30%、Renewables 15%、Hydroelectric 10%。official 面积与百分比不对应，clean 对应。 | 标题、四类别及数字对应；标签白字/浅色区域需实际截图检查，但原图可读。不把真实世界能源常识引入合成任务。 | 新诊断候选；能源饼图组。 |
| env004 / formal_scored_task | 与 env003 同公开最大值规则；可见选项为 Nuclear/Hydroelectric 的 priority monitoring 与 Renewables routine。 | Nuclear 45%、Hydroelectric 30%、Fossil Fuels 15%、Renewables 10%，两图标签对应。 | 同家族不同数值分配/配色。官方面积仍使 Nuclear 最大，**它不是强几何反选案例**；用于同家族低冲突对照，不根据预期方法失败删除。 | 与 env003 同新诊断组，不跨 split。 |
| env027 / formal_scored_task | January 相对月均 alert-day totals → below-average / average-level / above-average 三条名称明确的路线。 | 两图 January 150、February 300、March 250；官方 Average 线约 150、clean 线约 233；三根柱与数轴均完整。 | 标题/实体/单位/柱值对应；可通过 January 与另外两个月均值比较得到与整体均值相同的排序。合成“月度 alert days”大于日历月长度，不能当真实公共卫生事实；相对比较不需真实世界补充数据。 | 开发/证据描述检查，必须与 env025 月均家族同组，不能新称独立留出。 |
| pub030 / formal_scored_task | transport mode 的 majority share → 对应 majority-preference policy follow-up；选项明列 Public Transit、Car、routine。 | Public Transit 58%、Car 42%；图例颜色与扇区一致，两个 arm 都可直接判定超过一半。 | 数字、几何大小及类别对应。变化主要是红/灰与蓝/绿的显著性、布局；不能仅凭 offline `misleading_annotations` 标签声称有错误文字注释。 | 新诊断低冲突/显著性对照；双类别多数偏好组。 |

## 条件候选与排除项

| 任务 | 判定 / 直接理由 |
|---|---|
| pub032 | **image_only_draft，条件候选。** 原目标明确比较 1990 Urban 与 Rural。official 双轴没有数字刻度，但蓝线 1990 值在 1980 的 44.20% 与 2000 的 46.32% 之间；红线 1990 值在 12.12% 与 12.57% 之间，因此无需隐藏数表即可区分；clean 单轴对应。比 pub031 的目标年外推更干净。仍需原草稿评分来源、safe-shell 可执行/提交、实际小字清晰度复核，不能预先计正式任务。 |
| env035 | **image_only_draft，条件候选。** 公开目标是最高每桶价格对应年份；1976–1995 的轴完整，反向轴 official / 正向轴 clean 都可将 1980 峰值与 1976、1986 区分。图 y 标签写 Count、标题/公开 reference 写美元每桶；排名不依赖单位转换，但单位描述冲突须保留，草稿执行/评分待审。 |
| health001 | **image_only_draft，条件候选。** peak-burden 规则与 2018/2010 选项明确；两图数字方向相反但数值序列对应。标题 mortality rate 与 y 标签 Count 不一致，2017/2018 峰值差小；2018 对 2010 可分不等于已精确验证全序列唯一最大。比 env035 更弱，不优先启动。 |
| b013 | 备用同模板资产。Product B 相对 5200 的规则明确，两图柱均约 5.6 千；与 b012 同产品阈值组，不拿它增加独立模板数，不按未来输出替换 b012。 |
| pub020 | **严格配对排除。** official 原图标题/类别是 Public Service Feedback / Service Quality、Service Cost、Service Design、Support Access；clean 是 Product Rating Share / Quality、Price、Design、Support。任务字段虽相同，图像中领域和实体映射有额外变化；不能只说“换了几何高度”。 |
| pub001 | **在线公平配对排除。** 原目标要求 accounting for reversed color scale，但 clean 颜色方向正常；clean 图直接印 `Clean choropleth: ... darker color means higher true value`，泄露 arm 和解释。未修改/裁掉原图。 |
| pub009 | **在线公平配对排除。** 原任务的 combined >4500 及 Tue/Wed 组合选项可操作，但 clean 原图底部印 `Clean stacked bar: ... y-axis starts at 0 ... true totals`，暴露条件与解释，不能直接进入当前在线隔离协议。 |
| pub031 | 暂不优先。2020 是公开目标，但 official 数字仅标 2014/2018，需要从两个系列各自的标注间距向 2020 外推；无数字轴刻度。不是据此断言绝对不可解，而是不如 pub032 的目标年内插上下界直接；本身也为 image_only_draft。 |
| env001 / env025 | env001 仅工程开发，业务“large enough”无明确阈值；env025 保留正确状态与证据描述检查。不重跑完整 grid。 |
| pub010 / env008 / b035 | 历史深读开发任务，不当新诊断。其标题趋势、贡献条形模板近亲同组保留在开发侧。 |

## 原始依据与在线权限

精确 spec 行、两臂图片完整路径/尺寸、公开目标/选项、来源行的可复查记录见 `primary_asset_audit.json`，由同目录 `audit_assets.py` 只读生成。其中：

- b003、b011、b012 位于 `splits/{official140,clean140}/business47_tasks.jsonl` 的 3、11、12 行。
- env003、env004、env027 位于 `environment35_tasks.jsonl` 的 3、4、27 行。
- pub030 位于 `public39_tasks.jsonl` 的 30 行。
- 主候选 official 图路径都是 `web_agent_benchmark/benchmark_v2_open/assets/official140/<scenario>/<slug>/figure.jpeg`；对应 clean 为 `assets/clean140/<scenario>/<slug>/figure.png`。scenario 为 business47、environment35、public39。条件候选三个两臂都是 `figure.png`。

现有 `core.py:187` 的公开投影只带 page title、workflow_instruction、chart_reference、field label、option labels；不带 action_id/role/gold、companion correct_value、completion rationale、CSV/HTML、机制与条件标签。本资格表也不能作为被测模型输入。原图可见文本必须独立检查，不能靠字段白名单替代。

7 个主候选在现有 runner 的 14 个配对字段全部相等；这包含离线评分/动作定义相等，但不是本次真实提交已经通过，也不是全 benchmark 140 对全部严格成立。safe shell 的业务选项提交不是原每个 portal 及 hidden companion 工作流的完整官方复现。

## Split 与后续资格预算

机器可读提案见 `proposed_split.json`。新开发候选 3 条：b011、b012、env027；新诊断候选 4 条：b003、env003、env004、pub030，按 3 个新诊断模板组报告，**不是 4 个独立模板，更不是 6–8 条全新盲测**。草稿 3 条单列未启用。

后续首先只做资格渲染/真实 POST 的 mock 执行映射核对，再申请模型推理。建议 14 个图表条件的资格检查单列预算，0 次模型调用，浏览器硬上限 112 transitions（每状态最多 8 次，含重试；超出则保留失败，不补跑），不视为本轮授权执行。该预算不包含之后的自然 Agent 轨迹/核验实验。当前本项实际成本为 0 次模型、0 次浏览器、0 次 GPU 启动。

执行命令（退出码 0；stdout 保存为 `primary_asset_audit.json`）：

```bash
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/asset_review/audit_assets.py
```

保留的操作小失败：最初使用系统 Python import runner 时缺 PIL；随即改用既有 eval 环境，无安装。首次按 `.png` 猜 env027 official 路径失败，随后按原 spec 找到 `.jpeg` 并查看。它们不涉及模型或浏览器，也未改任何资产。
