# 下一步与审批入口

## 最新状态：2026-09-07 12:22 UTC，四条已真实运行

GPU0共享许可已明确适用于本对话后续进程。本轮四条均已尝试：b011两臂反复改选、8调用内未提出提交；env027两臂正确选择并由B0原样真实提交。24次真实模型调用/36浏览器动作，加既有mock后累计28/40调用事件、45/160动作。没有补跑或扩大实验，自己的Qwen服务已释放。

当前自然错误的提交前checkpoint为0；不以b011中途选错冒充提交前错误。49项回归与212项工件检查通过，但新fresh子Agent因额度错误未执行，独立审查ERROR/unavailable。此前未运行/资源阻塞说明与旧检查、旧mock审查均为历史，不覆盖当前结果；父目录before-live副本保留原预算/summary。

[真实运行报告](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/STAGE_REPORT.md) · [逐样本轨迹](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/CASE_REPORT.md) · [当前停止点](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/NEXT_ACTION.md) · [实际命令](runs/natural_prefix_20260907T0932Z/live_20260907T1202Z/COMMANDS.md)。不要重跑已存在live_attempt的四单元。以下原文保留为历史记录。


## 当前停止点：四条自然轨迹已授权，待安全可用资源

不要重复申请本轮4条模型实验许可：用户已经同意。新增natural_prefix入口和48项回归完成，mock浏览器实测通过；已用4/40调用事件（全为mock）、9/160动作，四条真实轨迹未运行。GPU0当前50569MiB且PID87116任务归属不可见，8045没有Qwen；需要等待资源释放，或由用户明确本轮与该任务的共享安排/可调用服务。

资源就绪可接着runs/natural_prefix_20260907T0932Z运行live，不重复prepare或browser-control，累计预算不清零。详细命令与限制见[本轮下一步](runs/natural_prefix_20260907T0932Z/NEXT_ACTION.md)。不启动其他候选、方法网格、pilot或新机制。下文为历史停止点。

## 当前停止点：2026-09-07 七候选网页资格已完成

此前建议的0模型/112浏览器动作检查已执行，实际0/98；不再等待网页渲染或提交验证。6条可进入明确标注身份的主路由候选池，b012条件保留。建议下一张单独执行单只采集少量自然Agent前缀，先开发b011/env027，再按原分组进入诊断；须明确使用release主路由safe-shell适配以及模型/图像缩放/预算，不冒称完整原portal。本轮没有启动这一步，也不使用剩余14次动作补跑。

[逐任务资格与split](runs/web_qualification_20260907T0801Z/QUALIFICATION_TABLE.md) · [详细下一步及边界](runs/web_qualification_20260907T0801Z/NEXT_ACTION.md)。下文均为历史轮次的停止点。

## 当前停止点：2026-09-07 冻结面板完成

已授权的24单元完成，25模型调用/140浏览器transition；不再等待共享许可。三条件全对且0自主裁剪，不能把简单控制成功说成复杂误导图表问题已解决。建议下一张单独执行单先做原7候选网页资格检查（0模型/最多112浏览器动作）；此次不执行，不动用当前余量，不启动pilot或新机制。详见[最新下一步](runs/frozen_panel_20260907T015908Z/live_20260907T0307Z/NEXT_ACTION.md)。下文为历史。


## 2026-09-07 已获24单元真实运行授权，等待安全可用的GPU0

交付前更新：另一clear_rule_probe实验已在8045启动同款Qwen；需明确本面板也允许共用GPU0，并与该服务串行协调。当前模型调用范围已授权，缺的不是再批24单元，而是资源共享安排。不可静默沿用另一轮文件里记载的共用许可。

全轮投影及真实提交连接已实现，离线测试/两项浏览器执行检查有工件，见 [本轮下一步](runs/frozen_panel_20260907T015908Z/NEXT_ACTION.md)。已用0模型调用/8浏览器transition，24行均未运行。GPU0被未知归属计算进程占用且8045未提供Qwen服务；不共用或终止该任务。待用户确认GPU0释放或提供可复用的授权专用服务后，继续同一冻结面板及累计80/200预算，无需再次授权同一调用范围。新任务、D0/D1/D2、pilot/全量/新机制仍未授权。

以下2026-09-06“未授权”表述是历史状态，不覆盖今天的新授权。

## 20260906T145758Z 离线交付后的下一步（当前）

真实基准保持stage2_live_smoke_20260906T1342Z，不再重复env001/env025完整grid。两组原始失败、B4等价比较更正、8状态×3条件的面板/提示/交错排程、新7条资产级资格及split均已交付，见 [DELIVERY.md](revisions/20260906T145758Z_offline_panel/DELIVERY.md)。本轮0推理/0GPU启动/0浏览器动作。

运行前先完成全轮模型输入投影（隐藏旧选择同时保留外层真实状态）、调用/动作前记账持久化、真实label→POST连接和确定性测试；不能把已生成首轮输入当作已实现live runner。面板v1已固定，不根据输出逐题改提示，不用reason/gold覆盖label。建议下一次明确授权24单元、最多80调用/200浏览器动作；当前未授权启动服务或新推理。

新7任务仅资产级合格（4formal+3legacy），实际shell渲染/提交资格还没验证，建议另列0模型/112浏览器动作检查，不塞进颜色控制预算。自然轨迹与D0/D1/D2之后再议，不启动pilot/140对或新机制。独立审查WARN及初稿排程修订均有原文记录。

## 最新停止点：20260906T1342Z，修复与16单元重跑结束

本轮已完成此前建议的B3格式/错误反馈/计数修复并执行新smoke；不要再次把“尚未修复/没有模型授权”当作当前状态。B3本轮4/4合法决定，但0自主crop、0自然改选；最终真实合成改选控制仍有reason与option_label矛盾。GPU0自启Qwen服务已释放。

下一步先解决可解释性混淆，而不是扩数据或开发新机制：

1. 先在单独获批的小控制范围内区分通用结构化行动一致性、初始选择锚定、颜色/规则映射问题。公开规则与标准答案独立于模型输出预先给定，保留本轮两次失败，不跨提示择优、不循环调同一小题至成功，不由Codex替模型决定正确选项。当前证据未把这些可能原因分离。
2. 补齐真正由模型自主请求观察的控制证据。本轮仅注入路径证明四图传输，不能把0自主crop解释为找不到证据或证明工具已经被充分使用。
3. env001缺公开数值阈值，应另建明确规则的开发变体或替换为本地已有无歧义任务，不覆盖原数据/gold。env025适合展示“选对但理由无支持”，但两arm自然都正确，不是已发生恢复的样本。

这些工作需要下一次明确的小范围运行预算；本轮到此停止，没有追加控制、pilot、完整140对或新观察选择机制。优先读 [本轮报告](revisions/20260906T1342Z/STAGE_REPORT.md) 中正控制失败与逐样本证据，再确定下一张执行单；不能直接从3/4终局分数跳到新方法立项。

## 最新停止点：20260906T1219Z 真实 smoke 后

模型资源问题已解决并实际运行：GPU 0上的已有 Qwen3-VL-8B 完成了16单元提交链路，服务在实验后释放。不要继续依据下方历史“无授权服务/真实未运行”申请同一件事。当前研究仍停在阶段二，不是 pilot 已就绪。

下一步应先处理 **B3 的执行阶段/核查阶段输出格式混淆**：四单元均没有解析器接受的决定、零成功 crop；无效输出却被记作裁剪分发失败。应保留原轨迹和历史权限，澄清当前阶段仅接受决策/观察，不执行浏览器提交；区分格式错误、合法观察请求与成功观察的计数，并用通用小控制验证，不加样本答案或机制提示。不在此轮修改在线实现后偷偷补跑，也不把失败回退解释为视觉观察选择不够好。

建议下一次授权范围先是通用 B3 接口修正及合成视觉小控制（维持最多3核查调用/2观察），覆盖直接合法决策、合法crop后累计多图、非法action/嵌套decision的拒绝与明确反馈；完整2×2×4重跑另行说明预算。严格执行已批准调用/动作/单元上限，旧run保留。当前尚未实施这些修改或启动新运行。

研究样本方面：env001 缺明确“足够大”的阈值，仍只用于工程；不覆盖原始gold。env025 的自然选择均正确，核查理由存在参考线关系/平均口径问题，不能拿正确终局代替有效纠错证据。先解决接口及样本可核验性，才审批阶段三 B1/B5 与开发/留出任务，不开发新观察选择机制。

最新详情：[真实 smoke 报告](revisions/20260906T1219Z/STAGE_REPORT.md)。以下正文为历史保留；“当前/最近/没有授权”等均以本节为准。

## 当前停止点（20260906T0830Z 增量轮）

阶段一、二的接口修复、单元/浏览器控制和唯一16单元 mock grid 已完成。**本次真实模型结果为未运行**：旧 8045 本地服务已不在运行。本次没有自行启动服务。以下旧正文保留供历史追踪，其中“最近动作”“无授权”等时间性陈述不代表本次开始时的状态。

独立审查保持 WARN：当前工程链路有证据，但泛化页面的 selected-option 可见性、完整日志隐藏值扫描、validator 的全部 replay/response 一致性仍有限。修订后 B3 历史/反馈逻辑已通过单元测试，不与修改前的16单元 smoke 混同。下一轮不得把这些工程限制或 env001 的规则歧义当作视觉观察选择的新研究瓶颈。

最近需要的外部条件是：由用户/服务所有者提供或确认一个已经运行、明确获授权的本地视觉模型服务，然后才在新授权下进行真实阶段二 smoke。不能仅凭 localhost 或 /health ok 推断服务所有权；本次不得自动再跑16单元。

下一次真实 smoke 的现有可运行入口（只示例，不执行）：

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers \\
LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu \\
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \\
  -m research.decision_evidence_audit.runner --mode live-local \\
  --local-model-url http://127.0.0.1:8045 --local-model-name qwen3_vl \\
  --tasks env001,env025 --max-model-calls 160 --max-browser-transitions 800 \\
  --max-output-tokens 1024 --temperature 0 --top-p 1 --seed 12345
```

8045 只是已知历史端口，不保证恢复；必须先确认实际端点与模型、授权和健康信息。该命令不启动/下载模型，会先进行一笔计入预算的双图传输检查。真实运行后优先确认 env025 的 label/name 问题是否仍出现，不能先作视觉能力结论。env001 目标阈值仍不明确，仅用于工程开发。

阶段三仍只保留执行单的计划：约4开发+8诊断留出，最多144配置单元（不是144独立任务），B1/B5尚未适配，当前 split 无已分配 holdout，**不存在可直接运行的完整 pilot 入口**。需先复核在线可判定规则、分组近重复和 B5 身份，给出预估最多1500模型调用/6000浏览器动作再请用户审批。本轮未为凑入口扩充 runner；现有 CLI 明确拒绝超过2任务或非开发任务。

只有强简单对照在独立、可核验样本上留下明确且非接口造成的残余失败，才考虑决策相关视觉观察选择；不转回前提账本、长程回滚或大型多Agent。当前证据不足以作出该决定。

---

跨服务器续跑仍应先读取同目录的 `REMOTE_GPU_HANDOFF.md` 以了解安全边界；其中“尚未运行真实模型”的状态已经由本文件和 `STAGE_REPORT.md` 的 2026-09-06 live-local 结果取代。

## 当前停止点

阶段一与阶段二到此停止。获批的 16-unit live-local smoke 已执行并保留完整失败分母：16 个 unit 均有终局工件，只有 env001 两个 condition 到达 checkpoint，因此 8/16 完成 replay→submit 链路，env025 的 8 个 unit 为 `not_run_no_checkpoint`。本轮自启模型服务已关闭，GPU 0 和端口 8045 已释放。阶段三 pilot、140-pair 评测和阶段四候选机制均未启动。

当前 live 工件：`runs/stage2_live_smoke_20260906T073005Z/`。普通失败保留 validator 为 `valid=true`；严格完整提交 validator 为 `valid=false`，只因为两个 env025 前缀无 clean checkpoint、对应 8 units 未提交。实际消耗为 41/160 model calls、95/800 browser transitions、56,507 tokens、44 image inputs。

尚不能回答：

- 普通重读 B2 是否已经足够；
- 通用主动视觉核验 B3 是否已经足够；
- B4 自提取是否更稳；
- 是否存在值得开发“决策相关视觉观察选择”的残余问题。

本轮只有一个 base task 到达 checkpoint，不提供研究结论。即使以后进入 stage-three，也必须先排除已发现的执行/tool-schema 映射问题，不能把执行失败误归因于视觉观察选择。

## 最近的可审批动作：通用接口修正后重做 stage-two chain smoke

当前没有剩余的运行单元授权。最近的安全动作不是 stage-three，而是：

1. 把 `select_option.select_name` 的公开语义做成唯一且通用的接口：要么明确要求返回 DOM state 中的 exact `name`，要么让 executor 在无歧义时同时解析公开 `name` 和公开 label。不得写 env025 专用规则、答案提示或基于该任务改视觉判断 prompt。
2. 用 synthetic select 的 deterministic/browser controls 覆盖“name 正常、label 正常、歧义 label 拒绝、错误 option 不被纠正”等情形；不增加新的长期 gate。
3. 只有用户另行批准 fresh units 和 hard ceilings 后，才用新的 run ID 重做相同 2×2×4 live-local chain smoke。旧 16 units 不覆盖、不删、不挑选性补跑。
4. 重跑前重新核验 GPU 0 所有权/空闲、loopback port、权重/环境、browser witness、模型 `/health`，并将双图 witness 计入同一 model-call ceiling。服务必须在结束后关闭。

建议的下一次 stage-two 命令仍由当前 runner 生成，但在接口修正、测试和新预算批准前不在这里给出可误启动的完整命令。AIME 继续禁用，只走用户另行批准的本地模型。

## 阶段三前置实现/核验

未来若用户明确批准 pilot，仍按以下顺序增量完成，不重构成大型框架；当前不得执行：

1. 先完成上面的通用 select-target 修正，并在新的授权下取得完整 16-unit live-local chain smoke；若仍不完整，继续停在阶段二。
2. 固定获授权 backbone、版本、解码参数和图像计量。本轮可复用的参考配置是 Qwen3-VL-8B-Instruct、temperature 0、top-p 1、seed 12345，但未来仍须重新审批和记录。
3. 实现 B1 普通反思，输入只含相同 checkpoint/history，不加入图表错误 taxonomy。
4. 审核本地 GUI target-level recovery 来源并实现 B5；若不能完整复现，名称必须是 `inspired adapter`，保留其目标验证能力，不偷加候选机制。
5. 让 B1–B5 复用同一 executor、safe shell、label ordering、multi-image/crop 工具与记录格式；为 B5 增加执行错误、目标错误和正确完成控制。
6. 把当前 deterministic 的 post-commit close/confirmation/duplicate-receipt 控制扩展成 Playwright 注入；阶段二已覆盖 prefix backend failure、选择 no-op retry、不可逆 submit 单次尝试、browser launch/shell health failure 和 partial-run validator。
7. 用 learned-model crop 小控制补齐累计 3/4 图路径；本轮真实双图 witness 已通过，但 B3 没有实际请求 crop。
8. 生成并人工审核阶段三 split；不要把下面的未 materialize 计划误称冻结数据集。

当前 `manifests/split_manifest.json` 只有 env001/env025 两个 development pair，diagnostic/formal holdout 为空。

## 阶段三抽样计划（待审批后 materialize）

目标约 12 个 base tasks：4 development + 8 首次 diagnostic holdout，另保留未读 formal group。

- env001/env025 可留在 development；再选约 2 个 development 和 8 个 diagnostic。
- 仅从重新核验 online evidence 与 pair invariant 的任务选取，不按哪个方法容易赢筛选。
- 同源图、近重复、同模板/只换实体或按钮文字的变体必须同组。
- 覆盖实际可用的 annotation、geometry/proportion、scale/direction，以及可合格的 legend/encoding 类；本地 strict94 没有 dual-axis，dual-encoding `env032` 有 `gt_uncertain`，不得为了凑类别隐瞒。
- 所有 cherry-picking pair 都在已知非 chart-only 的 26 对中；若要研究该类，必须先重新定义/版本化任务，不能混入严格配对 pilot。
- 一旦读取 diagnostic 输出并据此改方法，该组不再称 unseen。

阶段三比较：每个 task-condition 保存一个自然前缀，在首次 submit checkpoint 比较 B0–B5：

```text
12 base × 2 chart conditions × 6 configs = 144 config units
```

这不是 144 个独立任务。当前 runner 硬限制最多两个 environment task 且只有 B0/B2/B3/B4；**不存在可冒充 stage-three pilot 的命令**。在 B1/B5、approved split 和模型授权齐备后，才增量扩展实际 runner，并把最终命令写回本文件供用户批准。

## 阶段三预算估算

按执行单上限估算：

| 部分 | Model calls 上限 | Browser transitions 上限 |
|---|---:|---:|
| 24 个 task-condition 自然前缀 | 24×12 = 288 | 24×20 = 480 |
| 5 个有核查策略（B1–B5） | 24×5×3 = 360 | crop 若不导航不计 transition；导航照实计 |
| 144 units 后续修改/提交 | 144×4 = 576 | 144×8 = 1152 |
| 物理 replay 保守项 | — | 144×20 = 2880 |
| 计划合计 | 约 1224 | 约 4512 |
| 建议 hard ceiling（含异常余量） | 1500 | 6000 |

该表只是未获批的 stage-three 上限草案，不是运行许可。本轮 stage-two 本地 Qwen smoke 的实测为 41 calls、56,507 tokens、44 image inputs；本地执行没有外部 API 费用，但 GPU 机会成本未折算。任何未来运行仍须提交固定配置、fresh unit ceiling、调用/transition 上限和费用估算再次审批；更强模型的小面板另行批准。

## 阶段四入口条件

本轮不写候选机制代码。只有阶段三出现以下证据才进入最小原型：

1. 在相同在线可见证据、相同 backbone 和相同 B3 工具下，多个独立任务仍失败；
2. 残余失败跨至少两类非标题视觉问题；
3. 已排除分辨率、crop、prompt/interface、option mapping 和执行失败；
4. 给定正确局部图表判断的诊断表明主要瓶颈确实在“选哪处证据看”，而非后续规则/执行。

若满足，候选仅实现一次可审计的“候选解释 → 动作分歧 → 最多 2 次观察”选择规则，并与完整 B3 及去掉动作分歧选择的消融比较。候选不能读取 mechanism、另一 arm、gold、raw data 或 evaluator bbox。

若 B2/B3 已解决绝大多数问题、候选不优于 B3、损害正确状态，或收益仅来自额外信息/更强模型，则停止该方向，不靠继续加模块保住假设。

## 仍需项目所有者处理

- 决定是否授权“通用 select-target 接口修正 + 新的 stage-two 16-unit chain smoke”；当前批准已消费完，不自动沿用。
- 若批准重跑，再明确 GPU/服务启动授权和 fresh calls/transitions ceiling；当前服务已关闭。
- 轮换 `.claude/settings.json` 中的明文 AIME 凭据，将其迁出仓库型配置并收紧权限；不要把值发回本对话。
- 决定 open release 的许可证和第三方资产权限；当前 manifest 明确仍待确认。
- 只有 stage-two 完整链路通过且另行审批后，才 materialize 阶段三 split、B1/B5 和 pilot 命令。
