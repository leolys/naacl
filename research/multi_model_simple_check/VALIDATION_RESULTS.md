# 工程验证记录

2026-09-16；不把工程 PASS 当研究结果。

- 初次单元测试：39 项通过，1 个旧测试模块因调用时未提供其既有 `PYTHONPATH` 而导入失败（`from audit import read`）。未修改该旧模块；按其既有路径调用后通过。
- 最终单元测试：48 项通过，15.264 秒。包括旧双模型默认行为、公共信息投影与 gold 变更不影响输入、真实历史、无自动提交、预算、单模型显式扩展、缺少错误 checkpoint 时 N/A。
- 新单模型真实浏览器脚本化测试：2 个非图表前缀、6 个 B0/B2/B3 分支，18 次 mock 调用、42 次实际浏览器操作、6 次实际 localhost 提交，均通过。含 B3 工具分支。无真实被测模型调用。
- 现存 Chromium 125.0.6422.26 + app-local 依赖成功启动。主代理与独立代理的浏览器 witness 均通过。
- 主代理早先 GPU 7 CUDA witness 通过：32×32 seeded matmul，sum=1019.2579956054688；torch 2.8.0，transformers 4.57.1。随后 spec 仅更正浏览器版本，最终 spec hash=563c93e4。
- 独立文档复核代理 `/root/multimodel_doc_validation` 逐字执行 VALIDATION.md 三命令：两个 CUDA 命令均在分配前因 GPU 7 已非空闲退出 1，无 WITNESS；浏览器命令退出 0。没有模型加载、安装、修复、换卡或杀进程。

因此截至此记录，GPU 环境不能宣称完成最终文档验证，模型控制和八任务真实推理均未运行。阻塞是资源占用变化，不是研究模型的图表能力失败。
新的 GPU 共享授权或空闲复核若到达，必须记录在后续条目，不能抹去本次被守卫拦截的结果。

## 补充授权后的复核与启动

用户随后明确允许共用 GPU 7、仍串行。新鲜代理 `/root/multimodel_shared_doc_validation` 逐字执行带 `--allow-shared-gpu` 的两个 CUDA witness 与原浏览器 witness，全部退出 0，没有文档偏差。
两环境 spec_hash=563c93e4、GPU=7、H100 80GB、shape=[32,32]、sum=1019.2579956054688、Python 3.10.18；torch 2.8.0 / torchvision 0.23.0 / transformers 4.57.1 / accelerate 1.11.0 / qwen-vl-utils 0.0.14 / timm 1.0.20 均一致。
Qwen 环境 witness 前占用 0 MiB；InternVL 前占用 1237 MiB，共享参数有效。两个命令均有非致命的 wandb 内部 pkg_resources 弃用警告；未启用 W&B。
浏览器再次输出 BROWSER_WITNESS 125.0.6422.26。

另新增了本地 HTTP/协议故障立即停止该模型面板、而非向剩余任务重复请求的测试；扩展模块共 5 项通过。连同前述旧测试，本轮验证的不同单元测试总计 49 项。

2026-09-16 20:56（服务器时间），专用 screen `6720.misvis_multi_20260916` 启动有界波次。此条只确认启动；真实模型资格、实际覆盖及失败应查运行目录的动态记录，不由 witness 推断。

## 启动异常与用户授权的接口适配

Qwen32 / InternVL 的原浏览器 20 秒启动超时均发生在 0 模型调用、0 浏览器操作；源快照和失败保留。
独立审查 `/root/browser_startup_failure_review` 支持仅对这两个零派发状态另存一次 120 秒启动等待的重试；
核对 actor/policy/harness、原模型配置/index/code、浏览器哈希、task manifest 均不变。详见 STARTUP_RETRY_NOTE.md。

Qwen32 重试到第三个非图表 Route 控制时，模型将选择动作包在自拟回执中；解析器拒绝，共4次调用/17操作。
用户明确授权通用动作包装适配，另存 v2，不补跑已有图表。独立审查发现必须保留 finish 的停止语义，已修正。
第一次 v2 全回归57项中1项捕获嵌套 dict 类型错误（final_unit_tests_v2.log）；修复后重新全跑：
**57 项通过，10.609 秒**（final_unit_tests_v2_fixed.log），未删除失败日志。
新语法/回执边界真实浏览器 mock：2次 mock 调用、6次浏览器操作、1次 localhost 真提交；无真实模型生成。
它证实模型声称 executed=true 不会提前制造提交，真实选项修改/提交由 executor 执行并写回执。
工程测试通过不等于图表研究假设成立。对应源与命令见 ACTION_CODEC_V2.md。
