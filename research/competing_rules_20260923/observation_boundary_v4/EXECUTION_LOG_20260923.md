# 执行记录：观察边界修订

这是对用户指出的O/B/C混层问题的有界开发诊断，不接续或覆盖旧面板。没有下载模型、调用其他服务或使用GPU。

## 改动与保留

- 新增 `../prompts_observation_v4.py`，生成器和核验器共享通用观察边界。
- `../engine.py` 增加显式提示选择；缺省仍是原版。原解析、候选顺序上限、规则状态、执行器不改。
- `../run_demo.py` 的额外核验也读取同一提示配置。
- `../configs/demo.json` 选择v4；这不表示其完整面板已重跑。
- 上述改动前文件及README在 `before_change/`；旧请求、输出、评分和ZIP未更改。
- `run_check.py` 是独立五例模块诊断入口，保留自然提案与配对输入，不执行提案或建议。

## 先测与审查

采用experiment-bridge的先测试、独立上下文子Agent运行前审查。初审发现“规则不能证明另一条规则”未明确禁止自证、以及单一rule_id与多规则引用措辞不一致，均作提示级最小修正。详见 `PREDEPLOY_REVIEW.md`；审查不是人工或跨模型家族背书。

首次新增mock测试因测试夹具没有声明chart_1而失败，生产校验器正确拒绝；仅补齐夹具中的图像引用，未放宽生产校验。初次失败XML保留在 `unit_tests_initial_fixture_failure.xml`。

最终离线命令（工作目录为本项目根目录）：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
.\.venv\Scripts\python.exe -m pytest tests_engine.py tests_format.py tests_adapter.py tests_resume.py observation_boundary_v4/tests_prompts.py observation_boundary_v4/tests_run_check.py -q --junitxml=observation_boundary_v4/unit_tests_final.xml
```

结果：42 passed、1 skipped、17条既有依赖弃用警告。跳过项为需显式启用的浏览器回归；本条命令没有调用模型。结构测试不能证明O的语义纯净、图像读取准确或研究有效性。

## 固定真实运行

工作目录：`D:/ths_Viswork/research/competing_rules_20260923`。已授权公司凭据仅通过进程环境变量MODEL_API_KEY传入，执行后清除，不写入请求档案。

```powershell
.\.venv\Scripts\python.exe observation_boundary_v4/run_check.py --config observation_boundary_v4/config.json --output observation_boundary_v4/runs/paired_v4_20260923
```

固定5例×旧/新两套提示，每模块生成＋核验两次；新增2例各1次普通Actor提案。预计22次请求，60次尝试/30次浏览器操作硬上限；串行，传输失败有限重试，不按答案重试。运行版本、配置、完整请求/响应、配对图像、推荐、规则状态和预算均在输出目录。

所有模块结束后才离线核对原标签。没有真实业务提交；规则状态未被后续Actor读取。最终实测计数以 `COST_AND_WIRE_AUDIT_20260923.json` 及运行 `completion.json` 为准，不以计划调用数冒充已运行成本。
