# 本轮执行记录

新目录`research/candidate_registration_20260926`；旧源输入与结果只读。ARIS未使用、未恢复。

## 测试

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/candidate_registration_20260926/test_panel.py -q --junitxml=research/candidate_registration_20260926/offline_tests_001.xml
ssh hexin_2007_K_root "cd /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/candidate_registration_20260926 && env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest test_panel -v"
```

两处均12项通过；展示器另有7项回归。mock只证明工程流程，不代表真实生成效果。预审详见PRE_REVIEW.md。

## 本轮唯一真实启动

```powershell
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/candidate_registration_20260926/run_panel.py --project /mnt/data/lys/CognitiveHijacking_CognitiveDenial --output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/candidate_registration_20260926/run_live_001"
```

启动前models接口与进程身份只读核验：模型Qwen3.8-27B，API PID316818、Engine319282、占卡282313，GPU7 UUID仍为GPU-2e359d8b-f029-a43f-686b-e2eee0d1bfb7、72211MiB已用/8784MiB空闲。未启停或改变作业。运行时另存service_preflight.json、config.json、source_hashes.json及11个源快照。

请求尝试硬上限40，正常最多32；模型调用仅localhost8058，无付费API或浏览器操作。仅两个反问实现，无普通重看条件。

## 离线核对及展示命令

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/candidate_registration_20260926/audit_run.py --run research/candidate_registration_20260926/run_live_001 --output research/candidate_registration_20260926/RESULTS_AUDIT.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/candidate_registration_20260926/build_review.py --run research/candidate_registration_20260926/run_live_001 --output research/candidate_registration_20260926/review_001 --annotations research/candidate_registration_20260926/ANNOTATIONS_ZH.json
```

中文由Codex离线提供。生成HTML独立内嵌原图；归档完整实际请求，阅览版将请求base64替换为图片hash以免重复展示，system/user文字不删。候选数、完整新输出记录数和真正新增解释路径分开。

八次登记先于所有下游调用完成，阶段快照第一次tar有共享目录元数据变化警告；第二次仅归档JSON文件退出0。两份accepted内容hash独立核对相同。仅重做文件归档，没有重跑模型。最终归档使用`pack_finished_run.py`，仅遍历文件并核对打包前后hash，避免目录元数据警告。

## 完成结果与最后验证

唯一真实启动退出0，8个单元均完成。30次请求（8登记、14展开、8核验），全部HTTP200、零重试；输入78651、输出16320 token。登记14候选，展开10个完整返回、4个unexpanded；其中一个完整返回改变了候选行动。没有业务提交或actor。

本地最终测试命令及展示QA：

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/candidate_registration_20260926/test_panel.py research/candidate_registration_20260926/test_viewer.py -q --junitxml=research/candidate_registration_20260926/offline_tests_002.xml
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/qa_review.py --html research/candidate_registration_20260926/review_001/CANDIDATE_REGISTRATION_REVIEW.html --output research/candidate_registration_20260926/review_qa_001
```

19项测试通过；桌面/移动端无溢出、无断链、无远程依赖或请求、无页面异常，内嵌4张原图。实际查看desktop/b002/mobile截图，确认中文候选与OBC显示正常。图面阅览不冒充用户人工确认。

最终下载的267文件归档SHA与服务器一致，机械审计通过全部30实际请求和11源快照。下载尚未完成时有一次提前解包，被Windows文件锁阻止，运行目录未产生；等待SCP退出0并核对SHA后解包成功。该交付编排错误没有引发推理重跑或旧结果修改。

本轮停止，无后续推理、自动扩样本、GPU启停或付费API。
