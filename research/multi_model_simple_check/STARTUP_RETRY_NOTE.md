# 明示的单次启动重试例外

原波次中 Qwen3-VL-32B 和 InternVL3-8B 都已加载成功，但 Chromium 启动超过 20 秒；两者都为 0 模型调用、0 浏览器 transition、0 前缀，48 行均未运行。这不是模型流程控制失败，也不是图表任务失败。
原 service / panel 日志、extension_failure、budget、progress 和 final_status 原样保留。

独立 sub-agent `/root/browser_startup_failure_review` 只读核对入口顺序、原日志与重试候选，认为可做一次严格零派发的基础设施诊断；它明确指出 120 秒不是已证实的修复，process exit 0 不是实验成功。
主代理额外离线浏览器 witness（没有模型加载/请求）于服务器 21:19 完成，Chromium 125.0.6422.26 在约 3.301 秒启动。原三次尝试的 browser SHA256 相同；当前无残留的本轮浏览器进程；cgroup memory.failcnt=0。这些证据尚不能定位两次超时的根因。

作为 PROTOCOL.md 原波次结束规则的明示例外：只对上述两条尚未派发任何请求的模型各做 **一次** `_startup_retry01`，按 32B 后 InternVL 串行，仍为用户授权共享 GPU 7。已完成的 Qwen2.5 不重跑，也不补跑其 pub013/B2 截图差异分支。

重试唯一行为设置变化：Chromium launch timeout 从 20 秒变为 120 秒；日志可增加 DEBUG=pw:browser。模型权重、native adapter、精度、解码、任务 manifest、图像、gold、prompt、harness、actor 与 verifier 预算不变。
启动器在读原工件后强制验证 0 调用/transition/events/request files/prefixes，原 failure 必须为 BrowserType.launch TimeoutError；比较原 manifest、模型配置、浏览器 SHA、全部旧 actor/policy/harness 源快照以及模型 config/index/code SHA。
使用原 wave.lock，全程持有；HTTP 服务先独占绑定端口再加载权重；新鲜 GPU 检查要求权重大小加 10 GiB 可用显存。只终止自己创建的 service 子进程。
任何已调用过模型/已生成前缀的运行均不可进入本入口。不删除、移动、覆盖原运行，不生成第三次尝试。

两尝试合计仍受每模型 400 次调用/2000 transition 限制（原尝试为 0，新的硬上限不变）。原 48 条未运行行不能作为另一组样本拼入统计。成功根据资格、真实前缀/提交、final_status、stop/failure 工件判定。
完成这一次诊断尝试后停止，无论成功或失败，不自动扩大任务或追加模型。

## 执行命令（原波次完成后，逐个运行，不能同时启动）

```bash
env DEBUG=pw:browser /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u -m research.multi_model_simple_check.retry_startup --model qwen3_32b --allow-shared-gpu
env DEBUG=pw:browser /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u -m research.multi_model_simple_check.retry_startup --model internvl3_8b --allow-shared-gpu
```
