# 执行命令与工件索引

本机不是Git工作树根，不能提供有效git diff。新增实验文件集中于本目录；旧实验、任务、原图、gold、评分器未改。本轮在线依赖的逐文件SHA和运行结束检查在每个run/source_hashes.json及summary.json。

## 远程真实运行入口

统一通过用户配置的`ssh hexin_2007_K_root`执行。工作目录前缀均为：

`/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/conclusion_search_20260926`

解释器：`/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python`。

涉及浏览器的命令前置：

```sh
env PYTHONDONTWRITEBYTECODE=1 \
PLAYWRIGHT_BROWSERS_PATH=/mnt/data/lys/model_services/qwen3_8_27b/browsers \
LD_LIBRARY_PATH=/mnt/data/lys/model_services/qwen3_8_27b/browser_libs/usr/lib/x86_64-linux-gnu
```

以下参数中的`PROJECT`、`HERE`、`PRIOR`仅为阅读缩写，不是记录中向模型提供的变量：

```text
PROJECT=/mnt/data/lys/CognitiveHijacking_CognitiveDenial
HERE=PROJECT/research/conclusion_search_20260926
PRIOR=PROJECT/research/alternative_conclusion_20260926/run_live_002

python -u HERE/run_search.py --project PROJECT --prior-run PRIOR --output HERE/run_live_001
python -u HERE/run_additional.py --phase chart --project PROJECT --parent-run HERE/run_live_001 --prior-run PRIOR --output HERE/run_chart_001
python -u HERE/run_additional.py --phase transfer --project PROJECT --parent-run HERE/run_chart_001 --prior-run PRIOR --output HERE/run_transfer_001
python -u HERE/run_contract.py --project PROJECT --parent-run HERE/run_transfer_001 --prior-run PRIOR --output HERE/run_contract_001
python -u HERE/run_isolated.py --project PROJECT --prior-run PRIOR --output HERE/run_isolated_001
python -u HERE/run_joint.py --project PROJECT --output HERE/run_joint_001
```

前三、第五、第六命令退出0；第四命令退出1：GUI已完成，静态调用前错误检查派生JSON字节hash。错误及回溯保留在summary.json。新第五版本以严格语义/源字节双校验工程续接，不改第四版状态。各启动锁防止换输出路径不计费重跑，累计账本完整继承。

下载后离线汇总：

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conclusion_search_20260926/summarize_results.py --output research/conclusion_search_20260926/RESULTS_SUMMARY.json
```

## 本机测试

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/conclusion_search_20260926/test_search_strategies.py research/conclusion_search_20260926/test_run_search.py research/conclusion_search_20260926/test_prepare_transfer.py research/conclusion_search_20260926/test_additional.py research/conclusion_search_20260926/test_contract.py research/conclusion_search_20260926/test_isolated.py research/conclusion_search_20260926/test_joint.py research/conclusion_search_20260926/test_build_search_review.py -q --junitxml=research/conclusion_search_20260926/offline_tests_final.xml
```

实际51 passed，退出0。不能递归收集整个目录：runtime_source含旧测试快照，会与新模块重名。早期离线测试逐版22/32/33/37/40项记录均保留；最后新增反定制词检查初版误将red作为required的子串，改为词边界后通过，未据此改提示。远端新增隔离3项、联合2项unittest也分别通过；不会调用模型。

## 可审查的实际文件

- config.json：模型、token、解码、100/300累计安全边界。
- run_search.py、search_strategies.py：四个首轮方案；run_additional.py：完整原图与静态迁移。
- run_contract.py：输出契约；run_isolated.py：只在GUI生成阶段隔离执行承诺，同时续接未运行静态契约。
- run_joint.py：最后四次候选层面联合发现；已知静态readonly value投影缺陷保留并披露，不推广为正式实现。
- 各run/*/*/request_01.json、context.json、image_identity.json、response_01.json、raw.json、accepted.json：真实模型输入输出。`accepted`只表示接口接纳，不表示正确。
- 各GUI分支result.json、state_*.png/json、actor_*/、private/submissions.jsonl：动作前后及真实提交。private评分材料仅离线评估，不进入被测模型。
- 各run/runtime_source：当次运行源码，不给旧输出追写当前版本。
- PROTOCOL及各ADDENDUM：每步开发变更和范围；各CODE_REVIEW/SEMANTIC_REVIEW为独立审查，不是人工确认。

## 展示重建

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conclusion_search_20260926/build_annotations.py
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conclusion_search_20260926/build_search_review.py --run research/conclusion_search_20260926/run_live_001 --chart-run research/conclusion_search_20260926/run_chart_001 --transfer-run research/conclusion_search_20260926/run_transfer_001 --contract-run research/conclusion_search_20260926/run_contract_001 --isolated-run research/conclusion_search_20260926/run_isolated_001 --joint-run research/conclusion_search_20260926/run_joint_001 --annotations research/conclusion_search_20260926/ANNOTATIONS_ZH.json --output research/conclusion_search_20260926/review_final_001
```

只运行离线代码，不调用API。输出目录若存在会拒绝覆盖。HTML内嵌图像，单文件可在另一电脑离线打开；模型文字与完整请求折叠展示，中文翻译由Codex离线提供。

展示QA实际执行：

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/conclusion_search_20260926/qa_review.py --html research/conclusion_search_20260926/review_final_001/CONCLUSION_SEARCH_REVIEW.html --output research/conclusion_search_20260926/review_qa_001
```

本机Edge headless，1440×1000及390×844：无损坏锚点、无远程依赖或请求、无脚本异常、无横向溢出；11个字节去重内嵌图像。HTML约12.2MB。QA.json和三张截图保留，Codex已实际查看桌面/手机截图。

最后只读健康检查HTTP200，原模型API PID316818、Engine319282及占卡PID282313继续在运行，启动时间分别仍为10:59:49、11:00:46、10:48:06。没有停止这些进程。全部六阶段153条源码快照hash经独立审查匹配；本轮模型调用止于89次。

文件归档阶段两次首次tar遇到Ceph目录“file changed as we read it”，仅重试归档，第二次成功；这些是文件读取/传输，不是模型失败重跑。交付前只输出文件名的凭据模式扫描未发现匹配项。
