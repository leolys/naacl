# 运行与复查入口

先打开 `ONLINE_DEFENSE_REVIEW.html`：单文件、图片内嵌、离线可读，不需要项目、Python 或 API key。`REPORT.md` 与 `EVIDENCE.json` 是对应规范记录。中文导读为离线整理，英文原输出保留。

## 本轮已经做了什么

固定 3 基础任务 × 2 图表条件 × 2 系统，共 12 条真实 API 开发轨迹。另有 1 条单独 JSON 类型接口调试，不替换原面板。

原普通与方法完整请求、响应、原生网页截图和 POST 收据在 `live_v1/`。规则在各方法单元的 `rule_state_v1.json`；尚未产生规则的失败单元不会伪造状态文件。`live_budget.json` 合并控制、失败与调试成本。

## 本机环境与零请求检查

在 `D:\ths_Viswork` 运行：

```powershell
$py = 'D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
& $py -m pytest --import-mode=importlib research/online_defense_20260925/tests research/explanation_completion_20260925/tests -q
& $py research/online_defense_20260925/collect_evidence.py
```

`--import-mode=importlib` 避免两个历史测试目录中的同名 `test_runner.py` 相互遮蔽。不删除历史测试、不更改已有环境。旧 Flask/itsdangerous 有三条弃用告警，不代表测试失败。

已有原始环境镜像为 `runtime_snapshot/`；它保留原应用代码与资产，仅补回原缺失的两张 pub005 图片。恢复证据在 `asset_recovery/provenance.json`。不重新生成或替换图表。

## 280 条任务条件的批量准备

```powershell
& $py research/online_defense_20260925/batch_main.py --mode prepare --config research/online_defense_20260925/batch_config.template.json --output research/online_defense_20260925/batch_prepared_v2
```

该命令只做准备，不调用模型、不启动浏览器。输出含 140 个基础任务 × 2 条件的清单；两系统共 560 条计划轨迹，而不是已跑 560 条。目录若已存在会拒绝覆盖。

模板预算为空、协议名是 `preparation_only`，不能直接作为 live 配置。没有新的授权不能启动 140 对。批量准备完成也不代表该原型的研究效果达标。

## 未来获得明确授权后的入口（本轮未执行）

1. 复制模板到新配置文件，设置此次明确授权的请求、浏览器操作和估算费用总限额；保留串行、无 GPU。协议名改为 `online_explanation_completion_v2_batch_live`。完整任务 ID、图表条件、系统、模型、端点和动作上限必须事先固定。
2. 新建单独授权文件，`authorized` 为 true，并填写真实用户批准依据。其 `protocol`、`endpoint`、`model`、展开后的 `task_ids`、`arms`、`systems`、三个总限额、`max_actor_calls`、`max_reverification` 和 `interface_version` 必须与最终配置逐项相同。不能使用本轮旧授权。
3. API key 只设置到当前进程的 `MODEL_API_KEY` 环境变量，不写进 JSON、代码、压缩包或报告。
4. 用新输出目录运行。不要覆盖 `live_v1` 或接口调试。

```powershell
# 仅在新的范围/预算已获用户授权、对应文件已创建后使用。
try {
  & $py research/online_defense_20260925/batch_main.py --mode live --config research/online_defense_20260925/authorized_config.json --authorization research/online_defense_20260925/authorized_scope.json --output research/online_defense_20260925/new_authorized_batch
} finally {
  Remove-Item Env:MODEL_API_KEY -ErrorAction SilentlyContinue
}
```

恢复时加 `--resume`，必须使用相同配置、原授权、原账本与未改变的冻结源码/资产。已结束的成功或失败单元均跳过；半条轨迹、未知请求结果、来源变化不会自动重放或偷偷重开账本。需要人为处理时先保留当前记录、查明原因，再另行决定新版本。

预算预留、估算费率、每阶段输出 token 和传输重试配置不允许在批量 override 中修改。不得通过降低记账费率、关闭预留或增加重试来绕过名义上限。金额仍只是估算，不是账单保证。

## 冻结与打包边界

v1 记录的源文件和原结果不变。v1 早期源快照未完全收录传递导入的格式/用量辅助模块，报告已披露；后续版本收录实际导入的项目源。压缩包中的现存辅助文件不能倒推成已经证明 v1 运行时完全一致。

包内 `research/` 与 `.aris/task_flows_20260924/` 的相对目录需保留。浏览器可读展示不需要依赖；重新执行代码需要 Python、Flask、BeautifulSoup、requests、Playwright 与 Chromium/Edge。`runtime.json` 记录本轮具体版本。没有自动安装包、下载模型或占用 GPU 的步骤。

## 当前研究建议

先查看失败样本和 `reviews/CLAIMS_FROM_RESULTS.md`。本轮不是成功率达标验收，也没有证明持久化收益；不要因为批量入口可用就立即扩为论文主实验。后续任何语义协议调整应独立版本、预先选定样本和预算，不把旧失败替换成新成功。
