# 新版执行命令

本地新增目录：`D:/ths_Viswork/research/proposal_completion_20260926`。

远程新目录：`/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/proposal_completion_20260926`。

没有改写原实验目录；不使用ARIS、不创建模型服务、不改任何GPU占用。服务使用用户既有Qwen3.8-27B，127.0.0.1:8058。执行前只读核对模型列表、API/Engine PID316818/319282和启动时间，及GPU7 UUID；占卡PID282313和其他作业保持不变。

## 公开输入准备

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/prepare_inputs.py --project D:/ths_Viswork --output research/proposal_completion_20260926/inputs
```

生成四例context、初始链副本、完整PNG、manifest；所有来源hash均已核对。静态只深拷贝完整task，不删readonly value。输入打包后上传新目录，远端提取前检查inputs不存在。

## 工程测试

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' -m pytest research/proposal_completion_20260926/test_pipeline.py research/proposal_completion_20260926/test_builder.py -q --junitxml=research/proposal_completion_20260926/offline_tests_final.xml
```

实际18 passed，退出0；其中12条协议/数据流测试，6条阅览器测试。远端使用既有评测环境另运行`python -m unittest test_pipeline -v`，12项通过。测试含mock模型调用，mock不作为真实生成效果。

## 唯一真实启动

```powershell
ssh hexin_2007_K_root "env PYTHONDONTWRITEBYTECODE=1 /mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -u /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/proposal_completion_20260926/run.py --project /mnt/data/lys/CognitiveHijacking_CognitiveDenial --output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/proposal_completion_20260926/run_live_001"
```

旧预算不沿用。本新固定面板最多24请求尝试，0浏览器操作；16正常调用是理论最大值，不是必须用满。只对明确暂态HTTP失败允许至多1次重试；未知传输结果全局停止，不做质量重试。每一请求保存system/user、JSON schema、完整base64图像、原响应和用量。accepted只表示结构/关联通过。

## 离线审查与展示

```powershell
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/audit_results.py --run research/proposal_completion_20260926/run_live_001 --output research/proposal_completion_20260926/RESULTS_AUDIT.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/builder.py --run research/proposal_completion_20260926/run_live_001 --output research/proposal_completion_20260926/review_001 --annotations research/proposal_completion_20260926/ANNOTATIONS_ZH.json
& 'D:/ths_Viswork/research/competing_rules_20260923/.venv/Scripts/python.exe' research/proposal_completion_20260926/qa_review.py --html research/proposal_completion_20260926/review_001/PROPOSAL_COMPLETION_REVIEW.html --output research/proposal_completion_20260926/review_qa_001
```

上述离线工具不调用模型；输出目录若已存在会拒绝覆盖。展示器构建时依赖上一版通用HTML helper，但产出的HTML内嵌图像，可独立打开。中文注释由Codex离线完成，不消耗API，也不冒充模型输出或人工确认。

## 实际完成记录

- 唯一真实启动退出码0，共8次请求：4次提案生成、4次旧链核验；全部HTTP200，未重试。四例提案均为空，展开阶段未调用。
- 输入20626 token、输出2905 token；0次浏览器操作、0次业务提交、0次付费API调用。
- 归档首次tar打包因共享目录报告`file changed as we read it`退出1；仅重试文件打包，第二次退出0。没有因此重跑实验或调用模型；下载后对实际请求、图像和源码哈希逐项核对。
- 离线Edge桌面与移动端展示检查通过：无断链、无外部资源或远程请求、无页面错误、无水平溢出，内嵌4张图；截图已人工式视觉查看。这里的检查不等于用户人工审核或研究效果成立。
- 独立审查见`RESULT_REVIEW.md`，明确区分零提案、未进入展开、旧链核验与真实业务纠正。本轮停止，不追加推理。
