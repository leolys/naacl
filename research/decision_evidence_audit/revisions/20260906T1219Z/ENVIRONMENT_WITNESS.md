# 独立环境 witness

Agent：`/root/env_witness`，fresh context，未运行模型推理/浏览器/安装，未写文件。
命令见 COMMANDS.md 中唯一 CUDA WITNESS，两个尝试完全相同。

首次 sandbox 退出 1，无 stdout；CUDA 初始化返回 Error 304（OS call failed or operation not supported）。
通过工具 require_escalated 后退出 0：

```text
WITNESS (8, 8) NVIDIA H100 80GB HBM3 1
VERSIONS 2.8.0+cu128 4.57.1 0.0.14 1.11.0
```

独立反馈：未发现文档与实际差异；此命令未检查物理 UUID，仅证明指定 CUDA 运算可执行，不代表模型服务或实验审计通过。主执行者另有 GPU UUID 与 /health 记录。
