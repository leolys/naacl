# 执行记录

本轮全部在本地 Windows 项目中进行；不使用远程 GPU、不下载模型、不改旧140结果。Python 为既有 `research/competing_rules_20260923/.venv/Scripts/python.exe`。凭证仅经进程环境提供，不写命令文件或结果包。

## 真实请求前

- 资产审计：原图/公开任务/旧初始链可用；clean原图与公开HTML可用，公开字段一致。无被测模型请求。
- 方法第一轮审查 REVISE；最小修改后第二轮方法/协议 PASS（same-family/provisional）。研究评分仍 REVISE，不扩方法。
- 原始 `python -m pytest <absolute tests path> -q --junitxml=tests/offline_receipt_root.xml` 在项目根目录、默认插件自动加载下没有输出，已对自己创建的 session 发送中断，退出1；不计通过，未启动模型。
- 使用本实验工作目录与 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 重跑这组同步测试：`python -m pytest tests -q --junitxml=tests/offline_receipt_isolated.xml`，11通过；3个既有Flask/itsdangerous弃用提示。
- 加入固定配置/图路径守卫后：`python -m pytest tests -q --junitxml=tests/offline_receipt_final.xml`，12通过，3个同类提示。网络在测试中被禁止。
- `python runner.py --prepare --output <experiment>/prepared`：6条件准备，0请求。随后runner的固定配置检查有修正，此快照作为前期版本保留。
- `python runner.py --prepare --output <experiment>/prepared_final`：最终版6条件准备，0请求。live将使用新的run目录独立保存实际导入源快照。

上述通过仅是工程检查，不是语义正确性、研究效果或有效竞争确认。

补充两个必要回归后，`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q --junitxml=tests/offline_receipt_release.xml`：14通过，3条既有弃用提示，3.69秒。新增覆盖全panel预算上限及已发送结果未知时全panel停止。既有12项回执保留，不覆盖。

## 真实运行

在用户本轮明确授权、方法/工程门槛通过后，执行 `python runner.py --live --output <experiment>/run`。凭证只在进程环境，退出时移除；源、提示、配置、manifest 在首请求前由runner快照。进程退出0，summary状态为completed_with_case_failures，不是所有任务成功。

18次真实请求，18 HTTP200/stop；无失败重试、质量重采样或翻译调用。5条件完成全部阶段，env001在第2阶段因task_048图证引用格式被拒绝，第3阶段未运行。全轮估算0.6804625美元；未使用剩余额度。业务浏览器/GPU均0。

`python delivery.py audit`：实际18请求的固定提示、完整图字节、上下文与真实问题传递匹配；原资产与runtime源保存检查PASS。此审计不验证语义。

运行后方法审查与原生翻译sub-agent都返回服务usage-limit错误。没有重试、降低审查强度或购买额度；其余离线报告由root完成，标为本地解读，不伪造sub-agent结论。正式结果到主张门槛REVIEW_UNAVAILABLE。已发现的health001编号错指与env001证据接口失败均原样留档，没有追加修复后推理。

## 离线交付

- `python delivery.py render`：使用既有render-html技能helper生成自包含HTML，内嵌六张未改字节的原图与完整结果JSON。
- 浏览器默认Chromium路径不存在，首次检查失败；未下载浏览器。改用本机已有Edge后执行 `python delivery.py browser`：6图均加载、无脚本错误/外部请求、展开全部记录后无横向溢出。主agent查看了截图。此变化只影响离线交付脚本，不改实际推理源。
- `python evidence_check.py <experiment> --batch EVIDENCE_CLAIMS.json`：6条引用存在检查通过，只证明记录存在，不证明语义主张。
- `python archive_delivery.py`：运行前审查与实际失败回执留档，245工件索引，凭证模式扫描0匹配；未增加模型调用。
- HTML人工可读，但fresh展示审查也无法使用受限reviewer路线，明确REVIEW_UNAVAILABLE。本地浏览器PASS不是审查者PASS。
