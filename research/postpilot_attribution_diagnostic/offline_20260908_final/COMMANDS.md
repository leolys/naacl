# 本轮命令与工件

工作目录：`/hipilot/sharestorage/lys/CognitiveHijacking_CognitiveDenial`。
全部是离线读取、派生报告与普通单测；无被测模型服务/浏览器调用，无新下载。

## 执行单定位

```bash
sed -n '1,260p' Codex_PostPilot_Attribution_Diagnostic.md
rg --files --hidden -g '!.git' -g '!external_tools' -g '!node_modules' -g '!model_cache' -g '!*.json' -g '!*.jsonl' -g '!*.png' -g '!*.jpeg' -g '!*.jpg' | rg -i '(post.?pilot|attribution|diagnostic|Codex.*\.md$|AGENTS\.md$)'
rg --files --max-depth 3 -g '*.md' -g '!external_tools/**' -g '!.git/**' | rg -i '(codex|post.?pilot|attribution|review|audit|human|manual)'
```

第一条exit2，指定文件未找到；后续检索列出已有Codex执行文档和旧诊断代码，但没有所指定文件。没有从不存在的文件推导四任务。

## 离线复核与测试

```bash
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m unittest research.postpilot_attribution_diagnostic.test_offline_audit -v
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -m research.postpilot_attribution_diagnostic.offline_audit --output research/postpilot_attribution_diagnostic/offline_20260908_final
```

测试exit0，4项通过（0.007秒）；离线主程序exit0，2026-09-08T15:50:08.401923+00:00生成主JSON工件。32个checkpoint、96条旧策略记录、16个原spec对齐，149个历史API尝试已盘点。输出目录必须是新目录，防止覆盖旧结果。

早期同命令输出到offline_20260908_v1，3项测试通过，但简要历史计数读的是旧策略字段，未体现H_base替换后的4条回执；原始完整请求保留无误。修复后新增1项针对实际字段的测试，输出到本final目录。两个版本都是离线工程产物，不是额外实验。

历史审核抽取（终端输出随后通过apply_patch原样保存为REVIEW_RECORDS.json）：

```bash
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import json; from research.postpilot_attribution_diagnostic.offline_audit import collect_review_records,read,DEFAULT_RUN; print(json.dumps(collect_review_records(read(DEFAULT_RUN/"TASK_MANIFEST.json")),ensure_ascii=False,indent=2))'
```

exit0，17条来源记录，涉及全部8题；含复制记录，不能按17次独立审核计数。

16个公开投影对齐的实际只读命令（stdout通过apply_patch保存为PUBLIC_PROJECTION_ALIGNMENT.json）：

```bash
env PYTHONDONTWRITEBYTECODE=1 /hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python -c 'import json,pathlib; from research.decision_evidence_audit.core import public_task_projection; a=json.load(open("research/postpilot_attribution_diagnostic/offline_20260908_final/RAW_SPEC_ALIGNMENT.json")); out=[]
for r in a:
 raw=json.loads(pathlib.Path(r["source"]).read_text().splitlines()[r["line"]-1]); p=public_task_projection(raw,task_alias=r["public_task"]["task_alias"]); out.append(dict(task_slug=r["task_slug"],arm=r["arm"],public_projection_matches=p==r["public_task"],source=r["source"],line=r["line"],comparison="All seven public projection fields; exact equality including option order."))
print(json.dumps(out,ensure_ascii=False,indent=2)); assert all(x["public_projection_matches"] for x in out)'
```

exit0，16/16一致。这里只调用既有core的纯公开投影函数，不创建环境或执行浏览器。

最终单测stdout/stderr见test_results.log；追加审核抽取函数后再次执行4项测试，exit0。`git ... status --short --untracked-files=no`在工作前后均为空；新增文件位于本诊断目录，未暂存或提交。

## 代码范围

- 新增`research/postpilot_attribution_diagnostic/offline_audit.py`：只读JSON和图片，不导入在线模型客户端、浏览器、执行器或scorer。
- 新增`research/postpilot_attribution_diagnostic/test_offline_audit.py`：转移分类、空输出、解码像素比较、实际历史字段测试。
- 只新增本目录报告；不修改旧manifest/score/模型响应/原图/任务spec。
- 未修改原runner、h_base、policies、模型/图像处理配置。
- 使用analyze-results做分层、experiment-audit做只读独立审查。run-experiment只用于明确复用现有环境及资源边界，没有启动运行。
