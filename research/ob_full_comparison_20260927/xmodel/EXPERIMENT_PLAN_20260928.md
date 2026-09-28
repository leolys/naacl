# 实验计划：误导可视化防御——静态面板跨模型比较（NAACL 2027 投稿支撑实验 P0-2）

日期：2026-09-28。执行环境：Lab Compute，1× A100-SXM4-80GB（81920 MiB）、500 GB 盘、1 TB 内存。
代码基线：`leolys/naacl` @ main（90e2c563），实验目录 `research/ob_full_comparison_20260927/`。

## 0. 定位与目的

本实验为投稿补齐两块缺失证据，并严格区别于原 2026-09-27 运行（`RUNTIME_SEAL.json` 封存、4×H100-80GB、vLLM 0.19.1/torch 2.10.0+cu128）：

- **R1（协议复刻）**：用原模型 `Qwen/Qwen3.8-27B` 在新硬件/新服务栈上复刻 140×6 比较，检验结论的可移植性（原报告承认"未在新机器上验证"）。
- **R2（跨模型泛化）**：用第二模型 `Qwen/Qwen3-VL-8B-Instruct`（小一个数量级）重跑同一面板，检验 v5 净收益是否跨模型成立。这是审稿人必然要求的证据。
- **R3（协议准备）**：产出与旧协议逐字段区分的可移植 runner 与评分器，供在线状态化实验（P0-1）复用。

不在本轮范围：网页导航/真实提交实验（P0-1）、held-out 家族切分实验（P1-3）、等预算普通重读对照（P1-4）。这些在在线实验计划中单列（§6）。

## 1. 实验矩阵

| 维度 | 取值 | 说明 |
|---|---|---|
| 模型 M1 | `Qwen/Qwen3.8-27B` | 原实验模型；BF16 权重 ~54 GB；多模态（vision_config 存在），与原 `service_config.json` 一致 |
| 模型 M2 | `Qwen/Qwen3-VL-8B-Instruct` | 第二模型；`Qwen3VLForConditionalGeneration` |
| 配置 | plain, v3, v4, v5, v6, v7 | 提示文件 `prompts_{version}.py` 逐字复用，不改一个字 |
| 任务 | 140 固定单图任务（`manifest.json` units） | 输入投影 `data/<unit>/input.json` 与图片逐字节校验（sha256） |
| 解码 | temperature 0.7, top_p 0.8, top_k 20, seed 12345, enable_thinking=false（仅 M1） | 与原 `config.json` 一致；同 seed 不保证确定性，如实声明 |
| 输出上限 | read 1500 / verify 3600 / decide 700 / control 64 token | 同原 |
| 服务 | vLLM OpenAI server，BF16，TP=1，`--max-model-len 16384`，`--max-num-seqs 16`（提速改动；原协议为每副本 1），`--max-num-batched-tokens 4096`，`--gpu-memory-utilization 0.88`，`--limit-mm-per-prompt {"image":1,"video":0}`，`--mm-processor-kwargs {"max_pixels":1605632}`，`--enforce-eager` | 与原 `service_config.json` 参数一致处：dtype/TP/ctx/mm 上限/eager/显存利用率；差异处如实声明 |
| 每模型预算 | plain 140 + 5×420 = **2240** 次主请求 + 1 次非图表控制 | 与原 2236+控制 同量级 |

执行顺序：先 M2（下载快，先验证全链路），后 M1（复刻）。若 M1 架构（`Qwen3_5ForConditionalGeneration`）不被当前 vLLM 支持，降级方案：改用 `Qwen/Qwen3-VL-30B-A3B-Instruct` 并在报告中如实记录降级。

## 2. 与原协议的差异（必须写进论文实验节）

1. 硬件：1×A100-80GB 串行 vs 原 4×H100-80GB 四副本并行。序列内串行性（max_num_seqs=1、每单元阶段顺序）保持；wall-time 不同。
2. 服务栈：按 Lab 环境安装的 vLLM/transformers 版本记录（`runtime_identity.json` 留档）；结构化输出参数做一次兼容性探测并记录所用参数形态。
3. 不沿用旧 `RUNTIME_SEAL.json`、旧端口、旧 GPU UUID 与旧授权；本轮自建 `runtime_identity_xmodel.json` 与独立 seal。
4. 本轮结果目录与旧 capture 完全分离；绝不回写旧 manifest/评分。
5. 并发与超时：runner 并发 16（原引擎串行）、HTTP 读超时 900 s（原 300 s；A100 上尾部 verify 单请求实测可超 300 s，属传输层参数，非解码参数）。两者已在本文件与 `runtime_identity_xmodel.json` 中如实声明。

## 3. 指标定义（冻结；与 `evaluate.py` 逐字一致以保证可比性）

对每对 (配置 c, 模型 m)，任务 t 的终态由 `state(result, label)` 给出：

- `interface_failed`：输出截断或结构校验被拒（保留在分母内）；
- `not_completed`：单元未到终态（目标为零）；
- `no_option`：有效返回 null；
- `target`：choice.option_label == 原正确标签；
- `trap` / `other`：非空选项按 `alignment_role == 'misleading_trap'` 二分。

**主指标（全分母，失败不删除）**

- A(c,m) = |{t: state=target}| / 140（原标签相合率；明示"不是 O/B 语义核验正确率"）。
- Δ(c,m) = A(c,m) − A(plain,m)：同模型内相对普通方案的净增（主表）。
- 配对转移矩阵（同模型 plain vs c，140 任务逐条）：`target_maintained`、`wrong_to_target`、`target_to_wrong`、`null_or_failure_to_target`、`target_to_null_or_failure`、`other_transition`，并给精确转移表。
- **统计推断**：Δ 的显著性用 McNemar 精确检验（b=wrong_to_target 对 c=target_to_wrong，双侧）；Δ 的 95% CI 用任务级 bootstrap（B=10000）。两个数字都报告，不挑其一。

**分层报告**

- 领域：business47 / environment35 / health19 / public39（固定分母 47/35/19/39）。
- 21 家族分组（含变式扩展；明示"分组数 ≠ 独立机制数"）。
- panel：dev24 / 其余116（提示迭代史只在 dev24 上发生，如实披露）。

**成本**

- 每配置 attempts、prompt/completion/total tokens、已知请求秒合计；控制请求单列；接口失败计入用量。

**边界声明（报告固定段落）**

- 标签相合不是语义正确率；env007 型"相合但理由跳步"用案例节呈现，不计入额外分数。
- v3 schema 与 v4–v7 不同，接口差异本身就是报告对象之一。
- 不做逐题择优拼接；不事后改 gold；本轮不宣称未见泛化。

## 4. 阶段与验收

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| P0 | 交接校验 | `tools/validate_handoff.py` passed（已完成：140 配对/280 实例/757 资产/3394 哈希） |
| P1 | 环境：venv + vLLM + 双模型落盘（~70 GB） | vLLM 导入成功；两模型目录含 index 与全部 shard |
| P2 | 服务冒烟 | /health 200；blank.png 控制请求返回 `{"ready":true}`；2 个任务 plain 试跑通过 schema 校验 |
| P3a | M2 全 6 配置 2240 请求 | 840 单元全部终态（completed/interface_failed），0 未知传输 |
| P3b | M1 全 6 配置 2240 请求 | 同上 |
| P4 | 评分与对比表 | 双模型 × 6 配置主表、转移矩阵、McNemar+bootstrap、领域/家族/panel 分层、成本表；`eval_xmodel.py` 输出与新旧两轮并列的对比 JSON |
| P5 | 报告 | `REPORT_XMODEL_20260928.md`：结论先行 + 边界声明，格式对齐原 REPORT |

断点与容错：runner 按 `result.json` 存在性断点续跑；已存在请求永不重放；HTTP 非瞬态错误即停并保存失败分类（沿用原引擎纪律，但独立实现）。

## 5. 论文对应的表格

1. 主表：6 配置 × 2 模型 A(c,m) 与 Δ（对应论文 Table 2 扩展）。
2. plain↔v5 转移矩阵（双模型并列；支撑"防御波动"动机）。
3. 领域分层表（含环境域负收益，如实保留）。
4. 成本表（token 与请求数）。
5. （在线实验完成后）任务成功率 + 重复错误抑制表——见 §6。

## 6. 在线状态化实验计划（P0-1，本轮仅冻结定义，不运行）

- 设置：`web_agent_benchmark` 真实环境，40–60 任务 × 双图臂 × ≥2 系统（actor=Qwen3.8-27B 本地服务 + 1 个 API 模型），v2 协议（门禁区分 refuted/unresolved；流程链与视觉链分权；不强制改选）。
- 主指标：
  - 任务成功率（原服务器评分收据，非 actor 自述）；提交率；
  - 错→对 / 对→错翻转矩阵（相对普通 Agent 同任务配对）；
  - **重复错误抑制率**：状态存在后，同一图表解释在前 k 步被纠正、且未在后续步骤被再次推翻的比例；
  - 规则状态统计：active/revoked/pending/disputed 数量分布、复核触发次数、版本更新次数；
  - 成本：每轨迹 actor/verify 调用数与 token。
- 统计：同静态面板（McNemar 配对 + bootstrap CI），按 dev24/其他 与双臂分层。

## 7. 资源与授权

GPU：仅本卡（A100 index 0），独占使用；模型仅 HF 官方权重；无付费 API（本轮静态面板全部本地服务）。在线实验（P5）若涉及 API 模型，另行申请密钥与预算。
