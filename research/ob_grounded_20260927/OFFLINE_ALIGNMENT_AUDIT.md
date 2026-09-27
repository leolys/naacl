# 冻结后的原标签对齐审计

此工具不调用模型、不执行业务提交、不修改原数据或评分函数。模型运行代码不导入它，也不读取其输出。FREEZE.json、五份运行源、manifest以及每个公开input/image哈希都先核验。

## 第一版：保留未支持映射

ORIGINAL_LABEL_ALIGNMENT.json 使用 public_benchmark_shell_app.action_options 统一投影四领域，124条精确匹配，16个商业任务的选项与冻结公开输入不一致，因此标记unsupported，没有强行映射或评分。文件未覆盖，SHA256 e7533bba69260288bf87999fc0169dd5832eb35356eba9f2e626589c04ecd04e。

原因不是在线输入错误：商业shell有自己的task_override/action_space投影。已有2026-09-24运行时DOM审计正是从各领域原生shell导出的。本次仅阅读该历史工件和代码定位接口，没有运行ARIS技能或复跑它的HTTP提交检查。

## 第二版：按领域调用原生选项函数

- business47：business_shell.business_shell_app.action_options(task)，保留原task_override。
- public39：public_benchmark.public_benchmark_shell_app.action_options(record)，保留legacy分支。
- environment35/health19：各自shell.action_options(record)，保留原review_role，再单独添加alignment_role用于统一统计，不重写原角色。

ORIGINAL_LABEL_ALIGNMENT_v2.json 的140条均与冻结公开选项逐字、顺序一致；原资产图像哈希也逐条相同。每条都只有一个原correct选项。输出SHA256 7c656454c9b71629e5057a4d90f348a5eff9442fe221998ac38159bc4f08b443。原任务文件及五个依赖模块哈希保存在输出中。

4项本地mock验证了精确匹配、重排拒绝、重复标签拒绝和review_role原样保留；这不是模型效果，也不是新人工审核。第一次错误适配的未支持记录保留，最终离线对齐使用v2。

## 结论边界

“140条可对齐”只证明可以把模型给出的公开选项映射到原运行时标签，不说明模型140条选对，更不说明提交完成或O/B语义核验正确。原标签未被Codex改判，既有证据冲突限定不因本次映射被取消。历史Terra建议与新Qwen选择只作跨模型参照，不能当同模型核验收益。
