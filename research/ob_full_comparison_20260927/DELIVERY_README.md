# 如何阅览和复核

## 只想看结果

直接双击`review_final_002/OB_FULL_COMPARISON_REVIEW.html`。这是约64MB的独立HTML，包含所有140张任务图及六版真实记录；可复制到别的电脑，不需项目、服务器、Python或网络。初次加载可能稍慢。

顶部是六版主表及24/116子集。下方搜索任务编号；可筛选v5等方案相对普通方案的新增相合、流失相合、空选项、接口失败。每条任务都有六张结果卡。逐层展开“观察／核验／重新选择”，可看完整实际文字输入、O/B、输出schema、解码参数、接受输出和原始响应。图像使用同一原图，并有请求/图像哈希。

界面、总结和版本说明为中文；模型原文保留英语，没有调用翻译API。评分标签与任务家族明确标记为离线信息，不是新增给模型的任务提示。本轮没有新增反问链或网页提交。

建议从pub001、b017、health005的改善开始，再看env007的“标签相合但理由不足”、env001和pub035的退化。所有失败都能筛选，不只展示成功样本。

## 想审数据和源文件

- `REPORT.md`：完整统计、转移、成本、版本差异、证据解释和限制。
- `FINAL_ADVERSARIAL_REVIEW.md`：独立AI审查，不能代替项目所有者人工确认。
- `analysis/final_001/`：六版各自完整评分，原140/24/116分母、三种参照转移、家族分层、完整性审计。
- `captures/final_001/runs/<version>/full_<task>/<stage>/`：实际request.json、context.json、response_01.json、accepted.json或failure.json；每配置result.json。
- `captures/final_001/workers/<n>/ledger.json`：实际调用账本；失败和服务控制已计入。
- `data/`：固定140公开输入、图；`offline/`：不发送给模型的原标签和历史参照。
- `RUNTIME_SEAL.json`：封存在线源码/输入身份；`checks/FINAL_RESOURCE_CHECK.json`：资源验收；`TEST_RESULTS.md`、`qa_final_002/`：工程与展示检查。

证据ZIP保留本轮目录及少量相邻历史只读源文件，以支持原提示/标签哈希对照和离线评分复现；不要扁平化目录。离线命令见`EXECUTION_COMMANDS.md`。无需为阅览或复核启动模型，也不要执行dispatch/run/cleanup来重做本轮。

没有修改原标签、旧结果或封存提示。模型输出保留所有截断、ID大小写失败、空选项和退化。原140分母上的相合数不是语义人工正确率，不是动态任务恢复率。
