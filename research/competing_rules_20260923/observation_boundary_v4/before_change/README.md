# 三任务方法开发验证包

这是原140对任务上的方法适配与三个开发示例，不是已经完成的140对评测，也不是论文有效性证明。原始文稿在 METHOD_SOURCE.md。

## 阅读顺序

1. `refine-logs/EXPERIMENT_PLAN.md`：两项待证主张、正式对照矩阵、运行范围与限制。
2. `configs/demo.json`：当前v3接口的3×2×2配置，供独立新运行使用，最多150 API请求尝试和300浏览器操作，无GPU。v3没有重新跑整个面板；本轮v2完整面板使用`configs/demo_v2_remaining.json`，v3仅单独验证health004两条件，配置为`configs/health004_supplement.json`。
3. `panel140_manifest.json`、`configs/panel140_draft.json`：完整库的后续实验计划，不自动启动；消融尚未实现。
4. `DELIVERY_SUMMARY.md`：本次总说明。`DEMO_REPORT.md`和`examples/`固定展示v2完整面板；health004补充另列，绝不把补充成功替换原失败。`report_summary_v1.json`与`examples_v1/`保留v1。`INTERFACE_FIX_20260923.md`解释接口修复和失败重放。
5. `runs/`：完整请求、响应、截图、动作、核验、规则状态与真实提交回执。

## 数据与任务不变项

`data/case01..case06`依次为pub013原图/清洁图、health004原图/清洁图、b046原图/清洁图。图片逐字节复制；公开任务文字与选项原样保留，选项按文字排序去掉“正确总在首位”的旁路。`public.json`是被测模型允许获得的投影；`offline/`只供评分与来源审核，禁止把整份原spec放进prompt。

模型没有CSV、隐藏标签、另一arm、人工审核结论或指定证据框。b046原图没有打印柱值，读到的数值只能是图像估计。公开任务本身的提示不删、不加。health004保留已有审核状态，不冒称新人工确认。

页面是新的字段完整公开外壳，保留原公开附加字段和提交动作，不是原门户所有页面的复刻。真实浏览器完成选择、必填填写、POST及确认。主选项按原expected/misleading action映射评分；公开必填完成及附加文本字面匹配另列。`official_full_end_to_end_score=not_computed`不可改写成官方端到端成功率。

## 安装与运行

使用独立Python环境，不需本项目其他代码或GPU。本轮实际验证为Windows、Python3.9.13、已有Edge；requirements按本轮运行版本列出，未宣称最新Python或其他系统已验证。浏览器路径在配置中；可用现有Edge/Chrome，或自行安装Playwright Chromium并将路径设为null。凭据不随包提供。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:MODEL_API_KEY = Read-Host '输入已授权的公司API密钥'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:DEMO_BROWSER_EXECUTABLE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
.\.venv\Scripts\python.exe -m pytest tests_engine.py tests_adapter.py -q
.\.venv\Scripts\python.exe run_demo.py --config configs/demo.json --data data --output runs/your_new_run
Remove-Item Env:MODEL_API_KEY
```

配置中的代理是当前机器Clash端口。其他电脑按实际网络改为其代理，直连可设null。模型GET列表只说明目录存在；每次返回的model/usage路由均另存，不将别名当底层身份认证。输出目录必须新建，拒绝覆盖旧结果。仅网络、429及选定5xx可有限重试，不根据结果重跑或换模型。

API请求的图像顺序固定为原尺寸完整图、当前真实网页截图。设置temperature=0，不保证网关后端完全确定。只有普通actor真正输出submit才提交；核验仅改变选择，不会把建议伪造成submit。

## 如何看一次轨迹

`step_00/actor/request.json`是完整发送体（含图像base64），`context.json`是便于阅读的同一上下文及图像文件引用。`response_01.json`和`attempt_01.json`分别保存返回体和路由/耗时。首次图表选择的`defense/generate`、`normalized_candidates.json`、`defense/verify`可逐项检查竞争规则、图内证据及O/B/推导状态。`handoff.json`分开列推荐和实际改选。`browser/browser_history.jsonl`只记真正执行动作及回执；`submission_receipts.jsonl`是服务端POST收据。最后`offline_results.json`才合入gold评分。

状态保存规则与证据，不存固定动作答案；动作在独立历史记录。原任务主要只有一次语义判断，后续填写、提交和规则读取日志不是独立的再次判断，不能据此报告“防回退成功率”。

原批次v1与修复版v2分别完整运行同样12条轨迹，不能合为24个独立样本或择优组合。v1有5条因接口容器/观察引用问题未完成；修复后是从初始页重新开始的统一工程复核，不是旧状态续跑。一次零API重放因文字渲染像素不同而中止，未降低一致性要求。`resume_interfaces.py`仅离线测试，未用于真实模型续跑。

`configs/demo.json`不代表140任务已实现。全量配置当前disabled，六个正式对照的编排、去组件及等信息记忆尚未实现；本包具备三任务普通/完整方法的实际运行入口。三任务全部图像、公开投影和离线原spec均已随包提供，不依赖远端项目。完整140清单保留原数据路径及哈希，完整280张图像没有重复打包；将来全量运行仍需要原库。

仅重现已定义的两条件工程补充时使用下面的独立入口，不会启动12条面板；输出路径必须是未使用的新路径：

```powershell
.\.venv\Scripts\python.exe run_supplement.py --config configs/health004_supplement.json --data data --output runs/your_new_health_pair
```

离线测试不需要API。完整测试命令为 `python -m pytest tests_engine.py tests_format.py tests_adapter.py tests_resume.py -q`。浏览器工程测试需要显式设置浏览器环境变量及原库快照；包外缺失快照时该项会清楚标记跳过，而三个实际任务runner使用随包data不需原库。不要把测试脚本的手工动作当作模型结果。

本包使用experiment-plan组织主张—对照，使用experiment-bridge组织实现、先测与独立代码审查。代码审查为同模型家族的独立上下文审查，非跨家族证明。
