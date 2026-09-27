# O/B-only 实际执行记录

新目录ob_only_verification_20260926，原数据/候选/核验结果只读。ARIS继续暂停，无付费API，无GPU启停。

## 执行前

只读 `nvidia-smi` / `ps` / localhost health与models；GPU7 UUID原值，显存72211MiB已用/8784MiB空闲，API316818/engine319282/guard282313身份未变。GPU6有其他作业，未触碰。完整运行前探测另存service_preflight.json。

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/ob_only_verification_20260926/test_panel.py -q --junitxml=research/ob_only_verification_20260926/offline_tests_002.xml
ssh hexin_2007_K_root "cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_only_verification_20260926 && env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest test_panel -q"
```

两端各13项通过。offline_tests_001.xml保留首次测试序列化bytes的失败；修复只涉及测试取context，不改模型处理逻辑。

## 唯一真实启动

```powershell
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_only_verification_20260926/run_panel.py --output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_only_verification_20260926/run_live_001"
```

独立LIVE_LOCK禁止重跑。每单元O/B核验后新选择，最多16正常call/20尝试，300秒HTTP超时。输出3600/700，thinkingfalse，其余解码同前轮。全部请求、响应、图像、索引、源C离线映射与用量保留；未知传输即停止，结构失败不质量重跑。

初始3基础任务/4图输入/8来源单元，28旧新链，非8独立任务。只返回选项，不执行表单。运行后统计与结论见REPORT.md、RESULTS_AUDIT.json、RESULT_REVIEW.md。

## 完成与取回

唯一真实进程退出码0、summary.status=finished。16请求均HTTP200，8核验8选择，0重试、0超时，来源与运行源保持不变。78,826token，usage完整。

```powershell
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/pack_terminal_run.py --source /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/ob_only_verification_20260926/run_live_001 --output /tmp/ob_only_verification_20260926_finished_001.tgz"
scp hexin_2007_K_root:/tmp/ob_only_verification_20260926_finished_001.tgz research/ob_only_verification_20260926/finished_001.tgz
tar -xzf research/ob_only_verification_20260926/finished_001.tgz -C research/ob_only_verification_20260926
```

199文件打包前后hash相同；远端/下载包SHA256均为bf58ca0c7d323eb6fcd144f50afc5248f7301398a5a5e0b42b61f92403704346。下载退出0且核对hash后才解压。partial_*是已完成单元的中途只读副本，不算额外模型调用，不入最终ZIP。

## 离线核对与展示

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/ob_only_verification_20260926/test_panel.py research/ob_only_verification_20260926/test_viewer.py -q --junitxml=research/ob_only_verification_20260926/offline_tests_003.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/ob_only_verification_20260926/audit_run.py --run research/ob_only_verification_20260926/run_live_001 --output research/ob_only_verification_20260926/RESULTS_AUDIT.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/ob_only_verification_20260926/build_review.py --run research/ob_only_verification_20260926/run_live_001 --output research/ob_only_verification_20260926/review_001 --notes research/ob_only_verification_20260926/NOTES_ZH.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/qa_review.py --html research/ob_only_verification_20260926/review_001/OB_ONLY_REVIEW.html --output research/ob_only_verification_20260926/review_qa_001
```

本地17项通过。实际请求/源hash审计通过（不是语义正确）；HTML QA通过：4内嵌原图、0远程依赖/请求、0断锚/页面错误，桌面/手机无横向溢出。中文全部离线，不调用翻译API。

已目视检查桌面首页、b002详情与手机截图，图表、摘要与展开内容正常显示。对抗审查结束后，将完整请求/响应、冻结源码、原图、测试、报告与独立HTML打包；ZIP另做CRC与SHA256核对。包内包含模型服务依赖记录，不包含模型权重，独立HTML可直接离线打开。

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/ob_only_verification_20260926/package_delivery.py
```

工件包清单、大小与SHA256见同目录DELIVERY.json。打包后不追加模型调用，不重跑旧结果。
