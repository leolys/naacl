# 控制通过后的调度错误与同面板衔接

`live_panel_01` 于 2026-09-07 21:13 CST 停止。两个后端各完成四个公开 Route 控制与两个双图顺序控制，全部通过；各使用 8 次生成调用，各 22 次浏览器 transition、4 次真实 localhost POST。加入更早身份停止的 1 次 API / 4 次 transition，累计 17 次真实调用、48 次 transition。

正式 manifest 的 unit 已含 `status: not_run`。运行时 `panel.py` 的 `dict(**unit, status="starting", ...)` 因重复关键字抛出 TypeError，发生在创建第一个 prefix 记录、任何图表页面或模型请求之前。用该 manifest 直接执行同一表达式可离线复现。此前 fixture 没有 status，故 71 项测试未发现该缺口；不是模型不遵循流程。

最小修复为 `{**unit, "status": "starting", "checkpoint_reached": False}`；不改原 manifest。fixture 加入同字段，并添加读取真实 manifest 的调度回归。actor/verifier、图像尺度、动作与提交规则不改。

此前的 `live_panel_01` 保留为基础设施停止；其中 96 条记录全部是未运行，不是 96 次策略失败。原 stop 仅保存 TypeError 类型；具体原因由上述独立复现证实，不追写旧运行的源身份或 traceback。

后续同一获授权面板用 `MODEL_CONFIG_scheduler_fix.json`，在新目录启动尚未执行的 32 个固定前缀。显式引用已通过的控制工件，不重做这些控制，不把控制响应当新任务动作，也不放入在线任务历史。新增可选的普通控制承接分支仅检查既有结果完整通过、配置相同及预算已承接；默认仍执行控制。无法承接则停止，不暗中跳过。

调用编号继续：API 从 request_0010，本地从 request_0009。API 累计已用 9 / 400，本地 8 / 400。已知 API 用量按保守费率上界共 $0.175096；余限 $49.824904，实际账单未知。原预留累计值不是实际支出。脚本浏览器回归的 124 次实际 transition 另占原 4000 上限，故后续 live 账本上限收紧为 3876（包含已承接 48 次），没有扩预算。

这是针对前任务工程故障的同面板显式衔接，不是重跑已看过的图表轨迹或改变研究协议来挑结果。若后续模型/预算停止，仍保存未运行项；不切换为 Qwen-only、不增加任务、不继续开发机制。
