# 通用反问竞争解释：六条件开发诊断

打开 COUNTERQUESTION_GENERAL_REVIEW.html 可离线阅读六张原图、中文分析和完整原始JSON。它是新独立文件，不改旧140展示。

- REPORT_ZH.md：中文证据报告，明确区分模型记录与本地解读。
- PROTOCOL.md / manifest.json / config.json：预先固定范围、任务和预算。
- prompts_v2.py / PROMPT_GUIDE_ZH.md：实际英文通用提示与中文说明。
- runner.py：固定面板实现；原历史代码只读依赖。
- run/cases/*/：完整request/response/raw/accepted、seed、候选、核验、规则状态。
- run/runtime_source/：实际运行源快照；run/runtime.json记录环境。完整历史工程并未复制，不宣称ZIP可在无Python依赖时直接推理；展示HTML自包含。
- tests/：14项离线回归及各版本回执。
- reviews/：运行前方法与代码审查；运行后复核REVIEW_UNAVAILABLE，不存在虚构的PASS。
- LOCAL_ISSUES.md：health001文本ID错指、env001证据格式，以及视觉核验风险。
- NEXT_ACTION.md：停止边界与剩余问题。

本轮18请求、估算0.6804625美元；5条件完成核验，1条件候选格式失败；未真实执行任何网页动作。模型输出不等于人工真值，工程通过不等于方法有效。

历史结果不覆盖。不要直接重跑live目录；新的请求需要新的有界任务和预算，不继承本轮剩余授权。
