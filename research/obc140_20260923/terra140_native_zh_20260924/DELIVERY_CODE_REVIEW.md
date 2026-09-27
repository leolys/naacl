# 最终交付代码审查

日期：2026-09-24  
范围：只读检查 `make_view.py`、`finalize_summary.py`、`verify_delivery.py`、`package_delivery.py`、`READ_ME.md`。未检查新增语义样本，未调用模型/API，未修改冻结代码、队列或结果。

## 结论

未发现 P1。发现以下三个可直接证实的 P2 交付门禁问题。

### P2 — `verify_delivery.py` 可在固定队列未终态时写出 `engineering_status: PASS`

`verify_delivery.py:64-72` 的 PASS 条件只有“尝试元数据不缺失”和“当前记录所需中文映射不缺失”。脚本不读取 `run/run_state.json`，也不要求 140 条任务均达到允许的终态。因此运行中的占位记录没有新增模型文本可译时，并不会阻止 PASS；当前未完成计数可能被一份名为 `delivery_checks.json` 的 PASS 工件误当成交付完成证明。

建议在写 PASS 前要求固定清单完整、全局状态属于明确允许的最终状态，并逐条确认 proposal／generation／verification 已终态；保留失败／invalid 可以，但不能把 `not_run`／`running` 当成最终交付通过。

### P2 — 归档未绑定最终检查或最终 HTML 的离线浏览验证

`make_view.py:154-191` 的浏览器检查是可选参数；`package_delivery.py:16-17` 只要求最终文件名的 HTML 存在，随后既不要求 `delivery_checks.json`／`browser_check.json` 为 PASS，也不核对它们与待打包 HTML、当前 records 或 `view_provenance.json` 的哈希／新鲜度。`run.lock` 能阻止正在活跃的运行立即打包，但不能阻止先前生成的陈旧最终 HTML／REPORT 在锁释放后被归档，也不能证明单文件在另一台机器上无外部请求、无脚本错误、140 张图均可加载。

建议让打包入口硬性验证：运行已终态、交付检查 PASS、最终浏览器检查 PASS（140 条、零外部请求、零脚本错误），并把这些检查绑定到当前 HTML 与记录快照的摘要。

### P2 — “归档无凭据”的扫描覆盖不足，却在清单中作无条件声明

`package_delivery.py:19-36` 会递归收集交付目录及 review trace；`37-41` 只扫描 `.json/.md/.txt/.py/.html`，且只识别 `sk-...` 一种形态。其他被实际收入归档的文本类型不会扫描（当前目录已有 5 个 `.xml` 测试报告），非 `sk-` 的 bearer token、API key 字段值、私钥块等也不会命中。尽管如此，`45-46` 无条件写入“no API credential”。因此代码没有充分建立它所声明的安全不变量。

建议对所有可解码文本候选统一扫描，并覆盖常见 Authorization/Bearer、API key、私钥块和环境文件模式；不可解码或未扫描的文件应由明确允许清单控制。清单中的“无凭据”声明只能在完整扫描通过后写入。

## 已核对且未发现 P1/P2 的口径

- `make_view.py` 深拷贝英文记录，中文存入独立 `translations.items`；指定代码中未见中文覆盖原英文。
- generation invalid 草稿有显式“未通过结构校验”提示；长度截断与引用／校验失败另列，不会计入 generation／verification completed。
- 页面标签、报告和 README 都明确说明 `active` 只代表规则状态，不等于 implication 或行动推荐被接受。
- 新请求尝试、复用 b001/pub013、估算账本和实际账单未知值分别记录；未见把历史复用调用计入新请求或把估算写成实际扣款。

## 验证边界

审查时队列仍在运行，`run.lock` 存在；最终 HTML、`browser_check.json` 和 `delivery_checks.json` 尚不存在。按要求未运行完整最终归档或浏览器验证，也未把当前计数当成最终计数。
