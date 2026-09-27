# 固定八任务的本地多模型扩展（2026-09-16）

此轮只更换 backbone，不开发新纠错机制，不补跑旧 96 条，不扩展 140 对。
八任务已用于研究开发，不再称为独立未见评测。其原始规则、图、gold 与人工审核口径保留。

## 预选模型与顺序

1. Qwen2.5-VL-7B-Instruct：相近规模的代际比较，复用 qwen3_vl 环境。
2. Qwen3-VL-32B-Instruct：相对旧 Qwen3-VL-8B 的规模比较。
3. InternVL3-8B：不同视觉模型家族；其语言骨干仍为 Qwen2.5 系列，不能称完全独立的语言模型家族。

权重均已在本机，索引所列分片完整。暂不纳入 GUI-owl/UI-TARS：其原生 GUI 动作接口与当前结构化标签动作不相同；本轮不是官方 GUI 系统排名。
官方来源：[Qwen2.5](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)、[Qwen3](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct)、[InternVL3](https://huggingface.co/OpenGVLab/InternVL3-8B)。

## 冻结设计

任务顺序：b010、b046、health001、env035、health005、pub013、b014、env005。
每任务 official140（原误导 arm）、clean140（原对照 arm），选项顺序照旧。
每模型 16 条自然前缀，首次真正提出业务提交但尚未执行时生成 checkpoint。
每 checkpoint 分支 B0/B2/B3，最多 48 个配置记录；三个模型合计最多 48 条前缀、144 个配置记录，不是 144 条独立任务。
无 checkpoint 的三个配置记未执行，不能算核验器失败。

复用 prospective_h_base_v1：真实最近四步动作及公开回执、正常条件式完成说明。
B0 执行真实 pending submit；B2 独立全图目标核查（1 次）；B3 当前表单与图表、当前选项、公开历史的通用主动核验（最多 3 次调用/2 次 crop，可不 crop）。
B2/B3 后共同选择执行器落实建议，再至多 4 次普通 actor 调用，自主提出提交才执行。
保留「核验推荐」「落实选择」「actor 最终提交」三层，不强制提交、不锁选、不注入错误。
B2 与 B3 的上下文和图像权限仍有差异，本轮不能把差异独归因于工具或裁剪。

## 资源、预处理与停止

用户最新明确授权共用 GPU 7，单卡串行（在此前独占检查被挡住之后补充授权，旧阻塞记录保留）。每次加载前 fresh nvidia-smi，要求可用显存至少为权重索引总字节数加 10 GiB 运行余量；不足就记该模型资源阻塞，不改用其他 GPU、不停止他人作业。不下载权重、不开新付费 API、不修改共享 Conda。共享卡占用和 wall-time 不是纯模型速度对比。
每模型上限 400 次真实调用尝试（含控制/失败；控制最多 16，任务最多 384）、2000 次实际浏览器操作（含恢复重放）；三模型总上限 1200/6000。并发 1，无隐式重试、无换模型兜底。
前缀每条最多 12 次调用/20 次浏览器操作；延续最多 4 次。用完就如实记超时。
解码：bfloat16、seed=12345、greedy、max_new_tokens=1024，无量化/CPU offload。
Qwen 使用 native processor + qwen_vl_utils；min_pixels=200704，max_pixels=1003520。
InternVL3 使用官方动态 448×448 tiling，最多 12 个网格块加 thumbnail，ImageNet normalization。
两家的实际视觉 token/像素预算不等；相同原截图不等于相同编码成本。逐响应记录 image_grid/patches、tokens 和图像 SHA。
本机现存 Chromium 实际版本 125.0.6422.26，不假定目录名等于版本；与旧服务器浏览器版本不同，应作为跨轮限制记录。

先运行固定四个非图表 Route 流程控制和两组反转顺序双图颜色检查。任何检查失败即该模型不进入八任务，不反复调 prompt 求通过。服务兼容故障与行为能力失败分开记录。
无自然错误 checkpoint 时恢复率为 N/A。只报告观察到的配对转移，不声称新机制必要性或显著总体优势。

## 隔离与工件

只把 public_task allowlist、真实截图、当前公开 DOM/选择与真实公开历史送给模型。gold、隐藏表格、另一 arm、机制标签和 evaluator 证据框均禁止进入在线 payload。
任务/图片 SHA 在推理前冻结。scorer 只在每模型在线调度结束后运行。保存完整请求、响应、状态截图、真实提交回执、预算、源快照、模型配置/index/code 哈希与各 shard 大小。
旧 panel.py 仅增加显式可选 backbones 参数，默认双模型行为保留；原版另存 backups/panel.py.before。新工件仅写本目录 runs/extension_20260916_v1。
本轮结束即停止，不自动追加任务、强化提示或开发机制。

原波次出现两个 0 派发的浏览器启动超时后，明示的一次基础设施例外及审查依据见 STARTUP_RETRY_NOTE.md：另存目录，限定 120 秒启动等待，严格禁止对已生成前缀重采样；原失败与总预算保留。

Qwen32 在非图表控制出现动作包装格式错误后，用户另行明确授权一次通用语法适配：见 ACTION_CODEC_V2.md。
只解包装、不改模型输入或判断，旧4次调用/17次操作携入同一总额度；新版本与旧输出解析协议分开报告。
此例外不允许重跑 InternVL / Qwen2.5 的已见任务，不允许继续反复调整格式或提示求通过。
