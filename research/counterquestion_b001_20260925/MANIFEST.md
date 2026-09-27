# b001 本轮工件索引

| 工件 | 内容 |
|---|---|
| PLAN.md / config.json | 用户指定单样本、3 个逻辑调用、9 次尝试及 1 美元估算上限 |
| prompts.py / run_diagnostic.py | 通用反问、问题关联候选、新旧链核验实现 |
| run/seed_input.json / run/chart.jpeg | 继承的公开任务和原解释，未修改原图 |
| run/counterquestions/ | 第一阶段完整请求／响应及三个反问 |
| run/competitors/ | 第二阶段真实反问输入／新候选输出 |
| run/verification/ | 第三阶段独立规范化候选核验 |
| run/result.json / run/budget.json | 阶段记录、来源映射、核验、规则状态、3 次实际尝试和估算 0.137255 美元 |
| run/runtime.json / run/runtime_source/ | 真实执行版本，原输入来源与冻结代码 |
| run/reading_zh.json | 原生中文逐字段阅读层，0 次翻译 API，保留模型可能错误 |
| tests/offline_receipt.xml / tests/offline_receipt_v2.xml | 原 35 项与修复后 45 项离线测试，均保留 |
| live_wire_check.json | 三次实际请求上下文、反问依赖、图片与源码一致性检查 |
| reviews/ | 同家族、暂定的运行前、运行后和展示审查 |
| REPORT_ZH.md | 中文过程解释与局限，未将保持选择当成纠错 |
| B001_COUNTERQUESTION_REVIEW_v2.html | 最终单文件离线展示：原图、中文过程和完整中英文 JSON |
| view_provenance_v2.json / browser_check_v2.json | 最终显示来源、无外部请求与无水平越界检查 |
| B001_COUNTERQUESTION_REVIEW.html / view_provenance.json / browser_check.json | 保留的初版展示；初次检查只验加载，后续发现原尺寸图越界并在 v2 修正 |
| PACKAGE_INDEX.json / PACKAGE_CHECK.json | 打包后生成的逐文件哈希及完整性回执 |

源码中没有保存 API 密钥。离线展示可以跨电脑打开；在线运行代码的绝对来源路径是运行时记录，不代表另一台电脑无需配置依赖就能重新发起付费请求。
