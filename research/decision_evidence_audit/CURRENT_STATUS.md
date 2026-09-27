# Stage 2.5 当前状态

> 2026-09-07 增量：三个明确规则任务的真实检查已执行。6 条自然前缀中 3 条正确到达提交前、3 条反复改选未提出提交；24 个计划分支中 12 条实际提交且保持正确。没有错误 checkpoint，不能评价纠错效果。61 次真实模型调用；含工程重跑和正控制共 490 次浏览器 transition。GPU 0 共用许可已获用户明确授权，本轮服务已关闭。最新报告：[明确规则样本报告](revisions/20260907T0157Z_clear_rule_probe/STAGE_REPORT.md)，[逐题离线展示](revisions/20260907T0157Z_clear_rule_probe/live_case_view/CASE_VIEWER.html)。下文保留前一阶段历史状态。

状态日期：2026-09-06（Asia/Shanghai）  
执行依据：`Codex_Stage2_5_Review_and_Live_Check.md`

## 结论

Stage 2.5 的离线审查、候选任务资格检查、完整性代码修复、scripted-mock 回归和当前源码对应的 fresh `2 tasks × 2 chart conditions × 4 configurations = 16 units` 真实模型检查均已完成。用户明确授权在 GPU 0 启动本地已有 Qwen3-VL-8B；没有下载权重、调用付费 API 或占用其他 GPU。服务在运行后关闭，GPU 0 已释放。

新 run `stage25_live_smoke_20260906T1515Z` 取得 4/4 checkpoint、16/16 replay/POST/receipt/confirmation、33/33 请求响应配对和严格 validator 零错误零警告。按数据集 scorer，原始 checkpoint 为 1 个错、3 个对；三种核查在唯一错误项上均未改选，在三个正确项上共 9/9 保持正确。通用主动视觉核验 4/4 输出合法决定，但 0 次自主 crop。

单列的真实 backend 开发控制也只运行一次：注入两次 observe 后 2/2 crop 成功，最终真实调用收到 4 张累计图并正确输出 Route B；但自然改选控制的 reason 说应选 Route B、顶层 `option_label` 却仍为 Route A，因此套件 2/3 通过、exit 1，未重试。该控制证明 crop/累计多图传输链可执行，不是自主观察或 benchmark recovery 证据。

唯一错误项 `env001/official140` 的公开规则没有“large enough”的阈值，已预先归为 `engineering_only`；合格的 `env025` 两个 checkpoint 原本都正确。因此当前仍没有无歧义错误 checkpoint 可估计 recovery，既不能声称简单核查已经解决问题，也不能声称其失败证明必须开发新的观察选择机制。详细逐单元报告见 `revisions/20260906T1515Z/STAGE_REPORT.md`。

## 运行工件清单

| Run | 实际运行时版本/模型 | 开始—结束（UTC） | 单元与预算 | 结果身份 | 现时解释 |
|---|---|---|---|---|---|
| `stage2_live_smoke_20260906T073005Z` | 早期适配器；Qwen3-VL-8B-Instruct | 07:41:41—07:46:40 | 16 planned；41 calls；95 transitions | 2/4 checkpoint，8/16 完整提交；7 success、1 misleading failure、8 no checkpoint | 历史不完整链 smoke；env025 的 select 字段解析失败，不能比较策略 |
| `stage2_mock_smoke_20260906T0837Z` | 后续适配器；scripted visible-state mock | 08:36:02—08:36:51 | 16 units；36 mock calls；96 transitions | 4/4 checkpoint，16/16 submit；8 success、8 misleading failure | 工程回归；mock 分数无视觉推理含义 |
| `stage2_live_smoke_20260906T1219Z` | select 修复后的适配器；Qwen3-VL-8B-Instruct | 12:22:33—12:24:23 | 16 units；41 real calls；96 transitions | 4/4 checkpoint，16/16 submit；12 success、4 misleading failure | 完整提交链成立；B3 0/4 合法决定、0 crop，属于接口失败，不能解释主动视觉能力 |
| `stage2_live_smoke_20260906T1342Z` | B3 格式/计数修复后；Qwen3-VL-8B-Instruct | 13:57:25—13:59:10 | 16 units；33 real calls；96 transitions；另有 6 次真实合成控制 | 4/4 checkpoint，16/16 submit；12 success、4 misleading failure；B3 4/4 合法决定、0 crop、0 revision | 此前真实模型工程证据；两个真实控制各留有一次失败，不能作方法有效性比较 |
| `stage25_mock_integrity_20260906T145414Z` | 当前 integrity-v2 代码；scripted visible-state mock | 14:54:30—14:55:20 | 16 units；36 mock calls；96 transitions | 4/4 checkpoint，16/16 submit；16/16 状态和截图从文件重算一致；36/36 请求响应配对 | 本轮新增工程完整性回归；不是真实模型结果 |
| `stage25_live_smoke_20260906T1515Z` | 当前 integrity-v2 代码；Qwen3-VL-8B-Instruct | 15:12:13—15:14:07 | 16 units；33 real calls；96 transitions | 4/4 checkpoint，16/16 submit；12 success、4 misleading failure；B3 4/4 合法决定、0 crop、0 revision | 当前权威真实链路证据；1 个 scorer 错误 checkpoint 仅属 engineering-only，研究合格错误为 0 |

上述旧 run 均未改写。四个历史 run 的新只读验证结果保存在 `revisions/20260906T144628Z/offline_audit/historical_integrity_recompute.json`。

## 历史工件能验证什么

新 validator 对四个旧 run 的实际文件进行只读重算：

- 41/36/41/33 个 benchmark 模型请求均找到同 ID 的响应；成功或显式失败状态完整，四个 run 都没有缺失响应。
- 已存在的恢复截图分别有 8/16/16/16 个，可从原始 checkpoint 截图与 restored screenshot 文件重新计算 SHA-256；结果与历史 `screenshot_equal` 一致。
- 旧 replay 只保存了 `restored_state_digest` 和布尔值，没有保存 `restored_state` 本体。因此 restored-state equality 无法从独立文件重算，不能事后补证。
- 旧预算文件只证明终局账本与请求/动作数量一致，不能证明账本从 run 开始持续落盘。
- 旧 source fingerprint 与当前源码不同是正常的历史版本差异；它们没有运行起始配置文件和完整 runtime source snapshot。

这些限制不把旧 run 判为伪造或无效；它们限定了能够从旧工件提出的完整性主张。

## 当前代码的完整性闭环

本轮没有改变 B0、B2、B3、B4 的决策逻辑。修改集中在：

- `BudgetLedger` 在 run 目录创建后立即写入空账本，并在每次模型调用或浏览器 transition 计费后原子更新。新 mock 最终为 132 个事件、133 次快照写入。
- `evaluator/run_start.json` 在浏览器 episode 前保存完整运行配置、配置摘要和起始源码/任务/图表依赖清单。
- `evaluator/runtime_source_snapshot/` 保存实际指纹覆盖的源码、测试、manifest、两份 task spec 和所选图表；live 模式还会包含本地 client/server 源码。
- 每个 prefix、每个 unit 前后及 finalization 检查 runtime source identity。发现变化会停止后续执行、保留未完成单元和错误，而不会把修复前后结果拼接成一个 run。
- replay 新增 persisted `restored_state`；validator 从 checkpoint、restored state 和两张截图文件重算状态/图像相等性。
- validator 逐一核对 request 文件名、request ID、response ID、成功文本或显式失败记录，并与 session budget ledger 的 request IDs 对齐。

当前 mock 的起始源码树摘要为 `40e6e55534f4f947ad67322894f0c6a4da5df60eb9836714a441324f7b9bcc2b`，配置摘要为 `9935863fd63958c89fa155501fe0e561132c28e3c36b7899a438c930a7799fde`；23/23 runtime snapshot 文件匹配。随后真实 run 的源码树摘要为 `2b9a80eec6be0927635ec04cdc47f82a4fb5aae071f2c696ec8da22054e5595c`，配置摘要为 `e7e7580c4f3b2b132c3fd1207c1f5f46a9121c6746cf78653d2d7f4671b3a695`，25/25 runtime snapshot 文件匹配且运行中未变化。摘要只用于标识具体运行，不是新增项目级冻结制度。

## 数据与任务资格现状

本轮重新验证的本地 release 为 `benchmark_v2_open`，版本 `2026-07-07`，状态 `open_release_candidate`：140 official + 140 clean + 40 real-world，320 task instances、180 case、797 资产，缺失资产 0。

对 140 对 task rows 的 14 个任务/动作/评分字段复核得到：

- 114 对在所审非图表字段上相同，可进入 chart-only 候选池。
- 26 对不相同：其中 22 对同时改变可见目标/选项及评分映射，4 对改变可见选项措辞；没有发现“只有 action ID 改名”或“只有无关元数据改变”的差异对。
- 具体 26 对为 `b017`–`b034`、`health006`–`health013`；不得把它们当强配对样本。
- 当前公开 label 字典序排序后，114 个正确选项位置为第 1/2/3 位 = 22/60/32。它消除了原始 gold-first，但分布不平衡；正式 pilot 前应采用与 gold 无关的固定外部 seed 排列，本轮未实现。

候选资格表为 `TASK_ELIGIBILITY.csv`。它覆盖当前 2 个开发任务和 12 个未依据模型输出选择的新候选；28 张实际 dashboard render 及几何记录在 `revisions/20260906T144628Z/candidate_renders/`。13 项达到 `eligible_primary_decision_probe`，`env001` 仅为 `engineering_only`。这些 13 项分属明显的近重复族，不能直接当作 13 个独立现象。

论文/正式结果版本对应关系仍为 `pending`：release manifest 可追踪到 `official_benchmark_v1` 和 `clean_benchmark_v1`，论文材料的主结果又指向 2026-05-23 的 merged result 目录；当前没有不可歧义的记录证明 2026-07-07 release task rows 与当时实际运行 rows 字节或字段完全相同。因此不能推断 26 对差异全部影响已报告论文结果。

## 在线信息和提交边界

当前 safe shell 保持白名单在线投影：目标、标题、图表说明、字段标签、可见 option labels、可见 DOM、URL path 和实际观察图像。action ID、gold、role/score、机制、另一 arm、pair/condition、CSV/HTML 和 evaluator 结果保持离线。

before-submit hook 在模型第一次提出可见业务提交动作、但 executor 尚未执行时触发；所有条件和当前选择统一触发。恢复使用 fresh page 加真实前缀重放。最终动作由共同 executor 执行，真实本地 HTTP POST 写 server receipt 并进入 confirmation；`finish` 不等于 POST。这里仍是 neutral diagnostic safe shell，不是原 benchmark 网页或完整 GUI Agent runtime 的等价复现。

## 本轮测试和执行命令

主要命令：

```bash
python web_agent_benchmark/benchmark_v2_open/scripts/validate_release.py

/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.stage25_offline_audit \
  --output research/decision_evidence_audit/revisions/20260906T144628Z/offline_audit

PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers \
LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu \
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.stage25_render_audit \
  --output research/decision_evidence_audit/revisions/20260906T144628Z/candidate_renders \
  --browser-executable /tmp/decision_evidence_pw_browsers/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell

/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m unittest discover -s research/decision_evidence_audit/tests -v

RUN_DECISION_EVIDENCE_BROWSER_TEST=1 \
PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers \
LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu \
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m unittest research.decision_evidence_audit.tests.test_browser_integration -v
```

结果：release validator 通过；41 tests discovered，38 passed、3 opt-in browser tests skipped；随后 3/3 browser tests 单独通过。当前 integrity-v2 mock strict validator 为 `valid=true, errors=[], warnings=[]`。测试通过只证明覆盖的工程链路，不证明研究假设。

## 本轮实际预算

| 部分 | 真实模型调用 | mock/脚本调用 | 浏览器导航或 transition |
|---|---:|---:|---:|
| 新的真实 16-unit grid | 33/160 | 0 | 96/800 |
| 真实 backend crop/累计多图控制 | 3 次 Qwen HTTP completion；5 个计费调用事件 | 2 个注入 observe | 0 |
| integrity-v2 16-unit mock | 0 | 36 | 96 |
| 候选 dashboard render | 0 | 0 | 28 个只读 dashboard 导航 |
| 单元/浏览器控制 | 0 | 测试内注入 | 3 项浏览器控制通过 |

真实 grid 记录 42,773 prompt tokens、2,087 completion tokens、38 个图像输入；控制的 3 次真实调用另有 3,727/122 tokens 和 8 个图像输入。合并为 38/160 个计费调用事件、36 次真实 HTTP completion、96/800 transitions、48,709 tokens、46 个真实图像输入；0 次失败重试。运行后模型服务已关闭，GPU 0 从加载时 17,291 MiB 回到 3 MiB。

本轮没有启动阶段三 pilot、140 对评测、B1/B5 适配或新观察选择机制；执行单要求的单次 true-backend control 已完成且未重试。
