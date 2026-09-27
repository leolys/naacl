# 实际环境与运行边界

本轮只使用已有 Qwen3.8-27B 服务，无新付费API、权重下载或GPU启停。客户端结构化输出的工程成功不代表模型语义正确。

远端客户端：`/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python`。2026-09-27本轮实际查询为Python 3.10.20（conda-forge/GCC14.3.0），不同于更早记录的基础Conda Python，不应直接抄旧版本。包查询Pillow12.2.0、playwright1.59.0、httpx0.28.1；实际传输代码用requests.Session，不依赖httpx。并发与进程锁在Linux运行，Windows只作离线分析、mock测试和展示检查。

本地：`D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe`，Python3.9.13，pytest7.1.2、playwright1.60.0、requests2.28.1；远端实际requests2.33.1。展示QA用已有系统Edge headless，不访问外网，不算业务浏览器transition。没有安装或修改这些既有环境。

服务接口：`http://127.0.0.1:8058/v1/chat/completions`，返回模型名Qwen3.8-27B、root为`/mnt/data/datasets/open_source_models/Qwen3.8-27B`、max_model_len16384。这里记录可观察的部署名/路径，不从名称进一步推断未经验证的训练身份。

每次面板真实启动的`preflight_*.json`保存health、models、nvidia-smi、已有服务进程身份与命令。已观察API316818、Engine319282、guard282313；API和推理进程启动于2026-09-26。GPU7 UUID `GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7`。现有命令BF16、tensor-parallel1、max_num_seqs1、max_model_len16384、图像最多1张/max_pixels1605632、eager。不将其他GPU当前作业当成本任务可用资源。

本轮请求固定temperature0.7、top_p0.8、top_k20、seed12345、enable_thinking=false；READ最多1500、VERIFY3600、DECIDE700输出token。原图字节未裁剪/改绘，预处理由同一现有服务完成。固定seed不构成跨运行完全确定性的保证。每个真实请求另存完整messages、单图data URI、动态输出schema及实际响应。

此前历史v3来自同服务/解码/图处理口径，但不是同期随机试验。本轮普通基线与新核验共享公开任务、图像、选项顺序和最终输出schema；前者一阶段，后者三阶段，成本不相等。只有离线评价工具能读`offline/labels.json`，该目录未上传给执行器。

三阶段方案另沿用此前已生成的275条O/B记录：136个任务来自历史Terra候选，4个任务来自上轮Qwen补链。因此本轮并非纯Qwen从零生成全部解释链的端到端实验。旧候选生成调用不重复计入本轮，但它们是既有资源，不是零成本；当前请求账本只能说明本轮核验/选择及开发成本，不能据此宣称整套方法端到端仅需三次请求。原候选在历史v3与本轮新版之间保持相同。

复现必须另获服务/运行授权并开新目录；不要为重新执行修改这次固定时间与调用上限，或覆盖本轮和旧轮工件。
