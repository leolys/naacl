# 执行记录

所有命令在 D:/ths_Viswork/research/explanation_completion_20260925 内运行。Python 使用已有研究虚拟环境；没有安装包、下载模型或启动 GPU。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest tests -q --junitxml=tests/offline_receipt_review_fix.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' runner.py --prepare --output 'D:/ths_Viswork/research/explanation_completion_20260925/prepared_final'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' runner.py --live --output 'D:/ths_Viswork/research/explanation_completion_20260925/run'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' check_delivery.py audit --run run
& 'D:/anaconda/python.exe' 'D:/ths_Viswork/aris_repo/tools/evidence_check.py' 'D:/ths_Viswork/research/explanation_completion_20260925' --batch EVIDENCE_CLAIMS.json
```

live 命令的凭据仅在该进程环境中设置，并在 finally 中移除；本文件不包含凭据，也不建议把密钥写入脚本。真实运行 session 正常退出 0，没有中断或重新启动。

结果：33 测试通过；prepare=0 次模型调用；live=9 次请求尝试、3/3 流程完成、0 失败/重试、0.4324315 美元估算；wire audit PASS；六条证据存在性检查 verified（仅存在性，不证明研究主张）。

早期 27 项测试与后来的 33 项测试回执分别保留。第一次使用相对新目录的 prepare 在发请求前被本机路径行为阻断，修复后用新目录重新准备。prepared 是较早代码的准备快照，prepared_final 才是本轮启动前最终检查；run/runtime_source 是实际运行源。

中文使用 Codex 原生整理，不另调用 API。HTML 首版生成后浏览器检查发现目录解析不完整，另版修复并保留首版；最终交付位置见 README.md。没有修改任何真实模型响应。

后续仅离线交付修复：新增标题解析回归后 34 项通过；review_v2 的页面内容通过审查，但 Windows CRLF 与渲染器读入 LF 的源指纹不一致。delivery.py 显式写入 LF，另存 review_v3，未改 run；独立复核确认内容等价、全部指纹匹配。保留两版审查，不以改旧记录制造 PASS。

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' delivery.py render --run 'D:/ths_Viswork/research/explanation_completion_20260925/run' --output-dir 'D:/ths_Viswork/research/explanation_completion_20260925/review_v3'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' check_delivery.py browser --view-dir 'D:/ths_Viswork/research/explanation_completion_20260925/review_v3'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest tests -q --junitxml=tests/offline_receipt_packaging.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' check_delivery.py package
```

最后两条的实际测试回执和打包完整性记录分别见 tests/offline_receipt_packaging.xml、PACKAGE_CHECK.json。打包不包含凭据、虚拟环境及早期准备目录；独立展示不依赖 Python，实验重新推理仍需要已有项目依赖及新授权。
