# 本轮执行与复核命令

全部真实推理由已封存的四客户端完成，本次收尾没有新增推理、没有补跑。用户最初启动授权、封存包、远端真实argv与PID均保留。不要为了复核报告重新执行dispatch或run。

## 已启动运行的真实记录

- 封存身份：`RUNTIME_SEAL.json`，SHA256 `17afcc2f2606d5783f57c6456fc82b375cc270e1dbadd68111e2637a3b333ab9`。
- 四客户端、进程与服务身份：`captures/final_001/dispatch/`；真实终态日志为`worker_0.log`至`worker_3.log`。
- 实际请求参数在每条`runs/<version>/full_<task>/<stage>/request.json`；每次响应、用量、执行顺序在同目录及`workers/<n>/ledger.json`。不是仅保存prompt模板。
- 远端资源生命周期入口为封存的`resource_manager.py`、`dispatch.py`、`watchdog.py`、`cleanup.py`；最终清理信号与恢复前空闲检查见capture的`cleanup/`。不需要重新执行这些入口。

## 收尾时实际使用的命令

远端只读状态：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=15 hexin_2007_K_root "PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_full_comparison_20260927/status.py"
```

四客户端结束后生成唯一新快照：

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=15 hexin_2007_K_root "PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_full_comparison_20260927/collect.py"
scp -o BatchMode=yes -o ConnectTimeout=15 hexin_2007_K_root:/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_full_comparison_20260927/CAPTURE_20260927T114350560414Z.zip D:/ths_Viswork/research/ob_full_comparison_20260927/CAPTURE_20260927T114350560414Z.zip
```

下载前检查目标不存在；收件262,127,164字节、14328成员，SHA256 `6f48454fafbf929279352180c58073abc6fdc5d8acf9083646516fe604fb659f`。快照仅模型/客户端结果已稳定；仍在运行的guard日志是采集时点快照，不声称所有系统文件在同一纳秒采集。

只读资源验收（不会发模型请求、启动或停止进程）：

```powershell
Get-Content -Raw -LiteralPath 'D:\ths_Viswork\research\ob_full_comparison_20260927\checks\final_resource_check.py' | ssh -o BatchMode=yes -o ConnectTimeout=15 hexin_2007_K_root 'PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -'
```

## 本地离线分析

从`D:/ths_Viswork/research/ob_full_comparison_20260927`执行，Python为已有任务虚拟环境，无安装。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$taskPython='D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe'
& $taskPython -m pytest -q test_full.py test_analysis.py --junitxml=checks/FINAL_LOCAL_TESTS.xml
& $taskPython receive_capture.py --archive CAPTURE_20260927T114350560414Z.zip --name final_001 --sha256 6f48454fafbf929279352180c58073abc6fdc5d8acf9083646516fe604fb659f
& $taskPython evaluate.py --capture captures/final_001 --output analysis/final_001
& $taskPython integrity_audit.py --capture captures/final_001 --output analysis/final_001/INTEGRITY.json
& $taskPython build_tables.py
& $taskPython build_review.py --capture captures/final_001 --analysis analysis/final_001 --output review_final_001
& $taskPython qa_viewer.py --html review_final_001/OB_FULL_COMPARISON_REVIEW.html --output qa_final_001
& $taskPython build_review.py --capture captures/final_001 --analysis analysis/final_001 --output review_final_002
& $taskPython qa_viewer.py --html review_final_002/OB_FULL_COMPARISON_REVIEW.html --output qa_final_002
& $taskPython package_delivery.py --output OB_FULL_COMPARISON_EVIDENCE_20260927.zip
```

这些输出使用新路径/独占创建；复核时请使用全新输出名，不删除或覆盖既有正式文件。`build_tables.py`固定写SUPPLEMENTAL.json，只在新工作副本中重新生成。证据包保留相邻历史源文件供原标签哈希与提示相等测试使用；保留目录层级即可离线读取，不需要连接服务器。

## 已知检查记录和非结果错误

- 18项本地测试通过，Windows跳过1项Linux锁；开跑前远端8项替代离线实测已通过。远端原环境没有pytest，未安装，没将其计成模型失败。
- 早期实时capture在写入中跨越文件清单与账本时间，严格评分拒绝；保留progress_001且不用于本报告。
- 本轮最终核对840结果、2232主阶段请求、2236含控制尝试，缺失0；306封存文件及标签保持。
- 收尾一次只读tail使用了不存在的`resources/guard_remaining/guard.log`，随后据源码改读实际`process.log`并完成精确身份与分配日志检查；没有重启或改动该guard。
- 报告编辑曾有一次apply_patch上下文顺序检查失败；未改线上工件，按正确段落顺序重新应用。此类离线工具错误不是模型请求，也未清除模型失败。
- 初次直接执行展示模板遇Python3.9编码报错，严格UTF-8解码和compile(bytes)检查通过；加显式UTF-8声明后正常生成，不改模型工件。第一版QA通过，但人工看截图发现手机表头/配置名过度折行；第二版只加宽表横向滚动并重新QA，旧HTML和QA保留。
- 展示和打包的实际PASS/哈希以`qa_final_002/QA.json`及`OB_FULL_COMPARISON_EVIDENCE_20260927.manifest.json`为准。测试只验证链路与工件，不等于语义核验全部正确。
