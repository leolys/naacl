# 实际离线执行命令

工作目录为 `/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。无curl模型请求、GPU查询或启动、浏览器启动、下载/安装。

已执行：

```bash
set -o pipefail
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/prepare_offline.py | tee research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/offline_preparation.log
```

首次退出1：提取原纯parser AST执行时缺少typing.Any定义，未产出raw_failure_audit.json或panel。仅补齐新离线脚本导入后用完全相同命令（日志换 `offline_preparation_retry1.log`）再次执行，退出0：

```text
OFFLINE_PREPARATION_OK 6 historical cases; raw-label equality 6/6; 3993 arithmetic checks; 8 states; 24 pending units; 0 new model calls; 0 browser transitions
```

stderr有现存Pillow的getdata弃用提示，不影响结果。日志保留首轮失败，没有把CPU代码错误计为模型错误。脚本只读取现存run/图像并向本新目录独占创建工件，重复执行会拒绝覆盖。它没有模型/浏览器客户端入口。

脚本重用原run已有代码指纹做版本比对（不新增hash方案）；只从匹配的policies.py提取纯解析函数，不运行已经改变的runner/models。原始结果和后续用户未提交修改均保留。实际图像另由view_image只读检查，未修改原图。

24单元真实命令尚未提供：新的选择隐藏边界适配与实际提交测试还没有实现，且新模型/GPU权限未获批。不能拿本离线准备器当成可运行live实验的证明。预算申请见EXPERIMENT_PLAN.md。

最终只读测试另行实际执行：

```bash
set -o pipefail
PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/test_offline_preparation.py 2>&1 | tee research/decision_evidence_audit/revisions/20260906T145758Z_offline_panel/offline_tests.log
```

退出0，6/6通过：历史规则/原label、八状态因子/顺序数量、选择隐藏/像素一致、在线payload不含evaluator键、B4两arm原理由一致、split分组与运行资格声明。没有新模型推理或浏览器动作。测试不证明还未实现的跨轮投影、实际DOM选项排序或提交链路；这些不得据本日志标为完成。

独立审查之后，只把状态执行排程改为交错；初稿control_panel/EXPERIMENT_PLAN用 `cp -n` 保存在pre_schedule_review/，匹配1342Z的原policies.py另copy为B3_REFERENCE.py。没有更改24个model_payload。扩展同一只读测试检查交错及每4状态的规则/正误平衡后再次执行上述测试命令，日志换offline_tests_final.log，退出0、仍6/6通过。没有重跑准备器或任何模型/浏览器实验。

首次准备器stdout为空（offline_preparation.log），stderr当时只在工具输出中；此处准确转录末行，不冒称完整错误已经由tee捕获：`NameError: name 'Any' is not defined. Did you mean: 'any'?`。修复/重试细节见前文。
