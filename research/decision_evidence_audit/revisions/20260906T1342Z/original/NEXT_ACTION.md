# 下一步与审批入口

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
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \\
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
