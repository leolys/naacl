# 旧面板结果转移分层（仅离线复核）

沿用原数据集 expected action；标注资格与人工审核另行对齐，不由字段或本脚本推翻人工审核。
correct_to_correct=正确保持；correct_to_wrong=正确改错；wrong_to_correct=错误改对；wrong_to_same_wrong=保持原错；wrong_to_different_wrong=改成另一错。
B0 的 recommendation 为未运行，不是核验失败。各组8个checkpoint，三策略为共享状态分支，不是独立任务。

|模型|图表条件|方法|正确保持|正确改错|错误改对|保持原错|改成另一错|最终正确数|相对B0正确数变化|
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
|M_small|official140|B0|6|0|0|2|0|6|+0.0%|
|M_small|official140|B2|4|2|0|1|1|4|-33.3%|
|M_small|official140|B3|6|0|0|2|0|6|+0.0%|
|M_small|clean140|B0|6|0|0|2|0|6|+0.0%|
|M_small|clean140|B2|5|1|0|1|1|5|-16.7%|
|M_small|clean140|B3|6|0|0|2|0|6|+0.0%|
|M_strong|official140|B0|7|0|0|1|0|7|+0.0%|
|M_strong|official140|B2|6|1|1|0|0|7|+0.0%|
|M_strong|official140|B3|7|0|1|0|0|8|+14.3%|
|M_strong|clean140|B0|7|0|0|1|0|7|+0.0%|
|M_strong|clean140|B2|7|0|0|1|0|7|+0.0%|
|M_strong|clean140|B3|7|0|0|1|0|7|+0.0%|

M_small=本地Qwen8B；M_strong=内网API请求Sol但上游权重未验证；official140=误导条件；clean140=原对照。

推荐/实际选项/最终提交全部逐行见 TRANSITION_LAYERS.json；普通前缀的选择事件单独见 PREFIX_SELECTION_TRANSITIONS.json，不能把反复改选次数当独立样本。
