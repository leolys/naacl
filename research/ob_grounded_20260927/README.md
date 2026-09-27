# O/B核验：固定版本的140条应用诊断

这份交付围绕原观察O和读法B进行核验，没有恢复O+B⇒C整链判定器，也没有自动学习持久规则。核心流程是：**候选不可见的同图读取 → 原O/B逐项核验 → 根据公开选项重新选择**。这三个阶段的输出分别保存，不拿最后选项掩盖中间判断。

终态140条：78条与原目标相合、26条原陷阱、8条其他选项、21条null、7条接口失败。全轮483次已有本地模型请求，0付费API、0业务提交。已经跑完有界诊断，**尚未达到全量稳定核验效果**。

## 建议从这里看

- `review_full_002/OB_GROUNDED_REVIEW.html`：140条的单文件展示；复制此HTML到别的电脑即可离线打开，图像全部内嵌。不需要服务器、项目或模型。
- `REPORT.md`：最终数字、具体有效和失效例子、能支持与不能支持的结论。
- `PROMPTS_ZH.md`：冻结提示的中文说明；实际英文在`prompts_v3.py`及每次真实request中。
- `SEMANTIC_REVIEW_SUMMARY.md`：21个固定家族代表的定性审查，**不是**140条人工准确率。
- `NEXT_ACTION.md`：此次停止点及后续应优先解决的问题。

展示中可按任务编号搜索或按运行状态、原标签对齐筛选。建议先看pub030/b003的局部正例，再看health005、env033、health006、env008；随后看pub005与pub021，区分真实缺口、错误支持与最终未选择。原始模型文字、中文摘要、Codex旁注三者分开显示。

尾部pub032/pub035/pub038尤其适合看下一步瓶颈：数值锚点已经可见，却未转化成各自坐标下的比较区间。具体边界见`FULL_REVIEW_FINAL_TAIL.md`；这些是事后诊断例，不替代固定抽样。

## 怎样理解结果

“有依据支持／存在反证／证据不足”是**被测模型对O或B的判断**，不是人工认证。接口检查通过只证明输出格式、记录覆盖等工程条件；独立的文件审计核对请求和工件身份，也不证明内容正确。

本轮应用的是official140原指定的140张图，不是140对双条件网页实验。新选项只是静态重新选择，业务提交为0。与原目标标签相合不等于O/B全对，也不等于Agent已执行成功。旧Terra建议与新Qwen输出跨模型，不是同模型核验增益。

原公共输入有已知提示性内容：b003/b006/b008指定标注份额，pub019原图含Clean choropleth等说明。全部原样保留并披露，不按结果改图、排除或改gold。env008保留原标签与既有evidence_conflict限定，Wind的视觉支持没有被抹去。

## 可复核的原始记录

- `data/`：本轮所有公开输入与原图；`manifest.json`记录候选来源和身份。
- `runs/v1_dev`、`v2_dev`、`v3_dev`：三次固定开发版本，全部失败保留。
- `runs/v3_confirm`、`runs/v3_full`：冻结确认与全量；full中复用的12条指回confirm，不算新调用。
- 每阶段`request.json`是实际发送消息和图片字节，`response_01.json`是实际响应，`accepted.json`仅代表接口接受，`failure.json`是原拒绝原因。
- `FINAL_COSTS.json`：全部请求尝试、用量及来源账本；`FINAL_ACCOUNTING.json`是分阶段计数。
- `FULL_LABEL_AGREEMENT.json`：原选项标签的离线映射，不是原scorer或新人工gold。
- `FINAL_ARTIFACT_AUDIT.json`、`SNAPSHOT_LINK_AUDIT.json`、`FINAL_COMPLETION_AUDIT.md`：最终工程核对及边界。
- `FULL_REVIEW_PARTIAL*.md`等：对抗审查，保留撤回的审阅误读。早期partial路径如何对应最终文件见`REPRODUCTION.md`。

中文由Codex离线整理，未调用翻译API。原O/B沿用精确对应中文，新B理由及最终理由提供中文摘要；逐O核验依据仅部分翻译，实际覆盖数列在展示页，英文始终保留。翻译不是额外模型证据。

## 运行与重现

本轮只调用已有服务器本机Qwen3.8-27B服务，未新增付费API、下载权重或启停其他GPU作业；ARIS保持暂停。实际命令、版本和回归结果见`EXECUTION.md`、`CODE_CHANGES.md`与`FREEZE.json`。

离线重算及展示命令见`REPRODUCTION.md`。旧配置带截止时间与调用上限，不应直接修改后重跑；如需新的真实实验，应另建版本、预算和结果目录，保留本轮工件。
