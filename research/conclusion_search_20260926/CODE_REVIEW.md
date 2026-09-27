# 四方案执行前代码审查

2026-09-26。只读审查 run_search.py、search_strategies.py、config.json、PROTOCOL.md 及其调用的旧 runner/schema/prompt 接口；无模型调用、SSH 或 ARIS。仅新建本评审记录，不改实现。

## 初审 blocking 与复核

### 原任务/评分输入文件应锁到旧 checkpoint 对应版本

旧 run_live_002/source_hashes.json 锁定的是运行代码和提示等依赖，没有锁定当前读取的 public39_tasks.jsonl。新 run_arm 初版仅保存当前任务文件哈希，没有与旧 arm result.json 的 task_file_sha256 比较。

如果任务文件的隐藏评分字段发生变化，公开页面、截图和历史仍可能重建相同，但新旧评分不再同一版本。因此应在 make_app 前比较这两个哈希，变化即停止；不要仅依赖截图相等来声称任务/gold未变。

**复核关闭**：当前run_search.py已在make_app之前比较当前任务JSONL SHA与旧arm result.task_file_sha256；不等则抛错，不进入模型请求。此项修复已直接阅读确认。

## 已核对通过的静态执行路径

1. **真实公开状态重建**：每分支使用新浏览器真实重放旧历史；任何动作失败/意外提交停止；state 只规范化公开 url 的 localhost临时端口，截图 SHA 和历史均须相等。
2. **候选投影**：V1/V2 白名单复制 goal/state/history/options/pending，existing_conclusions 只含去重的精确公开 option_label；不带旧 claim/O/B/notes/ID/数量。null option 明确不支持，不由 Codex重写。
3. **独立搜索权限**：V3不给旧候选；V4不给旧候选且按全部公开 options 原顺序逐项请求。两者仍见当前选择/历史/图，不是完全去锚定。
4. **V4接口**：发送的 schema 将初始生成的 chains.maxItems 从3限制为1；LocalAPI 的 hypothesis 阶段token预算在新config中存在。解析后再检查单链数量、option_label必须等于当前公开假设选项，并保留原始响应。
5. **合并不筛选**：V4仅为新增链ID加确定性前缀，保留全部接受的候选；原2链加最多3链不超过共同核验上限5，超限直接报错，不静默丢链。新行动标签只作离线描述，不决定执行路线。
6. **共同下游**：三问答方案使用同一旧补充器，四方案均用同一核验和actor；零问/零新增也会核验和续跑。只有结构、服务或重建失败可中止，不以真假判断或评分择链。
7. **真实提交**：后续动作来自原actor；原执行器执行，直到自然submit/finish/限额。不把新结论标签直接写入选择，不以核验状态锁定动作。
8. **传输与预算**：继承已审 base.LocalAPI 的唯一127.0.0.1:8058端点、trust_env=False、禁止重定向；未知传输设置全局blocked且不重发。原actor包装异常后会按账本blocked还原LimitStop。明确暂态HTTP最多两次，均在发送前计入新账本。
9. **总量**：config设置100次模型请求尝试、300次浏览器操作、串行；所有goto、重放与后续动作计数。旧历史请求仅作来源，本轮不重采样自然前缀、不假装新初始生成。健康/models探测为只读服务检查，不是模型推理。
10. **无替代路径**：没有付费API fallback、模型下载、GPU启动或停止代码；输出独占目录和本轮独占启动锁避免换输出名质量重跑。

## 非阻塞的记录/解释注意

- search_strategies.py 的模块说明称 V3 仅设计，实际 V3由run_search.py实现；报告应解释这是模块职责而非声称V3没有执行。
- 若全局预算/服务停止发生在分支内，finally会保存当前item，但初版item状态可能仍为started；应在最终报告中按根summary stopped和账本blocked归类，不能计为未结束的后台任务。可在冻结前补显式停止状态，便于审计。
- 若某个V4假设返回结构错误，当前实现结束该分支，后续选项/核验/actor未执行；应报告“部分执行/接口失败”，不能说对称全选项探索已完整完成，也不能算作模型认定该选项无依据。
- 同一公开选项可以产生不同依据；new_action_labels为空不能证明没有解释新增，反之不为空也不证明有可见证据支持。
- 新V2和V3改变搜索提示，V4还增加独立调用次数；仅V1保持旧新Q系统提示不变，且V1仍合并了投影与去重变化。

## 执行前最后证据

审查者运行以下命令：

```powershell
& 'D:\anaconda\python.exe' -m unittest discover -s 'D:\ths_Viswork\research\conclusion_search_20260926' -p 'test_*.py' -v
```

**22 tests，OK，退出码0**。覆盖投影不带旧依据、精确公开选项去重、V1原提示不变、V1/V2同上下文、V3无旧候选、只规范化state.url、V4假设对称性/单链schema/允许全空/ID重命名、预算与本机端点配置。服务传输/未知停止/账本等继承之前已测试且按旧002哈希锁定的base实现。零新增仍核验/actor的路径已静态阅读；本次22项中没有完整真实浏览器回归，不将静态检查冒充浏览器测试。

结论：当前可见源码没有未关闭的执行blocking，可以开始已固定的四方案面板。测试通过仅证明所覆盖的工程契约，不证明模型会发现新候选或纠正任务。
