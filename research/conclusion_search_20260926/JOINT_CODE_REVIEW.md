# 最后四例联合发现：执行前对抗代码审查

审查范围：`run_joint.py`、`JOINT_ADDENDUM.md`、`test_joint.py`，以及其复用的 `run_isolated.py`、冻结 `LocalAPI`/ledger、schema、COMMON 提示。仅本地离线检查；未调用模型、SSH、浏览器或 ARIS。

## 执行前结论

本版是**候选生成诊断**，不是核验或真实纠错实验。固定四例和预算边界符合缩小后的方案；首轮发现的最终静态图片来源断言缺失已修复并独立核实，**当前无执行阻塞**。下文列出的科学解释限制不需要通过增加调用来解决。

### 必须补齐：校验最终实际发送的静态图片

`case_inputs()` 静态分支调用 `validate_derived_context(transfer_inputs, run_transfer_001)`，但返回的实际图片位于 `run_isolated_001/<case>/chart.png`。前者只校验准备工件与旧 transfer 图，不证明最终发送的后一文件相同。请在所有模型调用前明确比较这两个最终/来源图片的 SHA256；不修改任何旧图或 manifest。

同时建议核对本轮复用 `shared_initial.json` 与父工件记录的来源 SHA/初始内容，以便“同初始链”不仅是记录当前哈希。此建议不意味着重新生成初始链。

### 修复闭合复核

主持者已在 `case_inputs()` 添加最终静态图与 `run_transfer_001` 图的 SHA256 等值断言，以及每例 `shared_initial.json` 与父 `reuse_provenance.initial_sha256` 的等值断言。审查者下载后独立执行全部四例 `case_inputs()`，均通过；初始链数依次为 2/2/1/2。

审查者现已读取完整父工件账本：`request_attempts=85`、`browser_operations=78`、无 `blocked_reason`。八次最坏请求余额足够；本次最多达到 93 次尝试，不需要调用额外服务。至此来源断言和预算检查闭合。

## 已确认的边界

- 固定顺序为 `official140`、`clean140`、`b002`、`pub013`，不由输出决定是否增加或删除后续案例。
- 每例仅一次 `api.call()`，没有语义/质量重试。冻结 `service_attempts_per_call=2`，因此四例最多八次请求尝试。只有既有暂态 HTTP 状态可重试一次，未知网络结果全局停止。
- 父 `run_isolated_001` 必须完成且账本未 blocked；`inherited.request_attempts + 8 <= 100` 在 API 构造和任何推理之前检查。父完整账本继承，不以新目录重置。父累计 85/78 已在修复闭合时独立读取核实。
- 在线模型端点保持已授权 localhost Qwen，配置与父版本对齐；历史代码哈希冻结，新目录与排他锁禁止覆盖/重复启动。
- 唯一在线阶段为 `hypothesis` 名义下的联合候选生成。源码没有调用 `verify`、`Actor`、`BrowserSession` 或正常动作执行器；没有新增浏览器操作。
- 在线内容为目标、去执行承诺的公开状态、完整公开选项、旧候选的去重行动标签、同一完整图。没有旧 O/B/claim、历史动作、pending proposal、gold 或另一 arm 内容。已有结论标签会重新带来候选锚定，不能称完全去锚定。
- 通用提示允许零条、不指定所需答案、不包含本例颜色/图例方向/“priority 就是最大”等额外业务规则。联合发现与旧逐选项/先问后补充流程有多项变化，不进行单因素归因。
- 返回结构最大两链，普通校验只检查字段/合法选项/ID；不会把结构通过或非空数组自动记成语义正确。旧链完整保留，新链只重命名 ID，差异标签仅为行动新颖性记录。
- 工件明确写 `verification_status=not_run_candidate_only_diagnostic`、`submitted=false`。结果必须沿用此含义，不将 `accepted.json` 或 `completed_static_only` 翻译成“核验通过/纠正成功”。

## 独立离线执行

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& 'D:\anaconda\python.exe' -m pytest 'D:\ths_Viswork\research\conclusion_search_20260926\test_joint.py' -q
```

结果：**2 passed**。另用内存 mock 将继承请求数设为 93，调用 `main()`：在需要八次余额的检查处抛出预期异常，`LocalAPI` 构造器断言未调用；未创建实验输出或执行网络调用。

## 报告必须保留的限制

四例均为既有开发案例；pub001 两图来自同一基础任务。输出两种行动不等于两条有依据的竞争链，空数组也不证明图上不存在其他解释。Codex 离线语义审阅不是用户人工确认或独立模型核验。本版不估计提交成功率，也不改变 V5 的已知归因：该轮纠正发生于全图核验重读，彼时没有交付新的结构化链。

固定四次候选生成完成或发生全局停止后，本轮模型调用结束；不用余量追加方案。

## 后续真实资产审查更正

快速执行前审查遗漏了 `joint_context()` 对静态 pub013 应用递归 `value` 删除的范围问题。实际运行启动后发现：它连 readonly 的四项公开业务值一起删除，虽然最高风险任务仍在 goal/chart_reference 等重复文字中保留。已及时反馈、未补跑，也没有改写实际请求。详情和逐字段清单见 `FINAL_SEMANTIC_REVIEW.md`。因此上文“公开文字保持”对该最终静态请求并不完全成立；此次来源哈希校验通过不能替代输入投影语义检查。
