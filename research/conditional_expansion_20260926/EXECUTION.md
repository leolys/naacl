# 三字段条件式展开：实际执行记录

所有改动位于新目录research/conditional_expansion_20260926；旧反问、候选、图像和结果不覆盖。ARIS仍停用。

## 测试和预审

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/conditional_expansion_20260926/test_pipeline.py -q --junitxml=research/conditional_expansion_20260926/offline_tests_001.xml
ssh hexin_2007_K_root "cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926 && env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest test_pipeline -v"
```

本地/远端均12项测试通过；模拟调用不作为真实效果。PRE_REVIEW.md为独立审查，不是用户人工确认。

## 本轮唯一真实启动

```powershell
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/run_panel.py --project /mnt/data/lys/CognitiveHijacking_CognitiveDenial --output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/run_live_001"
```

服务沿用Qwen3.8-27B、localhost8058，启动前models和GPU/PID只读检查：API316818、Engine319282、guard282313，GPU7 UUID GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7，72211MiB已用/8784MiB空闲。其他作业不变，不启停模型或占卡进程。

运行时preflight、config、source_hashes和全部system/user/schema/原图/原响应/usage均保留；来源两种反问的提示只存副本，不加入本轮消息。固定14旧候选，不做上游新生成；先14展开后8核验，最多28请求尝试。

## 离线核对与展示

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conditional_expansion_20260926/audit_run.py --run research/conditional_expansion_20260926/run_live_001 --output research/conditional_expansion_20260926/RESULTS_AUDIT.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conditional_expansion_20260926/build_review.py --run research/conditional_expansion_20260926/run_live_001 --output research/conditional_expansion_20260926/review_001 --annotations research/conditional_expansion_20260926/ANNOTATIONS_ZH.json
```

中文由Codex离线提供，无翻译API。HTML原图内嵌，能独立打开；请求中的图片base64在阅览层替换为hash引用，system/user全文保留。旧展开与新展开并排呈现，不把结构完整、C照抄或核验enum当作正确率。

## 实际终态与归档

唯一真实启动退出码1：第19次请求（coverage/pub001_misleading/verify）ReadTimeout=120秒，触发冻结协议的未知传输结果停止。未续跑或质量重试。14展开完成，4核验完成、1核验未知、3核验未发送。原runtime文件未修改。

用新pack_terminal_run.py归档status=stopped（未把它改成finished）。204个源文件打包前后hash一致；远程tgz与下载文件SHA256均为357f9727bcc636908ab85ff01d9b0b4727dfc8ad3b39ed7066114f769708c187，下载退出0后才解压。run_live_001保持原样。展开中间快照只用于提前阅览，不是独立实验。

```powershell
scp research/conditional_expansion_20260926/pack_terminal_run.py hexin_2007_K_root:/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/pack_terminal_run.py
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/pack_terminal_run.py --source /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conditional_expansion_20260926/run_live_001 --output /tmp/conditional_expansion_20260926_terminal_001.tgz"
scp hexin_2007_K_root:/tmp/conditional_expansion_20260926_terminal_001.tgz research/conditional_expansion_20260926/terminal_001.tgz
tar -xzf research/conditional_expansion_20260926/terminal_001.tgz -C research/conditional_expansion_20260926
```

原RESULTS_AUDIT.json保留；新增v2明示缺失usage，不改实际结果。19请求输入核对通过；18个响应已知53958token，另1次未知。独立审查另见RESULT_REVIEW.md。

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conditional_expansion_20260926/audit_run.py --run research/conditional_expansion_20260926/run_live_001 --output research/conditional_expansion_20260926/RESULTS_AUDIT_v2.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conditional_expansion_20260926/prepare_review.py
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/conditional_expansion_20260926/test_pipeline.py research/conditional_expansion_20260926/test_viewer.py -q --junitxml=research/conditional_expansion_20260926/offline_tests_terminal.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/qa_review.py --html research/conditional_expansion_20260926/review_001/CONDITIONAL_EXPANSION_REVIEW.html --output research/conditional_expansion_20260926/review_qa_001
```

终态测试19 passed。HTML QA passed：4内嵌图、0远程依赖/请求、0断锚/页面错误，desktop/mobile无横向溢出；desktop、b002、mobile截图已视觉检查。服务只读ps/tail显示原进程仍在，日志最后Running=0/Waiting=0，不据此推断超时具体原因。未重启服务。
