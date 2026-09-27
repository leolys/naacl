# 本轮实际执行报告：因强 API 身份不符停止

日期：2026-09-07。授权已经获得；**正式 8 任务面板未运行，不是缺少 GPU/金额授权**。

## 最重要的结果

Qwen3-VL-8B-Instruct 已成功加载到 GPU0。随后第一条真实 GPT 接口控制发现：发送 `gpt-5.6-sol`，响应顶层仍为 `gpt-5.6-sol`，但本次执行的 `usage.model_name` 为 **`gpt-5.6-luna`**。按预定身份检查，整个面板立即停止，不接受 Luna 替代、不继续单 Qwen 实验、不尝试一串别名。

这是**网关所报告执行身份与请求身份不一致**，不是对 Sol 权重身份的独立取证，也不是 Sol 或 Qwen 在误导图表上失败。当前无法把这个返回算作已确认强模型的结果。

## 本轮做了什么、用了什么资源

| 项目 | 本轮真实记录 |
|---|---|
| 获批资源 | API 上限 $50；共享 GPU0；每模型最多 400 次调用；总 4000 transition；并发 1 |
| GPU | GPU0，NVIDIA H100 80GB HBM3 |
| Qwen 权重 | 已有 Qwen3-VL-8B-Instruct，未下载 |
| Qwen 加载 | BF16，10.197 秒，约 17282 MiB 显存 |
| Qwen 配置 | greedy，输出上限 1024，seed 12345，max_pixels=1003520，原生多图接口 |
| Qwen 生成调用 | **0**；服务只被检查 health，尚未轮到本地控制 |
| API 候选配置 | gpt-5.6-sol，medium，max_completion_tokens=8192，high detail，不传 temperature |
| API 元数据读取 | 2 次 GET：`/models` 和 `/model/info?model=gpt-5.6-sol`，均 200 |
| API 真实生成 | **1 次**，固定非图表 Route A 已选状态，未重试 |
| 浏览器实际 transition | **4 次**，均为该控制的公开状态设置 |
| 真实提交 | **0**，异模型返回在交给 actor/action parser 前被拒绝 |
| 正式基础任务启动 | **0 / 8** |
| 正式自然前缀启动 | **0 / 32** |
| 计划配置 | **96 条全部保留为未运行**，不是 96 条执行轨迹 |

Qwen 服务使用本机 PID 40510（NVIDIA 进程视图显示对应 GPU 进程 43031），仅绑定 `CUDA_VISIBLE_DEVICES=0`。本轮结束后重新核对命令行、工作目录、8045 监听身份，再精确 TERM 40510，服务退出 143。复查 GPU0 降回 3 MiB、利用率 0%，8045 已关闭。没有停止其他 GPU 作业，也没有删除结果。

## 第一条真实 API 请求的完整证据

- [实际序列化请求，不含鉴权头](live_panel_01/api_wire/call_0001/request.json)：包含完整 system/user 消息和一张实际控制截图的图像内容，非 CASE_VIEWER 摘要。
- [原返回，已脱敏](live_panel_01/api_wire/call_0001/response.json)：`model=gpt-5.6-sol`，`usage.model_name=gpt-5.6-luna`。
- [在线请求、截图与前缀时间线](live_panel_01/online/controls/M_strong/route_A_A/prefix/)；截图对应本次动作前状态：Route A 已被控制设置选中。
- [停止原因](live_panel_01/stop.json)、[实际预算事件](live_panel_01/budget.json)、[逐调用 API 账本](live_panel_01/api_wire/api_spend.json)。

返回内容为 `{"action":"click_button","text":"Submit Form"}`。这个字符串符合“公开目标 Route A、当前已选 A”的普通流程，但**只是一条身份不合格的返回**；不能宣布四场景流程控制或多图控制已经通过。由于身份检查先于动作处理，它没有形成被接受的 submit proposal，也没有执行 POST。

网关响应 ID：`resp_0f05be575d561b8f016a9eaf2adc8487d0928c0e77a291e768`；网关请求跟踪 ID：`260907203345936838dca`。调用总耗时 43.804 秒；输入 2775、输出 15、总 2790 token；返回的 reasoning_tokens 为 0。不能用这个字段推断 Sol 不支持 medium，它可能根本不是所请求的执行路由。

## 费用如何记录

本轮 `/model/info` 返回四个名为 Sol 的部署，配置上游均为 Sol，含基础输入/输出 $4/$20 每百万 token，最高已报档位输入/输出 $8/$40。元数据归档见 [gateway_metadata_01/requests.json](gateway_metadata_01/requests.json)。这说明“配置声称 Sol”与“本次执行报告 Luna”发生冲突，元数据本身不能替代逐请求身份核查。

请求前预留 $9，按全部输入容量与输出上限保守计算。由于返回身份不符，这次请求不按 Sol 已知用量费率释放预留，账本保留 `accounted_upper_usd=9`。**这不是实际花了 $9。**响应另自报 `usage.cost=0.00028649999999999997`，保留原值；其币种/结算口径未独立核验，实际账单仍为未知，不能把预留或自报值冒充实付。

仅发生一条生成，没有失败后第二次请求；未达到额度上限。停止原因是身份不符，不是费用不够。没有触发正式任务前的成本场景估计，因为固定控制尚未通过。

## 工程与信息边界

启动前 [68 项单元及原核心回归](prelaunch_tests.log) 通过。新增可选费用结算仅在完整 usage、已知网关费率和身份符合时收紧预算，未知/失败请求仍保留预留；旧固定预留默认行为不变。修改前源副本在 `before_live_accounting_sources/`，真正执行版本在 `live_panel_01/executed_sources/`，旧准备/实验工件没有回写当前身份。

run-experiment 技能促成一次 fresh-agent 8×8 CUDA witness 和运行身份/清理检查；它只验证 CUDA 与现有库版本，没有新增环境、hash contract 或大型审查系统。OpenAI Docs 用来确认候选公开参数；费用依据另外读取获授权网关元数据，未把官方网页直接当该网关账单。

唯一被测请求只包含合成的公开 Route 控制、当前截图、公开执行回执和正常条件式完成说明；没有向模型发送新 8 任务的图、gold、机制标记、另一 arm、scorer 或研究者报告。正式原数据与任务规则均未改动。

## 可以和不可以得出的结论

直接观察：GPU0 能加载已有 Qwen；现有 key 的这一次 Sol 请求执行记录报告 Luna；身份不符时整个面板停止且保留 96 条未运行状态。

不能得出：Sol/Luna/Qwen 的图表纠错强弱，B2/B3 是否足够，任何新任务的成功率或自然错误提交恢复率。新研究 checkpoint 数为 0，恢复率 N/A；这里的 0 来自**没有开始研究任务**，不是跑完面板未见错误。

下一步仅需解决网关路由：请管理员确认该 key 所属团队能否真实调用 Sol、是否存在默认/自动路由，或提供一个可确认身份的强模型部署 ID。可转发 [无密钥的问题单](GATEWAY_ROUTE_ISSUE.md)。在这一处明确之前不重试别名、不补跑 Qwen-only、不换任务；本轮现有 1 次调用及其费用记录保留，后续不能重置为未消费预算。
