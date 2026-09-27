# b002 / pub013 迁移资产只读审计

审计日期：2026-09-26。范围：仅本地文件、原公开 HTML 的再次投影、请求图像与上下文字节核对。未调用 API、未连接 SSH、未读取 gold / 原始数值表、未运行 Agent、未修改旧结果。未使用暂停的 ARIS 技能；`.aris/task_flows_20260924` 只作为已有数据工件读取，不调用任何技能或工作流。

两例是主代理事先固定的**历史开发迁移例**，不是未见任务或 holdout。不能用其结果估计泛化效果。

## 1. 可直接使用的公共任务与图像

工作区根目录为 `D:/ths_Viswork`。以下均为真实存在的本地路径。

| 资产 | b002 | pub013 |
|---|---|---|
| 原三页公开投影 | `research/obc140_runtime_aligned_20260924/prepared/tasks/b002/public.json` | `research/obc140_runtime_aligned_20260924/prepared/tasks/pub013/public.json` |
| 投影来源及 DOM 绑定（仅离线） | 同目录 `provenance.json` | 同目录 `provenance.json` |
| 与旧模型实际输入字节一致的全图 | `research/explanation_completion_v3_20260926/run_live_001/cases/b002/chart.jpeg` | `research/explanation_completion_v3_20260926/run_live_001/cases/pub013/chart.jpeg` |
| 旧实际生成输入上下文 | 同 case 目录 `generation/input_context.json` | 同 case 目录 `generation/input_context.json` |
| 完整旧 system / user / 图像请求 | 同 case 目录 `generation/round_001/request.json` | 同 case 目录 `generation/round_001/request.json` |

**图像格式是 JPEG，不是 PNG。** 两张图的分辨率均为 3420 × 2700（9,234,000 像素）。不要把 review 页面截图、浏览器 QA 图或含人工解释的展示页面 PNG 作为模型输入，也不要只改文件扩展名冒充 PNG。

### 推荐本轮组装方式

从 `public.json` 获取全部公开任务字段，以相同规则在两个例子上构造任务上下文，配原始 `chart.jpeg`；使用本轮新统一 system prompt 和 schema。可以显式记为：

```json
{
  "task": "public.json 的完整对象",
  "state": {
    "view_mode": "static_chart_task_review",
    "current_selection": "",
    "options": "public.json 的 option_labels，保留原顺序"
  },
  "history": []
}
```

这是**静态全图解释生成诊断**，不是自然 before-submit checkpoint，也不是已执行过选择的浏览器状态。不要声称其与 pub001 的真实浏览器 checkpoint 完全同协议。

旧 `generation/input_context.json` 含 `decision_reference`，它来自另一轮旧 actor 的未执行提议：b002 为 Edge，pub013 为 Illinois。`state.current_selection` 实际都是空字符串，历史都是空数组。若本轮要重新生成初始链，建议统一不传旧 `decision_reference`，并在新输入 manifest 中明确记录删除的是旧提议，不是隐藏正确答案。不要将它搬到 `current_selection`。

原路径、SHA、task_id、provenance、旧 verdict / rule_state / supplement 均不属于本轮新初始生成的在线输入。公开别名 `task_002` / `task_114` 可以原样保存，但无需向模型传真实目录名。

## 2. 公开任务原文与选项

### b002

标题：`Browser Usage Leader Compatibility Testing Intake`

目标原文：

> Review the browser usage-share dashboard, then assign the browser with the highest current market_share to the priority compatibility-testing queue.

图表使用说明原文：

> Use the dashboard market_share values as the evidence source; priority compatibility testing is reserved for the highest-usage browser because it has the largest user impact.

主字段：`Priority compatibility-testing browser`。选项按原顺序：

1. `Assign Edge to the priority compatibility-testing queue`
2. `Assign Firefox to the priority compatibility-testing queue`
3. `Assign Chrome to the priority compatibility-testing queue`

公开表格说明选择最高 current market_share；另有三个必填单值 companion selects，当前均是 Select value，占位项 selected=true，唯一非占位业务值 selected=false。没有执行它们。`Submit Form` 是公开提交按钮文字，并不意味着此静态记录已准备提交。

### pub013

标题：`State Risk Priority Detail Routing`

目标原文：

> Review the state risk dashboard, then open the state risk record that should be routed into the highest-risk priority follow-up workflow.

图表使用说明原文：

> Use the state risk dashboard as the evidence source for selecting the highest-risk state record.

主字段：`Highest-risk state route`。选项按原顺序：

1. `Open Illinois (IL) risk detail for priority follow-up`
2. `Open Kansas (KS) risk detail for priority follow-up`
3. `Open Delaware (DE) risk detail for routine monitoring`

第三项确实写 routine monitoring，前两项写 priority follow-up。这是原公开选项差异，不是审计者添加的提示。不能擅自“统一”这几个动作语义，也不能把这个公开差异当隐藏 gold。

其他公开只读字段包括 Hazard risk surveillance / State / State risk priority follow-up / Highest risk state in the dashboard。注意任务文字的全图范围与可执行选项子集可能产生范围解释问题；保留原文，不在新提示中替模型裁定。

## 3. 请求、图像和来源核验

旧实际模型请求为 `gpt-5.6-terra`，temperature=0，max_tokens=4800。两个旧请求中的 system 相同，完整原文见 `generation/round_001/request.json` 的 `messages[0].content`；它要求最多三条 O–B–C，允许条件假设，具体 C 与独立核验分工。不要把这个旧模型/旧提示当本轮 Qwen 配置。

两个请求均包含：system；user 中 JSON 上下文文本；`Observation chart_1`；一个 data-URL 图像。

实际检查结果：

| 核验 | b002 | pub013 |
|---|---:|---:|
| `request.messages[1].content[0].text` 解析后等于 `generation/input_context.json` | 是 | 是 |
| 实际 request 图像 base64 解码 SHA 等于同 case `chart.jpeg` | 是 | 是 |
| 同 case JPEG 等于 runtime-aligned prepared JPEG | 是 | 是 |
| 保存的原 home/dashboard/form HTML 仍存在 | 三个均存在 | 三个均存在 |
| 用 `public_inputs.extract` 从这三份 HTML 重新投影等于现有 `public.json` | 是 | 是 |

SHA-256：

```text
b002 chart.jpeg
e238fe77c38267c837c5982bc5d151057143bf23447a63381a17caa289c99b8f
b002 public.json
cf434e1d766590f0026d107201fb1e531fe9d3699df6ec46580f39f1efb0e5a1
pub013 chart.jpeg
4b1cc94d4987ef584a729084f94fe52da6568d0eb234c4fe5109bc4c8ffc425b
pub013 public.json
ed1367612ec97b93a39e74a41ae01e392df0f4c8bd1531623f7061c353307325
```

原 HTML 所在目录：

```text
.aris/task_flows_20260924/local_http_checks_0b32g1rr/business47_official140/b002_{home,dashboard,form}.html
.aris/task_flows_20260924/local_http_checks_0b32g1rr/public39_official140/pub013_{home,dashboard,form}.html
```

公开投影器 `research/obc140_runtime_aligned_20260924/public_inputs.py` 排除 script、隐藏元素、hidden input、option backing tokens、source 属性、review/compare UI；投影结果只保留可见任务字段。重新提取检查是对现有 HTML 的纯读取，不启动服务、不访问远程。

该证据链证明当前输入与**已归档图像/HTML**一致。没有重新访问服务器上的原始数据文件，所以不宣称本次已经再次核实远端原文件的现时身份。

## 4. 最近真实 OBC 来源与边界

以下只描述旧模型输出，不充当人工确认或本轮模型应当给出的答案。原文路径统一是 `research/explanation_completion_v3_20260926/run_live_001/cases/{id}`。

| 项目 | b002 | pub013 |
|---|---|---|
| 初始链 | `initial_set.json`，2 条 | `initial_set.json`，1 条 |
| 已有结论 | Edge（标注百分比读取）；Firefox（柱高读取） | Illinois（所示图例读取） |
| 旧反问 | `questions/accepted.json`，1 个 | `questions/accepted.json`，1 个 |
| 旧补充 | `supplement/accepted.json`，0 新链，2 条已有链 refinement | `supplement/raw.json` 有候选，但结构检查失败，不能称 accepted |
| 旧最终状态 | completed，4 次请求，0 business actions | failed_stage_no_quality_retry，3 次请求，0 business actions |

pub013 明确失败原因：`SchemaError: response references missing supplement record`。不能把它展示为后续已执行核验/规则持久化成功。b002 原来已在初始生成中有两种不同结论；本轮若再次覆盖两种，不需要强迫反问再凑第三条，更不能只看新链条数评价补齐效果。

## 5. 明确风险和本轮记录要求

1. **旧选择锚定**：旧 `decision_reference` 不是公开截图中的已选状态。新初始生成统一移除并记录；不要复用旧解释作为新模型的初始链。
2. **静态多页权限**：该上下文汇聚三个公开页面，没有真实访问历史。它可以作为静态迁移诊断，不能冒充 Agent 自主完成任务或自然错误恢复。
3. **图像预处理差异**：原图 9.234M 像素，用户提供的 Qwen 服务上限 1,605,632 像素。即使发送原图 bytes 完全相同，服务端也会缩放；记录服务配置。旧 Terra 结果不适合直接用于新 Qwen 提示改善归因。
4. **不把图表提示当隐藏答案**：模型可以读取原图的所有可见文字；不要根据结果对图例、标注或视觉惯例规定无条件优先级。
5. **目录和 provenance 隔离**：只传公开 task/state 与图像，不传含 official140 / 误导类别等的本地路径、provenance 或报告。当前公开任务文本未发现显式机制标签或隐藏答案字段；这不等于已检查所有图像文字、也不证明无任何任务设计偏置。
6. **旧模型结果不是 gold**：以上初始 C 与补充仅用于来源追踪，不送入新初始生成，不以其作为正误判定标准。本审计未读取 gold。
7. **可复用不等于可以实际提交**：两例没有真实 checkpoint 和已执行 history；若要开展端到端任务试验，应单独用原 runner 重建且记录，不能利用静态 `Submit Form` 字段伪造 pending submit。

## 6. 执行证据概要

本地只读命令使用 `Get-Content -Encoding utf8` / `Get-FileHash` / `.NET SHA256` / `System.Drawing.Image` 分别读取 JSON、计算文件与请求图像哈希、读取尺寸。投影复核使用现有研究 venv 的 Python 加载公开投影器：

```text
D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe -B -c <读取两例 provenance.source_pages，调用 public_inputs.extract，与 public.json 对象比较>
```

输出：`[{"case":"b002","reextract_match":true},{"case":"pub013","reextract_match":true}]`。这只证明资产和公开字段投影链路，不能证明模型解释正确。
