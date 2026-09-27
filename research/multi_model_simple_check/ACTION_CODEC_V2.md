# 明示接口适配版本：actor_action_envelope_v2

用户在 Qwen3-VL-32B 尚未进入任何图表任务时，明确授权这一次通用格式适配。
原启动尝试与 startup_retry01 工件保留。后者共消耗 4 次真实调用、17 次浏览器操作；
失败点是第三个公开 Route 控制将正确选择动作包在自拟执行回执中，旧解析器拒绝执行。
不能把该现象报告为图表语义失败或相信模型声称的 executed=true。

新入口仅用于 qwen3_32b_action_codec_v2；这不是再次补跑已见图表任务。
原零派发 startup_retry 守卫不改。新入口必须证明旧面板从未开始，累计旧账本，
总上限仍 400 次调用、2000 次浏览器操作，控制累计最多 16 次，任务最多 384 次。
固定重新执行同一组非图表资格检查，不再出现失败后继续改格式/提示求通过。

## 改动边界

- 只在 prefix / actor_continuation 响应处接受一个完整 JSON 对象的一层 action 字典。
- 仅保留原执行器已有动作名和字符串字段；缺字段、嵌套多层、未知动作不补全。
- 丢弃模型自拟 executed、URL、error、attempt 等，浏览器执行器独自生成真实回执。
- 原 responses 文件保存未改动的原文，action_codec sidecar 保存规范化及丢弃字段；
  timeline 使用实际交给执行器的规范化动作。这两者不同是明示接口转换，不是假装原生输出。
- 普通平坦输出逐字不变；B2/B3 核验结构完全不改。不读取 gold、当前正确性或图表内容。
- 模型输入、历史、提示、图像、权重、解码、scorer 不变；浏览器启动等待仍为 120 秒。

只有这一模型的新运行启用 v2。与旧 v1 的 Qwen2.5 / InternVL 结果不应宣称完全同接口；
报告必须列出实际发生的 unwrapped 次数与阶段。不会为统一版本而补跑其他模型。

## 明确命令（在项目根目录）

```bash
env PYTHONPATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/prefix_selection_diagnostic:/mnt/data/lys/CognitiveHijacking_CognitiveDenial PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.multi_model_simple_check.test_action_codec -v
env LD_LIBRARY_PATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/multi_model_simple_check/runtime/browser_libs/usr/lib/x86_64-linux-gnu PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.test_action_codec --browser-output research/multi_model_simple_check/runs/extension_20260916_v1/mock_action_codec_v2
screen -L -Logfile research/multi_model_simple_check/runs/extension_20260916_v1/qwen3_32b_action_codec_v2_wave.log -dmS misvis_qwen32_codec_20260916 env DEBUG=pw:browser /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u -m research.multi_model_simple_check.launch_action_codec --authorized-action-codec --allow-shared-gpu
```

真实启动前必须完成 mock 测试与独立窄范围审查，等待 InternVL 当前运行结束、重新检查 GPU7。
不改变原波次/旧 manifest/旧 score；显式接口适配仅一次，无下一次自动重试。

独立审查指出应保留原 prompt 中的 finish（不提交即结束）动作；已加入 allowlist 并补测试，
避免把本应结束的动作错误变为 invalid 后继续循环。没有扩大浏览器能力或增加提交规则。
真实浏览器 mock 验证自拟“已完成”不能提前产生提交回执：2 次 mock 调用、6 次浏览器操作、1 次真实本地提交。
