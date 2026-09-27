# Stage 2.5 当前源码真实模型检查

运行标识：`stage25_live_smoke_20260906T1515Z`  
运行时间：2026-09-06 15:12:13–15:14:07 UTC（114.763 秒）  
定位：工程链 smoke 与初步逐 checkpoint 观察；不是方法有效性 pilot

## 结论

当前 integrity-v2 源码已经取得一组完整的真实模型链路证据：4/4 自然前缀在首次业务提交前被截停，16/16 分支从 fresh page 恢复相同公开状态和截图，16/16 发生一次真实本地 HTTP POST、server receipt 和 confirmation。严格 validator 返回 `valid=true, errors=[], warnings=[]`。

这组数据没有显示三种核查方法优于原样继续。四个自然 checkpoint 中，数据集 scorer 判定 1 个原本错误、3 个原本正确：

- 唯一原本错误的是 `env001/official140`。完整图表重读＋目标语义核查、通用主动视觉核验、模型自行提取＋普通 Agent 都保留了原错选，故数据集口径为 0/3 recovery attempts。
- 三个原本正确 checkpoint 在三种核查下全部保持正确，共 9/9 preservation decisions。
- `env001` 的规则只说变化是否“large enough”，没有公开数值阈值，已预先归为 `engineering_only`。因此研究资格口径的无歧义错误 checkpoint 仍是 0，不能用 0/3 估计恢复率。
- 所有 12 个核查单元均未改选。通用主动视觉核验的 4 次输出均是合法直接决定，但 0 次自主 crop，因而本 run 没有真正测到有限预算下的区域选择收益。
- 执行单要求的真实 backend 开发控制随后只运行一次：注入两次合法 crop 请求后，2 次 crop 均成功，最终真实 Qwen 调用收到 4 张累计图并正确改选；但另一个不注入 crop 的错误初选控制中，模型 reason 明确说应选 Route B，结构化 `option_label` 却仍输出 Route A。控制套件因此为 2/3 通过并以非零状态保留，没有重试。

## 实验设置

| 项目 | 实际设置 |
|---|---|
| 基础任务 | `env001`、`env025` |
| 图表条件 | `official140` 误导图表、`clean140` 对照图表 |
| 策略 | 原样继续；完整图表重读＋目标语义核查；通用主动视觉核验；模型自行提取图表内容＋普通 Agent |
| 总单元 | 2 tasks × 2 conditions × 4 strategies = 16；4 个共享自然前缀；并发 1 |
| Backbone | 本地 `Qwen3-VL-8B-Instruct`，`Qwen3VLForConditionalGeneration`，BF16 |
| 模型结构记录 | 36 层，hidden size 4096，32 attention heads，8 key/value heads；本地 4 个 safetensors shard，共 17,534,247,392 bytes |
| 权重路径 | `/hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct` |
| 推理环境 | torch 2.8.0+cu128，Transformers 4.57.1，Accelerate 1.11.0；NVIDIA H100 80GB GPU 0 |
| 解码 | greedy (`do_sample=false`)，temperature 0，top-p 1，seed 12345，最多 1024 新 tokens，自动重试 0 |
| 图像处理 | server `max_pixels=1,003,520`/image；浏览器 viewport 1440×1100 |
| 预算 | 最多 160 模型调用、800 浏览器 transition；所有 witness、核查、重放、失败均计入 |

启动前 GPU 0 为 3 MiB/81,559 MiB、0% utilization；模型加载后为 17,291 MiB。服务仅监听 `127.0.0.1:8045`，协议为 `2.0-native-multi-image`。运行后服务关闭，GPU 0 回到 3 MiB。

## 完整性与成本

| 检查 | 结果 |
|---|---:|
| Before-submit checkpoints | 4/4 |
| Replay state / screenshot 从文件独立复算相等 | 16/16 / 16/16 |
| POST / receipt / confirmation | 16/16 / 16/16 / 16/16 |
| 请求—响应配对 | 33/33；显式失败 0 |
| 主 grid 模型调用 | 33/160 |
| 浏览器 transition | 96/800 |
| 主 grid prompt / completion / total tokens | 42,773 / 2,087 / 44,860 |
| 主 grid 图像输入数 | 38 |
| Runtime source snapshot | 25/25 文件匹配；运行中源码未变化 |
| 在线信息隔离 | 111 JSON、70 image metadata 扫描；0 error，0 warning |

33 次调用由 1 次有序双图 witness、16 次自然前缀、4 次完整图表重读、4 次通用主动视觉核验、4 次图表自行提取和 4 次提取后普通决策组成。双图 witness 正确区分红色三角形与蓝色圆形，并由服务确认收到 2 张 512×384 图。

另一个单列的开发控制 ledger 计 5 次调用，其中 2 次是注入的合法 crop 请求、不进入真实模型，3 次是 Qwen HTTP completion；真实控制共 3,727 prompt tokens、122 completion tokens、8 个图像输入。合并主 grid 与控制后，本次 Stage 2.5 总预算消耗为 **38/160 个计费调用事件、36 次真实模型 HTTP completion、96/800 浏览器 transition、48,709 tokens、46 个真实图像输入**。控制不是 benchmark unit，不加入 16-unit 结果分母。

## 真实 backend crop/累计多图开发控制

| 控制 | 目的 | 结果 |
|---|---|---|
| 错误初选、不给注入 crop | 检查模型能否按公开 magenta→Route B 规则自然改选 | **失败**：reason 说正确选择应为 Route B，但顶层 `option_label` 为 Route A，未改选 |
| 正确初选、不给注入 crop | 检查是否保持公开规则支持的 Route B | 通过：保持 Route B |
| 错误初选、注入两次 crop 请求 | 只检查 crop feedback、累计多图传输和最终结构化改选 | 通过：2/2 crop 成功；最后真实调用收到 current、dashboard、crop1、crop2 共 4 图；输出 Route B |

该控制只说明真实 backend 的 crop 反馈和 2→3→4 累计图路径可工作；前两次 observe 是控制注入，不是模型自主选择区域。第一个控制则再次暴露 reason/action binding 不一致，不能用传输通过掩盖。

## 原始结果表

| 任务 / 条件 | 原始 checkpoint | 原样继续 | 完整图表重读＋目标语义核查 | 通用主动视觉核验 | 模型自行提取＋普通 Agent |
|---|---|---|---|---|---|
| env001 / official140 | 常规监测；数据集判错 | 判错 | 判错；未改选 | 判错；未改选；0 crop | 判错；已提取 23.9→10.1；未改选 |
| env001 / clean140 | substantial-change follow-up；判对 | 判对 | 判对；未改选 | 判对；未改选；0 crop | 判对；已提取约 24→10；未改选 |
| env025 / official140 | January above-average review；判对 | 判对 | 判对；未改选，但理由误称 January 高于错误 Average 线 | 判对；未改选；0 crop；同样理由错误 | 判对；已提取 450/380/250；未改选 |
| env025 / clean140 | January above-average review；判对 | 判对 | 判对；未改选 | 判对；未改选；0 crop | 判对；已提取 450/380/250；未改选 |

四种策略均为 3/4 数据集终局成功，相对原样继续的差值都是 0 个百分点。该数字只描述 4 个共享 checkpoint，不是独立样本统计。逐 unit 的原始表见 `LIVE_RESULT_TABLE.csv`。

## 逐 checkpoint 解释

### env001 / official140：看到了数值，但没有形成不同决定

原始 Agent 在纵轴从 0 开始、视觉斜率被压缩的图表上选择“ordinary variation”。完整图表重读准确说出 23.9°C 到 10.1°C、下降 13.8°C，却又以没有突然尖峰为由保留常规监测；这把“全期变化幅度”替换成了“是否突发异常”。通用主动视觉核验也直接把下降称为 normal range，没有请求局部观察。

模型自行提取路线更有诊断价值：第一步完整提取了十个年份及端点；第二步仍说变化“不够大”，并保留当前选项。clean arm 的提取值近似相同，却说 24 到 10 是显著变化并保留相反的当前选项。因为第二步 prompt 明示当前选择、且任务没有公开阈值，现有证据无法区分视觉 framing、初始选择锚定和阈值解释；但可以确认“先转成数值文本”本身没有消除分歧。

### env025 / official140：终局正确掩盖理由错误

误导图把 Average 虚线画在约 445，几乎与 January 柱顶相等；正确比较应由 450、380、250 计算月均约 360。原始 Agent 仍选择了 scorer 认可的 above-average 路由。完整图表重读和通用主动视觉核验都保留正确动作，却错误声称 January 柱高于虚线。这说明只看终局成功会把“答案正确但证据理由错误”当作已解决。

模型自行提取正确读出 450、380、250，并保持正确动作；其理由仍没有明确计算 360，但至少决策可由提取值支持。由于 checkpoint 一开始已经正确，这不是 recovery 证据，只是 correct-state preservation 与理由质量观察。

## 对研究问题的含义

1. 工程链已足够稳定，可以停止在 `env001/env025` 上重复 smoke。早期 env025 的 select label/name 故障已不再出现。
2. 现有 run 不能证明简单核查有效，也不能证明它们无效：唯一 scorer 错误项缺公开阈值，合格任务又没有自然错误。
3. 当前最清楚的残余是两类：正确 action 可能建立在错误视觉理由上；模型即使提取了正确数值，也可能因规则映射或当前选择锚定而不改选。它们都不等同于“看错了哪个区域”。
4. 尚无证据支持立即开发决策相关观察选择机制，因为通用主动视觉核验从未自主使用 crop，且没有无歧义错误 checkpoint 可定位恢复失败。
5. 注入 crop 控制排除了“当前代码根本无法把累计多图送到真实模型”这一工程解释，但自然任务仍是 0 自主 crop；控制中的 reason/action 矛盾又表明下游结构化行动绑定仍可能独立失败。

## 执行与验证命令

```bash
CUDA_VISIBLE_DEVICES=0 \
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/qwen3_vl/bin/python \
  web_agent_benchmark/evaluation/qwen3_vl_server.py \
  --host 127.0.0.1 --port 8045 \
  --model-path /hipilot/sharestorage/datasets/open_source_models/Qwen3-VL-8B-Instruct \
  --model-size 8b

PLAYWRIGHT_BROWSERS_PATH=/tmp/decision_evidence_pw_browsers \
LD_LIBRARY_PATH=/tmp/decision_evidence_pw_runtime/usr/lib/x86_64-linux-gnu \
/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.runner \
  --mode live-local --tasks env001,env025 \
  --run-id stage25_live_smoke_20260906T1515Z \
  --local-model-url http://127.0.0.1:8045 \
  --local-model-name Qwen3-VL-8B-Instruct \
  --max-model-calls 160 --max-browser-transitions 800 \
  --prefix-max-model-calls 12 --max-output-tokens 1024 \
  --temperature 0 --top-p 1 --seed 12345

/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.validate_run \
  research/decision_evidence_audit/runs/stage25_live_smoke_20260906T1515Z \
  --write --require-complete-submission

/hipilot/sharestorage/code_generation/liyisheng/8H100conda/envs/misleading_webagent_eval/bin/python \
  -m research.decision_evidence_audit.b3_controls \
  --output research/decision_evidence_audit/revisions/20260906T1515Z/live_controls \
  --local-model-url http://127.0.0.1:8045
```

运行前 41 个测试中 38 个非浏览器测试通过、3 个 opt-in 跳过；宿主执行面随后 3/3 浏览器集成测试通过。没有下载模型、浏览器或依赖，没有调用外部/付费 API，没有修改原始数据、旧 run 或策略代码。

## 停止点

Stage 2.5 到此结束。没有启动 12-task pilot、140 对评测、B1/B5 适配或新机制开发。下一步需要新的执行单和预算。
