# 实现对抗审查

2026-09-26。普通离线代码审查；未使用暂停中的 ARIS，未调用模型或 SSH。阅读 runner.py、prompts.py、schemas.py、config.json、PROTOCOL.md，以及 audit/run_public39.py 和保存的单动作 schema。

## 初审发现及复核状态

### 1. 提交 hook 的动作别名：初审 blocking，已修复复核

`is_submit` 初版只识别 `click_button / Submit Form`，但原 `execute_browser_action` 的 `click_link` 可 fallback 到同名 button；该输出也符合 actor schema。因此模型可以真实提交却绕过 hook。须同时覆盖原执行器允许的这种公开别名，并以单测核对。不能把这种绕过当作自然未到提交状态。

复核：`is_submit` 现同时识别 click_button/click_link，仍要求公开文本恰为 Submit Form。不是扩大到自动提交或任意按钮。

### 2. 模型服务异常的全局停止：初审 blocking，已修复复核

原 `llm_next_action` 会把 `LimitStop` 包装为 `RuntimeError`；外层若仅捕获原异常类型，会把预算/未知传输停止降成分支失败继续调用。另，方法请求的非成功 HTTP 初版直接抛 HTTPError，也会被分支 catch 吞掉。应在 actor 边界还原停止信号，并在所有方法阶段把服务失败明确升级为全局停止。

端点已经硬限制本机 8058，Session 禁用环境代理；仍需 `allow_redirects=False`，避免 30x 跟随到未授权端点。暂态 HTTP 的失败与最多一次重试都必须计入同一账本。结构或质量失败不重跑。

复核：Ledger.block 现持久记录全局停止原因；任何后续计费/执行事件先检查 blocked；Actor.next 在原包装异常后根据账本还原 LimitStop。LocalAPI 显式禁止 redirect，暂态 HTTP 最多尝试两次，其余非200及重试耗尽全局停止。

## 已确认的设计与实现边界

- 自然前缀复用归档原 Public39 的系统/用户提示构造和原执行器；只换到已授权本地传输，history_runtime=None；后续统一增加真实历史和同格式候选报告。原行为与后续上下文不同，协议已标明。
- hook 在提案执行前保存当前页面、真实历史、截图与 pending。B0 使用 actor 实际输出，不编造提交；方法 actor 可保留、改选、finish 或超时，无正确答案护栏。
- 在线方法上下文从公开 state/history/options/pending 构造；评分及 arm 名称留在外层实验记录。核验不接收问题/分支字段或选定赢家。候选 ID 仍可能提示来源，因此不是严格盲审。
- 每 arm 只生成一次初始集合，I/O/N 共享；old/new 问题用同 schema、上限、补充器、核验及 actor。两种问题提示无任务 ID、州名或正确答案定制。
- 方法分支新建浏览器并真实重放历史，state、图像 SHA、实际历史三项完全一致才继续；重放动作计入总账。
- 账本请求尝试在发送前增加，浏览器操作在 goto/action 前增加；上限合计 64 请求/240 动作，跨 arm 共用。未知传输不应自动重发。
- old_questions 是旧“问题目标”的统一接口适配，**不是旧 v3 完整方法复现**：共同 supplement 不提供旧 refinement 记录。不能把本轮差异归因旧 v3 整套能力。
- 本例已知 clean 成功、official 错误，是开发诊断。只有最终真实提交且原评分成功才叫完成纠正；新 C、临时改选或核验支持都应分别报告。

## 离线测试记录

审查者执行：

```powershell
& 'D:\anaconda\python.exe' -m unittest discover -s 'D:\ths_Viswork\research\alternative_conclusion_20260926\tests' -p 'test_prompts_schemas.py' -v
```

结果：33 tests，OK，退出码 0。覆盖记录结构、引用关系、初始原文不改写、候选输出与核验职责分离、允许零补充、旧/新 Q 同接口及通用提示。此时还未运行后续 fake transport / browser 控制；该 33 项通过不表示整个线上链路已验证。

## 尚不能从静态代码证明

远端新请求的实际截图库、state 文本无意外提示、每次重放一致性、服务真实返回身份、分支最终提交及 scorer 输出，需运行工件逐条核实。图表两种条件是否给出预期差异也不能由单测或此审查预设。

静态源码复核后没有发现新的 blocking。测试还须采用修复后的异常预期：503耗尽为 LimitStop，不再是 HTTPError；全局blocked后不能继续增加浏览器计数，两个独立上限应分别测试。该审查通过只表示当前可见实现符合预定有界开发诊断，不保证运行成功或研究假设成立。

测试复核补记：上述异常预期已更新。审查者随后执行同一 unittest 命令、移除 `-p test_prompts_schemas.py` 文件限制，运行全部 **47 tests，OK，退出码0**。这次增加本机 mock 传输、全局停止、两提交别名、预算、公开投影和离线提交评分测试；没有发出真实模型请求。
