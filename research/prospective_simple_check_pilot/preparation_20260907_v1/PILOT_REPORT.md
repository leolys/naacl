# 准备阶段交付：真实面板未运行

2026-09-07，`prospective_h_base_v1`。

## 当前结果

已完成新基础协议、8 个任务的预选 manifest、API 后端和共享前缀/选择/提交适配代码，并执行单元及真实浏览器的非图表 mock 检查。**没有启动 Qwen、没有 API 生成调用，没有新真实图表能力结果。旧六状态不补跑。**

计划为 8 基础任务×2 图表条件×2 模型＝32 个各自自然生成的前缀，最多 96 条 B0/B2/B3 配置记录。[CASE_TABLE.csv](CASE_TABLE.csv) 的 96 行全是 `not_run_awaiting_authorization`，不是 96 个失败，也不是 96 条已执行策略轨迹。错误 checkpoint/恢复指标本轮未观测，不能报 0% 或 100%。

## 预选数据与限定

固定顺序：b010、b046、health001、env035、health005、pub013、b014、env005。8 对原任务/动作/评分字段一致，16 张原图已逐对查看；原图、原任务、原 scorer 均未更改。依据资格/覆盖选择，未调用新模型或用旧模型表现来筛选本组。

64 个旧 recovery run manifests、旧计划/资格表及今天网页诊断共同形成 52 例保守排除集合，含已用原图来源的换名衍生。新组包含尺度方向、尺度范围、面积函数、比例冲突与平均注释；只有 1 个注释主导任务。

这不是 8 个全新模板：记录为 8 原来源标识、7 工作流模板组，5 个任务与旧开发模板仍有重叠，不支持模板外泛化。health001/health005/env035 的原 `image_only_draft` 原样保留，只支持这次带限定的主决策筛查。存在原图证据冲突、clean 制图文字线索和中间点重构差异；详见 [PILOT_PROTOCOL.md](PILOT_PROTOCOL.md) 与 [TASK_MANIFEST.json](TASK_MANIFEST.json)。

## 实际测试

| 检查 | 实际结果 | 能证明的范围 |
|---|---|---|
| 新单元 15 项 | 全部通过 | 默认拒绝未授权 API；图像字节/顺序；路由不符；截断；预算；信息隔离；四步历史；manifest |
| 新单元＋既有核心回归 | 53 项通过，11.311 秒 | 原 hook、执行器重试、B2/B3观察上限、原隔离/评分回归仍通过 |
| 本地浏览器第一次 | 进入任务前停滞，0 mock calls/0 transition；最终停止自己的进程，工件保留 | 启动失败/停滞，不是模型或任务失败；原因未确定 |
| 本地 CPU 浏览器第二次 | 4 流程＋5 分支工程场景全部通过 | 真实 POST/confirmation、状态像素恢复、三层记录、普通 actor 后续提交控制 |

第二次浏览器：20 次 scripted mock 调用，56 次实际浏览器 transition，8 次服务端提交回执；API HTTP 生成调用 0，真实模型调用 0，GPU 启动/推理 0。第一、二次浏览器账合计仍是 20 mock/56 transition。单元测试中的纯假对象/伪传输调用另计为软件测试，不是模型或浏览器工作负载。

四个公开 Route 控制：A 已选→A 提交（1 actor call），B 已选而目标 A→改 A 后提交（2），A 已选而目标 B→改 B 后提交（2），B 已选→B 提交（1）。这是脚本 mock 确认链路，不证明真实模型理解流程。

五个分支工程场景共享一个非图表脚本状态，**不是 benchmark 注入错误实验**：

| 场景 | 核验推荐 | 执行器落实 | actor 最终真实提交 | 工程结论 |
|---|---|---|---|---|
| B0 | 无核验 | Route B | Route B | 执行原真实 mock 提议，没有偷换成固定正确提交 |
| B2 后 actor 覆盖 | Route A | Route A | Route B | 三层分开，actor 可覆盖；不能只看推荐宣布恢复 |
| B3 零 crop | Route A | Route A | Route A | 零 crop 是合法分支 |
| B3 一次 crop | Route A | Route A | Route A | 原观察工具可接通，不证明视觉价值 |
| B2 最后只改选 | Route A | Route A | 无提交 | 调用用完后不自动补交 |

证据：[unit_test.log](unit_test.log)、[mock_browser_02/result.json](mock_browser_02/result.json)、各分支 `replay.json`、`handoff.json`、请求/响应、timeline 和服务端 receipt。

## 代码改动与完成程度

所有新增实验代码位于 `research/prospective_simple_check_pilot/`，原 runner/policies/safe_shell 未改：

- `prepare.py`：离线资格/来源排除、32 单元交错顺序、96 行未运行表、无授权模型配置。
- `h_base.py`：通用条件式完成说明、四步真实历史、B2独立输入/B3有限历史、最终推荐语义、真实选择 handoff。
- `api_backend.py`：显式配置的有序多图 chat-completions 后端，独立模型身份三层记录、无重试/无回退、脱敏、截断和保守费用账。
- `harness.py`：真实 pending 提议捕获、像素状态恢复、B0原样提交、B2/B3取消原提议→普通 actor 续跑、三层输出。
- `test_preparation.py`、`mock_browser.py`：本轮单元及非图表工程测试。

这是完成“协议、manifest、API 后端准备”，**不是已验证真实 API 可用，也不是已完成生产面板执行器资格**。未来准确端点可能要求不同 output/reasoning 字段，需授权控制确认。跨模型生产调度、总预算协调及双成本/评分汇总 live CLI 尚未接线；当前不提供一个会悄悄只跑 Qwen 的入口。

采用 `experiment-plan` 将执行单的问题、反例解释、顺序和预算落实为协议与表格；没有按该 skill 的通用模板扩展论文主张或新方法实验。

## 剩余阻塞与下一步

1. 强多模态 API 的准确模型 ID、项目所有者确认的旗舰身份、该模型在具体 endpoint 的使用权限和可接受路由；历史网关曾把请求转至 Luna，不能用 HTTP 200 代替身份确认。
2. 美元封顶、当前计费依据/可验证单请求费用上界，及实际计费对账来源。模型未确定，所以没有编造当前价格或总费用预测。
3. `MODEL_API_KEY` 安全环境配置（本轮布尔检查为未设置），代理/直连方式；文档里的 key 示例未使用。
4. 本轮 Qwen 服务或共享 GPU0 新授权，以及 local400/API400/总800 calls、4000 transitions、并发1的预算确认；之前授权不自动继承。
5. 授权后先做两图顺序/正常 JSON/路由和非图表流程控制，固定真实推理配置、输出额度和运行时源副本，再接生产调度/双成本记录。任何控制失败保留且计入预算，不在8例上反复调参。

当前停止于准备交付，不启动真实面板、不扩至 140 对、不开发候选观察机制。
