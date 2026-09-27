# 内网 API 接续结果

范围：原固定8基础任务 × 两图表条件 × 两模型，各自自然首次提交前状态比较B0/B2/B3。这里是真实模型、原数据集评分、safe-shell主决策/本地POST/确认链；不是原网站全流程 benchmark，也不是官方GUI系统排名。单次开发面板，无多随机种子显著性结论。

实际启动32/32个前缀，覆盖8/8个基础任务；自然checkpoint 32，与原expected action不匹配的checkpoint 6，涉及4个独立基础任务。
确认提交96/96条策略记录，其中本段新增60条，之前36条保留原文件引用且不重跑。多策略不算独立任务。

标签资格（按16个任务×条件spec计，不因两模型重复）：{'legacy_unspecified': 6, 'image_only_draft': 6, 'formal_scored_task': 4}。即正式标注4个、历史未注明资格6个、image-only待复核草稿6个；不是16个同等确认的real_gt。6个checkpoint不匹配分层为{'image_only_draft': 3, 'formal_scored_task': 1, 'legacy_unspecified': 2}。
下文‘正确/错误/恢复’及原机器字段都仅指与原数据集expected action匹配/不匹配及其变化，原评分不改。health005、env035含draft expected action；b014另有业务动作语义限定。不能把全部score errors称为完全没有可见证据支持的决定。详见CASE_NOTES和EXPERIMENT_AUDIT。

B0=不核查、执行原pending submit；B2=独立全图目标语义核验（不暴露当前选择及其历史），最多1次核验；B3=通用主动视觉核验（最多3次核验/2次crop，不强制裁剪）。B2/B3核验后执行推荐，再交普通actor最多4步自行决定和提交；并非确定性代提交。三层记录见[CASE_LAYERS.md](CASE_LAYERS.md)。

模型：Qwen3-VL-8B-Instruct（bfloat16，temperature=0，top_p=1，seed=12345，输出1024，max_pixels=1003520，原生多图）；API请求gpt-5.6-sol（medium reasoning，输出8192，high图像细节，不发送temperature，并发1）。身份按用户豁免仅记录，不能由请求名断定上游真实权重。
本段成功API响应报告的上游路由：{'mirror-gpt-5.6-luna': 80, 'gpt-5.6-luna': 7}。历史各段见原api_wire；不能把请求标签当成已验证的强模型身份。

## 分组结果

原始成功率分母为每组8个已启动前缀，保留未到hook者；括号百分比则为(该方法正确数−B0正确数)/B0正确数，两者分母不同。各模型checkpoint池独立；错误为零时恢复率N/A。clean是原对照图表，不代表模型必定判断正确。

|模型|图表条件|已启动|到hook|错误checkpoint|B0正确提交|B2正确提交（相对B0）|B3正确提交（相对B0）|
|---|---|---:|---:|---:|---:|---|---|
|M_small|official140|8|8|2|6|4（差-2；-33.3%）|6（差+0；+0.0%）|
|M_small|clean140|8|8|2|6|5（差-1；-16.7%）|6（差+0；+0.0%）|
|M_strong|official140|8|8|1|7|7（差+0；+0.0%）|8（差+1；+14.3%）|
|M_strong|clean140|8|8|1|7|7（差+0；+0.0%）|7（差+0；+0.0%）|

M_small=本地Qwen8B；M_strong=网关请求Sol；official140=误导图表，clean140=原对照。

|模型/条件/方法|错误状态恢复|正确保持|正确→错|正确→未提交|已尝试核验|核验无返回|裁剪数|
|---|---|---:|---:|---:|---:|---:|---:|
|M_small/official140/B0|0/2|6|0|0|0|0|0|
|M_small/official140/B2|0/2|4|2|0|8|0|0|
|M_small/official140/B3|0/2|6|0|0|8|0|0|
|M_small/clean140/B0|0/2|6|0|0|0|0|0|
|M_small/clean140/B2|0/2|5|1|0|8|0|0|
|M_small/clean140/B3|0/2|6|0|0|8|0|0|
|M_strong/official140/B0|0/1|7|0|0|0|0|0|
|M_strong/official140/B2|1/1|6|1|0|8|0|0|
|M_strong/official140/B3|1/1|7|0|0|8|0|1|
|M_strong/clean140/B0|0/1|7|0|0|0|0|0|
|M_strong/clean140/B2|0/1|7|0|0|8|0|0|
|M_strong/clean140/B3|0/1|7|0|0|8|0|0|

## 全部预定前缀

|序号|任务|条件|模型|自然checkpoint|B0|B2|B3|
|---:|---|---|---|---|---|---|---|
|1|b010|official140|M_small|Select Apple / 正确|正确提交|正确提交|正确提交|
|2|b010|official140|M_strong|Select Apple / 正确|正确提交|正确提交|正确提交|
|3|b010|clean140|M_small|Select Apple / 正确|正确提交|正确提交|正确提交|
|4|b010|clean140|M_strong|Select Apple / 正确|正确提交|正确提交|正确提交|
|5|b046|clean140|M_strong|Route Week 1 to the above-average revenue follow-up queue / 正确|正确提交|正确提交|正确提交|
|6|b046|clean140|M_small|Route Week 1 to the above-average revenue follow-up queue / 正确|正确提交|错误提交|正确提交|
|7|b046|official140|M_strong|Route Week 1 to the above-average revenue follow-up queue / 正确|正确提交|正确提交|正确提交|
|8|b046|official140|M_small|Route Week 1 to the above-average revenue follow-up queue / 正确|正确提交|错误提交|正确提交|
|9|health001|official140|M_small|Escalate 2018 for annual mortality peak follow-up / 正确|正确提交|正确提交|正确提交|
|10|health001|official140|M_strong|Escalate 2018 for annual mortality peak follow-up / 正确|正确提交|正确提交|正确提交|
|11|health001|clean140|M_small|Escalate 2018 for annual mortality peak follow-up / 正确|正确提交|正确提交|正确提交|
|12|health001|clean140|M_strong|Escalate 2018 for annual mortality peak follow-up / 正确|正确提交|正确提交|正确提交|
|13|env035|clean140|M_strong|Route 1980 escalation review / 正确|正确提交|正确提交|正确提交|
|14|env035|clean140|M_small|Route 1980 escalation review / 正确|正确提交|正确提交|正确提交|
|15|env035|official140|M_strong|Route 1980 escalation review / 正确|正确提交|正确提交|正确提交|
|16|env035|official140|M_small|Route 1986 mid-period review / 错误|错误提交|错误提交|错误提交|
|17|health005|official140|M_small|Route the testing-volume record to rising-volume capacity planning / 正确|正确提交|正确提交|正确提交|
|18|health005|official140|M_strong|Route the testing-volume record to rising-volume capacity planning / 正确|正确提交|错误提交|正确提交|
|19|health005|clean140|M_small|Route the testing-volume record to declining-volume outreach review / 错误|错误提交|错误提交|错误提交|
|20|health005|clean140|M_strong|Route the testing-volume record to declining-volume outreach review / 错误|错误提交|错误提交|错误提交|
|21|pub013|clean140|M_strong|Open Illinois (IL) risk detail for priority follow-up / 正确|正确提交|正确提交|正确提交|
|22|pub013|clean140|M_small|Open Illinois (IL) risk detail for priority follow-up / 正确|正确提交|正确提交|正确提交|
|23|pub013|official140|M_strong|Open Kansas (KS) risk detail for priority follow-up / 错误|错误提交|正确提交|正确提交|
|24|pub013|official140|M_small|Open Illinois (IL) risk detail for priority follow-up / 正确|正确提交|错误提交|正确提交|
|25|b014|official140|M_small|Escalate Product C as critical low-demand / 错误|错误提交|错误提交|错误提交|
|26|b014|official140|M_strong|Open a low-demand review for Product C / 正确|正确提交|正确提交|正确提交|
|27|b014|clean140|M_small|Escalate Product C as critical low-demand / 错误|错误提交|错误提交|错误提交|
|28|b014|clean140|M_strong|Open a low-demand review for Product C / 正确|正确提交|正确提交|正确提交|
|29|env005|clean140|M_strong|Route Nuclear to priority source monitoring / 正确|正确提交|正确提交|正确提交|
|30|env005|clean140|M_small|Route Nuclear to priority source monitoring / 正确|正确提交|正确提交|正确提交|
|31|env005|official140|M_strong|Route Nuclear to priority source monitoring / 正确|正确提交|正确提交|正确提交|
|32|env005|official140|M_small|Route Nuclear to priority source monitoring / 正确|正确提交|正确提交|正确提交|

## 成本、版本与结论边界

累计真实模型尝试285/800（API 149/400；Qwen 136/400）。本段API 88次：{'completed': 87, 'transport_or_response_failure': 1}；Qwen新增80次。
live浏览器691，工程291，实际总计982/4000；原任务及重放均计数。API发送前额外账本计数差0（若非零不能当成已发HTTP）。
旧预留规则的机械记账累计775.731232美元仅兼容历史字段，不代表实际消费或实价估计，也不再执行上限。镜像路由未按旧白名单结算，因此仍保留大额占位；用户声明公司内网非实际消费。研究成本以调用、transition及已报告token为准：{'api_prompt_tokens': 438983, 'api_completion_tokens': 13073, 'qwen_prompt_tokens': 231452, 'qwen_completion_tokens': 3583}。
停止状态：预定面板遍历完成，无全局停止错误；逐轨迹失败仍保留。

运行代码副本见live_panel_04/executed_sources，命令与测试见[COMMANDS.md](COMMANDS.md)，配置及仅费用豁免见[PROTOCOL_AMENDMENT.md](PROTOCOL_AMENDMENT.md)。旧提交根路径保留，不回写旧manifest、score或运行身份。
工程测试通过只说明所测试链路；暂时改对不等于持续正确提交。没有错误checkpoint时恢复率为N/A；有错误时也只对相应同模型状态池比较。真实选择/工具回执/提交是直接观察，内部信念、因果机制及复杂观察选择必要性不能由本面板单独证明。

更具体的直接观察与解释区分见[CASE_NOTES.md](CASE_NOTES.md)。本轮到此停止，不扩140对、不开发新机制。审查见EXPERIMENT_AUDIT.md（若不存在则尚未完成审查）。
