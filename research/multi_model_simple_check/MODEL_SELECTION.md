# 为什么选这三个本地模型

这是对原八任务实验的 backbone 扩展，不是从本地模型中按任务得分选赢家。预选发生在新模型接触任务之前。

| 模型 | 本地权重目录 | 索引权重大小/分片 | 比较价值 |
|---|---|---|---|
| Qwen2.5-VL-7B-Instruct | Qwen2.5-VL-7B-Instruct | 16,584,333,312 字节 / 5 | 与旧 Qwen3-VL-8B 相近规模的代际对比 |
| Qwen3-VL-32B-Instruct | Qwen3-vl-32-instruct | 66,714,780,128 字节 / 14 | 同 Qwen3-VL 系列的规模对比 |
| InternVL3-8B | InternVL3-8B | 15,888,747,520 字节 / 4 | 不同视觉模型家族；语言骨干仍属 Qwen2.5 |

路径根均为 `/mnt/data/datasets/open_source_models`。这些是 safetensors index 给出的 tensor 字节，不是运行显存、参数精确个数或完整文件字节数。运行服务会进一步记录实际加载参数个数、权重分片文件大小、配置/code/index SHA256；不把目录名字当身份验证。

本轮不选：GUI-owl-32B / UI-TARS1.5-7B（原生坐标式 GUI 协议不同）；Thinking 模型（推理 token 与输出解析预算需单独设计）；72B/235B（单卡资源不合适）；Qwen3.5/3.6（本轮先用现有已知 runtime，避免同时大改模型依赖）。InternVL3-38B 的索引权重约 76.8 GB，单张共用 H100 留给视觉处理和 KV cache 的空间过少。

这只是合理的受控小面板，不保证上述三者是现有所有模型中的最优选择。模型间 native 图像处理与视觉 token 数仍有差异。原 Qwen8 结果来自旧浏览器/服务器，应作历史参照，而非严格只变参数量的当场消融。

官方模型说明：[Qwen2.5-VL-7B](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)、[Qwen3-VL-32B](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct)、[InternVL3-8B](https://huggingface.co/OpenGVLab/InternVL3-8B)。
