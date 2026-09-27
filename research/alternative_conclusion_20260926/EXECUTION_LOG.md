# 执行记录与复核命令

2026-09-26。以下为本轮实际入口、参数及结果的整理，不是再次运行许可；输出目录和两个启动锁已存在，runner禁止覆盖重跑。

## 本地静态与单元测试

工作目录 `D:\ths_Viswork`，使用现有项目虚拟环境，不修改原Conda环境：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
& 'D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe' -m pytest research/alternative_conclusion_20260926/tests -q --junitxml=research/alternative_conclusion_20260926/offline_tests_final.xml
```

结果：**58 passed in 0.73s**，退出码0。阶段性33/47/49/57项记录保留，不用最终报告覆盖旧记录。新增阅览器检查后为58项。单元测试没有模型调用。

## 远程执行入口

使用原SSH别名`hexin_2007_K_root`。新代码只上传到本轮独立目录，不覆盖项目runner或旧实验结果。

远程浏览器Python及环境前缀：

```bash
env PYTHONDONTWRITEBYTECODE=1 \
PLAYWRIGHT_BROWSERS_PATH=/mnt/data/lys/model_services/qwen3_8_27b/browsers \
LD_LIBRARY_PATH=/mnt/data/lys/model_services/qwen3_8_27b/browser_libs/usr/lib/x86_64-linux-gnu \
/mnt/data/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python
```

1. **只读服务/浏览器预检**：上述Python后接以下入口及参数。通过；0推理、16浏览器操作，回执`preflight_001/receipt.json`。

```text
/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/preflight.py
--project /mnt/data/lys/CognitiveHijacking_CognitiveDenial
--output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/preflight_001
--historical /mnt/data/lys/model_services/qwen3_8_27b/validation/browser_pair_20260926_110903
```

2. **原live启动**：上述Python加`-u`运行本轮`runner.py`，参数：

```text
--project /mnt/data/lys/CognitiveHijacking_CognitiveDenial
--output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/run_live_001
```

结果：两arm首页请求返回后均因缺jsonschema而在动作验证处失败；2请求尝试、累计18浏览器操作。没有执行任何模型动作，没有看到图表，没有提交。退出状态不能代替逐arm结果，失败工件完整保留。

3. **纯工程修复后响应复用续接**：同一runner入口及环境，参数：

```text
--project /mnt/data/lys/CognitiveHijacking_CognitiveDenial
--output /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/run_live_002
--resume-infra-run /mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/run_live_001
```

结果：退出码0，summary.status=finished，八分支均真实完成；最终总账27请求、58浏览器操作。不是从零再跑一次：首页复用原2响应、旧成本整体继承。详见`INFRA_FIX.md`。

4. **结束检查**：`ps -p 316818,319282,282313 -o pid,lstart,args`、`nvidia-smi`、本机服务`/health`与`/v1/models`。健康200、原PID身份仍在；没有控制模型或占卡进程。整理见`FINAL_RESOURCE_CHECK.md`。

## 下载与离线审计

```powershell
scp -r hexin_2007_K_root:/mnt/data/lys/CognitiveHijacking_CognitiveDenial/research/alternative_conclusion_20260926/run_live_002 D:/ths_Viswork/research/alternative_conclusion_20260926/
& 'D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe' research/alternative_conclusion_20260926/analyze_run.py --run research/alternative_conclusion_20260926/run_live_002 --output research/alternative_conclusion_20260926/RESULT_AUDIT.json
```

退出码0。27请求、2响应复用事件、0HTTP重试；两次复用的完整输入仅state.url端口不同；方法图像与源快照哈希检查通过。独立子代理又直接比较了实际base64图片、请求文本和真实提交回执，不只依赖该脚本的结果。

## 单文件展示与浏览器QA

```powershell
& 'D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe' research/alternative_conclusion_20260926/build_review.py --run research/alternative_conclusion_20260926/run_live_002 --output research/alternative_conclusion_20260926/review_001 --notes research/alternative_conclusion_20260926/notes_zh.json
& 'D:\ths_Viswork\research\competing_rules_20260923\.venv\Scripts\python.exe' research/alternative_conclusion_20260926/qa_review.py --page research/alternative_conclusion_20260926/review_001/EXPLANATION_ALTERNATIVE_REVIEW.html --output research/alternative_conclusion_20260926/viewer_qa_001 --channel msedge
```

均退出码0。使用已安装Edge153.0.4234.48，无下载浏览器。11张唯一截图全部解码，缺失锚点0、远程请求0、页面错误0；1440宽桌面／390宽移动视口均无横向溢出。主代理查看了桌面总览、新反问部分及移动截图，中文正常。QA只打开本地静态HTML，与真实实验58次浏览器操作分开，模型请求0。

## 文件角色

- `run_live_001/`与`run_live_002/`：只读实验工件，包含精确runtime_source。
- 根目录`prompts.py`、`schemas.py`、`runner.py`、`preflight.py`、`config.json`、`PROTOCOL.md`：本轮实现；实际运行身份以各run源快照为准。
- `notes_*.json`、报告、审查及展示：运行后离线整理，不进入被测模型输入。
- `audit/browser_pair_20260926_110903/`：用户旧部署验证副本，与本轮成本分开，不假装是本轮独立复现数据。
- `review_001/PROVENANCE.json`：展示输入哈希和生成器身份。`RESULTS_FULL.json`将请求中的重复图片换成SHA引用，原完整base64请求仍保存在run中；HTML内嵌实际PNG。

不再次执行真实命令，不在旧目录追加模型调用，不以删启动锁方式重置预算。
