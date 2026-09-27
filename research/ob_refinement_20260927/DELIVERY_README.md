# 如何阅览与复查本轮工件

最终结论以REPORT.md为准，不能把测试通过、图中标成“原目标一致”或某版开发分数当作全量效果成立。

## 本地阅览

打开`review_final_001/OB_REFINEMENT_REVIEW.html`。它把原图、公开任务、每个已运行版本的实际阶段输出、输入提示和中文审阅嵌在一个文件内，可单独复制到另一台电脑，无需模型、项目或网络。页面只展示相应面板的真实运行，不用旧结果伪装未运行的新结果。

选择任务后，可展开各版本的“独立观察”“核验原O与B”“重新选择”，再展开“实际提示及公共输入”。原标签和AI审阅在单独的离线区域，不是在线模型输入。“原目标一致”是按原数据标签打分，不是整条解释链语义正确认证；空选项仍保留在分母内。

## 原始记录

- `runs/<版本>_<面板>/full_<任务>/<阶段>/request.json`：实际完整请求，包括原图data URI、system、user、解码和输出schema。
- 同目录`response_01.json`：实际服务响应及用量；`accepted.json`是解析结果，不是人工修订文本。
- `context.json`：便于阅读的公开文本投影；应结合request.json检查，不能单靠它证明实际发送了什么。
- 单元`result.json`与面板`summary.json`：实际静态选项和执行状态，不是浏览器提交回执。
- `runtime_source/`、`source_hashes.json`、`preflight_*.json`：运行时源码、身份与已有服务只读预检。
- `offline/`：原标签和历史v3结果，仅用于离线比较；没有被上传在线运行包。
- `audit/`和`DEV_REVIEW.md`：对抗审查和身份绑定；AI审阅不替代项目所有者的人工审核。
- `audit/v7_dev_initial.json`是保留的审查初稿，不是正式版。其pub009旁注曾把图面估值错归READ，已在`audit/v7_dev.json`更正，勘误见DEV_REVIEW第25节；没有修改模型输出或得分。展示使用更正后的正式审计。
- `FINAL_COSTS.json`：本轮所有真实尝试；既有候选的历史生成成本不在本轮账本内，但不能视为端到端零成本。

## 离线重新计分

在解压根目录，用可用Python环境执行以下只读分析。输出使用新文件名；程序拒绝覆盖旧结果。

```text
python evaluate.py --version v7 --panel dev --output analysis/recheck_v7_dev.json
python costs.py --snapshot ob_refinement_v7_dev_001.json --output recheck_costs.json
```

ZIP中的DELIVERY_FILE_MANIFEST.json给出每个包内文件的SHA256。ZIP同时保存新轮真实请求、响应和最终快照元信息，但不重复打包可从这些文件还原内容的中期/终态tgz容器。`integrity.py --snapshot`检验原tgz容器时，仍需原工作目录里的对应tgz；`finalize_evidence.py`还会核对未改动的旧实验源目录。它们的本轮实际检查结果已封存于FINAL_INTEGRITY.json，不声称仅靠这个ZIP可以重新检查未打包的历史目录。

## 重新发起实验不是离线阅览

本包不含模型权重、环境安装包、凭据，也不提供继续使用已到期截止时间/上限的绕过方法。新的真实模型运行需要新执行目录、明确服务资源授权和预先固定方案。不要覆盖本轮结果，或把FREEZE的缺失改成随便新建一个文件。线上调用仅限本轮已授权的Qwen服务；没有自动付费API回退。

本轮修改都在新的ob_refinement_20260927目录内；没有改旧ob_grounded工件、原任务、图表、答案或ARIS暂停设置。
