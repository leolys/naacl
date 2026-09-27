# 本轮命令

服务器通过 `ssh hexin_2007_K_root` 连接。以下 Bash 命令均从 `/mnt/data/lys/CognitiveHijacking_CognitiveDenial` 执行；本目录源文件由 apply_patch 在桌面准备后 scp 部署。仅 panel.py 增加可选 backbone 参数，原版保留在 backups/panel.py.before。

```bash
python3 -m research.multi_model_simple_check.environment --prepare-browser
env LD_LIBRARY_PATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/multi_model_simple_check/runtime/browser_libs/usr/lib/x86_64-linux-gnu /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.environment --browser-witness
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.run --prepare
```

依赖准备的两次失败也保留说明：第一次 apt 尝试重复下载系统已装的 libdrm2/libxshmfence1，但当前 apt 源不提供已装版本，未安装任何内容；第二次 ldd 指出 avahi/ffi7 的传递依赖；第三次 app-local 补齐成功。没有修改 apt 源、系统库或 Conda 包。完整最终包版本/哈希见 runtime/browser_libs/PACKAGE_MANIFEST.json。

```bash
env PYTHONPATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/prefix_selection_diagnostic:/mnt/data/lys/CognitiveHijacking_CognitiveDenial PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.prospective_simple_check_pilot.test_panel research.prospective_simple_check_pilot.test_preparation research.prefix_selection_diagnostic.test_diagnostic research.multi_model_simple_check.test_extension -v
env LD_LIBRARY_PATH=/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/multi_model_simple_check/runtime/browser_libs/usr/lib/x86_64-linux-gnu PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.multi_model_simple_check.test_extension --browser-output research/multi_model_simple_check/runs/extension_20260916_v1/mock_browser_extension
```

CUDA 与独立代理逐字复核命令见 VALIDATION.md；执行状态见 VALIDATION_RESULTS.md。全模型启动命令不等于已经启动；应以 wave_status.json / 各模型 final_status.json 为准。
